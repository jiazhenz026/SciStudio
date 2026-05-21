# Code-scope audit — ADR-038 implementation

Date: 2026-05-15
Auditor: no-context audit agent (D38-2.1)
Repository state: `git log -1 --oneline` on audit branch → `7c1ae58 chore(#910): seed track/adr-038/lineage-db tracking branch` (tracking branch tip). The seed commit is a docs-only marker; the underlying source tree is identical to `main@0cc8a8f docs(#904): Phase 0 architecture refactor for ADR-038 + ADR-039 cascade (#905)`. All findings below reference the state of the source tree at this commit.
ADR §5.2 file list reviewed against: 14 source-tree paths actually scanned across `src/scistudio/**`, `frontend/src/**`, `tests/**`.

## Summary

ADR-038 §5.1 lists 7 new backend files (under `src/scistudio/core/lineage/`), 1 new API route file, 6 new frontend `Lineage/` components, and 1 new `frontend/src/store/lineageSlice.ts`. §5.2 lists **14 modified files** (10 backend, 1 worker, 3 frontend).

This audit confirms **13 of the 14** ADR §5.2 entries actually touch live code that participates in the lineage / metadata flow on `main`. One row (`frontend/src/store/index.ts`) is correctly listed but trivial.

**Newly discovered (missing from §5.2): 7 additional callsites / files**, all in already-listed subsystems but not enumerated as separate edits:

1. `src/scistudio/ai/agent/mcp/tools_inspection.py` — two distinct `get_metadata_store()` call sites + `get_lineage()` tool that returns lineage data
2. `src/scistudio/ai/agent/mcp/tools_qa.py` — `get_metadata_store()` call site
3. `src/scistudio/cli/main.py:111` — creates `checkpoints` + `lineage` directories in `init_project`; symmetric to `runtime.py:365`
4. `src/scistudio/api/runtime.py:365-367` — `create_project` scaffold list includes `checkpoints` and `lineage` directories
5. `src/scistudio/core/lineage/__init__.py` — public re-export surface for `LineageStore` + `LineageRecord`
6. `src/scistudio/core/lineage/graph.py` — `ProvenanceGraph` class consumes the old hash-keyed `LineageRecord`; needs schema-rewrite or removal
7. `frontend/src/store/uiSlice.ts`, `frontend/src/store/tabSlice.test.ts`, `frontend/src/store/__tests__/tabState.test.ts`, `frontend/src/store/executionSlice.ts` — every site that reads `state.activeBottomTab` may need to react to the `"jobs"` tab removal

Two ADR §5.2 line-number citations are stale relative to `main`:

- ADR §5.2 says `api/runtime.py:969-978` houses the `DAGScheduler` construction. Actual location: **`api/runtime.py:1045-1054`**.
- ADR §2.1 says `api/runtime.py:969-978` omits the `lineage_recorder` kwarg. Same — actual lines **1045-1054**.

No files in §5.2 are **overestimated** (all of them genuinely touch the affected surfaces) with one minor nuance noted in the third table.

Several **tests** beyond `tests/engine/test_lineage_recorder.py` and `tests/core/test_lineage*.py` (which ADR §5.4 names) need migration — including `tests/api/test_deps.py` which asserts the exact `lineage/lineage.db` path and **does not appear in any ADR-038 list**.

## Files that ARE in ADR §5.2 and ALSO touch the affected surfaces (confirmed in-scope)

