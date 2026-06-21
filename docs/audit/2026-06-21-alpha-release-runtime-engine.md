---
title: "Alpha Release Runtime Engine Audit"
status: Draft
owners:
  - "@jiazhenz026"
related_issue: 1733
related_pr: 1734
agent: A1-runtime-engine
persona: audit_reviewer
audit_mode: with-context
date: 2026-06-21
recommendation: pass-with-must-fix
---

# Alpha Release Runtime Engine Audit

Recommendation: **pass-with-must-fix**.

No P0 was found. The core scheduler/runner path can execute a minimal real
workflow in scratch space, persist an artifact, and write lineage rows. Alpha
should still require remediation or explicit owner risk acceptance for the P1
items below.

## Findings

### P0

None found.

### P1-1: Run-start validation allows registered missing-port edges as warning-only

The alpha criteria require core contracts to reject invalid input or document
allowed instability (`docs/audit/2026-06-21-alpha-release-criteria.md:51-55`).
For registered block types, a workflow edge that references a missing source or
target port remains non-fatal:

- `src/scistudio/workflow/validator.py:332-340` appends `"Warning: port ... not found"` and continues.
- `src/scistudio/api/runtime/_runs.py:313-316` rejects only diagnostics that do not start with `"Warning:"`, so the production start path permits these missing-port diagnostics.
- `src/scistudio/engine/scheduler/_dispatch.py:539-550` skips a missing upstream output port at input gathering time.
- `tests/workflow/test_validator.py:277-297` currently codifies missing port names as warnings.

Command evidence:

```text
PYTHONPATH=src python - <<'PY'
... validate_workflow edge A:missing -> B:in with both block specs registered ...
PY

diagnostics= ["Warning: port 'missing' not found on block 'producer'"]
hard_errors= []
```

Impact: an invalid typed graph can pass run-start validation and fail later as a
worker validation error, or silently drop an optional input. For alpha, make
missing ports on known registered block specs a hard error in strict/run-start
mode, keep warning-only behavior only for draft/save mode if needed, or
explicitly risk-accept and document the instability.

### P1-2: Committed representative execution coverage does not prove the full core runtime path

The alpha criteria require at least one representative workflow to execute end
to end and persist inspectable artifacts/lineage
(`docs/audit/2026-06-21-alpha-release-criteria.md:51-52`), and classify missing
representative tests for a core contract as P1
(`docs/audit/2026-06-21-alpha-release-criteria.md:73-81`).

Existing committed coverage exercises important slices, but not one core-only
representative workflow through validation, `DAGScheduler`, `LocalRunner`,
worker subprocess, artifact persistence, and lineage in the same test/check:

- `tests/integration/test_smoke_workflows.py:1-5` says the smoke workflows use a mock runner to avoid subprocess overhead; `tests/integration/test_smoke_workflows.py:25-32` builds that mock runner.
- `tests/integration/test_multimodal_workflow.py:22-29` skips unless the imaging plugin is installed; its scheduler E2E helper still uses an `AsyncMock` runner at `tests/integration/test_multimodal_workflow.py:296-315`.
- Worker subprocess behavior is tested separately, including environment and cancellation envelopes (`tests/engine/test_worker.py:196-245`, `tests/engine/test_worker.py:297-353`) and required-input validation (`tests/engine/test_worker.py:456-468`).
- Lineage propagation is tested separately (`tests/contracts/test_lineage_run_recipe_contract.py:98-140`, `tests/engine/test_lineage_data_objects_propagation.py:93-135`).

Manual audit evidence shows the runtime can do the path, but this is not
committed release evidence. Add a core-only representative test/check, or record
explicit risk acceptance if the manual audit probe is sufficient for this alpha.

Manual probe result:

```text
states= {'produce': 'done'}
block_executions= [('produce', 'completed')]
data_objects= 1
block_io= 1
artifact_files= ['data/zarr/audit-real-runtime-probe/produce/audit-table.parquet']
```

### P2-1: Documented resource request gating is not wired to block declarations

Architecture says the engine applies `ResourceManager` before work starts
(`docs/architecture/ARCHITECTURE.md:984-1006`) and that block resource request
metadata is used as an admission-control signal
(`docs/architecture/ARCHITECTURE.md:1116-1130`). The scheduler currently passes
a default request:

