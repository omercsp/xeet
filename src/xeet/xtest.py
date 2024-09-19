from xeet import LogLevel
from xeet.common import XeetException, XeetVars, NonEmptyStr, pydantic_errmsg
from xeet.log import log_info, log_raw, log_error, log_verbose
from xeet.pr import create_print_func, pr_info
from typing import Any
from pydantic import BaseModel, Field, ValidationError, ConfigDict, AliasChoices
from timeit import default_timer as timer
from typing import ClassVar
from enum import auto, Enum
from dataclasses import dataclass
from io import TextIOWrapper
import shlex
import subprocess
import signal
import os
import sys
import json


_ORANGE = '\033[38;5;208m'
_pr_orange = create_print_func(_ORANGE, LogLevel.ALWAYS)


class XeetRunException(XeetException):
    ...


class TestStatusCategory(str, Enum):
    Undefined = "Undefined"
    Skipped = "Skipped"
    NotRun = "Not run"
    Failed = "Failed"
    Passed = "Passed"
    Unknown = "Unknown"


class TestStatus(Enum):
    Undefined = auto()
    Skipped = auto()
    InitErr = auto()
    PreRunErr = auto()
    RunErr = auto()  # This isn't a test failure per se, but a failure to run the test
    VerifyRunErr = auto()
    VerifyRcFailed = auto()
    VerifyFailed = auto()
    UnexpectedPass = auto()
    Timeout = auto()
    Passed = auto()
    ExpectedFail = auto()


_NOT_RUN_STTS = {TestStatus.InitErr, TestStatus.PreRunErr, TestStatus.RunErr,
                 TestStatus.VerifyRunErr}
_FAILED_STTS = {TestStatus.VerifyFailed, TestStatus.VerifyRcFailed, TestStatus.UnexpectedPass,
                TestStatus.Timeout}
_PASSED_STTS = {TestStatus.Passed, TestStatus.ExpectedFail}


def status_catgoery(status: TestStatus) -> TestStatusCategory:
    if status == TestStatus.Undefined:
        return TestStatusCategory.Undefined
    if status == TestStatus.Skipped:
        return TestStatusCategory.Skipped
    if status in _NOT_RUN_STTS:
        return TestStatusCategory.NotRun
    if status in _FAILED_STTS:
        return TestStatusCategory.Failed
    if status in _PASSED_STTS:
        return TestStatusCategory.Passed
    return TestStatusCategory.Unknown


@dataclass
class TestResult:
    status: TestStatus = TestStatus.Undefined
    rc: int | None = None
    allowed_rc: set[int] | None = None
    pre_cmd_rc: int | None = None
    verify_cmd_rc: int | None = None
    post_cmd_rc: int | None = None
    duration: float = 0
    filter_ok = False
    stdout_file: str = ""
    stderr_file: str = ""
    unified_output: bool = True
    verify_output_file: str = ""
    pre_test_output_file: str = ""
    post_test_output_file: str = ""
    status_reason: str = ""
    post_test_err: str = ""
    timeout_period: float | None = None

    @property
    def pre_test_ok(self) -> bool:
        return self.pre_cmd_rc == 0 or self.pre_cmd_rc is None

    @property
    def post_test_ok(self) -> bool:
        return self.post_cmd_rc == 0 or self.post_cmd_rc is None


class _OutputBehavior(str, Enum):
    Unify = "unify"
    Split = "split"


_EMPTY_STR = ""


class XtestModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: NonEmptyStr
    base: str = _EMPTY_STR
    abstract: bool = False
    short_desc: str = Field(_EMPTY_STR, max_length=75)
    long_desc: str = _EMPTY_STR
    groups: list[NonEmptyStr] | None = None
    allowed_rc: set[int] | None = Field(
        None, validation_alias=AliasChoices("allowed_rc", "allowed_return_codes"))
    ignore_rc: bool | None = None
    timeout: float | None = None
    shell_path: str | None = None
    pre_cmd: str | None = None
    pre_cmd_shell: bool | None = None
    cmd: str | None = None
    shell: bool | None = None
    verify_cmd: str | None = None
    verify_cmd_shell: bool | None = None
    post_cmd: str | None = None
    post_cmd_shell: bool | None = None
    expected_failure: bool | None = None
    output_behavior: _OutputBehavior | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None
    env_file: str | None = None
    skip: bool | None = None
    skip_reason: str | None = None
    var_map: dict[str, str] | None = Field(
        None, validation_alias=AliasChoices("var_map", "variables", "vars"))

    use_os_env: bool | None = None

    # Inheritance behavior
    inherit_variables: bool = True
    inherit_env_variables: bool = True

    inhertit_ignore_fields: ClassVar[set[str]] = {"model_config", "name", "base", "abstract",
                                                  "short_desc", "long_desc", "env", "var_map"}

    def inherit(self, other: "XtestModel") -> None:
        for f in self.model_fields.keys():
            if f in self.inhertit_ignore_fields or f.startswith("inherit_"):
                continue
            val = getattr(self, f)
            if val is not None:
                continue
            other_val = getattr(other, f)
            if other_val is not None:
                setattr(self, f, other_val)

        if self.inherit_variables and other.var_map:
            if self.var_map:
                self.var_map = {**other.var_map, **self.var_map}
            else:
                self.var_map = {**other.var_map}

        if self.inherit_env_variables and other.env:
            if self.env:
                self.env = {**other.env, **self.env}
            else:
                self.env = {**other.env}


