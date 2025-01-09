from . import TestCriteria
from .xtest import Xtest, XtestModel
from .xres import TestResult, TestStatus, TestSubStatus, RunResult, IterationResult, status_as_str
from .driver import XeetModel, xeet_init
from .run_reporter import RunNotifier, RunReporter
from xeet import XeetException
from timeit import default_timer as timer
from enum import Enum
from xeet.log import log_info, log_blank, log_verbose
from threading import Lock, Thread, Event


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
    def __init__(self, tests: list[Xtest]) -> None:
        self.tests = tests
        self._index = 0
        self._lock = Lock()

    def get_next(self) -> Xtest | None:
        with self._lock:
            if self._index >= len(self.tests):
                return None
            ret = self.tests[self._index]
            self._index += 1
            return ret

    def reset(self) -> None:
        self._index = 0


class _TestRunner(Thread):
    runner_id_count = 0
    runner_error = Event()

    @staticmethod
    def reset() -> None:
        _TestRunner.runner_error.clear()
        _TestRunner.runner_id_count = 0

    def __init__(self, pool: _TestsPool, notifier: RunNotifier, iter_res: IterationResult,
                 iteration: int) -> None:
        super().__init__()
        self.pool = pool
        self.notifier = notifier
        self.iter_res = iter_res
        self._stop_event = Event()
        self.runner_id = f"r{iteration}.{_TestRunner.runner_id_count}"
        _TestRunner.runner_id_count += 1
        self.error: XeetException | None = None

    def log_info(self, *args, **kwargs) -> None:
        log_info(f"{self.runner_id}:", *args, **kwargs, depth=1)

    def run(self) -> None:
        while True:
            if self._stop_event.is_set() or _TestRunner.runner_error.is_set():
                self.log_info("Stopping")
                break
            test = self.pool.get_next()
            if test is None:
                self.log_info("No more tests, goodbye")
                break
            self.log_info(f"got test '{test.name}'")
            self.notifier.on_test_start(test)
            try:
                test_res = self._run_test(test)
            except XeetException as e:
                self.log_info(f"Error occurred during test '{test.name}': {e}")
                self.error = e
                _TestRunner.runner_error.set()
                break

            self.iter_res.add_test_result(test.name, test_res)
            self.notifier.on_test_end(test, test_res)

    def _run_test(self, test: Xtest) -> TestResult:
        if test.error:
            return TestResult(status=TestStatus.NotRun, sub_status=TestSubStatus.InitErr,
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
    if criteria.include_groups:
        groups_str = ", ".join(sorted(criteria.include_groups))
        log_info(f"Included groups: {groups_str}")
    if criteria.exclude_groups:
        groups_str = ", ".join(sorted(criteria.exclude_groups))
        log_info(f"Excluded groups: {groups_str}")
    if criteria.require_groups:
        groups_str = ", ".join(sorted(criteria.require_groups))
        log_info(f"Required groups: {groups_str}")

    tests = driver.xtests(criteria)
    if not tests:
        raise XeetException("No tests to run")

    log_info("Tests run list: {}".format(", ".join([x.name for x in tests])))
    log_info(f"Using {threads} threads per iteration")

    run_res = RunResult(iterations=iterations, criteria=criteria)
    notifier.on_run_start(run_res, tests)
    tests_pool = _TestsPool(tests)

    for iter_n in range(iterations):
        iter_res = run_res.iter_results[iter_n]
        if iterations > 1:
            log_info(f">>> Iteration {iter_n}/{iterations - 1}")
        driver.xdefs.set_iteration(iter_n, iterations)
        notifier.on_iteration_start(iter_res, iter_n)
        _TestRunner.reset()
        runners = [_TestRunner(tests_pool, notifier, iter_res, iter_n) for _ in range(threads)]
        for runner in runners:
            runner.start()
        for runner in runners:
            runner.join()
        if _TestRunner.runner_error.is_set():
            log_info("Error occurred during run")
            first_error = next((r.error for r in runners if r.error), None)
            if first_error:
                raise first_error

        if iterations > 1:
            log_info(f"Finished iteration #{iter_n}/{iterations - 1}")
        for status, sub_status in iter_res.status_results_summary:
            test_names = iter_res.status_results_summary[(status, sub_status)]
            if not test_names:
                continue
            test_list_str = ", ".join(test_names)
            log_info(f"{status_as_str(status, sub_status)}: {test_list_str}")
        notifier.on_iteration_end()
        tests_pool.reset()
    notifier.on_run_end()
    return run_res
