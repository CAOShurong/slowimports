"""Draw the report.

Three views, each answering a different question:

``bars``     which single modules cost the most
``icicle``   where the time sits in the import graph
``advice``   what to change, and what it buys

The bars are all one colour on purpose. Bar length already encodes duration,
so colouring by duration too would spend the identity channel restating what
length already says. The icicle chart *does* colour, because there identity
-- which package a block belongs to -- is genuinely a second dimension.
"""

from __future__ import annotations

from .model import ImportNode, ImportTree
from .palette import MAX_SERIES, Palette

__all__ = ["Renderer"]

FULL, PARTIALS = "█", " ▏▎▍▌▋▊▉"
ASCII_FULL, ASCII_PARTIAL = "#", "-"


def format_ms(us: int) -> str:
    """Durations at a precision a reader can act on."""
    ms = us / 1000.0
    if ms >= 1000:
        return f"{ms / 1000:.2f} s"
    if ms >= 100:
        return f"{ms:.0f} ms"
    if ms >= 10:
        return f"{ms:.1f} ms"
    return f"{ms:.2f} ms"


def truncate(text: str, width: int, ellipsis: str = "…") -> str:
    """Shorten from the left, because the tail of a dotted path identifies it.

    "...linalg.lapack_lite" says more than "numpy.linalg.la...".

    ``ellipsis`` is a parameter rather than a constant so ASCII mode stays
    ASCII: a single U+2026 leaking into otherwise-plain output is enough to
    make it undecodable on a terminal that asked for none.
    """
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= len(ellipsis):
        return text[:width]
    return ellipsis + text[-(width - len(ellipsis)) :]


