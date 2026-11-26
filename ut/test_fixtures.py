from ut import *
from ut.ut_dummy_defs import *
from xeet import XeetException
from xeet.core import system_var_name
from xeet.core.events import EventReporter
from xeet.core.fixture import Fixture
from xeet.core.result import (FixtureResult, MtrxResult, RunResult, TestResult, TestPrimaryStatus,
                              TestSecondaryStatus)
from xeet.core.test import Test
from xeet.reporters import ConsoleDebugPrinter, ConsolePrinter
from rich.live import Live
from typing import Callable
import os


F0 = "f0"
F1 = "f1"
F2 = "f2"
F3 = "f3"

_SETUP = "setup"
_TEARDOWN = "teardown"
_TEST = "test"


def _ok_steps(value: str = "") -> list[dict]:
    return [gen_dummy_step_desc(dummy_val0=value)]


#  Records the order of the fixtures and tests events
class _Recorder(EventReporter):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, str]] = []
        self.on_setup_start: dict[str, Callable] = {}
        self.on_teardown_start: dict[str, Callable] = {}

    def on_fixture_setup_start(self, fixture: Fixture) -> None:
        func = self.on_setup_start.get(fixture.name)
        if func:
            func()

    def on_fixture_setup_end(self, fixture_res: FixtureResult) -> None:
        if not fixture_res.skipped:
            self.events.append((_SETUP, fixture_res.name))

    def on_fixture_teardown_start(self, fixture: Fixture) -> None:
        func = self.on_teardown_start.get(fixture.name)
        if func:
            func()

    def on_fixture_teardown_end(self, fixture_res: FixtureResult) -> None:
        if not fixture_res.teardown_skip_reason:
            self.events.append((_TEARDOWN, fixture_res.name))

    def on_test_end(self, test_res: TestResult) -> None:
        self.events.append((_TEST, test_res.test.name))

    def names(self, kind: str) -> list[str]:
        return [name for k, name in self.events if k == kind]


def _recorder(xut: XeetUnittest) -> _Recorder:
    ret = _Recorder()
    xut.driver().rti.add_run_reporter(ret)
    return ret


def _mtrx_res(run_res: RunResult, iteration: int = 0, mtrx: int = 0) -> MtrxResult:
    return run_res.iter_results[iteration].mtrx_results[mtrx]


def _fixture_res(run_res: RunResult, name: str, iteration: int = 0, mtrx: int = 0
                 ) -> FixtureResult:
    ret = _mtrx_res(run_res, iteration, mtrx).fixture_result(name)
    assert ret is not None
    return ret


def _test_res(run_res: RunResult, name: str) -> TestResult:
    return _mtrx_res(run_res).results[name]


def _assert_fixture_error(test_res: TestResult, fixture_name: str) -> None:
    assert test_res.status.primary == TestPrimaryStatus.NotRun
    assert test_res.status.secondary == TestSecondaryStatus.FixtureErr
    assert f"Fixture '{fixture_name}'" in test_res.status_reason
    assert test_res.status_reason in test_res.error_summary()


def test_fixtures_order(xut: XeetUnittest):
    for name in (F0, F1, F2):
        xut.add_fixture(name, setup=_ok_steps(), teardown=_ok_steps())
    xut.add_test(TEST0, fixtures=[F2, F0, F1], run=[DUMMY_OK_STEP_DESC])
    xut.add_test(TEST1, fixtures=[F1], run=[DUMMY_OK_STEP_DESC])
    xut.add_test(TEST2, run=[DUMMY_OK_STEP_DESC], save=True)
    recorder = _recorder(xut)

    xut.run_tests(jobs=3, randomize=True)
    assert recorder.names(_SETUP) == [F0, F1, F2]
    assert recorder.names(_TEARDOWN) == [F2, F1, F0]
    assert set(recorder.names(_TEST)) == {TEST0, TEST1, TEST2}
    #  All setups precede the tests, and all teardowns follow them
    kinds = [kind for kind, _ in recorder.events]
    assert kinds == [_SETUP] * 3 + [_TEST] * 3 + [_TEARDOWN] * 3


