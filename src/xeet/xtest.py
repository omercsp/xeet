from xeet import LogLevel
from xeet.common import XeetException, XeetVars, NonEmptyStr, pydantic_errmsg
from xeet.log import log_info, log_raw, log_error, log_verbose
from xeet.pr import create_print_func, pr_info
from xeet.xstep import (XStep, XeetStepInitException, XtestStepTestSettings, xstep_factory,
                        run_xstep_list, XStepListResult)
from typing import Any
from pydantic import BaseModel, Field, ValidationError, ConfigDict, AliasChoices
from typing import ClassVar
from enum import auto, Enum
from dataclasses import dataclass
import os
import sys


_ORANGE = '\033[38;5;208m'
_pr_orange = create_print_func(_ORANGE, LogLevel.ALWAYS)


class XeetRunException(XeetException):
    ...


class TestStatusCategory(str, Enum):
    Undefined = "Undefined"
    Skipped = "Skipped"
    NotRun = "Not run"
    Failed = "Failed"
    Passed = "Passed"
    Unknown = "Unknown"


class TestStatus(Enum):
    Undefined = auto()
    Skipped = auto()
    InitErr = auto()
    PreRunErr = auto()
    RunErr = auto()  # This isn't a test failure per se, but a failure to run the test
    Failed = auto()
    UnexpectedPass = auto()
    Passed = auto()
    ExpectedFail = auto()


_NOT_RUN_STTS = {TestStatus.InitErr, TestStatus.PreRunErr, TestStatus.RunErr}
_FAILED_STTS = {TestStatus.Failed, TestStatus.UnexpectedPass}
_PASSED_STTS = {TestStatus.Passed, TestStatus.ExpectedFail}


def status_catgoery(status: TestStatus) -> TestStatusCategory:
    if status == TestStatus.Undefined:
        return TestStatusCategory.Undefined
    if status == TestStatus.Skipped:
        return TestStatusCategory.Skipped
    if status in _NOT_RUN_STTS:
        return TestStatusCategory.NotRun
    if status in _FAILED_STTS:
        return TestStatusCategory.Failed
    if status in _PASSED_STTS:
        return TestStatusCategory.Passed
    return TestStatusCategory.Unknown


@dataclass
class TestResult:
    status: TestStatus = TestStatus.Undefined
    duration: float = 0
    status_reason: str = ""
    post_test_err: str = ""
    timeout_period: float | None = None
    pre_steps_res: XStepListResult | None = None
    steps_res: XStepListResult | None = None
    post_steps_res: XStepListResult | None = None


_EMPTY_STR = ""


class XtestModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: NonEmptyStr
    base: str = _EMPTY_STR
    abstract: bool = False
    short_desc: str = Field(_EMPTY_STR, max_length=75)
    long_desc: str = _EMPTY_STR
    groups: list[NonEmptyStr] | None = None
    pre_steps: list[Any] = Field(default_factory=list, validation_alias="pre_test")
    test_steps: list[Any] = Field(default_factory=list, validation_alias="test")
    post_steps: list[Any] = Field(default_factory=list, validation_alias="post_test")

    expected_failure: bool | None = None
    skip: bool | None = None
    skip_reason: str | None = None
    var_map: dict[str, str] | None = Field(
        None, validation_alias=AliasChoices("var_map", "variables", "vars"))

    # Inheritance behavior
    inherit_variables: bool = True
    inherit_env_variables: bool = True
    inhertit_ignore_fields: ClassVar[set[str]] = {"model_config", "name", "base", "abstract",
                                                  "short_desc", "long_desc", "env", "var_map"}

    def inherit(self, other: "XtestModel") -> None:
        for f in self.model_fields.keys():
            if f in self.inhertit_ignore_fields or f.startswith("inherit_"):
                continue
            val = getattr(self, f)
            if val is not None:
                continue
            other_val = getattr(other, f)
            if other_val is not None:
                setattr(self, f, other_val)

        if self.inherit_variables and other.var_map:
            if self.var_map:
                self.var_map = {**other.var_map, **self.var_map}
            else:
                self.var_map = {**other.var_map}

        if self.inherit_env_variables and other.env:
            if self.env:
                self.env = {**other.env, **self.env}
            else:
                self.env = {**other.env}


