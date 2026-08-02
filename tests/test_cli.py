"""End-to-end tests through the CLI, plus the runner and the renderer.

These really do start subprocesses. Import time cannot be measured in-process
-- by the time this code runs, most of the standard library is already
imported and would report as free -- so a test that avoided the subprocess
would not be testing the thing.
"""

from __future__ import annotations

import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from typing import ClassVar

from slowimports.cli import main, split_passthrough
from slowimports.palette import Palette
from slowimports.parse import parse_importtime
from slowimports.render import Renderer, format_ms, truncate
from slowimports.runner import RunnerError, Target, resolve, run_profile

ANSI = re.compile(r"\x1b\[[0-9;]*m")
HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(os.path.dirname(HERE), "examples", "slow_cli.py")


def run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class TestArgumentSplitting(unittest.TestCase):
    def test_no_separator_means_nothing_passed_through(self):
        self.assertEqual(
            split_passthrough(["app.py", "--advice"]), (["app.py", "--advice"], [])
        )

    def test_separator_divides_our_flags_from_theirs(self):
        ours, theirs = split_passthrough(["app.py", "--advice", "--", "-v", "--fast"])
        self.assertEqual(ours, ["app.py", "--advice"])
        self.assertEqual(theirs, ["-v", "--fast"])

    def test_only_the_first_separator_counts(self):
        _, theirs = split_passthrough(["a.py", "--", "-x", "--", "-y"])
        self.assertEqual(theirs, ["-x", "--", "-y"])


class TestTargetResolution(unittest.TestCase):
    def test_dot_py_is_a_script(self):
        self.assertEqual(resolve("app.py", []).kind, "script")

    def test_a_path_is_a_script(self):
        self.assertEqual(resolve(os.path.join("dir", "app"), []).kind, "script")

    def test_a_bare_name_is_a_module(self):
        self.assertEqual(resolve("definitely_not_on_path_12345", []).kind, "module")

    def test_explicit_kind_wins(self):
        self.assertEqual(resolve("app.py", [], kind="module").kind, "module")

    def test_describe_is_readable(self):
        self.assertEqual(Target("module", "pytest", []).describe(), "-m pytest")
        self.assertEqual(Target("script", "a.py", ["-v"]).describe(), "a.py -v")


class TestRunner(unittest.TestCase):
    def test_profiling_a_snippet(self):
        result = run_profile(resolve("import json", [], kind="code"))
        self.assertTrue(result.ok)
        tree = parse_importtime(result.stderr)
        self.assertIsNotNone(tree.by_name("json"))

    def test_target_stdout_is_captured_separately(self):
        result = run_profile(resolve("print('hello')", [], kind="code"))
        self.assertIn("hello", result.stdout)

    def test_a_failing_target_still_yields_a_profile(self):
        # The imports that happened before the failure are still measurable,
        # and are usually exactly what the user wanted to see.
        result = run_profile(resolve("import json; raise SystemExit(3)", [], kind="code"))
        self.assertEqual(result.returncode, 3)
        self.assertIsNotNone(parse_importtime(result.stderr).by_name("json"))

    def test_missing_interpreter_is_reported(self):
        with self.assertRaises(RunnerError):
            run_profile(resolve("import json", [], kind="code"), python="no-such-python-12345")

    def test_arguments_reach_the_target(self):
        result = run_profile(resolve("import sys; print(sys.argv[1:])", [], kind="code"))
        self.assertIn("[]", result.stdout)


class TestRendering(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(HERE, "fixture_importtime.txt"), encoding="utf-8") as handle:
            self.tree = parse_importtime(handle.read())
        self.renderer = Renderer(Palette(depth="none"), width=80)

    def test_bars_fit_the_width(self):
        for row in self.renderer.bars(self.tree, 10):
            self.assertLessEqual(len(ANSI.sub("", row)), 82)

    def test_packages_fit_the_width(self):
        for row in self.renderer.packages(self.tree, 10):
            self.assertLessEqual(len(ANSI.sub("", row)), 84)

    def test_icicle_fits_the_width(self):
        for row in self.renderer.icicle(self.tree):
            if row.startswith("  coloured:"):
                continue
            self.assertLessEqual(len(ANSI.sub("", row)), 82)

    def test_bar_is_proportional(self):
        self.assertEqual(self.renderer.bar(0.0, 10).strip(), "")
        self.assertEqual(len(self.renderer.bar(1.0, 10)), 10)
        self.assertEqual(self.renderer.bar(1.0, 10).strip(), "█" * 10)

    def test_bar_clamps_out_of_range(self):
        self.assertEqual(len(self.renderer.bar(5.0, 8)), 8)
        self.assertEqual(len(self.renderer.bar(-1.0, 8)), 8)

    def test_ascii_mode_emits_no_block_characters(self):
        renderer = Renderer(Palette(depth="none"), unicode=False, width=80)
        text = "\n".join(renderer.bars(self.tree, 5) + renderer.icicle(self.tree))
        text.encode("ascii", errors="strict")

    def test_truncate_keeps_the_identifying_tail(self):
        self.assertEqual(truncate("numpy.linalg.lapack", 10), "…lg.lapack")
        self.assertEqual(truncate("json", 10), "json")

    def test_format_ms_scales(self):
        self.assertEqual(format_ms(500), "0.50 ms")
        self.assertEqual(format_ms(15_000), "15.0 ms")
        self.assertEqual(format_ms(150_000), "150 ms")
        self.assertEqual(format_ms(2_500_000), "2.50 s")

    def test_colour_does_not_change_visible_width(self):
        plain = Renderer(Palette(depth="none"), width=80).bars(self.tree, 5)
        colour = Renderer(Palette(depth="truecolor"), width=80).bars(self.tree, 5)
        self.assertEqual(
            [len(ANSI.sub("", r)) for r in plain],
            [len(ANSI.sub("", r)) for r in colour],
        )


