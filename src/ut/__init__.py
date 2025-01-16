from xeet.pr import mute_prints, pr_obj, DictPrintType
from xeet.common import XeetVars, _REF_PREFIX
from xeet.core import BaseXeetSettings, TestsCriteria
from xeet.core.api import run_tests, XeetRunSettings
from xeet.core.xeet_conf import _XeetConf, xeet_conf, clear_conf_cache
from xeet.core.test import Test, Phase
from xeet.core.result import (TestResult, PhaseResult, TestStatus, TestPrimaryStatus, RunResult,
                              StepResult)
from tempfile import gettempdir
from typing import Any, Iterable
from collections.abc import Callable
from copy import copy
from functools import cache
from xeet.log import init_logging, log_info
import pytest
import yaml
import json
import os
import tempfile


_log_file = os.path.join(gettempdir(), "xeet_ut.log")
init_logging("xeet", _log_file, False)
mute_prints()


_xeet_dir: tempfile.TemporaryDirectory | None = None


def initialize() -> None:
    global _xeet_dir
    _xeet_dir = tempfile.TemporaryDirectory()


def finalize() -> None:
    if _xeet_dir is None:
        return
    _xeet_dir.cleanup()


@cache
def _xeet_dir_name() -> str:
    if _xeet_dir is None:
        raise RuntimeError("Xeet directory is not initialized. Call init_xeet_dir() first.")
    return _xeet_dir.name


class ConfigTestWrapper:
    def __init__(self, name):
        self.name: str = name.strip()
        self.includes: list[str] = list()
        self.tests: list[dict] = list()
        self.variables: dict[str, Any] = dict()
        self.settings: dict[str, Any] = dict()
        if os.path.isabs(self.name):
            self.file_path = self.name
        else:
            assert _xeet_dir is not None
            self.file_path = os.path.join(_xeet_dir_name(), self.name)
        log_info(self.file_path)

    @property
    def desc(self) -> dict:
        return {
            "include": self.includes,
            "tests": self.tests,
            "variables": self.variables,
            "settings": self.settings,
        }

    def save(self, show: bool = False) -> None:
        file_suffix = os.path.splitext(self.file_path)[1]
        log_info(f"Saving config to '{self.file_path}'")
        with open(self.file_path, 'w') as f:
            if file_suffix == ".yaml" or file_suffix == ".yml":
                f.write(yaml.dump(self.desc))
                if show:
                    pr_obj(self.desc, pr_func=print, print_type=DictPrintType.YAML)
            elif file_suffix == ".json":
                f.write(json.dumps(self.desc))
                if show:
                    pr_obj(self.desc, pr_func=print)
            else:
                raise ValueError(f"Unsupported file format '{file_suffix}'")

    @staticmethod
    def config_set(func):
        def _inner(self, *args, **kwargs):
            if kwargs.pop("reset", False):
                self.reset()
            save = kwargs.pop("save", False)
            show = kwargs.pop("show", False)
            ret = func(self, *args, **kwargs)
            if save:
                self.save()
            if show:
                pr_obj(self.desc, pr_func=print, print_type=DictPrintType.YAML)
            return ret
        return _inner

    @config_set
    def add_test(self, name, **kwargs) -> dict:
        desc = {"name": name, **kwargs}
        self.tests.append(desc)
        return desc

    @config_set
    def add_var(self, name: str, value: Any, **_) -> None:
        self.variables[name] = value

    @config_set
    def add_include(self, name: str, **_) -> None:
        self.includes.append(name)

    @config_set
    def add_setting(self, name: str, value: Any, **_) -> None:
        self.settings[name] = value

    def reset(self):
        self.tests.clear()
        self.variables.clear()
        self.includes.clear()
        self.settings.clear()
        clear_conf_cache()


class XeetUnittest(ConfigTestWrapper):
    def __init__(self, name: str):
        super().__init__(name)

    def gen_xvars(self) -> XeetVars:
        return XeetVars(self.variables)

    def run_tests(self, iteraions: int = 1, **kwargs) -> RunResult:
        criteria = TestsCriteria(**kwargs)
        run_sttings = XeetRunSettings(file_path=self.file_path, criteria=criteria,
                                      iterations=iteraions)
        return run_tests(run_sttings)

    def run_test(self, name: str, **kwargs) -> TestResult:
        run_result = self.run_tests(names={name}, **kwargs)
        return run_result.test_result(name, 0)

    def run_tests_list(self, names: Iterable[str], **kwargs) -> list[TestResult]:
        run_info = self.run_tests(names=set(names), **kwargs)
        return [run_info.test_result(name, 0) for name in names]

    def get_test(self, name) -> Test:
        tests = self.conf().get_tests(TestsCriteria(names={name}))
        assert len(tests) == 1
        return tests[0]

    def gen_test_res(self, test_name: str, **kwargs) -> TestResult:
        test = self.get_test(test_name)
        return gen_test_result(test, **kwargs)

    def update_test_res_test(self, test_res: TestResult, test_name: str) -> None:
        test = self.get_test(test_name)
        test_res.test = test
        _update_phase_result(test_res.pre_run_res, test_res.pre_run_res.steps_results,
                             test.pre_phase)
        _update_phase_result(test_res.main_res, test_res.main_res.steps_results, test.
                             main_phase)
        _update_phase_result(test_res.post_run_res, test_res.post_run_res.steps_results,
                             test.post_phase)

    def conf(self) -> _XeetConf:
        return xeet_conf(BaseXeetSettings(file_path=self.file_path))

    def run_compare_test(self, test_name: str, expected: TestResult) -> None:
        self.update_test_res_test(expected, test_name)
        assert_test_results_equal(self.run_test(test_name), expected)


