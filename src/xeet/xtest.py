from io import TextIOWrapper
from xeet.config import Config, TestDesc
from xeet.common import (XeetException, StringVarExpander, parse_assignment_str, get_global_vars,
                         validate_json_schema, NAME, GROUPS, ABSTRACT, BASE, ENV, INHERIT_ENV,
                         INHERIT_VARIABLES, INHERIT_GROUPS, SHORT_DESC, VARIABLES, XeetVars)
from xeet.log import (log_info, log_raw, log_error, logging_enabled_for, log_verbose, INFO)
from xeet.pr import pr_orange
from typing import Optional
import shlex
import subprocess
import signal
import os
import difflib
from timeit import default_timer as timer
from typing import Union


XTEST_UNDEFINED = -1
XTEST_PASSED = 0
XTEST_FAILED = 1
XTEST_SKIPPED = 2
XTEST_NOT_RUN = 3
XTEST_EXPECTED_FAILURE = 4
XTEST_UNEXPECTED_PASS = 5


class TestResult(object):
    def __init__(self) -> None:
        super().__init__()
        self.status = XTEST_UNDEFINED
        self.rc: Optional[int] = None
        self.pre_run_rc: Optional[int] = None
        self.post_run_rc: Optional[int] = None
        self.short_comment: str = ""
        self.extra_comments: list[str] = []
        self.duration: float = 0
        self.run_ok = False
        self.filter_ok = False
        self.compare_stdout_ok = False
        self.compare_stderr_ok = False

    @property
    def pre_run_ok(self) -> bool:
        return self.pre_run_rc == 0 or self.pre_run_rc is None

    @property
    def post_run_ok(self) -> bool:
        return self.post_run_rc == 0 or self.post_run_rc is None


_SHELL = "shell"
_SHELLPATH = "shell_path"
_INHERIT_OS_ENV = "inherit_os_env"
_CWD = "cwd"
_SKIP = "skip"
_SKIP_REASON = "skip_reason"
_LONG_DESC = "description"
_COMMAND = "command"
_ALLOWED_RC = "allowed_return_codes"
_EXPECTED_FAILURE = "expected_failure"
_COMPARE_OUTPUT = "compare_output"
_OUTPUT_FILTER = "output_filter"
_PRE_COMMAND = "pre_command"
_POST_COMMAND = "post_command"
_OUTPUT_BEHAVIOR = "output_behavior"
_TIMEOUT = "timeout"

# Output behavior values
_UNIFY = "unify"
_SPLIT = "split"

# compare output keys
_STDOUT = "stdout"
_STDERR = "stderr"
_ALL = "all"
_NOTHING = "none"

_COMMAND_SCHEMA = {
    "anyOf": [
        {"type": "string", "minLength": 1},
        {"type": "array", "items": {"type": "string", "minLength": 1}}
    ]
}

TEST_SCHEMA = {
    "type": "object",
    "properties": {
        NAME: {"type": "string", "minLength": 1},
        BASE: {"type": "string", "minLength": 1},
        SHORT_DESC: {"type": "string", "maxLength": 75},
        _LONG_DESC: {"type": "string"},
        GROUPS: {
            "type": "array",
            "items": {"type": "string", "minLength": 1}
        },
        _COMMAND: _COMMAND_SCHEMA,
        _ALLOWED_RC: {
            "type": "array",
            "items": {"type": "integer", "minimum": 0, "maximum": 255}
        },
        _TIMEOUT: {
            "type": "integer",
            "minimum": 0
        },
        _COMPARE_OUTPUT: {"type": "string", "enum": [_ALL, _STDOUT, _STDERR, _NOTHING]},
        _OUTPUT_FILTER: _COMMAND_SCHEMA,
        _PRE_COMMAND: _COMMAND_SCHEMA,
        _POST_COMMAND: _COMMAND_SCHEMA,
        _EXPECTED_FAILURE: {"type": "boolean"},
        _OUTPUT_BEHAVIOR: {"enum": [_UNIFY, _SPLIT]},
        _CWD: {"type": "string", "minLength": 1},
        _SHELL: {"type": "boolean"},
        _SHELLPATH: {"type": "string", "minLength": 1},
        ENV: {
            "type": "object",
            "additionalProperties": {
                "type": "string"
            }
        },
        _INHERIT_OS_ENV: {"type": "boolean"},
        INHERIT_ENV: {"type": "boolean"},
        ABSTRACT: {"type": "boolean"},
        _SKIP: {"type": "boolean"},
        _SKIP_REASON: {"type": "string"},
        VARIABLES: {"type": "object"},
        INHERIT_VARIABLES: {"type": "boolean"},
        INHERIT_GROUPS: {"type": "boolean"}
    },
    "additionalProperties": False,
    "required": [NAME]
}


