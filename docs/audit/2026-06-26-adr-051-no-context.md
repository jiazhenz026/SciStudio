# ADR-051 No-Context Audit (2026-06-26)

**Auditor:** no-context audit agent (read-only). Independently compared
`docs/adr/ADR-051.md` and `docs/specs/adr-051-interactive-blocks.md` against the
implementation, tests, and observable behaviour, using only repository artifacts
and tools run by the auditor.
**Subject:** implementation of ADR-051 "Interactive Data-Processing Blocks"
(branch `feat/1781-adr-051-interactive-blocks`).

## Summary

ADR-051 is implemented faithfully and to a high standard. Interaction is a
capability (`InteractiveMixin` + `execution_mode = INTERACTIVE`) bound at the
universal registry scan chokepoint; the runtime executes interactive blocks as
two real worker subprocesses around an engine-held pause; the decision is
recorded in lineage and intermediate scratch is excluded and released; the
frontend resolves panels from the manifest `panel_id` with no `blockType`
branching. Every normative FR/SC is met or substantially met.

- **P1 (blocking): 0**
- **P2 (real defect / meaningful divergence): 1**
- **P3 (quality / divergence-nit / test-gap): 3**

**Overall verdict: PASS / ship-ready.** No normative FR or SC is broken. The
single P2 is a cross-run isolation gap in the interactive-completion event
handler that appears pre-existing (#591/#594 provenance) and is not mandated by
any ADR-051 FR, but lives in the exact event flow ADR-051 reworks and is
asymmetric with the workflow-scoped cancel path the change relies on.

> **Resolution (manager):** all four findings were addressed in the follow-up
> fix commit. See the "Manager resolution" notes inline.

## Method

Read in full: the two governing docs; backend `interactive.py`, `state.py`,
`block.py`, `registry/{_capability,_spec,__init__}.py`,
`runners/{worker,local,base,process_handle}.py`,
`scheduler/{_dispatch,_events,_lineage,__init__}.py`, `engine/events.py`,
`api/ws.py`, `process/builtins/{data_router,pair_editor}.py`; frontend
`InteractiveModals.tsx`, `store/types.ts`, `handleLifecycle.ts`,
`dispatchEvent.ts`; all eight test suites + `tests/fixtures/interactive_blocks.py`.

Commands run (project venv, `PYTHONPATH=<target>/src`, from target):

| Command | Result |
|---|---|
| `pytest tests/blocks/test_interactive_{mixin,registry_validation}.py test_data_router.py test_pair_editor.py -o addopts=""` | **51 passed** |
| `pytest tests/engine/test_interactive_{two_phase,lineage,cancellation}.py test_scheduler_interactive.py -o addopts=""` | **5 passed** (incl. real-subprocess e2e) |
| `python -m scistudio.qa.audit.full_audit --repo-root . --format markdown` | **Status: pass; 0 error-severity findings** |
| `frontend: tsc --noEmit` | **EXIT 0** |

## Findings

### P2-1 — `_on_interactive_complete` is not workflow-scoped; `interactive_complete` frame carries no `workflow_id`

- **Severity:** P2
- **Location:** `engine/scheduler/_events.py` (`_on_interactive_complete`);
  `api/ws.py` (inbound handler); `frontend/.../InteractiveModals.tsx`
  (`onConfirm`).
- **Spec vs code:** The codebase's `#1517/#1596` invariant
  (`_event_is_for_run`) is "a scheduler must only react to events for its own
  `workflow_id`." Sibling handlers (`_on_block_done`, `_on_cancel_block`, …) all
  call it; `_on_interactive_complete` did not, resolving the pending future
  purely by `block_id`. The frontend `onConfirm` sent no `workflow_id` (unlike
  `onCancel`), and `ws.py` emitted the decision only — so the guard could not
  scope it without a frontend change.
- **Why it matters:** With one process-global `EventBus`, two concurrent runs
  each containing an interactive block with the same node id, both paused, would
  have one browser confirm resolve **both** schedulers' futures — a silent
  cross-run wrong-result.
- **Manager resolution:** Fixed. `onConfirm` now sends `workflow_id`; `ws.py`
  carries it in the `INTERACTIVE_COMPLETE` event (decision nested under
  `response`); `_on_interactive_complete` now applies `_event_is_for_run`
  (fail-open on absent `workflow_id`, so legacy callers still work) and extracts
  the decision without leaking `workflow_id` into `interactive_response`. New
  test `test_interactive_run_scoping.py` asserts a mismatched `workflow_id` does
  not resolve the future.

### P3-1 — Core panels resolve via a bundled `PANEL_REGISTRY`, not the ADR-048 asset route (FR-007 literalism)

- **Severity:** P3
- **Spec vs code:** FR-007 says panels are "loaded from the block's manifest
  through the ADR-048 same-origin asset-serving mechanism." Core panels instead
  resolve by `panel_id` against a bundled registry (`module_url=""`); the
  asset-route path is the package path. The load-bearing requirement (manifest
  resolution, **no `blockType` branching**, SC-006) is fully met.
- **Manager resolution:** Documented. FR-007 and the spec technical approach now
  state explicitly that core panels resolve from a bundled registry keyed by
  `panel_id` and that the ADR-048 asset-route dynamic import is the package path
  (no core consumer ships a wheel-served panel).

### P3-2 — SC-001 e2e proved the compute subprocess directly but the prompt subprocess only indirectly

- **Severity:** P3
- **Manager resolution:** Fixed. The `SelectOptionBlock` fixture now records the
  OS pid of the process running `prepare_prompt` in its `panel_payload`, and the
  two-phase e2e asserts that pid differs from the test process pid — a direct
  proof that the prompt phase ran in a worker subprocess.

### P3-3 — `interactive_response` JSON-safety was enforced implicitly, not by an explicit reject like `panel_payload`

- **Severity:** P3
- **Manager resolution:** Fixed. `_run_interactive` now performs an explicit
  `json.dumps(response_data)` check before merging the decision into the compute
  config, so a non-JSON response is rejected by the runtime symmetrically with
  the `panel_payload` check (FR-004).

## Per-FR / SC conformance (as audited, before fixes)

| Req | Verdict | Basis |
|---|---|---|
| FR-001 | pass | `is_interactive = execution_mode==INTERACTIVE`; capability gated by mixin. |
| FR-002 | pass | `_validate_interactive_capability` in `_spec_from_class` (all 4 scan tiers); matrix + real-scan tests green. |
| FR-003 | pass | `prepare_prompt` runs only in the prompt-phase subprocess with full inputs + config. |
| FR-004 | pass | `panel_payload` `json.dumps`-checked; response JSON-safe by WS-parse (now explicit too, P3-3). |
| FR-005 | pass | Single `run_prompt` over full inputs; one PAUSE + one future. |
| FR-006 | pass | PAUSED + `BLOCK_PAUSED` + `INTERACTIVE_PROMPT`; prompt worker exits before the wait → nothing resident. |
| FR-007 | partial→pass | Manifest `panel_id` resolution, no `blockType` branching (SC-006); core registry path now documented (P3-1). |
| FR-008 | pass | One `await future`, one compute call; no recompute loop. |
| FR-009 | pass | RUNNING; fresh `LocalRunner.run` subprocess; decision (+intermediate) merged into compute config. |
| FR-010 | pass | Intermediate engine-held, threaded into compute config, absent from prompt data, loadable via `load_intermediate`. |
| FR-011 | pass | Decision in `block_config_resolved`; intermediate excluded; lineage test asserts both. |
| FR-012 | pass | Cancel→CANCELLED, future cancelled, scratch released, no compute; test asserts all three. |
| FR-013 | pass | No block code in the scheduler process; `prepare_prompt`/`run` only via worker subprocess. |
| FR-014 | pass | DataRouter/PairEditor migrated; `run()` logic unchanged; migration tests green. |
| FR-015 | pass | `INTERACTIVE_PROMPT` carries `block_type` + `panel_manifest`; payload nested. |
| SC-001 | pass | Real two-phase e2e; compute subprocess proven via env; prompt subprocess now proven via pid (P3-2). |
| SC-002 | pass | 6/6 malformed declarations rejected; valid + AUTO accepted. |
| SC-003 | pass | Lineage test: decision recorded, intermediate absent. |
| SC-004 | pass | Cancellation test: CANCELLED, 0 compute spawns, scratch deleted. |
| SC-005 | pass | DataRouter/PairEditor behaviour suites unchanged and green. |
| SC-006 | pass | `PANEL_REGISTRY` keyed by `panel_id`; no `blockType` panel selection; tsc clean. |
