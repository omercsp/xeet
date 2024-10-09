from dataclasses import dataclass
from xeet.pr import pr_dict, pr_info, PrintColors, colors_enabled
from xeet.xtest import Xtest, XtestModel, TestStatus, TestResult
from xeet.config import Config, ConfigModel, read_config_file, TestCriteria
from xeet.common import XeetException, update_global_vars
from xeet.log import log_info, log_blank, start_raw_logging, stop_raw_logging
from xeet.runtime import RunInfo
import textwrap
import os
import sys


def _show_test(test: Xtest, full_details: bool, expanded_cmds: bool) -> None:
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
        for count, (k, v) in enumerate(test.env.items()):
            print_blob(f"     [{count}]", f"{k}={v}")
    if test.cwd:
        print_blob("Working directory", _test_str(test.cwd))
    if test.groups:
        print_blob("Groups", ", ".join(test.groups))
    if test.pre_cmd:
        cmd = test.pre_cmd_expanded if expanded_cmds else test.pre_cmd
        shell_str = " (shell)" if test.pre_cmd_shell else ""
        print_blob(f"Pre-test command{shell_str}", _test_str(cmd))
    if test.cmd:
        cmd = test.cmd_expanded if expanded_cmds else test.cmd
        shell_str = " (shell)" if test.cmd_shell else ""
        print_blob(f"Test command{shell_str}", _test_str(cmd))
    if test.verify_cmd:
        cmd = test.verify_cmd_expanded if expanded_cmds else test.verify_cmd
        shell_str = " (shell)" if test.verify_cmd_shell else ""
        print_blob(f"Verification command{shell_str}", _test_str(cmd))
    if test.post_cmd:
        cmd = test.post_cmd_expanded if expanded_cmds else test.post_cmd
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
    if expand:
        _set_global_vars(conf, False)
    config = read_config_file(conf)
    xtest = config.xtest(test_name)
    if xtest is None:
        raise XeetException(f"No such test: {test_name}")
    if expand:
        xtest.expand()
    _show_test(xtest, True, expand)


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

    if not names_only:
        pr_info(print_fmt.format("Name", "Description"))
        pr_info(print_fmt.format("----", "-----------"))
    for test in tests:
        if test.init_err:
            error_str = _display_token(f"<error: {test.init_err}>", _error_max_str_len)
            name_str = _display_token(test.name, _max_name_print_len)
            pr_info(err_print_fmt.format(name_str, error_str))
            continue
        if names_only:
            pr_info(test.name, end=' ')
            continue

        pr_info(print_fmt.format(_display_token(test.name, _max_name_print_len),
                                 _display_token(test.short_desc, _max_desc_print_len)))


_status_color_map = {
    TestStatus.Passed: PrintColors.GREEN,
    TestStatus.Failed: PrintColors.RED,
    TestStatus.Skipped: PrintColors.RESET,
    TestStatus.Unexpected_pass: PrintColors.RED,
    TestStatus.Expected_failure: PrintColors.GREEN,
    TestStatus.Not_run: PrintColors.YELLOW,
}


def _status_color(status: TestStatus):
    return _status_color_map.get(status, "") if colors_enabled() else ""


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


def _post_run_print(res: TestResult, run_settings: RunSettings) -> None:
    if run_settings.debug_mode:
        pr_info("".center(50, '-'))
        if res.short_comment:
            pr_info(res.short_comment)
        for comment in res.extra_comments:
            pr_info(comment)
        pr_info("." * 50)
        pr_info()
        return

    msg = f"[{_status_color(res.status)}{res.status:<7}{_reset_color()}]"
    if res.short_comment:
        msg += f" {res.short_comment}"
    if res.status == TestStatus.Skipped and res.skip_reason:
        pr_info(res.skip_reason)
    pr_info(msg)
    for comment in res.extra_comments:
        pr_info(comment)
    if res.extra_comments:
        pr_info()


def _summarize_iter(run_info: RunInfo, iter_n: int,
                    show_successful: bool = False) -> None:
    def summarize_test_list(suffix: str, test_names: list[str], color: str = "") -> None:
        title = f"{suffix}"
        test_list_str = ", ".join(test_names)
        summary_str = "{}{}{}: {}"
        if not colors_enabled():
            color = ""
        pr_info(summary_str.format(color, title, _reset_color(), test_list_str))

        start_raw_logging()
        log_info(f"{title} {test_list_str}")
        stop_raw_logging()

    iter_info = run_info.iterations_info[iter_n]

    pr_info()
    log_info(f"Finished iteration (#{iter_n}/{run_info.iterations - 1})")
    if run_info.iterations > 1:
        pr_info(f"\nxeet iteration #{iter_n} summary:")

    if show_successful and iter_info.successful_tests:
        summarize_test_list("Passed", iter_info.successful_tests, PrintColors.GREEN)
    if iter_info.expected_failures:
        summarize_test_list("Expectedly failed", iter_info.expected_failures, PrintColors.GREEN)
    if iter_info.failed_tests:
        summarize_test_list("Failed", iter_info.failed_tests, PrintColors.RED)
    if iter_info.unexpected_pass:
        summarize_test_list("Unexpectedly passed", iter_info.unexpected_pass, PrintColors.RED)
    if iter_info.skipped_tests:
        summarize_test_list("Skipped", iter_info.skipped_tests)
    if iter_info.not_run_tests:
        summarize_test_list("Not ran", iter_info.not_run_tests, PrintColors.YELLOW)
    pr_info()


def _run_single_test(test: Xtest, settings: RunSettings) -> TestResult:
    if test.init_err:
        return TestResult(status=TestStatus.Not_run, short_comment=test.init_err)

    test.expand()
    if settings.show_summary:
        _show_test(test, full_details=False, expanded_cmds=True)
        sys.stdout.flush()
    return test.run()


def run_tests(config: Config, run_settings: RunSettings) -> RunInfo:
    log_info("Starting run", pr=pr_info, pr_suffix="------------\n")
    _set_global_vars(config.file_path, run_settings.debug_mode)
    criteria = run_settings.criteria
    if criteria.include_groups:
        log_info("Included groups: {}".format(", ".join(criteria.include_groups)))
    if criteria.exclude_groups:
        log_info("Excluded groups: {}".format(", ".join(criteria.exclude_groups)))
    if criteria.require_groups:
        log_info("Required groups: {}".format(", ".join(criteria.require_groups)))

    tests = config.xtests(run_settings.criteria)
    if not tests:
        raise XeetException("No tests to run")
    log_info(f"{run_settings.debug_mode=}")
    if run_settings.debug_mode:
        for test in tests:
            test.debug_mode = True

    log_info("Running tests: {}".format(", ".join([x.name for x in tests])), pr=pr_info)

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
        _summarize_iter(run_info, iter_n, show_successful=True)
    return run_info


def dump_test(config: Config, name: str) -> None:
    desc = config.test_desc(name)
    if desc is None:
        raise XeetException(f"No such test: {name}")
    pr_info(f"Test '{name}' descriptor:")
    pr_dict(desc, as_json=True)


def dump_config(config: Config) -> None:
    pr_info(config.model.model_dump_json(indent=4))


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
