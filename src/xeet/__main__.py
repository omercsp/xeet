from xeet import XEET_BASE_VERSION
from xeet.config import Config
from xeet.common import XeetException, XEET_NO_TOKEN, XEET_YES_TOKEN
from xeet.log import init_logging, log_error
from xeet.pr import pr_bright, set_no_color_print, XEET_RESET, XEET_RED
import xeet.actions as actions
import sys
import argparse
import argcomplete


RUN_CMD = "run"
LIST_CMD = "list"
GROUPS_CMD = "groups"
INFO_CMD = "info"
DUMP_XTEST_CMD = "dump"
DUMP_CONFIG_CMD = "dump_config"
DUMP_SCHEMA_CMD = "dump_schema"


def parse_arguments() -> argparse.Namespace:
    yes_no: list[str] = [XEET_NO_TOKEN, XEET_YES_TOKEN]

    parser = argparse.ArgumentParser(prog='xeet')
    parser.add_argument('--version', action='version', version=f'%(prog)s {XEET_BASE_VERSION}')
    parser.add_argument('--no-colors', action='store_true', default=False, help='disable colors')
    parser.add_argument('--no-splash', action='store_true',
                        default=False, help='don\'t show splash')

    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument('-v', '--verbose', action='count',
                               help='log file verbosity', default=0)
    common_parser.add_argument('-c', '--conf', metavar='CONF', help='configuration file to use',
                               default="xeet.json")
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

    run_parser = subparsers.add_parser(RUN_CMD, help='run a test',
                                       parents=[common_parser, test_groups_parser])
    run_parser.add_argument('-t', '--test-name', metavar='TESTS', default=[],
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

    info_parser = subparsers.add_parser(INFO_CMD, help='show test info', parents=[common_parser])
    info_parser.add_argument('-t', '--test-name', metavar='TEST', default=None,
                             help='set test name', required=True)
    info_parser.add_argument('-x', '--expand', help='expand values', action='store_true',
                             default=False)

    dump_parser = subparsers.add_parser(DUMP_XTEST_CMD, help='dump a test',
                                        parents=[common_parser])
    dump_parser.add_argument('-t', '--test-name', metavar='TEST', default=None,
                             help='set test name', required=True)

    dump_parser.add_argument('-i', '--includes', help='with inclusions',
                             action='store_true', default=False)

    list_parser = subparsers.add_parser(LIST_CMD, help='list tests',
                                        parents=[common_parser, test_groups_parser])
    list_parser.add_argument('-a', '--all', action='store_true', default=False,
                             help='show hidden and shadowed tests')
    list_parser.add_argument('--names-only', action='store_true', default=False,
                             help=argparse.SUPPRESS)

    subparsers.add_parser(GROUPS_CMD, help='list groups',
                          parents=[common_parser, test_groups_parser])

    dump_parser = subparsers.add_parser(DUMP_SCHEMA_CMD, help='dump configuration file schema',
                                        parents=[common_parser])
    dump_schema_choices = [
        actions.DUMP_UNIFIED_SCHEMA,
        actions.DUMP_CONFIG_SCHEMA,
        actions.DUMP_XTEST_SCHEMA]
    dump_parser.add_argument('-s', '--schema', choices=dump_schema_choices,
                             default=actions.DUMP_UNIFIED_SCHEMA)

    subparsers.add_parser(DUMP_CONFIG_CMD, help='dump configuration')

    argcomplete.autocomplete(parser, always_complete_options=False)
    args = parser.parse_args()
    if args.subparsers_name == RUN_CMD and \
            args.test_name and \
            (args.group or args.require_group or args.exclude_group):
        parser.error("test name and groups are mutually exclusive")
    return args


def xrun() -> int:
    args = parse_arguments()
    if args.no_colors:
        set_no_color_print()

    if not args.no_splash:
        title = f"Xeet, v{XEET_BASE_VERSION}"
        pr_bright(f"{title}\n{'=' * len(title)}\n")

    try:
        log_ok, err_msg = init_logging(args.log_file, args.verbose)
        if not log_ok:
            raise XeetException(err_msg)
        cmd_name = args.subparsers_name
        if cmd_name == DUMP_SCHEMA_CMD:
            actions.dump_schema(args.schema)
            return 0

        expand = cmd_name == RUN_CMD or (cmd_name == INFO_CMD and args.expand)
        config = Config(args, expand)
        if config.main_cmd == RUN_CMD:
            return actions.run_test_list(config)
        elif config.main_cmd == LIST_CMD:
            actions.list_tests(config)
        elif config.main_cmd == GROUPS_CMD:
            actions.list_groups(config)
        elif config.main_cmd == INFO_CMD:
            actions.show_test_info(config)
        elif config.main_cmd == DUMP_CONFIG_CMD:
            actions.dump_config(config)
        elif config.main_cmd == DUMP_XTEST_CMD:
            actions.dump_test(args.test_name, config)

    except XeetException as e:
        print(f"{XEET_RESET}{XEET_RED}", end='', file=sys.stderr)
        log_error(f"xeet: {e}", pr=True, file=sys.stderr)
        print(XEET_RESET, file=sys.stderr)
        return 255
    return 0


if __name__ == "__main__":
    exit(xrun())
