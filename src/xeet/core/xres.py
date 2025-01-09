from . import TestCriteria
from enum import Enum, auto
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class XStepResult:
    err_summary: str = ""
    completed: bool = False
    duration: float | None = None
    failed: bool = False

    def error_summary(self) -> str:
        if not self.completed:
            return f" incomplete: {self.err_summary}"
        if self.failed:
            return f" failed: {self.err_summary}"
        return ""


class TestStatus(Enum):
    Undefined = auto()
    Skipped = auto()
    RunErr = auto()  # This isn't a test failure per se, but a failure to run the test
    Failed = auto()
    Passed = auto()


class TestSubStatus(Enum):
    Undefined = auto()
    InitErr = auto()
    PreRunErr = auto()
    UnexpectedPass = auto()
    ExpectedFail = auto()


_STATUS_TEXT = {
    TestStatus.Undefined: "Undefined",
    TestStatus.Passed: "Passed",
    TestStatus.Failed: "Failed",
    TestStatus.RunErr: "Run error",
    TestStatus.Skipped: "Skipped",
}


_SUB_STATUS_TEXT = {
    TestSubStatus.Undefined: "Undefined",
    TestSubStatus.InitErr: "Initialization error",
    TestSubStatus.PreRunErr: "Pre-run error",
    TestSubStatus.ExpectedFail: "Expected failure",
    TestSubStatus.UnexpectedPass: "Unexpected pass",
}


def status_as_str(status: TestStatus, sub_status: TestSubStatus = TestSubStatus.Undefined) -> str:
    if sub_status == TestSubStatus.Undefined:
        return _STATUS_TEXT[status]
    return _SUB_STATUS_TEXT[sub_status]


@dataclass
class XStepListResult:
    prefix: str = ""
    results: list[XStepResult] = field(default_factory=list)
    completed: bool = True
    failed: bool = False

    def error_summary(self) -> str:
        for i, r in enumerate(self.results):
            if not r.completed or r.failed:
                return f"{self.prefix} step #{i}: {r.error_summary()}"
        return ""

    #  post_init is called after the dataclass is initialized. This is used
    #  in unittesting only. By default, results is empty, so completed and failed
    #  are True and False, respectively.
    def __post_init__(self) -> None:
        if not self.results:
            return
        self.completed = all([r.completed for r in self.results])
        self.failed = any([r.failed for r in self.results])


@dataclass
class TestResult:
    status: TestStatus = TestStatus.Undefined
    sub_status: TestSubStatus = TestSubStatus.Undefined
    post_run_status: TestStatus = TestStatus.Undefined
    duration: float = 0
    status_reason: str = ""
    pre_run_res: XStepListResult = field(default_factory=lambda: XStepListResult(prefix="Pre-run"))
    run_res: XStepListResult = field(default_factory=lambda: XStepListResult(prefix="Run"))
    post_run_res: XStepListResult = field(
        default_factory=lambda: XStepListResult(prefix="Post-run"))

    def error_summary(self) -> str:
        ret = ""
        if self.sub_status == TestSubStatus.PreRunErr:
            ret = self.pre_run_res.error_summary()
        elif self.status == TestStatus.Skipped or self.sub_status == TestSubStatus.InitErr:
            ret = self.status_reason
        elif self.status == TestStatus.Failed or self.status == TestStatus.RunErr:
            ret = self.run_res.error_summary()

        if not self.post_run_res.completed or self.post_run_res.failed:
            ret = "NOTICE: Post-test failed or didn't complete\n"
            ret += self.post_run_res.error_summary()

        return ret


class IterationResult:
    def __init__(self, iter_n: int) -> None:
        self.iter_n = iter_n
        #  self.status_results_summary = {s: [] for s in TestStatus}
        self.status_results_summary: dict[tuple[TestStatus, TestSubStatus], list[str]] = {}
        self.results = {}

        self.not_run_tests: bool = False
        self.failed_tests: bool = False
        self._lock = Lock()

    def add_test_result(self, test_name: str, result: TestResult) -> None:
        with self._lock:
            if result.status == TestStatus.RunErr:
                self.not_run_tests = True
            elif result.status == TestStatus.Failed:
                self.failed_tests = True
            key = (result.status, result.sub_status)
            if key not in self.status_results_summary:
                self.status_results_summary[key] = [test_name]
            else:
                self.status_results_summary[key].append(test_name)

            self.results[test_name] = result


class RunResult:
    def __init__(self, iterations: int, criteria: TestCriteria) -> None:
        self.iterations: int = iterations
        self.iter_results = [IterationResult(i) for i in range(iterations)]
        self.criteria = criteria

    @property
    def failed_tests(self) -> bool:
        return any([ir.failed_tests for ir in self.iter_results])

    @property
    def not_run_tests(self) -> bool:
        return any([ir.not_run_tests for ir in self.iter_results])

    def test_result(self, test_name: str, iteration: int) -> TestResult:
        return self.iter_results[iteration].results[test_name]
