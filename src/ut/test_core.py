from ut import *
from ut.ut_dummy_defs import *
from ut.ut_exec_defs import gen_sleep_cmd, gen_exec_step_desc
from xeet import XeetException
from xeet.core.result import (StepResult, TestResult, PhaseResult, TestStatus, TestPrimaryStatus,
                              TestSecondaryStatus)
from xeet.core.test import Test, TestResult, TestStatus
from xeet.steps.dummy_step import DummyStepModel
from xeet.core.api import fetch_tests_list
from xeet.core import TestsCriteria
from xeet.common import platform_path
from timeit import default_timer as timer
import os


def test_doc_inheritance(xut: XeetUnittest) -> None:
    xut.add_test(TEST0, short_desc="text", long_desc="text", reset=True)
    xut.add_test(TEST1, base=TEST0, save=True)
    x = xut.get_test(TEST1)
    assert x.model.base == TEST0
    assert x.model.short_desc == ""
    assert x.model.long_desc == ""


#  Convert the following commented code to a pytest function like the one above.
def test_step(xut: XeetUnittest):
    xut.add_var("var0", 5)
    xut.add_var("var1", 6)
    step_desc0 = gen_dummy_step_desc(dummy_val0="test")
    step_desc1 = gen_dummy_step_desc(dummy_val0="{var0}", dummy_val1=ref_str("var1"))
    expected_step_res0 = gen_dummy_step_result(step_desc0)
    expected_step_res1 = gen_dummy_step_result({"dummy_val0": "5", "dummy_val1": 6})
    xut.add_test(TEST0, run=[step_desc0, step_desc1], save=True)

    expected_test_steps_results = PhaseResult(
        steps_results=[expected_step_res0, expected_step_res1])
    expected = TestResult(status=PASSED_TEST_STTS, main_res=expected_test_steps_results)
    expected = gen_test_result(status=PASSED_TEST_STTS,
                               main_results=[expected_step_res0, expected_step_res1])
    xut.run_compare_test(TEST0, expected)


def test_step_model_inheritance(xut: XeetUnittest):
    save_steps_path = "settings.my_steps"
    xut.add_setting("my_steps", {
        "base_step0": gen_dummy_step_desc(dummy_val0="test"),
        "base_step1": gen_dummy_step_desc(base=f"{save_steps_path}.base_step0"),
        "base_step2": gen_dummy_step_desc(base=f"{save_steps_path}.base_step1",
                                          dummy_val0="other_from_base")
    }, reset=True)
    #  config = read_config_file(xut.main_config_wrapper.file_path)
    xut.add_test(TEST0, run=[
        gen_dummy_step_desc(base=f"{save_steps_path}.base_step0"),
        gen_dummy_step_desc(base=f"{save_steps_path}.base_step1"),
        gen_dummy_step_desc(base="settings.my_steps.base_step2")])
    xut.add_test(TEST1, run=[gen_dummy_step_desc(base=f"no.such.setting")])
    xut.add_test(TEST2, run=[gen_dummy_step_desc(base=f"tests[0].run[2]")], save=True)
    xut.add_test(TEST3,
                 run=[gen_dummy_step_desc(base=f"tests[?(@.name == '{TEST2}')].run[0]")],
                 save=True)

    model = xut.get_test(TEST0).main_phase.steps[0].model
    assert isinstance(model, DummyStepModel)
    assert model.step_type == "dummy"
    assert model.dummy_val0 == "test"

    test = xut.get_test(TEST1)
    assert test.error != ""

    model = xut.get_test(TEST2).main_phase.steps[0].model
    assert isinstance(model, DummyStepModel)
    assert model.step_type == "dummy"
    assert model.dummy_val0 == "other_from_base"

    model = xut.get_test(TEST3).main_phase.steps[0].model
    assert isinstance(model, DummyStepModel)
    assert model.step_type == "dummy"
    assert model.dummy_val0 == "other_from_base"


