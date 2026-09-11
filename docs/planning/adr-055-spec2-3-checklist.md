---
title: "ADR-055 Spec 2-3 Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
related_specs:
  - adr-055-agent-context-workspace
  - adr-055-local-background-runtime
language_source: en
---

# ADR-055 Spec 2-3 Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: "After the design discussion, start a manager worktree and
  implement ADR-055 Spec 2 and Spec 3." Each PR updates its own spec to the
  owner decisions recorded on 2026-09-10 in its issue.
- Task kind: `feature` (implementation tracks); `manager` (this checklist)
- Manager persona: `manager`
- Issue: `#2282` (manager); implementation `#2279` (Spec 2), `#2280` (Spec 3);
  related out-of-scope fix `#2281` (worker orphan cleanup, owner-separated)
- Gate record: `.workflow/records/2282-track-adr-055-spec2-3.json`
- Branch/worktree plan: manager umbrella `track/adr-055-spec2-3` at
  `.worktrees/track-adr-055-spec2-3`; agent branches
  `feat/2279-agent-context-workspace` (stacked on
  `feat/2271-webmcp-bridge`, `--base-ref` recorded per #2143; rebased onto
  `main` before its PR opens, after PR #2275 merges — owner option B) and
  `feat/2280-local-background-runtime` (base `origin/main`)
- Protected branch: `main`
- Umbrella branch: `track/adr-055-spec2-3`
- Umbrella PR: `#2283`
- Umbrella PR title: `[DO NOT MERGE] ADR-055 Spec 2-3 dispatch`
- Final PR target: `main` (manager assigns both spec PRs as final PRs to the
  protected branch; the Spec 2 PR opens only once its base is `main`, so
  `ci.yml` runs on it)
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`
- Filled prompts: `docs/planning/adr-055-spec2-3-dispatch-prompts.md`

## 2. Scope

- In scope:
  - Spec 2 (`docs/specs/adr-055-agent-context-workspace.md`) as amended by the
    #2279 owner decisions: `get_agent_context`; inspect tools (absolute paths,
    OS-user read scope, bounded streaming reads); author tools (project-confined,
    server-side hook blacklist for `workflows/*.yaml` and `data/`); hook parity
    via tool results (list_blocks-before-block-write per backend lifetime,
    concrete port type warning, scistudio CLI denial in `run_command`,
    `run_workflow` poll hint); managed `run_command` (asyncio, ProcessRegistry,
    bounded output, request-vs-job cancellation, in-memory status); spec text
    updates, including moving transfer into the Spec 4 spec text
  - Spec 3 (`docs/specs/adr-055-local-background-runtime.md`) as amended by the
    #2280 owner decisions: mode picker on every launch with "don't ask again";
    headless external-AI mode with tray (menu: open connection window, copy
    address, status, open in desktop mode, stop and quit) and connection window;
    backend stops with Electron (POSIX watchdog kept; Windows verified, backstop
    added only if needed); mode-aware `second-instance`; OTA inclusion; shell
    file lists kept in parity; spec text updates
- Out of scope:
  - Transfer implementation (upload picker, download endpoint): Spec 4
    (`adr-055-lab-deployment`)
  - Worker/grandchild orphan cleanup on backend stop: #2281
  - Hub OAuth / lab deployment: Spec 4
  - AI-host presentation (deferred by owner)
  - Spec 0/1 code except the minimal, gate-amended touch points named in the
    Spec 2 prompt (PRs #2274/#2275 own those files)
  - `docs/ai-developer/**` (governance surface) including the release runbook
- Protected paths: none expected; any `src/scistudio/core/**` need is a stop
  condition
- Deferred work: transfer -> Spec 4 spec text (owner decision, moved in the
  Spec 2 PR); worker orphans -> #2281

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
      `track/adr-055-spec2-3` at `.worktrees/track-adr-055-spec2-3`
- [x] Existing issue linked, or new issue created only if none exists. ->
      #2279, #2280, #2281, #2282 (no open issue tracked the work; #2263 closed)
- [x] Gate record started. -> `.workflow/records/2282-track-adr-055-spec2-3.json`
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created. -> `track/adr-055-spec2-3`
- [x] Umbrella PR opened. -> #2283 (via `scripts/scistudio_pr_create.py`, pre-flight clean)
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist. -> main / #2283
- [x] No `pip install -e .` environment pollution found. -> gate CLI runs via
      `PYTHONPATH=src`, no editable install
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template and linked
      below. -> `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (A1, A2;
      audit prompts appended before audit dispatch)
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
| `A1` | `implementer` | `N/A` | `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (A1) | Spec 2 agent context, workspace, execution tools | `feat/2279-agent-context-workspace` | `.worktrees/feat-2279-agent-context-workspace` | prompt A1 "Scope" | `frontend/**`, `desktop/**`, `docs/ai-developer/**`, transfer, #2281 | `#2279` | `[~]` |
| `A2` | `implementer` | `N/A` | `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (A2) | Spec 3 local startup modes and background runtime | `feat/2280-local-background-runtime` | `.worktrees/feat-2280-local-background-runtime` | prompt A2 "Scope" | `frontend/**`, `src/scistudio/**` (except conditional Windows backstop), `docs/ai-developer/**`, #2281 | `#2280` | `[~]` |

## 7. Track: Spec 2 — Agent Context, Workspace, Execution

### 7.1 Track Scope

- Owner: `A1 (implementer)`
- In scope: spec `adr-055-agent-context-workspace` as amended by #2279
  decisions 1-6
- Out of scope: transfer (Spec 4), frontend, desktop, #2281
- Required docs: spec text updated to the decisions; Spec 4 spec gains the
  transfer requirements removed from Spec 2
- Required tests: `tests/ai/test_mcp_agent_context.py`,
  `tests/ai/test_mcp_workspace_tools.py`, `tests/ai/test_mcp_execution_tools.py`,
  `tests/api/test_projects.py` (write-helper parity), hook-parity cases

### 7.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded. -> `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (A1)
- [x] Correct prompt template selected. -> work template (non-audit)
- [x] Audit mode recorded when persona is `audit_reviewer`. -> N/A
- [x] Agent branch/worktree assigned (stacked on `feat/2271-webmcp-bridge`,
      `--base-ref` recorded).
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 7.3 Implementation

- [ ] Shared write helper extracted; editor route parity -> `<artifact>`
- [ ] `get_agent_context` -> `<artifact>`
- [ ] Inspect + author tools with hook blacklist and parity results -> `<artifact>`
- [ ] `run_command` + managed job tools -> `<artifact>`
- [ ] Spec 2 + Spec 4 spec text updated -> `<artifact>`
- [ ] Tests -> `<artifact>`

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
- [ ] Rebased onto `main` after PR #2275 merged; PR opened against `main`.
- [ ] Track merged or integrated.

## 8. Track: Spec 3 — Local Startup Modes And Background Runtime

### 8.1 Track Scope

- Owner: `A2 (implementer)`
- In scope: spec `adr-055-local-background-runtime` as amended by #2280
  decisions 1-5
- Out of scope: `runtime-port.js` discovery changes (dropped by owner),
  instance adoption, worker cleanup (#2281), frontend, lab deployment
- Required docs: spec text updated to the decisions
- Required tests: `desktop/test/background-mode.test.js`,
  `desktop/test/bootstrap.test.js` and `tests/scripts/test_ota_publish.py`
  (shell file list parity), `desktop/test/menu.test.js`

### 8.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded. -> `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (A2)
- [x] Correct prompt template selected. -> work template (non-audit)
- [x] Audit mode recorded when persona is `audit_reviewer`. -> N/A
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 8.3 Implementation

- [ ] Mode picker (every launch, "don't ask again", changeable later) -> `<artifact>`
- [ ] Headless mode, tray, connection window, stop/restart -> `<artifact>`
- [ ] Mode-aware `second-instance` and `window-all-closed` -> `<artifact>`
- [ ] OTA inclusion and mode-honoring relaunch -> `<artifact>`
- [ ] Windows backend-lifetime verification (backstop only if needed) -> `<artifact>`
- [ ] Shell file lists (`build.files`, `SHELL_FILES`) in parity -> `<artifact>`
- [ ] Spec 3 spec text updated -> `<artifact>`
- [ ] Tests -> `<artifact>`

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
| Gate ledger check (local) | per-branch `gate_record check` | `[ ]` | `<pending>` |
| Targeted tests | per-track test files (sections 7.1, 8.1) | `[ ]` | `<pending>` |
| Pre-push gate check | n/a — pre-push hook is the allow shim; pre-pr is the hard local gate per ADR-042 Addendum 6 | `[ ]` | `<pending>` |
| Gate ledger check (pre-PR) | `gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | `<pending>` |
| Gate finalize (pre-PR) | `gate_record finalize --closes "#2279"` / `"#2280"` / `"#2282"` | `[ ]` | `<pending>` |
| Wrapper preflight | `python scripts/scistudio_pr_create.py` | `[ ]` | `<pending>` |
| CI | GitHub Actions | `[ ]` | `<pending>` |
| Spec 3 live launch evidence | Windows dev/installed launch by manager; macOS/Linux installed-build runs by owner | `[ ]` | `<pending>` |

## 10. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-09-10 | manager | Owner decisions amend both specs (Spec 2: transfer moved to Spec 4, OS-user read scope, hook blacklist + parity via results, backend-lifetime list_blocks tracking; Spec 3: mode picker every launch, tray, backend stops with Electron) | Recorded in #2279/#2280; each PR updates its own spec text | N/A |
| 2026-09-10 | A1 | Needs `src/scistudio/api/app.py` (outside write set): the production `MCPContext` is `_RuntimeAdapter` inside the lifespan, and `app.state.registry` (the registry `terminate_all` runs on at shutdown) is created there, distinct from `ApiRuntime.process_registry` (LocalRunner's). Verified by manager at `e817f9b82` (`app.py:63/121/207`, `api/runtime/__init__.py:365`) | Manager approved: add `process_registry` and `project_files` members to `_RuntimeAdapter` only, gate-amended first, matching optional `MCPContext` members, no other app.py edits; `run_command` registers in `app.state.registry` | #2281 corrected (comment): workers live in `ApiRuntime.process_registry`, which `terminate_all` does not cover |
| 2026-09-10 | A1 | Needs `tests/ai/test_mcp_fastmcp.py` (outside write set): `test_fastmcp_lists_36_tools` pins the exact `mcp.list_tools()` name set, which includes external-tagged tools, so every new Spec 2 tool breaks it; the socket-transport count in `tests/integration/test_phase2_mcp_end_to_end.py` stays 36 (external tools filtered) | Manager approved: update the expected set only, gate-amended first | N/A |

## 11. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
