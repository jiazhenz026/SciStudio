---
title: "ADR-054 Panels And MiniApps Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs: [54, 55]
related_specs: [adr-054-panels, adr-054-miniapp, adr-055-enterprise-support, adr-055-identity-seam]
language_source: en
---

# ADR-054 Panels And MiniApps Agent Dispatch Checklist

> Mandatory tracking file. Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`.
> The manager records agent evidence after reviewing it. Planned work is not completed work.

## 1. Change Summary

- Owner request: coordinate and implement ADR-054 Panels and MiniApps, adapting Phase A to ADR-055 enterprise features.
- Task kind: `manager`; persona: `manager`.
- Issue: #2296 (coordination); #2293 (A), #2294 (B), #2295 (C); #2288 (tracking and deferrals). Phase D issue to be linked before its implementation.
- Gate record: `.workflow/records/2296-adr054-coordination.json`.
- Branch/worktree plan: `codex/2296-adr054-coordination`, `.worktrees/adr054-manager`; each implementation agent has its own branch and worktree.
- Protected branch: `main`.
- Umbrella branch: `codex/2296-adr054-coordination`.
- Umbrella PR: #2353 (draft, open before dispatch).
- Umbrella PR title: `[DO NOT MERGE] ADR-054 Panels and MiniApps coordination`.
- Final PR target: `main`, one implementation PR per phase. No merge authorization.
- Dispatch prompt templates: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`, `agent-dispatch-audit-with-context-prompt-template.md`, `agent-dispatch-audit-no-context-prompt-template.md` in that same directory.
- Filled prompts: `docs/planning/adr-054-phase-a-dispatch.md` (prepared before dispatch).

## 2. Scope

- In scope: A mechanism and enterprise adaptation; B core parity migration; C authoring/migration docs and skills; D panel Python and MiniApp user flows.
- Phase A follows current `adr-054-panels` T-001 through T-013, including SDK sample mode. Owner decision in this session: preserve the existing sidebar entry in A; change entries together in D. Historical Panels-tab/promotion amendments in #2293 do not apply to A.
- Enterprise integration uses the existing identity seam. Register only `/api/panels/t/`, keep session-authenticated operations separate, preserve prefix handling, and test against a replacement guard. No Lab-specific middleware.
- Out of scope: private enterprise implementation, 0.6 legacy removal, notebook/sync, Python execution in preview/interactive, workflow engine changes, owner-controlled architecture text.
- Protected paths: core/runtime/engine, governance, ADR frontmatter and owner-controlled architecture require their normal scope and authorization handling; agents must report before expanding into them.
- Deferred work: `TODO(#2288)`: legacy removal in 0.6, notebook/sync and external package migrations remain tracked there. B/C/D are scheduled phases, not silently omitted parts of A.

## 3. Conventions

- `[ ]` not started; `[~]` in progress; `[x]` done; `[!]` blocked.
- Completed rows require committed artifacts, gate events, or PR/CI evidence.
- Amend scope before editing outside the write set. Do not share writable worktrees.

## 4. Manager Preflight

- [x] Dedicated branch/worktree created from `7b132175`.
- [x] Existing coordination and A/B/C issues inspected; no duplicate issue created.
- [x] Manager gate initialized and plan recorded through the ledger CLI.
- [x] Scope declared: `docs/planning/adr-054-*` and manager ledger.
- [x] Umbrella branch created.
- [x] Umbrella PR opened and number recorded: #2353; initial checklist committed at `831b37b6`.
- [x] Filled prompts prepared in `docs/planning/adr-054-phase-a-dispatch.md`; committed before dispatch.
- [x] Runtime choice avoids editable install: `PYTHONPATH=src python`.
- [x] Manager gate passed commit hygiene and full audit; Sentrux MCP unavailable, CLI fallback is gate-selected where applicable.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: N/A. No bypass requested or used.
- Owner authorization source: N/A.
- Reason: N/A.

| Hook/check | Command | Bypass | Status | Evidence |
|---|---|---|---|---|
| Commit hooks | Removed in #2150; validation is at pre-PR/CI | N/A | [x] | `docs/ai-developer/rules.md` |
| Pre-PR reconcile | `gate_record check --mode pre-pr` | N/A | [ ] | Pending |

## 5.1 Docs Impact Check

