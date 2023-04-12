from typing import Callable


XEET_GREEN = '\033[92m'
XEET_RED = '\033[91m'
XEET_YELLOW = '\033[93m'
XEET_WHITE = '\u001b[37;1m'
XEET_RESET = '\033[0m'

_colored_print = True


def xeet_color_enabled() -> bool:
    return _colored_print


def set_no_color_print() -> None:
    global _colored_print
    _colored_print = False


def _gen_print_func(color: str) -> Callable:
    def _print(*args, **kwargs) -> None:
        if not _colored_print:
            print(*args, **kwargs)
            return
        print(color, end='')
        print(*args, **kwargs)
        print(XEET_RESET, end='')
    return _print


pr_ok = _gen_print_func(XEET_GREEN)
pr_err = _gen_print_func(XEET_RED)
pr_warn = _gen_print_func(XEET_YELLOW)
pr_info = print
pr_verbose = print
pr_bright = _gen_print_func(XEET_WHITE)
