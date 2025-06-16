from . import RuntimeInfo, XeetSettings, TestsCriteria, XeetRunSettings
from .result import (IterationResult, TestResult, TestPrimaryStatus, TestSecondaryStatus, RunResult,
                     MtrxResult, TestStatus, time_result)
from .conf import xeet_conf
from .event_logger import EventLogger
from .test import TestModel, Test
from .matrix import Matrix
from xeet.log import logging_enabled
from xeet.common import pydantic_errmsg
from pydantic import ValidationError
from .events import EventNotifier
from .test import Test
from xeet import XeetException
from xeet.log import log_info
from threading import Thread, Event, Condition
from signal import signal, SIGINT
from functools import cache, cached_property
from typing import Callable
from random import shuffle


_INIT_ERR_STTS = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr)


class _TestsPool:
    def __init__(self, tests: list[Test], threads: int) -> None:
        self._base_tests = tests
        self.threads = threads
        self._tests: list[Test] = []
        self.condition = Condition()
        self.abort = Event()
        self.reset(randomize=False)
        self.runner_id_str = ""
        self.info: Callable = log_info

    def stop(self) -> None:
        self.abort.set()
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
                if not test.error and not test.obtain_resources():
                    self.info(f"resources not available for '{test.name}'")
                    continue
                if i > 0:
                    busy_tests = self._tests[0:i]
                    self._tests = self._tests[i:]
                    if len(self._tests) < self.threads:
                        self._tests.extend(busy_tests)
                    else:
                        self._tests = self._tests[0:self.threads] + busy_tests + \
                            self._tests[self.threads:]
                self.info(f"got '{test.name}'")
                return self._tests.pop(i), False
            except XeetException as e:
                self.info(f"Error occurred getting test '{test.name}': {e}")
                test.error = str(e)
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
    stop_event = Event()

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
            if self.stop_event.is_set():
                self.info(f"stopping")
                break
            self.test = self.pool.next_test(self.info)
            if self.test is None:
                self.info("No more tests, goodbye")
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
        if self.test.error:
            return TestResult(test=self.test, status=_INIT_ERR_STTS, status_reason=self.test.error)

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
        self.stop_event: Event = None  # type: ignore
        self.runners: list[_TestRunner] = []

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
                index += 1

    def _add_test(self, test: Test) -> None:
        self.tests.append(test)
        self.test_by_name[test.name] = test
        for group in test.model.groups:
            if group not in self.test_by_group:
                self.test_by_group[group] = list()
            self.test_by_group[group].append(test)

    @cached_property
    def all_named(self) -> list[str]:
        return list(self.test_by_name.keys())

    @cached_property
    def all_groups(self) -> list[str]:
        return list(self.test_by_group.keys())

    def run(self, run_settings: XeetRunSettings) -> RunResult:
        run_res = RunResult(run_settings.iterations,  matrix_count=self.matrix.prmttns_count,
                            criteria=run_settings.criteria)
        self.rti.set_run_settings(run_settings)
        tests = self.fetch_tests(run_settings.criteria)
        self.pool = _TestsPool(tests, run_settings.jobs)
        self.threads = run_settings.jobs
        self.runners: list[_TestRunner] = []
        self.stop_event = Event()
        run_res.set_start_time()
        self.rti.notifier.on_run_start(run_res, tests, self.matrix, self.threads)
        signal(SIGINT, self._stop_runners)
        for iter_n in range(self.rti.iterations):
            self._run_iter(run_res.iter_results[iter_n], run_settings)
        run_res.set_end_time()
        self.rti.notifier.on_run_end()
        return run_res

    #  Retuns a tuple of (is apremutaion, parent test, permutation index)
    def _prmttn_info(self, name: str) -> tuple[bool, str, int]:
        parts = name.split(":")
        if len(parts) != 2:
            return False, name, -1
        try:
            prmttn_index = int(parts[1])
        except ValueError:
            return False, name, -1
        return True, parts[0], prmttn_index

    def fetch_tests(self, criteria: TestsCriteria, setup: bool = False,
                    init_phases: bool = False) -> list[Test]:
        tests: dict[str, Test] = dict()  # Use dict to avoid duplicates. Dict also preserves order.
        if not criteria.names and not criteria.fuzzy_names and not criteria.include_groups:
            tests = {test.name: test for test in self.tests}
        else:
            for name in criteria.names:
                prmmt_name, prmttn_base, prmttn_index = self._prmttn_info(name)
                if prmmt_name:
                    if prmttn_base not in self.test_by_name:
                        continue
                    mtrix_test = self.test_by_name[prmttn_base]
                    if not mtrix_test.prmmtn_tests or prmttn_index > len(mtrix_test.prmmtn_tests):
                        continue
                    tests[name] = mtrix_test.prmmtn_tests[prmttn_index]
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

        for name in remove:
            tests.pop(name, None)
        ret = [test for test in tests.values()]
        ret.sort(key=lambda t: t.index)
        if setup:
            for test in ret:
                test.setup()
        elif init_phases:
            for test in ret:
                test.init_phases()
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
        ret.inherit(base_model)
        return ret

    @time_result
    def _run_iter(self, iter_res: IterationResult, run_settings: XeetRunSettings
                  ) -> IterationResult:
        self.rti.set_iteration(iter_res.iter_n)
        self.rti.notifier.on_iteration_start(iter_res)
        for mtrx_i, mtrx_prmmtn in enumerate(self.matrix.permutations()):
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
            self.runners = [_TestRunner(i, self.pool, self.rti.notifier, mtrx_res) for i in
                            range(self.threads)]
            for runner in self.runners:
                runner.start()
            for runner in self.runners:
                runner.join()
            mtrx_res.set_end_time()
            first_error = next((runner.error for runner in self.runners if runner.error), None)
            if first_error:
                self.rti.notifier.on_run_message(
                    f"Error occurred during iteration {iter_res.iter_n}: {first_error}")
                raise first_error
            self.rti.notifier.on_matrix_end()
        self.rti.notifier.on_iteration_end()
        return iter_res

    def _stop_runners(self, *_, **__) -> None:
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        for runner in self.runners:
            runner.stop()


@cache
def xeet_driver(settings: XeetSettings) -> _XeetDriver:
    return _XeetDriver(settings)
