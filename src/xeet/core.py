from xeet.runtime import RunInfo
from xeet.xtest import Xtest, XtestModel, TestResult, TestStatus
from xeet.driver import XeetModel, xeet_init, TestCriteria
from xeet.common import XeetException
from xeet.log import log_info, log_blank, log_verbose
from xeet import RunReporter
from enum import Enum
from timeit import default_timer as timer


def fetch_xtest(config_path: str, name: str) -> Xtest | None:
    return xeet_init(config_path).xtest(name)


def fetch_tests_list(config_path: str, criteria: TestCriteria) -> list[Xtest]:
    log_verbose(f"Fetch tests list cirteria: {criteria}")
    return xeet_init(config_path).xtests(criteria)


def fetch_groups_list(config_path: str) -> list[str]:
    config = xeet_init(config_path)
    return list(config.all_groups())


def fetch_test_desc(config_path: str, name: str) -> dict | None:
    return xeet_init(config_path).test_desc(name)


def fetch_config(config_path: str) -> dict:
    return xeet_init(config_path).defs.defs_dict


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
        return TestResult(status=TestStatus.InitErr, status_reason=test.error)

    log_info(f"Running test '{test.name}'")
    test.xdefs.reporter.on_test_setup_start(test)
    test.setup()
    test.xdefs.reporter.on_test_setup_end()
    start = timer()
    ret = test.run()
    ret.duration = timer() - start
    return ret


def run_tests(conf: str,
              criteria: TestCriteria,
              reporter: RunReporter,
              debug_mode: bool = False,
              iterations: int = 1) -> RunInfo:
    log_info("Starting run", pr_suffix="------------\n")
    driver = xeet_init(conf, debug_mode)
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

    log_info("Running tests: {}\n".format(", ".join([x.name for x in tests])))

    run_info = RunInfo(iterations=iterations, tests=tests, criteria=criteria)
    driver.defs.reporter = reporter

    reporter.on_run_start(run_info)
    for iter_n in range(iterations):
        iter_info = run_info.iterations_info[iter_n]
        if iterations > 1:
            log_info(f">>> Iteration {iter_n}/{iterations - 1}")
        reporter.on_iteration_start(iter_info, iter_n)
        for test in tests:
            reporter.on_test_enter(test)
            test_res = _run_test(test)
            run_info.add_test_result(test.name, iter_n, test_res)
            reporter.on_test_end(test_res)
            reporter.xtest = None  # type: ignore
            log_blank()
        reporter.on_iteration_end()

        if iterations > 1:
            log_info(f"Finished iteration #{iter_n}/{iterations - 1}")
        for status in TestStatus:
            test_names = iter_info.tests[status]
            if not test_names:
                continue
            test_list_str = ", ".join(test_names)
            log_info(f"{status}: {test_list_str}")
    reporter.on_run_end()
    return run_info
