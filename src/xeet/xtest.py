from io import TextIOWrapper
from xeet.xconfig import XeetConfig, XTestDesc
from xeet.xschemas import XTestKeys, OutputBehaviorValues, XTEST_SCHEMA
from xeet.xcommon import (XeetException, StringVarExpander, parse_assignment_str,
                          validate_json_schema)
from xeet.xlogging import (log_info, log_raw, log_error, logging_enabled_for, log_verbose,
                           INFO)
from typing import Optional
import shlex
import subprocess
import signal
import os
import difflib
from timeit import default_timer as timer
from typing import Union, Tuple


XTEST_UNDEFINED = -1
XTEST_PASSED = 0
XTEST_FAILED = 1
XTEST_SKIPPED = 2
XTEST_NOT_RUN = 3
XTEST_EXPECTED_FAILURE = 4
XTEST_UNEXPECTED_PASS = 5


class XTestResult(object):
    def __init__(self, xtest, status: int = XTEST_UNDEFINED, rc: int = 255,
                 comment: Optional[str] = None, duration: float = 0) -> None:
        super().__init__()
        self.status = status
        self.rc = rc
        self.short_comment = comment
        self.extra_comments: list[str] = []
        self.xtest = xtest
        self.duration: float = duration


class XTest(object):
    def _log_info(self, msg: str, *args, **kwargs) -> None:
        kwargs['extra_frames'] = 1
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
                                                   OutputBehaviorValues.Unify)
        self.stderr_file = None
        self.stdout_file = None
        if self.output_behavior == OutputBehaviorValues.Unify or \
           self.output_behavior == OutputBehaviorValues.Split or \
           self.output_behavior == OutputBehaviorValues.OutOnly:
            self.stdout_file = f"{config.output_dir}/{self.name}"
            log_info(f"stdout file: {self.stdout_file}")
        if self.output_behavior == OutputBehaviorValues.Split or \
           self.output_behavior == OutputBehaviorValues.ErrOnly:
            self.stderr_file = f"{config.output_dir}/{self.name}.err"
            log_info(f"stderr file: {self.stderr_file}")

        self.compare_output = task_descriptor.get(XTestKeys.CompareOutput, True)
        self.expected_output_file = task_descriptor.get(XTestKeys.CompareOutputFile, None)
        self.output_filter: list = task_descriptor.get(XTestKeys.OutputFilter, [])
        if isinstance(self.output_filter, str):
            self.output_filter = self.output_filter.split()
        if task_descriptor.get(XTestKeys.CompareOutput, True):
            self.expected_output_file = task_descriptor.get(
                XTestKeys.CompareOutputFile,
                f"{config.default_expected_output_dir}/{self.name}")
            self.diff_file = f"{config.output_dir}/{self.name}.diff"
        else:
            self.expected_output_file = None
            self.diff_file = None

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
            out_dir = None
            err_dir = None
            if self.stdout_file:
                out_dir = os.path.dirname(self.stdout_file)
            if self.stderr_file:
                err_dir = os.path.dirname(self.stderr_file)

            if out_dir:
                log_verbose("Creating output directory if it doesn't exist: '{}'", out_dir)
                os.makedirs(out_dir, exist_ok=True)
            if err_dir and err_dir != out_dir:
                log_verbose("Creating stderr directory if it doesn't exist: '{}'", err_dir)
                os.makedirs(err_dir, exist_ok=True)
        except OSError as e:
            raise XeetException(f"Error creating output directory - {e}")

    def _get_test_io_descriptors(self) -> \
            tuple[Union[TextIOWrapper, int], Union[TextIOWrapper, int]]:
        out_file = subprocess.DEVNULL
        err_file = subprocess.DEVNULL
        if self.stdout_file:
            out_file = open(self.stdout_file, "w")
        if self.stderr_file:
            err_file = open(self.stderr_file, "w")
        elif self.output_behavior == OutputBehaviorValues.Unify:
            err_file = out_file
        return out_file, err_file

    def _run_cmd(self) -> XTestResult:
        self._log_info("running command:")
        log_raw(self.command)
        p = None
        res = XTestResult(self)
        if self.env_inherit:
            env = os.environ
            env.update(self.env)
        else:
            env = self.env
        out_file, err_file = None, None
        try:
            if self.debug_mode:
                p = subprocess.run(self.command, shell=self.shell, executable=self.shell_path,
                                   env=env, cwd=self.cwd, timeout=self.timeout)
                res.rc = p.returncode
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
        return res

    def _filter_output(self, res: XTestResult) -> None:
        if not self.stdout_file or not self.output_filter:
            return
        expander = StringVarExpander(self.vars_map)
        filter_cmd = [expander(x) for x in self.output_filter]
        log_info("Filter command: '{}'".format(" ".join(filter_cmd)))
        try:
            p = subprocess.run(filter_cmd, capture_output=True, text=True)
            self._log_info(f"Filter command returned: {p.returncode}")
            self._log_info(f"Filter stderr: {p.stderr}")
            if p.returncode != 0:
                res.status = XTEST_FAILED
                res.short_comment = f"output filter failed"
                res.extra_comments.append(f"Filter command returned: {p.returncode}")
                res.extra_comments.append(f"Filter stderr:")
                res.extra_comments.append(p.stderr)
                return
        except OSError as e:
            res.status = XTEST_NOT_RUN
            log_error(f"Error running filter output command- {e}", pr=False)
            res.short_comment = "Error filtering output:"
            res.extra_comments.append(str(e))

    def _compare_output(self, res: XTestResult) -> None:
        if not self.stdout_file:
            return
        if not self.expected_output_file:
            return
        self._log_info(f"comparing output with '{self.expected_output_file}'")
        try:
            with open(self.stdout_file, "r") as out_file, \
                    open(self.expected_output_file, "r") as expected_file:
                diff = difflib.unified_diff(expected_file.readlines(), out_file.readlines(),
                                            fromfile=self.expected_output_file,
                                            tofile=self.stdout_file)

                diff = list(diff)
            if len(diff) == 0:
                self._log_info(f"output matches expected")
                return

            self._log_info(f"output mismatch")
            res.status = XTEST_FAILED
            if self.diff_file:
                with open(self.diff_file, "w") as diff_file:
                    diff_file.writelines(diff)

            if res.short_comment:
                res.short_comment += "Output mismatch"
            else:
                res.short_comment = "Output mismatch"

            res.extra_comments.append(f"Diff head:\n>>>>>")
            for index, line in enumerate(diff):
                res.extra_comments.append(line.strip("\n"))
                if index > 5:
                    res.extra_comments.append("...")
                    break
            res.extra_comments.append("<<<<<")
            res.extra_comments.append(f"Full diff file: {self.diff_file}")

        except OSError as e:
            res.status = XTEST_NOT_RUN
            err = f"Error comparing output - {e}"
            log_error(err, pr=False)
            res.short_comment = "Error comparing output"
            res.extra_comments.append(err)
            res.extra_comments.append("Output comparison skipped")

    def _post_run(self, res: XTestResult) -> None:
        if not self.post_command:
            return
        post_cmd_map = {}
        post_cmd_map.update(self.vars_map)
        expander = StringVarExpander(post_cmd_map)
        post_run_cmd = [expander(x) for x in self.post_command]
        self._log_info(f"verifying with '{post_run_cmd}'")
        try:
            p = subprocess.run(post_run_cmd, capture_output=True, text=True)
            self._log_info(f"Post run command returned: {p.returncode}")
            if p.returncode != 0:
                res.status = XTEST_FAILED
                res.short_comment = f"post run failed"
                res.extra_comments.append(f"Post run command returned: {p.returncode}")
                res.extra_comments.append(f"Post run stderr:")
                res.extra_comments.append(p.stderr)
                return
        except OSError as e:
            res.status = XTEST_NOT_RUN
            log_error(f"Error running post run command- {e}", pr=False)
            res.short_comment = "Post run error:"
            res.extra_comments.append(str(e))

    def _pre_run(self) -> Tuple[bool, Optional[str]]:
        if not self.pre_command:
            return True, None
        pre_cmd_map = {}
        pre_cmd_map.update(self.vars_map)
        expander = StringVarExpander(pre_cmd_map)
        pre_run_cmd = [expander(x) for x in self.pre_command]
        self._log_info(f"running pre_command '{pre_run_cmd}'")
        try:
            p = subprocess.run(pre_run_cmd, capture_output=True, text=True)
            self._log_info(f"Pre run command returned: {p.returncode}")
            if p.returncode != 0:
                self._log_info(f"Pre run failed")
                return False, f"Pre run command returned: {p.returncode}"
        except OSError as e:
            log_error(f"Error running pre run command- {e}", pr=False)
            return False, f"Error running pre run command- {e}"
        return True, None

    def run(self) -> XTestResult:
        if self.init_err:
            res = XTestResult(self, XTEST_NOT_RUN)
            res.extra_comments.append(self.init_err)
            return res
        if self.skip:
            self._log_info("marked to be skipped")
            reason = "marked as skip{}".format(f" - {self.skip_reason}" if self.skip_reason else "")
            return XTestResult(self, XTEST_SKIPPED, comment=reason)
        if not self.command:
            self._log_info("No command for test, will not run")
            return XTestResult(self, XTEST_NOT_RUN, comment="No command")

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
        if not self.debug_mode:
            ok, msg = self._pre_run()
            if not ok:
                return XTestResult(self, XTEST_NOT_RUN, comment=msg)

        res = self._run_cmd()
        if not self.debug_mode:
            if res.status == XTEST_PASSED:
                self._filter_output(res)
            if res.status == XTEST_PASSED:
                self._compare_output(res)
            if res.status == XTEST_PASSED:
                self._post_run(res)

        if res.status == XTEST_FAILED or res.status == XTEST_UNEXPECTED_PASS:
            if self.stderr_file:
                res.extra_comments.append(f"Stderr file: {self.stderr_file}")
            if self.stdout_file:
                res.extra_comments.append(f"Full output file: {self.stdout_file}")

        if res.status == XTEST_PASSED:
            self._log_info("completed successfully")
        return res
