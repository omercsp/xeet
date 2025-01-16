from ut import pytest, ref_str
from xeet.common import (text_file_tail, XeetVars, XeetNoSuchVarException,
                         XeetRecursiveVarException, XeetBadVarNameException, filter_str,
                         StrFilterData, validate_str, validate_types)
from xeet.core.resource import ResourcePool, ResourceModel, Resource
from typing import Any
import tempfile
import os


_FILE_CONTENT = """
line00
line01
line02
line03
line04
line05
line06
line07

line08
line09
""".strip()


@pytest.fixture
def temp_file_with_content():
    #  Pytest fixture to create a temporary file with predefined content
    #  and ensure it's cleaned up after the test.
    tmpfile = tempfile.NamedTemporaryFile(mode="w", delete=False)
    tmpfile.write(_FILE_CONTENT)
    tmpfile.close()
    file_path = tmpfile.name
    file_size = os.path.getsize(file_path)
    yield file_path, file_size
    os.remove(file_path)


def _os_str(s):
    #  Helper to handle OS-specific line endings
    return s.replace("\n", os.linesep)


def test_text_file_tail(temp_file_with_content):
    file_path, file_size = temp_file_with_content
    os_content = _os_str(_FILE_CONTENT)

    assert text_file_tail(file_path, 1, file_size) == _os_str("line09")
    assert text_file_tail(file_path, 2, file_size) == _os_str("line08\nline09")
    assert text_file_tail(file_path, 3, file_size) == _os_str("\nline08\nline09")
    assert text_file_tail(file_path, 4, file_size) == _os_str("line07\n\nline08\nline09")
    assert text_file_tail(file_path, 11, file_size) == os_content
    assert text_file_tail(file_path, 15, file_size) == os_content
    assert text_file_tail(file_path, 1, 1) == _os_str("9")
    assert text_file_tail(file_path, 5, 3) == _os_str("e09")
    assert text_file_tail(file_path, 5, 13) == os_content[-13:]
    assert text_file_tail(file_path, 5, 14) == os_content[-14:]
    assert text_file_tail(file_path, 5, 15) == os_content[-15:]
    assert text_file_tail(file_path, 5, 16) == os_content[-16:]

    with pytest.raises(ValueError):
        text_file_tail(file_path, 0, 1000)
    with pytest.raises(ValueError):
        text_file_tail(file_path, -1)


def test_xeet_vars_simple():
    xvars = XeetVars({"var1": "value1", "var2": 5})
    assert xvars.expand(ref_str("var1")) == "value1"
    assert xvars.expand(ref_str("var2")) == 5
    with pytest.raises(XeetNoSuchVarException):
        xvars.expand(ref_str("var3"))

    ref = ref_str("var1")
    assert xvars.expand(f"_{ref}_") == f"_{ref}_"
    assert xvars.expand(f"${ref}") == f"{ref}"  # check escaped $

    xvars.set_vars({"l0": ["a", "b", "c"]})
    xvars.set_vars({"l1": ["a", "{var1}", ref_str("var2")]})
    xvars.set_vars({"d0": {"a": 1, "b": 2, "c": 3}})
    xvars.set_vars({"d1": {"a": 1, "b": ref_str("var2"), "c": ref_str("l1")}})
    assert xvars.expand(ref_str("l0")) == ["a", "b", "c"]
    assert xvars.expand(ref_str("l1")) == ["a", "value1", 5]
    assert xvars.expand(ref_str("d0")) == {"a": 1, "b": 2, "c": 3}

    expanded_d1 = xvars.expand(ref_str("d1"))
    assert expanded_d1 == {"a": 1, "b": 5, "c": ["a", "value1", 5]}


def test_invalid_var_name():
    xvars = XeetVars()
    with pytest.raises(XeetBadVarNameException):
        xvars.set_vars({"bad name": "value"})
    with pytest.raises(XeetBadVarNameException):
        xvars.set_vars({" bad name": "value"})
    with pytest.raises(XeetBadVarNameException):
        xvars.set_vars({" bad name ": "value"})
    with pytest.raises(XeetBadVarNameException):
        xvars.set_vars({"bad name ": "value"})
    with pytest.raises(XeetBadVarNameException):
        xvars.set_vars({"bad.name": "value"})
    with pytest.raises(XeetBadVarNameException):
        xvars.set_vars({"bad-name": "value"})
    with pytest.raises(XeetBadVarNameException):
        xvars.set_vars({"bad?name": "value"})
    with pytest.raises(XeetBadVarNameException):
        xvars.set_vars({"0bad_name": "value"})
    with pytest.raises(XeetBadVarNameException):
        xvars.set_vars({"": "value"})
    with pytest.raises(XeetBadVarNameException):
        xvars.set_vars({"  ": "value"})


