from xeet.core.run_reporter import RunReporter
from xeet.pr import create_print_func, LogLevel, colors_enabled
from xeet.core.xtest import TestPrimaryStatus, TestResult, TestStatus, TestSecondaryStatus, Xtest
from xeet.core.xstep import XStep
from xeet.common import short_str
from xeet.core.xres import TestPrimaryStatus, XStepResult, StatusTestsDict
from rich.console import Console
from rich.live import Live
from enum import Enum
from dataclasses import dataclass, field


# See https://rich.readthedocs.io/en/stable/appendix/colors.html for color names
_Colors = tuple[str, str]
_NO_COLORS: _Colors = ("", "")


def _gen_color_pair(color: str) -> _Colors:
    if not colors_enabled() or not color:
        return _NO_COLORS
    return (f"[{color}]", f"[/{color}]")


def colorize_str(text: str, color: _Colors | str) -> str:
    if isinstance(color, str):
        color = _gen_color_pair(color)
    return f"{color[0]}{text}{color[1]}"


_TEST_NAME_COLOR = _gen_color_pair("bold")
_ITERATION_COLOR = _gen_color_pair("medium_orchid")
_MATRIX_COLOR = _gen_color_pair("medium_purple")

_STATUS_COLORS = {
    TestPrimaryStatus.NotRun: _gen_color_pair("orange1"),
    TestPrimaryStatus.Failed: _gen_color_pair("red"),
    TestPrimaryStatus.Passed: _gen_color_pair("green"),
}


def _status_colors(status: TestPrimaryStatus) -> _Colors:
    return _STATUS_COLORS.get(status, _NO_COLORS)


class CliPrinterVerbosity(str, Enum):
    Default = "default"
    Quiet = "quiet"
    Concise = "concise"
    Verbose = "verbose"


@dataclass
class CliPrinter(RunReporter):
    verbosity: CliPrinterVerbosity = CliPrinterVerbosity.Default
    summary_only: bool = False

    curr_tests: list[str] = field(default_factory=list)
    live: Live = None  # type: ignore
    console: Console = None  # type: ignore
    iteration_str: str = ""

    def set_live(self, live: Live) -> None:
        self.live = live
        self.console = live.console

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

    def on_run_start(self, tests: list[Xtest] = [], **_) -> None:
        def _null_pr(*_, **__) -> None:
            ...

        if self.quiet or self.summary_only:
            self.on_test_start = _null_pr
            self.on_test_end = _null_pr
            self.on_iteration_start = _null_pr

        if self.quiet:
            self.on_run_end = _null_pr
            return

        if self.concise or self.summary_only:
            return

        self.console.print("Starting run\n============")
        run_res = self.run_res
        assert run_res is not None
        self.console.print(f"Matrix permutations: {self.mtrx_count}")
        self.console.print(f"Test criteria:\n{run_res.criteria}\n")
        self.console.print("Running tests: {}\n".format(", ".join([x.name for x in tests])))

    def on_test_start(self, test: Xtest | None = None, **_) -> None:
        assert test is not None
        self.curr_tests.append(test.name)
        self._print_curr_tests()

    def on_test_end(self, test: Xtest | None = None, test_res: TestResult | None = None, **_
                    ) -> None:
        assert test is not None
        assert test_res is not None
        name = short_str(test.name, 40)

        msg = f"{colorize_str(name, _TEST_NAME_COLOR):<55}"

        status_text = str(TestStatus(test_res.status.primary))
        status_suffix = ""
        if test_res.status.secondary != TestSecondaryStatus.Undefined:
            status_suffix = str(test_res.status)

        stts_str = colorize_str(status_text, _status_colors(test_res.status.primary))
        msg += f"[{stts_str}]"
        if status_suffix:
            msg += f" {short_str(status_suffix, 30)}"
        if not self.concise:
            details = test_res.error_summary()
            if details:
                msg += f"\n{details}\n"
        self.curr_tests.remove(test.name)
        self.console.print(msg)

    def on_iteration_start(self) -> None:
        self.iteration_str = f"Iteration #{self.iteration}/{self.iterations - 1}"
        if self.mtrx_count > 1:
            return
        self.console.print(colorize_str(self.iteration_str, _ITERATION_COLOR))

    def on_matrix_start(self) -> None:
        if self.mtrx_count == 1 and self.iterations == 1:
            return
        self.console.print(self._mtx_header(self.iteration, self.mtrx_idx))

    def on_matrix_end(self) -> None:
        if self.mtrx_count == 1 and self.iterations == 1:
            return
        self.console.print("---------")

    def _summarize_result_names(self, results: StatusTestsDict, show_names: bool) -> None:
        stss = sorted(results.keys(), key=lambda x: x.primary.value)
        for s in stss:
            names = results[s]
            colors = _status_colors(s.primary)
            msg = f"{colors[0]}{s}{colors[1]}"
            if show_names:
                msg += f" ({len(names)}): " + ", ".join(names)
            else:
                msg += f": {len(names)}"
            self.console.print(msg)
        self.console.print()

    def _mtx_header(self, iter_i, mtrx_i) -> str:
        ret = ""
        if self.mtrx_count > 1:
            ret += colorize_str(f"Matrix permutation #{mtrx_i}", _MATRIX_COLOR)
            if self.iterations == 1:
                return ret
        if self.iterations > 1:
            if ret:
                ret += "@"
            ret += colorize_str(f"Iteration #{iter_i}", _ITERATION_COLOR)
        return ret

    def on_run_end(self) -> None:
        self.live.update("")
        self.console.print("\nRun finished. Results summary:\n==============================")

        single_result = self.iterations == 1 and self.mtrx_count == 1
        if single_result:
            result = self.run_res.iter_results[0].mtrx_results[0].status_results_summary
            self._summarize_result_names(result, not self.concise)
            if self.verbose:
                self.console.print("\nAccumulated summary:")
                self._summarize_result_names(result, False)
            return

        total_summary: StatusTestsDict = {}
        for iter_i, iter_res in enumerate(self.run_res.iter_results):
            iter_summary: dict[TestStatus, list[str]] = {}
            for mtrx_i, mtrx_res in enumerate(iter_res.mtrx_results):
                stss = sorted(mtrx_res.status_results_summary.keys(),
                              key=lambda x: x.primary.value)
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

                    self.console.print(self._mtx_header(iter_i, mtrx_i))
                    self._summarize_result_names(mtrx_res.status_results_summary, self.verbose)

        if not self.concise:
            self.console.print("Accumulated summary:")
        self._summarize_result_names(total_summary, False)


