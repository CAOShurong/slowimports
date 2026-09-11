"""Move deferrable imports inside the functions that use them.

``--advice`` names the safe moves. This produces the patch. It refuses
multi-line or commented import statements rather than guess at formatting.
"""

from __future__ import annotations

import ast
import difflib
import os
from dataclasses import dataclass, field

from .analyze import ImportBinding, analyze_source

__all__ = ["RewriteError", "RewriteResult", "apply_deferrals", "unified_diff"]


class RewriteError(ValueError):
    """The rewrite would not parse, or the target is not a writable script."""


@dataclass
class RewriteResult:
    source: str
    moved: list[ImportBinding] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.moved)


def _newline(source: str) -> str:
    return "\r\n" if "\r\n" in source else "\n"


def _bound_alias(alias: ast.alias, *, from_import: bool) -> str:
    if alias.asname:
        return alias.asname
    if from_import:
        return alias.name
    return alias.name.split(".", 1)[0]


def _format_import(node: ast.Import, keep: list[ast.alias]) -> str:
    parts = []
    for alias in keep:
        parts.append(f"{alias.name} as {alias.asname}" if alias.asname else alias.name)
    return "import " + ", ".join(parts)


def _format_from(node: ast.ImportFrom, keep: list[ast.alias]) -> str:
    parts = []
    for alias in keep:
        parts.append(f"{alias.name} as {alias.asname}" if alias.asname else alias.name)
    return f"from {node.module} import " + ", ".join(parts)


def _line_has_comment(line: str) -> bool:
    code = line.split("#", 1)[0]
    return "#" in line and bool(code.strip())


def _direct_uses(fn: ast.AST, names: set[str]) -> set[str]:
    """Names loaded in ``fn``'s own body, not in nested functions."""
    used: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if node is fn:
                self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if node is fn:
                self.generic_visit(node)

        def visit_Lambda(self, node: ast.Lambda) -> None:
            if node is fn:
                self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, ast.Load) and node.id in names:
                used.add(node.id)

    Visitor().visit(fn)
    return used


