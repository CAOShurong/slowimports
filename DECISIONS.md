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
