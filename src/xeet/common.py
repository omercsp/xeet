from xeet.log import start_raw_logging, stop_raw_logging, log_verbose, log_warn
import sys
import re
import os
import traceback
import json
import copy
from typing import Optional, Any, Tuple
import jsonschema

XEET_YES_TOKEN = 'yes'
XEET_NO_TOKEN = 'no'


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


_variables = {}


def set_xeet_var(name: str, value: Any, allow_system: bool = False) -> None:
    global _variables
    if not allow_system and name.startswith("__") and name.endswith("__"):
        log_warn("Variable name '{}' is reserved for system use", name)
        return
    _variables[name] = value


def set_xeet_vars(vars_map: dict, allow_system: bool = False) -> None:
    for name, value in vars_map.items():
        set_xeet_var(name, value, allow_system)


def dump_defualt_vars() -> None:
    start_raw_logging()
    for k, v in _variables.items():
        log_verbose("{}='{}'", k, v)
    stop_raw_logging()


class StringVarExpander(object):
    var_re = re.compile(r'{{\S*?}}')

    def __init__(self, vars_map: Optional[dict] = None) -> None:
        if not vars_map:
            self.vars_map = _variables
        else:
            self.vars_map = copy.deepcopy(_variables)
            self.vars_map.update(vars_map)

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


def validate_json_schema(data: dict, schema: dict) -> Optional[str]:
    try:
        jsonschema.validate(data, schema)
        return None
    except jsonschema.ValidationError as e:
        if e.absolute_path:
            path = "/".join(str(v) for v in list(e.absolute_path))
            return f"Schema validation error at '{path}': {e.message}"
        else:
            return f"Schema validation error: {e.message}"
