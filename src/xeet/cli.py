from xeet.core.xtest import Xtest, TestStatus
from xeet.core.xres import (TestResult, XStepResult, MtrxResult, IterationResult, RunResult,
                            TestStatus, TestSubStatus, status_as_str, TestFullStatus)
from xeet.core.xstep import XStep
from xeet.core.run_reporter import RunReporter
from xeet.core import TestCriteria
import xeet.core.api as core
from xeet.pr import DictPrintType, pr_obj, pr_info, colors_enabled, create_print_func, LogLevel
from xeet.common import XeetException, json_values, short_str, yes_no_str
from rich.live import Live
from rich.console import Console
from dataclasses import dataclass, field
from typing import ClassVar
import textwrap
import shutil


_DFLT_WIDTH = 78


def _show_test(test: Xtest, full_details: bool, setup: bool) -> None:
    try:
        console_width = shutil.get_terminal_size().columns - 2
    except (AttributeError, OSError):
        console_width = _DFLT_WIDTH

    def print_val(title: str, value) -> None:
        title = f"{title}:"
        text = textwrap.fill(str(value), initial_indent=f"{title:<32} ", subsequent_indent=33 * " ",
                             width=console_width)
        pr_info(text)

    def print_step_list(title: str, steps: list[XStep]) -> None:
        if not steps:
            if full_details:
                print_val(title, "<empty list>")
            return
        pr_info(f"{title}:")
        for count, step in enumerate(steps):
            details = step.details(full=full_details, printable=True, setup=setup)
            k, v = details[0]
            print_val(f" - [{count}] {k}", v)
            for k, v in details[1:]:
                print_val(f"       {k}", v)

    print_val("Name", test.name)
    if test.model.short_desc:
        print_val("Short description", test.model.short_desc)
    if test.model.long_desc:
        print_val("Description", test.model.long_desc)
    if test.model.abstract:
        print_val("Abstract", yes_no_str(test.model.abstract))
    if test.error:
        print_val("Initialization error", test.error)
        return
    if test.model.groups:
        print_val("Groups", ", ".join(test.model.groups))

    print_step_list("Pre-run steps", test.pre_run_steps.steps)
    print_step_list("Run steps", test.run_steps.steps)
    print_step_list("Post-run steps", test.post_run_steps.steps)


def show_test_info(conf: str, test_name: str, setup: bool, full_details: bool) -> None:
    xtest = core.fetch_xtest(conf, test_name, setup=setup)
    if xtest is None:
        raise XeetException(f"No such test: {test_name}")
    if setup:
        xtest.setup()
    _show_test(xtest, full_details=full_details, setup=setup)


def list_groups(conf: str) -> None:
    pr_info(", ".join(core.fetch_groups_list(conf)))


def list_tests(conf: str, names_only: bool, criteria: TestCriteria) -> None:
    def _display_token(token: str | None, max_len: int) -> str:
        if not token:
            return ""
        return short_str(token, max_len)

    tests = core.fetch_tests_list(conf, criteria)

    _max_name_print_len = 40
    _max_desc_print_len = 65
    _error_max_str_len = _max_desc_print_len + 2  # 2 for spaces between description and flags
    print_fmt = f"{{:<{_max_name_print_len}}}  {{}}"  # '{{}}' is a way to escape a '{}'
    err_print_fmt = f"{{:<{_max_name_print_len}}}  {{}}"

    if names_only:
        pr_info(" ".join([test.name for test in tests if not test.error]))
        return

    pr_info(print_fmt.format("Name", "Description"))
    pr_info(print_fmt.format("----", "-----------"))
    for test in tests:
        if test.error:
            error_str = _display_token(f"<error: {test.error}>", _error_max_str_len)
            name_str = _display_token(test.name, _max_name_print_len)
            pr_info(err_print_fmt.format(name_str, error_str))
            continue
        pr_info(print_fmt.format(_display_token(test.name, _max_name_print_len),
                                 _display_token(test.model.short_desc, _max_desc_print_len)))


_Colors = tuple[str, str]
_NO_COLORS: _Colors = ("", "")


def _gen_color_pair(color: str) -> _Colors:
    if not colors_enabled() or not color:
        return _NO_COLORS
    return (f"[{color}]", f"[/{color}]")


def _colorize_str(text: str, color: _Colors | str) -> str:
    if isinstance(color, str):
        color = _gen_color_pair(color)
    return f"{color[0]}{text}{color[1]}"


