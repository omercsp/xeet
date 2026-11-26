from . import RuntimeInfo, XeetSettings, TestsCriteria, XeetRunSettings
from .result import (IterationResult, TestResult, TestPrimaryStatus, TestSecondaryStatus, RunResult,
                     MtrxResult, TestStatus, FixtureResult, time_result)
from .conf import xeet_conf
from .event_logger import EventLogger
from .test import TestModel, Test
from .fixture import Fixture, FIXTURES_SETTINGS_KEY
from .matrix import Matrix
from xeet.log import logging_enabled
from xeet.common import pydantic_errmsg
from pydantic import ValidationError
from .events import EventNotifier
from xeet import XeetException
from xeet.log import log_info, log_error
from threading import Thread, Event, Condition, RLock
from signal import signal, SIGINT
from functools import cache, cached_property
from typing import Callable
from random import shuffle
import logging
import os


_INIT_ERR_STTS = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr)
_FIXTURE_ERR_STTS = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.FixtureErr)


#  A run wide abort request, shared by the driver, the tests pool and the runners. The first
#  request wins, and its reason is kept. The lock is reentrant since set() can be called from a
#  signal handler, which may interrupt another set() call on the main thread.
class _RunAbort:
    def __init__(self) -> None:
        self._event = Event()
        self._lock = RLock()
        self.reason = ""

    #  Returns True only for the call that actually requested the abort
    def set(self, reason: str) -> bool:
        with self._lock:
            if self._event.is_set():
                return False
            self.reason = reason
            self._event.set()
            return True

    def is_set(self) -> bool:
        return self._event.is_set()


class _TestsPool:
    def __init__(self, tests: list[Test], threads: int, abort: _RunAbort) -> None:
        self._base_tests = tests
        self.threads = threads
        self._tests: list[Test] = []
        self.condition = Condition()
        self.abort = abort
        self.reset(randomize=False)
        self.runner_id_str = ""
        self.info: Callable = log_info
        #  Tests that can't run because a fixture they require failed, mapped to the reason
        self.blocked: dict[str, str] = {}

    #  Wakes up runners waiting for a test. Must be called after the abort was set.
    def stop(self) -> None:
        with self.condition:
            self.condition.notify_all()

    def next_test(self, info: Callable) -> Test | None:
        self.info = info
        with self.condition:
            while True:
                if self.abort.is_set():
                    return None
                test, busy = self._next_test()
                if busy:
                    self.info(f"no obtainable tests, waiting")
                    self.condition.wait()
                    self.info(f"woke up")
                    continue
                return test

    #  returns a tuple of test and a boolean indicating if there are no tests to run
    #  in case there are tests but they are busy, the return value is (None, True),
    #  meaning not current test is available but there are tests to run
    def _next_test(self) -> tuple[Test | None, bool]:
        if len(self._tests) == 0:
            return None, False
        for i, test in enumerate(self._tests):
            self.info(f"Trying to get test '{test.name}'")
            try:
                #  if test.error is set, it means that the test is not runnable
                #  and should be skipped. No need to check for resources.
                if not test.error and test.name not in self.blocked and \
                        not test.obtain_resources():
                    self.info(f"resources not available for '{test.name}'")
                    continue
                if i > 0:
                    busy_tests = self._tests[0:i]
                    remaining = self._tests[i + 1:]
                    if len(remaining) < self.threads:
                        self._tests = remaining + busy_tests
                    else:
                        self._tests = remaining[0:self.threads] + busy_tests + \
                            remaining[self.threads:]
                else:
                    self._tests.pop(0)
                self.info(f"got '{test.name}'")
                return test, False
            except XeetException as e:
                self.info(f"Error occurred getting test '{test.name}': {e}")
                test.error = str(e)
                self._tests.pop(i)
                return test, False  # return the test with error, will become a runtime error
        return None, True

    def release_test(self, test: Test) -> None:
        with self.condition:
            test.release_resources()
            self.condition.notify_all()

    def insert(self, test: Test) -> None:
        if len(self._tests) < self.threads:
            self._tests.append(test)
        else:
            self._tests.insert(self.threads, test)

    def reset(self, randomize: bool) -> None:
        self._tests = self._base_tests.copy()
        if randomize:
            shuffle(self._tests)


