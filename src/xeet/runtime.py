from xeet.xtest import (XTEST_NOT_RUN, XTEST_FAILED, XTEST_SKIPPED, XTEST_EXPECTED_FAILURE,
                        XTEST_UNEXPECTED_PASS)


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
        self.__failed = False

    def add_test_result(self, test_name: str, iteration: int, result: int) -> None:
        if result == XTEST_SKIPPED:
            self.iterations_info[iteration].skipped_tests.append(test_name)
        elif result == XTEST_NOT_RUN:
            self.__failed = True
            self.iterations_info[iteration].not_run_tests.append(test_name)
        elif result == XTEST_FAILED:
            self.__failed = True
            self.iterations_info[iteration].failed_tests.append(test_name)
        elif result == XTEST_UNEXPECTED_PASS:
            self.__failed = True
            self.iterations_info[iteration].unexpected_pass.append(test_name)
        elif result == XTEST_EXPECTED_FAILURE:
            self.iterations_info[iteration].expected_failures.append(test_name)
        else:
            self.iterations_info[iteration].successful_tests.append(test_name)

    @property
    def failed(self) -> bool:
        return self.__failed

    def iter_info(self, iteration: int) -> IterInfo:
        return self.iterations_info[iteration]
