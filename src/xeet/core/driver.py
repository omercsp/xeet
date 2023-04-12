from . import RuntimeInfo, XeetSettings, TestsCriteria, XeetRunSettings
from .result import (IterationResult, TestResult, TestPrimaryStatus, TestSecondaryStatus, RunResult,
                     TestStatus, time_result)
from .conf import xeet_conf
from .event_logger import EventLogger
from .test import TestModel, Test
from xeet.log import logging_enabled
from xeet.common import pydantic_errmsg
from pydantic import ValidationError
from functools import cache, cached_property


_INIT_ERR_STTS = TestStatus(TestPrimaryStatus.NotRun, TestSecondaryStatus.InitErr)


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
        self.tests: list[Test] = list()
        self.test_by_name: dict[str, Test] = dict()
        self.test_by_group: dict[str, list[Test]] = dict()

        for index, d in enumerate(self.conf.descs()):
            model = self._test_model(d)
            test = Test(model, self.rti, index)
            self.tests.append(test)
            self.test_by_name[test.name] = test
            for group in model.groups:
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
        run_res = RunResult(run_settings.iterations, run_settings.criteria)
        self.rti.set_run_settings(run_settings)
        tests = self.fetch_tests(run_settings.criteria)
        run_res.set_start_time()
        self.rti.notifier.on_run_start(run_res, tests)
        for iter_n in range(self.rti.iterations):
            self._run_iter(tests, run_res.iter_results[iter_n])
        run_res.set_end_time()
        self.rti.notifier.on_run_end()
        return run_res

    def fetch_tests(self, criteria: TestsCriteria, setup: bool = False,
                    init_phases: bool = False) -> list[Test]:
        tests: dict[str, Test] = dict()  # Use dict to avoid duplicates. Dict also preserves order.
        if not criteria.names and not criteria.fuzzy_names and not criteria.include_groups:
            tests = {test.name: test for test in self.tests}
        else:
            for name in criteria.names:
                if name in self.test_by_name:
                    tests[name] = self.test_by_name[name]
            for fuzzy in criteria.fuzzy_names:
                for test in self.tests:
                    if fuzzy in test.name:
                        tests[test.name] = test
        for group in criteria.include_groups:
            tests.update({test.name: test for test in self.test_by_group.get(group, [])})

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
        if not criteria.hidden_tests:
            for name, test in tests.items():
                if test.model.abstract:
                    remove.add(name)
            for name in remove:
                tests.pop(name, None)

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
    def _run_iter(self, tests: list[Test], iter_res: IterationResult) -> IterationResult:
        self.rti.set_iteration(iter_res.iter_n)
        self.rti.notifier.on_iteration_start(iter_res)
        for test in tests:
            self.rti.notifier.on_test_start(test=test)
            if test.error:
                test_res = TestResult(test=test, status=_INIT_ERR_STTS, status_reason=test.error)
            else:
                test_res = test.run()
            iter_res.add_test_result(test.name, test_res)
            self.rti.notifier.on_test_end(test_res)
        self.rti.notifier.on_iteration_end()
        return iter_res


@cache
def xeet_driver(settings: XeetSettings) -> _XeetDriver:
    return _XeetDriver(settings)
