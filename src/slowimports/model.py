"""The import tree, and the arithmetic that makes it answerable.

CPython's ``-X importtime`` reports two numbers per module: *self*, the time
spent in that module's own body, and *cumulative*, that plus everything it
imported. Neither alone answers the question people actually have, which is
"what do I get back if I stop importing this at startup?"

That number is the cumulative cost of the module minus the cost of anything
underneath it that something else already needed. :meth:`ImportTree.savings`
computes it, and it is the figure the whole tool is built to report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["ImportNode", "ImportTree", "median_us", "select_median_tree"]


@dataclass
class ImportNode:
    """One module in the import graph, as CPython reported it."""

    name: str
    self_us: int
    cumulative_us: int
    depth: int
    children: list[ImportNode] = field(default_factory=list)
    parent: ImportNode | None = field(default=None, repr=False, compare=False)

    @property
    def self_ms(self) -> float:
        return self_us_to_ms(self.self_us)

    @property
    def cumulative_ms(self) -> float:
        return self_us_to_ms(self.cumulative_us)

    @property
    def top_level(self) -> str:
        """The distribution-ish root, e.g. ``numpy`` for ``numpy.linalg.lapack``."""
        return self.name.split(".", 1)[0]

    def walk(self):
        """Yield this node and every descendant, parents before children."""
        yield self
        for child in self.children:
            yield from child.walk()

    def ancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent


def self_us_to_ms(value: int) -> float:
    return value / 1000.0


class ImportTree:
    """A parsed profile: the forest of imports plus queries over it.

    ``-X importtime`` prints children before parents and marks depth with
    indentation, so the roots are whatever ended up at depth zero. There is
    usually more than one, which is why this is a forest rather than a tree
    despite the name.
    """

    def __init__(self, roots: list[ImportNode], *, total_us: int | None = None) -> None:
        self.roots = roots
        self._total_us = total_us
        self._by_name: dict[str, ImportNode] | None = None
        self.repeat = 1
        self.min_us: int | None = None
        self.max_us: int | None = None

    # -- basics ------------------------------------------------------------

    def __iter__(self):
        for root in self.roots:
            yield from root.walk()

    def __len__(self) -> int:
        return sum(1 for _ in self)

    @property
    def total_us(self) -> int:
        """Total import time: every module's own body, summed.

        The obvious alternative is to add up the roots' cumulative times.
        That is the same number for complete output, but only for complete
        output, and it is not self-consistent with anything else the report
        shows: the per-package breakdown is built from self times, so if the
        total came from cumulative times the percentages would not add to
        100% whenever the two disagree -- on truncated output, or simply
        through CPython's own rounding, which is off by a microsecond here
        and there.

        A report whose parts do not sum to its whole is worse than one that
        is a microsecond off, so the total is defined as the sum of the parts.
        """
        if self._total_us is not None:
            return self._total_us
        return sum(node.self_us for node in self)

    @property
    def total_ms(self) -> float:
        return self_us_to_ms(self.total_us)

    def by_name(self, name: str) -> ImportNode | None:
        if self._by_name is None:
            self._by_name = {node.name: node for node in self}
        return self._by_name.get(name)

    # -- queries -----------------------------------------------------------

    def slowest(self, limit: int = 15, *, by: str = "self") -> list[ImportNode]:
        """The heaviest modules, by their own body or by their subtree."""
        key = (lambda n: n.self_us) if by == "self" else (lambda n: n.cumulative_us)
        return sorted(self, key=key, reverse=True)[:limit]

    def top_level_costs(self) -> dict[str, int]:
        """Time spent *inside* each top-level package, exclusive of others.

        Every module's own body time is charged to its own package, so the
        values sum to the total and the shares sum to 100%.

        The tempting alternative -- charging each package its cumulative
        time -- double-counts and produces a report that does not add up.
        ``unittest.mock`` imports ``asyncio``, so on a trivial script
        ``unittest`` would claim 65% and ``asyncio`` 50% of the same
        milliseconds. Whichever number the reader trusted, they would be
        wrong.

        "What would I get back by dropping this?" is a different question,
        and :meth:`savings` is where it is answered.
        """
        costs: dict[str, int] = {}
        for node in self:
            costs[node.top_level] = costs.get(node.top_level, 0) + node.self_us
        return dict(sorted(costs.items(), key=lambda kv: kv[1], reverse=True))

    def savings(self, name: str) -> int:
        """Time recovered if ``name`` were no longer imported at startup.

        Not simply its cumulative time. A module's subtree usually contains
        things another part of the program imports anyway -- ``re`` and
        ``enum`` turn up everywhere -- and those would still be paid for. So
        the answer is the cumulative cost minus every descendant that is also
        reachable from outside this subtree.

        Returns 0 for an unknown name, which is the honest answer for
        "removing something that was never imported".
        """
        return self.savings_for({name})

    def savings_for(self, names: set[str]) -> int:
        """Time recovered if *all* of ``names`` stopped being imported.

        Summing :meth:`savings` over a set is not the same thing, and is
        wrong in both directions. Two candidates that share a dependency each
        exclude it -- because the other still needs it -- so the sum
        understates. Two candidates where one contains the other overlap, so
        the sum overstates.

        Doing it properly means asking which modules survive: start from the
        roots that are not being removed, follow their imports, and charge
        for the difference. That is what a headline "you could save N ms"
        figure has to mean if it is to be checkable.
        """
        targets = {name for name in names if self.by_name(name) is not None}
        if not targets:
            return 0

        surviving: set[str] = set()
        stack = [root for root in self.roots if root.name not in targets]
        while stack:
            node = stack.pop()
            if node.name in surviving or node.name in targets:
                continue
            surviving.add(node.name)
            stack.extend(node.children)

        # A removed module's subtree may still be reached from a survivor.
        for node in self:
            if node.name not in surviving:
                continue
            for child in node.children:
                if child.name in targets:
                    continue
                if child.name not in surviving:
                    stack.append(child)
        while stack:
            node = stack.pop()
            if node.name in surviving or node.name in targets:
                continue
            surviving.add(node.name)
            stack.extend(node.children)

        kept = sum(node.self_us for node in self if node.name in surviving)
        return max(0, self.total_us - kept)

    def as_dict(self) -> dict:
        """Plain data, for ``--json`` and for comparing two runs."""

        def encode(node: ImportNode) -> dict:
            return {
                "name": node.name,
                "self_us": node.self_us,
                "cumulative_us": node.cumulative_us,
                "children": [encode(child) for child in node.children],
            }

        payload = {
            "total_us": self.total_us,
            "modules": len(self),
            "roots": [encode(root) for root in self.roots],
        }
        if self.repeat > 1:
            payload["repeat"] = self.repeat
            payload["min_us"] = self.min_us
            payload["max_us"] = self.max_us
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> ImportTree:
        def decode(raw: dict, depth: int, parent: ImportNode | None) -> ImportNode:
            node = ImportNode(
                name=raw["name"],
                self_us=int(raw["self_us"]),
                cumulative_us=int(raw["cumulative_us"]),
                depth=depth,
                parent=parent,
            )
            node.children = [decode(c, depth + 1, node) for c in raw.get("children", ())]
            return node

        roots = [decode(raw, 0, None) for raw in data.get("roots", ())]
        total = data.get("total_us")
        tree = cls(roots, total_us=int(total) if total is not None else None)
        tree.repeat = max(1, int(data.get("repeat") or 1))
        if "min_us" in data:
            tree.min_us = int(data["min_us"])
        if "max_us" in data:
            tree.max_us = int(data["max_us"])
        return tree


def median_us(values: list[int]) -> int:
    """Integer median. Even length uses the lower-middle pair averaged."""
    if not values:
        return 0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) // 2


def select_median_tree(trees: list[ImportTree]) -> ImportTree:
    """The profile whose total is closest to the median total."""
    if not trees:
        raise ValueError("no trees")
    totals = [tree.total_us for tree in trees]
    med = median_us(totals)
    return min(trees, key=lambda tree: (abs(tree.total_us - med), tree.total_us))