def test_fixtures_once_per_permutation(xut: XeetUnittest):
    xut.add_matrix("m", ["a", "b"])
    xut.add_fixture(F0, setup=_ok_steps("{m}"), teardown=_ok_steps("{m}"))
    for name in (TEST0, TEST1, TEST2):
        xut.add_test(name, fixtures=[F0], run=[DUMMY_OK_STEP_DESC])
    xut.save()
    recorder = _recorder(xut)

    run_res = xut.run_tests(iterations=3)
    assert recorder.names(_SETUP) == [F0] * 6
    assert recorder.names(_TEARDOWN) == [F0] * 6
    for iteration in range(3):
        for mtrx, value in enumerate(["a", "b"]):
            mtrx_res = _mtrx_res(run_res, iteration, mtrx)
            assert len(mtrx_res.fixture_results) == 1
            fixture_res = mtrx_res.fixture_results[0]
            assert fixture_res.setup_res.steps_results[0].dummy_val0 == value  # type: ignore
            assert fixture_res.teardown_res.steps_results[0].dummy_val0 == value  # type: ignore


def test_fixtures_of_running_tests_only(xut: XeetUnittest):
    other_platform = "nt" if os.name == "posix" else "posix"
    for name in (F0, F1, F2, F3):
        xut.add_fixture(name, setup=_ok_steps())
    xut.add_test(TEST0, fixtures=[F0], skip=True, run=[DUMMY_OK_STEP_DESC])
    xut.add_test(TEST1, fixtures=[F1], platforms=[other_platform], run=[DUMMY_OK_STEP_DESC])
    #  Undefined fixtures of tests that don't run are ignored
    xut.add_test(TEST2, fixtures=["undefined"], skip=True, run=[DUMMY_OK_STEP_DESC])
    xut.add_test(TEST3, fixtures=[F3], run=[DUMMY_OK_STEP_DESC], save=True)
    recorder = _recorder(xut)

    run_res = xut.run_tests()
    assert recorder.names(_SETUP) == [F3]
    assert [r.name for r in _mtrx_res(run_res).fixture_results] == [F3]
    assert _test_res(run_res, TEST3).status == PASSED_TEST_STTS


def test_fixtures_validation(xut: XeetUnittest):
    xut.add_fixture(F0, setup=_ok_steps(), reset=True)
    xut.add_test(TEST0, fixtures=[F0, "undefined0"], run=[DUMMY_OK_STEP_DESC])
    xut.add_test(TEST1, fixtures=["undefined1"], run=[DUMMY_OK_STEP_DESC], save=True)
    with pytest.raises(XeetException, match="undefined0.*undefined1"):
        xut.run_tests()

    #  A broken fixture fails the run only if it's required
    bad_descs = [
        {"setup": [{"type": "no_such_type"}]},
        {"setup": _ok_steps(), "no_such_field": 1},
        {},
        {"teardown": ["not a step"]},
        "not a fixture",
    ]
    for bad_desc in bad_descs:
        xut.add_fixture(F0, setup=_ok_steps(), reset=True)
        xut.settings["fixtures"][F1] = bad_desc
        xut.add_test(TEST0, fixtures=[F0], run=[DUMMY_OK_STEP_DESC], save=True)
        run_res = xut.run_tests()
        assert _test_res(run_res, TEST0).status == PASSED_TEST_STTS

        xut.add_test(TEST1, fixtures=[F1], run=[DUMMY_OK_STEP_DESC], save=True)
        with pytest.raises(XeetException, match=f"Fixture '{F1}' error"):
            xut.run_tests()

    xut.add_test(TEST0, fixtures=[F0, F0], run=[DUMMY_OK_STEP_DESC], reset=True, save=True)
    assert "unique" in xut.get_test(TEST0).error


