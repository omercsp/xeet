from dataclasses import dataclass
from xeet.pr import pr_dict, pr_info, PrintColors, colors_enabled
from xeet.xtest import Xtest, XtestModel, TestStatus, TestResult, status_catgoery
from xeet.config import Config, ConfigModel, read_config_file, TestCriteria
from xeet.common import XeetException, update_global_vars, text_file_tail
from xeet.log import log_info, log_blank, start_raw_logging, stop_raw_logging
from xeet.runtime import RunInfo
import textwrap
import os
import sys


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

    if test.cmd_shell or test.pre_cmd_shell or test.post_cmd_shell:
        print_val("Shell path", test.shell_path)

    print_bool("Inherit OS environment", test.use_os_env)
    if test.env_file:
        print_val("Environment file", test.env_file)
    if test.env:
        pr_info("Environment")
        env_dict = test.env_expanded if expanded else test.env
        for count, (k, v) in enumerate(env_dict.items()):
            print_blob(f"     [{count}]", f"{k}={v}")
    if test.cwd:
        print_blob("Working directory", _test_str(test.cwd))
    if test.groups:
        print_blob("Groups", ", ".join(test.groups))
    if test.pre_cmd:
        cmd = test.pre_cmd_expanded if expanded else test.pre_cmd
        shell_str = " (shell)" if test.pre_cmd_shell else ""
        print_blob(f"Pre-test command{shell_str}", _test_str(cmd))
    if test.cmd:
        cmd = test.cmd_expanded if expanded else test.cmd
        shell_str = " (shell)" if test.cmd_shell else ""
        print_blob(f"Test command{shell_str}", _test_str(cmd))
    if test.verify_cmd:
        cmd = test.verify_cmd_expanded if expanded else test.verify_cmd
        shell_str = " (shell)" if test.verify_cmd_shell else ""
        print_blob(f"Verification command{shell_str}", _test_str(cmd))
    if test.post_cmd:
        cmd = test.post_cmd_expanded if expanded else test.post_cmd
        shell_str = " (shell)" if test.post_cmd_shell else ""
        print_blob(f"Post-test command{shell_str}", _test_str(cmd))


def _set_global_vars(conf_file_path: str, debug_mode: bool = False) -> None:
    root = os.path.dirname(conf_file_path)
    output_dir = os.path.join(root, "xeet.out")
    update_global_vars({
        f"CWD": os.getcwd(),
        f"ROOT": os.path.dirname(conf_file_path),
        f"OUTPUT_DIR": output_dir,
        f"DEBUG": "1" if debug_mode else "0",
    })


def show_test_info(conf: str, test_name: str, expand: bool) -> None:
    config = read_config_file(conf)
    if expand:
        _set_global_vars(config.file_path)
    xtest = config.xtest(test_name)
    if xtest is None:
        raise XeetException(f"No such test: {test_name}")
    if expand:
        xtest.expand()
    _show_test(xtest, full_details=True, expanded=expand)


def list_groups(config: Config) -> None:
    pr_info(", ".join(list(config.all_groups())))


def list_tests(config: Config, criteria: TestCriteria, names_only: bool) -> None:
    def _display_token(token: str | None, max_len: int) -> str:
        if not token:
            return ""
        if len(token) < max_len:
            return token
        return f"{token[:max_len - 3]}..."

    tests = config.xtests(criteria)

    _max_name_print_len = 40
    _max_desc_print_len = 65
    _error_max_str_len = _max_desc_print_len + 2  # 2 for spaces between description and flags
    log_info(f"Listing tests show_hidden={criteria.hidden_tests} names_only={names_only}")
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
    TestStatus.VerifyRunErr: _StatusPrintInfo(PrintColors.YELLOW, "Verification run error"),
    TestStatus.VerifyFailed: _StatusPrintInfo(PrintColors.RED, "Failed verification"),
    TestStatus.VerifyRcFailed: _StatusPrintInfo(PrintColors.RED, "Failed RC verification"),
    TestStatus.PreRunErr: _StatusPrintInfo(PrintColors.YELLOW, "Pre-run error"),
    TestStatus.RunErr: _StatusPrintInfo(PrintColors.YELLOW, "Run error"),
    TestStatus.Timeout: _StatusPrintInfo(PrintColors.RED, "Timeout"),
    TestStatus.UnexpectedPass: _StatusPrintInfo(PrintColors.RED, "Unexpected pass"),
    TestStatus.Skipped: _StatusPrintInfo(PrintColors.RESET, "Skipped"),
}


