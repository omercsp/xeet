from xeet.core.xtest import Xtest, TestStatus
from xeet.core.xres import TestResult, status_catgoery, XStepResult, IterationResult, RunResult
from xeet.core.xstep import XStep
from xeet.core.run_reporter import RunReporter
from xeet.core import TestCriteria
import xeet.core.api as core
from xeet.pr import (DictPrintType, pr_obj, pr_info, PrintColors, colors_enabled, create_print_func,
                     LogLevel)
from xeet.common import XeetException, json_values, short_str, yes_no_str
from dataclasses import dataclass
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


def list_tests(conf: str, names_only: bool, **kwargs) -> None:
    def _display_token(token: str | None, max_len: int) -> str:
        if not token:
            return ""
        return short_str(token, max_len)

    criteria = TestCriteria(**kwargs)
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


@dataclass
class _StatusPrintInfo:
    color: str
    string: str


_STATUS_PRINT_INFO = {
    TestStatus.Passed: _StatusPrintInfo(PrintColors.GREEN, "Passed"),
    TestStatus.InitErr: _StatusPrintInfo(PrintColors.YELLOW, "Initialization error",),
    TestStatus.ExpectedFail: _StatusPrintInfo(PrintColors.GREEN, "Expected failure"),
    TestStatus.Failed: _StatusPrintInfo(PrintColors.RED, "Failed"),
    TestStatus.PreRunErr: _StatusPrintInfo(PrintColors.YELLOW, "Pre-run error"),
    TestStatus.RunErr: _StatusPrintInfo(PrintColors.YELLOW, "Run error"),
    TestStatus.UnexpectedPass: _StatusPrintInfo(PrintColors.RED, "Unexpected pass"),
    TestStatus.Skipped: _StatusPrintInfo(PrintColors.RESET, "Skipped"),
}


def _reset_color():
    return PrintColors.RESET if colors_enabled() else ""


class CliRunReporter(RunReporter):
    def __init__(self, show_summary: bool) -> None:
        super().__init__()
        self.show_summary = show_summary

    def on_run_start(self, tests: list[Xtest]) -> None:
        pr_info("Starting run\n------------")
        run_res = self.run_res
        assert run_res is not None
        if run_res.criteria.include_groups:
            groups_str = ", ".join(sorted(run_res.criteria.include_groups))
            pr_info(f"Included groups: {groups_str}")
        if run_res.criteria.exclude_groups:
            groups_str = ", ".join(sorted(run_res.criteria.exclude_groups))
            pr_info(f"Excluded groups: {groups_str}")
        if run_res.criteria.require_groups:
            groups_str = ", ".join(sorted(run_res.criteria.require_groups))
            pr_info(f"Required groups: {groups_str}")
        pr_info("Running tests: {}\n".format(", ".join([x.name for x in tests])))

    def on_test_start(self, test: Xtest) -> None:
        name = short_str(test.name, 40)

        color = PrintColors.BOLD if colors_enabled() else ""
        print_str = f"{color}{name}{_reset_color()}"
        if self.show_summary:
            pr_info(print_str)
        else:  # normal mode
            print_str = f"{print_str:<60} ....... "
            pr_info(f"{print_str}", end='')
        pr_info("", end='', flush=True)

    def on_test_end(self, test: Xtest, test_res: TestResult) -> None:
        def _post_print_details(status_suffix: str = "", details: str = "") -> None:
            category = status_catgoery(test_res.status).value
            if colors_enabled():
                stts_str = f"{_STATUS_PRINT_INFO[test_res.status].color}{category}{_reset_color()}"
            else:
                stts_str = category
            msg = f"[{stts_str}]"
            if status_suffix:
                msg += f" {short_str(status_suffix, 30)}"
            if details:
                msg += f"\n{details}\n"
            pr_info(msg)

        details = ""
        status_suffix = ""
        if test_res.status == TestStatus.InitErr:
            status_suffix = "Init error"
            details = test_res.status_reason
        elif test_res.status == TestStatus.Skipped:
            details = test_res.status_reason
        elif test_res.status == TestStatus.PreRunErr:
            status_suffix = "Pre-test error"
            if test_res.pre_run_res is not None:
                details = test_res.pre_run_res.error_summary()
        elif test_res.status == TestStatus.RunErr:
            status_suffix = "Run error"
            details = test_res.status_reason
        elif test_res.status == TestStatus.Failed:
            if test_res.run_res is not None:
                details = test_res.run_res.error_summary()
        elif test_res.status == TestStatus.ExpectedFail:
            status_suffix = "Expected failure"
        elif test_res.status == TestStatus.UnexpectedPass:
            status_suffix = "Unexpected pass"
        elif test_res.status == TestStatus.Passed and \
                (not test_res.post_run_res.completed or test_res.post_run_res.failed):
            details = "NOTICE: Post-test failed\n"
            details += test_res.post_run_res.error_summary()
        _post_print_details(status_suffix, details)

    def on_iteration_end(self) -> None:
        assert isinstance(self.iter_res, IterationResult)
        assert isinstance(self.run_res, RunResult)

        def summarize_test_list(status: TestStatus) -> None:
            assert isinstance(self.iter_res, IterationResult)
            test_names = self.iter_res.status_results_summary[status]
            if not test_names:
                return
            status_print_info = _STATUS_PRINT_INFO[status]
            color = status_print_info.color if colors_enabled() else ""
            title = status_print_info.string
            test_list_str = ", ".join(test_names)
            pr_info(f"{color}{title}{_reset_color()}: {test_list_str}")

        pr_info()
        iter_n = self.iter_res.iter_n
        if self.run_res.iterations > 1:
            pr_info(f"\nIteration #{iter_n}/{self.run_res.iterations - 1} summary:")
        for status in TestStatus:
            summarize_test_list(status)
        pr_info()