class _TestRunner(Thread):
    def __init__(self, index: int, pool: _TestsPool, notifier: EventNotifier,
                 mtrx_result: MtrxResult) -> None:
        super().__init__()
        self.pool = pool
        self.notifier = notifier
        self.mtrx_res = mtrx_result
        self.runner_id = index
        self.error: XeetException | None = None
        self.test: Test | None = None

    def info(self, *args, **kwargs) -> None:
        self.notifier.on_run_message(f"runner#{self.runner_id}:", *args, **kwargs)

    def run(self) -> None:
        while True:
            if self.pool.abort.is_set():
                self.info(f"stopping")
                break
            self.test = self.pool.next_test(self.info)
            if self.test is None:
                self.info("No more tests, goodbye")
                break
            #  An abort requested after the test was handed out may have missed it, as it
            #  wasn't yet assigned to the runner.
            if self.pool.abort.is_set():
                self.info(f"aborted before starting test '{self.test.name}'")
                self.pool.release_test(self.test)
                break
            self.notifier.on_test_start(test=self.test)
            try:
                test_res = self._run_test()
            except XeetException as e:
                self.info(f"Error occurred during test '{self.test.name}': {e}")
                self.error = e
                #  _TestRunner.stop_all()
                break
            finally:
                self.pool.release_test(self.test)

            self.mtrx_res.add_test_result(self.test.name, test_res)
            self.notifier.on_test_end(test_res)

    def stop(self) -> None:
        if self.test:
            self.info("stopping test")
            self.test.stop()

    def _run_test(self) -> TestResult:
        assert self.test is not None
        self.test.build_steps()
        if self.test.error:
            return TestResult(test=self.test, status=_INIT_ERR_STTS, status_reason=self.test.error)
        blocked_reason = self.pool.blocked.get(self.test.name)
        if blocked_reason:
            return TestResult(test=self.test, status=_FIXTURE_ERR_STTS,
                              status_reason=blocked_reason)

        return self.test.run()


