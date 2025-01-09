from . import TestsCriteria, RuntimeInfo
from .test import Test, TestModel
from .result import (TestResult, TestPrimaryStatus, TestSecondaryStatus, RunResult, TestStatus,
                     EmptyRunResult, IterationResult, time_result)
from .driver import XeetModel, xeet_init
from .events import EventNotifier, EventReporter
from xeet import XeetException
from enum import Enum
from threading import Lock, Thread, Event


def fetch_test(config_path: str, name: str) -> Test | None:
    return xeet_init(config_path).get_test(name)


def fetch_tests_list(config_path: str, criteria: TestsCriteria) -> list[Test]:
    return xeet_init(config_path).get_tests(criteria)


def fetch_groups_list(config_path: str) -> list[str]:
    config = xeet_init(config_path)
    return list(config.all_groups())


def fetch_test_desc(config_path: str, name: str) -> dict | None:
    return xeet_init(config_path).test_desc(name)


def fetch_config(config_path: str) -> dict:
    return xeet_init(config_path).rti.defs_dict


class SchemaType(str, Enum):
    CONFIG = "config"
    XTEST = "test"
    UNIFIED = "unified"


def fetch_schema(schema_type: str) -> dict:
    if schema_type == SchemaType.CONFIG.value:
        return XeetModel.model_json_schema()
    if schema_type == SchemaType.XTEST.value:
        return TestModel.model_json_schema()
    if schema_type == SchemaType.UNIFIED.value:
        d = XeetModel.model_json_schema()
        d["properties"]["tests"]["items"] = TestModel.model_json_schema()
        return d
    raise XeetException(f"Invalid dump type: {schema_type}")


class _TestsPool:
    def __init__(self, tests: list[Test]) -> None:
        self.tests = tests
        self._index = 0
        self._lock = Lock()

    def get_next(self) -> Test | None:
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

    def __init__(self, pool: _TestsPool, notifier: EventNotifier, iter_res: IterationResult
                 ) -> None:
        super().__init__()
        self.pool = pool
        self.notifier = notifier
        self.iter_res = iter_res
        self._stop_event = Event()
        self.runner_id = _TestRunner.runner_id_count
        _TestRunner.runner_id_count += 1
        self.error: XeetException | None = None

    def info(self, *args, **kwargs) -> None:
        self.notifier.on_run_message(f"runner#{self.runner_id}:", *args, **kwargs)

    def run(self) -> None:
        while True:
            if self._stop_event.is_set() or _TestRunner.runner_error.is_set():
                self.info("Stopping")
                break
            test = self.pool.get_next()
            if test is None:
                self.info("No more tests, goodbye")
                break
            self.notifier.on_test_start(test=test)
            try:
                test_res = self._run_test(test)
            except XeetException as e:
                self.info(f"Error occurred during test '{test.name}': {e}")
                self.error = e
                _TestRunner.runner_error.set()
                break

            self.iter_res.add_test_result(test.name, test_res)
            self.notifier.on_test_end(test_res)

    _INIT_ERR_STTS = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr)

    def _run_test(self, test: Test) -> TestResult:
        if test.error:
            return TestResult(test=test, status=self._INIT_ERR_STTS, status_reason=test.error)

        ret = test.run()
        return ret


@time_result
def _run_iter(rti: RuntimeInfo, tests_pool: _TestsPool, iter_n: int, run_res: RunResult,
              threads: int) -> IterationResult:
    iter_res = run_res.iter_results[iter_n]
    rti.set_iteration(iter_n)
    notifier = rti.notifier
    notifier.on_iteration_start(iter_res)
    _TestRunner.reset()
    runners = [_TestRunner(tests_pool, notifier, iter_res) for _ in range(threads)]
    for runner in runners:
        runner.start()
    for runner in runners:
        runner.join()
    if _TestRunner.runner_error.is_set():
        notifier.on_run_message("Error occurred during run")
        first_error = next((r.error for r in runners if r.error), None)
        if first_error:
            raise first_error

    notifier.on_iteration_end()
    tests_pool.reset()
    return iter_res


def run_tests(conf: str,
              criteria: TestsCriteria,
              reporters: EventReporter | list[EventReporter],
              debug_mode: bool = False,
              threads: int = 1,
              iterations: int = 1) -> RunResult:
    driver = xeet_init(conf, debug_mode)
    rti = driver.rti
    rti.iterations = iterations
    if not isinstance(reporters, list):
        reporters = [reporters]
    for reporter in reporters:
        rti.add_run_reporter(reporter)
    notifier = rti.notifier
    notifier.on_init()

    tests = driver.get_tests(criteria)
    if not tests:
        return EmptyRunResult
    run_res = RunResult(iterations=iterations, criteria=criteria)

    notifier.on_run_start(run_res, tests, threads)
    run_res.set_start_time()
    tests_pool = _TestsPool(tests)
    for iter_n in range(iterations):
        _run_iter(rti, tests_pool, iter_n, run_res, threads)
        tests_pool.reset()
    run_res.set_end_time()
    notifier.on_run_end()
    return run_res
