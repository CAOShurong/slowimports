"""Colour, and the rules about when it means anything.

The eight categorical hues are a documented palette, validated for lightness
band, chroma floor, contrast against the surface, and separation under
simulated protanopia and deuteranopia. Both variants clear every gate on the
adjacent-pair list:

    dark   worst adjacent CVD dE 8.4, normal-vision dE 19.3
    light  worst adjacent CVD dE 9.1, normal-vision dE 19.6

Two consequences are enforced rather than left to habit:

* **Bars are one colour.** A bar's length already encodes its duration.
  Colouring it by that same duration spends the identity channel restating
  what the reader can already see.
* **Hues are never cycled.** Past eight packages there is no ninth colour
  that survives the simulation, so the tail is grouped as "other" and drawn
  in muted grey rather than given a colour that lies about being distinct.
"""

from __future__ import annotations

import os
import sys

__all__ = ["MAX_SERIES", "Palette"]

SERIES_DARK = (
    "#3987e5",  # blue
    "#d95926",  # orange
    "#199e70",  # aqua
    "#c98500",  # yellow
    "#d55181",  # magenta
    "#008300",  # green
    "#9085e9",  # violet
    "#e66767",  # red
)

SERIES_LIGHT = (
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#4a3aa7",
    "#e34948",
)

MAX_SERIES = len(SERIES_DARK)

INK_MUTED = "#898781"
AXIS_DARK = "#383835"
AXIS_LIGHT = "#c3c2b7"

#: Reserved status steps, distinct from the categorical slots so a warning
#: never impersonates a series.
STATUS_GOOD = "#0ca30c"
STATUS_WARNING = "#fab219"
STATUS_CRITICAL = "#d03b3b"


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _xterm256(rgb: tuple[int, int, int]) -> int:
    """Nearest xterm-256 index, trying the colour cube and the grey ramp.

    Near-grey values land closer on the ramp than in the cube; without
    checking both, muted grey chrome picks up a purple cast.
    """
    r, g, b = rgb
    levels = (0, 95, 135, 175, 215, 255)

    def nearest(v: int) -> int:
        return min(range(6), key=lambda i: abs(levels[i] - v))

    ri, gi, bi = nearest(r), nearest(g), nearest(b)
    cube_err = (levels[ri] - r) ** 2 + (levels[gi] - g) ** 2 + (levels[bi] - b) ** 2

    step = min(23, max(0, round(((r + g + b) / 3 - 8) / 10)))
    grey = 8 + 10 * step
    grey_err = (grey - r) ** 2 + (grey - g) ** 2 + (grey - b) ** 2

    return 232 + step if grey_err < cube_err else 16 + 36 * ri + 6 * gi + bi


def detect_depth(force: str | None = None, stream=None) -> str:
    """Colour capability: ``truecolor``, ``256``, ``16`` or ``none``."""
    if force:
        return force
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR"):
        return "none"
    if os.environ.get("TERM") == "dumb":
        return "none"
    if not hasattr(stream, "isatty") or not stream.isatty():
        return "none"
    if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
        return "truecolor"
    if os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM") in (
        "vscode",
        "iTerm.app",
        "WezTerm",
        "ghostty",
    ):
        return "truecolor"
    if "256" in os.environ.get("TERM", ""):
        return "256"
    return "256" if os.name == "nt" else "16"


class Palette:
    """Hex colours resolved to escape codes at the terminal's depth."""

    def __init__(self, *, dark: bool = True, depth: str | None = None, stream=None) -> None:
        self.dark = dark
        self.depth = detect_depth(depth, stream)
        self.series = SERIES_DARK if dark else SERIES_LIGHT
        self.axis_hex = AXIS_DARK if dark else AXIS_LIGHT

    @property
    def enabled(self) -> bool:
        return self.depth != "none"

    def fg(self, hex_color: str) -> str:
        if not self.enabled:
            return ""
        rgb = _hex_to_rgb(hex_color)
        if self.depth == "truecolor":
            return f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"
        if self.depth == "256":
            return f"\x1b[38;5;{_xterm256(rgb)}m"
        return f"\x1b[{self._nearest_ansi16(rgb)}m"

    @staticmethod
    def _nearest_ansi16(rgb: tuple[int, int, int]) -> int:
        basics = {
            31: (205, 49, 49),
            32: (13, 188, 121),
            33: (229, 229, 16),
            34: (36, 114, 200),
            35: (188, 63, 188),
            36: (17, 168, 205),
            37: (229, 229, 229),
            90: (102, 102, 102),
            91: (241, 76, 76),
            92: (35, 209, 139),
            93: (245, 245, 67),
            94: (59, 142, 234),
            95: (214, 112, 214),
            96: (41, 184, 219),
        }
        return min(
            basics,
            key=lambda code: sum((basics[code][i] - rgb[i]) ** 2 for i in range(3)),
        )

    def series_fg(self, slot: int) -> str:
        """Colour for categorical slot ``slot``; muted grey beyond the eighth."""
        if not 0 <= slot < MAX_SERIES:
            return self.muted()
        return self.fg(self.series[slot])

    def primary(self) -> str:
        """The single hue bars are drawn in."""
        return self.fg(self.series[0])

    def muted(self) -> str:
        return self.fg(INK_MUTED)

    def axis(self) -> str:
        return self.fg(self.axis_hex)

    def status(self, level: str) -> str:
        return self.fg(
            {"good": STATUS_GOOD, "warning": STATUS_WARNING, "critical": STATUS_CRITICAL}.get(
                level, INK_MUTED
            )
        )

    def reset(self) -> str:
        return "\x1b[0m" if self.enabled else ""

    def bold(self) -> str:
        return "\x1b[1m" if self.enabled else ""

    def dim(self) -> str:
        return "\x1b[2m" if self.enabled else ""