class _XeetDriver:
    def __init__(self, settings: XeetSettings) -> None:
        self.rti = RuntimeInfo()
        if logging_enabled():
            self.rti.add_run_reporter(EventLogger())
        for reporter in settings.reporters:
            self.rti.add_run_reporter(reporter)
        self.rti.notifier.on_init()

        self.conf = xeet_conf(settings.file_path, self.rti.xvars)
        self.rti.notifier.on_conf_load()
        self.rti.set_config_data(
            xeet_file_path=self.conf.file_path,
            defs_dict=self.conf.model.model_dump(by_alias=True),
            variables=self.conf.model.variables
        )

        for name, resources in self.conf.model.resources.items():
            self.rti.add_resource_pool(name, resources)

        self.tests: list[Test] = list()
        self.test_by_name: dict[str, Test] = dict()
        self.test_by_group: dict[str, list[Test]] = dict()
        self.matrix = Matrix(self.conf.model.matrix)
        self.rti.set_matrix(self.matrix)

        self.pool: _TestsPool = None  # type: ignore
        self.abort: _RunAbort = None  # type: ignore
        self.runners: list[_TestRunner] = []

        self.fixtures: dict[str, Fixture] = {}  # Fixtures built so far, by name
        self.run_fixtures: list[Fixture] = []  # Fixtures required by the run, in setup order
        self.fixture_users: dict[str, list[str]] = {}  # Fixture name -> names of requiring tests
        self.curr_fixture: Fixture | None = None
        self.in_teardowns = False
        self.skip_teardowns = False

        index = 0
        for d in self.conf.descs():
            model = self._test_model(d)
            test = Test(model, self.rti, index)
            self._add_test(test)
            index += 1
            if not model.matrix or test.error:
                continue
            matrix = Matrix(model.matrix)
            if not matrix.prmttns_count:
                self.rti.notifier.on_run_message(
                    f"Test '{model.name}' has no permutations, skipping")
                continue
            for prmttn_index, prmttn in enumerate(matrix.permutations()):
                test_prmmtn_model = model.model_copy(deep=True)
                test_prmmtn_model.name = f"{model.name}:{prmttn_index}"
                test_prmmtn_model.prmttn = prmttn
                test_prmmtn_model.matrix = {}
                prmttn_test = Test(test_prmmtn_model, self.rti, index)
                test.prmmtn_tests.append(prmttn_test)
                self._add_test(prmttn_test)
                index += 1

    def _add_test(self, test: Test) -> None:
        self.tests.append(test)
        self.test_by_name[test.name] = test
        for group in test.model.groups:
            if group not in self.test_by_group:
                self.test_by_group[group] = list()
            self.test_by_group[group].append(test)

    @cached_property
    def all_test_names(self) -> list[str]:
        return list(self.test_by_name.keys())

    @cached_property
    def all_groups(self) -> list[str]:
        return list(self.test_by_group.keys())

    def run(self, run_settings: XeetRunSettings) -> RunResult:
        run_res = RunResult(run_settings.iterations,  matrix_count=self.matrix.prmttns_count,
                            criteria=run_settings.criteria)
        self.rti.set_run_settings(run_settings)
        tests = self.fetch_tests(run_settings.criteria)
        self.run_fixtures = self._required_fixtures(tests)
        self.curr_fixture = None
        self.in_teardowns = False
        self.skip_teardowns = False
        self.abort = _RunAbort()
        self.pool = _TestsPool(tests, run_settings.jobs, self.abort)
        self.threads = run_settings.jobs
        self.runners: list[_TestRunner] = []
        run_res.set_start_time()
        self.rti.notifier.on_run_start(run_res, tests, self.matrix, self.threads,
                                       [f.name for f in self.run_fixtures])
        prev_handler = signal(SIGINT, self._stop_runners)
        completed = False
        try:
            for iter_n in range(self.rti.iterations):
                if self.abort.is_set():
                    break
                self._run_iter(run_res.iter_results[iter_n], run_settings)
            completed = True
        finally:
            signal(SIGINT, prev_handler)
            run_res.set_end_time()
            try:
                self.rti.notifier.on_run_end()
            except Exception as e:
                #  Don't let a reporter failure hide the error that ended the run
                if completed:
                    raise
                log_error(f"error ending run - {e}")
        return run_res

    #  Returns a tuple of (is a permutation, parent test, permutation index)
    def _prmttn_info(self, name: str) -> tuple[bool, str, int]:
        parts = name.split(":")
        if len(parts) != 2:
            return False, name, -1
        try:
            prmttn_index = int(parts[1])
        except ValueError:
            return False, name, -1
        return True, parts[0], prmttn_index

    def fetch_tests(self, criteria: TestsCriteria) -> list[Test]:
        tests: dict[str, Test] = dict()  # Use dict to avoid duplicates. Dict also preserves order.
        explictly_added_permutation_tests = set()
        if not criteria.names and not criteria.fuzzy_names and not criteria.include_groups:
            tests = {test.name: test for test in self.tests}
        else:
            for name in criteria.names:
                is_prmmt_name, prmttn_base, prmttn_index = self._prmttn_info(name)
                if is_prmmt_name:
                    if prmttn_base not in self.test_by_name:
                        continue
                    mtrix_test = self.test_by_name[prmttn_base]
                    if not mtrix_test.prmmtn_tests or prmttn_index >= len(mtrix_test.prmmtn_tests):
                        continue
                    tests[name] = mtrix_test.prmmtn_tests[prmttn_index]
                    explictly_added_permutation_tests.add(name)
                elif name in self.test_by_name:
                    tests[name] = self.test_by_name[name]
            for fuzzy in criteria.fuzzy_names:
                for test in self.tests:
                    if fuzzy in test.name:
                        tests[test.name] = test
            for group in criteria.include_groups:
                tests.update({test.name: test for test in self.test_by_group.get(group, [])})

        if criteria.implicit_prmttn_tests:
            mtrx_tests = [test for test in tests.values()
                          if test.model.matrix and not test.model.abstract]
            for mtrx_test in mtrx_tests:
                for prmttn_test in mtrx_test.prmmtn_tests:
                    tests[prmttn_test.name] = tests.get(prmttn_test.name, prmttn_test)

        #  Handle exclusions
        for name in criteria.exclude_names:
            tests.pop(name, None)

        for fuzzy in criteria.fuzzy_exclude_names:
            for test_name in list(tests.keys()):
                if fuzzy in test_name:
                    tests.pop(test_name, None)

        for group in criteria.exclude_groups:
            for test in self.test_by_group.get(group, []):
                tests.pop(test.name, None)

        remove = set()
        for group in criteria.require_groups:
            for name, test in tests.items():
                if group not in test.model.groups:
                    remove.add(name)
        if not criteria.abstract_tests:
            for name, test in tests.items():
                if test.model.abstract:
                    remove.add(name)

        if not criteria.matrix_tests:
            for name, test in tests.items():
                if test.model.matrix:
                    remove.add(name)

        if not criteria.implicit_prmttn_tests:
            for name, test in tests.items():
                if test.is_permutation and name not in explictly_added_permutation_tests:
                    remove.add(name)

        for name in remove:
            tests.pop(name, None)
        ret = [test for test in tests.values()]
        ret.sort(key=lambda t: t.index)
        return ret

    def _test_model(self, desc: dict, inherited: set[str] | None = None) -> TestModel:
        name = desc.get("name")
        if not name:
            desc = {"name": "<Unknown>", "error": "Test has no name"}
            return TestModel(**desc)

        if inherited is None:
            inherited = set()

        if name in self.test_by_name:
            return self.test_by_name[name].model

        try:
            ret = TestModel(**desc)
        except ValidationError as e:
            err = pydantic_errmsg(e)
            groups = desc.get("groups", [])
            desc = {"name": "dummy", "error": err}
            ret = TestModel(**desc)
            #  Override the dummy name and groups with the real ones. Work around the pydanitc
            #  XeetToken enforcement that requires them to be a valid XeetToken.
            ret.name = name
            ret.groups = desc.get("groups", groups)
            return ret

        base_name = ret.base
        if not base_name:
            return ret
        if base_name in inherited:
            desc = {"name": name, "error": f"Inheritance loop detected for '{base_name}'"}
            return TestModel(**desc)
        inherited.add(name)
        base_desc = self.conf.test_desc(base_name)
        if not base_desc:
            desc = {"name": name, "error": f"No such base test '{base_name}'"}
            return TestModel(**desc)
        base_model = self._test_model(base_desc, inherited)
        if base_model.error:
            ret.error = f"Base test '{base_name}' error: {base_model.error}"
            return ret
        ret.set_parent(base_model)
        return ret

    @time_result
    def _run_iter(self, iter_res: IterationResult, run_settings: XeetRunSettings
                  ) -> IterationResult:
        self.rti.set_iteration(iter_res.iter_n)
        self.rti.notifier.on_iteration_start(iter_res)
        for mtrx_i, mtrx_prmmtn in enumerate(self.matrix.permutations()):
            if self.abort.is_set():
                break
            if (run_settings.criteria.prmttn_idxs_inc and mtrx_i not in
                run_settings.criteria.prmttn_idxs_inc) or \
                (run_settings.criteria.prmttn_idxs_exc and mtrx_i in
                 run_settings.criteria.prmttn_idxs_exc):
                continue
            self.pool.reset(run_settings.randomize)
            self.rti.set_matrix_prmttn(mtrx_i, mtrx_prmmtn)
            mtrx_res = iter_res.add_mtrx_res(mtrx_prmmtn, mtrx_i)
            self.rti.notifier.on_matrix_start(mtrx_prmmtn, mtrx_res)

            mtrx_res.set_start_time()
            activated: list[tuple[Fixture, FixtureResult]] = []
            try:
                self.runners = []
                self._setup_fixtures(mtrx_res, activated)
                self.runners = [_TestRunner(i, self.pool, self.rti.notifier, mtrx_res) for i in
                                range(self.threads)]
                for runner in self.runners:
                    runner.start()
                for runner in self.runners:
                    runner.join()
            finally:
                self._teardown_fixtures(activated)
            mtrx_res.set_end_time()
            first_error = next((runner.error for runner in self.runners if runner.error), None)
            if first_error:
                self.rti.notifier.on_run_message(
                    f"Error occurred during iteration {iter_res.iter_n}: {first_error}")
                raise first_error
            self.rti.notifier.on_matrix_end()
        self.rti.notifier.on_iteration_end()
        return iter_res

    #  The first interrupt stops the tests and the fixture setup in progress, then the activated
    #  fixtures are torn down. Another interrupt during the teardowns skips the remaining ones.
    def _stop_runners(self, *_, **__) -> None:
        if not self.abort.set("Interrupted by user"):
            self._skip_teardowns()
            return
        self.pool.stop()
        for runner in self.runners:
            runner.stop()
        if self.curr_fixture and not self.in_teardowns:
            self.curr_fixture.stop()

    def _skip_teardowns(self) -> None:
        if not self.in_teardowns or self.skip_teardowns:
            return
        self.skip_teardowns = True
        if self.curr_fixture:
            self.curr_fixture.stop()

    @property
    def fixture_names(self) -> list[str]:
        return list(self.conf.model.settings.get(FIXTURES_SETTINGS_KEY, {}).keys())

    #  Returns the named fixture, or None if it isn't defined. Fixtures are built on first use, so
    #  errors in unused fixtures don't affect the run.
    def fixture(self, name: str) -> Fixture | None:
        if name in self.fixtures:
            return self.fixtures[name]
        descs = self.conf.model.settings.get(FIXTURES_SETTINGS_KEY, {})
        if name not in descs:
            return None
        fixture = Fixture(name, descs[name], self.rti)
        self.fixtures[name] = fixture
        return fixture

    #  Only tests that are going to run require their fixtures. Skipped tests, or tests that
    #  can't run on this platform, don't.
    @staticmethod
    def _requires_fixtures(test: Test) -> bool:
        if test.error or test.model.skip:
            return False
        platforms = test.model.platform_list()
        return not platforms or os.name in platforms

    #  Returns the fixtures required by the given tests, in definition order. Raises an exception
    #  if a required fixture isn't defined or is invalid.
    def _required_fixtures(self, tests: list[Test]) -> list[Fixture]:
        self.fixture_users = {}
        for test in tests:
            if not self._requires_fixtures(test):
                continue
            for name in test.model.fixture_list():
                self.fixture_users.setdefault(name, []).append(test.name)

        defined = self.fixture_names
        undefined = [name for name in self.fixture_users if name not in defined]
        if undefined:
            details = ", ".join(f"'{name}' (required by {', '.join(self.fixture_users[name])})"
                                for name in undefined)
            raise XeetException(f"Undefined fixtures: {details}")

        ret = []
        for name in defined:
            if name not in self.fixture_users:
                continue
            fixture = self.fixture(name)
            assert fixture is not None
            if fixture.error:
                raise XeetException(f"Fixture '{name}' error: {fixture.error}")
            ret.append(fixture)
        return ret

    #  Sets up the fixtures required by the run, in order. A fixture is activated (its setup is
    #  attempted) only if some test that requires it can still run. A failed setup blocks the
    #  tests that require the fixture.
    def _setup_fixtures(self, mtrx_res: MtrxResult,
                        activated: list[tuple[Fixture, FixtureResult]]) -> None:
        self.pool.blocked = {}
        if not self.rti.fixtures_enabled:
            return
        notifier = self.rti.notifier
        for fixture in self.run_fixtures:
            fixture_res = FixtureResult(name=fixture.name)
            fixture_res.set_start_time()
            mtrx_res.add_fixture_result(fixture_res)
            users = [name for name in self.fixture_users[fixture.name]
                     if name not in self.pool.blocked]
            if self.abort.is_set():
                fixture_res.skip_reason = "Run aborted"
            elif not users:
                fixture_res.skip_reason = "No runnable test requires it"
            if fixture_res.skipped:
                fixture_res.set_end_time()
                notifier.on_fixture_setup_end(fixture_res)
                continue

            activated.append((fixture, fixture_res))
            fixture.prepare()
            if not fixture.setup_phase.steps:
                continue
            self.curr_fixture = fixture
            notifier.on_fixture_setup_start(fixture)
            fixture.run_setup(fixture_res)
            self.curr_fixture = None
            notifier.on_fixture_setup_end(fixture_res)
            if not fixture_res.setup_failed:
                continue
            reason = f"Fixture '{fixture.name}' setup failed: {fixture_res.setup_error_summary()}"
            for name in users:
                self.pool.blocked[name] = reason

    #  Tears down the activated fixtures, in reverse activation order
    def _teardown_fixtures(self, activated: list[tuple[Fixture, FixtureResult]]) -> None:
        notifier = self.rti.notifier
        self.in_teardowns = True
        skipped = []
        try:
            for fixture, fixture_res in reversed(activated):
                if not fixture.teardown_phase.steps:
                    fixture_res.set_end_time()
                    continue
                if self.skip_teardowns:
                    fixture_res.teardown_skip_reason = "Skipped by user interrupt"
                    fixture_res.set_end_time()
                    skipped.append(fixture.name)
                    notifier.on_fixture_teardown_end(fixture_res)
                    continue
                fixture.reset_stop()  # The fixture's setup might have been stopped
                self.curr_fixture = fixture
                notifier.on_fixture_teardown_start(fixture)
                fixture.run_teardown(fixture_res)
                self.curr_fixture = None
                fixture_res.set_end_time()
                notifier.on_fixture_teardown_end(fixture_res)
        finally:
            self.in_teardowns = False
            self.curr_fixture = None
        if skipped:
            notifier.on_run_message(f"Skipped fixtures teardowns: {', '.join(skipped)}",
                                    severity=logging.WARN)


@cache
def xeet_driver(settings: XeetSettings) -> _XeetDriver:
    return _XeetDriver(settings)