def _reset_color():
    return PrintColors.RESET if colors_enabled() else ""


@dataclass
class RunSettings:
    iterations: int
    debug_mode: bool
    show_summary: bool
    criteria: TestCriteria


def _pre_run_print(name: str, settings: RunSettings) -> None:
    if settings.debug_mode:
        return
    if len(name) > 40:
        name = f"{name[:37]}..."
    color = PrintColors.BOLD if colors_enabled() else ""
    print_str = f"{color}{name}{_reset_color()}"
    if settings.show_summary:
        pr_info(print_str)
    else:  # normal mode
        print_str = f"{print_str:<60} ....... "
        pr_info(f"{print_str}", end='')
    pr_info("", end='', flush=True)


def _status_category_str(status: TestStatus) -> str:
    category = status_catgoery(status).value
    if colors_enabled():
        return f"{_STATUS_PRINT_INFO[status].color}{category:<7}{_reset_color()}"
    return f"{category:<7}"


def _post_run_print(res: TestResult, run_settings: RunSettings) -> None:
    def _post_print_details(status_suffix: str = "", details: str = "") -> None:
        msg = f"[{_status_category_str(res.status)}]"
        if status_suffix:
            if len(status_suffix) < 30:
                msg += f" {status_suffix}"
            else:
                msg += f" {status_suffix[:27]}..."
        if details:
            msg += f"\n{details}\n"
        pr_info(msg)

    # First tuple element is the error message, second is the text to print
    def _file_tail_str(file_path: str | None, title: str, unified: bool = False) -> str:
        unified_str = " (unified)" if unified else ""
        if file_path is None:
            return f"no {title} flle path{unified_str}"

        if not os.path.exists(file_path):
            return f"no {title} flle at '{file_path}'{unified_str}"

        try:
            tail_text = text_file_tail(file_path)
        except OSError as e:
            return f"error reading {title} file at '{file_path}'{unified_str}: {e.strerror}"
        if len(tail_text) == 0:
            return f"empty {title} file{unified_str}"
        ret = f" {title} tail{unified_str} ".center(50, '-')
        ret += f"\n{tail_text}"
        ret += "-" * 50
        return ret

    def _test_output_tails() -> str:
        if res.unified_output:
            return _file_tail_str(res.stdout_file, "test output", True)
        return "\n".join([
            _file_tail_str(res.stdout_file, "test stdout"),
            "",
            _file_tail_str(res.stderr_file, "test stderr")])

    if run_settings.debug_mode:
        return

    details = ""
    status_suffix = ""
    if res.status == TestStatus.InitErr:
        status_suffix = "Malformed test"
        details = res.status_reason
    elif res.status == TestStatus.Skipped:
        status_suffix = res.status_reason
    elif res.status == TestStatus.PreRunErr:
        status_suffix = "Pre-test error"
        details = "\n".join([res.status_reason,
                             _file_tail_str(res.pre_test_output_file, "pre test output")])
    elif res.status == TestStatus.RunErr:
        status_suffix = "Run error"
        details = res.status_reason
    elif res.status == TestStatus.VerifyRcFailed:
        details = "\n".join([res.status_reason, _test_output_tails()])
    elif res.status == TestStatus.VerifyFailed:
        details = "\n".join([
            res.status_reason,
            _file_tail_str(res.verify_output_file, "verification output"),
        ])
    elif res.status == TestStatus.Timeout:
        status_suffix = f"timeout ({res.timeout_period}s)"
        details = _test_output_tails()
    elif res.status == TestStatus.ExpectedFail:
        status_suffix = "Expected failure"
    elif res.status == TestStatus.UnexpectedPass:
        status_suffix = "Unexpected pass"
        details = _test_output_tails()
    elif res.status == TestStatus.VerifyRunErr:
        details = res.status_reason
        details += _file_tail_str(res.verify_output_file, "verification output")
    elif res.status == TestStatus.Passed and not res.post_test_ok:
        details = "NOTICE: Post-test failed\n"
        details += _file_tail_str(res.post_test_output_file, "post test output")
    _post_print_details(status_suffix, details)


