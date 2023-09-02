from xeet.pr import XEET_GREEN, XEET_RED, XEET_YELLOW, XEET_WHITE, XEET_RESET, xeet_color_enabled
from xeet.xtest import (XTest, TestResult, XTEST_NOT_RUN, XTEST_PASSED, XTEST_FAILED,
                        XTEST_SKIPPED, XTEST_EXPECTED_FAILURE, XTEST_UNEXPECTED_PASS, GROUPS,
                        ABSTRACT, SHORT_DESC)

from xeet.config import Config, TestDesc
from xeet.common import print_dict, XeetException
from xeet.log import log_blank, log_info, start_raw_logging, stop_raw_logging
from xeet.runtime import RunInfo
import textwrap
import sys
from typing import Optional


def _prepare_tests_list(config: Config, runable: bool) -> list[TestDesc]:
    names = config.test_name_arg
    runnable_test_names = set(config.runnable_test_names())
    if names:
        ret = []
        for name in names:
            if name not in runnable_test_names:
                possible_names = [x for x in runnable_test_names if x.startswith(name)]
                if len(possible_names) == 0:
                    raise XeetException(f"No tests match '{name}'")
                if len(possible_names) > 1:
                    names_str = ", ".join(possible_names)
                    raise XeetException(f"Multiple tests match '{name}': {names_str}")
                name = possible_names[0]
            test_desc = config.get_test_desc(name)
            ret.append(test_desc)
        return ret
    include_groups = config.include_groups
    require_groups = config.require_groups
    exclude_groups = config.exclude_groups
    if runable:
        ret = config.runnable_descs()
    else:
        ret = config.descs
    if include_groups or require_groups or exclude_groups:
        def filter_desc(desc: TestDesc) -> bool:
            test_groups = desc.target_desc.get(GROUPS, [])
            if not test_groups:
                return False
            if include_groups and not include_groups.intersection(test_groups):
                return False
            if require_groups and not require_groups.issubset(test_groups):
                return False
            if exclude_groups and exclude_groups.intersection(test_groups):
                return False
            return True
        ret = [desc for desc in ret if filter_desc(desc)]
    return ret


def _show_test(test: XTest, full_details: bool) -> None:
    def print_val(title: str, value) -> None:
        print(f"{title:<24}{value:<}")

    def print_bool(title, value: bool) -> None:
        print_val(title, "Yes" if value else "No")

    def print_blob(title: str, text: str) -> None:
        if text is None or len(text) == 0:
            print(title)
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

    print_val("Test name:", test.name)
    if test.short_desc:
        print_val("Short description:", test.short_desc)
    if full_details:
        if test.long_desc:
            print_blob("Description:", test.long_desc)
        print_bool("Abstract:", test.abstract)
    print_bool("Use shell: ", test.shell)
    if test.shell:
        shell_title = "Shell path:"
        if test.shell_path:
            print_val(shell_title, test.shell_path)
        else:
            print_val(shell_title, "/usr/bin/sh")

    print_bool("Inherit environment", test.env_inherit)
    if test.env:
        print("Environment:")
        for count, (k, v) in enumerate(test.env.items()):
            print_blob(f"     [{count}]", f"{k}={v}")
    if test.cwd:
        print_blob("Working directory:", _test_str(test.cwd))

    if test.command:
        print_blob("Command (joined):", _test_str(" ".join(test.command)))


def show_test_info(config: Config) -> None:
    test_name = config.test_name_arg
    if not test_name:
        raise XeetException("No test name was specified")
    desc = config.get_test_desc(test_name)
    if desc is None:
        raise XeetException(f"No such xtest: {test_name}")
    test = XTest(desc, config)
    _show_test(test, True)


def list_groups(config: Config) -> None:
    for g in config.all_groups():
        print(g)


