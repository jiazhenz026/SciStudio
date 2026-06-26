---
title: "ADR-051 Interactive Blocks Implementation Checklist"
status: In Progress
owners:
  - "@jiazhenz026"
related_adrs:
  - 17
  - 18
  - 19
  - 27
  - 29
  - 38
  - 48
  - 51
related_specs:
  - adr-051-interactive-blocks
language_source: en
---

# ADR-051 Interactive Blocks Implementation Checklist

> Mandatory tracking file. The manager leads implementation; dispatched agents
> (no-context audit, test engineer) edit only the rows they own.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Lead the full implementation of ADR-051 (interactive
  data-processing blocks) on latest `origin/main`, then dispatch 1 no-context
  audit agent and fix all P1-P3, then 1 test engineer for system/e2e smoke.
  Deliver as ONE ready-for-review PR closing #1781.
- Task kind: `feature` (Tier 1, strict; touches protected core/runtime/engine)
- Manager persona: `manager` (also leads implementation per owner directive)
- Issue: `#1781`
- ADR: `docs/adr/ADR-051.md`
- Spec: `docs/specs/adr-051-interactive-blocks.md`
- Gate record: `.workflow/records/1781-feat-1781-adr-051-interactive-blocks.json`
- Branch/worktree: `feat/1781-adr-051-interactive-blocks` in
  `C:/Users/jiazh/Desktop/workspace/sci-wt/adr-051-interactive` (off `origin/main`
  @ 8154e12f).
- Protected branch: `main`
- Final PR target: `main`
- Single-PR delivery: per explicit owner directive ("所有成果统一交付1个PR"), the
  umbrella `[DO NOT MERGE]` PR ceremony is intentionally collapsed into one
  feature branch that is both the integration branch and the final PR branch.
  Rationale recorded in Drift Log row 1. The no-context audit is read-only
  (report committed under `docs/audit/`); the test engineer adds tests onto the
  same branch; implementation is manager-led on the same branch — so there is no
  parallel multi-writer integration that the umbrella PR exists to protect.
- Required label at PR time: `admin-approved:core-change` (touches protected
  core: `engine/scheduler`, `engine/runners`, `blocks/base`). Owner must apply;
  CI verifies actor provenance. Flagged to owner at delivery.

## 2. Scope

- In scope (declared in gate ledger):
  - `src/scistudio/blocks/base/interactive.py` (create)
  - `src/scistudio/blocks/base/state.py`, `block.py`
  - `src/scistudio/blocks/registry/**`
  - `src/scistudio/engine/scheduler/_dispatch.py`, `_events.py`, `_lineage.py`,
    `__init__.py`
  - `src/scistudio/engine/runners/worker.py`, `local.py`, `process_handle.py`
  - `src/scistudio/engine/events.py`
  - `src/scistudio/api/ws.py`
  - `src/scistudio/blocks/process/builtins/data_router.py`, `pair_editor.py`
  - `frontend/src/**` (InteractiveModals, DataRouterModal, PairEditorModal, panel host)
  - `docs/architecture/ARCHITECTURE.md`, `docs/block-development/**`
  - `docs/specs/adr-051-interactive-blocks.md` (status only),
    `docs/planning/adr-051-interactive-blocks-checklist.md`
  - `docs/audit/**` (audit report), `tests/blocks/**`, `tests/engine/**`
