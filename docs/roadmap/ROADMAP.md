# SciEasy — Roadmap

> **Guiding rule**: each milestone produces something testable. No milestone is
> "write a bunch of code and hope it works at the end." Every phase ends with
> a green CI.

---

## Phase 0 — Repository bootstrap

**Goal**: a clean repo that anyone can clone, install, and run an empty test suite against.

### 0.1 Project scaffolding

- [ ] Create `pyproject.toml` with package metadata, dependencies, and `[project.scripts]` entry
- [ ] Create `src/scieasy/__init__.py` with version string
- [ ] Create every directory and `__init__.py` listed in `docs/PROJECT_TREE.md` — no classes, just empty files with module docstrings explaining purpose
- [ ] Create `frontend/package.json` with React + ReactFlow + TypeScript + Tailwind dependencies (no components yet)
- [ ] Create `tests/conftest.py` with a placeholder fixture
- [ ] Copy `docs/ARCHITECTURE.md`, `docs/ADR.md`, `docs/PROJECT_TREE.md` into repo

### 0.2 Tooling configuration

- [ ] Configure `ruff` in `pyproject.toml` (linting + formatting rules)
- [ ] Configure `mypy` in `pyproject.toml` (strict mode on `src/scieasy/`)
- [ ] Configure `pytest` in `pyproject.toml` (test paths, markers)
- [ ] Create `.pre-commit-config.yaml` (ruff + mypy on staged files)
- [ ] Create `Makefile` with shortcuts: `make lint`, `make typecheck`, `make test`, `make serve`

### 0.3 CI pipeline

- [ ] Create `.github/workflows/ci.yml`:
  - ruff check
  - mypy check
  - pytest (empty suite should pass)
- [ ] Verify: push to GitHub → CI green ✅

### Deliverable

```
git clone → pip install -e ".[dev]" → make lint → make typecheck → make test
All green. Zero implementation, zero failures.
```

---

## Phase 1 — Interface skeleton

**Goal**: every ABC, Protocol, Enum, and Pydantic model exists with complete type hints and docstrings. All method bodies are `raise NotImplementedError`. The codebase is a **compilable, type-checkable spec** that Claude can inherit from without reading docs.

### 1.1 Core type hierarchy

- [ ] `core/types/base.py` — `DataObject` ABC, `TypeSignature`, `StorageReference`
- [ ] `core/types/array.py` — `Array(DataObject)` with `axes`, `shape`, `ndim`, `dtype`, `chunk_shape`
- [ ] `core/types/series.py` — `Series(DataObject)` with `index_name`, `value_name`, `length`
- [ ] `core/types/dataframe.py` — `DataFrame(DataObject)` with `columns`, `row_count`, `schema`
- [ ] `core/types/text.py` — `Text(DataObject)`with content, format, encoding
- [ ] `core/types/artifact.py` — `Artifact(DataObject)`with file_path, mime_type, description
- [ ] `core/types/composite.py` — `CompositeData(DataObject)` with `slots`, `get()`, `set()`, `slot_types()`
- [ ] `core/types/registry.py` — `TypeRegistry` class with `register()`, `resolve()`, `all_types()` signatures
- [ ] Domain types as one-liner subclasses: `Image(Array)`, `Spectrum(Series)`, `PeakTable(DataFrame)`, `MSImage(Array)`, `AnnData(CompositeData)`, etc.

### 1.2 Storage and proxy interfaces

- [ ] `core/storage/base.py` — `StorageBackend` Protocol (read, write, slice, iter_chunks, metadata)
- [ ] `core/storage/ref.py` — `StorageReference` dataclass
- [ ] `core/storage/zarr_backend.py` — class signature only, all methods `NotImplementedError`
- [ ] `core/storage/arrow_backend.py` — class signature only
- [ ] `core/storage/filesystem.py` — class signature only
- [ ] `core/storage/composite_store.py` — class signature only
- [ ] `core/proxy.py` — `ViewProxy` with `slice()`, `iter_chunks()`, `to_memory()`, `shape`, `axes`

### 1.3 Lineage interfaces

- [ ] `core/lineage/record.py` — `LineageRecord` dataclass, `EnvironmentSnapshot` dataclass
- [ ] `core/lineage/environment.py` — `EnvironmentSnapshot` with `capture()` classmethod
- [ ] `core/lineage/store.py` — `LineageStore` with `write()`, `query()`, `ancestors()` signatures
- [ ] `core/lineage/graph.py` — `ProvenanceGraph` signatures

### 1.4 Block system interfaces

- [ ] `blocks/base/state.py` — `BlockState` (8 states incl. CANCELLED, SKIPPED; ADR-018), `ExecutionMode`, `InputDelivery` enums
- [ ] `blocks/base/ports.py` — `Port`, `InputPort`, `OutputPort` dataclasses with `accepted_types`, `constraint`, Collection-transparent type checking
- [ ] `blocks/base/config.py` — `BlockConfig` Pydantic model
- [ ] `blocks/base/result.py` — `BlockResult` dataclass
- [ ] `blocks/base/block.py` — `Block` ABC with `validate()`, `run()`, `postprocess()`, Collection utilities: `pack()`, `unpack()`, `map_items()`, `parallel_map()` (ADR-020)
- [ ] `blocks/io/io_block.py` — `IOBlock(Block)` with `direction` field
- [ ] `blocks/process/process_block.py` — `ProcessBlock(Block)`
- [ ] `blocks/code/code_block.py` — `CodeBlock(Block)` with `InputDelivery` handling signatures
- [ ] `blocks/app/app_block.py` — `AppBlock(Block)` with bridge protocol signatures
- [ ] `blocks/ai/ai_block.py` — `AIBlock(Block)`
- [ ] `blocks/subworkflow/subworkflow_block.py` — `SubWorkflowBlock(Block)`
- [ ] `blocks/registry.py` — `BlockSpec` dataclass, `BlockRegistry` with `scan()`, `instantiate()`, `hot_reload()`, `all_specs()`

