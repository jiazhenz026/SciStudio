# SciEasy Interface SSOT — Draft v1

> **Phase 3 manager-merged consolidation.** Synthesis of M1 + M2 (Phase 2.5 consolidators) + I1 + I2 (Phase 2 supplementary issue-investigators) + K1/K2/K3 + C1..C7 + D1 + xcheck.
>
> **Status**: WORKING DRAFT. Not the final INTERFACE_SPEC.md. Phase 4 audit agents verify this; Phase 5 manager-fix produces draft v2; Phase 6 (manager-writes-SSOT) produces the final.
>
> **Baseline SHA**: `a4b8b5f` (post-ADR-040 cascade merge).
> **Umbrella issue**: #1090.
> **Authority hierarchy**: ARCHITECTURE.md PRIMARY > ADR SUPPLEMENTARY > CLAUDE.md (process conventions only). ARCH wins on conflict.
>
> **🛑 BLOCKED on Codex cross-cascade reconciliation before Phase 6.**

---

## Reading guide

This draft is a **delta-style consolidation**, not a verbatim re-write of M1/M2 (which together total ~166KB of detailed signatures). The Phase 6 manager writes the verbatim SSOT; here we capture the **merged decisions** and **delta from M-agent drafts**.

For each module:
- **Source-of-record**: which Phase 2.5 file is the primary source (M1, M2, or manager-written from C/D/I)
- **Final interface count + a/b/c/d breakdown** (after K-disagreement resolution + I-addition folding)
- **Key decisions** (b/c/d sub-labels + which side wins for b)
- **Manager overrides** (where I disagree with M1 or M2)
- **New issue-driven entries** (from I1/I2)
- **Open issue placeholders** (the `#TBD-*` refs that Phase 9 turns into real GitHub issue numbers)

The Phase 6 SSOT writer (= me, post-Codex-cross-check) takes this draft + M1/M2 verbatim signatures + I additions and produces `docs/specs/INTERFACE_SPEC.md` with the grammar that `scripts/spec_audit/extract_spec.py` parses.

---

## Aggregate counts (draft v1)

| Phase | Total | a | b | c | d | Notes |
|---|---|---|---|---|---|---|
| K1 | 121 | 52 | 12 | 2 | 55 | de-dup coarse |
| K2 | 152 | ~80 | 22 | 2 | 47 | finer de-dup |
| K3 | 143 | 73 | 18 | 2 | 50 | de-dup medium |
| M1 (modules 1-2 only) | 35 | 13 | 5 | 0 | 17 | incomplete cutoff |
| M2 (modules 1-11 of 13) | 150 | ~70 | ~25 | ~3 | ~52 | missing mcp-tools + agent-provisioning |
| I1 new | 14 | 0 | 2 | 8 | 4 | issue-driven additions |
| I2 new | 14 | 0 | 2 | 8 | 4 | issue-driven additions (high overlap with I1) |
| **Draft v1 (this doc)** | **~180** | **~80** | **~28** | **~12** | **~60** | folded, de-duped |

**Distribution pattern**: ~45% a, ~15% b, ~7% c, ~33% d. The c-class growth from K's 2 → draft's ~12 is the I-agent contribution (issue-tracked unimplemented promises).

---

## Module 1 — block-abc

**Source-of-record**: M1 (definitive; M2 also covered with slight variations)
**Final interface count**: 30 (M1 had 28; +2 from manager curation)
**Breakdown**: a=14, b=6, c=0, d=10

