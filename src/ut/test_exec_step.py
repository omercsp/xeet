from dataclasses import dataclass
from logging import debug
from typing import Iterable
from ut import ConfigTestWrapper, tests_utils_command, XeetUnittest
from xeet.xtest import (Xtest, TestResult, TestStatus, XeetRunException, status_catgoery,
                        TestStatusCategory)
from xeet.xstep import XStepModel, XStepTestArgs
from xeet.steps.exec_step import ExecStep, ExecStepModel, ExecStepResult
from xeet.core import run_tests, RunSettings, fetch_xtest, fetch_tests_list
from xeet.config import TestCriteria, read_config_file
from xeet.common import XeetException, XeetVars
from xeet.log import log_info
import dataclasses
import tempfile
import os


if os.environ.get("UT_DEBUG", "0") == "1":
    _TRUE_CMD = "true"
    _FALSE_CMD = "false"
    _SHOWENV_CMD = "printenv"
    _ECHOCMD = "echo"
    _PWD_CMD = "pwd"
    _SLEEP_1_CMD = "sleep 1"
else:
    _TRUE_CMD = tests_utils_command("rc.py", "0")
    _FALSE_CMD = tests_utils_command("rc.py", "1")
    _SHOWENV_CMD = tests_utils_command("showenv.py")
    _ECHOCMD = tests_utils_command("echo.py")
    _PWD_CMD = tests_utils_command("pwd.py")
    _SLEEP_1_CMD = tests_utils_command("sleep.py", "1")
_BAD_CMD = "nonexistent"


_exec_fields = set(ExecStepModel.model_fields.keys())


def _gen_exec_step_desc(**kwargs) -> dict:
    for k in list(kwargs.keys()):
        if k not in _exec_fields:
            raise ValueError(f"Invalid ExecStep field '{k}'")
    return {"type": "exec", **kwargs}


_step_args = XStepTestArgs()


def _gen_exec_step(args: dict) -> ExecStep:
    model = ExecStepModel(**args)
    return ExecStep(model, _step_args)


def _gen_exec_step_result(step: ExecStep, **kwargs) -> ExecStepResult:
    return ExecStepResult(step=step, **kwargs)


class TestExecStep(XeetUnittest):

    default_xvars = XeetVars()

    def assertStepResultEqual(self, res: ExecStepResult, expected: ExecStepResult,   # type: ignore
                              ignore_rc: bool = False) -> None:
        super().assertStepResultEqual(res, expected)
        self.assertEqual(res.output_behavior, expected.output_behavior)
        self.assertEqual(bool(res.os_error), bool(expected.os_error))
        if not ignore_rc:
            self.assertEqual(res.rc, expected.rc)
        self.assertEqual(res.rc_ok, expected.rc_ok)
        self.assertEqual(bool(res.stdout_diff), bool(expected.stdout_diff))
        self.assertEqual(bool(res.stderr_diff), bool(expected.stderr_diff))
        self.assertEqual(bool(res.timeout_period), bool(expected.timeout_period))

    def assertExecStep(self, step: ExecStep, expected: ExecStepResult, xvars: XeetVars = default_xvars,
                       **kwargs) -> None:
        step.expand(xvars)
        res: ExecStepResult = step.run()  # type: ignore
        self.assertStepResultEqual(res, expected, **kwargs)

    def test_simple_exec(self):
        desc = _gen_exec_step_desc(cmd=_TRUE_CMD)
        step = _gen_exec_step(desc)
        self.assertExecStep(step, _gen_exec_step_result(step, rc=0, rc_ok=True, completed=True))

        desc = _gen_exec_step_desc(cmd=_FALSE_CMD)
        step = _gen_exec_step(desc)
        self.assertExecStep(step, _gen_exec_step_result(step, rc=1, rc_ok=False, completed=True, failed=True))

        desc = _gen_exec_step_desc(cmd=_BAD_CMD)
        step = _gen_exec_step(desc)
        self.assertExecStep(step, _gen_exec_step_result(step, rc=None, completed=False, os_error=True))

    def test_allowed_rc(self):
        rc_10_cmd = tests_utils_command("rc.py", "10")
        desc = _gen_exec_step_desc(cmd=rc_10_cmd, allowed_rc=[10])
        step = _gen_exec_step(desc)
        self.assertExecStep(step, _gen_exec_step_result(step, rc=10, rc_ok=True, completed=True))

        desc = _gen_exec_step_desc(cmd=rc_10_cmd, allowed_rc=[10, 100])
        step = _gen_exec_step(desc)
        self.assertExecStep(step, _gen_exec_step_result(step, rc=10, rc_ok=True, completed=True))

        desc = _gen_exec_step_desc(cmd=rc_10_cmd, allowed_rc=[11, 100])
        step = _gen_exec_step(desc)
        self.assertExecStep(step, _gen_exec_step_result(step, rc=10, rc_ok=False, completed=True, failed=True))

        desc = _gen_exec_step_desc(cmd=rc_10_cmd, allowed_rc=[11, 100])
        step = _gen_exec_step(desc)
        self.assertExecStep(step, _gen_exec_step_result(step, rc=10, rc_ok=False, completed=True, failed=True))

        desc = _gen_exec_step_desc(cmd=tests_utils_command("rc.py"), allowed_rc="*")
        step = _gen_exec_step(desc)
        result = _gen_exec_step_result(step, rc_ok=True, completed=True)
        for _ in range(5):
            self.assertExecStep(step, result, ignore_rc=True)

