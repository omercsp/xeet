from xeet.log import start_raw_logging, stop_raw_logging, log_verbose, log_warn
import sys
import re
import os
import traceback
import json
from typing import Any, Tuple

XEET_YES_TOKEN = 'yes'
XEET_NO_TOKEN = 'no'

# Common keys


class XeetException(Exception):
    def __init__(self, error: str) -> None:
        self.error = error

    def __str__(self) -> str:
        return self.error


def _dict_path_elements(path: str) -> list:
    elements = []
    for element in path.split('/'):
        if element.startswith("#"):
            try:
                index_el = int(element[1:])
                element = index_el
            except (IndexError, ValueError):
                pass
        elements.append(element)
    return elements


def dict_value(d: dict, path: str, require=False, default=None) -> Any:
    elements = _dict_path_elements(path)
    field = d
    try:
        for element in elements:
            field = field[element]
        return field

    except (KeyError, IndexError):
        if require:
            raise XeetException(f"No '{path}' setting was found")
    return default


class XeetVars(object):
    _SYSTEM_VAR_PREFIX = "XEET_"

    def __init__(self) -> None:
        self._vars = {}

    def __getitem__(self, name: str) -> Any:
        return self._vars[name]

    def set_var(self, name: str, value: Any, system: bool = False) -> None:
        if name.startswith(self._SYSTEM_VAR_PREFIX):
            log_warn((f"Invalid variable name '{name}'. "
                      f"Variables prefixed with '{self._SYSTEM_VAR_PREFIX}'"
                      " are reserved for system use"))
            return
        if system:
            name = f"{self._SYSTEM_VAR_PREFIX}{name}"
        self._vars[name] = value

    def set_vars(self, vars_map: dict, system: bool = False) -> None:
        for name, value in vars_map.items():
            self.set_var(name, value, system)

    def set_vars_raw(self, vars_map: dict) -> None:
        self._vars.update(vars_map)

    def get_vars(self) -> dict:
        return self._vars

    def system_vars(self) -> dict:
        return {
            k: v if v else "" for k, v in self._vars.items()
            if k.startswith(self._SYSTEM_VAR_PREFIX)
        }


_global_variables = XeetVars()


def set_global_vars(vars_map: dict, system: bool = False) -> None:
    _global_variables.set_vars(vars_map, system)


def get_global_vars() -> dict:
    return _global_variables.get_vars()


def dump_global_vars() -> None:
    start_raw_logging()
    for k, v in _global_variables.get_vars().items():
        log_verbose("{}='{}'", k, v)
    stop_raw_logging()


class StringVarExpander(object):
    var_re = re.compile(r'{{\S*?}}')

    def __init__(self, vars_map: dict) -> None:
        self.vars_map = vars_map
        self.expansion_stack = []

    def __call__(self, s: str) -> str:
        if not s:
            return s
        if self.expansion_stack:
            raise XeetException("Incomplete variable expansion?")
        return re.sub(self.var_re, self._expand_re, s)

    def _expand_re(self, match) -> str:
        var = match.group()[2:-2]
        if var in self.expansion_stack:
            raise XeetException(f"Recursive expanded var '{var}'")
        if var.startswith("$"):
            return os.getenv(var[1:], "")
        value = self.vars_map.get(var, "")
        if type(value) is list or type(value) is dict:
            raise XeetException(f"Var expanded path '{var}' doesn't refer to valid type")
        self.expansion_stack.append(var)
        s = re.sub(self.var_re, self._expand_re, str(value))
        self.expansion_stack.pop()
        return s


def parse_assignment_str(s: str) -> Tuple[str, str]:
    parts = s.split('=', maxsplit=1)
    if len(parts) == 1:
        return s, ""
    return parts[0], parts[1]


def bt() -> None:
    traceback.print_stack(file=sys.stdout)


def print_dict(d: dict) -> None:
    print(json.dumps(d, indent=4))


def text_file_head(file_path: str, lines: int = 5) -> str:
    ret = ""
    try:
        with open(file_path, 'r') as f:
            for _ in range(lines):
                line = f.readline()
                if not line:
                    break
                ret += line
    except OSError:
        pass
    return ret.rstrip("\n")

def text_file_tail(file_path: str, lines: int = 5) -> str:
    ret = ""
    try:
        with open(file_path, 'r') as f:
            f.seek(0, os.SEEK_END)
            f.seek(f.tell() - 1, os.SEEK_SET)
            if f.read(1) == '\n':
                f.seek(f.tell() - 1, os.SEEK_SET)
            for _ in range(lines):
                line = f.readline()
                ret += line
    except OSError:
        pass
    return ret.rstrip("\n")
