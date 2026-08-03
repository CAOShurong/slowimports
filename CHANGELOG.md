# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/CAOShurong/slowimports/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/CAOShurong/slowimports/releases/tag/v0.1.1
[0.1.0]: https://github.com/CAOShurong/slowimports/releases/tag/v0.1.0
