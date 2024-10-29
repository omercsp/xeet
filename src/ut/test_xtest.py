from typing import Iterable, Iterator
from ut import unittest, ConfigTestWrapper, tests_utils_command
from xeet.xtest import (Xtest, TestResult, TestStatus, XeetRunException, XtestModel,
                        status_catgoery, TestStatusCategory)
from xeet.actions import run_tests, CliRunSettings
from xeet.config import TestCriteria, read_config_file
from xeet.common import XeetException
import tempfile
import os


_TEST0 = "test0"
_TEST1 = "test1"
_TEST2 = "test2"
_TEST3 = "test3"
_TEST4 = "test4"
_TEST5 = "test5"

if os.environ.get("UT_DEBUG", "0") == "1":
    _TRUE_CMD = "true"
    _FALSE_CMD = "false"
    _SHOWENV_CMD = "printenv"
    _ECHOCMD = "echo"
else:
    _TRUE_CMD = tests_utils_command("rc.py", "0")
    _FALSE_CMD = tests_utils_command("rc.py", "1")
    _SHOWENV_CMD = tests_utils_command("showenv.py")
    _ECHOCMD = tests_utils_command("echo.py")
_BAD_CMD = "nonexistent"


def _file_content(path: str) -> str:
    with open(path, 'r') as f:
        return f.read()


