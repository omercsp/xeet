from xeet.common import XeetVars, XeetException, pydantic_errmsg, text_file_tail
from xeet.log import log_raw, log_error, log_warn
from xeet.pr import pr_info
from pydantic import (BaseModel, ConfigDict, field_validator, ValidationInfo, model_validator,
                      Field, ValidationError)
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable
from timeit import default_timer as timer
from io import TextIOWrapper
from typing_extensions import Self
import shlex
import os
import subprocess
import signal
import difflib


class XStepModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    step_type: str = Field(validation_alias="type")
    name: str = ""


class XeetStepException(XeetException):
    ...


class XeetStepInitException(XeetStepException):
    def __init__(self, error: str, step_type, prefix: str, index: int) -> None:
        super().__init__(error)
        self.step_type = step_type
        self.prefix = prefix
        self.index = index

    def __str__(self) -> str:
        ret = f"Error initializing {self.prefix} step {self.index}"
        if self.step_type:
            ret += f" ({self.step_type})"
        return f"{ret}:\n{self.error}"


@dataclass
class XStepResult:
    step: "XStep"
    failed: bool = False
    err_summary: str = ""
    completed = False
    duration: float | None = None

    def error_summary(self) -> str:
        ret = f"{self.step.stage_prefix} step {self.step.index}"
        if self.step.model.name:
            ret += f" ('{self.step.model.name}')"
        if not self.completed:
            ret += f" incomplete: {self.err_summary}"
        if self.failed:
            ret += f" failed: {self.err_summary}"
        return ret


@dataclass
class XtestStepTestSettings:
    log_info: Callable
    debug_mode: bool
    output_dir: str


class XStep:

    @staticmethod
    def model_class() -> type[XStepModel]:
        return XStepModel

    @staticmethod
    def result_class() -> type[XStepResult]:
        return XStepResult

    def __init__(self, model: XStepModel, test_settings: XtestStepTestSettings, index: int,
                 stage_prefix: str):
        self.model = model
        self.test_settings = test_settings
        self.log_info = test_settings.log_info
        self.index = index
        self.stage_prefix = stage_prefix

    def expand(self, _: XeetVars) -> str:
        ...

    def run(self) -> XStepResult:
        res = self.result_class()(self)
        start = timer()
        self._run(res)
        res.duration = timer() - start
        self.log_info(f"step finished with in {res.duration:.3f}s")
        return res

    def print_name(self) -> str:
        ret = f"{self.stage_prefix} step {self.index}: {self.model.step_type}"
        if self.model.name:
            ret += f" ('{self.model.name}')"
        return ret

    def summary(self) -> str:
        return self.print_name()

    def _run(self, _: XStepResult) -> XStepResult:
        raise NotImplementedError


@dataclass
class XStepListResult:
    results: list[XStepResult] = field(default_factory=list)
    completed: bool = True
    failed: bool = False

    def error_summary(self) -> str:
        return "\n".join([r.error_summary() for r in self.results if r.failed])


#  stop_on_err will stop if either a step fails or is incomplete
def run_xstep_list(step_list: list[XStep], stop_on_err: bool) -> XStepListResult:
    res = XStepListResult()
    for step in step_list:
        step_res = step.run()
        res.results.append(step_res)
        if not step_res.completed:
            res.completed = False
            if stop_on_err:
                break
        if step_res.failed:
            res.failed = True
            if stop_on_err:
                break
    return res


class _OutputBehavior(str, Enum):
    Unify = "unify"
    Split = "split"


class XExecStepModel(XStepModel):
    timeout: float | None = None
    shell_path: str | None = None
    cmd: str | None = None
    use_shell: bool | None = None
    output_behavior: _OutputBehavior | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None
    env_file: str | None = None
    use_os_env: bool | None = None
    allowed_rc: list[int] | str = [0]
    stdout_file: str | None = None
    stderr_file: str | None = None
    expected_stdout: str | None = None
    expected_stderr: str | None = None
    expected_stdout_file: str | None = None
    expected_stderr_file: str | None = None

    @field_validator('allowed_rc')
    @classmethod
    def check_rc_value(cls, v: str, _: ValidationInfo) -> list[int] | str:
        if isinstance(v, str):
            assert v == "*", "Only '*' is allowed"
        return v

    @model_validator(mode='after')
    def check_output_behavior(self) -> Self:
        if self.output_behavior is None:
            self.output_behavior = _OutputBehavior.Unify

        assert not (self.expected_stdout and self.expected_stdout_file)
        assert not (self.expected_stderr and self.expected_stderr_file)
        return self


