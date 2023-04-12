from xeet.xprint import (XEET_GREEN, XEET_RED, XEET_YELLOW, XEET_WHITE, XEET_RESET,
                         xeet_color_enabled)
from xeet.xschemas import XTestKeys
from xeet.xtest import (XTest, XTestResult, XTEST_NOT_RUN, XTEST_PASSED, XTEST_FAILED,
                        XTEST_SKIPPED, XTEST_EXPECTED_FAILURE, XTEST_UNEXPECTED_PASS)

from xeet.xconfig import (XeetConfig, XTestDesc, DUMP_CONFIG_SCHEMA, DUMP_XTEST_SCHEMA,
                          DUMP_UNIFIED_SCHEMA)
from xeet.xcommon import print_dict, XeetException
from xeet.xlogging import log_blank, log_info, start_raw_logging, stop_raw_logging
from xeet.xrun_info import XeetRunInfo
import textwrap
import sys
from typing import Optional


def _prepare_xtests_list(config: XeetConfig, runable: bool) -> list[XTestDesc]:
    names = config.xtest_name_arg
    if names:
        ret = []
        for name in names:
            xtest_desc = config.get_xtest_desc(name)
            if not xtest_desc:
                raise XeetException(f"No such test: {name}")
            ret.append(xtest_desc)
        return ret
    include_groups = config.include_groups
    require_groups = config.require_groups
    exclude_groups = config.exclude_groups
    if runable:
        ret = config.runnable_xdescs()
    else:
        ret = config.xdescs
    if include_groups or require_groups or exclude_groups:
        def filter_desc(desc: XTestDesc) -> bool:
            xtest_groups = desc.target_desc.get(XTestKeys.Groups, [])
            if not xtest_groups:
                return False
            if include_groups and not include_groups.intersection(xtest_groups):
                return False
            if require_groups and not require_groups.issubset(xtest_groups):
                return False
            if exclude_groups and exclude_groups.intersection(xtest_groups):
                return False
            return True
        ret = [xdesc for xdesc in ret if filter_desc(xdesc)]
    return ret


def _show_xtest(xtest: XTest, full_details: bool) -> None:
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

    def _xtest_str(cmd_str: str) -> str:
        if len(cmd_str.strip()) == 0:
            return "[n/a - empty string)]"
        return cmd_str

    print_val("Test name:", xtest.name)
    if xtest.short_desc:
        print_val("Short description:", xtest.short_desc)
    if full_details:
        if xtest.long_desc:
            print_blob("Description:", xtest.long_desc)
        print_bool("Abstract:", xtest.abstract)
    print_bool("Use shell: ", xtest.shell)
    if xtest.shell:
        shell_title = "Shell path:"
        if xtest.shell_path:
            print_val(shell_title, xtest.shell_path)
        else:
            print_val(shell_title, "/usr/bin/sh")

    print_bool("Inherit environment", xtest.env_inherit)
    if xtest.env:
        print("Environment:")
        for count, (k, v) in enumerate(xtest.env.items()):
            print_blob(f"     [{count}]", f"{k}={v}")
    if xtest.cwd:
        print_blob("Working directory:", _xtest_str(xtest.cwd))

    if xtest.command:
        print_blob("Command (joined):", _xtest_str(" ".join(xtest.command)))


def show_xtest_info(config: XeetConfig) -> None:
    xtest_name = config.xtest_name_arg
    if not xtest_name:
        raise XeetException("No xtest name was specified")
    xdesc = config.get_xtest_desc(xtest_name)
    if xdesc is None:
        raise XeetException(f"No such xtest: {xtest_name}")
    xtest = XTest(xdesc, config)
    _show_xtest(xtest, True)


def list_groups(config: XeetConfig) -> None:
    for g in config.all_groups():
        print(g)


