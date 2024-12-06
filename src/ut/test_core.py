from ut import ref_str, XeetUnittest
from xeet.xtest import (Xtest, TestResult, TestStatus, XeetRunException, status_catgoery,
                        TestStatusCategory)
from xeet.xstep import XStepTestArgs, XStepListResult
from xeet.steps.dummy_step import DummyStepModel, DummyStep, DummyStepResult
from xeet.core import fetch_xtest, fetch_tests_list
from xeet.config import TestCriteria
from xeet.common import XeetVars
import os


_TEST0 = "test0"
_TEST1 = "test1"
_TEST2 = "test2"
_TEST3 = "test3"
_TEST4 = "test4"
_TEST5 = "test5"


_dummy_fields = set(DummyStepModel.model_fields.keys())


def _gen_dummy_step_desc(**kwargs) -> dict:
    for k in list(kwargs.keys()):
        if k not in _dummy_fields:
            raise ValueError(f"Invalid DummyStep field '{k}'")
    return {"type": "dummy", **kwargs}


_step_args = XStepTestArgs()


def _gen_dummy_step(args: dict) -> DummyStep:
    model = DummyStepModel(**args)
    return DummyStep(model, _step_args)


def _gen_dummy_step_result(step: DummyStep, completed: bool, failed: bool) -> DummyStepResult:
    return DummyStepResult(step=step, return_value=step.dummy_model.return_value,
                           completed=completed, failed=failed)


_OK_STEP_DESC = _gen_dummy_step_desc(return_value="test")
_OK_STEP = _gen_dummy_step(_OK_STEP_DESC)
_OK_STEP_RESULT = _gen_dummy_step_result(_OK_STEP, completed=True, failed=False)
_FAILING_STEP_DESC = _gen_dummy_step_desc(fail=True)
_FAILING_STEP = _gen_dummy_step(_FAILING_STEP_DESC)
_FAILING_STEP_RESULT = _gen_dummy_step_result(_FAILING_STEP, completed=True, failed=True)
_INCOMPLETED_STEP_DESC = _gen_dummy_step_desc(completed=False)
_INCOMPLETED_STEP = _gen_dummy_step(_INCOMPLETED_STEP_DESC)
_INCOMPLETED_STEP_RESULT = _gen_dummy_step_result(_INCOMPLETED_STEP, completed=False, failed=False)


