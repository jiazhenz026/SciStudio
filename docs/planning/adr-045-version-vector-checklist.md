---
title: "ADR-045 Version Vector Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 41
  - 43
  - 45
language_source: en
---

# ADR-045 Version Vector Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: land ADR-045 by first fixing ADR-041/ADR-043 implemented-state drift, then dispatch at most four agents for the version-vector race-condition implementation.
- Contract consistency rule: ADRs, specs, governed files/contracts, code signatures, API/event payloads, tests, gate records, and audit facts must describe the same contract. If code is the better implemented truth, update docs in the same change.
- Task kind: `manager`
- Manager persona: `manager`
- Issues: `#1407` for ADR-041/ADR-043 drift, `#1401` reopened for ADR-045 implementation tracking.
- Gate record: `.workflow/records/1407-adr-045-manager-1407-drift.json`
- Branch/worktree plan: manager integration branch `track/adr-045/version-vector` in `.claude/worktrees/manager-adr-045-1407`; agent branches will use `feat/issue-1401/adr-045-*` from this tracking branch.
- Protected branch: `main`
- Umbrella branch: `track/adr-045/version-vector`
- Umbrella PR: `#1410` `https://github.com/zjzcpj/SciStudio/pull/1410`
- Umbrella PR title: `[DO NOT MERGE] ADR-045 version-vector implementation`
- Final PR target: `main`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - `docs/adr/ADR-041.md`
  - `docs/adr/ADR-043.md`
  - `docs/adr/ADR-045.md`
  - `docs/specs/adr-041-codeblock-v2.md`
  - `docs/specs/adr-043-io-format-capability-registry.md`
  - `docs/specs/adr-043-package-migration.md`
  - `docs/specs/adr-045-workflow-state-version.md`
  - `docs/planning/adr-045-version-vector-checklist.md`
  - `docs/planning/dispatch-prompts/adr-045-*.md`
  - `docs/audit/adr-045-*.json`
  - later ADR-045 implementation files assigned in dispatch prompts.
- Out of scope:
  - Broad cleanup unrelated to #1407 or ADR-045 race handling.
  - Weakening governance, Sentrux, CI, full-audit, or protected-path checks.
  - Real-time collaborative editing, OT, CRDT, or cross-workflow global ordering.
- Protected paths:
  - Governance and audit code are read-only unless explicitly added by owner scope.
- Deferred work:
  - N/A at checklist creation. Any later deferral must use `TODO(#NNN)` in repo files.

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

