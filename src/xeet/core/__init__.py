from .run_reporter import RunReporter
from xeet.common import in_windows, platform_path, json_value, cache, XeetVars
from typing import Any
import os


_GLBL_VARS_PREFIX = "XG_"


def glbl_var_name(name: str) -> str:
    return f"{_GLBL_VARS_PREFIX}{name}"


class XeetDefs:
    def __init__(self, xeet_file_path: str, debug_mode: bool, reporter: RunReporter) -> None:
        self.xeet_file_path = os.path.abspath(xeet_file_path)
        self.cwd = os.path.abspath(os.getcwd())
        self.root_dir = os.path.dirname(self.xeet_file_path)
        if self.root_dir == "":
            self.root_dir = self.cwd
        else:
            self.root_dir = os.path.abspath(self.root_dir)
        self.output_dir = f"{self.root_dir}/xeet.out"
        self.expected_output_dir = f"{self.root_dir}/xeet.expected"
        if in_windows():
            self.cwd = platform_path(self.cwd)
            self.root_dir = platform_path(self.root_dir)
            self.output_dir = platform_path(self.output_dir)
            self.expected_output_dir = platform_path(self.expected_output_dir)
        self.xvars = XeetVars(start_vars={
            glbl_var_name("CWD"): self.cwd,
            glbl_var_name("ROOT"): self.root_dir,
            glbl_var_name("OUT_DIR"): self.output_dir,
            glbl_var_name("EXPECTED_DIR"): self.expected_output_dir,
            glbl_var_name("DEBUG"): "1" if debug_mode else "0"
        })
        self.defs_dict = {}
        self.debug_mode = debug_mode
        self.reporter = reporter

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
