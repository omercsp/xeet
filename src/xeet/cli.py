from dataclasses import dataclass
from xeet.pr import pr_dict, pr_info, PrintColors, colors_enabled
from xeet.xtest import Xtest, TestStatus, TestResult, status_catgoery
from xeet.config import TestCriteria
from xeet.common import XeetException, short_str
from xeet.runtime import RunInfo, IterationInfo
import xeet.core as core
import textwrap


def _show_test(test: Xtest, full_details: bool, expanded: bool) -> None:
    def print_val(title: str, value) -> None:
        title = f"{title}:"
        pr_info(f"{title:<32}{value:<}")

    def print_bool(title, value: bool) -> None:
        print_val(title, "Yes" if value else "No")

    def print_blob(title: str, text: str) -> None:
        if text is None or len(text) == 0:
            pr_info(title)
            return
        first = True
        for line in text.split('\n'):
            for in_line in textwrap.wrap(line, width=80):

                if first:
                    print_val(title, in_line)
                    first = False
                    continue
                print_val("", in_line)

    def _test_str(cmd_str: str) -> str:
        if len(cmd_str.strip()) == 0:
            return "[n/a - empty string)]"
        return cmd_str

    print_val("Test name", test.name)
    if test.short_desc:
        print_val("Short description", test.short_desc)
    if full_details:
        if test.long_desc:
            print_blob("Description", test.long_desc)
        print_bool("Abstract", test.abstract)
    if test.init_err:
        print_blob("Initialization error", test.init_err)
        return
    if test.base:
        print_val("Base test", test.base)
    if test.pre_run_steps:
        for pre_step in test.pre_run_steps:
            print_blob("Step", pre_step.summary())

    #  if test.cmd_shell or test.pre_cmd_shell or test.post_cmd_shell:
    #      print_val("Shell path", test.shell_path)

    #  print_bool("Inherit OS environment", test.use_os_env)
    #  if test.env_file:
    #      print_val("Environment file", test.env_file)
    #  if test.env:
    #      pr_info("Environment")
    #      env_dict = test.env_expanded if expanded else test.env
    #      for count, (k, v) in enumerate(env_dict.items()):
    #          print_blob(f"     [{count}]", f"{k}={v}")
    #  if test.cwd:
    #      print_blob("Working directory", _test_str(test.cwd))
    #  if test.groups:
    #      print_blob("Groups", ", ".join(test.groups))
    #  if test.pre_cmd:
    #      cmd = test.pre_cmd_expanded if expanded else test.pre_cmd
    #      shell_str = " (shell)" if test.pre_cmd_shell else ""
    #      print_blob(f"Pre-test command{shell_str}", _test_str(cmd))
    #  if test.cmd:
    #      cmd = test.cmd_expanded if expanded else test.cmd
    #      shell_str = " (shell)" if test.cmd_shell else ""
    #      print_blob(f"Test command{shell_str}", _test_str(cmd))
    #  if test.verify_cmd:
    #      cmd = test.verify_cmd_expanded if expanded else test.verify_cmd
    #      shell_str = " (shell)" if test.verify_cmd_shell else ""
    #      print_blob(f"Verification command{shell_str}", _test_str(cmd))
    #  if test.post_cmd:
    #      cmd = test.post_cmd_expanded if expanded else test.post_cmd
    #      shell_str = " (shell)" if test.post_cmd_shell else ""
    #      print_blob(f"Post-test command{shell_str}", _test_str(cmd))


def show_test_info(conf: str, test_name: str, expand: bool) -> None:
    xtest = core.fetch_xtest(conf, test_name)
    if xtest is None:
        raise XeetException(f"No such test: {test_name}")
    if expand:
        xtest.expand()
    _show_test(xtest, full_details=True, expanded=expand)


def list_groups(conf: str) -> None:
    pr_info(", ".join(core.fetch_groups_list(conf)))


def list_tests(conf: str, criteria: TestCriteria, names_only: bool) -> None:
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
        pr_info(" ".join([test.name for test in tests if not test.init_err]))
        return

    pr_info(print_fmt.format("Name", "Description"))
    pr_info(print_fmt.format("----", "-----------"))
    for test in tests:
        if test.init_err:
            error_str = _display_token(f"<error: {test.init_err}>", _error_max_str_len)
            name_str = _display_token(test.name, _max_name_print_len)
            pr_info(err_print_fmt.format(name_str, error_str))
            continue
        pr_info(print_fmt.format(_display_token(test.name, _max_name_print_len),
                                 _display_token(test.short_desc, _max_desc_print_len)))


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


