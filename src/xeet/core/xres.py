from . import TestCriteria
from enum import Enum, auto
from dataclasses import dataclass, field


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


class TestStatusCategory(str, Enum):
    Undefined = "Undefined"
    Skipped = "Skipped"
    NotRun = "Not run"
    Failed = "Failed"
    Passed = "Passed"
    Unknown = "Unknown"


class TestStatus(Enum):
    Undefined = auto()
    Skipped = auto()
    InitErr = auto()
    PreRunErr = auto()
    RunErr = auto()  # This isn't a test failure per se, but a failure to run the test
    Failed = auto()
    UnexpectedPass = auto()
    Passed = auto()
    ExpectedFail = auto()


_NOT_RUN_STTS = {TestStatus.InitErr, TestStatus.PreRunErr, TestStatus.RunErr}
_FAILED_STTS = {TestStatus.Failed, TestStatus.UnexpectedPass}
_PASSED_STTS = {TestStatus.Passed, TestStatus.ExpectedFail}


def status_catgoery(status: TestStatus) -> TestStatusCategory:
    if status == TestStatus.Undefined:
        return TestStatusCategory.Undefined
    if status == TestStatus.Skipped:
        return TestStatusCategory.Skipped
    if status in _NOT_RUN_STTS:
        return TestStatusCategory.NotRun
    if status in _FAILED_STTS:
        return TestStatusCategory.Failed
    if status in _PASSED_STTS:
        return TestStatusCategory.Passed
    return TestStatusCategory.Unknown


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
    duration: float = 0
    status_reason: str = ""
    pre_run_res: XStepListResult = field(default_factory=lambda: XStepListResult(prefix="Pre-run"))
    run_res: XStepListResult = field(default_factory=lambda: XStepListResult(prefix="Run"))
    post_run_res: XStepListResult = field(
        default_factory=lambda: XStepListResult(prefix="Post-run"))


class IterationResult:
    def __init__(self, iter_n: int) -> None:
        self.iter_n = iter_n
        self.status_results_summary = {s: [] for s in TestStatus}
        self.results = {}

        self.not_run_tests: bool = False
        self.failed_tests: bool = False

    def add_test_result(self, test_name: str, result: TestResult) -> None:
        catgoery = status_catgoery(result.status)
        if catgoery == TestStatusCategory.NotRun:
            self.not_run_tests = True
        elif catgoery == TestStatusCategory.Failed:
            self.failed_tests = True

        self.status_results_summary[result.status].append(test_name)
        self.results[test_name] = result


class RunResult:
    def __init__(self, iterations: int, criteria: TestCriteria) -> None:
        self.iterations: int = iterations
        self.iter_results = [IterationResult(i) for i in range(iterations)]
        self.criteria = criteria

    def _test_result_key(self, test_name: str, iteration: int) -> str:
        return f"{test_name}_{iteration}"

    @property
    def failed_tests(self) -> bool:
        return any([ir.failed_tests for ir in self.iter_results])

    @property
    def not_run_tests(self) -> bool:
        return any([ir.not_run_tests for ir in self.iter_results])

    def test_result(self, test_name: str, iteration: int) -> TestResult:
        return self.iter_results[iteration].results[test_name]
