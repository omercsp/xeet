from ut import unittest, ref_str
from xeet.common import (text_file_tail, XeetVars, XeetNoSuchVarException,
                         XeetRecursiveVarException, XeetBadVarNameException, filter_str,
                         StrFilterData)
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
        #  Create a temporary file with the content
        tmpfile = tempfile.NamedTemporaryFile(mode="w", delete=False)
        tmpfile.write(_FILE_CONTENT)
        tmpfile.close()
        file_size = os.path.getsize(tmpfile.name)
        file_path = tmpfile.name

        #  _compare(1, file_size, "line09")
        self.assertEqual(text_file_tail(file_path, 1, file_size), "line09")
        self.assertEqual(text_file_tail(file_path, 2, file_size), "line08\nline09")
        self.assertEqual(text_file_tail(file_path, 3, file_size), "\nline08\nline09")
        self.assertEqual(text_file_tail(file_path, 4, file_size), "line07\n\nline08\nline09")
        self.assertEqual(text_file_tail(file_path, 11, file_size), _FILE_CONTENT)
        self.assertEqual(text_file_tail(file_path, 15, file_size), _FILE_CONTENT)
        self.assertEqual(text_file_tail(file_path, 1, 1), "9")
        self.assertEqual(text_file_tail(file_path, 5, 3), "e09")
        self.assertEqual(text_file_tail(file_path, 5, 13), "line08\nline09")
        self.assertEqual(text_file_tail(file_path, 5, 14), "\nline08\nline09")
        self.assertEqual(text_file_tail(file_path, 5, 15), "\n\nline08\nline09")
        self.assertEqual(text_file_tail(file_path, 5, 16), "7\n\nline08\nline09")

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
