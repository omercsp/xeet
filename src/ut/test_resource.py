from ut import *
from ut.ut_dummy_defs import *
from ut.ut_exec_defs import GOOD_EXEC_RES, gen_sleep_cmd, gen_exec_step_desc
from xeet.core.xres import XStepListResult, TestStatus, TestPrimaryStatus, TestSecondaryStatus
from xeet.core.xtest import TestResult, TestPrimaryStatus
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


class TestResourcesUsage(XeetUnittest):
    def test_simple_synchronized_support(self):
        self.add_resource("res1", "", "simple", reset=True)

        sleep1_desc = gen_exec_step_desc(cmd=gen_sleep_cmd(0.5))
        res1_desc = gen_resouce_req("res1")
        self.add_test(TEST0, run=[sleep1_desc], resources=[res1_desc])
        self.add_test(TEST1, run=[sleep1_desc], resources=[res1_desc])
        self.add_test(TEST2, run=[sleep1_desc], resources=[res1_desc], save=True)

        start = timer()
        results = self.run_tests_list([TEST0, TEST1, TEST2], threads=3)
        results = list(results)
        duration = timer() - start
        self.assertGreater(duration, 1.5)

    def test_get_resource_by_name(self):
        self.add_resource("res1", "r0", "simple", reset=True)
        self.add_resource("res1", "r1", "simple")

        self.add_test(TEST0, run=[DUMMY_OK_STEP_DESC],
                      resources=[gen_resouce_req("res1", names=["r0"])])
        self.add_test(TEST1, run=[DUMMY_OK_STEP_DESC], resources=[
                      gen_resouce_req("res1", names=["r0", "r1"])])
        self.add_test(TEST2, run=[DUMMY_OK_STEP_DESC],
                      resources=[gen_resouce_req("res1", names=["r1"])])

        #  Bad resource requests
        self.add_test(TEST3, run=[DUMMY_OK_STEP_DESC],
                      resources=[gen_resouce_req("res1", names=["r3"])])

        self.add_test(TEST4, run=[DUMMY_OK_STEP_DESC],
                      resources=[gen_resouce_req("res1", names=["r1", "r1"])])

        self.add_test(TEST5, run=[DUMMY_OK_STEP_DESC],
                      resources=[gen_resouce_req("res1", names=["r0", "r1", "r2"])],
                      save=True)

        expected_test_steps_results = XStepListResult(results=[DUMMY_OK_STEP_RES])
        expected = TestResult(PASSED_TEST_STTS, run_res=expected_test_steps_results)
        results = self.run_tests_list([TEST0, TEST1, TEST2], threads=3)
        for res in results:
            self.assertTestResultEqual(res, expected)

        expected = TestResult(TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr))
        results = self.run_tests_list([TEST3, TEST4, TEST5], threads=3)
        for res in results:
            self.assertTestResultEqual(res, expected)

    def test_get_resource_by_count(self):
        self.add_resource("res1", "", "simple", reset=True)

        self.add_test(TEST0, run=[DUMMY_OK_STEP_DESC],
                      resources=[gen_resouce_req("res1", count=1)])
        self.add_test(TEST1, run=[DUMMY_OK_STEP_DESC],
                      resources=[gen_resouce_req("res1", count=1)])
        self.add_test(TEST2, run=[DUMMY_OK_STEP_DESC],
                      resources=[gen_resouce_req("res1", count=0)])
        self.add_test(TEST3, run=[DUMMY_OK_STEP_DESC],
                      resources=[gen_resouce_req("res1", count=2)], save=True, show=False)

        expected_test_steps_results = XStepListResult(results=[DUMMY_OK_STEP_RES])
        expected = TestResult(PASSED_TEST_STTS, run_res=expected_test_steps_results)
        results = self.run_tests_list([TEST0, TEST1], threads=3)
        for res in results:
            self.assertTestResultEqual(res, expected)

        expected = TestResult(TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr))
        results = self.run_tests_list([TEST2], threads=3)
        for res in results:
            self.assertTestResultEqual(res, expected)

    def test_randomized_resource_race(self):
        self.add_resource("res1", "", "simple", reset=True)
        self.add_resource("res1", "", "simple")
        self.add_resource("res2", "", "simple")
        N = 20

        for i in range(N):
            #  Random sleep time between 0.1 and 0.9
            sleep_time = round(random.randint(1, 5) * 0.1, 1)
            sleep_desc = gen_exec_step_desc(cmd=gen_sleep_cmd(sleep_time))
            res_one_usage = random.choice([0, 2])
            res_two_usage = random.choice([0, 1])
            resource = []
            if res_one_usage:
                resource.append(gen_resouce_req("res1", count=res_one_usage))
            if res_two_usage:
                resource.append(gen_resouce_req("res2", count=res_two_usage))
            self.add_test(f"test{i}", run=[sleep_desc], resources=resource)
        self.main_config_wrapper.save()
        for i in range(2, 8, 2):
            #  results = self.run_tests_list([f"test{j}" for j in range(i)], threads=3)
            results = self.run_all_tests(threads=i)
            self.assertEqual(len(list(results)), N)
            for res in results:
                self.assertTestResultEqual(res, GOOD_EXEC_RES)
