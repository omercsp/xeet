from xeet import XEET_BASE_VERSION
from xeet.config import (XeetConfig, parse_arguments, RUN_CMD, LIST_CMD, INFO_CMD, DUMP_CONFIG_CMD,
                         DUMP_XTEST_CMD, DUMP_SCHEMA_CMD, GROUPS_CMD)
from xeet.common import XeetException
from xeet.log import init_logging, log_error
from xeet.pr import pr_bright, set_no_color_print, XEET_RESET, XEET_RED
import xeet.actions as actions
import sys


def xrun() -> int:
    args = parse_arguments()
    if args.no_colors:
        set_no_color_print()

    if not args.no_splash:
        title = f"Xeet, v{XEET_BASE_VERSION}"
        pr_bright(f"{title}\n{'=' * len(title)}\n")

    try:
        init_logging(args.log_file, args.verbose)

        config = XeetConfig(args)
        if config.main_cmd == RUN_CMD:
            return actions.run_xtest_list(config)
        elif config.main_cmd == LIST_CMD:
            actions.list_xtests(config)
        elif config.main_cmd == GROUPS_CMD:
            actions.list_groups(config)
        elif config.main_cmd == INFO_CMD:
            actions.show_xtest_info(config)
        elif config.main_cmd == DUMP_CONFIG_CMD:
            actions.dump_config(config)
        elif config.main_cmd == DUMP_XTEST_CMD:
            actions.dump_xtest(args.test_name, config)
        elif config.main_cmd == DUMP_SCHEMA_CMD:
            actions.dump_schema(config)

    except XeetException as e:
        print(f"{XEET_RESET}{XEET_RED}", end='', file=sys.stderr)
        log_error(f"xeet: {e}", pr=True, file=sys.stderr)
        print(XEET_RESET, file=sys.stderr)
        return 255
    return 0


if __name__ == "__main__":
    exit(xrun())
