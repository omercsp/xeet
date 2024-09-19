from xeet.log import log_info
from xeet.common import XeetException, NonEmptyStr, pydantic_errmsg, XeetVars
from xeet.xtest import Xtest, XtestModel
from xeet import XeetDefs
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


class XeetModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    json_schema: str | None = Field(None, alias="$schema")
    includes: list[NonEmptyStr] = Field(default_factory=list, alias="include")
    tests: list[dict] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, dict] = Field(default_factory=dict)
    base_steps: dict[str, dict] = Field(default_factory=dict,
                                        validation_alias=AliasChoices("base_steps", "steps"))

    root_dir: str = Field(default_factory=str, exclude=True)
    tests_dict: dict[str, dict] = Field(default_factory=dict, alias="test_names", exclude=True)

    @model_validator(mode='after')
    def check_passwords_match(self) -> "XeetModel":
        for t in self.tests:
            name = t.get(_NAME, "").strip()
            t[_NAME] = name  # Remove leading/trailing spaces
            if not name:
                continue
            if name in self.tests_dict:
                raise ValueError(f"Duplicate test name '{name}'")
            self.tests_dict[name] = t
        return self

    def include(self, other: "XeetModel") -> None:
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


class Driver:
    def __init__(self, model: XeetModel, xvars: XeetVars) -> None:
        self.model = model
        self.xvars = xvars
        self.defs = XeetDefs(model.model_dump(by_alias=True), f"{model.root_dir}/xeet.out", xvars)
        self.expected_output_dir = f"{model.root_dir}/xeet.expected"

        #  Remove variables that are already in the environment
        for v in xvars.vars_map.keys():
            model.variables.pop(v, None)

        self.xvars.set_vars(model.variables)
        self.xvars.set_vars({
            "XEET_OUTPUT_DIR": self.defs.output_dir,
            "XEET_EXPECTED_DIR": self.expected_output_dir,
        })
        log_info(f"Output directory: {self.defs.output_dir}")

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
        return Xtest(model, self.defs)

    def xtest(self, name: str) -> Xtest | None:
        desc = self.test_desc(name)
        if not desc:
            log_info(f"Test '{name}' not found")
            return None
        return self._xtest(desc)

    def xtests(self, criteria: TestCriteria) -> list[Xtest]:
        return [self._xtest(desc) for desc in self.model.tests
                if criteria.match(desc.get(_NAME, ""),
                                  desc.get(_GROUPS, []), desc.get(_ABSTRACT, False))]

    def test_desc(self, name: str) -> dict | None:
        return self.model.tests_dict.get(name, None)

    def all_groups(self) -> set[str]:
        ret = set()
        for desc in self.model.tests:
            ret.update(desc.get(_GROUPS, []))
        return ret


class XeetConfigException(XeetException):
    ...


class XeetIncludeLoopException(XeetConfigException):
    def __init__(self, file_path: str) -> None:
        super().__init__(f"Include loop detected - '{file_path}'")


def _init(conf_file_path: str, xvars) -> str:
    cwd = os.path.abspath(os.getcwd())
    root_dir = os.path.dirname(conf_file_path)
    log_info(f"Xeet root directory: {root_dir}")
    if root_dir == "":
        root_dir = cwd
    else:
        root_dir = os.path.abspath(root_dir)
    xvars.set_vars({
        f"XEET_CWD": cwd,
        f"XEET_ROOT": root_dir,
    })
    return root_dir


def _read_xeet_conf_file(file_path: str,
                         xvars: XeetVars,
                         root_dir: str = "",
                         included: set[str] | None = None) -> XeetModel:
    if not file_path:
        for file in ("xeet.yaml", "xeet.yml", "xeet.json"):
            if os.path.exists(file):
                file_path = file
                break
        if not file_path:
            raise XeetConfigException("Empty configuration file path")
    if included is None:  # First call, main xeet configuration file
        included = set()
        root_dir = _init(file_path, xvars)

    assert xvars is not None
    file_path = xvars.expand(file_path)
    if not os.path.isabs(file_path):
        file_path = os.path.join(root_dir, file_path)

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
            model = XeetModel(**desc)
            model.root_dir = root_dir
    except (IOError, TypeError, ValueError, YamlParserError, ConstructorError,
            ComposerError) as e:
        raise XeetConfigException(f"Error parsing {file_path} - {e}")

    included.add(file_path)
    if model.includes:
        includes = [r.root for r in model.includes]
        log_info(f"Reading included files: {', '.join(includes)}")
        for i in includes[::-1]:
            inc_model = _read_xeet_conf_file(i, xvars, root_dir, included)
            model.include(inc_model)
    included.remove(file_path)

    return model


def xeet_init(file_path: str) -> Driver:
    xvars = XeetVars()
    model = _read_xeet_conf_file(file_path, xvars)
    return Driver(model, xvars)
