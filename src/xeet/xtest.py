from xeet import LogLevel
from xeet.common import (XeetException, XeetVars, NonEmptyStr, global_vars, pydantic_errmsg,
                         yes_no_str)
from xeet.log import log_info, log_raw, log_verbose
from xeet.pr import create_print_func, pr_info
from xeet.xstep import XStep, XeetStepInitException, XStepTestArgs, run_xstep_list, XStepListResult
from xeet.steps import get_xstep_class
from xeet.globals import get_named_step
from typing import Any
from pydantic import BaseModel, Field, ValidationError, ConfigDict, AliasChoices, model_validator
from enum import auto, Enum
from dataclasses import dataclass, field
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
    timeout_period: float | None = None
    pre_run_res: XStepListResult = field(default_factory=XStepListResult)
    run_res: XStepListResult = field(default_factory=XStepListResult)
    post_run_res: XStepListResult = field(default_factory=XStepListResult)


_EMPTY_STR = ""


class StepsInheritType(str, Enum):
    Prepend = "prepend"
    Append = "append"
    Replace = "replace"


class XtestModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: NonEmptyStr
    base: str = _EMPTY_STR
    abstract: bool = False
    short_desc: str = Field(_EMPTY_STR, max_length=75)
    long_desc: str = _EMPTY_STR
    groups: list[NonEmptyStr] | None = None
    #  None means inherit from parent
    pre_run: list[Any] | None = None
    run: list[Any] | None = None
    post_run: list[Any] | None = None

    expected_failure: bool | None = None
    skip: bool | None = None
    skip_reason: str | None = None
    var_map: dict[str, Any] | None = Field(
        None, validation_alias=AliasChoices("var_map", "variables", "vars"))

    # Inheritance behavior
    inherit_variables: bool = True
    pre_test_inheritance: StepsInheritType = StepsInheritType.Replace
    test_steps_inheritance: StepsInheritType = StepsInheritType.Replace
    post_test_inheritance: StepsInheritType = StepsInheritType.Replace

    def inherit(self, other: "XtestModel") -> None:
        if self.inherit_variables and other.var_map:
            if self.var_map:
                self.var_map = {**other.var_map, **self.var_map}
            else:
                self.var_map = {**other.var_map}

    @model_validator(mode='after')
    def post_validate(self) -> "XtestModel":
        if self.abstract and self.groups:
            raise ValueError("Abstract tests can't have groups")
        return self


