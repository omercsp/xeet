from ut import *
from ut.ut_dummy_defs import *
from xeet.core import TestsCriteria
from xeet.core.xeet_conf import (XeetModel, XeetIncludeLoopException, _XeetConf, xeet_conf,
                                 clear_conf_cache, BaseXeetSettings)
from xeet.core.test import StepsInheritType, TestModel
import os


_ALL_TESTS_CRIT = TestsCriteria()


def assert_dummy_descs_equal(res: dict, expected: dict) -> None:
    assert isinstance(res, dict)
    assert isinstance(expected, dict)
    for k, v in expected.items():
        assert k in res
        assert res[k] == v
    for k in res.keys():
        assert k in expected


def test_config_model_inclusion():
    CONF0 = "conf0.yaml"
    CONF1 = "conf1.yaml"
    CONF2 = "conf2.yaml"
    CONF3 = "conf3.yaml"
    CONF4 = "conf4.yaml"

    conf0 = ConfigTestWrapper(CONF0)
    root = os.path.dirname(conf0.file_path)
    d0_0 = conf0.add_test(TEST0, arg=1)
    conf0.add_var("var0", 0)
    conf0.add_setting("setting0", {"a": 0}, save=True)

    conf1 = ConfigTestWrapper(CONF1)
    conf1.add_include(conf0.file_path)
    d1_1 = conf1.add_test(TEST1, arg=2)
    conf1.add_var("var1", 1)
    conf1.add_setting("setting1", {"a": 1}, save=True)

    model = xeet_conf(BaseXeetSettings(conf1.file_path)).model
    assert isinstance(model, XeetModel)
    assert len(model.tests) == 2
    assert model.tests[0] == d0_0
    assert model.tests[1] == d1_1
    assert len(model.variables) == 2
    assert model.variables["var0"] == 0
    assert model.variables["var1"] == 1
    assert len(model.settings) == 2
    assert model.settings["setting0"] == {"a": 0}
    assert model.settings["setting1"] == {"a": 1}

    conf2 = ConfigTestWrapper(CONF2)
    conf2.add_include("{XEET_ROOT}/" + CONF1)
    d2_0 = conf2.add_test(TEST0, arg=30)
    d2_1 = conf2.add_test(TEST1, arg=40)
    d2_2 = conf2.add_test(TEST2, arg=50)  # new test
    conf2.save()
    model = xeet_conf(BaseXeetSettings(conf2.file_path)).model
    assert isinstance(model, XeetModel)
    assert len(model.tests) == 3
    assert model.tests[0] == d2_0
    assert model.tests[1] == d2_1
    assert model.tests[2] == d2_2

    conf3 = ConfigTestWrapper(CONF3)
    conf3.add_include(f"{root}/{CONF1}")
    d3_0 = conf3.add_test(TEST0, arg=31)
    d3_3 = conf3.add_test(TEST3, arg=41)
    d3_4 = conf3.add_test(TEST4, arg=51, save=True)
    #  model = xeet_conf(BaseXeetSettings(conf3.file_path)).model

    conf4 = ConfigTestWrapper(CONF4)
    conf4.add_include(f"{root}/{CONF2}")
    conf4.add_include(f"{root}/{CONF3}")
    d4_5 = conf4.add_test(TEST5, arg=62)
    conf4.save()

    model = xeet_conf(BaseXeetSettings(conf4.file_path)).model
    assert isinstance(model, XeetModel)
    assert len(model.tests) == 6
    assert model.tests_dict[TEST0] == d3_0
    assert model.tests_dict[TEST1] == d1_1
    assert model.tests_dict[TEST2] == d2_2
    assert model.tests_dict[TEST3] == d3_3
    assert model.tests_dict[TEST4] == d3_4
    assert model.tests_dict[TEST5] == d4_5
    assert model.settings["setting0"] == {"a": 0}
    assert model.settings["setting1"] == {"a": 1}


