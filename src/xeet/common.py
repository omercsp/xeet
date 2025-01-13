from os.path import samefile
from xeet import XeetException
from pydantic import Field, RootModel, ValidationError, BaseModel
from typing import Any, Callable, Iterable
#  from jsonpath_ng import parse
from jsonpath_ng.ext import parse as parse_ext
from jsonpath_ng.exceptions import JsonPathParserError
from functools import cache
from pathlib import PureWindowsPath
import time
import threading
import re
import os


class KeysBaseModel(BaseModel):
    field_keys: set[str] = Field(default_factory=set, exclude=True)
    inherited_keys: set[str] = Field(default_factory=set, exclude=True)

    def has_key(self, key: str, check_inherited: bool = False) -> bool:
        return key in self.field_keys

    def inherited_key(self, key: str) -> bool:
        return key in self.inherited_keys

    def inherit_attr(self, key: str, value: Any) -> None:
        setattr(self, key, value)
        self.inherited_keys.add(key)

    def model_post_init(self, __: Any):
        self.field_keys = set(self.model_dump(exclude_unset=True).keys())
        self.inherited_keys = set()


class XeetNoSuchVarException(XeetException):
    ...


class XeetRecursiveVarException(XeetException):
    ...


class XeetBadVarNameException(XeetException):
    ...


class XeetInvalidVarType(XeetException):
    ...


class XeetVars:
    _REF_PREFIX = "$ref://"
    _var_re = re.compile(r'\\*{[a-zA-Z0-9"\'_\.\$\[\]]*?}')
    _var_name_re = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

    def __init__(self, start_vars: dict | None = None, parent: "XeetVars | None" = None) -> None:
        self.parent = parent
        if start_vars is None:
            self.vars_map = {}
        else:
            self.vars_map = {**start_vars}

    def _value_of(self, name: str) -> Any:
        #  Split the name by '.' and get the value of the last part
        parts = name.split(".", 1)
        name = parts[0]
        path = ".".join(parts[1:])
        if name in self.vars_map:
            v = self.vars_map[name]
        elif self.parent is not None:
            v = self.parent._value_of(name)
        else:
            raise XeetNoSuchVarException(f"Unknown variable '{name}'")
        if not path:
            return v
        if not isinstance(v, (dict, list)):
            raise XeetNoSuchVarException(f"Invalid variable path '{name}.{path}'")
        try:
            ret, found = json_value(v, path)
            if not found:
                raise XeetNoSuchVarException(f"Invalid variable path '{name}.{path}'")
            return ret
        except XeetException as e:
            raise XeetNoSuchVarException(f"Invalid variable path '{name}.{path}' - {e}")

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

    def reset(self) -> None:
        self.vars_map.clear()
        self._expand_str.cache_clear()

    def expand(self, v: Any, value_types: list[type] = list()) -> Any:
        try:
            if isinstance(v, str):
                ret = self._expand_str(v)
            elif isinstance(v, dict):
                ret = {k: self.expand(v) for k, v in v.items()}
            elif isinstance(v, list):
                ret = [self.expand(v) for v in v]
            else:
                ret = v
            if value_types and type(ret) not in value_types:
                raise XeetInvalidVarType(f"Invalid value type for {v}: {ret} is {type(ret)}")
            return ret
        except RecursionError:
            raise XeetRecursiveVarException("Recursive var expansion for '{s}'")

    @cache
    def _expand_str(self, s: str) -> Any:
        if not s:
            return s
        if len(s) >= len(self._REF_PREFIX):
            if s.startswith(self._REF_PREFIX[0]) and s[1:].startswith(self._REF_PREFIX):
                return s[1:]
            if s.startswith(self._REF_PREFIX):
                var_name = s[len(self._REF_PREFIX):]
                if not var_name:
                    raise XeetBadVarNameException("Empty variable name")
                v = self._value_of(var_name)
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
            ret += str(self._value_of(m_str))
        e = m.end()
        s2 = s[e:]
        ret += s2
        return self.expand(ret)


