---
title: "A1 Dispatch Prompt — Panel Escape Hatch"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 51
language_source: en
---

# A1 Dispatch Prompt — Panel Escape Hatch (#2195)

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: A user was locked inside an AI-written interactive block's panel that drew neither a continue nor a cancel control; the host must always offer a way out.
- Task kind: bugfix
- Persona: implementer
- Issue: #2195
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2195
- Umbrella PR: #2198 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/interactive-panel-quality
- Agent branch: fix/2195-panel-escape-hatch
- Agent worktree: .worktrees/fix-2195-panel-escape-hatch
- Gate record: .workflow/records/2195-fix-2195-panel-escape-hatch.json (create it with `gate_record init`)
- Checklist: docs/planning/interactive-panel-quality-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2195` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/bug-fix.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-051-interactive-blocks.md — User Story 3 and FR-012 describe
  the cancellation contract this restores.

## Scope

You own only:

- frontend/src/App.parts/InteractiveModals.tsx
- frontend/src/App.parts/InteractiveModals.parts/**
- Tests for the above.

You must not touch:

- Any backend path (`src/scistudio/**`).
- `src/scistudio/_skills/**`, `src/scistudio/_agent_reference/**`.
- `frontend/src/App.parts/InteractiveModals.parts/panelModuleLoader.ts` beyond
  what the work below strictly requires — agent A3 owns a comment fix in that
  file. If you need a behavioral change there, stop and report back.
- `PANEL_HOST_API_VERSION`, the `PanelHostApi` interface, or the `PanelModule`
  interface. This fix must not change the panel contract or its version, and
  existing panel modules must keep working with no edits.

If you need an out-of-scope path, stop and report back.
Do not edit it.

## Coordination

- You are not alone in this codebase.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- The manager explicitly assigns you a final PR to `main` (not to the umbrella
  branch). Your PR body must close #2195 with a closing keyword.
- MUST NOT merge any PR unless the owner explicitly authorizes it.
- Edit only your checklist rows (§7.3 of the checklist).
- Record every completed row with a PR, commit, test, report, or gate evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- Host-owned Continue / `host.setDecision` plumbing is deliberately out of scope
  and is NOT deferred work you should mark — the owner decided Continue stays
  the panel's responsibility.

## Work To Do

Two independent stuck paths. Fix both.

1. **Host-owned escape hatch.** `DynamicPanel` renders a `fixed inset-0
   z-[9999]` overlay whose whole body is the package module's DOM
   (`frontend/src/App.parts/InteractiveModals.parts/DynamicPanel.tsx`). There is
   no ESC handler, no backdrop close, no close control — and the overlay covers
   the Toolbar Stop button (`frontend/src/App.tsx:490`), so a panel that never
   calls `host.cancel()` locks the whole app.

   Add a thin host-drawn title bar above the panel's mount container showing the
   block's name and a close (X) control at the right. X and the ESC key both
   drive the same `onCancel` the core panels already receive, so the run-scoped
   `cancel_block` frame is unchanged.

   The panel's content area must be untouched: a panel that draws its own Cancel
   (the tutorial's
   `src/scistudio/tutorials/core/what-is-a-type/assets/panels/review_labels/panel.mjs`)
   must not break or look wrong — one control sits in the title bar, one in the
   content area. The owner chose the title-bar placement specifically so the two
   do not collide.

2. **No silent `null`.** `frontend/src/App.parts/InteractiveModals.tsx:148-154`
   returns `null` when a manifest has a `panel_id` but is neither a registered
   core panel nor carries a `module_url`. That is reachable: `PanelManifest`
   defaults `module_url` to `""` and the registry only requires a non-empty
   `panel_id`, so a block that forgets `module_url` registers, runs, and pauses
   with no window at all — just a `console.warn`. Replace that branch with the
   same visible error surface + Cancel that `DynamicPanel` already renders for
   load failures.

3. Add tests. Cover: ESC cancels a mounted exit-less panel; the title-bar X
   cancels it; the no-`module_url` manifest renders the error surface with a
   working Cancel; core panels and a panel that draws its own controls still
   behave as before.

4. Decide the docs impact. This changes a user-visible affordance of the
   interactive modal. If a document describes that modal, update it; otherwise
   record an explicit docs N/A rationale in your ledger.

## Required Tests And Checks

- Frontend tests for both paths, colocated with the components you change
  (`DynamicPanel.test.tsx` and the `InteractiveModals` tests are the existing
  homes).
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr` to run
  tier-selected checks and reconcile the gate ledger before PR creation
  (receipt behavior is folded into the ledger per ADR-042 Addendum 6; there is
  no separate `gate_receipt` command)
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2195"` before PR creation
- `python scripts/scistudio_pr_create.py` for the final PR (do not use
  `gh pr create` directly)
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr <url> --pr-body-file <path>` after PR is created

This task does not change wrapper, hook, gate-record, CI, or AI-runtime
behavior, so the AI-docs impact check is N/A — record that rationale.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results.
- Checklist rows updated.
- PR number or commit.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- You conclude the fix cannot be done without changing the panel host API
  version or the `PanelModule` contract.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- CI or local checks fail for unclear reasons.
- Another agent's work blocks yours.
- You cannot add/update required tests.
```
