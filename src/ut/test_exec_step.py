from ut import tests_utils_command, XeetUnittest
from xeet.steps.exec_step import ExecStep, ExecStepModel, ExecStepResult, _OutputBehavior
from xeet.xtest import TestResult, TestStatus, XStepListResult
from xeet.common import XeetVars, in_windows
import tempfile
import os
import json

from xeet.xtest import TestResult


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

_OUTPUT_CMD = tests_utils_command("output.py")
_BAD_CMD = "nonexistent"


exec_fields = set(ExecStepModel.model_fields.keys())


def gen_exec_step_desc(**kwargs) -> dict:
    for k in list(kwargs.keys()):
        if k not in exec_fields:
            raise ValueError(f"Invalid ExecStep field '{k}'")
    return {"type": "exec", **kwargs}


_TEST0 = "test0"
_TEST1 = "test1"
_TEST2 = "test2"
_TEST3 = "test3"
_TEST4 = "test4"
_TEST5 = "test5"
_TEST6 = "test6"


def _gen_exec_result(status: TestStatus, **kwargs) -> TestResult:
    step_res_desc = ExecStepResult(**kwargs)
    return TestResult(status=status, run_res=XStepListResult(results=[step_res_desc]))


_GOOD_RES = _gen_exec_result(status=TestStatus.Passed, rc=0, rc_ok=True, completed=True)