def _summarize_iter(run_info: RunInfo, iter_n: int) -> None:
    def summarize_test_list(status: TestStatus) -> None:
        test_names = run_info.iterations_info[iter_n][status]
        status_print_info = _STATUS_PRINT_INFO[status]
        color = status_print_info.color if colors_enabled() else ""
        title = status_print_info.string
        test_list_str = ", ".join(test_names)
        pr_info(f"{color}{title}{_reset_color()}: {test_list_str}")

        start_raw_logging()
        log_info(f"{title} {test_list_str}")
        stop_raw_logging()

    iter_info = run_info.iterations_info[iter_n]

    pr_info()
    log_info(f"Finished iteration (#{iter_n}/{run_info.iterations - 1})")
    if run_info.iterations > 1:
        pr_info(f"\nxeet iteration #{iter_n} summary:")
    for status in TestStatus:
        if not iter_info[status]:
            continue
        summarize_test_list(status)
    pr_info()


def _run_single_test(test: Xtest, settings: RunSettings) -> TestResult:
    if test.init_err:
        return TestResult(status=TestStatus.InitErr, status_reason=test.init_err)

    test.expand()
    if settings.show_summary:
        _show_test(test, full_details=False, expanded=True)
        sys.stdout.flush()
    test.debug_mode = settings.debug_mode
    return test.run()


def run_tests(config: Config, run_settings: RunSettings) -> RunInfo:
    log_info("Starting run", pr=pr_info, pr_suffix="------------\n")
    _set_global_vars(config.file_path, run_settings.debug_mode)
    criteria = run_settings.criteria
    if criteria.include_groups:
        groups_str = ", ".join(sorted(criteria.include_groups))
        log_info(f"Included groups: {groups_str}", pr=pr_info)
    if criteria.exclude_groups:
        groups_str = ", ".join(sorted(criteria.exclude_groups))
        log_info(f"Excluded groups: {groups_str}", pr=pr_info)
    if criteria.require_groups:
        groups_str = ", ".join(sorted(criteria.require_groups))
        log_info(f"Required groups: {groups_str}", pr=pr_info)

    tests = config.xtests(run_settings.criteria)
    if not tests:
        raise XeetException("No tests to run")

    log_info("Running tests: {}\n".format(", ".join([x.name for x in tests])), pr=pr_info)

    iterations = run_settings.iterations
    run_info = RunInfo(iterations=iterations)

    for iter_n in range(iterations):
        if iterations > 1:
            log_info(f">>> Iteration {iter_n}/{iterations - 1}")
        for test in tests:
            _pre_run_print(test.name, run_settings)
            test_res = _run_single_test(test, run_settings)
            _post_run_print(test_res, run_settings)
            run_info.add_test_result(test.name, iter_n, test_res)
            log_blank()
        if run_settings.debug_mode:
            continue
        _summarize_iter(run_info, iter_n)
    return run_info


def dump_test(config: Config, name: str) -> None:
    desc = config.test_desc(name)
    if desc is None:
        raise XeetException(f"No such test: {name}")
    pr_info(f"Test '{name}' descriptor:")
    pr_dict(desc, as_json=True)


_DUMP_CONFIG_SCHEMA = "config"
_DUMP_UNIFIED_SCHEMA = "unified"
_DUMP_XTEST_SCHEMA = "test"

DUMP_TYPES = [_DUMP_UNIFIED_SCHEMA, _DUMP_CONFIG_SCHEMA, _DUMP_XTEST_SCHEMA]


def dump_schema(dump_type: str) -> None:
    if dump_type == _DUMP_CONFIG_SCHEMA:
        d = ConfigModel.model_json_schema()
    elif dump_type == _DUMP_XTEST_SCHEMA:
        d = XtestModel.model_json_schema()
    elif dump_type == _DUMP_UNIFIED_SCHEMA:
        d = ConfigModel.model_json_schema()
        d["properties"]["tests"]["items"] = XtestModel.model_json_schema()
    else:
        raise XeetException(f"Invalid dump type: {dump_type}")
    pr_dict(d, as_json=True)
