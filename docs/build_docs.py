#!/usr/bin/env python3
"""Generate README.md, including the screenshots, from real runs.

Every image and every code block in the README is produced by running the
tool, so a rendering change shows up as a README diff rather than as
documentation quietly drifting away from the code.

    python docs/build_docs.py            # regenerate
    python docs/build_docs.py --check    # fail if it would change (for CI)

Images need Pillow, which is not a runtime dependency:

    python -m pip install pillow
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "docs" / "readme_template.md"
README = ROOT / "README.md"
EXAMPLE = "examples/slow_cli.py"
# Rendering from a committed profile rather than measuring afresh. Import time
# is wall-clock time, so a live run gives different milliseconds every
# invocation and --check could never pass; with a fixed profile the figures
# are the same on every machine, which makes the CI freshness gate meaningful.
PROFILE = "docs/example-profile.json"

SGR = re.compile(r"\x1b\[([0-9;]*)m")

BACKGROUND = "#1a1a19"
DEFAULT_INK = "#c3c2b7"

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\consola.ttf",
    r"C:\Windows\Fonts\cour.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
]

# Each figure: placeholder -> (image name, width, extra CLI arguments).
FIGURES = {
    "<!--SHOT_ADVICE-->": ("advice", 88, ["--from", PROFILE, EXAMPLE, "--advice"]),
    "<!--SHOT_PACKAGES-->": (
        "packages",
        88,
        ["--from", PROFILE, EXAMPLE, "--packages", "-n", "10"],
    ),
}

# Text blocks are captured with colour off, so they stay copy-pasteable.
BLOCKS = {
    "<!--TEXT_PACKAGES-->": (
        84,
        ["--from", PROFILE, EXAMPLE, "--packages", "-n", "8"],
    ),
}


def capture(width: int, extra: list[str], *, colour: bool) -> str:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    env["COLUMNS"] = str(width)
    argv = [
        sys.executable,
        "-m",
        "slowimports",
        "--width",
        str(width),
        "--color",
        "truecolor" if colour else "none",
        *extra,
    ]
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=ROOT,
        check=False,
    )
    if not result.stdout.strip():
        raise SystemExit(f"capture produced nothing: {' '.join(extra)}\n{result.stderr}")
    return result.stdout.rstrip("\n")


def load_font(size: int):
    from PIL import ImageFont

    for path in FONT_CANDIDATES:
        if pathlib.Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    from PIL import ImageFont as fallback

    return fallback.load_default()


def split_runs(line: str) -> list[tuple[str, str]]:
    """Split a styled line into ``(text, hex colour)`` runs."""
    runs: list[tuple[str, str]] = []
    colour = DEFAULT_INK
    pos = 0
    for match in SGR.finditer(line):
        if match.start() > pos:
            runs.append((line[pos : match.start()], colour))
        params = match.group(1)
        if params in ("", "0"):
            colour = DEFAULT_INK
        elif params.startswith("38;2;"):
            r, g, b = (int(v) for v in params.split(";")[2:5])
            colour = f"#{r:02x}{g:02x}{b:02x}"
        pos = match.end()
    if pos < len(line):
        runs.append((line[pos:], colour))
    return runs


def render_png(text: str, out: pathlib.Path, *, font_size: int = 14) -> None:
    from PIL import Image, ImageDraw

    font = load_font(font_size)
    bbox = font.getbbox("M")
    cw = max(1, bbox[2] - bbox[0])
    ch = int(font_size * 1.42)
    pad = 14

    lines = text.split("\n")
    plain = [SGR.sub("", line) for line in lines]
    width = cw * (max(len(p) for p in plain) + 1) + pad * 2
    height = ch * len(lines) + pad * 2

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    for row, line in enumerate(lines):
        x = pad
        y = pad + row * ch
        for chunk, colour in split_runs(line):
            if not chunk:
                continue
            draw.text((x, y), chunk, font=font, fill=colour)
            x += cw * len(chunk)
    image.save(out, optimize=True)


def build() -> str:
    text = TEMPLATE.read_text(encoding="utf-8")

    for placeholder, (name, width, extra) in FIGURES.items():
        if placeholder not in text:
            raise SystemExit(f"template is missing {placeholder}")
        out = ROOT / "docs" / f"{name}.png"
        render_png(capture(width, extra, colour=True), out)
        # An absolute URL so the image also renders on the PyPI project page,
        # where relative links do not resolve.
        url = f"https://raw.githubusercontent.com/CAOShurong/slowimports/main/docs/{name}.png"
        text = text.replace(placeholder, f"![{name}]({url})")

    for placeholder, (width, extra) in BLOCKS.items():
        if placeholder not in text:
            raise SystemExit(f"template is missing {placeholder}")
        text = text.replace(
            placeholder, "```\n" + capture(width, extra, colour=False) + "\n```"
        )
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="exit non-zero if README.md is out of date"
    )
    args = parser.parse_args()

    generated = build()
    if args.check:
        current = README.read_text(encoding="utf-8") if README.exists() else ""
        if current != generated:
            print("README.md is out of date; run: python docs/build_docs.py")
            return 1
        print("README.md is up to date.")
        return 0

    README.write_text(generated, encoding="utf-8")
    print(f"wrote {README.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