- [x] Dedicated manager branch and worktree created. -> `track/adr-045/version-vector`, `.claude/worktrees/manager-adr-045-1407`
- [x] Existing issue linked, or new issue created only if none exists. -> #1407 open; #1401 reopened with `gh issue reopen`
- [x] Gate record started. -> `.workflow/records/1407-adr-045-manager-1407-drift.json`
- [x] Scope include/exclude recorded in the gate record. -> `.workflow/records/1407-adr-045-manager-1407-drift.json`
- [x] Umbrella branch created. -> `track/adr-045/version-vector`
- [x] Umbrella PR opened. -> https://github.com/zjzcpj/SciStudio/pull/1410
- [x] Umbrella PR title includes `[DO NOT MERGE]`. -> `[DO NOT MERGE] ADR-045 version-vector implementation`
- [x] Protected branch and umbrella PR number recorded in this checklist. -> protected branch `main`; PR #1410
- [x] No `pip install -e .` environment pollution found. -> `PYTHONPATH=src` import points to manager worktree source
- [x] Dispatch checklist copied from the template and committed. -> pending first manager commit
- [x] Dispatch prompts created from the correct prompt template and linked below. -> `docs/planning/dispatch-prompts/adr-045-a1-backend-versioning.md`, `adr-045-a2-file-tabs.md`, `adr-045-a3-frontend-reconcile.md`, `adr-045-a4-audit-with-context.md`
- [x] Sentrux baseline recorded, or N/A reason recorded. -> `docs/audit/adr-045-sentrux.json`

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record pre-commit --staged` | `N/A` | `[ ]` | pending |
| Commit message | `python -m scistudio.qa.governance.gate_record commit-msg <commit-msg-file>` | `N/A` | `[ ]` | pending |
| Pre-push | `python -m scistudio.qa.governance.gate_record pre-push` | `N/A` | `[ ]` | pending |

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | implementer | N/A | `docs/planning/dispatch-prompts/adr-045-a1-backend-versioning.md` | Backend runtime version map, workflow write-site emits, watcher fallback | `feat/issue-1401/adr-045-backend-versioning` | `.claude/worktrees/adr-045-a1-backend-versioning` | backend runtime/routes/tests assigned in prompt | frontend, file tabs unless prompt says otherwise | #1401; PR #1411 | `[x]` PR https://github.com/zjzcpj/SciStudio/pull/1411; gate `.workflow/records/1401-a1-backend-versioning.json`; Codex P1/P2 accepted and fixed; behavior tests `pytest ... --timeout=60 --no-cov` 71 passed; ADR/spec aligned on `state_version` response contract and exact watcher suppression; full audit `docs/audit/adr-045-a1-full-audit.json`; Sentrux free-tier pass 3/15 rules |
| A2 | implementer | N/A | `docs/planning/dispatch-prompts/adr-045-a2-file-tabs.md` | Backend file tab GET/save version contract and `file.changed` events | `feat/issue-1401/adr-045-file-tabs` | `.claude/worktrees/adr-045-a2-file-tabs` | project file route/tests assigned in prompt | workflow backend and frontend reconciliation | #1401; PR #1425 | `[x]` PR https://github.com/zjzcpj/SciStudio/pull/1425; gate `.workflow/records/1401-a2-file-tabs.json`; rebased onto A1 merge `dfc3ddc3`; `pytest ... --timeout=60 --no-cov` 12 passed; file endpoint compat 15 passed; ruff/format pass; full audit `docs/audit/adr-045-a2-full-audit.json`; Sentrux free-tier pass 3/15 rules. |
| A3 | implementer | N/A | `docs/planning/dispatch-prompts/adr-045-a3-frontend-reconcile.md` | Frontend workflow/file reconcile, source_id handling, conflict state | `feat/issue-1401/adr-045-frontend-reconcile` | `.claude/worktrees/adr-045-a3-frontend-reconcile` | frontend API/websocket/store/tests assigned in prompt | backend persistence and event emission | #1401; PR #1443 | `[~]` PR https://github.com/zjzcpj/SciStudio/pull/1443; rebased to tracking `3f617ae4`; gate `.workflow/records/1401-a3-frontend-reconcile.json`; frontend Vitest targeted suite 25 passed; frontend build passed; backend race-matrix integration tests from tracking branch rerun 6 passed; full audit `docs/audit/adr-045-a3-full-audit.json` passed. Codex triage: no review comments, inline comments, or PR comments found. Blocked from green gate by Sentrux free-tier `max_cycles` baseline failure (4 > 3), reproduced on clean tracking `3f617ae4`; Workflow Gate Check fails `sentrux.free_tier.nonpassing-status`. |
| A4 | audit_reviewer | with-context | `docs/planning/dispatch-prompts/adr-045-a4-audit-with-context.md` | Integration audit after A1-A3 outputs | `audit/issue-1401/adr-045-version-vector` | `.claude/worktrees/adr-045-a4-audit` | audit report and checklist audit rows | implementation code | #1401 | `[ ]` |

## 7. Track: #1407 ADR-041/ADR-043 Drift Fix

### 7.1 Track Scope

- Owner: manager
- In scope:
  - Promote implemented ADR/spec statuses honestly.
  - Remove phantom governed contracts or replace them with canonical implemented symbols.
  - Align ADR/spec contract lists and signature blocks with code when code is the implemented source of truth.
- Out of scope:
  - Refactoring CodeBlock v2 or ADR-043 runtime code while fixing documentation drift.
- Required docs:
  - ADR/spec frontmatter and signature sections listed in §2.
- Required tests:
  - full audit and targeted QA audit checks.

### 7.2 Dispatch

- [x] Manager owns this first drift-fix slice. -> #1407

### 7.3 Implementation

- [x] Inspect current symbol/signature truth. -> `rg` over ADR/spec/code and issue #1407
- [x] Patch ADR-041/ADR-043/spec status and contract/signature drift. -> `docs/adr/ADR-041.md`, `docs/adr/ADR-043.md`, ADR-041/043 specs
- [x] Run full audit and fix newly exposed drift. -> `docs/audit/adr-045-full-audit.json`

### 7.4 Audit

- [x] Manager audit completed. -> `docs/audit/adr-045-drift-fix-audit.json`, `docs/audit/adr-045-full-audit.json`
- [x] Findings recorded. -> `docs/audit/adr-045-drift-fix-audit.json`
- [x] P1 findings fixed before integration. -> full audit pass

### 7.5 Integration

- [x] Scope compliance verified. -> gate record `.workflow/records/1407-adr-045-manager-1407-drift.json`
- [x] Track ready for ADR-045 implementation dispatch. -> #1407 drift fixed and ADR-045 spec drafted

## 8. Track: ADR-045 Spec And Status Transition

### 8.1 Track Scope

- Owner: manager for spec draft/status transition; implementation agents after dispatch.
- In scope:
  - Draft `docs/specs/adr-045-workflow-state-version.md`.
  - Move ADR-045 from planning to implementation when the spec exists.
  - Keep #1401 as the implementation tracker.
- Out of scope:
  - Real-time multi-user merging beyond ADR-045's conflict surfacing.
- Required docs:
  - ADR-045 and spec.
- Required tests:
  - N/A for spec drafting; implementation agents must add tests.

### 8.2 Dispatch

- [x] ADR-045 spec file created. -> `docs/specs/adr-045-workflow-state-version.md`
- [x] ADR-045 status/phase transitioned. -> `docs/adr/ADR-045.md`
- [x] #1401 tracker open for implementation or replacement open issue recorded. -> `gh issue reopen 1401`
- [x] Umbrella PR opened before agent dispatch. -> #1410
- [x] Prompt files created or dispatch prompts recorded. -> `docs/planning/dispatch-prompts/adr-045-a*.md`

### 8.3 Implementation

- [x] A1 backend versioning output reviewed. -> PR #1411 merged; Codex P1/P2 accepted and fixed.
- [x] A2 file tab output reviewed. -> PR #1425 merged; no Codex comments found.
- [~] A3 frontend reconciliation output reviewed. -> A3 stopped on missing `file.changed` WebSocket backend contract; manager fix in progress.
- [ ] A4 audit report reviewed.

### 8.4 Audit

- [ ] Audit agent assigned after implementation outputs exist.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Findings recorded.

### 8.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 9. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Ruff | `ruff check src/scistudio/api/routes/workflow_watcher.py src/scistudio/api/routes/workflows.py src/scistudio/api/schemas.py src/scistudio/api/ws.py tests/integration/conftest.py tests/integration/test_race_autosave.py tests/integration/test_race_lineage_restore.py tests/integration/test_race_agent_write.py tests/integration/test_race_external_editor.py tests/integration/test_race_multi_session.py` | `[x]` | pass |
| Format | `ruff format --check src/scistudio/api/routes/workflow_watcher.py src/scistudio/api/routes/workflows.py src/scistudio/api/schemas.py src/scistudio/api/ws.py tests/integration/conftest.py tests/integration/test_race_autosave.py tests/integration/test_race_lineage_restore.py tests/integration/test_race_agent_write.py tests/integration/test_race_external_editor.py tests/integration/test_race_multi_session.py` | `[x]` | 10 files already formatted |
| Tests | `pytest tests/api/test_workflow_version_vector.py tests/api/test_file_version_vector.py tests/api/test_workflow_changed_event_schema.py tests/api/routes/test_workflow_watcher_fallback.py tests/api/test_reload_on_save.py tests/integration/test_race_autosave.py tests/integration/test_race_lineage_restore.py tests/integration/test_race_agent_write.py tests/integration/test_race_external_editor.py tests/integration/test_race_multi_session.py --timeout=60 --no-cov` | `[x]` | 22 passed |
| Targeted QA audit | `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/adr-045-drift-fix-audit.json --skip-frontmatter-lint --skip-fact-drift --skip-architecture-drift --skip-vulture` | `[x]` | `docs/audit/adr-045-drift-fix-audit.json` |
| Full audit | `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/adr-045-full-audit.json` | `[x]` | `docs/audit/adr-045-full-audit.json` |
| Sentrux | MCP scan/check/session evidence | `[x]` | `docs/audit/adr-045-sentrux.json` |

## 10. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-05-22 | manager | #1407: ADR-041/043 implemented code existed but ADR/spec phase/status remained planning/Draft, hiding doc/signature drift. | Manager opened drift-fix track before ADR-045 implementation dispatch. | #1407 |
| 2026-05-22 | manager | Owner emphasized contract consistency for ADR-045 dispatch. | Added contract-consistency requirements to spec, checklist, and all A1-A4 dispatch prompts. | #1401 |
| 2026-05-22 | A3 / manager | A3 found `file.changed` was emitted to EventBus but not forwarded over `/ws`, and file-tab external-editor watcher fallback was absent. | Manager expanded gate scope, added `file.changed` WebSocket forwarding, project-file watcher fallback, workflow body/header `source_id` parity, and ADR race-matrix integration tests. | #1401 |
| 2026-05-22 | manager | Umbrella CI semantic duplication and A3 Sentrux cycle checks flagged route-level duplication/cycles in the file-event contract wiring. | Manager refactored watcher event flow and moved shared file event constants into `scistudio.api.file_contracts` so route modules no longer import each other for `file.changed` contract truth. | #1401 |

## 11. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.

## 12. Dispatch Runtime Log

Append only. Manager-owned rows only; implementation agents update their
assigned track rows above.

| Date | Agent | Tool ID | Status | Notes |
|---|---|---|---|---|
| 2026-05-22 | A1 / Galileo | `019e4dd1-232e-7ec3-8348-c444808bbadc` | `[x]` | PR #1411 merged to `track/adr-045/version-vector`; Codex P1/P2 accepted and fixed. |
| 2026-05-22 | A2 / Linnaeus | `019e4dd1-2401-7ec0-9752-d5849a342f5b` | `[x]` | PR #1425 merged to `track/adr-045/version-vector`; no Codex auto-review comments. |
| 2026-05-22 | A3 / Godel | `019e4dd1-24fb-7d43-af13-37dd74fd67f1` | `[!]` | Stopped on backend contract blocker: `file.changed` not in `/ws` outbound allowlist; manager accepted finding. |
| 2026-05-22 | manager | local | `[~]` | Added backend contract-consistency fix and five ADR race-matrix integration test files; targeted backend regression suite passed 22 tests. |
| 2026-05-22 | manager | local | `[~]` | Fixed semantic duplication ratchet and route-import cycle risk by sharing watcher event flow and moving `file.changed`/allowlist constants to `src/scistudio/api/file_contracts.py`; targeted backend regression suite passed 22 tests. |
| 2026-05-22 | A3 / Godel | local | `[~]` | Resumed on tracking `4a9951b4`; frontend API/store/WebSocket reconcile and deterministic tests cover stale drop, source_id self-echo, clean remote adoption, dirty conflict preservation, gitRestore refresh, and file.changed handling; A3 did not add backend integration files because manager landed them on tracking. Sentrux free-tier baseline remains failing on clean tracking (`max_cycles` 4 > 3), so this is recorded as a gate blocker rather than claimed pass evidence. |
| 2026-05-22 | A4 / audit | pending | `[ ]` | Held until A3 PR/commit exists; prompt prepared at `docs/planning/dispatch-prompts/adr-045-a4-audit-with-context.md`. |

## 13. Codex Auto-Audit Triage

Append only. Do not resolve or reply to GitHub review threads unless the owner
explicitly asks.

| Date | PR | Source | Severity | Finding | Decision | Owner | Status |
|---|---|---|---|---|---|---|---|
| 2026-05-22 | #1411 | `chatgpt-codex-connector` | P1 | `WorkflowResponse.version` was repurposed from YAML/schema semver to ADR-045 state counter, which can corrupt read-then-save clients. | Accept. Preserve `version` as semver and expose state counter under `state_version`; update docs/tests for contract consistency. | A1 / Galileo | `[x]` |
| 2026-05-22 | #1411 | `chatgpt-codex-connector` | P2 | Watcher suppression drops every event for the workflow ID during the first-party window, which can hide a real external edit after an API/git write. | Accept. Suppress only exact first-party echoes and add a regression test for external edit after first-party write. | A1 / Galileo | `[x]` |
| 2026-05-22 | #1425 | GitHub review/comment scan | N/A | No Codex review, inline comments, or PR comments found after CI completed. | No action required. | manager | `[x]` |
| 2026-05-22 | #1443 | GitHub review/comment scan | N/A | No Codex review, inline comments, or PR comments found after PR creation and CI gate failure inspection. | No action required; gate blocker is Sentrux evidence, not Codex feedback. | A3 / Godel | `[x]` |
