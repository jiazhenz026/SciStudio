---
title: "ADR-054 Panel Contract Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 48
  - 51
  - 54
language_source: en
---

# ADR-054 Panel Contract Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `Own the whole implementation of ADR-054 spec 1 (the panel
  contract), dispatch agents including a no-context audit and an adversarial
  no-context test engineer that proves previewer behaviour survives the
  migration, and deliver one PR.`
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#2229`
- Gate record: `.workflow/records/2229-track-adr-054-spec1-panel-contract.json`
- Branch/worktree plan: manager on `track/adr-054-spec1-panel-contract` in
  `.worktrees/mgr-2229-panel-contract`; every dispatched agent branches from the
  track branch into its own worktree and pushes its branch for manager
  integration.
- Protected branch: `main`
- Umbrella branch: `track/adr-054-spec1-panel-contract`
- Umbrella PR: `#2230`
- Umbrella PR title: `[DO NOT MERGE] ADR-054 spec 1: the unified panel contract`
- Final PR target: `main`
- Governing spec: `docs/specs/adr-054-panel-contract.md`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope: everything in the spec's `scope.in` and `governs.files`, delivered
  through its section 4.3 sequence T-001 to T-016.
  - `src/scistudio/core/panels.py`, `src/scistudio/panels/**`
    (renamed from `src/scistudio/previewers/**`)
  - `src/scistudio/api/routes/panels.py`, `routes/data.py`, `routes/blocks.py`,
    `api/schemas.py`
  - `src/scistudio/blocks/base/interactive.py`, `src/scistudio/core/dropins.py`,
    `src/scistudio/core/entry_points.py`
  - `frontend/src/panels/**` and the previewer/panel surfaces it replaces
  - `tests/panels/**` (renamed from `tests/previewers/**`), the panel tests
    under `tests/api/**`, `tests/architecture/test_layer_deps.py`,
    `tests/adr052_contract/**`
  - `docs/adr/ADR-048-addendum*.md`, `docs/adr/ADR-051-addendum2.md`
  - `docs/planning/adr-054-panel-contract-checklist.md`, `docs/audit/**`
- Out of scope (spec `scope.out` and `governs.excludes`):
  - The explore session, the kernel, the notebook, the dependency analysis.
  - `src/scistudio/_skills/**`, `src/scistudio/_agent_reference/**`.
  - `docs/architecture/**`, `docs/package-development/**`, `docs/user/**`
    (human documentation revision is `#2211`).
  - `src/scistudio/plot/runtime.py`; plot rendering, the preview cache, plot
    artifact registration.
  - Giving a plot panel the producing capability (`#2212`).
- Protected paths: `docs/architecture/ARCHITECTURE.md` is owner-controlled and
  is not edited by this dispatch. `#2059` and `#2211` own the architecture and
  user-documentation follow-through.
- Deferred work:
  - `TODO(#2212)` the plot panel's producing capability.
  - `TODO(#2211)` human documentation revision for the panel vocabulary.

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
      -> `track/adr-054-spec1-panel-contract`,
      `.worktrees/mgr-2229-panel-contract`
- [x] Existing issue linked, or new issue created only if none exists.
      -> `#2213` is the closed spec-authoring issue and `#2209` tracks the ADR
      as a whole and states each stage lands against its own issue, so `#2229`
      was created for this stage.
- [x] Gate record started.
      -> `.workflow/records/2229-track-adr-054-spec1-panel-contract.json`
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created.
- [x] Umbrella PR opened. -> `#2230`
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found.
      -> no agent is permitted to run it; every prompt restates the prohibition.
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template and linked
      below.
- [ ] Sentrux baseline recorded, or N/A reason recorded.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `No bypass was requested or used.`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | `no commit hook installed since #2150` |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | `subject check runs at pre-pr/ci since #2150` |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | `installed hook is a fast allow shim` |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `N/A` | `[ ]` | `pending` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `N/A - this dispatch changes the panel
  subsystem, not the gate CLI, the PR wrapper, the hooks, CI, or any AI runtime
  behaviour, so no AI developer workflow doc changes are required.`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `W1-rename` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w1-rename` | T-001 and FR-051 | `refactor/2229-panel-rename` | `.worktrees/w1-panel-rename` | the whole tree, mechanical rename only | any behaviour change | `#2229` | `[x]` |
