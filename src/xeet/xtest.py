from xeet import XeetDefs
from xeet.common import (XeetException, XeetVars, NonEmptyStr, pydantic_errmsg, yes_no_str,
                         KeysBaseModel)
from xeet.log import log_info, log_verbose, log_warn
from xeet.xstep import XStep, XStepModel, XeetStepInitException, XStepResult
from xeet.steps import get_xstep_class
from typing import Any
from pydantic import Field, ValidationError, ConfigDict, AliasChoices, model_validator
from enum import auto, Enum
from dataclasses import dataclass, field
import os


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
class XStepListResult:
    prefix: str = ""
    results: list[XStepResult] = field(default_factory=list)
    completed: bool = True
    failed: bool = False

    def error_summary(self) -> str:
        for i, r in enumerate(self.results):
            if not r.completed or r.failed:
                return f"{self.prefix} step #{i}: {r.error_summary()}"
        return ""

    #  post_init is called after the dataclass is initialized. This is used
    #  in unittesting only. By default, results is empty, so completed and failed
    #  are True and False, respectively.
    def __post_init__(self) -> None:
        if not self.results:
            return
        self.completed = all([r.completed for r in self.results])
        self.failed = any([r.failed for r in self.results])


@dataclass
class TestResult:
    status: TestStatus = TestStatus.Undefined
    duration: float = 0
    status_reason: str = ""
    pre_run_res: XStepListResult = field(default_factory=lambda: XStepListResult(prefix="Pre-run"))
    run_res: XStepListResult = field(default_factory=lambda: XStepListResult(prefix="Run"))
    post_run_res: XStepListResult = field(
        default_factory=lambda: XStepListResult(prefix="Post-run"))


_EMPTY_STR = ""


class StepsInheritType(str, Enum):
    Prepend = "prepend"
    Append = "append"
    Replace = "replace"


class XtestModel(KeysBaseModel):
    model_config = ConfigDict(extra='forbid')
    name: NonEmptyStr
    base: str = _EMPTY_STR
    abstract: bool = False
    short_desc: str = Field(_EMPTY_STR, max_length=75)
    long_desc: str = _EMPTY_STR
    groups: list[str] = Field(default_factory=list)
    #  None means inherit from parent
    pre_run: list[Any] = Field(default_factory=list)
    run: list[Any] = Field(default_factory=list)
    post_run: list[Any] = Field(default_factory=list)

    expected_failure: bool = False
    skip: bool = False
    skip_reason: str = _EMPTY_STR
    var_map: dict[str, Any] = Field(default_factory=dict,
                                    validation_alias=AliasChoices("var_map", "variables", "vars"))

    # Inheritance behavior
    inherit_variables: bool = True
    pre_run_inheritance: StepsInheritType = StepsInheritType.Replace
    run_inheritance: StepsInheritType = StepsInheritType.Replace
    post_run_inheritance: StepsInheritType = StepsInheritType.Replace

    # Internals
    error: str = Field(_EMPTY_STR, exclude=True)

    @model_validator(mode='after')
    def post_validate(self) -> "XtestModel":
        if self.abstract and self.groups:
            raise ValueError("Abstract tests can't have groups")

        groups = []
        for g in self.groups:
            g = g.strip()
            if not g:
                continue
            groups.append(g)
        self.groups = groups
        return self

    def inherit(self, other: "XtestModel") -> None:
        if self.inherit_variables and other.has_key("var_map"):
            if self.var_map:
                self.var_map = {**other.var_map, **self.var_map}
            else:
                self.var_map = {**other.var_map}

        def _inherit_steps(steps_key: str, inherit_method: str) -> list:
            self_steps = getattr(self, steps_key)
            if not other.has_key(steps_key) or \
                    (self.has_key(steps_key) and inherit_method == StepsInheritType.Replace):
                return self_steps
            other_steps = getattr(other, steps_key)

            if inherit_method == StepsInheritType.Append:
                ret = other_steps + self_steps
            else:
                ret = self_steps + other_steps
            if ret:
                self.field_keys.add(steps_key)
            return ret

        if other.error:
            self.error = other.error
            return

        self.pre_run = _inherit_steps("pre_run", self.pre_run_inheritance)
        self.run = _inherit_steps("run", self.run_inheritance)
        self.post_run = _inherit_steps("post_run", self.post_run_inheritance)