_ORANGE = '\033[38;5;208m'
_pr_debug_title = create_print_func(_ORANGE, LogLevel.ALWAYS)


class CliDebugReporter(CliRunReporter):
    def __init__(self) -> None:
        super().__init__(show_summary=False)

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

    def on_test_end(self, test: Xtest, test_res: TestResult) -> None:
        _pr_debug_title(f"Test '{test.name}' ended. (status: {test_res.status}, "
                        f"duration: {test_res.duration:.3f}s)")

    def on_step_setup_start(self, test: Xtest, phase_name: str, step: XStep, step_index: int
                            ) -> None:
        text = self._step_title(step, phase_name, step_index, sentence_start=True)
        _pr_debug_title(f"{text} - setup")

    def on_step_start(self, test: Xtest, phase_name: str, step: XStep, step_index: int) -> None:
        title = self._step_title(step, phase_name, step_index, sentence_start=True)
        _pr_debug_title(f"{title} - staring run")

    def on_step_end(self, test: Xtest, phase_name: str, step: XStep, step_index: int,
                    step_res: XStepResult) -> None:
        text = self._step_title(step, phase_name, step_index, sentence_start=True)
        text += f" - run ended (completed, " if step_res.completed else f" (incomplete, "
        text += f"failed, " if step_res.failed else f"passed, "
        text += f"duration: {step_res.duration:.3f}s)"
        _pr_debug_title(text)

    def on_phase_start(self, test, phase_name: str, steps_count: int) -> None:
        if steps_count == 0:
            return
        _pr_debug_title(f"Starting {phase_name} phase run, {steps_count} step(s)")

    def on_phase_end(self, test, phase_name: str, steps_count: int) -> None:
        if steps_count == 0:
            return
        text = phase_name[0].upper() + phase_name[1:]
        _pr_debug_title(f"{text} phase ended")


def run_tests(conf: str,
              repeat: int,
              show_summary: bool,
              debug: bool,
              **kwargs) -> RunResult:
    criteria = TestCriteria(**kwargs)
    if debug:
        reporter = CliDebugReporter()
    else:
        reporter = CliRunReporter(show_summary=show_summary)
    return core.run_tests(conf, criteria, reporter, debug_mode=debug, iterations=repeat)


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
