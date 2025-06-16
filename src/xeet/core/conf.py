from .resource import ResourceModel
from .matrix import MatrixModel, Matrix
from xeet.log import log_info
from xeet.common import XeetException, NonEmptyStr, pydantic_errmsg, XeetVars, XeetToken
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from typing import Any, Iterator
from yaml import safe_load
from yaml.parser import ParserError as YamlParserError
from yaml.constructor import ConstructorError
from yaml.composer import ComposerError
from yaml.scanner import ScannerError
from copy import deepcopy
import json
import os


_NAME = "name"
_MATRIX = "matrix"
_PRMTTN = "prmttn"


class XeetConfModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    json_schema: str | None = Field(None, alias="$schema")
    includes: list[NonEmptyStr] = Field(default_factory=list, alias="include")
    tests: list[dict] = Field(default_factory=list)
    variables: dict[XeetToken, Any] = Field(default_factory=dict)
    settings: dict[XeetToken, dict] = Field(default_factory=dict)
    tests_dict: dict[str, dict] = Field(default_factory=dict, exclude=True)
    resources: dict[XeetToken, list[ResourceModel]] = Field(default_factory=dict)
    matrix: MatrixModel = Field(default_factory=MatrixModel)

    @model_validator(mode='after')
    def post_validate(self) -> "XeetConfModel":
        for t in self.tests:
            name = t.get(_NAME, "").strip()
            t[_NAME] = name  # Remove leading/trailing spaces
            if not name:
                continue
            if name in self.tests_dict:
                raise ValueError(f"Duplicate test name '{name}'")
            self.tests_dict[name] = t

        #  Check if any of the matrix names conflict with the existing variables
        colliding_keys = set(self.matrix.keys()) & set(self.variables.keys())
        if colliding_keys:
            keys_str = ', '.join(colliding_keys)
            raise ValueError(f"Matrix names conflict with the existing variables: {keys_str}")
        return self

    def include(self, other: "XeetConfModel") -> None:
        self.variables = {**other.variables, **self.variables}
        self.resources = {**other.resources, **self.resources}
        self.matrix = {**other.matrix, **self.matrix}
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


class _XeetConf:
    def __init__(self, file_path: str, model: XeetConfModel) -> None:
        self.file_path = file_path
        self.model = model

    def test_desc(self, name: str) -> dict | None:
        return self.model.tests_dict.get(name, None)

    def descs(self) -> Iterator[dict]:
        """Iterate over all test descriptions in the configuration."""
        for desc in self.model.tests:
            yield desc


class XeetConfigException(XeetException):
    ...


class XeetIncludeLoopException(XeetConfigException):
    def __init__(self, file_path: str) -> None:
        super().__init__(f"Include loop detected - '{file_path}'")


def _read_conf_file(file_path: str, xvars: XeetVars, included: set[str] | None = None
                    ) -> XeetConfModel:
    if included is None:
        included = set()

    file_path = xvars.expand(file_path)
    if not os.path.isabs(file_path):
        file_path = os.path.join(os.getcwd(), file_path)

    if file_path in included:
        raise XeetIncludeLoopException(file_path)

    file_suffix = os.path.splitext(file_path)[1]
    log_info(f"reading configuration file '{file_path}'")
    try:
        with open(file_path, 'r') as f:
            if file_suffix == ".yaml" or file_suffix == ".yml":
                desc = safe_load(f)
            else:
                desc = json.load(f)
            model = XeetConfModel(**desc)
    except ValidationError as e:
        raise XeetConfigException(f"Error parsing {file_path} - {pydantic_errmsg(e)}")
    except (IOError, TypeError, ValueError, YamlParserError, ConstructorError,
            ComposerError, ScannerError) as e:
        raise XeetConfigException(f"Error parsing {file_path} - {e}")

    included.add(file_path)

    if model.includes:
        base_dir = os.path.dirname(file_path)
        includes = [xvars.expand(r) for r in model.includes]
        log_info(f"reading included files: {', '.join(includes)}")
        for inc_file_name in includes[::-1]:
            if not os.path.isabs(inc_file_name):
                inc_file_name = os.path.join(base_dir, inc_file_name)
            inc_model = _read_conf_file(inc_file_name, xvars, included)
            model.include(inc_model)
    included.remove(file_path)

    return model


def xeet_conf(file_path: str, xvars: XeetVars) -> _XeetConf:
    if not file_path:
        for file in ("xeet.yaml", "xeet.yml", "xeet.json"):
            if os.path.exists(file):
                file_path = file
                break
        if not file_path:
            raise XeetConfigException("Empty configuration file path")

    model = _read_conf_file(file_path, xvars)

    ret = _XeetConf(file_path, model)
    return ret