- Out of scope (per ADR §6 / spec scope.out):
  - Any domain package interactive block (e.g. LCMS blank-subtraction).
  - A live re-computation loop / backend reads while window open.
  - A generic runtime-rendered declarative widget schema.
  - The subprocess->engine RUNNING/PAUSED/progress status channel (#56).
  - The re-run policy for a recorded decision.
  - Any change to the read-only previewer subsystem beyond reusing its injection.
- Protected paths:
  - `docs/ai-developer/**` excluded; not edited (governance_touch=false).
- Deferred work:
  - Any discovered deferral must be tracked with `TODO(#1781)` or a follow-up
    issue before merge.

## 3. Conventions

- `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked
- Every completed row MUST cite an artifact: commit, test command, report path,
  or gate-record entry. Chat messages are not evidence.
- Scope changes require a gate-record amendment before work continues.

## 4. Manager Preflight

- [x] Dedicated manager branch and worktree created. -> `feat/1781-adr-051-interactive-blocks`, `sci-wt/adr-051-interactive`
- [x] Existing issue linked. -> `#1781` (ADR-051 tracking issue; still open)
- [x] Gate record started. -> `.workflow/records/1781-feat-1781-adr-051-interactive-blocks.json`
- [x] Scope include/exclude recorded in the gate record. -> gate `init` + `plan`
- [x] Plan recorded (Tier 1 requires plan before implementation). -> gate `plan`
- [N/A] Umbrella PR / `[DO NOT MERGE]` title. -> collapsed to single PR per owner directive (Drift Log row 1)
- [x] No `pip install -e .` pollution. -> use `.venv` + `PYTHONPATH=src`, never `-e .`
- [x] Dispatch checklist created and committed. -> this file
- [ ] Sentrux baseline recorded, or N/A reason recorded. -> recorded as guard event inside `gate_record check`

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: N/A (no bypass authorized or used)
- Owner authorization source: N/A
- Reason: N/A — normal gate validation used throughout.

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-PR reconcile | `gate_record check --mode pre-pr --base origin/main --head HEAD --pr-body-file .workflow/local/pr-body.md` | N/A | `[ ]` | pending |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: no (runtime
  block-execution behavior changes, but NOT the AI gate tooling).
- AI docs (`docs/ai-developer/**`) in scope: no. governance_touch=false.
- Product docs updated: `docs/architecture/ARCHITECTURE.md`,
  `docs/block-development/{block-contract,architecture-for-block-devs,quickstart}.md`
  (required by spec §4.2). Tracked in Track: Implementation T-009.

## 6. Dispatch Matrix

Implementation is manager-led (single coherent author on a tightly-coupled
runtime change). Only the two owner-mandated roles are dispatched.

| Agent | Persona | Audit mode | Task | Branch/worktree | Write set | Out of scope | Status |
|---|---|---|---|---|---|---|---|
| AUDIT-NC | audit_reviewer | no-context | Independent audit of the integrated ADR-051 implementation vs repository docs/spec/code/tests; classify P1-P3 | read-only worktree off the feature branch HEAD | `docs/audit/<date>-adr-051-no-context.md` only | all production code (read-only) | `[ ]` |
| TEST-ENGINEER | test_engineer | N/A | Design + implement system-level / e2e smoke for ADR-051 (pause→decide→compute, migration parity, cancellation, registry validation) | feature branch (additive) | `tests/**` system/e2e + fixtures | production code unless manager amends | `[ ]` |

## 7. Integration Contract (pinned)

Pinned from the Understand exploration map. Every task adheres to this.

- **Capability binding**: a block is interactive iff `execution_mode ==
  ExecutionMode.INTERACTIVE` (already exists, `state.py:25`) AND it inherits
  `InteractiveMixin`. No new enum value. Registry rejects the XOR at scan time.
- **Contract module** `blocks/base/interactive.py`: `PanelManifest` (mirrors
  ADR-048 `FrontendManifest`: `panel_id, module_url, export_name, css, version,
  api_version, response_schema?, asset_root`; `to_dict` omits `asset_root`),
  `InteractivePrompt(panel_payload: dict, intermediate: tuple[StorageReference,...])`,
  `InteractiveMixin` (ClassVar `interactive_panel`, `prepare_prompt`),
  `SupportsInteraction` Protocol, `PANEL_API_VERSION = "1"`.
- **Worker phase marker**: `build_worker_payload(..., phase="compute")` adds
  `"phase"` to stdin payload only when != "compute". `worker.main()` branches:
  `phase=="prompt"` → run `block.prepare_prompt`, emit
  `{wire_version, phase:"prompt", panel_payload, intermediate:[ref_dicts], environment}`;
  else → existing `block.run` path (single-phase AUTO path byte-unchanged).
- **Runner**: `LocalRunner.run_prompt(block, inputs, config)` spawns the prompt
  worker and returns `{panel_payload, intermediate, environment}`. Compute phase
  reuses the existing `LocalRunner.run` (block.run already reads
  `config["interactive_response"]`).
- **Two-phase scheduler** (surgical edit of `_run_interactive`): PAUSED →
  `run_prompt` (subprocess) → emit INTERACTIVE_PROMPT → await future → RUNNING →
  `run` (subprocess) with `interactive_response` + `interactive_intermediate` in
  config → finalize. Engine holds intermediate refs in
  `self._interactive_intermediate[node_id]`; released in `finally` (success AND
  cancel).
- **Prompt event payload** (FR-007/FR-015): INTERACTIVE_PROMPT `data =
  {workflow_id, block_type, panel_manifest: {...}, panel_payload: {...}}`.
  `panel_payload` is NESTED (not spread) — fixes the clobber footgun. Wire
  transport (`serialise_event`, `_OUTBOUND_EVENTS`) unchanged.
- **Response routing**: unchanged — `{type:"interactive_complete", block_id,
  data:{...}}` → `_on_interactive_complete` resolves the future → merged into
  compute config as `interactive_response`.
- **Lineage** (FR-011): compute config (with `interactive_response`) is passed to
  `_build_block_done_data`, which records it as `block_config_resolved`
  (ADR-038) and EXCLUDES `interactive_intermediate`. Fixes the existing bug where
  the decision was dropped from lineage.
- **Frontend panel resolution** (FR-007/SC-006): `InteractiveModals` resolves the
  panel from `panel_manifest.panel_id` against a built-in `PANEL_REGISTRY`
  (core path) with the ADR-048 dynamic-import path available for package panels.
  No `blockType === "DataRouter"` string branching remains.
- **Core panel manifests**: DataRouter → `core.interactive.data_router`,
  PairEditor → `core.interactive.pair_editor`.

## 8. Implementation Tasks (manager-led)

| Task | Description | Status | Evidence |
|---|---|---|---|
| T-001 | `scistudio.blocks.base.interactive`: InteractiveMixin, SupportsInteraction, InteractivePrompt, PanelManifest | `[ ]` | |
| T-002 | Registry scan-time validation (capability<->INTERACTIVE) + surface manifest in block metadata | `[ ]` | |
| T-003 | Worker phase marker dispatch (prepare_prompt vs run) | `[ ]` | |
| T-004 | Two-phase scheduler orchestration replacing `_run_interactive` (PAUSED, intermediate refs, finalize) | `[ ]` | |
| T-005 | Lineage records decision, excludes intermediate refs | `[ ]` | |
| T-006 | Cancellation teardown (CANCELLED, release scratch, no compute phase) | `[ ]` | |
| T-007 | Frontend manifest-driven panel host (remove blockType branching) | `[ ]` | |
| T-008 | Migrate Data Router + Pair Editor blocks + repackage panel components | `[ ]` | |
| T-009 | Update architecture + block-development docs | `[ ]` | |
| Tests | 5 new + 2 modified backend test files | `[ ]` | |

## 9. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Backend interactive tests | `pytest tests/blocks/test_interactive_*.py tests/engine/test_interactive_*.py tests/blocks/test_data_router.py tests/blocks/test_pair_editor.py` | `[ ]` | pending |
| Frontend tests | frontend panel-resolution + migrated panels | `[ ]` | pending |
| Gate ledger check (pre-PR) | `gate_record check --mode pre-pr --base origin/main --head HEAD --pr-body-file .workflow/local/pr-body.md` | `[ ]` | pending |
| Gate finalize (pre-PR) | `gate_record finalize --base origin/main --head HEAD --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#1781"` | `[ ]` | pending |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run --title <t> --body <b>` | `[ ]` | pending |

## 10. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-06-26 | manager | Owner directed ONE-PR delivery; standard umbrella `[DO NOT MERGE]` PR ceremony would create a second PR. | Collapse to a single feature/integration/PR branch; document here. Audit is read-only, test engineer is additive, implementation is manager-led — no multi-writer integration to protect. | #1781 |

## 11. Final Readiness

- [ ] All implementation tasks T-001..T-009 complete with tests.
- [ ] No-context audit committed; all P1-P3 fixed (or P3 tracked with owner-approved rationale).
- [ ] Test engineer system/e2e smoke added and passing.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, commit, PR.
- [ ] PR closes #1781; marked READY FOR REVIEW.
- [ ] `admin-approved:core-change` label applied by owner; CI passed.
</content>
</invoke>
