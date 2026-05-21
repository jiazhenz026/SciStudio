---
title: "Issue 1384 E2E Discovery Agent Dispatch Checklist"
status: Draft
owners:
  - "@jiazhenz026"
related_issues:
  - 1384
related_prs:
  - 1364
language_source: en
---

# Issue 1384 E2E Discovery Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Add automated, non-blocking GUI E2E discovery tests for
  GUI-001..015, GIT-001..005, and workflow-refresh behavior.
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#1384`
- Gate record: `.workflow/records/1384-e2e-discovery-manager.json`
- Branch/worktree plan:
  - Manager branch: `track/issue-1384-e2e-discovery`
  - Manager worktree: `../SciStudio-e2e-manager-1384`
  - Agent branch pattern: `feat/issue-1384/<agent-scope>`
  - Agent worktree pattern: `../SciStudio-e2e-<agent-scope>-1384`
- Protected branch: `main`
- Integration base branch: `umbrella/adr-039-addendum-1-impl`
- Umbrella branch: `track/issue-1384-e2e-discovery`
- Umbrella PR: `#1387`
- Umbrella PR title: `[DO NOT MERGE] issue #1384 E2E discovery suite`
- Final PR target: `umbrella/adr-039-addendum-1-impl`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`

## 2. Scope

- In scope:
  - `frontend/playwright.config.ts`
  - `frontend/e2e/**`
  - `frontend/package.json`
  - `.github/workflows/e2e-discovery.yml`
  - `docs/planning/issue-1384-e2e-discovery-checklist.md`
  - `docs/planning/dispatch-prompts/issue-1384-*.md`
  - `.workflow/records/1384-e2e-discovery-manager.json`
- Out of scope:
  - Moving or renaming existing tests.
  - 100GB large-file/stress implementation.
  - Contract-test matrix implementation.
  - Blocking E2E required-check rollout.
  - Reverting or changing PR #1364 Git behavior.
- Protected paths:
  - `.github/workflows/e2e-discovery.yml` is intentionally in scope.
- Deferred work:
  - N/A for this manager plan. Any implementation deferral must cite an issue.

## 3. Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Every completed row MUST include an artifact:
  PR link, commit, test command, report path, or gate-record entry.
- Chat messages are not checklist evidence.
- Agents edit only their own rows.
- Scope changes require gate-record amendment before work continues.

## 4. Manager Preflight

- [x] Dedicated manager branch and worktree created.
  Evidence: `track/issue-1384-e2e-discovery` at
  `../SciStudio-e2e-manager-1384`.
- [x] Existing issue linked, or new issue created only if none exists.
  Evidence: issue `#1384`.
- [x] Gate record started.
  Evidence: `.workflow/records/1384-e2e-discovery-manager.json`.
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch pushed.
  Evidence: `origin/track/issue-1384-e2e-discovery`.
- [x] Umbrella PR opened.
  Evidence: `#1387`.
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found.
  Evidence: manager setup used only repository Python modules via
  `PYTHONPATH=src`.
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template and linked
      below.
- [ ] Sentrux baseline recorded, or N/A reason recorded.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record pre-commit --staged` | N/A | `[ ]` | pending |
| Commit message | `python -m scistudio.qa.governance.gate_record commit-msg <commit-msg-file>` | N/A | `[ ]` | pending |
| Pre-push | `python -m scistudio.qa.governance.gate_record pre-push` | N/A | `[ ]` | pending |

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| E2E-Harness | implementer | N/A | `docs/planning/dispatch-prompts/issue-1384-e2e-harness.md` | Playwright harness, service startup, fixtures, non-blocking CI | `feat/issue-1384/e2e-harness` | `../SciStudio-e2e-harness-1384` | `frontend/playwright.config.ts`, `frontend/e2e/support/**`, `frontend/e2e/fixtures/**`, `frontend/package.json`, `.github/workflows/e2e-discovery.yml` | specs under `frontend/e2e/specs/**` except scaffold placeholders | `#1384` / umbrella `#1387` | `[x]` local checks pass; committed on branch |
| E2E-GUI | implementer | N/A | `docs/planning/dispatch-prompts/issue-1384-e2e-gui.md` | GUI-001..015 specs | `feat/issue-1384/e2e-gui` | `../SciStudio-e2e-gui-1384` | `frontend/e2e/specs/gui/**` | harness, Git specs, workflow-refresh specs | `#1384` / umbrella `#1387` | `[~]` committed on branch; pending integration |
| E2E-Git-WFR | implementer | N/A | `docs/planning/dispatch-prompts/issue-1384-e2e-git-wfr.md` | GIT-001..005 + WFR-001..006 specs against PR #1364 behavior | `feat/issue-1384/e2e-git-wfr` | `../SciStudio-e2e-git-wfr-1384` | `frontend/e2e/specs/git/**`, `frontend/e2e/specs/workflow-refresh/**` | harness, GUI specs | `#1384` / umbrella `#1387` | `[~]` committed on branch; pending integration |
| E2E-Audit | audit_reviewer | with-context | `docs/planning/dispatch-prompts/issue-1384-e2e-audit.md` | Read-only audit of harness/spec correctness and no over-mocking | `audit/issue-1384/e2e-discovery` | `../SciStudio-e2e-audit-1384` | `docs/audit/2026-05-21-issue-1384-e2e-discovery-audit.md` | implementation files except read-only inspection | `#1384` / umbrella `#1387` | `[ ]` |

## 7. Track: Harness And CI

### 7.1 Track Scope

- Owner: E2E-Harness
- In scope:
  - Playwright config.
  - Backend/frontend startup helpers.
  - Synthetic fluorescence image fixture generator.
  - Minimal load image -> threshold -> save workflow fixture.
  - Failure artifacts: screenshot, trace, browser console, network log,
    backend log, project snapshot path.
  - Automatic non-blocking CI on relevant `pull_request` and `push` events.
- Out of scope:
  - Product fixes for failing scenarios.
- Required docs:
  - `frontend/e2e/README.md`
- Required tests:
  - `npm run test:e2e:smoke` may fail on product behavior, but the harness
    must launch and produce artifacts.

### 7.2 Dispatch

- [x] Prompt file created.
  Evidence: `docs/planning/dispatch-prompts/issue-1384-e2e-harness.md`.
- [x] Correct prompt template selected.
  Evidence: dispatch prompt names
  `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.
- [x] Agent branch/worktree assigned.
  Evidence: branch `feat/issue-1384/e2e-harness`, worktree
  `../SciStudio-e2e-harness-1384`.
- [x] Write set and out-of-scope paths included in prompt.
  Evidence: `docs/planning/dispatch-prompts/issue-1384-e2e-harness.md`.
- [x] TODO rule included in prompt.
  Evidence: `docs/planning/dispatch-prompts/issue-1384-e2e-harness.md`.
- [x] Required checks included in prompt.
  Evidence: `docs/planning/dispatch-prompts/issue-1384-e2e-harness.md`.

### 7.3 Implementation

- [x] Playwright harness implemented.
  Evidence: `frontend/playwright.config.ts`,
  `frontend/e2e/support/**`; `cd frontend && npm run test:e2e:smoke`
  passed locally.
- [x] Fixture image/workflow implemented.
  Evidence: `frontend/e2e/fixtures/syntheticFluorescence.ts`,
  `frontend/e2e/fixtures/minimalWorkflow.ts`;
  `cd frontend && npm run test:e2e:smoke` passed locally.
- [x] CI workflow implemented non-blocking.
  Evidence: `.github/workflows/e2e-discovery.yml` captures E2E exit code,
  uploads artifacts, and exits successfully for discovery failures.
- [x] README written.
  Evidence: `frontend/e2e/README.md`.

### 7.4 Audit

- [ ] Manager review pending.

### 7.5 Integration

- [ ] Pending.

## 8. Track: GUI Behavior Specs

### 8.1 Track Scope

- Owner: E2E-GUI
- In scope:
  - GUI-001..015.
  - Tests may fail for product bugs but must be deterministic and have clear
    assertions.
  - Any action that updates workflow content must assert canvas refresh.
- Out of scope:
  - Git-specific PR #1364 workflows.
- Required docs:
  - E2E scenario comments or README matrix updates.
- Required tests:
  - `npm run test:e2e -- --grep @gui`

### 8.2 Dispatch

- [x] Prompt file created.
- [x] Agent branch/worktree assigned.

### 8.3 Implementation

- [ ] GUI-001..005 PR smoke specs -> pending.
- [ ] GUI-006..015 discovery specs -> pending.

### 8.4 Audit

- [ ] Manager review pending.

### 8.5 Integration

- [ ] Pending.

## 9. Track: Git And Workflow Refresh Specs

### 9.1 Track Scope

- Owner: E2E-Git-WFR
- In scope:
  - GIT-001..005.
  - WFR-001..006.
  - PR #1364 post-refactor behavior: no stash UI/API expectations;
    dirty restore/switch auto-commit; inline restore/diff history actions.
- Out of scope:
  - Product fixes to PR #1364.
- Required docs:
  - E2E scenario comments or README matrix updates.
- Required tests:
  - `npm run test:e2e -- --grep @git`
  - `npm run test:e2e -- --grep @workflow-refresh`

### 9.2 Dispatch

- [x] Prompt file created.
- [x] Agent branch/worktree assigned.

### 9.3 Implementation

- [ ] GIT-001..005 specs -> pending.
- [ ] WFR-001..006 specs -> pending.

### 9.4 Audit

- [ ] Manager review pending.

### 9.5 Integration

- [ ] Pending.

## 10. Track: Audit

### 10.1 Track Scope

- Owner: E2E-Audit
- In scope:
  - Read-only review after implementation integration.
  - Verify tests are true GUI E2E, not component tests in disguise.
  - Verify expected failures are product signals, not broken tests.
  - Verify PR #1364 behavior is reflected.
- Out of scope:
  - Implementation fixes unless separately assigned.
- Required docs:
  - `docs/audit/2026-05-21-issue-1384-e2e-discovery-audit.md`
- Required tests:
  - N/A, audit reviewer records commands inspected/run.

### 10.2 Dispatch

- [ ] Prompt file created.
- [ ] Audit mode recorded: with-context.

### 10.3 Audit

- [ ] Audit report pending.

## 11. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Ruff | `ruff check .` | `[x]` | passed locally in `../SciStudio-e2e-harness-1384` |
| Format | `ruff format --check .` | `[x]` | passed locally in `../SciStudio-e2e-harness-1384` |
| Frontend unit | `cd frontend && npm test` | `[x]` | 43 files / 442 tests passed, 13 skipped |
| E2E smoke | `cd frontend && npm run test:e2e:smoke` | `[x]` | 3 Chromium tests passed; artifacts in `frontend/.e2e-artifacts` |
| E2E discovery | `cd frontend && npm run test:e2e` | `[x]` | 3 Chromium tests passed; non-blocking CI path added |
| Full audit | `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output .audit/full-audit.json` | `[ ]` | pending |
| Sentrux | `sentrux check .` or MCP equivalent | `[ ]` | pending |

## 12. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-05-21 | manager | Owner clarified that E2E failures are acceptable initially, but tests must be correct; CI must be automatic and non-blocking. | Added CI and failure-classification requirements. | N/A |
| 2026-05-21 | manager | Owner added workflow-refresh requirement for all workflow-updating buttons, especially Lineage Restore; tests must follow PR #1364 Git refactor. | Added WFR track and PR #1364 acceptance criteria. | N/A |

## 13. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes issue `#1384`.
- [ ] CI passed except explicitly non-blocking E2E product failures.
- [ ] Checklist final state matches PR and gate record.
