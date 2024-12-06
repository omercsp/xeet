from ut import ConfigTestWrapper
from ut.dummy_test_config import DummyTestConfig, gen_dummy_step_desc, DummyStep
from xeet.config import TestCriteria, _extract_include_files, XeetIncludeLoopException
from xeet.xtest import Xtest


_TEST0 = "test0"
_TEST1 = "test1"
_TEST2 = "test2"
_TEST3 = "test3"
_TEST4 = "test4"

_INC_CONF0 = "xeet_inc0.json"
_INC_CONF1 = "xeet_inc1.json"
_ALL_TESTS_CRIT = TestCriteria([], [], [], [], True)


class TestConfig(DummyTestConfig):
    def test_inclusion_lists(self):
        CONF0_0 = "conf0.0.json"
        CONF1_0 = "conf1.0.json"
        CONF1_1 = "conf1.1.json"
        CONF1_2 = "conf1.2.json"
        CONF2_0 = "conf2.0.json"

        conf0_0 = ConfigTestWrapper(CONF0_0)
        conf0_0.save()
        config_files = _extract_include_files(conf0_0.file_path)
        self.assertEqual(len(config_files), 1)
        self.assertEqual(config_files[0], conf0_0.file_path)

        conf1_0 = ConfigTestWrapper(CONF1_0, includes=[conf0_0.file_path])
        conf1_0.save()
        config_files = _extract_include_files(conf1_0.file_path)
        self.assertEqual(len(config_files), 2)
        self.assertEqual(config_files[0], conf0_0.file_path)
        self.assertEqual(config_files[1], conf1_0.file_path)

        conf1_1 = ConfigTestWrapper(CONF1_1, includes=[conf0_0.file_path])
        conf1_1.save()

        conf2_0 = ConfigTestWrapper(CONF2_0, includes=[conf1_0.file_path, conf1_1.file_path])
        conf2_0.save()
        config_files = _extract_include_files(conf2_0.file_path)
        self.assertEqual(len(config_files), 5)
        self.assertEqual(config_files[0], conf0_0.file_path)
        self.assertEqual(config_files[1], conf1_0.file_path)
        self.assertEqual(config_files[2], conf0_0.file_path)
        self.assertEqual(config_files[3], conf1_1.file_path)
        self.assertEqual(config_files[4], conf2_0.file_path)

        conf1_2 = ConfigTestWrapper(CONF1_2)
        conf1_2.save()
        conf2_0.includes.append(conf1_2.file_path)
        conf2_0.save()
        config_files = _extract_include_files(conf2_0.file_path)
        self.assertEqual(len(config_files), 6)
        self.assertEqual(config_files[0], conf0_0.file_path)
        self.assertEqual(config_files[1], conf1_0.file_path)
        self.assertEqual(config_files[2], conf0_0.file_path)
        self.assertEqual(config_files[3], conf1_1.file_path)
        self.assertEqual(config_files[4], conf1_2.file_path)
        self.assertEqual(config_files[5], conf2_0.file_path)

    def test_recursive_inclusion(self):
        CONF0 = "conf0.json"
        CONF1 = "conf1.json"
        CONF2 = "conf2.json"
        conf0 = ConfigTestWrapper(CONF0)
        conf0.save()
        config_files = _extract_include_files(conf0.file_path)
        self.assertEqual(len(config_files), 1)
        self.assertEqual(config_files[0], conf0.file_path)

        conf0.includes = [conf0.file_path]
        conf0.save()
        self.assertRaises(XeetIncludeLoopException, _extract_include_files, conf0.file_path)

        conf1 = ConfigTestWrapper(CONF1, includes=[conf0.file_path])
        conf1.save()
        conf0.includes = [CONF1]
        conf0.save()
        self.assertRaises(XeetIncludeLoopException, _extract_include_files, conf0.file_path)

        conf2 = ConfigTestWrapper(CONF2, includes=[conf1.file_path])
        conf2.save()
        conf1.includes = [conf2.file_path]
        conf1.save()
        self.assertRaises(XeetIncludeLoopException, _extract_include_files, conf0.file_path)
        self.assertRaises(XeetIncludeLoopException, _extract_include_files, conf1.file_path)

        conf2 = ConfigTestWrapper(CONF2, includes=[conf0.file_path])
        conf2.save()
        self.assertRaises(XeetIncludeLoopException, _extract_include_files, conf0.file_path)

        conf2.includes = []
        conf2.save()
        self.assertListEqual(_extract_include_files(conf0.file_path), [
                             conf2.file_path, conf1.file_path, conf0.file_path])

    def test_get_xtest_by_name_simple(self):
        self.set_test(_TEST0, reset=True, save=True)

        config = self.config_file()
        xtest = config.xtest(_TEST0)
        self.assertIsInstance(xtest, Xtest)
        assert xtest is not None
        self.assertEqual(xtest.name, _TEST0)

        xtest = config.xtest("no_such_test")
        self.assertIsNone(xtest)

    def test_get_xtest_by_name(self):
        self.set_test(_TEST0, reset=True)
        self.set_test(_TEST1)
        self.set_test(_TEST2)
        self.set_test(_TEST3, save=True)

        config = self.config_file()
        crit = TestCriteria([_TEST0], [], [], [], True)
        xtests = config.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, _TEST0)

        crit.names = set([_TEST1])
        xtests = config.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, _TEST1)

        crit.names = set([_TEST0, _TEST3])
        xtests = config.xtests(criteria=crit)
        self.assertEqual(len(xtests), 2)
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST0, _TEST3]))

    def test_get_xtest_by_group(self):
        GROUP0 = "group0"
        GROUP1 = "group1"
        GROUP2 = "group2"

        self.set_test(_TEST0, groups=[GROUP0], reset=True)
        self.set_test(_TEST1, groups=[GROUP1])
        self.set_test(_TEST2, groups=[GROUP2])
        self.set_test(_TEST3, groups=[GROUP0, GROUP1], save=True)

        config = self.config_file()
        crit = TestCriteria([], [GROUP0], [], [], True)
        xtests = config.xtests(criteria=crit)
        self.assertEqual(len(xtests), 2)
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST0, _TEST3]))

        crit.require_groups = set([GROUP1])
        xtests = config.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, _TEST3)

        crit.exclude_groups = set([GROUP1])
        xtests = config.xtests(criteria=crit)
        self.assertEqual(len(xtests), 0)

        crit.require_groups.clear()
        xtests = config.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)
        self.assertEqual(xtests[0].name, _TEST0)

        crit.include_groups = set([GROUP2, GROUP1])
        xtests = config.xtests(criteria=crit)
        self.assertEqual(len(xtests), 1)  # exclude group for group1 is still set
        self.assertEqual(xtests[0].name, _TEST2)

        crit.exclude_groups.clear()
        xtests = config.xtests(criteria=crit)
        self.assertEqual(len(xtests), 3)
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST1, _TEST2, _TEST3]))

    def test_get_all_tests(self):
        self.set_test(_TEST0, reset=True)
        self.set_test(_TEST1)
        self.set_test(_TEST2, save=True)
        config = self.config_file()
        xtests = config.xtests(criteria=_ALL_TESTS_CRIT)
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST0, _TEST1, _TEST2]))

        included_conf_wrapper = ConfigTestWrapper(_INC_CONF0)
        included_conf_wrapper.add_test(_TEST2)
        included_conf_wrapper.add_test(_TEST3)
        included_conf_wrapper.add_test(_TEST4)
        included_conf_wrapper.save()

        self.add_include(_INC_CONF0, save=True)

        config = self.config_file()
        xtests = config.xtests(criteria=_ALL_TESTS_CRIT)
        self.assertSetEqual(set([t.name for t in xtests]),
                            set([_TEST0, _TEST1, _TEST2, _TEST3, _TEST4]))

    def test_get_hidden_tests(self):
        self.set_test(_TEST0, reset=True)
        self.set_test(_TEST1, abstract=True)
        self.set_test(_TEST2, save=True)

        crit = TestCriteria([], [], [], [], True)
        config = self.config_file()
        xtests = config.xtests(criteria=crit)
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST0, _TEST1, _TEST2]))

        crit.hidden_tests = False
        xtests = config.xtests(criteria=crit)
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST0, _TEST2]))

    def test_shadowed_tests(self):
        def assert_test(name: str, dummy_field: str) -> None:
            xtest = self.config_file().xtest(name)
            self.assertIsInstance(xtest, Xtest)
            assert xtest is not None
            assert xtest.run_steps is not None
            self.assertEqual(len(xtest.run_steps), 1)
            self.assertIsInstance(xtest.run_steps[0], DummyStep)
            self.assertEqual(xtest.run_steps[0].dummy_model.dummy_field,   # type: ignore
                             dummy_field)

        depth0 = "depth0"
        depth1 = "depth1"
        depth2 = "depth2"

        depth0_step = gen_dummy_step_desc(dummy_field=depth0)
        depth1_step = gen_dummy_step_desc(dummy_field=depth1)
        depth2_step = gen_dummy_step_desc(dummy_field=depth2)

        self.set_test(_TEST0, run=[depth0_step], reset=True)
        self.set_test(_TEST1, run=[depth0_step])
        self.add_include(_INC_CONF0, save=True)

        conf_wrapper = ConfigTestWrapper(_INC_CONF0, includes=[_INC_CONF1])
        conf_wrapper.add_test(_TEST1, run=[depth1_step])
        conf_wrapper.add_test(_TEST2, run=[depth1_step], save=True)

        conf_wrapper = ConfigTestWrapper(_INC_CONF1)
        conf_wrapper.add_test(_TEST2, run=[depth2_step])
        conf_wrapper.add_test(_TEST3, run=[depth2_step], save=True)

        config = self.config_file()
        xtests = config.xtests(criteria=_ALL_TESTS_CRIT)
        self.assertSetEqual(set([t.name for t in xtests]), set([_TEST0, _TEST1, _TEST2, _TEST3]))

        assert_test(_TEST0, depth0)
        assert_test(_TEST1, depth0)
        assert_test(_TEST2, depth1)
        assert_test(_TEST3, depth2)
