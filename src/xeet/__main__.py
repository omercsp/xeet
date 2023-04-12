from xeet import XEET_BASE_VERSION
from xeet.xconfig import (XeetConfig, parse_arguments, RUN_CMD, LIST_CMD, INFO_CMD, DUMP_CONFIG_CMD,
                          DUMP_XTEST_CMD, DUMP_SCHEMA_CMD, GROUPS_CMD)
from xeet.xcommon import XeetException
from xeet.xlogging import init_logging, log_error
from xeet.xprint import pr_bright, set_no_color_print, XEET_RESET, XEET_RED
import xeet.xactions as xactions
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
            return xactions.run_xtest_list(config)
        elif config.main_cmd == LIST_CMD:
            xactions.list_xtests(config)
        elif config.main_cmd == GROUPS_CMD:
            xactions.list_groups(config)
        elif config.main_cmd == INFO_CMD:
            xactions.show_xtest_info(config)
        elif config.main_cmd == DUMP_CONFIG_CMD:
            xactions.dump_config(config)
        elif config.main_cmd == DUMP_XTEST_CMD:
            xactions.dump_xtest(args.test_name, config)
        elif config.main_cmd == DUMP_SCHEMA_CMD:
            xactions.dump_schema(config)

    except XeetException as e:
        print(f"{XEET_RESET}{XEET_RED}", end='', file=sys.stderr)
        log_error(f"xeet: {e}", pr=True, file=sys.stderr)
        print(XEET_RESET, file=sys.stderr)
        return 255
    return 0


if __name__ == "__main__":
    exit(xrun())