def test_output_file(self, name: str) -> str:
    return os.path.join(self.path, name)


def project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def ref_str(var_name: str) -> str:
    return f"{_REF_PREFIX}{var_name}"


_RES_COMP_FN = Callable[[Any, Any], None]

_res_comparisons: dict[type[StepResult], _RES_COMP_FN] = {}  # type: ignore


def register_res_comparison(res_type: type[StepResult], comparison_func: _RES_COMP_FN) -> None:
    _res_comparisons[res_type] = comparison_func


def assert_step_results_equal(res: StepResult, expected: StepResult) -> None:
    assert isinstance(res, StepResult)
    assert isinstance(expected, StepResult)
    assert res.completed == expected.completed
    assert res.failed == expected.failed
    assert id(res.step) == id(expected.step)

    comp_func = _res_comparisons.get(type(expected))
    if comp_func:
        comp_func(res, expected)
    else:
        raise ValueError(f"No comparison function for type '{type(expected)}'")


def assert_phase_results_equal(res: PhaseResult | None, expected: PhaseResult | None) -> None:
    if expected is None:
        assert res is None
        return

    assert isinstance(res, PhaseResult)
    assert isinstance(expected, PhaseResult)
    assert id(res.phase), id(expected.phase)
    assert res.completed == expected.completed
    assert res.failed == expected.failed
    assert len(res.steps_results) == len(expected.steps_results)
    for r0, r1 in zip(res.steps_results, expected.steps_results):
        assert_step_results_equal(r0, r1)


def assert_test_results_equal(res: TestResult, expected: TestResult) -> None:
    assert res.status.primary == expected.status.primary
    assert res.status.secondary == expected.status.secondary
    assert id(res.test) == id(expected.test)

    assert_phase_results_equal(res.pre_run_res, expected.pre_run_res)
    assert_phase_results_equal(res.main_res, expected.main_res)
    assert_phase_results_equal(res.post_run_res, expected.post_run_res)


TEST0 = "test0"
TEST1 = "test1"
TEST2 = "test2"
TEST3 = "test3"
TEST4 = "test4"
TEST5 = "test5"
TEST6 = "test6"
GROUP0 = "group0"
GROUP1 = "group1"
GROUP2 = "group2"

PASSED_TEST_STTS = TestStatus(TestPrimaryStatus.Passed)
FAILED_TEST_STTS = TestStatus(TestPrimaryStatus.Failed)


def _update_phase_result(phase_res: PhaseResult, steps_results: list[StepResult],
                         phase: Phase | None) -> None:
    phase_res.steps_results = steps_results
    if phase is None:
        return
    phase_res.phase = phase
    for i, step_res in enumerate(steps_results):
        step_res.phase_res = phase_res
        step_res.step = phase.steps[i]


#  result lsts are copied to avoid the same object being used in mulitple phases, as each step
#  result is assigned to a step during the run.
def dup_step_res_list(res_list: list[StepResult]) -> list[StepResult]:
    return [copy(res) for res in res_list]


def gen_test_result(test: Test | None = None,
                    pre_results: list[StepResult] = list(),
                    main_results: list[StepResult] = list(),
                    post_results: list[StepResult] = list(),
                    **kwargs) -> TestResult:
    ret = TestResult(test=test, **kwargs)  # type: ignore
    _update_phase_result(ret.pre_run_res, pre_results, test.pre_phase if test else None)
    _update_phase_result(ret.main_res, main_results, test.main_phase if test else None)
    _update_phase_result(ret.post_run_res, post_results, test.post_phase if test else None)
    return ret


__all__ = ["pytest", "XeetUnittest", "ConfigTestWrapper", "project_root", "ref_str",
           "assert_step_results_equal", "assert_phase_results_equal", "assert_test_results_equal",
           "TEST0", "TEST1", "TEST2", "TEST3", "TEST4", "TEST5", "TEST6", "GROUP0", "GROUP1",
           "GROUP2", "PASSED_TEST_STTS", "FAILED_TEST_STTS", "gen_test_result", "dup_step_res_list"]