- `src/scistudio/engine/scheduler/_dispatch.py:86-93` documents TODO(#887) and calls `can_dispatch(ResourceRequest(), ...)`.
- `src/scistudio/engine/resources.py:227-238` documents that `acquire()` has no production caller and discrete GPU/CPU counters stay at zero.

This is already tracked and documented as low risk in the code comments. It is
not a core-alpha blocker for short internal tests, but it should stay visible as
a good-to-fix item before broader local-resource testing.

### P3

None found.

## Positive Evidence

Graph validation covers structural checks, cycles, type compatibility, dangling
required inputs in strict mode, dynamic ports, and CodeBlock v2 config. The
targeted validation suite passed with the worktree source path.

Scheduler lifecycle evidence is strong for alpha scope:

- `DAGScheduler.execute()` emits workflow lifecycle events, dispatches ready
  roots, waits for completion, and cleans active tasks in `finally`
  (`src/scistudio/engine/scheduler/__init__.py:192-224`).
- Block/workflow cancellation includes workflow-scoped events and subprocess
  handle termination (`src/scistudio/engine/scheduler/__init__.py:247-264`,
  `src/scistudio/engine/scheduler/_events.py:145-216`,
  `src/scistudio/engine/scheduler/_events.py:227-291`).
- Runtime event filtering scopes by `workflow_id` when present
  (`src/scistudio/engine/scheduler/_events.py:34-47`), and the concurrency
  suite tests shared-bus run isolation (`tests/engine/test_scheduler_concurrency.py:449-507`).
- State-machine tests cover terminal states, cancel-block/cancel-workflow state
  tables, happy path, and downstream skip on error
  (`tests/engine/test_scheduler_state_machine_contract.py:37-42`,
  `tests/engine/test_scheduler_state_machine_contract.py:133-208`,
  `tests/engine/test_scheduler_state_machine_contract.py:233-286`).

Worker and lineage contracts also have useful coverage:

- Worker subprocess validation calls `Block.validate()` before `run()`
  (`src/scistudio/engine/runners/worker.py:492-504`) and validates required
  outputs before serialization (`src/scistudio/engine/runners/worker.py:533-545`).
- DataObject outputs without storage references are rejected before leaving the
  worker subprocess (`src/scistudio/engine/runners/worker.py:340-354`,
  `src/scistudio/engine/runners/worker.py:369-383`).
- Scheduler terminal payloads include workflow id, block metadata, config,
  environment, inputs, and object IDs for lineage
  (`src/scistudio/engine/scheduler/_lineage.py:221-257`,
  `src/scistudio/engine/scheduler/_lineage.py:260-332`).

## Commands Run

Environment note: plain `python -m pytest ...` initially imported a globally
installed SciStudio from `/opt/anaconda3/...`, producing stale failures and
coverage noise. I therefore used `PYTHONPATH=src` for all material checks; no
`pip install -e .` was used.

- `PYTHONPATH=src python - <<'PY' ... import scistudio ... PY`
  - Result: imported `/Users/jiazhenz/SciStudio-alpha-audit-20260621/src/scistudio/__init__.py`.
- `PYTHONPATH=src python -m pytest --no-cov tests/workflow/test_validator.py tests/workflow/test_validator_dynamic_ports.py tests/workflow/test_validator_codeblock_v2.py -q`
  - Result: passed, `47 passed`.
- `PYTHONPATH=src python -m pytest --no-cov tests/engine/test_dag.py tests/engine/test_scheduler.py tests/engine/test_scheduler_state_machine_contract.py tests/engine/test_scheduler_terminal_data.py -q`
  - Result: passed, 100% of selected tests.
- `PYTHONPATH=src python -m pytest --no-cov tests/engine/test_scheduler_concurrency.py -q --tb=short`
  - Result: passed, `9 passed`.
- `PYTHONPATH=src python -m pytest --no-cov tests/engine/test_local_runner.py tests/engine/test_worker.py tests/integration/test_smoke_workflows.py tests/integration/test_cancel_scenario.py -q --tb=short`
  - Result: passed, 100% of selected tests.
- `PYTHONPATH=src python -m pytest --no-cov tests/contracts/test_lineage_run_recipe_contract.py tests/engine/test_lineage_data_objects_propagation.py tests/engine/test_lineage_recorder.py -q --tb=short`
  - Result: passed, `29 passed`.
- `PYTHONPATH=src python - <<'PY' ... missing-port validate_workflow probe ... PY`
  - Result: warning-only diagnostic and `hard_errors=[]`.
- `PYTHONPATH=src python - <<'PY' ... scratch DAGScheduler + LocalRunner + worker + LineageStore probe ... PY`
  - Result: block state `done`, one completed block execution row, one data object row, one block IO row, and one persisted parquet artifact.

## Limitations

I did not run full CI or gate-record checks; this is the assigned A1 audit
report for the manager-owned alpha audit workflow. Package and extension catalog
completeness remains out of A1 scope unless it breaks core runtime.
