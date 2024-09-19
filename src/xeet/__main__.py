from xeet import xeet_version
from xeet.config import read_config_file, TestCriteria
from xeet.common import XeetException
from xeet.log import init_logging, log_error, log_info
from xeet.pr import pr_header, disable_colors
import xeet.actions as actions

import os
import argparse
import argcomplete


_RUN_CMD = "run"
_LIST_CMD = "list"
_GROUPS_CMD = "groups"
_INFO_CMD = "info"
_DUMP_CMD = "dump"
_DUMP_CONFIG_CMD = "dump_config"
_DUMP_SCHEMA_CMD = "dump_schema"
_YES_TOKEN = 'yes'
_NO_TOKEN = 'no'


def parse_arguments() -> argparse.Namespace:
    yes_no: list[str] = [_NO_TOKEN, _YES_TOKEN]

    parser = argparse.ArgumentParser(prog='xeet')
    parser.add_argument('--version', action='version', version=f'v{xeet_version}')
    parser.add_argument('--no-colors', action='store_true', default=False, help='disable colors')
    parser.add_argument('--no-splash', action='store_true',
                        default=False, help='don\'t show splash')

    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument('-v', '--verbose', action='count',
                               help='log file verbosity', default=0)
    common_parser.add_argument('-c', '--conf', metavar='CONF', help='configuration file to use')
    common_parser.add_argument('--log-file', metavar='FILE', help='set log file', default=None)

    test_groups_parser = argparse.ArgumentParser(add_help=False)
    test_groups_parser.add_argument('-g', '--group', metavar='GROUP', default=[], action='append',
                                    help='run tests in this group')
    test_groups_parser.add_argument('-G', '--require-group', metavar='GROUP', default=[],
                                    action='append', help='require tests to be in this group')
    test_groups_parser.add_argument('-X', '--exclude-group', metavar='GROUP', default=[],
                                    action='append', help='exclude tests in this group')

    subparsers = parser.add_subparsers(help='commands', dest='subparsers_name')
    subparsers.required = True

    run_parser = subparsers.add_parser(_RUN_CMD, help='run a test',
                                       parents=[common_parser, test_groups_parser])
    run_parser.add_argument('-t', '--test-names', metavar='TESTS', default=[],
                            help='test names', action='append')
    run_parser.add_argument('--debug', action='store_true', default=False,
                            help='run tests in debug mode')
    run_parser.add_argument('-r', '--repeat', metavar='COUNT', default=1, type=int,
                            help='repeat count')
    run_parser.add_argument('--cmd', metavar='CMD', default=None, help='set test command')
    run_parser.add_argument('--cwd', metavar='DIR', default=None, help='set test working directory')
    run_parser.add_argument('--shell', type=str, choices=yes_no, action='store', default=None,
                            help='set shell usage')
    run_parser.add_argument('--shell-path', metavar='PATH', help='set shell path', default=None)
    run_parser.add_argument('--env-file', metavar='FILE',
                            default=None, help='environment file path')
    run_parser.add_argument('--show-summary', action='store_true', default=False,
                            help='show test summary before run')
    run_parser.add_argument('-V', '--variable', metavar='VAR', default=[], action='append',
                            help='set a variable')

    info_parser = subparsers.add_parser(_INFO_CMD, help='show test info', parents=[common_parser])
    info_parser.add_argument('-t', '--test-name', metavar='TEST', default=None,
                             help='set test name', required=True)
    info_parser.add_argument('-x', '--expand', help='expand values', action='store_true',
                             default=False)

    dump_parser = subparsers.add_parser(_DUMP_CMD, help='dump a test',
                                        parents=[common_parser])
    dump_parser.add_argument('-t', '--test-name', metavar='TEST', default=None,
                             help='set test name', required=True)

    dump_parser.add_argument('-i', '--includes', help='with inclusions',
                             action='store_true', default=False)

    list_parser = subparsers.add_parser(_LIST_CMD, help='list tests',
                                        parents=[common_parser, test_groups_parser])
    list_parser.add_argument('-a', '--all', action='store_true', default=False,
                             help='show hidden tests')
    list_parser.add_argument('--names-only', action='store_true', default=False,
                             help=argparse.SUPPRESS)

    subparsers.add_parser(_GROUPS_CMD, help='list groups',
                          parents=[common_parser, test_groups_parser])
    dump_parser = subparsers.add_parser(_DUMP_SCHEMA_CMD, help='dump configuration file schema',
                                        parents=[common_parser])
    dump_parser.add_argument('-s', '--schema', choices=actions.DUMP_TYPES,
                             default=actions.DUMP_TYPES[0])

    subparsers.add_parser(_DUMP_CONFIG_CMD, help='dump configuration', parents=[common_parser])

    argcomplete.autocomplete(parser, always_complete_options=False)
    args = parser.parse_args()
    if args.subparsers_name == _RUN_CMD:
        if args.test_names and (args.group or args.require_group or args.exclude_group):
            parser.error("test name and groups are mutually exclusive")
        if args.repeat < 1:
            parser.error("repeat count must be a psitive integer")
    return args


def _gen_tests_list_criteria(args: argparse.Namespace) -> TestCriteria:
    if hasattr(args, "all"):
        all_tests = args.all
    else:
        all_tests = False
    if hasattr(args, "test_names"):
        test_names = args.test_names
    else:
        test_names = []
    return TestCriteria(test_names, args.group, args.require_group, args.exclude_group,
                        all_tests)


def _gen_run_settings(args: argparse.Namespace) -> actions.RunSettings:
    criteria = _gen_tests_list_criteria(args)
    return actions.RunSettings(iterations=args.repeat, show_summary=args.show_summary,
                               debug_mode=args.debug, criteria=criteria)


def xrun() -> int:
    args = parse_arguments()
    if args.no_colors:
        disable_colors()

    title = f"xeet, v{xeet_version}"
    if not args.no_splash:
        pr_header(f"{title}\n{'=' * len(title)}\n")
    try:
        if args.log_file:
            init_logging(title, args.log_file, args.verbose)
        log_info(f"Running command '{args.subparsers_name}'")
        log_info(f"CWD is '{os.getcwd()}'")
        cmd_name = args.subparsers_name
        if cmd_name == _DUMP_SCHEMA_CMD:
            actions.dump_schema(args.schema)
            return 0

        config = read_config_file(args.conf)
        if cmd_name == _RUN_CMD:
            run_info = actions.run_tests(config, _gen_run_settings(args))
            return 1 if run_info.had_bad_tests() else 0

        if cmd_name == _LIST_CMD:
            actions.list_tests(config, _gen_tests_list_criteria(args), args.names_only)
        elif cmd_name == _GROUPS_CMD:
            actions.list_groups(config)
        elif cmd_name == _INFO_CMD:
            actions.show_test_info(args.conf, args.test_name, args.expand)
        elif cmd_name == _DUMP_CONFIG_CMD:
            actions.dump_config(config)
        elif cmd_name == _DUMP_CMD:
            actions.dump_test(config, args.test_name)
        return 0

    except XeetException as e:
        log_error(f"xeet: {e}")
        return 255


if __name__ == "__main__":
    exit(xrun())
