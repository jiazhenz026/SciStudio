---
title: "Codebase No-Context Audit Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs: []
language_source: en
---

# Codebase No-Context Audit Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `Dispatch 3 no-context audit agents (read only ADR/spec/docs/code/tests, not issues/records) to find doc-contract drift, layer/module routing problems, and serious code bugs; land audit reports in a new PR.`
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#1589`
- Gate record: `.workflow/records/1589-audit-2026-06-11-codebase-no-context.json`
- Branch/worktree plan: `manager branch audit/2026-06-11-codebase-no-context @ ../sci-wt/audit-nc; the 3 audit agents are no-context read-only sub-agents that return structured findings (no writable worktree of their own).`
- Protected branch: `main`
- Umbrella branch: `audit/2026-06-11-codebase-no-context (serves as umbrella + final audit branch)`
- Umbrella PR: `#1590`
- Umbrella PR title: `[DO NOT MERGE] audit(repo): no-context multi-agent audit (drift / routing / bugs)`
- Final PR target: `main`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md` (N/A — no implementation agents)
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md` (N/A)
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md` (USED for all 3 agents)

## 1.1 Orchestration Decision (manager note)

- The 3 audit agents are dispatched **no-context** and **read-only**: they may read
  only ADRs, specs, repository docs, code, tests, committed generated facts, and
  tool output they run themselves. They are not given the owner request, this
  checklist, the issue, PR claims, commit messages, or any manager summary.
- Because the agents are strictly read-only, each one **returns its complete
  audit report as structured output**, and the **manager persists** each report
  as a committed file under `docs/audit/` on this branch, plus a consolidated
  index. This keeps the audit reports as committed repository evidence merged
  into the final PR (the durability requirement) while keeping auditors fully
  read-only and context-isolated. No audit report exists only in chat.
- The manager independently spot-verifies every P1/blocking finding against the
  cited code before it enters the consolidated report.

## 2. Scope

- In scope:
  - `docs/audit/2026-06-11-doc-contract-drift-no-context.md`
  - `docs/audit/2026-06-11-layer-module-routing-no-context.md`
  - `docs/audit/2026-06-11-code-bugs-no-context.md`
  - `docs/audit/2026-06-11-codebase-no-context-INDEX.md`
  - `docs/audit/2026-06-11-adr048-pr-review.md` (Track B — owner's primary target)
  - `docs/planning/codebase-no-context-audit-checklist.md`
  - `.workflow/records/1589-audit-2026-06-11-codebase-no-context.json` (gate ledger)
- Out of scope:
  - Any implementation / source / test file change. This PR is audit evidence
    only; remediation is tracked as follow-up issues.
- Protected paths:
  - `N/A` — no protected-core file is modified (auditors are read-only).
- Deferred work:
  - Remediation of findings -> tracked as new follow-up issues, not fixed here.

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

- [x] Dedicated manager branch and worktree created. -> `audit/2026-06-11-codebase-no-context @ ../sci-wt/audit-nc`
- [x] Existing issue linked, or new issue created only if none exists. -> `#1589` (no existing issue tracked a broad no-context repo audit)
- [x] Gate record started. -> `.workflow/records/1589-audit-2026-06-11-codebase-no-context.json`
- [x] Scope include/exclude recorded in the gate record. -> `--include docs/audit --include docs/planning`
- [x] Umbrella branch created. -> `audit/2026-06-11-codebase-no-context`
- [x] Umbrella PR opened. -> `#1590`
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch (`main`) and umbrella PR number (`#1590`) recorded in this checklist.
- [x] No `pip install -e .` environment pollution found. -> dev env via `SCISTUDIO_DEV=1 PYTHONPATH=.../src`
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template (audit no-context) and linked below.
- [ ] Sentrux baseline recorded, or N/A reason recorded. -> recorded automatically by `gate_record check` (docs-only diff).

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `No bypass used. Normal local gate validation in effect.`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `gate_record check --mode pre-commit` | `N/A` | `[ ]` | `pending` |
| Commit message | `gate_record check --mode commit-msg` | `N/A` | `[ ]` | `pending` |
| Pre-push | `gate_record check --mode pre-push` | `N/A` | `[ ]` | `pending` |
| Pre-PR reconcile | `gate_record check --mode pre-pr --pr-body-file <body>` | `N/A` | `[ ]` | `pending` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `N/A — this PR adds audit reports + a dispatch checklist only; no AI-runtime/wrapper/hook behavior changes.`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `AUD-1 drift` | `audit_reviewer` | `no-context` | audit-no-context template (composed verbatim, §7.1) | ADR/spec ⇄ code contract drift across whole repo | n/a (read-only) | n/a (read-only) | report returned to manager | edit any file; read issues/records/PRs | `#1589` | `[~] dispatched (wf wci703d2k)` |
| `AUD-2 routing` | `audit_reviewer` | `no-context` | audit-no-context template (composed verbatim, §7.2) | layer & module routing / boundary integrity across src+packages+frontend | n/a (read-only) | n/a (read-only) | report returned to manager | edit any file; read issues/records/PRs | `#1589` | `[~] dispatched (wf wci703d2k)` |
| `AUD-3 bugs` | `audit_reviewer` | `no-context` | audit-no-context template (composed verbatim, §7.3) | serious code bugs / correctness defects in runtime path | n/a (read-only) | n/a (read-only) | report returned to manager | edit any file; read issues/records/PRs | `#1589` | `[x] done (5 findings)` |
| `PR-1 #1577` | `audit_reviewer` | `with-context` | audit-with-context template (composed verbatim) | review PR #1577 (SPEC1 preview-system) vs ADR-048 + spec | n/a (read-only) | n/a (read-only) | report returned to manager | edit/merge any PR; fix code | `#1589` | `[x] done (1×P1 / 2×P2 / 2×P3)` |
| `PR-2 #1580` | `audit_reviewer` | `with-context` | audit-with-context template (composed verbatim) | review PR #1580 (SPEC2 plot-tools) vs ADR-048 + spec | n/a (read-only) | n/a (read-only) | report returned to manager | edit/merge any PR; fix code | `#1589` | `[x] done (4×P3)` |
| `PR-3 #1581` | `audit_reviewer` | `with-context` | audit-with-context template (composed verbatim) | review PR #1581 (SPEC3 docs) vs ADR-048 + spec | n/a (read-only) | n/a (read-only) | report returned to manager | edit/merge any PR; fix code | `#1589` | `[x] done (3×P3, pass)` |