class Xtest:
    def __init__(self, desc: dict, output_base_dir: str, xeet_root: str):
        self.name: str = desc.get("name")  # type: ignore
        if not isinstance(self.name, str):
            self.init_err = "Bad name type"
            self.name = "<unknown>"
            return
        if not self.name:
            self.init_err = "No name"
            self.name = "<unknown>"
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

        self.base = self.model.base
        self.xeet_root = xeet_root
        self.init_err = _EMPTY_STR
        args = XStepTestArgs(
            log_info=self._log_info, debug_mode=self.debug_mode, output_dir=self.output_dir)
        self.pre_run_steps = self._init_step_list(self.model.pre_run, args, "pre")
        if self.init_err:
            return
        self.run_steps = self._init_step_list(self.model.run, args, "test")
        if self.init_err:
            return
        self.post_run_steps = self._init_step_list(self.model.post_run, args, "post")

    def _init_step_list(self, step_list: list[dict] | None, args: XStepTestArgs, prefix: str
                        ) -> list[XStep] | None:
        if step_list is None:
            return None
        args.stage_prefix = prefix
        steps = []
        try:
            for index, step_desc in enumerate(step_list):
                args.index = index
                steps.append(_gen_xstep(step_desc, args))
            return steps
        except XeetStepInitException as e:
            self.init_err = str(e)
            return None

    def inherit(self, other: "Xtest") -> None:
        def _inherit_steps(self_steps, other_steps, inherit_method):
            if self_steps is None:
                return other_steps
            if other_steps is None or inherit_method == StepsInheritType.Replace:
                return self_steps

            if inherit_method == StepsInheritType.Append:
                ret = other_steps + self_steps
            else:
                ret = self_steps + other_steps

            for i, step in enumerate(ret):
                step.index = i
            return ret
        if other.init_err:
            self.init_err = other.init_err
            return

        self.model.inherit(other.model)
        self.pre_run_steps = _inherit_steps(self.pre_run_steps, other.pre_run_steps,
                                            self.model.pre_test_inheritance)
        self.run_steps = _inherit_steps(self.run_steps, other.run_steps,
                                        self.model.test_steps_inheritance)
        self.post_run_steps = _inherit_steps(self.post_run_steps, other.post_run_steps,
                                             self.model.post_test_inheritance)

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
        xvars = XeetVars(self.model.var_map, global_vars())
        xvars.set_vars({
            "XEET_TEST_NAME": self.name,
            "XEET_TEST_OUTDIR": self.output_dir,
        })

        self._log_info(f"Auto variables:")
        for k, v in xvars.vars_map.items():
            log_raw(f"{k}={v}")
        self._log_info(f"Expanding '{self.name}' internals")

        try:
            for steps in (self.pre_run_steps, self.run_steps, self.post_run_steps):
                if steps is None:
                    continue
                for step in steps:
                    step.setup(xvars)
        except XeetException as e:
            self.init_err = str(e)
            return

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
        if not self.run_steps:
            self._log_info("No command for test, will not run")
            res.status = TestStatus.RunErr
            res.status_reason = "No command"
            return res

        if self.abstract:
            raise XeetRunException("Can't run abstract tasks")

        self._log_info("starting run")
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
        if not self.pre_run_steps:
            self._log_info("No pre-test steps")
            return
        self._log_info("Running pre-test steps")
        run_xstep_list(self.pre_run_steps, res.pre_run_res, stop_on_err=True)
        if not res.pre_run_res.completed or res.pre_run_res.failed:
            self._log_info(f"Pre-test failed or didn't complete")
            res.status = TestStatus.PreRunErr
            res.status_reason = res.pre_run_res.error_summary()
            return

    def _run(self, res: TestResult) -> None:
        if res.status != TestStatus.Undefined:
            self._log_info("Skipping run. Prior stage failed")
            return
        self._log_info("Running test steps")
        run_xstep_list(self.run_steps, res.run_res, stop_on_err=True)
        if not res.run_res.completed:
            self._log_info("Test didn't complete")
            res.status = TestStatus.RunErr
            res.status_reason = res.run_res.error_summary()
            return
        if res.run_res.failed:
            self._log_info(f"Test failed (expected: {yes_no_str(self.expected_failure)})")
            if self.expected_failure:
                res.status = TestStatus.ExpectedFail
            else:
                res.status = TestStatus.Failed
                res.status_reason = res.run_res.error_summary()
            return
        if self.expected_failure:
            self._log_info("Unexpected pass")
            res.status = TestStatus.UnexpectedPass
            return
        res.status = TestStatus.Passed

    def _post_test(self, res: TestResult) -> None:
        if not self.post_run_steps:
            self._log_info("Skipping post-test, no steps")
            return
        self._log_info(f"Running post-test steps")
        run_xstep_list(self.post_run_steps, res.post_run_res, stop_on_err=False)
        #  self._debug_pre_step_print("Post-test", self.post_cmd_expanded, self.post_cmd_shell)
        if not res.post_run_res.completed or res.post_run_res.failed:
            err = res.post_run_res.error_summary()
            log_info(f"Post test run failed - {err}")
            #  res.post_test_err = str(err)

    def _log_info(self, msg, *args, **kwargs) -> None:
        log_info(f"{self.name}: {msg}", *args, depth=1, **kwargs)


def _gen_xstep(desc: dict, args: XStepTestArgs, included: set[str] | None = None) -> XStep:
    if included is None:
        included = set()
    model_type = desc.get("type")
    if not model_type:
        raise XeetStepInitException("Step type not specified", "", args)
    xstep_class = get_xstep_class(model_type)
    if xstep_class is None:
        raise XeetStepInitException(f"Unknown step type '{model_type}'", model_type, args)
    xstep_model_class = xstep_class.model_class()
    try:
        xstep_model = xstep_model_class(**desc)
    except ValidationError as e:
        raise XeetStepInitException(f"{pydantic_errmsg(e)}", model_type, args)
    base = desc.get("base")
    if base in included:
        raise XeetStepInitException(f"Include loop detected - '{base}'", model_type, args)
    if base:
        base_desc = get_named_step(base)
        if not base_desc:
            raise XeetStepInitException(f"Base step '{base}' not found", model_type, args)
        base_step = _gen_xstep(base_desc, args, included)
        args.parent = base_step
    else:
        args.parent = None
    ret = xstep_class(xstep_model, args=args)

    return ret
