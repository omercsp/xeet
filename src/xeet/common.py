from pydantic import Field, RootModel, ValidationError
from typing import Any, Iterable
from jsonpath_ng import parse
from jsonpath_ng.exceptions import JsonPathParserError
from functools import cache
import re
import os


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


class XeetNoSuchVarException(XeetException):
    ...


class XeetRecursiveVarException(XeetException):
    ...


class XeetBadVarNameException(XeetException):
    ...


class XeetVars:
    _REF_PREFIX = "$ref://"
    _var_re = re.compile(r'\\*{[a-zA-Z_][a-zA-Z0-9_]*?}')
    _var_name_re = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

    def __init__(self, start_vars: dict | None = None, parent: "XeetVars | None" = None) -> None:
        self.parent = parent
        if start_vars is None:
            self.vars_map = {}
        else:
            self.vars_map = {**start_vars}

    def value_of(self, name: str) -> str:
        if name in self.vars_map:
            return self.vars_map[name]
        if self.parent is not None:
            return self.parent.value_of(name)
        raise XeetNoSuchVarException(f"Var '{name}' not found")

    def _set_var(self, name: str, value: Any) -> None:
        if not self._var_name_re.match(name):
            raise XeetBadVarNameException(f"Invalid variable name '{name}'")
        self.vars_map[name] = value

    def _pop_var(self, name: str) -> Any:
        return self.vars_map.pop(name)

    def set_vars(self, vars_map: dict) -> None:
        for name, value in vars_map.items():
            self._set_var(name, value)
        self._expand_str.cache_clear()

    def pop_vars(self, var_names: Iterable) -> None:
        for name in var_names:
            self._pop_var(name)
        self._expand_str.cache_clear()

    def expand(self, v: Any) -> Any:
        try:
            if isinstance(v, str):
                return self._expand_str(v)
            if isinstance(v, dict):
                return {k: self.expand(v) for k, v in v.items()}
            if isinstance(v, list):
                return [self.expand(v) for v in v]
            return v
        except RecursionError:
            raise XeetRecursiveVarException("Recursive var expansion for '{s}'")

    @cache
    def _expand_str(self, s: str) -> str:
        if not s:
            return s
        if len(s) >= len(self._REF_PREFIX):
            if s.startswith(self._REF_PREFIX[0]) and s[1:].startswith(self._REF_PREFIX):
                return s[1:]
            if s.startswith(self._REF_PREFIX):
                var_name = s[len(self._REF_PREFIX):]
                if not var_name:
                    raise XeetBadVarNameException("Empty variable name")
                v = self.value_of(var_name)
                return self.expand(v)
        return self._expand_str_literals(s)

    def _expand_str_literals(self, s: str) -> str:
        if not s:
            return s
        m = XeetVars._var_re.search(s)
        if not m:
            return s
        ret = s[:m.start()]
        m_str = m.group()
        backslash = False
        while m_str[0] == "\\":
            m_str = m_str[1:]
            if backslash:
                ret += "\\\\"
                backslash = False
            else:
                backslash = True

        if backslash:
            return ret + m_str + self.expand(s[m.end():])

        m_str = m_str[1:-1]
        if m_str.startswith("$"):
            ret += os.getenv(m_str[1:], "")
        else:
            ret += str(self.value_of(m_str))
        ret += s[m.end():]
        return self.expand(ret)


@cache
def global_vars() -> XeetVars:
    return XeetVars()


#  Read the last n lines of a text file. Allows at most max_bytes to be read.
#  this isn't very efficient for large files if max_bytes value is big, but
#  it's intended for small text content.
def text_file_tail(file_path: str, n_lines: int = 30, max_bytes=4096) -> str:
    if n_lines <= 0 or max_bytes <= 0:
        raise ValueError("Invalid n_lines or max_bytes")
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


def in_windows() -> bool:
    return os.name == "nt"


#  Return a list of values found by the JSONPath expression
def json_values(obj: dict, path: str) -> list[Any]:
    try:
        expr = parse(path)
        return [match.value for match in expr.find(obj)]
    except JsonPathParserError as e:
        raise XeetException(f"Invalid JSONPath expression: {path} - {e}")


#  Return the first value found by the JSONPath expression. If no value is found, return None
#  If multiple values are found, raise an exception
def json_value(obj: dict, path: str) -> tuple[Any, bool]:
    values = json_values(obj, path)
    if len(values) == 0:
        return None, False
    if len(values) > 1:
        raise XeetException(f"Multiple values found for JSONPath expression: {path}")
    return values[0], True
