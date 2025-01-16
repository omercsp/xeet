from ut import *
from ut.ut_exec_defs import *
from xeet.steps.exec_step import ExecStepModel, _OutputBehavior, ExecStepResult
from xeet.core.result import TestStatus, TestPrimaryStatus, TestSecondaryStatus
from xeet.common import XeetVars, in_windows, platform_path
import tempfile
import os
import json


def test_simple_exec(xut: XeetUnittest):
    true_cmd_desc = gen_exec_step_desc(cmd=TRUE_CMD)
    false_cmd_desc = gen_exec_step_desc(cmd=FALSE_CMD)
    bad_cmd_desc = gen_exec_step_desc(cmd=BAD_CMD)

    xut.add_test(TEST0, run=[true_cmd_desc], reset=True)
    xut.add_test(TEST1, run=[false_cmd_desc])
    xut.add_test(TEST2, run=[bad_cmd_desc], save=True)

    step_res = ExecStepResult(rc=0, rc_ok=True, completed=True)
    expected = gen_test_result(status=PASSED_TEST_STTS, main_results=[step_res])
    xut.run_compare_test(TEST0, expected)

    step_res = ExecStepResult(rc=1, rc_ok=False, completed=True, failed=True)
    expected = xut.gen_test_res(TEST1, status=FAILED_TEST_STTS, main_results=[step_res])
    xut.run_compare_test(TEST1, expected)

    step_res = ExecStepResult(rc=None, os_error=OSError(), completed=False)
    status = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.TestErr)
    expected = gen_test_result(status=status, main_results=[step_res])
    xut.run_compare_test(TEST2, expected)


def test_var_expansions(xut: XeetUnittest):
    xut.add_var("number", 1, reset=True)
    xut.add_var("dict", {"key": "value"})

    step_desc = gen_exec_step_desc(cmd=ref_str("number"))
    xut.add_test(TEST0, run=[step_desc])

    step_desc = gen_exec_step_desc(cmd=TRUE_CMD, cwd=ref_str("number"))
    xut.add_test(TEST1, run=[step_desc])

    step_desc = gen_exec_step_desc(cmd=gen_showenv_cmd("key"), env=ref_str("number"),
                                   expected_stdout="value\n")
    xut.add_test(TEST2, run=[step_desc])

    step_desc = gen_exec_step_desc(cmd=gen_showenv_cmd("key"), env=ref_str("dict"),
                                   expected_stdout="value\n")
    xut.add_test(TEST3, run=[step_desc], save=True)

    init_err_status = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr)

    # For fail on setup tests, and empty result, as the variable is not expanded and no result
    # is created for the step.
    # expected = TestResult(status=init_err_status, run_res=PhaseResult())
    run_res = xut.run_tests(names={TEST0, TEST1, TEST2})
    for test in [TEST0, TEST1, TEST2]:
        expected = xut.gen_test_res(test, status=init_err_status)
        res = run_res.test_result(test, 0)
        assert_test_results_equal(res, expected)

    expected = xut.gen_test_res(TEST3, status=PASSED_TEST_STTS,
                                main_results=[GOOD_EXEC_STEP_RES])
    assert_test_results_equal(xut.run_test(TEST3), expected)


def test_allowed_rc(xut: XeetUnittest):
    rc_10_cmd = gen_rc_cmd(10)

    step_desc = gen_exec_step_desc(cmd=rc_10_cmd, allowed_rc=[10])
    xut.add_test(TEST0, run=[step_desc], reset=True)

    step_desc = gen_exec_step_desc(cmd=rc_10_cmd, allowed_rc=[10, 100])
    xut.add_test(TEST1, run=[step_desc])

    step_desc = gen_exec_step_desc(cmd=rc_10_cmd, allowed_rc=[11, 100])
    xut.add_test(TEST2, run=[step_desc])

    step_desc = gen_exec_step_desc(cmd=RAND_RC_CMD, allowed_rc="*")
    xut.add_test(TEST3, run=[step_desc], save=True)

    expected_step_res = ExecStepResult(rc=10, rc_ok=True, completed=True)
    expected = xut.gen_test_res(TEST0, status=PASSED_TEST_STTS,
                                main_results=[expected_step_res])
    assert_test_results_equal(xut.run_test(TEST0), expected)
    xut.update_test_res_test(expected, TEST1)
    assert_test_results_equal(xut.run_test(TEST1), expected)

    expected_step_res = ExecStepResult(rc=10, rc_ok=False, completed=True, failed=True)
    expected = xut.gen_test_res(TEST2, status=FAILED_TEST_STTS,
                                main_results=[expected_step_res])
    assert_test_results_equal(xut.run_test(TEST2), expected)

    expected = xut.gen_test_res(TEST3, status=PASSED_TEST_STTS,
                                main_results=[GOOD_EXEC_STEP_RES])
    for _ in range(5):
        assert_test_results_equal(xut.run_test(TEST3), expected)


