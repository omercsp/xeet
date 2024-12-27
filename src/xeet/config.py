from xeet.log import log_info
from xeet.common import XeetException, global_vars, NonEmptyStr, pydantic_errmsg
from xeet.xtest import Xtest, XtestModel
from xeet.globals import set_settings, set_named_steps
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, model_validator
from typing import Any
from yaml import safe_load
from yaml.parser import ParserError as YamlParserError
from yaml.constructor import ConstructorError
from yaml.composer import ComposerError
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

    #  def _match_name(self, name: str) -> str:
    #      if name in test_list:
    #          return name
    #      possible_names = [x for x in test_list if x.startswith(name)]
    #      if len(possible_names) == 0:
    #          raise XeetException(f"No tests match '{name}'")
    #      if len(possible_names) > 1:
    #          names_str = ", ".join(possible_names)
    #          raise XeetException(f"Multiple tests match '{name}': {names_str}")
    #      return possible_names[0]


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    json_schema: str | None = Field(None, alias="$schema")
    includes: list[NonEmptyStr] = Field(default_factory=list, alias="include")
    tests: list[dict] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, dict] = Field(default_factory=dict)
    base_steps: dict[str, dict] = Field(default_factory=dict,
                                        validation_alias=AliasChoices("base_steps", "steps"))

    tests_dict: dict[str, dict] = Field(default_factory=dict, alias="test_names", exclude=True)

    @model_validator(mode='after')
    def check_passwords_match(self) -> "ConfigModel":
        for t in self.tests:
            name = t.get(_NAME, "").strip()
            t[_NAME] = name  # Remove leading/trailing spaces
            if not name:
                continue
            if name in self.tests_dict:
                raise ValueError(f"Duplicate test name '{name}'")
            self.tests_dict[name] = t
        return self

    def include(self, other: "ConfigModel") -> None:
        self.variables = {**other.variables, **self.variables}
        other_tests = []
        for test in other.tests:
            name = test.get(_NAME)
            if not name or name in self.tests_dict:
                continue
            self.tests_dict[name] = test
            other_tests.append(test)
        self.tests = other_tests + self.tests
        self.base_steps = {**other.base_steps, **self.base_steps}
        for key, value in other.settings.items():
            if key in self.settings:
                self.settings[key] = {**value, **self.settings[key]}
            else:
                self.settings[key] = value


class Config:
    def __init__(self, file_path: str, model: ConfigModel) -> None:
        self.model = model
        self.variables = model.variables
        self.test_descs = model.tests
        self.includes = model.includes
        self.tests_dict: dict[str, dict] = Field(default_factory=dict)
        self.file_path = file_path
        self.root_path = os.path.dirname(file_path)
        self.base_steps = model.base_steps
        if not self.root_path:
            self.root_path = "."
        self.output_dir = f"{self.root_path}/xeet.out"
        self.expected_output_dir = f"{self.root_path}/xeet.expected"
        self.tests_dict = {t.get(_NAME): t for t in self.test_descs if t.get(_NAME)}  # type: ignore
        log_info(f"Configuration file '{file_path}' read")
        log_info(f"Output directory: {self.output_dir}")
        set_settings(model.settings)
        set_named_steps(self.base_steps)

    def _xtest_model(self, desc: dict, inherited: set[str] | None = None) -> XtestModel:
        if inherited is None:
            inherited = set()
        name = desc.get(_NAME)
        if not name:
            desc = {"name": "<Unknown>", "error": "Test has no name"}
            return XtestModel(**desc)
        try:
            ret = XtestModel(**desc)
        except ValidationError as e:
            err = pydantic_errmsg(e)
            desc = {"name": name, "error": err}
            return XtestModel(**desc)

        base_name = ret.base
        if not base_name:
            return ret
        if base_name in inherited:
            desc = {"name": name, "error": f"Inheritance loop detected for '{base_name}'"}
            return XtestModel(**desc)
        inherited.add(name)
        base_desc = self.test_desc(base_name)
        if not base_desc:
            desc = {"name": name, "error": f"No such base test '{base_name}'"}
            return XtestModel(**desc)
        base_model = self._xtest_model(base_desc, inherited)
        if base_model.error:
            return base_model
        ret.inherit(base_model)
        return ret

    def _xtest(self, desc: dict) -> Xtest:
        model = self._xtest_model(desc)
        model.output_base_dir = self.output_dir
        return Xtest(model)

    def xtest(self, name: str) -> Xtest | None:
        desc = self.test_desc(name)
        if not desc:
            log_info(f"Test '{name}' not found")
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


class XeetConfigException(XeetException):
    ...


class XeetIncludeLoopException(XeetConfigException):
    def __init__(self, file_path: str) -> None:
        super().__init__(f"Include loop detected - '{file_path}'")


_root_dir: str = ""


def _init(conf_file_path: str) -> None:
    global _root_dir
    cwd = os.path.abspath(os.getcwd())
    _root_dir = os.path.dirname(conf_file_path)
    log_info(f"Xeet root directory: {_root_dir}")
    if _root_dir == "":
        _root_dir = cwd
    else:
        _root_dir = os.path.abspath(_root_dir)
    output_dir = os.path.join(_root_dir, "xeet.out")
    global_vars().set_vars({
        f"XEET_CWD": cwd,
        f"XEET_ROOT": _root_dir,
        f"XEET_OUTPUT_DIR": output_dir,
    })


def _read_config_model(file_path: str, included: set[str] | None = None) -> ConfigModel:
    if not file_path:
        for file in ("xeet.yaml", "xeet.yml", "xeet.json"):
            if os.path.exists(file):
                file_path = file
                break
        if not file_path:
            raise XeetConfigException("Empty configuration file path")
    if included is None:  # First call, main xeet configuration file
        included = set()
        _init(file_path)

    file_path = global_vars().expand(file_path)
    if not os.path.isabs(file_path):
        file_path = os.path.join(_root_dir, file_path)

    if file_path in included:
        raise XeetIncludeLoopException(file_path)

    file_suffix = os.path.splitext(file_path)[1]
    log_info(f"Reading configuration file '{file_path}'")
    try:
        with open(file_path, 'r') as f:
            if file_suffix == ".yaml" or file_suffix == ".yml":
                desc = safe_load(f)
            else:
                desc = json.load(f)
            model = ConfigModel(**desc)
    except (IOError, TypeError, ValueError, YamlParserError, ConstructorError,
            ComposerError) as e:
        raise XeetConfigException(f"Error parsing {file_path} - {e}")

    included.add(file_path)
    if model.includes:
        includes = [r.root for r in model.includes]
        log_info(f"Reading included files: {", ".join(includes)}")
        for i in includes[::-1]:
            inc_model = _read_config_model(i, included)
            model.include(inc_model)
    included.remove(file_path)

    return model


def read_config_file(file_path: str) -> Config:
    model = _read_config_model(file_path)
    return Config(file_path, model)
