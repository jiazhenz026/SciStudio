---
title: "ADR-054 Spec 3 Dispatch Prompt: S3-C3 The Session API, Its Events, And The Layer Rule"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S3-C3 — The Session API, Its Events, And The Layer Rule

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
- Agent branch: feat/2240-explore-api
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s3-c3-api
- Gate record: .workflow/records/2240-feat-2240-explore-api.json
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
- **docs/specs/adr-054-explore-session.md — T-017 of §4.3, and FR-056, FR-057, FR-058, FR-060 are yours. Read all of it.**
- **docs/specs/adr-054-notebook-dependency-analysis.md — the analysis you
  consume. Already implemented and merged into your branch's history.**
- docs/adr/ADR-054.md for the surrounding design.

## Scope

You own only:

- `src/scistudio/api/routes/explore.py`
- `src/scistudio/api/ws.py`
- `tests/api/test_explore_routes.py`
- `tests/architecture/test_layer_deps.py`
- `.workflow/records/2240-feat-2240-explore-api.json`

You must not touch:

- Every file under `src/scistudio/explore/` — other agents own them. The route
  module is a door, not a place to put logic. If an operation you need is not on
  the session service, report it rather than reaching past it.
- `src/scistudio/api/project_layout.py` — agent S3-B2 owns it.
- Every frontend path, `docs/specs/**`, `docs/architecture/**`.

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

- The frontend that consumes these routes and events is the explore-frontend
  spec's and is out of scope for this whole spec.

## Work To Do

Implement T-017 of the spec's §4.3 sequence.

1. **Every operation of FR-056 has a route**, and the route module exposes
   nothing that reaches the kernel directly (§4.1, "The API is the only door").
   Walk FR-056 item by item and check each off.
2. **Every event of FR-057 is emitted** over the WebSocket hub the workflow
   already uses, with new event types, so the frontend keeps one connection. Do
   not open a second socket.
3. FR-058 for the error and refusal shapes the routes return.
4. **FR-060, the layer rule.** Add the explore subsystem's forbidden imports to
   `tests/architecture/test_layer_deps.py`: `scistudio.explore` may import
   `core` and `blocks` and must import neither `scistudio.api`, nor
   `scistudio.ai`, nor `scistudio.engine`; and nothing in `engine` may import
   `explore`. Spec 2 already added the subsystem to the enumeration with its own
   constraint — extend that entry, do not add a second mechanism, and do not
   remove spec 2's rule.
5. Follow the shape of the existing route modules for validation, error
   handling, and dependency injection. Read a neighbouring routes file first.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/api/test_explore_routes.py tests/architecture/test_layer_deps.py -q`
- Route by route: every operation of FR-056 has a test that exercises the real
  route, not the service behind it.
- The events are tested by subscribing to the hub during a scripted session and
  comparing the **sequence**, not just the presence, of events.
- A refusal from the session (a bad emission, a stale slice) surfaces as the
  documented error shape rather than a bare 500. A bare 500 with an orphaned
  side effect is a defect shape this repository has shipped before.
- The layer test must fail if someone adds `import scistudio.api` to an explore
  module; prove that by trying it in a scratch copy.
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