def test_xeet_vars_string_literals():
    xvars = XeetVars({"ROOT": "/tmp/xxx"})
    assert xvars.expand("{ROOT}/abc") == "/tmp/xxx/abc"

    xvars = XeetVars({"var1": "value1", "var2": "value2"})
    assert xvars.expand("{var1}") == "value1"
    assert xvars.expand("_{var1}_") == "_value1_"
    assert xvars.expand("{var1}_{var2}") == "value1_value2"

    with pytest.raises(XeetNoSuchVarException):
        xvars.expand("{var3}")  # unknown var

    xvars = XeetVars({
        "var1": "value1",
        "var2": "{var1} value2",
    })

    assert xvars.expand("{var1}") == "value1"
    assert xvars.expand("{var2}") == "value1 value2"
    assert xvars.expand("{var2}_{var1}") == "value1 value2_value1"

    xvars = XeetVars({
        "var1": "base",
        "var2": "{var1} value2",
        "var3": "{var1} value3",
        "var4": "{var2} {var3}",
    })
    assert xvars.expand("{var4}") == "base value2 base value3"

    xvars = XeetVars({
        "var1": "value1",
    })
    assert xvars.expand("{{var1}") == "{value1"
    with pytest.raises(XeetNoSuchVarException):
        xvars.expand("{{var1}}")
    assert xvars.expand("{var1}}") == "value1}"
    assert xvars.expand("{var1}}") == "value1}"
    assert xvars.expand("{var1}}") == "value1}"

    with pytest.raises(XeetBadVarNameException):
        xvars.set_vars({"bad name": "value"})
    xvars = XeetVars({
        "var1": "{var3} value1",
        "var2": "{var1} value2",
        "var3": "{var2} value3",
    })
    with pytest.raises(XeetRecursiveVarException):
        xvars.expand("{var3}")  # recursive expansion
    assert xvars.set_vars({"var1": "value1"}) is None
    assert xvars.expand("{var1}") == "value1"
    assert xvars.expand("{var3}") == "value1 value2 value3"

    assert xvars.expand(r"\{var1}") == "{var1}"
    assert xvars.expand(r"\\{var1}") == r"\\value1"
    assert xvars.expand(r"\\\t{var1}") == r"\\\tvalue1"
    assert xvars.expand(r"\\\t{var1}\\{var1}_\{var1}  \\\\{var2}\\\n{{var1}") == \
           r"\\\tvalue1\\value1_{var1}  \\\\value1 value2\\\n{value1"

    xvars = XeetVars({
        "var1": "value1",
        "var2": "var1",
    })
    xvars.expand("{{var2}}")
    assert xvars.expand("{{var2}}") == "value1"

    xvars = XeetVars({
        "var1": "value1",
        "var2": "{var1}",
    })
    assert xvars.expand(r"\{{var2}}") == "{value1}"
    with pytest.raises(XeetNoSuchVarException):
        xvars.expand("{{var2}}")


def test_xeet_vars_scopes():
    xvars0 = XeetVars({"var1": "value1", "var2": 5})
    xvars1 = XeetVars({"var1": "value2", "var3": 10}, xvars0)
    xvars2 = XeetVars({"var1": "value3", "var4": 15}, xvars1)

    assert xvars0.expand(ref_str("var1")) == "value1"
    assert xvars1.expand(ref_str("var1")) == "value2"
    assert xvars2.expand(ref_str("var1")) == "value3"

    assert xvars0.expand(ref_str("var2")) == 5
    assert xvars1.expand(ref_str("var2")) == 5
    assert xvars2.expand(ref_str("var2")) == 5

    with pytest.raises(XeetNoSuchVarException):
        xvars0.expand(ref_str("var3"))
    assert xvars1.expand(ref_str("var3")) == 10
    assert xvars2.expand(ref_str("var3")) == 10

    with pytest.raises(XeetNoSuchVarException):
        xvars0.expand(ref_str("var4"))
    with pytest.raises(XeetNoSuchVarException):
        xvars1.expand(ref_str("var4"))
    assert xvars2.expand(ref_str("var4")) == 15
    with pytest.raises(XeetNoSuchVarException):
        xvars0.expand(ref_str("var4"))

    with pytest.raises(XeetNoSuchVarException):
        xvars0.expand(ref_str("varx"))
    with pytest.raises(XeetNoSuchVarException):
        xvars1.expand(ref_str("varx"))
    with pytest.raises(XeetNoSuchVarException):
        xvars2.expand(ref_str("varx"))


