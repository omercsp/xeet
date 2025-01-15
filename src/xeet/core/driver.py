from .xtest import Xtest, XtestModel
from .run_reporter import RunReporter, RunNotifier
from .resource import ResourceModel
from . import TestCriteria, XeetDefs
from xeet.log import log_info, log_warn
from xeet.common import XeetException, NonEmptyStr, pydantic_errmsg, XeetVars
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from typing import Any
from yaml import safe_load
from yaml.parser import ParserError as YamlParserError
from yaml.constructor import ConstructorError
from yaml.composer import ComposerError
from yaml.scanner import ScannerError
import json
import os


_NAME = "name"
_GROUPS = "groups"
_ABSTRACT = "abstract"


class XeetModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    json_schema: str | None = Field(None, alias="$schema")
    includes: list[NonEmptyStr] = Field(default_factory=list, alias="include")
    tests: list[dict] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, dict] = Field(default_factory=dict)
    resources: dict[str, list[ResourceModel]] = Field(default_factory=dict)

    root_dir: str = Field(default_factory=str, exclude=True)
    tests_dict: dict[str, dict] = Field(default_factory=dict, alias="test_names", exclude=True)

    @model_validator(mode='after')
    def post_validate(self) -> "XeetModel":
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
        self.resources = {**other.resources, **self.resources}
        other_tests = []
        for test in other.tests:
            name = test.get(_NAME)
            if not name or name in self.tests_dict:
                continue
            self.tests_dict[name] = test
            other_tests.append(test)
        self.tests = other_tests + self.tests
        for key, value in other.settings.items():
            if key in self.settings:
                self.settings[key] = {**value, **self.settings[key]}
            else:
                self.settings[key] = value


class Driver:
    def __init__(self, model: XeetModel, xdefs: XeetDefs) -> None:
        self.model = model
        self.xdefs = xdefs
        self.xvars = xdefs.xvars

        for v in model.variables:
            if v in self.xvars.vars_map:
                log_warn(f"Variable '{v}' is already defined in the environment")
                model.variables.pop(v)
        self.xvars.set_vars(model.variables)

        for name, resources in model.resources.items():
            self.xdefs.add_resource_pool(name, resources)

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
            ret.error = f"Base test '{base_name}' error: {base_model.error}"
            return ret
        ret.inherit(base_model)
        return ret

    def _xtest(self, desc: dict) -> Xtest:
        model = self._xtest_model(desc)
        return Xtest(model, self.xdefs)

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


def _read_conf_file(file_path: str,
                    xvars: XeetVars,
                    root_dir: str,
                    included: set[str] | None = None) -> XeetModel:
    if included is None:
        included = set()

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
            ComposerError, ScannerError) as e:
        raise XeetConfigException(f"Error parsing {file_path} - {e}")

    included.add(file_path)
    if model.includes:
        includes = [r.root for r in model.includes]
        log_info(f"Reading included files: {', '.join(includes)}")
        for i in includes[::-1]:
            inc_model = _read_conf_file(i, xvars, root_dir, included)
            model.include(inc_model)
    included.remove(file_path)

    return model


def xeet_init(file_path: str, debug_mode=False, reporters: list[RunReporter] = list()) -> Driver:
    if not file_path:
        for file in ("xeet.yaml", "xeet.yml", "xeet.json"):
            if os.path.exists(file):
                file_path = file
                break
        if not file_path:
            raise XeetConfigException("Empty configuration file path")

    notifier = RunNotifier(reporters)
    xdefs = XeetDefs(file_path, debug_mode, notifier)
    log_info(f"Main Xeet configuration file: {xdefs.xeet_file_path}")
    log_info(f"Root directory: {xdefs.root_dir}")
    log_info(f"Current working directory: {xdefs.cwd}")
    log_info(f"Expected output directory: {xdefs.expected_output_dir}")
    model = _read_conf_file(xdefs.xeet_file_path, xdefs.xvars, xdefs.root_dir)
    xdefs.set_defs(model.model_dump(by_alias=True))
    return Driver(model, xdefs)
