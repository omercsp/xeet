from xeet.runtime import RunInfo, IterationInfo
from xeet.xtest import Xtest, XtestModel, TestResult, TestStatus
from xeet.config import ConfigModel, read_config_file, TestCriteria
from xeet.common import XeetException, update_global_vars
from xeet.pr import pr_info
from xeet.log import log_info, log_blank
from enum import Enum
from dataclasses import dataclass


def fetch_xtest(config_path: str, name: str) -> Xtest | None:
    return read_config_file(config_path).xtest(name)


def fetch_tests_list(config_path: str, criteria: TestCriteria) -> list[Xtest]:
    return read_config_file(config_path).xtests(criteria)


def fetch_groups_list(config_path: str) -> list[str]:
    config = read_config_file(config_path)
    return list(config.all_groups())


def fetch_test_desc(config_path: str, name: str) -> dict | None:
    return read_config_file(config_path).test_desc(name)


class SchemaType(str, Enum):
    CONFIG = "config"
    XTEST = "test"
    UNIFIED = "unified"


def fetch_schema(schema_type: str) -> dict:
    if schema_type == SchemaType.CONFIG.value:
        return ConfigModel.model_json_schema()
    if schema_type == SchemaType.XTEST.value:
        return XtestModel.model_json_schema()
    if schema_type == SchemaType.UNIFIED.value:
        d = ConfigModel.model_json_schema()
        d["properties"]["tests"]["items"] = XtestModel.model_json_schema()
        return d
    raise XeetException(f"Invalid dump type: {schema_type}")


@dataclass
class RunSettings:
    iterations: int
    debug_mode: bool
    criteria: TestCriteria
    echo: bool = False

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

    test.expand()
    test.debug_mode = settings.debug_mode
    return test.run()


def run_tests(conf: str, run_settings: RunSettings) -> RunInfo:
    def _log(*args, **kwargs):
        log_info(*args, pr=pr_info, pr_cond=run_settings.echo, **kwargs)

    _log("Starting run", pr_suffix="------------\n")
    config = read_config_file(conf)
    update_global_vars({"DEBUG": "1" if run_settings.debug_mode else "0"})
    criteria = run_settings.criteria
    if criteria.include_groups:
        groups_str = ", ".join(sorted(criteria.include_groups))
        _log(f"Included groups: {groups_str}")
    if criteria.exclude_groups:
        groups_str = ", ".join(sorted(criteria.exclude_groups))
        _log(f"Excluded groups: {groups_str}")
    if criteria.require_groups:
        groups_str = ", ".join(sorted(criteria.require_groups))
        _log(f"Required groups: {groups_str}")

    tests = config.xtests(run_settings.criteria)
    if not tests:
        raise XeetException("No tests to run")

    _log("Running tests: {}\n".format(", ".join([x.name for x in tests])))

    iterations = run_settings.iterations
    run_info = RunInfo(iterations=iterations)

    run_settings.on_run_start(run_info=run_info)
    for iter_n in range(iterations):
        iter_info = run_info.iterations_info[iter_n]
        if iterations > 1:
            _log(f">>> Iteration {iter_n}/{iterations - 1}")
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
    run_settings.on_run_end(run_info=run_info)
    return run_info
