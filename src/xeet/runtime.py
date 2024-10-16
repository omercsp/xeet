from xeet.xtest import TestStatus, TestResult


class RunInfo(object):
    def __init__(self, iterations: int) -> None:
        self.iterations: int = iterations
        self.iterations_info = [{s: [] for s in TestStatus} for _ in range(iterations)]
        self._failed = False
        self.results = {}

    def _test_result_key(self, test_name: str, iteration: int) -> str:
        return f"{test_name}_{iteration}"

    def add_test_result(self, test_name: str, iteration: int, result: TestResult) -> None:
        self.iterations_info[iteration][result.status].append(test_name)
        self.results[self._test_result_key(test_name, iteration)] = result

    def test_result(self, test_name: str, iteration: int) -> TestResult:
        return self.results[self._test_result_key(test_name, iteration)]

    @property
    def failed(self) -> bool:
        return self._failed
