from xeet.common import XeetVars, text_file_tail, in_windows
from xeet.pr import pr_info
from xeet import XeetDefs
from xeet.xstep import XStep, XStepModel, XStepResult
from pydantic import field_validator, ValidationInfo, model_validator, Field
from enum import Enum
from io import TextIOWrapper
from typing import ClassVar
from dataclasses import dataclass
import threading
import shlex
import os
import subprocess
import difflib
import json


class _OutputBehavior(str, Enum):
    Unify = "unify"
    Split = "split"


class ExecStepModel(XStepModel):
    timeout: float | None = Field(None, ge=0)
    shell_path: str | None = None
    cmd: str | None = None
    use_shell: bool | None = None
    output_behavior: _OutputBehavior | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None
    env_file: str | None = None
    use_os_env: bool = False
    allowed_rc: list[int] | str = [0]
    stdout_file: str | None = None
    stderr_file: str | None = None
    expected_stdout: str | None = None
    expected_stderr: str | None = None
    expected_stdout_file: str | None = None
    expected_stderr_file: str | None = None

    @field_validator('allowed_rc')
    @classmethod
    def check_rc_value(cls, v: str | list[int], _: ValidationInfo) -> list[int] | str:
        if isinstance(v, str):
            assert v == "*", "Only '*' is allowed"
        return v

    @model_validator(mode='after')
    def check_expected_output(self) -> "ExecStepModel":
        assert not (self.expected_stdout and self.expected_stdout_file)
        assert not (self.expected_stderr and self.expected_stderr_file)
        return self

    base_class_fields: ClassVar[set[str]] = set(XStepModel.model_fields.keys())

    def inherit(self, parent: "ExecStepModel") -> None:  # type: ignore
        super().inherit(parent)
        for attr in self.model_fields:
            if attr in self.base_class_fields or self._had_key(attr):
                continue
            setattr(self, attr, getattr(parent, attr))


@dataclass
class ExecStepResult(XStepResult):
    stdout_file: str = ""
    stderr_file: str = ""
    duration: float | None = None
    timeout_period: float | None = None
    output_behavior: _OutputBehavior = _OutputBehavior.Unify
    os_error: OSError | None = None
    rc: int | None = None
    allowed_rc: list[int] | str = ""
    rc_ok: bool = False
    stdout_diff: str = ""
    stderr_diff: str = ""