def test_fixture_setup_failure(xut: XeetUnittest):
    xut.add_fixture(F0, setup=[DUMMY_FAILING_STEP_DESC, DUMMY_OK_STEP_DESC],
                    teardown=_ok_steps())
    xut.add_fixture(F1, setup=_ok_steps(), teardown=_ok_steps())
    xut.add_test(TEST0, fixtures=[F0, F1], run=[DUMMY_OK_STEP_DESC])
    xut.add_test(TEST1, fixtures=[F1], run=[DUMMY_OK_STEP_DESC])
    xut.add_test(TEST2, run=[DUMMY_OK_STEP_DESC], save=True)
    recorder = _recorder(xut)

    run_res = xut.run_tests()
    _assert_fixture_error(_test_res(run_res, TEST0), F0)
    assert _test_res(run_res, TEST1).status == PASSED_TEST_STTS
    assert _test_res(run_res, TEST2).status == PASSED_TEST_STTS
    assert run_res.not_run_tests
    assert not run_res.failed_tests

    f0_res = _fixture_res(run_res, F0)
    assert f0_res.setup_status == TestPrimaryStatus.Failed
    assert len(f0_res.setup_res.steps_results) == 1  # Setup stops on the first failure
    #  A failed setup is still torn down
    assert recorder.names(_TEARDOWN) == [F1, F0]
    assert f0_res.teardown_status == TestPrimaryStatus.Passed


def test_fixture_incomplete_setup(xut: XeetUnittest):
    xut.add_fixture(F0, setup=[DUMMY_INCOMPLETED_STEP_DESC])
    xut.add_test(TEST0, fixtures=[F0], run=[DUMMY_OK_STEP_DESC], save=True)
    run_res = xut.run_tests()
    _assert_fixture_error(_test_res(run_res, TEST0), F0)
    assert _fixture_res(run_res, F0).setup_status == TestPrimaryStatus.NotRun


def test_fixture_skipped_if_not_needed(xut: XeetUnittest):
    xut.add_fixture(F0, setup=[DUMMY_FAILING_STEP_DESC], teardown=_ok_steps())
    xut.add_fixture(F1, setup=_ok_steps(), teardown=_ok_steps())
    xut.add_fixture(F2, setup=_ok_steps(), teardown=_ok_steps())
    xut.add_test(TEST0, fixtures=[F0, F1, F2], run=[DUMMY_OK_STEP_DESC])
    xut.add_test(TEST1, fixtures=[F2], run=[DUMMY_OK_STEP_DESC], save=True)
    recorder = _recorder(xut)

    run_res = xut.run_tests()
    #  F1 is required only by a blocked test, so it's neither set up nor torn down
    assert recorder.names(_SETUP) == [F0, F2]
    assert recorder.names(_TEARDOWN) == [F2, F0]
    f1_res = _fixture_res(run_res, F1)
    assert f1_res.skipped
    assert f1_res.setup_status == TestPrimaryStatus.Skipped
    assert f1_res.teardown_status == TestPrimaryStatus.Skipped
    _assert_fixture_error(_test_res(run_res, TEST0), F0)
    assert _test_res(run_res, TEST1).status == PASSED_TEST_STTS


def test_fixture_test_variables(xut: XeetUnittest):
    for var in (system_var_name("TEST_NAME"), "test_var"):
        xut.add_fixture(F0, setup=_ok_steps(f"{{{var}}}"), teardown=_ok_steps(), reset=True)
        xut.add_test(TEST0, fixtures=[F0], variables={"test_var": 1}, run=[DUMMY_OK_STEP_DESC],
                     save=True)
        run_res = xut.run_tests()
        _assert_fixture_error(_test_res(run_res, TEST0), F0)
        f0_res = _fixture_res(run_res, F0)
        assert f0_res.setup_status == TestPrimaryStatus.NotRun
        assert var in f0_res.setup_error
        assert f0_res.teardown_status == TestPrimaryStatus.Passed


def test_fixture_teardown_failure(xut: XeetUnittest):
    xut.add_fixture(F0, setup=_ok_steps(), teardown=[DUMMY_FAILING_STEP_DESC, DUMMY_OK_STEP_DESC])
    xut.add_test(TEST0, fixtures=[F0], run=[DUMMY_OK_STEP_DESC], save=True)
    run_res = xut.run_tests()
    assert _test_res(run_res, TEST0).status == PASSED_TEST_STTS
    f0_res = _fixture_res(run_res, F0)
    #  Teardown steps run even if a previous one failed
    assert len(f0_res.teardown_res.steps_results) == 2
    assert f0_res.teardown_failed
    assert run_res.teardown_failed
    assert not run_res.failed_tests
    assert not run_res.not_run_tests


