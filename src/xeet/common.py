from xeet import XeetException
from xeet.pr import *
from pydantic import Field, ValidationError, BaseModel
from pydantic.json_schema import SkipJsonSchema
from typing import Any
from collections.abc import Iterable, Callable
from jsonpath_ng.ext import parse as parse_ext
from jsonpath_ng.exceptions import JsonPathParserError
from functools import cache, wraps
from pathlib import PureWindowsPath
from dataclasses import dataclass
from rich.text import Text
from typing import Annotated
import re
import time
import threading
import re
import os


_TOKEN_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
XeetToken = Annotated[str, Field(pattern=_TOKEN_PATTERN, min_length=1)]


class KeysBaseModel(BaseModel):
    field_keys: SkipJsonSchema[set[str]] = set()
    inherited_keys: SkipJsonSchema[set[str]] = set()

    def has_key(self, key: str) -> bool:
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


_REF_PREFIX = "$ref://"

XeetVarsModel = dict[XeetToken, Any]


class XeetVars:
    def __init__(self, start_vars: XeetVarsModel | None = None,
                 parent: "XeetVars | None" = None) -> None:
        self.parent = parent
        self.vars_map = {}
        if start_vars:
            self.set_vars(start_vars)

    def _value_of(self, raw_var_name: str) -> Any:
        #  Split the name by '.' and get the value of the last part
        parts = raw_var_name.split(".", 1)
        var_name = parts[0]
        path = ".".join(parts[1:])
        if var_name in self.vars_map:
            v = self.vars_map[var_name]
        elif self.parent is not None:
            v = self.parent._value_of(var_name)
        else:
            raise XeetNoSuchVarException(f"Unknown variable '{raw_var_name}'")
        if not path:
            return v
        if not isinstance(v, (dict, list)):
            raise XeetNoSuchVarException(f"Invalid variable path '{raw_var_name}.{path}'")
        try:
            ret, found = json_value(v, path)
            if not found:
                raise XeetNoSuchVarException(f"Invalid variable path '{raw_var_name}.{path}'")
            return ret
        except XeetException as e:
            raise XeetNoSuchVarException(f"Invalid variable path '{raw_var_name}.{path}' - {e}")

    def has_var(self, name: str) -> bool:
        try:
            self._value_of(name)
            return True
        except XeetNoSuchVarException:
            return False

    def _set_var(self, name: XeetToken, value: Any) -> None:
        self.vars_map[name] = value

    def _pop_var(self, name: str) -> Any:
        return self.vars_map.pop(name)

    def set_vars(self, vars_map: XeetVarsModel) -> None:
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

    def expand(self, v: Any) -> Any:
        try:
            if isinstance(v, str):
                ret = self._expand_str(v)
            elif isinstance(v, dict):
                ret = {k: self.expand(v) for k, v in v.items()}
            elif isinstance(v, list):
                ret = [self.expand(v) for v in v]
            else:
                ret = v
            return ret
        except RecursionError:
            raise XeetRecursiveVarException("Recursive var expansion for '{s}'")

    @cache
    def _expand_str(self, s: str) -> Any:
        if not s:
            return s
        if s.startswith(_REF_PREFIX[0]) and s[1:].startswith(_REF_PREFIX):
            return s[1:]
        if s.startswith(_REF_PREFIX):
            #  This is a reference to a variable
            parts = s[len(_REF_PREFIX):].split(".", 1)
            var_name = parts[0]
            if not var_name:
                raise XeetBadVarNameException("Empty variable name")
            path = parts[1] if len(parts) > 1 else ""
            v = self._value_of(var_name)
            v = self.expand(v)
            if not path or not (type(v) is dict or type(v) is list):
                return v
            v, found = json_value(v, path)
            if not found:
                raise XeetNoSuchVarException(f"Invalid variable path '{var_name}.{path}'")
            return v
        return self._expand_str_literals(s)

    # Regex Explanation:
    #
    # \\*
    # The '\\' is an escaped backslash. The '*' quantifier means it will match
    # zero or more preceding backslash characters.
    #
    # {[^{}]+}
    # This part finds a simple, non-nested block of braces.
    #   - `{`: Matches the literal opening brace.
    #   - `[^{}]+`: Matches one or more characters that are NOT an opening
    #     or closing brace. This is the key to preventing a "greedy" match
    #     that would capture nested braces.
    #   - `}`: Matches the literal closing brace.
    #
    # Unlike the previous version, this pattern does not need a capturing
    # group because the entire desired string is matched by the pattern.

    _literal_re = re.compile(r"\\*{[^{}]+}")

    def _expand_str_literals(self, s: str) -> str:
        if not s:
            return s
        m = XeetVars._literal_re.search(s)
        if not m:
            return s
        m_str = m.group(0)
        last_backslash = m_str.rfind("\\")
        if last_backslash != -1:
            #  If the last backslash is odd, it means the first part is a literal
            if (last_backslash + 1) % 2 == 1:
                return s[:m.start()] + m_str[1:] + self._expand_str_literals(s[m.end():])
            ret = s[:m.start() + last_backslash + 1]
            literal = m_str[last_backslash + 2:-1].strip()
        else:
            ret = s[:m.start()]
            literal = m_str[1:-1].strip()

        if not literal or literal == "$":
            raise XeetBadVarNameException("Empty variable name in string literal")
        if literal.startswith("$"):
            ret += os.getenv(literal[1:], "")
        else:
            #  In case the value is a string, it might be expanded to a refernce
            #  string, so expand it again.
            m_str_value = self.expand(self._value_of(literal))

            #  Corener case: if the value is a dict, we need to escape it so it won't
            #  be interpreted as a variable reference.
            if isinstance(m_str_value, dict):
                ret += "\\"
            ret += str(m_str_value)
        ret += s[m.end():]
        return self._expand_str_literals(ret)


