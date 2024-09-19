from xeet.xtest import TestStatus, TestResult, TestStatusCategory, status_catgoery


class RunInfo(object):
    def __init__(self, iterations: int) -> None:
        self.iterations: int = iterations
        self.iterations_info = [{s: [] for s in TestStatus} for _ in range(iterations)]
        self.results = {}

        self.not_run_tests: bool = False
        self.failed_tests: bool = False

    def _test_result_key(self, test_name: str, iteration: int) -> str:
        return f"{test_name}_{iteration}"

    def add_test_result(self, test_name: str, iteration: int, result: TestResult) -> None:
        catgoery = status_catgoery(result.status)
        if catgoery == TestStatusCategory.NotRun:
            self.not_run_tests = True
        elif catgoery == TestStatusCategory.Failed:
            self.failed_tests = True

        self.iterations_info[iteration][result.status].append(test_name)
        self.results[self._test_result_key(test_name, iteration)] = result

    def test_result(self, test_name: str, iteration: int) -> TestResult:
        return self.results[self._test_result_key(test_name, iteration)]

    def had_bad_tests(self) -> bool:
        return self.not_run_tests or self.failed_tests
