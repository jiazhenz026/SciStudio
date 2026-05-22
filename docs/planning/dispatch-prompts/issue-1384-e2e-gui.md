---
title: "Issue 1384 E2E GUI Dispatch Prompt"
status: Draft
owners:
  - "@jiazhenz026"
related_issues:
  - 1384
language_source: en
---

# Issue 1384 E2E GUI Dispatch Prompt

Use `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

## Task Identity

- Repository: SciStudio
- Owner request: Add GUI-001..015 Playwright discovery specs.
- Task kind: `feature`
- Persona: `implementer`
- Issue: `#1384`
- Umbrella PR: pending `[DO NOT MERGE]`
- Integration base branch: `umbrella/adr-039-addendum-1-impl`
- Umbrella branch: `track/issue-1384-e2e-discovery`
- Agent branch: `feat/issue-1384/e2e-gui`
- Agent worktree: `../SciStudio-e2e-gui-1384`
- Gate record: `.workflow/records/1384-e2e-discovery-manager.json`
- Checklist: `docs/planning/issue-1384-e2e-discovery-checklist.md`

## Required Rules

Read and follow:

- GitHub issue `#1384`
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/implementer.md

## Scope

You own only:

- `frontend/e2e/specs/gui/**`
- Your rows in `docs/planning/issue-1384-e2e-discovery-checklist.md`

You must not touch:

- Harness files outside read-only use.
- Git-specific and workflow-refresh specs.
- Product source code.

## Work To Do

Implement GUI-001..015 as Playwright specs:

- GUI-001 Open/create empty project.
- GUI-002 Load minimal workflow.
- GUI-003 Run minimal load image -> threshold -> save workflow.
- GUI-004 View lineage after run.
- GUI-005 View artifact/data preview.
- GUI-006 Edit block config and save.
- GUI-007 External workflow YAML reload.
- GUI-008 Invalid config error display.
- GUI-009 Failed workflow display.
- GUI-010 Failed rerun behavior.
- GUI-011 Cancel running workflow.
- GUI-012 Bottom-tab persistence.
- GUI-013 WebSocket disconnect/reconnect.
- GUI-014 Project tree file operation refresh.
- GUI-015 Modal/dialog behavior.

Any test that updates workflow content must assert canvas refresh against API
or disk state, not only button success.

## Required Tests And Checks

- `cd frontend && npm run test:e2e -- --grep @gui`

Failures are acceptable when they expose product bugs. Test bugs are not
acceptable. Avoid fixed sleeps; wait for UI/API/WebSocket conditions.

## Output Required

- Changed file paths.
- Test commands and results.
- Checklist rows updated.
- Known product failures with enough artifact context to file or link issues.