def test_fixture_teardown_only(xut: XeetUnittest):
    xut.add_fixture(F0, teardown=_ok_steps())
    xut.add_test(TEST0, fixtures=[F0], run=[DUMMY_OK_STEP_DESC], save=True)
    recorder = _recorder(xut)
    run_res = xut.run_tests()
    assert recorder.names(_SETUP) == []
    assert recorder.names(_TEARDOWN) == [F0]
    f0_res = _fixture_res(run_res, F0)
    assert f0_res.setup_status == TestPrimaryStatus.Undefined
    assert f0_res.teardown_status == TestPrimaryStatus.Passed


def test_fixtures_inheritance(xut: XeetUnittest):
    xut.add_fixture(F0, setup=_ok_steps())
    xut.add_fixture(F1, setup=_ok_steps())
    xut.add_test("base", abstract=True, fixtures=[F0], run=[DUMMY_OK_STEP_DESC])
    xut.add_test(TEST0, base="base")
    xut.add_test(TEST1, base="base", fixtures=[F1], save=True)
    assert xut.get_test(TEST0).model.fixture_list() == [F0]
    assert xut.get_test(TEST1).model.fixture_list() == [F1]

    recorder = _recorder(xut)
    xut.run_tests(names=[TEST0])
    assert recorder.names(_SETUP) == [F0]
    recorder.events.clear()
    xut.run_tests(names=[TEST1])
    assert recorder.names(_SETUP) == [F1]


def test_fixtures_include_order(xut: XeetUnittest):
    inc = ConfigTestWrapper("fixtures_inc.yaml")
    inc.add_fixture(F0, setup=_ok_steps("included"))
    inc.add_fixture(F1, setup=_ok_steps("included"), save=True)

    xut.add_include(inc.file_path)
    xut.add_fixture(F2, setup=_ok_steps("main"))
    xut.add_fixture(F0, setup=_ok_steps("main"))
    xut.add_test(TEST0, fixtures=[F2, F1, F0], run=[DUMMY_OK_STEP_DESC], save=True)
    recorder = _recorder(xut)

    run_res = xut.run_tests()
    #  Included fixtures first; an overriding fixture keeps its included position
    assert recorder.names(_SETUP) == [F0, F1, F2]
    f0_res = _fixture_res(run_res, F0)
    assert f0_res.setup_res.steps_results[0].dummy_val0 == "main"  # type: ignore


def test_fixtures_variables(xut: XeetUnittest):
    fixture_vars = "{XEET_FIXTURE_NAME}|{XEET_FIXTURE_DIR}"
    xut.add_fixture(F0, setup=_ok_steps(fixture_vars), teardown=_ok_steps(fixture_vars))
    xut.add_test(TEST0, fixtures=[F0], run=[gen_dummy_step_desc(dummy_val0="{XEET_FIXTURES_DIR}")],
                 save=True)
    run_res = xut.run_tests()
    f0_res = _fixture_res(run_res, F0)
    setup_value = f0_res.setup_res.steps_results[0].dummy_val0  # type: ignore
    teardown_value = f0_res.teardown_res.steps_results[0].dummy_val0  # type: ignore
    assert setup_value == teardown_value
    name, fixture_dir = setup_value.split("|")
    assert name == F0
    assert os.path.basename(fixture_dir) == F0
    test_value = _test_res(run_res, TEST0).main_res.steps_results[0].dummy_val0  # type: ignore
    assert test_value == os.path.dirname(fixture_dir)
    assert os.path.isdir(os.path.join(fixture_dir, "su0"))
    assert os.path.isdir(os.path.join(fixture_dir, "td0"))