def test_cwd(xut: XeetUnittest):
    cwd = platform_path(tempfile.gettempdir())
    step_desc = gen_exec_step_desc(cmd=PWD_CMD, cwd=cwd, expected_stdout=f"{cwd}\n")
    xut.add_test(TEST0, run=[step_desc], reset=True, save=True)

    expected = xut.gen_test_res(TEST0, status=PASSED_TEST_STTS,
                                main_results=[GOOD_EXEC_STEP_RES])
    assert_test_results_equal(xut.run_test(TEST0), expected)


def test_timeout(xut: XeetUnittest):
    timeout = 0.5
    step_desc = gen_exec_step_desc(cmd=gen_sleep_cmd(1), timeout=timeout)  # 1 second sleep
    xut.add_test(TEST0, run=[step_desc], reset=True, save=True)

    expected_step_res = ExecStepResult(completed=False, timeout_period=True)
    status = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.TestErr)
    expected = xut.gen_test_res(TEST0, status=status, main_results=[expected_step_res])
    res = xut.run_test(TEST0)
    assert_test_results_equal(res, expected)
    assert res.duration >= timeout
    assert res.main_res.duration >= timeout
    assert res.main_res.steps_results[0].duration >= timeout


def test_env(xut: XeetUnittest):
    step_desc = gen_exec_step_desc(cmd=f"{SHOWENV_CMD} TEST_ENV", env={"TEST_ENV": "test"},
                                   expected_stdout="test\n")
    xut.add_test(TEST0, run=[step_desc], reset=True)

    step_desc = gen_exec_step_desc(cmd=f"{SHOWENV_CMD} NOSUCHVAR", expected_stdout="\n")
    xut.add_test(TEST1, run=[step_desc])

    os.environ["OS_TEST_ENV"] = "os test"
    step_desc = gen_exec_step_desc(cmd=f"{SHOWENV_CMD} OS_TEST_ENV", use_os_env=True,
                                   expected_stdout="os test\n")
    xut.add_test(TEST2, run=[step_desc])

    step_desc = gen_exec_step_desc(cmd=f"{SHOWENV_CMD} OS_TEST_ENV", use_os_env=False,
                                   expected_stdout="\n")
    xut.add_test(TEST3, run=[step_desc], save=True)

    expected = xut.gen_test_res(TEST0, status=PASSED_TEST_STTS,
                                main_results=[GOOD_EXEC_STEP_RES])
    expected = gen_test_result(status=PASSED_TEST_STTS, main_results=[GOOD_EXEC_STEP_RES])
    for test in [TEST0, TEST1, TEST2, TEST3]:
        xut.run_compare_test(test, expected)

    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        env_vars = {"var0": "val0", "var1": "val1"}
        f.write(json.dumps(env_vars))
    env_file_path = platform_path(f.name)
    step_desc = gen_exec_step_desc(cmd=f"{SHOWENV_CMD} var0", env_file=env_file_path,
                                   expected_stdout="val0\n")
    xut.add_test(TEST0, run=[step_desc], reset=True)

    step_desc = gen_exec_step_desc(cmd=f"{SHOWENV_CMD} var1", env_file=env_file_path,
                                   expected_stdout="val1\n")
    xut.add_test(TEST1, run=[step_desc])

    step_desc = gen_exec_step_desc(cmd=f"{SHOWENV_CMD} var2", env_file=env_file_path,
                                   expected_stdout="\n")
    xut.add_test(TEST2, run=[step_desc], save=True)

    for test in [TEST0, TEST1, TEST2]:
        xut.run_compare_test(test, expected)

    os.remove(env_file_path)


def test_shell_usage(xut: XeetUnittest):
    if in_windows():
        return

    cmd = f"{ECHOCMD} --no-newline 1; {ECHOCMD} --no-newline 2"
    step_desc = gen_exec_step_desc(cmd=cmd, use_shell=True, expected_stdout="12")
    xut.add_test(TEST0, run=[step_desc], reset=True, save=True)

    step_desc = gen_exec_step_desc(cmd=cmd, use_shell=False,
                                   expected_stdout=f"1; {ECHOCMD} --no-newline 2")
    xut.add_test(TEST1, run=[step_desc], save=True)

    expected = gen_test_result(status=PASSED_TEST_STTS, main_results=[GOOD_EXEC_STEP_RES])
    xut.run_compare_test(TEST0, expected)
    xut.run_compare_test(TEST1, expected)


