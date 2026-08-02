"""Analyzer tests.

These are the ones that matter most. A false positive here tells someone to
move an import that is needed at import time, and they find out through a
``NameError`` on a code path they did not test. So the bulk of this file is
cases that must *not* be reported.
"""

from __future__ import annotations

import unittest

from slowimports.analyze import analyze_source, rank_deferrable


def deferrable(source: str) -> set[str]:
    return {b.bound_name for b in analyze_source(source) if b.deferrable}


def bindings(source: str) -> dict[str, object]:
    return {b.bound_name: b for b in analyze_source(source)}


class TestDeferrable(unittest.TestCase):
    def test_used_only_in_a_function(self):
        self.assertEqual(
            deferrable("import json\ndef f():\n    return json.dumps({})\n"),
            {"json"},
        )

    def test_used_only_in_a_method(self):
        source = "import json\nclass A:\n    def f(self):\n        return json.dumps({})\n"
        self.assertEqual(deferrable(source), {"json"})

    def test_used_only_in_a_nested_function(self):
        source = (
            "import json\n"
            "def outer():\n"
            "    def inner():\n"
            "        return json\n"
            "    return inner\n"
        )
        self.assertEqual(deferrable(source), {"json"})

    def test_used_only_in_a_lambda_body(self):
        self.assertEqual(deferrable("import json\nf = lambda: json.dumps({})\n"), {"json"})

    def test_from_import(self):
        source = "from decimal import Decimal\ndef f():\n    return Decimal(1)\n"
        self.assertEqual(deferrable(source), {"Decimal"})

    def test_aliased_import(self):
        source = "import numpy as np\ndef f():\n    return np.zeros(3)\n"
        self.assertEqual(deferrable(source), {"np"})

    def test_async_function_body(self):
        source = "import json\nasync def f():\n    return json.dumps({})\n"
        self.assertEqual(deferrable(source), {"json"})

    def test_annotation_with_future_import(self):
        source = (
            "from __future__ import annotations\n"
            "import numpy\n"
            "def f(x: numpy.ndarray) -> numpy.ndarray:\n"
            "    return numpy.zeros(3)\n"
        )
        self.assertEqual(deferrable(source), {"numpy"})

    def test_module_attributes_are_reported_by_top_level(self):
        source = "import xml.etree.ElementTree as ET\ndef f():\n    return ET.parse('x')\n"
        found = bindings(source)["ET"]
        self.assertEqual(found.module, "xml.etree.ElementTree")
        self.assertTrue(found.deferrable)


class TestNotDeferrable(unittest.TestCase):
    """Every case here would break at run time if it were reported."""

    def test_module_level_call(self):
        self.assertEqual(
            deferrable("import json\nX = json.dumps({})\ndef f():\n    return json\n"),
            set(),
        )

    def test_class_body_runs_during_import(self):
        self.assertEqual(deferrable("import json\nclass A:\n    D = json.dumps({})\n"), set())

    def test_decorator(self):
        self.assertEqual(
            deferrable("import functools\n@functools.cache\ndef f():\n    pass\n"), set()
        )

    def test_base_class(self):
        self.assertEqual(deferrable("import enum\nclass C(enum.Enum):\n    A = 1\n"), set())

    def test_default_argument(self):
        self.assertEqual(
            deferrable("import json\ndef f(x=json.dumps({})):\n    return x\n"), set()
        )

    def test_keyword_only_default(self):
        self.assertEqual(
            deferrable("import json\ndef f(*, x=json.dumps({})):\n    return x\n"), set()
        )

    def test_lambda_default_is_evaluated_at_import(self):
        self.assertEqual(deferrable("import json\nf = lambda x=json.dumps({}): x\n"), set())

    def test_annotation_without_future_import(self):
        source = "import numpy\ndef f(x: numpy.ndarray):\n    return 1\n"
        self.assertEqual(deferrable(source), set())

    def test_return_annotation_without_future_import(self):
        source = "import numpy\ndef f() -> numpy.ndarray:\n    return 1\n"
        self.assertEqual(deferrable(source), set())

    def test_module_level_annotated_assignment(self):
        source = "import decimal\nX: decimal.Decimal = 1\n"
        self.assertEqual(deferrable(source), set())

    def test_module_level_conditional(self):
        source = "import sys\nif sys.version_info > (3,):\n    pass\ndef f():\n    return sys\n"
        self.assertEqual(deferrable(source), set())

    def test_rebound_later(self):
        source = "import json\ndef f():\n    return json\njson = None\n"
        self.assertEqual(deferrable(source), set())

    def test_declared_global_in_a_function(self):
        source = "import json\ndef f():\n    global json\n    json = None\n"
        self.assertEqual(deferrable(source), set())

    def test_imported_twice_is_ambiguous(self):
        source = "import json\nimport json\ndef f():\n    return json\n"
        self.assertEqual(deferrable(source), set())

    def test_star_import_is_never_reported(self):
        source = "from os.path import *\ndef f():\n    return join('a', 'b')\n"
        self.assertEqual(deferrable(source), set())

    def test_future_import_is_a_compiler_directive(self):
        source = "from __future__ import annotations\ndef f():\n    return 1\n"
        self.assertEqual(analyze_source(source), [])

    def test_relative_import_is_left_alone(self):
        source = "from . import sibling\ndef f():\n    return sibling\n"
        self.assertEqual(deferrable(source), set())

    def test_import_already_inside_a_function(self):
        source = "def f():\n    import json\n    return json\n"
        self.assertEqual(analyze_source(source), [])


class TestUnused(unittest.TestCase):
    def test_unused_is_flagged_separately(self):
        found = bindings("import json\ndef f():\n    return 1\n")["json"]
        self.assertTrue(found.unused)
        self.assertFalse(found.deferrable)

    def test_used_import_is_not_unused(self):
        found = bindings("import json\ndef f():\n    return json\n")["json"]
        self.assertFalse(found.unused)


class TestRanking(unittest.TestCase):
    def test_sorted_by_saving_and_filtered_by_threshold(self):
        source = "import cheap\nimport pricey\ndef f():\n    return cheap, pricey\n"
        costs = {"cheap": 200, "pricey": 50_000}
        ranked = rank_deferrable(
            analyze_source(source), lambda m: costs.get(m, 0), minimum_us=1000
        )
        self.assertEqual([d.binding.module for d in ranked], ["pricey"])
        self.assertAlmostEqual(ranked[0].saving_ms, 50.0)

    def test_syntax_error_propagates(self):
        with self.assertRaises(SyntaxError):
            analyze_source("def (:\n")


if __name__ == "__main__":
    unittest.main()
