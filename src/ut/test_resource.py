from ut import *
from ut.ut_dummy_defs import *
from ut.ut_exec_defs import gen_sleep_cmd, gen_exec_step_desc, GOOD_EXEC_STEP_RES
from xeet.core.result import TestStatus, TestPrimaryStatus, TestSecondaryStatus
from xeet.core.test import TestPrimaryStatus
from timeit import default_timer as timer
from typing import Any
import random


def gen_resouce_req(res_name: str, count: int | None = None, names: list[str] = list(),
                    as_var: str = "") -> dict:
    desc: dict[str, Any] = {"pool": res_name}
    if count is not None:
        desc["count"] = count
    if names:
        desc["names"] = names
    if as_var:
        desc["as_var"] = as_var
    return desc


def test_simple_synchronized_support(xut: XeetUnittest):
    xut.add_resource("res1", "", "simple", reset=True)

    sleep1_desc = gen_exec_step_desc(cmd=gen_sleep_cmd(0.5))
    res1_desc = gen_resouce_req("res1")
    xut.add_test(TEST0, run=[sleep1_desc], resources=[res1_desc])
    xut.add_test(TEST1, run=[sleep1_desc], resources=[res1_desc])
    xut.add_test(TEST2, run=[sleep1_desc], resources=[res1_desc], save=True)

    start = timer()
    results = xut.run_tests_list([TEST0, TEST1, TEST2], threads=3)
    results = list(results)
    duration = timer() - start
    assert duration > 1.5


def test_get_resource_by_name(xut: XeetUnittest):
    xut.add_resource("res1", "r0", "simple", reset=True)
    xut.add_resource("res1", "r1", "simple")

    xut.add_test(TEST0, run=[DUMMY_OK_STEP_DESC],
                 resources=[gen_resouce_req("res1", names=["r0"])])
    xut.add_test(TEST1, run=[DUMMY_OK_STEP_DESC], resources=[
                 gen_resouce_req("res1", names=["r0", "r1"])])
    xut.add_test(TEST2, run=[DUMMY_OK_STEP_DESC],
                 resources=[gen_resouce_req("res1", names=["r1"])])

    #  Bad resource requests
    xut.add_test(TEST3, run=[DUMMY_OK_STEP_DESC],
                 resources=[gen_resouce_req("res1", names=["r3"])])

    xut.add_test(TEST4, run=[DUMMY_OK_STEP_DESC],
                 resources=[gen_resouce_req("res1", names=["r1", "r1"])])

    xut.add_test(TEST5, run=[DUMMY_OK_STEP_DESC],
                 resources=[gen_resouce_req("res1", names=["r0", "r1", "r2"])],
                 save=True)

    expected = gen_test_result(status=PASSED_TEST_STTS, main_results=[DUMMY_OK_STEP_RES])
    results = xut.run_tests_list([TEST0, TEST1, TEST2], threads=3)
    for res in results:
        xut.update_test_res_test(expected, res.test.name)
        assert_test_results_equal(res, expected)

    expected = gen_test_result(
        status=TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr))
    results = xut.run_tests_list([TEST3, TEST4, TEST5], threads=3)
    for res in results:
        xut.update_test_res_test(expected, res.test.name)
        assert_test_results_equal(res, expected)


def test_get_resource_by_count(xut: XeetUnittest):
    xut.add_resource("res1", "", "simple", reset=True)

    xut.add_test(TEST0, run=[DUMMY_OK_STEP_DESC],
                 resources=[gen_resouce_req("res1", count=1)])
    xut.add_test(TEST1, run=[DUMMY_OK_STEP_DESC],
                 resources=[gen_resouce_req("res1", count=1)])
    xut.add_test(TEST2, run=[DUMMY_OK_STEP_DESC],
                 resources=[gen_resouce_req("res1", count=0)])
    xut.add_test(TEST3, run=[DUMMY_OK_STEP_DESC],
                 resources=[gen_resouce_req("res1", count=2)], save=True, show=False)

    expected = gen_test_result(status=PASSED_TEST_STTS, main_results=[DUMMY_OK_STEP_RES])
    results = xut.run_tests_list([TEST0, TEST1], threads=3)
    for res in results:
        xut.update_test_res_test(expected, res.test.name)
        assert_test_results_equal(res, expected)

    expected = gen_test_result(
        status=TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr))
    results = xut.run_tests_list([TEST2], threads=3)
    for res in results:
        xut.update_test_res_test(expected, res.test.name)
        assert_test_results_equal(res, expected)


def test_randomized_resource_race(xut: XeetUnittest):
    xut.add_resource("res1", "", "simple", reset=True)
    xut.add_resource("res1", "", "simple")
    xut.add_resource("res2", "", "simple")
    N = 20

    for i in range(N):
        #  Random sleep time between 0.1 and 0.9
        sleep_time = round(random.randint(1, 8) * 0.01, 2)
        sleep_desc = gen_exec_step_desc(cmd=gen_sleep_cmd(sleep_time))
        res_one_usage = random.choice([0, 2])
        res_two_usage = random.choice([0, 1])
        resource = []
        if res_one_usage:
            resource.append(gen_resouce_req("res1", count=res_one_usage))
        if res_two_usage:
            resource.append(gen_resouce_req("res2", count=res_two_usage))
        xut.add_test(f"test{i}", run=[sleep_desc], resources=resource)
    xut.save()
    expected = gen_test_result(status=PASSED_TEST_STTS, main_results=[GOOD_EXEC_STEP_RES])
    for i in range(2, 12, 2):
        results = xut.run_tests(threads=i).iter_results[0].mtrx_results[0].results
        assert len(list(results)) == N
        for name, res in results.items():
            xut.update_test_res_test(expected, name)
            assert_test_results_equal(res, expected)
