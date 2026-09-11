# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `--apply` rewrites a `.py` file: single-name imports that `--advice`
  would list are moved into the functions that use them. `--apply-dry-run`
  prints a unified diff. Combined `import a, b` lines are left alone.
- `--repeat N` measures N times and ranks the **median** total. Import-time
  is wall-clock; a single run will flake a tight `--budget-ms`. `--json`
  includes `repeat`, `min_us`, and `max_us`.
- `--forbid pandas,torch` fails with exit code 1 if those packages (or
  modules) appear in the startup import graph. `--json` includes `forbid_ok`.
  A time budget still passes on a fast runner when someone imports pandas;
  a forbid list does not.
- `--advice` now reads the source of `-m MODULE` and installed console scripts,
  not only a path that already ends in `.py`. `slowimports -m myapp --advice`
  is the command the first screen already showed.
- `--compare` lists packages that got slower or faster (ignoring sub-ms
  jitter), not only packages that appeared or disappeared.
- `--slower-ms` fails with exit code 1 when total import time grew by more
  than that many milliseconds versus a `--compare` profile. `--json` includes
  `slower_ok`.
- `--budget-ms` fails with exit code 1 when total import time exceeds a CI
  budget. `--json` includes `budget_ms` and `budget_ok` when the flag is set.

### Fixed

- README is generated from `docs/readme_template.md` again. The uvx one-liner
  and PyPI downloads badge now live in the template, so `docs/build_docs.py
  --check` stays green.
- `--advice` no longer treats `if TYPE_CHECKING:` imports as runtime
  candidates. Those names are not loaded, so suggesting they move would be
  wrong.

## [0.2.1] — 2026-08-12

### Fixed

- `--json` now returns a nonzero status when the profiled target fails, just
  like the terminal renderer, while still emitting the usable import profile.
- Captured target stdout and stderr now default to UTF-8 on every platform,
  matching the runner's decoder. This prevents Unicode output from failing a
  target or becoming mojibake on non-UTF-8 Windows locales. An explicitly set
  `PYTHONIOENCODING` is still honoured.

### Documented

- CPython warns that `-X importtime` output can be broken for multithreaded
  imports; SlowImports cannot reconstruct missing or interleaved events.
- Child-process imports are outside the parent profile unless the child emits
  its own trace, and combining multiple traces is unsupported.

## [0.2.0] — 2026-08-11

### Fixed

- Installed `console_scripts` commands can now be profiled on Windows. Their
  native `.exe` launchers are resolved through the selected Python
  interpreter's standard package metadata or a bounded embedded wrapper,
  including installer-generated aliases such as `pip3.13`.
- Console-script resolution now refuses an interpreter mismatch or ambiguous
  or conflicting launcher data rather than silently profiling a same-named
  module from the wrong environment. Entry-point functions are never loaded
  or run.

## [0.1.1] — 2026-08-03

### Fixed

- Repository and image URLs, after the GitHub account was renamed from
  `TeresaCSR` to `CAOShurong`. GitHub redirects repository links, but
  `raw.githubusercontent.com` does not, so the screenshots in the project
  description on PyPI stopped loading. A published description is a snapshot,
  which is why this needs a release rather than a commit.

## [0.1.0] — 2026-08-03

First release.

### Added

- **Import-time profiling** of a script, a module, an installed console
  script, or a one-line snippet, by running it under `-X importtime` in a
  subprocess and parsing the result into a tree.
- **Deferrable-import analysis.** Reads the target's source with `ast` and
  reports an import only when every use of the bound name is inside a function
  body. Module-level code, class bodies, decorators, base classes, default
  arguments, annotations without `from __future__ import annotations`,
  rebinding and `global` declarations all disqualify a name, so the advice
  errs towards missing a safe move rather than suggesting an unsafe one.
- **Savings that mean something.** A module's reported saving is what would
  actually be recovered — its cost minus whatever still gets imported once it
  is gone — and the headline figure for a set of imports is computed for the
  set rather than summed, because summing is wrong in both directions.
- **Three views**: cost by package (the default, and the level people act on),
  a ranked bar chart of individual modules, and an icicle chart of the import
  graph.
- **`--save` / `--compare`** for before-and-after work, reporting the delta
  plus which packages stopped and started being imported.
- **`--from`** renders a saved profile without measuring again, for a profile
  someone sent you — and it is what makes this project's own README
  reproducible.
- **A validated colour palette.** Eight categorical hues checked for lightness
  band, chroma floor, surface contrast and separation under simulated
  protanopia and deuteranopia. Bars are a single colour, since length already
  encodes duration; hues are never cycled past eight.
- **Graceful degradation**: 24-bit colour down through 256, 16 and none, block
  drawing down to ASCII, and a UTF-8 switch for CJK-locale Windows consoles
  whose default encoding cannot carry block characters.
- **Zero dependencies.**

[Unreleased]: https://github.com/CAOShurong/slowimports/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/CAOShurong/slowimports/releases/tag/v0.2.1
[0.2.0]: https://github.com/CAOShurong/slowimports/releases/tag/v0.2.0
[0.1.1]: https://github.com/CAOShurong/slowimports/releases/tag/v0.1.1
[0.1.0]: https://github.com/CAOShurong/slowimports/releases/tag/v0.1.0