def test_bad_test_desc(xut: XeetUnittest):
    xut.add_test(TEST0, bad_setting="text", long_desc="text")
    xut.add_test(TEST1, long_desc="text", variables={"ba d": "value"})
    xut.add_test("bad name", run=[DUMMY_OK_STEP_DESC], save=True)
    results = xut.run_tests_list(names=[TEST0, TEST1, "bad name"])
    assert len(results) == 3
    for r in results:
        assert r.status.primary == TestPrimaryStatus.NotRun
        assert r.status.secondary == TestSecondaryStatus.InitErr


def test_simple_test(xut: XeetUnittest):
    xut.add_test(TEST0, run=[DUMMY_OK_STEP_DESC])
    xut.add_test(TEST1, run=[DUMMY_FAILING_STEP_DESC])
    xut.add_test(TEST2, run=[DUMMY_INCOMPLETED_STEP_DESC], save=True)

    expected = gen_test_result(status=PASSED_TEST_STTS, main_results=[DUMMY_OK_STEP_RES])
    xut.run_compare_test(TEST0, expected)

    expected.main_res.steps_results = [DUMMY_FAILING_STEP_RES]
    expected.status = FAILED_TEST_STTS
    xut.run_compare_test(TEST1, expected)

    expected.main_res.steps_results = [DUMMY_INCOMPLETED_STEP_RES]
    expected.status = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.TestErr)
    xut.run_compare_test(TEST2, expected)


def test_phases(xut: XeetUnittest):
    # To make things shorter
    ok_step = DUMMY_OK_STEP_DESC
    ok_res = DUMMY_OK_STEP_RES
    incompleted_step = DUMMY_INCOMPLETED_STEP_DESC
    incompleted_res = DUMMY_INCOMPLETED_STEP_RES
    failing_step = DUMMY_FAILING_STEP_DESC
    failing_res = DUMMY_FAILING_STEP_RES

    xut.add_test(TEST0, run=[ok_step])
    xut.add_test(TEST1, run=[ok_step, failing_step, ok_step])
    xut.add_test(TEST2, run=[ok_step, incompleted_step, ok_step], save=True)

    expected = gen_test_result(status=PASSED_TEST_STTS, main_results=[ok_res])
    xut.run_compare_test(TEST0, expected)

    expected.main_res.steps_results = [ok_res, failing_res]
    expected.status = FAILED_TEST_STTS
    xut.run_compare_test(TEST1, expected)

    expected.main_res.steps_results = [ok_res, incompleted_res]
    expected.status = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.TestErr)
    xut.run_compare_test(TEST2, expected)

    ok_ok_list = [ok_step, ok_step]
    ok_ok_res_list: list[StepResult] = [ok_res, ok_res]
    ok_ok_ok_list = [ok_step, ok_step, ok_step]
    ok_ok_ok_res_list: list[StepResult] = [ok_res, ok_res, ok_res]
    ok_fail_ok_list = [ok_step, failing_step, ok_step]

    ok_fail_ok_res_list: list[StepResult] = [ok_res, failing_res, ok_res]
    ok_fail_res_list: list[StepResult] = [ok_res, failing_res]
    ok_incomplete_ok_list = [ok_step, incompleted_step, ok_step]
    ok_incomplete_ok_res_list: list[StepResult] = [ok_res, incompleted_res, ok_res]
    ok_incomplete_res_list: list[StepResult] = [ok_res, incompleted_res]
    xut.add_test(TEST0, pre_run=ok_ok_list, run=ok_ok_ok_list, post_run=ok_ok_list, reset=True)

    # The following 3 tests should all not-run due to the failing pre-run step.
    xut.add_test(TEST1, pre_run=ok_fail_ok_list, run=ok_ok_list, post_run=ok_ok_list)
    xut.add_test(TEST2, base=TEST1)
    xut.add_test(TEST3, base=TEST0, pre_run=ok_fail_ok_list, save=True)
    expected = gen_test_result(status=PASSED_TEST_STTS,
                               pre_results=dup_step_res_list(ok_ok_res_list),
                               main_results=dup_step_res_list(ok_ok_ok_res_list),
                               post_results=dup_step_res_list(ok_ok_res_list))

    xut.run_compare_test(TEST0, expected)
    expected.status = TestStatus(TestPrimaryStatus.NotRun,
                                 TestSecondaryStatus.PreTestErr)
    expected.pre_run_res.steps_results = dup_step_res_list(ok_fail_res_list)
    expected.main_res.steps_results = []
    expected.post_run_res.steps_results = dup_step_res_list(ok_ok_res_list)
    for t in (TEST1, TEST2, TEST3):
        xut.run_compare_test(t, expected)
    # Check failing run step
    xut.add_test(TEST0, pre_run=ok_ok_list, run=ok_fail_ok_list, post_run=ok_ok_list,
                 reset=True)
    xut.add_test(TEST1, base=TEST0, save=True)
    expected = gen_test_result(status=FAILED_TEST_STTS,
                               pre_results=dup_step_res_list(ok_ok_res_list),
                               main_results=dup_step_res_list(ok_fail_res_list),
                               post_results=dup_step_res_list(ok_ok_res_list))
    for t in (TEST0, TEST1):
        xut.run_compare_test(t, expected)
    # Check incomplete run step
    xut.add_test(TEST0, pre_run=ok_ok_list, run=ok_incomplete_ok_list, post_run=ok_ok_list,
                 reset=True)
    xut.add_test(TEST1, base=TEST0)

    # Add some variations, and validate post-run always runs
    xut.add_test(TEST2, base=TEST0, post_run=[])
    xut.add_test(TEST3, base=TEST2, post_run=ok_incomplete_ok_list)
    xut.add_test(TEST4, base=TEST3, post_run=ok_fail_ok_list, save=True)
    expected = gen_test_result(status=TestStatus(TestPrimaryStatus.NotRun,
                                                 TestSecondaryStatus.TestErr),
                               pre_results=dup_step_res_list(ok_ok_res_list),
                               main_results=dup_step_res_list(ok_incomplete_res_list),
                               post_results=dup_step_res_list(ok_ok_res_list))
    for t in (TEST0, TEST1):
        xut.run_compare_test(t, expected)
    expected.post_run_res.steps_results = []
    xut.run_compare_test(TEST2, expected)
    expected.post_run_res.steps_results = dup_step_res_list(ok_incomplete_ok_res_list)
    xut.run_compare_test(TEST3, expected)
    expected.post_run_res.steps_results = dup_step_res_list(ok_fail_ok_res_list)
    xut.run_compare_test(TEST4, expected)