### Key decisions (b/c/d)
- `Block` class itself: **b-code-wins** (allowed_input_types default `[]` not `[DataObject]`, plus many ClassVars ARCH omits)
- `Block.validate`: **b-code-wins** (annotation `dict[str, Any]` vs ARCH `dict[str, Collection]`)
- `Block.postprocess`: **b-code-wins** (same pattern as validate)
- `Block.transition`: **d-document** (load-bearing, no method-level doc in ARCH §5.1)
- `Block.persist_array` / `persist_table`: **d-document** (ADR-031 Add 1 helpers, mentioned only at IOBlock level in ARCH §4.3)
- `IOBlock.load` signature: **b-code-wins** (`output_dir=""` param from ADR-031 D4 not in ARCH §5.3)
- `AIBlock`: **b-code-wins** (D1's `model: str, prompt_template: str` is pre-ADR-035; ARCH §5.3 + §7.6 need full rewrite per ADR-035)
- `SubWorkflowBlock`: **b-code-wins** (ClassVars + `_scheduler_factory` injection vs D1's nonexistent `WorkflowLoader` pattern)
- `CodeRunner` Protocol: **d-document** (ARCH §12 names entry-point but doesn't enumerate Protocol contract)
- `ExternalAppBridge` Protocol: **d-document** (4 methods unspecified)
- `RunDir` (AIBlock per-execution coord): **d-document** (ADR-035 spec'd, ARCH §7.6 abstract only — signal file layout not enumerated)
- `CompletionWatcher`: **d-document** (priority order MCP > FileWatcher > mark-done not in ARCH)
- `LLMProvider` / `AnthropicProvider` / `OpenAIProvider`: **d-remove** (dead post-ADR-035; AIBlock doesn't call these)
- `RunnerRegistry`, `FileExchangeBridge`, `FileWatcher`, `ProcessExitedWithoutOutputError`, `_PopenProcessAdapter`, `_sequential_execute`, `CompletionEvent`/`CompletionSource`/`WatcherCancelledError`: **d-private** (rename `_underscore`, remove from public spec)

### Manager-curation additions to M1's list
- (none — M1's 28 entries are complete)

### Issue-driven additions (I1/I2 confirmed)
- **`Block-ABC related: ADR-028 §D8 supported_extensions ClassVar`**: c-impl. New ClassVar `supported_extensions: ClassVar[dict[str, str]]` to declare per-class file-extension acceptance. Issue `#1074`. Currently 0% implemented (no ClassVar exists on IOBlock base or subclasses).
- **`block-abc.IOBlock._detect_format` helper**: c-impl. New helper that reads `supported_extensions` to dispatch by extension. Issue `#1073`. 0% impl.
- **`block-abc.IOBlock` per-subclass `supported_extensions` declarations** (LoadData, SaveData, LoadImage, SaveImage, plugin IO blocks): c-impl. Issue `#1075` / `#1076`. 0% impl.
- **`block-abc.iterate_over_axes` O(one-slice) contract drift**: b-docs-wins. ARCH §4.5.1 promises O(one slice + one output slice); code calls `to_memory()` on full source. Issue `#888`. Fix is code-side.
- **`block-abc.SubWorkflowBlock._scheduler_factory` injection contract**: c-defer (to ADR-017/022 Phase 5.2b). Issue `#890`.
- **`block-abc.AppBlock.bridge.prepare` dead JSON-dump fallback**: b-docs-wins. Issue `#1080`. Fix is code-side (remove fallback or implement properly).
- **`block-abc.AppBlock._bin_outputs_by_extension` Artifact downgrade**: b-docs-wins. Issue `#1079`.

### Open issue placeholders (Phase 9 turns into real issues)
`#TBD-block-class-vars-arch-update`, `#TBD-block-transition-document`, `#TBD-block-validate-annotation`, `#TBD-block-postprocess-annotation`, `#TBD-block-persist-helpers-document`, `#TBD-ioblock-load-output-dir`, `#TBD-aiblock-arch-update-for-adr-035`, `#TBD-subworkflow-classvar-vs-config`, `#TBD-coderunner-protocol-document`, `#TBD-runner-implementations-document`, `#TBD-runner-registry-private-marker`, `#TBD-externalappbridge-document`, `#TBD-fileexchangebridge-private-marker`, `#TBD-filewatcher-private-marker`, `#TBD-process-exited-error-private-marker`, `#TBD-llmprovider-legacy-removal`, `#TBD-aiblock-run-dir-protocol-document`, `#TBD-completion-watcher-document`, `#TBD-completion-internals-private-marker`, `#TBD-popen-adapter-private-marker`. Plus existing real issues: `#888`, `#890`, `#1073`, `#1074`, `#1075`, `#1076`, `#1079`, `#1080`.

→ **Verbatim signatures in Phase 6 SSOT**: lift from M1's §1 (lines 16-535 of `docs/audit/2026-05-17-spec-ssot-p2.5-M1.md`).

---

## Module 2 — port-system

**Source-of-record**: M1 (definitive)
**Final interface count**: 13
**Breakdown**: a=7, b=2, c=0, d=4

### Key decisions
- `InputPort.constraint`: **b-code-wins** (annotation `Callable[[Any], bool]` vs ARCH's `Callable[[DataObject], bool]`; runtime receives Collection per ADR-020)
- Two-phase validation, dynamic_ports, helpers — all **a**
- `Port.is_collection` field: **d-document** (code has it; D1 doesn't list)
- `validate_port_constraint`, `port_accepts_type`, `port_accepts_signature`, `validate_connection`, `ports_from_config_dicts`, `ConstraintFn` type alias: **d-document** (public functions not enumerated in ARCH §5.2)

### Issue-driven additions
- (none specific to port-system; covered under block-abc context)

→ **Verbatim signatures in Phase 6 SSOT**: lift from M1's §2 (lines 539-685 of M1).

---

## Module 3 — data-types

**Source-of-record**: M2 (only consolidator that reached this module)
**Final interface count**: 19 (per M2's count; C2 reported 19 contract surfaces)
**Breakdown** (per M2): mostly **a**, several **d-document** for private helpers and bridge properties

### Key decisions (from M2)
- 7 core DataObject types (DataObject, Array, Series, DataFrame, Text, Artifact, CompositeData): all **a** (well-aligned per D1 §4.1 + C2's inventory)
- `FrameworkMeta`: **a** (5 fields confirmed)
- `TypeSignature`, `TypeSpec`, `TypeRegistry`: **a** with d-document for `TypeRegistry.resolve()` overload
- `ChannelInfo`, `PhysicalQuantity`: **a**
- `DataObject._transient_data`, `_data` / `_arrow_table` bridge properties: **d-document** (load-bearing transitional surfaces)
- `with_meta_changes`, `_reconstruct_one`, `_serialise_one`, `_get_backend`, `_get_type_registry`: **d-private** (internal helpers)
- C2-flagged: `_serialise_one` raises ValueError if storage_ref is None except for Artifact with file_path — special-case behavior should be in d-document for `_serialise_one` if it's promoted from `_private`

### Manager override vs M2
- (none — M2's classifications align with C2 + D1)

### Issue-driven additions
- (none specific to data-types)

→ **Verbatim signatures in Phase 6 SSOT**: lift from M2's §3.

---

## Module 4 — storage-backends

**Source-of-record**: M2 (only consolidator)
**Final interface count**: 9 (per M2)
**Breakdown**: mostly **a**, one **b** for StorageReference frozen-mismatch

### Key decisions (from M2 + C2)
- `StorageBackend` Protocol (6 methods: read, write, slice, iter_chunks, get_metadata, write_from_memory): **a**
- `StorageReference`: **b-docs-wins** (C2: docstring calls it "immutable" but dataclass NOT `frozen=True`. Fix is code-side: add `frozen=True` to match documented intent)
- `ZarrBackend`, `ArrowBackend`, `FilesystemBackend`: **a** (atomic-write behavior consistent with described intent for Zarr+Filesystem; ArrowBackend not atomic — flag in d-document for behavior nit)
- `CompositeStore.iter_chunks`: **b-docs-wins** (silently ignores `chunk_size`, yields `(slot_name, data)` tuples — semantically inconsistent with other backends; fix code-side OR document the exception)
- `CompositeStore.write` non-atomic: **b-docs-wins** (manifest written last — fix code-side or document the gap; M2 + C2 flag this)
- `BackendRouter` default mappings: **a**
- `flush_context` module-level global: **d-document** (thread-safety + subprocess assumptions undocumented)

### Manager override vs M2
- (none)

→ **Verbatim signatures in Phase 6 SSOT**: lift from M2's §4.

---

## Module 5 — collection-transport

**Source-of-record**: M2
**Final interface count**: 6 (per M2)
**Breakdown**: a=3, d=3

### Key decisions (from M2 + C3)
- `Collection` class: **a** (NOT a DataObject; `__slots__` + `__class_getitem__` returning bare class for type annotations)
- `Collection.storage_refs` (plural): **d-document** (naming asymmetry vs DataObject `storage_ref` singular — capture in spec)
- `LazyList`: **a** (memory-safe iteration; consistent with ARCH §6.2)
- `Block.pack` / `unpack` / `unpack_single` / `map_items` / `parallel_map`: cross-listed under block-abc (lives on Block class); spec entry here is a redirect to block-abc canonical entry
- `Block._auto_flush`: cross-listed under block-abc
- `flush_context`: cross-listed under storage-backends
- 3-tier memory safety model: described concept entry (referencing ARCH §6.2)
- Built-in collection-operation blocks (MergeCollection, SplitCollection, FilterCollection, SliceCollection, MergeBlock, SplitBlock, DataRouter, PairEditor): registered via `scieasy.blocks` entry-points; not separate spec entries (they implement ProcessBlock contract from block-abc)

### Manager override
- I3 cross-listings need explicit redirect lines in Phase 6 to avoid Phase 4 audit double-counting

### Issue-driven additions
- **LazyList `.view()` post-ADR-031**: b-code-wins. Issue `#661` (Block SDK `_data` pattern in docs still references; 32 sites across 14 files). Sub-label: d-remove (32 doc sites to clean).
- **#1078 `core.materialisation` module** (NEW): c-impl. `materialise_to_file` / `reconstruct_from_file` proposed to fix AppBlock bridge dead JSON-dump fallback. 0% impl. This is a NEW module the cascade hasn't categorized — manager assigns to collection-transport (closest fit for transport-related materialisation).

→ **Verbatim signatures in Phase 6 SSOT**: lift from M2's §5 + add new entry for `core.materialisation` (signature from issue #1078).

---

## Module 6 — block-registry

**Source-of-record**: M2
**Final interface count**: 8 (per M2)
**Breakdown**: a=3, b=1, d=4

### Key decisions (from M2 + C3)
- `BlockRegistry`: **a** (scan, hot_reload, packages, specs_by_package)
- `BlockSpec`: **b-code-wins** (C3 flag: `BlockSpec.source` is de-facto enum typed as `str` — values "builtin"/"tier1"/"entry_point"/"monorepo". Spec should be `Literal[...]`. Fix is code-side to add Literal type.)
- `PackageInfo` dataclass: **a**
- `BlockRegistrationError`: **a**
- `BlockTestHarness` (`scieasy.testing.harness`): **d-document** (C3 flag: `smoke_test` does NOT auto-wrap inputs — capture in spec; callers supply Collection directly)
- **Entry-point groups**: `scieasy.blocks`, `scieasy.types`, `scieasy.runners` — **a** in concept
  - But C3 flag: 14 of 14 core `scieasy.blocks` entry-points are direct class references, NOT `(PackageInfo, list[Block])` callables. `BlockRegistry._packages` is always `{}` for core blocks. **b-docs-wins**: ARCH §5.4 describes the callable protocol as the standard; core uses direct class refs. Either ARCH should describe both forms OR core entry-points should be migrated.
- `scieasy.types` empty in core: **a** (confirmed; all domain types in plugins per ADR-027 D2)
- `scieasy.runners` callable contract: **d-document** (CodeRunner Protocol cross-listed under block-abc d-document)

### Manager override
- (none)

### Issue-driven additions
- **#1077 `BlockRegistry.find_loader` / `find_saver` / `find_io_blocks_for_type`**: c-impl. 3 new BlockRegistry methods proposed per ADR-028 §D8. 0% impl. K-agents missed this entirely.

→ **Verbatim signatures in Phase 6 SSOT**: lift from M2's §6 + add new entries for `find_loader`/`find_saver`/`find_io_blocks_for_type` (signatures from #1077).

---

## Module 7 — execution-engine

**Source-of-record**: M2
**Final interface count**: 27 (per M2; C4 reported 47 — M2 grouped sub-surfaces)
**Breakdown**: a=8, b=8, c=0, d=11

### Key decisions (from M2 + C4 + I1/I2)
- `EngineEvent`: **a**
- `EventBus`: **a**
- 17 named event-type constants: **b-docs-wins** (C4 flag: `CHECKPOINT_SAVED` + `BLOCK_READY` defined but never emitted — fix is code-side: emit or remove)
- `DAG` internal dataclass + `build_dag` / `topological_sort` / `CycleError` / `get_downstream_blocks` / `get_root_nodes` / `get_leaf_nodes`: **d-document** (engine internals, but `build_dag`/`topological_sort` are public — escalate to d-document)
- `DAGScheduler`: **b-code-wins** (C4 flag: constructor has 9 params, ARCH §6.1 lists 5 — code has truth; ARCH update needed)
- `RunHandle`: **d-private** (C4 flag: BlockRunner.run() currently returns `dict[str, Any]`; RunHandle is future-evolution placeholder. Mark private until actually used.)
- `ResourceRequest`, `ResourceSnapshot`: **a**
- `ResourceManager`: **b-code-wins** (C4 + xcheck flag: `memory_high_watermark` class docstring says 0.80, code default is 0.90 — code wins, doc update needed)
- `WorkflowCheckpoint`: **b-code-wins** (C4 flag: `pending_block` + `config_snapshot` always written as None/{} — either drop fields or implement)
- `CheckpointManager`: **b-code-wins** (C4 flag: `list_checkpoints()` doesn't exist; spec should not promise it)
- `serialize_intermediate_refs` / `deserialize_intermediate_refs`: **d-document**
- `BlockRunner` Protocol: **a**
- `LocalRunner`: **a**
- `Worker stdout envelope` JSON shape: **a** (verified by C4)
- `ProcessHandle`, `ProcessExitInfo`, `ProcessRegistry`: **a**
- `ProcessMonitor`: **b-docs-wins** (C4 flag: `poll_interval_sec` hardcoded 1.0, no constructor param — fix is code-side to make configurable per documented intent)
- `spawn_block_process` (sync): **a**
- `register_async_process`, `build_worker_payload`: **d-document**
- `PlatformOps` Protocol + `PosixOps` / `WindowsOps` / `get_platform_ops`: **d-document** (cross-platform protocol unspecified in ARCH)
- `BlockTerminalStateReportedError`: **a** (issue #681 contract)
- `PtyTabSpec` / `request_pty_tab` / `notify_block_pty_event`: **b-docs-wins** (C4 flag: uses HTTP loopback with `SCIEASY_ENGINE_API_URL` + `SCIEASY_ENGINE_IPC_TOKEN`, not stdin/stdout per ARCH §7. Doc-fix to document the HTTP transport.)
- `engine.lineage_recorder` shim: **d-remove** (scheduled removal 2026-11-15 per C5)
- Worker internals (reconstruct_inputs, serialise_outputs, main): **d-private**

### Manager override vs M2
- (none)

### Issue-driven additions
- **#887 `ResourceManager.acquire()` zero callers**: b-code-wins. Manager confirms I-agents' upgrade from K's `a` to b. Add open issue.

→ **Verbatim signatures in Phase 6 SSOT**: lift from M2's §7. Manager re-verify C4's 47-iface count to ensure no public surface missed.

---

## Module 8 — lineage-db

**Source-of-record**: M2 (+ C5 for SQL schemas)
**Final interface count**: 11 (per M2)
**Breakdown**: mostly **a** — module is well-aligned post-ADR-038

### Key decisions
- All 4 SQL tables (runs, block_executions, data_objects, block_io) — full CREATE TABLE: **a** (M2 lifted from C5, which verified column-by-column against ARCH §4.4)
- `LineageStore`: **a** (per-call connection open/close for file mode, single persistent for :memory:)
- Per-table record dataclasses (`RunRecord`, `BlockExecutionRecord`, `DataObjectRow`, `BlockIORow`): **a**
- `EnvironmentSnapshot`: **a** (5 fields per ADR-038 §3.4)
- `LineageRecorder`: **a** (event-driven; idempotent `dispose()`)
- `RunContext` + `get_run_context` / `set_run_context` / `reset_run_context`: **d-document** (load-bearing for engine/recorder wiring; not in ARCH §4.4)
- `render_methods_markdown`: **d-document** (methods-export function not enumerated in ARCH §4.4)
- `MetadataStore` shim: **d-remove** (scheduled removal 2026-11-15; pre-ADR-038 compat)
- C5 flags: `data_objects.size_bytes` and `mtime_at_write` never populated by recorder (always None) — minor d-document for behavior note

### Issue-driven additions
- (none specific to lineage-db)

→ **Verbatim signatures in Phase 6 SSOT**: lift from M2's §8.

---

## Module 9 — versioning-git

**Source-of-record**: M2 (+ C5 for full GitEngine method enumeration)
**Final interface count**: 12 (per M2)
**Breakdown**: mostly **d-document** + 2 **b** + 2 **d-remove**

### Key decisions (from M2 + C5 — confirmed d-class module)
- `GitEngine` class with 20+ public methods (init_repository, is_repository, commit, log, diff, restore, head_state, status, current_branch, branches, branch_create, branch_switch, branch_delete, merge, cherry_pick, merge_stage_file, merge_complete, merge_abort, stash_list, stash_save, stash_apply, stash_drop): **d-document** (entire surface documented only in docstrings; ARCH §4.6 has design intent + per-platform table but no method list)
- `HeadState`, `MergeResult` (type alias): **d-document**
- `GitError`: **d-document**
- `BundledGitMissing`: **d-document**
- `GitBinary` (binary discovery): **d-document** (4 discovery paths: SCIEASY_GIT_BUNDLE_ROOT → PyInstaller → `<repo>/desktop/` walkup → `shutil.which("git")`)
- `DEFAULT_GITIGNORE` / `write_default_gitignore`: **d-document**
- `is_dirty` / `modified_files`: **d-document**
- Commit prefix convention (`auto:` / `agent:` / no-prefix): **d-document** (cited in ARCH §4.6 prose, no normative spec)
- **`git_author.json`**: **c-drop** (M2 + C5 confirm: this file does NOT exist in code; identity is hardcoded as `_DEFAULT_AUTHOR_NAME = "SciEasy User"` / `_DEFAULT_AUTHOR_EMAIL = "noreply@scieasy.local"`. Spec should NOT promise the JSON file. Fix is doc-side — remove the promise from ARCH §4.6.)
- **`watcher.py` / `GitChangeWatcher`** (in versioning-git): **d-remove** (collapsed into `api/routes/workflow_watcher.py`; PROJECT_TREE.md outdated)
- `no_git` marker: **d-document** (path inlined in runtime.py, not a named constant)

### Manager override vs M2
- (none — M2 + C5 + xcheck all agree this module is heavily d-class)

### Issue-driven additions
- (none specific to versioning-git)

→ **Verbatim signatures in Phase 6 SSOT**: lift from M2's §9 + C5's full GitEngine method enumeration. **Phase 4 audit**: confirm method list is complete vs current code (C5 captured 20+; verify no method missed).

---

## Module 10 — rest-api

**Source-of-record**: M2 (+ C6 for full route inventory)
**Final interface count**: 16 sections, ~85 routes + ~30 Pydantic schemas + 9 Typer commands
**Breakdown**: mostly **a** (post-ADR-040, well-aligned) + several **d** + 3 **b** FE-BE drifts

### Key decisions (from M2 + C6 + I1/I2)
- 14 workflow routes (WF-001..014): **a**
- 4 block routes (BLK-001..004): **a**
- 7 project routes (PROJ-001..007): **a**
- 3 data routes (DATA-001..003): **a**
- 4 filesystem routes (FS-001..004): **a**
- 1 AI route (AI-001 `GET /api/ai/status`): **a**
- 1 lint route (LINT-001 `POST /api/lint/python`): **a**
- 5 runs routes (RUNS-001..005): **a** but RUNS-005 (run detail) returns untyped dict from lineage store — **d-document** for the wire shape
- 18 git routes (GIT-001..018): **a**
- Pydantic request/response schemas: **a** for the 27 in active use; **d-remove** for `CancelBlockRequest` + `CancelWorkflowRequest` (C6 flag: dead weight, no route uses them)
- **Frontend `DynamicPortsConfig`**: **b-docs-wins** (TS-side adds `input_port_mapping` field absent from backend Pydantic. Fix: backend adds the field OR frontend drops it — let backend lead since ARCH §5.4 specifies the descriptor shape.)
- **Frontend `TypeHierarchyEntry.ui_ring_color`**: **b-code-wins** (TS declares; backend never populates — code is the truth; remove TS field.)
- **Frontend `LineageRunDetail` vs backend raw dict** (RUNS-005): **b-code-wins** (TS expects typed `LineageBlockExecution[]` with `duration_ms`; backend returns raw `dict` — code wins, frontend type should be `unknown`/`dict` until backend wraps. OR backend wraps in Pydantic.)
- **Frontend `LineageRerunResponse.new_run_id`**: **b-code-wins** (TS expects field; backend returns `{rerun_of, workflow_id, execute_from_block_id, result}` — no `new_run_id`. Frontend type fix.)
- 9 Typer CLI commands (`scieasy gui`, `serve`, `validate`, `run`, `init`, `install`, `mcp-bridge`, `init-block-package`, hidden helpers): **a**
- `ApiRuntime` internal class (create_project, open_project, refresh_block_registry, etc.): **d-document** (load-bearing, not in ARCH §8)
- `SPAStaticFiles` + lifespan + create_app + deps: **a**
- Frontend Zustand slices (10 actual vs ARCH §9.10's 7): **b-code-wins** (`chatSlice` doesn't exist; code adds `gitSlice`, `lineageSlice`, `tabSlice`, `terminalTabsSlice`. Doc update.)

### Issue-driven additions
- **#889 `validate_connection` REST endpoint ignores `get_effective_*_ports`**: b-code-wins. New entry — REST validation path not in any K report. Fix is code-side.
- **#827 `configure_logging` stub**: c-impl. NotImplementedError stub — should be implemented per documented intent.

→ **Verbatim signatures in Phase 6 SSOT**: lift from M2's §10 + C6's full per-route inventory.

---

## Module 11 — ws-sse-protocol

**Source-of-record**: M2 (+ C6 for message envelope details)
**Final interface count**: 8 sections, ~13 outbound + ~5 inbound messages + 2 PTY + 1 SSE
**Breakdown**: mostly **a**

### Key decisions (from M2 + C6)
- WebSocket `/ws` endpoint: **a**
- Outbound message envelope (`{type, ...}` discriminator): **a**
- 13 outbound message types (block_state, interactive_prompt, cancel_propagation, workflow.changed, git.head_changed, run.started/done/failed, agent_event, etc.): **a**
- 5 inbound message types (cancel_block, cancel_workflow, interactive_complete, user_message, permission_decision): **a**
- PTY WebSocket `/api/ai/pty/{tab_id}` JSON text frames: **a**
- PTY-IPC internal HTTP routes (referenced by C4 for execution-engine PtyTabSpec): cross-listed under execution-engine
- SSE log-stream `GET /api/logs/stream`: **a**
- Frontend Zustand slices: cross-listed under rest-api

### C6 flags
- `block_pty_opened` + `block_pty_closed` broadcaster messages BYPASS EventBus (sent directly): **d-document** (architectural inconsistency vs `/ws` EventBus-routed)
- `block_user_cancel` writes same `mark_done.json` signal as `block_user_marked_done` — full cancel propagation deferred per source note: **b-docs-wins** (document the limitation)

### Issue-driven additions
- (none specific to ws-sse)

→ **Verbatim signatures in Phase 6 SSOT**: lift from M2's §11.

---

## Module 12 — mcp-tools

**Source-of-record**: M2 §12 (M2 DID cover all 13 modules; my earlier grep missed §12/§13 due to awk range bug). Manager re-verified post-draft against C7's verbatim inventory.
**Final interface count**: ~30 (26 tools + 4 supporting interfaces)
**Breakdown**: a=22, b=1, c=1, d=6

### Key decisions (from C7)
- **26 `@mcp.tool` decorators** confirmed across 4 modules:
  - `tools_workflow.py` (10): `list_blocks`, `get_block_schema`, `list_types`, `get_workflow`, `validate_workflow`, `write_workflow`, `run_workflow`, `cancel_run`, `get_run_status`, `finish_ai_block`
  - `tools_authoring.py` (5): `read_block_source`, `list_block_examples`, `scaffold_block`, `reload_blocks`, `run_block_tests`
  - `tools_inspection.py` (7): `get_block_output`, `inspect_data`, `preview_data`, `get_lineage`, `get_block_config`, `update_block_config`, `get_block_logs`
  - `tools_qa.py` (4): `search_docs`, `get_doc`, `list_data`, `get_project_info`
- All 26 with Pydantic return models: **a** (post-ADR-040 contract; `_registry.py` removed)
- **`scaffold_block` widened signature** (input_ports + output_ports per ADR-040 §3.2a): **a**
- **`warnings: list[str]` on `ScaffoldBlockResult`**: **a**
- **`next_step: str` on write-class tool result models** (`WriteWorkflowResult`, `RunWorkflowResult`, etc.): **a**
- **`finish_ai_block` (26th tool)**: **b-docs-wins** (xcheck: ARCH §7.2 category (a) table claims 6R/3W = 9 tools, code has 6R/4W = 10. ARCH update needed to list `finish_ai_block`.)
- **`MCPContext` Protocol**: **b-code-wins** (C7 flag: only 3 declared attributes — `block_registry`, `type_registry`, `project_dir`. `scheduler`, `event_bus`, `workflow_runs`, `ai_block_run_dir` accessed via `getattr` fallbacks — NOT in Protocol. Either expand Protocol or document the fallback pattern. Code is current behavior.)
- `MCPServer` (FastMCP wrapper): **a** (post-ADR-040 thin wrapper)
- `StandaloneMCPRuntime` + `make_mcp_runtime` + `start_inprocess_server` + `stop_inprocess_server`: **a**
- `compose_system_prompt`, `_load_skill_md`, `_render_tool_catalog`, `_render_project_context`, `_splice_catalog`, `_TOOL_CATALOG_BEGIN/END`, `_PROJECT_CONTEXT_BEGIN/END` constants: **a** (well-documented in ADR-040 §3.3 / §3.4)
- `terminal.py::_write_system_prompt_tempfile`, `_ensure_mcp_config`, `spawn_claude`, `spawn_codex`: **a**
- `mcp.json` wire format (sys.executable anchored): **a**
- `mcp_bridge` subcommand: **a**
- **`list_block_runs` ghost tool**: **c-drop** (C7 flag: static fallback catalog in SKILL.md lines 103 lists this — but tool doesn't exist. The 7th inspection tool is `get_block_logs`. Spec drops this from inspection category list.)
- **`scieasy-inspect-data` skill claims `preview_data(ref, max_rows?, max_dim?)`**: **b-code-wins** (Code signature is `preview_data(ref, fmt)`. Skill body is wrong; fix is skill content side.)

### Issue-driven additions
- (none specific to mcp-tools beyond what C7 flagged)

### Phase 4 audit attention
M2 + C7 both cover this module — Phase 4 A-agent cross-checks both inventories. Special attention: the `MCPContext` Protocol gap (3 declared vs 7 used via getattr fallback) needs design decision in Phase 5.

→ **Verbatim signatures in Phase 6 SSOT**: lift from C7's full inventory.

---

## Module 13 — agent-provisioning

**Source-of-record**: M2 §13 (M2 covered) + C7 verbatim inventory (cross-check)
**Final interface count**: ~20 (orchestrator + 6 hooks + 6 skills + Codex config + version marker + lifecycle wiring)
**Breakdown**: a=8, b=1, c=0, d=11

### Key decisions (from C7)
- `install_project_agent_assets(project_dir, *, force=False) -> ProvisionResult`: **a**
- `ProvisionResult` dataclass (written/skipped/failed/version): **a**
- `SCIEASY_PROVISION_VERSION = "0.1.0"` constant: **a**
- Version-marker file `<project>/.claude/.scieasy-provision-version` content = `"0.1.0"`: **a**
- 6 hook scripts in `templates/hook_*.py`: **d-document** each (matcher patterns, exit-code semantics, stdin JSON shapes, session-marker side effects — all documented in ADR-040 §3.6 but no enumeration in ARCH §10.2)
  - `hook_deny_scieasy_cli` (PreToolUse Bash)
  - `hook_protect_workflow_yaml` (PreToolUse Edit|Write)
  - `hook_enforce_list_blocks_before_block_write` (PreToolUse Edit|Write|Bash|scaffold_block; session-keyed marker)
  - `hook_remind_poll_status` (PostToolUse run_workflow)
  - `hook_mark_list_blocks_called` (PostToolUse list_blocks; writes session marker)
  - `hook_enforce_concrete_port_types` (PostToolUse Edit|Write|scaffold_block; AST scan)
- Session-marker path `<project>/.scieasy/.session-state/<session_id>/list_blocks_called`: **d-document**
- `.claude/settings.json` template structure: **d-document**
- `.codex/config.toml` rendered content: **d-document**
- 6 SKILL.md files (base + 5 task skills): **d-document** (frontmatter + marker conventions)
- Lifecycle callsites (`create_project`, `open_project`, `scieasy init`): **a** (post-ADR-040 wiring, well-documented in ADR §3.8)
- **`claude_agents_md.md` template stale on Codex hook deferral**: **b-code-wins** (C7 flag: template text says Codex hooks are deferred to #1015 but `write_codex_config` actually DOES provision them. Fix: update template text.)

### Issue-driven additions
- **#1015 Layer 7 filesystem ACL on `<project>/blocks/`**: c-defer (ADR-041 placeholder per ADR-040 §3.10)
- **#1016 BlockRegistry runtime rejection of `DataObject`-typed ports**: c-defer (ADR-041 placeholder)

### Phase 4 audit attention
M2 + C7 both cover this — Phase 4 A-agent cross-checks both inventories.

→ **Verbatim signatures in Phase 6 SSOT**: lift from C7's full inventory.

---

## Cross-cutting: ADR-028 §D8 cluster (NEW, from I1+I2 independent confirmation)

The biggest finding from issue-investigators. ADR-028 §D8 documents a binding decision; code has 0% implementation. 5 chained open issues:

| Issue | Interface | Module | Class |
|---|---|---|---|
| #1073 | `IOBlock._detect_format` helper | block-abc | c-impl |
| #1074 | `IOBlock.supported_extensions: ClassVar[dict[str, str]]` | block-abc | c-impl |
| #1075 | Per-IO-block `supported_extensions` declarations (LoadData, SaveData) | block-abc | c-impl |
| #1076 | Per-plugin-IO-block `supported_extensions` declarations | (plugin scope — flagged for follow-up cascade) | c-impl |
| #1077 | `BlockRegistry.find_loader` / `find_saver` / `find_io_blocks_for_type` | block-registry | c-impl |
| #1078 | `core.materialisation` module (`materialise_to_file` / `reconstruct_from_file`) | collection-transport (new sub-module) | c-impl |

All 6 entries already folded into the respective module sections above.

---

## Other I1/I2 confirmed entries (folded above; summary table)

| Interface | Module | Class | Issue |
|---|---|---|---|
| `iterate_over_axes` O(slice) drift | block-abc | b-docs-wins | #888 |
| `ResourceManager.acquire()` zero callers | execution-engine | b-code-wins | #887 |
| `SubWorkflowBlock._scheduler_factory` injection | block-abc | c-defer | #890 |
| `validate_connection` REST endpoint | rest-api | b-code-wins | #889 |
| `configure_logging` stub | rest-api | c-impl | #827 |
| `LineageView` / `JobsPanel` UI placeholders | rest-api (frontend) | c-defer | #835 |
| `useSSE` / `useWebSocket` reconnection contract | rest-api (frontend) | d-document | #177 |
| PROJECT_TREE.md `proxy.py ViewProxy` annotation | data-types (PROJECT_TREE) | d-remove | #908 |
| Block SDK `_data` pattern in docs | data-types | d-remove (32 sites) | #661 |
| AppBlock `bridge.prepare` dead JSON-dump fallback | block-abc | b-docs-wins | #1080 |
| AppBlock `_bin_outputs_by_extension` Artifact downgrade | block-abc | b-docs-wins | #1079 |
| Layer 7 filesystem ACL | agent-provisioning | c-defer (ADR-041) | #1015 |
| BlockRegistry runtime DataObject-port rejection | agent-provisioning | c-defer (ADR-041) | #1016 |

---

## Known gaps for Phase 4 audit attention

1. **Correction**: M2 actually covered ALL 13 modules (138 interfaces); manager initial grep missed §12/§13 due to awk range bug. Draft v1 modules 12+13 reference M2 + C7 cross-check.
2. **M1's depth on modules 1-2** is higher than M2's. For Phase 6, lift detailed signatures from M1 for modules 1-2.
3. **xcheck Section 3 (ARCH↔ADR conflicts)** flagged 3 disagreements logged for follow-up cascade — NOT reconciled in this cascade.
4. **`src/scieasy/workflow/`** was flagged orphan by S1 but C6 confirmed LIVE — corrected. Module 9 (rest-api) entry covers the workflow Pydantic models via API path.

## Acceptance criteria for draft v1 → v2 (manager-fix in Phase 5)

- Every Phase 4 P1 finding resolved (or explicit reject with reason)
- Every K-disagreement that surfaced new evidence in Phase 4 re-classified
- Every `#TBD-*` placeholder mapped to a real GitHub issue number (deferred to Phase 9, but planning placeholder list locked here)
- Aggregate count finalized (~180 → finalized count)

## Acceptance criteria for draft v2 → Phase 6 (post Codex cross-check)

- Codex's draft v2 received from user
- Cross-cascade-manager comparison: which entries diverge in label or signature
- Any divergence: third-eye check (re-read source reports), pick winner
- Convergent SSOT entries proceed to verbatim signature lifting
- Divergent SSOT entries: manager + user joint decision

---

## Source reports (cross-reference)

For Phase 4 / Phase 6 — full verbatim signatures live here:

- `docs/audit/2026-05-17-spec-ssot-p1-modules.md` — module taxonomy
- `docs/audit/2026-05-17-spec-ssot-p1.5-code-C1.md` — block-abc + port-system (41 ifaces)
- `docs/audit/2026-05-17-spec-ssot-p1.5-code-C2.md` — data-types + storage-backends (27)
- `docs/audit/2026-05-17-spec-ssot-p1.5-code-C3.md` — collection-transport + block-registry
- `docs/audit/2026-05-17-spec-ssot-p1.5-code-C4.md` — execution-engine (47)
- `docs/audit/2026-05-17-spec-ssot-p1.5-code-C5.md` — lineage-db + versioning-git
- `docs/audit/2026-05-17-spec-ssot-p1.5-code-C6.md` — rest-api + ws-sse-protocol (42 routes + 13 WS)
- `docs/audit/2026-05-17-spec-ssot-p1.5-code-C7.md` — mcp-tools + agent-provisioning (26 tools)
- `docs/audit/2026-05-17-spec-ssot-p1.5-docs.md` — D1 docs-view, all 13 modules (102KB)
- `docs/audit/2026-05-17-spec-ssot-p1.5-xcheck.md` — X1 cross-check inconsistencies
- `docs/audit/2026-05-17-spec-ssot-p2-K1.md` / K2.md / K3.md — Phase 2 triple classifications
- `docs/audit/2026-05-17-spec-ssot-p2.5-M1.md` — modules 1-2 verbatim (incomplete cutoff)
- `docs/audit/2026-05-17-spec-ssot-p2.5-M2.md` — modules 1-11 verbatim (missing 12-13)
- `docs/audit/2026-05-17-spec-ssot-p2-issues-I1.md` — issue-driven additions
- `docs/audit/2026-05-17-spec-ssot-p2-issues-I2.md` — issue-driven additions (independent)
