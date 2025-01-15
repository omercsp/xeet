from . import TestsCriteria, RuntimeInfo
from .result import (IterationResult, TestResult, TestPrimaryStatus, TestSecondaryStatus, RunResult,
                     TestStatus, EmptyRunResult, time_result)
from .driver import xeet_init
from .events import EventReporter, EventNotifier
from .test import Test
from xeet import XeetException
from xeet.log import log_info
from threading import Thread, Event, Condition
from signal import signal, SIGINT
from typing import Callable


_INIT_ERR_STTS = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr)


class _TestsPool:
    def __init__(self, tests: list[Test], threads: int) -> None:
        self._base_tests = tests
        self.threads = threads
        self._tests: list[Test] = []
        self.condition = Condition()
        self.abort = Event()
        self.reset()
        self.runner_id_str = ""
        self.info: Callable = log_info

    def stop(self) -> None:
        self.abort.set()
        with self.condition:
            self.condition.notify_all()

    def next_test(self, info: Callable) -> Test | None:
        self.info = info
        with self.condition:
            while True:
                if self.abort.is_set():
                    return None
                test, busy = self._next_test()
                if busy:
                    self.info(f"no obtainable tests, waiting")
                    self.condition.wait()
                    self.info(f"woke up")
                    continue
                return test

    #  returns a tuple of test and a boolean indicating if there are no tests to run
    #  in case there are tests but they are busy, the return value is (None, True),
    #  meaning not current test is available but there are tests to run
    def _next_test(self) -> tuple[Test | None, bool]:
        if len(self._tests) == 0:
            return None, False
        for i, test in enumerate(self._tests):
            self.info(f"Trying to get test '{test.name}'")
            try:
                #  if test.error is set, it means that the test is not runnable
                #  and should be skipped. No need to check for resources.
                if not test.error and not test.obtain_resources():
                    self.info(f"resources not available for '{test.name}'")
                    continue
                if i > 0:
                    busy_tests = self._tests[0:i]
                    self._tests = self._tests[i:]
                    if len(self._tests) < self.threads:
                        self._tests.extend(busy_tests)
                    else:
                        self._tests = self._tests[0:self.threads] + busy_tests + \
                            self._tests[self.threads:]
                self.info(f"got '{test.name}'")
                return self._tests.pop(i), False
            except XeetException as e:
                self.info(f"Error occurred getting test '{test.name}': {e}")
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
    stop_event = Event()

    @staticmethod
    def reset() -> None:
        _TestRunner.runner_id_count = 0

    def __init__(self, pool: _TestsPool, notifier: EventNotifier, iter_res: IterationResult
                 ) -> None:
        super().__init__()
        self.pool = pool
        self.notifier = notifier
        self.iter_res = iter_res
        self.runner_id = _TestRunner.runner_id_count
        _TestRunner.runner_id_count += 1
        self.error: XeetException | None = None
        self.test: Test | None = None

    def info(self, *args, **kwargs) -> None:
        self.notifier.on_run_message(f"runner#{self.runner_id}:", *args, **kwargs)

    def run(self) -> None:
        while True:
            if self.stop_event.is_set():
                self.info(f"stopping")
                break
            self.test = self.pool.next_test(self.info)
            if self.test is None:
                self.info("No more tests, goodbye")
                break
            self.notifier.on_test_start(test=self.test)
            try:
                test_res = self._run_test()
            except XeetException as e:
                self.info(f"Error occurred during test '{self.test.name}': {e}")
                self.error = e
                #  _TestRunner.stop_all()
                break
            finally:
                self.pool.release_test(self.test)

            self.iter_res.add_test_result(self.test.name, test_res)
            self.notifier.on_test_end(test_res)

    def stop(self) -> None:
        if self.test:
            self.info("stopping test")
            self.test.stop()

    def _run_test(self) -> TestResult:
        assert self.test is not None
        if self.test.error:
            return TestResult(test=self.test, status=_INIT_ERR_STTS, status_reason=self.test.error)

        return self.test.run()


class XeetRunner:
    def __init__(self,
                 conf: str,
                 criteria: TestsCriteria,
                 reporters: EventReporter | list[EventReporter],
                 debug_mode: bool = False,
                 threads: int = 1,
                 iterations: int = 1) -> None:
        self.driver = xeet_init(conf, debug_mode)
        self.rti.iterations = iterations
        self.criteria = criteria
        self.threads = threads

        if not isinstance(reporters, list):
            reporters = [reporters]
        for reporter in reporters:
            self.rti.add_run_reporter(reporter)
        self.run_res = RunResult(iterations=iterations, criteria=criteria)
        self.tests = self.driver.get_tests(criteria)
        self.pool = _TestsPool(self.tests, self.threads)
        self.runners: list[_TestRunner] = []
        self.stop_event = Event()

    @property
    def rti(self) -> RuntimeInfo:
        return self.driver.rti

    def run(self) -> RunResult:
        if not self.tests:
            return EmptyRunResult
        self.run_res.set_start_time()
        self.rti.notifier.on_run_start(self.run_res, self.tests, self.threads)
        signal(SIGINT, self._stop_runners)
        for iter_n in range(self.rti.iterations):
            self._run_iter(iter_n)
        self.run_res.set_end_time()
        self.rti.notifier.on_run_end()
        return self.run_res

    @time_result
    def _run_iter(self, iter_n: int) -> IterationResult:
        iter_res = self.run_res.iter_results[iter_n]
        self.rti.set_iteration(iter_n)
        self.rti.notifier.on_iteration_start(iter_res)
        _TestRunner.reset()
        self.pool.reset()
        self.runners = [_TestRunner(self.pool, self.rti.notifier, iter_res) for _ in
                        range(self.threads)]
        for runner in self.runners:
            runner.start()
        for runner in self.runners:
            runner.join()
        first_error = next((runner.error for runner in self.runners if runner.error), None)
        if first_error:
            self.rti.notifier.on_run_message(
                f"Error occurred during iteration {iter_n}: {first_error}")
            raise first_error
        self.rti.notifier.on_iteration_end()
        return iter_res

    def _stop_runners(self, *_, **__) -> None:
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        for runner in self.runners:
            runner.stop()