#      def test_cwd(self):
#          self.set_test(_TEST0, cmd="pwd", save=True, reset=True)
#          res = self.run_test(_TEST0)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          self.assertEqual(_file_content(res.stdout_file).strip(), os.getcwd())

#          tmp_dir = tempfile.gettempdir()
#          self.set_test(_TEST0, cmd="pwd", cwd=tmp_dir, save=True, reset=True)
#          self.run_test(_TEST0)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          self.assertEqual(_file_content(res.stdout_file).strip(), tmp_dir)

#          self.set_test(_TEST1, base=_TEST0, save=True)
#          res = self.run_test(_TEST1)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          self.assertEqual(_file_content(res.stdout_file).strip(), tmp_dir)

#          self.set_test(_TEST2, base=_TEST0, save=True)
#          res = self.run_test(_TEST2)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          self.assertEqual(_file_content(res.stdout_file).strip(), tmp_dir)

#          self.set_test(_TEST3, base=_TEST0, cwd="{XEET_CWD}", save=True)
#          res = self.run_test(_TEST3)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          self.assertEqual(_file_content(res.stdout_file).strip(), os.getcwd())

#          self.set_test(_TEST0, cmd="pwd", cwd="/nonexistent", save=True, reset=True)
#          res = self.run_test(_TEST0)
#          self._check_test(res, rc=None, status=TestStatus.RunErr)


    def test_timeout(self):
        desc = _gen_exec_step_desc(cmd=_SLEEP_1_CMD, timeout=0.5)  #  1 second sleep
        step = _gen_exec_step(desc)
        self.assertExecStep(step, _gen_exec_step_result(step, completed=False, timeout_period=True))

#      def test_env(self):
#          self.set_test(_TEST0, cmd=f"{_SHOWENV_CMD} TEST_ENV",
#                        env={"TEST_ENV": "test"}, reset=True)
#          self.set_test(_TEST1, base=_TEST0)
#          self.set_test(_TEST2, base=_TEST0, env={"TEST_ENV": "test2"})
#          self.set_test(_TEST3, base=_TEST0, inherit_env_variables=False)
#          os.environ["OS_TEST_ENV"] = "os test"
#          self.set_test(_TEST4,  cmd=f"{_SHOWENV_CMD} OS_TEST_ENV")
#          self.set_test(_TEST5, base=_TEST4, use_os_env=False, save=True)

