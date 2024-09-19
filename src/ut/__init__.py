from xeet.log import init_logging
from xeet.pr import mute_prints
from tempfile import gettempdir
from dataclasses import dataclass, field
from typing import ClassVar
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
    _xeet_dir: ClassVar[tempfile.TemporaryDirectory] = None  # type: ignore

    def __post_init__(self):
        if not ConfigTestWrapper._xeet_dir:
            raise RuntimeError("xeet dir not initialized. "
                               "Did you forget to call ConfigTestWrapper.init_xeet_dir?")
        self.path = os.path.join(ConfigTestWrapper._xeet_dir.name, self.path)

    @property
    def desc(self) -> dict:
        return {"include": self.includes, "tests": self.tests}

    @cached_property
    def file_path(self):
        return os.path.join(self.path, self.name)

    def save(self):
        with open(self.file_path, 'w') as f:
            f.write(json.dumps(self.desc))

    def add_test(self, name: str, **kwargs) -> dict:
        desc = {"name": name, **kwargs}
        self.tests.append(desc)
        return desc

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


def utils_path() -> str:
    return os.path.join(project_root(), "utils")


def tests_utils_command(name: str, *args) -> str:
    path = os.path.join(utils_path(), "testing", name)
    args = " ".join(args)
    return f"python3 {path} {args}"


__all__ = ["unittest"]