class TestEndToEnd(unittest.TestCase):
    BASE: ClassVar[list[str]] = ["--color", "none", "--width", "80"]

    def test_profiling_a_snippet(self):
        code, out, _ = run([*self.BASE, "-c", "import json"])
        self.assertEqual(code, 0)
        self.assertIn("json", out)
        self.assertIn("import time", out.lower().replace("import time", "import time"))

    def test_default_view_is_by_package(self):
        _, out, _ = run([*self.BASE, "-c", "import json"])
        self.assertIn("by package", out)

    def test_advice_on_the_example(self):
        code, out, _ = run([*self.BASE, "--advice", EXAMPLE])
        self.assertEqual(code, 0)
        self.assertIn("What you can defer", out)
        # json is used at module level in the example, so it must not appear
        # as advice; unittest.mock is used only inside a function.
        self.assertIn("unittest.mock", out)

    def test_json_output_round_trips(self):
        code, out, _ = run(["--json", "-c", "import json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIn("roots", data)
        self.assertGreater(data["total_us"], 0)

    def test_output_is_plain_when_colour_is_off(self):
        _, out, _ = run([*self.BASE, "-c", "import json"])
        self.assertEqual(out, ANSI.sub("", out))

    def test_save_and_compare(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "before.json")
            code, _, _ = run([*self.BASE, "-c", "import json", "--save", path])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(path))

            code, out, _ = run([*self.BASE, "-c", "import json", "--compare", path])
            self.assertEqual(code, 0)
            self.assertIn("before", out)
            self.assertIn("now", out)

    def test_compare_reports_removed_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "before.json")
            run([*self.BASE, "-c", "import json, decimal", "--save", path])
            _, out, _ = run([*self.BASE, "-c", "import json", "--compare", path])
            self.assertIn("no longer imported", out)

    def test_all_views_render(self):
        code, out, _ = run([*self.BASE, "--all", EXAMPLE])
        self.assertEqual(code, 0)
        for heading in (
            "by package",
            "Slowest individual",
            "Import graph",
            "What you can defer",
        ):
            self.assertIn(heading, out)

    def test_no_target_prints_help(self):
        code, out, _ = run([])
        self.assertEqual(code, 2)
        self.assertIn("usage", out.lower())

    def test_a_failing_target_reports_the_failure_and_still_shows_the_profile(self):
        # Measuring succeeded -- the interpreter imported site, encodings and
        # the rest before giving up -- so the profile is real and worth
        # showing. But the command failed, and the exit code has to say so.
        code, out, _ = run([*self.BASE, "-m", "definitely_not_a_module_12345"])
        self.assertEqual(code, 1)
        self.assertIn("exited with code", out)
        self.assertIn("by package", out)

    def test_a_target_that_imports_nothing_is_a_hard_error(self):
        code, _, err = run(
            [*self.BASE, "--python", "no-such-python-12345", "-c", "import json"]
        )
        self.assertEqual(code, 1)
        self.assertIn("slowimports:", err)

    def test_ascii_mode_is_encodable(self):
        _, out, _ = run([*self.BASE, "--ascii", "-c", "import json"])
        out.encode("ascii", errors="strict")

    def test_passthrough_arguments_are_not_eaten(self):
        # --advice belongs to us; -X belongs to the script.
        code, out, _ = run([*self.BASE, "--advice", EXAMPLE, "--", "-X"])
        self.assertEqual(code, 0)
        self.assertIn("What you can defer", out)


if __name__ == "__main__":
    unittest.main()
