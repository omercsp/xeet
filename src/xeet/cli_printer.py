from xeet.core.events import LockableEventReporter
from xeet.common import locked
from xeet.pr import *
from xeet.core.test import (TestPrimaryStatus, TestResult, TestStatus, TestSecondaryStatus, Test,
                            Phase)
from xeet.core.step import Step
from xeet.common import short_str, underline
from xeet.core.result import PhaseResult, TestPrimaryStatus, StepResult, StatusTestsDict
from rich.live import Live
from rich.markup import escape as rich_escape
from enum import Enum
from dataclasses import dataclass, field


_ITERATION_COLOR = "medium_orchid"
_MATRIX_COLOR = "medium_purple"

_STATUS_COLORS = {
    TestPrimaryStatus.NotRun: "orange1",
    TestPrimaryStatus.Failed: "red",
    TestPrimaryStatus.Passed: "green",
    TestPrimaryStatus.Skipped: "grey53",
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


class CliPrinterTestTimingOpts(str, Enum):
    NoTime = "none"
    Full = "full"
    RunTime = "run"


@dataclass
class CliPrinter(LockableEventReporter):
    live: Live = None  # type: ignore
    verbosity: CliPrinterVerbosity = CliPrinterVerbosity.Default
    summary_opt: CliPrinterSummaryOpts = CliPrinterSummaryOpts.Default
    test_timing_opt: CliPrinterTestTimingOpts = CliPrinterTestTimingOpts.NoTime

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

    def on_run_start(self, **_) -> None:
        def _null_pr(*_, **__) -> None:
            ...

        if self.quiet or self.summary_opt == CliPrinterSummaryOpts.SummaryOnly:
            self.on_test_start = _null_pr
            self.on_test_end = _null_pr
            self.on_matrix_start = _null_pr

        if self.quiet:
            self.on_run_end = _null_pr
            return

        if self.concise or self.summary_opt == CliPrinterSummaryOpts.SummaryOnly:
            return

        title = colorize_str("Starting xeet run", XColors.Bold)
        pr_info(f"\n{underline(title)}")
        run_res = self.run_res
        assert run_res is not None
        if self.verbose:
            pr_info(f"{run_res.criteria}\n")
            pr_info("Running tests: {}\n".format(", ".join([x.name for x in self.tests])))
        if self.verbose or self.threads > 1:
            pr_info(f"Using {self.threads} threads per iteration")

    @locked
    def on_test_start(self, test: Test) -> None:

        self.curr_tests.append(test.name)
        self._print_curr_tests()

    @locked
    def on_test_end(self, test_res: TestResult) -> None:
        test = test_res.test
        msg = short_str(test.name, 40)
        msg = colorize_str(f"{msg:<45}", XColors.Bold)

        status_text = str(TestStatus(test_res.status.primary))
        status_suffix = ""
        if test_res.status.secondary != TestSecondaryStatus.Undefined:
            status_suffix = str(test_res.status)

        stts_str = colorize_str(status_text, _status_color(test_res.status.primary))
        msg += f"[{stts_str}]"
        if self.test_timing_opt != CliPrinterTestTimingOpts.NoTime or self.verbose:
            if self.test_timing_opt == CliPrinterTestTimingOpts.Full:
                msg += f" ({test_res.duration_str}s)"
            else:
                msg += f" ({test_res.main_res.duration_str})"
        if status_suffix:
            msg += f" {short_str(status_suffix, 30)}"
        if not self.concise:
            details = test_res.error_summary()
            if details:
                #  Escape special characters (e.g. Saure brackets) so rich won't get confused
                details = rich_escape(details)
                msg += f"\n{details}\n"
        self.curr_tests.remove(test.name)
        pr_info(msg)

    def on_matrix_start(self) -> None:
        pr_info()
        if self.mtrx_count == 1 and self.iterations == 1:
            return

        if self.mtrx_count == 1:
            pr_info(self._iter_header(self.iteration_index, -1))
        else:
            pr_info(self._iter_header(self.iteration_index, self.mtrx_prmttn_index))

    def _summarize_result_names(self, results: StatusTestsDict, show_names: bool, duration: float
                                ) -> None:
        stss = sorted(results.keys(), key=lambda x: x.primary.value)
        for s in stss:
            names = results[s]
            msg = colorize_str(str(s), _status_color(s.primary))
            if show_names:
                msg += f" ({len(names)}): " + ", ".join(names)
            else:
                msg += f": {len(names)}"
            pr_info(msg)
        pr_info(f"Duration: {duration:.3f}s\n")

    def _iter_header(self, iter_i: int, mtrx_i: int) -> str:
        ret = ""
        if self.mtrx_count > 1 and mtrx_i >= 0:
            msg = f"Matrix permutation #{mtrx_i}"
            if self.mtrx_prmttn:
                prmttn = ", ".join([f"{k}={v}" for k, v in self.mtrx_prmttn.items()])
                msg += f"\n({prmttn})"
            ret += colorize_str(msg, _MATRIX_COLOR)
            if self.iterations == 1:
                return ret
        if self.iterations > 1:
            if ret:
                ret += "@"
            ret += colorize_str(f"Iteration #{iter_i}", _ITERATION_COLOR)

        return ret

    def on_run_end(self) -> None:
        assert self.run_res is not None
        self.live.update("")
        if self.summary_opt == CliPrinterSummaryOpts.NoSummary:
            return
        if self.summary_opt != CliPrinterSummaryOpts.SummaryOnly:
            pr_info()
            msg = "Summary"
            msg += ":"
            pr_info(underline(colorize_str(msg, color=XColors.Bold)))

        single_result = self.iterations == 1 and self.mtrx_count == 1
        if single_result:
            mtrx_res = self.run_res.iter_results[0].mtrx_results[0]
            result = mtrx_res.status_results_summary
            self._summarize_result_names(result, not self.concise, mtrx_res.duration)
            return

        total_summary: StatusTestsDict = {}
        for iter_i, iter_res in enumerate(self.run_res.iter_results):
            iter_summary: StatusTestsDict = {}
            for mtrx_i, mtrx_res in enumerate(iter_res.mtrx_results):
                stss = sorted(mtrx_res.status_results_summary.keys(), key=lambda x: x.primary.value)
                for s in stss:
                    test_names = mtrx_res.status_results_summary[s]
                    if s not in iter_summary:
                        iter_summary[s] = list()
                    iter_summary[s].extend(test_names)
                    if s not in total_summary:
                        total_summary[s] = list()
                    total_summary[s].extend(test_names)

                if self.concise:
                    continue
                header = self._iter_header(iter_i, mtrx_i)
                header = underline(header, '-')
                pr_info(header)
                self._summarize_result_names(mtrx_res.status_results_summary, self.verbose,
                                             mtrx_res.duration)

        if not self.concise:
            pr_info()
            pr_info(underline(colorize_str("Accumulated summary:", color=XColors.Bold), '-'))
        self._summarize_result_names(total_summary, False, self.run_res.duration)


_pr_debug_title = create_print_func("orange1", LogLevel.ALWAYS)


@dataclass
class DebugPrinter(LockableEventReporter):
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

    @locked
    def on_test_start(self, test: Test) -> None:
        _pr_debug_title(f">>>>>>> Starting test '{test.name}' <<<<<<<")

    @locked
    def on_test_end(self, test_res: TestResult) -> None:
        test = test_res.test
        _pr_debug_title(f"Test '{test.name}' ended. (status: {test_res.status.primary}, "
                        f"duration: {test_res.duration:.3f}s)")
        if test_res.status.primary == TestPrimaryStatus.NotRun:
            pr_warn("Test didn't complete")
        if test_res.status.primary == TestPrimaryStatus.Failed:
            pr_error(f"Test failed")

    @locked
    def on_step_start(self, step: Step) -> None:
        title = self._step_title(step, step.phase.name, step.step_index, sentence_start=True)
        _pr_debug_title(f"{title} - staring run")

    @locked
    def on_step_end(self, step_res: StepResult) -> None:
        step = step_res.step
        text = self._step_title(step, step.phase.name, step.step_index, sentence_start=True)
        text += f" - run ended (completed, " if step_res.completed else f" (incomplete, "
        text += f"failed, " if step_res.failed else f"passed, "
        text += f"duration: {step_res.duration:.3f}s)"
        _pr_debug_title(text)

    @locked
    def on_phase_start(self, phase: Phase) -> None:
        steps_count = len(phase.steps)
        if steps_count == 0:
            _pr_debug_title(f"Empty {phase.name} phase - no steps")
            return
        _pr_debug_title(f"Starting {phase.name} phase run, {steps_count} step(s)")

    @locked
    def on_phase_end(self, phase_res: PhaseResult) -> None:
        phase = phase_res.phase
        if not phase.steps:
            return
        text = phase.name[0].upper() + phase.name[1:]
        _pr_debug_title(f"{text} phase ended")

    # General event message
    @locked
    def on_test_message(self, _: Test, msg: str, *args, **kwargs) -> None:
        self._print_msg(msg, *args, **kwargs)

    @locked
    def on_step_message(self, _: Step, msg: str, *args, **kwargs) -> None:
        self._print_msg(msg, *args, **kwargs)

    def _print_msg(self, *args, **kwargs) -> None:
        if not kwargs.pop("dbg_pr", True):
            return
        if len(args) > 0 and isinstance(args[0], str):
            msg = args[0]
            msg = msg[0:1].upper() + msg[1:]
            args = [msg] + list(args[1:])
        pr_info(*args, **kwargs)
