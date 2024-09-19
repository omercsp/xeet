import logging
from typing import Any
from xeet.common import json_value, XeetVars
from functools import cache

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
    def __init__(self, defs_dict: dict, root_dir: str, xvars: XeetVars) -> None:
        self.root_dir = root_dir
        self.output_dir = f"{root_dir}/xeet.out"
        self.expected_output_dir = f"{root_dir}/xeet.expected"
        self.defs_dict = defs_dict
        self.xvars = xvars
        self.xvars.set_vars({
            glbl_var_name("OUT_DIR"): self.output_dir,
            glbl_var_name("EXPECTED_DIR"): self.expected_output_dir,
        })
        self.debug_mode: bool = False

    @cache
    def config_ref(self, path: str) -> tuple[Any, bool]:
        return json_value(self.defs_dict, path)