#          res = self.run_test(_TEST0)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          self.assertEqual(_file_content(res.stdout_file).strip(), "test")

#          res = self.run_test(_TEST1)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          self.assertEqual(_file_content(res.stdout_file).strip(), "test")

#          res = self.run_test(_TEST2)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          self.assertEqual(_file_content(res.stdout_file).strip(), "test2")

#          res = self.run_test(_TEST3)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          self.assertEqual(_file_content(res.stdout_file).strip(), "")

#          res = self.run_test(_TEST4)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          self.assertEqual(_file_content(res.stdout_file).strip(), "os test")

#          res = self.run_test(_TEST5)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          self.assertEqual(_file_content(res.stdout_file).strip(), "")

#      def test_variables(self):
#          self.set_test(_TEST0, cmd=f"{_ECHOCMD} {{TEST_VAR}}",
#                        var_map={"TEST_VAR": "test"}, reset=True)
#          self.set_test(_TEST1, base=_TEST0)
#          self.set_test(_TEST2, base=_TEST0, var_map={"TEST_VAR": "test2"})
#          self.set_test(_TEST3, base=_TEST0, inherit_variables=False, save=True)

#          res = self.run_test(_TEST0)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          self.assertEqual(_file_content(res.stdout_file).strip(), "test")

#          res = self.run_test(_TEST1)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          self.assertEqual(_file_content(res.stdout_file).strip(), "test")

#          res = self.run_test(_TEST2)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          self.assertEqual(_file_content(res.stdout_file).strip(), "test2")

#          self.assertRaises(XeetException, self.run_test, _TEST3)

#      def test_autovars(self):
#          test_cmd = _ECHOCMD + \
#              (" {XEET_TEST_NAME} {XEET_TEST_STDOUT} {XEET_TEST_STDERR} {XEET_TEST_OUTPUT_DIR}")

#          self.set_test(_TEST0, cmd=test_cmd, reset=True)
#          self.set_test(_TEST1, base=_TEST0, var_map={"XEET_TEST_NAME": "bad"}, save=True)

#          res = self.run_test(_TEST0)
#          self._check_test(res, rc=0, status=TestStatus.Passed)
#          output_dir = os.path.dirname(res.stdout_file)
#          expected = f"{_TEST0} {res.stdout_file} {res.stderr_file} {output_dir}"
#          self.assertEqual(_file_content(res.stdout_file).strip(), expected)
#          self.assertRaises(XeetException, self.run_test, _TEST1)  # XEET prefix is reserved

#      def test_output_behavior(self):
#          cmd = f"{_ECHOCMD} stdout; {_ECHOCMD} stderr 1>&2"
#          self.set_test(_TEST0, shell=True, cmd=cmd, reset=True)
#          # Unifiy stdout and stderr explicitly
#          self.set_test(_TEST1, base=_TEST0, output_behavior="unify")
#          self.set_test(_TEST2, base=_TEST0, output_behavior="split")
#          self.set_test(_TEST3, shell=True, cmd=cmd, output_behavior="split", save=True)

#          for res in self.run_tests_list([_TEST0, _TEST1]):
#              self._check_test(res, rc=0, status=TestStatus.Passed)
#              self.assertEqual(_file_content(res.stdout_file).strip(), "stdout\nstderr")

#          for res in self.run_tests_list([_TEST2, _TEST3]):
#              self._check_test(res, rc=0, status=TestStatus.Passed)
#              self.assertEqual(_file_content(res.stdout_file).strip(), "stdout")
#              self.assertEqual(_file_content(res.stderr_file).strip(), "stderr")

#      #  Fetch functionality is only basically tested, as it is just a wrapper around the  config file
#      #  functionality,  which has its own extensive tests in test_config.py
#      def test_test_status_categories(self):
#          for status in TestStatus:
#              self.assertNotEqual(status_catgoery(status), TestStatusCategory.Unknown)

