from xeet.log import init_logging, log_info
from xeet.pr import mute_prints, pr_obj, DictPrintType
from xeet.common import XeetVars
from xeet.core import TestsCriteria
from xeet.core.api import run_tests
from xeet.core.driver import _Driver, xeet_init
from xeet.core.test import Test
from xeet.core.step import StepResult
from xeet.core.result import TestResult, StepsListResult, TestStatus, TestPrimaryStatus, RunResult
from tempfile import gettempdir
from dataclasses import dataclass, field
from typing import ClassVar, Any, Iterable
from collections.abc import Callable
import yaml
import json
import os
import unittest
import tempfile


_log_file = os.path.join(gettempdir(), "xeet_ut.log")
init_logging("xeet", _log_file, False)
mute_prints()


@dataclass
class ConfigTestWrapper:
    name: str
    includes: list[str] = field(default_factory=list)
    tests: list[dict] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)

    file_path: str = ""
    _xeet_dir: ClassVar[tempfile.TemporaryDirectory] = None  # type: ignore

    def __post_init__(self):
        if not ConfigTestWrapper._xeet_dir:
            raise RuntimeError("xeet dir not initialized. "
                               "Did you forget to call ConfigTestWrapper.init_xeet_dir?")

        if os.path.isabs(self.name):
            self.file_path = self.name
        else:
            self.file_path = os.path.join(ConfigTestWrapper._xeet_dir.name, self.name)
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
                self._reset()
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
    def add_include(self, name: str) -> None:
        self.includes.append(name)

    @config_set
    def add_settings(self, name: str, value: Any, **_) -> None:
        self.settings[name] = value

    def _reset(self):
        self.tests.clear()
        self.variables.clear()
        self.includes.clear()
        self.settings.clear()

    @staticmethod
    def init_xeet_dir():
        ConfigTestWrapper._xeet_dir = tempfile.TemporaryDirectory()

    @staticmethod
    def fini_xeet_dir():
        if ConfigTestWrapper._xeet_dir:
            ConfigTestWrapper._xeet_dir.cleanup()
            ConfigTestWrapper._xeet_dir = None  # type: ignore


def test_output_file(self, name: str) -> str:
    return os.path.join(self.path, name)


def project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def ref_str(var_name: str) -> str:
    return f"{XeetVars._REF_PREFIX}{var_name}"


_RES_COMPARISON_TYPE = Callable[[unittest.TestCase, Any, Any], None]


class XeetUnittest(unittest.TestCase):

    _res_comparisons: dict[type[StepResult], _RES_COMPARISON_TYPE] = {}

    @classmethod
    def register_res_comparison(cls, res_type: type[StepResult],
                                comparison_func: _RES_COMPARISON_TYPE) -> None:
        cls._res_comparisons[res_type] = comparison_func

    @classmethod
    def setUpClass(cls):
        ConfigTestWrapper.init_xeet_dir()
        cls.main_config_wrapper = ConfigTestWrapper("main.json")

    @classmethod
    def tearDownClass(cls):
        ConfigTestWrapper.fini_xeet_dir()

    @classmethod
    def add_var(cls, name: str, value: Any, **kwargs) -> None:
        cls.main_config_wrapper.add_var(name, value, **kwargs)

    def gen_xvars(self) -> XeetVars:
        return XeetVars(self.main_config_wrapper.variables)

    @classmethod
    def add_test(cls, name: str, **kwargs) -> None:
        cls.main_config_wrapper.add_test(name, **kwargs)

    @classmethod
    def add_include(cls, name: str, **kwargs) -> None:
        cls.main_config_wrapper.add_include(name, **kwargs)

    @classmethod
    def add_setting(cls, name: str, value: Any, **kwargs) -> None:
        cls.main_config_wrapper.add_settings(name, value, **kwargs)

    @classmethod
    def run_tests(cls, iteraions: int = 1, **kwargs) -> RunResult:
        criteria = TestsCriteria(**kwargs)
        return run_tests(cls.main_config_wrapper.file_path, criteria, list(),
                         iterations=iteraions)

    @classmethod
    def run_test(cls, name: str, **kwargs) -> TestResult:
        run_result = cls.run_tests(**kwargs)
        return run_result.test_result(name, 0)

    @classmethod
    def run_tests_list(cls, names: Iterable[str], **kwargs) -> list[TestResult]:
        run_info = cls.run_tests(names=set(names), **kwargs)
        return [run_info.test_result(name, 0) for name in names]

    @classmethod
    def get_test(cls, name) -> Test:
        return cls.driver().get_test(name)  # type: ignore

    @classmethod
    def driver(cls) -> _Driver:
        return xeet_init(cls.main_config_wrapper.file_path)

    def assertStepResultEqual(self, res: StepResult, expected: StepResult) -> None:
        self.assertEqual(res.failed, expected.failed)
        self.assertEqual(res.completed, expected.completed)
        comp_func = self._res_comparisons.get(type(expected))
        if comp_func:
            comp_func(self, res, expected)
        else:
            self.fail(f"No comparison function for type '{type(expected)}'")

    def assertStepResultListEqual(self, res: StepsListResult | None,
                                  expected: StepsListResult | None) -> None:
        if expected is None:
            self.assertIsNone(res)
            return

        self.assertIsNotNone(res)
        assert res is not None  # For the type checker
        self.assertEqual(res.completed, expected.completed)
        self.assertEqual(res.failed, expected.failed)
        self.assertEqual(len(res.results), len(expected.results))
        for r0, r1 in zip(res.results, expected.results):
            self.assertStepResultEqual(r0, r1)  # type: ignore

    def assertTestResultEqual(self, res: TestResult, expected: TestResult) -> None:
        self.assertEqual(res.status.primary, expected.status.primary)
        self.assertEqual(res.status.secondary, expected.status.secondary)
        self.assertStepResultListEqual(res.pre_run_res, expected.pre_run_res)
        self.assertStepResultListEqual(res.run_res, expected.run_res)
        self.assertStepResultListEqual(res.post_run_res, expected.post_run_res)


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

__all__ = ["unittest", "XeetUnittest", "ConfigTestWrapper", "project_root", "ref_str",
           "TEST0", "TEST1", "TEST2", "TEST3", "TEST4", "TEST5", "TEST6", "GROUP0", "GROUP1",
           "GROUP2", "PASSED_TEST_STTS", "FAILED_TEST_STTS"]