def list_tests(config: Config) -> None:
    def _display_token(token: Optional[str], max_len: int) -> str:
        if not token:
            return ""
        if len(token) < max_len:
            return token
        return f"{token[:max_len - 3]}..."

    _max_name_print_len = 40
    _max_desc_print_len = 65
    # 2 for spaces between description and flags
    _error_max_str_len = _max_desc_print_len + 2
    show_all: bool = config.args.all
    descs = _prepare_tests_list(config, runable=not show_all)
    names_only: bool = config.args.names_only
    log_info(f"Listing tests show_all={show_all} names_only={names_only}")
    #  This is hard to decipher, but '{{}}' is a way to escape a '{}'
    print_fmt = f"{{:<{_max_name_print_len}}}  {{}}"
    err_print_fmt = f"{{:<{_max_name_print_len}}}  {{}}"

    if not names_only:
        print(print_fmt.format("Name", "Description"))
        print(print_fmt.format("----", "-----------"))
    for desc in descs:
        if desc.error:
            error_str = _display_token(f"<error: {desc.error}>", _error_max_str_len)
            name_str = _display_token(desc.name, _max_name_print_len)
            print(err_print_fmt.format(name_str, error_str))
            continue
        abstract = desc.raw_desc.get(ABSTRACT, False)
        if not show_all and abstract:
            continue
        if names_only:
            print(desc.name, end=' ')
            continue

        short_desc = desc.raw_desc.get(SHORT_DESC, None)
        print(print_fmt.format(_display_token(desc.name, _max_name_print_len),
              _display_token(short_desc, _max_desc_print_len)))


__status_color_map = {
    XTEST_PASSED: XEET_GREEN,
    XTEST_FAILED: XEET_RED,
    XTEST_SKIPPED: XEET_RESET,
    XTEST_UNEXPECTED_PASS: XEET_RED,
    XTEST_EXPECTED_FAILURE: XEET_GREEN,
    XTEST_NOT_RUN: XEET_YELLOW,
}


def _status_color(status: int):
    return __status_color_map.get(status, "") if xeet_color_enabled() else ""


def _reset_color():
    return XEET_RESET if xeet_color_enabled() else ""


def _pre_run_print(name: str, config: Config) -> None:
    if config.debug_mode:
        return
    if len(name) > 40:
        name = f"{name[:37]}..."
    color = XEET_WHITE if xeet_color_enabled() else ""
    print_str = f"{color}{name}{_reset_color()}"
    if config.args.show_summary:
        print(print_str)
    else:  # normal mode
        print_str = f"{print_str:<60} ....... "
        print(f"{print_str}", end='')


__status_str_map = {
    XTEST_PASSED: "Passed",
    XTEST_FAILED: "Failed",
    XTEST_SKIPPED: "Skipped",
    XTEST_UNEXPECTED_PASS: "uxPass",
    XTEST_EXPECTED_FAILURE: "xFailed",
    XTEST_NOT_RUN: "Not Run",
}


def _post_run_print(res: TestResult, config: Config) -> None:
    if config.debug_mode:
        print("".center(50, '-'))
        if res.short_comment:
            print(res.short_comment)
        for comment in res.extra_comments:
            print(comment)
        print("." * 50)
        print()
        return

    status = res.status
    status_str = __status_str_map[status]
    msg = f"[{_status_color(status)}{status_str:<7}{_reset_color()}]"
    if res.short_comment:
        msg += f" {res.short_comment}"
    print(msg)
    for comment in res.extra_comments:
        print(comment)
    if res.extra_comments:
        print()


