# Decisions

# Decision Log

## D-20260913-002500-si001

### Unattended focus is this repo until launch-ready, then the next named product
- Status: accepted
- Date: 2026-09-13
- Deciders: user (无人值守, 只做 slowimports, 额度不要刷太快, HANDOFF 作长期记忆)

### Context

Stopping because "this repo looks done" caused empty nights. A 60-second
loop exhausted Grok Build quota (HTTP 402). Markdown-only and a stream of
tiny calculators (baudfit, i2cpullup) were rejected as 伪需求.

### Decision

- While HANDOFF current objective is slowimports, touch no other repo.
- After launch-ready (apply + first-screen + CI green + LAUNCH.md), the next
  agent must open `pytest-importcost`, not idle and not mint calculators.
- Recurring loop interval ≥ 10 minutes. Skip-if-busy. Never self-delete
  because one fire is idle.
- Durable state lives in this protocol (`HANDOFF.md`), not chat.

### Consequences

- Stars still need a human Show HN paste; agents keep the paste current.
- Feature flags that clone pytest-importcost (`--forbid` spam) are not the
  star path.

## D-20260913-010000-si002

### 70–90 on existing repos; README rigor is in scope; new AI repo later
- Status: accepted
- Date: 2026-09-13
- Deciders: user

### Decision

- Unclear or unrigorous README **should** be fixed.
- Do not spend effort on 90%→100% (extra flags, last edge cases).
- 70%→90% (real apply, honest first screen) **is** worth doing.
- Previous sequence still holds. Do **not** start a new repo this phase.
- After several existing-repo rounds, investigate an AI topic (skills /
  harness / context) and then build. User ideas come later.

## D-20260913-014500-si003

### Task 1 closed; new repo is runbrief
- Status: accepted
- Date: 2026-09-13
- Deciders: user (做完 task1 就可以搞新的；这一轮更新 HANDOFF 并开始做)

### Decision

slowimports is task 1 and is done at ~90%. Next product is `runbrief`
(command log on disk, short tail for agent context). Not a harness clone.

