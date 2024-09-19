from xeet.xtest import TestStatus, TestResult


class IterInfo(object):
    def __init__(self) -> None:
        self.failed_tests = []
        self.skipped_tests = []
        self.successful_tests = []
        self.not_run_tests = []
        self.expected_failures = []
        self.unexpected_pass = []


class RunInfo(object):
    def __init__(self, iterations: int) -> None:
        self.iterations: int = iterations
        self.iterations_info = [IterInfo() for _ in range(iterations)]
        self._failed = False
        self.results = {}

    def _test_result_key(self, test_name: str, iteration: int) -> str:
        return f"{test_name}_{iteration}"

    def add_test_result(self, test_name: str, iteration: int, result: TestResult) -> None:
        status = result.status
        if status == TestStatus.Skipped:
            self.iterations_info[iteration].skipped_tests.append(test_name)
        elif status == TestStatus.Not_run:
            self._failed = True
            self.iterations_info[iteration].not_run_tests.append(test_name)
        elif status == TestStatus.Failed:
            self._failed = True
            self.iterations_info[iteration].failed_tests.append(test_name)
        elif status == TestStatus.Unexpected_pass:
            self._failed = True
            self.iterations_info[iteration].unexpected_pass.append(test_name)
        elif status == TestStatus.Expected_failure:
            self.iterations_info[iteration].expected_failures.append(test_name)
        else:
            self.iterations_info[iteration].successful_tests.append(test_name)
        self.results[self._test_result_key(test_name, iteration)] = result

    def test_result(self, test_name: str, iteration: int) -> TestResult:
        return self.results[self._test_result_key(test_name, iteration)]

    @property
    def failed(self) -> bool:
        return self._failed

    def iter_info(self, iteration: int) -> IterInfo:
        return self.iterations_info[iteration]
