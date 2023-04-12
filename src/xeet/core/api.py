from . import XeetSettings
from . import TestsCriteria
from .test import Test, TestModel
from .result import RunResult
from .conf import XeetConfModel
from .driver import xeet_driver, XeetRunSettings
from xeet import XeetException
from enum import Enum


def fetch_tests(config_path: str, criteria: TestsCriteria, setup: bool = False,
                init_phases: bool = False) -> list[Test]:
    return xeet_driver(XeetSettings(config_path)).fetch_tests(criteria, setup, init_phases)


def fetch_groups(config_path: str) -> list[str]:
    return list(xeet_driver(XeetSettings(config_path)).all_groups)


def fetch_test_desc(config_path: str, name: str) -> dict | None:
    return xeet_driver(XeetSettings(config_path)).conf.test_desc(name)


def fetch_config(config_path: str) -> dict:
    return xeet_driver(XeetSettings(config_path)).rti.defs_dict


class SchemaType(str, Enum):
    CONFIG = "config"
    XTEST = "test"
    UNIFIED = "unified"


def fetch_schema(schema_type: str) -> dict:
    if schema_type == SchemaType.CONFIG.value:
        return XeetConfModel.model_json_schema(mode='serialization')
    if schema_type == SchemaType.XTEST.value:
        return TestModel.model_json_schema(mode='serialization')
    if schema_type == SchemaType.UNIFIED.value:
        d = XeetConfModel.model_json_schema(mode='serialization')
        d["properties"]["tests"]["items"] = TestModel.model_json_schema(mode='serialization')
        return d
    raise XeetException(f"Invalid dump type: {schema_type}")


def run_tests(settings: XeetSettings, run_settings: XeetRunSettings) -> RunResult:
    return xeet_driver(settings).run(run_settings)
