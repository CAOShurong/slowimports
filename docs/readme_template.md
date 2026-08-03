# slowimports

**Find out why your Python program is slow to start — and what to do about it.**

[![CI](https://github.com/CAOShurong/slowimports/actions/workflows/ci.yml/badge.svg)](https://github.com/CAOShurong/slowimports/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/slowimports.svg)](https://pypi.org/project/slowimports/)
[![Python](https://img.shields.io/pypi/pyversions/slowimports.svg)](https://pypi.org/project/slowimports/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Every Python CLI eventually gets slow to launch, and it is almost never the
code that runs. It is an import at the top of a file that is only needed on one
branch, pulling half a dependency tree in before `--help` can print.

`python -X importtime` will tell you where the milliseconds went, in nine
hundred lines of nested output. slowimports reads that, and then reads *your
source*, and tells you which imports you can actually move:

<!--SHOT_ADVICE-->

That last part is the point. Knowing `unittest.mock` costs 64 ms is trivia;
knowing it is only referenced inside one function, and that moving it there
recovers those 64 ms, is a change you can make in ten seconds.

## Install

```console
$ pip install slowimports
```

**No dependencies.** A tool that measures import cost has no business adding
any of its own — `subprocess` runs the target, `ast` reads the source, and
that is the whole shopping list. Python 3.9+, Linux, macOS and Windows.

## Use

```console
$ slowimports myscript.py            # a script
$ slowimports -m pytest              # a module
$ slowimports mytool                 # an installed command
$ slowimports -c 'import pandas'     # a single import
```

The default view groups by package, because that is the level you act on —
nobody removes `numpy.linalg`, they remove `numpy`:

<!--TEXT_PACKAGES-->

<!--SHOT_PACKAGES-->

Add `--advice` for the analysis, `--modules` to rank individual modules,
`--tree` for an icicle chart of the import graph, or `--all` for everything.

## How the advice works

It reads your file with `ast` and reports an import only when **every** use of
the bound name is inside a function body. Anything touched while the module is
being imported is left alone, because moving it would turn a working program
into a `NameError` on some path you did not test.

Disqualifying uses, all of which run at import time:

| | |
|---|---|
| module-level code | assignments, calls, `if` tests, loops |
| class bodies | they execute during import |
| decorators | `@functools.cache` |
| base classes | `class C(enum.Enum)` |
| default arguments | `def f(x=json.dumps({}))` |
| annotations | unless `from __future__ import annotations` makes them strings |
| rebinding | `json = something_else` later in the file |
| `global` declarations | the name may be reassigned |

Star imports are never reported: what `from x import *` binds is not knowable
without importing it, so nothing can be proven about the uses.

The analysis is deliberately one-sided. It will miss safe moves rather than
suggest an unsafe one.

## The saving is not the cumulative time

A module's `cumulative` figure counts everything it imported, and most of that
is shared. Dropping `pandas` does not give you back the `re` and `enum` that
five other things also need.

So the reported saving is what would actually be recovered: the total minus
whatever still gets imported once that module is gone. And the headline figure
for a set of imports is computed for the set, not summed — candidates that
share a dependency each exclude it, so adding the individual numbers
understates, while candidates that contain one another overlap, so it
overstates.

## Before and after

```console
$ slowimports app.py --save before.json
# ... make the changes ...
$ slowimports app.py --compare before.json
```

which reports the difference, plus which packages stopped being imported and
which started.

## Everything else

| | |
|---|---|
| `--json` | the profile as data |
| `-n N` | how many rows |
| `--min-saving MS` | ignore advice worth less than this (default 1 ms) |
| `--ascii` | no block-drawing characters |
| `--light` | colours stepped for a light terminal |
| `--python PATH` | measure a different interpreter |
| `-- ARGS` | everything after `--` goes to the target |

Colour degrades from 24-bit through 256 and 16 to none, and honours
`NO_COLOR`. Output is plain text when redirected, so `slowimports app.py >
report.txt` gives you a clean file.

## About the colours

The icicle chart's eight hues are a documented palette, checked by script for
lightness band, chroma floor, contrast against the background, and separation
under simulated protanopia and deuteranopia. Bars are deliberately a single
colour: a bar's length already encodes its duration, so colouring it by
duration too would spend the identity channel restating what length says.
Past eight packages the tail is drawn in grey rather than given a ninth hue
that would not survive the simulation.

## Contributing

Bug reports and pull requests welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
The test suite needs nothing installed:

```console
$ python -m unittest discover -s tests
```

If slowimports suggests an import that turns out not to be safe to move, that
is the most valuable bug you can report. Please include the file, or the
smallest version of it that still reproduces.

## License

MIT — see [LICENSE](LICENSE).
