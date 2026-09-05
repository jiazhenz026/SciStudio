---
title: "ADR-054 Spec 3 Dispatch Prompt: S3-B2 The Session, The Queue, And The Marks"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S3-B2 — The Session, The Queue, And The Marks

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
- Agent branch: feat/2240-session-queue
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s3-b2-session
- Gate record: .workflow/records/2240-feat-2240-session-queue.json
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
- **docs/specs/adr-054-explore-session.md — T-006, T-007, T-008, T-016 of §4.3, and FR-001 to FR-006, FR-016 to FR-026, FR-036 are yours. Read all of it.**
- **docs/specs/adr-054-notebook-dependency-analysis.md — the analysis you
  consume. Already implemented and merged into your branch's history.**
- docs/adr/ADR-054.md for the surrounding design.

## Scope

You own only:

- `src/scistudio/explore/session.py`
- `src/scistudio/explore/queue.py`
- `src/scistudio/api/project_layout.py` — the explore directory joins the layout
- `tests/explore/test_explore_session.py`
- `tests/explore/test_queue_and_marks.py`
- `.workflow/records/2240-feat-2240-session-queue.json`

You must not touch:

- `src/scistudio/explore/kernel.py`, `kernel_bridge.py`, `notebook_api.py`,
  `notebook.py`, `packaging.py`, `block_call.py`, `lineage.py` — other agents
  own them. You compose them; you do not modify them. If one is missing a
  capability you need, report it.
- `src/scistudio/core/versioning/_commit_ops.py` — agent S3-A3 owns it. Call the
  commit function it exposes.
- Every API route file, every frontend path, `docs/specs/**`,
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

- The routes that expose your operations and the events that carry your marks
  to the frontend are agent S3-C3's task and are **not** deferred work. Expose
  the operations of FR-056 and emit the events of FR-057 through whatever
  in-process channel you choose; S3-C3 adapts them to HTTP and the WebSocket
  hub.

## Work To Do

Implement T-006, T-007, T-008, and T-016 of the spec's §4.3 sequence. This is
the centre of the spec — read §4.1's paragraph "Marks are bookkeeping, not
execution" before you write anything.

1. **T-006, the session.** Open over a block's outputs, over a project file, or
   over a paused interactive block's inputs (FR-001 to FR-004). The notebook
   file's location in the project and its generated first cell, which names the
   ports (FR-005). List, close, and commit (FR-006). Refuse to open when the
   outputs are absent. The explore directory joins the project layout.
2. **T-007, the queue.** One queue. Admission of panel-emitted code through the
   statement whitelist — code outside the whitelist is **refused**, not
   sanitised (FR-018). Coalescing of queued duplicates (FR-017). The observation
   call around each run, using the bridge's fingerprint hook, feeding
   `ObservedChange` back into the analysis (FR-025). The shallow freeze bound
   (FR-021): a bridge request that arrives while a long cell runs waits behind
   it, the panel keeps its last window, and the read completes when the cell
   does. That is accepted behaviour, not a bug to engineer around.
3. **T-008, the marks.** Keep which cell last bound each name, updated from each
   run's observed changed set. Before a run, ask the graph for the definer of
   each read and compare — a mismatch marks the run out of order. After a run,
   ask the graph for the downstream set and mark it stale. **Neither step
   enqueues anything.** Run-with-upstream is the one place the service chooses
   cells on the person's behalf, and its skip rule is exact: a cell in the slice
   is skipped only if nothing about it is questionable **and** every name it
   changes is still bound by it. The spec's User Story 2 states the A, B, C case
   this produces; make it a fixture and assert the exact set.
4. **T-016, the kernel list and branch-switch retirement.** Every kernel listed
   with its memory; a branch change retires all of them (FR-016).
5. The session service imports `core` for storage, lineage, and versioning and
   `blocks` for the registry. It must **never** import the API, AI, or engine
   layers, and the engine must never import it (§4.1, "Where the service
   lives").
6. Apply the repository's stability markers to every public symbol you add.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/explore -q`
- The A, B, C fixture from User Story 2, asserting the **exact** set of cells
  each control enqueues, and asserting that no control enqueues a cell the
  person did not name. A test that only checks "something was enqueued" is
  worthless here.
- Every refused statement form of the admission whitelist gets its own test, and
  one accepted assignment.
- Duplicate submissions run once.
- An out-of-order re-run is marked and **nothing is re-executed**.
- A branch change retires every kernel; assert on the process, not on a flag.
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
