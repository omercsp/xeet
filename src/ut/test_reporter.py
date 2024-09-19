from ut import *
from ut.ut_dummy_defs import *
from xeet.core.xstep import XStep
from xeet.core.xres import XStepListResult, TestStatus
from xeet.core.xtest import Xtest, TestResult, TestStatus
from xeet.core.api import run_tests
from xeet.core.driver import TestCriteria
from xeet.core.run_reporter import RunReporter


class _Reporter(RunReporter):
    test_names: list[str] = []
    run_start_count = 0
    run_end_count = 0
    iteration_start_count = 0
    iteration_end_count = 0
    test_started: list[str] = []
    test_ended: list[str] = []
    phase_start_count = 0
    phase_end_count = 0
    step_start_count = 0
    step_end_count = 0
    expected_result = TestResult(status=TestStatus.Passed)
    errors = []

    curr_test: Xtest | None = None
    curr_phase: str = ""
    curr_step: XStep | None = None

    def reset(self):
        self.test_names = []
        self.run_start_count = 0
        self.run_end_count = 0
        self.iteration_start_count = 0
        self.iteration_end_count = 0
        self.test_started = []
        self.test_ended = []
        self.phase_start_count = 0
        self.phase_end_count = 0
        self.step_start_count = 0
        self.step_end_count = 0
        self.expected_result = TestResult(status=TestStatus.Passed)

        self.errors = []

    def on_run_start(self, tests: list) -> None:
        self.test_names = [t.name for t in tests]
        self.run_start_count += 1

    def on_run_end(self) -> None:
        self.run_end_count += 1

    def on_iteration_start(self) -> None:
        self.iteration_start_count += 1

    def on_iteration_end(self) -> None:
        self.iteration_end_count += 1

    # Test events
    def on_test_start(self, test: Xtest) -> None:
        self.test_started.append(test.name)
        if self.curr_test is test:
            self.errors.append("on_test_start: curr_test '{self.curr_test.name}' is previous test")
        self.curr_test = test

    def on_test_end(self, test: Xtest, _: TestResult) -> None:  # type: ignore
        self.test_ended.append(test.name)
        if self.curr_test is not test:
            self.errors.append("on_test_end: curr_test '{self.curr_test.name}' is not test"
                               "'{test.name}'")

    def on_phase_start(self, test, phase_name: str, _: int) -> None:  # type: ignore
        if self.curr_test is not test:
            self.errors.append("on_phase_start: curr_test '{self.curr_test.name}' is not test"
                               "'{test.name}'")
        self.phase_start_count += 1
        self.curr_phase = phase_name

    def on_phase_end(self, test, _: str, steps_count: int) -> None:  # type: ignore
        if self.curr_test is not test:
            self.errors.append("on_phase_end: curr_test '{self.curr_test.name}' is not test"
                               "'{test.name}'")
        self.phase_end_count += 1
        self.curr_phase = ""

    # Step events
    def on_step_start(self, test, phase_name: str, step, step_index: int) -> None:
        self.step_start_count += 1
        if self.curr_test is not test:
            self.errors.append("on_step_start: curr_test '{self.curr_test.name}' is not test"
                               "'{test.name}'")
        if self.curr_phase != phase_name:
            self.errors.append("on_step_start: curr_phase '{self.curr_phase}' is not phase"
                               "'{phase_name}'")
        if self.curr_step is step:
            self.errors.append("on_step_start: curr_step '{self.curr_step}' is previous step")
        self.curr_step = step

    def on_step_end(self, test, phase_name: str, step, step_index: int, step_res) -> None:
        self.step_end_count += 1
        if self.curr_test is not test:
            self.errors.append("on_step_end: curr_test '{self.curr_test.name}' is not test"
                               "'{test.name}'")
        if self.curr_phase != phase_name:
            self.errors.append("on_step_end: curr_phase '{self.curr_phase}' is not phase"
                               "'{phase_name}'")
        if self.curr_step is not step:
            self.errors.append("on_step_end: curr_step '{self.curr_step}' is not step"
                               "'{step}'")


class TestReporter(XeetUnittest):
    def test_reporter(self):
        self.add_var("var0", 10, reset=True)
        self.add_var("var1", 11)
        step_desc0 = gen_dummy_step_desc(dummy_val0="test")
        step_desc1 = gen_dummy_step_desc(dummy_val0="{var0}", dummy_val1=ref_str("var1"))
        expected_step_res0 = gen_dummy_step_result(step_desc0)
        expected_step_res1 = gen_dummy_step_result({"dummy_val0": "10", "dummy_val1": 11})

        n = 50
        tests = [f"test{i}" for i in range(n)]
        for t in tests:
            self.add_test(t, run=[step_desc0, step_desc1])
        self.main_config_wrapper.save()

        expected_test_steps_results = XStepListResult(
            results=[expected_step_res0, expected_step_res1])
        expected = TestResult(status=TestStatus.Passed, run_res=expected_test_steps_results)

        reporter = _Reporter()
        conf = self.main_config_wrapper.file_path
        for i in [1, 2, 3]:
            run_result = run_tests(conf, TestCriteria(), reporters=[reporter], iterations=i)
            if reporter.errors:
                print()
                for e in reporter.errors:
                    print(e)
                self.assertEqual(reporter.errors, [])
            self.assertEqual(reporter.run_start_count, 1)
            self.assertEqual(reporter.test_names, tests)
            self.assertEqual(reporter.run_end_count, 1)
            self.assertEqual(reporter.iteration_start_count, i)
            self.assertEqual(reporter.iteration_end_count, i)
            self.assertEqual(reporter.test_started, tests * i)
            self.assertEqual(reporter.test_ended, tests * i)
            self.assertEqual(reporter.phase_start_count, n * 3 * i)  # 3 phases
            self.assertEqual(reporter.phase_end_count, n * 3 * i)  # 3 phases
            self.assertEqual(reporter.step_start_count, n * 2 * i)  # 2 run steps
            self.assertEqual(reporter.step_end_count, n * 2 * i)  # 2 run steps

            for iter_info in run_result.iter_results:
                for _, test_res in iter_info.results.items():
                    self.assertTestResultEqual(test_res, expected)

            reporter.reset()
