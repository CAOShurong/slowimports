---
schema_version: portable-project-memory/v1
project_name: "slowimports"
updated_at: "2026-09-13T00:25:00+08:00"
---

# Project Context

## Objective

Measure Python **import-time** (not a sampling profiler) and **rewrite**
source so imports used only inside functions move there. The user-facing
promise is: `--help` gets faster because unused branches stop paying import
cost at startup.

## Deliverables

- Installable package `slowimports` (PyPI + git).
- CLI: profile, `--advice`, `--apply` / `--apply-dry-run`, CI gates.
- Honest README first screen (real `--apply` on `examples/slow_cli.py`).
- Paste-ready Show HN text in `docs/LAUNCH.md`.
- Tests + GitHub Actions CI.

## Scope and non-goals

### In scope

- CPython `-X importtime` / `PYTHONPROFILEIMPORTTIME`.
- AST analysis of which imports are function-only.
- Safe rewrite: split `import a, b`, refuse site-packages, honour `--min-saving`.
- Zero runtime dependencies.

### Out of scope

- Sampling CPU profilers (cProfile, pyinstrument).
- PEP 810 `lazy import` (that is flake8-lazy).
- Upstream PRs to other projects.
- Asking the user to review, approve, or post to HN.
- Other CAOShurong repos (portfolio sequence lives in HANDOFF next-actions
  and the user-level unattended handoff file).

## Project map

| Path | Purpose | Source of truth |
|---|---|---|
| `src/slowimports/cli.py` | CLI | code |
| `src/slowimports/rewrite.py` | `--apply` rewrite | code |
| `src/slowimports/analyze.py` | AST deferrability | code |
| `examples/slow_cli.py` | Demo target | code |
| `docs/LAUNCH.md` | Show HN paste | file |
| `README.md` | First-screen pitch | file |
| `HANDOFF.md` | Current agent state | this protocol |

## Commands and verification

| Purpose | Command | Expected |
|---|---|---|
| Tests | `python -m pytest tests` with `PYTHONPATH=src` | pass |
| Apply dry-run | `python -m slowimports examples/slow_cli.py --apply-dry-run` | unified diff, json stays top-level |
| Package | `pip install slowimports` | PyPI |

## Constraints

- Python 3.9+.
- User will not send messages in unattended mode; do not block on them.
- Do not burn quota with 60-second loops. Current cadence: 10 minutes.
- Push `origin main` yourself. No force-push.
- User will not submit HN; keep `docs/LAUNCH.md` current anyway.

## Data and provenance

- Import-time numbers in README must come from a real local run, not invented.

## Runtime and capability dependencies

- CPython (importtime). Not guaranteed on other interpreters.

## Definition of done

~90% for this repo (then leave; do not grind 90→100):

- `--apply` tested, refuses site-packages, splits combined imports.
- README states what apply will and will not do; first-screen numbers are real.
- `docs/LAUNCH.md` paste-ready. CI green on `main`.
- Then pytest-importcost to the same bar. New AI-topic repo only after those
  existing rounds, not immediately.
