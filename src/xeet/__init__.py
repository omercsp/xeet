from xeet.common import json_value, XeetVars, in_windows
import logging
from typing import Any
from functools import cache
from pathlib import PureWindowsPath
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

        if in_windows():
            self.cwd = PureWindowsPath(self.cwd).as_posix()
            self.root_dir = PureWindowsPath(self.root_dir).as_posix()
            self.output_dir = PureWindowsPath(self.output_dir).as_posix()
            self.expected_output_dir = PureWindowsPath(self.expected_output_dir).as_posix()

        self.xvars = XeetVars(start_vars={
            glbl_var_name("CWD"): self.cwd,
            glbl_var_name("ROOT"): self.root_dir,
            glbl_var_name("OUT_DIR"): self.output_dir,
            glbl_var_name("EXPECTED_DIR"): self.expected_output_dir
        })
        self.defs_dict = {}
        self.debug_mode = False
        self.reporter: RunReporter = None  # type: ignore

    def set_debug_mode(self, debug_mode: bool) -> None:
        self.debug_mode = debug_mode
        self.xvars.set_vars({glbl_var_name("DEBUG"): "1" if debug_mode else "0"})

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


class RunReporter:
    def __init__(self, iterations: int) -> None:
        super().__init__()
        self.run_info: Any = None
        self.iter_info: Any = None
        self.iteration: int = 0
        self.iterations: int = iterations
        self.xtest: Any = None
        self.xtest_result: Any = None
        self.xstep: Any = None
        self.xstep_index: int = 0
        self.steps_count: int = 0
        self.xstep_result: Any = None
        self.phase_name: str = ""

    def on_run_start(self, run_info) -> None:
        self.run_info = run_info
        self.client_on_run_start()

    def client_on_run_start(self) -> None:
        pass

    def on_run_end(self) -> None:
        self.client_on_run_end()

    def client_on_run_end(self) -> None:
        pass

    def on_iteration_start(self, iter_info, iter_index) -> None:
        self.iter_info = iter_info
        self.iteration = iter_index
        self.client_on_iteration_start()

    def client_on_iteration_start(self) -> None:
        pass

    def on_iteration_end(self) -> None:
        self.client_on_iteration_end()
        self.iter_info = None
        self.iteration = -1

    def client_on_iteration_end(self) -> None:
        pass

    def on_test_enter(self, test) -> None:
        self.xtest = test
        self.client_on_test_enter()

    def on_test_setup_start(self, test) -> None:
        self.xtest = test
        self.client_on_test_setup_start()

    def client_on_test_setup_start(self) -> None:
        pass

    def on_test_setup_end(self) -> None:
        self.client_on_test_setup_end()

    def client_on_test_setup_end(self) -> None:
        pass

    def on_step_setup_start(self, step, step_index: int) -> None:
        self.xstep = step
        self.xstep_index = step_index
        self.client_on_step_setup_start()

    def client_on_step_setup_start(self) -> None:
        pass

    def on_step_setup_end(self) -> None:
        self.client_on_step_setup_end()
        self.xstep = None
        self.xstep_index = -1

    def client_on_step_setup_end(self) -> None:
        pass

    def client_on_test_enter(self) -> None:
        pass

    def on_test_end(self, res) -> None:
        self.xtest_result = res
        self.client_on_test_end()
        self.xtest = None
        self.xtest_result = None

    def client_on_test_end(self) -> None:
        pass

    def on_phase_start(self, phase_name: str, steps_count: int) -> None:
        self.phase_name = phase_name
        self.steps_count = steps_count
        self.client_on_phase_start()

    def client_on_phase_start(self) -> None:
        pass

    def on_phase_end(self) -> None:
        self.client_on_phase_end()
        self.phase_name = ""
        self.steps_count = 0

    def client_on_phase_end(self) -> None:
        pass

    def on_step_start(self, step, step_index: int) -> None:
        self.xstep = step
        self.xstep_index = step_index
        self.client_on_step_start()

    def client_on_step_start(self) -> None:
        pass

    def on_step_end(self, res) -> None:
        self.xstep_result = res
        self.client_on_step_end()
        self.xstep = None
        self.xstep_index = -1
        self.xstep_result = None

    def client_on_step_end(self) -> None:
        pass
