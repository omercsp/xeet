from .console import BaseConsoleReporterOpts
from xeet.reporters.console import BaseConsoleReporterOpts, ConsoleReporterVerbosity
from xeet.core.events import LockableEventReporter
from xeet.pr import pr_warn, pr_error, pr_info, pr_generic, create_print_func, LogLevel
from xeet.core.test import TestPrimaryStatus, TestResult, Test, Phase
from xeet.core.step import Step
from xeet.core.result import PhaseResult, TestPrimaryStatus, StepResult, FixtureResult, TestStatus
from xeet.core.fixture import Fixture
from dataclasses import dataclass, field
from xeet.common import locked


_pr_debug_title = create_print_func("orange1", LogLevel.ALWAYS)


@dataclass
class ConsoleDebugPrinter(LockableEventReporter):
    display: BaseConsoleReporterOpts = field(default_factory=BaseConsoleReporterOpts)

    @property
    def concise(self) -> bool:
        return self.display._verbosity == ConsoleReporterVerbosity.Concise

    def _step_title(self, step: Step, phase_name: str, step_index: int,
                    sentence_start: bool = False) -> str:
        if sentence_start:
            text = phase_name[0].upper() + phase_name[1:]
        else:
            text = phase_name
        text += f" step #{step_index} ({step.model.step_type})"
        if step.model.name:
            text += f" '{step.model.name}'"
        return text

    def on_run_start(self, **_) -> None:
        if self.concise:
            return
        _pr_debug_title("Starting run")

    def _run_title(self, name: str) -> str:
        title = name
        if self.rti.iterations > 1 or self.rti.matrix.prmttns_count > 1:
            title += "@"
            if self.rti.iterations > 1:
                title += f"i{self.rti.iteration}"
            if self.rti.matrix.prmttns_count > 1:
                title += f"p{self.rti.prmttn_index}"
        return title

    @locked
    def on_test_start(self, test: Test) -> None:
        _pr_debug_title(f">>>>>>> Starting test '{self._run_title(test.name)}' <<<<<<<")

    @locked
    def on_test_end(self, test_res: TestResult) -> None:
        test = test_res.test
        _pr_debug_title(f"Test '{test.name}' ended. (status: {test_res.status}, "
                        f"duration: {test_res.duration:.3f}s)")
        if self.concise:
            pr_info()
            return
        if test_res.status.primary == TestPrimaryStatus.NotRun:
            pr_warn(f"Test didn't complete")
        if test_res.status.primary == TestPrimaryStatus.Failed:
            pr_error(f"Test failed")
        pr_info()

    @locked
    def on_step_start(self, step: Step) -> None:
        if self.concise:
            return
        title = self._step_title(step, step.phase.name, step.step_index, sentence_start=True)
        _pr_debug_title(f"{title} - staring run")

    @locked
    def on_step_end(self, step_res: StepResult) -> None:
        if self.concise:
            return
        step = step_res.step
        text = self._step_title(step, step.phase.name, step.step_index, sentence_start=True)
        text += f" - run ended (completed, " if step_res.completed else f" (incomplete, "
        text += f"failed, " if step_res.failed else f"passed, "
        text += f"duration: {step_res.duration:.3f}s)"
        _pr_debug_title(text)

    @locked
    def on_phase_start(self, phase: Phase) -> None:
        if self.concise:
            return
        steps_count = len(phase.steps)
        if steps_count == 0:
            _pr_debug_title(f"Empty {phase.name} phase - no steps")
            return
        _pr_debug_title(f"Starting {phase.name} phase run, {steps_count} step(s)")

    @locked
    def on_phase_end(self, phase_res: PhaseResult) -> None:
        if self.concise:
            return
        phase = phase_res.phase
        if not phase.steps:
            return
        text = phase.name[0].upper() + phase.name[1:]
        _pr_debug_title(f"{text} phase ended")

    @locked
    def on_fixture_setup_start(self, fixture: Fixture) -> None:
        _pr_debug_title(f">>>>>>> Setting up fixture '{self._run_title(fixture.name)}' <<<<<<<")

    @locked
    def on_fixture_setup_end(self, fixture_res: FixtureResult) -> None:
        self._fixture_end("setup", fixture_res, fixture_res.setup_status, fixture_res.setup_res,
                          fixture_res.setup_error_summary())

    @locked
    def on_fixture_teardown_start(self, fixture: Fixture) -> None:
        _pr_debug_title(f">>>>>>> Tearing down fixture '{self._run_title(fixture.name)}' <<<<<<<")

    @locked
    def on_fixture_teardown_end(self, fixture_res: FixtureResult) -> None:
        self._fixture_end("teardown", fixture_res, fixture_res.teardown_status,
                          fixture_res.teardown_res, fixture_res.teardown_error_summary())

    def _fixture_end(self, stage: str, fixture_res: FixtureResult, status: TestPrimaryStatus,
                     phase_res: PhaseResult, details: str) -> None:
        if status == TestPrimaryStatus.Skipped:
            _pr_debug_title(f"Fixture '{fixture_res.name}' {stage} skipped: {details}")
            pr_info()
            return
        _pr_debug_title(f"Fixture '{fixture_res.name}' {stage} ended. (status: "
                        f"{TestStatus(status)}, duration: {phase_res.duration:.3f}s)")
        if not self.concise and details:
            pr_warn(details)
        pr_info()

    # General event message
    @locked
    def on_test_message(self, _: Test, msg: str, *args, **kwargs) -> None:
        if self.concise:
            return
        self._print(msg, *args, **kwargs)

    @locked
    def on_fixture_message(self, _: Fixture, msg: str, *args, **kwargs) -> None:
        if self.concise:
            return
        self._print(msg, *args, **kwargs)

    @locked
    def on_step_message(self, _: Step, *args, **kwargs) -> None:
        if self.concise:
            return
        self._print(*args, **kwargs)

    def on_step_output(self, _: Step, *args, **kwargs) -> None:
        self._print(*args, **kwargs)

    def _print(self, *args, **kwargs) -> None:
        if not kwargs.pop("dbg_pr", True):
            return
        pr_generic(*args, **kwargs, pr_markup=False)
