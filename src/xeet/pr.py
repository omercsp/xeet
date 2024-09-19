from xeet import LogLevel
from typing import Union, Callable, TextIO
import pprint
import json
import sys
import yaml


_allowed_print_level = LogLevel.INFO


def set_print_level(level: int) -> None:
    global _allowed_print_level
    if level < LogLevel.NOTSET or level > LogLevel.CRITICAL:
        print(f"Unsupported log level '{level}'")
        return
    _allowed_print_level = level


class PrintColors(object):
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    RESET = ENDC


_colors_enabled = True
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


def create_print_func(dflt_color: str, level: int, out_file: TextIO = sys.stdout) -> Callable:
    def print_func(*args, **kwargs) -> None:
        if level < _allowed_print_level or _muted:
            return

        pr_color = kwargs.pop("_pr_color", dflt_color)
        if _colors_enabled and pr_color != PrintColors.RESET:
            print(pr_color, end="", file=out_file)
        print(*args, **kwargs, file=out_file)
        if _colors_enabled and pr_color != PrintColors.RESET:
            print(PrintColors.ENDC, end="", file=out_file)
    return print_func


pr_info = create_print_func(PrintColors.ENDC, LogLevel.INFO, sys.stdout)
pr_warn = create_print_func(PrintColors.YELLOW, LogLevel.WARN, sys.stderr)
pr_error = create_print_func(PrintColors.RED, LogLevel.ERROR, sys.stderr)
pr_ok = create_print_func(PrintColors.GREEN, LogLevel.INFO, sys.stdout)
pr_header = create_print_func(PrintColors.BOLD, LogLevel.INFO, sys.stdout)


def clear_printed_line():
    sys.stdout.write("\033[F")


class DictPrintType:
    PYTHON = 1
    JSON = 2
    YAML = 3


def pr_dict(d: Union[dict, list], **kwargs) -> None:
    pr_func = kwargs.pop("pr_func", pr_info)
    print_type = kwargs.pop("print_type", DictPrintType.PYTHON)
    indent = kwargs.pop("indent", 4)
    if print_type == DictPrintType.PYTHON:
        s = pprint.pformat(d, indent=indent)
    if print_type == DictPrintType.JSON:
        s = json.dumps(d, indent=4)
    else:
        s = yaml.dump(d, indent=indent)

    pr_func(s, **kwargs)
