---
title: "ADR-054 Spec 3 Dispatch Prompt: S3-A4 The on_new_input Setting And The Remap Policy"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S3-A4 — The on_new_input Setting And The Remap Policy

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
- Agent branch: feat/2240-on-new-input
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s3-a4-policy
- Gate record: .workflow/records/2240-feat-2240-on-new-input.json (yours; create it with `gate_record init`)
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
- **docs/specs/adr-054-explore-session.md — this is your specification. Read all of it; the first half of T-015 of §4.3, and FR-044, FR-045, FR-047, FR-048 are yours.**
- docs/adr/ADR-054.md for the surrounding design.

## Scope

You own only:

- `src/scistudio/blocks/base/interactive.py`
- `src/scistudio/engine/scheduler/_dispatch.py`
- `tests/blocks/base/test_interaction_policy.py`
- `.workflow/records/2240-feat-2240-on-new-input.json`

You must not touch:

- Every file under `src/scistudio/explore/` — other agents own them.
- `src/scistudio/blocks/code/backends/notebook.py` — agent S3-C2 owns it.
- Every frontend path, `docs/specs/**`, and `docs/architecture/**`.

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

- The packaged notebook block's ask pause — the prompt that names the notebook
  and the run's inputs, and the decision that carries a notebook commit
  (FR-046) — is agent S3-C2's task and is **not** deferred work. Do not write a
  TODO for it. Your job is the setting and the policy that decides whether the
  interaction-memory remap check is consulted at all; leave the dispatch seam
  where a packaged block plugs its prompt in.

## Work To Do

Implement the first half of T-015 of the spec's §4.3 sequence.

Both files you own are **protected core paths**. The owner has pre-approved
`admin-approved:core-change`; the manager applies the label to the final PR.
Your change must be strictly additive, and the default value must preserve
today's behaviour exactly.

1. `on_new_input` on the interactive block base, with the values `replay` and
   `ask` (FR-044). Read FR-044 and FR-045 for the defaults each block kind
   takes: an authored interactive block keeps asking by default, a packaged
   notebook block replays by default.
2. The engine's dispatch consults `on_new_input` **before** the interaction
   memory's remap check (FR-045). Today the remap check decides on its own
   whether a remembered decision still applies to a changed input signature;
   the setting becomes the policy that decides whether that check is consulted.
   `replay` means the block never pauses on a changed signature.
3. FR-047 and FR-048 for what a decision carries and how it is remembered.
4. Read `src/scistudio/engine/scheduler/_dispatch.py` and the interaction
   memory it uses before changing either. The additive shape §4.5 promises is
   "a setting with a default that preserves current behaviour" — prove that
   with a test over an existing authored interactive block.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/blocks/base/test_interaction_policy.py -q`
- `PYTHONPATH=./src python -m pytest tests/engine -q` — the whole engine suite,
  because you changed dispatch. Report the summary line.
- `PYTHONPATH=./src python -m pytest tests/blocks -q`
- The defaults test is the important one: an existing authored interactive
  block behaves exactly as it did before your change, with no setting written
  anywhere.
- `replay` never pauses across a changed input signature; `ask` pauses on a
  changed signature and does not pause on an unchanged one.
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
