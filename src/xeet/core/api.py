from . import TestsCriteria
from .test import Test, TestModel
from .result import (TestResult, TestPrimaryStatus, TestSecondaryStatus, RunResult, TestStatus,
                     EmptyRunResult)
from .driver import XeetModel, xeet_init
from .run_reporter import RunReporter
from xeet.log import log_info, log_verbose
from xeet import XeetException
from timeit import default_timer as timer
from enum import Enum


def fetch_xtest(config_path: str, name: str, setup: bool = False) -> Test | None:
    ret = xeet_init(config_path).get_test(name)
    if ret is not None and setup:
        ret.setup()
    return ret


def fetch_tests_list(config_path: str, criteria: TestsCriteria) -> list[Test]:
    log_verbose(f"Fetch tests list cirteria: {criteria}")
    return xeet_init(config_path).get_tests(criteria)


def fetch_groups_list(config_path: str) -> list[str]:
    config = xeet_init(config_path)
    return list(config.all_groups())


def fetch_test_desc(config_path: str, name: str) -> dict | None:
    return xeet_init(config_path).test_desc(name)


def fetch_config(config_path: str) -> dict:
    return xeet_init(config_path).rti.defs_dict


class SchemaType(str, Enum):
    CONFIG = "config"
    XTEST = "test"
    UNIFIED = "unified"


def fetch_schema(schema_type: str) -> dict:
    if schema_type == SchemaType.CONFIG.value:
        return XeetModel.model_json_schema()
    if schema_type == SchemaType.XTEST.value:
        return TestModel.model_json_schema()
    if schema_type == SchemaType.UNIFIED.value:
        d = XeetModel.model_json_schema()
        d["properties"]["tests"]["items"] = TestModel.model_json_schema()
        return d
    raise XeetException(f"Invalid dump type: {schema_type}")


def _run_test(test: Test) -> TestResult:
    if test.error:
        return TestResult(TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr),
                          status_reason=test.error)

    log_info(f"Running test '{test.name}'")
    start = timer()
    ret = test.run()
    ret.duration = timer() - start
    return ret


def run_tests(conf: str,
              criteria: TestsCriteria,
              reporters: RunReporter | list[RunReporter],
              debug_mode: bool = False,
              iterations: int = 1) -> RunResult:
    log_info("Starting run", pr_suffix="------------\n")
    if not isinstance(reporters, list):
        reporters = [reporters]
    driver = xeet_init(conf, debug_mode, reporters)
    notifier = driver.rti.notifier
    log_info(str(criteria))

    tests = driver.get_tests(criteria)
    if not tests:
        return EmptyRunResult
    run_res = RunResult(iterations=iterations, criteria=criteria)

    log_info("Tests run list: {}".format(", ".join([x.name for x in tests])))
    notifier.on_run_start(run_res, tests)

    for iter_n in range(iterations):
        iter_res = run_res.iter_results[iter_n]
        if iterations > 1:
            log_info(f">>> Iteration {iter_n}/{iterations - 1}")
        driver.rti.set_iteration(iter_n, iterations)
        notifier.on_iteration_start(iter_res, iter_n)
        for test in tests:
            notifier.on_test_start(test)
            test_res = _run_test(test)
            iter_res.add_test_result(test.name, test_res)
            notifier.on_test_end(test, test_res)
        notifier.on_iteration_end()

        if iterations > 1:
            log_info(f"Finished iteration #{iter_n}/{iterations - 1}")
        for status, test_names in iter_res.status_results_summary.items():
            if not test_names:
                continue
            test_list_str = ", ".join(test_names)
            log_info(f"{status}: {test_list_str}")
    notifier.on_run_end()
    return run_res