### 1.5 Format adapter and code runner interfaces

- [ ] `blocks/io/adapters/base.py` — `FormatAdapter` Protocol (read → DataObject, write → file)
- [ ] `blocks/io/adapter_registry.py` — `AdapterRegistry` with `register()`, `get_for_extension()`
- [ ] `blocks/code/runners/base.py` — `CodeRunner` Protocol (execute_inline, execute_script)
- [ ] `blocks/code/runners/runner_registry.py` — `RunnerRegistry`
- [ ] `blocks/code/introspect.py` — `introspect_script()` signature
- [ ] `blocks/app/bridge.py` — `ExternalAppBridge` Protocol
- [ ] `blocks/app/watcher.py` — `FileWatcher` signature

### 1.6 Engine interfaces

- [ ] `engine/dag.py` — `build_dag()`, `topological_sort()` signatures
- [ ] `engine/scheduler.py` — `DAGScheduler` with `execute()`, `pause()`, `resume()`, `cancel_block()`, `cancel_workflow()` signatures (ADR-018, event-driven)
- [ ] `engine/resources.py` — `ResourceRequest` dataclass, `ResourceManager` with `acquire()`, `release()`, EventBus auto-release
- [ ] `engine/runners/base.py` — `BlockRunner` Protocol (run → RunHandle, check_status, cancel)
- [ ] `engine/runners/local.py` — `LocalRunner(BlockRunner)` — isolated subprocess execution (ADR-017)
- [ ] `engine/runners/worker.py` — subprocess entry point (ADR-017)
- [ ] `engine/runners/process_handle.py` — `ProcessHandle`, `ProcessExitInfo`, `ProcessRegistry`, `spawn_block_process()` (ADR-019)
- [ ] `engine/runners/process_monitor.py` — `ProcessMonitor` background coroutine (ADR-019)
- [ ] `engine/runners/platform.py` — `PlatformOps` protocol + `PosixOps` + `WindowsOps` (ADR-019)
- [ ] `engine/checkpoint.py` — `WorkflowCheckpoint` dataclass (incl. skip_reasons; ADR-018), `save()`, `load()` signatures
- [ ] `engine/events.py` — `EngineEvent` dataclass, `EventBus` with `emit()`, `subscribe()`, 14 event type constants (ADR-018)

### 1.7 Workflow definition interfaces

- [ ] `workflow/definition.py` — `WorkflowDefinition`, `NodeDef`, `EdgeDef` dataclasses
- [ ] `workflow/serializer.py` — `load_yaml()`, `save_yaml()` signatures
- [ ] `workflow/validator.py` — `validate_workflow()` signature
- [ ] `workflow/layout.py` — `LayoutInfo` dataclass

### 1.8 API interface stubs

- [ ] `api/app.py` — FastAPI app factory (empty, but importable)
- [ ] `api/schemas.py` — Pydantic request/response models for all endpoints
- [ ] `api/routes/workflows.py` — route signatures with `raise NotImplementedError`
- [ ] `api/routes/blocks.py` — route signatures
- [ ] `api/routes/data.py` — route signatures
- [ ] `api/routes/ai.py` — route signatures
- [ ] `api/routes/projects.py` — route signatures
- [ ] `api/ws.py` — WebSocket handler signature
- [ ] `api/sse.py` — SSE handler signature
- [ ] `api/deps.py` — dependency injection stubs

### 1.9 AI service stubs