class Xtest:
    def __init__(self, desc: dict, output_base_dir: str, xeet_root: str,
                 dflt_shell_path: str | None):
        self.name = desc.get("name", "<no name>").strip()
        if not self.name:
            self.init_err = "No name"
            return
        try:
            self.model = XtestModel(**desc)
        except ValidationError as e:
            self.init_err = f"Error parsing test '{self.name}' - {pydantic_errmsg(e)}"
            return
        self._log_info(f"initializing test {self.name}")
        self.output_dir = f"{output_base_dir}/{self.name}"
        self._log_info(f"{self.output_dir=}")
        self.stdout_file = f"{self.output_dir}/stdout"
        self.stderr_file = f"{self.output_dir}/stderr"
        self.shell_path = self.model.shell_path
        self.debug_mode = False
        if not self.shell_path and dflt_shell_path:
            self.shell_path = dflt_shell_path

        self.base = self.model.base
        self.xeet_root = xeet_root
        self.init_err = _EMPTY_STR

        self.pre_cmd_expanded = _EMPTY_STR
        self.cmd_expanded = _EMPTY_STR
        self.post_cmd_expanded = _EMPTY_STR
        self.verify_cmd_expanded = _EMPTY_STR
        self.env_expanded = {}
        self.cwd_expanded = _EMPTY_STR
        self.env_file_expanded = _EMPTY_STR
        self.env_expanded = {}

        if not self.shell_path and dflt_shell_path:
            self.shell_path = dflt_shell_path
        if not self.shell_path:
            self.shell_path = os.getenv("SHELL", "/usr/bin/sh")

    def inherit(self, other: "Xtest") -> None:
        if other.init_err:
            self.init_err = other.init_err
            return
        self.model.inherit(other.model)

    @staticmethod
    def _setting_val(value: Any, dflt: Any) -> Any:
        if value is None:
            return dflt
        if isinstance(value, str):
            return value.strip()
        return value

    @property
    def allowed_rc(self) -> set[int]:
        return self._setting_val(self.model.allowed_rc, {0})

    @property
    def ignore_rc(self) -> bool:
        return self._setting_val(self.model.ignore_rc, False)

    @property
    def skip(self) -> bool:
        return self._setting_val(self.model.skip, False)

    @property
    def skip_reason(self) -> str:
        return self._setting_val(self.model.skip_reason, _EMPTY_STR)

    @property
    def output_behavior(self) -> _OutputBehavior:
        return self._setting_val(self.model.output_behavior, _OutputBehavior.Unify)

    @property
    def expected_failure(self) -> bool:
        return self._setting_val(self.model.expected_failure, False)

    @property
    def short_desc(self) -> str:
        return self.model.short_desc.strip()

    @property
    def long_desc(self) -> str:
        return self.model.long_desc.strip()

    @property
    def pre_cmd(self) -> str:
        return self._setting_val(self.model.pre_cmd, _EMPTY_STR)

    @property
    def pre_cmd_shell(self) -> bool:
        return self._setting_val(self.model.pre_cmd_shell, False)

    @property
    def cmd_shell(self) -> bool:
        return self._setting_val(self.model.shell, False)

    @property
    def cmd(self) -> str:
        return self._setting_val(self.model.cmd, _EMPTY_STR)

    @property
    def post_cmd(self) -> str:
        return self._setting_val(self.model.post_cmd, _EMPTY_STR)

    @property
    def post_cmd_shell(self) -> bool:
        return self._setting_val(self.model.post_cmd_shell, False)

    @property
    def verify_cmd(self) -> str:
        return self._setting_val(self.model.verify_cmd, _EMPTY_STR)

    @property
    def verify_cmd_shell(self) -> bool:
        return self._setting_val(self.model.verify_cmd_shell, False)

    @property
    def var_map(self) -> dict[str, str]:
        return self._setting_val(self.model.var_map, dict())

    @property
    def inherit_variables(self) -> bool:
        return self.model.inherit_variables

    @property
    def abstract(self) -> bool:
        return self.model.abstract

    @property
    def cwd(self) -> str:
        return self._setting_val(self.model.cwd, _EMPTY_STR)

    @property
    def env(self) -> dict[str, str]:
        return self._setting_val(self.model.env, dict())

    @property
    def env_file(self) -> str:
        return self._setting_val(self.model.env_file, _EMPTY_STR)

    @property
    def use_os_env(self) -> bool:
        return self._setting_val(self.model.use_os_env, True)

    @property
    def timeout(self) -> float | None:
        return self.model.timeout

    @property
    def groups(self) -> set[str]:
        if not self.model.groups:
            return set()
        return {g.root.strip() for g in self.model.groups}

    def _auto_vars(self) -> dict[str, str]:
        return {
            "TEST_NAME": self.name,
            "TEST_OUTPUT_DIR": self.output_dir,
            "TEST_STDOUT": self.stdout_file,
            "TEST_STDERR": self.stderr_file,
        }

    def expand(self) -> None:
        xvars = XeetVars(self.model.var_map)
        xvars.set_vars(self._auto_vars(), system=True)
        self._log_info(f"Auto variables:")
        for k, v in xvars.vars_map.items():
            log_raw(f"{k}={v}")
        self._log_info(f"Expanding '{self.name}' internals")
        self.env_expanded = {xvars.expand(k): xvars.expand(v) for k, v in self.env.items()}
        if self.cwd:
            self.cwd_expanded = xvars.expand(self.cwd)

        self.cmd_expanded = xvars.expand(self.cmd)
        self.pre_cmd_expanded = xvars.expand(self.pre_cmd)
        self.post_cmd_expanded = xvars.expand(self.post_cmd)
        self.verify_cmd_expanded = xvars.expand(self.verify_cmd)

        if self.env_file:
            self.env_file_expanded = xvars.expand(self.env_file)
        for k, v in self.env.items():
            name = k.strip()
            if not name:
                continue
            self.env_expanded[k] = xvars.expand(v)

    def _mkdir_output_dir(self) -> None:
        self._log_info(f"setting up output directory '{self.output_dir}'")
        if os.path.isdir(self.output_dir):
            # Clear the output director
            for f in os.listdir(self.output_dir):
                try:
                    os.remove(os.path.join(self.output_dir, f))
                except OSError as e:
                    raise XeetRunException(f"Error removing file '{f}' - {e.strerror}")
        else:
            try:
                log_verbose("Creating output directory if it doesn't exist: '{}'", self.output_dir)
                os.makedirs(self.output_dir, exist_ok=False)
            except OSError as e:
                raise XeetRunException(f"Error creating output directory - {e.strerror}")

    def run(self) -> TestResult:
        res = TestResult()
        if self.init_err:
            res.status = TestStatus.InitErr
            return res
        if self.skip:
            res.status = TestStatus.Skipped
            res.status_reason = self.skip_reason
            self._log_info("marked to be skipped")
            return res
        if not self.cmd:
            self._log_info("No command for test, will not run")
            res.status = TestStatus.RunErr
            res.status_reason = "No command"
            return res

        if self.abstract:
            raise XeetRunException("Can't run abstract tasks")

        self._log_info("starting run")
        if self.cwd_expanded:
            self._log_info(f"working directory will be set to '{self.cwd_expanded}'")
        else:
            self._log_info("using default working directory")
        if self.env:
            self._log_info("command environment variables:")
            for k, v in self.env_expanded.items():
                log_raw(f"{k}={v}")

        try:
            env = self._read_env_vars()
        except XeetRunException as e:
            res.status = TestStatus.RunErr
            res.status_reason = str(e)
            return res

        self._mkdir_output_dir()
        log_verbose("test commands is '{}'", self.cmd)
        self._pre_test(res, env)
        self._run(res, env)
        self._verify(res, env)
        self._post_test(res, env)

        if res.status == TestStatus.Passed or res.status == TestStatus.ExpectedFail:
            self._log_info("completed successfully")
        return res

    def _debug_pre_step_print(self, step_name: str, command, shell: bool) -> None:
        if not self.debug_mode:
            return
        shell_str = " (shell)" if shell else ""
        _pr_orange(f">>>>>>> {step_name} <<<<<<<\nCommand{shell_str}:")
        pr_info(command)
        _pr_orange("Execution output:")
        sys.stdout.flush()  # to make sure colors are reset

    def _debug_step_print(self, step_name: str, rc: int) -> None:
        if not self.debug_mode:
            return
        _pr_orange(f"{step_name} rc: {rc}\n")

    @staticmethod
    def _cmd_array(cmd: str, shell: bool) -> list[str]:
        if shell:
            return [cmd]
        return shlex.split(cmd)

    def _pre_test(self, res: TestResult, env: dict) -> None:
        if not self.pre_cmd_expanded:
            return
        shell = self.pre_cmd_shell
        self._debug_pre_step_print("Pre-test", self.pre_cmd_expanded, shell)
        cmd = self._cmd_array(self.pre_cmd_expanded, shell)
        res.pre_test_output_file = f"{self.output_dir}/pre_run_output"
        cmd_args = {
            "args": cmd,
            "text": True,
            "shell": shell,
            "env": env
        }
        try:
            self._log_info(f"running pre-test command '{cmd}'")
            if self.debug_mode:
                p = subprocess.run(**cmd_args)
            else:
                with open(res.pre_test_output_file, "w") as f:
                    p = subprocess.run(**cmd_args, stdout=f, stderr=f)
        except OSError as e:
            log_error(f"Error running pre-test command- {e.strerror}", pr=None)
            res.status = TestStatus.PreRunErr
            res.status_reason = str(e)
            return

        res.pre_cmd_rc = p.returncode
        self._log_info(f"Pre-test command returned: {p.returncode}")
        self._debug_step_print("Pre-test", p.returncode)
        if p.returncode == 0:
            return
        self._log_info(f"Pre-test failed")
        res.status = TestStatus.PreRunErr
        res.status_reason = f"Pre-test failed with rc={p.returncode}"

    def _get_test_io_descriptors(self) -> tuple[TextIOWrapper | int, TextIOWrapper | int]:
        err_file = subprocess.DEVNULL
        out_file = open(self.stdout_file, "w")
        if self.output_behavior == _OutputBehavior.Unify:
            err_file = out_file
        else:
            err_file = open(self.stderr_file, "w")
        return out_file, err_file

    def _read_env_vars(self) -> dict:
        ret = {}
        if self.use_os_env:
            ret.update(os.environ)
        if self.env_file_expanded:
            try:
                self._log_info(f"reading env file '{self.env_file_expanded}'")
                with open(self.env_file_expanded, "r") as f:
                    data = json.load(f)
                    #  err = validate_env_schema(data)
                    #  if err:
                    #      raise XeetRunException(f"Error reading env file - {err}")
                    ret.update(data)
            except OSError as e:
                raise XeetRunException(f"Error reading env file - {e.strerror}")
        if self.env_expanded:
            ret.update(self.env_expanded)
        return ret

    def _run(self, res: TestResult, env: dict) -> None:
        if res.status != TestStatus.Undefined:
            self._log_info("Skipping run. Prior step failed")
            return
        subproc_args: dict = {
            "env": env,
            "cwd": self.cwd_expanded if self.cwd_expanded else None,
            "shell": self.cmd_shell,
            "executable": self.shell_path if self.shell_path and self.cmd_shell else None,
        }
        self._log_info("running command:")
        log_raw(self.cmd)
        command = self.cmd_expanded
        if not self.cmd_shell and isinstance(command, str):
            command = shlex.split(command)
        subproc_args["args"] = command

        res.stdout_file = self.stdout_file
        res.stderr_file = self.stderr_file
        res.unified_output = self.output_behavior == _OutputBehavior.Unify

        p = None
        out_file, err_file = None, None
        try:
            start = timer()
            if self.debug_mode:
                subproc_args["timeout"] = self.model.timeout
                self._debug_pre_step_print("Test command", self.cmd_expanded, self.cmd_shell)
                p = subprocess.run(**subproc_args)
                res.rc = p.returncode
                assert isinstance(res.rc, int)
                self._debug_step_print("Test command", res.rc)
            else:
                out_file, err_file = self._get_test_io_descriptors()
                subproc_args["stdout"] = out_file
                subproc_args["stderr"] = err_file
                p = subprocess.Popen(**subproc_args)
                res.rc = p.wait(self.timeout)
            res.duration = timer() - start
            self._log_info(f"command finished with rc={res.rc} in {res.duration:.3f}s")
        except OSError as e:
            self._log_info(str(e))
            res.status = TestStatus.RunErr
            res.status_reason = str(e.strerror)
        except subprocess.TimeoutExpired as e:
            assert p is not None
            try:
                p.kill()
                p.wait()
            except OSError as kill_e:
                log_error(f"Error killing process - {kill_e}")
            self._log_info(str(e))
            res.status = TestStatus.Timeout
            res.timeout_period = self.timeout
        except KeyboardInterrupt:
            if p and not self.debug_mode:
                p.send_signal(signal.SIGINT)  # type: ignore
                p.wait()  # type: ignore
            raise XeetRunException("User interrupt")
        finally:
            if isinstance(out_file, TextIOWrapper):
                out_file.close()
            if isinstance(err_file, TextIOWrapper):
                err_file.close()

    def _verify_test_rc(self, res: TestResult) -> None:
        if self.debug_mode:
            pr_info("Verifying rc")

        if res.status != TestStatus.Undefined:
            self._log_info("Skipping verification, prior step failed")
            return

        if self.ignore_rc or res.rc in self.allowed_rc:
            return

        #  RC error
        allowed_str = ",".join([str(x) for x in self.allowed_rc])
        err = f"retrun code {res.rc}, not in allowed return codes ({allowed_str})"
        self._log_info(f"failed: {err}")
        res.status = TestStatus.VerifyRcFailed
        res.status_reason = err
        if self.debug_mode:
            pr_info(f"Verification failed: {err}")

    def _run_verify_cmd(self, res: TestResult, env: dict) -> None:
        if not self.verify_cmd:
            self._log_info("No verification command")
            return

        if res.status != TestStatus.Undefined:
            self._log_info("Skipping verification command run, prior step failed")
            return

        self._debug_pre_step_print("Verification", self.verify_cmd_expanded, self.verify_cmd_shell)
        self._log_info(f"verifying with '{self.verify_cmd_expanded}'")
        try:
            res.verify_output_file = f"{self.output_dir}/verification_output"
            verify_args = {
                "args": self._cmd_array(self.verify_cmd_expanded, self.verify_cmd_shell),
                "text": True,
                "shell": self.verify_cmd_shell,
                "env": env
            }
            if self.debug_mode:
                p = subprocess.run(**verify_args)
            else:
                with open(res.verify_output_file, "w") as f:
                    p = subprocess.run(**verify_args, stdout=f, stderr=f)
            msg = f"Verification command = {p.returncode}"
            self._log_info(msg)
            res.verify_cmd_rc = p.returncode
            self._debug_step_print("Verification", p.returncode)
            if p.returncode == 0:
                return
            res.status = TestStatus.VerifyFailed
            if self.debug_mode:
                return
            res.status_reason = f"Verification failed with rc={p.returncode}"
        except OSError as e:
            res.status = TestStatus.VerifyRunErr
            log_error(f"Error running verification command- {e}")
            res.status_reason = f"Verification run error: {e.strerror}"

    def _verify(self, res: TestResult, env: dict) -> None:
        self._verify_test_rc(res)
        self._run_verify_cmd(res, env)

        # This is a bit of a hack, until verifications are generic plugins. For now we include
        # the default RC and user command verificaionts.
        if self.expected_failure:
            if (res.status == TestStatus.VerifyFailed or
                    res.status == TestStatus.VerifyRcFailed):
                res.status = TestStatus.ExpectedFail
            elif res.status == TestStatus.Undefined:
                res.status = TestStatus.UnexpectedPass

        if res.status == TestStatus.Undefined:
            res.status = TestStatus.Passed

    def _post_test(self, res: TestResult, env: dict) -> None:
        if not self.post_cmd:
            self._log_info("Skipping post-test, no command")
            return
        self._debug_pre_step_print("Post-test", self.post_cmd_expanded, self.post_cmd_shell)
        self._log_info(f"post-test command '{self.post_cmd_expanded}'")
        try:
            res.post_test_output_file = f"{self.output_dir}/post_test_output"
            run_args = {
                "args": self._cmd_array(self.post_cmd_expanded, self.post_cmd_shell),
                "text": True,
                "shell": self.post_cmd_shell,
                "env": env
            }
            if self.debug_mode:
                p = subprocess.run(**run_args)
            else:
                with open(res.post_test_output_file, "w") as f:
                    p = subprocess.run(**run_args, stdout=f, stderr=f)
            msg = f"Post-test RC = {p.returncode}"
            self._log_info(msg)
            res.post_cmd_rc = p.returncode
            self._debug_step_print("Post-test", p.returncode)
        except OSError as e:
            log_error(f"Post test run failed - {e}", pr=False)
            res.post_test_err = str(e)

    @staticmethod
    def _valid_file(file: str | None) -> bool:
        return file is not None and os.path.isfile(file) and os.path.getsize(file) > 0

    def _log_info(self, msg: str, *args, **kwargs) -> None:
        log_info(f"{self.name}: {msg}", *args, depth=1, **kwargs)