def test_output_behavior(xut: XeetUnittest):
    cmd = f"{OUTPUT_CMD} --stdout O --stderr E --stdout O --stderr E"
    step_desc = gen_exec_step_desc(cmd=cmd, expected_stdout="OEOE")
    xut.add_test(TEST0, run=[step_desc])

    step_desc = gen_exec_step_desc(cmd=cmd, expected_stdout="OEOE",
                                   output_behavior=str(_OutputBehavior.Unify))
    xut.add_test(TEST1, run=[step_desc])

    step_desc = gen_exec_step_desc(cmd=cmd, expected_stdout="OO", expected_stderr="EE",
                                   output_behavior=str(_OutputBehavior.Split))
    xut.add_test(TEST2, run=[step_desc])

    step_desc = gen_exec_step_desc(cmd=cmd, expected_stderr="EE",
                                   output_behavior=str(_OutputBehavior.Split))
    xut.add_test(TEST3, run=[step_desc])
    step_desc = gen_exec_step_desc(cmd=cmd, expected_stdout="OO",
                                   output_behavior=str(_OutputBehavior.Split))
    xut.add_test(TEST4, run=[step_desc])

    step_desc = gen_exec_step_desc(cmd=cmd, expected_stdout="O",
                                   output_behavior=str(_OutputBehavior.Split))
    xut.add_test(TEST5, run=[step_desc])

    step_desc = gen_exec_step_desc(cmd=cmd, expected_stderr="E",
                                   output_behavior=str(_OutputBehavior.Split))
    xut.add_test(TEST6, run=[step_desc], save=True)

    expected = xut.gen_test_res(TEST0, status=PASSED_TEST_STTS,
                                main_results=[GOOD_EXEC_STEP_RES])
    assert_test_results_equal(xut.run_test(TEST0), expected)
    xut.update_test_res_test(expected, TEST1)
    assert_test_results_equal(xut.run_test(TEST1), expected)

    expected_step_res = ExecStepResult(rc=0, rc_ok=True, completed=True,
                                       output_behavior=_OutputBehavior.Split)
    expected = gen_test_result(status=PASSED_TEST_STTS, main_results=[expected_step_res])
    for test in [TEST2, TEST3, TEST4]:
        xut.run_compare_test(test, expected)

    expected_step_res = ExecStepResult(rc=0, rc_ok=True, completed=True, failed=True,
                                       output_behavior=_OutputBehavior.Split, stdout_diff="yes")
    expected = gen_test_result(status=FAILED_TEST_STTS, main_results=[expected_step_res])
    xut.run_compare_test(TEST5, expected)
    expected_step_res = ExecStepResult(rc=0, rc_ok=True, completed=True, failed=True,
                                       output_behavior=_OutputBehavior.Split, stderr_diff="yes")
    expected.main_res.steps_results[0] = expected_step_res
    xut.run_compare_test(TEST6, expected)


def test_exec_model_inheritance(xut: XeetUnittest):
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

        model = xut.get_test(test_name).main_phase.steps[0].model
        assert isinstance(model, ExecStepModel)
        assert model.cmd == cmd
        assert model.cwd == cwd
        assert model.expected_stdout == stdout
        assert model.expected_stderr == stderr
        assert model.shell_path == shell_path
        assert model.timeout == timeout
        assert model.use_shell == use_shell
        assert model.allowed_rc == allowed_rc

    base_step_desc = gen_exec_step_desc(cmd=dflt_cmd,
                                        cwd=dflt_cwd,
                                        expected_stdout=dflt_stdout,
                                        expected_stderr=dflt_stderr,
                                        timeout=dflt_timeout,
                                        use_shell=True,
                                        shell_path=dflt_shell_path,
                                        use_os_env=True,
                                        allowed_rc=dflt_allowed_rc)
    xut.add_setting("base_step", base_step_desc, reset=True)

    step_desc = gen_exec_step_desc(base="settings.base_step", cmd="other_cmd", cwd="")
    xut.add_test(TEST0, run=[step_desc])

    step_desc = gen_exec_step_desc(base="settings.base_step", expected_stdout="other_stdout",
                                   expected_stderr="other_stderr")
    xut.add_test(TEST1, run=[step_desc], save=True)

    step_desc = gen_exec_step_desc(base="settings.base_step", allowed_rc=[0, 2, 5],
                                   use_shell=False, timeout=1, shell_path="/bin/bash")
    xut.add_test(TEST2, run=[step_desc], save=True)

    validate_model(TEST0, cmd="other_cmd", cwd="")
    validate_model(TEST1, stdout="other_stdout", stderr="other_stderr")


def test_output_filter(xut: XeetUnittest):
    filters: list[dict] = [
        {"from_str": "a", "to_str": "b"},
    ]
    cmd = gen_echo_cmd("--no-newline abcdef")
    step_desc = gen_exec_step_desc(cmd=cmd, expected_stdout="bbcdef", output_filters=filters)
    expected = gen_test_result(status=PASSED_TEST_STTS, main_results=[GOOD_EXEC_STEP_RES])
    xut.add_test(TEST0, run=[step_desc], reset=True, save=True)
    xut.run_compare_test(TEST0, expected)

    #  escpe the curly brace, so it won't be interpreted as a xeet variable
    filters.append({"from_str": "[bc]\\{3}", "to_str": "***", "regex": True})
    step_desc = gen_exec_step_desc(cmd=cmd, expected_stdout="***def", output_filters=filters)
    xut.add_test(TEST0, run=[step_desc], reset=True, save=True)
    xut.run_compare_test(TEST0, expected)