def test_abstract_tests(xut: XeetUnittest):
    xut.add_test(TEST0, run=[DUMMY_OK_STEP_DESC], abstract=True)
    xut.add_test(TEST1, base=TEST0)
    xut.add_test(TEST2, base=TEST0, run=[DUMMY_FAILING_STEP_DESC], save=True)
    with pytest.raises(XeetException):
        xut.run_test(TEST0)

    expected = gen_test_result(status=PASSED_TEST_STTS, main_results=[DUMMY_OK_STEP_RES])
    xut.run_compare_test(TEST1, expected)

    expected.status = FAILED_TEST_STTS
    expected.main_res.steps_results = [DUMMY_FAILING_STEP_RES]
    xut.run_compare_test(TEST2, expected)


def test_skipped_tests(xut: XeetUnittest):
    xut.add_test(TEST0, pre_run=[DUMMY_FAILING_STEP_DESC], run=[
                  DUMMY_OK_STEP_DESC], skip=True)
    xut.add_test(TEST1, base=TEST0, skip=True)  # Skip isn't inherited
    xut.add_test(TEST2, base=TEST0, save=True)

    expected = gen_test_result(status=TestStatus(TestPrimaryStatus.Skipped))
    for test in [TEST0, TEST1]:
        xut.run_compare_test(test, expected)

    expected.status = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.PreTestErr)
    expected.pre_run_res.steps_results = [DUMMY_FAILING_STEP_RES]
    xut.run_compare_test(TEST2, expected)