class Renderer:
    """Formats a profile as styled terminal rows."""

    def __init__(self, palette: Palette, *, unicode: bool = True, width: int = 80):
        self.palette = palette
        self.unicode = unicode
        self.width = max(40, width)
        self.ellipsis = "…" if unicode else "~"

    # -- primitives --------------------------------------------------------

    def bar(self, fraction: float, cells: int) -> str:
        """A horizontal bar with sub-cell resolution.

        Eighth-block characters give eight times the resolution of whole
        cells, which is what keeps the small entries in a long tail visibly
        different from each other instead of all rounding to nothing.
        """
        fraction = min(1.0, max(0.0, fraction))
        if not self.unicode:
            filled = round(fraction * cells)
            return (ASCII_FULL * filled).ljust(cells, " ") if filled else " " * cells
        exact = fraction * cells
        whole = int(exact)
        remainder = exact - whole
        out = FULL * whole
        if whole < cells:
            eighth = int(remainder * 8)
            out += PARTIALS[eighth] if eighth else " "
        return out.ljust(cells, " ")[:cells]

    def _short(self, text: str, width: int) -> str:
        return truncate(text, width, self.ellipsis)

    def _style(self, text: str, code: str) -> str:
        if not self.palette.enabled or not code:
            return text
        return f"{code}{text}{self.palette.reset()}"

    # -- views -------------------------------------------------------------

    def bars(self, tree: ImportTree, limit: int = 15, *, by: str = "self") -> list[str]:
        """The heaviest modules as a ranked bar chart."""
        nodes = tree.slowest(limit, by=by)
        if not nodes:
            return ["  (nothing measured)"]

        pal = self.palette
        name_w = min(38, max(len(n.name) for n in nodes) + 1)
        time_w = 9
        bar_w = max(10, self.width - name_w - time_w - 6)
        biggest = max((n.self_us if by == "self" else n.cumulative_us) for n in nodes)
        biggest = max(biggest, 1)

        rows = []
        for node in nodes:
            value = node.self_us if by == "self" else node.cumulative_us
            label = self._short(node.name, name_w).ljust(name_w)
            bar = self.bar(value / biggest, bar_w)
            rows.append(
                "  "
                + self._style(label, pal.muted())
                + self._style(bar, pal.primary())
                + " "
                + format_ms(value).rjust(time_w)
            )
        return rows

    def packages(self, tree: ImportTree, limit: int = 12) -> list[str]:
        """Cost grouped by top-level package.

        Usually the more actionable view: nobody removes ``numpy.linalg``,
        they remove ``numpy``.
        """
        costs = tree.top_level_costs()
        if not costs:
            return ["  (nothing measured)"]
        items = list(costs.items())[:limit]
        pal = self.palette
        name_w = min(28, max(len(name) for name, _ in items) + 1)
        bar_w = max(10, self.width - name_w - 20)
        biggest = max(us for _, us in items) or 1
        total = tree.total_us or 1

        rows = []
        for name, us in items:
            share = us / total * 100
            rows.append(
                "  "
                + self._style(self._short(name, name_w).ljust(name_w), pal.muted())
                + self._style(self.bar(us / biggest, bar_w), pal.primary())
                + " "
                + format_ms(us).rjust(9)
                + self._style(f" {share:4.1f}%", pal.muted())
            )
        return rows

    def icicle(self, tree: ImportTree, *, max_depth: int = 4) -> list[str]:
        """The import graph as nested proportional blocks.

        Each row is one level of depth, and a block's width is its share of
        the total. Colour identifies the top-level package, so a block can be
        traced to its owner across rows. Beyond eight packages the tail is
        drawn muted rather than given a ninth colour that would not survive
        colour-vision simulation.
        """
        total = tree.total_us
        if total <= 0:
            return ["  (nothing measured)"]

        packages = list(tree.top_level_costs())
        slot_of = {name: i for i, name in enumerate(packages[:MAX_SERIES])}

        rows: list[str] = []
        level: list[ImportNode] = list(tree.roots)
        inner = self.width - 2

        for _ in range(max_depth):
            if not level:
                break
            level.sort(key=lambda n: n.cumulative_us, reverse=True)
            row = []
            used = 0
            for node in level:
                cells = round(node.cumulative_us / total * inner)
                if cells < 1:
                    continue
                cells = min(cells, inner - used)
                if cells < 1:
                    break
                row.append(self._block(node, cells, slot_of))
                used += cells
                if used >= inner:
                    break
            if not row:
                break
            rows.append("  " + "".join(row))
            level = [child for node in level for child in node.children]

        named = ", ".join(packages[:MAX_SERIES])
        separator = "  ·  " if self.unicode else "  -  "
        tail = (
            f"{separator}everything else grey (eight hues is the most that "
            "stays colour-vision safe)"
            if len(packages) > MAX_SERIES
            else ""
        )
        rows.append(self._style(f"  coloured: {named}{tail}", self.palette.muted()))
        return rows

    #: A block narrower than this is drawn as solid colour with no text.
    #: Cramming a name into three columns produces "…rg" for every one of
    #: them, which is noise wearing the costume of information.
    MIN_LABEL_CELLS = 7

    def _block(self, node: ImportNode, cells: int, slot_of: dict[str, int]) -> str:
        """One block of the icicle: a label if it fits, otherwise solid fill."""
        slot = slot_of.get(node.top_level)
        code = self.palette.series_fg(slot) if slot is not None else self.palette.muted()
        if cells >= self.MIN_LABEL_CELLS:
            name = node.name if len(node.name) <= cells - 1 else node.top_level
            body = (" " + self._short(name, cells - 1)).ljust(cells)[:cells]
        else:
            body = (FULL if self.unicode else ASCII_FULL) * cells
        return self._style(body, code)

    # -- chrome ------------------------------------------------------------

    def heading(self, text: str) -> str:
        pal = self.palette
        return "\n" + self._style(text, pal.bold())

    def summary(self, tree: ImportTree, target: str) -> list[str]:
        pal = self.palette
        total = tree.total_us
        level = "good" if total < 100_000 else "warning" if total < 400_000 else "critical"
        verdict = {
            "good": "fast",
            "warning": "noticeable",
            "critical": "slow",
        }[level]
        return [
            self._style(target, pal.bold()),
            "  "
            + self._style(format_ms(total), pal.status(level))
            + f" of import time across {len(tree)} modules"
            + self._style(f"  ({verdict})", pal.muted()),
        ]
