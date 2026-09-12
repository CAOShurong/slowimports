---
schema_version: portable-project-memory/v1
handoff_revision: 1
updated_at: "2026-09-13T00:25:00+08:00"
updated_by: "grok-unattended-init"
base_revision: git:34fe1303c3c2f0cd8e0de1e6208fd430a0453ac7
workspace_fingerprint: sha256:90e6de8fec56c69fa38c17195b4434cd1ee912680bdaa55ef1a8b4dc2631faba
context_fingerprint: sha256:0d2bd8aa85605d2088b2e3ad460958938b59b7a4a353f4c2c6b5b18748f18d4c
status: active
---

# Project Handoff

## Current objective

Make `slowimports` the launch-quality star vehicle: `--apply` correct,
README first screen shows a **real** rewrite, CI green, `docs/LAUNCH.md`
paste-ready. Do not add more CI-flag clones.

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