def test_expected_failure(xut: XeetUnittest):
    xut.add_test(TEST0, run=[DUMMY_FAILING_STEP_DESC], expected_failure=True)
    xut.add_test(TEST1, base=TEST0, expected_failure=True)
    xut.add_test(TEST2, base=TEST0, post_run=[DUMMY_INCOMPLETED_STEP_DESC])
    xut.add_test(TEST3, base=TEST2, run=[DUMMY_OK_STEP_DESC], save=True)

    expected = gen_test_result(status=TestStatus(TestPrimaryStatus.Passed,
                                                 TestSecondaryStatus.ExpectedFail),
                               main_results=[DUMMY_FAILING_STEP_RES])
    for test in [TEST0, TEST1]:
        xut.run_compare_test(test, expected)

    # Expected failure aren't inherited
    expected.status = FAILED_TEST_STTS
    expected.post_run_res.steps_results = [DUMMY_INCOMPLETED_STEP_RES]
    xut.run_compare_test(TEST2, expected)

    expected.status = PASSED_TEST_STTS
    expected.main_res.steps_results = [DUMMY_OK_STEP_RES]
    xut.run_compare_test(TEST3, expected)


def test_autovars(xut: XeetUnittest):
    xeet_root = os.path.dirname(xut.file_path)
    xeet_root = platform_path(xeet_root)
    out_dir = f"{xeet_root}/xeet.out"

    step_desc0 = gen_dummy_step_desc(dummy_val0="{XEET_ROOT} {XEET_CWD} {XEET_OUT_DIR}")
    step_desc1 = gen_dummy_step_desc(dummy_val0="{XEET_TEST_NAME} {XEET_TEST_OUT_DIR}")
    step_desc2 = gen_dummy_step_desc(dummy_val0="{XEET_PLATFORM}")

    xut.add_test(TEST0, run=[step_desc0, step_desc1], save=True)
    xut.add_test(TEST0, run=[step_desc0, step_desc1, step_desc2], reset=True, save=True)

    cwd = platform_path(os.getcwd())
    expected_step_result0 = gen_dummy_step_result(step_desc0)
    expected_step_result0.dummy_val0 = f"{xeet_root} {cwd} {out_dir}"
    expected_step_result1 = gen_dummy_step_result(step_desc1)
    expected_step_result1.dummy_val0 = f"{TEST0} {out_dir}/{TEST0}"
    expected_step_result2 = gen_dummy_step_result(step_desc2)
    expected_step_result2.dummy_val0 = os.name
    expected = gen_test_result(status=PASSED_TEST_STTS,
                               main_results=[expected_step_result0, expected_step_result1,
                                             expected_step_result2])
    xut.run_compare_test(TEST0, expected)


def _fetch_tests(xut: XeetUnittest, criteria: TestsCriteria) -> list[Test]:
    return fetch_tests_list(xut.file_path, criteria)


def test_fetch_tests(xut: XeetUnittest):
    criteria = TestsCriteria()
    xut.add_test(TEST0)
    xut.add_test(TEST1)
    xut.add_test(TEST2)
    xut.add_test(TEST3)
    xut.add_test(TEST4)
    xut.add_test(TEST5, save=True)

    tests = _fetch_tests(xut, criteria)
    assert len(tests) == 6
    assert set([t.name for t in tests]) == set([TEST0, TEST1, TEST2, TEST3, TEST4, TEST5])

    criteria.names = set([TEST0, TEST1, TEST5])
    tests = _fetch_tests(xut, criteria)
    assert len(tests) == 3
    assert set([t.name for t in tests]) == criteria.names

    criteria.names = set([TEST0, TEST1, TEST5, "no such test"])
    tests = _fetch_tests(xut, criteria)
    assert len(tests) == 3
    assert set([t.name for t in tests]) == set([TEST0, TEST1, TEST5])


def test_fetch_groups_list(xut: XeetUnittest):
    xut.add_test(TEST0, groups=["group0", "group1"])
    xut.add_test(TEST1, groups=["group1"])
    xut.add_test(TEST2, groups=["group1", "group2"])
    xut.add_test(TEST3, groups=["group2"])
    xut.add_test(TEST4, groups=["group2"])
    xut.add_test(TEST5, save=True)
    criteria = TestsCriteria(include_groups={"group1"})

    tests = _fetch_tests(xut, criteria)
    assert len(tests) == 3
    assert set([t.name for t in tests]) == set([TEST0, TEST1, TEST2])

    criteria.include_groups = set()
    criteria.names = set([TEST0, TEST2, TEST3, "no such test"])
    tests = _fetch_tests(xut, criteria)
    assert len(tests) == 3
    assert set([t.name for t in tests]) == set([TEST0, TEST2, TEST3])


