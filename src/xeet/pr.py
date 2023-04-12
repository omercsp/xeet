from xeet import LogLevel
from typing import Callable, Any
from rich.console import Console
import pprint
import json
import sys
import yaml


_stdout = Console(highlight=False, soft_wrap=True)
_stderr = Console(highlight=False, soft_wrap=True, stderr=True)


def stdout() -> Console:
    return _stdout


_allowed_print_level = LogLevel.INFO


def set_print_level(level: int) -> None:
    global _allowed_print_level
    if level < LogLevel.NOTSET or level > LogLevel.CRITICAL:
        print(f"Unsupported log level '{level}'")
        return
    _allowed_print_level = level


_colors_enabled = True


# See https://rich.readthedocs.io/en/stable/appendix/colors.html for color names
class XColors:
    NoColor = ''
    Green = 'green'
    Yellow = 'yellow'
    Rre = 'red'
    Bold = 'bold'


def colorize_str(text: str, color: str) -> str:
    if not colors_enabled() or color == XColors.NoColor:
        return text
    return f"[{color}]{text}[/{color}]"


_muted = False


# Disable all print functions. Useful for testing
def mute_prints():
    global _muted
    _muted = True


def disable_colors():
    global _colors_enabled
    _colors_enabled = False


def colors_enabled() -> bool:
    return _colors_enabled


def create_print_func(dflt_color: str, level: int, dflt_console: Console = _stdout) -> Callable:
    def print_func(*args, **kwargs) -> None:
        if level < _allowed_print_level or _muted:
            return

        if not kwargs.pop("pr_cond", True):
            return
        console: Console = kwargs.pop("pr_file", dflt_console)
        if _colors_enabled:
            color = kwargs.pop("pr_color", dflt_color)
        else:
            color = XColors.NoColor

        console.print(*args, **kwargs, style=color)
    return print_func


pr_info = create_print_func(XColors.NoColor, LogLevel.INFO, _stdout)
pr_warn = create_print_func(XColors.Yellow, LogLevel.WARN, _stderr)
pr_error = create_print_func(XColors.Rre, LogLevel.ERROR, _stderr)
pr_ok = create_print_func(XColors.Green, LogLevel.INFO, _stdout)
pr_header = create_print_func(XColors.Bold, LogLevel.INFO, _stdout)


def clear_printed_line():
    sys.stdout.write("\033[F")


class DictPrintType:
    PYTHON = 1
    JSON = 2
    YAML = 3


def pr_obj(obj: Any, **kwargs) -> None:
    pr_func = kwargs.pop("pr_func", pr_info)
    print_type = kwargs.pop("print_type", DictPrintType.PYTHON)
    indent = kwargs.pop("indent", 4)
    sort_keys = kwargs.pop("sort_keys", False)
    if isinstance(obj, (list, dict)):
        if print_type == DictPrintType.PYTHON:
            s = pprint.pformat(obj, indent=indent)
        if print_type == DictPrintType.JSON:
            s = json.dumps(obj, indent=4)
        else:
            s = yaml.dump(obj, indent=indent, sort_keys=sort_keys)
    else:
        s = str(obj)

    pr_func(s, **kwargs)


__all__ = ["pr_info", "pr_warn", "pr_error", "pr_ok", "pr_header", "pr_obj", "clear_printed_line",
           "set_print_level", "mute_prints", "disable_colors", "colors_enabled",
           "create_print_func", "DictPrintType", "colorize_str", "LogLevel", "XColors", "stdout"]
