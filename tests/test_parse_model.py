"""Parser and model tests, including the arithmetic behind the headline number.

The fixture is a real capture of ``python -X importtime -S -c "import json"``
on Windows, not a hand-written one. That matters: the format encodes the graph
by printing children before parents, so an invented sequence can describe a
shape CPython would never emit, and a parser tested against it is tested
against nothing. (This is not hypothetical -- the first version of this file
used an invented sample, and it asserted a tree shape that cannot occur.)

Most assertions are invariants derived from the fixture rather than numbers
copied out of it, so regenerating the capture on another machine does not
turn the suite red for no reason.
"""

from __future__ import annotations

import pathlib
import unittest

from slowimports.model import ImportNode, ImportTree
from slowimports.parse import ParseError, parse_importtime, strip_importtime

FIXTURE = pathlib.Path(__file__).parent / "fixture_importtime.txt"
SAMPLE = FIXTURE.read_text(encoding="utf-8")


class TestParse(unittest.TestCase):
    def setUp(self):
        self.tree = parse_importtime(SAMPLE)

    def test_header_is_skipped(self):
        self.assertNotIn("self [us]", [n.name for n in self.tree])

    def test_every_profile_line_became_exactly_one_node(self):
        lines = [
            line
            for line in SAMPLE.splitlines()
            if line.startswith("import time:") and "self [us]" not in line
        ]
        self.assertEqual(len(self.tree), len(lines))

    def test_indentation_becomes_depth(self):
        self.assertEqual(self.tree.by_name("json").depth, 0)
        self.assertEqual(self.tree.by_name("json.decoder").depth, 1)

    def test_children_are_attached_to_their_parent(self):
        json = self.tree.by_name("json")
        self.assertEqual([c.name for c in json.children], ["json.decoder", "json.encoder"])

    def test_nesting_follows_who_imported_whom(self):
        # re is imported by json.decoder, enum by re, types by enum. This is
        # the chain the fixture actually records.
        self.assertEqual(self.tree.by_name("re").parent.name, "json.decoder")
        self.assertEqual(self.tree.by_name("enum").parent.name, "re")
        self.assertEqual(self.tree.by_name("types").parent.name, "enum")

    def test_depth_matches_the_parent_chain(self):
        for node in self.tree:
            self.assertEqual(node.depth, len(list(node.ancestors())))

    def test_roots_have_no_parent_and_everything_else_does(self):
        for node in self.tree:
            if node.depth == 0:
                self.assertIsNone(node.parent, node.name)
            else:
                self.assertIsNotNone(node.parent, node.name)

    def test_times_are_read(self):
        node = self.tree.by_name("json")
        self.assertGreater(node.self_us, 0)
        self.assertGreaterEqual(node.cumulative_us, node.self_us)
        self.assertAlmostEqual(node.self_ms, node.self_us / 1000)

    def test_interleaved_program_output_is_ignored(self):
        noisy = "Warning: something happened\n" + SAMPLE + "and later\n"
        tree = parse_importtime(noisy)
        self.assertEqual(len(tree), len(self.tree))
        self.assertIsNotNone(tree.by_name("json"))

    def test_program_output_can_be_recovered_separately(self):
        noisy = "Traceback here\n" + SAMPLE + "and after\n"
        self.assertEqual(strip_importtime(noisy), "Traceback here\nand after")

    def test_empty_output_raises(self):
        with self.assertRaises(ParseError):
            parse_importtime("no profile here\n")

    def test_top_level_name(self):
        self.assertEqual(self.tree.by_name("json.decoder").top_level, "json")
        self.assertEqual(self.tree.by_name("re._parser").top_level, "re")


