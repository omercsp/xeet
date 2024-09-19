from xeet.log import init_logging
from xeet.pr import mute_prints, pr_dict
from xeet.common import XeetVars
from xeet.core import RunSettings, run_tests
from xeet.config import Config, TestCriteria, read_config_file
from xeet.xtest import TestResult, Xtest
from xeet.xstep import XStepResult, XStepListResult
from tempfile import gettempdir
from dataclasses import dataclass, field
from typing import ClassVar, Any, Iterable
from functools import cached_property
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
    path: str = ""
    includes: list[str] = field(default_factory=list)
    tests: list[dict] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    _xeet_dir: ClassVar[tempfile.TemporaryDirectory] = None  # type: ignore

    def __post_init__(self):
        if not ConfigTestWrapper._xeet_dir:
            raise RuntimeError("xeet dir not initialized. "
                               "Did you forget to call ConfigTestWrapper.init_xeet_dir?")
        self.path = os.path.join(ConfigTestWrapper._xeet_dir.name, self.path)

    @property
    def desc(self) -> dict:
        return {
            "include": self.includes,
            "tests": self.tests,
            "variables": self.variables,
            "settings": self.settings
        }

    @cached_property
    def file_path(self):
        return os.path.join(self.path, self.name)

    def save(self):
        with open(self.file_path, 'w') as f:
            f.write(json.dumps(self.desc))

    @staticmethod
    def config_set(func):
        def _inner(self, *args, **kwargs):
            if kwargs.pop("reset", False):
                self._reset()
            save = kwargs.pop("save", False)
            show = kwargs.pop("show", False)
            func(self, *args, **kwargs)
            if save:
                self.save()
            if show:
                pr_dict(self.desc, pr_func=print, as_json=True)
        return _inner

    @config_set
    def add_test(self, name, **kwargs) -> None:
        desc = {"name": name, **kwargs}
        self.tests.append(desc)

    @config_set
    def add_var(self, name: str, value: str) -> None:
        self.variables[name] = value

    @config_set
    def add_include(self, name: str) -> None:
        self.includes.append(name)

    @config_set
    def add_settings(self, name: str, value: Any) -> None:
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


def test_output_file(self, name: str) -> str:
    return os.path.join(self.path, name)


def project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def tests_utils_command(name: str, *args) -> str:
    path = os.path.join(project_root(), "scripts", "testing", name)
    ret = f"python3 {path}"
    if not args:
        return ret
    args = " ".join(args)
    return f"{ret} {args}"


def ref_str(var_name: str) -> str:
    return f"{XeetVars._REF_PREFIX}{var_name}"


class XeetUnittest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ConfigTestWrapper.init_xeet_dir()
        cls.main_config_wrapper = ConfigTestWrapper("main.json")
        cls.run_settings = RunSettings(1, False, TestCriteria([], [], [], [], False))
        cls.criteria = TestCriteria([], [], [], [], False)

    @classmethod
    def tearDownClass(cls):
        ConfigTestWrapper.fini_xeet_dir()

    @classmethod
    def add_test(cls, name, **kwargs) -> None:
        cls.main_config_wrapper.add_test(name, **kwargs)

    @classmethod
    def add_include(cls, name, **kwargs) -> None:
        cls.main_config_wrapper.add_include(name, **kwargs)

    @classmethod
    def add_setting(cls, name, value, **kwargs) -> None:
        cls.main_config_wrapper.add_settings(name, value, **kwargs)

    @classmethod
    def run_test(cls, name) -> TestResult:
        cls.run_settings.criteria.names = {name}
        run_info = run_tests(cls.main_config_wrapper.file_path, cls.run_settings)
        res = run_info.test_result(name, 0)
        return res

    @classmethod
    def run_tests_list(cls, names: Iterable[str]) -> Iterable[TestResult]:
        cls.run_settings.criteria.names = set(names)
        run_info = run_tests(cls.main_config_wrapper.file_path, cls.run_settings)
        for name in names:
            yield run_info.test_result(name, 0)

    @classmethod
    def get_test(cls, name) -> Xtest:
        return cls.config_file().xtest(name)  # type: ignore

    @classmethod
    def config_file(cls) -> Config:
        return read_config_file(cls.main_config_wrapper.file_path)

    def assertStepResultEqual(self, res: XStepResult, expected: XStepResult) -> None:
        self.assertEqual(res.failed, expected.failed)
        self.assertEqual(res.completed, expected.completed)

    def assertStepResultListEqual(self, res: XStepListResult | None,
                                  expected: XStepListResult | None) -> None:
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
        self.assertEqual(res.status, expected.status)
        self.assertStepResultListEqual(res.pre_run_res, expected.pre_run_res)
        self.assertStepResultListEqual(res.run_res, expected.run_res)
        self.assertStepResultListEqual(res.post_run_res, expected.post_run_res)


__all__ = ["unittest"]
