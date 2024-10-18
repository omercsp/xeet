from xeet.xtest import Xtest, XtestModel, TestStatus, TestResult, status_catgoery
from xeet.config import Config, ConfigModel, read_config_file, TestCriteria
from xeet.common import XeetException, update_global_vars, text_file_tail
from xeet.log import log_info, log_blank, start_raw_logging, stop_raw_logging
from xeet.runtime import RunInfo
from enum import Enum
import os
import sys


def fetch_xtest(config_path: str, name: str) -> Xtest | None:
    return read_config_file(config_path).xtest(name)


def fetch_tests_list(config_path: str, criteria: TestCriteria) -> list[Xtest]:
    return read_config_file(config_path).xtests(criteria)


def fetch_groups_list(config_path: str) -> list[str]:
    config = read_config_file(config_path)
    return list(config.all_groups())


def fetch_test_desc(config_path: str, name: str) -> dict | None:
    return read_config_file(config_path).test_desc(name)


class SchemaType(str, Enum):
    CONFIG = "config"
    XTEST = "test"
    UNIFIED = "unified"


def fetch_schema(schema_type: str) -> dict:
    if schema_type == SchemaType.CONFIG.value:
        return ConfigModel.model_json_schema()
    if schema_type == SchemaType.XTEST.value:
        return XtestModel.model_json_schema()
    if schema_type == SchemaType.UNIFIED.value:
        d = ConfigModel.model_json_schema()
        d["properties"]["tests"]["items"] = XtestModel.model_json_schema()
        return d
    raise XeetException(f"Invalid dump type: {schema_type}")


# TODO: remove from actions.py
#  @dataclass
#  class RunSettings:
#      iterations: int
#      debug_mode: bool
#      show_summary: bool
#      criteria: TestCriteria


#  def run_tests(config_path: str, run_settings: RunSettings) -> RunInfo:
#      ...
