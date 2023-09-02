from io import TextIOWrapper
from xeet.config import XeetConfig, XTestDesc
from xeet.schemas import CompareOutputKeys, XTestKeys, OutputBehaviorValues, XTEST_SCHEMA
from xeet.common import (XeetException, StringVarExpander, parse_assignment_str,
                         validate_json_schema)
from xeet.log import (log_info, log_raw, log_error, logging_enabled_for, log_verbose, INFO)
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


class XTestResult(object):
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


class XTest(object):
    def _log_info(self, msg: str, *args, **kwargs) -> None:
        #  kwargs['extra_frames'] = 1
        log_info(f"{self.name}: {msg}", *args, **kwargs)

    def __init__(self, xdesc: XTestDesc, config: XeetConfig) -> None:
        super().__init__()
        self.name = xdesc.name
        self._log_info("initializing test")

        assert xdesc is not None
        task_descriptor = xdesc.target_desc
        self.init_err = validate_json_schema(task_descriptor, XTEST_SCHEMA)
        if self.init_err:
            log_info(f"Error in test descriptor: {self.init_err}")
            return
        self.debug_mode = config.debug_mode
        self.xeet_root = config.xeet_root

        self.short_desc = task_descriptor.get(XTestKeys.ShortDesc, None)
        self.long_desc = task_descriptor.get(XTestKeys.LongDesc, None)

        self.cwd = task_descriptor.get(XTestKeys.Cwd, None)
        self.shell = task_descriptor.get(XTestKeys.Shell, False)
        self.shell_path = task_descriptor.get(
            XTestKeys.ShellPath, config.default_shell_path())
        self.command = task_descriptor.get(XTestKeys.Command, [])

        self.env_inherit = task_descriptor.get(XTestKeys.InheritOsEnv, True)
        self.env = task_descriptor.get(XTestKeys.Env, {})
        self.abstract = task_descriptor.get(XTestKeys.Abstract, False)
        self.skip = task_descriptor.get(XTestKeys.Skip, False)
        self.skip_reason = task_descriptor.get(XTestKeys.SkipReason, None)
        self.allowed_rc = task_descriptor.get(XTestKeys.AllowedRc, [0])
        self.timeout = task_descriptor.get(XTestKeys.Timeout, None)
        self.expected_failure = task_descriptor.get(XTestKeys.ExpectedFailure, False)
        self.output_behavior = task_descriptor.get(XTestKeys.OutputBehavior,
                                                   OutputBehaviorValues.Split)
        self.output_dir = config.output_dir
        self.out_base_name = f"{config.output_dir}/{self.name}"
        self.stdout_file = f"{self.out_base_name}.out"
        log_info(f"stdout file: {self.stdout_file}")
        if self.output_behavior == OutputBehaviorValues.Split:
            self.stderr_file = f"{self.out_base_name}.err"
            log_info(f"stderr file: {self.stderr_file}")
        else:
            self.stderr_file = None

        self.compare_output: str = task_descriptor.get(XTestKeys.CompareOutput,
                                                       CompareOutputKeys.All)
        if self.compare_output in (CompareOutputKeys.Stderr, CompareOutputKeys.All) and \
                self.output_behavior == OutputBehaviorValues.Unify:
            self._log_info(("stderr comparison is not supported with unified output,"
                            " normalizing to 'stdout'"))
            self.compare_output = CompareOutputKeys.Stdout

        log_info(f"compare_output={self.compare_output}")
        self.output_filter: list = task_descriptor.get(XTestKeys.OutputFilter, [])
        if isinstance(self.output_filter, str):
            self.output_filter = self.output_filter.split()
        if self.compare_output:
            self.expected_stdout_file = f"{config.default_expected_output_dir}/{self.name}.out"
            self.expected_stderr_file = f"{config.default_expected_output_dir}/{self.name}.err"
            self.out_diff_file = f"{config.output_dir}/{self.name}.out.diff"
            self.err_diff_file = f"{config.output_dir}/{self.name}.err.diff"
        else:
            self.expected_stdout_file: str = None  # type: ignore
            self.expected_stderr_file: str = None  # type: ignore
            self.out_diff_file: str = None  # type: ignore
            self.err_diff_file: str = None  # type: ignore

        self.post_command: list = task_descriptor.get(XTestKeys.PostCommand, [])
        if isinstance(self.post_command, str):
            self.post_command = self.post_command.split()

        self.pre_command: list = task_descriptor.get(XTestKeys.PreCommand, [])
        if isinstance(self.pre_command, str):
            self.pre_command = self.pre_command.split()

        self.vars_map = task_descriptor.get(XTestKeys.Variables, {})
        self.vars_map['__xname__'] = self.name

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

        variables = config.arg('variables')
        if variables:
            for v in variables:
                key, val = parse_assignment_str(v)
                self.vars_map[key] = val

        self.vars_map.update({
            "__stdout__": self.stdout_file,
            "__stderr__": self.stderr_file,
            "__output_file__": self.stdout_file,
        })

        #  Finally, expand variables if needed
        if config.expand_task:
            self.expand()

        if isinstance(self.command, str):
            if self.shell:
                self.command = [self.command]
            else:
                self.command = shlex.split(self.command)

    def expand(self) -> None:
        expander = StringVarExpander(self.vars_map)
        self._log_info("expanding")
        self.env = {expander(k): expander(v) for k, v in self.env.items()}
        if self.cwd:
            self.cwd = expander(self.cwd)
        if isinstance(self.command, str):
            self.command = expander(self.command)
        else:
            self.command = [expander(x) for x in self.command]

    def _create_output_dir(self) -> None:
        try:
            log_verbose("Creating output directory if it doesn't exist: '{}'", self.output_dir)
            os.makedirs(self.output_dir, exist_ok=True)
        except OSError as e:
            raise XeetException(f"Error creating output directory - {e}")

    def _get_test_io_descriptors(self) -> \
            tuple[Union[TextIOWrapper, int], Union[TextIOWrapper, int]]:
        out_file = subprocess.DEVNULL
        err_file = subprocess.DEVNULL
        out_file = open(self.stdout_file, "w")
        if self.stderr_file:
            err_file = open(self.stderr_file, "w")
        elif self.output_behavior == OutputBehaviorValues.Unify:
            err_file = out_file
        return out_file, err_file

    def _run_cmd(self, res: XTestResult) -> XTestResult:
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
            if self.debug_mode:
                print(" Test ouput ".center(50, '-'))
                p = subprocess.run(self.command, shell=self.shell, executable=self.shell_path,
                                   env=env, cwd=self.cwd, timeout=self.timeout)
                res.rc = p.returncode
                res.run_ok = res.rc in self.allowed_rc
                return res

            start = timer()
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
        return res

    def _filter_output(self, res: XTestResult) -> None:
        if res.status != XTEST_PASSED:
            return
        if not self.output_filter or self.debug_mode:
            res.filter_ok = True
            return
        expander = StringVarExpander(self.vars_map)
        filter_cmd = [expander(x) for x in self.output_filter]
        log_info("Filter command: '{}'".format(" ".join(filter_cmd)))
        try:
            p = subprocess.run(filter_cmd, capture_output=True, text=True)
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

    def _compare_file(self, res: XTestResult, src_file: str, expected_file: str, diff_file: str,
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

    def _compare_output(self, res: XTestResult) -> None:
        if res.status != XTEST_PASSED:
            return
        if self.compare_output == CompareOutputKeys.Nothing or self.debug_mode:
            res.compare_stderr_ok = True
            res.compare_stdout_ok = True
            return

        # Compare stdout
        if self.compare_output == CompareOutputKeys.Stderr:
            self._log_info("skipping stdout comparison")
            res.compare_stdout_ok = True
        else:
            res.compare_stdout_ok = self._compare_file(res, self.stdout_file,
                                                       self.expected_stdout_file,
                                                       self.out_diff_file,
                                                       "stdout")

        # Compare stderr
        if self.compare_output == CompareOutputKeys.Stdout:
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

    def _post_run(self, res: XTestResult) -> None:
        if res.status != XTEST_PASSED:
            return
        if not self.post_command:
            return
        if self.debug_mode:
            print(" Post run output ".center(50, '-'))
        post_cmd_map = {}
        post_cmd_map.update(self.vars_map)
        expander = StringVarExpander(post_cmd_map)
        post_run_cmd = [expander(x) for x in self.post_command]
        self._log_info(f"verifying with '{post_run_cmd}'")
        try:
            p = subprocess.run(post_run_cmd, capture_output=True, text=True)
            msg = f"Post run command = {p.returncode}"
            self._log_info(msg)
            res.post_run_rc = p.returncode
            if p.returncode == 0:
                return
            res.status = XTEST_FAILED
            res.short_comment = f"Post run failed"
            if p.stdout and len(p.stdout) > 0:
                msg += f", unified output tail:"
                res.extra_comments.append(msg)
                res.extra_comments.extend(p.stdout.splitlines()[-5:])
            else:
                msg += ", no post run output"
                res.extra_comments.append(msg)
        except OSError as e:
            res.status = XTEST_NOT_RUN
            log_error(f"Error running post run command- {e}", pr=False)
            res.short_comment = "Post run error:"
            res.extra_comments.append(str(e))

    def _pre_run(self, res: XTestResult) -> None:
        if not self.pre_command:
            return
        pre_cmd_map = {}
        pre_cmd_map.update(self.vars_map)
        expander = StringVarExpander(pre_cmd_map)
        pre_run_cmd = [expander(x) for x in self.pre_command]
        self._log_info(f"running pre_command '{pre_run_cmd}'")
        if self.debug_mode:
            print(" test pre command ".center(50, '-'))
        try:
            p = subprocess.run(pre_run_cmd, capture_output=not self.debug_mode, text=True)
            self._log_info(f"Pre run command returned: {p.returncode}")
            res.pre_run_rc = p.returncode
            if p.returncode == 0:
                return
            self._log_info(f"Pre run failed")
            res.status = XTEST_NOT_RUN
            res.short_comment = f"Pre run command RC={p.returncode}"
        except OSError as e:
            log_error(f"Error running pre run command- {e}", pr=False)
            res.status = XTEST_NOT_RUN
            res.short_comment = f"Error running pre run command- {e}"

    def run(self, res: XTestResult) -> None:
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

        self._create_output_dir()
        log_verbose("Command is '{}'", self.command)
        self._pre_run(res)
        if not res.pre_run_ok:
            return

        self._run_cmd(res)
        self._filter_output(res)
        self._compare_output(res)
        self._post_run(res)

        if not res.run_ok and res.status != XTEST_NOT_RUN and not self.debug_mode:
            if self.output_behavior == OutputBehaviorValues.Unify:
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
