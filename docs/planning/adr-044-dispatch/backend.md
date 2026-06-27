# ADR-044 Backend — Manager-Implemented (not dispatched)

The backend half of ADR-044 is tightly coupled (flatten ↔ schema ↔ serializer ↔
validator ↔ runtime wiring ↔ lineage snapshot ↔ subworkflow_block port helper).
The manager built complete firsthand knowledge of every affected file during the
investigation phase, so the backend is implemented directly on the umbrella
branch (`track/adr-044-subworkflow-20260621`) rather than dispatched to a separate
agent. This avoids cross-agent integration risk on interdependent code and keeps
one coherent design.

Backend write set (umbrella branch):
- `src/scistudio/workflow/schema.py` — `ExposedPortModel` / `ExposedPortsModel`; `exposed_ports` on `WorkflowModel`.
- `src/scistudio/workflow/definition.py` — `exposed_ports` field + thin `flatten_subworkflows` forwarding method.
- `src/scistudio/workflow/serializer.py` — `dump_yaml_str` helper; `exposed_ports` round-trip.
- `src/scistudio/workflow/flatten.py` (NEW) — `flatten_subworkflows` free function + `CyclicSubworkflowError`.
- `src/scistudio/workflow/subworkflow_ports.py` (NEW) — port-resolution helper (load ref file, read exposed_ports, inherit accepted_types). Shared by block + route + validator.
- `src/scistudio/workflow/validator.py` — broken-ref hard error at run start; subworkflow effective-ports for dangling-edge detection.
- `src/scistudio/blocks/subworkflow/subworkflow_block.py` — delete stub; authoring-only shell; `get_effective_*_ports`; `SubWorkflowBroken`.
- `src/scistudio/blocks/subworkflow/__init__.py` — exports.
- `src/scistudio/blocks/registry/_scan.py` — register `SubWorkflowBroken`.
- `src/scistudio/api/runtime/_runs.py` — flatten at `start_workflow` (before validate/dispatch); flattened snapshot.
- `src/scistudio/api/runtime/_workflows.py` — confirm `load_workflow` does NOT flatten; FR-011 import-to-project.
- `src/scistudio/api/routes/workflows.py` — `resolved_ports` on the workflow GET node response (FR-004 delivery to editor).
- `src/scistudio/api/schemas.py` (or wherever `WorkflowNode` response model lives) — optional `resolved_ports` field.
- `docs/architecture/ARCHITECTURE.md` §5.4.7.
- Backend tests: `tests/blocks/test_subworkflow.py` (rewrite), `tests/workflow/test_flatten_subworkflows.py` (NEW),
  `tests/workflow/test_serializer.py` (extend) / `tests/workflow/test_subworkflow_yaml_roundtrip.py`,
  `tests/integration/test_subworkflow_lineage.py` (NEW), `tests/api/test_runtime_subworkflow_flatten.py` (NEW).

Engine paths (`engine/scheduler/**`, `engine/runners/**`) are ADR-044 `excludes`
and require NO edits: grep confirms zero `_scheduler_factory`/`_cleanup_callback`
injection sites; FR-012 engine deletion is satisfied-by-absence (recorded as a
gate scope note). Two stale docstrings in `engine/runners/platform.py` are left
untouched (ADR exclude boundary) and flagged for the auditor.