class TestExecStep(XeetUnittest):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.output_dir = tempfile.TemporaryDirectory()
        cls.default_xvars = XeetVars()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.output_dir.cleanup()

    def assertStepResultEqual(self, res: ExecStepResult, expected: ExecStepResult  # type: ignore
                              ) -> None:
        super().assertStepResultEqual(res, expected)
        self.assertEqual(res.output_behavior, expected.output_behavior)
        self.assertEqual(bool(res.os_error), bool(expected.os_error))
        if res.allowed_rc != "*":
            self.assertEqual(res.rc, expected.rc)
        self.assertEqual(res.rc_ok, expected.rc_ok)
        self.assertEqual(bool(res.stdout_diff), bool(expected.stdout_diff))
        self.assertEqual(bool(res.stderr_diff), bool(expected.stderr_diff))
        self.assertEqual(bool(res.timeout_period), bool(expected.timeout_period))

    def assertExecStep(self, step: ExecStep, expected: ExecStepResult,
                       xvars: XeetVars | None = None, **kwargs) -> None:
        if xvars is None:
            xvars = self.default_xvars
        step.setup(xvars)
        res: ExecStepResult = step.run()  # type: ignore
        self.assertStepResultEqual(res, expected, **kwargs)

    def test_simple_exec(self):
        true_cmd_desc = gen_exec_step_desc(cmd=_TRUE_CMD)
        false_cmd_desc = gen_exec_step_desc(cmd=_FALSE_CMD)
        bad_cmd_desc = gen_exec_step_desc(cmd=_BAD_CMD)

        self.add_test(_TEST0, run=[true_cmd_desc], reset=True)
        self.add_test(_TEST1, run=[false_cmd_desc])
        self.add_test(_TEST2, run=[bad_cmd_desc], save=True)

        expected = _gen_exec_result(TestStatus.Passed, rc=0, rc_ok=True, completed=True)
        self.assertTestResultEqual(self.run_test(_TEST0), expected)

        expected = _gen_exec_result(TestStatus.Failed, rc=1, rc_ok=False, completed=True,
                                    failed=True)
        self.assertTestResultEqual(self.run_test(_TEST1), expected)

        expected = _gen_exec_result(TestStatus.RunErr, rc=None, os_error=OSError(),
                                    completed=False)
        self.assertTestResultEqual(self.run_test(_TEST2), expected)

    def test_allowed_rc(self):
        rc_10_cmd = tests_utils_command("rc.py", "10")
        rand_rc_cmd = tests_utils_command("rc.py")

        step_desc = gen_exec_step_desc(cmd=rc_10_cmd, allowed_rc=[10])
        self.add_test(_TEST0, run=[step_desc], reset=True)
        step_desc = gen_exec_step_desc(cmd=rc_10_cmd, allowed_rc=[10, 100])
        self.add_test(_TEST1, run=[step_desc])
        step_desc = gen_exec_step_desc(cmd=rc_10_cmd, allowed_rc=[11, 100])
        self.add_test(_TEST2, run=[step_desc])
        step_desc = gen_exec_step_desc(cmd=rand_rc_cmd, allowed_rc="*")
        self.add_test(_TEST3, run=[step_desc], save=True)

        expected = _gen_exec_result(TestStatus.Passed, rc=10, rc_ok=True, completed=True)
        self.assertTestResultEqual(self.run_test(_TEST0), expected)
        self.assertTestResultEqual(self.run_test(_TEST1), expected)

        expected = _gen_exec_result(TestStatus.Failed, rc=10, rc_ok=False, completed=True,
                                    failed=True)
        self.assertTestResultEqual(self.run_test(_TEST2), expected)

        expected = _gen_exec_result(TestStatus.Passed, rc_ok=True, completed=True)
        for _ in range(5):
            self.assertTestResultEqual(self.run_test(_TEST3), expected)

    def test_cwd(self):
        cwd = tempfile.gettempdir()
        step_desc = gen_exec_step_desc(cmd=_PWD_CMD, cwd=cwd, expected_stdout=f"{cwd}\n")
        self.add_test(_TEST0, run=[step_desc], reset=True, save=True)
        self.assertTestResultEqual(self.run_test(_TEST0), _GOOD_RES)

    def test_timeout(self):
        step_desc = gen_exec_step_desc(cmd=_SLEEP_1_CMD, timeout=0.5)  # 1 second sleep
        self.add_test(_TEST0, run=[step_desc], reset=True, save=True)
        expected = _gen_exec_result(TestStatus.RunErr, completed=False, timeout_period=True)
        self.assertTestResultEqual(self.run_test(_TEST0), expected)

    def test_env(self):
        step_desc = gen_exec_step_desc(cmd=f"{_SHOWENV_CMD} TEST_ENV", env={"TEST_ENV": "test"},
                                       expected_stdout="test\n")
        self.add_test(_TEST0, run=[step_desc], reset=True)

        step_desc = gen_exec_step_desc(cmd=f"{_SHOWENV_CMD} NOSUCHVAR", expected_stdout="\n")
        self.add_test(_TEST1, run=[step_desc])

        os.environ["OS_TEST_ENV"] = "os test"
        step_desc = gen_exec_step_desc(cmd=f"{_SHOWENV_CMD} OS_TEST_ENV", use_os_env=True,
                                       expected_stdout="os test\n")
        self.add_test(_TEST2, run=[step_desc])

        step_desc = gen_exec_step_desc(cmd=f"{_SHOWENV_CMD} OS_TEST_ENV", use_os_env=False,
                                       expected_stdout="\n")
        self.add_test(_TEST3, run=[step_desc], save=True)

        self.assertTestResultEqual(self.run_test(_TEST0), _GOOD_RES)
        self.assertTestResultEqual(self.run_test(_TEST1), _GOOD_RES)
        self.assertTestResultEqual(self.run_test(_TEST2), _GOOD_RES)
        self.assertTestResultEqual(self.run_test(_TEST3), _GOOD_RES)

        with tempfile.NamedTemporaryFile() as tmpfile:
            env_vars = {"var0": "val0", "var1": "val1"}
            with open(tmpfile.name, "w") as f:
                f.write(json.dumps(env_vars))
            step_desc = gen_exec_step_desc(cmd=f"{_SHOWENV_CMD} var0", env_file=tmpfile.name,
                                           expected_stdout="val0\n")
            self.add_test(_TEST0, run=[step_desc], reset=True)

            step_desc = gen_exec_step_desc(cmd=f"{_SHOWENV_CMD} var1", env_file=tmpfile.name,
                                           expected_stdout="val1\n")
            self.add_test(_TEST1, run=[step_desc])

            step_desc = gen_exec_step_desc(cmd=f"{_SHOWENV_CMD} var2", env_file=tmpfile.name,
                                           expected_stdout="\n")
            self.add_test(_TEST2, run=[step_desc], save=True)

            self.assertTestResultEqual(self.run_test(_TEST0), _GOOD_RES)
            self.assertTestResultEqual(self.run_test(_TEST1), _GOOD_RES)
            self.assertTestResultEqual(self.run_test(_TEST2), _GOOD_RES)

    def test_shell_usage(self):
        if in_windows():
            return

        cmd = f"{_ECHOCMD} --no-newline 1; {_ECHOCMD} --no-newline 2"
        step_desc = gen_exec_step_desc(cmd=cmd, use_shell=True, expected_stdout="12")
        self.add_test(_TEST0, run=[step_desc], reset=True, save=True)

        step_desc = gen_exec_step_desc(cmd=cmd, use_shell=False,
                                       expected_stdout=f"1; {_ECHOCMD} --no-newline 2")
        self.add_test(_TEST1, run=[step_desc], save=True)

        self.assertTestResultEqual(self.run_test(_TEST0), _GOOD_RES)
        self.assertTestResultEqual(self.run_test(_TEST1), _GOOD_RES)

    def test_output_behavior(self):
        cmd = f"{_OUTPUT_CMD} --stdout O --stderr E --stdout O --stderr E"
        step_desc = gen_exec_step_desc(cmd=cmd, expected_stdout="OEOE")
        self.add_test(_TEST0, run=[step_desc], reset=True)

        step_desc = gen_exec_step_desc(cmd=cmd, expected_stdout="OEOE",
                                       output_behavior=_OutputBehavior.Unify)
        self.add_test(_TEST1, run=[step_desc])

        step_desc = gen_exec_step_desc(cmd=cmd, expected_stdout="OO", expected_stderr="EE",
                                       output_behavior=_OutputBehavior.Split)
        self.add_test(_TEST2, run=[step_desc], save=True)

        step_desc = gen_exec_step_desc(cmd=cmd, expected_stderr="EE",
                                       output_behavior=_OutputBehavior.Split)
        self.add_test(_TEST3, run=[step_desc], save=True)
        step_desc = gen_exec_step_desc(cmd=cmd, expected_stdout="OO",
                                       output_behavior=_OutputBehavior.Split)
        self.add_test(_TEST4, run=[step_desc], save=True)

        step_desc = gen_exec_step_desc(cmd=cmd, expected_stdout="O",
                                       output_behavior=_OutputBehavior.Split)
        self.add_test(_TEST5, run=[step_desc], save=True)
        step_desc = gen_exec_step_desc(cmd=cmd, expected_stderr="E",
                                       output_behavior=_OutputBehavior.Split)
        self.add_test(_TEST6, run=[step_desc], save=True)

        self.assertTestResultEqual(self.run_test(_TEST0), _GOOD_RES)
        self.assertTestResultEqual(self.run_test(_TEST1), _GOOD_RES)

        expected = _gen_exec_result(TestStatus.Passed, rc=0, rc_ok=True, completed=True,
                                    output_behavior=_OutputBehavior.Split)
        self.assertTestResultEqual(self.run_test(_TEST2), expected)
        self.assertTestResultEqual(self.run_test(_TEST3), expected)
        self.assertTestResultEqual(self.run_test(_TEST4), expected)

        expected = _gen_exec_result(TestStatus.Failed, rc=0, rc_ok=True, completed=True,
                                    failed=True, output_behavior=_OutputBehavior.Split,
                                    stdout_diff="yes")
        self.assertTestResultEqual(self.run_test(_TEST5), expected)
        expected = _gen_exec_result(TestStatus.Failed, rc=0, rc_ok=True, completed=True,
                                    failed=True, output_behavior=_OutputBehavior.Split,
                                    stderr_diff="yes")
        self.assertTestResultEqual(self.run_test(_TEST6), expected)

    def test_exec_model_inheritance(self):
        dflt_cmd = "cmd"
        dflt_stdout = "stdout"
        dflt_stderr = "stderr"
        dflt_shell_path = "/bin/sh"
        dflt_timeout = 0.5
        dflt_cwd = tempfile.gettempdir()
        dflt_allowed_rc = [1]

        def validate_model(test_name: str,
                           cmd: str = dflt_cmd,
                           cwd: str = dflt_cwd,
                           stdout: str = dflt_stdout,
                           stderr: str = dflt_stderr,
                           shell_path: str = dflt_shell_path,
                           timeout: float = dflt_timeout,
                           use_shell: bool = True,
                           allowed_rc: list[int] = dflt_allowed_rc
                           ) -> None:

            model = self.get_test(test_name).run_steps.steps[0].model
            self.assertIsInstance(model, ExecStepModel)
            assert isinstance(model, ExecStepModel)
            self.assertEqual(model.cmd, cmd)
            self.assertEqual(model.cwd, cwd)
            self.assertEqual(model.expected_stdout, stdout)
            self.assertEqual(model.expected_stderr, stderr)
            self.assertEqual(model.shell_path, shell_path)
            self.assertEqual(model.timeout, timeout)
            self.assertEqual(model.use_shell, use_shell)
            self.assertEqual(model.allowed_rc, allowed_rc)

        base_step_desc = gen_exec_step_desc(cmd=dflt_cmd,
                                            cwd=dflt_cwd,
                                            expected_stdout=dflt_stdout,
                                            expected_stderr=dflt_stderr,
                                            timeout=dflt_timeout,
                                            use_shell=True,
                                            shell_path=dflt_shell_path,
                                            use_os_env=True,
                                            allowed_rc=dflt_allowed_rc)
        self.add_setting("base_step", base_step_desc, reset=True)

        step_desc = gen_exec_step_desc(base="settings.base_step", cmd="other_cmd", cwd="")
        self.add_test(_TEST0, run=[step_desc])

        step_desc = gen_exec_step_desc(base="settings.base_step", expected_stdout="other_stdout",
                                       expected_stderr="other_stderr")
        self.add_test(_TEST1, run=[step_desc], save=True)
        step_desc = gen_exec_step_desc(base="settings.base_step", allowed_rc=[0, 2, 5],
                                       use_shell=False, timeout=1, shell_path="/bin/bash")
        self.add_test(_TEST2, run=[step_desc], save=True)
        validate_model(_TEST0, cmd="other_cmd", cwd="")
        validate_model(_TEST1, stdout="other_stdout", stderr="other_stderr")
