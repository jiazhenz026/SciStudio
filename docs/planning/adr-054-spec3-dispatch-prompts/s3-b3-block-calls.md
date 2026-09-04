---
title: "ADR-054 Spec 3 Dispatch Prompt: S3-B3 Calling A Block From A Cell"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S3-B3 — Calling A Block From A Cell

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 3, the Explore Session runtime, in full.
- Task kind: feature
- Persona: implementer
- Issue: #2240
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2240
- Umbrella PR: #2241 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-spec3-explore-session
- Agent branch: feat/2240-block-calls
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s3-b3-blockcall
- Gate record: .workflow/records/2240-feat-2240-block-calls.json
- Checklist: docs/planning/adr-054-spec3-explore-session-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2240`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- **docs/specs/adr-054-explore-session.md — T-012 of §4.3, and FR-049, FR-050, FR-051 are yours. Read all of it.**
- **docs/specs/adr-054-notebook-dependency-analysis.md — the analysis you
  consume. Already implemented and merged into your branch's history.**
- docs/adr/ADR-054.md for the surrounding design.

## Scope

You own only:

- `src/scistudio/explore/block_call.py`
- `tests/explore/test_block_call_adapter.py`
- `.workflow/records/2240-feat-2240-block-calls.json`

You must not touch:

- `src/scistudio/explore/kernel_bridge.py` — agent S3-B1 owns it; your adapter
  is what the bridge exposes, in its own module.
- Every other explore module, every frontend path, `docs/specs/**`,
  `docs/architecture/**`.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. Several agents are implementing other
  modules of the same spec in separate worktrees. The write sets are disjoint by
  design; keep to yours.
- MUST work only on your assigned branch and worktree.
- MUST NOT use `pip install -e .`. `PYTHONPATH=./src` on every python call.
- Do not revert or overwrite other agents' work.
- **Do not open a pull request.** Commit, push your branch, and report. The
  manager integrates every branch and runs the pre-PR gate once.
- MUST NOT merge anything.
- Edit only your checklist rows (your row in §6, your line in §7.3).

## TODO And Deferral Rule

Use `TODO(#NNN): <reason>` citing an issue, ADR, spec, or ticket for anything
deferred. No hidden V1, MVP, or later work.

Known deferred items:

- The lineage records for a block call are agent S3-C1's task and are **not**
  deferred work. Return the facts a record needs; do not write the record.

## Work To Do

Implement T-012 of the spec's §4.3 sequence.

1. A block-call adapter that runs a block **in-process** from inside the kernel,
   with typed wrapping of its arguments and its result (FR-049).
2. The interactive-block case: a call to an interactive block blocks until a
   value arrives (FR-050). Read ADR-054 §5.5 for the surrounding design.
3. What the call reports for lineage (FR-051), returned to the caller rather
   than recorded here.
4. The block registry is `scistudio.blocks`; use it rather than importing block
   classes directly.
5. Apply the repository's stability markers to every public symbol you add.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/explore/test_block_call_adapter.py -q`
- A block runs in-process with typed wrapping; assert the wrapped type, not just
  that a value came back.
- An interactive call blocks until a value arrives, and does not busy-wait.
- A call to a block that does not exist fails with a message naming the block.
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode local --base origin/track/adr-054-spec3-explore-session --head HEAD`
- Record `--base-ref origin/track/adr-054-spec3-explore-session` at
  `gate_record init` and pass
  `--base origin/track/adr-054-spec3-explore-session` to every `check`. Without
  it the gate measures your branch against `origin/main`, reads spec 2's
  commits as yours, and reports false out-of-scope findings.
- Docs: `--docs-na "spec:the governing spec docs/specs/adr-054-explore-session.md landed in PR 2228 and this change implements one of its tasks without adding a separately documented surface"` unless your task says otherwise.
- `git add -A` before every commit. Trailers on every commit: `Gate-Record:`,
  `Task-Kind: feature`, `Issue: #2240`, `Assisted-by: Claude:claude-opus-5`.

## Output Required

- Changed file paths.
- Exact pytest summary lines.
- Your branch head sha.
- Checklist rows updated.
- Any blocker, scope issue, or spec ambiguity.

## Stop Conditions

Stop and report back if you need an out-of-scope file, the task conflicts with
AGENTS.md or the spec, checks fail for unclear reasons, another agent's work
blocks yours, you cannot add the required tests, or the spec is ambiguous in a
way that changes a contract another agent builds against.
```