@dataclass
class CliRunSettings(core.RunSettings):
    show_summary: bool = False

    def on_run_start(self,  # pyright: ignore[reportIncompatibleMethodOverride]
                     run_info: RunInfo, **_) -> None:
        pr_info("Starting run\n------------")
        if self.criteria.include_groups:
            groups_str = ", ".join(sorted(self.criteria.include_groups))
            pr_info(f"Included groups: {groups_str}")
        if self.criteria.exclude_groups:
            groups_str = ", ".join(sorted(self.criteria.exclude_groups))
            pr_info(f"Excluded groups: {groups_str}")
        if self.criteria.require_groups:
            groups_str = ", ".join(sorted(self.criteria.require_groups))
            pr_info(f"Required groups: {groups_str}")
        pr_info("Running tests: {}\n".format(
            ", ".join([x.name for x in run_info.tests])))

    def on_test_enter(self,  # pyright: ignore[reportIncompatibleMethodOverride]
                      test: Xtest, **_) -> None:
        if self.debug_mode:
            return
        name = short_str(test.name, 40)

        color = PrintColors.BOLD if colors_enabled() else ""
        print_str = f"{color}{name}{_reset_color()}"
        if self.show_summary:
            pr_info(print_str)
        else:  # normal mode
            print_str = f"{print_str:<60} ....... "
            pr_info(f"{print_str}", end='')
        pr_info("", end='', flush=True)

    def on_test_end(self,  # pyright: ignore[reportIncompatibleMethodOverride]
                    result: TestResult,  **_) -> None:
        def _post_print_details(status_suffix: str = "", details: str = "") -> None:
            category = status_catgoery(result.status).value
            if colors_enabled():
                stts_str = f"{_STATUS_PRINT_INFO[result.status].color}{category}{_reset_color()}"
            else:
                stts_str = category
            msg = f"[{stts_str}]"
            if status_suffix:
                msg += f" {short_str(status_suffix, 30)}"
            if details:
                msg += f"\n{details}\n"
            pr_info(msg)

        if self.debug_mode:
            return

        details = ""
        status_suffix = ""
        if result.status == TestStatus.InitErr:
            status_suffix = "Init error"
            details = result.status_reason
        elif result.status == TestStatus.Skipped:
            status_suffix = result.status_reason
        elif result.status == TestStatus.PreRunErr:
            status_suffix = "Pre-test error"
            if result.pre_run_res is not None:
                details = result.pre_run_res.error_summary()
        elif result.status == TestStatus.RunErr:
            status_suffix = "Run error"
            details = result.status_reason
        elif result.status == TestStatus.Failed:
            if result.run_res is not None:
                details = result.run_res.error_summary()
        elif result.status == TestStatus.ExpectedFail:
            status_suffix = "Expected failure"
        elif result.status == TestStatus.UnexpectedPass:
            status_suffix = "Unexpected pass"
        elif result.status == TestStatus.Passed and \
                (not result.post_run_res.completed or result.post_run_res.failed):
            details = "NOTICE: Post-test failed\n"
            details += result.post_run_res.error_summary()
        _post_print_details(status_suffix, details)

    def on_iteration_end(self,  # pyright: ignore[reportIncompatibleMethodOverride]
                         iter_info: IterationInfo,
                         run_info: RunInfo,
                         **_) -> None:
        def summarize_test_list(status: TestStatus) -> None:
            test_names = iter_info.tests[status]
            if not test_names:
                return
            status_print_info = _STATUS_PRINT_INFO[status]
            color = status_print_info.color if colors_enabled() else ""
            title = status_print_info.string
            test_list_str = ", ".join(test_names)
            pr_info(f"{color}{title}{_reset_color()}: {test_list_str}")

        pr_info()
        iter_n = iter_info.iter_n
        if run_info.iterations > 1:
            pr_info(f"\nIteration #{iter_n}/{run_info.iterations - 1} summary:")
        for status in TestStatus:
            summarize_test_list(status)
        pr_info()


def run_tests(conf: str, run_settings: CliRunSettings) -> RunInfo:
    return core.run_tests(conf, run_settings)


def dump_test(conf_path: str, name: str) -> None:
    desc = core.fetch_test_desc(conf_path, name)
    if desc is None:
        raise XeetException(f"No such test: {name}")
    pr_info(f"Test '{name}' descriptor:")
    pr_dict(desc, as_json=True)


def dump_schema(dump_type: str) -> None:
    pr_dict(core.fetch_schema(dump_type), as_json=True)