class TestCore(XeetUnittest):
    def assertStepResultEqual(self, res: DummyStepResult, expected: DummyStepResult  # type: ignore
                              ) -> None:
        super().assertStepResultEqual(res, expected)
        self.assertIsInstance(res, DummyStepResult)
        self.assertIsInstance(expected, DummyStepResult)
        self.assertEqual(res.return_value, expected.return_value)

    #  Validate docstrings are not inherited
    def test_doc_inheritance(self):
        self.set_test(_TEST0, short_desc="text", long_desc="text", reset=True)
        self.set_test(_TEST1, base=_TEST0, save=True)
        x = self.get_test(_TEST1)
        self.assertEqual(x.base, _TEST0)
        self.assertEqual(x.short_desc, "")
        self.assertEqual(x.long_desc, "")

    def test_xstep(self):
        def _run_step(step: DummyStep, xvars: XeetVars, expected: DummyStepResult) -> None:
            step.expand(xvars)
            res: DummyStepResult = step.run()  # type: ignore
            self.assertStepResultEqual(res, expected)

        xvars = XeetVars({"var0": 5})

        step = _gen_dummy_step(_gen_dummy_step_desc(dummy_field="test", return_value="test"))
        expected = _gen_dummy_step_result(step, completed=True, failed=False)
        _run_step(step, xvars, expected)

        step = _gen_dummy_step(_gen_dummy_step_desc(dummy_field="{var0}", return_value="{var0}"))
        expected = _gen_dummy_step_result(step, completed=True, failed=False)
        # By default, the generated step will return the value of the step, which is an unexpanded
        # string
        expected.return_value = "5"
        _run_step(step, xvars, expected)

        step = _gen_dummy_step(_gen_dummy_step_desc(fail=True))
        expected = _gen_dummy_step_result(step, completed=True, failed=True)
        _run_step(step, xvars, expected)

    def test_bad_test_desc(self):
        self.set_test(_TEST0, bad_setting="text", long_desc="text", reset=True,
                      check_fields=False, save=True)
        res = self.run_test(_TEST0)
        self.assertEqual(res.status, TestStatus.InitErr)

    def test_simple_test(self):
        self.set_test(_TEST0, run=[_OK_STEP_DESC], reset=True, save=True)
        expected_test_steps_results = XStepListResult(results=[_OK_STEP_RESULT])
        expected = TestResult(status=TestStatus.Passed, run_res=expected_test_steps_results)
        res = self.run_test(_TEST0)
        self.assertTestResultEqual(res, expected)

        self.set_test(_TEST0, run=[_FAILING_STEP_DESC], reset=True, save=True)
        expected_test_steps_results = XStepListResult(results=[_FAILING_STEP_RESULT])
        expected = TestResult(status=TestStatus.Failed, run_res=expected_test_steps_results)
        self.assertTestResultEqual(self.run_test(_TEST0), expected)

        self.set_test(_TEST0, run=[_INCOMPLETED_STEP_DESC], reset=True, save=True)
        expected_test_steps_results = XStepListResult(results=[_INCOMPLETED_STEP_RESULT])
        expected = TestResult(status=TestStatus.RunErr, run_res=expected_test_steps_results)
        self.assertTestResultEqual(self.run_test(_TEST0), expected)

    def test_simple_test_steps_inheritance(self):
        self.set_test(_TEST0, run=[_OK_STEP_DESC], reset=True)
        self.set_test(_TEST1, base=_TEST0)
        self.set_test(_TEST2, base=_TEST0, run=[_FAILING_STEP_DESC], save=True)

        expected_test_steps = XStepListResult(results=[_OK_STEP_RESULT])
        expected = TestResult(status=TestStatus.Passed, run_res=expected_test_steps)
        for res in self.run_tests_list([_TEST0]):
            self.assertTestResultEqual(res, expected)

        expected_test_steps = XStepListResult(results=[_FAILING_STEP_RESULT])
        expected = TestResult(status=TestStatus.Failed, run_res=expected_test_steps)
        self.assertTestResultEqual(self.run_test(_TEST2), expected)

    #  def test_xtest_commands(self):
    def test_step_lists(self):
        self.set_test(_TEST0, run=[_OK_STEP_DESC, _OK_STEP_DESC, _OK_STEP_DESC], reset=True)
        self.set_test(_TEST1, run=[_OK_STEP_DESC, _FAILING_STEP_DESC, _OK_STEP_DESC])
        self.set_test(_TEST2, run=[_OK_STEP_DESC, _INCOMPLETED_STEP_DESC, _OK_STEP_DESC], save=True)

        expected_test_steps = XStepListResult(results=[_OK_STEP_RESULT, _OK_STEP_RESULT,
                                                       _OK_STEP_RESULT])
        expected = TestResult(status=TestStatus.Passed, run_res=expected_test_steps)
        self.assertTestResultEqual(self.run_test(_TEST0), expected)

        expected_test_steps = XStepListResult(results=[_OK_STEP_RESULT, _FAILING_STEP_RESULT])
        expected = TestResult(status=TestStatus.Failed, run_res=expected_test_steps)
        self.assertTestResultEqual(self.run_test(_TEST1), expected)

        expected_test_steps = XStepListResult(results=[_OK_STEP_RESULT, _INCOMPLETED_STEP_RESULT])
        expected = TestResult(status=TestStatus.RunErr, run_res=expected_test_steps)
        self.assertTestResultEqual(self.run_test(_TEST2), expected)

        ok_ok_list = [_OK_STEP_DESC, _OK_STEP_DESC]
        ok_ok_res = XStepListResult(results=[_OK_STEP_RESULT, _OK_STEP_RESULT])
        ok_ok_ok_list = [_OK_STEP_DESC, _OK_STEP_DESC, _OK_STEP_DESC]
        ok_ok_ok_res = XStepListResult(results=[_OK_STEP_RESULT, _OK_STEP_RESULT, _OK_STEP_RESULT])
        ok_fail_ok_list = [_OK_STEP_DESC, _FAILING_STEP_DESC, _OK_STEP_DESC]
        ok_fail_ok_res = XStepListResult(
            results=[_OK_STEP_RESULT, _FAILING_STEP_RESULT, _OK_STEP_RESULT])
        ok_fail_res = XStepListResult(results=[_OK_STEP_RESULT, _FAILING_STEP_RESULT])
        ok_incomplete_ok_list = [_OK_STEP_DESC, _INCOMPLETED_STEP_DESC, _OK_STEP_DESC]
        ok_incomplete_ok_res = XStepListResult(results=[_OK_STEP_RESULT, _INCOMPLETED_STEP_RESULT,
                                                        _OK_STEP_RESULT])
        ok_incomplete_res = XStepListResult(results=[_OK_STEP_RESULT, _INCOMPLETED_STEP_RESULT])

        self.set_test(_TEST0, pre_run=ok_ok_list, run=ok_ok_ok_list,
                      post_run=ok_ok_list, reset=True)
        # The following 3 tess should all not-run due to the failing pre-run step.
        self.set_test(_TEST1, pre_run=ok_fail_ok_list, run=ok_ok_list, post_run=ok_ok_list)
        self.set_test(_TEST2, base=_TEST1)
        self.set_test(_TEST3, base=_TEST0, pre_run=ok_fail_ok_list, save=True)

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
        self.set_test(_TEST0, pre_run=ok_ok_list, run=ok_fail_ok_list,
                      post_run=ok_ok_list, reset=True)
        self.set_test(_TEST1, base=_TEST0, save=True)
        expected = TestResult(status=TestStatus.Failed, pre_run_res=ok_ok_res, run_res=ok_fail_res,
                              post_run_res=ok_ok_res)
        for t in (_TEST0, _TEST1):
            self.assertTestResultEqual(self.run_test(t), expected)

        #  Check incomplete run step
        self.set_test(_TEST0, pre_run=ok_ok_list, run=ok_incomplete_ok_list,
                      post_run=ok_ok_list, reset=True)
        self.set_test(_TEST1, base=_TEST0)
        # Add some vairations, and validate post-run always runs
        self.set_test(_TEST2, base=_TEST0, post_run=[])
        self.set_test(_TEST3, base=_TEST2, post_run=ok_incomplete_ok_list)
        self.set_test(_TEST4, base=_TEST3, post_run=ok_fail_ok_list, save=True)
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
        self.run_settings.criteria.hidden_tests = True
        self.set_test(_TEST0, run=[_OK_STEP_DESC], abstract=True, reset=True)
        self.set_test(_TEST1, base=_TEST0)
        self.set_test(_TEST2, base=_TEST0, run=[_FAILING_STEP_DESC], save=True)
        self.assertRaises(XeetRunException, self.run_test, _TEST0)

        expected_test_steps = XStepListResult(results=[_OK_STEP_RESULT])
        expected = TestResult(status=TestStatus.Passed, run_res=expected_test_steps)
        self.assertTestResultEqual(self.run_test(_TEST1), expected)

        expected.status = TestStatus.Failed
        expected.run_res = XStepListResult(results=[_FAILING_STEP_RESULT])
        self.assertTestResultEqual(self.run_test(_TEST2), expected)

    def test_skipped_tests(self):
        self.set_test(_TEST0, pre_run=[_FAILING_STEP_DESC], run=[
                      _OK_STEP_DESC], skip=True, reset=True)
        self.set_test(_TEST1, base=_TEST0, skip=True)  # Skipp isn't inherited
        self.set_test(_TEST2, base=_TEST0, save=True)

        expected = TestResult(status=TestStatus.Skipped)
        for res in self.run_tests_list([_TEST0, _TEST1]):
            self.assertTestResultEqual(res, expected)

        expected.status = TestStatus.PreRunErr
        expected.pre_run_res = XStepListResult(results=[_FAILING_STEP_RESULT])
        self.assertTestResultEqual(self.run_test(_TEST2), expected)

    def test_expected_failure(self):
        self.set_test(_TEST0, run=[_FAILING_STEP_DESC], expected_failure=True, reset=True)
        self.set_test(_TEST1, base=_TEST0, expected_failure=True)
        self.set_test(_TEST2, base=_TEST0, post_run=[_INCOMPLETED_STEP_DESC])
        self.set_test(_TEST3, base=_TEST2, run=[_OK_STEP_DESC], save=True)

        expected = TestResult(status=TestStatus.ExpectedFail,
                              run_res=XStepListResult(results=[_FAILING_STEP_RESULT]))
        for res in self.run_tests_list([_TEST0, _TEST1]):
            self.assertTestResultEqual(res, expected)

        expected.status = TestStatus.Failed
        expected.post_run_res = XStepListResult(results=[_INCOMPLETED_STEP_RESULT])
        self.assertTestResultEqual(self.run_test(_TEST2), expected)

        expected.status = TestStatus.Passed
        expected.run_res = XStepListResult(results=[_OK_STEP_RESULT])
        self.assertTestResultEqual(self.run_test(_TEST3), expected)

    def test_variables(self):
        var_map = {"var0": "test", "var1": 5, "var2": "test2"}
        step_desc0 = _gen_dummy_step_desc(return_value="{var0}")
        step0 = _gen_dummy_step(step_desc0)
        step_result0 = _gen_dummy_step_result(step0, completed=True, failed=False)
        step_result0.return_value = "test"

        step_desc1 = _gen_dummy_step_desc(return_value=ref_str("var1"))
        step1 = _gen_dummy_step(step_desc1)
        step_result1 = _gen_dummy_step_result(step1, completed=True, failed=False)
        step_result1.return_value = 5

        step_desc2 = _gen_dummy_step_desc(return_value="{var1} {var2}")
        step2 = _gen_dummy_step(step_desc2)
        step_result2 = _gen_dummy_step_result(step2, completed=True, failed=False)
        step_result2.return_value = "5 test2"

        self.set_test(_TEST0, run=[step_desc0, step_desc1, step_desc2], reset=True, save=True,
                      var_map=var_map)
        expected = TestResult(status=TestStatus.Passed,
                              run_res=XStepListResult(results=[step_result0, step_result1,
                                                               step_result2]))
        self.assertTestResultEqual(self.run_test(_TEST0), expected)

    def test_autovars(self):
        xeet_root = os.path.dirname(self.main_config_wrapper.file_path)
        out_dir = f"{xeet_root}/xeet.out"

        #  Auto global vars
        step_desc0 = _gen_dummy_step_desc(return_value="{XEET_ROOT} {XEET_CWD} {XEET_OUTPUT_DIR}")
        step0 = _gen_dummy_step(step_desc0)
        step_result0 = _gen_dummy_step_result(step0, completed=True, failed=False)
        step_result0.return_value = f"{xeet_root} {os.getcwd()} {out_dir}"

        #  Test sepecific
        step_desc1 = _gen_dummy_step_desc(return_value="{XEET_TEST_NAME} {XEET_TEST_OUTDIR}")
        step1 = _gen_dummy_step(step_desc1)
        step_result1 = _gen_dummy_step_result(step1, completed=True, failed=False)
        step_result1.return_value = f"{_TEST0} {out_dir}/{_TEST0}"

        self.set_test(_TEST0, run=[step_desc0, step_desc1], reset=True, save=True)
        expected = TestResult(status=TestStatus.Passed,
                              run_res=XStepListResult(results=[step_result0, step_result1]))
        self.assertTestResultEqual(self.run_test(_TEST0), expected)

    def test_test_status_categories(self):
        for status in TestStatus:
            self.assertNotEqual(status_catgoery(status), TestStatusCategory.Unknown)

    #  Fetch functionality is only basically tested, as it is just a wrapper around the config file
    #  functionality,  which has its own extensive tests in test_config.py
    def test_fetch_test(self):
        self.set_test(_TEST0, reset=True)
        self.set_test(_TEST1, bad="bad", check_fields=False, save=True)
        xtest = fetch_xtest(self.main_config_wrapper.file_path, _TEST0)
        self.assertIsNotNone(xtest)
        assert xtest is not None
        self.assertEqual(xtest.name, _TEST0)

        xtest = fetch_xtest(self.main_config_wrapper.file_path, _TEST1)
        self.assertIsNotNone(xtest)
        assert xtest is not None
        self.assertEqual(xtest.name, _TEST1)
        self.assertNotEqual(xtest.init_err, "")

        xtest = fetch_xtest(self.main_config_wrapper.file_path, _TEST2)
        self.assertIsNone(xtest)

    def _fetch_tests(self) -> list[Xtest]:
        return fetch_tests_list(self.main_config_wrapper.file_path, self.criteria)

    def test_fetch_tests_list(self):
        self.set_test(_TEST0, reset=True)
        self.set_test(_TEST1)
        self.set_test(_TEST2)
        self.set_test(_TEST3)
        self.set_test(_TEST4)
        self.set_test(_TEST5, save=True)

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
        self.set_test(_TEST0, groups=["group0", "group1"], reset=True)
        self.set_test(_TEST1, groups=["group1"])
        self.set_test(_TEST2, groups=["group1", "group2"])
        self.set_test(_TEST3, groups=["group2"])
        self.set_test(_TEST4, groups=["group2"])
        self.set_test(_TEST5, save=True)
        self.criteria = TestCriteria([], ["group1"], [], [], False)

        tests = self._fetch_tests()
        self.assertEqual(len(tests), 3)
        self.assertSetEqual(set([t.name for t in tests]), set([_TEST0, _TEST1, _TEST2]))

        self.criteria.names = set([_TEST0, _TEST2, _TEST3, "no such test"])
        tests = self._fetch_tests()
        self.assertEqual(len(tests), 2)
        self.assertSetEqual(set([t.name for t in tests]), set([_TEST0, _TEST2]))