def test_xeet_vars_path():
    xvars = XeetVars({
        "var1": {
            "var2": {
                "var3": 5,
            },
        },
        "var2": [{"field": 5}, {"field": 10}]
    })

    assert xvars.expand(ref_str("var1.var2.var3")) == 5
    assert xvars.expand(ref_str("var1.['var2']['var3']")) == 5
    assert xvars.expand(ref_str("var1.['var2'].var3")) == 5
    assert xvars.expand("{var1.var2.var3}") == "5"
    with pytest.raises(XeetNoSuchVarException):
        xvars.expand(ref_str("var1.var2.var4"))
    with pytest.raises(XeetNoSuchVarException):
        xvars.expand(ref_str("var1.var2.var4"))
    with pytest.raises(XeetNoSuchVarException):
        xvars.expand(ref_str("var1.var2.var3.var4"))
    assert xvars.expand(ref_str("var2.$[0].field")) == 5
    assert xvars.expand(ref_str("var2.$[1].field")) == 10
    with pytest.raises(XeetNoSuchVarException):
        xvars.expand(ref_str("var2.$[3].field"))

    xvars = XeetVars({"d": {"x": 1, "y": 2}, "v": "{d.x}"})
    assert xvars.expand(ref_str("d.x")) == 1
    assert xvars.expand(ref_str("v")) == "1"
    assert xvars.expand("{v}") == "1"


def test_value_validations():
    class A:
        def __init__(self, value=None):
            self.value = value
        pass

    class B(A):
        pass

    class C:
        pass

    assert validate_types(5, [int]) is True
    assert validate_types(5, [int, float]) is True
    assert validate_types(5, [float, int]) is True
    assert validate_types(5, [float]) is False
    assert validate_types(5, [str]) is False
    assert validate_types(A(), [A]) is True
    assert validate_types(A(), [B]) is False
    assert validate_types(B(), [B]) is True
    assert validate_types(B(), [A]) is True
    assert validate_types(B(), [A, C]) is True

    assert validate_types(5, {int: lambda x: x > 0, float: None}) is True
    assert validate_types(5, {int: lambda x: x < 0, float: None}) is False
    assert validate_types(B(), {A: lambda x: x.value is None}) is True

    assert validate_str("abc") is True
    assert validate_str("123") is True
    assert validate_str("123", max_len=2) is False
    assert validate_str("") is True
    assert validate_str("", min_len=1) is False
    assert validate_str(" ", min_len=1) is True
    assert validate_str(" ", min_len=1, strip=True) is False

    assert validate_str("abc", regex="[a-z]{3}") is True
    assert validate_str(5) is False
    assert validate_str([]) is False


def test_filter_string():
    s = "abc def ghi jkl def"
    filter0 = StrFilterData(from_str="def", to_str="xyz")
    assert filter_str(s, [filter0]) == "abc xyz ghi jkl xyz"

    filter1 = StrFilterData(from_str="jkl", to_str="123")
    assert filter_str(s, [filter0, filter1]) == "abc xyz ghi 123 xyz"

    filter2 = StrFilterData(from_str="[a-z]{3}", to_str="***", regex=True)
    assert filter_str(s, [filter2]) == "*** *** *** *** ***"
    assert filter_str(s, [filter1, filter2]) == "*** *** *** 123 ***"

    filter3 = StrFilterData(from_str="[a-z]{3}", to_str="***")
    assert filter_str(s, [filter3]) == s


def test_resource_pool():
    def assert_resource(r: list[Resource], values: list[Any]):
        assert len(r) == len(values)
        for i, v in enumerate(r):
            assert v.taken
            assert v.value == values[i]

    resource_models: list[ResourceModel] = [
            ResourceModel(**{"value": 1, "name": "r1"}),
            ResourceModel(**{"value": 2, "name": "r2"}),
            ResourceModel(**{"value": 3, "name": "r3"}),
            ResourceModel(**{"value": 4, "name": "r4"}),
            ResourceModel(**{"value": 5, "name": "r5"})
        ]
    pool = ResourcePool("pool1", resource_models)
    ra = pool.obtain()

    rb = pool.obtain()
    rc = pool.obtain()
    rd = pool.obtain()
    re = pool.obtain()
    rf = pool.obtain()
    assert pool.free_count() == 0
    assert_resource(ra, [1])
    assert_resource(rb, [2])
    assert_resource(rc, [3])
    assert_resource(rd, [4])
    assert_resource(re, [5])
    assert_resource(rf, [])

    for r in ra + rb + rc + rd + re:
        r.release()
    assert pool.free_count() == 5

    rf = pool.obtain(5)
    assert_resource(rf, [1, 2, 3, 4, 5])

    assert pool.free_count() == 0
    for r in rf:
        r.release()
    assert pool.free_count() == 5

    ra = pool.obtain(["r3"])
    assert_resource(ra, [3])
    assert pool.free_count() == 4
    rb = pool.obtain(["r3"])
    assert_resource(rb, [])
    assert pool.free_count() == 4
    rb = pool.obtain(["r4", "r5"])
    assert_resource(rb, [4, 5])
    assert pool.free_count() == 2
    rc = pool.obtain(["r1", "r2", "r4", "r5"])
    assert_resource(rc, [])
    assert pool.free_count() == 2
    for r in rb:
        r.release()

    rc = pool.obtain(["r1", "r2", "r4", "r5"])
    assert_resource(rc, [1, 2, 4, 5])
    assert pool.free_count() == 0
