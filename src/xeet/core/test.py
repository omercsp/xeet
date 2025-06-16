from .resource import Resource
from .import RuntimeInfo, system_var_name, is_system_var_name
from .result import (TestResult, TestPrimaryStatus, TestSecondaryStatus, PhaseResult, TestStatus,
                     time_result)
from .step import Step, StepModel, XeetStepInitException
from xeet.common import XeetException, XeetVars, pydantic_errmsg, KeysBaseModel, NonEmptyStr
from xeet.steps import get_xstep_class
from xeet.core.matrix import Matrix, MatrixModel
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


class _ResouceRequiremnt(KeysBaseModel):
    pool: NonEmptyStr
    count: int = Field(1, ge=1)
    names: list[NonEmptyStr] = Field(default_factory=list)
    as_var: str = _EMPTY_STR

    @model_validator(mode='after')
    def post_validate(self) -> "_ResouceRequiremnt":
        if self.has_key("names") and self.has_key("count"):
            raise ValueError("Resource requirement can't have both 'names' and 'count'")
        if len(set([n.root for n in self.names])) != len(self.names):
            raise ValueError("Resource names must be unique")

        return self


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
    matrix: MatrixModel = Field(default_factory=dict)

    platforms: list[str] = Field(default_factory=list)

    #  Resource requirements
    resources: list[_ResouceRequiremnt] = Field(default_factory=list)

    # Inheritance behavior
    inherit_variables: bool = True
    pre_run_inheritance: StepsInheritType = StepsInheritType.Replace
    run_inheritance: StepsInheritType = StepsInheritType.Replace
    post_run_inheritance: StepsInheritType = StepsInheritType.Replace

    # Internals
    error: str = Field(_EMPTY_STR, exclude=True)
    prmttn: dict[str, Any] = Field(default_factory=dict, exclude=True)
    __test__ = False

    @model_validator(mode='after')
    def post_validate(self) -> "TestModel":
        if self.abstract and self.groups:
            raise ValueError("Abstract tests can't have groups")

        user_vars = self.var_map.keys()
        for var in user_vars:
            if is_system_var_name(var):
                raise ValueError(f"Invalid user variable name '{var}'.")

        intersection = set(user_vars).intersection(set(self.matrix.keys()))
        if intersection:
            raise ValueError(f"User variables {intersection} are also used in matrix. "
                             "This is not allowed, as it may lead to unexpected results.")

        groups = []
        for g in self.groups:
            g = g.strip()
            if not g:
                continue
            groups.append(g)
        self.groups = groups
        return self

    def inherit(self, other: "TestModel") -> None:
        if self.inherit_variables:
            self.var_map = {**other.var_map, **self.var_map}
            self.matrix = {**other.matrix, **self.matrix}

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

        if not self.has_key("platforms") and other.has_key("platforms"):
            self.platforms = other.platforms

        if not self.has_key("resources") and other.has_key("resources"):
            self.resources = other.resources

    def matrix_permutations(self) -> list["TestModel"]:
        models = []
        if not self.matrix:
            return models
        matrix = Matrix(self.matrix)
        for i, prmttn in enumerate(matrix.permutations()):
            desc = self.model_dump()
            desc["name"] = f"{self.name}:{i}"
            desc["matrix"] = dict()
            test = TestModel(**desc)
            test.prmttn = prmttn
            models.append(test)
        return models


@dataclass
class Phase:
    name: str
    test: "Test"
    short_name: str
    stop_on_err: bool
    steps: list[Step] = field(default_factory=list)
    on_fail_status: TestPrimaryStatus = TestPrimaryStatus.Undefined
    on_run_err_status: TestPrimaryStatus = TestPrimaryStatus.Undefined

    def stop(self):
        for step in self.steps:
            step.stop()


