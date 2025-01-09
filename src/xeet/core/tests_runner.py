from dataclasses import dataclass, field
from . import TestsCriteria, RuntimeInfo
from .result import (IterationResult, TestResult, TestPrimaryStatus, TestSecondaryStatus, RunResult,
                     TestStatus, EmptyRunResult, time_result)
from .driver import xeet_init
from .events import EventReporter, EventNotifier
from .test import Test
from xeet import XeetException
from threading import Lock, Thread, Event
from signal import signal, SIGINT


_INIT_ERR_STTS = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr)


@dataclass
class XeetRunSettings:
    conf: str
    criteria: TestsCriteria
    reporters: list[EventReporter] = field(default_factory=list)
    debug: bool = False
    iterations: int = 1
    jobs: int = 1


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
            self.test = self.pool.get_next()
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
    def __init__(self, settings: XeetRunSettings) -> None:
        self.driver = xeet_init(settings.conf, settings.debug)
        self.rti.iterations = settings.iterations
        self.criteria = settings.criteria

        for reporter in settings.reporters:
            self.rti.add_run_reporter(reporter)
        self.run_res = RunResult(iterations=settings.iterations, criteria=settings.criteria)
        self.tests = self.driver.get_tests(settings.criteria)
        self.pool = _TestsPool(self.tests)
        self.threads = settings.jobs
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
