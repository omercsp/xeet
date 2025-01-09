from .events import EventNotifier, EventReporter
from xeet.common import in_windows, platform_path, json_value, cache, XeetVars, XeetVarsModel
from dataclasses import dataclass, field
from typing import Any
from functools import cached_property
import os


_SYS_VAR_PREFIX = "XEET_"


def system_var_name(name: str) -> str:
    return f"{_SYS_VAR_PREFIX}{name}"


def is_system_var_name(name: str) -> bool:
    return name.startswith(_SYS_VAR_PREFIX)


@dataclass
class TestsCriteria:
    names: list[str] = field(default_factory=list)
    exclude_names: set[str] = field(default_factory=set)
    fuzzy_names: list[str] = field(default_factory=list)
    fuzzy_exclude_names: set[str] = field(default_factory=set)
    include_groups: list[str] = field(default_factory=list)
    require_groups: set[str] = field(default_factory=set)
    exclude_groups: set[str] = field(default_factory=set)
    abstract_tests: bool = False
    __test__ = False

    @cached_property
    def empty(self) -> bool:
        return (not self.names and not self.exclude_names and
                not self.fuzzy_names and not self.fuzzy_exclude_names and
                not self.include_groups and not self.require_groups and
                not self.exclude_groups and not self.abstract_tests)


@dataclass
class XeetSettings:
    file_path: str = ""
    reporters: list[EventReporter] = field(default_factory=list)

    def __hash__(self) -> int:
        return hash((self.file_path))


@dataclass
class XeetRunSettings:
    criteria: "TestsCriteria" = field(default_factory=TestsCriteria)
    iterations: int = 1
    debug: bool = False
    output_dir: str = ""
    jobs: int = 1


_UNINITIALIZED = "#UNINITIALIZED#"
_ITERATION_ADDENDUM = "[/iteration#]"


class RuntimeInfo:
    def __init__(self) -> None:
        self.cwd = os.path.abspath(os.getcwd())
        self.xeet_file_path = _UNINITIALIZED
        self.root_dir = _UNINITIALIZED
        self.base_output_dir = _UNINITIALIZED
        self.output_dir = f"<OUTPUT_DIR>{_ITERATION_ADDENDUM}"
        self.expected_output_dir = _UNINITIALIZED

        self.xvars = XeetVars(start_vars=XeetVarsModel({
            system_var_name("CWD"): self.cwd,
            system_var_name("PLATFORM"): os.name.lower(),
        }))
        self.defs_dict = {}
        self.debug_mode = False
        self.notifier = EventNotifier()
        self.iterations = 0
        self.iteration = 0

    # Set the constant configuration data for the runtime info. This is
    # excuted after the configuration file is loaded and parsed.
    def set_config_data(self, xeet_file_path, defs_dict: dict,
                        variables: XeetVarsModel) -> None:
        self.xeet_file_path = os.path.abspath(xeet_file_path)
        self.root_dir = os.path.dirname(self.xeet_file_path)
        self.output_dir = f"{self.root_dir}/xeet.out"
        self.expected_output_dir = f"{self.root_dir}/xeet.expected"
        if in_windows():
            self.root_dir = platform_path(self.root_dir)
            self.output_dir = platform_path(self.output_dir)
            self.expected_output_dir = platform_path(self.expected_output_dir)
        self.output_dir = f"{self.output_dir}{_ITERATION_ADDENDUM}"
        self.defs_dict = defs_dict
        self.xvars.set_vars({
            system_var_name("ROOT"): self.root_dir,
            system_var_name("EXPECTED_DIR"): self.expected_output_dir,
            system_var_name("OUT_DIR"): self.output_dir,
        })
        self.xvars.set_vars(variables)

    def set_run_settings(self, run_settings: XeetRunSettings) -> None:
        self.iterations = run_settings.iterations
        self.debug_mode = run_settings.debug
        if run_settings.output_dir:
            self.base_output_dir = os.path.abspath(run_settings.output_dir)

        if not run_settings.output_dir:
            self.base_output_dir = f"{self.root_dir}/xeet.out"
        else:
            self.base_output_dir = os.path.abspath(run_settings.output_dir)
        if in_windows():
            self.cwd = platform_path(self.cwd)
            self.root_dir = platform_path(self.root_dir)
            self.output_dir = platform_path(self.output_dir)
        self.output_dir = f"{self.base_output_dir}[/iteration#]"
        self.xvars.set_vars(XeetVarsModel({
            system_var_name("OUT_DIR"): self.output_dir,
            system_var_name("ITERATIONS"): str(self.iterations),
            system_var_name("DEBUG"): "1" if self.debug_mode else "0"
        }))

    def add_run_reporter(self, reporter: EventReporter) -> None:
        reporter.rti = self
        self.notifier.add_reporter(reporter)

    def set_iteration(self, iteration: int) -> None:
        self.iteration = iteration
        if self.iterations > 1:
            self.output_dir = f"{self.base_output_dir}/{iteration}"
        elif iteration == 0:
            self.output_dir = self.base_output_dir
        self.xvars.set_vars(XeetVarsModel({
            system_var_name("OUT_DIR"): self.output_dir,
        }))

    @cache
    def config_ref(self, path: str) -> tuple[Any, bool]:
        return json_value(self.defs_dict, path)
