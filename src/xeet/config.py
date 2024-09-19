from xeet.log import log_info, log_warn
from xeet.common import XeetException, global_vars, NonEmptyStr, pydantic_errmsg
from xeet.xtest import Xtest
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, ValidationInfo
from typing import Any
import json
import os


_NAME = "name"
_GROUPS = "groups"
_ABSTRACT = "abstract"


class TestCriteria:
    def __init__(self, names: list[str], include_groups: list[str], require_groups: list[str],
                 exclude_groups: list[str], hidden_tests: bool) -> None:
        self.names = set(names)
        self.hidden_tests = hidden_tests
        self.include_groups = set(include_groups)
        self.require_groups = set(require_groups)
        self.exclude_groups = set(exclude_groups)

    def match(self, name: str, groups: list[str], hidden: bool) -> bool:
        if hidden and not self.hidden_tests:
            return False
        if self.names and name and name not in self.names:
            return False
        if self.include_groups and not self.include_groups.intersection(groups):
            return False
        if self.require_groups and not self.require_groups.issubset(groups):
            return False
        if self.exclude_groups and self.exclude_groups.intersection(groups):
            return False
        return True


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    json_schema: str | None = Field(None, alias="$schema")
    includes: list[NonEmptyStr] = Field(default_factory=list, alias="include")
    tests: list[dict] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    default_shell_path: str | None = Field(None, alias="default_shell_path", min_length=1)

    @field_validator('tests')
    @classmethod
    def check_alphanumeric(cls, v: list[dict], _: ValidationInfo) -> list[dict]:
        test_names = set()
        for test in v:
            name = test.get(_NAME)
            if name:
                if name in test_names:
                    raise ValueError(f"Duplicate test name '{name}'")
                test_names.add(name)
        return v


class Config:
    def __init__(self, file_path: str, model: ConfigModel) -> None:
        self.model = model
        self.variables = model.variables
        self.test_descs = model.tests
        self.includes = model.includes
        self.default_shell_path = model.default_shell_path
        self.tests_dict: dict[str, dict] = Field(default_factory=dict)
        self.file_path = file_path
        self.root_path = os.path.dirname(file_path)
        if not self.root_path:
            self.root_path = "."
        self.output_dir = f"{self.root_path}/xeet.out"
        self.expected_output_dir = f"{self.root_path}/xeet.expected"
        self.tests_dict = {t.get(_NAME): t for t in self.test_descs if t.get(_NAME)}  # type: ignore
        log_info(f"Configuration file '{file_path}' read")
        log_info(f"Output directory: {self.output_dir}")

    def include_config(self, other: "Config") -> None:
        self.variables = {**other.variables, **self.variables}
        added_tests = []
        for index, test in enumerate(other.test_descs):
            name = test.get(_NAME)
            if not name:
                continue
            if name in self.tests_dict:
                log_warn(f"Ignoring shadowed test '{name}' at index {index}, already defined")
                continue
            added_tests.append(test)
            self.tests_dict[name] = test
        self.test_descs = added_tests + self.test_descs

    def _xtest(self, desc: dict, inherited: set[str] | None = None) -> Xtest:
        ret = Xtest(desc, output_base_dir=self.output_dir, xeet_root=self.root_path,
                    dflt_shell_path=self.default_shell_path)
        if ret.init_err or not ret.base:
            return ret
        if not inherited:
            inherited = set()
        inherited.add(ret.name)
        if ret.base in inherited:
            ret.init_err = f"Inheritance loop detected for '{ret.base}'"
            return ret
        base_desc = self.tests_dict.get(ret.base, None)
        if not base_desc:
            ret.init_err = f"No such base test '{ret.base}'"
            return ret
        base_xtest = self._xtest(base_desc, inherited)
        if base_xtest.init_err:
            ret.init_err = base_xtest.init_err
            return ret
        ret.inherit(base_xtest)
        return ret

    def xtest(self, name: str) -> Xtest | None:
        desc = self.tests_dict.get(name, None)
        if not desc:
            return None
        return self._xtest(desc)

    def xtests(self, criteria: TestCriteria) -> list[Xtest]:
        return [self._xtest(desc) for desc in self.test_descs
                if criteria.match(desc.get(_NAME, ""),
                                  desc.get(_GROUPS, []), desc.get(_ABSTRACT, False))]

    def test_desc(self, name: str) -> dict | None:
        return self.tests_dict.get(name, None)

    def all_groups(self) -> set[str]:
        ret = set()
        for desc in self.test_descs:
            ret.update(desc.get(_GROUPS, []))
        return ret


