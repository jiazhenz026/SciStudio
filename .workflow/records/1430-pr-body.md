## Summary

Refactor the `src/scistudio/api/runtime.py` god-file (1,839 LOC) into a sub-package under `src/scistudio/api/runtime/`, keeping the full public import surface unchanged. Part of the umbrella backend god-file refactor tracked by #1427.

## Why

The original `runtime.py` carried every project-management, workflow-I/O, data-catalog, preview-routing, and lineage-recording responsibility in one file, and was the largest tracked waiver in `scripts/check_god_files.py` (1,839 LOC vs the 750-LOC threshold). Per umbrella #1427 the file size pushed it beyond comfortable review, search, and IDE navigation budgets, and blocked promotion of the god-file gate from advisory to hard-fail.

This PR is **pure structural refactor** — no behavior changes, no API changes, no schema changes. All previously-public names remain importable via `from scistudio.api.runtime import X` and `from scistudio.api import runtime` followed by attribute access.

## What changed

### Package layout

`src/scistudio/api/runtime.py` (1,839 LOC) → `src/scistudio/api/runtime/` (8 modules, all <500 LOC):

| File | LOC | Responsibility |
| ---- | --- | --- |
| `__init__.py` | 330 | Public package surface: `ApiRuntime` + dataclasses + re-exports |
| `_helpers.py` | 98 | `_now_iso`, `_slugify`, `_safe_parent_dir`, `_rmtree_force` |
| `_preview_cache.py` | 111 | DataFrame preview cache + pyarrow IO helpers |
| `_preview_image.py` | 125 | Raster preview helpers + `_infer_type_name_from_ref` |
| `_projects.py` | 476 | Project CRUD + registry refresh + lineage init |
| `_workflows.py` | 145 | Workflow YAML I/O + upload |
| `_data.py` | 335 | Data catalog + preview routing |
| `_runs.py` | 335 | Workflow execution + lineage recording |

### How the public surface is preserved

* `ApiRuntime` is **defined directly in `__init__.py`** so griffe emits the canonical `scistudio.api.runtime.ApiRuntime` symbol fact that ADR-012 / ADR-014 / ADR-038 / ADR-039 contract claims resolve against.
* Each method on `ApiRuntime` is bound via class-body static assignment (`open_project = _projects.open_project`, etc.) from a free function in a sub-module — griffe sees each method as a member of the class (subject `scistudio.api.runtime.ApiRuntime.<method>`).
* `KnownProject`, `DataRecord`, `WorkflowRun`, `LogBroadcaster` are dataclasses defined directly in `__init__.py` for the same reason.
* Private helpers (`_table_cache`, `_table_cache_lock`, `_read_preview_table_from_disk`, …) are re-exported from `__init__.py` so existing tests that reach in via `from scistudio.api import runtime as runtime_mod; runtime_mod._table_cache.clear()` keep working unchanged.
* `_preview_cache._get_preview_table` now resolves `_read_preview_table_from_disk` through `sys.modules['scistudio.api.runtime']` so the LRU-cache test (`tests/api/test_data.py::test_preview_dataframe_paging_sort_lru_cache`) can keep monkey-patching the public package symbol.

### Other files touched

* `scripts/check_god_files.py` — `src/scistudio/api/runtime.py` waiver retired (it's no longer a file, and every sub-module is below the 750-LOC threshold).
* `docs/adr/ADR-012.md`, `ADR-038.md`, `ADR-039.md`, `ADR-044.md`, `ADR-045.md` — frontmatter `governs.files` entries updated from `src/scistudio/api/runtime.py` → `src/scistudio/api/runtime/` (the directory glob) so closure + doc-drift audits still resolve. No body changes; historical narrative references to the old file path are left untouched.

### New test

`tests/api/test_runtime_import_surface.py` — 4 import-surface preservation tests pin:
1. Every previously-public name still importable from `scistudio.api.runtime`
2. `runtime._table_cache` and the internal getter share the same `OrderedDict` (so `.clear()` is observed)
3. Monkey-patching `runtime._read_preview_table_from_disk` is observed by the internal `_get_preview_table` callers
4. `ApiRuntime` exposes all 41 previously-defined methods

## Test plan

- [x] `ruff check` / `ruff format --check` clean on every changed file
- [x] `pytest tests/api/ tests/core/test_type_registry_scan_dirs.py tests/agent_provisioning/test_lifecycle_integration.py --timeout=60`: pass (8 pre-existing failures on `origin/umbrella/backend-god-file-refactor` deselected and confirmed unrelated to this refactor — see gate record)
- [x] `python scripts/check_god_files.py --enforce`: pass, 0 NEW violations (the original 1839-LOC waiver is retired)
- [x] `python -m scistudio.qa.audit.full_audit`: status=pass (all 8 child checks green)
- [x] Sentrux MCP scan + check_rules + health + session_end: pass, quality signal stable at 4443, 0 violations

## Gate record

`.workflow/records/1430-api-runtime.json` — all 6 stages complete (scope, plan, implement, docs, test, commit-and-submit).

Closes #1430
