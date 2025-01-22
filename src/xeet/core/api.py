from . import TestCriteria
from .xtest import Xtest, XtestModel
from .xres import (TestResult, TestPrimaryStatus, TestSecondaryStatus, RunResult, TestStatus,
                   EmptyRunResult, MtrxResult)
from .driver import XeetModel, xeet_init
from .run_reporter import RunNotifier, RunReporter
from .matrix import Matrix
from xeet import XeetException
from timeit import default_timer as timer
from enum import Enum
from xeet.log import log_info, log_verbose
from threading import Condition, Thread, Event


def fetch_xtest(config_path: str, name: str, setup: bool = False) -> Xtest | None:
    ret = xeet_init(config_path).xtest(name)
    if ret is not None and setup:
        ret.setup()
    return ret


def fetch_tests_list(config_path: str, criteria: TestCriteria) -> list[Xtest]:
    log_verbose(f"Fetch tests list cirteria: {criteria}")
    return xeet_init(config_path).xtests(criteria)


def fetch_groups_list(config_path: str) -> list[str]:
    config = xeet_init(config_path)
    return list(config.all_groups())


def fetch_test_desc(config_path: str, name: str) -> dict | None:
    return xeet_init(config_path).test_desc(name)


def fetch_config(config_path: str) -> dict:
    return xeet_init(config_path).xdefs.defs_dict


class SchemaType(str, Enum):
    CONFIG = "config"
    XTEST = "test"
    UNIFIED = "unified"


def fetch_schema(schema_type: str) -> dict:
    if schema_type == SchemaType.CONFIG.value:
        return XeetModel.model_json_schema()
    if schema_type == SchemaType.XTEST.value:
        return XtestModel.model_json_schema()
    if schema_type == SchemaType.UNIFIED.value:
        d = XeetModel.model_json_schema()
        d["properties"]["tests"]["items"] = XtestModel.model_json_schema()
        return d
    raise XeetException(f"Invalid dump type: {schema_type}")


class _TestsPool:
    def __init__(self, tests: list[Xtest], threads: int) -> None:
        self._base_tests = tests
        self.threads = threads
        self._tests: list[Xtest] = []
        self.condition = Condition()
        self.abort = Event()
        self.reset()

    def stop(self) -> None:
        self.abort.set()
        with self.condition:
            self.condition.notify_all()

    def next_test(self, runner_name: str) -> Xtest | None:
        with self.condition:
            while True:
                if self.abort.is_set():
                    return None
                test, busy = self._next_test(runner_name)
                if busy:
                    log_info(f"{runner_name}: No obtainable tests, waiting")
                    self.condition.wait()
                    log_info(f"{runner_name}: Woke up")
                    continue
                return test

    def _next_test(self, runner_name: str) -> tuple[Xtest | None, bool]:
        if len(self._tests) == 0:
            return None, False
        for i, test in enumerate(self._tests):
            log_info(f"{runner_name}: Trying to get test '{test.name}'")
            try:
                test.set_runner_id(runner_name)
                #  if test.error is set, it means that the test is not runnable
                #  and should be skipped. No need to check for resources.
                if not test.error and not test.obtain_resources():
                    test.set_runner_id()
                    continue
                if i > 0:
                    busy_tests = self._tests[0:i]
                    self._tests = self._tests[i:]
                    if len(self._tests) < self.threads:
                        self._tests.extend(busy_tests)
                    else:
                        self._tests = self._tests[0:self.threads] + busy_tests + \
                            self._tests[self.threads:]
                log_info(f"{runner_name}: got '{test.name}'")
                return self._tests.pop(i), False
            except XeetException as e:
                log_info(f"Error occurred during test '{test.name}': {e}")
                test.error = str(e)
                return test, False  # return the test with error, will become a runtime error
        return None, True

    def release_test(self, test: Xtest) -> None:
        with self.condition:
            test.release_resources()
            self.condition.notify_all()

    def insert(self, test: Xtest) -> None:
        if len(self._tests) < self.threads:
            self._tests.append(test)
        else:
            self._tests.insert(self.threads, test)

    def reset(self) -> None:
        self._tests = self._base_tests.copy()


