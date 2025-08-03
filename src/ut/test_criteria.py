from ut import *
from ut.ut_dummy_defs import *
from xeet.core.api import fetch_tests
from xeet.core import TestsCriteria
from xeet.core.matrix import Matrix


def assert_dummy_descs_equal(res: dict, expected: dict) -> None:
    assert isinstance(res, dict)
    assert isinstance(expected, dict)
    for k, v in expected.items():
        assert k in res
        assert res[k] == v
    for k in res.keys():
        assert k in expected


def test_get_test_by_name(xut: XeetUnittest):
    xut.add_test(TEST0)
    xut.add_test(TEST1)
    xut.add_test(TEST2)
    xut.add_test(TEST3, save=True)

    crit = TestsCriteria(names=[TEST0])
    tests = xut.driver().fetch_tests(criteria=crit)
    assert len(tests) == 1
    assert tests[0].name == TEST0

    crit.names = [TEST0, TEST3]
    tests = xut.driver().fetch_tests(criteria=crit)
    assert len(tests) == 2
    assert set([t.name for t in tests]) == set([TEST0, TEST3])

    crit.names = [TEST4, TEST2]
    tests = xut.driver().fetch_tests(criteria=crit)
    assert len(tests) == 1
    assert tests[0].name == TEST2

    crit.names = [TEST4, TEST5]
    tests = xut.driver().fetch_tests(criteria=crit)
    assert len(tests) == 0


def test_get_test_by_group(xut: XeetUnittest):
    xut.add_test(TEST0, groups=[GROUP0])
    xut.add_test(TEST1, groups=[GROUP1])
    xut.add_test(TEST2, groups=[GROUP2])
    xut.add_test(TEST3, groups=[GROUP0, GROUP1], save=True)

    crit = TestsCriteria(include_groups=[GROUP0])
    tests = xut.driver().fetch_tests(criteria=crit)
    assert len(tests) == 2
    assert set([t.name for t in tests]) == set([TEST0, TEST3])

    crit.require_groups = {GROUP1}
    tests = xut.driver().fetch_tests(criteria=crit)
    assert len(tests) == 1
    assert set([t.name for t in tests]) == {TEST3}

    crit.exclude_groups = set([GROUP1])
    tests = xut.driver().fetch_tests(criteria=crit)
    assert len(tests) == 0

    crit.require_groups.clear()
    tests = xut.driver().fetch_tests(criteria=crit)
    assert len(tests) == 1
    assert tests[0].name == TEST0

    crit.include_groups = [GROUP2, GROUP1]
    tests = xut.driver().fetch_tests(criteria=crit)
    assert len(tests) == 1  # exclude group for group1 is still set
    assert tests[0].name == TEST2

    crit.exclude_groups.clear()
    tests = xut.driver().fetch_tests(criteria=crit)
    assert len(tests) == 3
    assert set([t.name for t in tests]) == set([TEST1, TEST2, TEST3])


def test_get_all_tests():
    conf0 = "conf0.yaml"
    xut = XeetUnittest(conf0)
    xut.add_test(TEST0, reset=True)
    xut.add_test(TEST1)
    xut.add_test(TEST2, save=True)

    crit = TestsCriteria()
    tests = xut.driver().fetch_tests(crit)
    assert set([t.name for t in tests]) == set([TEST0, TEST1, TEST2])

    INC_CONF0 = "inc_conf0.yaml"
    inc_xut = XeetUnittest(INC_CONF0)
    inc_xut.add_test(TEST2)
    inc_xut.add_test(TEST3)
    inc_xut.add_test(TEST4, save=True)

    xut.add_include(INC_CONF0, save=True)

    tests = xut.driver().fetch_tests(crit)
    assert set([t.name for t in tests]) == set([TEST0, TEST1, TEST2, TEST3, TEST4])

    INC_CONF1 = "inc_conf1.yaml"
    included_conf_wrapper = ConfigTestWrapper(INC_CONF1)
    included_conf_wrapper.add_test(TEST5)
    included_conf_wrapper.add_test(TEST6)
    included_conf_wrapper.save()
    inc_xut.add_include(INC_CONF1, save=True)

    tests = xut.driver().fetch_tests(crit)
    assert set([t.name for t in tests]) == set([TEST0, TEST1, TEST2, TEST3, TEST4, TEST5, TEST6])


def test_get_hidden_tests():
    conf0 = "conf0.yaml"
    xut = XeetUnittest(conf0)
    xut.add_test(TEST0)
    xut.add_test(TEST1, abstract=True)
    xut.add_test(TEST2, save=True)

    crit = TestsCriteria(abstract_tests=True)
    tests = xut.driver().fetch_tests(criteria=crit)
    assert set([t.name for t in tests]) == {TEST0, TEST1, TEST2}

    crit.abstract_tests = False
    tests = xut.driver().fetch_tests(criteria=crit)
    assert set([t.name for t in tests]) == set([TEST0, TEST2])


