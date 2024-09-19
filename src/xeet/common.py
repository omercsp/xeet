from xeet.log import start_raw_logging, stop_raw_logging, log_verbose
from pydantic import Field, RootModel, ValidationError
from typing import Any
from functools import cache
import re
import os


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


_global_xvars: "_XeetVarsBase" = None  # type: ignore


class XeetVars:
    _SYSVAR_PREFIX = "XEET"
    _var_re = re.compile(r'{\S*?}')
    _var_name_re = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

    def __init__(self, start_vars: dict | None = None,
                 start_sys_vars: dict | None = None) -> None:
        self.vars_map = {}
        if _global_xvars:
            self.vars_map = {**_global_xvars.vars_map}
        if start_vars:
            self.set_vars(start_vars, False)
        if start_sys_vars:
            self.set_vars(start_sys_vars, True)

    def __getitem__(self, name: str) -> Any:
        try:
            return self.vars_map[name]
        except KeyError:
            raise XeetException(f"Var '{name}' not found")

    def _set_var(self, name: str, value: Any, system: bool = False) -> None:
        if not self._var_name_re.match(name):
            raise XeetException(f"Invalid variable name '{name}'")
        if name.startswith(self._SYSVAR_PREFIX):
            raise XeetException((f"Invalid variable name '{name}'. "
                                 f"Variables prefixed with '{self._SYSVAR_PREFIX}'"
                                 " are reserved for system use"))
        if system:
            name = f"{self._SYSVAR_PREFIX}_{name}"
        self.vars_map[name] = value

    def set_vars(self, vars_map: dict, system: bool = False) -> None:
        for name, value in vars_map.items():
            self._set_var(name, value, system)
        self.expand.cache_clear()

    @property
    def sys_vars_map(self) -> dict:
        return {
            k: v if v else "" for k, v in self.vars_map.items()
            if k.startswith(self._SYSVAR_PREFIX)
        }

    @cache
    def expand(self, s: str) -> str:
        if not s:
            return s
        return self._StrExpander(self).expand(s)

    class _StrExpander(object):
        def __init__(self, xvars: "XeetVars") -> None:
            self.vars = xvars
            self.expansion_stack = []

        def expand(self, s: str) -> str:
            return re.sub(XeetVars._var_re, self._expand_re, s)

        def _expand_re(self, match) -> str:
            var = match.group()[1:-1]
            if var in self.expansion_stack:
                raise XeetException(f"Recursive expanded var '{var}'")
            if var.startswith("$"):
                return os.getenv(var[1:], "")
            value = self.vars[var]
            #  if type(value) is list or type(value) is dict:
            #      raise XeetException(f"Var expanded path '{var}'
            #  doesn't refer to valid type")
            self.expansion_stack.append(var)
            s = re.sub(XeetVars._var_re, self._expand_re, str(value))
            self.expansion_stack.pop()
            return s


_global_xvars = XeetVars()


def update_global_vars(vars_map: dict) -> None:
    _global_xvars.set_vars(vars_map, True)


def global_vars() -> XeetVars:
    return _global_xvars


def dump_global_vars() -> None:
    start_raw_logging()
    for k, v in _global_xvars.vars_map.items():
        log_verbose("{}='{}'", k, v)
    stop_raw_logging()


#  Read the last n lines of a text file. Allows at most max_bytes to be read.
#  this isn't very efficient for large files if max_bytes value is big, but
#  it's intended for small text content.
def text_file_tail(file_path: str, n_lines: int = 5, max_bytes=4096) -> str:
    if n_lines <= 0 or max_bytes <= 0:
        raise XeetException("Invalid n_lines or max_bytes")
    with open(file_path, 'rb') as f:
        # Move to the end of the file
        f.seek(0, 2)
        file_size = f.tell()
        if file_size < max_bytes:
            f.seek(0)
            content = f.read()
        else:
            f.seek(-max_bytes, 2)
            content = f.read()
    #  Find the n_line'th occurrence of '\n' from the end
    pos = len(content) - 1
    for _ in range(n_lines):
        pos = content.rfind(b'\n', 0, pos)
        if pos == -1:  # Less than n_lines, return everything
            return content.decode('utf-8')
    return content[pos + 1:].decode('utf-8')


class NonEmptyStr(RootModel):
    root: str = Field(..., min_length=1)


class VarDef(RootModel):
    root: dict[NonEmptyStr, str] = Field(..., min_length=1, max_length=1)


def pydantic_errmsg(ve: ValidationError) -> str:
    errs = []
    for e in ve.errors():
        try:
            loc_len = len(e["loc"])
            if loc_len == 0:
                loc = "<ROOT>"
            elif loc_len == 1 and isinstance(e["loc"][0], int):
                token = e["loc"][0]
                loc = f"index {token}"
            else:
                loc = "/".join(str(i) for i in e["loc"])
            errs.append(f"'{loc}': {e['msg']}")
        except Exception:
            errs.append(str(e))
    return "\n".join(errs)


def yes_no_str(value: bool) -> str:
    return "Yes" if value else "No"
