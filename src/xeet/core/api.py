from . import TestCriteria
from .xtest import Xtest, XtestModel
from .xres import TestResult, TestStatus, RunResult
from .driver import XeetModel, xeet_init
from .run_reporter import RunReporter
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
    return xeet_init(config_path).defs.defs_dict


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
        with self._lock:
            self._index = 0


class _TestRunner(Thread):
    runner_id_count = 0
    runner_error = Event()

    @staticmethod
    def reset() -> None:
        _TestRunner.runner_error.clear()
        _TestRunner.runner_id_count = 0

    def __init__(self, pool: _TestsPool, reporter: RunReporter, run_res: RunResult,
                 iteration: int) -> None:
        super().__init__()
        self.pool = pool
        self.reporter = reporter
        self.run_res = run_res
        self._stop_event = Event()
        self.runner_id = f"r{iteration}.{_TestRunner.runner_id_count}"
        _TestRunner.runner_id_count += 1
        self.error: XeetException | None = None

    def log_info(self, *args, **kwargs) -> None:
        log_info(f"{self.runner_id}:", *args, **kwargs)

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
            self.reporter.on_test_enter(test)
            try:
                test_res = self._run_test(test)
            except XeetException as e:
                self.log_info(f"Error occurred during test '{test.name}': {e}")
                self.error = e
                _TestRunner.runner_error.set()
                break

            self.run_res.add_test_result(test.name, 0, test_res)
            self.reporter.on_test_end(test_res)
            log_blank()

    def _run_test(self, test: Xtest) -> TestResult:
        if test.error:
            return TestResult(status=TestStatus.InitErr, status_reason=test.error)

        test.xdefs.reporter.on_test_setup_start(test)
        test.setup()
        test.xdefs.reporter.on_test_setup_end()
        start = timer()
        ret = test.run()
        ret.duration = timer() - start
        return ret


def run_tests(conf: str,
              criteria: TestCriteria,
              reporter: RunReporter,
              debug_mode: bool = False,
              threads: int = 1,
              iterations: int = 1) -> RunResult:
    log_info("Starting run", pr_suffix="------------\n")
    driver = xeet_init(conf, debug_mode, reporter)
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

    log_info("Running tests: {}\n".format(", ".join([x.name for x in tests])))

    run_res = RunResult(iterations=iterations, criteria=criteria)
    tests_pool = _TestsPool(tests)

    reporter.on_run_start(run_res, tests)
    for iter_n in range(iterations):
        iter_info = run_res.iterations_info[iter_n]
        if iterations > 1:
            log_info(f">>> Iteration {iter_n}/{iterations - 1}")
        reporter.on_iteration_start(iter_info, iter_n)
        _TestRunner.reset()
        runners = [_TestRunner(tests_pool, reporter, run_res, iter_n) for _ in range(threads)]
        for runner in runners:
            runner.start()
        for runner in runners:
            runner.join()
        if _TestRunner.runner_error.is_set():
            log_info("Error occurred during run")
            first_error = next((r.error for r in runners if r.error), None)
            if first_error:
                raise first_error
        reporter.on_iteration_end()

        if iterations > 1:
            log_info(f"Finished iteration #{iter_n}/{iterations - 1}")
        for status in TestStatus:
            test_names = iter_info.tests[status]
            if not test_names:
                continue
            test_list_str = ", ".join(test_names)
            log_info(f"{status}: {test_list_str}")
        tests_pool.reset()
    reporter.on_run_end()
    return run_res