def test_inclusion_loop():
    CONF0 = "conf0.json"
    CONF1 = "conf1.json"
    CONF2 = "conf2.json"

    conf0 = ConfigTestWrapper(CONF0)
    conf0.add_include(conf0.file_path)
    conf0.save()

    with pytest.raises(XeetIncludeLoopException):
        xeet_conf(BaseXeetSettings(conf0.file_path))

    conf1 = ConfigTestWrapper(CONF1)
    conf1.add_include(conf0.file_path)
    conf1.save()
    with pytest.raises(XeetIncludeLoopException):
        xeet_conf(BaseXeetSettings(conf1.file_path))
    conf0.includes = [conf1.file_path]
    conf0.save()

    with pytest.raises(XeetIncludeLoopException):
        xeet_conf(BaseXeetSettings(conf1.file_path))

    conf2 = ConfigTestWrapper(CONF2)
    conf2.add_include(conf1.file_path)
    conf2.save()
    with pytest.raises(XeetIncludeLoopException):
        xeet_conf(BaseXeetSettings(conf2.file_path))

    conf0.includes = [conf2.file_path]
    conf0.save()
    with pytest.raises(XeetIncludeLoopException):
        xeet_conf(BaseXeetSettings(conf0.file_path))

    with pytest.raises(XeetIncludeLoopException):
        xeet_conf(BaseXeetSettings(conf1.file_path))

    with pytest.raises(XeetIncludeLoopException):
        xeet_conf(BaseXeetSettings(conf2.file_path))


def test_get_test_by_name():
    CONF0 = "conf0.yaml"
    conf0 = ConfigTestWrapper(CONF0)
    conf0.add_test(TEST0, reset=True)
    conf0.add_test(TEST1)
    conf0.add_test(TEST2)
    conf0.add_test(TEST3, save=True)

    xeet = xeet_conf(BaseXeetSettings(conf0.file_path))
    crit = TestsCriteria(names={TEST0}, hidden_tests=True)
    tests = xeet.get_tests(criteria=crit)
    assert len(tests) == 1
    assert tests[0].name == TEST0

    crit.names = set([TEST1])
    tests = xeet.get_tests(criteria=crit)
    assert len(tests) == 1
    assert tests[0].name == TEST1

    crit.names = set([TEST0, TEST3])
    tests = xeet.get_tests(criteria=crit)
    assert len(tests) == 2
    assert set([t.name for t in tests]) == set([TEST0, TEST3])


def test_get_test_by_group():
    CONF0 = "conf0.yaml"
    conf0 = ConfigTestWrapper(CONF0)
    conf0.add_test(TEST0, groups=[GROUP0], reset=True)
    conf0.add_test(TEST1, groups=[GROUP1])
    conf0.add_test(TEST2, groups=[GROUP2])
    conf0.add_test(TEST3, groups=[GROUP0, GROUP1], save=True)

    xeet = xeet_conf(BaseXeetSettings(conf0.file_path))
    crit = TestsCriteria(include_groups={GROUP0}, hidden_tests=True)
    tests = xeet.get_tests(criteria=crit)
    assert len(tests) == 2
    assert set([t.name for t in tests]) == set([TEST0, TEST3])

    crit.require_groups = set([GROUP1])
    tests = xeet.get_tests(criteria=crit)
    assert len(tests) == 1
    assert tests[0].name == TEST3

    crit.exclude_groups = set([GROUP1])
    tests = xeet.get_tests(criteria=crit)
    assert len(tests) == 0

    crit.require_groups.clear()
    tests = xeet.get_tests(criteria=crit)
    assert len(tests) == 1
    assert tests[0].name == TEST0

    crit.include_groups = set([GROUP2, GROUP1])
    tests = xeet.get_tests(criteria=crit)
    assert len(tests) == 1  # exclude group for group1 is still set
    assert tests[0].name == TEST2

    crit.exclude_groups.clear()
    tests = xeet.get_tests(criteria=crit)
    assert len(tests) == 3
    assert set([t.name for t in tests]) == set([TEST1, TEST2, TEST3])


