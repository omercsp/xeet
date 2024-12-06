from ut import tests_utils_command, XeetUnittest
from xeet.xstep import XStepTestArgs
from xeet.steps.exec_step import ExecStep, ExecStepModel, ExecStepResult, _OutputBehavior
from xeet.common import XeetVars, in_windows
import tempfile
import os
import json


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


class TestExecStep(XeetUnittest):
    exec_fields = set(ExecStepModel.model_fields.keys())

    @staticmethod
    def gen_exec_step_desc(**kwargs) -> dict:
        for k in list(kwargs.keys()):
            if k not in TestExecStep.exec_fields:
                raise ValueError(f"Invalid ExecStep field '{k}'")
        return {"type": "exec", **kwargs}

    @staticmethod
    def gen_exec_step(args: dict) -> ExecStep:
        model = ExecStepModel(**args)
        return ExecStep(model, TestExecStep.step_args)

    @staticmethod
    def gen_exec_step_result(step: ExecStep, **kwargs) -> ExecStepResult:
        return ExecStepResult(step=step, **kwargs)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.output_dir = tempfile.TemporaryDirectory()
        cls.step_args = XStepTestArgs(stage_prefix="ut", output_dir=cls.output_dir.name)
        cls.default_xvars = XeetVars()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.output_dir.cleanup()

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

    def assertExecStep(self, step: ExecStep, expected: ExecStepResult,
                       xvars: XeetVars | None = None, **kwargs) -> None:
        if xvars is None:
            xvars = self.default_xvars
        step.expand(xvars)
        res: ExecStepResult = step.run()  # type: ignore
        self.assertStepResultEqual(res, expected, **kwargs)

    def test_simple_exec(self):
        desc = self.gen_exec_step_desc(cmd=_TRUE_CMD)
        step = self.gen_exec_step(desc)
        result = self.gen_exec_step_result(step, rc=0, rc_ok=True, completed=True)
        self.assertExecStep(step, result)

        desc = self.gen_exec_step_desc(cmd=_FALSE_CMD)
        step = self.gen_exec_step(desc)
        result.rc = 1
        result.rc_ok = False
        result.failed = True
        self.assertExecStep(step, result)

        desc = self.gen_exec_step_desc(cmd=_BAD_CMD)
        step = self.gen_exec_step(desc)
        result.rc = None
        result.os_error = True  # type: ignore
        result.failed = False
        result.completed = False
        self.assertExecStep(step, result)

    def test_allowed_rc(self):
        rc_10_cmd = tests_utils_command("rc.py", "10")
        desc = self.gen_exec_step_desc(cmd=rc_10_cmd, allowed_rc=[10])
        step = self.gen_exec_step(desc)
        result = self.gen_exec_step_result(step, rc=10, rc_ok=True, completed=True)
        self.assertExecStep(step, result)

        desc = self.gen_exec_step_desc(cmd=rc_10_cmd, allowed_rc=[10, 100])
        step = self.gen_exec_step(desc)
        self.assertExecStep(step, result)

        desc = self.gen_exec_step_desc(cmd=rc_10_cmd, allowed_rc=[11, 100])
        step = self.gen_exec_step(desc)
        result.rc_ok = False
        result.failed = True
        self.assertExecStep(step, result)

        desc = self.gen_exec_step_desc(cmd=rc_10_cmd, allowed_rc=[11, 100])
        step = self.gen_exec_step(desc)
        self.assertExecStep(step, result)

        desc = self.gen_exec_step_desc(cmd=tests_utils_command("rc.py"), allowed_rc="*")
        step = self.gen_exec_step(desc)
        result.failed = False
        result.rc_ok = True
        for _ in range(5):
            self.assertExecStep(step, result, ignore_rc=True)

    def test_cwd(self):
        cwd = tempfile.gettempdir()
        desc = self.gen_exec_step_desc(cmd=_PWD_CMD, cwd=cwd, expected_stdout=f"{cwd}\n")
        step = self.gen_exec_step(desc)
        self.assertExecStep(step, self.gen_exec_step_result(step, completed=True, rc=0, rc_ok=True))

    def test_timeout(self):
        desc = self.gen_exec_step_desc(cmd=_SLEEP_1_CMD, timeout=0.5)  # 1 second sleep
        step = self.gen_exec_step(desc)
        self.assertExecStep(step, self.gen_exec_step_result(step, completed=False,
                                                            timeout_period=True))

    def test_env(self):
        desc = self.gen_exec_step_desc(cmd=f"{_SHOWENV_CMD} TEST_ENV", env={"TEST_ENV": "test"},
                                       expected_stdout="test\n")
        step = self.gen_exec_step(desc)
        self.assertExecStep(step, self.gen_exec_step_result(step, completed=True, rc=0, rc_ok=True))

        desc = self.gen_exec_step_desc(cmd=f"{_SHOWENV_CMD} NOSUCHVAR", expected_stdout="\n")
        step = self.gen_exec_step(desc)
        expected = self.gen_exec_step_result(step, completed=True, rc=0, rc_ok=True)
        self.assertExecStep(step, expected)

        os.environ["OS_TEST_ENV"] = "os test"
        desc = self.gen_exec_step_desc(cmd=f"{_SHOWENV_CMD} OS_TEST_ENV", use_os_env=True,
                                       expected_stdout="os test\n")
        step = self.gen_exec_step(desc)
        self.assertExecStep(step, expected)

        step.exec_model.use_os_env = False
        step.exec_model.expected_stdout = ""
        self.assertExecStep(step, expected)

        #  Create a temorary file to test file env variables
        with tempfile.NamedTemporaryFile() as tmpfile:
            env_vars = {"var0": "val0", "var1": "val1"}
            with open(tmpfile.name, "w") as f:
                f.write(json.dumps(env_vars))
            desc = self.gen_exec_step_desc(cmd=f"{_SHOWENV_CMD} var0", env_file=tmpfile.name,
                                           expected_stdout="val0\n")
            step = self.gen_exec_step(desc)
            self.assertExecStep(step, expected)

            step.exec_model.cmd = f"{_SHOWENV_CMD} var1"
            step.exec_model.expected_stdout = "val1\n"
            self.assertExecStep(step, expected)

            step.exec_model.cmd = f"{_SHOWENV_CMD} var2"
            step.exec_model.expected_stdout = "\n"
            self.assertExecStep(step, expected)

    def test_shell_usage(self):
        if in_windows():
            return
        cmd = f"{_ECHOCMD} 1; {_ECHOCMD} 2"
        shell_expected_stdout = "1\n2\n"
        no_shell_expected_stdout = f"1; {_ECHOCMD} 2\n"
        desc = self.gen_exec_step_desc(cmd=cmd, use_shell=True,
                                       expected_stdout=shell_expected_stdout)
        step = self.gen_exec_step(desc)
        expected = self.gen_exec_step_result(step, completed=True, rc=0, rc_ok=True)
        self.assertExecStep(step, expected)

        step.exec_model.use_shell = False
        step.exec_model.expected_stdout = no_shell_expected_stdout
        step.expand(XeetVars())
        self.assertExecStep(step, expected)

    def test_output_behavior(self):
        cmd = f"{_OUTPUT_CMD} --stdout O --stderr E --stdout O --stderr E"
        desc = self.gen_exec_step_desc(cmd=cmd, expected_stdout="OEOE")
        step = self.gen_exec_step(desc)
        expected = self.gen_exec_step_result(step, completed=True, rc=0, rc_ok=True)
        self.assertExecStep(step, expected)

        step.exec_model.output_behavior = _OutputBehavior.Unify
        self.assertExecStep(step, expected)

        step.output_behavior = _OutputBehavior.Split  # output behaviour isn't changed in expand
        step.exec_model.expected_stdout = "OO"
        step.exec_model.expected_stderr = "EE"
        expected.output_behavior = _OutputBehavior.Split
        self.assertExecStep(step, expected)

        step.exec_model.expected_stdout = None
        self.assertExecStep(step, expected)

        step.exec_model.expected_stderr = None
        self.assertExecStep(step, expected)

        step.exec_model.expected_stdout = "O"
        expected.failed = True
        expected.stdout_diff = "yes"
        self.assertExecStep(step, expected)

        step.exec_model.expected_stdout = "OO"
        step.exec_model.expected_stderr = "E"
        expected.stdout_diff = ""
        expected.stderr_diff = "yes"
        self.assertExecStep(step, expected)
