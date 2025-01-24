from xeet.core.test import Test
from xeet.core.step import Step
from xeet.core import TestsCriteria
from xeet.core.result import EmptyRunResult
from xeet.pr import stdout, pr_warn
from .cli_printer import CliPrinter, DebugPrinter, CliPrinterVerbosity
import xeet.core.api as core
from xeet.pr import DictPrintType, pr_obj, pr_info
from xeet.common import XeetException, json_values, short_str, yes_no_str
from rich.live import Live
import textwrap
import shutil


_DFLT_WIDTH = 78


def _show_test(test: Test, full_details: bool, setup: bool) -> None:
    try:
        console_width = shutil.get_terminal_size().columns - 2
    except (AttributeError, OSError):
        console_width = _DFLT_WIDTH

    def print_val(title: str, value) -> None:
        title = f"{title}:"
        text = textwrap.fill(str(value), initial_indent=f"{title:<32} ", subsequent_indent=33 * " ",
                             width=console_width)
        pr_info(text)

    def print_step_list(title: str, steps: list[Step]) -> None:
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
    test = core.fetch_test(conf, test_name, setup=setup)
    if test is None:
        raise XeetException(f"No such test: {test_name}")
    if setup:
        test.setup()
    _show_test(test, full_details=full_details, setup=setup)


def list_groups(conf: str) -> None:
    pr_info(", ".join(core.fetch_groups_list(conf)))


def list_tests(conf: str, names_only: bool, criteria: TestsCriteria) -> None:
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


RunVerbosity = CliPrinterVerbosity


def run_tests(conf: str, repeat: int, debug: bool, randomize: bool, criteria: TestsCriteria,
              threads: int, verbosity: RunVerbosity, summary_only: bool) -> int:

    with Live(console=stdout(), refresh_per_second=4, transient=False) as live:
        if debug:
            reporter = DebugPrinter(live=live)
        else:
            reporter = CliPrinter(live=live, verbosity=verbosity, summary_only=summary_only)
        run_res = core.run_tests(conf, criteria, reporter, debug_mode=debug, iterations=repeat,
                                 randomize=randomize, threads=threads)
        if run_res is EmptyRunResult:
            pr_warn("No tests to run")
            return 0
        rc = 0
        if run_res.failed_tests:
            rc += 1
        if run_res.not_run_tests:
            rc += 2
        return rc


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
