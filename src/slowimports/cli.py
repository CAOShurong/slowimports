"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from . import __version__
from .analyze import analyze_file, rank_deferrable
from .model import ImportTree
from .palette import Palette
from .parse import ParseError, parse_importtime, strip_importtime
from .render import Renderer, format_ms
from .runner import RunnerError, resolve, run_profile

EPILOG = """\
examples:
  slowimports myscript.py           profile a script
  slowimports -m pytest             profile importing a module
  slowimports mytool                profile an installed command
  slowimports -c 'import pandas'    profile one import

  slowimports myscript.py --advice  what to make lazy, and what it saves
  slowimports app.py --save before.json
  slowimports app.py --compare before.json

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

    out = parser.add_argument_group("output")
    out.add_argument("--json", action="store_true", help="machine-readable profile")
    out.add_argument("--save", metavar="FILE", help="write the profile for later comparison")
    out.add_argument("--compare", metavar="FILE", help="compare against a saved profile")
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


def profile(args) -> tuple[ImportTree, str, str, int]:
    """Run the target and parse its profile.

    Returns ``(tree, label, the target's own stderr, its exit code)``. The
    exit code is passed back rather than swallowed: a target that failed
    still produced a usable profile of everything it managed to import
    before dying, which is worth showing, but reporting success for a
    command that failed would be a lie.
    """
    if args.from_file:
        try:
            with open(args.from_file, encoding="utf-8") as handle:
                tree = ImportTree.from_dict(json.load(handle))
        except (OSError, ValueError) as exc:
            raise RunnerError(f"could not read {args.from_file}: {exc}") from None
        return tree, args.target or args.from_file, "", 0

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


def render_comparison(tree: ImportTree, path: str, renderer: Renderer) -> list[str]:
    pal = renderer.palette
    try:
        with open(path, encoding="utf-8") as handle:
            before = ImportTree.from_dict(json.load(handle))
    except (OSError, ValueError) as exc:
        return [f"  could not read {path}: {exc}"]

    delta = tree.total_us - before.total_us
    faster = delta < 0
    level = "good" if faster else "critical" if delta > 0 else "warning"
    arrow = "▼" if faster else "▲" if delta > 0 else "="
    pct = (delta / before.total_us * 100) if before.total_us else 0.0

    rows = [
        f"  before  {format_ms(before.total_us).rjust(9)}   {len(before)} modules",
        f"  now     {format_ms(tree.total_us).rjust(9)}   {len(tree)} modules",
        "  "
        + renderer._style(
            f"{arrow} {format_ms(abs(delta))}  ({abs(pct):.1f}% "
            f"{'faster' if faster else 'slower' if delta else 'unchanged'})",
            pal.status(level),
        ),
    ]

    before_costs = before.top_level_costs()
    now_costs = tree.top_level_costs()
    gone = sorted(
        set(before_costs) - set(now_costs), key=lambda n: before_costs[n], reverse=True
    )
    added = sorted(set(now_costs) - set(before_costs), key=lambda n: now_costs[n], reverse=True)
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
    return rows


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

    if args.json:
        json.dump(tree.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

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
        out.extend(render_comparison(tree, args.compare, renderer))

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
        source = args.target if args.target and args.target.endswith(".py") else None
        out.append(renderer.heading("What you can defer"))
        if source and os.path.exists(source):
            out.extend(render_advice(tree, source, renderer, args.min_saving))
        else:
            out.append("  --advice needs a source file to read; point it at a .py script.")

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

    print("\n".join(out))
    # The measurement succeeded either way, but the command did not, and a
    # script or CI step checking our exit code deserves to hear that.
    return 0 if returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
