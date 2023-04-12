from .run_reporter import RunNotifier
from xeet.common import in_windows, platform_path, json_value, cache, XeetVars
from dataclasses import dataclass, field
from typing import Any
import os


_SYS_VAR_PREFIX = "XEET_"


def system_var_name(name: str) -> str:
    return f"{_SYS_VAR_PREFIX}{name}"


def is_system_var_name(name: str) -> bool:
    return name.startswith(_SYS_VAR_PREFIX)


class RuntimeInfo:
    def __init__(self, xeet_file_path: str, debug_mode: bool, notifier: RunNotifier) -> None:
        self.xeet_file_path = os.path.abspath(xeet_file_path)
        self.cwd = os.path.abspath(os.getcwd())
        self.root_dir = os.path.dirname(self.xeet_file_path)
        if self.root_dir == "":
            self.root_dir = self.cwd
        else:
            self.root_dir = os.path.abspath(self.root_dir)

        #  Output dir is set here for informational purposes. It will be updated later the test
        #  is ran, possibly with an iteration number appended to it.
        self.output_dir = f"{self.root_dir}/xeet.out"
        if in_windows():
            self.cwd = platform_path(self.cwd)
            self.root_dir = platform_path(self.root_dir)
            self.output_dir = platform_path(self.output_dir)
        self.output_dir += f"/iteration#"
        self.expected_output_dir = f"{self.root_dir}/xeet.expected"

        self.xvars = XeetVars(start_vars={
            system_var_name("CWD"): self.cwd,
            system_var_name("ROOT"): self.root_dir,
            system_var_name("EXPECTED_DIR"): self.expected_output_dir,
            system_var_name("OUT_DIR"): self.output_dir,
            system_var_name("DEBUG"): "1" if debug_mode else "0"
        })
        self.defs_dict = {}
        self.debug_mode = debug_mode
        self.notifier = notifier
        self.current_iteration = 0

    def set_defs(self, defs_dict: dict) -> None:
        self.defs_dict = defs_dict

    def set_iteration(self, iteration: int, total_iterations: int) -> None:
        self.current_iteration = iteration
        if total_iterations > 1:
            self.output_dir = f"{self.root_dir}/xeet.out/{iteration}"
        else:
            self.output_dir = f"{self.root_dir}/xeet.out"
        self.xvars.set_vars({
            system_var_name("OUT_DIR"): self.output_dir,
        })

    @cache
    def config_ref(self, path: str) -> tuple[Any, bool]:
        return json_value(self.defs_dict, path)


@dataclass
class TestsCriteria:
    names: set[str] = field(default_factory=set)
    exclude_names: set[str] = field(default_factory=set)
    fuzzy_names: list[str] = field(default_factory=list)
    fuzzy_exclude_names: set[str] = field(default_factory=set)
    include_groups: set[str] = field(default_factory=set)
    require_groups: set[str] = field(default_factory=set)
    exclude_groups: set[str] = field(default_factory=set)
    hidden_tests: bool = False

    def match(self, name: str, groups: list[str], hidden: bool) -> bool:
        if hidden and not self.hidden_tests:
            return False
        included = not self.names and not self.fuzzy_names and not self.include_groups
        if not included and name:
            if self.names and name in self.names:
                included = True
            elif self.fuzzy_names and any(fuzzy in name for fuzzy in self.fuzzy_names):
                included = True

        if not included and self.include_groups and self.include_groups.intersection(groups):
            included = True

        if not included:
            return False

        if self.exclude_names and name in self.exclude_names:
            return False

        if self.fuzzy_exclude_names and any(fuzzy in name for fuzzy in self.fuzzy_exclude_names):
            return False

        if self.require_groups and not self.require_groups.issubset(groups):
            return False

        if self.exclude_groups and self.exclude_groups.intersection(groups):
            return False
        return True

    def __str__(self) -> str:
        lines = []
        if self.names:
            lines.append(f"Explicity included tests - " + ", ".join(sorted(self.names)))
        if self.include_groups:
            lines.append(f"Included groups - " + ", ".join(sorted(self.include_groups)))
        if self.fuzzy_names:
            lines.append(f"Fuzzy included tests - " + ", ".join(sorted(self.fuzzy_names)))
        if self.exclude_names:
            lines.append(f"Explicity excluded tests - " + ", ".join(sorted(self.exclude_names)))
        if self.fuzzy_exclude_names:
            lines.append(f"Fuzzy excluded tests - " + ", ".join(sorted(self.fuzzy_exclude_names)))
        if self.exclude_groups:
            lines.append(f"Excluded groups - " + ", ".join(sorted(self.exclude_groups)))
        if self.require_groups:
            lines.append(f"Required groups - " + ", ".join(sorted(self.require_groups)))
        if not lines:
            ret = "Test criteria: All tests"
            if self.hidden_tests:
                ret += " (hidden included)"
            return ret
        lines.insert(0, "Test criteria:")
        if self.hidden_tests:
            lines.append("Hidden tests are included")
        return "\n" + "\n".join(lines)