def test_step_details(xut: XeetUnittest):
    test_desc = gen_dummy_step_desc(dummy_val0="test {test_var}", dummy_val1=10)
    xut.add_var("test_var", "var")
    xut.add_test(TEST0, run=[test_desc], save=True)

    test = xut.get_test(TEST0)
    assert test is not None
    step = test.main_phase.steps[0]

    step_details = step.details(full=False, printable=False, setup=False)
    step_details = dict(step_details)

    assert set(step_details.keys()) == {"dummy_val0", "dummy_val1", "step_type"}
    assert step_details["dummy_val0"] == "test {test_var}"
    assert step_details["dummy_val1"] == 10
    assert step_details["step_type"] == "dummy"

    step_details = step.details(full=False, printable=True, setup=False)
    assert len(step_details) > 2
    # Check the dummy reordering, type is 0
    assert step_details[1][0] == "Dummy val1"
    assert step_details[2][0] == "Dummy val0"
    step_details = dict(step_details)
    assert set(step_details.keys()) == {"Dummy val0", "Dummy val1", "Step type"}
    assert step_details["Dummy val0"] == "test {test_var}"
    assert step_details["Dummy val1"] == 10
    assert step_details["Step type"] == "dummy"

    test = xut.get_test(TEST0)
    assert test is not None
    test.setup()
    step = test.main_phase.steps[0]
    step_details = step.details(full=False, printable=False, setup=True)
    step_details = dict(step_details)
    assert set(step_details.keys()) == {"dummy_val0", "dummy_val1", "step_type", "dummy_extra"}
    assert step_details["dummy_val0"] == "test var"
    assert step_details["dummy_val1"] == 10
    assert step_details["step_type"] == "dummy"
    assert step_details["dummy_extra"] == id(step)

    step_details = step.details(full=False, printable=True, setup=True)
    step_details = dict(step_details)
    assert set(step_details.keys()) == {"Dummy val0",
                                        "Dummy val1", "Step type", "Dummy extra print"}
    assert step_details["Dummy val0"] == "test var"
    assert step_details["Dummy val1"] == 10
    assert step_details["Step type"] == "dummy"


def test_platform_support(xut: XeetUnittest):
    step_desc = gen_dummy_step_desc(dummy_val0="test", dummy_val1=10)
    expected_step_res = gen_dummy_step_result(step_desc)
    this_platform = os.name
    other_platform = "nt" if this_platform != "nt" else "posix"
    xut.add_test(TEST0, platforms=[this_platform], run=[step_desc], reset=True)
    xut.add_test(TEST1, platforms=[this_platform, other_platform], run=[step_desc])
    xut.add_test(TEST2, platforms=[other_platform], run=[step_desc], save=True)

    expected = gen_test_result(status=PASSED_TEST_STTS, main_results=[expected_step_res])
    xut.run_compare_test(TEST0, expected)
    xut.run_compare_test(TEST1, expected)

    expected = gen_test_result(status=TestStatus(TestPrimaryStatus.Skipped))
    xut.run_compare_test(TEST2, expected)


def test_thread_support(xut: XeetUnittest):
    sleep1_desc = gen_exec_step_desc(cmd=gen_sleep_cmd(1))
    xut.add_test(TEST0, run=[sleep1_desc])
    xut.add_test(TEST1, run=[sleep1_desc])
    xut.add_test(TEST2, run=[sleep1_desc], save=True)

    start = timer()
    results = xut.run_tests_list([TEST0, TEST1, TEST2], threads=3)
    results = list(results)
    duration = timer() - start
    assert duration < 3 and duration > 1
    for res in results:
        assert res.status.primary == TestPrimaryStatus.Passed
        assert res.duration >= 1