## 7. Track: No-Context Codebase Audit

### 7.1 AUD-1 — Documentation / Contract Drift

- Lens: ADR/spec `governs` modules & files vs. real code; documented-but-unimplemented behavior; implemented-but-undocumented public behavior; public signature/schema drift; hand-edited generated facts.
- Allowed surfaces: `docs/adr/**`, `docs/specs/**`, `docs/architecture/**`, `src/scistudio/**`, `packages/**`, `frontend/src/**`, `tests/**`.
- Report path: `docs/audit/2026-06-11-doc-contract-drift-no-context.md`
- [x] Dispatched (wf wci703d2k). [x] Findings returned (4: 0×P1 / 1×P2 / 3×P3). [x] Report persisted. [x] P1 verified by manager (no P1 in this lens; DRIFT-03/04 phantom paths confirmed).

### 7.2 AUD-2 — Layer & Module Routing / Boundary Integrity

- Lens: import direction & layering (core ⇄ engine ⇄ api ⇄ blocks ⇄ plugins ⇄ frontend), plugin-logic-in-core, frontend-as-runtime-truth, dependency cycles, registry/dispatch wiring, dead or misrouted paths.
- Allowed surfaces: `src/scistudio/**`, `packages/**`, `frontend/src/**`, `docs/adr/**`, `docs/specs/**`, `pyproject.toml`, import-linter config.
- Report path: `docs/audit/2026-06-11-layer-module-routing-no-context.md`
- [x] Dispatched (wf wci703d2k). [x] Findings returned (7: 3×P1 / 3×P2 / 1×P3). [x] Report persisted. [x] P1 verified by manager (ROUTE-01/02/06 all confirmed; root = missing ai/agent/__init__.py → issue #1591).

### 7.3 AUD-3 — Serious Code Bugs / Correctness Defects

- Lens: resource/handle leaks, subprocess & cancellation races, swallowed exceptions, validation gaps, incorrect state transitions, async misuse, data-loss/corruption risks.
- Allowed surfaces: `src/scistudio/engine/**`, `src/scistudio/api/**`, `src/scistudio/core/**`, `src/scistudio/blocks/**`, `src/scistudio/ai/**`, `packages/**`, governing ADRs/specs for those modules.
- Report path: `docs/audit/2026-06-11-code-bugs-no-context.md`
- [x] Dispatched (wf wci703d2k). [x] Findings returned (5: 0×P1 / 3×P2 / 2×P3). [x] Report persisted. [x] P1 verified by manager (no P1; BUG-RM-01 no-acquire-caller + concurrency workflow_id gaps confirmed).

### 7.4 Audit (manager consolidation)

- [x] All 3 (Track A) + 3 (Track B) audit agents returned findings.
- [x] Each Track A per-lens audit report file persisted under `docs/audit/`.
- [x] Consolidated Track A index report persisted.
- [x] Track B consolidated PR-review report persisted (`2026-06-11-adr048-pr-review.md`).
- [x] Manager spot-verified every P1/blocking finding against cited code (Track A ROUTE-01/02/06; Track B #1577 F1 + both #1577 P2s).
- [x] Findings recorded with severity ordering.
- [x] Follow-up issue opened for the Track A P1 cluster (#1591); remaining P2/P3 documented as proposed plan in the index for owner triage; Track B P1 (#1577 F1) flagged for in-PR fix before SPEC 1 merge.

### 7.6 Track B — ADR-048 PR review (with-context)

- [x] PR #1577 (SPEC1) reviewed -> pass-with-fixes (1×P1 F1 collection routing, 2×P2, 2×P3).
- [x] PR #1580 (SPEC2) reviewed -> pass-with-fixes (4×P3, no P1/P2).
- [x] PR #1581 (SPEC3) reviewed -> pass (3×P3).
- [x] Report: `docs/audit/2026-06-11-adr048-pr-review.md`.

### 7.5 Integration

- [ ] Manager reviewed every persisted report.
- [ ] Scope compliance verified (docs-only diff).
- [ ] Reports committed to the audit branch.

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | `pending` |
| Targeted tests | `N/A — audit-evidence-only PR, no implementation code changed (test-na recorded)` | `[x]` | `gate ledger test_na` |
| Pre-push gate check | `gate_record check --mode pre-push --base origin/main --head HEAD` | `[ ]` | `pending` |
| Gate ledger check (pre-PR) | `gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | `pending` |
| Gate finalize (pre-PR) | `gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#1589"` | `[ ]` | `pending` |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --title <t> --body <b>` | `[ ]` | `pending` |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| `2026-06-11` | `manager` | Owner clarified after dispatch that the PRIMARY target is reviewing ADR-048 PRs #1577/#1580/#1581 (not a full-repo audit); full-repo sweep retained as prevention. | Recorded via `gate_record amend` (owner-directive); added Track B (3 with-context PR-review agents, wf wl21wy5or) + report `docs/audit/2026-06-11-adr048-pr-review.md`. | Track B landed; #1577 F1 (P1) flagged to owner. |

## 10. Final Readiness

- [ ] All 3 audit agents have final outputs.
- [ ] Manager reviewed every persisted report.
- [ ] Gate record includes issue, scope, plan, docs, checks, commit, and PR evidence.
- [ ] PR closes issue #1589.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