def test_no_fixtures(xut: XeetUnittest):
    xut.add_fixture(F0, setup=[DUMMY_FAILING_STEP_DESC], teardown=_ok_steps())
    xut.add_test(TEST0, fixtures=[F0], run=[DUMMY_OK_STEP_DESC], save=True)
    recorder = _recorder(xut)
    run_res = xut.run_tests(fixtures=False)
    assert recorder.names(_SETUP) == []
    assert recorder.names(_TEARDOWN) == []
    assert _mtrx_res(run_res).fixture_results == []
    assert _test_res(run_res, TEST0).status == PASSED_TEST_STTS

    #  Fixtures are still validated
    xut.add_test(TEST1, fixtures=["undefined"], run=[DUMMY_OK_STEP_DESC], save=True)
    with pytest.raises(XeetException, match="undefined"):
        xut.run_tests(fixtures=False)


def test_fixtures_interrupt_during_setup(xut: XeetUnittest):
    xut.add_fixture(F0, setup=_ok_steps(), teardown=_ok_steps())
    xut.add_fixture(F1, setup=_ok_steps(), teardown=_ok_steps())
    xut.add_test(TEST0, fixtures=[F0, F1], run=[DUMMY_OK_STEP_DESC], save=True)
    recorder = _recorder(xut)
    driver = xut.driver()
    recorder.on_setup_start[F0] = driver._stop_runners

    run_res = xut.run_tests(iterations=2)
    f0_res = _fixture_res(run_res, F0)
    assert f0_res.setup_status == TestPrimaryStatus.NotRun
    assert not f0_res.setup_res.steps_results
    assert _fixture_res(run_res, F1).skip_reason == "Run aborted"
    assert _mtrx_res(run_res).results == {}
    #  The interrupted fixture is torn down, and the run stops
    assert recorder.names(_TEARDOWN) == [F0]
    assert run_res.iter_results[1].mtrx_results == []


def test_fixtures_interrupt_during_teardown(xut: XeetUnittest):
    for name in (F0, F1, F2):
        xut.add_fixture(name, setup=_ok_steps(), teardown=_ok_steps())
    xut.add_test(TEST0, fixtures=[F0, F1, F2], run=[DUMMY_OK_STEP_DESC], save=True)
    recorder = _recorder(xut)
    driver = xut.driver()

    #  The first interrupt during the teardowns doesn't stop them, the second one does
    def _interrupt_twice() -> None:
        driver._stop_runners()
        assert not driver.skip_teardowns
        driver._stop_runners()
        assert driver.skip_teardowns

    recorder.on_teardown_start[F1] = _interrupt_twice
    run_res = xut.run_tests()
    assert recorder.names(_TEARDOWN) == [F2, F1]
    assert _fixture_res(run_res, F2).teardown_status == TestPrimaryStatus.Passed
    f1_res = _fixture_res(run_res, F1)
    assert f1_res.teardown_status == TestPrimaryStatus.NotRun
    assert not f1_res.teardown_res.steps_results
    f0_res = _fixture_res(run_res, F0)
    assert f0_res.teardown_status == TestPrimaryStatus.Skipped
    assert f0_res.teardown_skip_reason
    assert _test_res(run_res, TEST0).status == PASSED_TEST_STTS


#  Make sure the reporters handle fixtures (printing is muted in unit tests)
def test_fixtures_reporters(xut: XeetUnittest):
    xut.add_fixture(F0, setup=_ok_steps(), teardown=[DUMMY_FAILING_STEP_DESC])
    xut.add_fixture(F1, setup=[DUMMY_FAILING_STEP_DESC], teardown=_ok_steps())
    xut.add_fixture(F2, setup=_ok_steps())
    xut.add_test(TEST0, fixtures=[F0, F1, F2], run=[DUMMY_OK_STEP_DESC])
    xut.add_test(TEST1, fixtures=[F0], run=[DUMMY_OK_STEP_DESC], save=True)
    rti = xut.driver().rti
    rti.add_run_reporter(ConsoleDebugPrinter())
    rti.add_run_reporter(ConsolePrinter(live=Live()))
    run_res = xut.run_tests()
    _assert_fixture_error(_test_res(run_res, TEST0), F1)
    assert _fixture_res(run_res, F2).skipped
    assert run_res.teardown_failed
