# AI Project Entry Point

This project uses **Portable Project Memory v1**. The source of truth is the
project itself, not any AI conversation.

The model-neutral helper is `.ai/project_memory.py`. Agents with Python 3.10+
can use it for `fingerprint`, `check`, `hash-file`, and `export` without a
Codex Skill.

Resolve all relative paths in this protocol from the directory containing this
file, not from an arbitrary deeper working directory.

## Reading order

Before substantive work:

1. Read `PROJECT_CONTEXT.md` for durable goals, scope, structure, and commands.
2. Read `HANDOFF.md` for the last-known working state.
3. Read only relevant entries from `DECISIONS.md`.
4. Read `ARTIFACTS.md` when the task depends on binary, ignored, or external files.
5. Inspect the actual files, Git state, data, and available verification output.

If written memory conflicts with actual artifacts, do not silently choose one.
Verify the conflict, report it, and update stale memory only after evidence is
available.

## Source priority

The current user's explicit request has the highest instruction authority. For
factual claims, use this evidence order:

1. Actual artifacts and reproducible verification results.
2. Accepted entries in `DECISIONS.md`.
3. Stable intent in `PROJECT_CONTEXT.md`.
4. The snapshot in `HANDOFF.md`.
5. Earlier chat claims that were never verified.

## Capability declaration

Before claiming verification, identify which tier applies:

- **Full agent**: filesystem plus command/test execution;
- **File-only agent**: supplied files but no execution;
- **Chat-only model**: only pasted or uploaded content.

A file-only or chat-only model must mark execution-dependent checks `NOT_RUN`.
It must not pretend that local paths are visible.

## Working rules

- Preserve unrelated user changes.
- Separate confirmed facts from assumptions and unknowns.
- Use project-relative paths whenever possible.
- Do not store credentials, access tokens, personal secrets, or private
  chain-of-thought in project-memory files.
- Do not claim that a command, test, render, simulation, or review passed unless
  it was actually run or the evidence was supplied.

## When to update the handoff

Update `HANDOFF.md` only after a material event:

- a project artifact changed;
- a durable decision was made;
- verification changed what is known;
- a blocker or risk was discovered or resolved;
- work is pausing, completing, or moving to another agent.

Do not edit it for greetings, explanation-only turns, or unchanged status.
Keep it a concise current snapshot rather than an append-only diary. Re-read
`handoff_revision` immediately before saving and increment it by one; reconcile
if another writer changed it.

Put durable choices and their rationale in `DECISIONS.md`. Put stable project
background in `PROJECT_CONTEXT.md`.

## Agents without filesystem access

Ask the user to provide a generated `AI_CONTEXT_BUNDLE_*.md` plus the task
artifacts you need. Do not pretend that local paths or unuploaded files are
visible.