@dataclass
class CliPrinter(RunReporter):
    show_test_summary: bool = False
    concise: bool = False
    quiet: bool = False
    summary_only: bool = False
    summary_type: str = ""

    curr_tests: list[str] = field(default_factory=list)
    live: Live = None  # type: ignore
    console: Console = None  # type: ignore
    iteration_str: str = ""

    _STATUS_COLORS: ClassVar = {
        TestStatus.NotRun: _gen_color_pair("orange1"),
        TestStatus.Failed: _gen_color_pair("red"),
        TestStatus.Passed: _gen_color_pair("green"),
    }
    _TEST_NAME_COLOR: ClassVar = _gen_color_pair("bold")
    _ITERATION_COLOR: _Colors = _gen_color_pair("medium_orchid")
    _MATRIX_COLOR: _Colors = _gen_color_pair("medium_purple")

    FULL_SUMMARY: ClassVar = "full"
    SHORT_SUMMARY: ClassVar = "short"
    DFLT_SUMMARY: ClassVar = "default"
    NO_SUMMARY: ClassVar = "none"

    @staticmethod
    def status_colors(status: TestStatus) -> tuple[str, str]:
        return CliPrinter._STATUS_COLORS.get(status, _NO_COLORS)

    def set_live(self, live: Live) -> None:
        self.live = live
        self.console = live.console

    def __post_init__(self) -> None:
        if self.quiet or self.summary_only:
            self.on_test_start = self._null_pr
            self.on_test_end = self._null_pr
            self.on_run_start = self._null_pr

        if self.quiet:
            self.on_matrix_end = self._null_pr

        if self.summary_type not in (self.FULL_SUMMARY, self.SHORT_SUMMARY, self.DFLT_SUMMARY,
                                     self.NO_SUMMARY):
            self.summary_type = self.DFLT_SUMMARY
        if self.summary_type == self.DFLT_SUMMARY:
            if self.concise or self.mtrx_count > 1 or self.iterations > 1:
                self.summary_type = self.SHORT_SUMMARY
            else:
                self.summary_type = self.FULL_SUMMARY

    def _null_pr(*_, **__) -> None:
        ...

    def _print_curr_tests(self) -> None:
        if self.curr_tests:
            self.live.update(f"Running: {', '.join(self.curr_tests)}")
        else:
            self.live.update("")

    def on_run_start(self, tests: list[Xtest] = [], **_) -> None:
        if self.concise:
            return
        self.console.print("Starting run\n------------")
        run_res = self.run_res
        assert run_res is not None
        self.console.print(f"Matrix permutations: {self.mtrx_count}")
        self.console.print(f"Test criteria:\n{run_res.criteria}\n")
        self.console.print("Running tests: {}\n".format(", ".join([x.name for x in tests])))

        if self.mtrx_count == 1 or self.concise:
            self.on_matrix_start = self._null_pr
            self.on_matrix_end = self._null_pr

        if self.iterations == 1 or self.concise:
            self.on_iteration_start = self._null_pr
            self.on_iteration_end = self._null_pr

        if self.mtrx_count > 1:
            self.on_iteration_end = self._null_pr

    def on_test_start(self, test: Xtest | None = None, **_) -> None:
        assert test is not None
        self.curr_tests.append(test.name)
        self._print_curr_tests()

    def on_test_end(self, test: Xtest | None = None, test_res: TestResult | None = None, **_
                    ) -> None:
        assert test is not None
        assert test_res is not None
        name = short_str(test.name, 40)

        msg = f"{_colorize_str(name, self._TEST_NAME_COLOR):<55}"

        status_text = status_as_str(test_res.status)
        status_suffix = ""
        if test_res.sub_status != TestSubStatus.Undefined:
            status_suffix = status_as_str(test_res.status, test_res.sub_status)

        stts_str = _colorize_str(status_text, self.status_colors(test_res.status))
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
        self.iteration_str = f"Iteration #{self.iteration}/{self.iterations}"
        if self.mtrx_count > 1:
            return
        self.console.print(_colorize_str(self.iteration_str, self._ITERATION_COLOR))

    def on_iteration_end(self) -> None:
        self.console.print(_colorize_str("Iteration finished", self._ITERATION_COLOR))
        if self.iteration < self.iterations - 1:
            self.console.print("---------")

    def on_matrix_start(self) -> None:
        msg = f"Matrix permutation #{self.mtrx_idx}"
        msg = _colorize_str(msg, self._MATRIX_COLOR)
        if self.iterations > 1:
            iter_msg = _colorize_str(self.iteration_str, self._ITERATION_COLOR)
            msg += f" ({iter_msg})"
        self.console.print(msg)

    def on_matrix_end(self) -> None:
        #  def summarize_test_list(status: TestStatus, sub_status: TestSubStatus, names: list[str]
        #                          ) -> None:
        #      if not names:
        #          return
        #      title = status_as_str(status, sub_status)
        #      colors = self.status_colors(status)
        #      test_list_str = ", ".join(names)
        #      self.console.print(f"{colors[0]}{title}{colors[1]}: {test_list_str}\n")

        #  assert isinstance(self.iter_res, IterationResult)
        #  assert isinstance(self.run_res, RunResult)
        #  self.console.print()
        self.console.print(_colorize_str(f"Matrix permutation finished", self._MATRIX_COLOR))
        if self.mtrx_idx < self.mtrx_count - 1 or self.iteration < self.iterations - 1:
            self.console.print("---------")

        #  if self.concise:
        #      return
        #  self.console.print("Summary:")

        #  assert isinstance(self.mtrx_res, MtrxResult)
        #  keys = sorted(self.mtrx_res.status_results_summary.keys(), key=lambda x: x[0].value)
        #  for k in keys:
        #      test_names = self.mtrx_res.status_results_summary[k]
        #      summarize_test_list(k[0], k[1], test_names)
        #  self.live.update("")
        #  if self.mtrx_idx < self.mtrx_count - 1 or self.iteration < self.iterations - 1:
        #      self.console.print("\n---------")

    def on_run_end(self) -> None:
        def summarize_test_list(status: TestFullStatus, names: list[str]
                                ) -> None:
            if not names:
                return
            title = status_as_str(status[0], status[1])
            colors = self.status_colors(status)
            test_list_str = ", ".join(names)
            self.console.print(f"{colors[0]}{title}{colors[1]}: {test_list_str}\n")

        self.live.update("")
        #  if self.summary_type == self.NO_SUMMARY:
        #      return
        #  self.console.print("Run finished")
        for iter_i, iter_res in enumerate(self.run_res.iter_results):
            iter_summary: dict[TestFullStatus, int] = {}
            for mtrx_i, mtrx_res in enumerate(iter_res.mtrx_results):
                keys = sorted(self.mtrx_res.status_results_summary.keys(), key=lambda x: x[0].value)
                for k in keys:
                    test_names = self.mtrx_res.status_results_summary[k]
                    if k not in iter_summary:
                        iter_summary[k] = 0
                    iter_summary[k] += len(test_names)
                    if self.summary_type == self.FULL_SUMMARY:
                        summarize_test_list(k[0], k[1], test_names)jj


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

    def on_test_enter(self, test: Xtest) -> None:
        _pr_debug_title(f">>>>>>> Starting test '{test.name}' <<<<<<<")

    def on_iteration_end(self) -> None:
        ...

    def on_test_end(self, test: Xtest | None = None, test_res: TestResult | None = None, **_
                    ) -> None:
        assert test is not None
        assert test_res is not None
        _pr_debug_title(f"Test '{test.name}' ended. (status: {test_res.status}, "
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


def run_tests(conf: str,
              repeat: int,
              debug: bool,
              threads: int,
              criteria: TestCriteria,
              reporter: CliPrinter,
              ) -> RunResult:
    console = Console(highlight=False, soft_wrap=True)
    with Live(console=console, refresh_per_second=4, transient=False) as live:
        reporter.set_live(live)
        return core.run_tests(conf, criteria, reporter, debug_mode=debug, iterations=repeat,
                              threads=threads)


def dump_test(file_path: str, name: str) -> None:
    desc = core.fetch_test_desc(file_path, name)
    if desc is None:
        raise XeetException(f"No such test: {name}")
    pr_info(f"Test '{name}' descriptor:")
    pr_obj(desc, print_type=DictPrintType.YAML)


def dump_schema(dump_type: str) -> None:
    pr_obj(core.fetch_schema(dump_type), print_type=DictPrintType.JSON)


def dump_config(file_path: str, json_path: str) -> None:
    obj = core.fetch_config(file_path)
    if json_path:
        obj = json_values(obj, json_path)
        if not obj:
            raise XeetException(f"Path not found '{json_path}'")
        if len(obj) == 1:
            obj = obj[0]
    pr_obj(obj, print_type=DictPrintType.YAML)
