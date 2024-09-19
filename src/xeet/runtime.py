from xeet import TestCriteria
from xeet.xtest import TestStatus, TestResult, TestStatusCategory, Xtest, status_catgoery


class IterationInfo:
    def __init__(self, iter_n: int) -> None:
        self.iter_n = iter_n
        self.tests = {s: [] for s in TestStatus}

    def add_test(self, test_name: str, status: TestStatus) -> None:
        self.tests[status].append(test_name)


class RunInfo:
    def __init__(self, iterations: int, tests: list[Xtest], criteria: TestCriteria) -> None:
        self.iterations: int = iterations
        self.iterations_info = [IterationInfo(i) for i in range(iterations)]
        self.criteria = criteria
        self._tests = tests
        self.results = {}

        self.not_run_tests: bool = False
        self.failed_tests: bool = False

    @property
    def tests(self) -> list[Xtest]:
        return self._tests

    def _test_result_key(self, test_name: str, iteration: int) -> str:
        return f"{test_name}_{iteration}"

    def add_test_result(self, test_name: str, iteration: int, result: TestResult) -> None:
        catgoery = status_catgoery(result.status)
        if catgoery == TestStatusCategory.NotRun:
            self.not_run_tests = True
        elif catgoery == TestStatusCategory.Failed:
            self.failed_tests = True

        self.iterations_info[iteration].add_test(test_name, result.status)
        self.results[self._test_result_key(test_name, iteration)] = result

    def test_result(self, test_name: str, iteration: int) -> TestResult:
        return self.results[self._test_result_key(test_name, iteration)]
