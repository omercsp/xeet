from xeet.common import print_dict
import jsonschema
from typing import Optional


def _validate_json_schema(data: dict, schema: dict) -> Optional[str]:
    try:
        jsonschema.validate(data, schema)
        return None
    except jsonschema.ValidationError as e:
        if e.absolute_path:
            path = "/".join(str(v) for v in list(e.absolute_path))
            return f"Schema validation error at '{path}': {e.message}"
        else:
            return f"Schema validation error: {e.message}"


VARIABLES = "variables"

SCHEMA = "$schema"
INCLUDE = "include"
TESTS = "tests"
DFLT_SHELL_PATH = "default_shell_path"


_CONFIG_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        SCHEMA: {
            "type": "string",
            "minLength": 1
        },
        INCLUDE: {
            "type": "array",
            "items": {"type": "string", "minLength": 1}
        },
        TESTS: {
            "type": "array",
            "items": {"type": "object"}
        },
        VARIABLES: {"type": "object"},
        DFLT_SHELL_PATH: {
            "type": "string",
            "minLength": 1
        },
    }
}


def validate_config_schema(config):
    return _validate_json_schema(config, _CONFIG_SCHEMA)


GROUPS = "groups"
NAME = "name"
ABSTRACT = "abstract"
SHORT_DESC = "short_desc"
BASE = "base"
ENV = "env"
INHERIT_ENV = "inherit_env"
INHERIT_VARIABLES = "inherit_variables"
INHERIT_GROUPS = "inherit_groups"
SHELL = "shell"
SHELL_PATH = "shell_path"
INHERIT_OS_ENV = "inherit_os_env"
CWD = "cwd"
SKIP = "skip"
SKIP_REASON = "skip_reason"
LONG_DESC = "description"
TEST_COMMAND = "test_cmd"
ALLOWED_RC = "allowed_return_codes"
EXPECTED_FAILURE = "expected_failure"
PRE_TEST_CMD = "pre_test_cmd"
PRE_TEST_CMD_SHELL = "pre_test_cmd_shell"
VERIFY_CMD = "verify_cmd"
VERIFY_CMD_SHELL = "verify_cmd_shell"
POST_TEST_CMD = "post_test_cmd"
POST_TEST_CMD_SHELL = "post_test_cmd_shell"
OUTPUT_BEHAVIOR = "output_behavior"
TIMEOUT = "timeout"
ENV_FILE = "env_file"

# Output behavior values
UNIFY = "unify"
SPLIT = "split"

_COMMAND_SCHEMA = {
    "anyOf": [
        {"type": "string", "minLength": 1},
        {"type": "array", "items": {"type": "string", "minLength": 1}}
    ]
}

_ENV_SCHEMA = {
    "type": "object",
    "additionalProperties": {
        "type": "string"
    }
}


def validate_env_schema(xtest):
    return _validate_json_schema(xtest, _ENV_SCHEMA)


_XTEST_SCHEMA = {
    "type": "object",
    "properties": {
        NAME: {"type": "string", "minLength": 1},
        BASE: {"type": "string", "minLength": 1},
        SHORT_DESC: {"type": "string", "maxLength": 75},
        LONG_DESC: {"type": "string"},
        GROUPS: {
            "type": "array",
            "items": {"type": "string", "minLength": 1}
        },
        TEST_COMMAND: _COMMAND_SCHEMA,
        ALLOWED_RC: {
            "type": "array",
            "items": {"type": "integer", "minimum": 0, "maximum": 255}
        },
        TIMEOUT: {
            "type": "integer",
            "minimum": 0
        },
        PRE_TEST_CMD: _COMMAND_SCHEMA,
        PRE_TEST_CMD_SHELL: {"type": "boolean"},
        POST_TEST_CMD: _COMMAND_SCHEMA,
        POST_TEST_CMD_SHELL: {"type": "boolean"},
        VERIFY_CMD: _COMMAND_SCHEMA,
        VERIFY_CMD_SHELL: {"type": "boolean"},
        EXPECTED_FAILURE: {"type": "boolean"},
        OUTPUT_BEHAVIOR: {"enum": [UNIFY, SPLIT]},
        CWD: {"type": "string", "minLength": 1},
        SHELL: {"type": "boolean"},
        SHELL_PATH: {"type": "string", "minLength": 1},
        ENV: _ENV_SCHEMA,
        ENV_FILE: {"type": "string", "minLength": 1},
        INHERIT_OS_ENV: {"type": "boolean"},
        INHERIT_ENV: {"type": "boolean"},
        ABSTRACT: {"type": "boolean"},
        SKIP: {"type": "boolean"},
        SKIP_REASON: {"type": "string"},
        VARIABLES: {"type": "object"},
        INHERIT_VARIABLES: {"type": "boolean"},
        INHERIT_GROUPS: {"type": "boolean"}
    },
    "additionalProperties": False,
    "required": [NAME]
}


def validate_xtest_schema(xtest):
    return _validate_json_schema(xtest, _XTEST_SCHEMA)


__ALL__ = [SCHEMA, INCLUDE, TESTS, DFLT_SHELL_PATH,
           GROUPS, NAME, ABSTRACT, SHORT_DESC, BASE, ENV, INHERIT_ENV, INHERIT_VARIABLES,
           INHERIT_GROUPS, VARIABLES, SHELL, SHELL_PATH, INHERIT_OS_ENV, CWD, SKIP, SKIP_REASON,
           LONG_DESC, TEST_COMMAND, ALLOWED_RC, EXPECTED_FAILURE, PRE_TEST_CMD, PRE_TEST_CMD_SHELL,
           VERIFY_CMD, VERIFY_CMD_SHELL, POST_TEST_CMD, POST_TEST_CMD_SHELL, OUTPUT_BEHAVIOR,
           TIMEOUT, ENV_FILE, UNIFY, SPLIT, validate_env_schema, validate_xtest_schema]


def dump_config_schema():
    print_dict(_CONFIG_SCHEMA)


def dump_xtest_schema():
    print_dict(_XTEST_SCHEMA)


def dump_unified_schema():
    schema = _CONFIG_SCHEMA
    schema["properties"][TESTS]["items"] = _XTEST_SCHEMA
    print_dict(schema)
