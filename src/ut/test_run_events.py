from ut import *
from ut.ut_dummy_defs import *
from xeet.core import TestsCriteria
from xeet.core.step import Step
from xeet.core.result import PhaseResult, StepResult, TestResult
from xeet.core.test import Test, Phase
from xeet.core.api import run_tests, XeetRunSettings
from xeet.core.xeet_conf import clear_conf_cache
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
    mtrx_start_count = 0
    mtrx_end_count = 0
    tests_acc: dict[str, _TetsReportAcc] = field(default_factory=dict)
    errors = list()

    def reset(self):
        self.test_names = list()
        self.run_start_count = 0
        self.run_end_count = 0
        self.iteration_start_count = 0
        self.iteration_end_count = 0
        self.mtrx_start_count = 0
        self.mtrx_end_count = 0
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

    def on_matrix_start(self) -> None:
        self.mtrx_start_count += 1

    def on_matrix_end(self) -> None:
        self.mtrx_end_count += 1

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

    def on_test_start(self, test: Test) -> None:
        self._std_test_check(test)
        if test.name not in self.tests_acc:
            self.tests_acc[test.name] = _TetsReportAcc(name=test.name)
        self.tests_acc[test.name].test_start_count += 1

    def on_test_end(self, test_res: TestResult) -> None:
        test = test_res.test
        if not self._std_test_check(test_res.test):
            return
        self.tests_acc[test.name].test_end_count += 1

    def _std_phase_check(self, phase, fname: str = "") -> bool:
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

    def on_phase_end(self, phase_res: PhaseResult) -> None:
        phase = phase_res.phase
        if not self._std_phase_check(phase_res.phase):
            return
        self.tests_acc[phase.test.name].phases_ended.append(phase.name)

    # Step events
    def _std_step_check(self, step) -> bool:
        fname = inspect.currentframe().f_back.f_code.co_name  # type: ignore
        if not isinstance(step, Step):
            self.errors.append(f"{fname}: bad step object")
            return False
        if not self._std_phase_check(step.phase, fname):
            return False
        return True

    def on_step_start(self, step: Step) -> None:
        if not self._std_step_check(step):
            return
        assert step is not None
        self.tests_acc[step.phase.test.name].steps_started += 1

    def on_step_end(self, step_res: StepResult) -> None:
        step = step_res.step
        if not self._std_step_check(step):
            return
        self.tests_acc[step.phase.test.name].steps_ended += 1


def _run_events(xut: XeetUnittest, threads: int):
    xut.add_var("var0", 10, reset=True)
    mtrx_vals = [11, 12]
    xut.add_matrix("var1", mtrx_vals)
    step_desc0 = gen_dummy_step_desc(dummy_val0="test")
    step_desc1 = gen_dummy_step_desc(dummy_val0="{var0}", dummy_val1=ref_str("var1"))
    expected_step_res0 = gen_dummy_step_result(step_desc0)
    expected_step_res1 = gen_dummy_step_result({"dummy_val0": "10", "dummy_val1": 11})
    expected_post_res0 = gen_dummy_step_result(step_desc0)

    n = 12
    #  n = 1
    tests = [f"test{i}" for i in range(n)]
    for t in tests:
        xut.add_test(t, run=[step_desc0, step_desc1], post_run=[step_desc0])
    xut.save()

    expected = gen_test_result(status=PASSED_TEST_STTS,
                               main_results=[expected_step_res0, expected_step_res1],
                               post_results=[expected_post_res0])

    reporter = _Reporter()
    conf = xut.file_path
    for i in [1, 2, 3]:
        run_sttings = XeetRunSettings(file_path=conf, criteria=TestsCriteria(),
                                      reporters=[reporter], iterations=i, jobs=threads)
        run_result = run_tests(run_sttings)
        if reporter.errors:
            print()
            for e in reporter.errors:
                print(e)
            assert len(reporter.errors) == 0
        assert reporter.run_start_count == 1
        assert reporter.test_names == tests
        assert reporter.run_end_count == 1
        assert reporter.iteration_start_count == i
        assert reporter.iteration_end_count == i
        expected_mtrx_count = i * len(mtrx_vals)
        assert reporter.mtrx_start_count == expected_mtrx_count
        assert reporter.mtrx_end_count == expected_mtrx_count

        acc_test = reporter.tests_acc
        assert len(acc_test) == n
        for acct in acc_test.values():
            assert acct.test_start_count == expected_mtrx_count
            assert acct.test_end_count == expected_mtrx_count
            #  2 phases. Run and post. Pre is empty so it is not counted
            assert len(acct.phases_started) == 2 * expected_mtrx_count
            assert len(acct.phases_ended) == 2 * expected_mtrx_count
            #  2 steps in run and 1 in post
            assert acct.steps_started == 3 * expected_mtrx_count
            assert acct.steps_ended == 3 * expected_mtrx_count

        for iter_info in run_result.iter_results:
            for _, test_res in iter_info.mtrx_results[0].results.items():
                xut.update_test_res_test(expected, test_res.test.name)
                assert_test_results_equal(test_res, expected)

        reporter.reset()
        #  Clear the driver cache to avoid reporters duplication in iterations,
        #  as rpoerters are added to the driver in the test run
        clear_conf_cache()


def test_run_events(xut: XeetUnittest):
    for threads in [1, 2, 4]:
        _run_events(xut, threads)
