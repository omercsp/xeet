import logging
from typing import Any
from xeet.common import json_value, XeetVars
from functools import cache
from dataclasses import dataclass
import os

try:
    from ._version import version
    xeet_version = version
except ImportError:
    xeet_version = "0.0.0"


class LogLevel(object):
    NOTSET = logging.NOTSET
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARN = logging.WARN
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL
    ALWAYS = logging.CRITICAL + 1


_GLBL_VARS_PREFIX = "XG_"


def glbl_var_name(name: str) -> str:
    return f"{_GLBL_VARS_PREFIX}{name}"


class XeetDefs:
    def __init__(self, xeet_file_path: str) -> None:
        self.xeet_file_path = os.path.abspath(xeet_file_path)
        self.cwd = os.path.abspath(os.getcwd())
        self.root_dir = os.path.dirname(self.xeet_file_path)
        if self.root_dir == "":
            self.root_dir = self.cwd
        else:
            self.root_dir = os.path.abspath(self.root_dir)
        self.output_dir = f"{self.root_dir}/xeet.out"
        self.expected_output_dir = f"{self.root_dir}/xeet.expected"
        self.xvars = XeetVars(start_vars={
            glbl_var_name("CWD"): self.cwd,
            glbl_var_name("ROOT"): self.root_dir,
            glbl_var_name("OUT_DIR"): self.output_dir,
            glbl_var_name("EXPECTED_DIR"): self.expected_output_dir
        })
        self.defs_dict = {}
        self.run_settings: "RunSettings" = None  # type: ignore

    def set_run_settings(self, run_settings: "RunSettings") -> None:
        self.run_settings = run_settings
        if run_settings.debug_mode:
            self.xvars.set_vars({glbl_var_name("DEBUG"): "1"})

    def set_defs(self, defs_dict: dict) -> None:
        self.defs_dict = defs_dict

    @cache
    def config_ref(self, path: str) -> tuple[Any, bool]:
        return json_value(self.defs_dict, path)


class TestCriteria:
    def __init__(self, names: list[str], include_groups: list[str], require_groups: list[str],
                 exclude_groups: list[str], hidden_tests: bool) -> None:
        self.names = set(names)
        self.hidden_tests = hidden_tests
        self.include_groups = set(include_groups)
        self.require_groups = set(require_groups)
        self.exclude_groups = set(exclude_groups)

    def match(self, name: str, groups: list[str], hidden: bool) -> bool:
        if hidden and not self.hidden_tests:
            return False
        if self.names and name and name not in self.names:
            return False
        if self.include_groups and not self.include_groups.intersection(groups):
            return False
        if self.require_groups and not self.require_groups.issubset(groups):
            return False
        if self.exclude_groups and self.exclude_groups.intersection(groups):
            return False
        return True

    #  def _match_name(self, name: str) -> str:
    #      if name in test_list:
    #          return name
    #      possible_names = [x for x in test_list if x.startswith(name)]
    #      if len(possible_names) == 0:
    #          raise XeetException(f"No tests match '{name}'")
    #      if len(possible_names) > 1:
    #          names_str = ", ".join(possible_names)
    #          raise XeetException(f"Multiple tests match '{name}': {names_str}")
    #      return possible_names[0]


@dataclass
class RunSettings:
    iterations: int
    debug_mode: bool

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

    def on_step_start(self, **_) -> None:
        pass

    def on_step_end(self, **_) -> None:
        pass
