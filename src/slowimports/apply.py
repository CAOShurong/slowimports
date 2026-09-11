"""Rewrite source: move deferrable imports into the functions that use them.

Only whole import statements with a single name are moved. ``import a, b``
is left alone so one alias cannot be torn out of a shared line.
"""

from __future__ import annotations

import ast
from collections import defaultdict

from .analyze import ImportBinding, analyze_source


def _innermost_functions(tree: ast.AST, use_lines: set[int]) -> list[ast.AST]:
    covering: list[ast.AST] = []

    class Finder(ast.NodeVisitor):
        def _visit_fn(self, node: ast.AST) -> None:
            start = node.lineno
            end = getattr(node, "end_lineno", None) or start
            if any(start <= ln <= end for ln in use_lines):
                covering.append(node)
            self.generic_visit(node)

        visit_FunctionDef = _visit_fn
        visit_AsyncFunctionDef = _visit_fn

    Finder().visit(tree)
    inner: list[ast.AST] = []
    for node in covering:
        start = node.lineno
        end = getattr(node, "end_lineno", None) or start
        nested = any(
            other is not node
            and start <= other.lineno
            and (getattr(other, "end_lineno", None) or other.lineno) <= end
            for other in covering
        )
        if not nested:
            inner.append(node)
    return inner


def _insert_after_header(node: ast.AST) -> int:
    body = getattr(node, "body", None) or []
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(getattr(body[0], "value", None), ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return int(body[0].end_lineno or body[0].lineno)
    return int(node.lineno)


def _line_ending(lines: list[str]) -> str:
    if lines and lines[0].endswith("\r\n"):
        return "\r\n"
    return "\n"


def plan_apply(source: str, bindings: list[ImportBinding]) -> list[ImportBinding]:
    by_line: dict[int, list[ImportBinding]] = defaultdict(list)
    for binding in bindings:
        if binding.deferrable:
            by_line[binding.lineno].append(binding)
    return [b for group in by_line.values() if len(group) == 1 for b in group]


def apply_source(source: str, bindings: list[ImportBinding] | None = None) -> str:
    if bindings is None:
        bindings = analyze_source(source)
    movable = plan_apply(source, bindings)
    if not movable:
        return source

    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    if not lines:
        return source
    ending = _line_ending(lines)

    inserts: dict[int, list[str]] = defaultdict(list)
    deletes: set[int] = set()

    for binding in movable:
        for fn in _innermost_functions(tree, set(binding.uses_in_functions)):
            after = _insert_after_header(fn)
            body = fn.body
            indent = "    "
            if body:
                raw = lines[body[0].lineno - 1]
                indent = raw[: len(raw) - len(raw.lstrip())] or "    "
            stmt = f"{indent}{binding.statement}{ending}"
            if stmt not in inserts[after]:
                inserts[after].append(stmt)
        for lineno in range(binding.lineno, binding.end_lineno + 1):
            deletes.add(lineno)

    out: list[str] = []
    for i, line in enumerate(lines, start=1):
        if i not in deletes:
            out.append(line)
        out.extend(inserts.get(i, []))
    text = "".join(out)
    ast.parse(text)
    return text


def apply_path(path: str, *, dry_run: bool = False) -> tuple[bool, str]:
    with open(path, encoding="utf-8", errors="replace") as handle:
        original = handle.read()
    rewritten = apply_source(original)
    if rewritten == original:
        return False, original
    if not dry_run:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(rewritten)
    return True, rewritten
