from . import BaseXeetSettings
from . import TestsCriteria
from .test import Test, TestModel
from .result import RunResult
from .xeet_conf import XeetModel, xeet_conf
from .tests_runner import XeetRunner, XeetRunSettings, is_empty_run_result as is_empty_run_result
from xeet import XeetException
from enum import Enum


def fetch_tests_list(config_path: str, criteria: TestsCriteria) -> list[Test]:
    return xeet_conf(BaseXeetSettings(config_path)).get_tests(criteria)


def fetch_groups_list(config_path: str) -> list[str]:
    config = xeet_conf(BaseXeetSettings(config_path))
    return list(config.all_groups())


def fetch_test_desc(config_path: str, name: str) -> dict | None:
    return xeet_conf(BaseXeetSettings(config_path)).test_desc(name)


def fetch_config(config_path: str) -> dict:
    return xeet_conf(BaseXeetSettings(config_path)).rti.defs_dict


class SchemaType(str, Enum):
    CONFIG = "config"
    XTEST = "test"
    UNIFIED = "unified"


def fetch_schema(schema_type: str) -> dict:
    if schema_type == SchemaType.CONFIG.value:
        return XeetModel.model_json_schema()
    if schema_type == SchemaType.XTEST.value:
        return TestModel.model_json_schema()
    if schema_type == SchemaType.UNIFIED.value:
        d = XeetModel.model_json_schema()
        d["properties"]["tests"]["items"] = TestModel.model_json_schema()
        return d
    raise XeetException(f"Invalid dump type: {schema_type}")


def run_tests(run_settings: XeetRunSettings) -> RunResult:
    return XeetRunner(run_settings).run()
