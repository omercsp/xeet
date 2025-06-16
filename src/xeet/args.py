from xeet import xeet_version
from xeet.core.api import SchemaType
from xeet.core.driver import xeet_driver
from xeet.reporters import ConsolePrinterOpts
from enum import Enum
from .pr import pr_warn
import xeet.cli as actions
import argparse
import argcomplete
import os


class XeetCliCmds(str, Enum):
    Run = "run"
    ListTests = "list"
    ListGroups = "groups"
    Info = "info"
    Dump = "dump"


class XeetCliDumpTypes(str, Enum):
    Test = "test"
    Schema = "schema"
    Config = "config"


_DISPLAY_COMPONENTS = ConsolePrinterOpts.components()


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


def _non_negative_int_checker(value: str) -> int:
    ivalue = int(value)
    if ivalue < 0:
        raise argparse.ArgumentTypeError(
            f"{value} is an invalid positive int value. Must be non-negative.")
    return ivalue


def _token_list_complete(all_tokens: set[str], prefix: str) -> list[str]:
    if not prefix:
        return [f"{group}" for group in sorted(list(all_tokens))]
    parts = prefix.split(',')
    specified_tokens = set(parts[:-1])
    current_partial = parts[-1]
    base_prefix = ",".join(parts[:-1]) + ',' if specified_tokens else ""
    available_tokens = all_tokens - specified_tokens
    matches = [
        token for token in sorted(list(available_tokens))
        if token.startswith(current_partial)
    ]
    return [f"{base_prefix}{match}" for match in matches]


def _groups_complete(prefix, parsed_args, **_) -> list[str]:
    xeet_settings = actions.XeetSettings(parsed_args.conf)
    all_groups = set(xeet_driver(xeet_settings).all_groups)
    return _token_list_complete(all_groups, prefix)


def _tests_complete(prefix, parsed_args, **_) -> list[str]:
    xeet_settings = actions.XeetSettings(parsed_args.conf)
    all_tests = set(xeet_driver(xeet_settings).all_test_names)
    return _token_list_complete(all_tests, prefix)


def _display_component_complete(prefix, **_) -> list[str]:
    components = [f"+{c}" for c in _DISPLAY_COMPONENTS] + [f"-{c}" for c in _DISPLAY_COMPONENTS]
    return _token_list_complete(set(components), prefix)


Args = argparse.Namespace