def _summarize_iter(run_info: RunInfo, iter_n: int,
                    show_succesful: bool = False) -> None:
    def summarize_test_list(suffix: str, test_names: list[str], color: str = "") -> None:
        title = f"{suffix}"
        test_list_str = ", ".join(test_names)
        summary_str = "{}{}{}: {}"
        if not xeet_color_enabled():
            color = ""
        print(summary_str.format(color, title, _reset_color(), test_list_str))

        start_raw_logging()
        log_info(f"{title} {test_list_str}")
        stop_raw_logging()

    iter_info = run_info.itearations_info[iter_n]

    print()
    log_info(f"Finished iteration (#{iter_n}/{run_info.iterations - 1})", pr=True)
    if run_info.iterations > 1:
        print(f"\nxeet iteration #{iter_n} summary:")

    if show_succesful and iter_info.successful_tests:
        summarize_test_list("Passed", iter_info.successful_tests, XEET_GREEN)
    if iter_info.expected_failures:
        summarize_test_list("Expectedly failed", iter_info.expected_failures, XEET_GREEN)
    if iter_info.failed_tests:
        summarize_test_list("Failed", iter_info.failed_tests, XEET_RED)
    if iter_info.unexpected_pass:
        summarize_test_list("Unexpectedly passed", iter_info.unexpected_pass, XEET_RED)
    if iter_info.skipped_tests:
        summarize_test_list("Skipped", iter_info.skipped_tests)
    if iter_info.not_run_tests:
        summarize_test_list("Not ran", iter_info.not_run_tests, XEET_YELLOW)
    print()


def _run_single_test(desc: TestDesc, config: Config) -> TestResult:
    ret = TestResult()
    if desc.error:
        ret.status = XTEST_NOT_RUN
        ret.short_comment = desc.error
        return ret

    test = XTest(desc, config)
    if config.args.show_summary:
        _show_test(test, full_details=False)
        sys.stdout.flush()
    test.run(ret)
    return ret


def run_test_list(config: Config) -> int:
    descs = _prepare_tests_list(config, runable=True)
    if not descs:
        raise XeetException("No tests to run")
    iterations = config.args.repeat
    if iterations < 1:
        raise XeetException(f"Invalid iteration count {iterations}")

    if iterations > 1:
        log_info(f"Starting run - {iterations} iteration", pr=True)
    else:
        log_info("Starting run", pr=True)
    include_groups = config.include_groups
    require_groups = config.require_groups
    exclude_groups = config.exclude_groups
    if include_groups:
        log_info("Included groups: {}".format(", ".join(sorted(include_groups))), pr=True)
    if require_groups:
        log_info("Required groups: {}".format(", ".join(sorted(require_groups))), pr=True)
    if exclude_groups:
        log_info("Excluding groups: {}".format(", ".join(sorted(exclude_groups))), pr=True)
    log_info("Running tests: {}".format(", ".join([x.name for x in descs])), pr=True)
    log_blank()
    print()

    run_info = RunInfo(iterations=iterations)

    for iter_n in range(iterations):
        if iterations > 1:
            log_info(f">>> Iteration {iter_n}/{iterations - 1}", pr=True)
        for desc in descs:
            _pre_run_print(desc.name, config)
            test_res = _run_single_test(desc, config)
            _post_run_print(test_res, config)
            run_info.add_test_result(desc.name, iter_n, test_res.status)
            log_blank()
        if config.debug_mode:
            continue
        _summarize_iter(run_info, iter_n, show_succesful=True)
    return 1 if run_info.failed else 0


def dump_test(name: str, config: Config) -> None:
    desc = config.get_test_desc(name)
    if desc is None:
        raise XeetException(f"No such test: {name}")
    print(f"Test '{name}' descriptor:")
    print_dict(desc.target_desc)


def dump_config(config: Config) -> None:
    print_dict(config.conf)


DUMP_CONFIG_SCHEMA = "config"
DUMP_UNIFIED_SCHEMA = "unfied"
DUMP_XTEST_SCHEMA = "test"


def dump_schema(dump_type: str) -> None:
    from xeet.xtest import TEST_SCHEMA
    from xeet.config import CONFIG_SCHEMA

    if dump_type == DUMP_CONFIG_SCHEMA:
        print_dict(CONFIG_SCHEMA)
    elif dump_type == DUMP_XTEST_SCHEMA:
        print_dict(TEST_SCHEMA)
    elif dump_type == DUMP_UNIFIED_SCHEMA:
        print_dict(CONFIG_SCHEMA)
