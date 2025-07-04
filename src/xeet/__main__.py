from xeet import xeet_version
from xeet.common import XeetException
from xeet.log import init_logging, log_error, log_info
from xeet.pr import *
from xeet.core.api import SchemaType
from xeet.core import TestsCriteria
from xeet.console_printer import ConsolePrinterTestTimingOpts, ConsoleDisplayOpts
import xeet.cli as actions

import os
import argparse
import argcomplete


_RUN_CMD = "run"
_LIST_CMD = "list"
_GROUPS_CMD = "groups"
_INFO_CMD = "info"
_DUMP_CMD = "dump"
_DUMP_TEST_CMD = "test"
_DUMP_SCHEMA_CMD = "schema"
_DUMP_CONFIG_CMD = "config"


_DISPLAY_COMPONENTS = ConsoleDisplayOpts.components()


def _display_type_checker(value: str) -> tuple[list[str], list[str]]:
    value = value.strip()
    if not value:
        raise argparse.ArgumentTypeError("display argument cannot be empty.")

    tokens = value.split(',')
    added = []
    removed = []

    for token in tokens:
        token = token.strip()
        if not token:
            continue

        if not token.startswith(('+', '-')):
            raise argparse.ArgumentTypeError(
                f"argument component '{token}' is missing a '+' or '-' prefix. "
                "Allowed formats are: +word, -word.")

        operator = token[0]
        word = token[1:]

        # 3. Check if the word is in the allowed list
        if word not in _DISPLAY_COMPONENTS:
            raise argparse.ArgumentTypeError(
                f"word '{word}' is not a valid choice. "
                f"Allowed words are: {', '.join(_DISPLAY_COMPONENTS)}"
            )

        if operator == '+':
            added.append(word)
        else:
            removed.append(word)
    return added, removed


def _tokens_list_type_checker(value: str) -> list[str]:
    value = value.strip()
    if not value:
        raise argparse.ArgumentTypeError("tokens list cannot be empty.")

    tokens = value.split(',')
    tokens = [token.strip() for token in tokens if token.strip()]
    if not tokens:
        raise argparse.ArgumentTypeError("tokens list cannot be empty.")
    return tokens


