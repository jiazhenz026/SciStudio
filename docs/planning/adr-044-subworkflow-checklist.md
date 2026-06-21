---
title: "ADR-044 SubWorkflow Implementation Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 44
language_source: en
---

# ADR-044 SubWorkflow Implementation Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Full ADR-044 refactor/implementation (SubWorkflowBlock authoring-only + inline flattening at run start), then one no-context auditor (ADR/spec/diff only), fix P1–P3, complete integration tests, Chrome e2e on owner browser, and a READY FOR REVIEW summary PR.
- Task kind: `feature`
- Manager persona: `manager`
- Issue: `#890` (reopened as the implementation tracking issue; ADR-044 §1/§8/FR-013, spec SC-004)
- Gate record: `.workflow/records/890-adr-044-subworkflow.json`
- Branch/worktree plan: manager on umbrella branch/worktree; one backend implementer worktree, one frontend implementer worktree, one no-context audit worktree.
- Protected branch: `main`
- Umbrella branch: `track/adr-044-subworkflow-20260621`
- Umbrella PR: `#1736`
- Umbrella PR title: `[DO NOT MERGE] ADR-044 SubWorkflowBlock authoring-only + inline flattening`
- Final PR target: `main` (READY FOR REVIEW summary PR, closes #890)
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - `src/scistudio/blocks/subworkflow/**` — rewrite stub to authoring-only shell; add SubWorkflowBroken placeholder.
  - `src/scistudio/workflow/**` — `flatten_subworkflows` + cycle detection, `exposed_ports` schema, serializer round-trip, validator broken-ref + exposed_ports checks.
  - `src/scistudio/api/runtime/**` — flatten at `start_workflow` only (not `load_workflow`); flattened-YAML lineage snapshot; external-file import (FR-011); effective-ports surface for editor.
  - `src/scistudio/blocks/registry/**` — register SubWorkflowBroken; keep SubWorkflowBlock categorization.
  - `src/scistudio/core/lineage/**` — confirm flattened snapshot reaches `workflow_yaml_snapshot` (no schema change per A-002).
  - `frontend/src/components/nodes/**` — SubWorkflowNode, broken placeholder, dynamic ports, double-click tab open; route from BlockNode.
  - `tests/**` — unit + integration suites for FR-001..FR-013 / SC-001..SC-007.
  - `docs/architecture/ARCHITECTURE.md` §5.4.7 — authoring-only model.
  - `docs/planning/**`, `docs/audit/**` — this checklist + audit report.
- Out of scope:
  - `src/scistudio/engine/scheduler/**`, `src/scistudio/engine/runners/**` (ADR-044 frontmatter `excludes`). No engine-side stub injection exists today, so no edits are required here. Two stale docstrings in `engine/runners/platform.py` are flagged for the auditor, not edited.
  - Reproducibility freeze/version pinning; cross-project catalog; template params; UI streaming of inner-block state (ADR §2.2).
- Protected paths:
  - `src/scistudio/workflow/**`, `src/scistudio/api/runtime/**`, `src/scistudio/core/lineage/**` may be protected-core; PR will require owner-authorized `admin-approved:core-change` (CI-verified).
- Deferred work:
  - `engine/runners/platform.py` stale "nested SubWorkflowBlock subprocess cleanup" docstrings (ADR-excluded path) — flag in audit; fix only with owner-approved scope amendment.

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

- [x] Dedicated manager branch and worktree created. → `track/adr-044-subworkflow-20260621` @ `/Users/jiazhenz/SciStudio-adr044-umbrella-20260621`
- [x] Existing issue linked. → `#890` reopened as implementation tracking issue
- [x] Gate record started. → `.workflow/records/890-adr-044-subworkflow.json`
- [x] Scope include/exclude recorded in the gate record. → init include globs
- [x] Umbrella branch created. → `track/adr-044-subworkflow-20260621`
- [x] Umbrella PR opened. → `#1736`
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch (`main`) and umbrella PR number (`#1736`) recorded in this checklist.
- [x] No `pip install -e .` environment pollution found. → use `PYTHONPATH=$PWD/src`
- [x] Dispatch checklist copied from the template and committed.
- [ ] Dispatch prompts created from the correct prompt template and linked below.
- [x] Sentrux baseline recorded, or N/A reason recorded. → Sentrux MCP unavailable this session; CLI fallback `sentrux scan/check` recorded as guard event via `gate_record check`.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `admin-approved:core-change` (pending owner authorization for protected-core paths)
- Owner authorization source: `owner-directed session 2026-06-21 (to confirm at PR time)`
- Reason: `change touches protected-core workflow/runtime/lineage paths`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-PR reconcile | `gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `admin-approved:core-change` | `[ ]` | pending |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no` (runtime feature only)
- AI docs checked: N/A — no `docs/ai-developer/**` change.
- Updated docs or N/A rationale: `docs/architecture/ARCHITECTURE.md` §5.4.7 updated; AI-developer docs N/A.

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `BE` (manager-self) | `implementer` | `N/A` | `docs/planning/adr-044-dispatch/backend.md` | Backend core + backend tests + ARCHITECTURE.md (implemented directly by manager on umbrella; coupled code) | `track/adr-044-subworkflow-20260621` | `/Users/jiazhenz/SciStudio-adr044-umbrella-20260621` | `src/scistudio/**`, `tests/**`, `docs/architecture/ARCHITECTURE.md` | `frontend/**`, `engine/scheduler/**`, `engine/runners/**` | `#890` | `[~]` |
| `FE` | `implementer` | `N/A` | `docs/planning/adr-044-dispatch/frontend.md` | Frontend SubWorkflowNode + routing + tests | `feature/adr-044-frontend-20260621` | `/Users/jiazhenz/SciStudio-adr044-frontend-20260621` | `frontend/**` | `src/**`, `tests/**` | `#890` | `[ ]` |
| `AUD` | `audit_reviewer` | `no-context` | `docs/planning/adr-044-dispatch/audit-no-context.md` | No-context audit (ADR/spec/diff only) | `audit/adr-044-no-context-20260621` | `/Users/jiazhenz/SciStudio-adr044-audit-20260621` | `docs/audit/2026-06-21-adr-044-subworkflow-no-context.md` | all implementation files | `#890` | `[ ]` |

## 6.1 Design Decisions (manager, from investigation synthesis)

- **D1 ref key:** nested `config.ref.path`, stored project-relative, resolved vs project root at flatten + port derivation. No serializer path-machinery change.
- **D2 port project_dir:** editor-side effective ports resolved at the API route (active project root) via shared helper; `SubWorkflowBlock.get_effective_*_ports` reads ref+project_dir from config (validator injects project_dir for save-time dangling-edge checks), returns `[]` if unresolved.
- **D3 flatten host:** free function `workflow/flatten.py` + thin `WorkflowDefinition.flatten_subworkflows(self, base_dir)` forwarding shim (ADR-literal compliance).
- **D4 FR-004 delivery:** `GET /api/workflows/{id}` enriches subworkflow nodes with response-only `resolved_ports` (computed server-side; never persisted). Frontend renders handles from it.
- **D5 broken node:** distinct registered `subworkflow_broken` block_type; one frontend component with a `broken` flag.
- **D6 test infra:** run tests with `PYTHONPATH=$PWD/src`; only add `pyproject` pytest `pythonpath` if collection truly fails (report first).
- **D7 engine exclude:** honor ADR `excludes`; FR-012 engine deletion satisfied-by-absence (no injection sites exist) — gate scope note; leave `platform.py` docstrings; no scheduler assertion.
- **D8 exposed_ports.internal separator:** DOT (`block_id.port`) on disk; flattener converts to COLON for `EdgeDef`; `EdgeModel` never validates the DOT form.

## 7. Track A: Backend Core

### 7.1 Track Scope

- Owner: `BE` implementer
- In scope: flatten + cycle detection, exposed_ports schema/serializer, validator, runtime wiring (flatten at start_workflow only), flattened lineage snapshot, stub rewrite, SubWorkflowBroken, registry, backend tests, ARCHITECTURE.md §5.4.7.
- Out of scope: frontend, engine/scheduler, engine/runners.
- Required docs: `docs/architecture/ARCHITECTURE.md` §5.4.7.
- Required tests: `tests/workflow/test_flatten_subworkflows.py`, `tests/blocks/test_subworkflow.py` (rewrite), `tests/workflow/test_subworkflow_validator.py`, `tests/integration/test_subworkflow_lineage.py`, `tests/api/test_runtime_subworkflow_flatten.py`.

### 7.2 Dispatch
- [ ] Prompt file created.
- [ ] Agent branch/worktree assigned.
- [ ] Write set + out-of-scope in prompt.
- [ ] TODO rule + required checks in prompt.

### 7.3 Implementation
- [ ] FR-001 `flatten_subworkflows` + cycle detection (SC-003) -> artifact
- [ ] FR-002 `load_workflow` returns authored graph (no flatten) -> artifact
- [ ] FR-003 flatten at `start_workflow`; flattened snapshot (SC-001, SC-002) -> artifact
- [ ] FR-004 dynamic effective ports from exposed_ports -> artifact
- [ ] FR-005/006 id prefix + edge rewrite (nodes/colon refs) -> artifact
- [ ] FR-007 CyclicSubworkflowError canonical-path DFS -> artifact
- [ ] FR-008/009 no-exposed_ports + standalone run -> artifact
- [ ] FR-010 SubWorkflowBroken placeholder + validator reject at run start -> artifact
- [ ] FR-011 external-file import to `<project>/subworkflows/` -> artifact
- [ ] FR-012 stub deletion (SC-005) -> artifact
- [ ] Backend tests -> artifact

### 7.4 Audit
- See Track C.

### 7.5 Integration
- [ ] Manager reviewed BE output.
- [ ] Scope compliance verified.
- [ ] Merged into umbrella.

## 8. Track B: Frontend

### 8.1 Track Scope
- Owner: `FE` implementer
- In scope: `SubWorkflowNode.tsx` (dynamic port handles FR-004, broken placeholder FR-010, double-click tab open US1.3), BlockNode routing, frontend tests.
- Out of scope: backend, python tests.
- Required docs: N/A (component-level; ARCHITECTURE owned by BE).
- Required tests: `frontend/src/components/nodes/__tests__/SubWorkflowNode.test.tsx`.

### 8.2 Dispatch
- [ ] Prompt file created.
- [ ] Agent branch/worktree assigned.
- [ ] Write set + out-of-scope in prompt.

### 8.3 Implementation
- [ ] SubWorkflowNode dynamic ports (SC-007) -> artifact
- [ ] Broken-ref placeholder render (FR-010) -> artifact
- [ ] Double-click opens referenced file tab (US1.3) -> artifact
- [ ] BlockNode routes subworkflow / SubWorkflowBroken types -> artifact
- [ ] Frontend tests -> artifact

### 8.5 Integration
- [ ] Manager reviewed FE output.
- [ ] Merged into umbrella.

## 9. Track C: No-Context Audit + Fixes

### 9.4 Audit
- [ ] Audit agent assigned (no-context, ADR/spec/diff only).
- [ ] Audit report path assigned: `docs/audit/2026-06-21-adr-044-subworkflow-no-context.md`.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

## 10. Track D: Chrome E2E (manager, owner browser)
- [ ] Dev backend + desktop started.
- [ ] SubWorkflowBlock dropped, ref set, exposed ports render (SC-007).
- [ ] Double-click opens referenced file tab.
- [ ] Broken-ref placeholder shown on missing file.
- [ ] Run flattened workflow; lineage snapshot inspected.
- [ ] Evidence (screenshots/gif) saved under `docs/audit/`.

## 11. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | pending |
| Targeted tests | recorded via `gate_record amend --test-path` | `[ ]` | pending |
| Gate ledger check (pre-PR) | `gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | pending |
| Gate finalize (pre-PR) | `gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#890"` | `[ ]` | pending |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run` | `[ ]` | pending |

## 12. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-06-21 | manager | ADR/spec say `blocks`/dot-port-refs/`api/runtime.py`; code uses `nodes`/colon-refs/`api/runtime/` package | Implement to ADR intent using real representation; document mapping in PR + ARCHITECTURE | N/A |

## 13. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux evidence, commit, and PR evidence.
- [ ] PR closes #890.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
