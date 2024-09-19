from xeet.runtime import RunInfo
from xeet.xtest import Xtest, XtestModel, TestResult, TestStatus
from xeet.driver import XeetModel, xeet_init, TestCriteria
from xeet.common import XeetException
from xeet.log import log_info, log_blank, log_verbose
from enum import Enum
from dataclasses import dataclass


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


@dataclass
class RunSettings:
    iterations: int
    debug_mode: bool
    criteria: TestCriteria

    def on_test_enter(self, **_) -> None:
        pass

    def on_test_end(self, **_) -> None:
        pass

    def on_iteration_end(self, **_) -> None:
        pass

    def on_iteration_start(self, **_) -> None:
        pass

    def on_run_start(self, **_) -> None:
        pass

    def on_run_end(self, **_) -> None:
        pass


def _run_single_test(test: Xtest, settings: RunSettings) -> TestResult:
    if test.init_err:
        return TestResult(status=TestStatus.InitErr, status_reason=test.init_err)

    log_info(f"Running test '{test.name}'")
    test.expand()
    test.debug_mode = settings.debug_mode
    return test.run()


def run_tests(conf: str, run_settings: RunSettings) -> RunInfo:
    log_info("Starting run", pr_suffix="------------\n")
    config = xeet_init(conf)
    config.xvars.set_vars({"DEBUG": "1" if run_settings.debug_mode else "0"})
    criteria = run_settings.criteria
    if criteria.include_groups:
        groups_str = ", ".join(sorted(criteria.include_groups))
        log_info(f"Included groups: {groups_str}")
    if criteria.exclude_groups:
        groups_str = ", ".join(sorted(criteria.exclude_groups))
        log_info(f"Excluded groups: {groups_str}")
    if criteria.require_groups:
        groups_str = ", ".join(sorted(criteria.require_groups))
        log_info(f"Required groups: {groups_str}")

    tests = config.xtests(run_settings.criteria)
    if not tests:
        raise XeetException("No tests to run")

    log_info("Running tests: {}\n".format(", ".join([x.name for x in tests])))

    iterations = run_settings.iterations
    run_info = RunInfo(iterations=iterations, tests=tests)

    run_settings.on_run_start(run_info=run_info)
    for iter_n in range(iterations):
        iter_info = run_info.iterations_info[iter_n]
        if iterations > 1:
            log_info(f">>> Iteration {iter_n}/{iterations - 1}")
        run_settings.on_iteration_start(iter_info=iter_info, run_info=run_info)
        for test in tests:
            run_settings.on_test_enter(test=test, iter_info=iter_info, run_info=run_info)
            test_res = _run_single_test(test, run_settings)
            run_settings.on_test_end(result=test_res, test=test, iter_info=iter_info,
                                     run_info=run_info)
            run_info.add_test_result(test.name, iter_n, test_res)
            log_blank()
        if run_settings.debug_mode:
            continue
        run_settings.on_iteration_end(iter_info=iter_info, run_info=run_info)

        if iterations > 1:
            log_info(f"Finished iteration #{iter_n}/{iterations - 1}")
        for status in TestStatus:
            test_names = iter_info.tests[status]
            if not test_names:
                continue
            test_list_str = ", ".join(test_names)
            log_info(f"{status}: {test_list_str}")
    run_settings.on_run_end(run_info=run_info)
    return run_info