#  Read the last n lines of a text file. Allows at most max_bytes to be read.
#  this isn't very efficient for large files if max_bytes value is big, but
#  it's intended for small text content.
def text_file_tail(file_path: str, n_lines: int = 30, max_bytes=4096) -> str:
    if n_lines <= 0 or max_bytes <= 0:
        raise ValueError("Invalid n_lines or max_bytes")

    file_size = os.path.getsize(file_path)
    with open(file_path, 'rb') as f:
        if file_size < max_bytes:
            f.seek(0)
            content: bytes = f.read()
        else:
            f.seek(-max_bytes, 2)
            content: bytes = f.read()

    new_line = b'\r\n' if in_windows() else b'\n'
    new_line_len = len(new_line)

    #  Find the n_line'th occurrence of '\n' from the end
    pos = len(content) - 1
    for _ in range(n_lines):
        pos = content.rfind(new_line, 0, pos)
        if pos == -1:  # Less than n_lines, return everything
            return content.decode('utf-8')
    return content[pos + new_line_len:].decode('utf-8')


class NonEmptyStr(RootModel):
    root: str = Field(..., min_length=1)


class VarDef(RootModel):
    root: dict[NonEmptyStr, str] = Field(..., min_length=1, max_length=1)


def pydantic_errmsg(ve: ValidationError) -> str:
    errs = []
    for e in ve.errors():
        try:
            loc_len = len(e["loc"])
            loc = ""
            if loc_len > 0:
                if loc_len == 1 and isinstance(e["loc"][0], int):
                    token = e["loc"][0]
                    loc = f"index {token}"
                else:
                    loc = "/".join(str(i) for i in e["loc"])
                loc = f"'{loc}': "
            errs.append(f"{loc}{e['msg']}")
        except Exception:
            errs.append(str(e))
    return "\n".join(errs)


def yes_no_str(value: bool) -> str:
    return "Yes" if value else "No"


def in_windows() -> bool:
    return os.name == "nt"


def platform_path(path: str) -> str:
    if in_windows():
        return PureWindowsPath(path).as_posix()
    return path


#  Return a list of values found by the JSONPath expression
def json_values(obj: dict | list, path: str) -> list[Any]:
    try:
        expr = parse_ext(path)
        return [match.value for match in expr.find(obj)]
    except JsonPathParserError as e:
        raise XeetException(f"Invalid JSONPath expression: {path} - {e}")


#  Return the first value found by the JSONPath expression. If no value is found, return None
#  If multiple values are found, raise an exception
def json_value(obj: dict | list, path: str) -> tuple[Any, bool]:
    values = json_values(obj, path)
    if len(values) == 0:
        return None, False
    if len(values) > 1:
        raise XeetException(f"Multiple values found for JSONPath expression: {path}")
    return values[0], True


def short_str(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."


class FileTailer:
    def __init__(self, file_path: str, poll_interval: float = 0.05, pr_func: Callable = print
                 ) -> None:
        self.file_path = file_path
        self.poll_interval = poll_interval
        self.stop_event = threading.Event()
        self.kill_event = threading.Event()
        self.pr_func = pr_func
        self.thread = threading.Thread(target=self.go)

    def start(self) -> None:
        self.thread.start()

    def go(self) -> None:
        try:
            with open(self.file_path, 'r') as file:
                while True:
                    if self.kill_event.is_set():
                        return
                    if self.stop_event.is_set() and file.tell() >= os.path.getsize(self.file_path):
                        return
                    where = file.tell()
                    line = file.readline()
                    if line:
                        self.pr_func(line, end="")
                    else:
                        time.sleep(self.poll_interval)
                        file.seek(where)  # Reset file pointer if no new data
        except Exception as e:
            self.pr_func(f"Error tailing file: {e}")

    def stop(self, kill: bool = False) -> None:
        self.stop_event.set()
        if kill:
            self.kill_event.set()
        if self.thread.is_alive():
            self.thread.join()