def list_xtests(config: XeetConfig) -> None:
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
    xdescs = _prepare_xtests_list(config, runable=not show_all)
    names_only: bool = config.args.names_only
    log_info(f"Listing xtests show_all={show_all} names_only={names_only}")
    #  This is hard to decipher, but '{{}}' is a way to escape a '{}'
    print_fmt = f"{{:<{_max_name_print_len}}}  {{}}"
    err_print_fmt = f"{{:<{_max_name_print_len}}}  {{}}"

    if not names_only:
        print(print_fmt.format("Name", "Description"))
        print(print_fmt.format("----", "-----------"))
    for xdesc in xdescs:
        if xdesc.error:
            error_str = _display_token(f"<error: {xdesc.error}>", _error_max_str_len)
            name_str = _display_token(xdesc.name, _max_name_print_len)
            print(err_print_fmt.format(name_str, error_str))
            continue
        abstract = xdesc.raw_desc.get(XTestKeys.Abstract, False)
        if not show_all and abstract:
            continue
        if names_only:
            print(xdesc.name, end=' ')
            continue

        short_desc = xdesc.raw_desc.get(XTestKeys.ShortDesc, None)
        print(print_fmt.format(_display_token(xdesc.name, _max_name_print_len),
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


def _pre_run_print(name: str, config: XeetConfig) -> None:
    if len(name) > 40:
        name = f"{name[:37]}..."
    if config.debug_mode:
        print(f" Test '{name}' begin ".center(50, '-'))
        return
    color = XEET_WHITE if xeet_color_enabled() else ""
    print_str = f"Running {color}{name}{_reset_color()}"
    if config.args.show_summary:
        print(print_str)
    else:  # normal mode
        print_str = f"{print_str:<60} ......."
        print(f"{print_str}", end='')


__status_str_map = {
    XTEST_PASSED: "Passed",
    XTEST_FAILED: "Failed",
    XTEST_SKIPPED: "Skipped",
    XTEST_UNEXPECTED_PASS: "uxPass",
    XTEST_EXPECTED_FAILURE: "xFailed",
    XTEST_NOT_RUN: "Not Run",
}


def _post_run_print(test_name: str, res: XTestResult, config: XeetConfig) -> None:
    if config.debug_mode:
        print(f" Test '{test_name}' end, RC={res.rc} ".center(50, '-'))
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


def _summarize_iter(run_info: XeetRunInfo, iter_n: int,
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


def _run_single_xtest(desc: XTestDesc, config: XeetConfig) -> XTestResult:
    if desc.error:
        return XTestResult(None, XTEST_NOT_RUN, comment=desc.error)
    xtest = XTest(desc, config)
    if config.args.show_summary:
        _show_xtest(xtest, full_details=False)
        sys.stdout.flush()

    return xtest.run()


def run_xtest_list(config: XeetConfig) -> int:
    descs = _prepare_xtests_list(config, runable=True)
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
    if include_groups or require_groups or exclude_groups:
        if include_groups:
            log_info("Running groups: {}".format(", ".join(sorted(include_groups))), pr=True)
        if require_groups:
            log_info("Required groups: {}".format(", ".join(sorted(require_groups))), pr=True)
        if exclude_groups:
            log_info("Excluding groups: {}".format(", ".join(sorted(exclude_groups))), pr=True)
    else:
        log_info("Running tests: {}".format(", ".join(config.xtests_base_run_list)), pr=True)
    log_blank()
    print()

    run_info = XeetRunInfo(iterations=iterations)

    for iter_n in range(iterations):
        if iterations > 1:
            log_info(f">>> Iteration {iter_n}/{iterations - 1}", pr=True)
        for desc in descs:
            _pre_run_print(desc.name, config)
            test_res = _run_single_xtest(desc, config)
            _post_run_print(desc.name, test_res, config)
            run_info.add_test_result(desc.name, iter_n, test_res.status)
            log_blank()
        if config.debug_mode:
            continue
        _summarize_iter(run_info, iter_n, show_succesful=True)
    return 1 if run_info.failed else 0


def dump_xtest(name: str, config: XeetConfig) -> None:
    xdesc = config.get_xtest_desc(name)
    if xdesc is None:
        raise XeetException(f"No such xtest: {name}")
    print(f"Test '{name}' descriptor:")
    print_dict(xdesc.target_desc)


def dump_config(config: XeetConfig) -> None:
    print_dict(config.conf)


def dump_schema(config: XeetConfig) -> None:
    from xeet.xschemas import XEET_CONFIG_SCHEMA, XTEST_SCHEMA
    dump_type = config.schema_dump_type

    if dump_type == DUMP_CONFIG_SCHEMA:
        print_dict(XEET_CONFIG_SCHEMA)
    elif dump_type == DUMP_XTEST_SCHEMA:
        print_dict(XTEST_SCHEMA)
    elif dump_type == DUMP_UNIFIED_SCHEMA:
        print_dict(XEET_CONFIG_SCHEMA)