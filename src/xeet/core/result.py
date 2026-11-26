from xeet import XeetException
from .matrix import MatrixPermutation
from enum import Enum, auto
from dataclasses import dataclass, field
from timeit import default_timer as timer
from functools import wraps
from threading import Lock
from typing import TYPE_CHECKING
from functools import cached_property
if TYPE_CHECKING:
    from .test import Test, Phase
    from .step import Step
    from . import TestsCriteria


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
    __test__ = False
    Undefined = auto()
    Skipped = auto()
    NotRun = auto()  # This isn't a test failure per se, but a failure to run the test
    Failed = auto()
    Passed = auto()


class TestSecondaryStatus(Enum):
    __test__ = False
    Undefined = auto()
    InitErr = auto()
    PreTestErr = auto()
    TestErr = auto()
    Stopped = auto()
    UnexpectedPass = auto()
    ExpectedFail = auto()
    FixtureErr = auto()


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
    TestSecondaryStatus.Stopped: "Stopped",
    TestSecondaryStatus.ExpectedFail: "Expected failure",
    TestSecondaryStatus.UnexpectedPass: "Unexpected pass",
    TestSecondaryStatus.FixtureErr: "Fixture error",
}


@dataclass
class TestStatus:
    primary: TestPrimaryStatus = TestPrimaryStatus.Undefined
    secondary: TestSecondaryStatus = TestSecondaryStatus.Undefined
    __test__ = False

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
    __test__ = False
    test: "Test" = None  # type: ignore
    status: TestStatus = field(default_factory=TestStatus)
    post_run_status: TestPrimaryStatus = TestPrimaryStatus.Undefined
    status_reason: str = ""
    pre_run_res: PhaseResult = None  # type: ignore
    main_res: PhaseResult = None  # type: ignore
    post_run_res: PhaseResult = None  # type: ignore

    def __post_init__(self):
        self.pre_run_res = PhaseResult(name="Pre-run", test_result=self)
        self.main_res = PhaseResult(name="Run", test_result=self)
        self.post_run_res = PhaseResult(name="Post-run", test_result=self)

        if self.test:  # on testings, test might be None
            self.pre_run_res.phase = self.test.pre_phase
            self.main_res.phase = self.test.main_phase
            self.post_run_res.phase = self.test.post_phase

    def error_summary(self) -> str:
        ret = ""
        if self.status.secondary == TestSecondaryStatus.PreTestErr:
            ret = self.pre_run_res.error_summary()
        elif self.status.primary == TestPrimaryStatus.Skipped or \
                self.status.secondary == TestSecondaryStatus.InitErr or \
                self.status.secondary == TestSecondaryStatus.FixtureErr:
            ret = self.status_reason
        elif self.status.primary == TestPrimaryStatus.Failed or \
                self.status.primary == TestPrimaryStatus.NotRun:
            ret = self.main_res.error_summary()

        if not self.post_run_res.completed or self.post_run_res.failed:
            ret = "NOTICE: Post-test failed or didn't complete\n"
            ret += self.post_run_res.error_summary()

        return ret


