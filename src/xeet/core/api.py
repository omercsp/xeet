from . import TestCriteria
from .xtest import Xtest, XtestModel
from .xres import TestResult, TestStatus, TestSubStatus, RunResult, status_as_str
from .driver import XeetModel, xeet_init
from .run_reporter import RunReporter
from xeet import XeetException
from timeit import default_timer as timer
from enum import Enum
from xeet.log import log_info, log_blank, log_verbose


def fetch_xtest(config_path: str, name: str, setup: bool = False) -> Xtest | None:
    ret = xeet_init(config_path).xtest(name)
    if ret is not None and setup:
        ret.setup()
    return ret


def fetch_tests_list(config_path: str, criteria: TestCriteria) -> list[Xtest]:
    log_verbose(f"Fetch tests list cirteria: {criteria}")
    return xeet_init(config_path).xtests(criteria)


def fetch_groups_list(config_path: str) -> list[str]:
    config = xeet_init(config_path)
    return list(config.all_groups())


def fetch_test_desc(config_path: str, name: str) -> dict | None:
    return xeet_init(config_path).test_desc(name)


def fetch_config(config_path: str) -> dict:
    return xeet_init(config_path).xdefs.defs_dict


class SchemaType(str, Enum):
    CONFIG = "config"
    XTEST = "test"
    UNIFIED = "unified"


def fetch_schema(schema_type: str) -> dict:
    if schema_type == SchemaType.CONFIG.value:
        return XeetModel.model_json_schema()
    if schema_type == SchemaType.XTEST.value:
        return XtestModel.model_json_schema()
    if schema_type == SchemaType.UNIFIED.value:
        d = XeetModel.model_json_schema()
        d["properties"]["tests"]["items"] = XtestModel.model_json_schema()
        return d
    raise XeetException(f"Invalid dump type: {schema_type}")


def _run_test(test: Xtest) -> TestResult:
    if test.error:
        return TestResult(status=TestStatus.RunErr, sub_status=TestSubStatus.InitErr,
                          status_reason=test.error)

    log_info(f"Running test '{test.name}'")
    start = timer()
    ret = test.run()
    ret.duration = timer() - start
    return ret


def run_tests(conf: str,
              criteria: TestCriteria,
              reporters: RunReporter | list[RunReporter],
              debug_mode: bool = False,
              iterations: int = 1) -> RunResult:
    log_info("Starting run", pr_suffix="------------\n")
    if not isinstance(reporters, list):
        reporters = [reporters]
    driver = xeet_init(conf, debug_mode, reporters)
    notifier = driver.xdefs.notifier
    if criteria.include_groups:
        groups_str = ", ".join(sorted(criteria.include_groups))
        log_info(f"Included groups: {groups_str}")
    if criteria.exclude_groups:
        groups_str = ", ".join(sorted(criteria.exclude_groups))
        log_info(f"Excluded groups: {groups_str}")
    if criteria.require_groups:
        groups_str = ", ".join(sorted(criteria.require_groups))
        log_info(f"Required groups: {groups_str}")

    tests = driver.xtests(criteria)
    if not tests:
        raise XeetException("No tests to run")

    log_info("Tests run list: {}".format(", ".join([x.name for x in tests])))

    run_res = RunResult(iterations=iterations, criteria=criteria)
    notifier.on_run_start(run_res, tests)

    for iter_n in range(iterations):
        iter_res = run_res.iter_results[iter_n]
        if iterations > 1:
            log_info(f">>> Iteration {iter_n}/{iterations - 1}")
        driver.xdefs.set_iteration(iter_n, iterations)
        notifier.on_iteration_start(iter_res, iter_n)
        for test in tests:
            notifier.on_test_start(test)
            test_res = _run_test(test)
            iter_res.add_test_result(test.name, test_res)
            notifier.on_test_end(test, test_res)
        notifier.on_iteration_end()

        if iterations > 1:
            log_info(f"Finished iteration #{iter_n}/{iterations - 1}")
        for status, sub_status in iter_res.status_results_summary:
            test_names = iter_res.status_results_summary[(status, sub_status)]
            if not test_names:
                continue
            test_list_str = ", ".join(test_names)
            log_info(f"{status_as_str(status, sub_status)}: {test_list_str}")
    notifier.on_run_end()
    return run_res
