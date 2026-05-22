---
title: "Issue 1384 E2E Git And Workflow Refresh Dispatch Prompt"
status: Draft
owners:
  - "@jiazhenz026"
related_issues:
  - 1384
related_prs:
  - 1364
language_source: en
---

# Issue 1384 E2E Git And Workflow Refresh Dispatch Prompt

Use `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

## Task Identity

- Repository: SciStudio
- Owner request: Add Git and workflow-refresh GUI E2E specs against PR #1364
  post-refactor behavior.
- Task kind: `feature`
- Persona: `implementer`
- Issue: `#1384`
- Umbrella PR: pending `[DO NOT MERGE]`
- Integration base branch: `umbrella/adr-039-addendum-1-impl`
- Umbrella branch: `track/issue-1384-e2e-discovery`
- Agent branch: `feat/issue-1384/e2e-git-wfr`
- Agent worktree: `../SciStudio-e2e-git-wfr-1384`
- Gate record: `.workflow/records/1384-e2e-discovery-manager.json`
- Checklist: `docs/planning/issue-1384-e2e-discovery-checklist.md`

## Required Rules

Read and follow:

- GitHub issue `#1384`
- PR `#1364`
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/implementer.md

## Scope

You own only:

- `frontend/e2e/specs/git/**`
- `frontend/e2e/specs/workflow-refresh/**`
- Your rows in `docs/planning/issue-1384-e2e-discovery-checklist.md`

You must not touch:

- Harness files outside read-only use.
- GUI non-Git specs.
- Product source code.

## PR #1364 Behavior Requirements

- Do not test old stash UI.
- Do not expect `/api/git/stash*`.
- Git tab should not expose a Stashes button.
- Dirty restore and dirty branch switch use auto-commit.
- Restore responses include `auto_commit_sha`.
- Git history restore/diff follows the inline action behavior after the
  ADR-039 Addendum 1 refactor.
- Lineage Restore must show the auto-commit hint when applicable and must
  refresh the canvas to the restored workflow.

## Work To Do

Implement:

- GIT-001 Git status after workflow modification.
- GIT-002 Commit dialog.
- GIT-003 Restore workflow file.
- GIT-004 Branch picker/switch with workflow refresh.
- GIT-005 Conflict view.
- WFR-001 Lineage Restore workflow.
- WFR-002 Git History inline Restore workflow.
- WFR-003 Dirty restore auto-commit.
- WFR-004 Dirty branch switch auto-commit.
- WFR-005 Invalid restore/switch failure preserves old canvas.
- WFR-006 Repeated restore no-op preserves canvas and avoids stale tab state.

Workflow-refresh acceptance for every case:

- Canvas nodes/edges match the current `workflows/<id>.yaml`.
- Current workflow id is correct.
- UI jumps to or remains on the correct tab for the user to see the restored
  workflow.
- No stale Lineage/Git detail misrepresents the current canvas.

## Required Tests And Checks

- `cd frontend && npm run test:e2e -- --grep @git`
- `cd frontend && npm run test:e2e -- --grep @workflow-refresh`

Failures are acceptable when they expose product bugs. Test bugs are not
acceptable.

## Output Required

- Changed file paths.
- Test commands and results.
- Checklist rows updated.
- Product failures with artifact context.