def _index_list_type_checker(value: str) -> set[int]:
    value = value.strip()
    if not value:
        raise argparse.ArgumentTypeError("index list cannot be empty.")

    tokens = value.split(',')
    indices = set()
    for token in tokens:
        token = token.strip()
        if not token.isdigit():
            raise argparse.ArgumentTypeError(f"'{token}' is not a valid index.")
        indices.add(int(token))
    return indices


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog='xeet')
    parser.add_argument('--version', action='version', version=f'v{xeet_version}')
    parser.add_argument('--no-colors', action='store_true', default=False, help='disable colors')

    conf_file_parser = argparse.ArgumentParser(add_help=False)
    conf_file_parser.add_argument('-c', '--conf', metavar='CONF', help='configuration file to use')

    common_parser = argparse.ArgumentParser(add_help=False, parents=[conf_file_parser])
    common_parser.add_argument('-v', '--log-verbosity', action='count',
                               help='log file verbosity', default=0)
    common_parser.add_argument('--log-file', metavar='FILE', default=None, help='set log file')

    test_filter_parser = argparse.ArgumentParser(add_help=False)
    test_filter_parser.add_argument('-g', '--group', metavar='GROUP', default=[],
                                    type=_tokens_list_type_checker, help='run tests in this group')
    test_filter_parser.add_argument('-G', '--require-group', metavar='GROUP', default=[],
                                    type=_tokens_list_type_checker,
                                    help='require tests to be in this group')
    test_filter_parser.add_argument('-X', '--exclude-group', metavar='GROUP', default=[],
                                    type=_tokens_list_type_checker,
                                    help='exclude tests in this group')
    test_filter_parser.add_argument('-t', '--test', metavar='TESTS', default=[],
                                    type=_tokens_list_type_checker, help='test name')
    test_filter_parser.add_argument('-T', '--exclude-test', metavar='TESTS', default=[],
                                    type=_tokens_list_type_checker, help='test name exclusion')
    test_filter_parser.add_argument('-z', '--fuzzy-test', metavar='NAME', default=[],
                                    type=_tokens_list_type_checker, help='fuzzy test name')
    test_filter_parser.add_argument('-Z', '--fuzzy-exclude-test', metavar='NAME', default=[],
                                    type=_tokens_list_type_checker,
                                    help='fuzzy test name exclusion')

    subparsers = parser.add_subparsers(help='commands', dest='subparsers_name')
    subparsers.required = True

    run_parser = subparsers.add_parser(_RUN_CMD, help='run a test',
                                       parents=[common_parser, test_filter_parser])
    run_parser.add_argument('--debug', action='store_true', default=False,
                            help='run tests in debug mode')
    run_parser.add_argument('-r', '--repeat', metavar='COUNT', default=1, type=int,
                            help='repeat count')
    run_parser.add_argument('-V', '--variable', metavar='VAR', default=[], action='append',
                            help='set a variable')
    run_parser.add_argument('-j', '--jobs', metavar='NUMBER', nargs='?', default=1, type=int,
                            help='number of jobs to use')
    run_parser.add_argument('--randomize', action='store_true', default=False)
    run_parser.add_argument('-p', '--permutations', default=set(), metavar='IDX',
                            type=_index_list_type_checker, help='matrix permutations to run')
    run_parser.add_argument('-P', '--no-permutations',  default=set(), metavar='IDX',
                            type=_index_list_type_checker, help='matrix permutations to exclude')
    output_type_grp = run_parser.add_mutually_exclusive_group()
    output_type_grp.add_argument('--concise', action='store_const',
                                 const=actions.RunVerbosity.Concise, help='concise output',
                                 dest='run_verbosity')
    output_type_grp.add_argument('--verbose', action='store_const',
                                 const=actions.RunVerbosity.Verbose, help='verbose output',
                                 dest='run_verbosity')
    output_type_grp.add_argument('--quiet', action='store_const',
                                 const=actions.RunVerbosity.Quiet, help='quiet output',
                                 dest='run_verbosity')
    run_parser.set_defaults(run_verbosity=actions.RunVerbosity.Default)

    display_fields = ", ".join(_DISPLAY_COMPONENTS)
    run_parser.add_argument('--display', metavar='FIELDS', type=_display_type_checker,
                            default=([], []), help=f'display fields (available: {display_fields})')
    run_parser.add_argument('--test-timing-type',
                            choices=[s.value for s in ConsolePrinterTestTimingOpts],
                            default=None, help='test timing verbosity')
    run_parser.add_argument('-O', '--output-dir', metavar='DIR', default=None,
                            help='output directory for test results')

    mtrx_args_parser = argparse.ArgumentParser(add_help=False)
    mtrx_args_parser.add_argument('--no-matrix-tests', action='store_true', default=False,
                                  help="do not include matrix tests")
    mtrx_args_parser.add_argument('--show-permutations-tests', action='store_true', default=False,
                                  help="include matrix permutations tests")
    info_parser = subparsers.add_parser(_INFO_CMD, help='show test info',
                                        parents=[common_parser, test_filter_parser,
                                                 mtrx_args_parser])
    info_parser.add_argument('-x', '--expand', action='store_true',
                             default=False, help='expand values')
    info_parser.add_argument('-f', '--full',  action='store_true', default=False,
                             help='full details')

    list_parser = subparsers.add_parser(_LIST_CMD, help='list tests',
                                        parents=[common_parser, test_filter_parser,
                                                 mtrx_args_parser])
    list_parser.add_argument('-a', '--all', action='store_true', default=False,
                             help='show hidden and matrix tests')
    list_parser.add_argument('--names-only', action='store_true', default=False,
                             help=argparse.SUPPRESS)

    subparsers.add_parser(_GROUPS_CMD, parents=[common_parser], help='list groups')

    dump_parser = subparsers.add_parser(_DUMP_CMD,
                                        help='dump a test, schema or configuration descriptor')
    dump_subparsers = dump_parser.add_subparsers(dest='dump_type', help='dump commands')
    dump_subparsers.required = True
    dump_test_parser = dump_subparsers.add_parser(_DUMP_TEST_CMD, parents=[conf_file_parser],
                                                  help='dump test descriptor')
    dump_test_parser.add_argument("-t", "--test-name", required=True, help="test name")

    dump_schema_parser = dump_subparsers.add_parser(_DUMP_SCHEMA_CMD, help='dump schema')
    dump_schema_parser.add_argument('-t', '--type', choices=[s.value for s in SchemaType],
                                    default=SchemaType.CONFIG.value, help='schema type')

    dump_config_parser = dump_subparsers.add_parser(_DUMP_CONFIG_CMD, help='dump config',
                                                    parents=[conf_file_parser])
    dump_config_parser.add_argument('-p', '--path', default=None, help='dump path')

    argcomplete.autocomplete(parser, always_complete_options=False)
    args = parser.parse_args()
    if args.subparsers_name == _RUN_CMD:
        if args.test and (args.group or args.require_group or args.exclude_group):
            parser.error("test name and groups are mutually exclusive")
        if args.repeat < 1:
            parser.error("repeat count must be a psitive integer")
        if args.jobs is None:
            args.jobs = os.cpu_count()
            if args.jobs is None or args.jobs < 1:
                pr_warn("Cannot determine number of processors, using 1")
                args.jobs = 1
        elif args.jobs <= 0:
            parser.error("number of jobs must be a positive integer")
    elif args.subparsers_name == _INFO_CMD:
        args.all = True
    return args