class Test:
    __test__ = False

    def __init__(self, model: TestModel, rti: RuntimeInfo) -> None:
        self.model = model
        self.rti = rti
        self.name: str = model.name
        self.pre_phase = Phase(name="pre", test=self, short_name="pre", stop_on_err=True)
        self.main_phase = Phase(name="main", test=self, short_name="stp", stop_on_err=True)
        self.post_phase = Phase(name="post", test=self, short_name="pst", stop_on_err=False)
        self.obtained_resources: list[Resource] = []

        if model.error:
            self.error = model.error
            return

        self.base = self.model.base
        self.error = _EMPTY_STR
        self._init_phase_steps(self.pre_phase, self.model.pre_run)
        if self.error:
            return
        self._init_phase_steps(self.main_phase, self.model.run)
        if self.error:
            return
        self._init_phase_steps(self.post_phase, self.model.post_run)
        if self.error:
            return

        try:
            variables = {**model.var_map, **model.prmttn}
            self.xvars = XeetVars(variables, rti.xvars)
        except XeetException as e:
            self.error = str(e)
            return
        self.xvars.set_vars({system_var_name("TEST_NAME"): self.name})
        self.output_dir = _EMPTY_STR
        self.stop_requested = False
        self.prmttn: dict[str, Any] = dict()

    def _init_phase_steps(self, phase: Phase, steps: list[dict]) -> None:
        for index, step_desc in enumerate(steps):
            try:
                self.notify(f"initializing {phase.name} step {index}")
                step_model = self._gen_step_model(step_desc)
                step_class = get_xstep_class(step_model.step_type)
                if step_class is None:  # Shouldn't happen
                    raise XeetStepInitException(f"Unknown step type '{step_model.step_type}'")
                step = step_class(model=step_model, test=self, phase=phase, step_index=index)
                phase.steps.append(step)
            except XeetStepInitException as e:
                self.error = f"error initializing {phase.name} step {index}: {e}"
                self.warn(self.error)

    @property
    def debug_mode(self) -> bool:
        return self.rti.debug_mode

    def setup(self) -> None:
        self.notify("setting up test", dbg_pr=False)
        self.output_dir = f"{self.rti.output_dir}/{self.name}"

        self.xvars.set_vars({system_var_name("TEST_OUT_DIR"): self.output_dir})
        step_xvars = XeetVars(parent=self.xvars)

        try:
            for phase in (self.pre_phase, self.main_phase, self.post_phase):
                for step in phase.steps:
                    step.setup(xvars=step_xvars, base_dir=self.output_dir)
                    step_xvars.reset()
        except XeetException as e:
            self.error = str(e)
            self.notify(f"error setting up test - {e}", dbg_pr=True)

    def release_resources(self) -> None:
        for r in self.obtained_resources:
            r.release()
        self.obtained_resources.clear()

    def obtain_resources(self) -> bool:
        try:
            for req in self.model.resources:
                self.notify(f"obtaining resource '{req.pool.root}'")
                if req.names:
                    names = [n.root for n in req.names]
                    obtained = self.rti.obtain_resource_list(req.pool.root, names)
                else:
                    obtained = self.rti.obtain_resource_list(req.pool.root, req.count)

                if not obtained:
                    self.notify(f"resource '{req.pool.root}' not available")
                    self.release_resources()
                    return False

                self.obtained_resources.extend(obtained)
                if req.as_var:
                    if self.xvars.has_var(req.as_var):
                        raise XeetException(f"Variable '{req.as_var}' already exists."
                                            " Can't assign resource to it")
                    if req.names:
                        var_value = {r.name: r.value for r in obtained}
                    else:
                        if req.count == 1:
                            var_value = obtained[0].value
                        else:
                            var_value = [r.value for r in obtained]
                    self.xvars.set_vars({req.as_var: var_value})
        except XeetException as e:
            self.error = f"Error obtaining resources - {e}"
            self.notify(self.error)
            self.release_resources()
            # We return true, as thes test doesn't have any resources at this point
            # it is marekd as with error, but we want other tests to run.
        return True

    def _mkdir_output_dir(self) -> None:
        self.notify(f"setting up output directory '{self.output_dir}'")
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except OSError as e:
            raise XeetException(f"Error creating output directory - {e.strerror}")

    _PhaseFunc = Callable[[TestResult], PhaseResult]

    @time_result
    def run(self) -> TestResult:
        if self.model.abstract:
            raise XeetException("Can't run abstract tasks")

        self.setup()
        res = TestResult(test=self)
        if self.error:
            res.status = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr)
            res.status_reason = self.error
            return res
        if self.model.skip:
            self.notify("marked to be skipped", dbg_pr=True)
            res.status = TestStatus(TestPrimaryStatus.Skipped)
            res.status_reason = self.model.skip_reason
            return res

        if self.model.platforms and os.name not in self.model.platforms:
            self.notify(f"skipping test due to platform mismatch", dbg_pr=True)
            res.status = TestStatus(TestPrimaryStatus.Skipped)
            res.status_reason = f"Platform '{os.name}' not in test's platform list"
            return res

        if not self.main_phase.steps:
            res.status = TestStatus(TestPrimaryStatus.Skipped)
            res.status_reason = self.model.skip_reason
            return res

        self.notify("starting run", dbg_pr=False)
        self._mkdir_output_dir()

        self._exec_phase(self.pre_phase, res, res.pre_run_res, self._pre_phase_exec, True)
        self._exec_phase(self.main_phase, res, res.main_res, self._main_phase_exec, True)
        self._exec_phase(self.post_phase, res, res.post_run_res, self._post_phase_exec, False)
        return res

    def _exec_phase(self, phase: Phase, test_res: TestResult, phase_res: PhaseResult,
                    phase_func: _PhaseFunc, skip_on_err: bool) -> PhaseResult:
        if test_res.status.primary != TestPrimaryStatus.Undefined and skip_on_err:
            self.notify(f"skipping {phase.name} phase, test status={test_res.status}",
                        dbg_pr=False)
            return phase_res
        if not phase.steps:
            self.notify(f"skipping {phase.name} phase; no steps", dbg_pr=False)
            return phase_res
        self.rti.notifier.on_phase_start(phase)
        phase_func(test_res)
        self.rti.notifier.on_phase_end(phase_res)
        return phase_res

    @time_result
    def _pre_phase_exec(self, res: TestResult) -> PhaseResult:
        if not self.pre_phase.steps:
            return res.pre_run_res
        self._run_phase(self.pre_phase, res.pre_run_res)
        if not res.pre_run_res.completed or res.pre_run_res.failed:
            res.status.primary = TestPrimaryStatus.NotRun
            if self.stop_requested:
                res.status.secondary = TestSecondaryStatus.Stopped
            else:
                res.status.secondary = TestSecondaryStatus.PreTestErr
                res.status_reason = res.pre_run_res.error_summary()
        return res.pre_run_res

    @time_result
    def _main_phase_exec(self, res: TestResult) -> PhaseResult:
        if res.status.primary != TestPrimaryStatus.Undefined:
            return res.main_res
        self._run_phase(self.main_phase, res.main_res)
        if not res.main_res.completed:
            res.status.primary = TestPrimaryStatus.NotRun
            if self.stop_requested:
                res.status.secondary = TestSecondaryStatus.Stopped
            else:
                res.status.secondary = TestSecondaryStatus.TestErr
            res.status_reason = res.main_res.error_summary()
            return res.main_res
        if res.main_res.failed:
            if self.model.expected_failure:
                res.status.primary = TestPrimaryStatus.Passed
                res.status.secondary = TestSecondaryStatus.ExpectedFail
            else:
                res.status.primary = TestPrimaryStatus.Failed
                res.status_reason = res.main_res.error_summary()
            return res.main_res
        if self.model.expected_failure:
            res.status.primary = TestPrimaryStatus.Failed
            res.status.secondary = TestSecondaryStatus.UnexpectedPass
            return res.main_res
        res.status.primary = TestPrimaryStatus.Passed
        return res.main_res

    @time_result
    def _post_phase_exec(self, res: TestResult) -> PhaseResult:
        if not self.post_phase.steps:
            return res.post_run_res
        self._run_phase(self.post_phase, res.post_run_res)

        if res.post_run_res.completed and not res.post_run_res.failed:
            return res.post_run_res

        if not res.post_run_res.completed:
            res.post_run_status = TestPrimaryStatus.NotRun
        elif res.post_run_res.failed:
            res.post_run_status = TestPrimaryStatus.Failed
        return res.post_run_res

    def _run_phase(self, phase: Phase, res: PhaseResult) -> None:
        if not phase.steps:
            return
        notifier = self.rti.notifier

        for step in phase.steps:
            notifier.on_step_start(step)
            step_res = step.run()
            notifier.on_step_end(step_res)
            res.append_step_result(step_res)
            if phase.stop_on_err and (step_res.failed or not step_res.completed):
                break

    def stop(self) -> None:
        self.stop_requested = True
        self.pre_phase.stop()
        self.main_phase.stop()
        self.post_phase.stop()

    def notify(self, *args, **kwargs) -> None:
        self.rti.notifier.on_test_message(self, *args, **kwargs)

    def warn(self, *args, **kwargs) -> None:
        self.rti.notifier.on_test_message(self, *args, severity=logging.WARN, **kwargs)

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
                    self.notify(f"using default step type '{base_type}'")
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