def test_get_all_tests():
    CONF0 = "conf0.yaml"
    conf0 = ConfigTestWrapper(CONF0)
    conf0.add_test(TEST0, reset=True)
    conf0.add_test(TEST1)
    conf0.add_test(TEST2, save=True)

    xeet = xeet_conf(BaseXeetSettings(conf0.file_path))
    tests = xeet.get_tests(_ALL_TESTS_CRIT)
    assert set([t.name for t in tests]) == set([TEST0, TEST1, TEST2])

    clear_conf_cache()
    INC_CONF0 = "inc_conf0.yaml"
    included_conf_wrapper = ConfigTestWrapper(INC_CONF0)
    included_conf_wrapper.add_test(TEST2)
    included_conf_wrapper.add_test(TEST3)
    included_conf_wrapper.add_test(TEST4, save=True)

    conf0.add_include(INC_CONF0, save=True)

    xeet = xeet_conf(BaseXeetSettings(conf0.file_path))
    tests = xeet.get_tests(_ALL_TESTS_CRIT)
    assert set([t.name for t in tests]) == set([TEST0, TEST1, TEST2, TEST3, TEST4])

    clear_conf_cache()
    INC_CONF1 = "inc_conf1.yaml"
    included_conf_wrapper = ConfigTestWrapper(INC_CONF1)
    included_conf_wrapper.add_test(TEST5)
    included_conf_wrapper.add_test(TEST6)
    included_conf_wrapper.save()

    clear_conf_cache()
    conf0.add_include(INC_CONF1, save=True)

    xeet = xeet_conf(BaseXeetSettings(conf0.file_path))
    tests = xeet.get_tests(_ALL_TESTS_CRIT)
    assert set([t.name for t in tests]) == set([TEST0, TEST1, TEST2, TEST3, TEST4, TEST5, TEST6])


def test_get_hidden_tests():
    CONF0 = "conf0.yaml"
    conf0 = ConfigTestWrapper(CONF0)
    conf0.add_test(TEST0, reset=True)
    conf0.add_test(TEST1, abstract=True)
    conf0.add_test(TEST2, save=True)

    crit = TestsCriteria(hidden_tests=True)
    xeet = xeet_conf(BaseXeetSettings(conf0.file_path))
    tests = xeet.get_tests(criteria=crit)
    assert set([t.name for t in tests]) == set([TEST0, TEST1, TEST2])

    crit.hidden_tests = False
    tests = xeet.get_tests(criteria=crit)
    assert set([t.name for t in tests]) == set([TEST0, TEST2])


def test_step_lists_inheritance():
    def assert_step_desc_list_equal(steps: list[dict] | None, expected: list[dict] | None) -> None:
        if expected is None:
            assert steps is None
            return
        assert steps is not None
        assert len(steps) == len(expected)
        for step_desc, expected_step_desc in zip(steps, expected):
            assert_dummy_descs_equal(step_desc, expected_step_desc)

    def assert_test_model_steps(name: str, xeet: _XeetConf,
                                pre_run: list = list(), run: list = list(),
                                post_run: list = list()) -> None:
        desc = xeet.test_desc(name)
        assert desc is not None
        model = xeet._test_model(desc)
        assert isinstance(model, TestModel)
        assert_step_desc_list_equal(model.pre_run, pre_run)
        assert_step_desc_list_equal(model.run, run)
        assert_step_desc_list_equal(model.post_run, post_run)

    CONF0 = "conf0.yaml"
    conf0 = ConfigTestWrapper(CONF0)
    conf0.add_test(TEST0, run=[DUMMY_OK_STEP_DESC], reset=True)
    conf0.add_test(TEST1, pre_run=[DUMMY_OK_STEP_DESC], base=TEST0)
    conf0.add_test(TEST2, base=TEST1, run=[DUMMY_FAILING_STEP_DESC])
    conf0.add_test(TEST3, base=TEST0, run_inheritance=StepsInheritType.Append.value,
                   run=[DUMMY_FAILING_STEP_DESC])
    conf0.add_test(TEST4, base=TEST0, run_inheritance=StepsInheritType.Prepend.value,
                   run=[DUMMY_FAILING_STEP_DESC])
    conf0.add_test(TEST5, base=TEST1, run=[], post_run=[DUMMY_OK_STEP_DESC, DUMMY_OK_STEP_DESC])
    conf0.add_test(TEST6, base=TEST5, run=[DUMMY_FAILING_STEP_DESC],
                   run_inheritance=StepsInheritType.Append.value, save=True)

    xeet = xeet_conf(BaseXeetSettings(conf0.file_path))
    assert_test_model_steps(TEST0, xeet, run=[DUMMY_OK_STEP_DESC])
    assert_test_model_steps(TEST1, xeet,
                            pre_run=[DUMMY_OK_STEP_DESC], run=[DUMMY_OK_STEP_DESC])
    assert_test_model_steps(TEST2, xeet,
                            pre_run=[DUMMY_OK_STEP_DESC], run=[DUMMY_FAILING_STEP_DESC])
    assert_test_model_steps(TEST3, xeet, run=[DUMMY_OK_STEP_DESC, DUMMY_FAILING_STEP_DESC])
    assert_test_model_steps(TEST4, xeet, run=[DUMMY_FAILING_STEP_DESC, DUMMY_OK_STEP_DESC])
    assert_test_model_steps(TEST5, xeet, pre_run=[DUMMY_OK_STEP_DESC],
                            post_run=[DUMMY_OK_STEP_DESC, DUMMY_OK_STEP_DESC])
    assert_test_model_steps(TEST6, xeet, pre_run=[DUMMY_OK_STEP_DESC],
                            run=[DUMMY_FAILING_STEP_DESC],
                            post_run=[DUMMY_OK_STEP_DESC, DUMMY_OK_STEP_DESC])


