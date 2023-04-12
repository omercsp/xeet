from .import RuntimeInfo, system_var_name, is_system_var_name
from .result import TestResult, TestPrimaryStatus, TestSecondaryStatus, PhaseResult, TestStatus
from .step import Step, StepModel, XeetStepInitException
from xeet.common import XeetException, XeetVars, pydantic_errmsg, KeysBaseModel
from xeet.steps import get_xstep_class
from typing import Any, Callable
from pydantic import Field, ValidationError, ConfigDict, AliasChoices, model_validator
from enum import Enum
from dataclasses import dataclass, field
import logging
import os


_EMPTY_STR = ""


class StepsInheritType(str, Enum):
    Prepend = "prepend"
    Append = "append"
    Replace = "replace"


class TestModel(KeysBaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str
    base: str = _EMPTY_STR
    abstract: bool = False
    short_desc: str = Field(_EMPTY_STR, max_length=75)
    long_desc: str = _EMPTY_STR
    groups: list[str] = Field(default_factory=list)
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
    def post_validate(self) -> "TestModel":
        if self.abstract and self.groups:
            raise ValueError("Abstract tests can't have groups")

        user_vars = self.var_map.keys()
        for var in user_vars:
            if is_system_var_name(var):
                raise ValueError(f"Invalid user variable name '{var}'.")

        groups = []
        for g in self.groups:
            g = g.strip()
            if not g:
                continue
            groups.append(g)
        self.groups = groups
        return self

    def inherit(self, other: "TestModel") -> None:
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
class Phase:
    name: str
    test: "Test"
    short_name: str
    stop_on_err: bool
    steps: list[Step] = field(default_factory=list)
    on_fail_status: TestPrimaryStatus = TestPrimaryStatus.Undefined
    on_run_err_status: TestPrimaryStatus = TestPrimaryStatus.Undefined


class Test:
    def __init__(self, model: TestModel, rti: RuntimeInfo) -> None:
        self.model = model
        self.rti = rti
        self.name: str = model.name

        if model.error:
            self.error = model.error
            return

        self.base = self.model.base
        self.error = _EMPTY_STR
        self.pre_phase = self._init_phase(self.model.pre_run, "pre", "pre", True)
        if self.error:
            return
        self.main_phase = self._init_phase(self.model.run, "main", "stp", True)
        if self.error:
            return
        self.post_phase = self._init_phase(self.model.post_run, "post", "pst", False)
        if self.error:
            return

        try:
            self.xvars = XeetVars(model.var_map, rti.xvars)
        except XeetException as e:
            self.error = str(e)
            return
        self.xvars.set_vars({system_var_name("TEST_NAME"): self.name})
        self.output_dir = _EMPTY_STR

    def _init_phase(self, steps: list[dict], name: str, short_name: str, stop_on_err: bool
                    ) -> Phase:
        ret = Phase(name=name, test=self, short_name=short_name, stop_on_err=stop_on_err)
        id_base = self.name
        id_base += f"_{name}"
        for index, step_desc in enumerate(steps):
            try:
                self._log_info(f"initializing {name} step {index}")
                step_model = self._gen_step_model(step_desc)
                step_class = get_xstep_class(step_model.step_type)
                if step_class is None:  # Shouldn't happen
                    raise XeetStepInitException(f"Unknown step type '{step_model.step_type}'")
                step = step_class(model=step_model, test=self, phase=ret, step_index=index)
                ret.steps.append(step)
            except XeetStepInitException as e:
                self._log_warn(f"Error initializing {name}step {index}: {e}")
                self.error = f"Error initializing {name}step {index}: {e}"
        return ret

    @property
    def debug_mode(self) -> bool:
        return self.rti.debug_mode

    def setup(self) -> None:
        self._log_info("setting up test", dbg_pr=False)
        self.output_dir = f"{self.rti.output_dir}/{self.name}"

        self.xvars.set_vars({system_var_name("TEST_OUT_DIR"): self.output_dir})
        step_xvars = XeetVars(parent=self.xvars)

        try:
            for steps in (self.pre_phase, self.main_phase,
                          self.post_phase):
                for step in steps.steps:
                    step.setup(xvars=step_xvars, base_dir=self.output_dir)
                    step_xvars.reset()
        except XeetException as e:
            self.error = str(e)
            self._log_info(f"Error setting up test - {e}", dbg_pr=True)

    def _mkdir_output_dir(self) -> None:
        self._log_info(f"setting up output directory '{self.output_dir}'")
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except OSError as e:
            raise XeetException(f"Error creating output directory - {e.strerror}")

    def run(self) -> TestResult:
        if self.model.abstract:
            raise XeetException("Can't run abstract tasks")

        self.setup()
        if self.error:
            return TestResult(TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr),
                              status_reason=self.error)
        if self.model.skip:
            self._log_info("Marked to be skipped", dbg_pr=True)
            return TestResult(TestStatus(TestPrimaryStatus.Skipped),
                              status_reason=self.model.skip_reason)
        if not self.main_phase:
            self._log_info("No command for test, will not run", dbg_pr=True)
            return TestResult(TestStatus(TestPrimaryStatus.NotRun), status_reason="No command")

        res = TestResult()
        self._log_info("Starting run", dbg_pr=False)
        self._mkdir_output_dir()

        self._exec_phase(self.pre_phase, res, res.pre_run_res, self._pre_phase_exec, True)
        self._exec_phase(self.main_phase, res, res.run_res, self._main_phase_exec, True)
        self._exec_phase(self.post_phase, res, res.post_run_res, self._post_phase_exec, False)
        return res

    def _exec_phase(self, phase: Phase, test_res: TestResult, phase_res: PhaseResult,
                    phase_func: Callable[[TestResult], None], skip_on_err: bool) -> None:
        if test_res.status.primary != TestPrimaryStatus.Undefined and skip_on_err:
            self._log_info(f"Skipping {phase.name} phase, test status={test_res.status}",
                           dbg_pr=False)
            return
        if not phase.steps:
            self._log_info(f"Skipping {phase.name} phase. No steps", dbg_pr=False)
            return
        self.rti.notifier.on_phase_start(test=self, test_res=test_res, phase=phase)
        phase_func(test_res)
        self.rti.notifier.on_phase_end(test=self, test_res=test_res, phase=phase,
                                       phase_res=phase_res)

    def _pre_phase_exec(self, res: TestResult) -> None:
        if not self.pre_phase.steps:
            return
        self._run_phase(self.pre_phase, res.pre_run_res)
        if not res.pre_run_res.completed or res.pre_run_res.failed:
            res.status.primary = TestPrimaryStatus.NotRun
            res.status.secondary = TestSecondaryStatus.PreTestErr
            res.status_reason = res.pre_run_res.error_summary()

    def _main_phase_exec(self, res: TestResult) -> None:
        if res.status.primary != TestPrimaryStatus.Undefined:
            return
        self._run_phase(self.main_phase, res.run_res)
        if not res.run_res.completed:
            res.status.primary = TestPrimaryStatus.NotRun
            res.status.secondary = TestSecondaryStatus.TestErr
            res.status_reason = res.run_res.error_summary()
            return
        if res.run_res.failed:
            if self.model.expected_failure:
                res.status.primary = TestPrimaryStatus.Passed
                res.status.secondary = TestSecondaryStatus.ExpectedFail
            else:
                res.status.primary = TestPrimaryStatus.Failed
                res.status_reason = res.run_res.error_summary()
            return
        if self.model.expected_failure:
            res.status.primary = TestPrimaryStatus.Failed
            res.status.secondary = TestSecondaryStatus.UnexpectedPass
            return
        res.status.primary = TestPrimaryStatus.Passed

    def _post_phase_exec(self, res: TestResult) -> None:
        if not self.post_phase.steps:
            return
        self._run_phase(self.post_phase, res.post_run_res)

        if res.post_run_res.completed and not res.post_run_res.failed:
            return

        if not res.post_run_res.completed:
            res.post_run_status = TestPrimaryStatus.NotRun
        elif res.post_run_res.failed:
            res.post_run_status = TestPrimaryStatus.Failed

    def _run_phase(self, phase: Phase, res: PhaseResult) -> None:
        if not phase.steps:
            return
        notifier = self.rti.notifier

        for step in phase.steps:
            notifier.on_step_start(step=step)
            step_res = step.run()
            notifier.on_step_end(step=step, step_res=step_res)
            res.steps_results.append(step_res)
            if phase.stop_on_err and (step_res.failed or not step_res.completed):
                break

    def _log_info(self, msg, *args, **kwargs) -> None:
        self.rti.notifier.on_test_message(test=self, msg=msg, *args, **kwargs)

    def _log_warn(self, msg, *args, **kwargs) -> None:
        self.rti.notifier.on_test_message(test=self, msg=msg, *args, severity=logging.WARN,
                                          **kwargs)

    _DFLT_STEP_TYPE_PATH = "settings.xeet.default_step_type"

    def _gen_step_model(self, desc: dict, included: set[str] | None = None) -> StepModel:
        if included is None:
            included = set()
        base = desc.get("base")
        if base in included:
            raise XeetStepInitException(f"Include loop detected - '{base}'")

        base_step_model = None
        base_type = None
        if base:
            #  TODO: add refernce by name in addition to path
            base_desc, found = self.rti.config_ref(base)
            if not found:
                raise XeetStepInitException(f"Base step '{base}' not found")
            if not isinstance(base_desc, dict):
                raise XeetStepInitException(f"Invalid base step '{base}'")
            base_step_model = self._gen_step_model(base_desc, included)
            base_type = base_step_model.step_type

        model_type = desc.get("type")
        if model_type:
            if base_type and model_type != base_type:
                raise XeetStepInitException(
                    f"Step type '{model_type}' doesn't match base type '{base_type}'")
        else:
            if not base_type:
                base_type, found = self.rti.config_ref(self._DFLT_STEP_TYPE_PATH)
                if found and base_type and isinstance(base_type, str):
                    self._log_info(f"using default step type '{base_type}'")
                else:
                    raise XeetStepInitException("Step type not specified")
            model_type = base_type
            desc["type"] = base_type

        step_class = get_xstep_class(model_type)
        if step_class is None:
            raise XeetStepInitException(f"Unknown step type '{model_type}'")
        step_model_class = step_class.model_class()
        try:
            step_model = step_model_class(**desc)
            if base_step_model:
                step_model.inherit(base_step_model)
        except ValidationError as e:
            raise XeetStepInitException(f"{pydantic_errmsg(e)}")
        return step_model
