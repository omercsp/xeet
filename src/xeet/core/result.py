from xeet import XeetException
from . import TestsCriteria
from enum import Enum, auto
from dataclasses import dataclass, field
from timeit import default_timer as timer
from functools import wraps
from typing import TYPE_CHECKING
from functools import cached_property
if TYPE_CHECKING:
    from .test import Test, Phase
    from .step import Step


@dataclass
class MeasuredResult:
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration_str(self) -> str:
        return f"{self.duration:.3f}s"

    def set_start_time(self) -> None:
        self.start_time = timer()

    def set_end_time(self) -> None:
        self.end_time = timer()

    @cached_property
    def duration(self) -> float:
        return self.end_time - self.start_time


def time_result(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = timer()
        ret: MeasuredResult = func(*args, **kwargs)
        ret.start_time = start
        ret.set_end_time()
        return ret
    return wrapper


@dataclass
class StepResult(MeasuredResult):
    completed: bool = False
    failed: bool = False
    errmsg: str = ""
    phase_res: "PhaseResult" = None  # type: ignore
    step: "Step" = None  # type: ignore


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
class PhaseResult(MeasuredResult):
    name: str = ""
    test_result: "TestResult" = None  # type: ignore
    phase: "Phase" = None  # type: ignore
    steps_results: list[StepResult] = field(default_factory=list)

    def append_step_result(self, step_res: StepResult) -> None:
        step_res.phase_res = self
        self.steps_results.append(step_res)

    @property
    def completed(self) -> bool:
        return all([r.completed for r in self.steps_results])

    @property
    def failed(self) -> bool:
        return any([r.failed for r in self.steps_results])

    def error_summary(self) -> str:
        for i, r in enumerate(self.steps_results):
            if not r.completed:
                return f"{self.name} step #{i} incompleted: {r.errmsg}"
            if r.failed:
                return f"{self.name} step #{i} failed: {r.errmsg}"
        return ""


@dataclass
class TestResult(MeasuredResult):
    test: "Test" = None  # type: ignore
    status: TestStatus = field(default_factory=TestStatus)
    post_run_status: TestPrimaryStatus = TestPrimaryStatus.Undefined
    status_reason: str = ""
    pre_run_res: PhaseResult = field(
        default_factory=lambda: PhaseResult(name="Pre-run"))  # type: ignore
    main_res: PhaseResult = field(
        default_factory=lambda: PhaseResult(name="Run"))  # type: ignore
    post_run_res: PhaseResult = field(
        default_factory=lambda: PhaseResult(name="Post-run"))  # type: ignore

    def __post_init__(self):
        if self.test:  # on testings, test might be None
            self.pre_run_res.phase = self.test.pre_phase
            self.main_res.phase = self.test.main_phase
            self.post_run_res.phase = self.test.post_phase

        self.pre_run_res.test_result = self
        self.main_res.test_result = self
        self.post_run_res.test_result = self

    def error_summary(self) -> str:
        ret = ""
        if self.status.secondary == TestSecondaryStatus.PreTestErr:
            ret = self.pre_run_res.error_summary()
        elif self.status.primary == TestPrimaryStatus.Skipped or \
                self.status.secondary == TestSecondaryStatus.InitErr:
            ret = self.status_reason
        elif self.status.primary == TestPrimaryStatus.Failed or \
                self.status.primary == TestPrimaryStatus.NotRun:
            ret = self.main_res.error_summary()

        if not self.post_run_res.completed or self.post_run_res.failed:
            ret = "NOTICE: Post-test failed or didn't complete\n"
            ret += self.post_run_res.error_summary()

        return ret


StatusTestsDict = dict[TestStatus, list[str]]


class IterationResult(MeasuredResult):
    def __init__(self, iter_n: int) -> None:
        self.iter_n = iter_n
        #  self.status_results_summary = {s: [] for s in TestStatus}
        self.status_results_summary: StatusTestsDict = {}
        self.results = {}

        self.not_run_tests: bool = False
        self.failed_tests: bool = False

    def add_test_result(self, test_name: str, result: TestResult) -> None:
        stts = result.status
        if stts.primary == TestPrimaryStatus.NotRun:
            self.not_run_tests = True
        elif stts.primary == TestPrimaryStatus.Failed:
            self.failed_tests = True
        if stts not in self.status_results_summary:
            self.status_results_summary[stts] = []

        self.status_results_summary[stts].append(test_name)
        self.results[test_name] = result


class RunResult(MeasuredResult):
    def __init__(self, iterations: int, criteria: TestsCriteria) -> None:
        super().__init__()
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
        try:
            return self.iter_results[iteration].results[test_name]
        except (KeyError, IndexError) as e:
            raise XeetException(f"Test '{test_name}' not found in iteration {iteration} - {e}")


EmptyRunResult = RunResult(iterations=0, criteria=TestsCriteria())
