from ut import ref_str
from ut.dummy_test_config import (DummyTestConfig, gen_dummy_step_desc, gen_dummy_step_result,
                                  OK_STEP_DESC, OK_STEP_RESULT, FAILING_STEP_DESC,
                                  FAILING_STEP_RESULT, INCOMPLETED_STEP_DESC,
                                  INCOMPLETED_STEP_RESULT)
from xeet.xtest import (Xtest, TestResult, TestStatus, XeetRunException, status_catgoery,
                        TestStatusCategory, XStepListResult)
from xeet.steps.dummy_step import DummyStepModel
from xeet.core import fetch_xtest, fetch_tests_list
from xeet.driver import TestCriteria
import os


_TEST0 = "test0"
_TEST1 = "test1"
_TEST2 = "test2"
_TEST3 = "test3"
_TEST4 = "test4"
_TEST5 = "test5"


class TestCore(DummyTestConfig):
    #  Validate docstrings are not inherited
    def test_doc_inheritance(self):
        self.add_test(_TEST0, short_desc="text", long_desc="text", reset=True)
        self.add_test(_TEST1, base=_TEST0, save=True)
        x = self.get_test(_TEST1)
        self.assertEqual(x.model.base, _TEST0)
        self.assertEqual(x.model.short_desc, "")
        self.assertEqual(x.model.long_desc, "")

    def test_xstep(self):
        self.add_var("var0", 5, reset=True)
        self.add_var("var1", 6)
        step_desc0 = gen_dummy_step_desc(dummy_val0="test")
        step_desc1 = gen_dummy_step_desc(dummy_val0="{var0}", dummy_val1=ref_str("var1"))
        expected_step_res0 = gen_dummy_step_result(step_desc0)
        expected_step_res1 = gen_dummy_step_result({"dummy_val0": "5", "dummy_val1": 6})
        self.add_test(_TEST0, run=[step_desc0, step_desc1], save=True)

        expected_test_steps_results = XStepListResult(
            results=[expected_step_res0, expected_step_res1])
        expected = TestResult(status=TestStatus.Passed, run_res=expected_test_steps_results)
        self.assertTestResultEqual(self.run_test(_TEST0), expected)

    def test_step_model_inheritance(self):
        save_steps_path = "settings.my_steps"
        self.add_setting("my_steps", {
            "base_step0": gen_dummy_step_desc(dummy_val0="test"),
            "base_step1": gen_dummy_step_desc(base=f"{save_steps_path}.base_step0"),
            "base_step2": gen_dummy_step_desc(base=f"{save_steps_path}.base_step1",
                                              dummy_val0="other_from_base")
        }, reset=True)
        #  config = read_config_file(self.main_config_wrapper.file_path)
        self.add_test(_TEST0, run=[
            gen_dummy_step_desc(base=f"{save_steps_path}.base_step0"),
            gen_dummy_step_desc(base=f"{save_steps_path}.base_step1"),
            gen_dummy_step_desc(base="settings.my_steps.base_step2")])
        self.add_test(_TEST1, run=[gen_dummy_step_desc(base=f"no.such.setting")])
        self.add_test(_TEST2, run=[gen_dummy_step_desc(base=f"tests[0].run[2]")], save=True)
        self.add_test(_TEST3,
                      run=[gen_dummy_step_desc(base=f"tests[?(@.name == '{_TEST2}')].run[0]")],
                      save=True)

        model = self.get_test(_TEST0).run_steps.steps[0].model
        self.assertIsInstance(model, DummyStepModel)
        assert isinstance(model, DummyStepModel)
        self.assertEqual(model.step_type, "dummy")
        self.assertEqual(model.dummy_val0, "test")

        test = self.get_test(_TEST1)
        self.assertTrue(test.error != "")

        model = self.get_test(_TEST2).run_steps.steps[0].model
        self.assertIsInstance(model, DummyStepModel)
        assert isinstance(model, DummyStepModel)
        self.assertEqual(model.step_type, "dummy")
        self.assertEqual(model.dummy_val0, "other_from_base")

        model = self.get_test(_TEST3).run_steps.steps[0].model
        self.assertIsInstance(model, DummyStepModel)
        assert isinstance(model, DummyStepModel)
        self.assertEqual(model.step_type, "dummy")
        self.assertEqual(model.dummy_val0, "other_from_base")

    def test_bad_test_desc(self):
        self.add_test(_TEST0, bad_setting="text", long_desc="text", reset=True,
                      save=True)
        res = self.run_test(_TEST0)
        self.assertEqual(res.status, TestStatus.InitErr)

    def test_simple_test(self):
        self.add_test(_TEST0, run=[OK_STEP_DESC], reset=True, save=True)
        expected_test_steps_results = XStepListResult(results=[OK_STEP_RESULT])
        expected = TestResult(status=TestStatus.Passed, run_res=expected_test_steps_results)
        res = self.run_test(_TEST0)
        self.assertTestResultEqual(res, expected)

        self.add_test(_TEST0, run=[FAILING_STEP_DESC], reset=True, save=True)
        expected_test_steps_results = XStepListResult(results=[FAILING_STEP_RESULT])
        expected = TestResult(status=TestStatus.Failed, run_res=expected_test_steps_results)
        self.assertTestResultEqual(self.run_test(_TEST0), expected)

        self.add_test(_TEST0, run=[INCOMPLETED_STEP_DESC], reset=True, save=True)
        expected_test_steps_results = XStepListResult(results=[INCOMPLETED_STEP_RESULT])
        expected = TestResult(status=TestStatus.RunErr, run_res=expected_test_steps_results)
        self.assertTestResultEqual(self.run_test(_TEST0), expected)

    def test_step_lists(self):
        self.add_test(_TEST0, run=[OK_STEP_DESC, OK_STEP_DESC, OK_STEP_DESC], reset=True)
        self.add_test(_TEST1, run=[OK_STEP_DESC, FAILING_STEP_DESC, OK_STEP_DESC])
        self.add_test(_TEST2, run=[OK_STEP_DESC, INCOMPLETED_STEP_DESC, OK_STEP_DESC], save=True)

        expected_test_steps = XStepListResult(results=[OK_STEP_RESULT, OK_STEP_RESULT,
                                                       OK_STEP_RESULT])
        expected = TestResult(status=TestStatus.Passed, run_res=expected_test_steps)
        self.assertTestResultEqual(self.run_test(_TEST0), expected)

        expected_test_steps = XStepListResult(results=[OK_STEP_RESULT, FAILING_STEP_RESULT])
        expected = TestResult(status=TestStatus.Failed, run_res=expected_test_steps)
        self.assertTestResultEqual(self.run_test(_TEST1), expected)

        expected_test_steps = XStepListResult(results=[OK_STEP_RESULT, INCOMPLETED_STEP_RESULT])
        expected = TestResult(status=TestStatus.RunErr, run_res=expected_test_steps)
        self.assertTestResultEqual(self.run_test(_TEST2), expected)

        ok_ok_list = [OK_STEP_DESC, OK_STEP_DESC]
        ok_ok_res = XStepListResult(results=[OK_STEP_RESULT, OK_STEP_RESULT])
        ok_ok_ok_list = [OK_STEP_DESC, OK_STEP_DESC, OK_STEP_DESC]
        ok_ok_ok_res = XStepListResult(results=[OK_STEP_RESULT, OK_STEP_RESULT, OK_STEP_RESULT])
        ok_fail_ok_list = [OK_STEP_DESC, FAILING_STEP_DESC, OK_STEP_DESC]
        ok_fail_ok_res = XStepListResult(
            results=[OK_STEP_RESULT, FAILING_STEP_RESULT, OK_STEP_RESULT])
        ok_fail_res = XStepListResult(results=[OK_STEP_RESULT, FAILING_STEP_RESULT])
        ok_incomplete_ok_list = [OK_STEP_DESC, INCOMPLETED_STEP_DESC, OK_STEP_DESC]
        ok_incomplete_ok_res = XStepListResult(results=[OK_STEP_RESULT, INCOMPLETED_STEP_RESULT,
                                                        OK_STEP_RESULT])
        ok_incomplete_res = XStepListResult(results=[OK_STEP_RESULT, INCOMPLETED_STEP_RESULT])

        self.add_test(_TEST0, pre_run=ok_ok_list, run=ok_ok_ok_list,
                      post_run=ok_ok_list, reset=True)
        # The following 3 tess should all not-run due to the failing pre-run step.
        self.add_test(_TEST1, pre_run=ok_fail_ok_list, run=ok_ok_list, post_run=ok_ok_list)
        self.add_test(_TEST2, base=_TEST1)
        self.add_test(_TEST3, base=_TEST0, pre_run=ok_fail_ok_list, save=True)

        self.assertTestResultEqual(self.run_test(_TEST0),
                                   TestResult(status=TestStatus.Passed,
                                   pre_run_res=ok_ok_res,
                                   run_res=ok_ok_ok_res,
                                   post_run_res=ok_ok_res))
        expected = TestResult(status=TestStatus.PreRunErr,
                              pre_run_res=ok_fail_res, post_run_res=ok_ok_res)

        for t in (_TEST1, _TEST2, _TEST3):
            self.assertTestResultEqual(self.run_test(t), expected)

        #  Check failing run step
        self.add_test(_TEST0, pre_run=ok_ok_list, run=ok_fail_ok_list,
                      post_run=ok_ok_list, reset=True)
        self.add_test(_TEST1, base=_TEST0, save=True)
        expected = TestResult(status=TestStatus.Failed, pre_run_res=ok_ok_res, run_res=ok_fail_res,
                              post_run_res=ok_ok_res)
        for t in (_TEST0, _TEST1):
            self.assertTestResultEqual(self.run_test(t), expected)

        #  Check incomplete run step
        self.add_test(_TEST0, pre_run=ok_ok_list, run=ok_incomplete_ok_list,
                      post_run=ok_ok_list, reset=True)
        self.add_test(_TEST1, base=_TEST0)
        # Add some vairations, and validate post-run always runs
        self.add_test(_TEST2, base=_TEST0, post_run=[])
        self.add_test(_TEST3, base=_TEST2, post_run=ok_incomplete_ok_list)
        self.add_test(_TEST4, base=_TEST3, post_run=ok_fail_ok_list, save=True)
        expected = TestResult(status=TestStatus.RunErr, pre_run_res=ok_ok_res,
                              run_res=ok_incomplete_res, post_run_res=ok_ok_res)
        for t in (_TEST0, _TEST1):
            self.assertTestResultEqual(self.run_test(t), expected)
        expected.post_run_res = XStepListResult()
        self.assertTestResultEqual(self.run_test(_TEST2), expected)

        expected.post_run_res = ok_incomplete_ok_res
        self.assertTestResultEqual(self.run_test(_TEST3), expected)

        expected.post_run_res = ok_fail_ok_res
        self.assertTestResultEqual(self.run_test(_TEST4), expected)

    def test_abstract_tests(self):
        self.criteria.hidden_tests = True
        self.add_test(_TEST0, run=[OK_STEP_DESC], abstract=True, reset=True)
        self.add_test(_TEST1, base=_TEST0)
        self.add_test(_TEST2, base=_TEST0, run=[FAILING_STEP_DESC], save=True)
        self.assertRaises(XeetRunException, self.run_test, _TEST0)

        expected_test_steps = XStepListResult(results=[OK_STEP_RESULT])
        expected = TestResult(status=TestStatus.Passed, run_res=expected_test_steps)
        self.assertTestResultEqual(self.run_test(_TEST1), expected)

        expected.status = TestStatus.Failed
        expected.run_res = XStepListResult(results=[FAILING_STEP_RESULT])
        self.assertTestResultEqual(self.run_test(_TEST2), expected)

    def test_skipped_tests(self):
        self.add_test(_TEST0, pre_run=[FAILING_STEP_DESC], run=[
                      OK_STEP_DESC], skip=True, reset=True)
        self.add_test(_TEST1, base=_TEST0, skip=True)  # Skip isn't inherited
        self.add_test(_TEST2, base=_TEST0, save=True)

        expected = TestResult(status=TestStatus.Skipped)
        for res in self.run_tests_list([_TEST0, _TEST1]):
            self.assertTestResultEqual(res, expected)

        expected.status = TestStatus.PreRunErr
        expected.pre_run_res = XStepListResult(results=[FAILING_STEP_RESULT])
        self.assertTestResultEqual(self.run_test(_TEST2), expected)

    def test_expected_failure(self):
        self.add_test(_TEST0, run=[FAILING_STEP_DESC], expected_failure=True, reset=True)
        self.add_test(_TEST1, base=_TEST0, expected_failure=True)
        self.add_test(_TEST2, base=_TEST0, post_run=[INCOMPLETED_STEP_DESC])
        self.add_test(_TEST3, base=_TEST2, run=[OK_STEP_DESC], save=True)

        expected = TestResult(status=TestStatus.ExpectedFail,
                              run_res=XStepListResult(results=[FAILING_STEP_RESULT]))
        for res in self.run_tests_list([_TEST0, _TEST1]):
            self.assertTestResultEqual(res, expected)

        expected.status = TestStatus.Failed
        expected.post_run_res = XStepListResult(results=[INCOMPLETED_STEP_RESULT])
        self.assertTestResultEqual(self.run_test(_TEST2), expected)

        expected.status = TestStatus.Passed
        expected.run_res = XStepListResult(results=[OK_STEP_RESULT])
        self.assertTestResultEqual(self.run_test(_TEST3), expected)

    def test_autovars(self):
        xeet_root = os.path.dirname(self.main_config_wrapper.file_path)
        out_dir = f"{xeet_root}/xeet.out"

        #  Auto global vars
        step_desc0 = gen_dummy_step_desc(dummy_val0="{XG_ROOT} {XG_CWD} {XG_OUT_DIR}")
        #  Test sepecific
        step_desc1 = gen_dummy_step_desc(dummy_val0="{XT_NAME} {XT_OUT_DIR}")

        self.add_test(_TEST0, run=[step_desc0, step_desc1], reset=True, save=True)

        expected_step_result0 = gen_dummy_step_result(step_desc0)
        expected_step_result0.dummy_val0 = f"{xeet_root} {os.getcwd()} {out_dir}"
        expected_step_result1 = gen_dummy_step_result(step_desc1)
        expected_step_result1.dummy_val0 = f"{_TEST0} {out_dir}/{_TEST0}"
        expected_test_steps_results = XStepListResult(results=[expected_step_result0,
                                                               expected_step_result1])
        expected = TestResult(status=TestStatus.Passed, run_res=expected_test_steps_results)
        self.assertTestResultEqual(self.run_test(_TEST0), expected)

    def test_test_status_categories(self):
        for status in TestStatus:
            self.assertNotEqual(status_catgoery(status), TestStatusCategory.Unknown)

    #  Fetch functionality is only basically tested, as it is just a wrapper around the config file
    #  functionality,  which has its own extensive tests in test_config.py
    def test_fetch_test(self):
        self.add_test(_TEST0, reset=True)
        self.add_test(_TEST1, bad="bad", save=True)
        xtest = fetch_xtest(self.main_config_wrapper.file_path, _TEST0)
        self.assertIsNotNone(xtest)
        assert xtest is not None
        self.assertEqual(xtest.name, _TEST0)

        xtest = fetch_xtest(self.main_config_wrapper.file_path, _TEST1)
        self.assertIsNotNone(xtest)
        assert xtest is not None
        self.assertEqual(xtest.name, _TEST1)
        self.assertNotEqual(xtest.error, "")

        xtest = fetch_xtest(self.main_config_wrapper.file_path, _TEST2)
        self.assertIsNone(xtest)

    def _fetch_tests(self) -> list[Xtest]:
        return fetch_tests_list(self.main_config_wrapper.file_path, self.criteria)

    def test_fetch_tests_list(self):
        self.criteria = TestCriteria([], [], [], [], False)
        self.add_test(_TEST0, reset=True)
        self.add_test(_TEST1)
        self.add_test(_TEST2)
        self.add_test(_TEST3)
        self.add_test(_TEST4)
        self.add_test(_TEST5, save=True)

        tests = self._fetch_tests()
        self.assertEqual(len(tests), 6)
        self.assertSetEqual(set([t.name for t in tests]),
                            set([_TEST0, _TEST1, _TEST2, _TEST3, _TEST4, _TEST5]))

        self.criteria.names = set([_TEST0, _TEST1, _TEST5])
        tests = self._fetch_tests()
        self.assertEqual(len(tests), 3)
        self.assertSetEqual(set([t.name for t in tests]), self.criteria.names)

        self.criteria.names = set([_TEST0, _TEST1, _TEST5, "no such test"])
        tests = self._fetch_tests()
        self.assertEqual(len(tests), 3)
        self.assertSetEqual(set([t.name for t in tests]), set([_TEST0, _TEST1, _TEST5]))

    def test_fetch_groups_list(self):
        self.add_test(_TEST0, groups=["group0", "group1"], reset=True)
        self.add_test(_TEST1, groups=["group1"])
        self.add_test(_TEST2, groups=["group1", "group2"])
        self.add_test(_TEST3, groups=["group2"])
        self.add_test(_TEST4, groups=["group2"])
        self.add_test(_TEST5, save=True)
        self.criteria = TestCriteria([], ["group1"], [], [], False)

        tests = self._fetch_tests()
        self.assertEqual(len(tests), 3)
        self.assertSetEqual(set([t.name for t in tests]), set([_TEST0, _TEST1, _TEST2]))

        self.criteria.names = set([_TEST0, _TEST2, _TEST3, "no such test"])
        tests = self._fetch_tests()
        self.assertEqual(len(tests), 2)
        self.assertSetEqual(set([t.name for t in tests]), set([_TEST0, _TEST2]))

    def test_platform_support(self):
        this_platform = os.name
        other_platform = "nt" if this_platform != "nt" else "posix"
        self.add_test(_TEST0, platforms=[this_platform], reset=True)
        self.add_test(_TEST1, platforms=[this_platform, other_platform])
        self.add_test(_TEST2, platforms=[other_platform], save=True)

        expected = TestResult(status=TestStatus.Passed)
        self.assertTestResultEqual(self.run_test(_TEST0), expected)
        self.assertTestResultEqual(self.run_test(_TEST1), expected)

        expected.status = TestStatus.Skipped
        self.assertTestResultEqual(self.run_test(_TEST2), expected)
