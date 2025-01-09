from xeet.common import (text_file_tail, in_windows, FileTailer, validate_types, yes_no_str,
                         StrFilterData, filter_str, validate_str)
from xeet.pr import pr_info
from xeet.core.step import Step, StepModel, StepResult
from xeet import XeetException
from pydantic import field_validator, ValidationInfo, model_validator, Field
from enum import Enum
from io import TextIOWrapper
from dataclasses import dataclass
from typing import Any
import time
import shlex
import os
import subprocess
import signal
import difflib
import json


class _OutputBehavior(str, Enum):
    Unify = "unify"
    Split = "split"

    def __str__(self) -> str:
        return self.value


class ExecStepModel(StepModel):
    timeout: float | None = Field(None, ge=0)
    shell_path: str | None = None
    cmd: str | None = None
    use_shell: bool = False
    output_behavior: _OutputBehavior = _OutputBehavior.Unify
    cwd: str | None = None
    env: dict[str, str] | str = Field(default_factory=dict)
    env_file: str | None = None
    use_os_env: bool = False
    allowed_rc: list[int] | str = [0]
    stdout_file: str = Field("stdout", min_length=1)
    stderr_file: str = Field("stderr", min_length=1)
    expected_stdout: str | None = None
    expected_stderr: str | None = None
    expected_stdout_file: str | None = None
    expected_stderr_file: str | None = None
    debug_new_line: bool = False
    output_filters: list[StrFilterData] = Field(default_factory=list)
    stop_process_wait: float = Field(3, ge=0)

    @field_validator('allowed_rc')
    @classmethod
    def check_rc_value(cls, v: str | list[int], _: ValidationInfo) -> list[int] | str:
        if isinstance(v, str):
            assert v == "*", "Only '*' is allowed"
        return v

    @model_validator(mode='after')
    def check_expected_output(self) -> "ExecStepModel":
        if self.expected_stdout and self.expected_stdout_file:
            raise ValueError("Only one of 'expected_stdout' and 'expected_stdout_file' can be set")
        if self.expected_stderr and self.expected_stderr_file:
            raise ValueError("Only one of 'expected_stderr' and 'expected_stderr_file' can be set")
        return self


@dataclass
class ExecStepResult(StepResult):
    stdout_file: str = ""
    stderr_file: str = ""
    timeout_period: float | None = None
    output_behavior: _OutputBehavior = _OutputBehavior.Unify
    os_error: OSError | None = None
    rc: int | None = None
    allowed_rc: list[int] | str = ""
    rc_ok: bool = False
    stdout_diff: str = ""
    stderr_diff: str = ""