class XTest(object):
    def _log_info(self, msg: str, *args, **kwargs) -> None:
        #  kwargs['extra_frames'] = 1
        log_info(f"{self.name}: {msg}", *args, **kwargs)

    def __init__(self, desc: TestDesc, config: Config) -> None:
        super().__init__()
        self.name = desc.name
        self._log_info("initializing test")

        assert desc is not None
        task_descriptor = desc.target_desc
        self.init_err = validate_json_schema(task_descriptor, TEST_SCHEMA)
        if self.init_err:
            log_info(f"Error in test descriptor: {self.init_err}")
            return
        self.debug_mode = config.debug_mode
        self.xeet_root = config.xeet_root

        self.short_desc = task_descriptor.get(SHORT_DESC, None)
        self.long_desc = task_descriptor.get(_LONG_DESC, None)

        self.cwd = task_descriptor.get(_CWD, None)
        self.shell = task_descriptor.get(_SHELL, False)
        self.shell_path = task_descriptor.get(
            _SHELLPATH, config.default_shell_path())
        self.command = task_descriptor.get(_COMMAND, [])

        self.env_inherit = task_descriptor.get(_INHERIT_OS_ENV, True)
        self.env = task_descriptor.get(ENV, {})
        self.abstract = task_descriptor.get(ABSTRACT, False)
        self.skip = task_descriptor.get(_SKIP, False)
        self.skip_reason = task_descriptor.get(_SKIP_REASON, None)
        self.allowed_rc = task_descriptor.get(_ALLOWED_RC, [0])
        self.timeout = task_descriptor.get(_TIMEOUT, None)
        self.expected_failure = task_descriptor.get(_EXPECTED_FAILURE, False)
        self.output_behavior = task_descriptor.get(_OUTPUT_BEHAVIOR,
                                                   _SPLIT)
        self.output_dir = f"{config.output_dir}/{self.name}"
        self.stdout_file = f"{self.output_dir}/stdout"
        log_info(f"stdout file: {self.stdout_file}")
        if self.output_behavior == _SPLIT:
            self.stderr_file = f"{self.output_dir}/stderr"
            log_info(f"stderr file: {self.stderr_file}")
        else:
            self.stderr_file = None

        self.compare_output: str = task_descriptor.get(_COMPARE_OUTPUT,
                                                       _ALL)
        if self.compare_output in (_STDERR, _ALL) and \
                self.output_behavior == _UNIFY:
            self._log_info(("stderr comparison is not supported with unified output,"
                            " normalizing to 'stdout'"))
            self.compare_output = _STDOUT

        log_info(f"compare_output={self.compare_output}")
        self.output_filter: list = task_descriptor.get(_OUTPUT_FILTER, [])
        if isinstance(self.output_filter, str):
            self.output_filter = self.output_filter.split()
        if self.compare_output:
            self.expected_output_dir = f"{config.expected_output_dir}/{self.name}"
            self.expected_stdout_file = f"{self.expected_output_dir}/stdout"
            self.expected_stderr_file = f"{self.expected_output_dir}/stderr"
            self.out_diff_file = f"{self.output_dir}/stdout.diff"
            self.err_diff_file = f"{self.output_dir}/stderr.diff"
        else:
            self.expected_output_dir: str = None  # type: ignore
            self.expected_stdout_file: str = None  # type: ignore
            self.expected_stderr_file: str = None  # type: ignore
            self.out_diff_file: str = None  # type: ignore
            self.err_diff_file: str = None  # type: ignore

        self.post_command: list = task_descriptor.get(_POST_COMMAND, [])
        if isinstance(self.post_command, str):
            self.post_command = self.post_command.split()

        self.pre_command: list = task_descriptor.get(_PRE_COMMAND, [])
        if isinstance(self.pre_command, str):
            self.pre_command = self.pre_command.split()

        #  Handle CLI arguments override
        cmd = config.arg('cmd')
        if cmd:
            self.command = cmd
        cwd = config.arg('cwd')
        if cwd:
            self.cwd = cwd
        shell = config.arg('shell')
        if shell:
            self.shell = shell
        shell_path = config.arg('shell_path')
        if shell_path:
            self.shell_path = shell_path
        env = config.arg('env')
        if env:
            self.env = {}
            for e in env:
                e_name, e_value = parse_assignment_str(e)
                self.env[e_name] = e_value

        self.vars_map = task_descriptor.get(VARIABLES, {})
        variables = config.arg('variables')
        if variables:
            for v in variables:
                key, val = parse_assignment_str(v)
                self.vars_map[key] = val

        self.vars = XeetVars()
        self.vars.set_vars_raw(get_global_vars())
        self.vars.set_vars(self.vars_map)
        self.vars.set_vars({
            f"TEST_NAME": self.name,
            f"TEST_OUTPUT_DIR": self.output_dir,
            f"TEST_STDOUT": self.stdout_file,
            f"TEST_STDERR": self.stderr_file,
            f"TEST_CWD": self.cwd,
            f"TEST_DEBUG": "1" if self.debug_mode else "0",
        }, system=True)

        #  Finally, expand variables if needed
        if config.expand_task:
            self.expand()

        if isinstance(self.command, str):
            if self.shell:
                self.command = [self.command]
            else:
                self.command = shlex.split(self.command)

    def expand(self) -> None:
        expander = StringVarExpander(self.vars.get_vars())
        self._log_info("expanding")
        self.env = {expander(k): expander(v) for k, v in self.env.items()}
        if self.cwd:
            self.cwd = expander(self.cwd)
        if isinstance(self.command, str):
            self.command = expander(self.command)
        else:
            self.command = [expander(x) for x in self.command]

        if self.pre_command:
            self.pre_command = [expander(x) for x in self.pre_command]
        if self.post_command:
            self.post_command = [expander(x) for x in self.post_command]
        if self.output_filter:
            self.output_filter = [expander(x) for x in self.output_filter]
            log_info(f"output filter: {self.output_filter}")

    def _setup_output_dir(self) -> None:
        self._log_info(f"setting up output directory '{self.output_dir}'")
        if os.path.isdir(self.output_dir):
            # Clear the output director
            for f in os.listdir(self.output_dir):
                try:
                    os.remove(os.path.join(self.output_dir, f))
                except OSError as e:
                    raise XeetException(f"Error removing file '{f}' - {e}")
        else:
            try:
                log_verbose("Creating output directory if it doesn't exist: '{}'", self.output_dir)
                os.makedirs(self.output_dir, exist_ok=False)
            except OSError as e:
                raise XeetException(f"Error creating output directory - {e}")

    def _get_test_io_descriptors(self) -> \
            tuple[Union[TextIOWrapper, int], Union[TextIOWrapper, int]]:
        out_file = subprocess.DEVNULL
        err_file = subprocess.DEVNULL
        out_file = open(self.stdout_file, "w")
        if self.stderr_file:
            err_file = open(self.stderr_file, "w")
        elif self.output_behavior == _UNIFY:
            err_file = out_file
        return out_file, err_file

    def _run_cmd(self, res: TestResult) -> None:
        if res.status != XTEST_PASSED and res.status != XTEST_UNDEFINED:
            self._log_info("Skipping run. Prior step failed")
            return
        self._log_info("running command:")
        log_raw(self.command)
        p = None
        if self.env_inherit:
            env = os.environ
            env.update(self.env)
        else:
            env = self.env
        out_file, err_file = None, None
        try:
            start = timer()
            if self.debug_mode:
                self._debug_pre_step_print("Test command", self.command)  # type: ignore
                p = subprocess.run(self.command, shell=self.shell, executable=self.shell_path,
                                   env=env, cwd=self.cwd, timeout=self.timeout)
                res.rc = p.returncode
                self._debug_post_step_print("Test command", res.rc)
            else:

                out_file, err_file = self._get_test_io_descriptors()
                p = subprocess.Popen(self.command, shell=self.shell, executable=self.shell_path,
                                     env=env, cwd=self.cwd, stdout=out_file, stderr=err_file)
                res.rc = p.wait(self.timeout)

            res.duration = timer() - start
            self._log_info(f"command finished with rc={res.rc} in {res.duration:.3f}s")
            if res.rc in self.allowed_rc:
                if self.expected_failure:
                    self._log_info(f"unexpected pass")
                    res.status = XTEST_UNEXPECTED_PASS
                else:
                    res.status = XTEST_PASSED
            else:
                if self.expected_failure:
                    self._log_info(f"exepcted failure")
                    res.status = XTEST_EXPECTED_FAILURE
                else:
                    allowed = ",".join([str(x) for x in self.allowed_rc])
                    err = f"rc={res.rc}, allowed={allowed}"
                    self._log_info(f"failed: {err}")
                    res.status = XTEST_FAILED
                    res.short_comment = err

        except (OSError, FileNotFoundError) as e:
            self._log_info(f"run time error: {e}")
            res.status = XTEST_NOT_RUN
            res.extra_comments.append(str(e))
        except subprocess.TimeoutExpired as e:
            self._log_info(str(e))
            res.status = XTEST_FAILED
            res.extra_comments.append(str(e))
        except KeyboardInterrupt:
            if p and not self.debug_mode:
                p.send_signal(signal.SIGINT)  # type: ignore
                p.wait()  # type: ignore
            raise XeetException("User interrupt")
        finally:
            if isinstance(out_file, TextIOWrapper):
                out_file.close()
            if isinstance(err_file, TextIOWrapper):
                err_file.close()
        res.run_ok = res.status == XTEST_PASSED or res.status == XTEST_EXPECTED_FAILURE
        self._log_info(f"run_ok={res.run_ok}")

    def _filter_output(self, res: TestResult) -> None:
        if res.status != XTEST_PASSED:
            self._log_info("Skipping output filter, prior step failed")
            return
        if not self.output_filter:
            res.filter_ok = True
            return
        log_info("Filter command: '{}'".format(" ".join(self.output_filter)))
        try:
            p = subprocess.run(self.output_filter, capture_output=True, text=True)
            self._log_info(f"Filter command returned: {p.returncode}")
            if p.returncode == 0:
                res.filter_ok = True
                return
            self._log_info(f"Filter command stderr: {p.stderr}")
            res.status = XTEST_FAILED
            res.short_comment = f"output filter failed"
            res.extra_comments.append(f"Filter command returned: {p.returncode}")
            res.extra_comments.append(f"Filter stderr:")
            res.extra_comments.append(p.stderr)
            res.filter_ok = False
        except OSError as e:
            res.status = XTEST_NOT_RUN
            log_error(f"Error running filter output command- {e}", pr=False)
            res.short_comment = "Error filtering output:"
            res.extra_comments.append(str(e))
            res.filter_ok = False

    def _compare_file(self, res: TestResult, src_file: str, expected_file: str, diff_file: str,
                      stream_name: str) -> bool:

        file_exists = self._valid_file(src_file)
        expected_file_exists = self._valid_file(expected_file)

        if not file_exists and not expected_file_exists:
            return True

        if not file_exists:
            res.short_comment = f"Missing {stream_name}"
            msg = f"No {stream_name} created for test"
            res.extra_comments.append(msg)
            log_info(msg)
            res.status = XTEST_FAILED
            return False
        if not expected_file_exists:
            res.status = XTEST_FAILED
            res.short_comment = f"Unexpected {stream_name}"
            msg = f"Test yielded unexpected {stream_name}"
            log_info(msg)
            res.extra_comments.append(msg)
            return False

        # get file path related to self.xeet_root
        file_pr = os.path.relpath(src_file, self.xeet_root)
        expected_file_pr = os.path.relpath(expected_file, self.xeet_root)
        self._log_info(f"comparing {file_pr} with '{expected_file_pr}'")
        try:
            with open(src_file, "r") as file_fd, \
                    open(expected_file, "r") as expected_file_fd:
                diff = difflib.unified_diff(expected_file_fd.readlines(), file_fd.readlines(),
                                            fromfile=expected_file, tofile=src_file)
                diff = list(diff)
            if len(diff) == 0:
                self._log_info(f"{stream_name} matches")
                return True

            self._log_info(f"{stream_name} mismatch")
            res.status = XTEST_FAILED
            if diff_file:
                with open(diff_file, "w") as diff_file_fd:
                    diff_file_fd.writelines(diff)

            if res.short_comment:
                res.short_comment += f"{stream_name} mismatch"
            else:
                res.short_comment = f"{stream_name} mismatch"

            res.extra_comments.append(f"Diff head:\n>>>>>")
            for index, line in enumerate(diff):
                res.extra_comments.append(line.strip("\n"))
                if index > 5:
                    res.extra_comments.append("...")
                    break
            res.extra_comments.append("<<<<<")
            res.extra_comments.append(f"Full diff file: {self.out_diff_file}")

        except OSError as e:
            res.status = XTEST_NOT_RUN
            err = f"Error comparing output - {e}"
            log_error(err, pr=False)
            res.short_comment = "Error comparing output"
            res.extra_comments.append(err)
            res.extra_comments.append("Output comparison skipped")
        return False

    def _compare_output(self, res: TestResult) -> None:
        if res.status != XTEST_PASSED:
            self._log_info("Skipping output comparison, prior step failed")
            return
        if self.compare_output == _NOTHING or self.debug_mode:
            self._log_info("Skipping output comparison, prior step failed")
            res.compare_stderr_ok = True
            res.compare_stdout_ok = True
            return

        # Compare stdout
        if self.compare_output == _STDERR:
            self._log_info("skipping stdout comparison")
            res.compare_stdout_ok = True
        else:
            res.compare_stdout_ok = self._compare_file(res, self.stdout_file,
                                                       self.expected_stdout_file,
                                                       self.out_diff_file,
                                                       "stdout")

        # Compare stderr
        if self.compare_output == _STDOUT:
            self._log_info("skipping stderr comparison")
            res.compare_stderr_ok = True
        else:
            if not self.stderr_file:
                self._log_info("Can't compare stderr, since output_behavior is 'unify'")
                res.compare_stderr_ok = False
                res.status = XTEST_NOT_RUN
                return
            res.compare_stderr_ok = self._compare_file(res, self.stderr_file,
                                                       self.expected_stderr_file,
                                                       self.err_diff_file,
                                                       "stderr")

        if not res.compare_stderr_ok or not res.compare_stdout_ok:
            res.status = XTEST_FAILED

    def _debug_pre_step_print(self, step_name: str, command: list[str]) -> None:
        pr_orange(f">>>>>>> {step_name} <<<<<<<\nCommand:")
        print(" ".join(command))
        pr_orange("Output:")

    def _debug_post_step_print(self, step_name: str, rc: int) -> None:
        pr_orange(f"{step_name} rc={rc}\n")

    def _post_run(self, res: TestResult) -> None:
        if res.status != XTEST_PASSED:
            log_info("Skipping post run, prior step failed")
            return
        if not self.post_command:
            log_info("Skipping post run, no command")
            return
        if self.debug_mode:
            self._debug_pre_step_print("Post run", self.post_command)
        self._log_info(f"verifying with '{self.post_command}'")
        try:
            if self.debug_mode:
                p = subprocess.run(self.post_command, text=True)
            else:
                p = subprocess.run(self.post_command, capture_output=True, text=True)
            msg = f"Post run command = {p.returncode}"
            self._log_info(msg)
            res.post_run_rc = p.returncode
            if p.returncode == 0:
                return
            res.status = XTEST_FAILED
            if self.debug_mode:
                self._debug_post_step_print("Post run", p.returncode)
                return
            res.short_comment = f"Post run failed"
            if p.stderr and len(p.stderr) > 0:
                msg += f", stderr tail:"
                res.extra_comments.append(msg)
                res.extra_comments.extend(p.stderr.splitlines()[-5:])
            else:
                msg += ", empty post run stderr"
                res.extra_comments.append(msg)
        except OSError as e:
            res.status = XTEST_NOT_RUN
            log_error(f"Error running post run command- {e}", pr=False)
            res.short_comment = "Post run error:"
            res.extra_comments.append(str(e))

    def _pre_run(self, res: TestResult) -> None:
        if not self.pre_command:
            return
        self._log_info(f"running pre_command '{self.pre_command}'")
        if self.debug_mode:
            self._debug_pre_step_print("Pre run", self.pre_command)
        try:
            p = subprocess.run(self.pre_command, capture_output=not self.debug_mode, text=True)
            self._log_info(f"Pre run command returned: {p.returncode}")
            res.pre_run_rc = p.returncode
            if self.debug_mode:
                self._debug_post_step_print("Pre run", p.returncode)
            if p.returncode == 0:
                return
            self._log_info(f"Pre run failed")
            res.status = XTEST_NOT_RUN
            res.short_comment = f"Pre run command RC={p.returncode}"
        except OSError as e:
            log_error(f"Error running pre run command- {e}", pr=False)
            res.status = XTEST_NOT_RUN
            res.short_comment = f"Pre run failure"
            res.extra_comments.append(str(e))
            res.pre_run_rc = -1

    def run(self, res: TestResult) -> None:
        if self.init_err:
            res.status = XTEST_NOT_RUN
            res.extra_comments.append(self.init_err)
            return
        if self.skip:
            self._log_info("marked to be skipped")
            res.status = XTEST_SKIPPED
            res.short_comment = "marked as skip{}".format(
                f" - {self.skip_reason}" if self.skip_reason else "")
            return
        if not self.command:
            self._log_info("No command for test, will not run")
            res.status = XTEST_NOT_RUN
            res.short_comment = "No command"
            return

        if self.abstract:
            raise XeetException("Can't run abstract tasks")

        self._log_info("starting run")
        if logging_enabled_for(INFO):
            if self.cwd:
                self._log_info(f"working directory will be set to '{self.cwd}'")
            else:
                self._log_info("no working directory will be set")
            if self.env:
                self._log_info("command Environment variables:")
                for k, v in self.env.items():
                    log_raw(f"{k}={v}")

        self.vars.update_os_env()
        self._setup_output_dir()
        log_verbose("_COMMAND is '{}'", self.command)
        self._pre_run(res)
        self._run_cmd(res)
        self._filter_output(res)
        self._compare_output(res)
        self._post_run(res)
        self.vars.restore_os_env()

        if not res.run_ok and res.status != XTEST_NOT_RUN and not self.debug_mode:
            if self.output_behavior == _UNIFY:
                output_msg = ("Unfified stdout/stderr:"
                              f"{os.path.relpath(self.stdout_file, self.xeet_root)}")
            else:
                output_msg = "Test stdout/stderr: "
                if self._valid_file(self.stdout_file):
                    output_msg += os.path.relpath(self.stdout_file, self.xeet_root)  # type: ignore
                else:
                    output_msg += "(Empty stdout)"
                output_msg += ", "
                if self._valid_file(self.stderr_file):
                    output_msg += os.path.relpath(self.stderr_file, self.xeet_root)  # type: ignore
                else:
                    output_msg += "(Empty stderr)"
            res.extra_comments.append(output_msg)

        if res.status == XTEST_PASSED:
            self._log_info("completed successfully")

    @staticmethod
    def _valid_file(file: Optional[str]) -> bool:
        return file is not None and os.path.isfile(file) and os.path.getsize(file) > 0