class XExecStepResult(XStepResult):
    stdout_file: str = ""
    stderr_file: str = ""
    return_code: int | None = None
    duration: float | None = None
    timeout_period: float | None = None
    output_behavior: _OutputBehavior = _OutputBehavior.Unify
    os_error: OSError | None = None
    unified_output: bool = False
    rc: int | None = None
    rc_ok: bool = False
    stdout_diff: str = ""
    stderr_diff: str = ""


class XExecStep(XStep):
    @staticmethod
    def model_class() -> type[XStepModel]:
        return XExecStepModel

    @staticmethod
    def result_class() -> type[XStepResult]:
        return XExecStepResult

    def __init__(self, model: XExecStepModel, **kwargs):
        super().__init__(model, **kwargs)
        self.exec_model = model
        self.timeout: float = 0
        self.shell_path = ""
        self.cmd = ""
        self.use_shell = False
        self.output_behavior = model.output_behavior
        self.cwd = ""
        self.env = {}
        self.env_file = ""
        self.use_os_env = False
        base_name = f"{self.stage_prefix}_{self.index}"
        if self.model.name:
            base_name += f"_{self.model.name}"

        if model.stdout_file:
            self.stdout_file = os.path.join(self.test_settings.output_dir, model.stdout_file)
        else:
            self.stdout_file = os.path.join(self.test_settings.output_dir, f"{base_name}_stdout")

        if model.stderr_file:
            self.stderr_file = os.path.join(self.test_settings.output_dir, model.stderr_file)
        else:
            self.stderr_file = os.path.join(self.test_settings.output_dir, f"{base_name}_stderr")

    def expand(self, xvars: XeetVars) -> None:  # type: ignore
        self.timeout = xvars.expand(self.exec_model.timeout)
        self.shell_path = xvars.expand(self.exec_model.shell_path)
        self.cmd = xvars.expand(self.exec_model.cmd)
        self.use_shell = xvars.expand(self.exec_model.use_shell)
        self.cwd = xvars.expand(self.exec_model.cwd)
        if self.cwd:
            self.log_info(f"working directory will be set to '{self.cwd}'")
        else:
            self.log_info("using default working directory")
        self.env = xvars.expand(self.exec_model.env)
        #  self.env_file = xvars.expand(self.exec_model.env_file)
        self.use_os_env = xvars.expand(self.exec_model.use_os_env)

    def _get_test_io_descriptors(self) -> tuple[TextIOWrapper | int, TextIOWrapper | int]:
        err_file = subprocess.DEVNULL
        out_file = open(self.stdout_file, "w")
        if self.output_behavior == _OutputBehavior.Unify:
            err_file = out_file
        else:
            err_file = open(self.stderr_file, "w")
        return out_file, err_file

    def _run(self, res: XExecStepResult) -> None:  # type: ignore
        subproc_args: dict = {
            "env": self.env,
            "cwd": self.cwd if self.cwd else None,
            "shell": self.use_shell,
            "executable": self.shell_path if self.shell_path and self.use_shell else None,
        }
        self.log_info("running command:")
        log_raw(self.cmd)
        command = self.cmd
        if not self.use_shell and isinstance(command, str):
            command = shlex.split(command)
        subproc_args["args"] = command

        res.stdout_file = self.stdout_file
        res.stderr_file = self.stderr_file
        res.unified_output = self.output_behavior == _OutputBehavior.Unify

        p = None
        out_file, err_file = None, None
        try:
            if self.test_settings.debug_mode:
                subproc_args["timeout"] = self.timeout
                p = subprocess.run(**subproc_args)
                res.rc = p.returncode
                assert isinstance(res.rc, int)
            else:
                out_file, err_file = self._get_test_io_descriptors()
                subproc_args["stdout"] = out_file
                subproc_args["stderr"] = err_file
                p = subprocess.Popen(**subproc_args)
                res.rc = p.wait(self.timeout)
            res.completed = True
        except OSError as e:
            res.os_error = e
            res.err_summary = str(e)
            self.log_info(res.err_summary)
        except subprocess.TimeoutExpired as e:
            assert p is not None
            try:
                p.kill()
                p.wait()
            except OSError as kill_e:
                log_error(f"Error killing process - {kill_e}")
            self.log_info(str(e))
            res.timeout_period = self.timeout
            res.err_summary = f"Timeout expired after {self.timeout}s"
        except KeyboardInterrupt:
            if p and not self.test_settings.debug_mode:
                p.send_signal(signal.SIGINT)  # type: ignore
                p.wait()  # type: ignore
            raise XeetStepException("User interrupt")
        finally:
            if isinstance(out_file, TextIOWrapper):
                out_file.close()
            if isinstance(err_file, TextIOWrapper):
                err_file.close()

        self._verify_rc(res)
        self._verify_output(res)

    def _verify_rc(self, res: XExecStepResult) -> None:
        if self.test_settings.debug_mode:
            pr_info("Verifying rc")

        if not res.completed:
            self.log_info("Skipping RC verification, prior step failed")
            return
        self.log_info(f"verifying return code")

        res.rc_ok = isinstance(self.exec_model.allowed_rc, str) or \
            res.rc in self.exec_model.allowed_rc
        if res.rc_ok:
            return
        res.failed = True

        #  RC error
        allowed_str = ",".join([str(x) for x in self.exec_model.allowed_rc])
        err = f"retrun code {res.rc} not in allowed return codes ({allowed_str})"
        self.log_info(f"failed: {err}")
        if self.test_settings.debug_mode:
            pr_info(f"RC verification failed: {err}")

        res.err_summary = err
        if self.output_behavior == _OutputBehavior.Unify:
            stdout_title = "output"
        else:
            stdout_title = "stdout"
        stdout_tail = text_file_tail(res.stdout_file)
        if stdout_tail:
            res.err_summary += f"\n{stdout_title} tail:\n------\n{stdout_tail}\n------"
        else:
            res.err_summary += f"\nempty {stdout_title}"
        if self.output_behavior == _OutputBehavior.Unify:
            return
        stderr_tail = text_file_tail(res.stderr_file)
        if stderr_tail:
            res.err_summary += f"\nstderr tail:\n------\n{stderr_tail}\n------"
        else:
            res.err_summary += "\nempty stderr"

    def _expected_text(self, string, file_path) -> list[str] | None:
        if string:
            ret = string.splitlines()
            if string.endswith("\n"):
                ret.append("")
            return ret
        if file_path:
            with open(file_path, "r") as f:
                return f.readlines()
        return None

    def _verify_output(self, res: XExecStepResult) -> None:
        self.log_info("verifying output")
        if not res.completed or res.failed:
            self.log_info("Skipping output verification, prior step failed")
            return
        expected_stdout = self._expected_text(self.exec_model.expected_stdout,
                                              self.exec_model.expected_stdout_file)
        if expected_stdout:
            with open(res.stdout_file, "r") as f:
                stdout = f.read()
                has_newline = stdout.endswith("\n")
                stdout = stdout.splitlines()
                if has_newline:
                    stdout.append("")
            diff = difflib.unified_diff(
                stdout,  # List of lines from file1
                expected_stdout,  # List of lines from file2
                fromfile=res.stdout_file,
                tofile="expected_stdout",
                lineterm=''  # Suppress extra newlines
            )
            res.stdout_diff = '\n'.join(diff)
            if res.stdout_diff:
                res.failed = True
                res.err_summary = f"stdout differs from expected\n{res.stdout_diff}"

        expected_stderr = self._expected_text(self.exec_model.expected_stderr,
                                              self.exec_model.expected_stderr_file)
        if expected_stderr:
            if self.output_behavior == _OutputBehavior.Unify:
                log_warn("expected_stderr is ignored when output_behavior is 'unify'")
                return
            with open(res.stderr_file, "r") as f:
                stderr = f.readlines()
            diff = difflib.unified_diff(
                stderr,  # List of lines from file1
                expected_stderr,  # List of lines from file2
                fromfile=res.stderr_file,
                tofile="expected_stderr",
                lineterm=''  # Suppress extra newlines
            )
            res.stderr_diff = '\n'.join(diff)
            if res.stderr_diff:
                res.failed = True
                res.err_summary = f"stderr differs from expected\n{res.stderr_diff}"


_XSTEP_CLASSES: dict[str, type[XStep]] = {
    "exec": XExecStep,
}


def xstep_factory(desc: dict, test_settings: XtestStepTestSettings, index: int,
                  stage_prefix: str) -> XStep:
    model_type = desc.get("type")
    if not model_type:
        raise XeetStepInitException("Step type not specified", "", stage_prefix, index)
    if model_type not in _XSTEP_CLASSES:
        raise XeetStepInitException(f"Unknown step type '{model_type}'", model_type, stage_prefix,
                                    index)
    xstep_class = _XSTEP_CLASSES[model_type]
    xstep_model_class = xstep_class.model_class()
    try:
        xstep_model = xstep_model_class(**desc)
    except ValidationError as e:
        raise XeetStepInitException(f"{pydantic_errmsg(e)}", model_type, stage_prefix, index)
    return xstep_class(xstep_model, test_settings=test_settings, index=index,
                       stage_prefix=stage_prefix)
