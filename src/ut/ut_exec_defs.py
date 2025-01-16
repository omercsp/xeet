from ut import *
from . import register_res_comparison
from xeet.common import platform_path
from xeet.steps.exec_step import ExecStepResult, ExecStepModel
import os


def tests_utils_command(name: str, *args) -> str:
    path = os.path.join(project_root(), "scripts", "testing", name)
    path = platform_path(path)
    ret = f"python {path}"
    if not args:
        return ret
    args = " ".join(args)
    return f"{ret} {args}"


# Common exec step constants and functions
SHOWENV_CMD = tests_utils_command("showenv.py")
ECHOCMD = tests_utils_command("echo.py")
PWD_CMD = tests_utils_command("pwd.py")
SLEEP_CMD = tests_utils_command("sleep.py")
OUTPUT_CMD = tests_utils_command("output.py")
RAND_RC_CMD = tests_utils_command("rc.py")
BAD_CMD = "bad command"


def gen_showenv_cmd(var_name: str) -> str:
    return f"{SHOWENV_CMD} {var_name}"


def gen_echo_cmd(msg: str) -> str:
    return f"{ECHOCMD} {msg}"


def gen_output_cmd(file_name: str, args: str) -> str:
    return f"{OUTPUT_CMD} {file_name} {args}"


def gen_sleep_cmd(seconds: float) -> str:
    return f"{SLEEP_CMD} {seconds}"


def gen_rc_cmd(rc: int) -> str:
    return tests_utils_command("rc.py", str(rc))


TRUE_CMD = gen_rc_cmd(0)
FALSE_CMD = gen_rc_cmd(1)


GOOD_EXEC_STEP_RES = ExecStepResult(rc=0, rc_ok=True, completed=True)


_exec_fields = set(ExecStepModel.model_fields.keys())


def gen_exec_step_desc(**kwargs) -> dict:
    for k in list(kwargs.keys()):
        if k not in _exec_fields:
            raise ValueError(f"Invalid ExecStep field '{k}'")
    return {"type": "exec", **kwargs}


def _compare_exec_step_result(res: ExecStepResult, expected: ExecStepResult) -> None:
    assert isinstance(res, ExecStepResult)
    assert isinstance(expected, ExecStepResult)
    assert res.output_behavior == expected.output_behavior
    assert bool(res.os_error) == bool(expected.os_error)
    if res.allowed_rc != "*":
        assert res.rc == expected.rc
    assert res.rc_ok == expected.rc_ok
    assert bool(res.stdout_diff) == bool(expected.stdout_diff)
    assert bool(res.stderr_diff) == bool(expected.stderr_diff)
    assert bool(res.timeout_period) == bool(expected.timeout_period)


register_res_comparison(ExecStepResult, _compare_exec_step_result)


__all__ = ["SHOWENV_CMD", "ECHOCMD", "PWD_CMD", "BAD_CMD", "OUTPUT_CMD", "RAND_RC_CMD",
           "GOOD_EXEC_STEP_RES", "TRUE_CMD", "FALSE_CMD", "gen_exec_step_desc", "gen_rc_cmd",
           "gen_showenv_cmd", "gen_echo_cmd", "gen_output_cmd", "gen_sleep_cmd"]
