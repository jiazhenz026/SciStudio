---
title: "ADR-054 Spec 3 Dispatch Prompt: S3-C1 Explore Lineage"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S3-C1 — Explore Lineage

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
- Agent branch: feat/2240-explore-lineage
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s3-c1-lineage
- Gate record: .workflow/records/2240-feat-2240-explore-lineage.json
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
- **docs/specs/adr-054-explore-session.md — T-013 of §4.3, and FR-052 to FR-055 and FR-051 are yours. Read all of it.**
- **docs/specs/adr-054-notebook-dependency-analysis.md — the analysis you
  consume. Already implemented and merged into your branch's history.**
- docs/adr/ADR-054.md for the surrounding design.

## Scope

You own only:

- `src/scistudio/core/lineage/record.py`
- `src/scistudio/core/lineage/store.py`
- `src/scistudio/core/lineage/retention.py`
- `src/scistudio/explore/lineage.py`
- `tests/explore/test_explore_lineage.py`
- `tests/core/lineage/` — additions only, for the new table
- `.workflow/records/2240-feat-2240-explore-lineage.json`

You must not touch:

- `src/scistudio/core/lineage/environment.py` — agent S3-B1 owns it.
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

- The session that writes your records and the packaged block whose run carries
  a notebook commit are other agents' tasks and are **not** deferred work.

## Work To Do

Implement T-013 of the spec's §4.3 sequence.

`src/scistudio/core/lineage/**` is a **protected core path**. The owner
pre-approved `admin-approved:core-change`; record
`--admin-label admin-approved:core-change` in your gate ledger. The manager
applies the label to the final PR. That label authorizes the protected path
only — it is not a gate bypass. Your change must be strictly additive: no
existing record, query, or migration may change behaviour.

1. The `explore_sessions` table, which **parallels `runs`** so that everything
   downstream — block executions, data objects, io edges — is the same code with
   a different foreign key (§4.1, "Lineage adds a table and reuses three").
   Resist the temptation to generalise the existing tables; add the anchor.
2. Cell-run records and block-call records (FR-052, FR-053, FR-051).
3. Retention hooks for the new records (FR-055).
4. A packaged block's run is an ordinary run whose block version is a commit
   sha, which is how the step points back at the session (FR-054).
5. If the lineage store has a schema version or a migration mechanism, use it.
   Read the store before adding a table.
6. Apply the repository's stability markers to every public symbol you add.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/explore/test_explore_lineage.py tests/core/lineage -q`
- The test that matters: an object produced in a session and consumed by a
  workflow run **resolves across the boundary** in both directions.
- A packaged block's run record carries the notebook commit.
- Retention removes the new records on the same terms as the ones it already
  removes, and does not orphan anything.
- Run the pre-existing lineage suite and prove nothing regressed. This is a
  protected path; an additive change has to demonstrate it is additive.
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
