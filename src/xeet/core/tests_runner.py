from dataclasses import dataclass, field
from . import TestsCriteria, RuntimeInfo
from .result import (IterationResult, TestResult, TestPrimaryStatus, TestSecondaryStatus, RunResult,
                     TestStatus, EmptyRunResult, time_result)
from .driver import xeet_init
from .events import EventReporter


_INIT_ERR_STTS = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr)


@dataclass
class XeetRunSettings:
    conf: str
    criteria: TestsCriteria
    reporters: list[EventReporter] = field(default_factory=list)
    debug: bool = False
    iterations: int = 1


class XeetRunner:
    def __init__(self, settings: XeetRunSettings) -> None:
        self.driver = xeet_init(settings.conf, settings.debug)
        self.rti.iterations = settings.iterations
        self.criteria = settings.criteria

        for reporter in settings.reporters:
            self.rti.add_run_reporter(reporter)
        self.run_res = RunResult(iterations=settings.iterations, criteria=settings.criteria)
        self.tests = self.driver.get_tests(settings.criteria)

    @property
    def rti(self) -> RuntimeInfo:
        return self.driver.rti

    def run(self) -> RunResult:
        if not self.tests:
            return EmptyRunResult
        self.run_res.set_start_time()
        self.rti.notifier.on_run_start(self.run_res, self.tests)
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
        for test in self.tests:
            self.rti.notifier.on_test_start(test=test)
            if test.error:
                test_res = TestResult(test=test, status=_INIT_ERR_STTS, status_reason=test.error)
            else:
                test_res = test.run()
            iter_res.add_test_result(test.name, test_res)
            self.rti.notifier.on_test_end(test_res)
        self.rti.notifier.on_iteration_end()
        return iter_res