#  Result of a fixture's setup and teardown passes in a single matrix permutation. The fixture is
#  referenced by name, so the result holds no references to runtime objects of its own.
@dataclass
class FixtureResult(MeasuredResult):
    name: str = ""
    skip_reason: str = ""  # set if the fixture wasn't activated (its setup wasn't attempted)
    setup_res: PhaseResult = None  # type: ignore
    teardown_res: PhaseResult = None  # type: ignore
    setup_error: str = ""  # error preparing the setup steps, before running them
    teardown_error: str = ""  # error preparing the teardown steps, before running them
    teardown_skip_reason: str = ""  # set if the teardown was skipped after it was due to run

    def __post_init__(self):
        self.setup_res = PhaseResult(name="Setup")
        self.teardown_res = PhaseResult(name="Teardown")

    @property
    def skipped(self) -> bool:
        return bool(self.skip_reason)

    @staticmethod
    def _phase_status(phase_res: PhaseResult, error: str) -> TestPrimaryStatus:
        if error or not phase_res.completed:
            return TestPrimaryStatus.NotRun
        if phase_res.failed:
            return TestPrimaryStatus.Failed
        return TestPrimaryStatus.Passed

    @property
    def setup_status(self) -> TestPrimaryStatus:
        if self.skipped:
            return TestPrimaryStatus.Skipped
        if not self.setup_res.steps_results and not self.setup_error:
            return TestPrimaryStatus.Undefined  # Teardown only fixture
        return self._phase_status(self.setup_res, self.setup_error)

    @property
    def teardown_status(self) -> TestPrimaryStatus:
        if self.skipped or self.teardown_skip_reason:
            return TestPrimaryStatus.Skipped
        if not self.teardown_res.steps_results and not self.teardown_error:
            return TestPrimaryStatus.Undefined  # Setup only fixture, or teardown not run yet
        return self._phase_status(self.teardown_res, self.teardown_error)

    @property
    def setup_failed(self) -> bool:
        return self.setup_status in (TestPrimaryStatus.NotRun, TestPrimaryStatus.Failed)

    @property
    def teardown_failed(self) -> bool:
        return self.teardown_status in (TestPrimaryStatus.NotRun, TestPrimaryStatus.Failed)

    def setup_error_summary(self) -> str:
        if self.skipped:
            return self.skip_reason
        return self.setup_error or self.setup_res.error_summary()

    def teardown_error_summary(self) -> str:
        if self.skipped:
            return self.skip_reason
        return self.teardown_skip_reason or self.teardown_error or \
            self.teardown_res.error_summary()


StatusTestsDict = dict[TestStatus, list[str]]


class MtrxResult(MeasuredResult):
    def __init__(self, mp: MatrixPermutation, mpi: int) -> None:
        self.mp = mp
        self.mpi = mpi
        #  self.status_results_summary = {s: [] for s in TestStatus}
        self.status_results_summary: StatusTestsDict = {}
        self.results: dict[str, TestResult] = dict()
        self.fixture_results: list[FixtureResult] = []

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

    def is_empty(self) -> bool:
        return not self.results

    def add_fixture_result(self, fixture_res: FixtureResult) -> None:
        self.fixture_results.append(fixture_res)

    def fixture_result(self, name: str) -> FixtureResult | None:
        return next((r for r in self.fixture_results if r.name == name), None)

    @property
    def teardown_failed(self) -> bool:
        return any(r.teardown_failed for r in self.fixture_results)


class IterationResult(MeasuredResult):
    def __init__(self, iter_n: int) -> None:
        super().__init__()
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

    @property
    def teardown_failed(self) -> bool:
        return any(mr.teardown_failed for mr in self.mtrx_results)

    def test_result(self, test_name: str, permutation: int) -> TestResult:
        return self.mtrx_results[permutation].results[test_name]

    def is_empty(self) -> bool:
        if not self.mtrx_results:
            return True
        return all(mr.is_empty() for mr in self.mtrx_results)


class RunResult(MeasuredResult):
    def __init__(self, iterations: int, matrix_count: int, criteria: "TestsCriteria") -> None:
        super().__init__()
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

    @property
    def teardown_failed(self) -> bool:
        return any(ir.teardown_failed for ir in self.iter_results)

    def test_result(self, test_name: str, iteration: int, mpi: int) -> TestResult:
        try:
            return self.iter_results[iteration].mtrx_results[mpi].results[test_name]
        except (KeyError, IndexError) as e:
            raise XeetException(f"Test '{test_name}' not found in iteration {iteration}, "
                                f"permutation {mpi} - {e}")

    def is_empty(self) -> bool:
        if not self.iter_results:
            return True
        return all(ir.is_empty() for ir in self.iter_results)