| File | Symbols / lines | ADR §5.2 row |
|---|---|---|
| `src/scistudio/engine/scheduler.py` | `LineageRecorder` import L36, kwarg L102, attribute L112, `lineage_recorder.record_start(node_id)` L216-217, BLOCK_DONE emission `data={"workflow_id","outputs"}` L425-431 and L549-555, `_persist_output_metadata` callsite L423 + L547, definition L564-594, `_persist_single_output` L596-627, `_sync_checkpoint_to_store` L629-683 (Collection unrolling at L608-618, L649-664) | scheduler.py row (lines 425-431, 549-555, 423, 547) — **all confirmed**; ΔLOC estimate of +180 is realistic |
| `src/scistudio/api/runtime.py` | `_init_metadata_store` L327-348 (opens `metadata.db`), called from `open_project` L463, `DAGScheduler` constructor L1045-1054 (does **not** pass `lineage_recorder` — confirmed dormant), `checkpoint_dir_for` L1034-1036 returns `<project>/checkpoints/<workflow_id>`, project scaffold dirs L356-368 include `"checkpoints"` and `"lineage"` | runtime.py row — confirmed; **but ADR-cited line numbers `:969-978` are stale; actual is `:1045-1054`** |
| `src/scistudio/engine/runners/local.py` | Worker envelope parsing L226-264; `parsed.get("environment")` is **not** lifted into the returned dict — `dict(parsed["outputs"])` at L233 discards `environment`. Comment at L229-231 names the envelope shape | local.py:229 row — confirmed; the line is a comment but the unwrap logic that drops `environment` is L232-264 |
| `src/scistudio/engine/lineage_recorder.py` | Whole module (93 LOC). Reads `data.get("config", {})`, `block_version`, `input_hashes`, `output_hashes`, `environment`, `partial_output_refs`, `error` from event data at L77-86 — all of which are **absent** from current BLOCK_DONE emission per scheduler.py L425-431 | lineage_recorder row — confirmed (move + extend to recorder.py + run-lifecycle hooks) |
| `src/scistudio/blocks/registry.py` | `BlockSpec.version` L38 defaults to `"0.1.0"` (not `"unknown"` as ADR §2.1 narrative claims — see Open Questions); `_spec_from_class` L671 reads `getattr(cls, "version", "0.1.0")`; no `importlib.metadata.version(<distribution>)` resolution anywhere. `_scan_builtins` L214-235, `_scan_tier1` L237-297, `_scan_tier2` L299-398, `_scan_monorepo_packages` L400+ all skip distribution-version injection | registry.py row — confirmed (force-inject + fail-loud) |
| `src/scistudio/core/meta/framework.py` | `FrameworkMeta.lineage_id: str \| None = None` L64, `derive()` propagates `lineage_id` via inheritance L104. Default factory at L62 (`object_id = uuid4().hex`). Docstring L13 + L50 explicitly references "LineageRecorder" | framework.py row — confirmed (populate `lineage_id` with `block_execution_id`) |
| `src/scistudio/core/metadata_store.py` | Entire 391-LOC module: `MetadataStore` class L65-372, `_CREATE_TABLE` L37-50 (table name `data_objects`, columns: `object_id`, `derived_from`, `type_name`, `backend`, `storage_path`, `created_at`, `wire_payload`, `workflow_id`, `block_id`, `port_name`), module singleton `_store` + `get_metadata_store` + `set_metadata_store` at L379-390 | metadata_store.py row — confirmed (delete → 6-month shim) |
| `src/scistudio/api/deps.py::get_lineage_store` | L34-44; orphan FastAPI dependency that constructs `LineageStore(Path(project.path) / "lineage" / "lineage.db")` and is **not** referenced by any router (verified — only test reference is `tests/api/test_deps.py`) | deps.py row — confirmed orphan |
| `src/scistudio/api/app.py` | `include_router` calls L196-207 currently register `workflows`, `blocks`, `data`, `filesystem`, `projects`, `ai`, `ai_pty`, `lint`. No `runs` router registered. Confirmed by `Glob src/scistudio/api/routes/*.py` — `runs.py` does not exist | app.py row — confirmed (register new `runs` router + shim wiring) |
| `src/scistudio/engine/checkpoint.py` | `CheckpointManager` L275+; docstring L271-281 references BLOCK_DONE subscription L298. Checkpoint files live under the directory returned by `runtime.py:checkpoint_dir_for` (i.e. `<project>/checkpoints/<workflow_id>/`). No `.scistudio/pause/` references currently exist | checkpoint.py row — confirmed (relocate path) |
| `src/scistudio/blocks/ai/ai_block.py` | `_make_run_id` L524-529 produces `YYYYMMDD-HHMMSS-{name}-{nonce}`; `RunDir(project_dir, run_id)` L230; `run_id` propagated to `PtyTabSpec.block_run_id` L292; passed to `_safe_notify(..., run_id, ...)` L327, L332, L338, L351, L357 | ai_block.py row — confirmed (rename `run_id` → `block_execution_id`) |
| `src/scistudio/blocks/ai/run_dir.py` | Path construction L102: `self.path = self.project_dir / ".scistudio" / "ai-block-runs" / run_id`; `run_id` validation L98; class docstring at L1-11 + L76 references the path verbatim; manifest schema comment at L33-36 embeds `"run_id"` field name | run_dir.py row — confirmed (rename path segment + field) |
| `frontend/src/components/BottomPanel.tsx` | `TAB_LABELS` declares `lineage: "🔗 Lineage"` L26 and `jobs: "📊 Jobs"` L27; `ALL_TABS` L33 includes both; comment at L30-32 explains Problems-tab removal. **No `<LineageTab/>` import or render** — confirms placeholder status | BottomPanel.tsx row — confirmed |
| `frontend/src/types/ui.ts` | `BottomTab = "ai" \| "config" \| "logs" \| "lineage" \| "jobs"` L5 | types/ui.ts row — confirmed |
| `frontend/src/store/index.ts` | `partialize: (state) => ({ activeBottomTab: state.activeBottomTab, ... })` L55-56 persists the active tab; slice constructors L43-52 do NOT include any lineageSlice today | store/index.ts row — confirmed (will register `lineageSlice`) |

