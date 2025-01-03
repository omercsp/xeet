from .events import EventNotifier, EventReporter
from xeet.common import in_windows, platform_path, json_value, cache, XeetVars
from dataclasses import dataclass
from typing import Any
import os


_SYS_VAR_PREFIX = "XEET_"


def system_var_name(name: str) -> str:
    return f"{_SYS_VAR_PREFIX}{name}"


def is_system_var_name(name: str) -> bool:
    return name.startswith(_SYS_VAR_PREFIX)


@dataclass
class BaseXeetSettings:
    file_path: str = ""
    debug: bool = False
    output_dir: str = ""

    def __hash__(self) -> int:
        return hash((self.file_path, self.debug, self.output_dir))


class RuntimeInfo:
    def __init__(self, settings: BaseXeetSettings) -> None:
        self.xeet_file_path = os.path.abspath(settings.file_path)
        self.cwd = os.path.abspath(os.getcwd())
        self.root_dir = os.path.dirname(self.xeet_file_path)
        if self.root_dir == "":
            self.root_dir = self.cwd
        else:
            self.root_dir = os.path.abspath(self.root_dir)

        if not settings.output_dir:
            self.base_output_dir = f"{self.root_dir}/xeet.out"
        else:
            self.base_output_dir = os.path.abspath(settings.output_dir)
        if in_windows():
            self.cwd = platform_path(self.cwd)
            self.root_dir = platform_path(self.root_dir)
            self.output_dir = platform_path(self.output_dir)
        self.output_dir = f"{self.base_output_dir}[/iteration#]"
        self.expected_output_dir = f"{self.root_dir}/xeet.expected"

        self.xvars = XeetVars(start_vars={
            system_var_name("CWD"): self.cwd,
            system_var_name("ROOT"): self.root_dir,
            system_var_name("EXPECTED_DIR"): self.expected_output_dir,
            system_var_name("OUT_DIR"): self.output_dir,
            system_var_name("DEBUG"): "1" if settings.debug else "0",
            system_var_name("PLATFORM"): os.name.lower(),
        })
        self.defs_dict = {}
        self.debug_mode = settings.debug
        self.notifier = EventNotifier()
        self.iterations = 0
        self.iteration = 0

    def add_run_reporter(self, reporter: EventReporter) -> None:
        reporter.rti = self
        self.notifier.add_reporter(reporter)

    def set_defs(self, defs_dict: dict) -> None:
        self.defs_dict = defs_dict

    def set_iteration(self, iteration: int) -> None:
        self.iteration = iteration
        if self.iterations > 1:
            self.output_dir = f"{self.base_output_dir}/{iteration}"
        elif iteration == 0:
            self.output_dir = self.base_output_dir
        self.xvars.set_vars({
            system_var_name("OUT_DIR"): self.output_dir,
        })

    @cache
    def config_ref(self, path: str) -> tuple[Any, bool]:
        return json_value(self.defs_dict, path)
