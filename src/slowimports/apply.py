"""Rewrite source: move deferrable imports into the functions that use them.

``--apply`` is the user-facing command. The mechanics live in :mod:`.rewrite`.
"""

from __future__ import annotations

from .analyze import ImportBinding, analyze_source
from .rewrite import apply_deferrals, rewrite, writable_script


def plan_apply(source: str, bindings: list[ImportBinding] | None = None) -> list[ImportBinding]:
    """Bindings that would actually be moved (skips one-liners / commented lines)."""
    if bindings is None:
        bindings = analyze_source(source)
    return rewrite(source, [b for b in bindings if b.deferrable]).moved


def apply_source(source: str, bindings: list[ImportBinding] | None = None) -> str:
    return apply_deferrals(source, bindings)


def apply_path(path: str, *, dry_run: bool = False) -> tuple[bool, str]:
    abs_path = writable_script(path)
    with open(abs_path, encoding="utf-8", errors="replace") as handle:
        original = handle.read()
    rewritten = apply_source(original)
    if rewritten == original:
        return False, original
    if not dry_run:
        with open(abs_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(rewritten)
    return True, rewritten
