"""Read ``-X importtime`` output into a tree.

The format is stable but awkward. CPython prints a line per module::

    import time:      1234 |       5678 |   json.decoder

and encodes the graph in two ways at once: the third column's leading spaces
give the depth, and children are printed *before* their parent, because a
module's own time is only known once its imports have finished.

So the parser reads bottom-up: it keeps a stack of pending deeper nodes, and
when a shallower line arrives, everything deeper than it on the stack is that
line's children.

Everything here tolerates junk. The target program's own stderr is
interleaved with the profile, and a program that writes a progress bar to
stderr must not break the parse.
"""

from __future__ import annotations

import re

from .model import ImportNode, ImportTree

__all__ = ["ParseError", "parse_importtime"]

# "import time:      1234 |       5678 |   json.decoder"
# The name field keeps its leading spaces: that is where depth lives.
_LINE = re.compile(
    r"^import time:\s*(?P<self>\d+)\s*\|\s*(?P<cumulative>\d+)\s*\|(?P<name>.*)$"
)
_HEADER = re.compile(r"^import time:\s*self\s*\[us\]")

#: CPython indents each level by two spaces.
_INDENT = 2


class ParseError(ValueError):
    """The output contained no import-time lines at all."""


def _depth_of(raw_name: str) -> int:
    stripped = raw_name.lstrip(" ")
    return (len(raw_name) - len(stripped)) // _INDENT


def parse_importtime(text: str) -> ImportTree:
    """Build an :class:`~slowimports.model.ImportTree` from importtime output.

    Raises :class:`ParseError` when nothing parseable is present, which in
    practice means the target failed before importing anything -- a much more
    useful thing to say than returning an empty tree.
    """
    # (depth, node) for nodes not yet attached to a parent.
    pending: list[tuple[int, ImportNode]] = []
    roots: list[ImportNode] = []
    seen_any = False

    for line in text.splitlines():
        if _HEADER.match(line):
            continue
        match = _LINE.match(line)
        if match is None:
            continue  # the target's own stderr; not ours to interpret
        raw_name = match.group("name")
        name = raw_name.strip()
        if not name:
            continue
        seen_any = True
        depth = _depth_of(raw_name)
        node = ImportNode(
            name=name,
            self_us=int(match.group("self")),
            cumulative_us=int(match.group("cumulative")),
            depth=depth,
        )

        # Everything still pending that sits deeper than this line was
        # imported by it. They were printed first, so they come off in
        # reverse and are put back in source order.
        children: list[ImportNode] = []
        while pending and pending[-1][0] > depth:
            children.append(pending.pop()[1])
        children.reverse()
        for child in children:
            child.parent = node
        node.children = children

        pending.append((depth, node))

    if not seen_any:
        raise ParseError("no '-X importtime' lines found in the output")

    # Whatever is left unattached is a root. Deeper leftovers can only happen
    # on truncated output; keeping them avoids silently dropping measurements.
    for _, node in pending:
        roots.append(node)
    return ImportTree(roots)


def strip_importtime(text: str) -> str:
    """The target's own stderr, with the profile lines removed.

    Worth showing separately: if a program printed a warning while being
    profiled, hiding it would be confusing, and leaving it interleaved with
    a thousand profile lines is no better.
    """
    kept = [
        line for line in text.splitlines() if not _LINE.match(line) and not _HEADER.match(line)
    ]
    return "\n".join(kept).strip()