## Files MISSING from ADR §5.2 (newly discovered)

| File | Symbols / lines | Concept (which D38 phase needs to touch this) |
|---|---|---|
| `src/scistudio/ai/agent/mcp/tools_inspection.py` | `inspect_data` lookup at L113-123 calls `get_metadata_store()` then `store.get_wire_by_storage_path(...)`; `get_lineage()` MCP tool at L356-381 calls `get_metadata_store()`, then `store.get_by_storage_path(...)` and `store.ancestors(object_id)` — returns `{"nodes": [...], "edges": [...]}`. Both code paths break when `MetadataStore` becomes a shim. | Phase 2 — must be ported to the new `LineageStore` API surface or to the shim. `get_lineage` already exists as an MCP affordance; mirror it onto `data_objects` table queries (§3.7). |
| `src/scistudio/ai/agent/mcp/tools_qa.py` | `get_project_info` L205-216 calls `get_metadata_store()` to populate `recent_runs` (currently no-op — comment "Recent runs: …leave empty — this is best-effort"). | Phase 3 — replace with a `LineageStore.list_runs(limit=…)` query against the new `runs` table; this becomes the AI agent's read path for run history. |
| `src/scistudio/cli/main.py:111` | `init` command scaffolds project directories including `"checkpoints"` and `"lineage"` (L102-116). Symmetric to `runtime.py:365`. Also constructs `DAGScheduler` at L187-194 **without `lineage_recorder` kwarg** — same dormancy as `api/runtime.py:1045`. | Phase 1 (scheduler wire-up) + Phase 2 (directory scaffold rewrite). ADR §2.1 calls out the cli/main.py L187-194 callsite for `lineage_recorder` but ADR §5.2 omits cli/main.py entirely. |
| `src/scistudio/api/runtime.py:356-368` | `create_project` scaffolds `"checkpoints"` and `"lineage"` subdirs. After ADR-038 §3.1, the new home is `.scistudio/lineage.db`; the on-disk `lineage/` dir becomes orphan. | Phase 2 (directory layout migration). Listed under runtime.py row but the specific scaffold block is not enumerated — flag for Phase 2 owner to remove the obsolete dirs and add `.scistudio/` as needed (cf. ADR-038 §3.5). |
| `src/scistudio/core/lineage/__init__.py` | Re-exports `LineageStore`, `LineageRecord`, `EnvironmentSnapshot`, `ProvenanceGraph` (L5-15). Public-facing import surface — downstream code (and ADR-038's deprecation shim) needs the same names re-exported. | Phase 1 — rewrite `__all__` to match the new record / store names; preserve old names via shim re-exports for the 6-month window. |
| `src/scistudio/core/lineage/graph.py` | `ProvenanceGraph` class (L1-106) consumes the **hash-keyed** `LineageRecord.input_hashes` / `output_hashes` fields. ADR-038 removes content hashing entirely (§3.4). The graph either needs a complete rewrite against the new schema (object-id-keyed `data_objects.derived_from` chain) or deletion. | Phase 2 — the ProvenanceGraph helper is the in-memory companion to LineageStore; without content hashes, it must be re-keyed on `data_objects.object_id` traversals or replaced by direct `LineageStore.ancestors_by_object_id()` calls. ADR §5.1 mentions "graph.py" only as "MODIFY: re-point to new store" — the deeper API rewrite is unstated. |
| `frontend/src/store/uiSlice.ts` + `frontend/src/store/executionSlice.ts` + `frontend/src/store/__tests__/tabState.test.ts` + `frontend/src/store/tabSlice.test.ts` | `uiSlice.ts` L7, L25, L30 all reference `activeBottomTab`; `executionSlice.ts` L72, L93 guard with `state.activeBottomTab !== "logs"`. Tests at `tabSlice.test.ts:23,88` and `__tests__/tabState.test.ts:38` use bottom-tab fixtures. Default value `"config"` at `uiSlice.ts:7`. None of these mention `"jobs"` explicitly, but the persisted-state shape changes when the discriminated union loses `"jobs"`. | Phase 3 — verify that a persisted localStorage state with `activeBottomTab === "jobs"` falls back to a valid value after migration (otherwise users with the saved tab get a runtime error). Add a migration shim in `index.ts`'s `onRehydrateStorage`. |

## Files in ADR §5.2 that DO NOT actually appear to touch the surface (overestimated scope)

No files in §5.2 are wholly overestimated. Two are partially nuanced:

| File | ADR §5.2 row | Reason it's unnecessary |
|---|---|---|
| `src/scistudio/blocks/registry.py` | "Force-inject `block_version` from `importlib.metadata.version(distribution_name)`; fail loudly on resolution failure" (+60 ΔLOC) | The current default at `BlockSpec.version` L38 is **`"0.1.0"`**, not `"unknown"` as ADR §2.1 claims. The functional gap (no PyPI version injection) is real; the narrative claim that the default is `"unknown"` is stale. Phase 1 should still inject distribution-version, but the "remove `unknown` default" framing is misleading — there is no `"unknown"` literal in `src/scistudio/blocks/registry.py`. (The string `"unknown"` does appear once at `engine/lineage_recorder.py:78` as the **read-side** default when extracting `block_version` from event data.) |
| `src/scistudio/engine/checkpoint.py` | "Relocate `<project>/checkpoints/<workflow_id>/` to `<project>/.scistudio/pause/`" (±25 ΔLOC) | The path is currently constructed **outside** `checkpoint.py` itself — in `api/runtime.py:1034-1036` (`checkpoint_dir_for`) and `cli/main.py:111` (scaffold dir). `engine/checkpoint.py` itself takes a `Path` and does not hard-code the segment. The Phase-2 owner should know to edit `runtime.py` + `cli/main.py` for the relocation; `checkpoint.py` only needs the docstring update mentioned. |

## Tests that construct lineage / metadata stores directly

| Test file | Test functions | Construction pattern |
|---|---|---|
| `tests/core/test_lineage.py` | `TestLineageStore` (10 methods, L109-249), `TestProvenanceGraph` (multiple, L252+), `TestLineageTerminationFields` (5 methods, L351-428) | `LineageStore(":memory:")` L113,128,135,141,161,173,180,189,210,410; `LineageStore()` default-path L240,245; constructs `LineageRecord(input_hashes=…, output_hashes=…)` repeatedly L25-33, L143-152, L361-373, L378-388, L393-404, L411-422 |
| `tests/core/test_lineage_extended.py` | `TestLineageStoreClose` (3 methods L17-70), `TestProvenanceGraphEdgeCases` (multiple from L73) | `LineageStore(":memory:")` L21,51; `LineageStore(db_path)` file-based L28,42; manual `sqlite3.ProgrammingError` assertion L23; `LineageRecord(...)` ctor L29-37, L52-63, L92-100 |
| `tests/core/test_metadata_store.py` | `TestPutWire`, `TestGet`, `TestGetByStoragePath`, `TestAncestors`, `TestDescendants`, `TestListByType`, `TestListByWorkflow`, `TestDelete`, `TestVacuum`, `TestPutWireIfMissing`, `TestSingleton`, `TestRepr` (~25+ methods total) | Fixture at L55-58: `MetadataStore(tmp_path / "metadata.db")`; asserts `"metadata.db" in repr(...)` L302; tests `set_metadata_store` + `get_metadata_store` L275+ |
| `tests/engine/test_lineage_recorder.py` | `TestLineageRecorder` (8 methods, L28-118) | `LineageRecorder(event_bus, lineage_store=store)` L24 with `MagicMock` store; asserts `record.block_id`, `record.termination`, `record.termination_detail`, `record.duration_ms` |
| `tests/api/test_deps.py` | `test_dependency_helpers_resolve_runtime_objects` L10-24 | Calls `deps.get_lineage_store(request)` and **asserts the exact path** `lineage\\lineage.db` or `lineage/lineage.db` — will fail when ADR-038 moves the DB to `.scistudio/lineage.db` |
| `tests/ai/test_mcp_tools_inspection.py` | `test_get_lineage_no_store_returns_empty` L168-172, `test_get_lineage_with_object_id` L175-179 | Asserts the `{"nodes": [], "edges": []}` fallback when `MetadataStore` is uninstalled — confirms the AI MCP path is in scope (see "Missing from ADR §5.2" table) |

## Frontend touchpoints (D38-2.4b / 2.4c)

| File | Lines | What needs to change |
|---|---|---|
| `frontend/src/components/BottomPanel.tsx` | L4 (`BottomTab` import), L22-28 (`TAB_LABELS` Record), L33 (`ALL_TABS` array — currently `["ai", "config", "logs", "lineage", "jobs"]`), L30-32 (comment about removed Problems tab) | Remove `"jobs"` from `ALL_TABS` (L33), remove `jobs:` entry from `TAB_LABELS` (L27). Add `<LineageTab>` render branch when `activeTab === "lineage"`. ADR §5.2 mentions L33 + L27 — confirmed. |
| `frontend/src/types/ui.ts` | L5: `export type BottomTab = "ai" \| "config" \| "logs" \| "lineage" \| "jobs";` | Remove `\| "jobs"` from union. ADR §5.2 confirmed. |
| `frontend/src/store/index.ts` | L43-52 (slice composition), L54-71 (`partialize` config), L72-111 (`onRehydrateStorage` migration) | Register `createLineageSlice` in `(...args) => ({...})`. Add a rehydration migration: if `state.activeBottomTab === "jobs"` after JSON parse, coerce to `"config"` (or `"lineage"`). ADR §5.2 mentions L only as "+5"; the rehydration migration is implicit, not enumerated. |
| `frontend/src/App.tsx` | L81 (`activeBottomTab = useAppStore(...)`), L86 (`setActiveBottomTab`), L140 (`useLogStream(... activeBottomTab === "logs" ...)`), L573, L585 (auto-switch logic), L1054-1057 (`<BottomPanel activeTab=... onTabChange=... />`) | No structural change required, but `setActiveBottomTab("lineage")` may need to be invoked by a new menu item / WebSocket auto-switch (e.g. "Run completed → switch to lineage"). Not enumerated in ADR §5.2. |
| `frontend/src/store/uiSlice.ts` | L7 (`activeBottomTab: "config"`), L25 (set-with-side-effects), L30 (logs-unread reset guard) | Add migration safety: if `tab` arg is `"jobs"` after union-narrowing fix, coerce to `"config"`. Not enumerated in ADR §5.2. |
| `frontend/src/store/executionSlice.ts` | L72, L93 (`state.activeBottomTab !== "logs"`) | No change needed — string compare still valid. Listed for completeness. |
| `frontend/src/store/tabSlice.test.ts` | L23 (`activeBottomTab: "config"`), L88 (`expect(...activeBottomTab).toBe("ai")`) | No change needed — `"config"` and `"ai"` survive the union narrowing. |
| `frontend/src/store/__tests__/tabState.test.ts` | L38 (`activeBottomTab: "config"`) | Same — `"config"` survives. |
| `frontend/src/hooks/useWebSocket.ts` | L151 (comment mentions ADR-035 §6.1 lineage — unrelated noise grep hit) | No code change; comment hit is incidental. |
| **NEW** `frontend/src/components/Lineage/LineageTab.tsx` + 5 siblings | n/a | ADR §5.1 specifies 6 new files. None exist on `main` — confirmed via `Glob frontend/src/components/Lineage/**` returning empty. |
| **NEW** `frontend/src/store/lineageSlice.ts` | n/a | ADR §5.1 specifies; confirmed missing. |

## Open questions for the manager

1. **`block_version` default discrepancy.** ADR §2.1 states "`block_version` field defaults to `"unknown"` because BlockRegistry has no version-injection logic." Actual default at `src/scistudio/blocks/registry.py:38` is `"0.1.0"`. The `"unknown"` string appears only at `engine/lineage_recorder.py:78` as a **fallback** when reading event data. Two interpretations:
   - The narrative meant "in the lineage record (write side), `block_version` ends up as `"unknown"` because the scheduler never plumbs it through" — accurate for the dormant path.
   - The Phase 1 implementer should change L38 to require explicit version (fail-loud) per ADR §3.3, **not** change a `"unknown"` literal (there is none in registry.py).

   Recommend the Phase 1 dispatch prompt clarify which symbol changes.

2. **`metadata_store.py::get_wire_by_storage_path`.** `tools_inspection.py:119` calls `store.get_wire_by_storage_path(sref.path)` — but `MetadataStore` only defines `get_wire(object_id)` and `get_by_storage_path` (which returns a `DataObject`, not a wire dict). This is a **latent bug on main** (the `hasattr` guard at L119 swallows it). Out of scope for D38 fixes, but worth filing as an audit follow-up issue so the shim doesn't preserve a broken accessor.

3. **`ProvenanceGraph` in the post-hash world.** ADR-038 §3.4 deletes content hashing. `ProvenanceGraph` is keyed entirely on output/input hashes (`graph.py:31-36`). Three options:
   - Delete it and replace with `LineageStore` SQL queries (§3.7).
   - Rewrite to walk `data_objects.derived_from` (object-id chains).
   - Keep as a shim that wraps the new schema with synthetic keys.

   §5.1 mentions only "MODIFY: re-point to new store" — recommend the Phase 2 owner be told explicitly which option to take.

4. **Frontend `activeBottomTab` rehydration.** If a user has `localStorage["scistudio-studio-ui"]` with `activeBottomTab: "jobs"` from a pre-ADR-038 session, the React tab renderer (which uses `TAB_LABELS[activeBottomTab]` indexing) will produce `undefined`. ADR §5.2 doesn't mention a rehydration migration. Recommend Phase 3 add a coercion in `frontend/src/store/index.ts::onRehydrateStorage`.

5. **`tests/api/test_deps.py` path assertion.** L21-23 hard-codes the substring `lineage/lineage.db`. After ADR-038 the path becomes `.scistudio/lineage.db`. ADR §5.4 lists "`tests/engine/test_lineage_recorder.py` and `tests/core/test_lineage*.py`" as needing migration but omits `test_deps.py`. Add to Phase 1 test-migration sweep.

6. **`tests/ai/test_mcp_tools_inspection.py:169` comment** still says "No MetadataStore installed in tests; should degrade gracefully." Once the shim exists, the comment is stale but the test stays valid (asserts empty `nodes`/`edges`). Flag for Phase 2 cleanup.

7. **CLI `init` parity with `api/runtime.py`.** `cli/main.py:111` and `api/runtime.py:365-367` both scaffold `"checkpoints"` and `"lineage"` dirs. After ADR-038, both must change in lockstep (move under `.scistudio/`). The cli site is not enumerated in §5.2.
