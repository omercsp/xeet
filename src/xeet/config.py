from xeet import XEET_BASE_VERSION
from xeet.common import (XeetException, StringVarExpander, set_xeet_var, set_xeet_vars,
                         validate_json_schema, dump_defualt_vars, dict_value,
                         XEET_NO_TOKEN, XEET_YES_TOKEN, NAME, GROUPS, ABSTRACT, BASE, ENV,
                         INHERIT_ENV, INHERIT_VARIABLES, INHERIT_GROUPS)
from xeet.log import log_info, logging_enabled_for
import os
import json
from typing import Optional, Any
import argparse
import logging
import argcomplete


RUN_CMD = "run"
LIST_CMD = "list"
GROUPS_CMD = "groups"
INFO_CMD = "info"
DUMP_XTEST_CMD = "dump"
DUMP_CONFIG_CMD = "dump_config"
DUMP_SCHEMA_CMD = "dump_schema"

DUMP_CONFIG_SCHEMA = "config"
DUMP_UNIFIED_SCHEMA = "unfied"
DUMP_XTEST_SCHEMA = "test"


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
    run_parser.add_argument('--env', metavar='ENV=VAL', default=None, action='append',
                            help='set an environment variable')
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
    dump_parser.add_argument('-s', '--schema',
                             choices=[DUMP_UNIFIED_SCHEMA, DUMP_CONFIG_SCHEMA, DUMP_XTEST_SCHEMA],
                             default=DUMP_UNIFIED_SCHEMA)

    subparsers.add_parser(DUMP_CONFIG_CMD, help='dump configuration')

    argcomplete.autocomplete(parser, always_complete_options=False)
    args = parser.parse_args()
    if args.subparsers_name == RUN_CMD and \
            args.test_name and \
            (args.group or args.require_group or args.exclude_group):
        parser.error("test name and groups are mutually exclusive")
    return args


class XTestDesc(object):
    def __init__(self, raw_desc: dict) -> None:
        self.name = raw_desc[NAME]
        self.error: str = ""
        self.raw_desc = raw_desc if raw_desc else {}
        self.target_desc = {}

    def target_desc_property(self, target: str, default=None) -> Any:
        return self.target_desc.get(target, default)


_SCHEMA = "$schema"
_INCLUDE = "include"
_TESTS = "tests"
_VARIABLES = "variables"
_DFLT_SHELL_PATH = "default_shell_path"


CONFIG_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        _SCHEMA: {
            "type": "string",
            "minLength": 1
        },
        _INCLUDE: {
            "type": "array",
            "items": {"type": "string", "minLength": 1}
        },
        _TESTS: {
            "type": "array",
            "items": {"type": "object"}
        },
        _VARIABLES: {"type": "object"},
        _DFLT_SHELL_PATH: {
            "type": "string",
            "minLength": 1
        },
    }
}


