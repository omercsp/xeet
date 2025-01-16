from ut import *
from ut.ut_dummy_defs import *
from xeet.core.driver import (XeetModel, TestCriteria, XeetIncludeLoopException, Driver,
                              xeet_init)
from xeet.core.xtest import Xtest, StepsInheritType, XtestModel
import os


_ALL_TESTS_CRIT = TestCriteria()


class TestDriver(XeetUnittest):
    def assertDummyDescsEqual(self, res: dict, expected: dict) -> None:
        self.assertIsInstance(res, dict)
        self.assertIsInstance(expected, dict)
        for k, v in expected.items():
            self.assertIn(k, res)
            self.assertEqual(res[k], v)
        for k in res.keys():
            self.assertIn(k, expected)

    def test_config_model_inclusion(self):
        CONF0 = "conf0.yaml"
        CONF1 = "conf1.yaml"
        CONF2 = "conf2.yaml"
        CONF3 = "conf3.yaml"
        CONF4 = "conf4.yaml"

        conf0 = ConfigTestWrapper(CONF0)
        root = os.path.dirname(conf0.file_path)
        d0_0 = conf0.add_test(TEST0, arg=1)
        conf0.add_var("var0", 0)
        conf0.add_settings("setting0", {"a": 0}, save=True)

        conf1 = ConfigTestWrapper(CONF1, includes=[conf0.file_path])
        d1_1 = conf1.add_test(TEST1, arg=2)
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

        conf2 = ConfigTestWrapper(CONF2, includes=["{XEET_ROOT}/" + CONF1])
        d2_0 = conf2.add_test(TEST0, arg=30)
        d2_1 = conf2.add_test(TEST1, arg=40)
        d2_2 = conf2.add_test(TEST2, arg=50)  # new test
        conf2.save()
        model = xeet_init(conf2.file_path).model
        self.assertIsInstance(model, XeetModel)
        self.assertEqual(len(model.tests), 3)
        self.assertDictEqual(model.tests[0], d2_0)
        self.assertDictEqual(model.tests[1], d2_1)
        self.assertDictEqual(model.tests[2], d2_2)

        conf3 = ConfigTestWrapper(CONF3, includes=[f"{root}/{CONF1}"])
        d3_0 = conf3.add_test(TEST0, arg=31)
        d3_3 = conf3.add_test(TEST3, arg=41)
        d3_4 = conf3.add_test(TEST4, arg=51, save=True)
        model = xeet_init(conf3.file_path).model

        conf4 = ConfigTestWrapper(CONF4, includes=[f"{root}/{CONF2}", f"{root}/{CONF3}"])
        d4_5 = conf4.add_test(TEST5, arg=62)
        conf4.save()
        model = xeet_init(conf4.file_path).model
        self.assertIsInstance(model, XeetModel)
        self.assertEqual(len(model.tests), 6)
        self.assertDictEqual(model.tests_dict[TEST0], d3_0)
        self.assertDictEqual(model.tests_dict[TEST1], d1_1)
        self.assertDictEqual(model.tests_dict[TEST2], d2_2)
        self.assertDictEqual(model.tests_dict[TEST3], d3_3)
        self.assertDictEqual(model.tests_dict[TEST4], d3_4)
        self.assertDictEqual(model.tests_dict[TEST5], d4_5)
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
        self.add_test(TEST0, reset=True, save=True)

        xeet = self.driver()
        xtest = xeet.xtest(TEST0)
        self.assertIsInstance(xtest, Xtest)
        assert xtest is not None
        self.assertEqual(xtest.name, TEST0)

        xtest = xeet.xtest("no_such_test")
        self.assertIsNone(xtest)

    def test_get_xtest_by_name(self):
        self.add_test(TEST0, reset=True)
        self.add_test(TEST1)
        self.add_test(TEST2)
        self.add_test(TEST3, save=True)

        xeet = self.driver()
        crit = TestCriteria(names={TEST0}, hidden_tests=True)
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, TEST0)

        crit.names = set([TEST1])
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, TEST1)

        crit.names = set([TEST0, TEST3])
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 2)
        self.assertSetEqual(set([t.name for t in xtests]), set([TEST0, TEST3]))

    def test_get_xtest_by_group(self):
        self.add_test(TEST0, groups=[GROUP0], reset=True)
        self.add_test(TEST1, groups=[GROUP1])
        self.add_test(TEST2, groups=[GROUP2])
        self.add_test(TEST3, groups=[GROUP0, GROUP1], save=True)

        xeet = self.driver()
        crit = TestCriteria(include_groups={GROUP0}, hidden_tests=True)
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 2)
        self.assertSetEqual(set([t.name for t in xtests]), set([TEST0, TEST3]))

        crit.require_groups = set([GROUP1])
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, TEST3)

        crit.exclude_groups = set([GROUP1])
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 0)

        crit.require_groups.clear()
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, TEST0)

        crit.include_groups = set([GROUP2, GROUP1])
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)  # exclude group for group1 is still set
        self.assertEqual(xtests[0].name, TEST2)

        crit.exclude_groups.clear()
        xtests = xeet.xtests(criteria=crit)
        self.assertEqual(len(xtests), 3)
        self.assertSetEqual(set([t.name for t in xtests]), set([TEST1, TEST2, TEST3]))

    def test_get_all_tests(self):
        self.add_test(TEST0, reset=True)
        self.add_test(TEST1)
        self.add_test(TEST2, save=True)

        xeet = self.driver()
        xtests = xeet.xtests(_ALL_TESTS_CRIT)
        self.assertSetEqual(set([t.name for t in xtests]), set([TEST0, TEST1, TEST2]))

        INC_CONF0 = "inc_conf0.yaml"
        included_conf_wrapper = ConfigTestWrapper(INC_CONF0)
        included_conf_wrapper.add_test(TEST2)
        included_conf_wrapper.add_test(TEST3)
        included_conf_wrapper.add_test(TEST4, save=True)

        self.add_include(INC_CONF0, save=True)

        xeet = self.driver()
        xtests = xeet.xtests(_ALL_TESTS_CRIT)
        self.assertSetEqual(set([t.name for t in xtests]),
                            set([TEST0, TEST1, TEST2, TEST3, TEST4]))

        INC_CONF1 = "inc_conf1.yaml"
        included_conf_wrapper = ConfigTestWrapper(INC_CONF1)
        included_conf_wrapper.add_test(TEST5)
        included_conf_wrapper.add_test(TEST6)
        included_conf_wrapper.save()

        self.add_include(INC_CONF1, save=True)

        xeet = self.driver()
        xtests = xeet.xtests(_ALL_TESTS_CRIT)
        self.assertSetEqual(set([t.name for t in xtests]),
                            set([TEST0, TEST1, TEST2, TEST3, TEST4, TEST5, TEST6]))

    def test_get_hidden_tests(self):
        self.add_test(TEST0, reset=True)
        self.add_test(TEST1, abstract=True)
        self.add_test(TEST2, save=True)

        crit = TestCriteria(hidden_tests=True)
        xeet = self.driver()
        xtests = xeet.xtests(criteria=crit)
        self.assertSetEqual(set([t.name for t in xtests]), set([TEST0, TEST1, TEST2]))

        crit.hidden_tests = False
        xtests = xeet.xtests(criteria=crit)
        self.assertSetEqual(set([t.name for t in xtests]), set([TEST0, TEST2]))

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

        self.add_test(TEST0, run=[DUMMY_OK_STEP_DESC], reset=True)
        self.add_test(TEST1, pre_run=[DUMMY_OK_STEP_DESC], base=TEST0)
        self.add_test(TEST2, base=TEST1, run=[DUMMY_FAILING_STEP_DESC])
        self.add_test(TEST3, base=TEST0, run_inheritance=StepsInheritType.Append,
                      run=[DUMMY_FAILING_STEP_DESC])
        self.add_test(TEST4, base=TEST0, run_inheritance=StepsInheritType.Prepend,
                      run=[DUMMY_FAILING_STEP_DESC])
        self.add_test(TEST5, base=TEST1, run=[], post_run=[DUMMY_OK_STEP_DESC, DUMMY_OK_STEP_DESC])
        self.add_test(TEST6, base=TEST5, run=[DUMMY_FAILING_STEP_DESC],
                      run_inheritance=StepsInheritType.Append, save=True)

        xeet = self.driver()
        assert_test_model_steps(TEST0, xeet, run=[DUMMY_OK_STEP_DESC])
        assert_test_model_steps(TEST1, xeet, pre_run=[DUMMY_OK_STEP_DESC], run=[DUMMY_OK_STEP_DESC])
        assert_test_model_steps(TEST2, xeet,
                                pre_run=[DUMMY_OK_STEP_DESC],
                                run=[DUMMY_FAILING_STEP_DESC])
        assert_test_model_steps(TEST3, xeet, run=[DUMMY_OK_STEP_DESC, DUMMY_FAILING_STEP_DESC])
        assert_test_model_steps(TEST4, xeet, run=[DUMMY_FAILING_STEP_DESC, DUMMY_OK_STEP_DESC])
        assert_test_model_steps(TEST5, xeet, pre_run=[DUMMY_OK_STEP_DESC],
                                post_run=[DUMMY_OK_STEP_DESC, DUMMY_OK_STEP_DESC])
        assert_test_model_steps(TEST6, xeet,
                                pre_run=[DUMMY_OK_STEP_DESC],
                                run=[DUMMY_FAILING_STEP_DESC],
                                post_run=[DUMMY_OK_STEP_DESC, DUMMY_OK_STEP_DESC])

    def test_exclude_tests(self):
        self.add_test(TEST0, reset=True)
        self.add_test(TEST1)
        self.add_test(TEST2, save=True)

        xeet = self.driver()
        xtests = xeet.xtests(TestCriteria(exclude_names={TEST0, TEST1}))
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, TEST2)

    def test_fuzzy_names(self):
        self.add_test(TEST0, reset=True)
        self.add_test(TEST1)
        self.add_test(TEST2)
        self.add_test("other", save=True)

        xeet = self.driver()
        xtests = xeet.xtests(TestCriteria(fuzzy_names=["t1"]))
        self.assertSetEqual(set([t.name for t in xtests]), set([TEST1]))

        xtests = xeet.xtests(TestCriteria(fuzzy_names=["test"]))
        self.assertSetEqual(set([t.name for t in xtests]), set([TEST0, TEST1, TEST2]))

    def test_misc_test_filteing(self):
        self.add_test(TEST0, reset=True)
        self.add_test(TEST1, groups=[GROUP0])
        self.add_test(TEST2, groups=[GROUP1])
        self.add_test(TEST3, groups=[GROUP0, GROUP1], save=True)

        xeet = self.driver()
        xtests = xeet.xtests(TestCriteria(include_groups={GROUP0}, exclude_groups={GROUP1}))
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, TEST1)

        xtests = xeet.xtests(TestCriteria(include_groups={GROUP1}, names={TEST0}))
        self.assertEqual(len(xtests), 3)
        self.assertSetEqual(set([t.name for t in xtests]), set([TEST0, TEST2, TEST3]))

        xtests = xeet.xtests(TestCriteria(include_groups={GROUP1}, fuzzy_exclude_names={"t3"}))
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, TEST2)

        xtests = xeet.xtests(TestCriteria(require_groups={GROUP0, GROUP1},
                                          exclude_names={TEST3}))
        self.assertEqual(len(xtests), 0)

    def test_get_groups(self):
        self.add_test(TEST0, groups=[GROUP0], reset=True)
        self.add_test(TEST1, groups=[GROUP1])
        self.add_test(TEST2, groups=[GROUP2], save=True)

        xeet = self.driver()
        groups = xeet.all_groups()
        self.assertSetEqual(groups, {GROUP0, GROUP1, GROUP2})