def test_exclude_tests(xut: XeetUnittest):
    xut.add_test(TEST0)
    xut.add_test(TEST1)
    xut.add_test(TEST2, save=True)

    crit = TestsCriteria(exclude_names={TEST0, TEST1})
    tests = xut.driver().fetch_tests(criteria=crit)
    assert len(tests) == 1
    assert tests[0].name == TEST2


def test_fuzzy_names(xut: XeetUnittest):
    xut.add_test(TEST0)
    xut.add_test(TEST1)
    xut.add_test(TEST2)
    xut.add_test("other", save=True)

    crit = TestsCriteria(fuzzy_names=["t1"])
    tests = xut.driver().fetch_tests(criteria=crit)
    assert set([t.name for t in tests]) == set([TEST1])

    crit.fuzzy_names = ["test"]
    tests = xut.driver().fetch_tests(criteria=crit)
    assert set([t.name for t in tests]) == set([TEST0, TEST1, TEST2])


def test_misc_test_filtering(xut: XeetUnittest):
    xut.add_test(TEST0, reset=True)
    xut.add_test(TEST1, groups=[GROUP0])
    xut.add_test(TEST2, groups=[GROUP1])
    xut.add_test(TEST3, groups=[GROUP0, GROUP1], save=True)

    tests = xut.driver().fetch_tests(TestsCriteria(include_groups=[GROUP0],
                                                   exclude_groups={GROUP1}))
    assert len(tests) == 1
    assert tests[0].name == TEST1

    tests = xut.driver().fetch_tests(TestsCriteria(include_groups=[GROUP1], names=[TEST0]))
    assert len(tests) == 3
    assert set([t.name for t in tests]) == set([TEST0, TEST2, TEST3])

    tests = xut.driver().fetch_tests(
        TestsCriteria(include_groups=[GROUP1], fuzzy_exclude_names={"t3"}))
    assert len(tests) == 1
    assert tests[0].name == TEST2

    tests = xut.driver().fetch_tests(
        TestsCriteria(require_groups={GROUP0, GROUP1}, exclude_names={TEST3}))
    assert len(tests) == 0


def test_matrix_filtering(xut: XeetUnittest):
    m0_dict = {"param1": [1, 2], "param2": [3, 4]}
    m1_dict = {"param1": [1, 2, 3] }
    xut.add_test(TEST0, matrix=m0_dict)
    xut.add_test(TEST1, matrix=m1_dict)
    xut.add_test(TEST2, save=True)

    mtrx0 = Matrix(m0_dict)
    mtrx1 = Matrix(m1_dict)

    assert mtrx0.prmttns_count == 4
    assert mtrx1.prmttns_count == 3

    test0_prmmtn_names = { f"{TEST0}:{i}" for i in range(mtrx0.prmttns_count)}
    test1_prmmtn_names = { f"{TEST1}:{i}" for i in range(mtrx1.prmttns_count)}

    #  Default criteria should return both matrix tests and permutations
    crit = TestsCriteria()
    tests = xut.driver().fetch_tests(criteria=crit)

    assert {t.name for t in tests} == {TEST0, TEST1, TEST2} | test0_prmmtn_names \
        | test1_prmmtn_names

    crit.matrix_tests = False
    tests = xut.driver().fetch_tests(criteria=crit)
    assert {t.name for t in tests} == {TEST2} | test0_prmmtn_names | test1_prmmtn_names

    crit.implicit_prmttn_tests = False
    tests = xut.driver().fetch_tests(criteria=crit)
    tests = fetch_tests(xut.file_path, criteria=crit)
    assert {t.name for t in tests} == {TEST2}

    crit.implicit_prmttn_tests = True
    crit.names = [TEST0]
    tests = xut.driver().fetch_tests(criteria=crit)
    assert {t.name for t in tests} == test0_prmmtn_names

    crit.names = [f"{TEST0}:1"]
    tests = xut.driver().fetch_tests(criteria=crit)
    assert {t.name for t in tests} == {f"{TEST0}:1"}

    crit.names.append(TEST1)
    tests = xut.driver().fetch_tests(criteria=crit)
    assert {t.name for t in tests} == {f"{TEST0}:1"} | test1_prmmtn_names

    crit.fuzzy_exclude_names = {"t1"}
    tests = xut.driver().fetch_tests(criteria=crit)
    assert {t.name for t in tests} == {f"{TEST0}:1"}

    crit.fuzzy_exclude_names.clear()
    crit.fuzzy_names = ["t1"]
    tests = xut.driver().fetch_tests(criteria=crit)
    assert {t.name for t in tests} == {f"{TEST0}:1"} | test1_prmmtn_names

    crit.exclude_names = {f"{TEST1}:1"}
    tests = xut.driver().fetch_tests(criteria=crit)
    assert {t.name for t in tests} == {f"{TEST0}:1"} | test1_prmmtn_names - {f"{TEST1}:1"}


def test_get_groups(xut: XeetUnittest):
    xut.add_test(TEST0, groups=[GROUP0])
    xut.add_test(TEST1, groups=[GROUP1])
    xut.add_test(TEST2, groups=[GROUP2], save=True)

    assert set(xut.driver().all_groups) == {GROUP0, GROUP1, GROUP2}
