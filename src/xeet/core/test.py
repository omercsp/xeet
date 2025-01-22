from .resource import Resource
from .import RuntimeInfo, system_var_name, is_system_var_name
from .result import TestResult, TestPrimaryStatus, TestSecondaryStatus, StepsListResult, TestStatus
from .step import Step, StepModel, XeetStepInitException
from xeet.common import (XeetException, XeetVars, pydantic_errmsg, yes_no_str, KeysBaseModel,
                         NonEmptyStr)
from xeet.log import log_info, log_verbose, log_warn
from xeet.steps import get_xstep_class
from xeet.pr import pr_info, pr_warn
from typing import Any
from pydantic import Field, ValidationError, ConfigDict, AliasChoices, model_validator
from functools import cache
from enum import Enum
from dataclasses import dataclass, field
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

        if not self.has_key("platforms") and other.has_key("platforms"):
            self.platforms = other.platforms

        if not self.has_key("resources") and other.has_key("resources"):
            self.resources = other.resources


@dataclass
class _StepList:
    name: str
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
        self.obtained_resources: list[Resource] = []
        if model.error:
            self.error = model.error
            return
        self.runner_id = ""

        self.base = self.model.base
        self.error = _EMPTY_STR
        self.pre_run_steps = self._init_step_list(self.model.pre_run, "pre", "pre", True)
        if self.error:
            return
        self.run_steps = self._init_step_list(self.model.run, "main", "stp", True)
        if self.error:
            return
        self.post_run_steps = self._init_step_list(self.model.post_run, "post", "pst", False)
        if self.error:
            return

        try:
            self.xvars = XeetVars(model.var_map, rti.xvars)
        except XeetException as e:
            self.error = str(e)
            return
        self.xvars.set_vars({system_var_name("TEST_NAME"): self.name})
        self.output_dir = _EMPTY_STR

    def set_runner_id(self, runner_id: str = "") -> None:
        self.runner_id = runner_id
        self._log_prefix.cache_clear()

    def _init_step_list(self, step_list: list[dict], name: str, short_name: str, stop_on_err: bool
                        ) -> _StepList:
        ret = _StepList(name=name, short_name=short_name, stop_on_err=stop_on_err)
        id_base = self.name
        id_base += f"_{name}"
        for index, step_desc in enumerate(step_list):
            try:
                self._log_info(f"initializing {name} step {index}")
                step_model = self._gen_xstep_model(step_desc)
                step_class = get_xstep_class(step_model.step_type)
                if step_class is None:  # Shouldn't happen
                    raise XeetStepInitException(f"Unknown step type '{step_model.step_type}'")
                step = step_class(model=step_model, rti=self.rti, test_name=self.name,
                                  phase_name=short_name, step_index=index)
                ret.steps.append(step)
            except XeetStepInitException as e:
                self._log_warn(f"Error initializing {name}step {index}: {e}")
                self.error = f"Error initializing {name}step {index}: {e}"
        return ret

    @property
    def debug_mode(self) -> bool:
        return self.rti.debug_mode

    def setup(self) -> None:
        self._log_prefix.cache_clear()
        self._log_info("Pre execution setup")
        self.output_dir = f"{self.rti.output_dir}/{self.name}"

        self.xvars.set_vars({system_var_name("TEST_OUT_DIR"): self.output_dir})
        step_xvars = XeetVars(parent=self.xvars)

        try:
            for steps in (self.pre_run_steps, self.run_steps,
                          self.post_run_steps):
                for step in steps.steps:
                    step.setup(xvars=step_xvars, base_dir=self.output_dir, runner_id=self.runner_id)
                    step_xvars.reset()
        except XeetException as e:
            self.error = str(e)
            self._log_info(f"Error setting up test - {e}", dbg_pr=True)

    def release_resources(self) -> None:
        for r in self.obtained_resources:
            r.release()
        self.obtained_resources.clear()

    def obtain_resources(self) -> bool:
        try:
            for req in self.model.resources:
                self._log_info(f"Obtaining '{req.pool.root}' resource(s)")
                if req.names:
                    names = [n.root for n in req.names]
                    obtained = self.rti.obtain_resource_list(req.pool.root, names)
                else:
                    obtained = self.rti.obtain_resource_list(req.pool.root, req.count)

                if not obtained:
                    self._log_info("Resource not available")
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
            self._log_info(self.error)
            self.release_resources()
            # We return true, as thes test doesn't have any resources at this point
            # it is marekd as with error, but we want other tests to run.
        return True

    def _mkdir_output_dir(self) -> None:
        self._log_info(f"setting up output directory '{self.output_dir}'")
        try:
            log_verbose("Creating output directory if it doesn't exist: '{}'", self.output_dir)
            os.makedirs(self.output_dir, exist_ok=True)
        except OSError as e:
            raise XeetException(f"Error creating output directory - {e.strerror}")

    def run(self, **steup_args) -> TestResult:
        if self.model.abstract:
            raise XeetException("Can't run abstract tasks")

        self.setup(**steup_args)
        if self.error:
            return TestResult(TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr),
                              status_reason=self.error)
        if self.model.skip:
            self._log_info("Marked to be skipped", dbg_pr=True)
            return TestResult(TestStatus(TestPrimaryStatus.Skipped),
                              status_reason=self.model.skip_reason)
        if self.model.platforms and os.name not in self.model.platforms:
            self._log_info(f"Skipping test due to platform mismatch", dbg_pr=True)
            return TestResult(TestStatus(TestPrimaryStatus.Skipped),
                              status_reason=f"Platform '{os.name}' not in test's platform list")
        if not self.run_steps:
            self._log_info("No command for test, will not run", dbg_pr=True)
            return TestResult(TestStatus(TestPrimaryStatus.NotRun), status_reason="No command")

        res = TestResult()
        self._log_info("Starting run")
        self._mkdir_output_dir()
        self._phase_wrapper(self.pre_run_steps, res, self._pre_test)
        self._phase_wrapper(self.run_steps, res, self._main_run)
        self._phase_wrapper(self.post_run_steps, res, self._post_test)

        if res.status.primary == TestPrimaryStatus.Passed or \
                res.status.secondary == TestSecondaryStatus.ExpectedFail:
            self._log_info("Completed successfully")
        return res

    def _pre_test(self, res: TestResult) -> None:
        if not self.pre_run_steps.steps:
            self._log_info("No pre-test steps")
            return
        self._log_info("Running pre-test steps")
        self._run_xstep_list(self.pre_run_steps, res.pre_run_res)
        if not res.pre_run_res.completed or res.pre_run_res.failed:
            self._log_info(f"Pre-test failed or didn't complete")
            res.status.primary = TestPrimaryStatus.NotRun
            res.status.secondary = TestSecondaryStatus.PreTestErr
            res.status_reason = res.pre_run_res.error_summary()
            return

    def _phase_wrapper(self, step_list: _StepList, res: TestResult, func) -> None:
        notifier = self.rti.notifier
        notifier.on_phase_start(self, step_list.name, len(step_list.steps))
        func(res)
        notifier.on_phase_end(self, step_list.name, len(step_list.steps))

    def _main_run(self, res: TestResult) -> None:
        if res.status.primary != TestPrimaryStatus.Undefined:
            self._log_info("Skipping run. Prior stage failed")
            return
        self._log_info("Running test steps")
        self._run_xstep_list(self.run_steps, res.run_res)
        if not res.run_res.completed:
            self._log_info("Test didn't complete")
            res.status.primary = TestPrimaryStatus.NotRun
            res.status.secondary = TestSecondaryStatus.TestErr
            res.status_reason = res.run_res.error_summary()
            return
        if res.run_res.failed:
            self._log_info(f"Test failed (expected: {yes_no_str(self.model.expected_failure)})")
            if self.model.expected_failure:
                res.status.primary = TestPrimaryStatus.Passed
                res.status.secondary = TestSecondaryStatus.ExpectedFail
            else:
                res.status.primary = TestPrimaryStatus.Failed
                res.status_reason = res.run_res.error_summary()
            return
        if self.model.expected_failure:
            self._log_info("Unexpected pass")
            res.status.primary = TestPrimaryStatus.Failed
            res.status.secondary = TestSecondaryStatus.UnexpectedPass
            return
        res.status.primary = TestPrimaryStatus.Passed

    def _post_test(self, res: TestResult) -> None:
        if not self.post_run_steps.steps:
            self._log_info("Skipping post-test, no steps")
            return
        self._log_info(f"Running post-test steps")
        self._run_xstep_list(self.post_run_steps, res.post_run_res)

        if res.post_run_res.completed and not res.post_run_res.failed:
            self._log_info("Post test run completed successfully")
            return

        err = res.post_run_res.error_summary()
        if not res.post_run_res.completed:
            res.post_run_status = TestPrimaryStatus.NotRun
            self._log_info(f"Post test run error - {err}")
        elif res.post_run_res.failed:
            res.post_run_status = TestPrimaryStatus.Failed
            self._log_info(f"Post test run failed - {err}")

    def _run_xstep_list(self, step_list: _StepList, res: StepsListResult) -> None:
        if not step_list.steps:
            return
        notifier = self.rti.notifier

        for index, step in enumerate(step_list.steps):
            notifier.on_step_start(self, step_list.name, step, index)
            step_res = step.run()
            notifier.on_step_end(self, step_list.name, step, index, step_res)
            res.results.append(step_res)
            if step_list.stop_on_err and (step_res.failed or not step_res.completed):
                break

    @cache
    def _log_prefix(self) -> str:
        if not self.runner_id:
            return f"{self.name}:"
        return f"{self.name}@{self.runner_id}:"

    def _log_info(self, msg, *args, **kwargs) -> None:
        if self.debug_mode and kwargs.pop("dbg_pr", False):
            kwargs.pop("pr", None)  # Prevent double printing
            pr_info(msg, *args, **kwargs)
        log_info(f"{self._log_prefix()} {msg}", *args, depth=1, **kwargs)

    def _log_warn(self, msg, *args, **kwargs) -> None:
        if self.debug_mode and kwargs.pop("dbg_pr", True):
            kwargs.pop("pr", None)  # Prevent double printing
            pr_warn(msg, *args, **kwargs)
        log_warn(f"{self._log_prefix()} {msg}", *args, depth=1, **kwargs)

    _DFLT_STEP_TYPE_PATH = "settings.xeet.default_step_type"

    def _gen_xstep_model(self, desc: dict, included: set[str] | None = None) -> StepModel:
        if included is None:
            included = set()
        base = desc.get("base")
        if base in included:
            raise XeetStepInitException(f"Include loop detected - '{base}'")

        base_step_model = None
        base_type = None
        if base:
            self._log_info(f"base step '{base}' found")
            #  TODO: add refernce by name in addition to path
            base_desc, found = self.rti.config_ref(base)
            if not found:
                raise XeetStepInitException(f"Base step '{base}' not found")
            if not isinstance(base_desc, dict):
                raise XeetStepInitException(f"Invalid base step '{base}'")
            base_step_model = self._gen_xstep_model(base_desc, included)
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
