from ut import unittest, ref_str
from xeet.common import (text_file_tail, XeetVars, XeetNoSuchVarException, XeetInvalidVarType,
                         XeetRecursiveVarException, XeetBadVarNameException, filter_str,
                         StrFilterData)
from xeet.core.resource import ResourcePool, ResourceModel, Resource
from xeet.core.matrix import Matrix
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


class TestCommon(unittest.TestCase):
    def test_text_file_tail(self):
        def _os_str(s):
            return s.replace("\n", os.linesep)

        #  Create a temporary file with the content
        tmpfile = tempfile.NamedTemporaryFile(mode="w", delete=False)
        tmpfile.write(_FILE_CONTENT)
        tmpfile.close()
        file_size = os.path.getsize(tmpfile.name)
        file_path = tmpfile.name

        os_content = _os_str(_FILE_CONTENT)
        #  Windows line ending is '\r\n', hence 2 bytes per line
        self.assertEqual(text_file_tail(file_path, 1, file_size), _os_str("line09"))
        self.assertEqual(text_file_tail(file_path, 2, file_size), _os_str("line08\nline09"))
        self.assertEqual(text_file_tail(file_path, 3, file_size), _os_str("\nline08\nline09"))
        self.assertEqual(text_file_tail(file_path, 4, file_size),
                         _os_str("line07\n\nline08\nline09"))
        self.assertEqual(text_file_tail(file_path, 11, file_size), os_content)
        self.assertEqual(text_file_tail(file_path, 15, file_size), os_content)
        self.assertEqual(text_file_tail(file_path, 1, 1), _os_str("9"))
        self.assertEqual(text_file_tail(file_path, 5, 3), _os_str("e09"))
        self.assertEqual(text_file_tail(file_path, 5, 13), os_content[-13:])
        self.assertEqual(text_file_tail(file_path, 5, 14), os_content[-14:])
        self.assertEqual(text_file_tail(file_path, 5, 15), os_content[-15:])
        self.assertEqual(text_file_tail(file_path, 5, 16), os_content[-16:])

        self.assertRaises(ValueError, text_file_tail, file_path, 0, 1000)
        self.assertRaises(ValueError, text_file_tail, file_path, -1, )

        #  delete the temporary file
        os.remove(file_path)

    def test_xeet_vars_simple(self):
        xvars = XeetVars({"var1": "value1", "var2": 5})
        self.assertEqual(xvars.expand(ref_str("var1")), "value1")
        self.assertEqual(xvars.expand(ref_str("var2")), 5)
        self.assertRaises(XeetNoSuchVarException, xvars.expand, ref_str("var3"))

        ref = ref_str("var1")
        self.assertEqual(xvars.expand(f"_{ref}_"), f"_{ref}_")
        self.assertEqual(xvars.expand(f"${ref}"), f"{ref}")  # check escaped $

        xvars.set_vars({"l0": ["a", "b", "c"]})
        xvars.set_vars({"l1": ["a", "{var1}", ref_str("var2")]})
        xvars.set_vars({"d0": {"a": 1, "b": 2, "c": 3}})
        xvars.set_vars({"d1": {"a": 1, "b": ref_str("var2"), "c": ref_str("l1")}})
        self.assertListEqual(xvars.expand(ref_str("l0")), ["a", "b", "c"])
        self.assertListEqual(xvars.expand(ref_str("l1")), ["a", "value1", 5])
        self.assertDictEqual(xvars.expand(ref_str("d0")), {"a": 1, "b": 2, "c": 3})

        expanded_d1 = xvars.expand(ref_str("d1"))
        self.assertDictEqual(expanded_d1, {"a": 1, "b": 5, "c": ["a", "value1", 5]})

    def test_invlid_var_name(self):
        xvars = XeetVars()
        self.assertRaises(XeetBadVarNameException, xvars.set_vars, {"bad name": "value"})
        self.assertRaises(XeetBadVarNameException, xvars.set_vars, {"bad.name": "value"})
        self.assertRaises(XeetBadVarNameException, xvars.set_vars, {"bad name": "value"})
        self.assertRaises(XeetBadVarNameException, xvars.set_vars, {"bad-name": "value"})
        self.assertRaises(XeetBadVarNameException, xvars.set_vars, {"bad?name": "value"})
        self.assertRaises(XeetBadVarNameException, xvars.set_vars, {"0bad_name": "value"})

    def test_xeet_vars_string_literals(self):
        xvars = XeetVars({"ROOT": "/tmp/xxx"})
        self.assertEqual(xvars.expand("{ROOT}/abc"), "/tmp/xxx/abc")

        xvars = XeetVars({"var1": "value1", "var2": "value2"})
        self.assertEqual(xvars.expand("{var1}"), "value1")
        self.assertEqual(xvars.expand("_{var1}_"), "_value1_")
        self.assertEqual(xvars.expand("{var1}_{var2}"), "value1_value2")

        self.assertRaises(XeetNoSuchVarException, xvars.expand, "{var3}")  # unknown var

        xvars = XeetVars({
            "var1": "value1",
            "var2": "{var1} value2",
        })

        self.assertEqual(xvars.expand("{var1}"), "value1")
        self.assertEqual(xvars.expand("{var2}"), "value1 value2")
        self.assertEqual(xvars.expand("{var2}_{var1}"), "value1 value2_value1")

        xvars = XeetVars({
            "var1": "base",
            "var2": "{var1} value2",
            "var3": "{var1} value3",
            "var4": "{var2} {var3}",
        })
        self.assertEqual(xvars.expand("{var4}"), "base value2 base value3")

        xvars = XeetVars({
            "var1": "value1",
        })
        self.assertEqual(xvars.expand("{{var1}"), "{value1")
        self.assertRaises(XeetNoSuchVarException, xvars.expand, "{{var1}}")
        self.assertEqual(xvars.expand("{var1}}"), "value1}")
        self.assertEqual(xvars.expand("{var1}}"), "value1}")
        self.assertEqual(xvars.expand("{var1}}"), "value1}")

        self.assertRaises(XeetBadVarNameException, xvars.set_vars, {"bad name": "value"})
        xvars = XeetVars({
            "var1": "{var3} value1",
            "var2": "{var1} value2",
            "var3": "{var2} value3",
        })
        self.assertRaises(XeetRecursiveVarException, xvars.expand, "{var3}")  # recursive expansion
        self.assertIsNone(xvars.set_vars({"var1": "value1"}))
        self.assertEqual(xvars.expand("{var1}"), "value1")
        self.assertEqual(xvars.expand("{var3}"), "value1 value2 value3")

        self.assertEqual(xvars.expand(r"\{var1}"), "{var1}")
        self.assertEqual(xvars.expand(r"\\{var1}"), r"\\value1")
        self.assertEqual(xvars.expand(r"\\\t{var1}"), r"\\\tvalue1")
        self.assertEqual(xvars.expand(r"\\\t{var1}\\{var1}_\{var1}  \\\\{var2}\\\n{{var1}"),
                         r"\\\tvalue1\\value1_{var1}  \\\\value1 value2\\\n{value1")

        xvars = XeetVars({
            "var1": "value1",
            "var2": "var1",
        })
        xvars.expand("{{var2}}")
        self.assertEqual(xvars.expand("{{var2}}"), "value1")

        xvars = XeetVars({
            "var1": "value1",
            "var2": "{var1}",
        })
        self.assertEqual(xvars.expand(r"\{{var2}}"), "{value1}")
        self.assertRaises(XeetNoSuchVarException, xvars.expand, "{{var2}}")

    def test_xeet_vars_scopes(self):
        xvars0 = XeetVars({"var1": "value1", "var2": 5})
        xvars1 = XeetVars({"var1": "value2", "var3": 10}, xvars0)
        xvars2 = XeetVars({"var1": "value3", "var4": 15}, xvars1)

        self.assertEqual(xvars0.expand(ref_str("var1")), "value1")
        self.assertEqual(xvars1.expand(ref_str("var1")), "value2")
        self.assertEqual(xvars2.expand(ref_str("var1")), "value3")

        self.assertEqual(xvars0.expand(ref_str("var2")), 5)
        self.assertEqual(xvars1.expand(ref_str("var2")), 5)
        self.assertEqual(xvars2.expand(ref_str("var2")), 5)

        self.assertRaises(XeetNoSuchVarException, xvars0.expand, ref_str("var3"))
        self.assertEqual(xvars1.expand(ref_str("var3")), 10)
        self.assertEqual(xvars2.expand(ref_str("var3")), 10)

        self.assertRaises(XeetNoSuchVarException, xvars0.expand, ref_str("var4"))
        self.assertRaises(XeetNoSuchVarException, xvars1.expand, ref_str("var4"))
        self.assertEqual(xvars2.expand(ref_str("var4")), 15)
        self.assertRaises(XeetNoSuchVarException, xvars0.expand, ref_str("var4"))

        self.assertRaises(XeetNoSuchVarException, xvars0.expand, ref_str("varx"))
        self.assertRaises(XeetNoSuchVarException, xvars1.expand, ref_str("varx"))
        self.assertRaises(XeetNoSuchVarException, xvars2.expand, ref_str("varx"))

    def test_xeet_vars_path(self):
        xvars = XeetVars({
            "var1": {
                "var2": {
                    "var3": 5,
                },
            },
            "var2": [{"field": 5}, {"field": 10}]
        })

        self.assertEqual(xvars.expand(ref_str("var1.var2.var3")), 5)
        self.assertEqual(xvars.expand(ref_str("var1.['var2']['var3']")), 5)
        self.assertEqual(xvars.expand(ref_str("var1.['var2'].var3")), 5)
        self.assertEqual(xvars.expand("{var1.var2.var3}"), "5")
        self.assertRaises(XeetNoSuchVarException, xvars.expand, ref_str("var1.var2.var4"))
        self.assertRaises(XeetNoSuchVarException, xvars.expand, ref_str("var1.var2.var4"))
        self.assertRaises(XeetNoSuchVarException, xvars.expand, ref_str("var1.var2.var3.var4"))
        self.assertEqual(xvars.expand(ref_str("var2.$[0].field")), 5)
        self.assertEqual(xvars.expand(ref_str("var2.$[1].field")), 10)
        self.assertRaises(XeetNoSuchVarException, xvars.expand, ref_str("var2.$[3].field"))

    def test_xeet_vars_type_required(self):
        xvars = XeetVars({
            "var1": "value1",
            "var2": 5,
            "var3": -1.1,
            "var4": [1, 2, 3],
            "var5": {"a": 1, "b": 2},
            "var6": True,
            "var7": None
        })
        self.assertEqual(xvars.expand(ref_str("var1"), [str]), "value1")
        self.assertEqual(xvars.expand(ref_str("var1"), [str, int]), "value1")
        self.assertRaises(XeetInvalidVarType, xvars.expand, ref_str("var1"), [int])

        self.assertEqual(xvars.expand(ref_str("var2"), [int]), 5)
        self.assertRaises(XeetInvalidVarType, xvars.expand, ref_str("var2"), [str])

        self.assertEqual(xvars.expand(ref_str("var3"), [float]), -1.1)
        self.assertRaises(XeetInvalidVarType, xvars.expand, ref_str("var3"), [int])

        self.assertEqual(xvars.expand(ref_str("var4"), [list]), [1, 2, 3])
        self.assertRaises(XeetInvalidVarType, xvars.expand, ref_str("var4"), [dict])

        self.assertEqual(xvars.expand(ref_str("var5"), [dict]), {"a": 1, "b": 2})
        self.assertRaises(XeetInvalidVarType, xvars.expand, ref_str("var5"), [list])

        self.assertEqual(xvars.expand(ref_str("var5.a"), [int]), 1)

        self.assertEqual(xvars.expand(ref_str("var6"), [bool]), True)
        self.assertRaises(XeetInvalidVarType, xvars.expand, ref_str("var6"), [list, int])

        self.assertEqual(xvars.expand(ref_str("var7"), [type(None)]), None)

        self.assertEqual(xvars.expand("{var2}", [str]), "5")
        self.assertRaises(XeetInvalidVarType, xvars.expand, "{var2}", [list, int])

    def test_filter_string(self):
        s = "abc def ghi jkl def"
        filter0 = StrFilterData(from_str="def", to_str="xyz")
        self.assertEqual(filter_str(s, [filter0]), "abc xyz ghi jkl xyz")

        filter1 = StrFilterData(from_str="jkl", to_str="123")
        self.assertEqual(filter_str(s, [filter0, filter1]), "abc xyz ghi 123 xyz")

        filter2 = StrFilterData(from_str="[a-z]{3}", to_str="***", regex=True)
        self.assertEqual(filter_str(s, [filter2]), "*** *** *** *** ***")
        self.assertEqual(filter_str(s, [filter1, filter2]), "*** *** *** 123 ***")

        filter3 = StrFilterData(from_str="[a-z]{3}", to_str="***")
        self.assertEqual(filter_str(s, [filter3]), s)

    def test_resource_pool(self):
        def assertResource(r: list[Resource], values: list[Any]):
            self.assertEqual(len(r), len(values))
            for i, v in enumerate(r):
                self.assertTrue(v.taken)
                self.assertEqual(v.value, values[i])

        def assertResourcePool(pool: ResourcePool, free: int):
            self.assertEqual(pool.free_count(), free)

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
        assertResourcePool(pool, 0)
        assertResource(ra, [1])
        assertResource(rb, [2])
        assertResource(rc, [3])
        assertResource(rd, [4])
        assertResource(re, [5])
        assertResource(rf, [])

        for r in ra + rb + rc + rd + re:
            r.release()
        assertResourcePool(pool, 5)

        rf = pool.obtain(5)
        assertResource(rf, [1, 2, 3, 4, 5])
        assertResourcePool(pool, 0)
        for r in rf:
            r.release()
        assertResourcePool(pool, 5)

        ra = pool.obtain(["r3"])
        assertResource(ra, [3])
        assertResourcePool(pool, 4)
        rb = pool.obtain(["r3"])
        assertResource(rb, [])
        assertResourcePool(pool, 4)
        rb = pool.obtain(["r4", "r5"])
        assertResource(rb, [4, 5])
        assertResourcePool(pool, 2)
        rc = pool.obtain(["r1", "r2", "r4", "r5"])
        assertResource(rc, [])
        assertResourcePool(pool, 2)
        for r in rb:
            r.release()

        rc = pool.obtain(["r1", "r2", "r4", "r5"])
        assertResource(rc, [1, 2, 4, 5])
        assertResourcePool(pool, 0)

    def test_matrix(self):
        matrix = Matrix({"a": [1, 2, 3], "b": [4, 5], "c": [6]})
        self.assertEqual(matrix.lengths, {"a": 3, "b": 2, "c": 1})
        self.assertEqual(matrix.n, 3)
        self.assertEqual(matrix.keys, ["a", "b", "c"])
        self.assertEqual(matrix.prmttns_count, 3*2*1)

        perms = list(matrix.permutations())
        self.assertEqual(len(perms), 3*2*1)
        self.assertEqual(perms[0], {"a": 1, "b": 4, "c": 6})
        self.assertEqual(perms[1], {"a": 1, "b": 5, "c": 6})
        self.assertEqual(perms[2], {"a": 2, "b": 4, "c": 6})
        self.assertEqual(perms[3], {"a": 2, "b": 5, "c": 6})
        self.assertEqual(perms[4], {"a": 3, "b": 4, "c": 6})
        self.assertEqual(perms[5], {"a": 3, "b": 5, "c": 6})