_configs = {}


#  def _read_config_file(file_path: str, read_files: set) -> Config:
#      read_files_str = ", ".join(read_files)
#      log_info(f"Reading configuration file '{file_path}', read_files='{read_files_str}'")
#      try:
#          with open(file_path, 'r') as f:
#              conf = json.load(f)
#          model = ConfigModel(**conf)
#          config = Config(file_path, model)
#      except ValidationError as e:
#          err = pydantic_errmsg(e)
#          raise XeetException(f"Invalid configuration file '{file_path}': {err}")
#      except (IOError, TypeError, ValueError) as e:
#          raise XeetException(f"Error parsing {file_path} - {e}")
#      if not model.includes:
#          return config
#      includes = [i.root for i in model.includes]
#      includes_str = ", ".join(includes)
#      log_info(f"Includes: {includes_str}")
#      read_files.add(file_path)
#      file_dir = os.path.dirname(os.path.abspath(file_path))
#      for f in model.includes:
#          f = global_vars().expand(f.root)
#          if f in read_files:
#              raise XeetException(f"Include loop detected - '{f}'")
#          included_config = _read_config_file(f"{file_dir}/{f}", read_files)
#          config.include_config(included_config)
#      read_files.remove(file_path)
#      return config


class XeetConfigException(XeetException):
    ...


class XeetIncludeLoopException(XeetConfigException):
    def __init__(self, file_path: str) -> None:
        super().__init__(f"Include loop detected - '{file_path}'")


def _extract_include_files(file_path: str, included: set[str] | None = None) -> list[str]:
    file_path = global_vars().expand(file_path)
    dir_name = os.path.dirname(file_path)

    if not included:  # first call
        included = set()

    if file_path in included:
        raise XeetIncludeLoopException(f"Include loop detected - '{file_path}'")

    try:
        file_path = os.path.abspath(file_path)
        with open(file_path, 'r') as f:
            conf = json.load(f)
            model = ConfigModel(**conf)
            config = Config(file_path, model)
    except ValidationError as e:
        err = pydantic_errmsg(e)
        raise XeetConfigException(f"Invalid configuration file '{file_path}': {err}")
    except (IOError, TypeError, ValueError) as e:
        raise XeetConfigException(f"Error parsing {file_path} - {e}")
    _configs[file_path] = config

    ret = []
    included.add(file_path)
    for i in model.includes:
        include_file_path = i.root
        if not os.path.isabs(include_file_path):
            include_file_path = os.path.join(dir_name, include_file_path)
        ret += _extract_include_files(include_file_path, included)
    ret.append(file_path)
    included.remove(file_path)
    return ret


def read_config_file(file_path: str) -> Config:
    if not file_path:
        raise XeetConfigException("Empty configuration file path")
    includes = _extract_include_files(file_path)
    if not includes:  # should never happen
        raise XeetConfigException(f"No configuration files found in '{file_path}'")
    log_info(f"Reading main configuration '{file_path}'")
    last_config = None
    read_configs = set()
    for i in includes:
        if i in read_configs:
            continue
        read_configs.add(i)
        config: Config = _configs[i]
        if last_config:
            config.include_config(last_config)
        last_config = config

    return last_config  # type: ignore
