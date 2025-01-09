from xeet.core.events import EventReporter
from xeet.pr import *
from xeet.core.test import (TestPrimaryStatus, TestResult, TestStatus, TestSecondaryStatus, Test,
                            Phase)
from xeet.core.step import Step
from xeet.common import short_str, title
from xeet.core.result import TestPrimaryStatus, StepResult, StatusTestsDict
from rich.live import Live
from enum import Enum
from dataclasses import dataclass, field
import inspect


_ITERATION_COLOR = "medium_orchid"

_STATUS_COLORS = {
    TestPrimaryStatus.NotRun: "orange1",
    TestPrimaryStatus.Failed: "red",
    TestPrimaryStatus.Passed: "green",
}


def _status_color(status: TestPrimaryStatus) -> str:
    return _STATUS_COLORS.get(status, XColors.NoColor)


class CliPrinterVerbosity(str, Enum):
    Default = "default"
    Quiet = "quiet"
    Concise = "concise"
    Verbose = "verbose"


class CliPrinterSummaryOpts(str, Enum):
    Default = "default"
    SummaryOnly = "summary_only"
    NoSummary = "no_summary"


@dataclass
class CliPrinter(EventReporter):
    live: Live = None  # type: ignore
    verbosity: CliPrinterVerbosity = CliPrinterVerbosity.Default
    summary_opt: CliPrinterSummaryOpts = CliPrinterSummaryOpts.Default

    curr_tests: list[str] = field(default_factory=list)

    @property
    def concise(self) -> bool:
        return self.verbosity == CliPrinterVerbosity.Concise

    @property
    def quiet(self) -> bool:
        return self.verbosity == CliPrinterVerbosity.Quiet

    @property
    def verbose(self) -> bool:
        return self.verbosity == CliPrinterVerbosity.Verbose

    @property
    def dflt_output(self) -> bool:
        return self.verbosity == CliPrinterVerbosity.Default

    def _print_curr_tests(self) -> None:
        if self.curr_tests:
            self.live.update(f"Running: {', '.join(self.curr_tests)}")
        else:
            self.live.update("")

    def _print_missing_args_msg(self) -> None:
        pr_warn("Missing arguments for event")
        import traceback
        traceback.print_stack()

    def on_run_start(self, **_) -> None:
        def _null_pr(*_, **__) -> None:
            ...

        if self.quiet or self.summary_opt == CliPrinterSummaryOpts.SummaryOnly:
            self.on_test_start = _null_pr
            self.on_test_end = _null_pr
            self.on_iteration_start = _null_pr

        if self.quiet:
            self.on_run_end = _null_pr
            return

        if self.concise or self.summary_opt == CliPrinterSummaryOpts.SummaryOnly:
            return

        pr_info(title("Starting xeet run", color=XColors.Bold))
        run_res = self.run_res
        assert run_res is not None
        if self.verbose:
            pr_info(f"{run_res.criteria}\n")
            pr_info("Running tests: {}\n".format(", ".join([x.name for x in self.tests])))
        if self.verbose or self.threads > 1:
            pr_info(f"Using {self.threads} threads per iteration")

    def on_test_start(self, test: Test | None = None, **_) -> None:
        if test is None:
            self._print_missing_args_msg()
            return

        self.curr_tests.append(test.name)
        self._print_curr_tests()

    def on_test_end(self, test: Test | None = None, test_res: TestResult | None = None, **_
                    ) -> None:
        if test is None or test_res is None:
            self._print_missing_args_msg()
            return

        msg = short_str(test.name, 40)
        msg = colorize_str(f"{msg:<45}", XColors.Bold)

        status_text = str(TestStatus(test_res.status.primary))
        status_suffix = ""
        if test_res.status.secondary != TestSecondaryStatus.Undefined:
            status_suffix = str(test_res.status)

        stts_str = colorize_str(status_text, _status_color(test_res.status.primary))
        msg += f"[{stts_str}]"
        if status_suffix:
            msg += f" {short_str(status_suffix, 30)}"
        if not self.concise:
            details = test_res.error_summary()
            if details:
                msg += f"\n{details}\n"
        self.curr_tests.remove(test.name)
        pr_info(msg)

    def on_iteration_start(self) -> None:
        pr_info()
        if self.iterations == 1:
            return
        pr_info(colorize_str(self._iter_header(self.iteration_index), _ITERATION_COLOR))

    def _summarize_result_names(self, results: StatusTestsDict, show_names: bool) -> None:
        stss = sorted(results.keys(), key=lambda x: x.primary.value)
        for s in stss:
            names = results[s]
            msg = colorize_str(str(s), _status_color(s.primary))
            if show_names:
                msg += f" ({len(names)}): " + ", ".join(names)
            else:
                msg += f": {len(names)}"
            pr_info(msg)
        pr_info()

    def _iter_header(self, iter_i: int, as_title=False) -> str:
        if as_title:
            return title(f"Iteration #{iter_i}", '-', newline_prefix=False, color=_ITERATION_COLOR)
        return colorize_str(f"Iteration #{iter_i}", _ITERATION_COLOR)

    def on_run_end(self) -> None:
        if self.run_res is None:
            self._print_missing_args_msg()
            return

        self.live.update("")
        if self.summary_opt == CliPrinterSummaryOpts.NoSummary:
            return
        if self.summary_opt != CliPrinterSummaryOpts.SummaryOnly:
            pr_info(title("Summary:", color=XColors.Bold))

        if self.iterations == 1:
            result = self.run_res.iter_results[0].status_results_summary
            self._summarize_result_names(result, not self.concise)
            return

        total_summary: StatusTestsDict = {}
        for iter_i, iter_res in enumerate(self.run_res.iter_results):
            iter_summary: StatusTestsDict = {}
            stss = sorted(iter_res.status_results_summary.keys(),
                          key=lambda x: x.primary.value)
            for s in stss:
                test_names = iter_res.status_results_summary[s]
                if s not in iter_summary:
                    iter_summary[s] = list()
                iter_summary[s].extend(test_names)
                if s not in total_summary:
                    total_summary[s] = list()
                total_summary[s].extend(test_names)

            if self.concise:
                continue
            header = self._iter_header(iter_i, as_title=True)
            pr_info(header)
            self._summarize_result_names(iter_res.status_results_summary, self.verbose)

        if not self.concise:
            pr_info(title("Accumulated summary:", '-', color=XColors.Bold))
        self._summarize_result_names(total_summary, False)


