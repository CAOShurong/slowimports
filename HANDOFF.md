---
schema_version: portable-project-memory/v1
handoff_revision: 2
updated_at: "2026-09-13T01:10:00+08:00"
updated_by: "grok-unattended"
base_revision: git:d813ff5a51e5a63f4ae28455c16e0011a944a0fa
workspace_fingerprint: sha256:e15a2e9f7a39655748faa2c4c03790b930a89e6f9d42f506c0bbf02ba9f4f471
context_fingerprint: sha256:55168ecc161fadc835475912de8930dc33b86158b74b6025dcc3a82355305c3e
status: active
---

# Project Handoff

## Current objective

Take this repo to ~90%, not 100%. README must be rigorous (what `--apply`
does and does not do). Then **leave** and do the same for pytest-importcost.
Do not open a new AI repo until those existing rounds are done.

## Confirmed state

- GitHub: https://github.com/CAOShurong/slowimports (public). PyPI: `slowimports`.
- Default branch `main`. Last known launch-docs commit: `34fe130`.
- `--apply` exists (`rewrite.py`): splits `import a, b`, refuses site-packages,
  honours `--min-saving`.
- Example dry-run (this machine): ~169 ms recoverable on `examples/slow_cli.py`;
  `json` stays at import time.
- Unattended loop: 10 min, id `01a09668-b5e8-7043-85e6-ce950f55846e`.
- User is not sending messages. Quota must not use 60-second fires.

## Changed artifacts

| Path | Change | State |
|---|---|---|
| `src/slowimports/rewrite.py` | apply engine | on main |
| `README.md` | real --apply first screen | on main (`34fe130`) |
| `docs/LAUNCH.md` | Show HN paste | on main |
| this protocol | initialized | this commit |

## Verification evidence

| Check | Result | Basis |
|---|---|---|
| pytest | PASS historically (144) | last apply work |
| apply dry-run example | PASS | local run, 169 ms recoverable |

## Decisions referenced

- `D-20260913-002500-si001`: unattended sequence; no 60s; no calculator sprawl.

## Risks and unknowns

- Stars will not move without a Show HN / Reddit paste. User will not post.
  Agents cannot use the user's HN account.
- README 169 ms is machine-specific; do not treat as a benchmark.

## Next actions

1. Keep `--apply` correct; CI green; first screen honest.
2. When that is true, **do not stop**. Continue in the sibling repo
   `pytest-importcost` (init protocol there if missing).
3. Then `termscope`, then the STM32 car repo. Sequence is in the user-level
   unattended handoff file, not in chat.

## Coordination boundary

This repository only until step 2. No upstream PRs. No new calculators.

## Claims that remain prohibited

- Do not call `--apply` a PEP 810 `lazy` rewriter.
- Do not invent import-time numbers.

## User decisions required

None. User is unattended.
