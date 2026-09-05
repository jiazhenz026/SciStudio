---
title: "ADR-054 Spec 3 Dispatch Prompt: S3-A3 Plumbing Commits To A Dedicated Ref"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S3-A3 — Plumbing Commits To A Dedicated Ref

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
- Agent branch: feat/2240-explore-commits
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s3-a3-commits
- Gate record: .workflow/records/2240-feat-2240-explore-commits.json (yours; create it with `gate_record init`)
- Checklist: docs/planning/adr-054-spec3-explore-session-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2240` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- **docs/specs/adr-054-explore-session.md — this is your specification. Read all of it; T-009 of §4.3, and FR-028 to FR-031 and FR-036 are yours.**
- docs/adr/ADR-054.md for the surrounding design.

## Scope

You own only:

- `src/scistudio/core/versioning/_commit_ops.py`
- `tests/core/versioning/test_explore_ref_commits.py`
- `.workflow/records/2240-feat-2240-explore-commits.json`

You must not touch:

- Every file under `src/scistudio/explore/` — other agents own them. Your work
  is the versioning capability they call, not its caller.
- Every other file under `src/scistudio/core/`, every frontend path,
  `docs/specs/**`, and `docs/architecture/**`.

If you need an out-of-scope path, stop and report back.
Do not edit it.

## Coordination

- You are not alone in this codebase. Several agents are implementing other
  modules of the same spec in separate worktrees right now. The write sets are
  disjoint by design; keep to yours.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`. Every python invocation needs `PYTHONPATH=./src`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- **Do not open a pull request.** Commit your work and push your branch. The
  manager integrates every branch into
  `track/adr-054-spec3-explore-session` and runs the pre-PR gate once for the
  whole candidate. Opening a PR per agent would multiply CI load for no signal.
- MUST NOT merge anything.
- Edit only your checklist rows (your row in §6, and your line in §7.3).

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- The session's decision of when to commit, what the commit message says, and
  the lineage record that points at the commit are other agents' tasks and are
  **not** deferred work — do not write a TODO for them. Expose a function that
  commits a given set of path-to-bytes entries to a named ref and returns the
  sha, plus a packing trigger.

## Work To Do

Implement T-009 of the spec's §4.3 sequence.

`src/scistudio/core/versioning/_commit_ops.py` is a **protected core path**.
The owner has pre-approved `admin-approved:core-change` for this work; the
manager applies the label to the final PR. Your change must be strictly
additive: nothing that exists today may change behaviour.

1. A commit path built from git plumbing — `hash-object`, `update-index`
   against a temporary index file, `write-tree`, `commit-tree`, `update-ref` —
   so that a commit lands on a named ref **without touching the working tree or
   the branch's index** (FR-028, FR-029). Read §4.1's "Commits without touching
   the working tree" paragraph; it names the exact plumbing sequence.
2. The ref namespace is dedicated to explore sessions and is not the branch
   (FR-030). The branch log must stay empty of these commits until someone
   commits explicitly.
3. Force packing after a bounded number of commits (FR-031, FR-036). The
   project ships its own git; the default threshold is a week of heavy use
   away, which is why this is explicit.
4. Reuse the repository's existing `GitEngine` invocation pattern rather than
   shelling out a new way. Read the module you are editing first.
5. Apply the repository's stability markers to every public symbol you add.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/core/versioning/ -q`
- The tests that matter here are the ones about what did *not* happen: after N
  commits to the ref, `git status` in the repository is clean, the branch's
  index is unchanged, the working tree is untouched, and `git log <branch>`
  shows none of them.
- One commit per call, each carrying the exact content given.
- The packing trigger fires at the bound and not before.
- Run the existing versioning tests too and confirm none regressed — this is a
  protected path and an additive change must prove it is additive.
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode local --base origin/track/adr-054-spec3-explore-session --head HEAD`
- Your branch is stacked on `track/adr-054-spec3-explore-session`, not on
  `main`. Record it with `--base-ref origin/track/adr-054-spec3-explore-session`
  at `gate_record init`, and pass
  `--base origin/track/adr-054-spec3-explore-session` to every `check`.
  Without it the gate measures your branch against `origin/main`, reads spec 2's
  commits as yours, and reports false out-of-scope findings.
- Docs: `--docs-na "spec:the governing spec docs/specs/adr-054-explore-session.md landed in PR 2228 and this change implements one of its tasks without adding a separately documented surface"`, unless your task section above says otherwise.
- `git add -A` before every commit.
- Commit trailers are required on every commit:
  `Gate-Record:`, `Task-Kind: feature`, `Issue: #2240`, `Assisted-by: Claude:claude-opus-5`.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results, including the exact pytest summary line.
- The commit sha of your branch head.
- Checklist rows updated.
- Any blocker, scope issue, or spec ambiguity.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The task conflicts with AGENTS.md, ADR-054, the spec, or the gate record.
- Local checks fail for unclear reasons.
- Another agent's work blocks yours.
- You cannot add/update required tests.
- The spec is ambiguous in a way that changes a contract another agent builds
  against. Do not guess; report the ambiguity and your proposed reading.
```
