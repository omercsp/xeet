from . import TestsCriteria
from .test import Test, TestModel
from .result import (TestResult, TestPrimaryStatus, TestSecondaryStatus, RunResult, TestStatus,
                     EmptyRunResult, IterationResult)
from .driver import XeetModel, xeet_init
from .events import EventNotifier, EventReporter
from xeet import XeetException
from typing import Callable
from timeit import default_timer as timer
from enum import Enum
from threading import Condition, Thread, Event


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


def _notify(*_, **__) -> None:
    ...


def _gen_notify_func(notifier: EventNotifier) -> Callable:
    def _notify(*args, **kwargs) -> None:
        notifier.on_run_message(*args, **kwargs)
    return _notify


class _TestsPool:
    def __init__(self, tests: list[Test], threads: int) -> None:
        self._base_tests = tests
        self.threads = threads
        self._tests: list[Test] = []
        self.condition = Condition()
        self.abort = Event()
        self.reset()

    def stop(self) -> None:
        self.abort.set()
        with self.condition:
            self.condition.notify_all()

    def next_test(self, runner_id: int) -> Test | None:
        with self.condition:
            while True:
                if self.abort.is_set():
                    return None
                test, busy = self._next_test(runner_id)
                if busy:
                    _notify(f"runner#{runner_id}: no obtainable tests, waiting")
                    self.condition.wait()
                    _notify(f"runner#{runner_id}: woke up")
                    continue
                return test

    #  returns a tuple of test and a boolean indicating if there are no tests to run
    #  in case there are tests but they are busy, the return value is (None, True),
    #  meaning not current test is available but there are tests to run
    def _next_test(self, runner_id: int) -> tuple[Test | None, bool]:
        if len(self._tests) == 0:
            return None, False
        for i, test in enumerate(self._tests):
            _notify(f"{runner_id}: Trying to get test '{test.name}'")
            try:
                #  if test.error is set, it means that the test is not runnable
                #  and should be skipped. No need to check for resources.
                if not test.error and not test.obtain_resources():
                    _notify(f"{runner_id}: resources not available for '{test.name}'")
                    continue
                if i > 0:
                    busy_tests = self._tests[0:i]
                    self._tests = self._tests[i:]
                    if len(self._tests) < self.threads:
                        self._tests.extend(busy_tests)
                    else:
                        self._tests = self._tests[0:self.threads] + busy_tests + \
                            self._tests[self.threads:]
                _notify(f"{runner_id}: got '{test.name}'")
                return self._tests.pop(i), False
            except XeetException as e:
                _notify(f"Error occurred getting test '{test.name}': {e}")
                test.error = str(e)
                return test, False  # return the test with error, will become a runtime error
        return None, True

    def release_test(self, test: Test) -> None:
        with self.condition:
            test.release_resources()
            self.condition.notify_all()

    def insert(self, test: Test) -> None:
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

    def run(self) -> None:
        while True:
            if self._stop_event.is_set() or _TestRunner.runner_error.is_set():
                self.pool.stop()
                _notify("Stopping")
                break
            test = self.pool.next_test(self.runner_id)
            if test is None:
                _notify("No more tests, goodbye")
                break
            self.notifier.on_test_start(test=test, runner_id=self.runner_id)
            try:
                test_res = self._run_test(test)
                self.iter_res.add_test_result(test.name, test_res)
                self.notifier.on_test_end(test=test, test_res=test_res)
            except XeetException as e:
                _notify(f"Error occurred during test '{test.name}': {e}")
                self.error = e
                _TestRunner.runner_error.set()
                break
            finally:
                self.pool.release_test(test)

    _INIT_ERR_STTS = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr)

    def _run_test(self, test: Test) -> TestResult:
        if test.error:
            return TestResult(self._INIT_ERR_STTS, status_reason=test.error)

        start = timer()
        ret = test.run()
        ret.duration = timer() - start
        return ret


def run_tests(conf: str,
              criteria: TestsCriteria,
              reporters: EventReporter | list[EventReporter],
              debug_mode: bool = False,
              threads: int = 1,
              iterations: int = 1) -> RunResult:
    driver = xeet_init(conf, debug_mode)
    rti = driver.rti
    if not isinstance(reporters, list):
        reporters = [reporters]
    for reporter in reporters:
        rti.add_run_reporter(reporter)
    notifier = rti.notifier
    global _notify
    _notify = _gen_notify_func(notifier)
    notifier.on_init()

    tests = driver.get_tests(criteria)
    if not tests:
        return EmptyRunResult
    run_res = RunResult(iterations=iterations, criteria=criteria)
    notifier.on_run_start(run_res, tests, threads)
    tests_pool = _TestsPool(tests, threads)

    for iter_n in range(iterations):
        iter_res = run_res.iter_results[iter_n]
        driver.rti.set_iteration(iter_n, iterations)
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
    notifier.on_run_end()
    return run_res
