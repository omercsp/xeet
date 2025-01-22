from ut import *
from ut.ut_dummy_defs import *
from xeet.core.step import Step
from xeet.core.result import StepResult, TestResult, PhaseResult
from xeet.core.test import Test, Phase
from xeet.core.api import run_tests
from xeet.core.driver import TestsCriteria
from xeet.core.events import EventReporter
from dataclasses import dataclass, field
import inspect


@dataclass
class _TetsReportAcc:
    name: str = ""
    test_start_count = 0
    test_end_count = 0
    phases_started: list[str] = field(default_factory=list)
    phases_ended: list[str] = field(default_factory=list)
    steps_started = 0
    steps_ended = 0


@dataclass
class _Reporter(EventReporter):
    test_names: list[str] = field(default_factory=list)
    run_start_count = 0
    run_end_count = 0
    iteration_start_count = 0
    iteration_end_count = 0
    tests_acc: dict[str, _TetsReportAcc] = field(default_factory=dict)
    errors = list()

    def reset(self):
        self.test_names = list()
        self.run_start_count = 0
        self.run_end_count = 0
        self.iteration_start_count = 0
        self.iteration_end_count = 0
        self.tests_acc = dict()
        self.errors = list()

    def on_run_start(self, **_) -> None:
        self.test_names = [t.name for t in self.tests]
        self.run_start_count += 1

    def on_run_end(self) -> None:
        self.run_end_count += 1

    def on_iteration_start(self) -> None:
        self.iteration_start_count += 1

    def on_iteration_end(self) -> None:
        self.iteration_end_count += 1

    # Test events
    def _std_test_check(self, test: Test | None = None, fname: str = "") -> bool:
        if not fname:
            fname = inspect.currentframe().f_back.f_code.co_name  # type: ignore
        if not isinstance(test, Test):
            self.errors.append(f"{fname}: bad test object")
            return False
        if test.name not in self.test_names:
            self.errors.append(f"{fname}: test '{test.name}' not in test list")
            return False
        #  on_test_start is the only event that adds tests to tests_acc
        if test.name not in self.tests_acc and fname != "on_test_start":
            self.errors.append(f"{fname}: test '{test.name}' not in test_acc")
            return False
        return True

    def on_test_start(self, test: Test | None = None, **_) -> None:
        self._std_test_check(test)
        assert test is not None
        if test.name not in self.tests_acc:
            self.tests_acc[test.name] = _TetsReportAcc(name=test.name)
        self.tests_acc[test.name].test_start_count += 1

    def on_test_end(self, test: Test | None = None, test_res: TestResult | None = None, **_
                    ) -> None:
        if not self._std_test_check(test):
            return
        fname = inspect.currentframe().f_code.co_name  # type: ignore
        if not isinstance(test_res, TestResult):
            self.errors.append(f"{fname}: bad test result object")
        assert test is not None
        self.tests_acc[test.name].test_end_count += 1

    def _std_phase_check(self, phase: Phase | None = None, fname: str = "") -> bool:
        if not fname:
            fname = inspect.currentframe().f_back.f_code.co_name  # type: ignore
        if phase is None:
            self.errors.append(f"{fname}: empty phase")
            return False
        if not self._std_test_check(phase.test, fname):
            return False
        return True

    def on_phase_start(self, phase: Phase | None = None, **_) -> None:
        if not self._std_phase_check(phase):
            return
        assert phase is not None
        self.tests_acc[phase.test.name].phases_started.append(phase.name)

    def on_phase_end(self, test: Test | None = None, phase: Phase | None = None, **_) -> None:
        if not self._std_phase_check(phase):
            return
        assert test is not None and phase is not None
        self.tests_acc[test.name].phases_ended.append(phase.name)

    # Step events
    def _std_step_check(self, step: Step | None = None,) -> bool:
        fname = inspect.currentframe().f_back.f_code.co_name  # type: ignore
        if not isinstance(step, Step):
            self.errors.append(f"{fname}: bad step object")
            return False
        if not self._std_phase_check(step.phase, fname):
            return False
        return True

    def on_step_start(self, step: Step | None = None, **_) -> None:
        if not self._std_step_check(step):
            return
        assert step is not None
        self.tests_acc[step.phase.test.name].steps_started += 1

    def on_step_end(self, step: Step | None = None, step_res: StepResult | None = None, **_
                    ) -> None:
        if not self._std_step_check(step):
            return
        fname = inspect.currentframe().f_code.co_name  # type: ignore
        if not isinstance(step_res, StepResult):
            self.errors.append(f"{fname}: bad step result object")
        assert step is not None
        self.tests_acc[step.phase.test.name].steps_ended += 1


class TestRunEvents(XeetUnittest):
    def _test_run_events(self, threads: int):
        self.add_var("var0", 10, reset=True)
        self.add_var("var1", 11)
        step_desc0 = gen_dummy_step_desc(dummy_val0="test")
        step_desc1 = gen_dummy_step_desc(dummy_val0="{var0}", dummy_val1=ref_str("var1"))
        expected_step_res0 = gen_dummy_step_result(step_desc0)
        expected_step_res1 = gen_dummy_step_result({"dummy_val0": "10", "dummy_val1": 11})

        n = 25
        tests = [f"test{i}" for i in range(n)]
        for t in tests:
            self.add_test(t, run=[step_desc0, step_desc1], post_run=[step_desc0])
        self.main_config_wrapper.save()

        expected_run_phase_result = PhaseResult(
            steps_results=[expected_step_res0, expected_step_res1])
        expected_post_phase_result = PhaseResult(steps_results=[expected_step_res0])
        expected = TestResult(PASSED_TEST_STTS, run_res=expected_run_phase_result,
                              post_run_res=expected_post_phase_result)

        reporter = _Reporter()
        conf = self.main_config_wrapper.file_path
        for i in [1, 2, 3]:
            run_result = run_tests(conf, TestsCriteria(), reporters=[reporter], iterations=i,
                                   threads=threads)
            if reporter.errors:
                print()
                for e in reporter.errors:
                    print(e)
                self.assertEqual(len(reporter.errors), 0)
            self.assertEqual(reporter.run_start_count, 1)
            self.assertEqual(reporter.test_names, tests)
            self.assertEqual(reporter.run_end_count, 1)
            self.assertEqual(reporter.iteration_start_count, i)
            self.assertEqual(reporter.iteration_end_count, i)
            acc_test = reporter.tests_acc
            self.assertEqual(len(acc_test), n)
            for acct in acc_test.values():
                self.assertEqual(acct.test_start_count, i)
                self.assertEqual(acct.test_end_count, i)
                #  2 phases. Run and post. Pre is empty so it is not counted
                self.assertEqual(len(acct.phases_started), 2 * i)
                self.assertEqual(len(acct.phases_ended), 2 * i)
                #  2 steps in run and 1 in post
                self.assertEqual(acct.steps_started, 3 * i)
                self.assertEqual(acct.steps_ended, 3 * i)

            for iter_info in run_result.iter_results:
                for _, test_res in iter_info.mtrx_results[0].results.items():
                    self.assertTestResultEqual(test_res, expected)
            reporter.reset()

    def test_run_events(self):
        for threads in [1, 2, 4]:
            self._test_run_events(threads)