| `W2-core` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w2-core` | T-002, T-003, T-013, T-015, T-016 | `feat/2229-panel-core-contract` | `.worktrees/w2-panel-core` | `src/scistudio/core/panels.py`, `src/scistudio/panels/**`, `src/scistudio/core/dropins.py`, `src/scistudio/core/entry_points.py`, `src/scistudio/blocks/base/interactive.py`, `tests/panels/**`, `tests/architecture/**`, `tests/adr052_contract/**` | frontend, API routes | `#2229` | `[ ]` |
| `W2-host` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w2-host` | T-005, T-006 | `feat/2229-panel-frame-host` | `.worktrees/w2-panel-host` | `frontend/src/panels/**` | backend, the existing previewer frontend | `#2229` | `[ ]` |
| `W3-api` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w3-api` | T-004, T-008 backend half, T-010 | `feat/2229-panel-api` | `.worktrees/w3-panel-api` | `src/scistudio/api/routes/panels.py`, `routes/data.py`, `routes/blocks.py`, `api/schemas.py`, `tests/api/**` | frontend, panel discovery internals | `#2229` | `[ ]` |
| `W3-fe` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w3-fe` | T-007, T-008 frontend half, T-011 | `feat/2229-panel-frontend` | `.worktrees/w3-panel-frontend` | the panel surfaces under `frontend/src/**` | backend | `#2229` | `[ ]` |
| `W4-builtin` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w4-builtin` | T-009 | `feat/2229-builtin-panels` | `.worktrees/w4-builtin-panels` | the built-in panel directories and their tests | the Python providers, the host | `#2229` | `[ ]` |
| `W4-compat` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w4-compat` | T-012, T-014 | `feat/2229-panel-compat-shim` | `.worktrees/w4-panel-compat` | the shim module, `docs/adr/ADR-048-addendum*.md`, `docs/adr/ADR-051-addendum2.md`, the shim tests | everything else | `#2229` | `[ ]` |
| `W5-test` | `test_engineer` | `N/A` | `adr-054-panel-contract-prompts.md#w5-test` | adversarial migration-regression suite | `test/2229-panel-migration-regression` | `.worktrees/w5-panel-tests` | tests, fixtures, e2e evidence only | all production code | `#2229` | `[ ]` |
| `W5-audit-nc` | `audit_reviewer` | `no-context` | `adr-054-panel-contract-prompts.md#w5-audit-nc` | independent conformance audit | `audit/2229-panel-no-context` | `.worktrees/w5-audit-no-context` | `docs/audit/2026-09-02-panel-contract-no-context.md` | all implementation files | `#2229` | `[ ]` |
| `W5-audit-wc` | `audit_reviewer` | `with-context` | `adr-054-panel-contract-prompts.md#w5-audit-wc` | spec conformance audit | `audit/2229-panel-with-context` | `.worktrees/w5-audit-with-context` | `docs/audit/2026-09-02-panel-contract-with-context.md` | all implementation files | `#2229` | `[ ]` |

For `test_engineer` rows, the write set should default to tests, fixtures,
validation scripts, e2e scenarios, audit evidence, and explicitly assigned
QA/governance tooling. Production code paths require a recorded scope
amendment.

## 7. Track: The Panel Contract

### 7.1 Track Scope

- Owner: `manager`
- In scope: the sixteen tasks of `docs/specs/adr-054-panel-contract.md`
  section 4.3.
- Out of scope: everything listed in section 2 above.
- Required docs:
  - `docs/adr/ADR-048-addendum*.md` (the contract change, the governance
    transfer, and the shim's removal condition, FR-044)
  - `docs/adr/ADR-051-addendum2.md` (the panel-side half of the same change)
  - this checklist
  - the audit reports under `docs/audit/`
- Required tests: the spec's `tests:` list, in particular
  `tests/panels/test_panel_contract.py`,
  `tests/panels/test_panel_capability_gate.py`,
  `tests/panels/test_panel_tiers.py`,
  `tests/panels/test_panel_editing.py`,
  `tests/panels/test_panel_asset_route.py`,
  `tests/panels/test_builtin_panels.py`,
  `tests/panels/test_compat_shim.py`,
  `tests/panels/test_panel_registration.py`,
  `tests/panels/test_panel_resolution.py`.

### 7.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [ ] Correct prompt template selected.
- [ ] Audit mode recorded when persona is `audit_reviewer`.
- [ ] Agent branch/worktree assigned.
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt.
- [ ] Required checks included in prompt.

### 7.3 Implementation

| Task | Title | Agent | Status | Artifact |
|---|---|---|---|---|
| T-001 | Rename the subsystem and its vocabulary | `W1-rename` | `[x]` | branch `refactor/2229-panel-rename`; gate ledger `.workflow/records/2229-refactor-2229-panel-rename.json`; `pytest tests/panels tests/api/test_panels.py tests/api/test_panel_discovery.py tests/api/test_panel_choice_routes.py tests/api/test_interactive_panels.py tests/architecture tests/adr052_contract tests/blocks` 2312 tests, 40 pre-existing `openpyxl` env failures (baseline 2304/41); `npm test` 1884 tests; `lint-imports` 13 kept 0 broken |
| T-002 | Move the contract into the core layer | `W2-core` | `[ ]` | |
| T-003 | The on-disk panel form and four-tier discovery | `W2-core` | `[ ]` | |
| T-004 | Merge the asset route | `W3-api` | `[ ]` | |
| T-005 | The frame host and the message contract | `W2-host` | `[ ]` | |
| T-006 | The capability gate in the host | `W2-host` | `[ ]` | |
| T-007 | One loader; delete the retired modules | `W3-fe` | `[ ]` | |
| T-008 | The backend names the fallback; delete the dispatch | `W3-api`, `W3-fe` | `[ ]` | |
| T-009 | Rewrite the eleven built-in panels | `W4-builtin` | `[ ]` | |
| T-010 | Read, write, copy-on-write, revert | `W3-api` | `[ ]` | |
| T-011 | Hot reload and the optional state hook | `W3-fe` | `[ ]` | |
| T-012 | The compatibility shim | `W4-compat` | `[ ]` | |
| T-013 | Layer enumeration and frozen symbol inventory | `W2-core` | `[ ]` | |
| T-014 | The ADR-048 and ADR-051 addenda | `W4-compat` | `[ ]` | |
| T-015 | Entry-point group, directory registration, provider | `W2-core` | `[ ]` | |
| T-016 | Capability-aware resolution and the user choice | `W2-core` | `[ ]` | |

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

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Baseline before the migration | `pytest tests/previewers tests/api/test_previewers.py tests/api/test_previewer_discovery.py tests/api/test_interactive_panels.py tests/architecture tests/adr052_contract -q --no-cov -p no:randomly` | `[x]` | exit 0 on `cae11210c`, the track branch's base |
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | |
| Targeted tests | `pytest tests/panels tests/api tests/architecture tests/adr052_contract` and `npm test` in `frontend/` | `[ ]` | |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2229"` | `[ ]` | |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run --title "<title>" --body "<body>"` | `[ ]` | |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| `2026-09-02` | `manager` | none yet | dispatch opened | `N/A` |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
