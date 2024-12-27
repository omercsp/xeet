import logging
from typing import Any
from xeet.common import json_value, XeetVars

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


class XeetDefs:
    def __init__(self, defs_dict: dict, output_dir, xvars: XeetVars) -> None:
        self.output_dir = output_dir
        self.defs_dict = defs_dict
        self.xvars = xvars
        self.debug_mode: bool = False

    def config_ref(self, path: str) -> tuple[Any, bool]:
        return json_value(self.defs_dict, path)
