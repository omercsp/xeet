from xeet.core.test import Test
from xeet.core.step import Step
from xeet.core import TestsCriteria
from xeet.core.driver import XeetSettings, _XeetDriver
from xeet.core.matrix import Matrix
from xeet.pr import stdout
from xeet.log import log_verbose
from xeet.reporters import (ConsolePrinter, ConsoleDebugPrinter, ConsoleReporterVerbosity,
                            BaseConsoleReporterOpts, ConsolePrinterOpts)
from xeet.core.api import XeetRunSettings
import xeet.core.api as core
from xeet.pr import DictPrintType, pr_obj, pr_info
from xeet.common import XeetException, json_values, short_str, yes_no_str
from rich.live import Live
from rich.markup import escape
import textwrap
import shutil
import sys


_DFLT_WIDTH = 78


def _console_width(no_wrap: bool) -> int:
    # Wrap only when writing to a terminal. Piped or redirected output is never wrapped, so it
    # doesn't depend on the terminal size or on the length of the printed paths.
    if no_wrap or not sys.stdout.isatty():
        return sys.maxsize
    try:
        return shutil.get_terminal_size().columns - 2
    except (AttributeError, OSError):
        return _DFLT_WIDTH


#  Returns the test's fixtures names, marking undefined or invalid ones
def _fixtures_info(driver: _XeetDriver, test: Test) -> str:
    ret = []
    for name in test.model.fixture_list():
        fixture = driver.fixture(name)
        if fixture is None:
            ret.append(f"{name} <undefined>")
        elif fixture.error:
            ret.append(f"{name} <error: {fixture.error}>")
        else:
            ret.append(name)
    return ", ".join(ret)


def _show_test(test: Test, full_details: bool, no_wrap: bool, fixtures: str = "") -> None:
    console_width = _console_width(no_wrap)

    def print_val(title: str, value, break_lines: bool = True) -> None:
        title = f"{title}:"
        lines = value.splitlines() if break_lines and isinstance(value, str) else [str(value)]
        for enum, line in enumerate(lines):
            if enum == 0:
                title = f"{title:<32}"
            else:
                title = " " * 32
            text = textwrap.fill(str(line), initial_indent=f"{title:<32} ",
                                 subsequent_indent=33 * " ", width=console_width)
            pr_info(escape(text))

    def print_step_list(title: str, steps: list[Step]) -> None:
        if not steps:
            if full_details:
                print_val(title, "<empty list>")
            return
        pr_info(f"{title}:")
        for count, step in enumerate(steps):
            details = step.details(full=full_details, printable=True)
            first_line = True
            for k, v in details.items():
                if first_line:
                    print_val(f" - [{count}] {k}", v)
                    first_line = False
                else:
                    print_val(f"       {k}", v)

    if test.error:
        print(f"{test.name} initialization error: {test.error}")
        return
    print_val("Name", test.name)
    if test.model.short_desc:
        print_val("Short description", test.model.short_desc)
    if test.model.long_desc:
        print_val("Description", test.model.long_desc, break_lines=False)
    if test.model.abstract:
        print_val("Abstract", yes_no_str(test.model.abstract))
    if test.model.groups:
        print_val("Groups", ", ".join(test.model.groups))
    if fixtures:
        print_val("Fixtures", fixtures)
    if test.model.matrix:
        print("Matrix:")
        for k, v in test.model.matrix.items():
            print_val(f" - {k}", v)
    if test.model.prmttn:
        print("Matrix Premutation:")
        for k, v in test.model.prmttn.items():
            print_val(f" - {k}", v)

    print_step_list("Pre-run steps", test.pre_phase.steps)
    print_step_list("Run steps", test.main_phase.steps)
    print_step_list("Post-run steps", test.post_phase.steps)


def show_test_info(conf: str, criteria: TestsCriteria, setup: bool, full_details: bool,
                   permutation: int = -1, no_wrap: bool = False) -> None:
    driver = core.xeet_driver(XeetSettings(conf))
    tests = driver.fetch_tests(criteria)
    if len(tests) == 0:
        raise XeetException("No tests found")
    for t in tests:
        t.build_steps()

    if not driver.matrix.empty:
        global_prmttns = driver.matrix.permutations_list()
        global_prmttn_idx = permutation if permutation >= 0 else (0 if setup else -1)
        if global_prmttn_idx >= 0:
            if global_prmttn_idx >= len(global_prmttns):
                raise XeetException(f"Matrix permutation index {global_prmttn_idx} out of range")
            driver.rti.set_matrix_prmttn(global_prmttn_idx, global_prmttns[global_prmttn_idx])
    elif permutation >= 0:
        raise XeetException("Configuration has no global matrix")

    for t in tests:
        if t.model.matrix and not t.model.prmttn:
            matrix = Matrix(t.model.matrix)
            if matrix.prmttns_count:
                t.set_matrix_prmttn(0, matrix.permutations_list()[0], matrix.prmttns_count)

    if setup:
        for t in tests:
            t.setup(setup_steps=True)
    for i, test in enumerate(tests):
        if i > 0:
            pr_info("-" * 80)
        _show_test(test, full_details=full_details, no_wrap=no_wrap,
                   fixtures=_fixtures_info(driver, test))


def list_groups(conf: str) -> None:
    pr_info(", ".join(core.fetch_groups(conf)))


def list_tests(conf: str, names_only: bool, criteria: TestsCriteria) -> None:
    def _display_token(token: str | None, max_len: int) -> str:
        if not token:
            return ""
        return short_str(token, max_len)

    log_verbose(f"Fetch tests list cirteria: {criteria}")
    tests = core.fetch_tests(conf, criteria)

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


RunVerbosity = ConsoleReporterVerbosity


def run_tests(conf_path: str, run_settings: XeetRunSettings, display_opts: BaseConsoleReporterOpts
              ) -> int:
    settings = XeetSettings(conf_path)
    with Live(console=stdout(), refresh_per_second=4, transient=False) as live:
        if run_settings.debug:
            settings.reporters.append(ConsoleDebugPrinter(display=display_opts))
        else:
            assert type(display_opts) is ConsolePrinterOpts
            settings.reporters.append(ConsolePrinter(live=live, display=display_opts))
        run_res = core.run_tests(settings, run_settings)
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
    pr_obj(core.fetch_schema(dump_type), print_type=DictPrintType.JSON, pr_markup=False)


def dump_config(file_path: str, json_path: str) -> None:
    obj = core.fetch_config(file_path)
    if json_path:
        obj = json_values(obj, json_path)
        if not obj:
            raise XeetException(f"Path not found '{json_path}'")
        if len(obj) == 1:
            obj = obj[0]
    pr_obj(obj, print_type=DictPrintType.YAML)
