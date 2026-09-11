"""Rewrite tests. A false positive here is a NameError waiting to happen."""

from __future__ import annotations

import os
import tempfile
import unittest

from slowimports.analyze import analyze_source
from slowimports.apply import apply_path, apply_source, plan_apply
from slowimports.rewrite import RewriteError, unified_diff, writable_script


class TestApply(unittest.TestCase):
    def test_moves_function_only_import(self):
        src = "import csv\n\ndef read(path):\n    return csv.reader(path)\n"
        out = apply_source(src)
        self.assertNotIn("import csv", out.split("def")[0])
        self.assertIn("    import csv\n", out)
        compile(out, "<apply>", "exec")

    def test_inserts_into_each_using_function(self):
        src = (
            "import json\n"
            "def a():\n"
            "    return json.dumps({})\n"
            "def b():\n"
            "    return json.loads('{}')\n"
        )
        out = apply_source(src)
        self.assertEqual(out.count("import json"), 2)
        self.assertIn("def a():\n    import json\n", out)
        self.assertIn("def b():\n    import json\n", out)

    def test_leaves_import_time_use_alone(self):
        src = "import json\nX = json.dumps({})\ndef f():\n    return json\n"
        self.assertEqual(apply_source(src), src)

    def test_splits_multi_name_import_line(self):
        src = "import csv, json\n\ndef f():\n    return json.dumps({})\n"
        out = apply_source(src)
        header = out.split("def")[0]
        self.assertEqual(header.strip(), "import csv")
        self.assertIn("    import json\n", out)
        compile(out, "<apply>", "exec")

    def test_moves_both_names_off_a_shared_line(self):
        src = "import csv, json\n\ndef f():\n    return csv.reader, json.dumps\n"
        out = apply_source(src)
        self.assertNotIn("import csv, json", out)
        self.assertIn("    import csv\n", out)
        self.assertIn("    import json\n", out)
        compile(out, "<apply>", "exec")

    def test_after_docstring(self):
        src = 'import csv\ndef read(path):\n    """Load rows."""\n    return csv.reader(path)\n'
        out = apply_source(src)
        self.assertIn('    """Load rows."""\n    import csv\n', out)

    def test_from_import(self):
        src = "from decimal import Decimal\n\ndef money(x):\n    return Decimal(str(x))\n"
        out = apply_source(src)
        self.assertNotIn("from decimal import Decimal", out.split("def")[0])
        self.assertIn("    from decimal import Decimal\n", out)

    def test_skips_commented_import(self):
        src = "import json  # keep\n\ndef f():\n    return json.dumps({})\n"
        self.assertEqual(apply_source(src), src)

    def test_skips_one_line_function(self):
        src = "import json\ndef f(): return json.dumps({})\n"
        self.assertEqual(apply_source(src), src)

    def test_nested_function_gets_the_import(self):
        src = (
            "import json\n"
            "def outer():\n"
            "    def inner():\n"
            "        return json.dumps({})\n"
            "    return inner\n"
        )
        out = apply_source(src)
        self.assertIn("        import json\n", out)
        self.assertNotIn("    import json\n    def inner", out)

    def test_unified_diff_headers(self):
        src = "import json\n\ndef f():\n    return json.dumps({})\n"
        out = apply_source(src)
        patch = unified_diff(src, out, "app.py")
        self.assertIn("--- a/app.py", patch)
        self.assertIn("+++ b/app.py", patch)
        self.assertIn("+    import json", patch)

    def test_writable_script_refuses_site_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = os.path.join(tmp, "site-packages")
            os.makedirs(nested)
            path = os.path.join(nested, "mod.py")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("x = 1\n")
            with self.assertRaises(RewriteError):
                writable_script(path)

    def test_writable_script_refuses_non_py(self):
        with self.assertRaises(RewriteError):
            writable_script(None)
        with self.assertRaises(RewriteError):
            writable_script("not-a-file.py")

    def test_apply_path_round_trip(self):
        src = "import json\n\ndef f():\n    return json.dumps({})\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "app.py")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(src)
            changed, text = apply_path(path)
            self.assertTrue(changed)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), text)
            compile(text, path, "exec")

    def test_plan_apply_lists_moved_names(self):
        src = "import json\n\ndef f():\n    return json.dumps({})\n"
        names = [b.bound_name for b in plan_apply(src, analyze_source(src))]
        self.assertEqual(names, ["json"])
