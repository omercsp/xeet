from xeet import XeetException
from . import TestsCriteria
from .matrix import MatrixPermutation
from enum import Enum, auto
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class StepResult:
    completed: bool = False
    failed: bool = False
    duration: float | None = None
    errmsg: str = ""


class TestPrimaryStatus(Enum):
    Undefined = auto()
    Skipped = auto()
    NotRun = auto()  # This isn't a test failure per se, but a failure to run the test
    Failed = auto()
    Passed = auto()


class TestSecondaryStatus(Enum):
    Undefined = auto()
    InitErr = auto()
    PreTestErr = auto()
    TestErr = auto()
    UnexpectedPass = auto()
    ExpectedFail = auto()


_STATUS_TEXT = {
    TestPrimaryStatus.Undefined: "Undefined",
    TestPrimaryStatus.Passed: "Passed",
    TestPrimaryStatus.Failed: "Failed",
    TestPrimaryStatus.NotRun: "Not run",
    TestPrimaryStatus.Skipped: "Skipped",
}


_SUB_STATUS_TEXT = {
    TestSecondaryStatus.Undefined: "Undefined",
    TestSecondaryStatus.InitErr: "Initialization error",
    TestSecondaryStatus.PreTestErr: "Pre-test error",
    TestSecondaryStatus.TestErr: "Test error",
    TestSecondaryStatus.ExpectedFail: "Expected failure",
    TestSecondaryStatus.UnexpectedPass: "Unexpected pass",
}


@dataclass
class TestStatus:
    primary: TestPrimaryStatus = TestPrimaryStatus.Undefined
    secondary: TestSecondaryStatus = TestSecondaryStatus.Undefined

    def __str__(self) -> str:
        if self.secondary == TestSecondaryStatus.Undefined:
            return _STATUS_TEXT[self.primary]
        return _SUB_STATUS_TEXT[self.secondary]

    def __hash__(self) -> int:
        return hash((self.primary, self.secondary))


@dataclass
class StepsListResult:
    prefix: str = ""
    results: list[StepResult] = field(default_factory=list)

    @property
    def completed(self) -> bool:
        return all([r.completed for r in self.results])

    @property
    def failed(self) -> bool:
        return any([r.failed for r in self.results])

    def error_summary(self) -> str:
        for i, r in enumerate(self.results):
            if not r.completed:
                return f"{self.prefix} step #{i} incompleted: {r.errmsg}"
            if r.failed:
                return f"{self.prefix} step #{i} failed: {r.errmsg}"
        return ""


@dataclass
class TestResult:
    status: TestStatus = field(default_factory=TestStatus)
    post_run_status: TestPrimaryStatus = TestPrimaryStatus.Undefined
    duration: float = 0
    status_reason: str = ""
    pre_run_res: StepsListResult = field(default_factory=lambda: StepsListResult(prefix="Pre-run"))
    run_res: StepsListResult = field(default_factory=lambda: StepsListResult(prefix="Run"))
    post_run_res: StepsListResult = field(
        default_factory=lambda: StepsListResult(prefix="Post-run"))

    def error_summary(self) -> str:
        ret = ""
        if self.status.secondary == TestSecondaryStatus.PreTestErr:
            ret = self.pre_run_res.error_summary()
        elif self.status.primary == TestPrimaryStatus.Skipped or \
                self.status.secondary == TestSecondaryStatus.InitErr:
            ret = self.status_reason
        elif self.status.primary == TestPrimaryStatus.Failed or \
                self.status.primary == TestPrimaryStatus.NotRun:
            ret = self.run_res.error_summary()

        if not self.post_run_res.completed or self.post_run_res.failed:
            ret = "NOTICE: Post-test failed or didn't complete\n"
            ret += self.post_run_res.error_summary()

        return ret


StatusTestsDict = dict[TestStatus, list[str]]


class MtrxResult:
    def __init__(self, mp: MatrixPermutation, mpi: int) -> None:
        self.mp = mp
        self.mpi = mpi
        #  self.status_results_summary = {s: [] for s in TestStatus}
        self.status_results_summary: StatusTestsDict = {}
        self.results = {}

        self.not_run_tests: bool = False
        self.failed_tests: bool = False
        self._lock = Lock()

    def add_test_result(self, test_name: str, result: TestResult) -> None:
        with self._lock:
            stts = result.status
            if stts.primary == TestPrimaryStatus.NotRun:
                self.not_run_tests = True
            elif stts.primary == TestPrimaryStatus.Failed:
                self.failed_tests = True
            if stts not in self.status_results_summary:
                self.status_results_summary[stts] = []

            self.status_results_summary[stts].append(test_name)
            self.results[test_name] = result


class IterationResult:
    def __init__(self, iter_n: int) -> None:
        self.iter_n = iter_n
        self.mtrx_results: list[MtrxResult] = []

    def add_mtrx_res(self, mp: MatrixPermutation, mpi: int) -> MtrxResult:
        self.mtrx_results.append(MtrxResult(mp, mpi))
        return self.mtrx_results[-1]

    @property
    def failed_tests(self) -> bool:
        return any([pr.failed_tests for pr in self.mtrx_results])

    @property
    def not_run_tests(self) -> bool:
        return any([pr.not_run_tests for pr in self.mtrx_results])

    def test_result(self, test_name: str, permutation: int) -> TestResult:
        return self.mtrx_results[permutation].results[test_name]


class RunResult:
    def __init__(self, iterations: int, matrix_count: int, criteria: TestsCriteria) -> None:
        self.iterations: int = iterations
        self.iter_results = [IterationResult(i) for i in range(iterations)]
        self.mtrx_count: int = matrix_count
        self.criteria = criteria

    @property
    def failed_tests(self) -> bool:
        return any([ir.failed_tests for ir in self.iter_results])

    @property
    def not_run_tests(self) -> bool:
        return any([ir.not_run_tests for ir in self.iter_results])

    def test_result(self, test_name: str, iteration: int, mpi: int) -> TestResult:
        try:
            return self.iter_results[iteration].mtrx_results[mpi].results[test_name]
        except (KeyError, IndexError) as e:
            raise XeetException(f"Test '{test_name}' not found in iteration {iteration}, "
                                f"permutation {mpi} - {e}")


EmptyRunResult = RunResult(iterations=0, matrix_count=0, criteria=TestsCriteria())
