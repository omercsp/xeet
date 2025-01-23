from ut import *
from ut.ut_dummy_defs import *
from xeet import XeetException
from xeet.core.xres import XStepListResult, TestStatus, TestPrimaryStatus, TestSecondaryStatus
from xeet.core.xtest import Xtest, TestResult, TestStatus
from xeet.steps.dummy_step import DummyStepModel
from xeet.core.api import fetch_xtest, fetch_tests_list
from xeet.core.driver import TestCriteria
from xeet.common import platform_path
import os


class TestCore(XeetUnittest):
    #  Validate docstrings are not inherited
    def test_doc_inheritance(self):
        self.add_test(TEST0, short_desc="text", long_desc="text", reset=True)
        self.add_test(TEST1, base=TEST0, save=True)
        x = self.get_test(TEST1)
        self.assertEqual(x.model.base, TEST0)
        self.assertEqual(x.model.short_desc, "")
        self.assertEqual(x.model.long_desc, "")

    def test_xstep(self):
        self.add_var("var0", 5, reset=True)
        self.add_var("var1", 6)
        step_desc0 = gen_dummy_step_desc(dummy_val0="test")
        step_desc1 = gen_dummy_step_desc(dummy_val0="{var0}", dummy_val1=ref_str("var1"))
        expected_step_res0 = gen_dummy_step_result(step_desc0)
        expected_step_res1 = gen_dummy_step_result({"dummy_val0": "5", "dummy_val1": 6})
        self.add_test(TEST0, run=[step_desc0, step_desc1], save=True)

        expected_test_steps_results = XStepListResult(
            results=[expected_step_res0, expected_step_res1])
        expected = TestResult(status=PASSED_TEST_STTS, run_res=expected_test_steps_results)
        self.assertTestResultEqual(self.run_test(TEST0), expected)

    def test_step_model_inheritance(self):
        save_steps_path = "settings.my_steps"
        self.add_setting("my_steps", {
            "base_step0": gen_dummy_step_desc(dummy_val0="test"),
            "base_step1": gen_dummy_step_desc(base=f"{save_steps_path}.base_step0"),
            "base_step2": gen_dummy_step_desc(base=f"{save_steps_path}.base_step1",
                                              dummy_val0="other_from_base")
        }, reset=True)
        #  config = read_config_file(self.main_config_wrapper.file_path)
        self.add_test(TEST0, run=[
            gen_dummy_step_desc(base=f"{save_steps_path}.base_step0"),
            gen_dummy_step_desc(base=f"{save_steps_path}.base_step1"),
            gen_dummy_step_desc(base="settings.my_steps.base_step2")])
        self.add_test(TEST1, run=[gen_dummy_step_desc(base=f"no.such.setting")])
        self.add_test(TEST2, run=[gen_dummy_step_desc(base=f"tests[0].run[2]")], save=True)
        self.add_test(TEST3,
                      run=[gen_dummy_step_desc(base=f"tests[?(@.name == '{TEST2}')].run[0]")],
                      save=True)

        model = self.get_test(TEST0).run_steps.steps[0].model
        self.assertIsInstance(model, DummyStepModel)
        assert isinstance(model, DummyStepModel)
        self.assertEqual(model.step_type, "dummy")
        self.assertEqual(model.dummy_val0, "test")

        test = self.get_test(TEST1)
        self.assertTrue(test.error != "")

        model = self.get_test(TEST2).run_steps.steps[0].model
        self.assertIsInstance(model, DummyStepModel)
        assert isinstance(model, DummyStepModel)
        self.assertEqual(model.step_type, "dummy")
        self.assertEqual(model.dummy_val0, "other_from_base")

        model = self.get_test(TEST3).run_steps.steps[0].model
        self.assertIsInstance(model, DummyStepModel)
        assert isinstance(model, DummyStepModel)
        self.assertEqual(model.step_type, "dummy")
        self.assertEqual(model.dummy_val0, "other_from_base")

    def test_bad_test_desc(self):
        self.add_test(TEST0, bad_setting="text", long_desc="text", reset=True,
                      save=True)
        res = self.run_test(TEST0)
        self.assertEqual(res.status.secondary, TestSecondaryStatus.InitErr)

    def test_simple_test(self):
        self.add_test(TEST0, run=[DUMMY_OK_STEP_DESC], reset=True, save=True)
        expected_test_steps_results = XStepListResult(results=[DUMMY_OK_STEP_RES])
        expected = TestResult(PASSED_TEST_STTS, run_res=expected_test_steps_results)
        res = self.run_test(TEST0)
        self.assertTestResultEqual(res, expected)

        self.add_test(TEST0, run=[DUMMY_FAILING_STEP_DESC], reset=True, save=True)
        expected_test_steps_results = XStepListResult(results=[DUMMY_FAILING_STEP_RES])
        expected = TestResult(FAILED_TEST_STTS, run_res=expected_test_steps_results)
        self.assertTestResultEqual(self.run_test(TEST0), expected)

        self.add_test(TEST0, run=[DUMMY_INCOMPLETED_STEP_DESC], reset=True, save=True)
        expected_test_steps_results = XStepListResult(results=[DUMMY_INCOMPLETED_STEP_RES])
        expected = TestResult(TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.TestErr),
                              run_res=expected_test_steps_results)
        self.assertTestResultEqual(self.run_test(TEST0), expected)

    def test_step_lists(self):
        # To make things shorter
        ok_step = DUMMY_OK_STEP_DESC
        ok_res = DUMMY_OK_STEP_RES
        incompleted_step = DUMMY_INCOMPLETED_STEP_DESC
        incompleted_res = DUMMY_INCOMPLETED_STEP_RES
        failing_step = DUMMY_FAILING_STEP_DESC
        failing_res = DUMMY_FAILING_STEP_RES

        self.add_test(TEST0, run=[ok_step, ok_step, ok_step], reset=True)
        self.add_test(TEST1, run=[ok_step, failing_step, ok_step])
        self.add_test(TEST2, run=[ok_step, incompleted_step, ok_step], save=True)

        expected_test_steps = XStepListResult(results=[ok_res, ok_res, ok_res])
        expected = TestResult(PASSED_TEST_STTS, run_res=expected_test_steps)
        self.assertTestResultEqual(self.run_test(TEST0), expected)

        expected_test_steps = XStepListResult(results=[ok_res, failing_res])
        expected = TestResult(FAILED_TEST_STTS, run_res=expected_test_steps)
        self.assertTestResultEqual(self.run_test(TEST1), expected)

        expected_test_steps = XStepListResult(results=[ok_res, incompleted_res])
        expected = TestResult(TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.TestErr),
                              run_res=expected_test_steps)
        self.assertTestResultEqual(self.run_test(TEST2), expected)

        ok_ok_list = [ok_step, ok_step]
        ok_ok_res = XStepListResult(results=[ok_res, ok_res])
        ok_ok_ok_list = [ok_step, ok_step, ok_step]
        ok_ok_ok_res = XStepListResult(results=[ok_res, ok_res, ok_res])
        ok_fail_ok_list = [ok_step, failing_step, ok_step]
        ok_fail_ok_res = XStepListResult(results=[ok_res, failing_res, ok_res])
        ok_fail_res = XStepListResult(results=[ok_res, failing_res])
        ok_incomplete_ok_list = [ok_step, incompleted_step, ok_step]
        ok_incomplete_ok_res = XStepListResult(results=[ok_res, incompleted_res, ok_res])
        ok_incomplete_res = XStepListResult(results=[ok_res, incompleted_res])

        self.add_test(TEST0, pre_run=ok_ok_list, run=ok_ok_ok_list,
                      post_run=ok_ok_list, reset=True)
        # The following 3 tess should all not-run due to the failing pre-run step.
        self.add_test(TEST1, pre_run=ok_fail_ok_list, run=ok_ok_list, post_run=ok_ok_list)
        self.add_test(TEST2, base=TEST1)
        self.add_test(TEST3, base=TEST0, pre_run=ok_fail_ok_list, save=True)

        self.assertTestResultEqual(self.run_test(TEST0),
                                   TestResult(PASSED_TEST_STTS,
                                   pre_run_res=ok_ok_res,
                                   run_res=ok_ok_ok_res,
                                   post_run_res=ok_ok_res))
        expected = TestResult(TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.PreTestErr),
                              pre_run_res=ok_fail_res, post_run_res=ok_ok_res)

        for t in (TEST1, TEST2, TEST3):
            self.assertTestResultEqual(self.run_test(t), expected)

        #  Check failing run step
        self.add_test(TEST0, pre_run=ok_ok_list, run=ok_fail_ok_list, post_run=ok_ok_list,
                      reset=True)
        self.add_test(TEST1, base=TEST0, save=True)
        expected = TestResult(FAILED_TEST_STTS, pre_run_res=ok_ok_res, run_res=ok_fail_res,
                              post_run_res=ok_ok_res)
        for t in (TEST0, TEST1):
            self.assertTestResultEqual(self.run_test(t), expected)

        #  Check incomplete run step
        self.add_test(TEST0, pre_run=ok_ok_list, run=ok_incomplete_ok_list,
                      post_run=ok_ok_list, reset=True)
        self.add_test(TEST1, base=TEST0)
        # Add some vairations, and validate post-run always runs
        self.add_test(TEST2, base=TEST0, post_run=[])
        self.add_test(TEST3, base=TEST2, post_run=ok_incomplete_ok_list)
        self.add_test(TEST4, base=TEST3, post_run=ok_fail_ok_list, save=True)
        expected = TestResult(TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.TestErr),
                              pre_run_res=ok_ok_res, run_res=ok_incomplete_res,
                              post_run_res=ok_ok_res)
        for t in (TEST0, TEST1):
            self.assertTestResultEqual(self.run_test(t), expected)
        expected.post_run_res = XStepListResult()
        self.assertTestResultEqual(self.run_test(TEST2), expected)

        expected.post_run_res = ok_incomplete_ok_res
        self.assertTestResultEqual(self.run_test(TEST3), expected)

        expected.post_run_res = ok_fail_ok_res
        self.assertTestResultEqual(self.run_test(TEST4), expected)

    def test_abstract_tests(self):
        self.add_test(TEST0, run=[DUMMY_OK_STEP_DESC], abstract=True, reset=True)
        self.add_test(TEST1, base=TEST0)
        self.add_test(TEST2, base=TEST0, run=[DUMMY_FAILING_STEP_DESC], save=True)
        self.assertRaises(XeetException, self.run_test, TEST0)

        expected_test_steps = XStepListResult(results=[DUMMY_OK_STEP_RES])
        expected = TestResult(PASSED_TEST_STTS, run_res=expected_test_steps)
        self.assertTestResultEqual(self.run_test(TEST1), expected)

        expected.status = FAILED_TEST_STTS
        expected.run_res = XStepListResult(results=[DUMMY_FAILING_STEP_RES])
        self.assertTestResultEqual(self.run_test(TEST2), expected)

    def test_skipped_tests(self):
        self.add_test(TEST0, pre_run=[DUMMY_FAILING_STEP_DESC], run=[
                      DUMMY_OK_STEP_DESC], skip=True, reset=True)
        self.add_test(TEST1, base=TEST0, skip=True)  # Skip isn't inherited
        self.add_test(TEST2, base=TEST0, save=True)

        expected = TestResult(TestStatus(TestPrimaryStatus.Skipped))
        for res in self.run_tests_list([TEST0, TEST1]):
            self.assertTestResultEqual(res, expected)

        expected.status = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.PreTestErr)
        expected.pre_run_res = XStepListResult(results=[DUMMY_FAILING_STEP_RES])
        self.assertTestResultEqual(self.run_test(TEST2), expected)

    def test_expected_failure(self):
        self.add_test(TEST0, run=[DUMMY_FAILING_STEP_DESC], expected_failure=True, reset=True)
        self.add_test(TEST1, base=TEST0, expected_failure=True)
        self.add_test(TEST2, base=TEST0, post_run=[DUMMY_INCOMPLETED_STEP_DESC])
        self.add_test(TEST3, base=TEST2, run=[DUMMY_OK_STEP_DESC], save=True)

        expected = TestResult(
            TestStatus(TestPrimaryStatus.Passed, TestSecondaryStatus.ExpectedFail),
            run_res=XStepListResult(results=[DUMMY_FAILING_STEP_RES]))
        for res in self.run_tests_list([TEST0, TEST1]):
            self.assertTestResultEqual(res, expected)

        #  Expected failure aren't inherited
        expected.status = FAILED_TEST_STTS
        expected.post_run_res = XStepListResult(results=[DUMMY_INCOMPLETED_STEP_RES])
        self.assertTestResultEqual(self.run_test(TEST2), expected)

        expected.status = PASSED_TEST_STTS
        expected.run_res = XStepListResult(results=[DUMMY_OK_STEP_RES])
        self.assertTestResultEqual(self.run_test(TEST3), expected)

    def test_autovars(self):
        xeet_root = os.path.dirname(self.main_config_wrapper.file_path)
        xeet_root = platform_path(xeet_root)
        out_dir = f"{xeet_root}/xeet.out"

        #  Auto global vars
        step_desc0 = gen_dummy_step_desc(dummy_val0="{XEET_ROOT} {XEET_CWD} {XEET_OUT_DIR}")
        #  Test sepecific
        step_desc1 = gen_dummy_step_desc(dummy_val0="{XEET_TEST_NAME} {XEET_TEST_OUT_DIR}")

        self.add_test(TEST0, run=[step_desc0, step_desc1], reset=True, save=True)

        cwd = platform_path(os.getcwd())
        expected_step_result0 = gen_dummy_step_result(step_desc0)
        expected_step_result0.dummy_val0 = f"{xeet_root} {cwd} {out_dir}"
        expected_step_result1 = gen_dummy_step_result(step_desc1)
        expected_step_result1.dummy_val0 = f"{TEST0} {out_dir}/{TEST0}"
        expected_test_steps_results = XStepListResult(results=[expected_step_result0,
                                                               expected_step_result1])
        expected = TestResult(PASSED_TEST_STTS, run_res=expected_test_steps_results)
        self.assertTestResultEqual(self.run_test(TEST0), expected)

    #  Fetch functionality is only basically tested, as it is just a wrapper around the driver
    #  functionality,  which has its own extensive tests.
    def test_fetch_test(self):
        self.add_test(TEST0, reset=True)
        self.add_test(TEST1, bad="bad", save=True)
        xtest = fetch_xtest(self.main_config_wrapper.file_path, TEST0)
        self.assertIsNotNone(xtest)
        assert xtest is not None
        self.assertEqual(xtest.name, TEST0)

        xtest = fetch_xtest(self.main_config_wrapper.file_path, TEST1)
        self.assertIsNotNone(xtest)
        assert xtest is not None
        self.assertEqual(xtest.name, TEST1)
        self.assertNotEqual(xtest.error, "")

        xtest = fetch_xtest(self.main_config_wrapper.file_path, TEST2)
        self.assertIsNone(xtest)

    def fetch_tests_list(self) -> list[Xtest]:
        return fetch_tests_list(self.main_config_wrapper.file_path, self.criteria)

    def test_fetch_tests_list(self):
        self.criteria = TestCriteria()
        self.add_test(TEST0, reset=True)
        self.add_test(TEST1)
        self.add_test(TEST2)
        self.add_test(TEST3)
        self.add_test(TEST4)
        self.add_test(TEST5, save=True)

        tests = self.fetch_tests_list()
        self.assertEqual(len(tests), 6)
        self.assertSetEqual(set([t.name for t in tests]),
                            set([TEST0, TEST1, TEST2, TEST3, TEST4, TEST5]))

        self.criteria.names = set([TEST0, TEST1, TEST5])
        tests = self.fetch_tests_list()
        self.assertEqual(len(tests), 3)
        self.assertSetEqual(set([t.name for t in tests]), self.criteria.names)

        self.criteria.names = set([TEST0, TEST1, TEST5, "no such test"])
        tests = self.fetch_tests_list()
        self.assertEqual(len(tests), 3)
        self.assertSetEqual(set([t.name for t in tests]), set([TEST0, TEST1, TEST5]))

    def test_fetch_groups_list(self):
        self.add_test(TEST0, groups=["group0", "group1"], reset=True)
        self.add_test(TEST1, groups=["group1"])
        self.add_test(TEST2, groups=["group1", "group2"])
        self.add_test(TEST3, groups=["group2"])
        self.add_test(TEST4, groups=["group2"])
        self.add_test(TEST5, save=True)
        self.criteria = TestCriteria(include_groups={"group1"})

        tests = self.fetch_tests_list()
        self.assertEqual(len(tests), 3)
        self.assertSetEqual(set([t.name for t in tests]), set([TEST0, TEST1, TEST2]))

        self.criteria.include_groups = set()
        self.criteria.names = set([TEST0, TEST2, TEST3, "no such test"])
        tests = self.fetch_tests_list()
        self.assertEqual(len(tests), 3)
        self.assertSetEqual(set([t.name for t in tests]), set([TEST0, TEST2, TEST3]))

    def test_step_details(self):
        test_desc = gen_dummy_step_desc(dummy_val0="test {test_var}", dummy_val1=10)
        self.add_var("test_var", "var", reset=True)
        self.add_test(TEST0, run=[test_desc], save=True)

        test = fetch_xtest(self.main_config_wrapper.file_path, TEST0)
        self.assertIsNotNone(test)
        assert test is not None
        step = test.run_steps.steps[0]

        step_details = step.details(full=False, printable=False, setup=False)
        step_details = dict(step_details)
        self.assertSetEqual(set(step_details.keys()),
                            {"dummy_val0", "dummy_val1", "step_type"})
        self.assertEqual(step_details["dummy_val0"], "test {test_var}")
        self.assertEqual(step_details["dummy_val1"], 10)
        self.assertEqual(step_details["step_type"], "dummy")

        step_details = step.details(full=False, printable=True, setup=False)
        self.assertGreater(len(step_details), 2)
        self.assertEqual(step_details[1][0], "Dummy val1")  # check the dummy reordering, type is 0
        self.assertEqual(step_details[2][0], "Dummy val0")
        step_details = dict(step_details)
        self.assertSetEqual(set(step_details.keys()), {"Dummy val0", "Dummy val1", "Step type"})

        self.assertEqual(step_details["Dummy val0"], "test {test_var}")
        self.assertEqual(step_details["Dummy val1"], 10)
        self.assertEqual(step_details["Step type"], "dummy")

        test = fetch_xtest(self.main_config_wrapper.file_path, TEST0, setup=True)
        self.assertIsNotNone(test)
        assert test is not None
        step = test.run_steps.steps[0]
        step_details = step.details(full=False, printable=False, setup=True)
        step_details = dict(step_details)
        self.assertSetEqual(set(step_details.keys()),
                            {"dummy_val0", "dummy_val1", "step_type", "dummy_extra"})
        self.assertEqual(step_details["dummy_val0"], "test var")
        self.assertEqual(step_details["dummy_val1"], 10)
        self.assertEqual(step_details["step_type"], "dummy")
        self.assertEqual(step_details["dummy_extra"], id(step))

        step_details = step.details(full=False, printable=True, setup=True)
        step_details = dict(step_details)
        self.assertSetEqual(set(step_details.keys()),
                            {"Dummy val0", "Dummy val1", "Step type", "Dummy extra print"})
        self.assertEqual(step_details["Dummy val0"], "test var")
        self.assertEqual(step_details["Dummy val1"], 10)
        self.assertEqual(step_details["Step type"], "dummy")