def _tests_criteria(args: argparse.Namespace, hidden: bool, mtrx: bool, prmttn: bool
                    ) -> TestsCriteria:
    return TestsCriteria(
        names=set(args.test),
        exclude_names=set(args.exclude_test),
        fuzzy_names=args.fuzzy_test,
        fuzzy_exclude_names=set(args.fuzzy_exclude_test),
        include_groups=set(args.group),
        require_groups=set(args.require_group),
        exclude_groups=set(args.exclude_group),
        hidden_tests=hidden,
        matrix_tests=mtrx,
        prmttn_tests=prmttn)


def _display_settings(args: argparse.Namespace) -> ConsoleDisplayOpts:
    opts = ConsoleDisplayOpts()
    if args.run_verbosity == actions.RunVerbosity.Concise:
        opts.set_concise()
    elif args.run_verbosity == actions.RunVerbosity.Verbose:
        opts.set_verbose()
    elif args.run_verbosity == actions.RunVerbosity.Quiet:
        opts.set_quiet()
    opts.set(args.display[0], args.display[1])
    return opts


def _run_settings(args: argparse.Namespace) -> actions.XeetRunSettings:
    #  We never run abastract and mtrix tests in run mode. We always run permutations
    criteria = _tests_criteria(args, hidden=False, mtrx=False, prmttn=True)
    criteria.prmttn_idxs_inc = args.permutations
    criteria.prmttn_idxs_exc = args.no_permutations
    return actions.XeetRunSettings(
        file_path=args.conf,
        criteria=criteria,
        output_dir=args.output_dir,
        debug=args.debug,
        iterations=args.repeat,
        jobs=args.jobs,
        randomize=args.randomize)


def xrun() -> int:
    args = parse_arguments()
    if args.no_colors:
        disable_colors()

    try:
        cmd_name = args.subparsers_name
        if cmd_name == _DUMP_CMD:
            if args.dump_type == _DUMP_SCHEMA_CMD:
                actions.dump_schema(args.type)
            elif args.dump_type == _DUMP_TEST_CMD:
                actions.dump_test(args.conf, args.test_name)
            elif args.dump_type == _DUMP_CONFIG_CMD:
                actions.dump_config(args.conf, args.path)
            return 0
        if args.log_file:
            init_logging("Xeet", args.log_file, args.log_verbosity)
        log_info(f"running command '{args.subparsers_name}'")
        log_info(f"CWD is '{os.getcwd()}'")
        if cmd_name == _RUN_CMD:
            return actions.run_tests(_run_settings(args), _display_settings(args))
        if cmd_name == _LIST_CMD:
            criteria = _tests_criteria(args, args.all, not args.no_matrix_tests,
                                       args.show_permutations_tests)
            actions.list_tests(args.conf, args.names_only, criteria)
        elif cmd_name == _GROUPS_CMD:
            actions.list_groups(args.conf)
        elif cmd_name == _INFO_CMD:
            criteria = _tests_criteria(args, args.all, not args.no_matrix_tests,
                                       args.show_permutations_tests)
            actions.show_test_info(args.conf, criteria, args.expand, args.full)
        else:
            raise XeetException(f"Unknown command '{cmd_name}'")
        return 0

    except XeetException as e:
        # flush the stdout buffer
        log_error(f"xeet: {e}")
        return 255


if __name__ == "__main__":
    exit(xrun())
