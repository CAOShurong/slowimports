"""Decide which top-level imports could be moved inside functions.

This is the part that turns a measurement into an action. Knowing that
``pandas`` costs 400 ms is only interesting if you can do something about it,
and the usual something is to stop importing it until it is needed.

That transformation is only safe when the imported name is never touched
while the module is being imported. Getting this wrong produces a
``NameError`` at run time in whatever code path the reader did not test, so
the analysis is deliberately one-sided: it reports a name as deferrable only
when every use is provably inside a function body, and stays silent whenever
it is unsure.

Uses that run at import time, and therefore disqualify a name:

* anything at module level -- assignments, calls, ``if`` tests, loops
* class bodies, which execute during import
* decorators, base classes, metaclass arguments
* default values and keyword defaults in a signature
* annotations, *unless* ``from __future__ import annotations`` is in effect,
  which turns them into strings
* ``__all__`` and other module-level names, via the ordinary rules above

Star imports (``from x import *``) are never reported: what they bind is not
knowable without importing, so nothing can be proven about their uses.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Callable

__all__ = ["Deferrable", "ImportBinding", "analyze_file", "analyze_source"]


@dataclass
class ImportBinding:
    """A name bound by a module-level import statement."""

    #: The local name the import binds (``np`` for ``import numpy as np``).
    bound_name: str
    #: The module the cost is attributed to (``numpy``).
    module: str
    lineno: int
    col_offset: int
    #: The statement as it should be written when moved inside a function.
    statement: str
    #: True for ``import x``/``import x.y``, False for ``from x import y``.
    is_plain_import: bool
    #: Every line where the bound name is used, and whether that use runs at
    #: import time.
    uses_at_import_time: list[int] = field(default_factory=list)
    uses_in_functions: list[int] = field(default_factory=list)

    @property
    def deferrable(self) -> bool:
        """Safe to move inside the functions that use it."""
        return not self.uses_at_import_time and bool(self.uses_in_functions)

    @property
    def unused(self) -> bool:
        """Bound but never referenced anywhere in this file."""
        return not self.uses_at_import_time and not self.uses_in_functions


@dataclass
class Deferrable:
    """A deferrable import with the cost measured for it."""

    binding: ImportBinding
    saving_us: int

    @property
    def saving_ms(self) -> float:
        return self.saving_us / 1000.0


class _Analyzer(ast.NodeVisitor):
    """Walk a module, recording where each imported name is referenced.

    ``_import_time_depth`` counts the contexts currently being evaluated at
    import time. It starts at 1 for module level and is decremented on the way
    into a function body, so a plain name lookup only counts as an
    import-time use while the counter is positive.
    """

    def __init__(self, *, future_annotations: bool) -> None:
        self.future_annotations = future_annotations
        self.bindings: dict[str, ImportBinding] = {}
        self._import_time_depth = 1
        #: Names rebound later (``json = load_json()``), which makes any
        #: reasoning about the import unreliable.
        self.shadowed: set[str] = set()
        self.has_star_import = False

    # -- imports -----------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        if self._import_time_depth > 0:
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                statement = (
                    f"import {alias.name} as {alias.asname}"
                    if alias.asname
                    else f"import {alias.name}"
                )
                self._bind(
                    ImportBinding(
                        bound_name=bound,
                        module=alias.name,
                        lineno=node.lineno,
                        col_offset=node.col_offset,
                        statement=statement,
                        is_plain_import=True,
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # Relative imports are intra-package and rarely the expensive ones;
        # more importantly their cost cannot be attributed to a top-level
        # distribution, so they are left alone.
        # __future__ imports are compiler directives. They bind a name, but
        # removing or moving one changes how the file is *compiled*, so they
        # are never advice-worthy.
        if node.module == "__future__":
            self.generic_visit(node)
            return
        if self._import_time_depth > 0 and node.level == 0 and node.module:
            for alias in node.names:
                if alias.name == "*":
                    self.has_star_import = True
                    continue
                bound = alias.asname or alias.name
                statement = f"from {node.module} import {alias.name}"
                if alias.asname:
                    statement += f" as {alias.asname}"
                self._bind(
                    ImportBinding(
                        bound_name=bound,
                        module=node.module,
                        lineno=node.lineno,
                        col_offset=node.col_offset,
                        statement=statement,
                        is_plain_import=False,
                    )
                )
        self.generic_visit(node)

    def _bind(self, binding: ImportBinding) -> None:
        if binding.bound_name in self.bindings:
            # Imported twice; the second binding wins at run time, and the
            # ambiguity is not worth advising on.
            self.shadowed.add(binding.bound_name)
            return
        self.bindings[binding.bound_name] = binding

    # -- deferred contexts -------------------------------------------------

    def _visit_function(self, node) -> None:
        # Decorators, defaults and (without future annotations) annotations
        # are all evaluated when the ``def`` executes, so they stay at the
        # current import-time depth.
        for decorator in node.decorator_list:
            self.visit(decorator)
        args = node.args
        for default in [*args.defaults, *(d for d in args.kw_defaults if d)]:
            self.visit(default)
        for arg in [
            *args.posonlyargs,
            *args.args,
            *args.kwonlyargs,
            *(a for a in (args.vararg, args.kwarg) if a),
        ]:
            if arg.annotation is not None:
                self._visit_annotation(arg.annotation)
        if node.returns is not None:
            self._visit_annotation(node.returns)

        # The body does not run until the function is called.
        self._import_time_depth -= 1
        for statement in node.body:
            self.visit(statement)
        self._import_time_depth += 1

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in [*node.args.defaults, *(d for d in node.args.kw_defaults if d)]:
            self.visit(default)
        self._import_time_depth -= 1
        self.visit(node.body)
        self._import_time_depth += 1

    def _visit_annotation(self, node) -> None:
        if self.future_annotations:
            # PEP 563: annotations are never evaluated, so a name used only
            # there is not needed at import time.
            self._import_time_depth -= 1
            self.visit(node)
            self._import_time_depth += 1
        else:
            self.visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._visit_annotation(node.annotation)
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.target)

    # Class bodies run during import, so nothing special is needed for them --
    # generic_visit keeps the current depth, which is the correct behaviour.

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        # ``if TYPE_CHECKING:`` is false at runtime. Imports in that body are
        # not loaded, so they are not advice -- moving them would be nonsense.
        if not _is_type_checking_test(node.test):
            for stmt in node.body:
                self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    # -- uses --------------------------------------------------------------

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            # Rebinding the name makes the original import irrelevant, and
            # reasoning about which one a use refers to is out of scope.
            if node.id in self.bindings:
                self.shadowed.add(node.id)
            return
        binding = self.bindings.get(node.id)
        if binding is None:
            return
        if self._import_time_depth > 0:
            binding.uses_at_import_time.append(node.lineno)
        else:
            binding.uses_in_functions.append(node.lineno)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        # A function declaring ``global json`` may rebind it; treat as unsafe.
        self.shadowed.update(n for n in node.names if n in self.bindings)


def _is_type_checking_test(node: ast.expr) -> bool:
    """True for ``TYPE_CHECKING`` and ``typing.TYPE_CHECKING`` (not ``not``)."""
    if isinstance(node, ast.Name):
        return node.id == "TYPE_CHECKING"
    if isinstance(node, ast.Attribute):
        return node.attr == "TYPE_CHECKING"
    return False


def _has_future_annotations(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in tree.body
    )


def analyze_source(source: str, filename: str = "<string>") -> list[ImportBinding]:
    """Every module-level import in ``source``, with where its name is used.

    Raises :class:`SyntaxError` if the source will not parse, which the caller
    should report rather than swallow -- a file that does not parse is a
    different problem from one with no deferrable imports.
    """
    tree = ast.parse(source, filename=filename)
    analyzer = _Analyzer(future_annotations=_has_future_annotations(tree))
    analyzer.visit(tree)

    return [
        binding for name, binding in analyzer.bindings.items() if name not in analyzer.shadowed
    ]


def analyze_file(path: str) -> list[ImportBinding]:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return analyze_source(handle.read(), filename=path)


def rank_deferrable(
    bindings: list[ImportBinding],
    cost_of: Callable[[str], int],
    *,
    minimum_us: int = 1000,
) -> list[Deferrable]:
    """Pair deferrable imports with their measured cost, biggest first.

    ``minimum_us`` filters out advice not worth taking: moving an import that
    saves a fifth of a millisecond makes the code worse for no reason.
    """
    out = []
    for binding in bindings:
        if not binding.deferrable:
            continue
        saving = cost_of(binding.module)
        if saving >= minimum_us:
            out.append(Deferrable(binding=binding, saving_us=saving))
    return sorted(out, key=lambda d: d.saving_us, reverse=True)