def parse_arguments() -> Args:
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
                                    type=_tokens_list_type_checker, help='run tests in this group',
                                    dest='groups').completer = _groups_complete  # type: ignore
    test_filter_parser.add_argument('-G', '--require-group', metavar='GROUP', default=[],
                                    type=_tokens_list_type_checker,
                                    help='require tests to be in this group', dest='require_groups'
                                    ).completer = _groups_complete  # type: ignore
    test_filter_parser.add_argument('-X', '--exclude-group', metavar='GROUP', default=[],
                                    type=_tokens_list_type_checker,
                                    help='exclude tests in this group', dest='exclude_groups'
                                    ).completer = _groups_complete  # type: ignore
    test_filter_parser.add_argument('-t', '--test', metavar='TESTS', default=[],
                                    type=_tokens_list_type_checker, help='test name',
                                    dest='tests').completer = _tests_complete  # type: ignore
    test_filter_parser.add_argument('-T', '--exclude-test', metavar='TESTS', default=[],
                                    type=_tokens_list_type_checker, help='test name exclusion',
                                    dest='exclude_tests'
                                    ).completer = _tests_complete  # type: ignore
    test_filter_parser.add_argument('-z', '--fuzzy-test', metavar='NAME', default=[],
                                    type=_tokens_list_type_checker, help='fuzzy test name',
                                    dest='fuzzy_tests')
    test_filter_parser.add_argument('-Z', '--fuzzy-exclude-test', metavar='NAME', default=[],
                                    type=_tokens_list_type_checker,
                                    help='fuzzy test name exclusion', dest='fuzzy_exclude_tests')

    subparsers = parser.add_subparsers(help='commands', dest='subparsers_name')
    subparsers.required = True

    run_parser = subparsers.add_parser(XeetCliCmds.Run, help='run a test',
                                       parents=[common_parser, test_filter_parser])
    run_parser.add_argument('--debug', action='store_true', default=False,
                            help='run tests in debug mode')
    run_parser.add_argument('-r', '--repeat', metavar='COUNT', default=1, type=int,
                            help='repeat count')
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
    output_type_grp.add_argument('--quiet', action='store_const', const=actions.RunVerbosity.Quiet,
                                 help='quiet output', dest='run_verbosity')
    run_parser.set_defaults(run_verbosity=actions.RunVerbosity.Default)

    display_fields = ", ".join(_DISPLAY_COMPONENTS)
    run_parser.add_argument('--display', metavar='FIELDS', type=_display_type_checker,
                            default=([], []), help=f'display fields (available: {display_fields})'
                            ).completer = _display_component_complete  # type: ignore
    run_parser.add_argument('--full-timing', action='store_true', default=False,
                            help='show full test timing')
    run_parser.add_argument('-O', '--output-dir', metavar='DIR', default=None,
                            help='output directory for test results')

    mtrx_args_parser = argparse.ArgumentParser(add_help=False)
    mtrx_args_parser.add_argument('--no-matrix-tests', action='store_true', default=False,
                                  help="do not include matrix tests")
    mtrx_args_parser.add_argument('--show-permutations-tests', action='store_true', default=False,
                                  help="include matrix permutations tests")

    info_parser = subparsers.add_parser(XeetCliCmds.Info, help='show test info',
                                        parents=[common_parser, test_filter_parser,
                                                 mtrx_args_parser])
    info_parser.add_argument('-x', '--expand', action='store_true', default=False,
                             help='expand values')
    info_parser.add_argument('-f', '--full',  action='store_true', default=False,
                             help='full details')
    info_parser.add_argument('-p', '--permutation', default=-1, metavar='IDX',
                             type=_non_negative_int_checker,
                             help='matrix permutation to show info of (default to 0)')

    list_parser = subparsers.add_parser(XeetCliCmds.ListTests, help='list tests',
                                        parents=[common_parser, test_filter_parser,
                                                 mtrx_args_parser])
    list_parser.add_argument('-a', '--all', action='store_true', default=False,
                             help='show hidden tests and matrix tests')
    list_parser.add_argument('--names-only', action='store_true', default=False,
                             help=argparse.SUPPRESS)

    subparsers.add_parser(XeetCliCmds.ListGroups, parents=[common_parser], help='list groups')

    dump_parser = subparsers.add_parser(XeetCliCmds.Dump,
                                        help='dump a test, schema or configuration descriptor')
    dump_subparsers = dump_parser.add_subparsers(dest='dump_type', help='dump commands')
    dump_subparsers.required = True
    dump_test_parser = dump_subparsers.add_parser(XeetCliDumpTypes.Test, parents=[conf_file_parser],
                                                  help='dump test descriptor')
    dump_test_parser.add_argument("-t", "--test-name", required=True, help="test name")

    dump_schema_parser = dump_subparsers.add_parser(XeetCliDumpTypes.Schema, help='dump schema')
    dump_schema_parser.add_argument('-t', '--type', choices=[s.value for s in SchemaType],
                                    default=SchemaType.CONFIG.value, help='schema type')

    dump_config_parser = dump_subparsers.add_parser(XeetCliDumpTypes.Config, help='dump config',
                                                    parents=[conf_file_parser])
    dump_config_parser.add_argument('-p', '--path', default=None, help='dump path')

    argcomplete.autocomplete(parser, always_complete_options=False)
    args = parser.parse_args()

    if args.subparsers_name == XeetCliCmds.Info:
        args.all = True
    if args.subparsers_name != XeetCliCmds.Run:
        return args

    if args.jobs is None:
        args.jobs = os.cpu_count()
        if args.jobs is None or args.jobs < 1:
            pr_warn("Cannot determine number of processors, using 1")
            args.jobs = 1
    elif args.jobs <= 0:
        parser.error("number of jobs must be a positive integer")

    if args.tests and (args.groups or args.require_groups or args.exclude_groups):
        parser.error("test name and groups are mutually exclusive")
    if args.repeat < 1:
        parser.error("repeat count must be a psitive integer")

    if args.debug:
        if args.run_verbosity == actions.RunVerbosity.Quiet or \
                args.run_verbosity == actions.RunVerbosity.Verbose:
            parser.error(f"cannot use '--debug' with '--{args.run_verbosity.value}'")
        if args.display != ([], []):
            parser.error("cannot use '--debug' with '--display'")

    return args
