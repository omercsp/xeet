from . import TestsCriteria
from .test import Test, TestModel
from .result import (TestResult, TestPrimaryStatus, TestSecondaryStatus, RunResult, TestStatus,
                     EmptyRunResult)
from .driver import XeetModel, xeet_init
from .events import EventReporter
from xeet import XeetException
from timeit import default_timer as timer
from enum import Enum


def fetch_test(config_path: str, name: str) -> Test | None:
    return xeet_init(config_path).get_test(name)


def fetch_tests_list(config_path: str, criteria: TestsCriteria) -> list[Test]:
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

    start = timer()
    ret = test.run()
    ret.duration = timer() - start
    return ret


def run_tests(conf: str,
              criteria: TestsCriteria,
              reporters: EventReporter | list[EventReporter],
              debug_mode: bool = False,
              iterations: int = 1) -> RunResult:
    driver = xeet_init(conf, debug_mode)
    rti = driver.rti

    if not isinstance(reporters, list):
        reporters = [reporters]
    for reporter in reporters:
        rti.add_run_reporter(reporter)
    notifier = rti.notifier
    notifier.on_init()

    tests = driver.get_tests(criteria)
    if not tests:
        return EmptyRunResult
    run_res = RunResult(iterations=iterations, criteria=criteria)
    notifier.on_run_start(run_res, tests)

    for iter_n in range(iterations):
        iter_res = run_res.iter_results[iter_n]
        rti.set_iteration(iter_n, iterations)
        notifier.on_iteration_start(iter_res)
        for test in tests:
            notifier.on_test_start(test=test)
            test_res = _run_test(test)
            iter_res.add_test_result(test.name, test_res)
            notifier.on_test_end(test=test, test_res=test_res)
        notifier.on_iteration_end()

    notifier.on_run_end()
    return run_res