class Xtest:
    def __init__(self, desc: dict, output_base_dir: str, xeet_root: str,
                 dflt_shell_path: str | None):
        self.name = desc.get("name", "<no name>").strip()
        if not self.name:
            self.init_err = "No name"
            return
        try:
            self.model = XtestModel(**desc)
        except ValidationError as e:
            self.init_err = f"Error parsing test '{self.name}' - {pydantic_errmsg(e)}"
            return
        self._log_info(f"initializing test {self.name}")
        self.output_dir = f"{output_base_dir}/{self.name}"
        self._log_info(f"Test output dir: {self.output_dir}")
        self.debug_mode = False
        #  if not self.shell_path and dflt_shell_path:
        #      self.shell_path = dflt_shell_path

        self.base = self.model.base
        self.xeet_root = xeet_root
        self.init_err = _EMPTY_STR

        #  if not self.shell_path and dflt_shell_path:
        #      self.shell_path = dflt_shell_path
        #  if not self.shell_path:
        #      self.shell_path = os.getenv("SHELL", "/usr/bin/sh")
        common_xstep_settings = XtestStepTestSettings(
            log_info=self._log_info, debug_mode=self.debug_mode, output_dir=self.output_dir)
        self.pre_steps = self._init_step_list(self.model.pre_steps, "pre", common_xstep_settings)
        if self.init_err:
            return
        self.test_steps = self._init_step_list(self.model.test_steps, "test", common_xstep_settings)
        if self.init_err:
            return
        self.post_steps = self._init_step_list(self.model.post_steps, "post", common_xstep_settings)

    def _init_step_list(self, step_list: list[dict], step_prefix: str,
                        step_setitings: XtestStepTestSettings) -> list[XStep]:
        if not step_list:
            return []
        steps = []
        try:
            for index, step_desc in enumerate(step_list):
                steps.append(xstep_factory(step_desc, step_setitings, index, step_prefix))
            return steps
        except XeetStepInitException as e:
            self.init_err = str(e)
            return []

    def inherit(self, other: "Xtest") -> None:
        if other.init_err:
            self.init_err = other.init_err
            return
        self.model.inherit(other.model)

    @staticmethod
    def _setting_val(value: Any, dflt: Any) -> Any:
        if value is None:
            return dflt
        if isinstance(value, str):
            return value.strip()
        return value

    @property
    def skip(self) -> bool:
        return self._setting_val(self.model.skip, False)

    @property
    def skip_reason(self) -> str:
        return self._setting_val(self.model.skip_reason, _EMPTY_STR)

    @property
    def expected_failure(self) -> bool:
        return self._setting_val(self.model.expected_failure, False)

    @property
    def short_desc(self) -> str:
        return self.model.short_desc.strip()

    @property
    def long_desc(self) -> str:
        return self.model.long_desc.strip()

    @property
    def var_map(self) -> dict[str, str]:
        return self._setting_val(self.model.var_map, dict())

    @property
    def inherit_variables(self) -> bool:
        return self.model.inherit_variables

    @property
    def abstract(self) -> bool:
        return self.model.abstract

    @property
    def groups(self) -> set[str]:
        if not self.model.groups:
            return set()
        return {g.root.strip() for g in self.model.groups}

    def expand(self) -> None:
        xvars = XeetVars(self.model.var_map)
        xvars.set_vars({
            "TEST_NAME": self.name,
            "TEST_OUTDIR": self.output_dir,
        }, system=True)
        self._log_info(f"Auto variables:")
        for k, v in xvars.vars_map.items():
            log_raw(f"{k}={v}")
        self._log_info(f"Expanding '{self.name}' internals")
        #  self.env_expanded = {xvars.expand(k): xvars.expand(v) for k, v in self.env.items()}
        try:
            for step in self.pre_steps:
                step.expand(xvars)
            for step in self.test_steps:
                step.expand(xvars)
            for step in self.post_steps:
                step.expand(xvars)
        except XeetException as e:
            self.init_err = str(e)
            return

        #  if self.env_file:
        #      self.env_file_expanded = xvars.expand(self.env_file)
        #  for k, v in self.env.items():
        #      name = k.strip()
        #      if not name:
        #          continue
        #      self.env_expanded[k] = xvars.expand(v)

    def _mkdir_output_dir(self) -> None:
        self._log_info(f"setting up output directory '{self.output_dir}'")
        if os.path.isdir(self.output_dir):
            # Clear the output director
            for f in os.listdir(self.output_dir):
                try:
                    os.remove(os.path.join(self.output_dir, f))
                except OSError as e:
                    raise XeetRunException(f"Error removing file '{f}' - {e.strerror}")
        else:
            try:
                log_verbose("Creating output directory if it doesn't exist: '{}'", self.output_dir)
                os.makedirs(self.output_dir, exist_ok=False)
            except OSError as e:
                raise XeetRunException(f"Error creating output directory - {e.strerror}")

    def run(self) -> TestResult:
        res = TestResult()
        if self.init_err:
            res.status = TestStatus.InitErr
            res.status_reason = self.init_err
            return res
        if self.skip:
            res.status = TestStatus.Skipped
            res.status_reason = self.skip_reason
            self._log_info("marked to be skipped")
            return res
        if not self.test_steps:
            self._log_info("No command for test, will not run")
            res.status = TestStatus.RunErr
            res.status_reason = "No command"
            return res

        if self.abstract:
            raise XeetRunException("Can't run abstract tasks")

        self._log_info("starting run")
        #  if self.cwd_expanded:
        #      self._log_info(f"working directory will be set to '{self.cwd_expanded}'")
        #  else:
        #      self._log_info("using default working directory")
        #  if self.env:
        #      self._log_info("command environment variables:")
        #      for k, v in self.env_expanded.items():
        #          log_raw(f"{k}={v}")

        #  try:
        #      env = self._read_env_vars()
        #  except XeetRunException as e:
        #      res.status = TestStatus.RunErr
        #      res.status_reason = str(e)
        #      return res

        self._mkdir_output_dir()
        self._pre_test(res)
        self._run(res)
        self._post_test(res)

        if res.status == TestStatus.Passed or res.status == TestStatus.ExpectedFail:
            self._log_info("completed successfully")
        return res

    def _debug_pre_step_print(self, step_name: str, command, shell: bool) -> None:
        if not self.debug_mode:
            return
        shell_str = " (shell)" if shell else ""
        _pr_orange(f">>>>>>> {step_name} <<<<<<<\nCommand{shell_str}:")
        pr_info(command)
        _pr_orange("Execution output:")
        sys.stdout.flush()  # to make sure colors are reset

    def _debug_step_print(self, step_name: str, rc: int) -> None:
        if not self.debug_mode:
            return
        _pr_orange(f"{step_name} rc: {rc}\n")

    def _pre_test(self, res: TestResult) -> None:
        if not self.pre_steps:
            self._log_info("No pre-test steps")
            return
        self._log_info("Running pre-test steps")
        res.pre_steps_res = run_xstep_list(self.pre_steps, stop_on_err=True)
        if not res.pre_steps_res.completed or res.pre_steps_res.failed:
            self._log_info(f"Pre-test failed or didn't complete")
            res.status = TestStatus.PreRunErr
            res.status_reason = res.pre_steps_res.error_summary()
            return

    def _run(self, res: TestResult) -> None:
        if res.status != TestStatus.Undefined:
            self._log_info("Skipping run. Prior stage failed")
            return
        self._log_info("Running test steps")
        res.steps_res = run_xstep_list(self.test_steps, stop_on_err=True)
        if not res.steps_res.completed:
            res.status = TestStatus.RunErr
            res.status_reason = res.steps_res.error_summary()
            return
        if res.steps_res.failed:
            res.status = TestStatus.Failed
            res.status_reason = res.steps_res.error_summary()
            return
        res.status = TestStatus.Passed

    def _post_test(self, res: TestResult) -> None:
        if not self.post_steps:
            self._log_info("Skipping post-test, no steps")
            return
        self._log_info(f"Running post-test steps")
        res.post_steps_res = run_xstep_list(self.post_steps, stop_on_err=False)
        #  self._debug_pre_step_print("Post-test", self.post_cmd_expanded, self.post_cmd_shell)
        if not res.post_steps_res.completed or res.post_steps_res.failed:
            err = res.post_steps_res.error_summary()
            log_error(f"Post test run failed - {err}")
            res.post_test_err = str(err)

    def _log_info(self, msg: str, *args, **kwargs) -> None:
        log_info(f"{self.name}: {msg}", *args, depth=1, **kwargs)
