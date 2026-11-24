from ut import *
from ut.ut_dummy_defs import *
from xeet.core.api import XeetRunSettings
from xeet.core import TestsCriteria
from xeet.core.driver import _RunAbort, _TestsPool, _TestRunner
from xeet.core.events import EventReporter
from xeet.core.result import MtrxResult, RunResult, TestResult
from xeet.core.test import Test
from threading import Event, Thread
from typing import Callable


_WAIT_TIMEOUT = 5


class _AbortReporter(EventReporter):
    def __init__(self) -> None:
        super().__init__()
        self.abort_func: Callable | None = None
        self.abort_on_end = ""
        self.iterations_started = 0
        self.mtrx_started = 0
        self.mtrx_ended = 0
        self.on_start: dict[str, Callable] = {}

    def on_iteration_start(self) -> None:
        self.iterations_started += 1

    def on_matrix_start(self) -> None:
        self.mtrx_started += 1

    def on_matrix_end(self) -> None:
        self.mtrx_ended += 1

    def on_test_start(self, test: Test) -> None:
        func = self.on_start.get(test.name)
        if func:
            func()

    def on_test_end(self, test_res: TestResult) -> None:
        assert self.abort_func is not None
        if test_res.test.name == self.abort_on_end:
            self.abort_func("Test abort")


def _add_tests(xut: XeetUnittest, count: int) -> list[str]:
    names = [f"test{i}" for i in range(count)]
    for name in names:
        xut.add_test(name, run=[DUMMY_OK_STEP_DESC])
    xut.save()
    return names


def _reporter(xut: XeetUnittest) -> _AbortReporter:
    driver = xut.driver()
    reporter = _AbortReporter()
    reporter.abort_func = driver._stop_runners
    driver.rti.add_run_reporter(reporter)
    return reporter


def _results(run_res: RunResult, iteration: int = 0, mtrx: int = 0) -> dict[str, TestResult]:
    return run_res.iter_results[iteration].mtrx_results[mtrx].results


def test_run_abort():
    abort = _RunAbort()
    assert not abort.is_set()
    assert abort.set("first")
    assert abort.is_set()
    assert not abort.set("second")
    assert abort.reason == "first"


def test_abort_stops_tests_handout(xut: XeetUnittest):
    names = _add_tests(xut, 3)
    reporter = _reporter(xut)
    reporter.abort_on_end = names[0]

    run_res = xut.driver().run(XeetRunSettings())
    assert list(_results(run_res).keys()) == [names[0]]
    assert xut.driver().abort.reason

    #  An abort doesn't leak into the next run
    reporter.abort_on_end = ""
    run_res = xut.driver().run(XeetRunSettings())
    assert sorted(_results(run_res).keys()) == names


def test_abort_stops_iterations(xut: XeetUnittest):
    names = _add_tests(xut, 2)
    reporter = _reporter(xut)
    reporter.abort_on_end = names[0]

    run_res = xut.driver().run(XeetRunSettings(iterations=3))
    assert list(_results(run_res, 0).keys()) == [names[0]]
    assert reporter.iterations_started == 1
    for i in (1, 2):
        assert run_res.iter_results[i].is_empty()


def test_abort_stops_matrix_permutations(xut: XeetUnittest):
    names = _add_tests(xut, 2)
    xut.add_matrix("mtrx", [1, 2, 3], save=True)
    reporter = _reporter(xut)
    reporter.abort_on_end = names[0]

    run_res = xut.driver().run(XeetRunSettings())
    assert len(run_res.iter_results[0].mtrx_results) == 1
    assert list(_results(run_res).keys()) == [names[0]]
    assert reporter.mtrx_started == 1
    assert reporter.mtrx_ended == 1


def test_abort_with_threads(xut: XeetUnittest):
    names = _add_tests(xut, 6)
    reporter = _reporter(xut)

    #  Both runners hold a test when the abort is requested, and no runner can go on to its next
    #  test before the abort is requested.
    second_started = Event()
    aborted = Event()

    def _first_start() -> None:
        assert second_started.wait(_WAIT_TIMEOUT)
        assert reporter.abort_func is not None
        reporter.abort_func("Test abort")
        aborted.set()

    def _second_start() -> None:
        second_started.set()
        assert aborted.wait(_WAIT_TIMEOUT)

    reporter.on_start = {names[0]: _first_start, names[1]: _second_start}
    run_res = xut.driver().run(XeetRunSettings(jobs=2))
    assert sorted(_results(run_res).keys()) == names[:2]


def test_abort_after_test_handout(xut: XeetUnittest):
    names = _add_tests(xut, 2)
    driver = xut.driver()
    abort = _RunAbort()
    pool = _TestsPool(driver.fetch_tests(TestsCriteria()), 1, abort)
    started: list[str] = []
    reporter = _AbortReporter()
    reporter.on_start = {name: lambda n=name: started.append(n) for name in names}
    driver.rti.add_run_reporter(reporter)

    #  The abort is requested right after the first test was handed out to the runner
    next_test = pool.next_test

    def _next_test(info: Callable) -> Test | None:
        test = next_test(info)
        abort.set("Test abort")
        return test

    pool.next_test = _next_test  # type: ignore
    mtrx_res = MtrxResult({}, 0)
    _TestRunner(0, pool, driver.rti.notifier, mtrx_res).run()
    assert started == []
    assert mtrx_res.is_empty()


class _BusyTest:
    def __init__(self, name: str) -> None:
        self.name = name
        self.error = ""

    def obtain_resources(self) -> bool:
        return False


def test_abort_wakes_waiting_runner():
    abort = _RunAbort()
    pool = _TestsPool([_BusyTest("busy")], 1, abort)  # type: ignore
    waiting = Event()
    ret: list[Test | None] = []

    def _info(msg: str, *_, **__) -> None:
        if "waiting" in msg:
            waiting.set()

    #  A daemon thread, so a lost wake-up fails the test instead of hanging the test process
    thread = Thread(target=lambda: ret.append(pool.next_test(_info)), daemon=True)
    thread.start()
    assert waiting.wait(_WAIT_TIMEOUT)
    abort.set("Test abort")
    pool.stop()
    thread.join(_WAIT_TIMEOUT)
    assert not thread.is_alive()
    assert ret == [None]