- [ ] `ai/generation/block_generator.py` — signature only
- [x] `ai/generation/type_generator.py` — full implementation (#230)
- [x] `ai/generation/validator.py` ��� stages 1-5 implemented (#230)
- [x] `ai/generation/templates.py` — block + type templates (#64)
- [ ] `ai/synthesis/workflow_planner.py` — signature only
- [ ] `ai/optimization/param_optimizer.py` — signature only

### 1.10 Utility stubs

- [ ] `utils/hashing.py` — `content_hash()` signature
- [ ] `utils/wrapping.py` — `wrap_as_dataobject()` signature
- [ ] `utils/broadcast.py` — `broadcast_apply()` signature with full type hints
- [ ] `utils/logging.py` — logging config

### 1.11 CLI stubs

- [ ] `cli/main.py` — Typer app with subcommands: `serve`, `run`, `validate`, `init`, `blocks`. All print "Not implemented yet."

### Verification gate

- [ ] `make typecheck` passes — mypy accepts all type hints, cross-module imports resolve correctly
- [ ] `make lint` passes — ruff clean
- [ ] `make test` passes — empty suite, no import errors
- [ ] `pip install -e .` works — package installs, `scieasy --help` shows CLI stub
- [ ] CI green ✅

### Deliverable

```
Every interface in ARCHITECTURE.md now exists as type-checked Python code.
No business logic. All methods raise NotImplementedError.
Claude can `from scieasy.blocks.base import Block` and get full type hints + autocomplete.
```

---

## Phase 2 — Architecture tests + CI hardening

**Goal**: structural rules from ARCHITECTURE.md and ADR.md become executable tests. From this point forward, any code that violates the architecture gets caught automatically.

### 2.1 Layer dependency tests

- [ ] `tests/architecture/test_layer_deps.py`:
  - `core/` does not import from `blocks/`, `engine/`, `api/`, `ai/`, `workflow/`
  - `blocks/` does not import from `engine/`, `api/`, `ai/`
  - `engine/` does not import from `api/`, `ai/`
  - `api/` does not import from `ai/` (ai is called by api, but api should import ai, not the other way)
  - No circular imports within any layer

### 2.2 Type system structural tests

- [ ] `tests/architecture/test_type_system.py`:
  - Every class in `core/types/` inherits from `DataObject`
  - No class inherits from more than one base type (no multi-inheritance of Array + DataFrame)
  - Every `Array` subclass declares `axes` (not None)
  - Every `CompositeData` subclass declares `expected_slots`
  - `TypeSignature` correctly encodes inheritance chain for all registered types
  - `Collection` is NOT a `DataObject` subclass (ADR-020: transport wrapper, not data type)

### 2.3 Block system structural tests

- [ ] `tests/architecture/test_block_system.py`:
  - Every class in `blocks/*/` inherits from exactly one of: IOBlock, ProcessBlock, CodeBlock, AppBlock, AIBlock, SubWorkflowBlock
  - Every block declares at least one output port
  - `Block.run()` signature: `inputs` annotated as `dict[str, Collection]`, `config` annotated as `BlockConfig`, return annotated as `dict[str, Collection]` (ADR-020)
  - `ProcessBlock.process_item()` signature: `item` annotated as `DataObject`, `config` annotated as `BlockConfig`, return annotated as `DataObject` (ADR-020 Addendum 5)
  - Block base class exposes Collection utilities: `pack`, `unpack`, `unpack_single`, `map_items`, `parallel_map`, `_auto_flush` (ADR-020)
  - No block at module level calls `to_memory()` (import-time side effect check)

### 2.4 Registry structural tests

- [ ] `tests/architecture/test_registries.py`:
  - `BlockRegistry` stores `BlockSpec`, never raw class references
  - `TypeRegistry` stores `TypeSpec`, never raw class references
  - All `pyproject.toml` entry_points point to importable classes
  - All entry_point classes pass `issubclass` check against their expected base

### 2.5 Naming and placement tests

- [ ] `tests/architecture/test_placement.py`:
  - No `.py` files in `src/scieasy/` root other than `__init__.py`
  - Every module has a docstring
  - No test files outside of `tests/`
  - Format adapters are in `blocks/io/adapters/` (not scattered elsewhere)
  - Code runners are in `blocks/code/runners/` (not scattered elsewhere)

### 2.6 CI enhancement

- [ ] Add `pytest tests/architecture/` as a dedicated CI step (runs before unit tests)
- [ ] Add badge to README: CI status
- [ ] Confirm: intentionally violating a rule (e.g. `core/` importing `blocks/`) → CI red ❌

### Deliverable

```
Architecture rules are now enforced by machine.
Push code that violates layer boundaries → CI blocks the PR.
Push a Block that doesn't inherit from the five categories → CI blocks the PR.
Push a DataObject subclass without axes → CI blocks the PR.
```

---

## Phase 3 — Core data layer implementation

**Goal**: data types can be created, stored, loaded lazily, and tracked by lineage. No blocks, no engine, no API yet — just the foundation.

### 3.1 DataObject + base types

- [ ] Implement `DataObject` metadata handling, `TypeSignature` auto-generation from class hierarchy
- [ ] Implement `Array`, `Series`, `DataFrame`, `Text`, `Artifact` with their field logic
- [ ] Implement `CompositeData` slot management (get, set, slot_types, validation of expected_slots)
- [ ] Implement `TypeRegistry` — scan, register, isinstance-style matching with inheritance

### 3.2 Storage backends

- [ ] Implement `ZarrBackend` — write Array to Zarr store, read back, slice by chunk
- [ ] Implement `ArrowBackend` — write DataFrame to Parquet, read back, column selection
- [ ] Implement `FilesystemBackend` — write/read Text and Artifact
- [ ] Implement `CompositeStore` — directory of slot backends, manifest JSON

### 3.3 ViewProxy

- [ ] Implement `ViewProxy.slice()` — Zarr chunk-aware partial read
- [ ] Implement `ViewProxy.iter_chunks()` — yield fixed-size chunks
- [ ] Implement `ViewProxy.to_memory()` — full load with size warning
- [ ] Implement `ViewProxy.shape`, `ViewProxy.axes` — metadata without loading

### 3.4 Lineage

- [ ] Implement `LineageStore` — SQLite schema, write record, query by hash
- [ ] Implement `EnvironmentSnapshot.capture()` — read Python version + key packages
- [ ] Implement `ProvenanceGraph.ancestors()` — trace data back through block executions

### 3.5 Broadcast utility

- [ ] Implement `broadcast_apply()` — axis name validation, iter over target axes, call func per slice
- [ ] Implement `iter_axis_slices()` — named-axis-aware slice generator for Array

### 3.6 Tests

- [ ] `tests/core/test_types.py` — create each type, verify TypeSignature, inheritance matching
- [ ] `tests/core/test_composite.py` — slot access, nested composites (SpatialData containing AnnData)
- [ ] `tests/core/test_storage.py` — round-trip write/read for each backend
- [ ] `tests/core/test_proxy.py` — lazy loading verified (no data in memory until .slice() or .to_memory())
- [ ] `tests/core/test_lineage.py` — write record, query, ancestor trace
- [ ] `tests/core/test_broadcast.py` — 2D mask × 3D cube, axis mismatch error

### Deliverable

```python
# This works end-to-end:
img = Image(axes=["y", "x"], storage_ref=zarr_ref)
proxy = img.view()
assert proxy.shape == (1024, 1024)       # no data loaded
chunk = proxy.slice({"y": slice(0, 100)}) # loads 100 rows only
full = proxy.to_memory()                  # loads everything (with warning if >2GB)
```

---

## Phase 4 — Block system implementation ✅

**Goal**: blocks can be instantiated, validated, and executed in isolation (no DAG, no scheduler). Port type checking works. Registry discovers blocks.

### 4.1 Port system

- [x] Implement port type matching (isinstance-based, inheritance-aware)
- [x] Implement port constraint validation (call constraint function, report constraint_description on failure)
- [x] Implement connection validation endpoint (source port → target port compatibility check)

### 4.2 Block lifecycle

- [x] Implement `Block.__init__`, `BlockConfig` validation, `BlockState` transitions
- [x] Implement `IOBlock` — load via FormatAdapter, save via FormatAdapter
- [x] Implement `ProcessBlock` base — pass-through validate/postprocess, subclass implements run
- [x] Implement 2-3 built-in ProcessBlocks (merge, split) as proof-of-concept

### 4.3 CodeBlock

- [x] Implement inline mode (MEMORY delivery only)
- [x] Implement script mode with MEMORY delivery
- [x] Implement PROXY delivery mode
- [x] Implement CHUNKED delivery mode with iteration + result concatenation
- [x] Implement `PythonRunner` (exec for inline, importlib for script)
- [x] Implement `introspect.py` — parse run() signature, read configure() return value
- [x] Stub `RRunner` and `JuliaRunner` (just raise NotImplementedError with helpful message)

### 4.4 AppBlock

- [x] Implement file-exchange bridge — serialise to exchange dir, launch subprocess
- [x] Implement `FileWatcher` — polling-based output detection
- [x] Implement pause/resume protocol (block state RUNNING → PAUSED → DONE)

### 4.5 SubWorkflowBlock

- [x] Implement child workflow loading
- [x] Implement input injection + output extraction mapping
- [x] (Depends on Phase 5 engine — uses simple sequential executor stub for now)

### 4.6 Registry

- [x] Implement `BlockRegistry.scan()` — Tier 1 (directory scan) + Tier 2 (entry_points)
- [x] Implement `BlockRegistry.instantiate()` — fresh import with mtime-based module name
- [x] Implement `BlockRegistry.hot_reload()` — re-scan Tier 1 dirs, diff specs
- [x] Implement `TypeRegistry` with same two-tier scan
- [x] Implement `AdapterRegistry` — extension → adapter mapping

### 4.7 Format adapters

- [x] Implement CSV adapter
- [x] Implement TIFF adapter
- [x] Implement Parquet adapter
- [x] Implement generic (binary → Artifact) adapter
- [x] Stub remaining adapters (mzXML, h5ad, fcs) with NotImplementedError

### 4.8 Tests

- [x] `tests/blocks/test_ports.py` — type matching, constraint pass/fail, CompositeData slot constraints
- [x] `tests/blocks/test_io_block.py` — load CSV → DataFrame, save DataFrame → Parquet
- [x] `tests/blocks/test_process_block.py` — merge two DataFrames
- [x] `tests/blocks/test_code_block.py` — inline Python, script Python, PROXY mode, CHUNKED mode
- [x] `tests/blocks/test_app_block.py` — mock subprocess + file watcher (write output file → block resumes)
- [x] `tests/blocks/test_registry.py` — Tier 1 scan discovers drop-in .py, hot reload picks up changes
- [x] `tests/blocks/test_subworkflow.py` — stub test with sequential executor

### Deliverable

```python
# This works end-to-end (single block, no DAG):
registry = BlockRegistry()
registry.scan()

block = registry.instantiate("Raman denoise", config={"window": 11})
result = block.run(
    inputs={"spectrum": some_spectrum.view()},
    config=block.config,
)
assert isinstance(result["smoothed"], Spectrum)
```

---

## Phase 5 — Execution engine

**Goal**: multi-block workflows execute as DAGs with Collection-based data transport (ADR-020), subprocess isolation (ADR-017), cancellation support (ADR-018), and cross-platform process lifecycle management (ADR-019).

### 5.0 Collection infrastructure and block refactor (ADR-020 Addendum)

- [ ] Implement `core/types/collection.py` — Collection class with homogeneity enforcement
- [ ] Implement `_auto_flush()` in Block base — write in-memory DataObject to storage, return lightweight ref
- [ ] Implement `process_item()` in Block base — convenience method, raises NotImplementedError
- [ ] Implement default `run()` in ProcessBlock — iterate primary input via `process_item()` + auto-flush (Tier 1)
- [ ] Modify `map_items()` — auto-flush each result after `func(item)` (Tier 2)
- [ ] Modify `parallel_map()` — auto-flush each result; add memory warning in docstring (Addendum 3)
- [ ] Modify `pack()` — auto-flush items without StorageReference as safety net (Tier 3)
- [ ] Implement `blocks/code/lazy_list.py` — LazyList for CodeBlock auto-unpack of length > 1 (Addendum 4)
- [ ] Modify CodeBlock auto-unpack — length=1 → single native object; length>1 → LazyList (Addendum 4)
- [ ] Modify CodeBlock auto-repack — size-threshold warning for large outputs
- [ ] Modify IOBlock — lazy Collection construction: create StorageReference per file, no eager read (Addendum 2)
- [ ] Add `FormatAdapter.create_reference(path) -> StorageReference` to adapter protocol (Addendum 2)
- [ ] Implement `create_reference()` in each adapter (CSV, TIFF, Parquet, Zarr, generic)
- [ ] Modify `FileExchangeBridge.prepare()` — iterate Collection, write files one at a time (Addendum 5)
- [ ] Modify `worker.py` — initialise output storage dir; post-run force-write scan for items without StorageReference (Addendum 5)
- [ ] Verify `core/storage/base.py` `StorageBackend.write()` handles raw in-memory DataObject (not just ViewProxy-backed objects) for _auto_flush support

### 5.1 DAG construction + scheduling

- [ ] Implement `build_dag()` from `WorkflowDefinition`
- [ ] Implement `topological_sort()` with cycle detection
- [ ] Implement event-driven `DAGScheduler.execute()` — subscribe to EventBus, dispatch blocks, propagate SKIPPED on failure/cancel (ADR-018)
- [ ] Implement `DAGScheduler.cancel_block()` — terminate subprocess, mark CANCELLED, propagate SKIPPED downstream
- [ ] Implement `DAGScheduler.cancel_workflow()` — cancel all RUNNING/PAUSED blocks, SKIP remaining

### 5.2 Process lifecycle (ADR-017, ADR-019)

- [ ] Implement `ProcessHandle` — cross-platform terminate/kill/is_alive/exit_info
- [ ] Implement `ProcessRegistry` — register/deregister/get_handle/terminate_all
- [ ] Implement `ProcessMonitor` — background coroutine polling for unexpected process exits
- [ ] Implement `PlatformOps` — PosixOps (signals, process groups) + WindowsOps (Job Objects, TerminateProcess)
- [ ] Implement `spawn_block_process()` factory — single point of subprocess creation
- [ ] Implement `LocalRunner` — subprocess execution via worker.py, returns RunHandle
- [ ] Implement `worker.py` — subprocess entry point: deserialise payload, reconstruct ViewProxy, call block.run(), return Collection StorageRefs

### 5.3 Resource management

- [ ] Implement `ResourceManager.can_dispatch()` with psutil OS memory watermark + GPU/CPU slot counting (ADR-022)
- [ ] Implement `ResourceManager.release()` for discrete resources (GPU slots, CPU cores only — memory handled by OS)
- [ ] Implement EventBus auto-release on BLOCK_DONE/ERROR/CANCELLED/PROCESS_EXITED (ADR-018)
- [ ] Add `psutil` to `pyproject.toml` dependencies
- [ ] Integrate with scheduler — dispatch respects resource limits and memory watermark

### 5.4 Checkpoint + pause/resume

- [ ] Implement `WorkflowCheckpoint` serialisation (block states incl. CANCELLED/SKIPPED, skip_reasons, intermediate Collection refs)
- [ ] Implement `DAGScheduler.pause()` — serialise state, return checkpoint
- [ ] Implement `DAGScheduler.resume()` — load checkpoint, skip completed/cancelled/skipped blocks
- [ ] Test crash recovery: kill mid-execution → resume from checkpoint

### 5.5 Event bus (ADR-018)

- [ ] Implement `EventBus.emit()` / `subscribe()` / `unsubscribe()` — async in-process pub/sub
- [ ] Define all 14 event type constants: BLOCK_READY/RUNNING/PAUSED/DONE/ERROR/CANCELLED/SKIPPED, CANCEL_BLOCK/WORKFLOW_REQUEST, PROCESS_SPAWNED/EXITED, WORKFLOW_STARTED/COMPLETED, CHECKPOINT_SAVED
- [ ] Wire all subscribers: DAGScheduler, ResourceManager, ProcessRegistry, LineageRecorder, CheckpointManager

### 5.6 Collection operation blocks (ADR-021)

- [ ] Implement `MergeCollection` — concatenate 2 same-typed Collections
- [ ] Implement `SplitCollection` — split by index or condition
- [ ] Implement `FilterCollection` — keep items matching metadata predicate
- [ ] Implement `SliceCollection` — extract sub-range [start:end]

### 5.7 SubWorkflowBlock completion

- [x] Add `_scheduler_factory` ClassVar for engine-layer injection (avoids import-linter: blocks cannot import engine)
- [x] `run()` delegates to `_run_with_scheduler()` when factory is set, else falls back to `_sequential_execute()`
- [x] Collections (ADR-020) flow through child workflow namespace unchanged
- [x] Tests: scheduler factory injection, fallback behavior, Collection passthrough
- [ ] Child workflow runs in its own subprocess with own scheduler, communicates via Collection StorageRefs (Phase 5.2b worker integration)

### 5.8 Tests

- [ ] `tests/engine/test_dag.py` — build DAG, topo sort, cycle detection
- [ ] `tests/engine/test_scheduler.py` — 3-block linear pipeline, branching DAG, diamond DAG, cancel block + SKIPPED propagation, cancel workflow
- [ ] `tests/engine/test_process_handle.py` — ProcessHandle terminate/kill on POSIX/Windows, process tree kill
- [ ] `tests/engine/test_process_monitor.py` — detect unexpected exit, emit PROCESS_EXITED event
- [ ] `tests/engine/test_events.py` — EventBus emit/subscribe, error isolation between subscribers
- [ ] `tests/engine/test_resources.py` — GPU slot exhaustion, auto-release on block terminal events
- [ ] `tests/engine/test_checkpoint.py` — pause → serialise (with CANCELLED/SKIPPED states) → resume → correct result
- [ ] `tests/core/test_collection.py` — Collection construction, homogeneity enforcement, pack/unpack round-trip, auto-flush in pack/map_items
- [ ] `tests/blocks/test_lazy_list.py` — LazyList iteration (memory bounded), indexing, len (no load), GC behaviour
- [ ] `tests/integration/test_multimodal_workflow.py` — the Appendix A scenario with Collection transport (load → process → merge → export)
- [ ] `tests/integration/test_cancel_scenario.py` — cancel Cellpose → napari/SRS SKIPPED → Raman continues

### Deliverable

```python
# This works end-to-end:
workflow = load_yaml("examples/workflows/raman_preprocessing.yaml")
scheduler = DAGScheduler(workflow)
await scheduler.execute()
# All blocks executed in correct order, results stored, lineage recorded
```

---

## Phase 6 — Workflow definition + CLI

**Goal**: workflows are defined in YAML, validated, and executable from the command line without a frontend.

### 6.1 Workflow serialisation

- [ ] Implement YAML load/save with schema validation (Pydantic)
- [ ] Implement layout persistence (optional node positions)
- [ ] Implement `validate_workflow()` — type compatibility on all edges, missing connections, dangling ports

### 6.2 CLI

- [ ] Implement `scieasy init` — create project workspace directory structure
- [ ] Implement `scieasy validate workflow.yaml` — load + validate + report
- [ ] Implement `scieasy run workflow.yaml` — load + validate + execute (headless)
- [ ] Implement `scieasy blocks` — list installed blocks from registry
- [ ] Implement `scieasy serve` — start FastAPI server (stub for now, full in Phase 7)

### 6.3 Tests

- [ ] `tests/workflow/test_serializer.py` — YAML round-trip
- [ ] `tests/workflow/test_validator.py` — catch type mismatch, dangling port, cycle
- [ ] CLI smoke tests — `scieasy --help`, `scieasy blocks`, `scieasy validate examples/...`

### Deliverable

```bash
scieasy init my_project
cd my_project
scieasy validate workflows/raman_preprocessing.yaml   # "Valid ✓"
scieasy run workflows/raman_preprocessing.yaml         # Executes, prints results
scieasy blocks                                          # Lists all installed blocks
```

---

## Phase 7 — API layer

**Goal**: full REST + WebSocket + SSE backend. Frontend can connect. Includes execute-from (ADR-023) and type-aware data preview.

### 7.1 REST endpoints — Workflow

- [ ] Workflow CRUD (create, get, update, delete)
- [ ] Workflow execution (execute, pause, resume — delegates to DAGScheduler)
- [ ] Workflow cancel + block cancel (ADR-018 — emit CANCEL_WORKFLOW_REQUEST / CANCEL_BLOCK_REQUEST via EventBus)
- [ ] Execute-from endpoint (ADR-023): validate predecessors have cached outputs, reset downstream blocks, delegate to `DAGScheduler.execute_from()`
- [ ] `create_app()` factory — wire FastAPI with EventBus, ResourceManager, ProcessRegistry, BlockRunner, DAGScheduler

### 7.2 REST endpoints — Block registry

- [ ] List all blocks (`GET /api/blocks/`) — name, category, description, port summary
- [ ] Get block schema (`GET /api/blocks/{type}/schema`) — ports, config JSON Schema with `ui_priority` per parameter, port type hierarchy for colour resolution, optional `ui_ring_color` on sub-types (ADR-023)
- [ ] Validate connection (`POST /api/blocks/validate-connection`) — check port type compatibility

### 7.3 REST endpoints — Data

- [ ] Upload data files (`POST /api/data/upload`)
- [ ] Get data metadata (`GET /api/data/{ref}`)
- [ ] Type-appropriate preview (`GET /api/data/{ref}/preview`) — table rows for DataFrame, image thumbnail for Image/Array, chart data for Series/Spectrum, text content for Text, file metadata for Artifact (ADR-023)

### 7.4 REST endpoints — Project management (ADR-023 Addendum 1)

- [ ] Create project (`POST /api/projects/`) — create workspace directory structure (equivalent to `scieasy init`), write `project.yaml`, return project metadata with workspace path
- [ ] List projects (`GET /api/projects/`) — return name, path, description, last_opened, workflow_count
- [ ] Get project (`GET /api/projects/{id}`)
- [ ] Update project (`PUT /api/projects/{id}`)
- [ ] Delete project (`DELETE /api/projects/{id}`)

### 7.5 REST endpoints — API schemas

- [ ] Add `ProjectCreate`, `ProjectResponse` to `schemas.py`
- [ ] Add `ExecuteFromRequest`, `ExecuteFromResponse` to `schemas.py`

### 7.6 Real-time communication

- [ ] WebSocket handler — bidirectional: broadcast block state changes + cancel_propagation; receive cancel_block/cancel_workflow + interactive_complete (ADR-018). Already implemented in `ws.py`.
- [ ] SSE handler — stream execution logs with block ID and severity level

### 7.7 Dependency injection (`deps.py`)

- [ ] `get_engine()` — return configured DAGScheduler + EventBus + ResourceManager + ProcessRegistry + LocalRunner
- [ ] `get_block_registry()` — return BlockRegistry with scanned blocks
- [ ] `get_type_registry()` — return TypeRegistry
- [ ] `get_lineage_store()` — return LineageStore for current project

### 7.8 Tests

- [ ] `tests/api/test_workflows.py` — CRUD, execute, pause, resume, cancel, execute-from
- [ ] `tests/api/test_blocks.py` — list, schema (verify ui_priority in response), validate-connection
- [ ] `tests/api/test_data.py` — upload, metadata, type-appropriate preview
- [ ] `tests/api/test_projects.py` — create (verify directory structure), list, get, update, delete
- [ ] `tests/api/test_ws.py` — WebSocket connect, receive state updates, send cancel
- [ ] `tests/api/test_sse.py` — SSE log stream connection and filtering

### Deliverable

```bash
scieasy serve
# Server starts on http://localhost:8000
# curl /api/projects/ → list projects
# curl /api/blocks/ → list blocks with schemas
# curl /api/workflows/{id}/execute → start workflow, WebSocket pushes state updates
# curl /api/workflows/{id}/execute-from → re-run from specific block
```

---

## Phase 8 — Frontend (ADR-023)

**Goal**: visual workflow editor with three-column layout, data preview, inline block config, and project management.

### 8.0 Project scaffolding

- [ ] Initialise Vite + React + TypeScript project in `frontend/`
- [ ] Install dependencies: `@xyflow/react`, `zustand`, `plotly.js`, `react-plotly.js`, `tailwindcss`, `shadcn/ui`
- [ ] Configure Tailwind, PostCSS, TypeScript paths
- [ ] Create `App.tsx` root layout with resizable three-column + toolbar + bottom panel

### 8.1 Project management (ADR-023 Addendum 1)

- [ ] Welcome screen when no project is open (New Project, Open Project, Recent Projects)
- [ ] `ProjectDialog.tsx` — New/Open project modal dialogs
- [ ] Projects dropdown menu in toolbar
- [ ] `projectSlice` in Zustand store (currentProject, recentProjects, isProjectOpen)
- [ ] Save/load project via `POST/GET /api/projects/`

### 8.2 Block Palette (left column)

- [ ] `BlockPalette.tsx` — full-height left sidebar with categories (IO, Process, Code, App, AI, SubWF, Custom)
- [ ] `BlockCard.tsx` — draggable block card (icon, name, port summary)
- [ ] Search and category filter
- [ ] "Reload blocks" button
- [ ] Fetch block list from `GET /api/blocks/`
- [ ] Collapsible to icon-only mode (`Ctrl+B`)

### 8.3 ReactFlow Canvas

- [ ] `WorkflowCanvas.tsx` — ReactFlow instance with minimap (inside canvas), zoom, pan
- [ ] `BlockNode.tsx` — custom node: header (icon + name + [▶] + [↻]), inline top-3 params, type-coloured ports, state badge footer
- [ ] `PortHandle.tsx` — custom handle: solid circle for single items, double ring for Collection, coloured by base type (ADR-023 Section 9.6)
- [ ] `TypedEdge.tsx` — custom edge: source port colour, dashed for Collection
- [ ] `SubWorkflowNode.tsx` — drill-down node for SubWorkflowBlock
- [ ] Connection validation on wire draw (`POST /api/blocks/validate-connection`)
- [ ] Delete selected blocks/edges via `Delete`/`Backspace` key
- [ ] Drag-drop block from palette onto canvas
- [ ] Undo/Redo (`Ctrl+Z`/`Ctrl+Y`)
- [ ] `typeColorMap.ts` — base type → hex colour mapping

### 8.4 Data Preview Panel (right column)

- [ ] `DataPreview.tsx` — port selector dropdown, collection tabs, renderer dispatch
- [ ] `TableRenderer.tsx` — paginated DataFrame table (first 100 rows, column sort, search)
- [ ] `ImageRenderer.tsx` — zoomable Image/Array viewer (channel selector, brightness)
- [ ] `ChartRenderer.tsx` — Plotly line chart for Series/Spectrum
- [ ] `TextRenderer.tsx` — Monaco read-only with syntax highlighting
- [ ] `ArtifactRenderer.tsx` — PDF/image inline, others metadata + download link
- [ ] `CompositeRenderer.tsx` — expandable slot list
- [ ] Collection tab bar: ≤20 direct tabs, 21-100 paginated, >100 paginated + jump-to
- [ ] Lazy loading via `GET /api/data/{ref}/preview`, cached in `previewSlice`
- [ ] Collapsible, auto-shows on block selection (`Ctrl+D`)

### 8.5 Bottom Panel (browser-style tabs)

- [ ] `BottomPanel.tsx` — resizable height, collapsible, browser-style tab bar
- [ ] `AIChat.tsx` — conversational AI interface (block generation, workflow suggestions)
- [ ] `ConfigPanel.tsx` — full parameter form from JSON Schema (auto-switches on block click)
- [ ] `LogViewer.tsx` — SSE log stream with block filter, severity filter, auto-scroll
- [ ] Auto-expand on execution start, auto-switch to Logs tab

### 8.5b Bottom Panel — deferred tabs (Phase 8.5)

- [ ] `LineageView.tsx` — provenance chain for selected block output
- [ ] `JobsList.tsx` — current/historical execution list
- [ ] `ProblemsPanel.tsx` — validation errors and type mismatch warnings

### 8.6 Toolbar

- [ ] Projects menu (New, Open, Save, Recent, Close) — ADR-023 Addendum 1
- [ ] File operations (Import YAML, Save, Export)
- [ ] Execution controls (Run, Pause, Stop, Reset) — wired to backend REST endpoints
- [ ] Edit operations (Delete, Reload Blocks)
- [ ] All keyboard shortcuts (Ctrl+Enter, Ctrl+S, Delete, Ctrl+Z, etc.)

### 8.7 Execution UI

- [ ] `useWebSocket.ts` — connect to backend, dispatch state events to `executionSlice`
- [ ] `useSSE.ts` — SSE connection for log streaming
- [ ] Live block state badges via WebSocket (8 states with colours and animations)
- [ ] Cancel button on RUNNING/PAUSED blocks (ADR-018)
- [ ] "Start from here" button on completed blocks (`POST /api/workflows/{id}/execute-from`) — ADR-023

### 8.8 State management

- [ ] Zustand store with 7 slices: project, workflow, execution, ui, preview, palette, chat
- [ ] `lib/api.ts` — typed REST API client
- [ ] TypeScript types mirroring backend schemas (`types/workflow.ts`, `types/blocks.ts`, `types/data.ts`)

### 8.9 Tests

- [ ] Component rendering tests (Vitest + React Testing Library)
- [ ] WebSocket state update integration test
- [ ] Human test plan: `docs/testing/phase-5-to-8-human-tests.md` (Phase 8 section)

### Deliverable

```bash
cd frontend && npm run dev
# Opens http://localhost:5173
# Welcome screen → New Project → drag blocks → wire connections → Run → see results in preview
```

---

## Phase 9 — AI services

**Goal**: AI can generate blocks, propose workflows, and suggest parameters. AI Chat tab in bottom panel provides the user-facing interface.

### 9.1 Block and type generation

- [ ] Implement prompt templates for all five block categories + data types
- [ ] Implement validation pipeline (static analysis → dry run → port contract check)
- [ ] End-to-end: natural-language description → validated block in registry
- [ ] Wire `POST /api/ai/generate-block` to generation pipeline

### 9.2 Workflow synthesis

- [ ] Implement: data description + goal → proposed DAG (YAML)
- [ ] Wire `POST /api/ai/suggest-workflow` to synthesis pipeline
- [ ] AI Chat tab: user describes goal → AI proposes workflow → "Apply" button adds to canvas

### 9.3 Parameter optimization

- [ ] Implement: observe intermediate results → suggest parameter changes
- [ ] Wire `POST /api/ai/optimize-params` to optimization pipeline
- [ ] AI Chat tab: user selects block → AI suggests parameter tweaks based on output preview

---

## Phase 10 — Integration + polish

**Goal**: the Appendix A scenario (LC-MS + Raman + IF + SRS) runs end-to-end through the full stack (CLI + API + frontend).

- [ ] Implement mzXML adapter, h5ad adapter
- [ ] Build example blocks: CellposeSegment, RamanBaseline, SpectralPCA
- [ ] Build example workflow YAML files in `examples/` directory
- [ ] Build the full multimodal workflow from ARCHITECTURE.md Appendix A
- [ ] Run it end-to-end: data loaded → ElMAVEN (mock, whole-collection) → R script → Cellpose (parallel_map) → napari (mock, serial per-item) → merge → export
- [ ] Verify in frontend: project creation → workflow loading → execution → data preview → "Start from here" re-run
- [ ] Confirm lineage, checkpoints, Collection transport, cancel + SKIPPED propagation all work in the integrated scenario
- [ ] Performance profiling on large datasets (>1000 items in Collection)
- [ ] Polish: error messages, loading states, empty states, responsive layout
- [ ] Write `docs/getting-started.md` tutorial based on this scenario

---

## Milestone summary

| Phase | Deliverable | Bootstrap gate exemption? |
|---|---|---|
| 0 | Empty repo, CI green | Yes |
| 1 | Interface skeleton, mypy passes | Yes |
| 2 | Architecture tests enforce boundaries | Yes |
| 3 | Core data layer works standalone | No — full gate from here |
| 4 | Blocks work in isolation | No |
| 5 | Multi-block DAG workflows execute | No |
| 6 | CLI headless execution | No |
| 7 | API backend complete | No |
| 8 | Frontend visual editor | No |
| 9 | AI services | No |
| 10 | Full multimodal demo | No |

Phases 0–2 are the foundation — no business logic, pure structure and guardrails. The bootstrap gate exemption (Appendix A of CLAUDE.md) covers these phases. Once Phase 3 begins, full workflow gate discipline applies.
