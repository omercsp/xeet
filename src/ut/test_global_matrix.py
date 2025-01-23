from ut import *
from ut.ut_dummy_defs import *
from xeet import XeetException


def test_global_matrix_support(xut: XeetUnittest):
    values = ["a", "b", "c"]
    xut.add_matrix("m0", values, reset=True)
    step_desc = gen_dummy_step_desc(
        dummy_val0="{m0}",
        dummy_val1="{XEET_MATRIX_INDEX} {XEET_MATRIX_COUNT} {XEET_MATRIX_PERMUTATION.m0}")
    xut.add_test(TEST0, run=[step_desc], save=True)
    run_result = xut.run_tests()

    assert len(run_result.iter_results) == 1
    mtrx_results = run_result.iter_results[0].mtrx_results
    assert len(mtrx_results) == 3

    expected_step = gen_dummy_step_result(step_desc)
    expected = gen_test_result(status=PASSED_TEST_STTS, main_results=[expected_step])
    xut.update_test_res_test(expected, TEST0)
    for i, v in enumerate(values):
        expected_step.dummy_val0 = v
        expected_step.dummy_val1 = f"{i} 3 {v}"
        assert TEST0 in mtrx_results[i].results
        assert_test_results_equal(mtrx_results[i].results[TEST0], expected)

    values0 = ["a", "b", "c"]
    values1 = [1, 2, 3]
    xut.add_matrix("m0", values0, reset=True)
    xut.add_matrix("m1", values1)
    step_desc = gen_dummy_step_desc(dummy_val0="{m0} {m1}")
    xut.add_test(TEST0, run=[step_desc], save=True)
    run_result = xut.run_tests()

    assert len(run_result.iter_results) == 1
    assert len(run_result.iter_results[0].mtrx_results) == 9


def test_global_matrix_var_conflict(xut: XeetUnittest):
    values = ["a", "b", "c"]
    xut.add_var("m0", "var", reset=True)
    xut.add_matrix("m0", values)
    step_desc = gen_dummy_step_desc(dummy_val0="{m0}")
    xut.add_test(TEST0, run=[step_desc], save=True)
    with pytest.raises(XeetException):
        xut.run_tests()