@dataclass
class _XStepList:
    name: str
    stop_on_err: bool
    steps: list[XStep] = field(default_factory=list)
    on_fail_status: TestStatus = TestStatus.Undefined
    on_run_err_status: TestStatus = TestStatus.Undefined


class Xtest:
    def __init__(self, model: XtestModel, xdefs: XeetDefs) -> None:
        self.model = model
        self.xdefs = xdefs
        self.name: str = model.name.root
        if model.error:
            self.error = model.error
            return
        self._log_info(f"initializing test {self.name}")
        self.output_dir = f"{xdefs.output_dir}/{self.name}"
        self._log_info(f"Test output dir: {self.output_dir}")

        self.base = self.model.base
        self.error = _EMPTY_STR
        self.pre_run_steps = self._init_step_list(self.model.pre_run, "pre", True)
        if self.error:
            return
        self.run_steps = self._init_step_list(self.model.run, "main", True)
        if self.error:
            return
        self.post_run_steps = self._init_step_list(self.model.post_run, "post", False)
        if self.error:
            return

        self.xvars = XeetVars(model.var_map, xdefs.xvars)
        self.xvars.set_vars({
            "NAME": self.name,
            "OUT_DIR": self.output_dir,
        }, prefix="XT_")

    def _init_step_list(self, step_list: list[dict] | None, name: str, stop_on_err: bool
                        ) -> _XStepList:
        ret = _XStepList(name=name, stop_on_err=stop_on_err)
        if step_list is None:
            return ret
        id_base = self.name
        if name:
            id_base += f"_{name}"
            name = f" {name}"
        for index, step_desc in enumerate(step_list):
            try:
                self._log_info(f"initializing{name} step {index}")
                step_model = self._gen_xstep_model(step_desc)
                step_class = get_xstep_class(step_model.step_type)
                if step_class is None:  # Shouldn't happen
                    raise XeetStepInitException(f"Unknown step type '{step_model.step_type}'")
                step = step_class(step_model, self.xdefs, f"{id_base}_{index}")
                ret.steps.append(step)
            except XeetStepInitException as e:
                self._log_warn(f"Error initializing{name}step {index}: {e}")
                self.error = f"Error initializing{name}step {index}: {e}"
        return ret

    @property
    def debug_mode(self) -> bool:
        return self.xdefs.debug_mode

    def setup(self) -> None:
        self._log_info("Pre execution setup")
        step_xvars = XeetVars(parent=self.xvars)

        try:
            for steps in (self.pre_run_steps, self.run_steps,
                          self.post_run_steps):
                self.xdefs.reporter.phase_name = steps.name
                if steps is None:
                    continue
                for index, step in enumerate(steps.steps):
                    self.xdefs.reporter.on_step_setup_start(step, index)
                    step.setup(step_xvars)
                    self.xdefs.reporter.on_step_setup_end()
                    step_xvars.reset()
        except XeetException as e:
            self.error = str(e)
            self._log_info(f"Error setting up test - {e}")
        self.xdefs.reporter.phase_name = ""

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
        if self.error:
            res.status = TestStatus.InitErr
            res.status_reason = self.error
            return res
        if self.model.skip:
            res.status = TestStatus.Skipped
            res.status_reason = self.model.skip_reason
            self._log_info("marked to be skipped")
            return res
        if not self.run_steps:
            self._log_info("No command for test, will not run")
            res.status = TestStatus.RunErr
            res.status_reason = "No command"
            return res

        if self.model.abstract:
            raise XeetRunException("Can't run abstract tasks")

        self._log_info("starting run")
        self._mkdir_output_dir()
        self._phase_wrapper(self.pre_run_steps, res, self._pre_test)
        self._phase_wrapper(self.run_steps, res, self._run)
        self._phase_wrapper(self.post_run_steps, res, self._post_test)

        if res.status == TestStatus.Passed or res.status == TestStatus.ExpectedFail:
            self._log_info("completed successfully")
        return res

    def _pre_test(self, res: TestResult) -> None:
        if not self.pre_run_steps.steps:
            self._log_info("No pre-test steps")
            return
        self._log_info("Running pre-test steps")
        self._run_xstep_list(self.pre_run_steps, res.pre_run_res)
        if not res.pre_run_res.completed or res.pre_run_res.failed:
            self._log_info(f"Pre-test failed or didn't complete")
            res.status = TestStatus.PreRunErr
            res.status_reason = res.pre_run_res.error_summary()
            return

    def _phase_wrapper(self, step_list: _XStepList, res: TestResult, func) -> None:
        self.xdefs.reporter.on_phase_start(step_list.name, len(step_list.steps))
        func(res)
        self.xdefs.reporter.on_phase_end()

    def _run(self, res: TestResult) -> None:
        if res.status != TestStatus.Undefined:
            self._log_info("Skipping run. Prior stage failed")
            return
        self._log_info("Running test steps")
        self._run_xstep_list(self.run_steps, res.run_res)
        if not res.run_res.completed:
            self._log_info("Test didn't complete")
            res.status = TestStatus.RunErr
            res.status_reason = res.run_res.error_summary()
            return
        if res.run_res.failed:
            self._log_info(f"Test failed (expected: {yes_no_str(self.model.expected_failure)})")
            if self.model.expected_failure:
                res.status = TestStatus.ExpectedFail
            else:
                res.status = TestStatus.Failed
                res.status_reason = res.run_res.error_summary()
            return
        if self.model.expected_failure:
            self._log_info("Unexpected pass")
            res.status = TestStatus.UnexpectedPass
            return
        res.status = TestStatus.Passed

    def _post_test(self, res: TestResult) -> None:
        if not self.post_run_steps.steps:
            self._log_info("Skipping post-test, no steps")
            return
        self._log_info(f"Running post-test steps")
        self._run_xstep_list(self.post_run_steps, res.post_run_res)
        if not res.post_run_res.completed or res.post_run_res.failed:
            err = res.post_run_res.error_summary()
            self._log_info(f"Post test run failed - {err}")
            #  res.post_test_err = str(err)

    def _run_xstep_list(self, step_list: _XStepList, res: XStepListResult) -> None:
        if not step_list.steps:
            return
        reporter = self.xdefs.reporter

        for index, step in enumerate(step_list.steps):
            reporter.on_step_start(step, index)
            step_res = step.run()
            reporter.on_step_end(step_res)
            res.results.append(step_res)
            if not step_res.completed:
                res.completed = False
            if step_res.failed:
                res.failed = True
            if step_list.stop_on_err and (step_res.failed or not step_res.completed):
                break

    def _log_info(self, msg, *args, **kwargs) -> None:
        log_info(f"{self.name}: {msg}", *args, depth=1, **kwargs)

    def _log_warn(self, msg, *args, **kwargs) -> None:
        log_warn(f"{self.name}: {msg}", *args, depth=1, **kwargs)

    _DFLT_STEP_TYPE_PATH = "settings.xeet.default_step_type"

    def _gen_xstep_model(self, desc: dict, included: set[str] | None = None) -> XStepModel:
        if included is None:
            included = set()
        base = desc.get("base")
        if base in included:
            raise XeetStepInitException(f"Include loop detected - '{base}'")

        base_step = None
        base_type = None
        if base:
            self._log_info(f"base step '{base}' found")
            #  TODO: add refernce by name in addition to path
            base_desc, found = self.xdefs.config_ref(base)
            if not found:
                raise XeetStepInitException(f"Base step '{base}' not found")
            if not isinstance(base_desc, dict):
                raise XeetStepInitException(f"Invalid base step '{base}'")
            base_step = self._gen_xstep_model(base_desc, included)
            base_type = base_step.step_type

        model_type = desc.get("type")
        if model_type:
            if base_type and model_type != base_type:
                raise XeetStepInitException(
                    f"Step type '{model_type}' doesn't match base type '{base_type}'")
        else:
            if not base_type:
                base_type, found = self.xdefs.config_ref(self._DFLT_STEP_TYPE_PATH)
                if found and base_type and isinstance(base_type, str):
                    self._log_info(f"using default step type '{base_type}'")
                else:
                    raise XeetStepInitException("Step type not specified")
            model_type = base_type
            desc["type"] = base_type

        xstep_class = get_xstep_class(model_type)
        if xstep_class is None:
            raise XeetStepInitException(f"Unknown step type '{model_type}'")
        xstep_model_class = xstep_class.model_class()
        try:
            xstep_model = xstep_model_class(**desc)
            if base_step:
                xstep_model.inherit(base_step)
        except ValidationError as e:
            raise XeetStepInitException(f"{pydantic_errmsg(e)}")
        return xstep_model