def _insert_lineno(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> int | None:
    """1-based line to insert *before*. None if the function is a one-liner."""
    if not fn.body:
        return None
    first = fn.body[0]
    if first.lineno == fn.lineno:
        return None
    if (
        isinstance(first, ast.Expr)
        and isinstance(getattr(first, "value", None), ast.Constant)
        and isinstance(first.value.value, str)
        and len(fn.body) > 1
    ):
        return first.end_lineno + 1
    return first.lineno


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def rewrite(
    source: str,
    bindings: list[ImportBinding] | None = None,
    *,
    filename: str = "<string>",
) -> RewriteResult:
    """Return rewritten source. ``bindings`` defaults to every deferrable import."""
    if bindings is None:
        bindings = [b for b in analyze_source(source, filename=filename) if b.deferrable]
    move = {b.bound_name: b for b in bindings if b.deferrable}
    if not move:
        return RewriteResult(source=source)

    tree = ast.parse(source, filename=filename)
    lines = source.splitlines(keepends=True)
    nl = _newline(source)
    skipped: list[str] = []
    candidates = set(move)

    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    used_in_ok: set[str] = set()
    used_in_bad: set[str] = set()
    placements: list[tuple[int, ast.AST, set[str]]] = []
    for fn in functions:
        needed = _direct_uses(fn, candidates)
        if not needed:
            continue
        at = _insert_lineno(fn)
        if at is None:
            used_in_bad |= needed
            skipped.append(f"line {fn.lineno}: one-line function {fn.name!r} left alone")
            continue
        used_in_ok |= needed
        placements.append((at, fn, needed))
    for node in ast.walk(tree):
        if isinstance(node, ast.Lambda):
            used_in_bad |= _direct_uses(node, candidates)

    editable: set[str] = set()
    import_nodes: list[ast.AST] = []
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.ImportFrom) and (node.module == "__future__" or node.level):
            continue
        start = node.lineno
        end = node.end_lineno or node.lineno
        if start != end:
            skipped.append(f"line {start}: multi-line import left alone")
            continue
        idx = start - 1
        if idx >= len(lines) or _line_has_comment(lines[idx]):
            skipped.append(f"line {start}: commented import left alone")
            continue
        from_import = isinstance(node, ast.ImportFrom)
        for alias in node.names:
            name = _bound_alias(alias, from_import=from_import)
            if name in candidates:
                editable.add(name)
        import_nodes.append(node)

    placeable = {
        name
        for name in candidates
        if name in used_in_ok and name not in used_in_bad and name in editable
    }
    if not placeable:
        return RewriteResult(source=source, skipped=skipped)

    replacements: dict[int, str] = {}
    for node in import_nodes:
        from_import = isinstance(node, ast.ImportFrom)
        idx = node.lineno - 1
        keep = [
            alias
            for alias in node.names
            if _bound_alias(alias, from_import=from_import) not in placeable
        ]
        drop = [
            alias
            for alias in node.names
            if _bound_alias(alias, from_import=from_import) in placeable
        ]
        if not drop:
            continue
        indent = _indent_of(lines[idx])
        ending = nl if lines[idx].endswith(("\n", "\r\n")) else ""
        if not keep:
            replacements[idx] = ""
        elif from_import:
            replacements[idx] = indent + _format_from(node, keep) + ending
        else:
            replacements[idx] = indent + _format_import(node, keep) + ending

    inserts: dict[int, list[str]] = {}
    for at, fn, needed in placements:
        names = needed & placeable
        if not names:
            continue
        body = fn.body[0]
        indent = " " * (body.col_offset if body.col_offset else fn.col_offset + 4)
        chunk = [
            f"{indent}{move[name].statement}{nl}"
            for name in sorted(names, key=lambda n: move[n].lineno)
        ]
        inserts.setdefault(at - 1, []).extend(chunk)

    ops: list[tuple[int, str, object]] = []
    for idx, text in replacements.items():
        ops.append((idx, "replace", text))
    for idx, chunk in inserts.items():
        ops.append((idx, "insert", chunk))
    ops.sort(key=lambda op: op[0], reverse=True)
    out = list(lines)
    for idx, kind, payload in ops:
        if kind == "insert":
            out[idx:idx] = payload  # type: ignore[assignment]
        else:
            out[idx] = payload  # type: ignore[assignment]
    out = [line for line in out if line != ""]
    text = "".join(out)
    try:
        ast.parse(text, filename=filename)
    except SyntaxError as exc:
        raise RewriteError(f"rewrite of {filename} did not parse: {exc}") from exc

    moved = [move[name] for name in placeable]
    moved.sort(key=lambda b: b.lineno)
    return RewriteResult(source=text, moved=moved, skipped=skipped)


def apply_deferrals(
    source: str,
    bindings: list[ImportBinding] | None = None,
    *,
    filename: str = "<string>",
) -> str:
    return rewrite(source, bindings, filename=filename).source


def writable_script(path: str | None) -> str:
    """Absolute path of a user ``.py`` file. Refuses site-packages."""
    if not path or not os.path.isfile(path) or not path.lower().endswith(".py"):
        raise RewriteError("--apply only rewrites a .py script passed as the target")
    abs_path = os.path.abspath(path)
    norm = abs_path.replace("\\", "/").lower()
    if "/site-packages/" in norm or "/dist-packages/" in norm:
        raise RewriteError(f"refusing to rewrite installed module {abs_path}")
    return abs_path


def rel_path(path: str) -> str:
    try:
        text = os.path.relpath(path)
    except ValueError:
        text = path
    return text.replace("\\", "/")


def unified_diff(before: str, after: str, path: str) -> str:
    """Unified diff with ``a/`` ``b/`` prefixes, empty if unchanged."""
    if before == after:
        return ""
    label = rel_path(path)
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{label}",
            tofile=f"b/{label}",
        )
    )