class ExecStep(Step):
    @staticmethod
    def model_class() -> type[StepModel]:
        return ExecStepModel

    @staticmethod
    def result_class() -> type[StepResult]:
        return ExecStepResult

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.exec_model: ExecStepModel = kwargs["model"]
        self.cmd = ""
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
        self.output_behavior = self.exec_model.output_behavior
        self.use_shell = (not in_windows()) and self.exec_model.use_shell
        self.shell_path = self.exec_model.shell_path
        if not self.shell_path:
            self.shell_path, _ = self.rti.config_ref("settings.exec_step.default_shell_path")
        self.output_verification_err = False
        self.output_filters: list[StrFilterData] = []
        self.p: subprocess.Popen | None = None

    def setup(self, **kwargs) -> None:  # type: ignore
        super().setup(**kwargs)

        self.cmd = self.xvars.expand(self.exec_model.cmd)
        if not validate_str(self.cmd, strip=True, min_len=1):
            raise XeetException(f"Invalid command '{self.cmd}'")
        self.cmd = self.cmd.strip()

        self.cwd = self.xvars.expand(self.exec_model.cwd)
        if self.cwd is not None:
            if not validate_str(self.cwd, strip=True, min_len=1):
                raise XeetException(f"Invalid working directory '{self.cwd}'")
            self.cwd = self.cwd.strip()
            self.notify(f"Working directory will be set to '{self.cwd}'")

        self.env = self.xvars.expand(self.exec_model.env)
        if not validate_types(self.env, dict):
            raise XeetException(f"Invalid environment variables '{self.env}'")
        for k, v in self.env.items():
            self.env[k] = str(v)

        self.env_file = self.xvars.expand(self.exec_model.env_file)
        if self.env_file is not None:
            if not validate_str(self.env_file, strip=True):
                raise XeetException(f"Invalid environment file '{self.env_file}'")
            self.env_file = self.env_file.strip()
            self.notify(f"Environment file will be read from '{self.env_file}'")

        #  Output files
        stdout_name = self.xvars.expand(self.exec_model.stdout_file)
        if not validate_str(stdout_name, strip=True, min_len=1):
            raise XeetException(f"Invalid stdout name '{stdout_name}'")
        self.stdout_file = self._output_file(stdout_name)

        if self.output_behavior == _OutputBehavior.Unify:
            self.notify(f"Unified output will be written to '{self.stdout_file}'", dbg_pr=False)
        else:
            stderr_name = self.xvars.expand(self.exec_model.stderr_file)
            if not validate_str(stderr_name, strip=True, min_len=1):
                raise XeetException(f"Invalid stderr name '{stderr_name}'")
            self.stderr_file = self._output_file(stderr_name)
            self.notify(f"Stdout will be written to '{self.stdout_file}'", dbg_pr=False)
            self.notify(f"Stderr will be written to '{self.stderr_file}'", dbg_pr=False)

        #  Expected output
        self.expected_stdout = self.xvars.expand(self.exec_model.expected_stdout)
        if self.expected_stdout is not None and not validate_str(self.expected_stdout):
            raise XeetException(f"Invalid expected stdout '{self.expected_stdout}'")

        self.expected_stderr = self.xvars.expand(self.exec_model.expected_stderr)
        if self.expected_stderr is not None and not validate_str(self.expected_stderr):
            raise XeetException(f"Invalid expected stderr '{self.expected_stderr}'")

        self.expected_stdout_file = self.xvars.expand(self.exec_model.expected_stdout_file)
        if self.expected_stdout_file is not None:
            if not validate_str(self.expected_stdout_file):
                raise XeetException(f"Invalid expected stdout file '{self.expected_stdout_file}'")
            self.expected_stdout_file = self.expected_stdout_file.strip()

        self.expected_stderr_file = self.xvars.expand(self.exec_model.expected_stderr_file)
        if self.expected_stderr_file is not None:
            if not validate_str(self.expected_stderr_file):
                raise XeetException(f"Invalid expected stderr file '{self.expected_stderr_file}'")
            self.expected_stderr_file = self.expected_stderr_file.strip()

        self.output_filters.clear()
        for f in self.exec_model.output_filters:
            ef = StrFilterData(
                regex=self.xvars.expand(f.regex),
                from_str=self.xvars.expand(f.from_str),
                to_str=self.xvars.expand(f.to_str)
            )
            if not validate_str(ef.from_str, min_len=1):
                raise XeetException(f"Invalid 'from' string '{ef.from_str}'")
            if not validate_str(ef.to_str):
                raise XeetException(f"Invalid 'to' string '{ef.to_str}'")
            if not validate_types(ef.regex, bool):
                raise XeetException(f"Invalid regex flag '{ef.regex}'")
            self.output_filters.append(ef)

    def _io_descriptors(self) -> tuple[TextIOWrapper, TextIOWrapper]:
        out_file = open(self.stdout_file, "w")
        if self.output_behavior == _OutputBehavior.Unify:
            err_file = out_file
        else:
            err_file = open(self.stderr_file, "w")
        return out_file, err_file

    def _read_env_vars(self) -> dict:
        ret = {}
        if self.exec_model.has_key("use_os_env") and self.exec_model.use_os_env:
            use_os_env = self.exec_model.use_os_env
        else:
            use_os_env, _ = self.rti.config_ref("settings.exec_step.use_os_env")
        if use_os_env:
            ret.update(os.environ)
        if self.env_file:
            self.notify(f"reading env file '{self.env_file}'")
            with open(self.env_file, "r") as f:
                data = json.load(f)
                #  err = validate_env_schema(data)
                #  if err:
                #      raise XeetRunException(f"Error reading env file - {err}")
                ret.update(data)
        if self.env:
            ret.update(self.env)
        return ret

    def _run(self, res: ExecStepResult) -> bool:  # type: ignore
        try:
            env = self._read_env_vars()
        except OSError as e:
            res.errmsg = f"Error reading env file: {e}"
            self.warn(res.errmsg)
            return False

        #  start_new_session=True is used to make sure the process is detached from the current
        #  session, so that it isn't killed when the parent process is killed. Instead we can
        #  kill the spawned process orderly.
        subproc_args: dict = {
            "start_new_session": True,
            "env": env,
            "cwd": self.cwd if self.cwd else None,
            "shell": self.use_shell,
            "executable": self.shell_path if self.shell_path and self.use_shell else None,
        }
        self.notify(f"running command (shell: {self.use_shell}):\n{self.cmd}")
        command = self.cmd
        if not self.use_shell and isinstance(command, str):
            try:
                command = shlex.split(command)
            except ValueError as e:
                res.errmsg = f"Error splitting command: {e}"
                return False
        subproc_args["args"] = command

        res.stdout_file = self.stdout_file
        res.stderr_file = self.stderr_file
        res.output_behavior = self.output_behavior
        res.allowed_rc = self.exec_model.allowed_rc
        timeout = self.exec_model.timeout

        out_file, err_file = self._io_descriptors()
        subproc_args["stdout"] = out_file
        subproc_args["stderr"] = err_file
        tails: list[FileTailer] = []
        if self.debug_mode:
            tails.append(FileTailer(self.stdout_file, pr_func=self.notify))
            if self.output_behavior == _OutputBehavior.Split:
                tails.append(FileTailer(self.stderr_file, pr_func=self.notify))
        try:
            self.debug(" output start ".center(33, "-"))
            with self.step_run_cond:
                if self.stop_requested:
                    res.errmsg = "Stop requested before starting the process"
                    return False
                self.p = subprocess.Popen(**subproc_args)
                self.notify(f"process started with pid {self.p.pid}", dbg_pr=False)
                for tail in tails:
                    tail.start()
            res.rc = self.p.wait(timeout)
            for tail in tails:
                tail.stop()
            if self.stop_requested:
                res.errmsg = "Stop requested while waiting for the process"
                return False
            if self.exec_model.debug_new_line:
                self.debug("")
        except OSError as e:
            for tail in tails:
                tail.stop(kill=True)
            res.os_error = e
            res.errmsg = str(e)
            self.notify(res.errmsg)
            return False
        except subprocess.TimeoutExpired as e:
            assert self.p is not None
            try:
                for tail in tails:
                    tail.stop(kill=True)
                self.p.kill()
                self.p.wait()
            except OSError as kill_e:
                self.error(f"error killing process - {kill_e}")
            self.notify(str(e))
            res.timeout_period = timeout
            res.errmsg = f"Timeout expired after {timeout}s"
            return False
        except KeyboardInterrupt:
            if self.p and not self.debug_mode:
                p.send_signal(signal.SIGINT)  # type: ignore
                p.wait()  # type: ignore
            res.errmsg = "User interrupt"
            return False
        finally:
            self.debug(" output end ".center(33, "-"))
            if isinstance(out_file, TextIOWrapper):
                out_file.close()
            if isinstance(err_file, TextIOWrapper):
                err_file.close()
            with self.step_run_cond:
                self.p = None
        self.notify(f"command finished with return code {res.rc}")
        try:
            self._verify_rc(res)
            self._verify_output(res)
        except OSError as e:
            res.errmsg = f"Error verifying result: {e}"
            self.warn(res.errmsg)
            return False
        return True

    def _verify_rc(self, res: ExecStepResult) -> None:
        self.notify("verifying rc", dbg_pr=False)

        res.rc_ok = isinstance(self.exec_model.allowed_rc, str) or \
            res.rc in self.exec_model.allowed_rc
        if res.rc_ok:
            self.notify("return code is valid")
            return
        res.failed = True

        #  RC error
        allowed_str = ",".join([str(x) for x in self.exec_model.allowed_rc])
        err = f"retrun code {res.rc} not in allowed return codes ({allowed_str})"
        self.notify(f"failed: {err}")
        if self.debug_mode:
            pr_info(f"RC verification failed: {err}")

        res.errmsg = err
        if self.output_behavior == _OutputBehavior.Unify:
            stdout_title = "output"
        else:
            stdout_title = "stdout"
        stdout_tail = text_file_tail(res.stdout_file)
        if stdout_tail:
            res.errmsg += f"\n{stdout_title} tail:\n------\n{stdout_tail}\n------"
        else:
            res.errmsg += f"\nempty {stdout_title}"
        if self.output_behavior == _OutputBehavior.Unify:
            return
        stderr_tail = text_file_tail(res.stderr_file)
        if stderr_tail:
            res.errmsg += f"\nstderr tail:\n------\n{stderr_tail}\n------"
        else:
            res.errmsg += "\nempty stderr"

    def _verify_output(self, res: ExecStepResult) -> None:
        def _expected_text(string, file_path) -> list[str] | None:
            if string is not None:
                return string.split("\n")
            if file_path:
                with open(file_path, "r") as f:
                    return f.read().split("\n")
            return None

        def _compare_std_file(name, file_path, expected):
            with open(file_path, "r") as f:
                content = f.read()
                if self.output_filters:
                    self.notify(f"applying filters to {name} - {self.output_filters}")
                    content = filter_str(content, self.output_filters)
                    with open(f"{file_path}.filtered", "w") as filtered_f:
                        filtered_f.write(content)
                content = content.split("\n")
            diff = difflib.unified_diff(
                content,  # List of lines from file1
                expected,  # List of lines from file2
                fromfile=file_path,
                tofile=f"expected_{name}",
                lineterm=''  # Suppress extra newlines
            )
            return '\n'.join(diff)

        self.notify("verifying output", dbg_pr=False)
        if res.failed:
            self.notify("skipping output verification, prior step failed")
            return

        expected_stdout = _expected_text(self.expected_stdout, self.expected_stdout_file)
        expected_stderr = _expected_text(self.expected_stderr, self.expected_stderr_file)
        if not expected_stdout and not expected_stderr:
            self.notify("no output verification is required")
            return

        if expected_stdout:
            res.stdout_diff = _compare_std_file("stdout", res.stdout_file, expected_stdout)
            if res.stdout_diff:
                res.failed = True
                self.notify("stdout differs from expected", dbg_pr=False)
                res.errmsg = f"stdout differs from expected\n{res.stdout_diff}"
                self.debug(res.errmsg)
                return

        if expected_stderr:
            if self.output_behavior == _OutputBehavior.Unify:
                self.warn("expected_stderr is ignored when output_behavior is 'unify'")
                return
            res.stderr_diff = _compare_std_file("stderr", res.stderr_file, expected_stderr)
            if res.stderr_diff:
                res.failed = True
                self.notify("stderr differs from expected", dbg_pr=False)
                res.errmsg = f"stderr differs from expected\n{res.stderr_diff}"
                self.debug(res.errmsg)
                return
        self.notify("output is verified")

    _STOP_WAIT_INTERVAL = 0.1

    def _stop(self) -> None:
        if self.p and self.p.poll() is None:
            self.notify("Stopping process...{self.p.pid}")
            self.p.terminate()

            time_waited = 0

            # Poll every interval until process is terminated
            while time_waited <= self.exec_model.stop_process_wait:
                if self.p.poll() is not None:  # Process exited
                    return
                time.sleep(self._STOP_WAIT_INTERVAL)
                time_waited += self._STOP_WAIT_INTERVAL

            if self.p.poll() is not None:  # Process exited
                return
            # If still running after timeout, force kill
            self.notify("Process termination timeout, forcing kill...")
            self.p.kill()

    def _detail_value(self, key: str, printable: bool, setup: bool = False, **_) -> Any:
        if key == "env":
            env = self.env if setup else self.exec_model.env
            if not env:
                return super()._detail_value(key, printable)
            if not printable or isinstance(env, str):
                return env
            return "\n".join([f"{k}='{v}'" for k, v in env.items()])

        if key == "output_filters":
            filters = self.output_filters if setup else self.exec_model.output_filters
            if not filters:
                return super()._detail_value(key, printable)
            ret = ""
            for i, f in enumerate(filters):
                ret += (f"[{i}] From: '{f.from_str}'\n"
                        f"    To: '{f.to_str}'\n"
                        f"    Regex: {f.regex}\n")
            return ret

        if not setup:
            return super()._detail_value(key, printable)
        setup_keys = {"cmd", "cwd", "use_shell", "shell_path", "env_file",
                      "expected_stdout", "expected_stderr", " expected_stdout_file",
                      "expected_stderr_file"}
        if key not in setup_keys:
            return super()._detail_value(key, printable)
        try:
            value = getattr(self, key)
            if key == "use_shell" and printable:
                return yes_no_str(value)
            return value
        except AttributeError:
            return f"[Unknown attribute - {key}]"

    def _printable_field_name(self, name: str) -> str:
        if name == "allowed_rc":
            return "Allowed return codes"
        if name == "cmd":
            return "Command"
        if name == "cwd":
            return "Working directory"
        if name == "env":
            return "Environment variables"
        return super()._printable_field_name(name)
