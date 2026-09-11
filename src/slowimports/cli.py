"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from . import __version__
from .analyze import analyze_file, rank_deferrable
from .model import ImportTree, select_median_tree
from .palette import Palette
from .parse import ParseError, parse_importtime, strip_importtime
from .render import Renderer, format_ms
from .runner import RunnerError, resolve, run_profile, source_path_for

EPILOG = """\
examples:
  slowimports myscript.py           profile a script
  slowimports -m pytest             profile importing a module
  slowimports mytool                profile an installed command
  slowimports -c 'import pandas'    profile one import

  slowimports myscript.py --advice  what to make lazy, and what it saves
  slowimports app.py --save before.json
  slowimports app.py --compare before.json --slower-ms 20
  slowimports app.py --budget-ms 200     fail CI if startup imports exceed 200 ms
  slowimports app.py --repeat 5 --budget-ms 200
  slowimports app.py --forbid pandas,torch
  slowimports -m myapp --advice          same analysis for a module, not just a file

why this exists:
  Python CLIs are often slow to start, and the reason is almost always an
  import that is only needed on one code path. This measures where the time
  goes, then reads your source to find which imports can safely move inside
  the functions that use them.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slowimports",
        description="Find out why your Python program is slow to start.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="a script, an installed command, or a module name",
    )
    parser.add_argument("--version", action="version", version=f"slowimports {__version__}")

    how = parser.add_argument_group("what to run")
    how.add_argument("-m", "--module", metavar="MOD", help="profile 'python -m MOD'")
    how.add_argument("-c", "--code", metavar="CODE", help="profile a snippet")
    how.add_argument(
        "--python", metavar="PATH", help="interpreter to measure (default: this one)"
    )
    how.add_argument("--timeout", type=float, default=120.0, metavar="SEC")

    view = parser.add_argument_group("what to show")
    view.add_argument(
        "--packages", action="store_true", help="group by top-level package (default view)"
    )
    view.add_argument("--modules", action="store_true", help="rank individual modules instead")
    view.add_argument("--tree", action="store_true", help="show the icicle chart")
    view.add_argument(
        "--advice",
        action="store_true",
        help="read the source and report which imports can be deferred",
    )
    view.add_argument("--all", action="store_true", help="every view")
    view.add_argument("-n", "--limit", type=int, default=12, metavar="N")
    view.add_argument(
        "--min-saving",
        type=float,
        default=1.0,
        metavar="MS",
        help="ignore advice worth less than this (default: 1 ms)",
    )
    view.add_argument(
        "--budget-ms",
        type=float,
        default=None,
        metavar="MS",
        help="fail if total import time exceeds this many milliseconds",
    )
    view.add_argument(
        "--forbid",
        metavar="PACKAGES",
        default=None,
        help="fail if these packages are imported at startup (comma-separated)",
    )
    view.add_argument(
        "--repeat",
        type=int,
        default=1,
        metavar="N",
        help="run N times and rank the median (default: 1)",
    )

    out = parser.add_argument_group("output")
    out.add_argument("--json", action="store_true", help="machine-readable profile")
    out.add_argument("--save", metavar="FILE", help="write the profile for later comparison")
    out.add_argument("--compare", metavar="FILE", help="compare against a saved profile")
    out.add_argument(
        "--slower-ms",
        type=float,
        default=None,
        metavar="MS",
        help="with --compare, fail if total import time grew by more than this",
    )
    out.add_argument(
        "--from",
        dest="from_file",
        metavar="FILE",
        help="render a saved profile instead of measuring again "
        "(useful for a profile someone sent you, and what "
        "makes this project's own docs reproducible)",
    )
    out.add_argument(
        "--color", choices=("auto", "truecolor", "256", "16", "none"), default="auto"
    )
    out.add_argument("--ascii", action="store_true", help="avoid block-drawing characters")
    out.add_argument("--light", action="store_true", help="colours for a light terminal")
    out.add_argument("--width", type=int, default=0, metavar="COLS")
    return parser


def terminal_width(requested: int) -> int:
    if requested > 0:
        return requested
    try:
        return max(50, min(120, shutil.get_terminal_size(fallback=(88, 24)).columns))
    except Exception:
        return 88


def split_passthrough(argv: list[str]) -> tuple[list[str], list[str]]:
    """Separate our own options from the target's, at the first ``--``.

    ``argparse.REMAINDER`` looks like the tool for this and is a trap: it
    swallows everything after the first positional, so
    ``slowimports app.py --advice`` hands ``--advice`` to the script and this
    tool never sees it. Requiring an explicit ``--`` makes the boundary
    something the reader can see:

        slowimports app.py --advice -- --flag-for-the-script
    """
    if "--" not in argv:
        return argv, []
    index = argv.index("--")
    return argv[:index], argv[index + 1 :]


def _target_from_args(args) -> tuple[str, list[str]]:
    passthrough = list(getattr(args, "passthrough", ()) or ())
    if args.code:
        return "code", passthrough
    if args.module:
        return "module", passthrough
    return "auto", passthrough


def _measure_once(args) -> tuple[ImportTree, str, str, int]:
    """One measured run. ``--from`` is handled in :func:`profile`."""
    kind, passthrough = _target_from_args(args)
    if kind == "code":
        target = resolve(args.code, passthrough, kind="code")
    elif kind == "module":
        target = resolve(args.module, passthrough, kind="module")
    else:
        target = resolve(args.target, passthrough)

    result = run_profile(target, python=args.python, timeout=args.timeout)
    try:
        tree = parse_importtime(result.stderr)
    except ParseError:
        detail = strip_importtime(result.stderr) or result.stdout.strip()
        raise RunnerError(
            f"{target.describe()} produced no import-time data "
            f"(exit code {result.returncode}).\n"
            + (
                "  Its output was:\n    " + detail.replace("\n", "\n    ")
                if detail
                else "  It produced no output either."
            )
        ) from None
    return (
        tree,
        target.describe(),
        strip_importtime(result.stderr),
        result.returncode,
    )


def profile(args) -> tuple[ImportTree, str, str, int]:
    """Run the target and parse its profile.

    Returns ``(tree, label, the target's own stderr, its exit code)``. The
    exit code is passed back rather than swallowed: a target that failed
    still produced a usable profile of everything it managed to import
    before dying, which is worth showing, but reporting success for a
    command that failed would be a lie.

    ``--repeat N`` measures N times and keeps the run whose total is closest
    to the median. Import-time is wall-clock; a single sample will flake a
    tight CI budget.
    """
    if args.from_file:
        try:
            with open(args.from_file, encoding="utf-8") as handle:
                tree = ImportTree.from_dict(json.load(handle))
        except (OSError, ValueError) as exc:
            raise RunnerError(f"could not read {args.from_file}: {exc}") from None
        return tree, args.target or args.from_file, "", 0

    n = max(1, int(getattr(args, "repeat", 1) or 1))
    if n == 1:
        return _measure_once(args)

    trees: list[ImportTree] = []
    extras: list[str] = []
    codes: list[int] = []
    label = ""
    for _ in range(n):
        tree, label, extra, code = _measure_once(args)
        trees.append(tree)
        extras.append(extra)
        codes.append(code)
    chosen = select_median_tree(trees)
    idx = trees.index(chosen)
    totals = [item.total_us for item in trees]
    chosen.repeat = n
    chosen.min_us = min(totals)
    chosen.max_us = max(totals)
    # Keep the pairing of stderr/exit code with the tree we actually report.
    return chosen, label, extras[idx], codes[idx]


def render_advice(
    tree: ImportTree, source_path: str, renderer: Renderer, min_saving_ms: float
) -> list[str]:
    """The actionable section: what to move, and what it buys."""
    pal = renderer.palette
    try:
        bindings = analyze_file(source_path)
    except SyntaxError as exc:
        return [f"  could not parse {source_path}: {exc}"]
    except OSError as exc:
        return [f"  could not read {source_path}: {exc}"]

    deferrable = rank_deferrable(bindings, tree.savings, minimum_us=int(min_saving_ms * 1000))
    unused = [b for b in bindings if b.unused and tree.savings(b.module) > 0]

    if not deferrable and not unused:
        return [
            renderer._style(
                "  Nothing to defer: every top-level import is used while the "
                "module is being imported.",
                pal.muted(),
            )
        ]

    rows: list[str] = []
    # Not the sum of the per-import figures. Candidates that share a
    # dependency each exclude it -- because the other still needs it -- so
    # adding them up understates; candidates where one contains the other
    # overlap, so it overstates. Ask what survives if all of them go.
    total = tree.savings_for({d.binding.module for d in deferrable})
    if deferrable:
        rows.append(
            "  "
            + renderer._style(format_ms(total), pal.status("good"))
            + " recoverable in total by moving these inside the functions "
            "that use them:"
        )
        rows.append("")
        for item in deferrable:
            b = item.binding
            where = ", ".join(str(n) for n in sorted(set(b.uses_in_functions))[:4])
            rows.append(
                "    "
                + renderer._style(f"line {b.lineno}", pal.muted())
                + f"  {b.statement}"
                + renderer._style(f"   saves {format_ms(item.saving_us)}", pal.status("good"))
            )
            rows.append(renderer._style(f"        used only at line(s) {where}", pal.muted()))
    if unused:
        rows.append("")
        rows.append("  Imported but never used in this file:")
        for b in unused:
            rows.append(
                "    "
                + renderer._style(f"line {b.lineno}", pal.muted())
                + f"  {b.statement}"
                + renderer._style(
                    f"   would save {format_ms(tree.savings(b.module))}",
                    pal.status("good"),
                )
            )
    rows.append("")
    rows.append(
        renderer._style(
            "  Only imports whose every use is inside a function body are listed; "
            "anything\n  touched while the module loads is left alone.",
            pal.muted(),
        )
    )
    return rows


_DELTA_FLOOR_US = 1000


def package_deltas(
    now: dict[str, int],
    before: dict[str, int],
    *,
    floor_us: int = _DELTA_FLOOR_US,
) -> tuple[list[str], list[str], list[tuple[str, int]], list[tuple[str, int]]]:
    """Added, removed, slower, faster top-level packages (sub-ms jitter ignored)."""
    added = sorted(set(now) - set(before), key=lambda n: now[n], reverse=True)
    gone = sorted(set(before) - set(now), key=lambda n: before[n], reverse=True)
    slower: list[tuple[str, int]] = []
    faster: list[tuple[str, int]] = []
    for name in set(now) & set(before):
        delta = now[name] - before[name]
        if delta >= floor_us:
            slower.append((name, delta))
        elif delta <= -floor_us:
            faster.append((name, delta))
    slower.sort(key=lambda item: item[1], reverse=True)
    faster.sort(key=lambda item: item[1])
    return added, gone, slower, faster


def _load_saved_tree(path: str) -> ImportTree:
    with open(path, encoding="utf-8") as handle:
        return ImportTree.from_dict(json.load(handle))


def render_comparison(tree: ImportTree, path: str, renderer: Renderer) -> tuple[list[str], int]:
    pal = renderer.palette
    try:
        before = _load_saved_tree(path)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return [f"  could not read {path}: {exc}"], 0

    delta = tree.total_us - before.total_us
    faster_total = delta < 0
    level = "good" if faster_total else "critical" if delta > 0 else "warning"
    arrow = "▼" if faster_total else "▲" if delta > 0 else "="
    pct = (delta / before.total_us * 100) if before.total_us else 0.0

    rows = [
        f"  before  {format_ms(before.total_us).rjust(9)}   {len(before)} modules",
        f"  now     {format_ms(tree.total_us).rjust(9)}   {len(tree)} modules",
        "  "
        + renderer._style(
            f"{arrow} {format_ms(abs(delta))}  ({abs(pct):.1f}% "
            f"{'faster' if faster_total else 'slower' if delta else 'unchanged'})",
            pal.status(level),
        ),
    ]

    before_costs = before.top_level_costs()
    now_costs = tree.top_level_costs()
    added, gone, slower, faster = package_deltas(now_costs, before_costs)
    if gone:
        rows.append("")
        rows.append("  no longer imported:")
        for name in gone[:8]:
            rows.append(
                f"    {name:<24}"
                + renderer._style(f"-{format_ms(before_costs[name])}", pal.status("good"))
            )
    if added:
        rows.append("")
        rows.append("  newly imported:")
        for name in added[:8]:
            rows.append(
                f"    {name:<24}"
                + renderer._style(f"+{format_ms(now_costs[name])}", pal.status("critical"))
            )
    if slower:
        rows.append("")
        rows.append("  slower:")
        for name, amount in slower[:8]:
            rows.append(
                f"    {name:<24}"
                + renderer._style(f"+{format_ms(amount)}", pal.status("critical"))
            )
    if faster:
        rows.append("")
        rows.append("  faster:")
        for name, amount in faster[:8]:
            rows.append(
                f"    {name:<24}"
                + renderer._style(f"-{format_ms(-amount)}", pal.status("good"))
            )
    return rows, delta


def parse_forbid_names(raw: str | None) -> list[str]:
    """Split ``pandas,torch`` into distinct names."""
    if not raw:
        return []
    seen: list[str] = []
    for part in raw.split(","):
        name = part.strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def forbidden_hits(tree: ImportTree, names: list[str]) -> list[tuple[str, int]]:
    """Packages/modules from ``--forbid`` that actually loaded, with self-time."""
    hits: list[tuple[str, int]] = []
    for name in names:
        us = 0
        found = False
        for node in tree:
            if "." in name:
                hit = node.name == name or node.name.startswith(name + ".")
            else:
                hit = node.top_level == name
            if hit:
                us += node.self_us
                found = True
        if found:
            hits.append((name, us))
    hits.sort(key=lambda item: item[1], reverse=True)
    return hits


def render_forbid(hits: list[tuple[str, int]]) -> str:
    if not hits:
        return ""
    width = max(len(name) for name, _ in hits)
    lines = ["slowimports: forbidden imports at startup:"]
    for name, us in hits:
        lines.append(f"  {name:<{width}s}  {format_ms(us)}")
    return "\n".join(lines)


def advice_source(args) -> str | None:
    """The file ``--advice`` should read: a script, ``-m`` module, or command."""
    if args.code:
        return None
    kind, passthrough = _target_from_args(args)
    if kind == "code":
        return None
    try:
        if kind == "module":
            target = resolve(args.module, passthrough, kind="module")
        elif args.target:
            target = resolve(args.target, passthrough)
        else:
            return None
        return source_path_for(
            target,
            args.python,
            timeout=min(float(args.timeout or 15.0), 15.0),
        )
    except RunnerError:
        return None


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    ours, passthrough = split_passthrough(raw)

    parser = build_parser()
    args = parser.parse_args(ours)
    args.passthrough = passthrough

    if not (args.target or args.module or args.code or args.from_file):
        parser.print_help()
        return 2

    # Block-drawing characters need an encoder that can carry them. A CJK
    # Windows console defaults to GBK or CP932, which cannot, and the bars
    # come out as replacement characters. Re-point the encoder rather than
    # give up on the drawing.
    if not args.ascii:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            args.ascii = True
        else:
            try:
                "█▏".encode(sys.stdout.encoding or "ascii")
            except (LookupError, UnicodeEncodeError):
                args.ascii = True

    try:
        tree, label, extra, returncode = profile(args)
    except RunnerError as exc:
        print(f"slowimports: {exc}", file=sys.stderr)
        return 1

    over_budget = args.budget_ms is not None and tree.total_ms > args.budget_ms
    budget_line = (
        f"slowimports: budget exceeded: {format_ms(tree.total_us)} > {args.budget_ms:g} ms"
        if over_budget
        else ""
    )

    compare_delta_us = 0
    compare_error = ""
    if args.compare:
        try:
            before = _load_saved_tree(args.compare)
            compare_delta_us = tree.total_us - before.total_us
        except (OSError, ValueError, TypeError, KeyError) as exc:
            compare_error = f"slowimports: could not read {args.compare}: {exc}"
    grew = (
        args.slower_ms is not None
        and not compare_error
        and args.compare
        and compare_delta_us / 1000.0 > args.slower_ms
    )
    slower_line = (
        f"slowimports: slower than saved by more than {args.slower_ms:g} ms" if grew else ""
    )

    forbid_names = parse_forbid_names(args.forbid)
    hits = forbidden_hits(tree, forbid_names)
    forbid_line = render_forbid(hits)

    if args.json:
        payload = tree.as_dict()
        if args.budget_ms is not None:
            payload["budget_ms"] = args.budget_ms
            payload["budget_ok"] = not over_budget
        if args.slower_ms is not None:
            payload["slower_ms"] = args.slower_ms
            payload["slower_ok"] = not grew
        if forbid_names:
            payload["forbid"] = forbid_names
            payload["forbidden"] = [
                {"name": name, "self_us": us, "self_ms": round(us / 1000.0, 3)}
                for name, us in hits
            ]
            payload["forbid_ok"] = not hits
        if tree.repeat > 1:
            payload["repeat"] = tree.repeat
            payload["min_us"] = tree.min_us
            payload["max_us"] = tree.max_us
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        if compare_error:
            print(compare_error, file=sys.stderr)
        if budget_line:
            print(budget_line, file=sys.stderr)
        if slower_line:
            print(slower_line, file=sys.stderr)
        if forbid_line:
            print(forbid_line, file=sys.stderr)
        return 0 if returncode == 0 and not over_budget and not grew and not hits else 1

    if args.save:
        try:
            with open(args.save, "w", encoding="utf-8") as handle:
                json.dump(tree.as_dict(), handle, indent=2)
        except OSError as exc:
            print(f"slowimports: could not write {args.save}: {exc}", file=sys.stderr)
            return 1

    palette = Palette(dark=not args.light, depth=None if args.color == "auto" else args.color)
    renderer = Renderer(palette, unicode=not args.ascii, width=terminal_width(args.width))

    show_all = args.all
    show_modules = args.modules or show_all
    show_tree = args.tree or show_all
    show_advice = args.advice or show_all
    # The package view is the default because it is the one people act on.
    show_packages = args.packages or show_all or not (show_modules or show_tree or show_advice)

    out: list[str] = []
    out.extend(renderer.summary(tree, label))

    if args.compare:
        out.append(renderer.heading("Compared with the saved profile"))
        compare_rows, compare_delta_us = render_comparison(tree, args.compare, renderer)
        out.extend(compare_rows)
        grew = args.slower_ms is not None and compare_delta_us / 1000.0 > args.slower_ms
        if grew:
            slower_line = f"slowimports: slower than saved by more than {args.slower_ms:g} ms"

    if show_packages:
        out.append(renderer.heading("Where the time goes, by package"))
        out.extend(renderer.packages(tree, args.limit))
    if show_modules:
        out.append(renderer.heading("Slowest individual modules (own body only)"))
        out.extend(renderer.bars(tree, args.limit))
    if show_tree:
        out.append(renderer.heading("Import graph"))
        out.extend(renderer.icicle(tree))
    if show_advice:
        source = advice_source(args)
        out.append(renderer.heading("What you can defer"))
        if source:
            given = args.target and os.path.isfile(args.target)
            if not given:
                out.append(renderer._style(f"  reading {source}", renderer.palette.muted()))
            out.extend(render_advice(tree, source, renderer, args.min_saving))
        else:
            out.append(
                "  --advice reads the target's source. Pass a .py script, "
                "-m MODULE, or an installed command."
            )

    if args.save:
        out.append("")
        out.append(f"  saved to {args.save}")
    if extra:
        out.append(renderer.heading("The program also wrote to stderr"))
        out.extend("  " + line for line in extra.splitlines()[:10])

    if returncode != 0:
        out.append("")
        out.append(
            renderer._style(
                f"  note: the target exited with code {returncode}. Everything "
                "it managed to\n  import before that is still measured above.",
                palette.status("warning"),
            )
        )
    if over_budget:
        out.append("")
        out.append(renderer._style(f"  {budget_line}", palette.status("critical")))
    if slower_line:
        out.append("")
        out.append(renderer._style(f"  {slower_line}", palette.status("critical")))
    if forbid_line:
        out.append("")
        out.append(renderer._style(f"  {forbid_line}", palette.status("critical")))

    print("\n".join(out))
    # The measurement succeeded either way, but the command did not, and a
    # script or CI step checking our exit code deserves to hear that.
    return 0 if returncode == 0 and not over_budget and not grew and not hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
