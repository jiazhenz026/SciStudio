---
title: "ADR-055 Spec 0-1 Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
related_specs:
  - adr-055-prefix-independence
  - adr-055-webmcp-bridge
language_source: en
---

# ADR-055 Spec 0-1 Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: "Act as manager; implement ADR-055 spec0-1 (prefix
  independence + WebMCP bridge, referencing the read-only scistudio-web-demo);
  deliver 2 PRs with CI passing, no deferrals."
- Task kind: `feature` (implementation tracks); `manager` (this checklist)
- Manager persona: `manager`
- Issue: `#2270` (Spec 0), `#2271` (Spec 1); umbrella context `#2263` (closed),
  ADR-055 tracking `#2239` (closed)
- Gate record: `.workflow/records/track-adr-055-spec0-1-track-adr-055-spec0-1.json`
- Branch/worktree plan: manager umbrella `track/adr-055-spec0-1` at
  `.worktrees/track-adr-055-spec0-1`; agent branches
  `feat/2270-prefix-independence` (base `origin/main`) and
  `feat/2271-webmcp-bridge` (stacked on `feat/2270-prefix-independence`,
  `--base-ref` recorded per #2143)
- Protected branch: `main`
- Umbrella branch: `track/adr-055-spec0-1`
- Umbrella PR: `#2273`
- Umbrella PR title: `[DO NOT MERGE] ADR-055 Spec 0-1 dispatch`
- Final PR target: `main` (manager explicitly assigns both spec PRs as final
  PRs to the protected branch per owner directive "推上去2个PR")
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - Spec 0 (`docs/specs/adr-055-prefix-independence.md`): backend `root_path`
    plumbing, SPA bootstrap injection, CLI `--root-path`/host flags, frontend
    `base-path.ts` + migration of root-relative call sites, worker callback URL
  - Spec 1 (`docs/specs/adr-055-webmcp-bridge.md`): `src/scistudio/api/routes/webmcp.py`,
    adapter contract in `ai/agent/mcp/server.py`, audience-tag filtering,
    session middleware (loopback token), `frontend/src/webmcp/`, tests
- Out of scope:
  - Domain tools (`get_agent_context`, workspace, execution):
    adr-055-agent-context-workspace
  - Hub OAuth, per-user routing: adr-055-lab-deployment
  - Local background runtime: adr-055-local-background-runtime
  - AI-host presentation (deferred by owner)
  - ANY write/commit/push to `scistudio-web-demo` (read-only reference at
    `.scratch-design/webmcp-recovery/scistudio-web-demo`; local blocking hooks
    installed, push remote disabled, upstream branch protection on)
- Protected paths: none touched beyond the spec-declared core files; core-path
  changes are spec-governed (ADR-055 governs lists them)
- Deferred work: N/A (owner directive: no deferrals)

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

- [x] Dedicated manager branch and worktree created. ->
      `track/adr-055-spec0-1` at `.worktrees/track-adr-055-spec0-1`
- [x] Existing issue linked, or new issue created only if none exists. ->
      #2270, #2271 (no open issue tracked the work; #2239/#2263 closed)
- [x] Gate record started. -> `.workflow/records/track-adr-055-spec0-1-track-adr-055-spec0-1.json`
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created. -> `track/adr-055-spec0-1`
- [x] Umbrella PR opened. -> #2273
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist. -> main / #2273
- [x] No `pip install -e .` environment pollution found. -> gate CLI runs via
      `PYTHONPATH=src`, no editable install
- [x] Dispatch checklist copied from the template and committed.
- [ ] Dispatch prompts created from the correct prompt template and linked
      below.
- [x] Sentrux baseline recorded, or N/A reason recorded. -> N/A: Sentrux MCP
      not available in this runtime; guard evidence is recorded by
      `gate_record check` where applicable.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | `<pending>` |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | `<pending>` |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | `<pending>` |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file <body-file>` | `N/A` | `[ ]` | `<pending>` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `N/A — no AI-workflow behavior changes`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `A1` | `implementer` | `N/A` | `.workflow/local/dispatch-a1-spec0.md` | Spec 0 prefix independence | `feat/2270-prefix-independence` | `.worktrees/feat-2270-prefix-independence` | spec §4.2 files | `docs/ai-developer/**`, demo repo, other ADR-055 specs | `#2270` | `[ ]` |
| `A2` | `implementer` | `N/A` | `.workflow/local/dispatch-a2-spec1.md` | Spec 1 WebMCP bridge | `feat/2271-webmcp-bridge` | `.worktrees/feat-2271-webmcp-bridge` | spec §4.2 files | `docs/ai-developer/**`, demo repo, other ADR-055 specs | `#2271` | `[ ]` |

## 7. Track: Spec 0 — Prefix Independence

### 7.1 Track Scope

- Owner: `A1 (implementer)`
- In scope: spec `adr-055-prefix-independence` §3 FR-001..FR-009, §4.2 files
- Out of scope: JupyterHub/auth, WebMCP bridge routes, lab deployment
- Required docs: spec acceptance; user docs N/A unless behavior surface
  changes warrant it (record rationale in ledger)
- Required tests: `tests/api/test_root_path.py`,
  `frontend/src/lib/api/base-path.test.ts`

### 7.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected. -> work template (non-audit)
- [x] Audit mode recorded when persona is `audit_reviewer`. -> N/A
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 7.3 Implementation

- [ ] Backend root_path + SPA injection + CLI flags -> `<pending>`
- [ ] Frontend base-path module + call-site migration -> `<pending>`
- [ ] Tests: `tests/api/test_root_path.py`, `base-path.test.ts` -> `<pending>`

### 7.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 7.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 8. Track: Spec 1 — WebMCP Bridge

### 8.1 Track Scope

- Owner: `A2 (implementer)`
- In scope: spec `adr-055-webmcp-bridge` §3 FR-001..FR-011, §4.2 files;
  transplant from demo commit `952f697b` (read-only)
- Out of scope: domain tools, Hub OAuth backend, AI-host presentation,
  local socket wire protocol changes
- Required docs: spec acceptance; N/A rationale recorded otherwise
- Required tests: `tests/api/test_webmcp.py`, `tests/ai/test_mcp_fastmcp.py`
  (audience filtering), `frontend/src/webmcp/register.test.ts`

### 8.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected. -> work template (non-audit)
- [x] Audit mode recorded when persona is `audit_reviewer`. -> N/A
- [x] Agent branch/worktree assigned (stacked on Spec 0 branch, `--base-ref`
      recorded).
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 8.3 Implementation

- [ ] Bridge router + adapter contract + audience filtering -> `<pending>`
- [ ] Session middleware (loopback token) + project binding -> `<pending>`
- [ ] Frontend registration module + tests -> `<pending>`

### 8.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 8.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 9. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | `<pending>` |
| Targeted tests | per-track test commands | `[ ]` | `<pending>` |
| Pre-push gate check | `python -m scistudio.qa.governance.gate_record check --mode pre-push --base origin/main --head HEAD` | `[ ]` | `<pending>` |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | `<pending>` |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#<issue>"` | `[ ]` | `<pending>` |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run ...` | `[ ]` | `<pending>` |

## 10. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-09-06 | manager | Hook-install command resolved a relative gitdir and briefly wrote blocking hooks into the main repo `.git/hooks`; a local-only test commit landed in the demo clone | Restored main hooks to documented state (pre-push allow shim; no commit hooks per #2150); `reset --hard` the demo clone back to `cf0fe769` (no push, remote disabled); reinstalled blocking hooks with absolute paths and verified they fire | N/A |

## 11. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