ValidationDict = dict[type, Callable[[Any], bool] | None]


class _Validator:
    def __init__(self, type_validators: ValidationDict = dict()) -> None:
        self.type_validators = type_validators
        self.inner_validator = self._gen_inner_validator()

    def _gen_inner_validator(self) -> Callable:
        @_validate_arg(list(self.type_validators.keys()))
        def _validate(v: Any) -> bool:
            instance = False
            for t, validator in self.type_validators.items():
                if not isinstance(v, t) or validator is None:
                    continue
                instance = True
                if not validator(v):
                    return False
            return instance
        return _validate

    def __call__(self, v: Any) -> bool:
        return self.inner_validator(v)


def gen_validator(type_validators: ValidationDict) -> Callable:
    return _Validator(type_validators)


def validate_types(v: Any, allowed_types: type | list[type] | ValidationDict) -> bool:
    if isinstance(allowed_types, type):
        allowed_types = [allowed_types]
    if isinstance(allowed_types, list):
        return isinstance(v, tuple(allowed_types))
    return _Validator(allowed_types)(v)


def _validate_arg(allowed_types: list[type]):
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(arg: Any, **kwargs) -> bool:
            if not validate_types(arg, allowed_types):
                return False
            return func(arg, **kwargs)
        return wrapper
    return decorator


@_validate_arg([str])
def validate_str(v: str, min_len: int = -1, max_len: int = -1, strip: bool = False,
                 regex: str = "") -> bool:
    if strip:
        v = v.strip()
    if min_len >= 0 and len(v) < min_len:
        return False
    if max_len >= 0 and len(v) > max_len:
        return False
    if regex:
        if not re.match(regex, v):
            return False
    return True


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
    except KeyError as e:
        raise XeetException(f"Key error in JSONPath expression: {path} - {e}")


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


@dataclass
class StrFilterData:
    from_str: str
    to_str: str
    regex: bool = False
    from_re: re.Pattern | None = None


def filter_str(s: str, filters: Iterable[StrFilterData]) -> str:
    def _filter_all(s: str, fltr: StrFilterData) -> str:
        if fltr.regex:
            if fltr.from_re is None:
                fltr.from_re = re.compile(fltr.from_str)
            return fltr.from_re.sub(fltr.to_str, s)

        return s.replace(fltr.from_str, fltr.to_str)

    for fltr in filters:
        s = _filter_all(s, fltr)
    return s


def underline(title: str, underline_char='=') -> str:
    text = Text.from_markup(title.strip("\n"))
    underline = underline_char * len(text.plain)
    text = f"{title}\n{underline}"
    return text