class _TestRunner(Thread):
    runner_id_count = 0
    runner_error = Event()

    @staticmethod
    def reset() -> None:
        _TestRunner.runner_error.clear()
        _TestRunner.runner_id_count = 0

    def __init__(self, pool: _TestsPool, notifier: RunNotifier, mtrx_res: MtrxResult,
                 iteration: int) -> None:
        super().__init__()
        self.pool = pool
        self.notifier = notifier
        self.mtrx_res = mtrx_res
        self._stop_event = Event()
        self.runner_id = f"r{iteration}.{_TestRunner.runner_id_count}"
        _TestRunner.runner_id_count += 1
        self.error: XeetException | None = None

    def log_info(self, *args, **kwargs) -> None:
        log_info(f"{self.runner_id}:", *args, **kwargs, depth=1)

    def run(self) -> None:
        while True:
            if self._stop_event.is_set() or _TestRunner.runner_error.is_set():
                self.pool.stop()
                self.log_info("Stopping")
                break
            test = self.pool.next_test(self.runner_id)
            if test is None:
                self.log_info("No more tests, goodbye")
                break
            self.notifier.on_test_start(test)
            try:
                test_res = self._run_test(test)
                self.mtrx_res.add_test_result(test.name, test_res)
                self.notifier.on_test_end(test, test_res)
            except XeetException as e:
                self.log_info(f"Error occurred during test '{test.name}': {e}")
                self.error = e
                _TestRunner.runner_error.set()
            finally:
                self.pool.release_test(test)

    def _run_test(self, test: Xtest) -> TestResult:
        if test.error:
            return TestResult(TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr),
                              status_reason=test.error)

        start = timer()
        ret = test.run()
        ret.duration = timer() - start
        return ret


def run_tests(conf: str,
              criteria: TestCriteria,
              reporters: RunReporter | list[RunReporter],
              debug_mode: bool = False,
              threads: int = 1,
              iterations: int = 1) -> RunResult:
    log_info("Starting xeet session", pr_suffix="------------\n")
    if not isinstance(reporters, list):
        reporters = [reporters]
    driver = xeet_init(conf, debug_mode, reporters)
    notifier = driver.xdefs.notifier
    log_info(str(criteria))

    tests = driver.xtests(criteria)
    if not tests:
        return EmptyRunResult

    log_info("Tests run list: {}".format(", ".join([x.name for x in tests])))
    log_info(f"Using {threads} threads per iteration")

    matrix = Matrix(driver.model.matrix)
    run_res = RunResult(iterations=iterations, criteria=criteria, matrix_count=matrix.prmttns_count)
    log_info(f"Matrix permutations count: {matrix.prmttns_count}")
    notifier.on_run_start(run_res, tests)
    tests_pool = _TestsPool(tests, threads)

    for iter_n in range(iterations):
        iter_res = run_res.iter_results[iter_n]
        driver.xdefs.set_iteration(iter_n, iterations)
        notifier.on_iteration_start(iter_res, iter_n)
        if iterations > 1:
            log_info(f">>> Iteration {iter_n}/{iterations - 1}")
        for mtrx_i, mtrx in enumerate(matrix.permutations()):
            mtrx_res = iter_res.add_mtrx_res(mtrx, mtrx_i)
            driver.xdefs.xvars.set_vars(mtrx)
            if mtrx:
                log_info(f"Matrix permutation {mtrx_i}: {mtrx}")
            notifier.on_matrix_start(mtrx, mtrx_i, mtrx_res)
            _TestRunner.reset()
            runners = [_TestRunner(tests_pool, notifier, mtrx_res, iter_n) for _ in range(threads)]
            for runner in runners:
                runner.start()
            for runner in runners:
                runner.join()
            if _TestRunner.runner_error.is_set():
                log_info("Error occurred during run")
                first_error = next((r.error for r in runners if r.error), None)
                if first_error:
                    raise first_error
            tests_pool.reset()
            if mtrx:
                log_info(f"Matrix permutation {mtrx_i} results:")
            for status, test_names in mtrx_res.status_results_summary.items():
                if not test_names:
                    continue
                test_list_str = ", ".join(test_names)
                log_info(f"{status}: {test_list_str}")
                test_list_str = ", ".join(test_names)
                log_info(f"{status}: {test_list_str}")
            notifier.on_matrix_end()

        if iterations > 1:
            log_info(f"Finished iteration #{iter_n}/{iterations - 1}")
        notifier.on_iteration_end()
    notifier.on_run_end()
    return run_res