_ORANGE = '\033[38;5;208m'
_pr_debug_title = create_print_func(_ORANGE, LogLevel.ALWAYS)


class DebugPrinter(CliPrinter):
    def _step_title(self, step: XStep, phase_name: str, step_index: int,
                    sentence_start: bool = False) -> str:
        if sentence_start:
            text = phase_name[0].upper() + phase_name[1:]
        else:
            text = phase_name
        text += f" step #{step_index} ({step.model.step_type})"
        if step.model.name:
            text += f" '{step.model.name}'"
        return text

    def __post_init__(self) -> None:
        ...

    def on_test_enter(self, test: Xtest) -> None:
        _pr_debug_title(f">>>>>>> Starting test '{test.name}' <<<<<<<")

    def on_iteration_end(self) -> None:
        ...

    def on_test_end(self, test: Xtest | None = None, test_res: TestResult | None = None, **_
                    ) -> None:
        assert test is not None
        assert test_res is not None
        _pr_debug_title(f"Test '{test.name}' ended. (status: {test_res.status.primary}, "
                        f"duration: {test_res.duration:.3f}s)")

    def on_step_start(self, test: Xtest | None = None, phase_name: str = "",
                      step: XStep | None = None, step_index: int = -1, **_) -> None:
        assert test is not None
        assert step is not None
        assert step_index >= 0
        title = self._step_title(step, phase_name, step_index, sentence_start=True)
        _pr_debug_title(f"{title} - staring run")

    def on_step_end(self, phase_name: str = "", step: XStep | None = None, step_index: int = -1,
                    step_res: XStepResult | None = None, **_) -> None:
        assert step is not None
        assert step_res is not None
        text = self._step_title(step, phase_name, step_index, sentence_start=True)
        text += f" - run ended (completed, " if step_res.completed else f" (incomplete, "
        text += f"failed, " if step_res.failed else f"passed, "
        text += f"duration: {step_res.duration:.3f}s)"
        _pr_debug_title(text)

    def on_phase_start(self, phase_name: str = "", steps_count: int = -1, **_) -> None:
        if steps_count == 0:
            return
        _pr_debug_title(f"Starting {phase_name} phase run, {steps_count} step(s)")

    def on_phase_end(self, phase_name: str = "", steps_count: int = -1, **_) -> None:
        if steps_count == 0:
            return
        text = phase_name[0].upper() + phase_name[1:]
        _pr_debug_title(f"{text} phase ended")
