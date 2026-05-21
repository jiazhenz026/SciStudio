---
title: "Issue 1384 E2E Harness Dispatch Prompt"
status: Draft
owners:
  - "@jiazhenz026"
related_issues:
  - 1384
language_source: en
---

# Issue 1384 E2E Harness Dispatch Prompt

Use `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

## Task Identity

- Repository: SciStudio
- Owner request: Add automated non-blocking GUI E2E discovery tests.
- Task kind: `feature`
- Persona: `implementer`
- Issue: `#1384`
- Umbrella PR: pending `[DO NOT MERGE]`
- Protected branch: `main`
- Integration base branch: `umbrella/adr-039-addendum-1-impl`
- Umbrella branch: `track/issue-1384-e2e-discovery`
- Agent branch: `feat/issue-1384/e2e-harness`
- Agent worktree: `../SciStudio-e2e-harness-1384`
- Gate record: `.workflow/records/1384-e2e-discovery-manager.json`
- Checklist: `docs/planning/issue-1384-e2e-discovery-checklist.md`

## Required Rules

Read and follow:

- GitHub issue `#1384`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/implementer.md

## Scope

You own only:

- `frontend/playwright.config.ts`
- `frontend/e2e/support/**`
- `frontend/e2e/fixtures/**`
- `frontend/e2e/README.md`
- `frontend/package.json`
- `.github/workflows/e2e-discovery.yml`
- Your rows in `docs/planning/issue-1384-e2e-discovery-checklist.md`

You must not touch:

- `frontend/e2e/specs/gui/**`
- `frontend/e2e/specs/git/**`
- `frontend/e2e/specs/workflow-refresh/**`
- Existing unit/integration test locations.

## Coordination

- You are not alone in this codebase.
- MUST work only on your assigned branch/worktree.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work.
- Existing tests must not be moved.

## TODO And Deferral Rule

Deferred work must be tracked in the repo and cite an issue.

Known deferred items:

- Blocking required E2E CI is deferred until discovery tests stabilize.

## Work To Do

1. Add Playwright configuration under `frontend/`.
2. Add support utilities that start backend/frontend, create isolated temp
   project dirs, collect console/network/backend logs, and preserve trace and
   screenshots on failure.
3. Add a synthetic pseudo fluorescence image fixture generator and minimal
   load image -> threshold -> save workflow fixture. If a real owner image is
   unavailable, generate a small deterministic image.
4. Add npm scripts:
   - `test:e2e:smoke`
   - `test:e2e`
5. Add automatic non-blocking CI on relevant `pull_request` and `push` events.
   Do not require nightly/manual operation for the initial workflow.
6. Document how expected product failures differ from test bugs.

## Required Tests And Checks

- `cd frontend && npm test`
- `cd frontend && npm run test:e2e:smoke`
- `ruff check .`
- `ruff format --check .`

E2E may fail because product behavior is broken. The harness itself must still
launch, report, and upload artifacts correctly.

## Output Required

- Changed file paths.
- Tests/checks run and results.
- Checklist rows updated.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- You cannot start the backend/frontend without changing product code.
- Playwright dependencies require lockfile updates outside your write set.
