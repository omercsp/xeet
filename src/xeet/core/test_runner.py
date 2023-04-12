from . import TestsCriteria, RuntimeInfo
from .result import (IterationResult, TestResult, TestPrimaryStatus, TestSecondaryStatus, RunResult,
                     TestStatus, EmptyRunResult, time_result)
from .driver import xeet_init
from .events import EventReporter


_INIT_ERR_STTS = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr)


class TestRunner:
    def __init__(self,
                 conf: str,
                 criteria: TestsCriteria,
                 reporters: EventReporter | list[EventReporter],
                 debug_mode: bool = False,
                 iterations: int = 1) -> None:
        self.driver = xeet_init(conf, debug_mode)
        self.rti.iterations = iterations
        self.criteria = criteria

        if not isinstance(reporters, list):
            reporters = [reporters]
        for reporter in reporters:
            self.rti.add_run_reporter(reporter)
        self.run_res = RunResult(iterations=iterations, criteria=criteria)
        self.tests = self.driver.get_tests(criteria)

    @property
    def rti(self) -> RuntimeInfo:
        return self.driver.rti

    @time_result
    def run(self) -> RunResult:
        if not self.tests:
            return EmptyRunResult
        self.rti.notifier.on_run_start(self.run_res, self.tests)
        for iter_n in range(self.rti.iterations):
            self._run_iter(iter_n)
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