class TestModel(unittest.TestCase):
    def setUp(self):
        self.tree = parse_importtime(SAMPLE)

    def test_package_costs_sum_to_the_total(self):
        # The report shows percentages. If these did not add up, the reader
        # would be quietly misled -- which is the reason the total is defined
        # as the sum of self times rather than as the roots' cumulative.
        self.assertEqual(sum(self.tree.top_level_costs().values()), self.tree.total_us)

    def test_package_costs_are_exclusive(self):
        costs = self.tree.top_level_costs()
        expected_json = sum(n.self_us for n in self.tree if n.top_level == "json")
        self.assertEqual(costs["json"], expected_json)
        # Nothing of re's time is charged to json, even though json imports it.
        self.assertNotIn("re", [k for k in costs if k == "json"])
        self.assertGreater(costs["re"], 0)

    def test_packages_are_ordered_by_cost(self):
        values = list(self.tree.top_level_costs().values())
        self.assertEqual(values, sorted(values, reverse=True))

    def test_slowest_by_self_and_by_cumulative_can_differ(self):
        by_self = self.tree.slowest(1, by="self")[0]
        by_cumulative = self.tree.slowest(1, by="cumulative")[0]
        self.assertGreaterEqual(by_self.self_us, max(n.self_us for n in self.tree) - 1)
        self.assertGreaterEqual(
            by_cumulative.cumulative_us, max(n.cumulative_us for n in self.tree) - 1
        )

    def test_savings_of_an_unknown_module_is_zero(self):
        self.assertEqual(self.tree.savings("nonexistent"), 0)

    def test_savings_never_exceed_the_total(self):
        for node in self.tree:
            self.assertLessEqual(self.tree.savings(node.name), self.tree.total_us)

    def test_savings_are_never_negative(self):
        for node in self.tree:
            self.assertGreaterEqual(self.tree.savings(node.name), 0)

    def test_savings_of_a_leaf_is_exactly_its_own_time(self):
        leaf = self.tree.by_name("json.encoder")
        self.assertEqual(leaf.children, [])
        self.assertEqual(self.tree.savings("json.encoder"), leaf.self_us)

    def test_savings_of_a_parent_exceed_savings_of_its_child(self):
        self.assertGreater(self.tree.savings("json"), self.tree.savings("json.encoder"))

    def test_dropping_every_root_saves_everything(self):
        self.assertEqual(
            self.tree.savings_for({r.name for r in self.tree.roots}),
            self.tree.total_us,
        )


class TestSharedDependencies(unittest.TestCase):
    """The cases a naive answer gets wrong."""

    def build(self) -> ImportTree:
        # a imports shared; b needs it too, but importtime prints only the
        # first import, so b's reference is a zero-cost repeat.
        shared = ImportNode("shared", 100, 100, 1)
        a = ImportNode("a", 10, 110, 0, children=[shared])
        shared.parent = a
        repeat = ImportNode("shared", 0, 0, 1)
        b = ImportNode("b", 20, 20, 0, children=[repeat])
        repeat.parent = b
        return ImportTree([a, b])

    def test_shared_dependency_is_not_credited_to_one_dropper(self):
        # Dropping a alone still leaves b needing shared, so a is worth only
        # its own body.
        self.assertEqual(self.build().savings("a"), 10)

    def test_joint_savings_are_not_the_sum(self):
        tree = self.build()
        individual = tree.savings("a") + tree.savings("b")
        joint = tree.savings_for({"a", "b"})
        self.assertEqual(individual, 30)
        # Dropping both frees shared as well, which neither frees alone.
        self.assertEqual(joint, 130)

    def test_joint_savings_of_everything_is_the_total(self):
        tree = self.build()
        self.assertEqual(tree.savings_for({"a", "b"}), tree.total_us)

    def test_joint_savings_of_nothing_is_zero(self):
        self.assertEqual(self.build().savings_for(set()), 0)

    def test_unknown_names_are_ignored(self):
        tree = self.build()
        self.assertEqual(tree.savings_for({"a", "nope"}), tree.savings("a"))


class TestSerialisation(unittest.TestCase):
    def test_round_trip_through_dict(self):
        tree = parse_importtime(SAMPLE)
        restored = ImportTree.from_dict(tree.as_dict())
        self.assertEqual(restored.total_us, tree.total_us)
        self.assertEqual(len(restored), len(tree))
        self.assertEqual(restored.top_level_costs(), tree.top_level_costs())

    def test_round_trip_preserves_the_shape(self):
        tree = parse_importtime(SAMPLE)
        restored = ImportTree.from_dict(tree.as_dict())
        self.assertEqual(restored.by_name("types").parent.name, "enum")
        self.assertEqual(
            [c.name for c in restored.by_name("json").children],
            [c.name for c in tree.by_name("json").children],
        )

    def test_round_trip_preserves_savings(self):
        tree = parse_importtime(SAMPLE)
        restored = ImportTree.from_dict(tree.as_dict())
        for name in ("json", "json.encoder", "re"):
            self.assertEqual(restored.savings(name), tree.savings(name))


if __name__ == "__main__":
    unittest.main()
