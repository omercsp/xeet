from ut import unittest
import os
import shlex
import subprocess


_HERE = os.path.dirname(os.path.abspath(__file__))
_OUT_DIR = os.path.join(_HERE, "out")
_EXPECTED_OUTPUT_DIR = os.path.join(_HERE, "expected")
_LOG_DIR = os.path.join(_HERE, "log")
_STDOUT_FILENAME = "stdout"
_STDERR_FILENAME = "stderr"


def _file_content(file_path: str) -> str:
    if not os.path.exists(file_path):
        return ""
    with open(file_path) as f:
        return f.read()

class XeetCmdInfo:
    def __init__(self, name: str, tc: unittest.TestCase, rc: int, config_file_name: str, *args) -> None:
        self.name = name
        self.config_file_name = config_file_name
        self.config_file_path = os.path.join(_HERE, "configs", config_file_name)
        self.args = args
        self.rc = rc
        self.tc = tc
        self.completed_process: subprocess.CompletedProcess | None = None
        self.use_log = True

    @property
    def main_xeet_cmd(self) -> str:
        raise NotImplementedError

    @property
    def stdout_path(self) -> str:
        return os.path.join(_OUT_DIR, self.name, _STDOUT_FILENAME)

    @property
    def stderr_path(self) -> str:
        return os.path.join(_OUT_DIR, self.name, _STDERR_FILENAME)

    @property
    def expected_stdout_file(self) -> str:
        return os.path.join(_EXPECTED_OUTPUT_DIR, self.name, _STDOUT_FILENAME)

    @property
    def expected_stderr_file(self) -> str:
        return os.path.join(_EXPECTED_OUTPUT_DIR, self.name, _STDERR_FILENAME)

    def filter_output(self, output: str) -> str:
        lines = output.splitlines()
        if lines[0].startswith("xeet, v"):
            lines = lines[1:]
        return "\n".join(lines)

    def run(self) -> None:
        cmd = f"xeet --no-colors {self.main_xeet_cmd} -c '{self.config_file_path}' " + " ".join(self.args)
        if self.use_log:
            cmd += f" --log-file '{os.path.join(_LOG_DIR, self.name)}.log'"
        cmd = shlex.split(cmd)
        os.makedirs(os.path.dirname(self.stdout_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.stderr_path), exist_ok=True)
        with open(self.stdout_path, "w") as stdout, open(self.stderr_path, "w") as stderr:
            self.completed_process = subprocess.run(cmd, stdout=stdout, stderr=stderr)

        actual_output = _file_content(self.stdout_path)
        actual_output = self.filter_output(actual_output)
        expected_output = _file_content(self.expected_stdout_file)
        self.tc.assertEqual(actual_output, expected_output)
        self.tc.assertEqual(self.completed_process.returncode, self.rc)

class XeetRunInfo(XeetCmdInfo):
    @property
    def main_xeet_cmd(self) -> str:
        return "run"


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(_OUT_DIR, exist_ok=True)
        os.makedirs(_LOG_DIR, exist_ok=True)

    def test_single_test(self):
        print()
        XeetRunInfo("single_test", self, 0, "sanity.yaml", "-t", "001_pass").run()
        print()
