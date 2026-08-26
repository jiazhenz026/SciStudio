---
title: "Interactive Panel Quality Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 51
language_source: en
---

# Interactive Panel Quality Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `AI-written interactive blocks are poor quality — a user was locked in a panel with no continue/cancel button; make the runtime unlockable and teach and validate the panel contract.`
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#2195`, `#2196`, `#2197`
- Gate record: `.workflow/records/2195-track-interactive-panel-quality.json`
- Branch/worktree plan: `manager on track/interactive-panel-quality in .worktrees/mgr-interactive-panel; one agent branch + worktree per issue`
- Protected branch: `main`
- Umbrella branch: `track/interactive-panel-quality`
- Umbrella PR: `#2198`
- Umbrella PR title: `[DO NOT MERGE] track: interactive panel quality`
- Final PR target: `main — three independent agent PRs, one per issue (owner-directed)`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

### 1.1 Owner-Directed Deviation: Agent PRs Target `main`

`agent-dispatch.md` §2 defaults dispatched agents to the umbrella branch. The
owner directed three independent PRs instead, one per issue. The three write
sets are disjoint after the sequencing in §2, so there is no integration surface
that needs an umbrella merge, and a PR based on `track/**` would not fire the
issue-closing keywords that each of these PRs must carry.

The manager therefore explicitly assigns each agent its own final PR to `main`,
which `agent-dispatch.md` §4 permits ("MUST NOT target your PR to the protected
branch unless the manager explicitly assigns that final PR"). The umbrella
branch and `[DO NOT MERGE]` umbrella PR are still created, and carry this
checklist, the dispatch prompts, and the manager gate record.

## 2. Scope

- In scope:
  - `frontend/src/App.parts/InteractiveModals.tsx` and
    `frontend/src/App.parts/InteractiveModals.parts/**` — host-owned escape hatch.
  - `src/scistudio/blocks/registry/**`, `src/scistudio/ai/agent/mcp/**`,
    `src/scistudio/workflow/validator.py`,
    `src/scistudio/agent_provisioning/**` — interactive contract validation.
  - `src/scistudio/_skills/**`, `src/scistudio/_agent_reference/block-contract.md`,
    `src/scistudio/cli/templates/**` — panel authoring skill and scaffold.
  - `docs/planning/interactive-panel-quality-*` — manager checklist and prompts.
- Out of scope:
  - The panel host API version and the `PanelModule` contract. No `apiVersion`
    bump in any of the three tracks.
  - Host-owned Continue / decision plumbing (`host.setDecision`). Continue stays
    the panel's responsibility.
  - Error-surface redesign (copy button, failure-code display in the UI).
  - Executing panel modules in a JS runtime. The backend depends on no JS
    runtime and this dispatch does not introduce one.
- Protected paths:
  - `src/scistudio/blocks/**` — A2 edits `src/scistudio/blocks/registry/`.
    Requires `admin-approved:core-change` on PR #2196, verified in CI.
- Deferred work:
  - N/A at dispatch time. Agents record deferrals as `TODO(#NNN)`.

### 2.1 Manager Sequencing: `src/scistudio/ai/agent/mcp/tools_authoring.py`

Both A2 and A3 have a natural claim on this file: `ReloadBlocksResult` (line 83)
and `scaffold_block` (line 319) live in it. Two agents owning one file is a
hard fail, so the manager sequences it:

- **A2 owns `tools_authoring.py` exclusively.** It edits `ReloadBlocksResult`
  and `reload_blocks`.
- **A3 must not open it.** A3 implements the interactive scaffold as a
  self-contained helper plus templates and exposes one entry point, reporting
  its signature.
- **The manager applies the `scaffold_block` wiring** (category value +
  delegation to A3's helper) on A3's branch after #2196 merges, then re-runs
  A3's checks. Recorded in §9 when done.

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

- [x] Dedicated manager branch and worktree created. -> `track/interactive-panel-quality` in `.worktrees/mgr-interactive-panel`
- [x] Existing issue linked, or new issue created only if none exists. -> searched open issues for `interactive` / `panel`; only #2013 and #1849 are adjacent and neither covers this; created #2195, #2196, #2197
- [x] Gate record started. -> `.workflow/records/2195-track-interactive-panel-quality.json`
- [x] Scope include/exclude recorded in the gate record. -> `docs/planning/**`, `.workflow/records/**`
- [x] Umbrella branch created. -> `track/interactive-panel-quality`
- [x] Umbrella PR opened. -> #2198
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist. -> §1
- [x] No `pip install -e .` environment pollution found. -> restated in every dispatch prompt
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template and linked below. -> §6
- [ ] Sentrux baseline recorded, or N/A reason recorded.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `No bypass requested or used. PR #2196 needs admin-approved:core-change for src/scistudio/blocks/registry/, which is a protected-path authorization, not a gate bypass.`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | `pending` |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | `pending` |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | `pending` |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file <body-file>` | `N/A` | `[ ]` | `pending` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `yes`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `A2 adds a provisioned PostToolUse hook, which changes AI-runtime behavior; A2 must record whether the four AI docs above need updates and land the update or an N/A rationale in its own ledger. The manager verifies this at integration.`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `A1` | `implementer` | `N/A` | `docs/planning/interactive-panel-quality-dispatch-prompts/a1-escape-hatch.md` | Host-owned escape hatch + no silent null | `fix/2195-panel-escape-hatch` | `.worktrees/fix-2195-panel-escape-hatch` | `frontend/src/App.parts/InteractiveModals.tsx`, `frontend/src/App.parts/InteractiveModals.parts/**` | all backend, all skills/docs, panel host API version | `#2195` | `[ ]` |
| `A2` | `implementer` | `N/A` | `docs/planning/interactive-panel-quality-dispatch-prompts/a2-contract-validation.md` | Shared contract validation at 3 surfaces | `feat/2196-interactive-contract-validation` | `.worktrees/feat-2196-interactive-validation` | `src/scistudio/blocks/registry/**`, `src/scistudio/ai/agent/mcp/tools_authoring.py`, `src/scistudio/ai/agent/mcp/_reload.py`, `src/scistudio/workflow/validator.py`, `src/scistudio/agent_provisioning/**`, `tests/**` | `frontend/**`, `src/scistudio/_skills/**`, `src/scistudio/_agent_reference/**`, `src/scistudio/cli/templates/**` | `#2196` | `[ ]` |
| `A3` | `implementer` | `N/A` | `docs/planning/interactive-panel-quality-dispatch-prompts/a3-authoring-skill.md` | Panel authoring skill + scaffold template + doc fixes | `docs/2197-panel-authoring-skill` | `.worktrees/docs-2197-panel-authoring-skill` | `src/scistudio/_skills/**`, `src/scistudio/_agent_reference/block-contract.md`, `src/scistudio/cli/templates/**`, new scaffold helper module, `frontend/src/App.parts/InteractiveModals.parts/panelModuleLoader.ts` (comment only), `tests/**` | `src/scistudio/ai/agent/mcp/tools_authoring.py` (§2.1), `src/scistudio/blocks/**`, all other frontend behavior | `#2197` | `[ ]` |

For `test_engineer` rows, the write set should default to tests, fixtures,
validation scripts, e2e scenarios, audit evidence, and explicitly assigned
QA/governance tooling. Production code paths require a recorded scope
amendment.

## 7. Track: A1 — Host-Owned Escape Hatch (#2195)

### 7.1 Track Scope

- Owner: `A1`
- In scope:
  - Host-drawn title bar with block name and a close (X) control on the panel
    modal; X and ESC both drive the existing `onCancel`.
  - Replace the `return null` branch in `InteractiveModals.tsx` (lines 148-154)
    with the visible error surface + Cancel that `DynamicPanel` already renders.
- Out of scope:
  - `PANEL_HOST_API_VERSION`, `PanelHostApi`, `PanelModule` — no contract or
    version change; existing panels must need no edits.
  - Host-owned Continue or `host.setDecision`.
  - Any backend file.
- Required docs:
  - No public contract changes. Record a docs N/A rationale in the ledger unless
    the agent finds a doc that describes the modal's affordances.
- Required tests:
  - `frontend/src/App.parts/InteractiveModals.parts/DynamicPanel.test.tsx` and/or
    a sibling test: ESC and X cancel a mounted exit-less panel; the
    no-`module_url` manifest renders the error surface with a working Cancel;
    core panels and the tutorial panel are unchanged.

### 7.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected.
- [x] Audit mode recorded when persona is `audit_reviewer`. -> N/A, implementer
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 7.3 Implementation

- [ ] Title-bar X + ESC escape hatch -> `<artifact>`
- [ ] `return null` branch replaced with error surface + Cancel -> `<artifact>`
- [ ] Tests -> `<artifact>`
- [ ] Docs updated or N/A recorded -> `<artifact>`

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

## 8. Track: A2 — Interactive Contract Validation (#2196)

### 8.1 Track Scope

- Owner: `A2`
- In scope:
  - One shared validation implementation: manifest/filesystem checks and static
    panel-module source checks, at two severities (hard error vs `Warning:`).
  - Surface 1: registry scan collects rejection reasons; `reload_blocks` returns
    them instead of dropping blocks silently.
  - Surface 2: the same checks reach `scistudio.workflow.validator`, so
    `validate_workflow`, `write_workflow` verification, and run start refuse a
    hard-invalid interactive block.
  - Surface 3: a provisioned PostToolUse hook whose matcher covers panel
    `.js`/`.mjs`, not only `blocks/*.py`.
- Out of scope:
  - Executing the panel module. No JS runtime dependency.
  - A `scistudio` CLI entry point (the embedded agent is denied the CLI).
  - Frontend, skills, agent-reference docs, scaffold templates.
- Required docs:
  - `docs/package-development/blocks.md` if the validation changes what a package
    author must satisfy; the four AI docs in §5.1 if the new hook changes
    AI-runtime behavior; otherwise explicit N/A rationales.
- Required tests:
  - Per-check tests at both severities; one test per surface (`reload_blocks`
    rejection reporting, workflow-validator diagnostics, hook matcher).

### 8.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected.
- [x] Audit mode recorded when persona is `audit_reviewer`. -> N/A, implementer
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 8.3 Implementation

- [ ] Shared validation implementation -> `<artifact>`
- [ ] Surface 1: `reload_blocks` rejection reporting -> `<artifact>`
- [ ] Surface 2: workflow validator diagnostics -> `<artifact>`
- [ ] Surface 3: PostToolUse hook covering panel JS -> `<artifact>`
- [ ] Tests -> `<artifact>`
- [ ] Docs updated or N/A recorded -> `<artifact>`
- [ ] `admin-approved:core-change` requested on the PR -> `<artifact>`

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

## 9. Track: A3 — Panel Authoring Skill And Scaffold (#2197)

### 9.1 Track Scope

- Owner: `A3`
- In scope:
  - A dedicated interactive-panel authoring skill under
    `src/scistudio/_skills/scistudio/`, routed from `scistudio-write-block`.
  - An interactive scaffold: block `.py` with a correctly filled `PanelManifest`
    plus a panel module skeleton with default export, `apiVersion`, `mount`
    returning `{ unmount }`, and wired confirm and cancel controls.
  - Documentation fixes in `block-contract.md` (default export; exact
    `module_url` shape and filename) and the stale route comment in
    `panelModuleLoader.ts` line 8 (comment text only).
- Out of scope:
  - `src/scistudio/ai/agent/mcp/tools_authoring.py` — see §2.1. Expose a helper;
    the manager wires it.
  - Any frontend behavior change. The loader edit is a comment.
  - The validation implementation itself (A2 owns it); route to it only.
- Required docs:
  - `src/scistudio/_agent_reference/block-contract.md`, the new skill file, and
    `docs/package-development/blocks.md` if the panel contract text lives there
    too.
- Required tests:
  - Scaffold output shape: the generated block registers and the generated panel
    module satisfies the contract checks.

### 9.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected.
- [x] Audit mode recorded when persona is `audit_reviewer`. -> N/A, implementer
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 9.3 Implementation

- [ ] Panel authoring skill -> `<artifact>`
- [ ] Interactive scaffold helper + templates -> `<artifact>`
- [ ] `block-contract.md` default-export and `module_url` fixes -> `<artifact>`
- [ ] `panelModuleLoader.ts` route comment fix -> `<artifact>`
- [ ] Tests -> `<artifact>`
- [ ] Manager wires `scaffold_block` after #2196 merges (§2.1) -> `<artifact>`

### 9.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 9.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 10. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | `pending` |
| Targeted tests | `per-track, recorded with gate_record amend --test-path` | `[ ]` | `pending` |
| Pre-push gate check | `python -m scistudio.qa.governance.gate_record check --mode pre-push --base origin/main --head HEAD` | `[ ]` | `pending` |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | `pending` |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#<issue>"` | `[ ]` | `pending` |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run --title "<title>" --body "<body>"` | `[ ]` | `pending` |
| Frontend smoke (A1) | `manager-run desktop smoke on a paused interactive block` | `[ ]` | `pending` |

## 11. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| `2026-08-26` | `manager` | `agent-dispatch.md §2 defaults agent PRs to the umbrella branch; owner directed three independent PRs to main.` | `Manager explicitly assigns each agent its own final PR to main per §4 of the same rules; umbrella branch and [DO NOT MERGE] PR still created for visibility and to carry this checklist.` | `Recorded in §1.1` |
| `2026-08-26` | `manager` | `A2 and A3 both have a claim on src/scistudio/ai/agent/mcp/tools_authoring.py.` | `Sequenced: A2 owns the file; A3 exposes a helper and the manager wires scaffold_block after #2196 merges.` | `Recorded in §2.1; row in §9.3` |

## 12. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