Manager bootstrap changes no wrapper, hook, gate evaluator, CI, or product runtime.
Common rules, gated workflow, dispatch rules, manager persona, and templates were read.
AI workflow documentation updates are N/A for these coordination-only changes.
Implementation docs obligations remain with the implementation phases.

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | implementer | N/A | Phase A dispatch, A1 | Descriptor/discovery/routing/context/routes/interactive validation | `codex/2293-panel-backend` | `.worktrees/adr054-backend` | Backend panel subsystem and named integration files | Frontend, SDK/libraries, read-access implementation, app/security middleware | #2293 | [ ] |
| A2 | implementer | N/A | Phase A dispatch, A2 | SDK, libraries, frame/bridge, preview and interactive hosts | `codex/2293-panel-frontend` | `.worktrees/adr054-frontend` | Frontend panel integration and `panels/sdk`, `panels/lib` | Backend Python, enterprise capability definitions | #2293 | [ ] |
| A3 | implementer | N/A | Phase A dispatch, A3 | Bounded read extensions, opaque-origin/CORS hardening, app mounting | `codex/2293-panel-security` | `.worktrees/adr054-security` | Named read-access and app/security files plus tests | Panel registry/routes, frontend, identity seam definitions | #2293 | [ ] |

Audits get dedicated worktrees and a selected context mode after integration.

## 7. Track: Phase A With ADR-055 Compatibility

### 7.1 Track Scope

- Owner: manager for integration; A1/A2/A3 for their write sets.
- Required docs: `docs/planning/adr-054-enterprise-contracts.md`, implementation notes and changelog; full guides remain Phase C.
- Required tests: descriptor, tier/routing parity, contexts/tokens/reads, root/prefix guard matrix, CSP and direct-path attacks, frame/channel/disposal, interactive writeback, preview tab/drill-down, SDK sample mode and packaging.

### 7.2 Dispatch

- [ ] Prompts finalized from the work template with issue, branch, write set, TODO rule, tests, docs, and stop conditions.
- [ ] All agent branches/worktrees created and gates initialized.
- [ ] Umbrella PR and committed prompts exist before agents start.

### 7.3 Implementation

- [ ] A1 backend and tests, with backend/frontend contract communicated before integration.
- [ ] A2 frontend/SDK/library set and tests.
- [ ] A3 read extensions and global security/app wiring with tests.
- [ ] API snapshot and packaging reconciled after integration.
- [ ] ADR/spec contract landing and protected-path handling complete.

### 7.4 Audit

- [ ] With-context audit assigned; report committed.
- [ ] Independent no-context audit assigned; report committed.
- [ ] Findings fixed or explicitly tracked before readiness.

### 7.5 Integration

- [ ] Every diff reviewed, write sets checked, conflicts resolved intentionally.
- [ ] Enterprise PR #2336 overlap reconciled against its current state.
- [ ] Root and prefixed replacement-guard checks pass on the integrated candidate.
- [ ] Frontend/browser smoke and required containment evidence recorded.

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Manager local/pre-PR gate | `PYTHONPATH=src python -m scistudio.qa.governance.gate_record check` | [x] | Ledger events and `2966a1a9` |
| Manager finalize/wrapper | `gate_record finalize`; `scripts/scistudio_pr_create.py` | [x] | Draft #2353 |
| A targeted tests and pre-PR gate | Gate-selected checks from integration worktree | [ ] | Pending |
| CI | GitHub checks on each PR | [ ] | Pending |

## 9. Drift Log

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-09-11 | manager | Historical umbrella #2299 is closed; its branch predates the enterprise seam and MiniApp revision | New coordination branch from current main; retain historical record as context only | #2296 |
| 2026-09-11 | manager | #2293 describes unavailable Lab middleware and an interim Panels sidebar | Use existing identity seam; owner chose to preserve A entry and consolidate UI in D | #2293, #2288 |
| 2026-09-11 | manager | Current specs add D but #2296 lists only A/B/C | Coordinate all four phases; D depends on A | #2296 |

## 10. Final Readiness

- [ ] All implementation and audit outputs delivered and reviewed.
- [ ] Tests, docs, packaging, gate evidence and tracked deferrals complete.
- [ ] Each phase PR closes its implementation issue; umbrella closes coordination only.
- [ ] CI passed; checklist matches the actual candidate.
- [ ] Owner merge authorization obtained before any merge.