_pr_debug_title = create_print_func("orange1", LogLevel.ALWAYS)


@dataclass
class DebugPrinter(EventReporter):
    def _print_bad_args(self, **kwargs) -> None:
        frame = inspect.stack()[1]
        func_name = frame.function
        for k, v in kwargs.items():
            if v is None:
                pr_warn(f"{func_name}: bad argument: '{k}' is None")

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

    def on_run_start(self, **_) -> None:  # type: ignore
        _pr_debug_title("Starting run")

    def on_init(self, **_) -> None:
        _pr_debug_title("Initializing Xeet")

    def on_test_start(self, test: Test | None = None, **_) -> None:
        if test is None:
            self._print_bad_args(test=test)
            return
        _pr_debug_title(f">>>>>>> Starting test '{test.name}' <<<<<<<")

    def on_test_end(self, test: Test | None = None, test_res: TestResult | None = None, **_
                    ) -> None:
        if test is None or test_res is None:
            self._print_bad_args(test=test, test_res=test_res)
            return
        _pr_debug_title(f"Test '{test.name}' ended. (status: {test_res.status.primary}, "
                        f"duration: {test_res.duration:.3f}s)")
        if test_res.status.primary == TestPrimaryStatus.NotRun:
            pr_warn("Test didn't complete")
        if test_res.status.primary == TestPrimaryStatus.Failed:
            pr_error(f"Test failed")

    def on_step_start(self, step: Step | None = None, **_) -> None:
        if step is None:
            self._print_bad_args(step=step)
            return
        title = self._step_title(step, step.phase.name, step.step_index, sentence_start=True)
        _pr_debug_title(f"{title} - staring run")

    def on_step_end(self, step: Step | None = None, step_res: StepResult | None = None, **_
                    ) -> None:
        if step is None or step_res is None:
            self._print_bad_args(step=step, step_res=step_res)
            return
        text = self._step_title(step, step.phase.name, step.step_index, sentence_start=True)
        text += f" - run ended (completed, " if step_res.completed else f" (incomplete, "
        text += f"failed, " if step_res.failed else f"passed, "
        text += f"duration: {step_res.duration:.3f}s)"
        _pr_debug_title(text)

    def on_phase_start(self, phase: Phase | None = None, **_) -> None:
        if phase is None:
            self._print_bad_args(phase=phase)
            return
        steps_count = len(phase.steps)
        if steps_count == 0:
            _pr_debug_title(f"Empty {phase.name} phase - no steps")
            return
        _pr_debug_title(f"Starting {phase.name} phase run, {steps_count} step(s)")

    def on_phase_end(self, phase: Phase | None = None, **_) -> None:
        if phase is None:
            self._print_bad_args(phase=phase)
            return
        if not phase.steps:
            return
        text = phase.name[0].upper() + phase.name[1:]
        _pr_debug_title(f"{text} phase ended")

    # General event message
    def on_test_message(self, msg: str, *args, test: Test | None = None, **kwargs) -> None:
        if test is None:
            self._print_bad_args(test=test)
            return
        self._print_msg(msg, *args, **kwargs)

    def on_step_message(self, msg: str, *args, step: Step | None = None, **kwargs) -> None:
        if step is None:
            self._print_bad_args(step=step)
            return
        self._print_msg(msg, *args, **kwargs)

    def _print_msg(self, *args, **kwargs) -> None:
        if not kwargs.pop("dbg_pr", True):
            return
        pr_info(*args, **kwargs)
