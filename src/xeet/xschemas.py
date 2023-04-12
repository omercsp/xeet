class VerValues(object):
    MAJOR: int = 0
    MINOR: int = 0


class VerKeys(object):
    Major = "major"
    Minor = "minor"


class _CommonKeys(object):
    Variables = "variables"
    DiffCmd = "diff_cmd"


class AutoVarsKeys(object):
    CWD = "__cwd__"
    TEST_CLI_ARGS = "__args__"
    XROOT = "__xroot__"
    OUT_DIR = "__output_dir__"


class XTestKeys(object):
    Name = "name"
    Shell = "shell"
    ShellPath = "shell_path"
    Env = "env"
    InheritEnv = "inherit_env"
    InheritOsEnv = "inherit_os_env"
    Cwd = "cwd"
    Base = "base"
    Abstract = "abstract"
    Skip = "skip"
    SkipReason = "skip_reason"
    ShortDesc = "short_desc"
    LongDesc = "description"
    Groups = "groups"
    Command = "command"
    AllowedRc = "allowed_return_codes"
    ExpectedFailure = "expected_failure"
    CompareOutput = "compare_output"
    Stdout = "stdout"
    Stderr = "stderr"
    All = "all"
    Nothing = "none"
    OutputFilter = "output_filter"
    PreCommand = "pre_command"
    PostCommand = "post_command"
    Variables = _CommonKeys.Variables
    InheritVariables = "inherit_variables"
    InheritGroups = "inherit_groups"
    OutputBehavior = "output_behavior"
    Timeout = "timeout"


class GlobalKeys(object):
    Schema = "$schema"
    Include = "include"
    XTests = "tests"
    Variables = _CommonKeys.Variables
    DftlDiffCmd = _CommonKeys.DiffCmd
    DfltShellPath = "default_shell_path"


class OutputBehaviorValues(object):
    Unify = "unify"
    Split = "split"


_COMMAND_SCHEMA = {
    "anyOf": [
        {"type": "string", "minLength": 1},
        {"type": "array", "items": {"type": "string", "minLength": 1}}
    ]
}


XTEST_SCHEMA = {
    "type": "object",
    "properties": {
        XTestKeys.Name: {"type": "string", "minLength": 1},
        XTestKeys.Base: {"type": "string", "minLength": 1},
        XTestKeys.ShortDesc: {"type": "string", "maxLength": 75},
        XTestKeys.LongDesc: {"type": "string"},
        XTestKeys.Groups: {
            "type": "array",
            "items": {"type": "string", "minLength": 1}
        },
        XTestKeys.Command: _COMMAND_SCHEMA,
        XTestKeys.AllowedRc: {
            "type": "array",
            "items": {"type": "integer", "minimum": 0, "maximum": 255}
        },
        XTestKeys.Timeout: {
            "type": "integer",
            "minimum": 0
        },
        XTestKeys.CompareOutput: {"type": "string", "enum": [
            XTestKeys.All, XTestKeys.Stdout, XTestKeys.Stderr, XTestKeys.Nothing]},
        XTestKeys.OutputFilter: _COMMAND_SCHEMA,
        XTestKeys.PreCommand: _COMMAND_SCHEMA,
        XTestKeys.PostCommand: _COMMAND_SCHEMA,
        XTestKeys.ExpectedFailure: {"type": "boolean"},
        XTestKeys.OutputBehavior: {
            "enum": [
                OutputBehaviorValues.Unify,
                OutputBehaviorValues.Split,
            ]
        },
        XTestKeys.Cwd: {"type": "string", "minLength": 1},
        XTestKeys.Shell: {"type": "boolean"},
        XTestKeys.ShellPath: {"type": "string", "minLength": 1},
        XTestKeys.Env: {
            "type": "object",
            "additionalProperties": {
                "type": "string"
            }
        },
        XTestKeys.InheritOsEnv: {"type": "boolean"},
        XTestKeys.InheritEnv: {"type": "boolean"},
        XTestKeys.Abstract: {"type": "boolean"},
        XTestKeys.Skip: {"type": "boolean"},
        XTestKeys.SkipReason: {"type": "string"},
        XTestKeys.Variables: {"type": "object"},
        XTestKeys.InheritVariables: {"type": "boolean"},
        XTestKeys.InheritGroups: {"type": "boolean"}
    },
    "additionalProperties": False,
    "required": [XTestKeys.Name]
}

XEET_CONFIG_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        GlobalKeys.Schema: {
            "type": "string",
            "minLength": 1
        },
        GlobalKeys.Include: {
            "type": "array",
            "items": {"type": "string", "minLength": 1}
        },
        GlobalKeys.XTests: {
            "type": "array",
            "items": {"type": "object"}
        },
        GlobalKeys.Variables: {"type": "object"},
        GlobalKeys.DfltShellPath: {
            "type": "string",
            "minLength": 1
        },
    }
}