class ExecStep(XStep):
    @staticmethod
    def model_class() -> type[XStepModel]:
        return ExecStepModel

    @staticmethod
    def result_class() -> type[XStepResult]:
        return ExecStepResult

    def __init__(self, model: ExecStepModel, xdefs: XeetDefs, base_name: str) -> None:
        super().__init__(model, xdefs, base_name)
        self.exec_model = model
        self.shell_path = ""
        self.cmd = ""
        self.use_shell = False
        self.cwd = ""
        self.env = {}
        self.env_file = ""
        self.output_behavior = _OutputBehavior.Unify
        self.expected_stdout = ""
        self.expected_stderr = ""
        self.expected_stdout_file = ""
        self.expected_stderr_file = ""
        self.stdout_file = ""
        self.stderr_file = ""
        self.timeout_occurred = False

        if self.exec_model.output_behavior is None:
            self.output_behavior = _OutputBehavior.Unify
        else:
            self.output_behavior = self.exec_model.output_behavior

        if model.stdout_file:
            self.stdout_file = os.path.join(self.xdefs.output_dir, model.stdout_file)
        else:
            self.stdout_file = os.path.join(self.xdefs.output_dir, f"{base_name}_stdout")
        file_title = "unified output" if self.output_behavior == _OutputBehavior.Unify else "stdout"
        self.log_info(f"{file_title} will be written to '{self.stdout_file}'")

        if self.output_behavior == _OutputBehavior.Unify:
            self.stderr_file = ""
            return
        if model.stderr_file:
            self.stderr_file = os.path.join(self.xdefs.output_dir, model.stderr_file)
        else:
            self.stderr_file = os.path.join(self.xdefs.output_dir, f"{base_name}_stderr")

        self.log_info(f"stderr will be written to '{self.stderr_file}'")

    def setup(self, xvars: XeetVars) -> None:  # type: ignore
        super().setup(xvars)
        self.shell_path = xvars.expand(self.exec_model.shell_path)
        if not self.shell_path:
            self.shell_path, _ = self.xdefs.config_ref("exec_step.default_shell_path")

        self.cmd = xvars.expand(self.exec_model.cmd)
        self.use_shell = (not in_windows()) and xvars.expand(self.exec_model.use_shell)
        self.cwd = xvars.expand(self.exec_model.cwd)
        if self.cwd:
            self.log_info(f"Working directory will be set to '{self.cwd}'")
        else:
            self.log_info(f"Using current working directory '{os.getcwd()}'")
        self.env = xvars.expand(self.exec_model.env)
        self.env_file = xvars.expand(self.exec_model.env_file)

        if self.exec_model.env_file:
            self.env_file = xvars.expand(self.env_file)
        if self.exec_model.env is not None:
            for k, v in self.exec_model.env.items():
                name = k.strip()
                if not name:
                    continue
                self.env[k] = xvars.expand(v)

        self.expected_stdout = xvars.expand(self.exec_model.expected_stdout)
        self.expected_stderr = xvars.expand(self.exec_model.expected_stderr)
        self.expected_stdout_file = xvars.expand(self.exec_model.expected_stdout_file)
        self.expected_stderr_file = xvars.expand(self.exec_model.expected_stderr_file)

    def _read_env_vars(self) -> dict:
        ret = {}
        if self.exec_model.use_os_env:
            ret.update(os.environ)
        if self.env_file:
            self.log_info(f"reading env file '{self.env_file}'")
            with open(self.env_file, "r") as f:
                data = json.load(f)
                #  err = validate_env_schema(data)
                #  if err:
                #      raise XeetRunException(f"Error reading env file - {err}")
                ret.update(data)
        if self.env:
            ret.update(self.env)
        return ret

    def _io_descriptors(self) -> tuple[TextIOWrapper, TextIOWrapper]:
        out_file = open(self.stdout_file, "w")
        if self.output_behavior == _OutputBehavior.Unify:
            err_file = out_file
        else:
            err_file = open(self.stderr_file, "w")
        return out_file, err_file

    def _timeout_terminate(self, p):
        self.timeout_occurred = True
        self._kill_process(p)

    def _kill_process(self, p: subprocess.Popen) -> None:
        if p.returncode is not None:
            return
        try:
            p.terminate()
            p.wait(1)
            p.kill()
        except OSError as e:
            self.log_info(f"Error killing process - {e}", dbg_pr=False)

    def _run(self, res: ExecStepResult) -> bool:  # type: ignore
        try:
            env = self._read_env_vars()
        except OSError as e:
            res.err_summary = f"Error reading env file: {e}"
            self.log_warn(res.err_summary)
            return False

        subproc_args: dict = {
            "env": env,
            "cwd": self.cwd if self.cwd else None,
            "shell": self.use_shell,
            "executable": self.shell_path if self.shell_path and self.use_shell else None,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE if self.output_behavior == _OutputBehavior.Split
            else subprocess.STDOUT,
            "text": True,
            "bufsize": 0,
        }
        self.log_info(f"Running command (shell: {self.use_shell}):")
        self.log_raw(self.cmd)
        command = self.cmd
        if not self.use_shell and isinstance(command, str):
            try:
                command = shlex.split(command)
            except ValueError as e:
                res.err_summary = f"Error splitting command: {e}"
                return False
        subproc_args["args"] = command

        res.stdout_file = self.stdout_file
        res.stderr_file = self.stderr_file
        res.output_behavior = self.output_behavior
        res.allowed_rc = self.exec_model.allowed_rc
        timeout = self.exec_model.timeout

        p = None
        timer = None
        out_file, err_file = self._io_descriptors()
        try:
            p = subprocess.Popen(**subproc_args)
            self.timeout_occurred = False
            self.pr_debug(" output ".center(33, "-"))
            if timeout:
                self.log_info(f"Timeout set to {timeout}s", dbg_pr=False)
                timer = threading.Timer(timeout, self._timeout_terminate, [p])
                timer.start()

            while True:
                read_output = False
                assert p.stdout is not None
                data = p.stdout.read(1)
                if data:
                    self.pr_debug(data, end="")
                    out_file.write(data)
                    read_output = True
                if self.output_behavior == _OutputBehavior.Split:
                    assert p.stderr is not None
                    data = p.stderr.read(1)
                    if data:
                        self.pr_debug(data, end="")
                        err_file.write(data)
                        read_output = True

                if p.poll() is not None and not read_output:
                    break
            #  Handle remaining output
            for data in p.stdout.read():
                self.pr_debug(data, end="")
                out_file.write(data)
            if self.output_behavior == _OutputBehavior.Split:
                assert p.stderr is not None
                for data in p.stderr.read():
                    self.pr_debug(data, end="")
                    err_file.write(data)
            self.pr_debug("-" * 33)

            if self.timeout_occurred:
                res.timeout_period = timeout
                res.err_summary = f"Timeout expired after {timeout}s"
                self.log_info(res.err_summary)
                return False

            res.rc = p.returncode
        except OSError as e:
            res.os_error = e
            res.err_summary = str(e)
            self.log_info(res.err_summary)
            return False
        except KeyboardInterrupt:
            assert p is not None
            self._kill_process(p)
            res.err_summary = "User interrupt"
            return False
        finally:
            if p and p.stdout:
                p.stdout.close()
            if p and p.stderr:
                p.stderr.close()
            if isinstance(out_file, TextIOWrapper):
                out_file.close()
            if isinstance(err_file, TextIOWrapper):
                err_file.close()
            if timer:
                self.log_info("Closing output files")
                timer.cancel()
        self.log_info(f"Command finished with return code {res.rc}")
        self._verify_rc(res)
        self._verify_output(res)
        return True

    def _verify_rc(self, res: ExecStepResult) -> None:
        self.log_info("Verifying rc", dbg_pr=False)

        res.rc_ok = isinstance(self.exec_model.allowed_rc, str) or \
            res.rc in self.exec_model.allowed_rc
        if res.rc_ok:
            self.log_info("Return code is valid", dbg_pr=False)
            return
        res.failed = True

        #  RC error
        allowed_str = ",".join([str(x) for x in self.exec_model.allowed_rc])
        err = f"retrun code {res.rc} not in allowed return codes ({allowed_str})"
        self.log_info(f"failed: {err}")
        if self.debug_mode:
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

    def _verify_output(self, res: ExecStepResult) -> None:
        def _expected_text(string, file_path) -> list[str] | None:
            if string:
                ret = string.splitlines()
                if string.endswith("\n"):
                    ret.append("")
                return ret
            if file_path:
                with open(file_path, "r") as f:
                    return f.readlines()
            return None
        if self.debug_mode and self.output_behavior == _OutputBehavior.Split:
            self.pr_debug("Output verification isn't supported in debug mode when output_behavior "
                          "is 'split', verication will be skipped")
            return

        if res.failed:
            self.log_info("Skipping output verification, prior step failed")
            return
        self.log_info("verifying output", dbg_pr=False)
        expected_stdout = _expected_text(self.expected_stdout, self.expected_stdout_file)
        expected_stderr = _expected_text(self.expected_stderr, self.expected_stderr_file)
        if not expected_stdout and not expected_stderr:
            self.log_info("No output verification is required")
            return

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
                self.log_info("stdout differs from expected")
                res.err_summary = f"stdout differs from expected\n{res.stdout_diff}"

        if expected_stderr:
            if self.output_behavior == _OutputBehavior.Unify:
                self.log_warn("expected_stderr is ignored when output_behavior is 'unify'")
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
                self.log_info("stderr differs from expected")
                res.err_summary = f"stderr differs from expected\n{res.stderr_diff}"
        if not res.failed:
            self.log_info("Output is verified")
            return
