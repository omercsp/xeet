from ut import ConfigTestWrapper
from ut.dummy_test_config import DummyTestConfig,  OK_STEP_DESC, FAILING_STEP_DESC
from xeet.core.driver import (XeetModel, TestCriteria, XeetIncludeLoopException, Driver,
                              xeet_init)
from xeet.core.xtest import Xtest, StepsInheritType, XtestModel
import os


_TEST0 = "test0"
_TEST1 = "test1"
_TEST2 = "test2"
_TEST3 = "test3"
_TEST4 = "test4"
_TEST5 = "test5"
_TEST6 = "test6"
_GROUP0 = "group0"
_GROUP1 = "group1"
_GROUP2 = "group2"


_ALL_TESTS_CRIT = TestCriteria()


class TestDriver(DummyTestConfig):
    def test_config_model_inclusion(self):
        CONF0 = "conf0.yaml"
        CONF1 = "conf1.yaml"
        CONF2 = "conf2.yaml"
        CONF3 = "conf3.yaml"
        CONF4 = "conf4.yaml"

        conf0 = ConfigTestWrapper(CONF0)
        root = os.path.dirname(conf0.file_path)
        d0_0 = conf0.add_test(_TEST0, arg=1)
        conf0.add_var("var0", 0)
        conf0.add_settings("setting0", {"a": 0}, save=True)

        conf1 = ConfigTestWrapper(CONF1, includes=[conf0.file_path])
        d1_1 = conf1.add_test(_TEST1, arg=2)
        conf1.add_var("var1", 1)
        conf1.add_settings("setting1", {"a": 1}, save=True)

        model = xeet_init(conf1.file_path).model
        self.assertIsInstance(model, XeetModel)
        self.assertEqual(len(model.tests), 2)
        self.assertDictEqual(model.tests[0], d0_0)
        self.assertDictEqual(model.tests[1], d1_1)
        self.assertEqual(len(model.variables), 2)
        self.assertEqual(model.variables["var0"], 0)
        self.assertEqual(model.variables["var1"], 1)
        self.assertEqual(len(model.settings), 2)
        self.assertEqual(model.settings["setting0"], {"a": 0})
        self.assertEqual(model.settings["setting1"], {"a": 1})

        conf2 = ConfigTestWrapper(CONF2, includes=["{XG_ROOT}/" + CONF1])
        d2_0 = conf2.add_test(_TEST0, arg=30)
        d2_1 = conf2.add_test(_TEST1, arg=40)
        d2_2 = conf2.add_test(_TEST2, arg=50)  # new test
        conf2.save()
        model = xeet_init(conf2.file_path).model
        self.assertIsInstance(model, XeetModel)
        self.assertEqual(len(model.tests), 3)
        self.assertDictEqual(model.tests[0], d2_0)
        self.assertDictEqual(model.tests[1], d2_1)
        self.assertDictEqual(model.tests[2], d2_2)

        conf3 = ConfigTestWrapper(CONF3, includes=[f"{root}/{CONF1}"])
        d3_0 = conf3.add_test(_TEST0, arg=31)
        d3_3 = conf3.add_test(_TEST3, arg=41)
        d3_4 = conf3.add_test(_TEST4, arg=51, save=True)
        model = xeet_init(conf3.file_path).model

        conf4 = ConfigTestWrapper(CONF4, includes=[f"{root}/{CONF2}", f"{root}/{CONF3}"])
        d4_5 = conf4.add_test(_TEST5, arg=62)
        conf4.save()
        model = xeet_init(conf4.file_path).model
        self.assertIsInstance(model, XeetModel)
        self.assertEqual(len(model.tests), 6)
        self.assertDictEqual(model.tests_dict[_TEST0], d3_0)
        self.assertDictEqual(model.tests_dict[_TEST1], d1_1)
        self.assertDictEqual(model.tests_dict[_TEST2], d2_2)
        self.assertDictEqual(model.tests_dict[_TEST3], d3_3)
        self.assertDictEqual(model.tests_dict[_TEST4], d3_4)
        self.assertDictEqual(model.tests_dict[_TEST5], d4_5)
        self.assertEqual(model.settings["setting0"], {"a": 0})
        self.assertEqual(model.settings["setting1"], {"a": 1})

    def test_inclusion_loop(self):
        CONF0 = "conf0.json"
        CONF1 = "conf1.json"
        CONF2 = "conf2.json"
        conf0 = ConfigTestWrapper(CONF0)
        conf0.save()

        conf0.includes = [conf0.file_path]
        conf0.save()
        self.assertRaises(XeetIncludeLoopException, xeet_init, conf0.file_path)

        conf1 = ConfigTestWrapper(CONF1, includes=[conf0.file_path])
        conf1.save()
        self.assertRaises(XeetIncludeLoopException, xeet_init, conf1.file_path)

        conf0.includes = [conf1.file_path]
        conf0.save()
        self.assertRaises(XeetIncludeLoopException, xeet_init, conf1.file_path)

        conf2 = ConfigTestWrapper(CONF2, includes=[conf1.file_path])
        conf2.save()
        self.assertRaises(XeetIncludeLoopException, xeet_init, conf2.file_path)

        conf0.includes = [conf2.file_path]
        conf0.save()

        self.assertRaises(XeetIncludeLoopException, xeet_init, conf0.file_path)
        self.assertRaises(XeetIncludeLoopException, xeet_init, conf1.file_path)
        self.assertRaises(XeetIncludeLoopException, xeet_init, conf2.file_path)

    def test_get_xtest_by_name_simple(self):
        self.add_test(_TEST0, reset=True, save=True)

        xeet = self.driver()
        xtest = xeet.xtest(_TEST0)
        self.assertIsInstance(xtest, Xtest)
        assert xtest is not None
        self.assertEqual(xtest.name, _TEST0)

        xtest = xeet.xtest("no_such_test")
        self.assertIsNone(xtest)

    def test_get_xtest_by_name(self):
        self.add_test(_TEST0, reset=True)
        self.add_test(_TEST1)
        self.add_test(_TEST2)
        self.add_test(_TEST3, save=True)

        xeet = self.driver()
        crit = TestCriteria(names=[_TEST0], hidden_tests=True)
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, _TEST0)

        crit.names = set([_TEST1])
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, _TEST1)

        crit.names = set([_TEST0, _TEST3])
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 2)
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST0, _TEST3]))

    def test_get_xtest_by_group(self):
        self.add_test(_TEST0, groups=[_GROUP0], reset=True)
        self.add_test(_TEST1, groups=[_GROUP1])
        self.add_test(_TEST2, groups=[_GROUP2])
        self.add_test(_TEST3, groups=[_GROUP0, _GROUP1], save=True)

        xeet = self.driver()
        crit = TestCriteria(include_groups=[_GROUP0], hidden_tests=True)
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 2)
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST0, _TEST3]))

        crit.require_groups = set([_GROUP1])
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, _TEST3)

        crit.exclude_groups = set([_GROUP1])
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 0)

        crit.require_groups.clear()
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, _TEST0)

        crit.include_groups = set([_GROUP2, _GROUP1])
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)  # exclude group for group1 is still set
        self.assertEqual(xtests[0].name, _TEST2)

        crit.exclude_groups.clear()
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 3)
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST1, _TEST2, _TEST3]))

    def test_get_all_tests(self):
        self.add_test(_TEST0, reset=True)
        self.add_test(_TEST1)
        self.add_test(_TEST2, save=True)

        xeet = self.driver()
        xtests = xeet.xtests(_ALL_TESTS_CRIT)
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST0, _TEST1, _TEST2]))

        INC_CONF0 = "inc_conf0.yaml"
        included_conf_wrapper = ConfigTestWrapper(INC_CONF0)
        included_conf_wrapper.add_test(_TEST2)
        included_conf_wrapper.add_test(_TEST3)
        included_conf_wrapper.add_test(_TEST4, save=True)

        self.add_include(INC_CONF0, save=True)

        xeet = self.driver()
        xtests = xeet.xtests(_ALL_TESTS_CRIT)
        self.assertSetEqual(set([t.name for t in xtests]),
                            set([_TEST0, _TEST1, _TEST2, _TEST3, _TEST4]))

        INC_CONF1 = "inc_conf1.yaml"
        included_conf_wrapper = ConfigTestWrapper(INC_CONF1)
        included_conf_wrapper.add_test(_TEST5)
        included_conf_wrapper.add_test(_TEST6)
        included_conf_wrapper.save()

        self.add_include(INC_CONF1, save=True)

        xeet = self.driver()
        xtests = xeet.xtests(_ALL_TESTS_CRIT)
        self.assertSetEqual(set([t.name for t in xtests]),
                            set([_TEST0, _TEST1, _TEST2, _TEST3, _TEST4, _TEST5, _TEST6]))

    def test_get_hidden_tests(self):
        self.add_test(_TEST0, reset=True)
        self.add_test(_TEST1, abstract=True)
        self.add_test(_TEST2, save=True)

        crit = TestCriteria(hidden_tests=True)
        xeet = self.driver()
        xtests = xeet.xtests(criteria=crit)
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST0, _TEST1, _TEST2]))

        crit.hidden_tests = False
        xtests = xeet.xtests(criteria=crit)
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST0, _TEST2]))

    def test_step_lists_inheritance(self):
        def assert_step_desc_list_equal(
            steps: list[dict] | None,
            expected: list[dict] | None
        ) -> None:
            if expected is None:
                self.assertIsNone(steps)
                return
            self.assertIsNotNone(steps)
            assert steps is not None
            self.assertEqual(len(steps), len(expected))
            for step_desc, expected_step_desc in zip(steps, expected):
                self.assertDummyDescsEqual(step_desc, expected_step_desc)

        def assert_test_model_steps(name: str,
                                    xeet: Driver,
                                    pre_run: list = list(),
                                    run: list = list(),
                                    post_run: list = list()) -> None:

            desc = xeet.test_desc(name)
            self.assertIsNotNone(desc)
            self.assertIsInstance(desc, dict)
            assert desc is not None
            model = xeet._xtest_model(desc)
            self.assertIsInstance(model, XtestModel)
            assert_step_desc_list_equal(model.pre_run, pre_run)
            assert_step_desc_list_equal(model.run, run)
            assert_step_desc_list_equal(model.post_run, post_run)

        self.add_test(_TEST0, run=[OK_STEP_DESC], reset=True)
        self.add_test(_TEST1, pre_run=[OK_STEP_DESC], base=_TEST0)
        self.add_test(_TEST2, base=_TEST1, run=[FAILING_STEP_DESC])
        self.add_test(_TEST3, base=_TEST0, run_inheritance=StepsInheritType.Append,
                      run=[FAILING_STEP_DESC])
        self.add_test(_TEST4, base=_TEST0, run_inheritance=StepsInheritType.Prepend,
                      run=[FAILING_STEP_DESC])
        self.add_test(_TEST5, base=_TEST1, run=[], post_run=[OK_STEP_DESC, OK_STEP_DESC])
        self.add_test(_TEST6, base=_TEST5, run=[FAILING_STEP_DESC],
                      run_inheritance=StepsInheritType.Append, save=True)

        xeet = self.driver()
        assert_test_model_steps(_TEST0, xeet, run=[OK_STEP_DESC])
        assert_test_model_steps(_TEST1, xeet, pre_run=[OK_STEP_DESC], run=[OK_STEP_DESC])
        assert_test_model_steps(_TEST2, xeet, pre_run=[OK_STEP_DESC], run=[FAILING_STEP_DESC])
        assert_test_model_steps(_TEST3, xeet, run=[OK_STEP_DESC, FAILING_STEP_DESC])
        assert_test_model_steps(_TEST4, xeet, run=[FAILING_STEP_DESC, OK_STEP_DESC])
        assert_test_model_steps(_TEST5, xeet, pre_run=[OK_STEP_DESC], run=[],
                                post_run=[OK_STEP_DESC, OK_STEP_DESC])
        assert_test_model_steps(_TEST6, xeet, pre_run=[OK_STEP_DESC], run=[FAILING_STEP_DESC],
                                post_run=[OK_STEP_DESC, OK_STEP_DESC])

    def test_exclude_tests(self):
        self.add_test(_TEST0, reset=True)
        self.add_test(_TEST1)
        self.add_test(_TEST2, save=True)

        xeet = self.driver()
        xtests = xeet.xtests(TestCriteria(exclude_names=[_TEST0, _TEST1]))
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, _TEST2)

    def test_fuzzy_names(self):
        self.add_test(_TEST0, reset=True)
        self.add_test(_TEST1)
        self.add_test(_TEST2)
        self.add_test("other", save=True)

        xeet = self.driver()
        xtests = xeet.xtests(TestCriteria(fuzzy_names=["t1"]))
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST1]))

        xtests = xeet.xtests(TestCriteria(fuzzy_names=["test"]))
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST0, _TEST1, _TEST2]))

    def test_misc_test_filteing(self):
        self.add_test(_TEST0, reset=True)
        self.add_test(_TEST1, groups=[_GROUP0])
        self.add_test(_TEST2, groups=[_GROUP1])
        self.add_test(_TEST3, groups=[_GROUP0, _GROUP1], save=True)

        xeet = self.driver()
        xtests = xeet.xtests(TestCriteria(include_groups=[_GROUP0], exclude_groups=[_GROUP1]))
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, _TEST1)

        xtests = xeet.xtests(TestCriteria(include_groups=[_GROUP1], names=[_TEST0]))
        self.assertEqual(len(xtests), 3)
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST0, _TEST2, _TEST3]))

        xtests = xeet.xtests(TestCriteria(include_groups=[_GROUP1], fuzzy_exclude_names=["t3"]))
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, _TEST2)

        xtests = xeet.xtests(TestCriteria(require_groups=[_GROUP0, _GROUP1],
                                          exclude_names=[_TEST3]))
        self.assertEqual(len(xtests), 0)

    def test_get_groups(self):
        self.add_test(_TEST0, groups=[_GROUP0], reset=True)
        self.add_test(_TEST1, groups=[_GROUP1])
        self.add_test(_TEST2, groups=[_GROUP2], save=True)

        xeet = self.driver()
        groups = xeet.all_groups()
        self.assertSetEqual(groups, {_GROUP0, _GROUP1, _GROUP2})
