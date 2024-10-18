from dataclasses import dataclass
from xeet.xtest import Xtest, XtestModel, TestStatus, TestResult, status_catgoery
from xeet.config import Config, ConfigModel, read_config_file, TestCriteria
from xeet.common import XeetException, update_global_vars, text_file_tail
from xeet.log import log_info, log_blank, start_raw_logging, stop_raw_logging
from xeet.runtime import RunInfo
import os
import sys

class TestInfo:
    def __init__(self, xtest: Xtest) -> None:
        self.name = xtest.name
        self.groups = xtest.groups


def fetch_test_info(config_path: str, name: str) -> TestInfo:
    ...

def fetch_tests_list(config_path: str, criteria: TestCriteria) -> list[TestInfo]:
    ...

def fetch_test_list_names_only(config_path: str, criteria: TestCriteria) -> list[str]:
    ...

def fetch_groups_list(config_path: str) -> list[str]:
    ...

def fetch_test_desc(config_path: str, name: str) -> dict:
    ...

def fetch_config(config_path: str) -> Config:
    ...


# TODO: remove from actions.py
@dataclass
class RunSettings:
    iterations: int
    debug_mode: bool
    show_summary: bool
    criteria: TestCriteria


def run_tests(config_path: str, run_settings: RunSettings) -> RunInfo:
    ...
