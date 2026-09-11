"""slowimports - find out why your Python program is slow to start.

Measures where import time actually goes, then reads your source to work out
which of those imports can safely move inside the functions that use them::

    slowimports myscript.py --advice

The pieces are usable directly if you want to build on them: run a target
with :func:`~slowimports.runner.run_profile`, turn its stderr into a tree with
:func:`~slowimports.parse.parse_importtime`, and ask that tree what dropping a
module would save.
"""

from __future__ import annotations

__version__ = "0.4.0"
__all__ = [
    "ImportNode",
    "ImportTree",
    "__version__",
    "analyze_source",
    "main",
    "parse_importtime",
    "run_profile",
]


def __getattr__(name: str):
    """Resolve public names lazily.

    A tool about import cost that imported its whole world at startup would
    be quoting a price it does not pay itself.
    """
    if name in ("ImportNode", "ImportTree"):
        from . import model

        return getattr(model, name)
    if name == "parse_importtime":
        from .parse import parse_importtime

        return parse_importtime
    if name == "run_profile":
        from .runner import run_profile

        return run_profile
    if name == "analyze_source":
        from .analyze import analyze_source

        return analyze_source
    if name == "main":
        from .cli import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
