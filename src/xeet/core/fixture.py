from . import RuntimeInfo, system_var_name, FIXTURES_DIR_NAME
from .result import FixtureResult, PhaseResult
from .step import XeetStepInitException
from .test import Phase
from xeet.common import XeetException, XeetVars, pydantic_errmsg
from xeet.steps import get_xstep_class, gen_step_model
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from typing import Any
import logging


#  Fixtures are defined under this settings key, as a mapping of a name to a fixture descriptor
FIXTURES_SETTINGS_KEY = "fixtures"


class FixtureModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    short_desc: str = Field("", max_length=75)
    setup: list[Any] = Field(default_factory=list)
    teardown: list[Any] = Field(default_factory=list)

    @model_validator(mode='after')
    def post_validate(self) -> "FixtureModel":
        if not self.setup and not self.teardown:
            raise ValueError("Fixture has neither setup nor teardown steps")
        return self


#  A fixture prepares the environment for the tests that require it. Its setup steps run before
#  these tests, and its teardown steps run after all the tests of the matrix permutation ended.
#  Fixture steps run in the run wide variables scope, so they can't use tests specific variables.
class Fixture:
    def __init__(self, name: str, desc: Any, rti: RuntimeInfo) -> None:
        self.name = name
        self.rti = rti
        self.error = ""
        self.stop_requested = False
        self.model: FixtureModel = None  # type: ignore
        self.setup_phase = Phase(name="setup", owner=self, short_name="su", stop_on_err=True)
        self.teardown_phase = Phase(name="teardown", owner=self, short_name="td",
                                    stop_on_err=False)
        self.output_dir = ""
        self.xvars: XeetVars = None  # type: ignore
        self._curr_phase: Phase | None = None

        if not isinstance(desc, dict):
            self.error = "Invalid fixture descriptor"
            return
        try:
            self.model = FixtureModel(**desc)
        except ValidationError as e:
            self.error = pydantic_errmsg(e)
            return
        self._init_phase_steps(self.setup_phase, self.model.setup)
        if self.error:
            return
        self._init_phase_steps(self.teardown_phase, self.model.teardown)

    def _init_phase_steps(self, phase: Phase, steps: list[Any]) -> None:
        for index, step_desc in enumerate(steps):
            try:
                if not isinstance(step_desc, dict):
                    raise XeetStepInitException("Invalid step descriptor")
                step_model = gen_step_model(self, step_desc)
                step_class = get_xstep_class(step_model.step_type)
                if step_class is None:  # Shouldn't happen
                    raise XeetStepInitException(f"Unknown step type '{step_model.step_type}'")
                step = step_class(model=step_model, owner=self, phase=phase, step_index=index)
                phase.steps.append(step)
            except XeetStepInitException as e:
                self.error = f"error initializing {phase.name} step {index}: {e}"
                return

    @property
    def debug_mode(self) -> bool:
        return self.rti.debug_mode

    #  Sets the fixture's output directory and variables. Called once per matrix permutation,
    #  before the fixture is set up, as the output directory and matrix variables change.
    def prepare(self) -> None:
        self.reset_stop()
        self.output_dir = f"{self.rti.output_dir}/{FIXTURES_DIR_NAME}/{self.name}"
        self.xvars = XeetVars({
            system_var_name("FIXTURE_NAME"): self.name,
            system_var_name("FIXTURE_DIR"): self.output_dir,
        }, parent=self.rti.xvars)

    def run_setup(self, res: FixtureResult) -> None:
        res.setup_error = self._run_phase(self.setup_phase, res.setup_res)

    def run_teardown(self, res: FixtureResult) -> None:
        res.teardown_error = self._run_phase(self.teardown_phase, res.teardown_res)

    #  Stops the currently running phase, or the next one to run if none is running. Phases
    #  that weren't stopped aren't affected, so after the stop request is reset, a fixture whose
    #  setup was stopped can still be torn down.
    def stop(self) -> None:
        self.stop_requested = True
        if self._curr_phase:
            self._curr_phase.stop()

    def reset_stop(self) -> None:
        self.stop_requested = False

    #  Returns an error string if the phase couldn't run to its end, or an empty string otherwise.
    #  Steps failures are reported in the phase result.
    def _run_phase(self, phase: Phase, phase_res: PhaseResult) -> str:
        phase_res.phase = phase
        if not phase.steps:
            return ""
        step_xvars = XeetVars(parent=self.xvars)
        try:
            for step in phase.steps:
                step.setup(xvars=step_xvars, base_dir=self.output_dir)
                step_xvars.reset()
        except XeetException as e:
            self.notify(f"error setting up {phase.name} steps - {e}")
            return f"error setting up {phase.name} steps - {e}"

        self._curr_phase = phase
        notifier = self.rti.notifier
        notifier.on_phase_start(phase)
        phase_res.set_start_time()
        try:
            for step in phase.steps:
                if self.stop_requested:
                    break
                notifier.on_step_start(step)
                step_res = step.run()
                notifier.on_step_end(step_res)
                phase_res.append_step_result(step_res)
                if phase.stop_on_err and (step_res.failed or not step_res.completed):
                    break
        finally:
            phase_res.set_end_time()
            self._curr_phase = None
        notifier.on_phase_end(phase_res)
        if self.stop_requested:
            return "Stop requested"
        return ""

    def notify(self, *args, **kwargs) -> None:
        self.rti.notifier.on_fixture_message(self, *args, **kwargs)

    def warn(self, *args, **kwargs) -> None:
        self.rti.notifier.on_fixture_message(self, *args, severity=logging.WARN, **kwargs)