def test_exclude_tests():
    CONF0 = "conf0.yaml"
    conf0 = ConfigTestWrapper(CONF0)
    conf0.add_test(TEST0, reset=True)
    conf0.add_test(TEST1)
    conf0.add_test(TEST2, save=True)

    xeet = xeet_conf(BaseXeetSettings(conf0.file_path))
    tests = xeet.get_tests(TestsCriteria(exclude_names={TEST0, TEST1}))
    assert len(tests) == 1
    assert tests[0].name == TEST2


def test_fuzzy_names():
    CONF0 = "conf0.yaml"
    conf0 = ConfigTestWrapper(CONF0)
    conf0.add_test(TEST0, reset=True)
    conf0.add_test(TEST1)
    conf0.add_test(TEST2)
    conf0.add_test("other", save=True)

    xeet = xeet_conf(BaseXeetSettings(conf0.file_path))
    tests = xeet.get_tests(TestsCriteria(fuzzy_names=["t1"]))
    assert set([t.name for t in tests]) == set([TEST1])

    tests = xeet.get_tests(TestsCriteria(fuzzy_names=["test"]))
    assert set([t.name for t in tests]) == set([TEST0, TEST1, TEST2])


def test_misc_test_filtering():
    CONF0 = "conf0.yaml"
    conf0 = ConfigTestWrapper(CONF0)
    conf0.add_test(TEST0, reset=True)
    conf0.add_test(TEST1, groups=[GROUP0])
    conf0.add_test(TEST2, groups=[GROUP1])
    conf0.add_test(TEST3, groups=[GROUP0, GROUP1], save=True)

    xeet = xeet_conf(BaseXeetSettings(conf0.file_path))
    tests = xeet.get_tests(TestsCriteria(include_groups={GROUP0}, exclude_groups={GROUP1}))
    assert len(tests) == 1
    assert tests[0].name == TEST1

    tests = xeet.get_tests(TestsCriteria(include_groups={GROUP1}, names={TEST0}))
    assert len(tests) == 3
    assert set([t.name for t in tests]) == set([TEST0, TEST2, TEST3])

    tests = xeet.get_tests(TestsCriteria(include_groups={GROUP1}, fuzzy_exclude_names={"t3"}))
    assert len(tests) == 1
    assert tests[0].name == TEST2

    tests = xeet.get_tests(TestsCriteria(require_groups={GROUP0, GROUP1},
                                         exclude_names={TEST3}))
    assert len(tests) == 0


def test_get_groups():
    CONF0 = "conf0.yaml"
    conf0 = ConfigTestWrapper(CONF0)
    conf0.add_test(TEST0, groups=[GROUP0], reset=True)
    conf0.add_test(TEST1, groups=[GROUP1])
    conf0.add_test(TEST2, groups=[GROUP2], save=True)

    xeet = xeet_conf(BaseXeetSettings(conf0.file_path))
    groups = xeet.all_groups()
    assert groups == {GROUP0, GROUP1, GROUP2}
