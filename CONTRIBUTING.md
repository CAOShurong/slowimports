# Contributing to slowimports

Thanks for taking a look. Issues and pull requests are both welcome.

## The bug report that matters most

**An import slowimports said was safe to defer, but was not.** That is a
correctness failure in the analyser, and it is the one thing this project
cannot afford to get wrong: someone follows the advice, moves an import, and
finds out through a `NameError` on a path they did not test.

Please include the file, or the smallest version of it that still reproduces,
and what happened when you moved the import.

## Getting set up

```bash
git clone https://github.com/CAOShurong/slowimports
cd slowimports
python -m pip install -e ".[dev]"
```

The suite is standard-library only, so it also runs against a bare
interpreter with nothing installed — CI checks that, because the core is
meant to stay dependency-free:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

## Before opening a pull request

```bash
ruff check src tests docs examples
ruff format src tests docs examples
python -m unittest discover -s tests
python docs/build_docs.py --check
```

The README's figures are rendered by the tool from
[`docs/example-profile.json`](docs/example-profile.json). If you change
anything about rendering, run `python docs/build_docs.py` (needs Pillow) and
commit the result.

## Things decided on purpose

**The analyser is one-sided.** It reports an import only when every use is
provably inside a function body. Widening it to "probably safe" trades a
guarantee for a few more suggestions, which is the wrong trade for advice
people apply without checking.

**Savings are not cumulative times.** A module's subtree is mostly shared, and
dropping it does not free the parts other things still need. Anything that
reports cumulative time as a saving is overstating.

**Set savings are computed for the set.** Summing per-import figures
understates when candidates share a dependency and overstates when one
contains another.

**Bars are one colour.** Bar length encodes duration; colouring by duration as
well spends the identity channel restating it.

**No dependencies in the core.** A tool that measures import cost should not
add any of its own. A new non-stdlib import in `src/slowimports/` needs a
strong reason.

## Style

`ruff format` decides formatting. Beyond that, comments should say *why* — the
*what* is usually already in the code.

## License

Contributions are accepted under the [MIT license](LICENSE).