class TestXtest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ConfigTestWrapper.init_xeet_dir()
        cls.main_config_wrapper = ConfigTestWrapper("main.json")
        cls.run_settings = CliRunSettings(1, False, False, TestCriteria([], [], [], [], False))

    @classmethod
    def tearDownClass(cls):
        ConfigTestWrapper.fini_xeet_dir()

    @classmethod
    def set_test(cls, name, reset: bool = False,  save: bool = False, check_fields: bool = True,
                 **kwargs) -> None:
        if reset:
            cls.main_config_wrapper.tests.clear()
        if check_fields:
            for k in list(kwargs.keys()):
                if k not in XtestModel.model_fields.keys():
                    raise ValueError(f"Invalid Xtest field '{k}' when trying to set test '{name}'")
        cls.main_config_wrapper.add_test(name, **kwargs)
        if save:
            cls.main_config_wrapper.save()

    @classmethod
    def run_test(cls, name) -> TestResult:
        cls.run_settings.criteria.names = {name}
        run_info = run_tests(cls.main_config_wrapper.file_path, cls.run_settings)
        res = run_info.test_result(name, 0)
        return res

    @classmethod
    def run_tests_list(cls, names: Iterable[str]) -> Iterator[TestResult]:
        cls.run_settings.criteria.names = set(names)
        run_info = run_tests(cls.main_config_wrapper.file_path, cls.run_settings)
        for name in names:
            yield run_info.test_result(name, 0)

    @classmethod
    def get_test(cls, name) -> Xtest:
        return read_config_file(cls.main_config_wrapper.file_path).xtest(name)  # type: ignore

    #  Validate docstrings are not inherited
    def test_doc_inheritance(self):
        self.set_test(_TEST0, cmd=_TRUE_CMD, short_desc="text", long_desc="text", reset=True)
        self.set_test(_TEST1, base=_TEST0, save=True)
        x = self.get_test(_TEST1)
        self.assertEqual(x.base, _TEST0)
        self.assertEqual(x.short_desc, "")
        self.assertEqual(x.long_desc, "")

    def _check_test(self, res: TestResult, rc: int | None, status: TestStatus):
        if rc is None:
            self.assertIsNone(res.rc)
        else:
            self.assertEqual(res.rc, rc)
        self.assertEqual(res.status, status)

    def test_bad_test_desc(self):
        self.set_test(_TEST0, cmd=_TRUE_CMD, bad_setting="text", long_desc="text", reset=True,
                      check_fields=False, save=True)
        res = self.run_test(_TEST0)
        self._check_test(res, rc=None, status=TestStatus.InitErr)

    def test_allowed_rc(self):
        self.set_test(_TEST0, cmd=_TRUE_CMD, save=True, reset=True)
        res = self.run_test(_TEST0)
        self._check_test(res, rc=0, status=TestStatus.Passed)

        self.set_test(_TEST0, allowed_rc=[1], cmd=_TRUE_CMD, save=True, reset=True)
        res = self.run_test(_TEST0)
        self._check_test(res, rc=0, status=TestStatus.VerifyRcFailed)

        self.set_test(_TEST0, allowed_rc=[1], cmd=_FALSE_CMD, save=True, reset=True)
        res = self.run_test(_TEST0)
        self._check_test(res, rc=1, status=TestStatus.Passed)

        # Test ignore_rc
        self.set_test(_TEST0, allowed_rc=[0], ignore_rc=True,
                      cmd=_FALSE_CMD, save=True, reset=True)
        res = self.run_test(_TEST0)
        self._check_test(res, rc=1, status=TestStatus.Passed)

        # Inerit allowed_rc
        self.set_test(_TEST0, allowed_rc=[1], cmd=_FALSE_CMD, reset=True)
        self.set_test(_TEST1, base=_TEST0, cmd=_TRUE_CMD, save=True)
        res = self.run_test(_TEST1)
        self._check_test(res, rc=0, status=TestStatus.VerifyRcFailed)

        # Inerit allowed_rc, but override it
        self.set_test(_TEST2, base=_TEST0, allowed_rc=[0], cmd=_TRUE_CMD, save=True)
        res = self.run_test(_TEST2)
        self._check_test(res, rc=0, status=TestStatus.Passed)

        # Inerit allowed_rc, but ignore it
        self.set_test(_TEST3, base=_TEST0, cmd=_TRUE_CMD, ignore_rc=True, save=True)
        res = self.run_test(_TEST3)
        self._check_test(res, rc=0, status=TestStatus.Passed)

    def test_xtest_commands(self):
        self.set_test(_TEST0, cmd=_TRUE_CMD, reset=True)
        self.set_test(_TEST1, base=_TEST0)
        self.set_test(_TEST2, base=_TEST0, cmd=_FALSE_CMD, save=True)
        for res in self.run_tests_list((_TEST0, _TEST1)):
            self._check_test(res, rc=0, status=TestStatus.Passed)
            self.assertIsNone(res.pre_cmd_rc)
            self.assertIsNone(res.verify_cmd_rc)
            self.assertIsNone(res.post_cmd_rc)

        #  Override the test command
        res = self.run_test(_TEST2)
        self._check_test(res, rc=1, status=TestStatus.VerifyRcFailed)
        self.assertIsNone(res.pre_cmd_rc)
        self.assertIsNone(res.verify_cmd_rc)
        self.assertIsNone(res.post_cmd_rc)

        self.set_test(_TEST0, pre_cmd=_FALSE_CMD, cmd=_TRUE_CMD, reset=True)
        self.set_test(_TEST1, base=_TEST0)
        self.set_test(_TEST2, base=_TEST0, pre_cmd=_TRUE_CMD, save=True)
        for res in self.run_tests_list((_TEST0, _TEST1)):
            self._check_test(res, rc=None, status=TestStatus.PreRunErr)
            self.assertEqual(res.pre_cmd_rc, 1)
            self.assertIsNone(res.verify_cmd_rc)
            self.assertIsNone(res.post_cmd_rc)

        #  Validate pre-test command override
        res = self.run_test(_TEST2)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(res.pre_cmd_rc, 0)
        self.assertIsNone(res.verify_cmd_rc)
        self.assertIsNone(res.post_cmd_rc)

        self.set_test(_TEST0, pre_cmd=_TRUE_CMD, cmd=_TRUE_CMD, post_cmd=_FALSE_CMD,
                      reset=True)
        self.set_test(_TEST1, base=_TEST0)
        self.set_test(_TEST2, base=_TEST0, post_cmd=_TRUE_CMD)
        self.set_test(_TEST3, base=_TEST0, pre_cmd=_BAD_CMD, save=True)
        for res in self.run_tests_list((_TEST0, _TEST1)):
            self._check_test(res, rc=0, status=TestStatus.Passed)
            self.assertEqual(res.pre_cmd_rc, 0)
            self.assertIsNone(res.verify_cmd_rc)
            self.assertEqual(res.post_cmd_rc, 1)

        #  Validate post-test command override
        res = self.run_test(_TEST2)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(res.pre_cmd_rc, 0)
        self.assertIsNone(res.verify_cmd_rc)
        self.assertEqual(res.post_cmd_rc, 0)

        #  Validate post-test command override
        res = self.run_test(_TEST3)
        self._check_test(res, rc=None, status=TestStatus.PreRunErr)
        self.assertEqual(res.pre_cmd_rc, None)
        self.assertIsNone(res.verify_cmd_rc)
        self.assertEqual(res.post_cmd_rc, 1)

        #  Test verify command
        self.set_test(_TEST0, cmd=_TRUE_CMD, verify_cmd=_TRUE_CMD, reset=True)
        self.set_test(_TEST1, base=_TEST0)
        self.set_test(_TEST2, base=_TEST0, verify_cmd=_FALSE_CMD)
        self.set_test(_TEST3, base=_TEST0, verify_cmd=_FALSE_CMD, post_cmd=_TRUE_CMD)
        self.set_test(_TEST4, base=_TEST0, verify_cmd=_BAD_CMD, post_cmd=_TRUE_CMD, save=True)
        for res in self.run_tests_list((_TEST0, _TEST1)):
            self._check_test(res, rc=0, status=TestStatus.Passed)
            self.assertIsNone(res.pre_cmd_rc)
            self.assertEqual(res.verify_cmd_rc, 0)
            self.assertIsNone(res.post_cmd_rc)

        #  Override the verify command
        res = self.run_test(_TEST2)
        self._check_test(res, rc=0, status=TestStatus.VerifyFailed)
        self.assertIsNone(res.pre_cmd_rc)
        self.assertEqual(res.verify_cmd_rc, 1)
        self.assertIsNone(res.post_cmd_rc)

        #  Validate post-test is ran regardless of verify command
        res = self.run_test(_TEST3)
        self._check_test(res, rc=0, status=TestStatus.VerifyFailed)
        self.assertIsNone(res.pre_cmd_rc)
        self.assertEqual(res.verify_cmd_rc, 1)
        self.assertEqual(res.post_cmd_rc, 0)

        #  Validate bad verify command
        res = self.run_test(_TEST4)
        self._check_test(res, rc=0, status=TestStatus.VerifyRunErr)
        self.assertIsNone(res.pre_cmd_rc)
        self.assertEqual(res.verify_cmd_rc, None)
        self.assertEqual(res.post_cmd_rc, 0)

    def test_cwd(self):
        self.set_test(_TEST0, cmd="pwd", save=True, reset=True)
        res = self.run_test(_TEST0)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(_file_content(res.stdout_file).strip(), os.getcwd())

        tmp_dir = tempfile.gettempdir()
        self.set_test(_TEST0, cmd="pwd", cwd=tmp_dir, save=True, reset=True)
        self.run_test(_TEST0)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(_file_content(res.stdout_file).strip(), tmp_dir)

        self.set_test(_TEST1, base=_TEST0, save=True)
        res = self.run_test(_TEST1)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(_file_content(res.stdout_file).strip(), tmp_dir)

        self.set_test(_TEST2, base=_TEST0, save=True)
        res = self.run_test(_TEST2)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(_file_content(res.stdout_file).strip(), tmp_dir)

        self.set_test(_TEST3, base=_TEST0, cwd="{XEET_CWD}", save=True)
        res = self.run_test(_TEST3)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(_file_content(res.stdout_file).strip(), os.getcwd())

        self.set_test(_TEST0, cmd="pwd", cwd="/nonexistent", save=True, reset=True)
        res = self.run_test(_TEST0)
        self._check_test(res, rc=None, status=TestStatus.RunErr)

    def test_abstract_tests(self):
        self.run_settings.criteria.hidden_tests = True
        self.set_test(_TEST0, cmd=_TRUE_CMD, abstract=True, reset=True)
        self.set_test(_TEST1, base=_TEST0)
        self.set_test(_TEST2, base=_TEST0, cmd=_FALSE_CMD, save=True)
        self.assertRaises(XeetRunException, self.run_test, _TEST0)

        res = self.run_test(_TEST1)
        self._check_test(res, rc=0, status=TestStatus.Passed)

        res = self.run_test(_TEST2)
        self._check_test(res, rc=1, status=TestStatus.VerifyRcFailed)

        self.run_settings.criteria.hidden_tests = False

    def test_skipped_tests(self):
        self.set_test(_TEST0, pre_cmd=_FALSE_CMD, cmd=_TRUE_CMD, skip=True, reset=True)
        self.set_test(_TEST1, base=_TEST0)
        self.set_test(_TEST2, base=_TEST0, skip=False, save=True)
        for res in self.run_tests_list((_TEST0, _TEST1)):
            self._check_test(res, rc=None, status=TestStatus.Skipped)
            self.assertIsNone(res.pre_cmd_rc)

        self._check_test(self.run_test(_TEST2), rc=None, status=TestStatus.PreRunErr)

    def test_expected_failure(self):
        self.set_test(_TEST0, cmd=_FALSE_CMD, expected_failure=True, reset=True)
        self.set_test(_TEST1, base=_TEST0)
        self.set_test(_TEST2, base=_TEST0, expected_failure=False)
        self.set_test(_TEST3, base=_TEST0, cmd=_TRUE_CMD, save=True)
        for res in self.run_tests_list((_TEST0, _TEST1)):
            self._check_test(res, rc=1, status=TestStatus.ExpectedFail)

        self._check_test(self.run_test(_TEST2), rc=1, status=TestStatus.VerifyRcFailed)
        self._check_test(self.run_test(_TEST3), rc=0, status=TestStatus.UnexpectedPass)

    def test_timeout(self):
        self.set_test(_TEST0, cmd="sleep 1", timeout=0.5, reset=True)
        self.set_test(_TEST1, base=_TEST0, timeout=2)
        self.set_test(_TEST2, base=_TEST0, timeout=None, save=True)

        self._check_test(self.run_test(_TEST0), rc=None, status=TestStatus.Timeout)
        self._check_test(self.run_test(_TEST1), rc=0, status=TestStatus.Passed)
        self._check_test(self.run_test(_TEST2), rc=None, status=TestStatus.Timeout)

    def test_env(self):
        self.set_test(_TEST0, cmd=f"{_SHOWENV_CMD} TEST_ENV",
                      env={"TEST_ENV": "test"}, reset=True)
        self.set_test(_TEST1, base=_TEST0)
        self.set_test(_TEST2, base=_TEST0, env={"TEST_ENV": "test2"})
        self.set_test(_TEST3, base=_TEST0, inherit_env_variables=False)
        os.environ["OS_TEST_ENV"] = "os test"
        self.set_test(_TEST4,  cmd=f"{_SHOWENV_CMD} OS_TEST_ENV")
        self.set_test(_TEST5, base=_TEST4, use_os_env=False, save=True)

        res = self.run_test(_TEST0)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(_file_content(res.stdout_file).strip(), "test")

        res = self.run_test(_TEST1)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(_file_content(res.stdout_file).strip(), "test")

        res = self.run_test(_TEST2)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(_file_content(res.stdout_file).strip(), "test2")

        res = self.run_test(_TEST3)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(_file_content(res.stdout_file).strip(), "")

        res = self.run_test(_TEST4)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(_file_content(res.stdout_file).strip(), "os test")

        res = self.run_test(_TEST5)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(_file_content(res.stdout_file).strip(), "")

    def test_variables(self):
        self.set_test(_TEST0, cmd=f"{_ECHOCMD} {{TEST_VAR}}",
                      var_map={"TEST_VAR": "test"}, reset=True)
        self.set_test(_TEST1, base=_TEST0)
        self.set_test(_TEST2, base=_TEST0, var_map={"TEST_VAR": "test2"})
        self.set_test(_TEST3, base=_TEST0, inherit_variables=False, save=True)

        res = self.run_test(_TEST0)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(_file_content(res.stdout_file).strip(), "test")

        res = self.run_test(_TEST1)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(_file_content(res.stdout_file).strip(), "test")

        res = self.run_test(_TEST2)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        self.assertEqual(_file_content(res.stdout_file).strip(), "test2")

        self.assertRaises(XeetException, self.run_test, _TEST3)

    def test_autovars(self):
        test_cmd = _ECHOCMD + \
            (" {XEET_TEST_NAME} {XEET_TEST_STDOUT} {XEET_TEST_STDERR} {XEET_TEST_OUTPUT_DIR}")

        self.set_test(_TEST0, cmd=test_cmd, reset=True)
        self.set_test(_TEST1, base=_TEST0, var_map={"XEET_TEST_NAME": "bad"}, save=True)

        res = self.run_test(_TEST0)
        self._check_test(res, rc=0, status=TestStatus.Passed)
        output_dir = os.path.dirname(res.stdout_file)
        expected = f"{_TEST0} {res.stdout_file} {res.stderr_file} {output_dir}"
        self.assertEqual(_file_content(res.stdout_file).strip(), expected)
        self.assertRaises(XeetException, self.run_test, _TEST1)  # XEET prefix is reserved

    def test_groups(self):
        self.set_test(_TEST0, cmd=_TRUE_CMD, groups=["group1"], reset=True)
        self.set_test(_TEST1, base=_TEST0, groups=["group2"])
        self.set_test(_TEST2, base=_TEST0, groups=["group1", "group2"], save=True)

    def test_output_behavior(self):
        cmd = f"{_ECHOCMD} stdout; {_ECHOCMD} stderr 1>&2"
        self.set_test(_TEST0, shell=True, cmd=cmd, reset=True)
        # Unifiy stdout and stderr explicitly
        self.set_test(_TEST1, base=_TEST0, output_behavior="unify")
        self.set_test(_TEST2, base=_TEST0, output_behavior="split")
        self.set_test(_TEST3, shell=True, cmd=cmd, output_behavior="split", save=True)

        for res in self.run_tests_list([_TEST1]):
            self._check_test(res, rc=0, status=TestStatus.Passed)
            self.assertEqual(_file_content(res.stdout_file).strip(), "stdout\nstderr")

        for res in self.run_tests_list([_TEST2, _TEST3]):
            self._check_test(res, rc=0, status=TestStatus.Passed)
            self.assertEqual(_file_content(res.stdout_file).strip(), "stdout")
            self.assertEqual(_file_content(res.stderr_file).strip(), "stderr")

    def test_test_status_categories(self):
        for status in TestStatus:
            self.assertNotEqual(status_catgoery(status), TestStatusCategory.Unknown)