class XeetConfig(object):
    def __init__(self, args: argparse.Namespace) -> None:
        self.args: argparse.Namespace = args

        #  Dump scheme command doesn't require any configuration reading
        if self.main_cmd == DUMP_SCHEMA_CMD:
            return

        conf_path = args.conf
        if not conf_path:
            raise XeetException("Empty configuration file path")
        if os.path.isabs(conf_path):
            self.xeet_root = os.path.dirname(conf_path)
        else:
            conf_path = f"{os.getcwd()}/{conf_path}"
            self.xeet_root = os.path.dirname(conf_path)

        log_info(f"Using configuration file {conf_path}")

        #  Populate some variables early so they are available in
        self.xeet_root = os.path.dirname(conf_path)
        set_xeet_var("__cwd__", os.getcwd(), allow_system=True)
        set_xeet_var("__xroot__",  self.xeet_root, allow_system=True)
        set_xeet_var("__output_dir__", self.output_dir, allow_system=True)

        self.conf = {}
        self.conf = self._read_configuration(conf_path, set())
        conf_err = validate_json_schema(self.conf, CONFIG_SCHEMA)
        if conf_err:
            raise XeetException(f"Invalid configuration file '{conf_path}': {conf_err}")

        raw_xdescs = self.conf.get(_TESTS, [])
        self.raw_xtests_map = {}
        for raw_desc in raw_xdescs:
            name = raw_desc.get(NAME, None)
            if not name:
                log_info("Ignoring nameless test")
                continue
            self.raw_xtests_map[name] = raw_desc
        self.xdescs = []
        for raw_xdesc in raw_xdescs:
            xdesc = XTestDesc(raw_xdesc)
            self._solve_desc_inclusions(xdesc)
            self.xdescs.append(xdesc)
        self.xdescs_map = {xdesc.name: xdesc for xdesc in self.xdescs}

        set_xeet_vars(self.conf.get(_VARIABLES, {}))

        if logging_enabled_for(logging.DEBUG):
            dump_defualt_vars()

    def arg(self, name) -> Optional[Any]:
        if hasattr(self.args, name):
            return getattr(self.args, name)
        return None

    @property
    def output_dir(self) -> str:
        return f"{self.xeet_root}/xeet.out"

    @property
    def default_expected_output_dir(self) -> str:
        return f"{self.xeet_root}/xeet.expected"

    @property
    def main_cmd(self) -> str:
        return self.args.subparsers_name

    @property
    def expand_task(self) -> bool:
        return self.main_cmd == RUN_CMD or (self.main_cmd == INFO_CMD and self.args.expand)

    @property
    def schema_dump_type(self) -> Optional[str]:
        return self.arg("schema")

    @property
    def xtest_name_arg(self) -> Any:
        return self.arg("test_name")

    @property
    def include_groups(self) -> set[str]:
        groups = self.arg("group")
        return set(groups) if groups else set()

    @property
    def require_groups(self) -> set[str]:
        groups = self.arg("require_group")
        return set(groups) if groups else set()

    @property
    def exclude_groups(self) -> set[str]:
        groups = self.arg("exclude_group")
        return set(groups) if groups else set()

    @property
    def debug_mode(self) -> bool:
        return True if self.arg("debug") else False

    def all_groups(self) -> set[str]:
        ret = set()
        for xdesc in self.xdescs:
            ret.update(xdesc.target_desc_property(GROUPS, []))
        return ret

    def _read_configuration(self, file_path: str, read_files: set) -> dict:
        log_info(f"Reading configuration file {file_path}")
        try:
            orig_conf: dict = json.load(open(file_path, 'r'))
        except (IOError, TypeError, ValueError) as e:
            raise XeetException(f"Error parsing {file_path} - {e}")
        includes = orig_conf.get(_INCLUDE, [])
        conf = {}
        xtests = []
        variables = {}

        log_info(f"Configuration file includes: {includes}")
        read_files.add(file_path)
        expander = StringVarExpander()
        for f in includes:
            f = expander(f)
            if f in read_files:
                raise XeetException(f"Include loop detected - '{f}'")
            included_conf = self._read_configuration(f, read_files)
            xtests += included_conf[_TESTS]  # TODO
            variables.update(included_conf[_VARIABLES])
            conf.update(included_conf)
        read_files.remove(file_path)
        if _INCLUDE in conf:
            conf.pop(_INCLUDE)

        conf.update(orig_conf)
        xtests += (orig_conf.get(_TESTS, []))
        conf[_TESTS] = xtests  # TODO
        variables.update(orig_conf.get(_VARIABLES, {}))
        conf[_VARIABLES] = variables
        return conf

    def default_shell_path(self) -> Optional[str]:
        return self.setting(_DFLT_SHELL_PATH, None)

    def runnable_xtest_names(self) -> list[str]:
        return [desc.name for desc in self.xdescs
                if not desc.raw_desc.get(ABSTRACT, False)]

    def runnable_xdescs(self) -> list[XTestDesc]:
        return [desc for desc in self.xdescs
                if not desc.raw_desc.get(ABSTRACT, False)]

    #  Return anything. Types is forced by schema validations.
    def setting(self, path: str, default=None) -> Any:
        return dict_value(self.conf, path, default=default)

    def get_xtest_desc(self, name: str) -> Optional[XTestDesc]:
        return self.xdescs_map.get(name, None)

    def _solve_desc_inclusions(self, desc: XTestDesc) -> None:
        base_desc_name = desc.raw_desc.get(BASE, None)
        if not base_desc_name:
            desc.target_desc = desc.raw_desc
            return
        inclusions: dict[str, dict[str, Any]] = {desc.name: desc.raw_desc}
        inclusions_order: list[str] = [desc.name]
        while base_desc_name:
            if base_desc_name in inclusions:
                desc.error = f"Ihneritance loop detected for '{base_desc_name}'"
                return
            raw_base_desc = self.raw_xtests_map.get(base_desc_name, None)
            if not raw_base_desc:
                desc.error = f"no such base test '{base_desc_name}'"
                return
            inclusions[base_desc_name] = raw_base_desc
            inclusions_order.insert(0, base_desc_name)
            base_desc_name = raw_base_desc.get(BASE, None)

        for name in inclusions_order:
            raw_desc = inclusions[name]
            for k, v in raw_desc.items():
                if k == ENV and desc.target_desc.get(INHERIT_ENV, False):
                    desc.target_desc[k].update(v)
                    continue
                if k == _VARIABLES and \
                        desc.target_desc.get(INHERIT_VARIABLES, False):
                    desc.target_desc[k].update(v)
                    continue
                if k == GROUPS and desc.target_desc.get(INHERIT_GROUPS, False):
                    groups = set(desc.target_desc.get(GROUPS, []))
                    groups.update(raw_desc.get(GROUPS, []))
                    desc.target_desc[k] = list(groups)
                    continue
                if k == INHERIT_ENV or k == INHERIT_VARIABLES or \
                        k == ABSTRACT:
                    continue
                desc.target_desc[k] = v

        for k in (INHERIT_ENV, INHERIT_VARIABLES, INHERIT_GROUPS):
            if k in desc.target_desc:
                del desc.target_desc[k]
