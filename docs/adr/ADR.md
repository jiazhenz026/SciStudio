# SciEasy — Architecture Decision Records (ADR)

> ADRs capture the key design decisions made during SciEasy's architecture phase,
> including context, alternatives considered, and trade-offs accepted.
>
> **Status values**: `accepted` | `proposed` | `superseded` | `deprecated`

---

## ADR-001: Six base data types with inheritance

**Status**: accepted  
**Date**: 2026-04-02

### Context

The framework must represent all scientific data flowing between blocks — images, spectra, tabular data, text reports, opaque files, and complex multi-modal containers (AnnData, SpatialData). We need a type system that is small enough to learn quickly but extensible enough for any domain.

### Decision

Six base types inheriting from `DataObject`:

- `Array` — n-dimensional numeric data (images, hyperspectral cubes, tensors).
- `Series` — 1D indexed data (spectra, time series, chromatograms).
- `DataFrame` — columnar tabular data (peak tables, cell metadata, feature matrices).
- `Text` — plain text, markdown, JSON strings.
- `Artifact` — opaque files (PDFs, reports, binary blobs).
- `CompositeData` — named collection of heterogeneous `DataObject` slots.

Users extend via standard Python inheritance. Port type matching uses `isinstance`-style checks, so a `RamanSpectrum(Spectrum)` auto-matches any port accepting `Spectrum` or `Series`.

### Alternatives considered

- **Fewer types (Array + DataFrame + Blob only)**: too coarse. Series and Spectrum have different semantics from a 2D Array; collapsing them loses axis meaning and forces blocks to do runtime shape checking.
- **Many fine-grained types (separate Image, Volume, TimeSeries, Spectrum, etc. all at base level)**: combinatorial explosion. Hard for new users to know which base to pick. Inheritance solves this — `Image` is an `Array` with spatial conventions.
- **No CompositeData (force AnnData to inherit DataFrame)**: AnnData is fundamentally a container of heterogeneous objects (matrix + obs + var + uns), not a special DataFrame. Single-parent inheritance misrepresents the structure and breaks port semantics.

### Consequences

- Six types is a small learning surface for new users.
- CompositeData adds complexity to port matching (must support slot-level constraints) but accurately models real scientific data containers.
- Community types are always subtypes of one of six bases — no "where does this go?" ambiguity.

---

## ADR-002: Named axes on Array types

**Status**: accepted  
**Date**: 2026-04-02

### Context

Multi-modal workflows frequently need to align arrays of different dimensionality — applying a 2D mask `(y, x)` across every channel of a 3D MSI dataset `(y, x, mz)`. Without named axes, dimension alignment is positional and fragile ("dim 0 is probably y").

### Decision

Add an optional `axes: list[str] | None` field to `Array`. Domain subtypes declare their axis convention:

```
Image:      ["y", "x"]
MSImage:    ["y", "x", "mz"]
SRSImage:   ["y", "x", "wavenumber"]
FluorImage: ["y", "x", "channel"]
```

Named axes are pure metadata — they do not affect storage, ViewProxy, or chunk layout.

### Alternatives considered

- **xarray-style dimension labelling as the core data model**: too opinionated. Forces all Array users into xarray conventions. Many scientific libraries (cellpose, scikit-image, OpenCV) expect plain numpy arrays and would require constant conversion.
- **No named axes (positional only)**: leaves dimension semantics implicit. Every block that operates across modalities must hardcode assumptions like "the third axis is m/z". Error-prone and unreadable.

### Consequences

- Lightweight change: one optional field on Array, no storage impact.
- Port constraints can reference axis names (e.g. "must have y and x axes") instead of ndim checks.
- The broadcast utility (ADR-003) depends on named axes for alignment validation.
- `axes = None` remains valid for plain numeric arrays where axis semantics are irrelevant.

---

## ADR-003: Broadcast as explicit utility, not implicit type-system behaviour

**Status**: accepted  
**Date**: 2026-04-02

### Context

Applying low-dimensional data to high-dimensional data along specific axes is a recurring pattern (mask → MSI channels, baseline → spectrum batch, ROI → time-lapse frames). numpy-style automatic broadcasting is purely shape-based and ignores semantic alignment (e.g. whether two spatial arrays are actually co-registered).

### Decision

Provide `broadcast_apply()` in `scieasy.utils.broadcast` as an explicit, opt-in utility that block authors call when needed. It validates axis name alignment, iterates over the specified `over_axes`, and calls a user-provided function per slice. Broadcasting is never triggered automatically by the port system or DAG scheduler.

### Alternatives considered

- **Automatic broadcasting at the port/engine level**: shape match ≠ semantic match. An IF image and an MSI image may have compatible `(y, x)` shapes but different pixel sizes, FOV offsets, or coordinate systems. Auto-broadcasting without registration would silently produce wrong results.
- **No broadcast utility (leave it to block authors entirely)**: every block that needs this pattern would reimplement axis iteration from scratch. The utility eliminates boilerplate while keeping domain decisions (which axes, what function) in the block.

### Consequences

- Blocks retain full control over broadcasting semantics.
- The utility catches axis misalignment errors early with clear messages.
- Registration/alignment must be an explicit preceding step in the workflow — the framework does not guess.

---

## ADR-004: Five block categories plus SubWorkflowBlock

**Status**: accepted  
**Date**: 2026-04-02

### Context

The framework needs a small, memorable set of block categories that covers all processing scenarios — from pure computation to external GUI software to AI-driven analysis — without requiring users to navigate a complex taxonomy.

### Decision

Five categories covering distinct execution patterns, plus one meta-category:

| Category | When to use |
|---|---|
| `IOBlock` | Load or save data in any format. Single class with direction flag. |
| `ProcessBlock` | Deterministic data transformation (including merge, split, filter). |
| `CodeBlock` | Run user-provided R/Python/Julia scripts (inline or file-based). |
| `AppBlock` | Bridge external GUI software (ElMAVEN, Fiji, napari) via file exchange. |
| `AIBlock` | LLM-driven processing (classification, summarisation, code generation). |
| `SubWorkflowBlock` | Encapsulate an entire workflow as a single reusable block. |

### Alternatives considered

- **More categories (separate MergeBlock, ViewBlock, ExportBlock, CLIBlock)**: every additional category increases cognitive load. Merge is a ProcessBlock with multiple inputs. Export is an IOBlock with `direction="output"`. CLI tools are AppBlocks with non-GUI commands. The five categories are sufficient because they distinguish by execution pattern, not by data operation.
- **Single Block class with mode flags**: loses type safety. A ProcessBlock and an AppBlock have fundamentally different lifecycle requirements (auto-execute vs launch-pause-watch-resume). Separate base classes let the engine dispatch correctly without runtime mode checks.

### Consequences

- New users learn five concepts. Everything else is a subclass of one of them.
- SubWorkflowBlock enables hierarchical composition — a lab's standard preprocessing pipeline becomes a single palette item.
- The boundary between ProcessBlock and CodeBlock is sometimes fuzzy (a Python ProcessBlock vs a CodeBlock in inline mode). Convention: if the logic is reusable and has typed ports, make it a ProcessBlock. If it's a one-off script, use CodeBlock.

---

## ADR-005: CodeBlock supports inline and script execution modes

**Status**: accepted  
**Date**: 2026-04-02

### Context

Users have existing analysis scripts ranging from 5-line snippets to 500-line R pipelines with custom dependencies. A single execution model cannot serve both cases. Requiring users to restructure their scripts into a specific framework API would violate the "inclusive" principle.

### Decision

CodeBlock supports two modes:

- **Inline mode**: user writes code directly in the block's config panel. Variables are injected from input ports and extracted to output ports by name. Best for short, one-off operations.
- **Script mode**: user points the block at an existing `.py` / `.R` / `.jl` file. The framework calls a conventional `run(inputs, config) → dict` function. The script can import any libraries, define helper functions, and span hundreds of lines. An optional `configure()` function provides config schema for the UI form.

The framework introspects script files to auto-generate port declarations and config forms.

### Alternatives considered

- **Inline only**: breaks for complex scripts with imports, helper functions, and multi-file dependencies. Users would have to flatten everything into a single string.
- **Script only (always require a file)**: overkill for `output_0 = input_0[input_0["pvalue"] < 0.05]`. Inline mode reduces friction for quick operations.
- **Notebook-style cells**: adds UI complexity (cell ordering, state management) that duplicates Jupyter's job. SciEasy is a workflow framework, not a notebook.

### Consequences

- Users can integrate existing scripts without modification beyond adding a `run()` wrapper function.
- Script introspection (`introspect.py`) must handle Python, R, and Julia function signatures — a moderate implementation effort.
- Inline mode executes code via `exec()`, which has security implications. Acceptable for single-user local deployment; requires sandboxing for any future multi-user scenario (see Appendix C.3 of ARCHITECTURE.md).
- Data delivery to user scripts requires explicit handling — see ADR-016 for the original per-port `InputDelivery` mechanism (now partially superseded by ADR-020 Collection auto-unpack).

---

## ADR-006: External software integration via file-exchange bridge

**Status**: accepted  
**Date**: 2026-04-02

### Context

Many scientific workflows depend on standalone GUI applications (ElMAVEN for LC-MS peak picking, Fiji/ImageJ for image processing, napari for segmentation review, FlowJo for flow cytometry gating). These tools cannot be replaced — they have decades of domain-specific development. The framework must integrate them, not compete with them.

### Decision

`AppBlock` bridges external software via a file-exchange protocol:

1. Serialise input data to a temporary exchange directory in the app's native format.
2. Launch the external application as a subprocess.
3. Pause the workflow. Frontend shows "Waiting for external software."
4. Monitor the exchange directory for output files (using filesystem watcher).
5. When output files appear or are modified, read them, wrap as DataObjects, resume workflow.

### Alternatives considered

- **API-based integration (plugins for each app)**: most scientific GUI tools have no stable API, or their APIs are incomplete (e.g. Fiji's macro language cannot access all features). File exchange is the universal lowest-common-denominator.
- **Screen scraping / automation**: fragile, platform-dependent, and cannot access internal application state.
- **Ignore external tools (only support code-based processing)**: violates the core "inclusive" principle. Many users' workflows fundamentally depend on manual operations in these tools.

### Consequences

- File-based exchange is slow but universally compatible. No per-application plugin needed.
- The workflow pauses during external app use — batch throughput depends on human speed. Acceptable because these are inherently interactive steps.
- Exchange directory cleanup must be handled by the framework to avoid disk bloat.
- `watchdog` library dependency for filesystem monitoring.

---

## ADR-007: Lazy loading by default via ViewProxy

**Status**: accepted  
**Date**: 2026-04-02

### Context

Some datasets (MSI, spatial transcriptomics) exceed 100 GB. Loading full datasets into memory at block input is infeasible. Yet many blocks only need a small slice (one channel, one ROI, metadata only).

### Decision

`DataObject` instances are lightweight wrappers (~KB) holding a `StorageReference`. Blocks never receive raw data directly. The engine injects a `ViewProxy` that mediates access:

- `.slice(...)` — read a specific region (Zarr chunk-aware).
- `.iter_chunks(chunk_size)` — iterate in fixed-size pieces.
- `.to_memory()` — load everything (explicit opt-in, with large-data warnings).
- `.shape`, `.axes` — metadata without loading data.

### Alternatives considered

- **Eager loading (load everything into memory at block input)**: OOM on large datasets. Unacceptable for the target use case.
- **Memory-mapped files only**: works for single-machine, but doesn't extend to cloud/remote storage. Zarr-backed ViewProxy works with both local and remote stores.
- **Dask lazy arrays as the core abstraction**: adds a heavy dependency and forces all block authors to understand Dask semantics. ViewProxy is simpler — block authors who want full data just call `.to_memory()`.

### Consequences

- Block authors must be aware they're working with proxies, not raw arrays. Most blocks can call `.to_memory()` for small data or `.iter_chunks()` for large data.
- ViewProxy integrates with Zarr chunking for efficient partial reads.
- Storage backend is abstracted — switching from Zarr to a cloud store doesn't change block code.

> **Note (ADR-031)**: ViewProxy has been eliminated. Its methods (`to_memory()`, `slice()`, `iter_chunks()`) are absorbed directly into `DataObject`. Blocks receive typed `DataObject` instances with `storage_ref` set and call data access methods directly -- no intermediary accessor class. See ADR-031 D2.

---

## ADR-008: Two-tier block and type distribution

**Status**: accepted  
**Date**: 2026-04-02

### Context

The framework targets both bench scientists (who want to add a quick custom block without tooling knowledge) and community developers (who want to publish polished, versioned block packages). A single distribution mechanism cannot serve both audiences.

### Decision

Two tiers, both feeding into a unified registry:

- **Tier 1 — Drop-in files**: place a `.py` file in `{project}/blocks/` or `~/.scieasy/blocks/` (and corresponding `types/` directories). Framework auto-discovers on startup and via manual "Reload blocks" button. Zero packaging, zero config.
- **Tier 2 — pip install**: standard Python packages with `scieasy.blocks`, `scieasy.types`, and `scieasy.adapters` entry_points. `pip install scieasy-flowcyto` makes all blocks appear in the palette immediately.

Same two-tier model applies to custom data types.

### Alternatives considered

- **Tier 2 only (pip packages for everything)**: too heavy for "I just want to add a denoise block for this project." Requires pyproject.toml, package structure, pip install. Unacceptable friction for non-developers.
- **Three tiers with a Block Hub (in-app marketplace)**: desirable long-term but premature for v1. Adds significant infrastructure (index server, compatibility checking, in-app pip execution). Can be added later without architectural changes.
- **Dynamic code loading from a database or cloud**: introduces security and versioning complexity. Files on disk are inspectable, version-controllable (git), and debuggable with standard tools.

### Consequences

- Tier 1 makes the 5-minute "write a block, see it in the palette" experience possible.
- Tier 2 enables a healthy community ecosystem around modality-specific block packages.
- Registry scans two sources at startup — minimal performance impact since drop-in directories are typically small.
- Tier 2 entry_points shadow Tier 1 blocks with the same name (installed packages are authoritative).

---

## ADR-009: Registry stores specs, not class references

**Status**: accepted  
**Date**: 2026-04-02

### Context

Users modify drop-in block files during a session and click "Reload blocks" to pick up changes. Python's `importlib.reload()` produces a new class object that breaks `isinstance` checks against cached old references. The registry must handle reloads without corrupting running workflows.

### Decision

`BlockRegistry` and `TypeRegistry` store `BlockSpec` / `TypeSpec` descriptors (module path, class name, metadata, file mtime) — never the class object itself.

- **Scan phase** (startup + reload): import each file, read class-level metadata, build spec, discard class reference.
- **Instantiation phase** (workflow execution): fresh import from file using a unique module name incorporating mtime. Not placed in `sys.modules` to avoid cache pollution.

Running block instances are fully decoupled from the registry. A reload never affects in-flight workflows — only the next instantiation picks up new code.

### Alternatives considered

- **Store class references, use `importlib.reload()`**: reload produces a new class object. Old instances and new instances are incompatible under `isinstance`. Causes subtle breakage in port matching and type checking.
- **Restart the server on every change**: unacceptable UX for iterative development.
- **Hot-swap class references in running instances**: extremely complex, error-prone, and unsafe for stateful blocks mid-execution.

### Consequences

- Reload is safe and predictable: scan → update specs → notify frontend.
- Running workflows are never affected by reloads.
- Each fresh import has minor overhead (~ms per file) — acceptable for Tier 1 directories with typically <50 files.
- Tier 2 (pip packages) are not hot-reloaded — they update via `pip install --upgrade` and require restart.

---

## ADR-010: Batch execution mode declared per block

**Status**: superseded by ADR-020
**Date**: 2026-04-02

### Context

When processing a collection (e.g. 50 images), some blocks benefit from parallelism (Cellpose segmentation on CPU/GPU) while others require serial execution (napari manual review, one image at a time). A global batch strategy cannot accommodate both.

### Decision

Each block declares a `batch_mode` attribute:

- `PARALLEL`: all items through this block concurrently, then proceed to the next block. Uses `ProcessPoolExecutor` (CPU) or `ThreadPoolExecutor` (IO).
- `SERIAL`: each item runs through the full downstream sub-pipeline before the next item starts. Required for interactive/external blocks.
- `ADAPTIVE` (default): engine performs look-ahead on the DAG. If any downstream block in the same branch is SERIAL or INTERACTIVE, current block runs in SERIAL mode to avoid buffering. Otherwise, PARALLEL.

A `ResourceManager` throttles parallel dispatch based on GPU slots, CPU workers, and memory budget. Blocks declare resource needs via `ResourceRequest`.

### Alternatives considered

- **Global batch mode (entire workflow is parallel or serial)**: too coarse. A workflow with 8 auto blocks and 1 napari review block would be forced entirely serial, wasting parallelism on the 8 auto blocks.
- **No batch support (one item at a time always)**: unacceptable performance for automated pipelines with hundreds of items.
- **User configures batch mode per-run in the UI**: error-prone. The block author knows best whether their block supports parallelism. ADAPTIVE mode handles the common case automatically.

### Consequences

- Most blocks default to ADAPTIVE — authors only override for specific requirements.
- The engine's look-ahead scan adds minor complexity to the scheduler but eliminates the need for users to think about batch strategy.
- ResourceManager prevents GPU OOM by limiting concurrent GPU tasks even when batch_mode is PARALLEL.

---

## ADR-011: Workflow definition as declarative YAML, decoupled from frontend

**Status**: accepted  
**Date**: 2026-04-02

### Context

Workflows must be portable (shareable between users), version-controllable (git-friendly), machine-readable (AI synthesis and validation), and renderable by different frontends.

### Decision

Workflows are serialised as YAML files defining nodes (block type + config) and edges (source port → target port). The ReactFlow canvas is one visualisation of this definition, not the definition itself. An optional `layout` field per node stores canvas position for visual restoration.

### Alternatives considered

- **ReactFlow's internal JSON as the source of truth**: couples the workflow definition to a specific frontend library's data model. Makes headless execution, CLI validation, and AI synthesis harder.
- **Python DSL (workflow defined in code)**: powerful but excludes non-developers. YAML is readable by anyone and editable in any text editor.
- **Visual-only (no serialised format, workflow lives in the UI)**: makes version control, sharing, and headless execution impossible.

### Consequences

- Workflows are portable `.yaml` files that can be committed to git, shared via email, or published alongside papers.
- The `scieasy run workflow.yaml` CLI can execute workflows headlessly without a frontend.
- AI can generate and modify workflows by producing YAML.
- Frontend layout information is optional metadata — losing it only means the canvas auto-layouts on next open.

---

## ADR-012: Checkpoint-based pause and resume

**Status**: accepted  
**Date**: 2026-04-02

### Context

Workflows can be long-running (hours for large batch processing) and include interactive steps (AppBlock waiting for user action in external software). Users may close the browser, the machine may crash, or a collaborator may need to pick up where someone else left off.

### Decision

The engine serialises a `WorkflowCheckpoint` after every block completion:

- Block states (DONE / PAUSED / IDLE for each node).
- `StorageReference` for all intermediate outputs produced so far.
- ID of the pending block (if paused for interactive/external action).
- Full config snapshot at checkpoint time.

Checkpoints are saved to `{project}/checkpoints/` as JSON + references to Zarr/Parquet data. Resuming loads the latest checkpoint, skips completed blocks, and continues from the pending block.

### Alternatives considered

- **No checkpointing (always restart from the beginning)**: unacceptable for workflows with expensive blocks (hours of GPU compute) or interactive steps.
- **In-memory state only (no persistence)**: lost on browser close or crash.
- **Full data duplication at each checkpoint**: storage-prohibitive for large datasets. Storing `StorageReference` pointers instead of copying data keeps checkpoints lightweight.

### Consequences

- Crash recovery without re-running completed blocks.
- Collaborative handoff: one person runs automated steps, saves checkpoint, another person does manual review.
- Checkpoint files reference intermediate data by storage path — if underlying data is moved or deleted, checkpoint becomes invalid.

---

## ADR-013: AI as a four-tier service layer, not embedded in the core

**Status**: accepted  
**Date**: 2026-04-02

### Context

The framework aims to be "AI-native" — AI should be able to generate blocks, compose workflows, extend type hierarchy, and optimise parameters. But tightly coupling AI into the core would make the framework unusable offline or without API keys.

### Decision

AI capabilities are a separate service layer (Layer 4) that calls into the core layers but is not called by them. Four tiers:

1. **Block generation**: NL description → any of the five block categories.
2. **Type generation**: NL description → DataObject subtypes with helper methods.
3. **Workflow synthesis**: data description + goal → complete DAG.
4. **Runtime parameter optimisation**: observe intermediate results → suggest parameter adjustments.

All AI features are optional. The framework is fully functional without them. AI-generated code passes through a validation pipeline (static analysis → dry run → port contract check → user review) before registration.

### Alternatives considered

- **AI deeply integrated (e.g. automatic type inference on every connection, AI-driven error recovery)**: makes behaviour unpredictable, adds latency to basic operations, and creates hard dependency on LLM availability.
- **No AI (add later as plugins)**: misses the opportunity to design generation-friendly interfaces from the start. Validation pipeline, config schemas, and convention-based entry functions are all designed with AI generation in mind.

### Consequences

- Framework works offline, on air-gapped machines, without API keys.
- AI features degrade gracefully — if the LLM is unavailable, users manually write blocks and compose workflows.
- The validation pipeline adds safety but also latency to AI generation (~seconds for dry run).
- AI-generated blocks are indistinguishable from hand-written blocks once validated — no second-class citizenship.

---

## ADR-014: ReactFlow + FastAPI as the frontend-backend stack

**Status**: accepted  
**Date**: 2026-04-02

### Context

The framework needs a visual workflow editor (drag-drop blocks, wire connections, live status) backed by a Python server (scientific computing ecosystem). The frontend-backend boundary must support real-time updates (block progress, interactive prompts) and large file transfers.

### Decision

- **Frontend**: React + ReactFlow (node-graph canvas) + Zustand (state) + shadcn/ui (components).
- **Backend**: FastAPI (REST + WebSocket + SSE) with Pydantic validation.
- **Communication**: REST for CRUD, WebSocket for real-time block state / interactive signals, SSE for log streaming.

### Alternatives considered

- **Desktop-native (PyQt / Electron + Python)**: richer OS integration but harder to distribute, update, and extend. Web-based approach works on any OS and allows future multi-user scenarios.
- **Streamlit or Panel**: rapid prototyping but limited control over complex UIs like node-graph editors. ReactFlow is the mature, purpose-built solution for visual workflow canvases.
- **Django or Flask instead of FastAPI**: FastAPI's native async support, automatic OpenAPI docs, WebSocket handling, and Pydantic integration make it the better fit for a real-time, schema-heavy API.

### Consequences

- Two-language codebase (Python backend + TypeScript frontend). Manageable because the boundary is a well-defined API.
- ReactFlow provides minimap, zoom, drag-drop, and connection validation out of the box.
- WebSocket enables sub-second UI updates during workflow execution.

---

## ADR-015: Inclusive strategy — wrap existing tools, never replace

**Status**: accepted  
**Date**: 2026-04-02

### Context

Researchers have years of investment in existing tools, scripts, and pipelines. Asking them to migrate is a non-starter. The framework must demonstrate immediate value by working with what they already have.

### Decision

The framework provides three integration mechanisms that cover the vast majority of existing tools:

- `CodeBlock` (inline + script mode): wrap any R/Python/Julia code with minimal modification.
- `AppBlock` (file-exchange bridge): integrate any GUI application that can read/write files.
- `SubWorkflowBlock`: encapsulate any existing multi-step pipeline as a reusable block.

The framework never reimplements functionality that existing tools do well. Instead, it provides the connective tissue between them.

### Alternatives considered

- **Provide built-in implementations for common operations (reimplementing ElMAVEN peak picking, Cellpose segmentation, etc.)**: duplicates effort, always lags behind the original tool, and fragments the user community.
- **Require formal plugins/adapters for every external tool**: too much upfront work. File-exchange bridge works with any tool immediately.

### Consequences

- Users see value from day one: put existing scripts and tools into blocks, wire them together, gain reproducibility and multi-modal integration.
- The framework's value proposition is composition and integration, not replacing any single tool.
- File-based integration is slower than in-process integration but universally compatible.
- Community can build tighter integrations (e.g. programmatic Cellpose block) as ProcessBlock subclasses when the default file-exchange approach becomes a bottleneck.

---

## ADR-016: Per-port InputDelivery for CodeBlock data handoff

**Status**: partially superseded by ADR-020  
**Date**: 2026-04-02  
**Supersession note**: ADR-020 introduces Collection-based transport with auto-unpack/repack for CodeBlock (ADR-020-Add4). MEMORY is now the only delivery mode; PROXY and CHUNKED are removed. Users who need lazy access should write a ProcessBlock instead. The `InputDelivery` enum has been deleted.

### Context

The framework promises lazy loading via ViewProxy (ADR-007) — DataObjects are lightweight wrappers, and blocks receive proxies that load data on demand. However, CodeBlock must bridge between this framework-internal abstraction and user scripts that expect native Python/R objects (numpy arrays, pandas DataFrames). The original CodeBlock implementation called `proxy.to_memory()` on every input unconditionally, meaning a 100 GB MSImage connected to a CodeBlock would be fully loaded into memory regardless of whether the script needed all of it. This silently violated the lazy-loading contract for any CodeBlock with large inputs.

The tension is fundamental: user scripts written in plain numpy/pandas/R cannot operate on a `ViewProxy` object — they need real data. But forcing full materialisation on every input makes the memory boundary architecture meaningless at the CodeBlock boundary.

### Decision

Each input port on a CodeBlock independently declares an `InputDelivery` mode that controls how data is handed to the user's script:

| Mode | What the script receives | When to use |
|---|---|---|
| `MEMORY` (default) | Native object via `proxy.to_memory()` | Small-to-medium data. Compatible with any script. |
| `PROXY` | The `ViewProxy` itself | Large data, experienced user controls `.slice()` / `.iter_chunks()` |
| `CHUNKED` | One chunk per invocation (framework iterates) | Large homogeneous batches where each chunk is processed identically |

Inline mode is locked to MEMORY (short scripts should not manage proxies). Script mode supports all three, configured via the `input_delivery` key in the script's `configure()` return value, or overridden per-port in the UI config panel.

For MEMORY mode, the framework displays a warning in the config panel when an input exceeds a configurable threshold (default 2 GB), suggesting the user switch to PROXY or CHUNKED delivery.

For CHUNKED mode, the framework calls the script's `run()` function once per chunk, passing the chunk as a native object. Non-chunked inputs are prepared once and reused across all chunk invocations. The framework concatenates per-chunk outputs into the final result.

### Alternatives considered

- **Always `to_memory()` (original design)**: simple, universally compatible, but breaks the lazy-loading promise for large data. A single CodeBlock with a 100 GB MSI input would OOM.
- **Always pass ViewProxy (never materialise)**: breaks all existing scripts. `np.mean(proxy)` doesn't work. Requires every user to learn the ViewProxy API. Unacceptable friction.
- **Auto-detect based on data size (small → memory, large → proxy)**: unpredictable. The user writes a script expecting a numpy array, then it silently becomes a ViewProxy when the dataset grows. Debugging nightmare.
- **ProcessBlock-style (always pass proxy, block author calls `.to_memory()` explicitly)**: reasonable for ProcessBlock authors who are writing framework-aware code, but CodeBlock users are writing standalone scripts that should work without framework knowledge.

### Consequences

- Default behaviour (MEMORY) is unchanged for 90% of CodeBlock usage — no learning curve for simple scripts.
- PROXY and CHUNKED modes are opt-in, only relevant when large data enters a CodeBlock.
- The `configure()` convention gains a new `input_delivery` key — framework introspection reads it and adjusts the config panel accordingly.
- CHUNKED mode adds complexity to the CodeBlock bridge (iteration loop, result concatenation) but keeps user scripts simple (process one chunk, return result).
- The framework-user boundary is now explicit and documented rather than a hidden `to_memory()` call. Users who connect large data to CodeBlock without choosing PROXY/CHUNKED see a clear warning rather than a silent OOM.
- ProcessBlock does not need InputDelivery — ProcessBlock authors write framework-aware code and receive ViewProxy directly, deciding for themselves when to materialise.

---

## ADR-017: Subprocess isolation for all block execution

**Status**: accepted
**Date**: 2026-04-03

### Context

The original architecture implicitly assumed that blocks could execute in-process. Specifically:

- `CodeBlock` inline mode executes user code via `exec(script, namespace)` in the engine's Python process (`src/scieasy/blocks/code/runners/python_runner.py:27`).
- `CodeBlock` script mode loads user scripts via `importlib.util.spec_from_file_location()` and calls `spec.loader.exec_module(module)` in the engine's process (`python_runner.py:62–67`).
- `RRunner` was planned to use `rpy2` (in-process bridge) per its docstring (`src/scieasy/blocks/code/runners/r_runner.py:12`).
- `JuliaRunner` was planned to use `juliacall` (in-process bridge) per its docstring (`src/scieasy/blocks/code/runners/julia_runner.py:12`).
- `ProcessBlock` subclasses have their `run()` method called directly by the engine.
- `AppBlock` already launches an external subprocess via `subprocess.Popen` (`src/scieasy/blocks/app/bridge.py:81–86`), but the Popen handle is returned from `launch()` and never stored, tracked, or used for lifecycle management.

This creates fundamental problems:

1. **Unrecoverable hangs**: if user code enters an infinite loop, deadlocks, or blocks on I/O, the engine's main process freezes. Python threads cannot be reliably killed (`threading` has no `kill()` API; `ctypes.pythonapi.PyThreadState_SetAsyncExc` is unreliable for C-extension code like scipy, cellpose, and numpy). The scheduler, all other blocks, and the API server become unresponsive.

2. **No cancellation path**: the framework must support user-initiated cancellation of any running block at any time (ADR-018). Cancellation requires the ability to forcefully terminate execution. Only OS-level process termination provides a reliable kill guarantee across all code (pure Python, C extensions, R, Julia, external applications).

3. **Memory and crash isolation**: a block that segfaults (common with native C/Fortran extensions), triggers OOM, or leaks memory only affects its own subprocess. Without process isolation, a single misbehaving block can crash or degrade the entire engine.

4. **Resource accounting**: with all blocks in subprocesses, the ResourceManager can track actual system resource usage per-process (via OS-level metrics) rather than relying solely on declared estimates.

### Discussion points and resolution

| # | Topic | Options discussed | Final decision |
|---|---|---|---|
| 1 | Should framework-internal `ProcessBlock` get an `IN_PROCESS` fast path? | (A) Allow `IN_PROCESS` for trusted ProcessBlocks to save ~100ms subprocess startup. (B) All blocks subprocess, no exceptions. | **Decision: (B).** The complexity of maintaining two execution models in the scheduler, resource manager, and cancellation system outweighs the ~100ms savings. All blocks are treated identically. |
| 2 | Should `CodeBlock` inline mode remain `exec()` for simplicity? | (A) Keep `exec()` for inline only (short scripts, low risk). (B) All CodeBlock modes go through subprocess. | **Decision: (B).** Even short inline scripts can call `time.sleep(999999)` or import a module that hangs. The user cannot distinguish "inline" from "script" at the risk level. Uniform subprocess execution. |
| 3 | Use `multiprocessing.Process` or `subprocess.Popen`? | (A) `multiprocessing.Process` — convenient Python API, shared memory support. (B) `subprocess.Popen` — clean interpreter, no inherited state. | **Decision: (B).** `multiprocessing` fork/spawn inherits the engine's loaded modules and memory (hundreds of MB for a long-running server). `subprocess.Popen` starts a clean Python interpreter, importing only what the block needs. Cleaner isolation, more predictable memory. |
| 4 | How to handle cross-process data transfer? | (A) Serialise full data payloads across the process boundary (pickle/JSON). (B) Pass `StorageReference` only; subprocess rebuilds `ViewProxy` from storage. | **Decision: (B).** Leverages the existing lazy-loading architecture (ADR-007). `DataObject` instances are lightweight wrappers (~KB) holding `StorageReference` pointers. The subprocess reconstructs `ViewProxy` from the storage reference and accesses data directly from the backing store (Zarr/Parquet/filesystem). Output follows the same pattern: subprocess writes results to storage and returns `StorageReference` pointers. Cross-process overhead is limited to process startup + reference serialisation (~100ms), not data copying. |

### Decision

**All blocks execute in isolated subprocesses. No exceptions.** The engine process becomes a pure orchestrator that never executes block logic directly.

#### Execution model per block category

| Category | Previous execution model | New execution model | Change required |
|---|---|---|---|
| `ProcessBlock` | In-process `run()` call | Subprocess: serialise `StorageReference` → spawn Python subprocess → subprocess imports block class, reconstructs `ViewProxy`, calls `run()` → subprocess writes outputs to storage → return `StorageReference` | **New**: subprocess wrapper |
| `CodeBlock` (inline, Python) | `exec(script, namespace)` in engine process (`python_runner.py:27`) | Subprocess: engine sends script string + `StorageReference` via stdin/tempfile → subprocess reconstructs data, calls `exec()` → writes outputs → return references | **Rewrite**: `PythonRunner.execute_inline()` |
| `CodeBlock` (script, Python) | `importlib.util.spec_from_file_location()` in engine process (`python_runner.py:62–67`) | Subprocess: engine sends script path + `StorageReference` + config → subprocess loads module, calls entry function → writes outputs → return references | **Rewrite**: `PythonRunner.execute_script()` |
| `CodeBlock` (R) | Planned `rpy2` in-process bridge (`r_runner.py:12`) | Subprocess calling `Rscript`: engine writes inputs to temp JSON/files → `subprocess.Popen(["Rscript", wrapper.R, ...])` → R script reads inputs, runs user code, writes outputs → engine reads outputs | **Rewrite**: `RRunner` entirely |
| `CodeBlock` (Julia) | Planned `juliacall` in-process bridge (`julia_runner.py:12`) | Subprocess calling `julia`: same pattern as R | **Rewrite**: `JuliaRunner` entirely |
| `AppBlock` | `subprocess.Popen` already external, but handle discarded (`bridge.py:81–86`) | `subprocess.Popen` with handle stored in `ProcessHandle`, registered in `ProcessRegistry`, monitored by `ProcessMonitor` | **Modify**: `FileExchangeBridge.launch()` return type and handle registration |
| `AIBlock` | HTTP API call (already async/non-blocking) | Subprocess for isolation consistency: subprocess makes HTTP call, returns result. Alternatively, since HTTP calls are non-blocking and cancellable via `asyncio`, AIBlock _may_ remain in-process as a documented exception if profiling shows subprocess overhead is problematic for latency-sensitive AI calls. Initial implementation: subprocess. | **New**: subprocess wrapper |
| `IOBlock` | In-process file I/O | Subprocess: particularly important for large file reads that may OOM or hang on network filesystems | **New**: subprocess wrapper |
| `SubWorkflowBlock` | Recursive engine call | Subprocess with child DAGScheduler: the child workflow runs in its own process with its own scheduler, communicating results back via `StorageReference` | **New**: subprocess wrapper with nested scheduler |

#### Cross-process data transfer protocol

```
Engine process (orchestrator)              Block subprocess (worker)
────────────────────────────               ──────────────────────────
1. Prepare invocation payload:
   {
     "block_class": "scieasy.blocks.process.cellpose.CellposeSegment",
     "block_config": { "diameter": 30, "model": "cyto2" },
     "inputs": {
       "image": {
         "storage_ref": "zarr:///project/data/zarr/img_001",
         "dtype_info": {"type_chain": ["FluorImage","Image","Array","DataObject"]}
       }
     },
     "output_storage_dir": "/project/data/zarr/run_001/"
   }

2. Spawn subprocess:                      3. Subprocess starts clean Python interpreter.
   Popen(["python", "-m",                    Reads payload from stdin.
     "scieasy.engine.runners.worker",         Imports block class.
     ...])                                    Reconstructs ViewProxy from storage_ref.
   Register ProcessHandle.                    Calls block.run(inputs, config).
                                              Writes outputs to output_storage_dir.
                                              Prints output references to stdout.

4. Engine reads stdout.                   5. Subprocess exits with code 0.
   Parses output StorageReference(s).
   Deregisters ProcessHandle.
   Stores references for downstream blocks.
```

The payload is serialised as JSON via stdin (small payloads, <10 KB typically) or via a temporary file (for complex configs). The subprocess reads the payload, performs all heavy work, and returns lightweight references.

**Key invariant**: no scientific data crosses the process boundary. Only `StorageReference` pointers (~100 bytes each) and config dicts cross. The 100 GB MSI dataset stays in Zarr on disk; both the engine and the subprocess access it via `ViewProxy` pointing at the same storage path.

#### Platform-specific process lifecycle management

| Operation | Linux / macOS | Windows |
|---|---|---|
| Process group creation | `subprocess.Popen(..., start_new_session=True)` creates a new session and process group. `os.getpgid(pid)` retrieves the group ID. | `subprocess.Popen(..., creationflags=CREATE_NEW_PROCESS_GROUP)` for basic group. For full tree management: `CreateJobObject()` + `AssignProcessToJobObject()` via `ctypes` or `win32api`. Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` ensures child cleanup. |
| Graceful termination | `os.killpg(pgid, signal.SIGTERM)` sends SIGTERM to entire process group. Grace period (configurable, default 5 seconds) allows cleanup handlers to run. | Windows has no equivalent of SIGTERM. `GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, pid)` can be sent to console processes, but many GUI applications ignore it. Practical approach: skip grace period on Windows, go directly to forced termination. |
| Forced termination | `os.killpg(pgid, signal.SIGKILL)` after grace period expires. Cannot be caught or ignored. | `TerminateProcess(handle, exit_code)` via `ctypes`. For Job Objects: `TerminateJobObject(job_handle, exit_code)` kills all processes in the job. |
| Process tree termination | `os.killpg(pgid, signal)` kills all processes in the group. Processes that `setsid()` to escape the group are not affected (rare in scientific tools). | Job Objects are the authoritative mechanism. `TerminateJobObject()` kills all processes assigned to the job, including grandchildren. Without Job Objects, `taskkill /T /F /PID {pid}` can be used as fallback (requires subprocess call). |
| Process alive check | `os.kill(pid, 0)` — sends signal 0 (no-op) to test if process exists. Raises `ProcessLookupError` if dead, `PermissionError` if alive but owned by another user. | `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)` via `ctypes`. If it returns a valid handle, the process exists. Then `GetExitCodeProcess()` — if it returns `STILL_ACTIVE (259)`, the process is running. |
| Zombie process cleanup | `os.waitpid(pid, os.WNOHANG)` to reap zombie (child exited but parent hasn't waited). Must be called after detecting death to prevent zombie accumulation. | Not applicable. Windows automatically cleans up process entries when all handles to the process are closed. |
| Subprocess launch isolation | `start_new_session=True` in `Popen` kwargs. This calls `setsid()` in the child, detaching it from the engine's terminal/session. Prevents Ctrl-C from the terminal propagating to block subprocesses. | `CREATE_NEW_PROCESS_GROUP` flag in `Popen` `creationflags`. Prevents Ctrl-C propagation. Combined with Job Object for lifecycle management. |

All platform-specific code is encapsulated in `ProcessHandle` (ADR-019) and `engine/runners/platform.py`. The rest of the codebase interacts with `ProcessHandle.terminate()`, `ProcessHandle.is_alive()`, etc., without knowing the underlying platform.

### Alternatives considered

- **Keep `IN_PROCESS` as an option for trusted/fast blocks**: creates two execution models that the scheduler, resource manager, and cancellation system must each handle separately. Doubles the testing surface for execution lifecycle. The ~100ms subprocess startup overhead is negligible for scientific workflows where blocks typically run for seconds to hours. If profiling later reveals subprocess overhead is a bottleneck for specific hot-path blocks, a fast-path optimisation can be added as a targeted, documented exception — but the architectural default must be subprocess.

- **Use threads with cooperative cancellation (cancellation tokens / flags)**: requires every block author to periodically check a cancellation flag in their `run()` method. User scripts and third-party libraries (scipy.optimize, cellpose.eval, DESeq2) will never check a framework-specific cancellation flag. A hung native C extension call (common in scientific computing) will never yield to Python's thread scheduler. Only OS-level process termination is reliable.

- **Use `multiprocessing.Process` instead of `subprocess.Popen`**: `multiprocessing` uses fork (on Linux) or spawn to create a copy of the parent process, inheriting all loaded modules and memory. For a long-running engine with dozens of imported packages, the child starts with hundreds of MB of unnecessary state. `subprocess.Popen` starts a clean Python interpreter, importing only what the block needs. Additionally, `multiprocessing` shares some global state (logging config, signal handlers) in ways that can interfere with block execution. `subprocess.Popen` provides cleaner isolation.

- **Use Docker containers for isolation**: maximum isolation but massive overhead (seconds to start, GB of disk per image, requires Docker installation). Appropriate for future cloud/multi-user deployment (the `CONTAINER` level in `SandboxPolicy`) but overkill for single-user local installations. Subprocess isolation provides the necessary safety with minimal overhead.

### Consequences

- The engine process is protected from block crashes, hangs, segfaults, and memory leaks. A block that OOMs only kills its own subprocess; the engine continues running.
- Every block is cancellable at any time via `ProcessHandle.terminate()` (ADR-018, ADR-019).
- Subprocess startup adds ~50–200ms overhead per block execution. For scientific workflows where blocks typically run seconds to hours, this is negligible (<0.1% of execution time).
- Block authors do not need to change their code. The framework handles serialisation of `StorageReference` and reconstruction of `ViewProxy` transparently in the subprocess worker.
- R execution is simplified: always `subprocess` calling `Rscript`, no `rpy2` in-process bridge complexity. Julia execution: always `subprocess` calling `julia`, no `juliacall` dependency.
- The `SandboxPolicy` enum from Appendix C.3 of the architecture document is partially realised: `SUBPROCESS` is now the universal baseline rather than a future option. `CONTAINER` and `WASM` remain future extensions that build on the same `ProcessHandle` abstraction.
- Platform-specific process management (signals, process groups, Job Objects) is encapsulated in `ProcessHandle` and `engine/runners/platform.py`, keeping the rest of the codebase platform-agnostic.
- A new module `engine/runners/worker.py` must be created as the subprocess entry point. This module receives the invocation payload, sets up the execution environment, runs the block, and returns results.

### EventBus integration

| Event type | Emitted by | Payload fields | Subscribers |
|---|---|---|---|
| `PROCESS_SPAWNED` | `spawn_block_process()` | `block_id: str`, `pid: int`, `resource_request: ResourceRequest` | `ProcessRegistry` (register handle), `ResourceManager` (record allocation) |
| `PROCESS_EXITED` | `ProcessMonitor` | `block_id: str`, `exit_info: ProcessExitInfo` | `DAGScheduler` (update block state), `ResourceManager` (release resources), `ProcessRegistry` (deregister handle), `CheckpointManager` (save state) |

### Detailed impact scope

#### New files

| File | Contents | Key classes/functions |
|---|---|---|
| `src/scieasy/engine/runners/worker.py` | **Subprocess entry point.** Reads invocation payload from stdin (JSON), imports block class, reconstructs `ViewProxy` from `StorageReference`, calls `block.run()`, writes outputs to storage, prints output `StorageReference` JSON to stdout, exits. | `def main() -> None` (entry point), `def reconstruct_inputs(payload: dict) -> dict[str, ViewProxy]` (rebuild proxies from storage refs), `def serialise_outputs(outputs: dict, output_dir: Path) -> dict` (write outputs, return refs) |
| `src/scieasy/engine/runners/platform.py` | **Platform abstraction layer.** Isolates all OS-specific process management (signals, process groups, Job Objects, alive checks, zombie cleanup). | `class PlatformOps(Protocol)` with methods: `create_process_group(popen: Popen) -> None`, `terminate_tree(pid: int, grace_period: float) -> ProcessExitInfo`, `kill_tree(pid: int) -> ProcessExitInfo`, `is_alive(pid: int) -> bool`, `get_exit_info(pid: int) -> ProcessExitInfo`. Implementations: `class PosixOps(PlatformOps)` (Linux+macOS), `class WindowsOps(PlatformOps)` (Windows). Factory: `def get_platform_ops() -> PlatformOps`. |
| `src/scieasy/engine/runners/process_handle.py` | **ProcessHandle and ProcessRegistry.** See ADR-019 for complete specification. Created as a separate file rather than in `process_mgr.py` because it is an engine-layer concern, not a block-layer concern. | See ADR-019 |
| `src/scieasy/engine/runners/process_monitor.py` | **ProcessMonitor background coroutine.** See ADR-019 for complete specification. | See ADR-019 |

#### Rewritten files

| File | Current state | New state | Detailed changes |
|---|---|---|---|
| `src/scieasy/blocks/code/runners/python_runner.py` | `execute_inline()`: calls `exec(script, namespace)` in-process (line 27). `execute_script()`: calls `importlib.util.spec_from_file_location()` + `spec.loader.exec_module()` in-process (lines 62–67). | Both methods prepare an invocation payload and delegate to `spawn_block_process()`. The actual `exec()` / `importlib` logic moves to `worker.py` and only runs inside the subprocess. | `execute_inline(self, script, namespace) -> dict`: **remove** `exec(script, namespace)` call. **Replace with**: build payload `{"mode": "inline", "script": script, "inputs": serialise_refs(namespace)}`, call `spawn_block_process(["python", "-m", "scieasy.engine.runners.worker"], ...)`, read stdout for output refs, return deserialised outputs. The `exec()` call itself moves to `worker.py`. `execute_script(self, script_path, entry_function, inputs, config) -> dict`: **remove** `importlib.util.spec_from_file_location()` + `exec_module()` calls. **Replace with**: build payload `{"mode": "script", "script_path": str(script_path), "entry_function": entry_function, "inputs": serialise_refs(inputs), "config": config}`, call `spawn_block_process(...)`, read stdout. The `importlib` loading moves to `worker.py`. **Remove** import of `importlib.util` (line 2). **Add** imports: `from scieasy.engine.runners.process_handle import spawn_block_process`. |
| `src/scieasy/blocks/code/runners/r_runner.py` | Both methods raise `NotImplementedError` with message suggesting `rpy2` (lines 17–18, 29–30). | **Remove** all `rpy2` references from docstring and error messages. Implement both methods using subprocess calling `Rscript`. | `execute_inline(self, script, namespace) -> dict`: write `script` to a temp `.R` file, write inputs to temp JSON files, build a wrapper R script that reads JSON inputs, `source()`s the user script, writes JSON outputs. Call `spawn_block_process(["Rscript", wrapper_path, ...])`. Parse output JSON. `execute_script(self, script_path, entry_function, inputs, config) -> dict`: write inputs to temp JSON files, build wrapper R script that calls `source(script_path)` then calls `entry_function(inputs, config)`, writes output JSON. Call `spawn_block_process(["Rscript", wrapper_path, ...])`. Parse output JSON. **Remove** docstring line "Planned backends: rpy2 (in-process)". **Add** docstring: "Executes R code in an isolated Rscript subprocess." |
| `src/scieasy/blocks/code/runners/julia_runner.py` | Both methods raise `NotImplementedError` with message suggesting `juliacall` (lines 17–18, 29–30). | **Remove** all `juliacall` references. Implement both methods using subprocess calling `julia`. | Same pattern as `RRunner`: write inputs to temp JSON, build wrapper Julia script, call `spawn_block_process(["julia", wrapper_path, ...])`, parse output JSON. **Remove** docstring line "Planned backends: juliacall (in-process)". **Add** docstring: "Executes Julia code in an isolated julia subprocess." |
| `src/scieasy/engine/runners/local.py` | All three methods (`run`, `check_status`, `cancel`) raise `NotImplementedError` (lines 37, 52, 62). Class docstring says "in the local process or as a local subprocess" (line 9). | **Implement** all three methods using subprocess execution via `spawn_block_process()`. Remove "in the local process" from docstring. | `run(self, block, inputs, config) -> dict`: build invocation payload from `block.__class__`, `inputs` (converted to `StorageReference` dicts), and `config`. Call `spawn_block_process()` to get `ProcessHandle`. Await subprocess completion by reading stdout. Parse output `StorageReference` JSON. Return output mapping. Store `ProcessHandle` in `self._active_runs: dict[str, ProcessHandle]` keyed by `run_id`. `check_status(self, run_id) -> Any`: look up `ProcessHandle` from `self._active_runs[run_id]`. Call `handle.is_alive()`. If alive, return `BlockState.RUNNING`. If exited, return `handle.exit_info()`. `cancel(self, run_id) -> None`: look up `ProcessHandle`. Call `await handle.terminate(grace_period_sec=5.0)`. Remove from `self._active_runs`. **Add** instance attribute: `self._active_runs: dict[str, ProcessHandle] = {}`. **Add** imports: `from scieasy.engine.runners.process_handle import ProcessHandle, spawn_block_process`. **Change** class docstring from "in the local process or as a local subprocess" to "as an isolated local subprocess". |
| `src/scieasy/blocks/code/code_block.py` | `run()` (lines 38–77): directly calls `runner.execute_inline()` or `runner.execute_script()`, performs state transitions (`self.transition(BlockState.RUNNING)`, `self.transition(BlockState.DONE)`), and handles errors. | `run()` no longer performs state transitions directly (the engine/scheduler manages state transitions based on subprocess exit). The method prepares the execution request and returns it. State transitions move to the scheduler layer. | `run(self, inputs, config) -> dict`: **remove** `self.transition(BlockState.RUNNING)` (line 42) and `self.transition(BlockState.DONE)` (line 73) — state transitions are managed by the scheduler based on subprocess lifecycle, not by the block itself. **Remove** try/except that catches `Exception` and calls `self.transition(BlockState.ERROR)` (lines 43, 75–77) — error detection is based on subprocess exit code, handled by the scheduler. The method becomes a pure function: prepare inputs, select runner, call runner method, return results. **Note**: `_prepare_inputs()` (lines 79–112) logic for `InputDelivery.MEMORY` (calling `value.to_memory()`) moves inside the subprocess worker, because `to_memory()` loads data into the subprocess's memory, not the engine's. The engine-side `_prepare_inputs()` changes to: for all delivery modes, convert `ViewProxy` to `StorageReference` dict (lightweight). The subprocess-side `worker.py` handles the actual delivery mode dispatch. |

#### Modified files

| File | Current state | Changes | Detailed field/parameter changes |
|---|---|---|---|
| `src/scieasy/blocks/app/bridge.py` | `launch()` (line 75) returns `subprocess.Popen[bytes]`. The Popen handle is created with `subprocess.Popen([command, str(exchange_dir)], cwd=..., stdout=PIPE, stderr=PIPE)` (lines 81–86). Handle is returned but never stored or registered by caller. | `launch()` must use `spawn_block_process()` and return `ProcessHandle` instead of raw `Popen`. | `launch(self, command: str, exchange_dir: Path) -> ProcessHandle`: **change return type** from `subprocess.Popen[bytes]` to `ProcessHandle`. **Replace** `subprocess.Popen(...)` call with `spawn_block_process(block_id=..., command=[command, str(exchange_dir)], resource_request=ResourceRequest(), cwd=str(exchange_dir))`. **Add** `block_id: str` parameter to `launch()` signature (needed for `ProcessHandle` registration). **Add** import: `from scieasy.engine.runners.process_handle import ProcessHandle, spawn_block_process`. **Remove** import: `import subprocess` (line 6, no longer directly used). The `ExternalAppBridge` protocol (line 12) must update `launch()` signature to return `ProcessHandle` and accept `block_id`. |
| `src/scieasy/blocks/app/app_block.py` | `run()` (lines 48–102): calls `bridge.launch(command, exchange_dir)` (line 75) but discards the return value. Error handling: bare `except Exception` → `self.transition(BlockState.ERROR)` → `raise` (lines 100–102). | Must store the `ProcessHandle` from `bridge.launch()`. Must pass `block_id` to `bridge.launch()`. State transitions move to scheduler (same as CodeBlock). | `run()`: **change** line 75 from `bridge.launch(command, exchange_dir)` to `self._process_handle = bridge.launch(block_id=self._block_id, command=command, exchange_dir=exchange_dir)`. **Add** instance attribute: `self._process_handle: ProcessHandle | None = None`. **Add** `self._block_id: str` parameter to `__init__()` (or set by the scheduler before `run()`). **Remove** `self.transition(BlockState.RUNNING)` (line 57), `self.transition(BlockState.PAUSED)` (line 74), `self.transition(BlockState.RUNNING)` (line 94), `self.transition(BlockState.DONE)` (line 97) — state transitions managed by scheduler. **Remove** try/except ERROR transition (lines 100–102) — error detection via subprocess exit code. |
| `src/scieasy/blocks/app/watcher.py` | `wait_for_output()` (lines 47–72): polls for files only. No process awareness. Timeout raises `TimeoutError`. | **Add** optional `process_handle: ProcessHandle | None` parameter to `__init__()` and `wait_for_output()`. When a process handle is provided, each poll iteration also checks `process_handle.is_alive()`. If the process has exited and no output files are detected, raise a new `ProcessExitedWithoutOutputError` instead of continuing to poll forever. | `__init__()`: **add** parameter `process_handle: ProcessHandle | None = None` after `poll_interval`. Store as `self._process_handle`. `wait_for_output()`: **add** inside the `while self._running:` loop (after `new_files` check, before timeout check): `if self._process_handle is not None and not await self._process_handle.is_alive(): exit_info = await self._process_handle.exit_info(); if not new_files: raise ProcessExitedWithoutOutputError(f"External process exited (code={exit_info.exit_code}) without producing output files matching {self.patterns}")`. **Add** new exception class at module level: `class ProcessExitedWithoutOutputError(RuntimeError): pass`. **Note**: `wait_for_output()` becomes `async` because `ProcessHandle.is_alive()` is async. This cascading change affects `AppBlock.run()` (must `await watcher.wait_for_output()`). |
| `src/scieasy/blocks/app/process_mgr.py` | Contains only a docstring: `"""External process lifecycle management (subprocess)."""` (line 1). Completely empty. | This file is superseded by `engine/runners/process_handle.py` and `engine/runners/process_monitor.py` (engine-layer concerns). | **Option A**: Delete the file entirely and remove from `__init__.py` imports. **Option B**: Keep as a thin re-export: `from scieasy.engine.runners.process_handle import ProcessHandle, ProcessRegistry`. **Recommended**: Option A (delete). The process lifecycle is an engine concern, not a block concern. Blocks interact with processes only through the `ProcessHandle` returned by `bridge.launch()`. |
| `src/scieasy/engine/runners/base.py` | `BlockRunner` protocol defines `run()` returning `dict[str, Any]` (line 16), `check_status()` returning `Any` (line 40), `cancel()` returning `None` (line 55). | `run()` return type changes to include `ProcessHandle` for lifecycle tracking. `check_status()` return type becomes structured. | `run()`: **change** return type from `dict[str, Any]` to `tuple[str, ProcessHandle]` where the `str` is a `run_id`. The actual output data is not returned by `run()` — instead, the scheduler reads outputs from storage after the subprocess exits. **Alternative**: `run()` returns a `RunHandle` dataclass containing `run_id: str`, `process_handle: ProcessHandle`, and a `result_future: asyncio.Future[dict[str, Any]]` that resolves when the subprocess completes. **Recommended**: the `RunHandle` approach, because it allows the scheduler to fire-and-forget and await the future when ready. **Add** new dataclass: `@dataclass class RunHandle: run_id: str; process_handle: ProcessHandle; result: asyncio.Future[dict[str, Any]]`. `check_status()`: **change** return type from `Any` to `BlockState`. `cancel()`: no signature change, but the docstring should note that cancellation is via `ProcessHandle.terminate()`. |
| `src/scieasy/blocks/base/block.py` | `_VALID_TRANSITIONS` dict (lines 13–20) defines allowed state transitions. No CANCELLED or SKIPPED states. | Updated in ADR-018 (see below). Listed here for completeness as a cross-ADR dependency. | See ADR-018 detailed impact scope. |
| `src/scieasy/engine/events.py` | `EngineEvent` dataclass with `event_type: str` (line 19). No defined event type constants. `EventBus` with `emit()`, `subscribe()`, `unsubscribe()` all raising `NotImplementedError`. | **Add** event type constants for `PROCESS_SPAWNED` and `PROCESS_EXITED`. EventBus implementation is part of ADR-018 (shared dependency). | **Add** at module level: `PROCESS_SPAWNED = "process_spawned"`, `PROCESS_EXITED = "process_exited"`. These are imported by `spawn_block_process()` and `ProcessMonitor` respectively. Full event type enumeration is in ADR-018. |

#### Documentation impact

| Document | Current state | Required changes |
|---|---|---|
| `docs/architecture/ARCHITECTURE.md` Section 5.1 (Block base class, lines 362–414) | Shows `Block.run()` being called directly, with no mention of subprocess isolation. | **Update** to describe that `run()` executes inside a subprocess, not in the engine process. Add a note that block authors do not need to change their code — the subprocess wrapper is transparent. |
| `docs/architecture/ARCHITECTURE.md` Section 5.3 (Block categories) | `CodeBlock` section (lines 563–784) describes `exec()` for inline mode, `importlib` for script mode, `rpy2` for R, `juliacall` for Julia. Mentions "`exec()` with a sandboxed namespace (inline), or subprocess / importlib for script mode" (line 781) and "R: via rpy2 bridge or subprocess calling Rscript" (line 782). | **Rewrite** the code runners paragraph (lines 780–783) to state all execution is via subprocess. **Remove** references to `exec()`, `importlib`, `rpy2`, `juliacall` as in-process execution paths. **Update** the framework bridge implementation code example (lines 704–772) to show subprocess delegation instead of direct runner calls. |
| `docs/architecture/ARCHITECTURE.md` Section 6.1 (DAG scheduler, lines 1024–1056) | `execute()` example shows direct block invocation: `result = await self.run_auto(block, inputs)` (line 1051). | **Update** to show subprocess-based execution: scheduler calls `runner.run()` which returns a `RunHandle`, then awaits `handle.result`. |
| `docs/architecture/ARCHITECTURE.md` Section 6.7 (Remote execution, lines 1209–1231) | `BlockRunner` protocol shows `async def run(self, block, inputs, config) -> dict` (line 1216). | **Update** return type to `RunHandle`. **Update** `LocalRunner` description from "Runs blocks in-process or as local subprocesses" to "Runs blocks as isolated local subprocesses". |
| `docs/architecture/ARCHITECTURE.md` Appendix C.3 (Sandbox policy, lines 1832–1847) | Lists `SandboxPolicy` enum with `NONE` as current default. States "Not implementing in v1". | **Update** to note that `SUBPROCESS` is now the universal default (no longer `NONE`). `NONE` is removed as an option. `CONTAINER` and `WASM` remain future. |
| `docs/architecture/ARCHITECTURE.md` Section 11 (Technology stack, lines 1690–1708) | Lists "Process management: subprocess + watchdog" (line 1700). | **Add** "Process lifecycle: ProcessHandle + ProcessRegistry + ProcessMonitor" to the table. **Note** platform abstraction: "Cross-platform process management via platform.py (POSIX signals + process groups / Windows Job Objects + TerminateProcess)". |

---

## ADR-018: Block cancellation, graceful workflow degradation, and event-driven runtime

**Status**: accepted
**Date**: 2026-04-03

### Context

The original architecture defined only the happy path for block execution. Specifically:

- `BlockState` enum (`src/scieasy/blocks/base/state.py:8–16`) defines six states: `IDLE`, `READY`, `RUNNING`, `PAUSED`, `DONE`, `ERROR`. There is no state for user-initiated cancellation or for blocks that cannot execute due to upstream failure.

- `_VALID_TRANSITIONS` (`src/scieasy/blocks/base/block.py:13–20`) defines the state machine:
  ```
  IDLE    → {READY, ERROR}
  READY   → {RUNNING, ERROR}
  RUNNING → {DONE, PAUSED, ERROR}
  PAUSED  → {RUNNING, ERROR}
  DONE    → {IDLE}
  ERROR   → {IDLE}
  ```
  No transition leads to a "cancelled" or "skipped" state.

- `DAGScheduler` (`src/scieasy/engine/scheduler.py:8–54`) is a skeleton with `execute()`, `pause()`, `resume()`, and `save_checkpoint()` all raising `NotImplementedError`. There is no `cancel_block()` or `cancel_workflow()` method. The architecture document describes `execute()` as a simple for-loop over topological sort (ARCHITECTURE.md lines 1039–1056), with no ability to respond to external signals during execution.

- `EventBus` (`src/scieasy/engine/events.py:25–62`) defines `emit()`, `subscribe()`, `unsubscribe()` all raising `NotImplementedError`. No event types are defined. The bus is not connected to any component.

- WebSocket handler (`src/scieasy/api/ws.py:8–28`) is a skeleton raising `NotImplementedError`. Only server→client events are mentioned in the architecture document (ARCHITECTURE.md lines 1457–1480). No client→server cancel messages are defined.

- `LineageRecord` (`src/scieasy/core/lineage/record.py:12–35`) records only successful executions: `output_hashes`, `duration_ms`, etc. There is no field for termination reason, partial outputs, or skip reasons.

- `WorkflowCheckpoint` (`src/scieasy/engine/checkpoint.py:12–24`) stores `block_states: dict[str, str]` but was designed for only the original six states.

Users need to:
1. Cancel blocks that run too long (e.g., Cellpose on a large batch).
2. Cancel workflows waiting for external software they no longer need.
3. Have the system respond predictably when an external application crashes or is killed via the OS task manager.
4. See unaffected parallel branches continue executing after a cancellation.
5. Understand why downstream blocks did not execute (clear skip reasons).

### Discussion points and resolution

| # | Topic | Options discussed | Final decision |
|---|---|---|---|
| 1 | Should there be a `TIMED_OUT` state separate from `ERROR`? | (A) Add `TIMED_OUT` for automatic timeout detection. (B) No automatic timeout; only `CANCELLED` (user-initiated) and `ERROR` (crash/failure). | **Decision: (B).** No automatic timeouts. AppBlocks delegate to external software where a 30-minute session is normal. Scientific computations vary wildly in duration. False timeouts interrupt valid work and erode trust. Users cancel manually when they decide something is stuck. |
| 2 | Should downstream blocks enter `ERROR` or a new `SKIPPED` state? | (A) Downstream blocks enter `ERROR`. (B) New `SKIPPED` state with diagnostic reason. | **Decision: (B).** `ERROR` implies something went wrong in that block. `SKIPPED` communicates "this block did not run because its prerequisites were not met." Different semantics → different user response (ERROR → investigate this block; SKIPPED → investigate the upstream block). |
| 3 | Should cancel propagation ask the user about each downstream block? | (A) Prompt user for each downstream block. (B) Deterministic propagation: if required inputs cannot be satisfied, skip automatically. | **Decision: (B).** The propagation is deterministic — if block X produces no output, nothing that needs X's output can run. No decision to make. |
| 4 | Should the scheduler remain a synchronous for-loop? | (A) Keep for-loop, add cancellation check between iterations. (B) Rewrite as event-driven loop. | **Decision: (B).** An event-driven scheduler can react to cancellation, errors, and process death at any time, not just at block boundaries. This also enables true parallel branch execution (the for-loop model is inherently sequential). |
| 5 | Which runtime components need event-driven architecture? | (A) Only DAGScheduler. (B) All runtime components that react to state changes. | **Decision: (B).** The EventBus becomes the backbone of the runtime. DAGScheduler, ResourceManager, ProcessRegistry, WebSocket handler, LineageRecorder, and CheckpointManager all subscribe to events. |
| 6 | What happens when a user cancels an AppBlock while the external app is running? | (A) Ask user to save work first. (B) Kill the process immediately; data loss is the user's responsibility. | **Decision: (B).** Cancellation is immediate. The user clicked cancel. No "save your work?" prompt. External process is killed via `ProcessHandle.terminate()`. |
| 7 | Should the framework detect process crashes (not just cancellation)? | (A) No — only handle user-initiated cancellation. (B) Detect unexpected process exit (crash, OOM-kill, user killing via task manager). | **Decision: (B).** The `ProcessMonitor` (ADR-019) detects unexpected process death. If an AppBlock's external app is killed via the OS task manager, the framework detects it, checks for output files, and transitions to ERROR or DONE accordingly. The runtime never crashes because an external process died. |

### Decision

#### Extended state machine

Two new states added to `BlockState`:

| State | Value | Meaning | Triggered by |
|---|---|---|---|
| `CANCELLED` | `"cancelled"` | User explicitly requested termination of this block | User action via WebSocket `cancel_block` message or REST `POST /api/workflows/{id}/blocks/{block_id}/cancel` |
| `SKIPPED` | `"skipped"` | Block cannot execute because a required upstream block did not produce output | Automatic propagation by DAGScheduler when an upstream block enters `ERROR`, `CANCELLED`, or `SKIPPED` without producing required outputs |

**New state transition table** (replaces `_VALID_TRANSITIONS` in `block.py:13–20`):

```
IDLE      → { READY, SKIPPED, ERROR }
READY     → { RUNNING, SKIPPED, ERROR }
RUNNING   → { DONE, PAUSED, ERROR, CANCELLED }
PAUSED    → { RUNNING, ERROR, CANCELLED }
DONE      → { IDLE }
ERROR     → { IDLE }
CANCELLED → { IDLE }
SKIPPED   → { IDLE }
```

**State diagram:**

```
                          ┌──────────────────────────────────────────────┐
                          │               WORKFLOW RESET                  │
                          │  (only when starting a new run of the same   │
                          │   workflow — all blocks return to IDLE)       │
                          └──┬─────┬─────────┬───────────┬──────────────┘
                             │     │         │           │
                             ▼     ▼         ▼           ▼
          ┌───────────── IDLE ◄── DONE    ERROR ──► IDLE
          │                │                ▲
          │                ▼                │
          │    ┌──── READY ────────────► ERROR
          │    │       │                    ▲
          │    │       ▼                    │
          │    │   RUNNING ──────┬───── ERROR
          │    │       │        │          ▲
          │    │       ▼        │          │
          │    │   PAUSED ──────┤───── ERROR
          │    │       │        │
          │    │       │        ▼
          │    │       │      DONE ──────► IDLE
          │    │       │
          │    │       │    (user cancels)
          │    │       └─────────────► CANCELLED ──► IDLE
          │    │                            ▲
          │    │                            │
          │    │       (user cancels        │
          │    │        while RUNNING) ─────┘
          │    │
          │    │    (upstream failed/cancelled,
          │    │     required inputs unsatisfiable)
          │    └──────────────────────► SKIPPED ────► IDLE
          │                                ▲
          └────────────────────────────────┘
              (upstream failed/cancelled
               before block left IDLE)
```

**Terminal states for a single workflow run**: `DONE`, `ERROR`, `CANCELLED`, `SKIPPED`. All four can transition back to `IDLE` only when the workflow is reset for a new execution.

#### No automatic timeout

The framework does not impose automatic timeouts on block execution. Rationale:

- AppBlocks delegate to external software where the user is actively working. A 30-minute session in ElMAVEN picking LC-MS peaks is normal operation, not a timeout.
- Scientific computations vary wildly in duration. Cellpose on 1000 high-resolution images may legitimately take hours. A training run may take days.
- False timeouts are worse than no timeouts: they interrupt valid work, lose partial results, and erode user trust in the framework.
- The user is the best judge of whether a process is stuck. When they decide it is, they cancel manually.

If per-block user-configurable timeouts are desired in the future, they can be added as an optional `timeout_sec: int | None = None` field on `Block` with `None` meaning "no timeout." The timeout would trigger the same cancellation flow (emit `CANCEL_BLOCK_REQUEST`). This is a future enhancement, not an architectural requirement.

#### Cancellation flow

**Single block cancellation:**

```
1. User clicks "Cancel" on Block X (currently RUNNING or PAUSED)
   │
   ▼
2. Frontend sends WebSocket message:
   {"type": "cancel_block", "block_id": "cellpose_001", "workflow_id": "wf_001"}
   │
   ▼
3. WebSocket handler receives message, emits to EventBus:
   EventBus.emit(EngineEvent(
       event_type=CANCEL_BLOCK_REQUEST,
       block_id="cellpose_001",
       data={"workflow_id": "wf_001"}
   ))
   │
   ├──────────────────────────────────────────────────────────────────┐
   │                                                                  │
   ▼                                                                  ▼
4a. ProcessRegistry receives event:                    4b. DAGScheduler receives event:
    handle = registry.get_handle("cellpose_001")           scheduler.handle_cancel("cellpose_001")
    await handle.terminate(grace_period_sec=5.0)           │
    │                                                      ▼
    │ On Linux/macOS:                                  5. Scheduler marks cellpose_001
    │   SIGTERM to process group                          as CANCELLED:
    │   → wait up to 5s                                    block_states["cellpose_001"] = CANCELLED
    │   → SIGKILL if still alive                           │
    │                                                      ▼
    │ On Windows:                                      6. Scheduler propagates SKIPPED:
    │   TerminateProcess on Job Object                     Identify all downstream blocks whose
    │   (no grace period — immediate)                      required inputs depend on cellpose_001's
    │                                                      outputs (directly or transitively).
    ▼                                                      │
4c. ProcessMonitor detects process exit:                   For each such block:
    emit PROCESS_EXITED event                               block_states[block_id] = SKIPPED
    │                                                       skip_reason[block_id] =
    ▼                                                         "upstream 'cellpose_001' cancelled"
4d. ResourceManager receives                               │
    CANCEL_BLOCK_REQUEST or PROCESS_EXITED:                Continue executing unaffected
    Release resources held by cellpose_001:                 parallel branches.
    gpu_slots += 1                                         │
    memory_budget += 4.0 GB                                ▼
    │                                                  7. Scheduler emits state change events:
    ▼                                                      emit BLOCK_CANCELLED(cellpose_001)
4e. LineageRecorder receives                               emit BLOCK_SKIPPED(napari_review_001,
    BLOCK_CANCELLED event:                                   reason="upstream cancelled")
    Write lineage record:                                  emit BLOCK_SKIPPED(srs_extract_001,
    termination="cancelled"                                  reason="upstream cancelled")
    duration_ms=elapsed since start                        │
    output_hashes=[] (no outputs)                          ▼
    │                                                  8. WebSocket handler receives state events:
    ▼                                                      Push to frontend:
4f. CheckpointManager receives                             {"type": "block_state",
    BLOCK_CANCELLED event:                                  "block_id": "cellpose_001",
    Save checkpoint with updated states.                    "state": "cancelled"}
                                                           {"type": "cancel_propagation",
                                                            "cancelled_block": "cellpose_001",
                                                            "skipped_blocks": [
                                                              {"block_id": "napari_review_001",
                                                               "reason": "upstream cancelled"},
                                                              {"block_id": "srs_extract_001",
                                                               "reason": "upstream cancelled"}
                                                            ],
                                                            "unaffected_blocks": [
                                                              "raman_preprocess_001",
                                                              "load_raman_001"
                                                            ]}
```

**Workflow-level cancellation:**

```
1. User clicks "Cancel Workflow"
   → emit CANCEL_WORKFLOW_REQUEST(workflow_id)
   → For each block in RUNNING or PAUSED state:
       emit CANCEL_BLOCK_REQUEST(block_id)
       (triggers the single-block flow above)
   → For each block in IDLE or READY state:
       block_states[block_id] = SKIPPED
       skip_reason = "workflow cancelled"
```

#### Downstream propagation logic (detailed)

When a block enters a terminal-without-output state (`ERROR` or `CANCELLED`):

```python
def propagate_skipped(self, failed_block_id: str, reason: str) -> list[str]:
    """Mark all unreachable downstream blocks as SKIPPED.

    Returns list of block_ids that were marked SKIPPED.
    """
    skipped = []
    # Get output ports that produced no data
    missing_ports = self._get_empty_output_ports(failed_block_id)

    # Find all downstream blocks connected to those empty ports
    queue = self._get_downstream_blocks(failed_block_id, missing_ports)

    while queue:
        block_id = queue.pop(0)
        if self.block_states[block_id] in (DONE, ERROR, CANCELLED, SKIPPED):
            continue  # already in a terminal state

        # Check: can this block's required inputs still be satisfied?
        unsatisfied = self._get_unsatisfied_required_inputs(block_id)
        if unsatisfied:
            self.block_states[block_id] = SKIPPED
            self.skip_reasons[block_id] = (
                f"Required input(s) {unsatisfied} cannot be satisfied: "
                f"upstream block '{failed_block_id}' {reason}"
            )
            skipped.append(block_id)

            # This block also produces no output → propagate further
            further_missing = self._get_all_output_ports(block_id)
            further_downstream = self._get_downstream_blocks(block_id, further_missing)
            queue.extend(further_downstream)

    return skipped
```

**Critical rule**: the propagation logic is identical for `ERROR` and `CANCELLED`. The scheduler does not distinguish between them — it only checks: "does this block have all required inputs satisfied?" This means:

- A crashed AppBlock (ERROR) and a user-cancelled AppBlock (CANCELLED) trigger the same downstream behaviour.
- Optional inputs do not trigger SKIPPED. If a block has one required and one optional input, and only the optional input's upstream fails, the block is still schedulable.

#### AppBlock-specific scenarios

| Scenario | Detection | Framework response |
|---|---|---|
| External app running normally, user working | `ProcessHandle.is_alive()` = True, no output files yet | Do nothing. Wait. |
| External app finishes, writes output files | `ProcessHandle.is_alive()` = False (exit code 0), FileWatcher detects files | → `DONE`. Collect output files. Continue workflow. |
| External app finishes, does NOT write output files | `ProcessHandle.is_alive()` = False (exit code 0), FileWatcher detects no matching files | → `ERROR` with message "External process exited normally (code 0) but did not produce expected output files matching patterns {patterns}". Propagate `SKIPPED` downstream. |
| External app crashes (segfault, unhandled exception) | `ProcessHandle.is_alive()` = False (exit code ≠ 0), no output files | → `ERROR` with message "External process exited with code {code}". Propagate `SKIPPED` downstream. |
| User kills external app via OS task manager | `ProcessMonitor` detects PID gone. `ProcessHandle.is_alive()` = False. | Same as crash: → `ERROR` with message "External process terminated unexpectedly (exit code {code})". Propagate `SKIPPED` downstream. |
| User cancels AppBlock via SciEasy UI | `CANCEL_BLOCK_REQUEST` → `ProcessHandle.terminate()` kills external app | → `CANCELLED`. External process killed immediately. No "save your work?" prompt. Propagate `SKIPPED` downstream. |
| External app crashes AFTER writing output files | `ProcessHandle.is_alive()` = False (exit code ≠ 0), but FileWatcher detected files | → `DONE`. Output files exist and are valid. The crash was after the useful work completed. (Edge case: partially written files. The block author's `collect()` method should validate file integrity.) |

#### Event-driven runtime architecture

The `EventBus` becomes the backbone of the runtime. All runtime components communicate through events rather than direct method calls. This decouples components and enables the system to react to cancellation, errors, and process death at any point during execution.

**Complete event type catalogue:**

| Event type constant | Emitted by | Payload (`data` dict fields) | Description |
|---|---|---|---|
| `BLOCK_READY` | `DAGScheduler` | `block_id: str` | Block's required inputs are all satisfied; ready to execute. |
| `BLOCK_RUNNING` | `DAGScheduler` | `block_id: str`, `run_id: str` | Block dispatched to runner, subprocess started. |
| `BLOCK_PAUSED` | `DAGScheduler` | `block_id: str`, `reason: str` | Block entered PAUSED state (waiting for external app or user interaction). |
| `BLOCK_DONE` | `DAGScheduler` | `block_id: str`, `output_refs: dict[str, str]`, `duration_ms: int` | Block completed successfully with output references. |
| `BLOCK_ERROR` | `DAGScheduler` | `block_id: str`, `error_detail: str`, `exit_code: int | None` | Block failed with error. |
| `BLOCK_CANCELLED` | `DAGScheduler` | `block_id: str` | Block was cancelled by user. |
| `BLOCK_SKIPPED` | `DAGScheduler` | `block_id: str`, `skip_reason: str`, `caused_by: str` | Block skipped because upstream did not produce required output. `caused_by` = block_id of the root cause. |
| `CANCEL_BLOCK_REQUEST` | WebSocket handler, REST endpoint | `block_id: str`, `workflow_id: str` | User requests cancellation of a specific block. |
| `CANCEL_WORKFLOW_REQUEST` | WebSocket handler, REST endpoint | `workflow_id: str` | User requests cancellation of the entire workflow. |
| `PROCESS_SPAWNED` | `spawn_block_process()` | `block_id: str`, `pid: int`, `resource_request: ResourceRequest` | A subprocess was created for a block. |
| `PROCESS_EXITED` | `ProcessMonitor` | `block_id: str`, `exit_info: ProcessExitInfo` | A subprocess exited (normally, crashed, or killed). |
| `WORKFLOW_STARTED` | `DAGScheduler` | `workflow_id: str` | Workflow execution began. |
| `WORKFLOW_COMPLETED` | `DAGScheduler` | `workflow_id: str`, `final_states: dict[str, str]` | All blocks reached terminal states (DONE/ERROR/CANCELLED/SKIPPED). |
| `CHECKPOINT_SAVED` | `CheckpointManager` | `workflow_id: str`, `checkpoint_path: str` | A checkpoint was persisted to disk. |

**Subscription matrix — who listens to what:**

| Subscriber | `BLOCK_DONE` | `BLOCK_ERROR` | `BLOCK_CANCELLED` | `BLOCK_SKIPPED` | `CANCEL_BLOCK_REQUEST` | `CANCEL_WORKFLOW_REQUEST` | `PROCESS_SPAWNED` | `PROCESS_EXITED` |
|---|---|---|---|---|---|---|---|---|
| **DAGScheduler** | ✓ schedule next | ✓ propagate SKIPPED | ✓ propagate SKIPPED | — | ✓ initiate cancel | ✓ cancel all | — | ✓ update block state |
| **ResourceManager** | ✓ release | ✓ release | ✓ release | — | — | — | ✓ record allocation | ✓ release |
| **ProcessRegistry** | — | — | — | — | ✓ terminate process | ✓ terminate all | ✓ register handle | ✓ deregister handle |
| **WebSocket handler** | ✓ push to client | ✓ push to client | ✓ push to client | ✓ push to client | — | — | — | — |
| **LineageRecorder** | ✓ write record | ✓ write record | ✓ write record | ✓ write record | — | — | — | — |
| **CheckpointManager** | ✓ save | ✓ save | ✓ save | ✓ save | — | — | — | — |

### Alternatives considered

- **`TIMED_OUT` as a separate state**: adds a state that cannot be reliably distinguished from "my computation is just slow." Since we decided against automatic timeouts, the state has no trigger. If user-configurable timeouts are added later, the timeout action is semantically identical to a cancel — using `CANCELLED` with a reason field (`"cancelled: user-configured timeout exceeded"`) is sufficient. No separate state needed.

- **Downstream blocks enter `ERROR` instead of `SKIPPED`**: `ERROR` implies something went wrong inside that block. `SKIPPED` accurately communicates "this block did not run because its prerequisites were not met." Different semantics lead to different user actions: ERROR → look at this block's logs; SKIPPED → look at the upstream block that caused it.

- **Cancel propagation stops the entire workflow**: too aggressive. A multi-branch workflow (LC-MS + Raman + IF) should not lose the Raman and IF results because the user cancelled one LC-MS block. Only the dependent subgraph is affected.

- **Keep the synchronous for-loop scheduler, add cancellation checks between iterations**: a for-loop model cannot react to events during block execution — it only checks between blocks. If a Cellpose block runs for 2 hours, the cancel request sits in a queue for 2 hours. Event-driven scheduling reacts immediately.

- **Direct method calls between components instead of EventBus**: tight coupling. Adding a new subscriber (e.g., a metrics collector) requires modifying the scheduler. EventBus allows adding subscribers without changing emitters. Also enables testing components in isolation by mocking the bus.

### Consequences

- `BlockState` grows from 6 to 8 states. All state-dependent code must handle `CANCELLED` and `SKIPPED`.
- The DAGScheduler changes from a synchronous for-loop to an event-driven loop. This is a fundamental rewrite of the scheduler.
- Every block is cancellable at any time because of subprocess isolation (ADR-017). No cooperative cancellation protocol needed.
- `SKIPPED` propagation is deterministic and auditable — the reason chain traces back to the original `CANCELLED` or `ERROR` block.
- The EventBus becomes a critical runtime component. A bug in the EventBus can affect all subscribers. It must be well-tested and have clear error handling (a failing subscriber should not block event delivery to other subscribers).
- The runtime never crashes because an upstream block failed. Missing inputs are a normal condition that triggers `SKIPPED`, not an exception.

### Detailed impact scope

#### New files

| File | Contents | Key classes/functions |
|---|---|---|
| (None — all changes are modifications to existing files or new files already listed in ADR-017 and ADR-019) | | |

#### Rewritten files

| File | Current state | New state | Detailed changes |
|---|---|---|---|
| `src/scieasy/engine/scheduler.py` | Skeleton class (54 lines). `__init__()`, `execute()`, `pause()`, `resume()`, `set_state()`, `save_checkpoint()` all raise `NotImplementedError`. No `cancel_block()` or `cancel_workflow()` methods. | Fully event-driven scheduler. | **Rewrite entirely.** `__init__(self, workflow: WorkflowDefinition, event_bus: EventBus, runner: BlockRunner, resource_manager: ResourceManager) -> None`: store workflow graph, build internal DAG (via `build_dag()`), initialise `block_states: dict[str, BlockState]` (all IDLE), `skip_reasons: dict[str, str]` (empty), subscribe to events on `event_bus`. Subscriptions: `PROCESS_EXITED` → `self._on_process_exited`, `CANCEL_BLOCK_REQUEST` → `self._on_cancel_block`, `CANCEL_WORKFLOW_REQUEST` → `self._on_cancel_workflow`. `async execute(self) -> None`: emit `WORKFLOW_STARTED`. Scan for blocks whose required inputs are all satisfied → transition to READY → dispatch via `runner.run()` → transition to RUNNING. Enter event loop: await events from EventBus. On `BLOCK_DONE`: store output refs, scan for newly-ready blocks, dispatch them. On `BLOCK_ERROR`/`BLOCK_CANCELLED`: call `propagate_skipped()`, check if workflow is complete. On `WORKFLOW_COMPLETED`: break loop. `async _on_cancel_block(self, event: EngineEvent) -> None`: validate block is in RUNNING or PAUSED state. Call `runner.cancel(run_id)`. Transition block to CANCELLED. Call `propagate_skipped(block_id, "cancelled")`. Emit `BLOCK_CANCELLED`. `async _on_cancel_workflow(self, event: EngineEvent) -> None`: for each RUNNING/PAUSED block: emit `CANCEL_BLOCK_REQUEST`. For each IDLE/READY block: transition to SKIPPED, emit `BLOCK_SKIPPED`. `def propagate_skipped(self, failed_block_id: str, reason: str) -> list[str]`: implementation as described in "Downstream propagation logic" section above. **Add** `cancel_block(block_id)` and `cancel_workflow()` public methods (emit events). **Remove** `pause()` and `resume()` — these are not removed from the API but internally they now emit events rather than directly manipulating state. |
| `src/scieasy/engine/events.py` | `EngineEvent` dataclass (lines 12–22) with `event_type: str`, `block_id: str | None`, `data: dict`, `timestamp: datetime`. `EventBus` class (lines 25–62) with `emit()`, `subscribe()`, `unsubscribe()` all raising `NotImplementedError`. | Fully implemented EventBus with event type constants and async support. | **Add** event type constants at module level (13 constants as listed in the event catalogue above): `BLOCK_READY = "block_ready"`, `BLOCK_RUNNING = "block_running"`, `BLOCK_PAUSED = "block_paused"`, `BLOCK_DONE = "block_done"`, `BLOCK_ERROR = "block_error"`, `BLOCK_CANCELLED = "block_cancelled"`, `BLOCK_SKIPPED = "block_skipped"`, `CANCEL_BLOCK_REQUEST = "cancel_block_request"`, `CANCEL_WORKFLOW_REQUEST = "cancel_workflow_request"`, `PROCESS_SPAWNED = "process_spawned"`, `PROCESS_EXITED = "process_exited"`, `WORKFLOW_STARTED = "workflow_started"`, `WORKFLOW_COMPLETED = "workflow_completed"`, `CHECKPOINT_SAVED = "checkpoint_saved"`. **Implement** `EventBus`: `__init__()`: `self._subscribers: dict[str, list[Callable]] = defaultdict(list)`. `emit(event)`: iterate `self._subscribers[event.event_type]`, call each callback with the event. If a callback raises, log the error and continue (one failing subscriber must not block others). If callback is a coroutine, schedule it with `asyncio.create_task()`. `subscribe(event_type, callback)`: append callback to `self._subscribers[event_type]`. `unsubscribe(event_type, callback)`: remove callback from list. **Change** `EngineEvent.data` type annotation from `dict[str, Any]` to remain as-is (generic dict is intentional for flexibility), but **add** docstring specifying the expected payload fields per event type (referencing the event catalogue). |

#### Modified files

| File | Current state | Changes | Detailed field/parameter changes |
|---|---|---|---|
| `src/scieasy/blocks/base/state.py` | `BlockState` enum (lines 8–16): 6 values: `IDLE`, `READY`, `RUNNING`, `PAUSED`, `DONE`, `ERROR`. | **Add** two new enum values. | **Add** after `ERROR = "error"` (line 16): `CANCELLED = "cancelled"` and `SKIPPED = "skipped"`. Final enum has 8 values. No other changes to this file (other enums `ExecutionMode`, `BatchMode`, `InputDelivery`, `BatchErrorStrategy` are unchanged). |
| `src/scieasy/blocks/base/block.py` | `_VALID_TRANSITIONS` (lines 13–20): 6 entries. | **Replace** the entire dict with the new 8-entry transition table. | **Replace** lines 13–20 with: `_VALID_TRANSITIONS: dict[BlockState, set[BlockState]] = { BlockState.IDLE: {BlockState.READY, BlockState.SKIPPED, BlockState.ERROR}, BlockState.READY: {BlockState.RUNNING, BlockState.SKIPPED, BlockState.ERROR}, BlockState.RUNNING: {BlockState.DONE, BlockState.PAUSED, BlockState.ERROR, BlockState.CANCELLED}, BlockState.PAUSED: {BlockState.RUNNING, BlockState.ERROR, BlockState.CANCELLED}, BlockState.DONE: {BlockState.IDLE}, BlockState.ERROR: {BlockState.IDLE}, BlockState.CANCELLED: {BlockState.IDLE}, BlockState.SKIPPED: {BlockState.IDLE}, }`. **Add** import of `CANCELLED` and `SKIPPED` in the `from .state import ...` line if they are used directly (currently the import on line 10 imports the `BlockState` class, which is sufficient). |
| `src/scieasy/core/lineage/record.py` | `LineageRecord` dataclass (lines 12–35): 9 fields. No termination or skip fields. | **Add** 3 new fields for termination tracking. | **Add** after `batch_info` (line 35): `termination: str = "completed"` (allowed values: `"completed"`, `"cancelled"`, `"error"`, `"skipped"`), `partial_output_refs: list[str] | None = None` (storage references for any partial outputs produced before cancellation/error), `termination_detail: str | None = None` (human-readable detail: error message, skip reason, or cancellation source). |
| `src/scieasy/core/lineage/store.py` | `_CREATE_TABLE` SQL (lines 13–26): 9 columns. `write()` method (lines 53–82): inserts 9 values. `_row_to_record()` (lines 84–100): reads 9 columns. | **Add** 3 new columns to the schema. **Update** `write()`, `_row_to_record()`, and `query()`. | **Change** `_CREATE_TABLE` (lines 13–26): add 3 columns after `batch_info TEXT`: `termination TEXT NOT NULL DEFAULT 'completed'`, `partial_output_refs TEXT`, `termination_detail TEXT`. **Add** new index: `CREATE INDEX IF NOT EXISTS idx_lineage_termination ON lineage (termination);` (for filtering by termination type). **Change** `write()` (line 67): add `termination`, `partial_output_refs`, `termination_detail` to INSERT statement and values tuple. **Change** `_row_to_record()`: add parsing of 3 new columns from row tuple (indices 9, 10, 11). **Add** to `query()`: optional `termination: str | None = None` filter parameter. When provided, add `WHERE termination = ?` clause. |
| `src/scieasy/engine/checkpoint.py` | `WorkflowCheckpoint` dataclass (lines 12–24): 5 fields including `block_states: dict[str, str]`. | **Add** `skip_reasons` field. **Update** block_states documentation to include CANCELLED and SKIPPED as valid values. | **Add** after `config_snapshot` (line 24): `skip_reasons: dict[str, str] = field(default_factory=dict)` (mapping of block_id to skip reason string for all SKIPPED blocks). The `block_states` field already uses `str` values, so CANCELLED and SKIPPED are automatically valid. **Update** docstring to list all 8 valid state values. |
| `src/scieasy/engine/resources.py` | `ResourceManager` class (lines 27–72): `__init__()`, `acquire()`, `release()`, `available` property — all `raise NotImplementedError`. No EventBus integration. | **Add** EventBus subscription for automatic resource release. | **Change** `__init__()` signature: add `event_bus: EventBus | None = None` parameter. If provided, subscribe to `BLOCK_DONE`, `BLOCK_ERROR`, `BLOCK_CANCELLED`, `PROCESS_EXITED` events with `self._on_block_terminal` callback. **Add** method `_on_block_terminal(self, event: EngineEvent) -> None`: look up resource allocation for `event.block_id`, call `self.release(allocation)`. **Add** internal tracking: `self._allocations: dict[str, ResourceRequest] = {}` mapping block_id to its allocated resources. `acquire()` stores the allocation; `release()` removes it. |
| `src/scieasy/engine/batch.py` | `BatchExecutor` class (lines 8–99): `execute_serial()`, `execute_parallel()`, `execute_adaptive()` all `raise NotImplementedError`. | **Add** cancellation awareness to batch execution. | **Add** parameter to all three `execute_*` methods: `cancel_event: asyncio.Event | None = None`. When set, the executor checks `cancel_event.is_set()` before dispatching each item. If set, remaining items are not dispatched; results for unstarted items are marked as SKIPPED in the `BatchResult`. **Add** to returned `BatchResult` (needs new dataclass or dict): `skipped: list[int]` for item indices that were skipped due to cancellation. |
| `src/scieasy/api/ws.py` | Single function `websocket_handler()` (lines 8–28) raising `NotImplementedError`. | **Implement** WebSocket handler with bidirectional event routing. | **Rewrite** `websocket_handler(websocket, event_bus)`: `await websocket.accept()`. Start two concurrent tasks: (1) **Inbound loop**: `async for message in websocket: data = json.loads(message); if data["type"] == "cancel_block": event_bus.emit(EngineEvent(event_type=CANCEL_BLOCK_REQUEST, block_id=data["block_id"], data={"workflow_id": data["workflow_id"]})); elif data["type"] == "cancel_workflow": event_bus.emit(EngineEvent(event_type=CANCEL_WORKFLOW_REQUEST, data={"workflow_id": data["workflow_id"]}))`. (2) **Outbound loop**: subscribe to `BLOCK_READY`, `BLOCK_RUNNING`, `BLOCK_PAUSED`, `BLOCK_DONE`, `BLOCK_ERROR`, `BLOCK_CANCELLED`, `BLOCK_SKIPPED`, `WORKFLOW_COMPLETED` events. On each event, `await websocket.send_json(serialise_event(event))`. **Add** helper `serialise_event(event: EngineEvent) -> dict` that converts event to the WebSocket JSON protocol format. **Add** `cancel_propagation` message type: when `BLOCK_CANCELLED` is followed by one or more `BLOCK_SKIPPED` events, aggregate them into a single `cancel_propagation` message listing all skipped blocks and unaffected blocks. |
| `src/scieasy/api/schemas.py` | 10 Pydantic models for workflow, block, data, AI, and error responses (lines 1–119). No cancel-related schemas. | **Add** cancel-related request/response schemas. | **Add** after the Workflow section (after line 31): `class CancelBlockRequest(BaseModel): block_id: str; workflow_id: str`. `class CancelWorkflowRequest(BaseModel): workflow_id: str`. `class CancelBlockResponse(BaseModel): block_id: str; state: str; skipped_blocks: list[dict[str, str]] = []` (each dict has `block_id` and `reason`). `class CancelWorkflowResponse(BaseModel): workflow_id: str; cancelled_blocks: list[str] = []; skipped_blocks: list[str] = []`. |
| `src/scieasy/api/routes/workflows.py` | 7 endpoints (lines 1–96): create, get, update, delete, execute, pause, resume. No cancel endpoints. | **Add** 2 cancel endpoints. | **Add** after `resume_workflow()` (line 96): `@router.post("/{workflow_id}/cancel", response_model=CancelWorkflowResponse) async def cancel_workflow(workflow_id: str) -> dict[str, Any]:` — emits `CANCEL_WORKFLOW_REQUEST` to EventBus. `@router.post("/{workflow_id}/blocks/{block_id}/cancel", response_model=CancelBlockResponse) async def cancel_block(workflow_id: str, block_id: str) -> dict[str, Any]:` — emits `CANCEL_BLOCK_REQUEST` to EventBus. **Add** import: `from scieasy.api.schemas import CancelBlockRequest, CancelBlockResponse, CancelWorkflowRequest, CancelWorkflowResponse`. |

#### Documentation impact

| Document | Current state | Required changes |
|---|---|---|
| `docs/architecture/ARCHITECTURE.md` Section 5.1 (Block base class, lines 362–414) | Shows `BlockState` with 6 values (lines 367–373). Shows `_VALID_TRANSITIONS` equivalent in prose. | **Update** `BlockState` enum to show 8 values. **Add** the new state diagram. **Add** description of `CANCELLED` and `SKIPPED` semantics. |
| `docs/architecture/ARCHITECTURE.md` Section 6.1 (DAG scheduler, lines 1024–1056) | Shows synchronous for-loop scheduler. | **Rewrite** to describe event-driven scheduler. **Add** description of cancellation flow and SKIPPED propagation. **Add** the EventBus subscription matrix. |
| `docs/architecture/ARCHITECTURE.md` Section 6.3 (Pause, resume, checkpointing, lines 1105–1126) | `WorkflowCheckpoint` dataclass with 5 fields. | **Add** `skip_reasons` field. **Update** description to explain that CANCELLED and SKIPPED blocks are included in checkpoints. |
| `docs/architecture/ARCHITECTURE.md` Section 6.5 (Batch error handling, lines 1174–1192) | `BatchErrorStrategy` and `BatchResult`. | **Add** cancellation-aware batch execution description. **Add** `skipped` field to `BatchResult`. |
| `docs/architecture/ARCHITECTURE.md` Section 8.2 (REST endpoints, lines 1429–1453) | 10 endpoints listed. No cancel endpoints. | **Add** `POST /api/workflows/{id}/cancel` and `POST /api/workflows/{id}/blocks/{block_id}/cancel`. |
| `docs/architecture/ARCHITECTURE.md` Section 8.3 (WebSocket protocol, lines 1455–1480) | Only server→client messages shown. | **Add** client→server messages: `cancel_block`, `cancel_workflow`. **Add** server→client message: `cancel_propagation`. |
| `docs/architecture/ARCHITECTURE.md` Section 4.4 (Data lineage, lines 275–290) | `LineageRecord` with 9 fields. | **Add** `termination`, `partial_output_refs`, `termination_detail` fields. |
| `docs/architecture/ARCHITECTURE.md` Appendix A (Concrete example walkthrough, lines 1729–1783) | Describes only the happy-path execution flow. | **Add** a cancellation scenario variant: "What happens if the user cancels Cellpose during step 4?" showing CANCELLED → napari SKIPPED → SRS extract SKIPPED → Raman branch continues. |
| `CHANGELOG.md` | Current entries. | **Add** entry under `[Unreleased]` for ADR-018: block cancellation and event-driven runtime. |

---

## ADR-018 Addendum 1: Scheduler concurrency implementation

**Status**: proposed
**Date**: 2026-04-06

### Purpose

ADR-018 committed to an event-driven DAGScheduler that reacts to events as they arrive and dispatches independent branches of the workflow concurrently. ARCHITECTURE.md §6.1 and Appendix A both describe this behaviour — for example, the multimodal walkthrough states that "Three IOBlocks load data in parallel (independent branches). Each runs in its own subprocess (ADR-017)".

The implementation in `src/scieasy/engine/scheduler.py` as of 2026-04-06 does **not** match that contract. Independent branches execute strictly in topological order, serialised on `popen.communicate()` inside the scheduler coroutine. This addendum documents the discrepancy, specifies the required implementation change, and captures the decisions made during Phase 10 planning about how concurrency, cancellation, and resource throttling must interact.

This addendum does **not** revise any of ADR-018's user-visible decisions (state machine, cancel propagation, event catalogue, subscription matrix). Those remain authoritative. The addendum only narrows the implementation strategy.

### Context

ADR-018 §5 ("Event-driven runtime architecture") and the subscription matrix assume that the scheduler is a true event loop: `DAGScheduler.execute()` kicks off the initial set of READY blocks and then awaits events, and each `BLOCK_DONE` event fires an `_on_block_done` handler that dispatches newly-ready successors. The expected behaviour is that when two blocks with no data dependency between them are simultaneously READY, they both start immediately — each on its own subprocess — and the scheduler returns to the event loop to await whichever finishes first.

Source code audit (grep of `asyncio.(create_task|gather|ensure_future)` across `src/scieasy/engine/scheduler.py`) returns **zero matches**. Every dispatch is performed as a direct `await self._dispatch(node_id)`, and `_dispatch` itself performs `await self._runner.run(block, inputs, node.config)` inline, which in turn awaits `popen.communicate()` on the worker subprocess. The call chain is synchronous with respect to the event loop — no other coroutine runs until the current block's subprocess exits.

**Concrete observations** (referenced lines may shift as the file is edited):

- `scheduler.py` line 122–125 (in `execute()`): `for node_id in self._order: if self._block_states[node_id] == BlockState.IDLE and self._check_readiness(node_id): self._block_states[node_id] = BlockState.READY; await self._dispatch(node_id)`.
- `scheduler.py` line 155 (in `_dispatch()`): `result = await self._runner.run(block, inputs, node.config)` — direct inline await.
- `scheduler.py` line 218–223 (in `_on_block_done()`): scans for newly-ready nodes and calls `await self._dispatch(next_id)` — same inline pattern.
- `scheduler.py` line 409–412, 481, 584 (in `resume()`, `reset_block()`, `execute_from()`): all use `await self._dispatch(node_id)` inline.
- `runners/local.py` line 93: `stdout, stderr = await asyncio.to_thread(popen.communicate, stdin_payload)` — this bit is correct (the blocking call is off-loaded to a thread), but because every scheduler dispatch awaits it inline, the event loop still blocks progressing to the next dispatch until the subprocess finishes.

**User-visible consequence**: A workflow like the one in ARCH Appendix A with three independent IOBlock roots (load LC-MS, load Raman, load IF) executes as `load_lcms → (completes) → load_raman → (completes) → load_if → …`. A workflow that fans out a Collection via `SplitCollection` into four parallel `CellposeSegment` branches executes the Cellpose blocks serially, one after another, regardless of GPU availability.

**Phase 10 impact**: every parallelism story in Phase 10 depends on fixing this. Specifically:

- DAG branch parallelism (L1 in the Phase 10 discussion) is directly broken.
- Collection fan-out via `SplitCollection` → N parallel branches → `MergeCollection` (L2 in the Phase 10 discussion) is indirectly broken because it relies on branch parallelism.
- Any future multi-GPU imaging workflow is blocked.
- ResourceManager GPU slot gating becomes meaningless under serialised execution — a `gpu_slots=4` configuration behaves identically to `gpu_slots=1` because the scheduler never tries to dispatch a second GPU block concurrently.

### Discussion points and resolution

| # | Topic | Options discussed | Final decision |
|---|---|---|---|
| 1 | Where should the subprocess `await` happen so that independent branches run concurrently? | (A) Inline in `_dispatch`, as today. (B) In an `asyncio.Task` created by `_dispatch`, tracked separately. (C) Collected in a list and passed to `asyncio.gather` in `execute()`. | **Decision: (B).** `_dispatch` performs the synchronous state transition and input gathering, then wraps the long-running `runner.run(...)` call in `asyncio.create_task`. The task is stored in `self._active_tasks[block_id]` and runs independently. (A) is the current broken behaviour. (C) does not compose with event-driven re-dispatch triggered by `_on_block_done` — `gather` works for the initial root set but becomes awkward as new generations of READY blocks emerge. |
| 2 | How does `execute()` know when the workflow is done? | (A) Track a completion event set by `_check_completion` when all blocks are terminal (current approach). (B) Return from `execute()` only when `self._active_tasks` is empty AND all blocks are terminal. | **Decision: (A) + (B).** Keep the existing `self._completed_event` asyncio.Event pattern. Update `_check_completion` to require `all(state in terminal for state in block_states.values())` (unchanged) AND `not self._active_tasks` (new). This ensures `execute()` does not return before all running subprocesses have finalised. |
| 3 | How does cancellation propagate through the new task model? | (A) Use `task.cancel()` exclusively. (B) Use `ProcessHandle.terminate()` exclusively. (C) Use `ProcessHandle.terminate()` as the primary path and `task.cancel()` only for blocks still in pre-subprocess setup. | **Decision: (C).** The authoritative cancellation path stays as per ADR-019 — `ProcessHandle.terminate()` sends SIGTERM (+grace+SIGKILL on POSIX) or `TerminateJobObject` (Windows) to the worker subprocess. The task naturally unwinds when the subprocess exits, reads exit code, and transitions to CANCELLED. `task.cancel()` is only required for the small window between `_dispatch` entering and `spawn_block_process` returning — if cancellation is requested while the block is still in that setup phase, there is no `ProcessHandle` to terminate yet, so `task.cancel()` injects a `CancelledError` to abort setup. |
| 4 | Do we need locks around state mutation? | (A) Introduce an `asyncio.Lock` per block or a single scheduler lock. (B) Rely on cooperative scheduling (asyncio coroutines do not preempt). | **Decision: (B).** asyncio is single-threaded; a coroutine only yields at `await` points. As long as state mutations happen between awaits (rather than across them), no lock is needed. The existing `_reset_lock` for `reset_block()` is kept because that path can be triggered from an external caller and has multi-step state updates. |
| 5 | How are blocks throttled when `ResourceManager.can_dispatch()` returns False? | (A) Block inside `_dispatch` until resources free up. (B) Leave the block in READY state and retry dispatch when a resource event fires. | **Decision: (B).** Blocking inside `_dispatch` would reintroduce the serialisation bug under a different guise. Instead, `_dispatch` checks `can_dispatch` and, if refused, resets the block to READY and returns immediately. A new helper `_dispatch_newly_ready()` is called from `_on_block_done`, `_on_process_exited`, and the `ResourceManager`'s release callback; it re-scans for READY blocks and retries dispatch. |
| 6 | Should each `RunHandle.result` `asyncio.Future` be the source of truth for "block finished"? | (A) Yes — subscribe to the future's done callback and emit BLOCK_DONE from there. (B) No — keep the "await runner.run then emit" pattern, just move it into a task. | **Decision: (B).** Minimises the change surface. `RunHandle.result` remains an `asyncio.Future` (per `scheduler.py:40`) but is implemented as the result of `runner.run()` awaited inside `_run_and_finalize`. The exception-handling structure stays nearly identical to the current `_dispatch`, only moved one level in. |
| 7 | What happens if `execute()` raises mid-workflow (bug in a callback, cancelled externally)? | (A) Leak active tasks. (B) Cancel all active tasks in a `finally` block. | **Decision: (B).** `execute()` wraps its main body in `try: await self._completed_event.wait(); finally: await self._cancel_active_tasks_on_shutdown()`. The shutdown helper iterates `self._active_tasks`, terminates each subprocess via `ProcessHandle.terminate()`, and awaits task completion. This prevents zombie subprocesses after an engine-level exception. |
| 8 | Do existing tests still pass under the new implementation? | (A) Yes, because tests only check eventual state. (B) No, because some tests assume strict sequential ordering. | **Decision: (B).** Tests that assert "block A's BLOCK_DONE event arrives before block B's BLOCK_RUNNING event" when A and B are in independent branches will fail — that ordering was an artefact of the bug, not a guarantee. Acceptance criterion for this fix: all existing scheduler tests either pass unchanged, or are updated with a written rationale that the old assertion relied on the serialisation bug. |

### Decision

`DAGScheduler._dispatch` is split into two methods:

1. **`async def _dispatch(self, node_id: str) -> None`** — synchronous prelude performed on the scheduler coroutine: check `_paused`, check `_resource_manager.can_dispatch()` (re-queue if False), transition to RUNNING, emit BLOCK_RUNNING event, record lineage start, gather inputs, instantiate the block, wrap `_run_and_finalize(node_id, block, inputs, node)` in `asyncio.create_task`, store the task in `self._active_tasks[node_id]`, and return. The method no longer awaits the runner.

2. **`async def _run_and_finalize(self, node_id, block, inputs, node) -> None`** — the long-running body, executed as an independent task: await `self._runner.run(block, inputs, node.config)`, store output refs in `self._block_outputs[node_id]`, transition to DONE, emit BLOCK_DONE event, save checkpoint. Exception handling mirrors the current `try/except` in `_dispatch`, including the "post-cancellation clean exit" early return. On finally, pop `node_id` from `self._active_tasks`.

**New scheduler field**: `self._active_tasks: dict[str, asyncio.Task[None]] = {}` — keyed by `block_id`, tracks currently running block tasks.

**`_on_cancel_block(event)`** — updated cancellation path:
1. Look up `self._process_registry.get_handle(block_id)`.
2. If a handle exists: call `handle.terminate(grace_period_sec=block.terminate_grace_sec)`. Set `_block_states[block_id] = CANCELLED` and emit `BLOCK_CANCELLED`. The `_run_and_finalize` task will unwind naturally when the subprocess exits (it catches the exception raised by `runner.run()`, sees the current state is already CANCELLED, and early-returns).
3. If no handle exists (block is still in pre-subprocess setup): call `self._active_tasks[block_id].cancel()`. The `_run_and_finalize` task raises `CancelledError`, the scheduler transitions the block to CANCELLED, and emits `BLOCK_CANCELLED`.
4. Call `_propagate_skip(block_id, "cancelled")`.
5. Call `_check_completion()`.

**`_on_cancel_workflow(event)`** — iterates all running blocks and applies `_on_cancel_block` logic to each, then marks any still-IDLE/READY blocks as SKIPPED with reason "workflow cancelled".

**`_on_block_done(event)`** and **`_on_process_exited(event)`** — after their existing logic, call a new helper `_dispatch_newly_ready()`:

```python
async def _dispatch_newly_ready(self) -> None:
    """Scan for READY blocks that were previously blocked by can_dispatch
    and retry their dispatch. Also scan for IDLE blocks whose predecessors
    are now all DONE."""
    for node_id in self._order:
        state = self._block_states[node_id]
        if state == BlockState.IDLE and self._check_readiness(node_id):
            self._block_states[node_id] = BlockState.READY
            await self._dispatch(node_id)
        elif state == BlockState.READY and node_id not in self._active_tasks:
            # Previously blocked by can_dispatch; retry.
            await self._dispatch(node_id)
```

Note that `_dispatch` is itself idempotent now: if `can_dispatch()` returns False again, the block stays in READY and the method returns without creating a task.

**`_check_completion()`** — updated:

```python
def _check_completion(self) -> None:
    terminal = {BlockState.DONE, BlockState.ERROR, BlockState.CANCELLED, BlockState.SKIPPED}
    if all(s in terminal for s in self._block_states.values()) and not self._active_tasks:
        self._completed_event.set()
```

**`execute()`** — updated:

```python
async def execute(self) -> None:
    await self._event_bus.emit(EngineEvent(event_type=WORKFLOW_STARTED, ...))
    if not self._dag.nodes:
        self._completed_event.set()
        await self._event_bus.emit(EngineEvent(event_type=WORKFLOW_COMPLETED, ...))
        return
    try:
        # Initial dispatch of root-ready blocks. Note: no inline await on runner.
        for node_id in self._order:
            if self._block_states[node_id] == BlockState.IDLE and self._check_readiness(node_id):
                self._block_states[node_id] = BlockState.READY
                await self._dispatch(node_id)
        # Wait for event-driven completion. Event handlers dispatch successors
        # via _dispatch_newly_ready() called from _on_block_done / _on_process_exited.
        await self._completed_event.wait()
    finally:
        await self._cancel_active_tasks_on_shutdown()
    await self._event_bus.emit(EngineEvent(event_type=WORKFLOW_COMPLETED, ...))

async def _cancel_active_tasks_on_shutdown(self) -> None:
    """Best-effort cleanup of any tasks still running when execute() exits.
    Terminates subprocesses via ProcessRegistry, then awaits task completion.
    Swallows exceptions — this runs in a finally block."""
    for block_id, task in list(self._active_tasks.items()):
        handle = self._process_registry.get_handle(block_id) if self._process_registry else None
        if handle is not None:
            try:
                handle.terminate()
            except Exception:
                logger.exception("Error terminating process for block %s during shutdown", block_id)
        if not task.done():
            task.cancel()
            try:
                await task
            except BaseException:
                pass
```

### Alternatives considered

- **Keep inline `await` and use `multiprocessing.Pool` at scheduler level**: duplicates the ProcessHandle / ProcessRegistry infrastructure built in ADR-019, loses ProcessMonitor's crash detection for those children, and fragments the process management story. Rejected.
- **Use `asyncio.gather(*[self._dispatch(n) for n in ready_roots])` in `execute()`**: correct for the initial root dispatch but does not extend to `_on_block_done` which needs to dispatch newly-ready blocks on the fly. A mix of gather (for roots) and create_task (for successors) would be inconsistent. Rejected in favour of pure create_task.
- **Switch to `threading.Thread` per block instead of `asyncio.Task`**: threads in Python are GIL-bound for CPU work and provide no isolation advantage over the subprocess-per-block model we already have (ADR-017). They also complicate cancellation — see ADR-027 §8 (thread policy) — and would not interoperate with the existing `asyncio` event bus without a bridging layer. Rejected.
- **Defer the fix to Phase 11**: ADR-018 already promised this behaviour, and Phase 10 imaging workflows fundamentally depend on it (fan-out across 4 GPU workers, multi-branch multimodal workflows, etc.). Deferring would block Phase 10 from delivering any meaningful parallelism. Rejected.
- **Expose a per-workflow `sequential: bool` config flag**: allows callers to opt in to the current broken behaviour for deterministic test runs. This is a legitimate debugging feature but should not be the default. Deferred to a follow-up: if test determinism becomes a pain point, a `deterministic=True` flag can be added that internally uses `asyncio.gather` in dependency order rather than fully concurrent dispatch. Not in scope for this addendum.

### Consequences

- Independent DAG branches execute concurrently, restoring the behaviour ADR-018 §5 and ARCH Appendix A promised.
- `ResourceManager.can_dispatch()` becomes load-bearing: it is the sole throttle preventing unbounded subprocess fan-out. Bugs in `can_dispatch` (e.g., the `gpu_slots=0` default identified in ADR-027 §9) now have user-visible impact rather than being masked by serialised execution.
- Tests that asserted strict sequential ordering between independent blocks will fail and must be updated. Tests that check dependency-respecting ordering (A before B when B depends on A) continue to work unchanged.
- Debuggability degrades slightly because async stack traces interleave. Mitigation: set `task.set_name(f"dispatch:{block_id}")` for better logs and exception reporting.
- The implementation is more sensitive to exceptions in event handlers. A bug in a subscriber (e.g., LineageRecorder raising) must not cascade — `EventBus.emit` already logs-and-continues on subscriber exceptions, but the scheduler-level try/finally in `execute()` is new and needs careful testing.
- Cancellation on engine shutdown is now explicit via `_cancel_active_tasks_on_shutdown`. Previously the scheduler could leak subprocesses if `execute()` raised. This change is a correctness improvement.
- The scheduler's memory footprint grows by a few pointers per running block (the `_active_tasks` dict). Negligible.

### Detailed impact scope

#### Rewritten files

| File | Current state | New state | Detailed changes |
|---|---|---|---|
| `src/scieasy/engine/scheduler.py` | `_dispatch` inline awaits `runner.run`. Every `await self._dispatch(...)` is inline-awaited by the caller. Zero `asyncio.create_task`. | `_dispatch` is a synchronous prelude that creates a task for `_run_and_finalize`. `execute()` wraps its body in `try/finally` to guarantee task cleanup. Event handlers call `_dispatch_newly_ready()` for throttling retries. `_check_completion()` additionally checks `_active_tasks` is empty. New `_cancel_active_tasks_on_shutdown()` helper. | **Add** field `self._active_tasks: dict[str, asyncio.Task[None]] = {}` in `__init__`. **Split** `_dispatch` (current ~34 lines) into `_dispatch` (prelude, ~15 lines) and `_run_and_finalize` (body, ~30 lines). **Add** `_dispatch_newly_ready()` (~12 lines). **Add** `_cancel_active_tasks_on_shutdown()` (~15 lines). **Change** `execute()` to wrap in `try/finally`. **Change** `_on_block_done` and `_on_process_exited` to call `_dispatch_newly_ready` instead of scanning inline (smaller, ~5 lines each). **Change** `_on_cancel_block` to branch on "handle present → terminate" vs "handle absent → task.cancel()". **Change** `_check_completion` to also check `not self._active_tasks`. Total diff approximately 150 lines changed across one file. |

#### Modified files

| File | Current state | Changes |
|---|---|---|
| `tests/engine/test_scheduler.py` (and related) | Some tests may assert strict serial ordering of independent blocks. | **Audit** each test. Tests asserting ordering within independent branches must be updated to assert "A happened before B" only when B depends on A. **Add** a new test: `test_independent_branches_run_concurrently` that constructs a two-root DAG with a sleep in each block and asserts the total wall time is approximately `max(a, b)` rather than `a + b`. **Add** a new test: `test_resource_throttling_retries_dispatch` that constructs a DAG where two blocks both require a GPU, sets `gpu_slots=1`, and asserts the second block enters RUNNING only after the first completes. **Add** a new test: `test_scheduler_shutdown_cleanup` that triggers an exception mid-workflow and asserts `_active_tasks` is empty and all subprocesses are terminated after `execute()` returns. |
| `tests/engine/test_dag.py` | Tests for DAG construction. | No changes expected. |
| `tests/engine/test_runner.py` | Tests for LocalRunner. | No changes expected — the `LocalRunner` interface is unchanged. |
| `tests/integration/test_multimodal_workflow.py` | Existing integration tests may implicitly depend on serial execution. | **Audit** the test. If it checks output values only, no change. If it checks event ordering between independent branches, update assertions. |

#### New tests required

- `tests/engine/test_scheduler_concurrency.py` (new file) containing:
  - `test_independent_branches_run_concurrently`
  - `test_resource_throttling_retries_dispatch`
  - `test_scheduler_shutdown_cleanup_on_exception`
  - `test_cancel_block_before_subprocess_starts` (edge case: task.cancel() path)
  - `test_cancel_block_during_subprocess_run` (normal case: ProcessHandle.terminate() path)
  - `test_cancel_workflow_with_mix_of_running_and_ready_blocks`

#### Documentation impact

| Document | Current state | Required changes |
|---|---|---|
| `docs/architecture/ARCHITECTURE.md` §6.1 (DAG scheduler) | Describes event-driven scheduler at a conceptual level. Does not mention `asyncio.Task` or `_active_tasks`. | **Clarify** that scheduling is implemented via `asyncio.create_task` per block, with `_active_tasks` as the concurrent task registry. **Add** a short paragraph on ResourceManager throttling semantics (blocks stay in READY when `can_dispatch` returns False; retry is triggered on the next resource release event). **Update** the pseudo-code in the section to reflect the split between `_dispatch` and `_run_and_finalize`. |
| `docs/architecture/ARCHITECTURE.md` §6.1 EventBus subscription matrix | Shows DAGScheduler subscribing to BLOCK_DONE, BLOCK_ERROR, etc. | No change — the subscriptions are unchanged, only the internal dispatch strategy is. |
| `docs/architecture/ARCHITECTURE.md` Appendix A (concrete example walkthrough) | States "Three IOBlocks load data in parallel". | No change — the addendum makes the prose accurate; previously it described behaviour that the implementation did not provide. |
| `docs/adr/ADR.md` | This addendum. | Appended after ADR-018's Detailed impact scope table. |
| `CHANGELOG.md` | Current entries. | **Add** entry under `[Unreleased]` → `### Fixed`: "Scheduler concurrency implementation per ADR-018 Addendum 1". |

#### Out of scope

- **No changes to BlockState, EventBus event types, or the subscription matrix**. ADR-018 remains authoritative for those.
- **No changes to cancellation message protocol on WebSocket**. ADR-018 §8.3 remains authoritative.
- **No changes to LineageRecord schema**. ADR-018's addition of termination fields remains authoritative.
- **No changes to ProcessHandle, ProcessRegistry, or spawn_block_process**. ADR-019 remains authoritative.
- **No changes to Collection transport or block iteration model**. ADR-020 remains authoritative.
- **No new block states, no new events**. This addendum is implementation-only.

---

## ADR-019: ProcessHandle, ProcessRegistry, and cross-platform process lifecycle

**Status**: proposed
**Date**: 2026-04-03

### Context

With all blocks executing in subprocesses (ADR-017) and user-initiated cancellation requiring reliable process termination (ADR-018), the framework needs a unified abstraction for managing OS processes across Linux, macOS, and Windows.

The original codebase had:

- `subprocess.Popen` calls in `FileExchangeBridge.launch()` (`src/scieasy/blocks/app/bridge.py:81–86`) that returned a `Popen` handle, but the caller (`AppBlock.run()` at `app_block.py:75`) discarded it. The process was fire-and-forget with no monitoring or termination capability.
- `src/scieasy/blocks/app/process_mgr.py` — a file containing only a docstring (`"""External process lifecycle management (subprocess)."""`). Completely empty.
- No process tracking anywhere in the codebase. No PID registry. No process monitoring loop. No cross-platform termination logic.

Process management is complicated by three platform-specific concerns:

1. **Termination semantics**: Linux/macOS support graceful (`SIGTERM`) then forced (`SIGKILL`) termination with process groups. Windows only has `TerminateProcess()` (always forced, no graceful equivalent) with Job Objects for tree management.
2. **Process tree management**: a block's subprocess may spawn child processes (R launching worker processes, ElMAVEN spawning helpers, multiprocessing pools). Killing only the root process leaves orphan children consuming resources.
3. **Death detection**: detecting that a subprocess has crashed, been OOM-killed, or been killed by the user via the OS task manager requires periodic polling with platform-specific APIs.

### Discussion points and resolution

| # | Topic | Options discussed | Final decision |
|---|---|---|---|
| 1 | Should we use `psutil` for cross-platform process management? | (A) Use `psutil` for all process operations. (B) Custom implementation with platform abstraction layer. (C) `psutil` as helper, custom Job Object handling on Windows. | **Decision: (C).** `psutil` provides convenient cross-platform `Process.is_running()`, `Process.children()`, `Process.kill()` etc. However, it does not manage Windows Job Objects (children spawned after `psutil.Process()` creation are not tracked). For reliable process tree management on Windows, explicit Job Object handling is needed. Use `psutil` where it helps, custom code where it doesn't. |
| 2 | Should ProcessHandle, ProcessRegistry, and ProcessMonitor be one class or separate? | (A) Single `ProcessManager` class. (B) Three separate components. | **Decision: (B).** ProcessHandle is per-process state, ProcessRegistry is global tracking, ProcessMonitor is an active polling loop. Separating them keeps each testable and replaceable independently. |
| 3 | Where should process lifecycle code live — in the block layer or engine layer? | (A) In `blocks/app/process_mgr.py` (current empty file location). (B) In `engine/runners/`. | **Decision: (B).** Process lifecycle management is an engine concern (applies to all block types via subprocess isolation), not a block-specific concern. The `blocks/app/process_mgr.py` file should be deleted. |
| 4 | Grace period on terminate: should it be configurable per block? | (A) Fixed 5-second grace period for all. (B) Configurable per block via class attribute. | **Decision: (B).** Some blocks (e.g., a database-connected block) may need more time for cleanup. Add `terminate_grace_sec: ClassVar[float] = 5.0` to `Block` base class. Note: Windows has no graceful termination, so grace period is only effective on Linux/macOS. |

### Decision

#### ProcessHandle

`ProcessHandle` is a cross-platform abstraction over an OS process providing three guarantees:

1. **Always terminable**: `terminate()` kills the process and all its children, on any platform.
2. **Always observable**: `is_alive()` and `exit_info()` report process status without blocking.
3. **Always tracked**: every `ProcessHandle` is registered in `ProcessRegistry` at creation and deregistered at cleanup.

```python
@dataclass
class ProcessExitInfo:
    """Information about how a process exited."""
    exit_code: int | None          # process exit code (None if killed by signal)
    signal_number: int | None      # signal that killed it (Linux/macOS only, None on Windows)
    was_killed_by_framework: bool   # True if terminated via ProcessHandle.terminate()/kill()
    platform_detail: str            # human-readable detail, e.g. "SIGKILL", "TerminateProcess"


class ProcessHandle:
    """Cross-platform handle for a managed subprocess.

    Created exclusively by spawn_block_process(). Never instantiated directly.
    """

    block_id: str                       # which block owns this process
    pid: int                            # OS process ID
    start_time: datetime                # when the process was launched
    resource_request: ResourceRequest   # resources this process holds
    _popen: subprocess.Popen            # underlying Popen object (private)
    _platform_ops: PlatformOps          # platform-specific operations (private)

    async def is_alive(self) -> bool:
        """Check if the process is still running. Non-blocking.

        Linux/macOS: os.kill(pid, 0) — signal 0 tests existence.
        Windows: OpenProcess() + GetExitCodeProcess() checks for STILL_ACTIVE.
        """

    async def exit_info(self) -> ProcessExitInfo | None:
        """Return exit information if process has exited, None if still running.

        Linux/macOS: os.waitpid(pid, WNOHANG) to reap zombie and get status.
            Decodes signal number from status via os.WIFSIGNALED/os.WTERMSIG.
        Windows: GetExitCodeProcess(). If != STILL_ACTIVE, process has exited.
        """

    async def terminate(self, grace_period_sec: float = 5.0) -> ProcessExitInfo:
        """Terminate the process and all its children.

        Linux/macOS:
            1. os.killpg(pgid, signal.SIGTERM) — send SIGTERM to entire process group.
            2. Wait up to grace_period_sec for process to exit gracefully.
            3. If still alive: os.killpg(pgid, signal.SIGKILL) — force kill entire group.
            4. os.waitpid() to reap.

        Windows:
            1. TerminateJobObject(job_handle, exit_code=1) — kills all processes in the Job Object.
               (No grace period — Windows TerminateProcess is always immediate.)
            2. Or if no Job Object: TerminateProcess(process_handle, 1) for root process,
               then taskkill /T /F /PID for tree cleanup.

        Returns ProcessExitInfo describing how the process was terminated.
        """

    async def kill(self) -> ProcessExitInfo:
        """Immediate forced termination. No grace period.

        Linux/macOS: os.killpg(pgid, signal.SIGKILL)
        Windows: TerminateJobObject or TerminateProcess
        """
```

#### spawn_block_process factory function

All subprocess creation in the framework goes through this single function. No code anywhere calls `subprocess.Popen` directly.

```python
def spawn_block_process(
    block_id: str,
    command: list[str],
    resource_request: ResourceRequest,
    event_bus: EventBus,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    stdin_data: bytes | None = None,
) -> ProcessHandle:
    """Launch a subprocess with platform-appropriate isolation and register it.

    Linux/macOS:
        subprocess.Popen(..., start_new_session=True)
        This calls setsid() in the child, creating a new process group.
        os.getpgid(pid) retrieves the group ID for future killpg() calls.

    Windows:
        subprocess.Popen(..., creationflags=CREATE_NEW_PROCESS_GROUP)
        CreateJobObject() + AssignProcessToJobObject(job, process_handle)
        SetInformationJobObject with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        (ensures all child processes die when the Job Object handle is closed).

    After launch:
        1. Creates ProcessHandle wrapping the Popen object.
        2. Registers handle in ProcessRegistry.
        3. Emits PROCESS_SPAWNED event on EventBus.
        4. Returns the handle.

    Parameters:
        block_id: Identifier of the block this process belongs to.
        command: Command and arguments (e.g., ["python", "-m", "scieasy.engine.runners.worker"]).
        resource_request: Resources declared by the block.
        event_bus: EventBus for emitting PROCESS_SPAWNED event.
        cwd: Working directory for the subprocess.
        env: Environment variables (merged with os.environ).
        stdin_data: Optional data to write to subprocess stdin after launch.
    """
```

#### ProcessRegistry

```python
class ProcessRegistry:
    """Singleton tracking all active block processes.

    Thread-safe. Used by ProcessMonitor for polling, by DAGScheduler for
    cancellation, and by engine shutdown for cleanup.
    """

    _handles: dict[str, ProcessHandle]   # keyed by block_id
    _lock: threading.Lock                # thread-safe access

    def register(self, handle: ProcessHandle) -> None:
        """Add a handle. Called by spawn_block_process()."""

    def deregister(self, block_id: str) -> None:
        """Remove a handle. Called when process exits (detected by ProcessMonitor)."""

    def get_handle(self, block_id: str) -> ProcessHandle | None:
        """Look up handle by block_id. Returns None if not found."""

    def active_handles(self) -> list[ProcessHandle]:
        """Return a snapshot of all currently active handles. Safe to iterate."""

    def terminate_all(self, grace_period_sec: float = 5.0) -> None:
        """Emergency shutdown: terminate every active process.
        Called during engine shutdown (SIGINT handler, server stop)."""
```

#### ProcessMonitor

```python
class ProcessMonitor:
    """Background coroutine that polls active processes for unexpected exits.

    Detects: crashes (non-zero exit), OOM kills, user killing via task manager,
    external app closing normally. Emits PROCESS_EXITED event for each detection.
    """

    registry: ProcessRegistry
    event_bus: EventBus
    poll_interval_sec: float = 1.0

    async def run(self) -> None:
        """Main polling loop. Runs until cancelled.

        Each iteration:
        1. Get snapshot of active handles from registry.
        2. For each handle, call is_alive().
        3. If not alive:
           a. Call exit_info() to get exit details.
           b. Emit PROCESS_EXITED event with block_id and exit_info.
           c. Deregister from registry.
        4. Sleep poll_interval_sec.
        """

    async def stop(self) -> None:
        """Signal the monitor to stop after the current poll cycle."""
```

**Event flow when ProcessMonitor detects unexpected process death:**

```
ProcessMonitor detects handle.is_alive() == False
    │
    ▼
emit PROCESS_EXITED(block_id="elmaven_001", exit_info={exit_code=1, signal=None, ...})
    │
    ├──→ DAGScheduler._on_process_exited():
    │       If block was PAUSED (AppBlock waiting for external app):
    │           Check exchange_dir for output files.
    │           Files present → transition to DONE (app wrote output before crashing).
    │           No files → transition to ERROR ("External process exited (code 1)
    │                                            without producing output files").
    │           Call propagate_skipped() → downstream blocks SKIPPED.
    │       If block was RUNNING:
    │           Transition to ERROR.
    │           Call propagate_skipped() → downstream blocks SKIPPED.
    │
    ├──→ ResourceManager._on_block_terminal():
    │       Release GPU/CPU/memory held by elmaven_001.
    │
    ├──→ ProcessRegistry:
    │       Deregister handle (already done by ProcessMonitor).
    │
    ├──→ LineageRecorder:
    │       Write lineage record: termination="error",
    │       termination_detail="Process exited with code 1".
    │
    └──→ CheckpointManager:
            Save checkpoint with elmaven_001 state = ERROR.
```

### Alternatives considered

- **Use `psutil` exclusively for all process management**: `psutil` provides convenient cross-platform process APIs but does not manage Windows Job Objects. Children spawned after the `psutil.Process` object is created are not automatically tracked. For reliable tree termination, explicit Job Object handling is required. `psutil` is used as a helper where appropriate (e.g., `psutil.pid_exists()` as a fast alive check), but the core lifecycle management is custom.

- **Rely on `Popen.terminate()` and `Popen.kill()`**: these methods only affect the root process, not its children. A scientific block that uses `multiprocessing.Pool` or spawns R child processes would leave orphans. Process group (`os.killpg`) and Job Object (`TerminateJobObject`) management is essential for clean termination.

- **No `ProcessMonitor` — only detect death when the scheduler checks**: the scheduler operates at block boundaries (between blocks), not continuously. If an AppBlock's external process crashes while the workflow is PAUSED, the crash goes undetected until the user interacts or the watcher times out. Continuous monitoring provides prompt detection and clean error reporting.

- **Single `ProcessManager` class combining Handle + Registry + Monitor**: conflates three distinct responsibilities with different lifecycles. ProcessHandle is created per-process and garbage-collected when the process exits. ProcessRegistry is a singleton that lives for the engine's lifetime. ProcessMonitor is a background task that runs and stops. Combining them makes testing harder (can't test registry logic without running a monitor loop) and makes the code harder to understand.

### Consequences

- Every subprocess in the framework is tracked, monitorable, and terminable from creation to cleanup. No orphan processes.
- Platform-specific code is confined to `engine/runners/platform.py`. Adding support for a new platform means implementing one `PlatformOps` subclass.
- `ProcessMonitor` adds a background polling loop at 1-second intervals. With typically <10 active processes, CPU overhead is negligible.
- `ProcessRegistry.terminate_all()` provides a clean engine shutdown path. On `SIGINT` or server stop, all block processes are terminated rather than orphaned.
- The `spawn_block_process()` factory enforces that all subprocesses are created with process group (POSIX) or Job Object (Windows) isolation. Code review can verify that no `subprocess.Popen` calls exist outside this function.
- External applications launched by AppBlock are now subject to the same lifecycle management as framework subprocesses. Killing an AppBlock kills ElMAVEN and all of ElMAVEN's child processes.
- The `ProcessHandle` abstraction is reusable if future runners (SSHRunner, SlurmRunner from ARCHITECTURE.md section 6.7) need different process management — they implement their own `ProcessHandle` subclass with appropriate remote termination logic.

### Detailed impact scope

#### New files

| File | Contents | Key classes/functions | Detailed specification |
|---|---|---|---|
| `src/scieasy/engine/runners/process_handle.py` | ProcessHandle, ProcessExitInfo, ProcessRegistry, spawn_block_process | See Decision section above | `ProcessExitInfo` dataclass: 4 fields (`exit_code: int | None`, `signal_number: int | None`, `was_killed_by_framework: bool`, `platform_detail: str`). `ProcessHandle` class: 6 attributes (`block_id: str`, `pid: int`, `start_time: datetime`, `resource_request: ResourceRequest`, `_popen: subprocess.Popen`, `_platform_ops: PlatformOps`), 4 async methods (`is_alive`, `exit_info`, `terminate`, `kill`). `ProcessRegistry` class: 2 internal attributes (`_handles: dict[str, ProcessHandle]`, `_lock: threading.Lock`), 5 methods (`register`, `deregister`, `get_handle`, `active_handles`, `terminate_all`). `spawn_block_process` function: 7 parameters, returns `ProcessHandle`. |
| `src/scieasy/engine/runners/process_monitor.py` | ProcessMonitor background coroutine | See Decision section above | `ProcessMonitor` class: 3 attributes (`registry: ProcessRegistry`, `event_bus: EventBus`, `poll_interval_sec: float = 1.0`), 1 internal attribute (`_running: bool`), 2 async methods (`run`, `stop`). |
| `src/scieasy/engine/runners/platform.py` | PlatformOps protocol, PosixOps, WindowsOps, get_platform_ops factory | See ADR-017 Decision section | `PlatformOps(Protocol)`: 5 methods (`create_process_group(popen) -> None`, `terminate_tree(pid, grace_period) -> ProcessExitInfo`, `kill_tree(pid) -> ProcessExitInfo`, `is_alive(pid) -> bool`, `get_exit_info(popen) -> ProcessExitInfo | None`). `PosixOps`: implements using `os.killpg`, `os.kill(pid, 0)`, `os.waitpid`, `signal.SIGTERM`, `signal.SIGKILL`, `os.getpgid`. `WindowsOps`: implements using `ctypes.windll.kernel32` for `CreateJobObject`, `AssignProcessToJobObject`, `TerminateJobObject`, `TerminateProcess`, `OpenProcess`, `GetExitCodeProcess`. `get_platform_ops() -> PlatformOps`: returns `WindowsOps()` if `sys.platform == "win32"`, else `PosixOps()`. |

#### Modified files

| File | Changes | Detailed field/parameter changes |
|---|---|---|
| `src/scieasy/blocks/base/block.py` | **Add** `terminate_grace_sec` class variable. | **Add** after `key_dependencies: ClassVar[list[str]] = []` (line 43): `terminate_grace_sec: ClassVar[float] = 5.0` — grace period in seconds for `ProcessHandle.terminate()`. Used by the scheduler when cancelling this block. Default 5 seconds. Linux/macOS: SIGTERM → wait this long → SIGKILL. Windows: ignored (TerminateProcess is always immediate). |
| `src/scieasy/blocks/app/process_mgr.py` | **Delete** this file. | File currently contains only `"""External process lifecycle management (subprocess)."""`. Process lifecycle is an engine-layer concern (ADR-019), not a block-layer concern. All process management is in `engine/runners/process_handle.py`, `engine/runners/process_monitor.py`, and `engine/runners/platform.py`. **Also update** `src/scieasy/blocks/app/__init__.py` if it imports from `process_mgr`. |
| `src/scieasy/engine/runners/__init__.py` | **Add** exports for new modules. | **Add** imports: `from scieasy.engine.runners.process_handle import ProcessHandle, ProcessExitInfo, ProcessRegistry, spawn_block_process`, `from scieasy.engine.runners.process_monitor import ProcessMonitor`, `from scieasy.engine.runners.platform import PlatformOps, get_platform_ops`. |

#### Documentation impact

| Document | Current state | Required changes |
|---|---|---|
| `docs/architecture/ARCHITECTURE.md` Section 6.4 (Resource management, lines 1127–1171) | Describes `ResourceManager` with `acquire()` / `release()`. No mention of automatic release on process death. | **Add** description of EventBus-triggered automatic resource release. Reference ProcessMonitor detection of process death. |
| `docs/architecture/ARCHITECTURE.md` Section 11 (Technology stack, lines 1690–1708) | "Process management: subprocess + watchdog" (line 1700). | **Update** to: "Process lifecycle: ProcessHandle + ProcessRegistry + ProcessMonitor. Cross-platform: POSIX signals + process groups (Linux/macOS), Job Objects + TerminateProcess (Windows). Optional: psutil for convenience methods." |
| `docs/architecture/ARCHITECTURE.md` Appendix B (Glossary, lines 1786–1803) | 12 glossary terms. No process management terms. | **Add** glossary entries: `ProcessHandle` — "Cross-platform abstraction over an OS process, providing terminate/monitor/query capabilities. Every subprocess in the framework is wrapped in a ProcessHandle." `ProcessRegistry` — "Singleton tracking all active block subprocesses. Enables cancellation, monitoring, and clean shutdown." `ProcessMonitor` — "Background coroutine that polls active processes for unexpected exits (crash, OOM, user kill via task manager)." |
| `docs/architecture/ARCHITECTURE.md` new subsection after Section 6.4 | Does not exist. | **Add** new Section 6.5: "Process lifecycle management" describing ProcessHandle, ProcessRegistry, ProcessMonitor, platform abstraction, and the spawn_block_process factory. |
| `CHANGELOG.md` | Current entries. | **Add** entry under `[Unreleased]` for ADR-019. |

---

## ADR-020: Collection-based data transport — eliminate engine-level batch iteration

**Status**: proposed
**Date**: 2026-04-03

### Context

The original architecture defined three batch execution modes at the engine level: `PARALLEL` (all items through one block concurrently, then the next block), `SERIAL` (each item through the full downstream pipeline before the next), and `ADAPTIVE` (engine decides based on downstream blocks). These modes were declared per-block via `batch_mode` and executed by a dedicated `BatchExecutor` component.

This design created cascading architectural problems that were discovered during the cancellation and process lifecycle design (ADR-017, ADR-018, ADR-019):

1. **ProcessRegistry key collision**: in parallel mode, the same `block_id` spawns multiple concurrent subprocesses, but `ProcessRegistry` uses `block_id` as a unique key — only one handle per block can be stored, making parallel subprocess tracking impossible.

2. **Parallel→serial→parallel pipeline problem**: when a parallel block (Cellpose) feeds into a serial block (napari review), the current block-level scheduler forces ALL items to complete the parallel block before ANY item enters the serial block. For 50 images with Cellpose taking 5 minutes each, the user waits ~4 hours before they can review the first result — even though img1's result was ready in 5 minutes. Solving this requires item-level pipelining with buffering between blocks, fundamentally changing the scheduler from block-level to item-level granularity.

3. **External software integration failure**: AppBlock's serial batch mode opens one instance of the external application per item (100 ElMAVEN windows for 100 mzXML files). Users expect to open ONE ElMAVEN window and load all 100 files. The `batch_mode` abstraction cannot express "pass the entire collection to a single invocation."

4. **Complexity cost**: `BatchExecutor` required parallel/serial/adaptive dispatch strategies, `BatchErrorStrategy` (STOP/SKIP/RETRY/PAUSE), `BatchResult` tracking (succeeded/failed/skipped per item), and interaction with `ResourceManager` for per-item resource allocation. This complexity propagated into the scheduler, checkpoint system, lineage records (`batch_info`), cancellation logic (cancel one item vs. entire batch), and frontend display (per-item progress).

The root cause of all four problems is the same: **the engine is trying to manage item-level iteration that it does not have domain knowledge to perform correctly.** The engine does not know whether Cellpose should process images independently (per-item), whether ElMAVEN should receive all files at once (collection), or whether napari should present images one by one (serial per-item). Only the block author knows the correct batch semantics for their tool.

### Discussion points and resolution

| # | Topic | Options discussed | Final decision |
|---|---|---|---|
| 1 | Should Collection be a 7th base data type alongside Array, Series, etc.? | (A) Yes, add Collection to the type hierarchy. (B) No, Collection is a transport wrapper — its type identity is determined by its contents. | **Decision: (B).** Collection is not a data type — it is a packaging mechanism at the port/block boundary. A `Collection[Image]` is typed as `Image` for port matching purposes. This keeps the 6 base types stable and avoids polluting the type system. |
| 2 | Should the engine ever iterate over items? | (A) Engine iterates by default, blocks can opt out with `batch_handling=COLLECTION`. (B) Engine never iterates — all data flows as Collections, blocks handle iteration internally. | **Decision: (B).** Complete elimination of engine-level iteration. The engine only passes Collections between blocks. This is the maximally simple model for the engine and gives blocks full control. |
| 3 | Does this increase block author burden? | (A) Yes, unacceptably — block authors must write iteration loops. (B) Manageable — the Block base class provides `pack()`, `unpack()`, `map_items()`, `parallel_map()` utilities, and a `PerItemProcessBlock` convenience base class can be offered. | **Decision: (B).** The Block base class provides utilities that make simple per-item blocks as easy to write as before. The `map_items()` one-liner covers 80% of cases. Advanced blocks (ElMAVEN, napari) benefit from full control. |
| 4 | How should CodeBlock handle Collections? | (A) Pass Collections directly to user scripts (breaking change — scripts must understand Collection). (B) CodeBlock auto-unpacks before calling user code, auto-repacks after. | **Decision: (B).** CodeBlock transparently unwraps: length=1 → single native object (numpy/pandas/etc.), length>1 → list of native objects. User scripts never see a Collection object. This preserves the "zero framework knowledge" promise for script authors. |
| 5 | What happens to partial results when a block is cancelled? | (A) Engine guarantees partial result preservation. (B) All results lost on cancel — block can optionally save partial results to storage. | **Decision: (B).** Cancellation kills the subprocess, losing in-memory state. This is the same behaviour as stopping a Jupyter notebook cell. Blocks that need partial result preservation can write to storage incrementally — this is a block-level concern, not an engine concern. |
| 6 | How should Port type checking work with Collections? | Port declares `accepted_types=[Image]`. A `Collection[Image]` flows through. Is this compatible? | **Decision: Yes, transparently.** The port system checks the Collection's `item_type` against `accepted_types`, not the Collection wrapper itself. `Collection[Image]` matches `accepted_types=[Image]`. From the port system's perspective, Collection is invisible. |

### Decision

#### Core model change

**All data flowing between blocks is wrapped in a `Collection`.** The engine never unpacks, iterates, or inspects the contents of a Collection. It treats every Collection as an opaque unit: one Collection in, one Collection out, one subprocess, one ProcessHandle.

```
BEFORE (engine-driven iteration):
    IOBlock outputs [img1, img2, ..., img100]
        → engine unpacks into 100 items
        → BatchExecutor calls Cellpose.run(img1), run(img2), ..., run(img100)
        → engine collects 100 results
    [mask1, mask2, ..., mask100]

AFTER (Collection-based transport):
    IOBlock outputs Collection[Image](100 items)   ← one DataObject-like wrapper
        → engine passes it as-is to one run() call
        → Cellpose.run(inputs={"images": Collection[Image]})   ← called once
        → returns Collection[Image](100 masks)   ← one wrapper
```

A single item is simply `Collection` with `length=1`. There is no special case — the engine always deals with Collections.

#### Collection specification

```python
class Collection:
    """Homogeneous ordered collection of DataObjects.

    NOT a DataObject subclass — it is a transport wrapper, not a data type.
    Its type identity for port matching is determined by item_type.

    Invariants:
        - All items must be instances of the same base DataObject subclass.
        - item_type is set at construction and cannot change.
        - length=0 is valid (empty collection).
    """

    items: list[DataObject]
    item_type: type                    # e.g. Image, DataFrame

    def __init__(self, items: list[DataObject], item_type: type | None = None):
        if items and item_type is None:
            item_type = type(items[0])
        if items:
            for i, item in enumerate(items):
                if not isinstance(item, item_type):
                    raise TypeError(
                        f"Collection requires homogeneous types: item[{i}] is "
                        f"{type(item).__name__}, expected {item_type.__name__}")
        self.items = items
        self.item_type = item_type or DataObject

    def __getitem__(self, index): ...
    def __iter__(self): ...
    def __len__(self): return len(self.items)

    @property
    def length(self) -> int: return len(self.items)

    def storage_refs(self) -> list[StorageReference]:
        """Return StorageReference for each item (for cross-process serialisation)."""
        return [item.storage_ref for item in self.items]
```

#### Port system adaptation

Port type checking becomes Collection-transparent:

```python
def port_accepts_type(port: Port, data_type: type) -> bool:
    # If data_type is Collection, check item_type against accepted_types
    if data_type is Collection:
        return True  # Collection itself is always structurally valid;
                     # item_type is checked at runtime via constraint or connection validation

def validate_connection(source_port: OutputPort, target_port: InputPort) -> tuple[bool, str]:
    # Check that source's item_type (inside Collection) matches target's accepted_types
    # Since ALL data is Collection, this means:
    #   source produces Collection[X] → check X against target.accepted_types
    # Port.accepted_types still declares the ITEM type, not Collection
```

Block authors declare ports exactly as before:

```python
input_ports = [InputPort(name="images", accepted_types=[Image])]
```

This port accepts `Collection[Image]` of any length. The port system extracts `item_type=Image` from the Collection and checks it against `accepted_types=[Image]`.

#### Block base class utilities

```python
class Block(ABC):

    @abstractmethod
    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        ...

    # --- Pack / unpack ---

    @staticmethod
    def pack(items: list[DataObject], item_type: type | None = None) -> Collection:
        """Pack a list of DataObjects into a Collection."""
        return Collection(items, item_type=item_type)

    @staticmethod
    def unpack(collection: Collection) -> list[DataObject]:
        """Unpack a Collection into a list of individual DataObjects."""
        return list(collection.items)

    @staticmethod
    def unpack_single(collection: Collection) -> DataObject:
        """Unpack a length-1 Collection into a single DataObject.
        Raises ValueError if length != 1."""
        if len(collection) != 1:
            raise ValueError(f"Expected single-item Collection, got length {len(collection)}")
        return collection.items[0]

    # --- Iteration helpers (execute inside the block's subprocess) ---

    @staticmethod
    def map_items(func: Callable[[DataObject], DataObject],
                  collection: Collection) -> Collection:
        """Apply func to each item sequentially. Returns new Collection."""
        results = [func(item) for item in collection]
        return Collection(results)

    @staticmethod
    def parallel_map(func: Callable[[DataObject], DataObject],
                     collection: Collection,
                     max_workers: int = 4) -> Collection:
        """Apply func to each item using a process pool. Returns new Collection."""
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(func, collection.items))
        return Collection(results)
```

#### CodeBlock auto-unpack/repack

CodeBlock inserts a transparent conversion layer so user scripts never see Collection objects:

```python
class CodeBlock(Block):
    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        # Auto-unpack: Collection → native object(s) for user scripts
        user_inputs = {}
        for name, coll in inputs.items():
            if len(coll) == 1:
                user_inputs[name] = coll[0].to_memory()        # single native object
            else:
                user_inputs[name] = [item.to_memory() for item in coll]  # list

        # Execute user script (user sees numpy arrays, pandas DataFrames, etc.)
        result = runner.execute(script, user_inputs, config)

        # Auto-repack: native object(s) → Collection
        outputs = {}
        for name, value in result.items():
            if isinstance(value, list):
                outputs[name] = self.pack([wrap_as_dataobject(v) for v in value])
            else:
                outputs[name] = self.pack([wrap_as_dataobject(value)])
        return outputs
```

User scripts remain unchanged:

```python
# length=1: user receives a numpy array
smoothed = savgol_filter(input_0, 11, 3)
output_0 = smoothed

# length=100: user receives a list of numpy arrays
output_0 = [savgol_filter(s, 11, 3) for s in input_0]
```

#### What is removed

| Component | File | Status |
|---|---|---|
| `BatchMode` enum (PARALLEL, SERIAL, ADAPTIVE) | `blocks/base/state.py` | **Deleted** |
| `BatchErrorStrategy` enum (STOP, SKIP, RETRY, PAUSE) | `blocks/base/state.py` | **Deleted** |
| `BatchResult` dataclass | `blocks/base/result.py` | **Deleted** |
| `Block.batch_mode` class variable | `blocks/base/block.py` | **Deleted** |
| `Block.on_batch_error` class variable | `blocks/base/block.py` | **Deleted** |
| `BatchExecutor` class | `engine/batch.py` | **Entire file deleted** |
| `NodeDef.batch_mode` field | `workflow/definition.py` | **Deleted** |
| `LineageRecord.batch_info` field | `core/lineage/record.py` | **Deleted** |
| `batch_info TEXT` column | `core/lineage/store.py` | **Deleted from schema** |
| ADR-010 (Batch execution mode per block) | `docs/adr/ADR.md` | **Superseded by ADR-020** |

### Alternatives considered

- **Keep engine-level iteration with a `BatchHandling` flag (PER_ITEM vs COLLECTION)**: adds a new enum and branching logic in the scheduler ("if COLLECTION, pass whole; if PER_ITEM, iterate"). This halves the complexity compared to the original three-mode system but still leaves the engine responsible for iteration semantics. The Collection-only model eliminates this branching entirely.

- **Add a buffer mechanism between blocks for parallel→serial transitions**: solves the pipeline problem but adds a new runtime component (buffer), flush-condition configuration, and type-system complexity (buffer wraps items). The Collection model eliminates the need for inter-block buffering because there are no mode transitions — every block receives and returns one Collection.

- **Keep `BatchExecutor` but fix ProcessRegistry to support one-to-many**: addresses the ProcessRegistry collision but not the ElMAVEN problem, not the pipeline problem, and not the complexity cost. A targeted fix for a systemic issue.

### Consequences

- **Engine simplification**: `BatchExecutor` is deleted. `DAGScheduler` becomes a pure block-level orchestrator with no item-level logic. ~200 lines of batch code removed (BatchExecutor, BatchMode, BatchErrorStrategy, BatchResult, batch-related scheduler logic).
- **Block author control**: block authors have full control over how they process collections — parallel, serial, whole-collection, or any custom strategy. This matches reality: Cellpose has built-in GPU batching, ElMAVEN loads multiple files natively, napari supports multi-image sessions.
- **ProcessRegistry stays simple**: always 1 block = 1 subprocess = 1 ProcessHandle. No one-to-many mapping needed.
- **Cancellation stays simple**: cancel block = kill one subprocess = done. No per-item cancel tracking, no partial batch results, no multi-process termination coordination.
- **CodeBlock transparency**: user scripts are unaffected. The auto-unpack/repack layer in CodeBlock ensures that scripts written for the old model continue to work — a single-item Collection is unwrapped to a single native object, identical to what the script received before.
- **ADR-010 superseded**: the per-block `batch_mode` declaration is replaced by block-internal iteration logic. Blocks that previously declared `batch_mode=PARALLEL` now use `self.parallel_map()`. Blocks that declared `batch_mode=SERIAL` now use a simple for-loop. Blocks that declared `batch_mode=ADAPTIVE` no longer need the engine's look-ahead — they choose their own strategy.
- **Tradeoff — partial results**: the engine no longer guarantees per-item error isolation or partial result preservation. A subprocess crash loses all items. This is acceptable because: (1) it matches user expectations (like Jupyter cell interruption), (2) blocks can implement incremental saving if needed, (3) the complexity cost of per-item tracking far exceeds its benefit for the target use case.
- **New Collection type**: `Collection` is a new construct at the transport layer. It must be supported in cross-process serialisation (subprocess worker), checkpoint serialisation, and lineage recording. Since Collection holds `StorageReference` pointers (not data), serialisation overhead is minimal.

### Detailed impact scope

#### New files

| File | Contents |
|---|---|
| `src/scieasy/core/types/collection.py` | `Collection` class with homogeneity enforcement, `__getitem__`, `__iter__`, `__len__`, `storage_refs()`. |
| `tests/core/test_collection.py` | Tests: construction, homogeneity enforcement (reject mixed types), length-0 edge case, pack/unpack round-trip, storage_refs extraction. |

#### Deleted files

| File | Reason |
|---|---|
| `src/scieasy/engine/batch.py` | `BatchExecutor` is entirely eliminated. All batch logic moves to Block internals. |

#### Modified files — Layer 1 (Data Foundation)

| File | Changes |
|---|---|
| `core/lineage/record.py` | **Delete** `batch_info: dict[str, Any] \| None = field(default=None)` (line 35). |
| `core/lineage/store.py` | **Delete** `batch_info TEXT` from `_CREATE_TABLE` SQL (line 24). **Remove** `batch_info` from `write()` INSERT statement (line 67–81) and values tuple. **Remove** `batch_info` parsing from `_row_to_record()` (line 99). **Remove** `batch_info` from all SELECT column lists in `query()` (line 111) and `ancestors()` (line 141). **Update** row index offsets in `_row_to_record()` after column removal. |
| `core/types/__init__.py` | **Add** re-export: `from scieasy.core.types.collection import Collection`. |

#### Modified files — Layer 2 (Block System)

| File | Changes |
|---|---|
| `blocks/base/state.py` | **Delete** `BatchMode` enum (lines 27–33, 3 values). **Delete** `BatchErrorStrategy` enum (lines 43–49, 4 values). File retains: `BlockState`, `ExecutionMode`, `InputDelivery`. |
| `blocks/base/block.py` | **Delete** import of `BatchErrorStrategy, BatchMode` from line 10. **Delete** `batch_mode: ClassVar[BatchMode] = BatchMode.PARALLEL` (line 40). **Delete** `on_batch_error: ClassVar[BatchErrorStrategy] = BatchErrorStrategy.SKIP` (line 41). **Change** `run()` signature (line 111) from `dict[str, Any] -> dict[str, Any]` to `dict[str, Collection] -> dict[str, Collection]`. **Add** import `from scieasy.core.types.collection import Collection`. **Add** 6 utility methods: `pack()`, `unpack()`, `unpack_single()`, `map_items()`, `parallel_map()`, `get_single_or_list()` (for CodeBlock). |
| `blocks/base/result.py` | **Delete** `BatchResult` dataclass (lines 18–24). Retain `BlockResult`. |
| `blocks/base/__init__.py` | **Remove** imports/exports: `BatchErrorStrategy`, `BatchMode`, `BatchResult` (lines 16, 18–19, 26–28). **Add** import/export: `Collection`. |
| `blocks/base/ports.py` | **Update** `port_accepts_type()` (line 36): if incoming type is `Collection`, extract `item_type` and check that against `accepted_types`. **Update** `port_accepts_signature()` (line 48): handle `Collection` signature by delegating to item signature. **Update** `validate_connection()` (line 80): when source produces `Collection[X]`, check `X` against target's `accepted_types`. |
| `blocks/io/io_block.py` | **Update** `run()` return: wrap result in `Collection`. `direction="input"`: single file → `self.pack([result])`, directory → `self.pack(results)`. `direction="output"`: `self.unpack()` or `self.unpack_single()` before writing. |
| `blocks/process/process_block.py` | **Update** `run()` signature to `dict[str, Collection] -> dict[str, Collection]`. |
| `blocks/process/builtins/merge.py` | **Update** to unpack input Collections, perform Arrow concat, pack result. |
| `blocks/process/builtins/split.py` | **Update** to unpack input Collection, split, pack into two output Collections. |
| `blocks/code/code_block.py` | **Add** auto-unpack layer before user script execution: Collection len=1 → single native object, len>1 → list. **Add** auto-repack layer after: single value → `pack([wrap(value)])`, list → `pack([wrap(v) for v in value])`. **Update** `_prepare_inputs()` to first extract from Collection, then apply `InputDelivery` mode. |
| `blocks/app/app_block.py` | **Update** `run()` to receive `Collection`. Block decides internally whether to unpack (napari) or pass whole collection to bridge (ElMAVEN). |
| `blocks/ai/ai_block.py` | **Update** `run()` signature to `dict[str, Collection]`. |
| `blocks/subworkflow/subworkflow_block.py` | **Update** `run()` and `_sequential_execute()` to pass Collections through child workflow. |

#### Modified files — Layer 3 (Execution Engine)

| File | Changes |
|---|---|
| `engine/batch.py` | **Deleted** (see above). |
| `engine/__init__.py` | **Update** docstring: remove "batch executor" (line 1). |
| `engine/scheduler.py` | **Remove** any `BatchExecutor` usage or batch_mode branching. Scheduler calls `runner.run()` once per block, passing Collection inputs. |
| `engine/events.py` | **Remove** any batch-related event types if present. |
| `engine/checkpoint.py` | **Remove** any batch-related fields from `WorkflowCheckpoint` if present. |

#### Modified files — Layer 4 (Workflow Definition)

| File | Changes |
|---|---|
| `workflow/definition.py` | **Delete** `batch_mode: str \| None = None` from `NodeDef` (line 21). |

#### Modified files — Tests

| File | Changes |
|---|---|
| `tests/blocks/test_code_block.py` | **Add** tests for Collection auto-unpack/repack: single item, multiple items, list output. |
| `tests/blocks/test_io_block.py` | **Update** assertions to expect Collection-wrapped outputs. |
| `tests/blocks/test_app_block.py` | **Update** to pass Collection inputs, verify Collection outputs. |
| `tests/blocks/test_process_block.py` | **Update** to use pack/unpack in test assertions. |
| `tests/blocks/test_ports.py` | **Add** tests for Collection-transparent type checking: `Collection[Image]` matches port `accepted_types=[Image]`. |
| `tests/blocks/test_subworkflow.py` | **Update** to pass/expect Collections. |

#### Modified files — Documentation

| File | Changes |
|---|---|
| `docs/architecture/ARCHITECTURE.md` | Section 3 (layer overview): remove "batch executor" from Layer 3 description. Section 4.4 (lineage): remove `batch_info` field. Section 5.1 (Block base): remove `BatchMode`, `batch_mode`, add Collection and utility methods. Section 6.2 (Batch execution): **rewrite entirely** — describe Collection model, block-internal iteration, pack/unpack utilities. Section 6.6 (Batch error handling): **rewrite or delete** — no engine-level batch error strategy. Section 10.1 (Workflow YAML): remove `batch_mode` and `batch: true` from all node examples. Appendix A (example): update execution description. Appendix B (glossary): add `Collection` definition. |
| `docs/architecture/PROJECT_TREE.md` | Remove `engine/batch.py` entry. Update `blocks/base/state.py` annotation (remove BatchMode). Update `blocks/base/result.py` annotation (remove BatchResult). Update `blocks/base/block.py` annotation (remove batch_mode, add Collection utilities). Add `core/types/collection.py` entry. Update engine file count (11→10). Update total file count. |
| `docs/adr/ADR.md` | **Change** ADR-010 status from `accepted` to `superseded by ADR-020`. |
| `docs/roadmap/ROADMAP_v0.1.md` | Remove `BatchExecutor`, `BatchMode`, `BatchErrorStrategy` checklist items. Update Phase 5 description. |
| `docs/testing/phase-5-ai-tests.md` | Remove `tests/engine/test_batch.py` section. Replace with Collection transport tests. |
| `docs/testing/phase-5-human-tests.md` | Remove Test 9 (Batch Execution). Remove checklist items 12–14. Replace with Collection-based test scenarios. |
| `CHANGELOG.md` | Add ADR-020 entry under `[Unreleased]`. |

---

## ADR-020 Addendum: Lazy loading, memory safety, and boundary conversion

**Status**: proposed
**Date**: 2026-04-03

### Purpose

This addendum addresses five integration concerns discovered during review of ADR-020's interaction with the lazy loading system (ADR-007), subprocess isolation (ADR-017), and external software / user script boundaries.

### Addendum 1: unpack() returns DataObject, not ViewProxy

**Decision**: `Block.unpack(collection)` returns `list[DataObject]`. Block authors call `item.view()` to obtain a `ViewProxy` for lazy access.

**Rationale**: Collection declares that it holds DataObjects. `unpack()` should return exactly what Collection contains — no implicit conversion. The block author explicitly decides when and how to access data:

```python
images = self.unpack(inputs["images"])   # list[DataObject]
for img in images:
    proxy = img.view()                   # explicit: get lazy accessor
    data = proxy.slice({"y": slice(0, 100)})  # partial read
    # or
    data = proxy.to_memory()             # full load — author's choice
```

**Impact on existing code**:

| File | Change |
|---|---|
| `blocks/base/block.py` | `unpack()` return type annotation: `list[DataObject]` (not `list[ViewProxy]`). All other utilities (`map_items`, `parallel_map`, `process_item`) pass DataObjects to the user-provided function. |
| `blocks/process/process_block.py` | `process_item(self, item: DataObject, config)` — receives DataObject. |
| All ProcessBlock subclasses | Must call `item.view().to_memory()` or `item.view().slice()` to access data. |
| Documentation | ARCHITECTURE.md Section 6.2 example patterns must show `.view()` calls. |

### Addendum 2: IOBlock lazy Collection construction

**Decision**: When IOBlock loads a directory of files in `direction="input"`, it creates DataObjects with `StorageReference` pointing to each file on disk. It does **not** call `to_memory()` or read file contents.

**Rationale**: Eager loading N files during Collection construction defeats lazy loading. For 100 × 1GB TIFFs, eager construction = 100GB memory. Lazy construction = 100 × StorageReference ≈ 100KB.

```python
class IOBlock(Block):
    def run(self, inputs, config):
        path = Path(config["path"])

        if path.is_dir():
            # Lazy: create StorageReference per file, do NOT read data
            items = []
            for f in sorted(path.iterdir()):
                ref = StorageReference(backend="filesystem", path=str(f))
                obj = DataObject(storage_ref=ref, metadata={"source_file": f.name})
                items.append(obj)
            return {"data": self.pack(items)}
        else:
            # Single file
            ref = StorageReference(backend="filesystem", path=str(path))
            obj = DataObject(storage_ref=ref)
            return {"data": self.pack([obj])}
```

**Impact on existing code**:

| File | Change |
|---|---|
| `blocks/io/io_block.py` | `direction="input"` path: when `path.is_dir()`, iterate files and create `DataObject(storage_ref=...)` without calling `adapter.read()`. For single files, same pattern. Adapter is invoked lazily by ViewProxy when downstream blocks access data, not at load time. |
| `blocks/io/adapters/base.py` | `FormatAdapter` protocol may need a `create_reference(path) -> StorageReference` method that builds a ref without reading, in addition to the existing `read(path) -> DataObject` that does read. |
| `blocks/io/adapters/*.py` | Each adapter adds `create_reference()` implementation. For Zarr: ref points to `.zarr` directory. For Parquet: ref points to `.parquet` file. For TIFF: ref points to `.tif` file. |
| `core/proxy.py` | `ViewProxy` must be able to construct from a raw file `StorageReference` and delegate to the appropriate adapter for actual reading when `.to_memory()` or `.slice()` is called. |

### Addendum 3: parallel_map memory is block author's responsibility

**Decision**: `parallel_map` does not impose memory limits. Block authors choose `max_workers` based on their knowledge of item size. The framework provides a warning in documentation and docstring.

**Rationale**: 80% of `parallel_map` usage is small items (spectra, small tables) where memory is not a concern. For large items, block authors should use `map_items` (serial) or `map_items_to_storage` (serial + flush), or manage parallelism via domain-specific APIs (e.g., Cellpose's GPU batch size). The framework cannot predict item memory footprint without loading the item.

**Warning text** (in `parallel_map` docstring and developer documentation):

```
Warning: parallel_map loads `max_workers` items into memory concurrently.
For large items (images, MSI datasets), set max_workers=1 or use
map_items_to_storage() which flushes each result to disk immediately.
```

**Impact on existing code**:

| File | Change |
|---|---|
| `blocks/base/block.py` | `parallel_map()` docstring: add memory warning about concurrent item loading. |
| `docs/block-development.md` (future) | Developer guide must explain when to use `map_items` vs `parallel_map` vs `map_items_to_storage` with clear guidance on item size thresholds. |

### Addendum 4: CodeBlock uses LazyList for Collection length > 1

**Decision**: When auto-unpacking a Collection with length > 1 for user scripts, CodeBlock wraps items in a `LazyList` instead of eagerly loading all items into a Python list.

**Rationale**: Eager `[item.to_memory() for item in coll]` loads all items into memory simultaneously — worse than the old per-item BatchExecutor model. LazyList loads items on demand, bounding memory to the number of items the user's script holds simultaneously.

```python
class LazyList:
    """Looks like a list, loads items on demand from storage.

    Supports: len(), indexing, iteration, slicing.
    Does NOT support: np.array(lazy_list) without full materialisation
    (which is the user's explicit choice, like Dask's .compute()).
    """

    def __init__(self, collection: Collection):
        self._collection = collection

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self._collection[i].view().to_memory()
                    for i in range(*index.indices(len(self)))]
        return self._collection[index].view().to_memory()

    def __len__(self):
        return len(self._collection)    # no data loaded

    def __iter__(self):
        for i in range(len(self)):
            yield self[i]              # load one, yield, previous can be GC'd

    def __repr__(self):
        return f"LazyList[{self._collection.item_type.__name__}](length={len(self)})"
```

**CodeBlock auto-unpack logic:**

```python
# In CodeBlock.run():
for name, coll in inputs.items():
    if len(coll) == 1:
        user_inputs[name] = coll[0].view().to_memory()   # single native object
    else:
        user_inputs[name] = LazyList(coll)                # lazy list
```

**User script experience:**

```python
# Iteration — memory safe (1 item at a time):
output_0 = [savgol_filter(s, 11, 3) for s in input_0]

# Indexing — loads only the requested item:
first = input_0[0]
last = input_0[-1]

# Length — no data loaded:
n = len(input_0)

# Full materialisation — user's explicit choice (may OOM on large data):
all_data = list(input_0)       # loads everything
all_data = np.array(input_0)   # loads everything
```

**Auto-repack output handling:**

When the user script returns a list, the framework repacks it. If the list is large, `pack()` auto-flushes each item to storage (see Addendum 5). A size-threshold warning is emitted if total output exceeds a configurable limit (default 2GB):

```python
# In CodeBlock auto-repack:
total_size = sum(estimate_size(v) for v in output_values)
if total_size > config.get("memory_warning_threshold_gb", 2.0) * 1e9:
    logger.warning(
        f"Script output is {total_size / 1e9:.1f} GB in memory. "
        f"For large collections, consider processing items one at a time "
        f"or using script mode with PROXY delivery."
    )
```

**Impact on existing code**:

| File | Change |
|---|---|
| `blocks/code/code_block.py` | Auto-unpack: replace `[item.to_memory() for item in coll]` with `LazyList(coll)` for length > 1. Auto-repack: add size warning. |
| New file: `blocks/code/lazy_list.py` | `LazyList` class implementation. |
| `tests/blocks/test_code_block.py` | Add tests: LazyList iteration (memory bounded), LazyList indexing, LazyList len (no load), auto-repack size warning. |

### Addendum 5: Three-tier memory safety with automatic flush-to-storage

**Decision**: The framework provides three tiers of block authoring interface with automatic memory management. All framework-provided utilities (`map_items`, `parallel_map`, `pack`) automatically flush large outputs to storage.

#### Tier 1: `process_item()` — zero memory management (80% of blocks)

Block author overrides a single method. Framework handles iteration, flush, and packing:

```python
class ProcessBlock(Block):
    def process_item(self, item: DataObject, config: BlockConfig) -> DataObject:
        """Override this for per-item processing. Framework handles everything else."""
        raise NotImplementedError

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Default: iterate primary input, auto-flush each result."""
        primary = list(inputs.values())[0]
        refs = []
        for item in primary:
            result = self.process_item(item, config)
            result = _auto_flush(result)
            refs.append(result)                  # ~KB ref only
        return {self.output_ports[0].name: Collection(refs)}
```

Peak memory: 1 input item + 1 output item. Constant regardless of Collection size.

#### Tier 2: `run()` + framework utilities — automatic safety (15% of blocks)

Block author overrides `run()` but uses `map_items` / `parallel_map` / `pack`:

```python
def run(self, inputs, config):
    return {"masks": self.map_items(self._segment, inputs["images"])}
```

`map_items` and `parallel_map` auto-flush each result to storage internally. `pack()` auto-flushes any remaining in-memory items as a safety net.

Peak memory during `map_items`: 1 input + 1 output per iteration.
Peak memory at `pack()`: items already flushed, only refs remain.

#### Tier 3: `run()` + manual loop — pack() safety net (5% of blocks)

Block author writes a manual loop. `pack()` flushes accumulated items:

```python
def run(self, inputs, config):
    results = []
    for img in self.unpack(inputs["images"]):
        results.append(segment(img.view().to_memory()))   # accumulates in memory
    return {"masks": self.pack(results)}                   # pack() flushes each to storage
```

Peak memory: N × output_item_size during the loop (cannot be prevented).
After `pack()`: all flushed to storage, only refs remain.

This is the least optimal path but still has the `pack()` safety net.

#### Auto-flush implementation

```python
def _auto_flush(obj: DataObject) -> DataObject:
    """Write in-memory DataObject to storage, return lightweight reference.

    If the object already has a StorageReference, return as-is (no-op).
    Called internally by map_items, parallel_map, pack, and process_item default run.
    """
    if hasattr(obj, 'storage_ref') and obj.storage_ref is not None:
        return obj
    ref = _get_output_storage_backend().write(obj)
    return DataObject(storage_ref=ref, metadata=obj.metadata, dtype_info=obj.dtype_info)
```

**`_auto_flush` requires access to a storage backend within the subprocess.** The subprocess worker (`engine/runners/worker.py`) must initialise an output storage directory and make it available to `_auto_flush` via a thread-local or module-level reference.

#### worker.py force-write as final safety net

After `block.run()` returns, `worker.py` scans all output Collections. Any item without a `StorageReference` is written to storage. This catches cases where a block bypasses all framework utilities:

```python
# In worker.py, after block.run() returns:
for name, coll in outputs.items():
    for i, item in enumerate(coll):
        if item.storage_ref is None:
            item.storage_ref = storage_backend.write(item)
```

This does not reduce peak memory (items are already in memory), but ensures cross-process serialisation works.

#### AppBlock boundary conversion — memory safe by design

`FileExchangeBridge.prepare()` iterates the Collection and writes each item to a file one at a time:

```python
class FileExchangeBridge:
    def prepare(self, collection: Collection, exchange_dir: Path):
        for i, item in enumerate(collection):
            data = item.view().to_memory()      # +1 item
            adapter.write(data, exchange_dir / f"item_{i}{ext}")  # write file
            # data eligible for GC                # -1 item
```

Peak memory: 1 item. Safe regardless of Collection size.

**Impact on existing code**:

| File | Change | Detail |
|---|---|---|
| `blocks/base/block.py` | **Add** `process_item()` method to `Block` (raises `NotImplementedError`). **Add** `_auto_flush()` static method. **Modify** `map_items()`: call `_auto_flush(result)` after each `func(item)`. **Modify** `parallel_map()`: call `_auto_flush(result)` for each result. **Modify** `pack()`: call `_auto_flush(item)` for each item before adding to Collection. | `process_item` signature: `(self, item: DataObject, config: BlockConfig) -> DataObject`. |
| `blocks/process/process_block.py` | **Add** default `run()` implementation that iterates primary input, calls `self.process_item()`, auto-flushes, packs. Subclasses can override either `process_item()` (simple) or `run()` (complex). | Default `run()` uses first input port as primary input, first output port as output. |
| `blocks/app/bridge.py` | **Modify** `FileExchangeBridge.prepare()` to accept `Collection` and iterate items one at a time with per-item materialisation and file write. | Replace current bulk prepare with per-item loop. |
| `engine/runners/worker.py` | **Add** output storage directory initialisation. **Add** post-run scan: flush any items without StorageReference. **Add** `_get_output_storage_backend()` module-level accessor for `_auto_flush`. | Worker must know the project's storage directory to write intermediate results. |
| `core/storage/base.py` | `StorageBackend.write()` must handle writing a raw in-memory DataObject (not just ViewProxy-backed objects). | May need a `write_from_memory(data, path)` variant or auto-detection. |
| New file: `blocks/code/lazy_list.py` | `LazyList` class. | See Addendum 4. |
| New file: `tests/core/test_lazy_list.py` or extend `tests/blocks/test_code_block.py` | LazyList tests: iteration, indexing, len, GC behaviour. | |
| `docs/architecture/ARCHITECTURE.md` Section 6.2 | **Update** Collection section to document the three-tier interface and auto-flush behaviour. Add memory safety guarantees per tier. | |
| `docs/architecture/ARCHITECTURE.md` Section 6.6 | **Update** error handling section to note that `process_item` catches per-item exceptions within the framework loop. | |
| `docs/architecture/PROJECT_TREE.md` | **Add** `blocks/code/lazy_list.py` entry. | |

### Summary of all addendum decisions

| # | Decision | Memory safety | Framework enforced? |
|---|---|---|---|
| 1 | `unpack()` returns DataObject, not ViewProxy | Block author controls when data loads | Yes — unpack never triggers data load |
| 2 | IOBlock creates lazy StorageReferences, not eager reads | Collection construction is O(N × ref_size), not O(N × data_size) | Yes — IOBlock default behaviour |
| 3 | `parallel_map` memory is block author's responsibility | Warning in docs and docstring | No — author chooses max_workers |
| 4 | CodeBlock uses LazyList for length > 1 | Iteration loads 1 item at a time | Yes — unless user calls `list()` or `np.array()` |
| 5 | Three-tier auto-flush: process_item / map_items / pack | Tier 1-2: constant memory. Tier 3: pack() safety net | Yes (Tier 1-2 fully enforced, Tier 3 partial) |
| 6 | Collection type safety: explicit item_type required, port checks validate item_type | Prevents type-safe bypass via empty Collection or unchecked item_type | Yes — enforced at construction and port validation |

### Addendum 6: Collection type safety fix (P1 audit finding)

**Problem**: The original ADR-020 Collection specification has two type safety gaps:

1. **Empty Collection defaults to DataObject**: `Collection([], item_type=None)` sets `item_type = DataObject`. A port declaring `accepted_types=[Image]` accepts this empty `Collection[DataObject]` because `DataObject` is the universal base. Type checking is silently bypassed.

2. **`port_accepts_type(Collection)` returns True unconditionally**: The ADR-020 port adaptation stated `if data_type is Collection: return True`. This means any Collection passes any port, regardless of item_type. A `Collection[DataFrame]` would pass a port that only accepts `Image`.

**Fix 1: Empty Collection requires explicit item_type**

```python
class Collection:
    def __init__(self, items=None, item_type=None):
        items = items or []
        if items and item_type is None:
            item_type = type(items[0])       # infer from first item — OK
        if not items and item_type is None:
            raise TypeError("item_type is required for empty Collection")  # ← NEW
        # ... rest unchanged
```

Valid: `Collection([], item_type=Image)`, `Collection([img1, img2])` (infers Image).
Invalid: `Collection([])` → `TypeError`.

**Fix 2: Port type checking must validate item_type**

```python
def port_accepts_type(port, data_type):
    if not port.accepted_types:
        return True                          # port accepts anything
    if isinstance(data_type, Collection):    # ← CHECK ITEM_TYPE
        return any(issubclass(data_type.item_type, t) for t in port.accepted_types)
    return any(issubclass(data_type, t) for t in port.accepted_types)

def validate_connection(source_port, target_port):
    # Source produces Collection[X] → check X against target.accepted_types
    # Never return True just because it's a Collection
```

**Impact on ADR-020 main body**:

The following text in ADR-020 Decision section must be corrected:

| Original | Corrected |
|---|---|
| `self.item_type: type = item_type or DataObject` | `if not items and item_type is None: raise TypeError(...)` |
| `port_accepts_type: if data_type is Collection: return True` | `if isinstance(data_type, Collection): check item_type against accepted_types` |

**Impact on other files**:

| File | Change |
|---|---|
| `src/scieasy/core/types/collection.py` | Raise TypeError on empty Collection without item_type |
| `src/scieasy/blocks/base/ports.py` | `port_accepts_type` and `validate_connection` check Collection.item_type |
| `tests/core/test_collection.py` | Test: `Collection([])` raises TypeError; `Collection([], item_type=Image)` OK |
| `tests/blocks/test_ports.py` | Test: `Collection[DataFrame]` rejected by `accepted_types=[Image]` port |

---

## ADR-021: MergeCollection and Collection operation blocks

**Status**: proposed
**Date**: 2026-04-03

### Context

With the Collection-based data transport model (ADR-020), users sometimes need to combine multiple Collections into one before passing them to a block. For example, two batches of LC-MS data processed through different pipelines must be merged into a single Collection for ElMAVEN to open in one session.

### Decision

Provide a set of built-in Collection operation blocks as framework infrastructure. These blocks operate purely at the Collection level — they do not inspect or transform the contained DataObjects.

| Block | Purpose | Input ports | Output ports |
|---|---|---|---|
| `MergeCollection` | Concatenate 2 same-typed Collections into 1 | `a: [DataObject]`, `b: [DataObject]` | `merged: [DataObject]` |
| `SplitCollection` | Split a Collection by index or condition | `data: [DataObject]` + config (split point / predicate) | `left: [DataObject]`, `right: [DataObject]` |
| `FilterCollection` | Keep items matching a metadata predicate | `data: [DataObject]` + config (predicate) | `filtered: [DataObject]` |
| `SliceCollection` | Extract a contiguous sub-range `[start:end]` | `data: [DataObject]` + config (start, end) | `sliced: [DataObject]` |

These blocks preserve the static port contract — no dynamic ports. Users who need to merge 3+ Collections chain two `MergeCollection` blocks.

### Alternatives considered

- **Dynamic input ports on downstream blocks**: breaks the static port contract principle, requires frontend support for runtime port addition, and forces every block that might receive multiple collections to implement merge logic. Rejected.

### Consequences

- Collection operations are composable utility blocks, not special engine features.
- Users who need multi-source data merge add a `MergeCollection` node to the canvas — one extra node, zero framework complexity.
- Future Collection operations (sort, deduplicate, sample) can be added as new blocks without engine changes.

---

## ADR-022: OS-level memory monitoring replaces estimated memory budget

**Status**: proposed
**Date**: 2026-04-04

### Context

The original `ResourceManager` used a pre-allocated memory budget model: each block declared `estimated_memory_gb` in its `ResourceRequest`, and the manager maintained a ledger of allocated vs. available memory. This model worked for the per-item batch architecture where the engine controlled concurrency and each subprocess had a predictable memory footprint.

ADR-020 (Collection-based transport) fundamentally changed the memory model:

1. **Collection size is unknown at class definition time.** A `CellposeSegment` block might process 10 images or 10,000 images. `estimated_memory_gb` as a static ClassVar cannot represent this.

2. **Block-internal memory behaviour is variable.** The same block class can have vastly different peak memory depending on which Tier it uses: `process_item()` + auto_flush = O(1 item), `parallel_map(max_workers=4)` = O(4 items), manual loop without flush = O(N items).

3. **Multiple independent memory mechanisms now exist.** `_auto_flush` (ADR-020 Addendum 5), `LazyList` (Addendum 4), and `parallel_map` max_workers all control memory at the block level, but `ResourceManager` knows nothing about them. The manager's estimate-based budget is disconnected from actual runtime behaviour.

4. **Static estimates are either too conservative or too aggressive.** A block declaring `estimated_memory_gb=8.0` blocks concurrent execution of other blocks even when auto_flush keeps actual usage at 2GB. A block declaring `estimated_memory_gb=2.0` may actually use 50GB with a large Collection and no flush.

### Decision

Replace the estimated memory budget model with a three-layer defence based on **OS-level monitoring** for system memory, while retaining **declaration-based counting** for discrete resources (GPU, CPU).

#### Layer 1: ResourceManager — dispatch gating

ResourceManager checks actual system memory usage (via `psutil`) before dispatching each block. If usage exceeds the high watermark, dispatch is paused until running blocks complete and memory drops.

```python
@dataclass
class ResourceRequest:
    """Declared by each block: what discrete resources does it need?"""
    requires_gpu: bool = False
    gpu_memory_gb: float = 0.0      # GPU VRAM — still declared (not monitorable via psutil)
    cpu_cores: int = 1
    # estimated_memory_gb: REMOVED — replaced by OS monitoring

@dataclass
class ResourceSnapshot:
    """Read-only view of currently available resources."""
    available_gpu_slots: int = 0
    available_cpu_workers: int = 4
    system_memory_percent: float = 0.0   # actual OS memory usage (0.0–1.0)

class ResourceManager:
    """Dispatch gating based on discrete resources + OS memory monitoring."""

    def __init__(
        self,
        gpu_slots: int = 0,
        cpu_workers: int = 4,
        memory_high_watermark: float = 0.80,    # pause dispatch above 80%
        memory_critical: float = 0.95,           # never dispatch above 95%
    ) -> None: ...

    async def can_dispatch(self, request: ResourceRequest) -> bool:
        """Check if resources are available for dispatching a block.

        GPU: discrete slot counting (declaration-based, predictive).
        CPU: discrete core counting (declaration-based, predictive).
        Memory: OS-level check (monitoring-based, reactive).
        """
        # GPU check
        if request.requires_gpu and self._gpu_in_use >= self.gpu_slots:
            return False

        # CPU check
        if self._cpu_in_use + request.cpu_cores > self.max_cpu_workers:
            return False

        # Memory check — actual OS usage, not estimates
        import psutil
        mem_percent = psutil.virtual_memory().percent / 100.0
        if mem_percent > self.memory_high_watermark:
            return False

        return True

    def release(self, request: ResourceRequest) -> None:
        """Release discrete resources (GPU slots, CPU cores).
        Memory is not 'released' — it drops naturally when subprocess exits."""
        self._gpu_in_use -= (1 if request.requires_gpu else 0)
        self._cpu_in_use -= request.cpu_cores

    @property
    def available(self) -> ResourceSnapshot:
        import psutil
        return ResourceSnapshot(
            available_gpu_slots=self.gpu_slots - self._gpu_in_use,
            available_cpu_workers=self.max_cpu_workers - self._cpu_in_use,
            system_memory_percent=psutil.virtual_memory().percent / 100.0,
        )
```

#### Layer 2: Block-internal memory control (unchanged)

`_auto_flush`, `LazyList`, `parallel_map(max_workers)` control per-block memory at runtime. These mechanisms are invisible to ResourceManager and operate independently.

#### Layer 3: OS OOM killer + ProcessMonitor (unchanged)

If a subprocess exceeds available memory despite Layers 1 and 2, the OS kills it. ProcessMonitor detects the death, emits `PROCESS_EXITED`, and the scheduler marks the block as `ERROR`. The engine process is unaffected (ADR-017).

#### Why GPU memory is still declared

System RAM is monitorable via `psutil.virtual_memory()`. GPU VRAM is not reliably monitorable cross-platform:
- `nvidia-smi` / `pynvml` works for NVIDIA GPUs but requires CUDA toolkit
- AMD GPUs have different tools
- Apple Silicon unified memory complicates the model

GPU resource management retains the declaration-based model: `requires_gpu: bool` for slot counting and `gpu_memory_gb: float` for VRAM estimation. This is acceptable because GPU concurrency is low (typically 1-2 slots) and block authors have good estimates for VRAM usage.

### Updates to previous ADRs

| ADR | Section | Update |
|---|---|---|
| **ADR-010** (superseded) | References "memory budget" | No change — already superseded by ADR-020 |
| **ADR-017** | `ProcessHandle.resource_request: ResourceRequest` | **ResourceRequest still exists** but without `estimated_memory_gb`. ProcessHandle records GPU/CPU allocation for release on exit. No structural change. |
| **ADR-018** | EventBus auto-release on BLOCK_DONE/ERROR/CANCELLED | `release()` still called — releases GPU slots and CPU cores. Memory is not "released" (OS handles it when subprocess exits). **Semantic change**: release is for discrete resources only. |
| **ADR-019** | `spawn_block_process(resource_request=...)` | Parameter still accepted. ResourceRequest fields reduced but structure unchanged. |
| **ADR-020 Addendum 3** | `parallel_map` memory warning | **Unchanged** — block author manages internal memory. ResourceManager's OS monitoring provides system-level back-pressure. |
| **ADR-020 Addendum 5** | Three-tier auto-flush | **Unchanged** — auto_flush is Layer 2, independent of ResourceManager's Layer 1. |

### Alternatives considered

- **Keep static `estimated_memory_gb` with Collection size multiplier (Direction B')**: block declares `estimated_memory_per_item_gb`, framework multiplies by `min(collection_size, max_workers)`. Better than static estimate but still requires block author to predict per-item memory. Rejected because: per-item memory varies by data size (a 100×100 image vs a 10000×10000 image), and the framework still can't verify the estimate at runtime.

- **Dynamic `estimate_memory_gb(inputs)` method (Direction B)**: block implements a method that inspects Collection size and returns an estimate. Most accurate prediction but highest block-author burden. Most authors won't implement it correctly. Rejected as default; could be offered as an optional override for advanced blocks.

- **Remove memory management entirely from ResourceManager (Direction C)**: only manage GPU/CPU. Simple but loses protection against "launch 10 heavy blocks concurrently and OOM the system." Rejected — the OS monitoring approach provides this protection with zero block-author burden.

- **ResourceManager monitors per-subprocess memory via `psutil.Process(pid).memory_info()`**: enables per-block memory tracking and kill-if-over-limit. More granular than system-level watermark but adds complexity (continuous polling per process, deciding limits). Considered as a future enhancement, not v1.

### Consequences

- **Block authors no longer declare memory estimates.** `ResourceRequest` has 3 fields instead of 4. One less thing to get wrong.
- **ResourceManager is reactive, not predictive** for memory. It observes actual system state rather than trusting declarations. This is more accurate but less precise — it cannot prevent the first heavy block from launching; it can only prevent the second one if the first has already driven memory usage high.
- **New dependency: `psutil`.** Cross-platform (Windows/macOS/Linux), mature (5B+ downloads), lightweight, no compile dependencies. Already useful for ADR-019 (`ProcessHandle.is_alive()` can use `psutil.pid_exists()`). Single dependency serves both resource monitoring and process lifecycle.
- **The `release()` method semantics change.** It now only releases discrete resources (GPU, CPU). Memory is not explicitly released — it drops when the subprocess exits and the OS reclaims pages. EventBus auto-release (ADR-018) still calls `release()` for GPU/CPU cleanup.
- **Watermark thresholds are user-configurable.** `memory_high_watermark=0.80` and `memory_critical=0.95` are defaults. Users on high-memory machines (128GB+) can set higher thresholds; users on constrained machines can set lower ones.

### Detailed impact scope

#### Code files

| File | Change |
|---|---|
| `src/scieasy/engine/resources.py` | **Rewrite**: remove `estimated_memory_gb` from `ResourceRequest`, remove `available_memory_gb` from `ResourceSnapshot` (replace with `system_memory_percent`), remove `memory_budget_gb` from `ResourceManager.__init__`, add `memory_high_watermark`/`memory_critical` params, rewrite `acquire()`→`can_dispatch()` with `psutil.virtual_memory()`, simplify `release()` to GPU/CPU only. |
| `pyproject.toml` | **Add** `psutil` to `[project.dependencies]` |

#### Documentation files

| File | Change |
|---|---|
| `docs/architecture/ARCHITECTURE.md` Section 6.4 | **Rewrite** ResourceRequest/ResourceManager code blocks and description. Remove `estimated_memory_gb`, add three-layer defence explanation, add `psutil` monitoring. Update CellposeSegment example. |
| `docs/architecture/ARCHITECTURE.md` Section 11 | **Add** `psutil` to technology stack table: "System monitoring: `psutil` — cross-platform memory/CPU/process info for ResourceManager and ProcessHandle" |
| `docs/architecture/PROJECT_TREE.md` | **Update** `engine/resources.py` annotation: replace "memory budget" with "OS memory monitoring via psutil" |
| `docs/roadmap/ROADMAP.md` Phase 5.3 | **Update**: "Implement `ResourceManager.can_dispatch()` with psutil memory watermark + GPU/CPU slot counting" |
| `docs/roadmap/ROADMAP_v0.1.md` | **Update** ResourceRequest description |
| `docs/testing/phase-5-ai-tests.md` | **Rewrite** `test_memory_budget_enforcement()` → `test_memory_watermark_enforcement()`: mock `psutil.virtual_memory()` at different usage levels, verify dispatch gating |
| `docs/testing/phase-5-human-tests.md` | **Update** ResourceManager test: remove `memory_mb` from ResourceRequest, add watermark check test |

---

## ADR-023: Frontend layout redesign — three-column canvas with inline config, data preview, and "Start from here" execution

**Status**: proposed
**Date**: 2026-04-04

### Context

The original frontend specification (ARCHITECTURE.md Section 9 and ADR-014) defined a basic three-panel layout: Block Palette | ReactFlow Canvas | Config Panel. This layout was sufficient as an initial sketch but lacks several capabilities required by real scientific workflow editing:

1. **No data preview.** Users need to inspect block outputs (DataFrames, images, spectra) during and after execution without leaving the editor. The original design requires a separate step to view data.

2. **Config panel placement conflict.** The original design uses the right panel for block configuration. But data preview is more important during execution, and configuration is more important during editing. These two use cases compete for the same screen space.

3. **No structured bottom panel.** There is no designated space for logs, AI chat, lineage, or detailed config editing. Users have no visibility into execution progress or AI-assisted authoring.

4. **Block nodes are too sparse.** The original block node shows only name + ports + state badge. Users must click and switch panels to see or change parameters. This breaks the "see everything at a glance" principle that makes visual editors productive.

5. **No port type differentiation.** All ports look identical. Users cannot visually distinguish whether a connection carries an Image, a DataFrame, or a Spectrum without clicking to inspect.

6. **No partial re-execution.** The original architecture supports pause/resume (ADR-018) and checkpoint (Phase 5.4), but there is no mechanism for a user to say "re-run from this block" — a critical workflow for iterative scientific analysis where users adjust parameters on one block and want to re-run only the downstream portion.

### Decision

Redesign the frontend layout with the following structure, block node design, port colour system, data preview panel, and "Start from here" execution mechanism.

---

#### 1. Layout: Three-column with toolbar and bottom panel

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Toolbar                                                                      │
├───────────┬──────────────────────────────────────────────────┬──────────────┤
│           │              ReactFlow Canvas                    │              │
│  Block    │              (with minimap inside)               │    Data      │
│  Palette  │                                                  │   Preview    │
│           │                                                  │    Panel     │
│           │                                                  │              │
│           │                                                  │              │
│           │                                                  │              │
│           ├──────────────────────────────────────────────────┤              │
│           │ Bottom Panel (browser-style tabs)                │              │
│           │                                                  │              │
│           │                                                  │              │
└───────────┴──────────────────────────────────────────────────┴──────────────┘
```

**Structural rules:**

| Element | Behaviour |
|---------|-----------|
| Block Palette (left column) | Full height from toolbar to window bottom. Does not share vertical space with bottom panel. |
| ReactFlow Canvas (centre top) | Fills remaining horizontal space between palette and preview panel. Contains ReactFlow minimap (configurable position, default bottom-right of canvas viewport). |
| Bottom Panel (centre bottom) | Same width as canvas. Height adjustable via drag handle. Can be collapsed. |
| Data Preview Panel (right column) | Full height from toolbar to window bottom. Does not share vertical space with bottom panel. |
| Toolbar (top) | Full width. Fixed position. |

**All three columns are resizable via drag handles:**

| Panel | Default width/height | Min | Max | Drag direction |
|-------|---------------------|-----|-----|----------------|
| Block Palette | 220px | 160px | 400px | Horizontal (right edge) |
| Data Preview Panel | 320px | 240px | 600px | Horizontal (left edge) |
| Bottom Panel | 200px | 100px | 50% of canvas height | Vertical (top edge) |
| Canvas | Fills remaining space | — | — | — |

**Collapse behaviour:**

| Panel | Collapse trigger | Collapsed state |
|-------|-----------------|-----------------|
| Block Palette | Toggle button or `Ctrl+B` | Icon-only mode (~48px) showing category icons |
| Data Preview | Toggle button or `Ctrl+D` | Hidden (0px). Auto-shows when a block with output is selected. |
| Bottom Panel | Toggle button or `Ctrl+J` | Collapsed to tab bar only (~32px). Auto-expands when execution starts. |

---

#### 2. Toolbar

Fixed horizontal bar at the top. Grouped by function:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [📂 Import][💾 Save][📤 Export] │ [▶ Run][⏸ Pause][■ Stop][↻ Reset] │ [🗑 Delete][🔄 Reload Blocks] │
└──────────────────────────────────────────────────────────────────────────────┘
  File operations               Execution controls                 Edit operations
```

| Button | Action | Keyboard shortcut |
|--------|--------|-------------------|
| Import | Open file dialog → load workflow YAML | `Ctrl+O` |
| Save | Save current workflow to YAML | `Ctrl+S` |
| Export | Export workflow as YAML / JSON / PNG | `Ctrl+Shift+S` |
| Run | Execute workflow from beginning | `Ctrl+Enter` |
| Pause | Pause execution after current blocks complete (ADR-018) | — |
| Stop | Cancel entire workflow (ADR-018 `CANCEL_WORKFLOW_REQUEST`) | `Ctrl+.` |
| Reset | Clear all block states and outputs, return to IDLE | — |
| Delete | Delete selected block(s) or edge(s) | `Delete` or `Backspace` |
| Reload Blocks | Re-scan block registry and refresh palette | — |

**Additional keyboard shortcuts:**

| Shortcut | Action |
|----------|--------|
| `Delete` / `Backspace` | Delete selected block(s) or edge(s) |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` / `Ctrl+Shift+Z` | Redo |
| `Ctrl+A` | Select all nodes and edges |
| `Escape` | Deselect all |
| `Space` (hold) | Pan canvas |
| `Ctrl+Mouse wheel` | Zoom canvas |

---

#### 3. Block Palette (left column)

Full-height left sidebar with searchable, categorised block list.

```
┌───────────┐
│ [🔍 Search]│
├───────────┤
│ ▸ IO       │  Categories match block system:
│ ▸ Process  │    IO, Process, Code, App, AI, SubWorkflow
│ ▸ Code     │
│ ▸ App      │  Expand category → show individual blocks
│ ▸ AI       │  Drag block from palette onto canvas
│ ▸ SubWF    │
├───────────┤
│ ▸ Custom   │  User/project-local blocks (~/.scieasy/blocks/, project/blocks/)
└───────────┘
```

- Blocks are fetched from `GET /api/blocks/` on mount and after "Reload Blocks."
- Search filters by block name, category, and description.
- Drag-and-drop: dragging a block onto the canvas creates a new node with default config.

---

#### 4. Block node design

Each block on the canvas renders as a ReactFlow custom node with header, inline config, ports, and status footer.

```
┌────────────────────────────────────┐
│ 📦 Cellpose Segmentation   [▶][↻] │  ← Header
├────────────────────────────────────┤
│  Model:    [▼ cyto2       ]        │  ← Inline config (top N params)
│  Diameter: [  30.0        ]        │
│  Channels: [▼ [0,1]       ]        │
│                                    │
◯ images                     masks ◉ │  ← Ports (type-coloured)
◯ config                   errors  ◉ │
├────────────────────────────────────┤
│ ✅ Done · 3.2s · 47 items          │  ← Footer: state badge
└────────────────────────────────────┘
```

**Header elements:**

| Element | Description |
|---------|-------------|
| Icon | Block category icon (IO, Process, Code, App, AI, SubWF) |
| Name | Block display name (from block metadata or user-assigned) |
| `[▶]` button | Run this single block only (uses cached upstream outputs if available) |
| `[↻]` button | "Start from here" — re-run from this block through all downstream (see Section 8 below) |

**Inline config (hybrid approach):**

- Each block's JSON Schema may declare `"ui_priority"` on parameters. The block node displays the **top 3 parameters** by `ui_priority` (default: first 3 in schema order).
- Parameters are rendered as compact form controls (dropdowns, number inputs, text fields) directly in the node body.
- Editing an inline parameter updates the block config immediately (no save button).
- Clicking the block (single click) switches the bottom panel to the `[📋 Config]` tab, which shows the **complete parameter form** with all parameters, descriptions, validation, and advanced options.

**Port rendering:**

- Input ports on the **left** edge of the node. Output ports on the **right** edge.
- Each port displays its name and a coloured handle (circle). Colour is determined by the port's data type (see Section 5).
- Hovering over a port shows a tooltip with: type name, constraint (if any), and connection status.
- Drawing a connection from an output port to an input port triggers backend validation (`POST /api/blocks/validate-connection`). Invalid connections are rejected with a visual indicator (red flash, shake animation).

**State badge (footer):**

| State | Display | Colour |
|-------|---------|--------|
| IDLE | `○ Idle` | Grey `#9CA3AF` |
| READY | `◉ Ready` | Blue `#3B82F6` |
| RUNNING | `⟳ Running · {elapsed}` | Blue `#3B82F6` with spinner animation |
| PAUSED | `⏸ Paused` | Amber `#F59E0B` |
| DONE | `✅ Done · {elapsed} · {item_count} items` | Green `#22C55E` |
| ERROR | `❌ Error: {short_message}` | Red `#EF4444`. Clickable → expands traceback in bottom panel. |
| CANCELLED | `⊘ Cancelled` | Orange `#F97316` |
| SKIPPED | `⊘ Skipped: {reason}` | Grey `#9CA3AF` italic |

**Node sizing:**

- Width: fixed at 280px (fits 3 inline params comfortably).
- Height: dynamic based on number of inline params and ports. Minimum height for a zero-param, single-port block: ~80px.
- Nodes are not user-resizable (keeps canvas layout clean).

---

#### 5. Port type colour system

Base data types receive a pure solid colour. Sub-types inherit the parent colour by default. Users may optionally define a `ring_color` on custom sub-types for visual distinction.

**Base type colour table:**

| Base Type | Colour Name | Hex | Port Shape |
|-----------|-------------|-----|------------|
| `Array` | Blue | `#3B82F6` | Solid circle |
| `Series` | Green | `#22C55E` | Solid circle |
| `DataFrame` | Orange | `#F97316` | Solid circle |
| `Text` | Purple | `#A855F7` | Solid circle |
| `Artifact` | Grey | `#6B7280` | Solid circle |
| `CompositeData` | Red | `#EF4444` | Solid circle |
| `DataObject` (fallback) | White/Light Grey | `#E5E7EB` | Solid circle |

**Collection modifier:**

When a port type is `Collection[T]`, the port handle renders as a **double ring** (concentric circles) using `T`'s colour. This provides instant visual distinction between single-item and collection ports.

```
Single DataObject port:  ◉  (solid filled circle)
Collection port:         ◎  (double ring)
```

**Sub-type ring colour (user-extensible):**

Sub-types (e.g. `Image(Array)`, `RamanSpectrum(Series)`) inherit the parent's solid colour by default. Users may optionally declare a ring colour:

```python
class MALDIImage(Image):
    _ui_ring_color: ClassVar[str] = "#FFD700"  # gold ring around blue fill
```

If `_ui_ring_color` is defined, the port renders as the parent's solid colour with a coloured outer ring. If not defined, the port is indistinguishable from the parent type (acceptable — tooltip always shows the precise type).

**Edge colour:**

- Edges (connections) inherit the colour of the **source port's** base type.
- Collection edges render as **dashed lines** to distinguish from single-item edges.
- Invalid or disconnected edges render in red.

**Frontend implementation:**

The colour map is stored in a `typeColorMap.ts` configuration file:

```typescript
export const TYPE_COLORS: Record<string, string> = {
  Array: "#3B82F6",
  Series: "#22C55E",
  DataFrame: "#F97316",
  Text: "#A855F7",
  Artifact: "#6B7280",
  CompositeData: "#EF4444",
  DataObject: "#E5E7EB",
};
```

At runtime, the frontend resolves a port's colour by walking the type hierarchy (returned by `GET /api/blocks/{type}/schema`) until it finds a match in `TYPE_COLORS`. Sub-type ring colours are included in the block schema response as an optional `ui_ring_color` field.

---

#### 6. Data Preview Panel (right column)

Full-height right sidebar that displays the output of the currently selected block. This replaces the original "Config Panel" in the right column position.

**Panel structure:**

```
┌─────────────────────────────┐
│ Preview: {block_name}       │  ← Selected block name
├─────────────────────────────┤
│ Port: [▼ {port_name}    ]  │  ← Dropdown to select output port (if multiple)
├─────────────────────────────┤
│ Collection[Image] · 47 items│  ← Type badge + item count
├──┬──┬──┬──┬──┬──────────────┤
│ 1│ 2│ 3│ 4│ 5│  ... ▶       │  ← Collection item tabs
├──┴──┴──┴──┴──┴──────────────┤
│                             │
│   ┌─────────────────────┐   │
│   │                     │   │
│   │   Type-specific     │   │  ← Renderer area
│   │   renderer          │   │
│   │                     │   │
│   └─────────────────────┘   │
│                             │
├─────────────────────────────┤
│ Metadata:                   │  ← Item metadata
│   shape: (1024, 1024)       │
│   dtype: uint16             │
│   axes: ['y', 'x']         │
│   storage: zarr://data/...  │
└─────────────────────────────┘
```

**Renderer selection by type:**

| DataObject Type | Renderer | Description |
|----------------|----------|-------------|
| `DataFrame`, `PeakTable` | Table viewer | Paginated table showing first 100 rows. Column sorting. Search. |
| `Array`, `Image` | Image viewer | Zoomable, pannable. Multi-channel images: channel selector dropdown. Brightness/contrast controls. |
| `MSImage` | Image + spectrum | Click a pixel → display that pixel's mass spectrum in an overlay Plotly chart. |
| `Series`, `Spectrum` | Plotly line chart | x = index, y = value. Zoom, pan, hover tooltips. |
| `Text` | Monaco (read-only) | Syntax highlighting based on format (JSON, markdown, plain). |
| `Artifact` | File preview | Images and PDFs render inline. Other types display metadata + download link. |
| `CompositeData` | Slot list | Expandable list of slots. Each slot renders with its own type-appropriate renderer. |

**Collection tab behaviour:**

| Collection size | Tab rendering |
|-----------------|---------------|
| 1 item | No tab bar. Render directly. |
| 2–20 items | Horizontal tab bar: `[1] [2] [3] ... [N]`. Tab labels show item metadata (e.g. filename) if available, otherwise sequential numbers. |
| 21–100 items | Paginated tab bar with page navigation: `[◀ Prev] [1] [2] ... [10] [Next ▶]` showing 10 tabs per page. |
| >100 items | Paginated + jump-to input field: `Page 3 of 47 [Go to: ___]`. |

**Lazy loading:** Preview data is fetched on demand when a tab is clicked (`GET /api/data/{ref}/preview`). Previously fetched previews are cached in Zustand store. No eager loading of all Collection items.

**Empty states:**

| Scenario | Display |
|----------|---------|
| No block selected | "Select a block to preview its output" |
| Block selected but not yet executed | "Run the workflow to see output" |
| Block in ERROR state | Error message with traceback (scrollable) |
| Block output is empty Collection | "Empty collection (0 items)" |

---

#### 7. Bottom Panel (browser-style tabs)

A tabbed panel below the canvas, same width as the canvas area. Functions like a browser tab bar — tabs can be reordered, and each tab has independent scrollable content.

**Tab definitions:**

| Tab | Icon | Content | Phase |
|-----|------|---------|-------|
| **AI Chat** | 💬 | Conversational AI assistant. Users ask questions, request block generation, workflow suggestions. AI responses can include "Apply" buttons that modify the canvas. | Phase 8 MVP |
| **Config** | 📋 | Complete parameter form for the selected block (JSON Schema → auto-generated form). Appears automatically when a block is clicked. Includes all parameters, descriptions, validation hints, and reset-to-default. | Phase 8 MVP |
| **Logs** | 📜 | Real-time execution log stream (via SSE). Timestamps, block ID filter dropdown, severity filter (info/warn/error). Auto-scrolls during execution. | Phase 8 MVP |
| **Lineage** | 🔗 | Provenance chain for the selected block's output. Shows upstream blocks and data transformations as a mini-graph or list. | Phase 8.5 |
| **Jobs** | 📊 | List of current and historical workflow executions. Status, duration, block count, errors. Click to restore a previous run's checkpoint. | Phase 8.5 |
| **Problems** | ⚠️ | Validation errors and warnings. Type mismatches, dangling ports, cycle detection results. Updated live as the user edits the workflow. | Phase 8.5 |

**Tab interaction rules:**

- Clicking a block auto-switches to the **Config** tab (unless the user has manually pinned another tab).
- Starting execution auto-switches to the **Logs** tab and auto-expands the bottom panel if collapsed.
- Clicking an ERROR state badge auto-switches to **Logs** tab filtered to that block.
- AI Chat tab maintains conversation history across block selections.

---

#### 8. "Start from here" execution mechanism

A new execution mode that enables iterative parameter tuning — the core workflow for scientific data analysis.

**User story:** A user has a 5-block pipeline. Blocks A → B → C → D → E have all completed. The user changes a parameter on block C. They want to re-run C → D → E using the already-computed output of B, without re-running A and B.

**UI interaction:**

1. Each block node has a `[↻]` button in its header (visible when the block or any upstream block has completed at least once — i.e., cached outputs exist).

2. Clicking `[↻]` on block C triggers the following:

```
User clicks [↻] on Block C
        │
        ▼
Frontend sends: POST /api/workflows/{id}/execute-from
                Body: { "block_id": "C" }
        │
        ▼
Backend validates:
  - All predecessors of C have cached outputs (in checkpoint intermediate_refs)?
    ├── Yes → proceed
    └── No → return 409 Conflict with list of missing predecessors
        │
        ▼
Backend executes:
  1. Load predecessor outputs from checkpoint/intermediate_refs
  2. Set predecessors of C to state "done" with cached outputs
  3. Reset C and all downstream blocks (D, E) to state "idle"
  4. Clear cached outputs for C, D, E
  5. Begin execution from C (normal DAGScheduler.execute() but with pre-loaded state)
        │
        ▼
Frontend receives via WebSocket:
  - C: IDLE → RUNNING → DONE
  - D: IDLE → RUNNING → DONE
  - E: IDLE → RUNNING → DONE
  - A, B: remain DONE (unchanged)
```

**Backend API:**

```
POST /api/workflows/{workflow_id}/execute-from

Request body:
{
  "block_id": "string"     // The block to start execution from
}

Success response (200):
{
  "execution_started": true,
  "start_block": "C",
  "reset_blocks": ["C", "D", "E"],       // Blocks whose state was reset to idle
  "preserved_blocks": ["A", "B"],          // Blocks whose state remains done
  "missing_predecessors": []               // Empty on success
}

Conflict response (409):
{
  "execution_started": false,
  "start_block": "C",
  "missing_predecessors": ["B"],           // Predecessors without cached output
  "message": "Upstream block 'B' has no cached output. Run the full workflow first."
}
```

**DAGScheduler changes:**

A new method `execute_from(block_id: str)` is added to `DAGScheduler`:

```python
async def execute_from(self, block_id: str) -> None:
    """Execute workflow starting from a specific block.

    Prerequisites:
    - All predecessors of block_id must have cached outputs in
      the checkpoint's intermediate_refs.

    Behaviour:
    1. Validate all predecessors have cached outputs.
    2. Set all predecessors to "done" state with their cached outputs.
    3. Reset block_id and all its downstream blocks to "idle".
    4. Clear cached outputs for reset blocks.
    5. Call execute() — normal event-driven dispatch picks up
       from the first ready block (which will be block_id).

    Raises:
        ValueError: If any predecessor lacks cached output.
    """
```

**Interaction with existing mechanisms:**

| Mechanism | Relationship |
|-----------|-------------|
| **Checkpoint (ADR-018)** | "Start from here" reads `intermediate_refs` from the last checkpoint. Checkpoints must store per-block output references. |
| **Pause/Resume** | Resume continues from the pause point. "Start from here" goes back to an arbitrary completed block. They are complementary, not competing. |
| **Cancel + SKIPPED (ADR-018)** | If a user cancels block C and blocks D, E become SKIPPED, the user can fix the issue, then use "Start from here" on C to re-run C → D → E. The SKIPPED blocks are reset to IDLE. |
| **_auto_flush (ADR-020)** | auto_flush writes intermediate outputs to storage. These persisted outputs are what "Start from here" loads as predecessor inputs. Without auto_flush or explicit storage, cached outputs would not exist. |

**Edge cases:**

| Scenario | Behaviour |
|----------|-----------|
| "Start from here" on a root block (no predecessors) | Equivalent to a full `execute()` — all blocks reset to IDLE. |
| "Start from here" on the last block | Only that block re-runs. No downstream to reset. |
| Predecessor output was manually deleted from storage | Return 409 with `missing_predecessors`. User must re-run from an earlier point. |
| Workflow has been modified since last execution (new blocks/edges) | Validate the new DAG topology. If new predecessors of block_id exist that have no output, return 409. |
| Concurrent execution already running | Return 409 "Workflow is already executing." |

---

#### 9. Minimap

ReactFlow's built-in `<MiniMap>` component, rendered **inside** the canvas viewport.

- Position: bottom-right corner of the canvas (ReactFlow default).
- Shows all nodes as coloured rectangles (colour = state badge colour).
- Click on minimap to pan the canvas.
- Viewport rectangle shows current visible area.
- Can be toggled via `Ctrl+M`.

---

#### 10. State management (Zustand)

The frontend uses a single Zustand store with slices:

| Slice | Responsibility |
|-------|----------------|
| `workflowSlice` | Nodes, edges, workflow metadata (the source-of-truth mirror of backend state) |
| `executionSlice` | Per-block execution state, timing, output refs (updated via WebSocket) |
| `uiSlice` | Panel widths, collapsed states, selected block ID, active bottom tab |
| `previewSlice` | Cached preview data (keyed by StorageReference), loading states |
| `paletteSlice` | Available blocks from registry, search filter state |
| `chatSlice` | AI chat message history |

**Data flow:**

```
User edits workflow → Zustand workflowSlice → debounced PUT /api/workflows/{id}
                                                              │
WebSocket events ──────────────→ Zustand executionSlice ──→ ReactFlow node state badges
                                                              │
User clicks block ──→ Zustand uiSlice (selectedBlockId) ──→ Preview panel fetches data
                                          │                    Bottom panel shows Config tab
                                          ▼
                                 GET /api/data/{ref}/preview → Zustand previewSlice
```

**Key principle**: The backend is the source of truth for workflow definition and execution state. The frontend is a read-mostly mirror that sends mutations via REST and receives state updates via WebSocket. The frontend never computes execution state locally.

---

### Alternatives considered

**1. Config panel in the right column (original design)**

The original ARCHITECTURE.md Section 9 placed block configuration in the right panel. This was rejected because:
- Data preview during execution is more valuable than configuration editing.
- Configuration can be split: top-N params inline in the node, full form in the bottom panel.
- Right panel width is better used for tables, images, and charts that need horizontal space.

**2. Floating/modal config panel**

Show block config as a floating dialog or modal when double-clicking a block. Rejected because:
- Modals block interaction with the canvas.
- Floating panels clutter the workspace.
- Bottom panel tabs provide a non-blocking, always-accessible location.

**3. No inline config (all config in bottom panel)**

Keep block nodes minimal (name + ports + state only). All config editing in the bottom panel. Rejected because:
- Users must constantly switch between canvas and bottom panel to see what parameters are set.
- The hybrid approach (top-3 inline + full in bottom) provides best of both worlds.

**4. Port colours via shape instead of colour**

Use different shapes (circle, triangle, square, diamond) instead of colours for type distinction. Rejected because:
- ReactFlow handles are circular by default; custom shapes require significant SVG work.
- Colour is more immediately distinguishable than shape at small sizes.
- Colour + shape (double ring for Collection) provides two visual channels.

**5. Re-run via "invalidate and propagate" (no explicit "Start from here" button)**

Automatically detect when a block's config changes and mark it + downstream as "stale." Re-run stale blocks when the user clicks Run. Considered but deferred because:
- Requires tracking config diffs and "staleness" state — added complexity.
- Users may want to change multiple parameters before re-running.
- Explicit "Start from here" gives users precise control over what re-executes.
- Could be added as a future enhancement alongside the explicit button.

### Updates to previous ADRs and architecture documents

| Document | Section | Update |
|----------|---------|--------|
| **ADR-014** | Decision | Add note: "Layout redesigned in ADR-023. Right panel repurposed from Config to Data Preview." |
| **ARCHITECTURE.md** | Section 9 (Layer 6 — Frontend) | **Full rewrite** per this ADR: new layout, block node design, port colours, data preview, bottom panel. |
| **ARCHITECTURE.md** | Section 8.2 (REST endpoints) | **Add** `POST /api/workflows/{id}/execute-from` endpoint. |
| **ARCHITECTURE.md** | Appendix C.2 (ReactFlow layout persistence) | **Update** to reflect new panel structure. |
| **ROADMAP.md** | Phase 8 | **Rewrite** all sub-phases (8.1–8.4) to match new component breakdown. |
| **PROJECT_TREE.md** | `frontend/` | **Add** detailed directory structure for React components. |

### Impact on backend (new requirements)

| Requirement | Component | Description |
|-------------|-----------|-------------|
| `execute-from` endpoint | `routes/workflows.py` | New `POST /api/workflows/{id}/execute-from` REST endpoint. |
| `DAGScheduler.execute_from()` | `engine/scheduler.py` | New method: validate predecessors, load cached outputs, reset downstream, execute. |
| Block schema `ui_priority` | `blocks/base/config.py` or JSON Schema | Block parameter schemas should support an optional `ui_priority` integer for inline display ordering. |
| Block schema `ui_ring_color` | `core/types/base.py` | Optional `_ui_ring_color: ClassVar[str]` on DataObject subclasses, exposed via block schema API. |
| Preview endpoint enhancement | `routes/data.py` | `GET /api/data/{ref}/preview` must return type-appropriate preview data (table rows, image thumbnail, chart data). |

### Consequences

1. **Right panel is now Data Preview, not Config.** This is the largest visual change from the original design. Configuration editing moves to inline params (top-3) + bottom panel Config tab.

2. **Block nodes are larger and richer.** Each node carries inline params, type-coloured ports, and state badges. This means fewer blocks visible at once on the same screen area, but each block is self-documenting. The minimap compensates for reduced viewport.

3. **Bottom panel is a major new UI surface.** It hosts AI Chat, Config, Logs, Lineage, Jobs, and Problems — a significant frontend development effort. MVP should include AI Chat, Config, and Logs only.

4. **"Start from here" requires checkpoint infrastructure.** This feature depends on `intermediate_refs` being populated in checkpoints (Phase 5.4) and `_auto_flush` persisting block outputs (ADR-020). Without these, the button will be disabled with a tooltip explaining why.

5. **Port colour system requires type hierarchy in block schema API.** The `GET /api/blocks/{type}/schema` response must include port type names that the frontend can resolve to base types via the colour map. Sub-type ring colours require an optional field in the schema.

6. **New REST endpoint and scheduler method.** `execute-from` is a moderate backend change that builds naturally on existing checkpoint and scheduler infrastructure.

7. **Lazy preview loading adds API traffic.** Each Collection tab click triggers a preview fetch. Backend must support efficient preview generation (e.g. first 100 rows of a DataFrame, thumbnail of an Image). Caching in Zustand prevents redundant fetches.

### Detailed impact scope

#### New frontend files

| File | Purpose |
|------|---------|
| `frontend/src/App.tsx` | Root layout with resizable three-column + toolbar + bottom panel |
| `frontend/src/components/Toolbar.tsx` | File, execution, and edit operation buttons |
| `frontend/src/components/BlockPalette.tsx` | Left column: searchable categorised block list |
| `frontend/src/components/Canvas.tsx` | ReactFlow wrapper with minimap, zoom, pan |
| `frontend/src/components/BlockNode.tsx` | Custom ReactFlow node: header, inline config, ports, state badge |
| `frontend/src/components/PortHandle.tsx` | Custom ReactFlow handle: type-coloured circle/double-ring |
| `frontend/src/components/DataPreview.tsx` | Right column: port selector, collection tabs, renderer |
| `frontend/src/components/preview/TableRenderer.tsx` | DataFrame/PeakTable preview |
| `frontend/src/components/preview/ImageRenderer.tsx` | Array/Image preview with zoom |
| `frontend/src/components/preview/ChartRenderer.tsx` | Series/Spectrum Plotly chart |
| `frontend/src/components/preview/TextRenderer.tsx` | Text preview with Monaco |
| `frontend/src/components/preview/ArtifactRenderer.tsx` | File/PDF/generic preview |
| `frontend/src/components/preview/CompositeRenderer.tsx` | CompositeData slot list |
| `frontend/src/components/BottomPanel.tsx` | Tab container with AI Chat, Config, Logs, etc. |
| `frontend/src/components/bottom/AIChat.tsx` | AI conversational interface |
| `frontend/src/components/bottom/ConfigPanel.tsx` | Full parameter form from JSON Schema |
| `frontend/src/components/bottom/LogViewer.tsx` | SSE log stream with filters |
| `frontend/src/store/index.ts` | Zustand store with slices |
| `frontend/src/store/workflowSlice.ts` | Nodes, edges, metadata |
| `frontend/src/store/executionSlice.ts` | Block states, timing, output refs |
| `frontend/src/store/uiSlice.ts` | Panel widths, selections, active tab |
| `frontend/src/store/previewSlice.ts` | Cached preview data |
| `frontend/src/store/paletteSlice.ts` | Block registry data |
| `frontend/src/store/chatSlice.ts` | AI chat history |
| `frontend/src/config/typeColorMap.ts` | Base type → colour hex mapping |
| `frontend/src/hooks/useWebSocket.ts` | WebSocket connection + event dispatch to Zustand |
| `frontend/src/hooks/useSSE.ts` | SSE connection for log streaming |
| `frontend/src/lib/api.ts` | REST API client (fetch wrappers) |

#### Backend files to modify

| File | Change |
|------|--------|
| `src/scieasy/api/routes/workflows.py` | Add `execute_from()` endpoint |
| `src/scieasy/engine/scheduler.py` | Add `execute_from()` method |
| `src/scieasy/api/routes/data.py` | Implement preview endpoint with type-appropriate responses |
| `src/scieasy/api/schemas.py` | Add `ExecuteFromRequest`, `ExecuteFromResponse` models |
| `src/scieasy/blocks/base/config.py` | Support `ui_priority` in parameter schema |
| `src/scieasy/core/types/base.py` | Add optional `_ui_ring_color: ClassVar[str]` |

#### Documentation files to update

| File | Change |
|------|--------|
| `docs/architecture/ARCHITECTURE.md` Section 9 | Full rewrite of Layer 6 — Frontend |
| `docs/architecture/ARCHITECTURE.md` Section 8.2 | Add `execute-from` endpoint |
| `docs/architecture/PROJECT_TREE.md` | Add `frontend/src/` directory structure |
| `docs/roadmap/ROADMAP.md` Phase 8 | Rewrite to match new frontend component breakdown |
| `docs/testing/phase-5-to-8-human-tests.md` | Update Phase 8 test cases for new layout |

---

## ADR-023 Addendum 1: Project management in the frontend and API enhancements for ADR-023

**Date**: 2026-04-04

### Context

ADR-023 redesigned the frontend layout but did not address project-level operations. The backend already has skeleton endpoints for project CRUD (`routes/projects.py`) and the CLI already implements `scieasy init` (Phase 6). However, the frontend has no UI for creating, opening, saving, or switching projects. Additionally, the Phase 7 API roadmap needs updates to reflect ADR-023's new endpoint requirements and enhanced response formats.

### Decision

#### 1. Project management UI

Add a **Projects menu** to the toolbar, positioned before the file operations group:

```
[📁 Projects ▼] │ [📂 Import][💾 Save][📤 Export] │ [▶ Run][⏸ Pause]...
      │
      ├── New Project...        → dialog: name, description, directory
      ├── Open Project...       → dialog: select from list or browse directory
      ├── Save Project          → save current project state (project.yaml + workflows)
      ├── ─────────────
      ├── Recent Projects ▸     → sub-menu of last 5 opened projects
      └── Close Project         → close current project, return to welcome screen
```

**"New Project" flow:**

1. User clicks "New Project..." → modal dialog appears.
2. User enters: project name, optional description, parent directory (with file browser).
3. Frontend sends `POST /api/projects/` with `{ "name": "...", "description": "...", "path": "/path/to/parent" }`.
4. Backend executes the equivalent of `scieasy init` — creates the workspace directory structure (`workflows/`, `data/raw/`, `data/zarr/`, `data/parquet/`, `data/artifacts/`, `blocks/`, `types/`, `checkpoints/`, `lineage/`, `logs/`) and writes `project.yaml`.
5. Backend returns the project metadata including the workspace path.
6. Frontend switches to the new project (empty canvas, palette refreshed for project-local blocks).

**"Open Project" flow:**

1. User clicks "Open Project..." → modal dialog with two modes:
   - **List mode**: fetches `GET /api/projects/` → shows known projects with name, path, last opened date.
   - **Browse mode**: file dialog to select a project directory (must contain `project.yaml`).
2. Frontend sends `GET /api/projects/{project_id}` or posts the selected path.
3. Backend loads `project.yaml`, discovers `workflows/`, rescans `blocks/` and `types/` directories.
4. Frontend loads the first workflow from `workflows/` (or shows an empty canvas if none exist) and refreshes the block palette.

**"Save Project" flow:**

1. Saves the current workflow to `workflows/{workflow_id}.yaml` via `PUT /api/workflows/{id}`.
2. Saves any modified project metadata to `project.yaml`.
3. Shows a brief confirmation toast.

**Welcome screen (no project open):**

When no project is open (app first launched or project closed), the canvas area shows a welcome screen:

```
┌──────────────────────────────────────┐
│                                      │
│        Welcome to SciEasy            │
│                                      │
│   [📁 New Project]                   │
│   [📂 Open Project]                  │
│                                      │
│   Recent Projects:                   │
│     • Raman Analysis (~/projects/...)│
│     • LC-MS Pipeline (~/projects/...)│
│                                      │
└──────────────────────────────────────┘
```

#### 2. Phase 7 API enhancements for ADR-023

The following additions and modifications to Phase 7 REST endpoints are required by ADR-023:

**New endpoint:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/workflows/{id}/execute-from` | POST | Start execution from a specific block using cached upstream outputs (ADR-023 Section 8) |

**Enhanced response formats:**

| Endpoint | Enhancement |
|----------|-------------|
| `GET /api/blocks/{type}/schema` | Response must include `ui_priority` per parameter (for inline display ordering) and port type names with inheritance chain (for colour resolution). Optional `ui_ring_color` on sub-types. |
| `GET /api/data/{ref}/preview` | Response must be type-appropriate: table rows for DataFrame, image thumbnail (base64 or URL) for Image/Array, chart data points for Series/Spectrum, text content for Text, file metadata for Artifact. |
| `POST /api/projects/` | Accept `path` parameter for parent directory. Return created workspace path. |
| `GET /api/projects/` | Return list with `name`, `path`, `description`, `last_opened`, `workflow_count`. |

**New API schemas (schemas.py):**

```python
class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    path: str  # parent directory where workspace will be created

class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    path: str  # full workspace path
    last_opened: str | None = None  # ISO-8601
    workflow_count: int = 0

class ExecuteFromRequest(BaseModel):
    block_id: str

class ExecuteFromResponse(BaseModel):
    execution_started: bool
    start_block: str
    reset_blocks: list[str] = []
    preserved_blocks: list[str] = []
    missing_predecessors: list[str] = []
    message: str = ""
```

#### 3. Frontend state changes

Add a `projectSlice` to the Zustand store:

| Slice | Fields |
|-------|--------|
| `projectSlice` | `currentProject: ProjectResponse \| null`, `recentProjects: ProjectResponse[]`, `isProjectOpen: boolean` |

When `isProjectOpen` is false, the canvas area renders the welcome screen instead of ReactFlow.

### Impact on files

#### Backend

| File | Change |
|------|--------|
| `src/scieasy/api/schemas.py` | Add `ProjectCreate`, `ProjectResponse`, `ExecuteFromRequest`, `ExecuteFromResponse` |
| `src/scieasy/api/routes/projects.py` | Implement all 5 endpoints with workspace directory operations |
| `src/scieasy/api/routes/workflows.py` | Add `execute_from()` endpoint |
| `src/scieasy/api/routes/data.py` | Implement type-appropriate preview responses |
| `src/scieasy/engine/scheduler.py` | Add `execute_from()` method |

#### Frontend

| File | Change |
|------|--------|
| `frontend/src/components/Toolbar.tsx` | Add Projects dropdown menu |
| `frontend/src/components/ProjectDialog.tsx` | New/Open project modal dialogs |
| `frontend/src/components/WelcomeScreen.tsx` | Welcome screen when no project is open |
| `frontend/src/store/projectSlice.ts` | Current project, recent projects, isProjectOpen |
| `frontend/src/store/index.ts` | Add projectSlice |

#### Documentation

| File | Change |
|------|--------|
| `docs/architecture/ARCHITECTURE.md` Section 8.2 | Add project endpoint details |
| `docs/architecture/ARCHITECTURE.md` Section 9.3 | Add Projects menu to toolbar |
| `docs/architecture/PROJECT_TREE.md` | Add new frontend files |
| `docs/roadmap/ROADMAP.md` Phase 7 & 8 | Update for ADR-023 requirements |

---

## ADR-024: Frontend bundling, SPA serving, and `scieasy gui` command

**Status**: accepted
**Date**: 2026-04-05

### Context

The target user profile for SciEasy includes scientists who do not write code. The current developer workflow requires Node.js, `npm install`, and running a separate `npm run dev` process — this is unacceptable for end users. The installation and launch experience must be:

```
pip install scieasy
scieasy gui
```

This ADR defines how the React frontend is bundled into the Python package and served to users.

### Decision

#### 1. Frontend compiled into Python wheel as static files

The React frontend is built at **package build time** (not at install time). The compiled output is included in the Python wheel as package data.

Directory layout inside the installed package:

```
scieasy/
├── api/
│   ├── app.py
│   ├── static/         ← npm run build output (index.html, assets/)
│   ���── ...
```

Build pipeline:
- CI / release workflow runs `cd frontend && npm run build`
- Build output copied to `src/scieasy/api/static/`
- `pyproject.toml` declares `[tool.hatch.build.targets.wheel] packages = ["src/scieasy"]` with static files included via package-data
- Users installing via `pip install scieasy` receive the pre-built frontend
- Developers still use `npm run dev` with CORS for frontend development

#### 2. API prefix convention

All backend API routes use the `/api/` prefix. WebSocket uses `/ws`. All other paths serve the SPA.

```
/api/*         → FastAPI route handlers
/ws            → WebSocket endpoint
/*             → SPA fallback (serve index.html)
```

This is enforced in `create_app()`:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)

    # API routes (must be registered BEFORE static mount)
    app.include_router(projects_router, prefix="/api")
    app.include_router(workflows_router, prefix="/api")
    app.include_router(data_router, prefix="/api")
    app.include_router(blocks_router, prefix="/api")

    # WebSocket
    app.add_api_websocket_route("/ws", websocket_endpoint)

    # SPA fallback: serve pre-built frontend
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True))

    return app
```

#### 3. `scieasy gui` CLI command

A new CLI command starts the server and opens the user's default browser:

```python
@app.command()
def gui(
    port: int = typer.Option(8000, help="Port for the API server"),
    no_browser: bool = typer.Option(False, help="Do not open browser automatically"),
):
    """Launch SciEasy GUI in your default browser."""
    import threading
    import webbrowser
    import uvicorn

    url = f"http://localhost:{port}"
    if not no_browser:
        threading.Timer(1.5, webbrowser.open, args=[url]).start()

    uvicorn.run("scieasy.api.app:create_app", factory=True, host="0.0.0.0", port=port)
```

The existing `scieasy serve` command (from PR #160) remains available for headless/API-only usage.

#### 4. Zero-configuration first launch

When a user opens the GUI with no existing projects, the frontend shows a Welcome screen (ADR-023 Addendum 1). The backend provides a default workspace directory at `~/SciEasy/projects/`. The "Create Project" flow requires only a project name — all other settings use sensible defaults.

### Alternatives considered

| Alternative | Why rejected |
|---|---|
| Require Node.js at install time | Unacceptable for non-developer users |
| Electron app | Heavy distribution, separate update channel, overkill for local-first web UI |
| Streamlit / Gradio | Cannot support the custom canvas-based workflow editor from ADR-023 |
| Ship frontend as separate pip package | Extra install step, version synchronization complexity |

### Consequences

- Frontend and backend versions are always in sync (same wheel)
- No Node.js required for end users
- Developers need Node.js only for frontend development
- `pyproject.toml` must include a build hook or CI step for frontend compilation
- Frontend must use relative paths for all assets (no hardcoded `localhost:5173`)

### Detailed impact scope

#### New files

| File | Contents |
|---|---|
| `src/scieasy/api/static/` | Directory containing pre-built React frontend output (`index.html`, `assets/`). Created by `npm run build` during CI release step, included in wheel as package data. Not committed to git — `.gitignore`'d. |
| `src/scieasy/api/spa.py` | SPA fallback middleware: subclass of `StaticFiles` that returns `index.html` for any path not matching a real file. ~30 lines. Required because FastAPI's `StaticFiles(html=True)` only serves `index.html` for `/`, not for deep SPA routes like `/projects/123/workflows`. |
| `tests/api/test_spa_fallback.py` | Tests: (1) `/api/...` routes are NOT intercepted by SPA. (2) `/ws` is NOT intercepted. (3) Unknown paths like `/projects/foo` return `index.html`. (4) Static assets (`/assets/main.js`) are served directly. |

#### Modified files — Layer 5 (API)

| File | Changes |
|---|---|
| `src/scieasy/api/app.py` | **Add** import `from pathlib import Path`. **Add** import `from scieasy.api.spa import SPAStaticFiles`. **Add** static file mount at the END of `create_app()` (after all API routers and WebSocket): `static_dir = Path(__file__).parent / "static"` → `if static_dir.exists(): app.mount("/", SPAStaticFiles(directory=static_dir, html=True))`. Must be registered AFTER all `/api/*` and `/ws` routes (line 49, before `return app`). **No changes** to `_lifespan`, CORS, or existing route registration. |

#### Modified files — Layer 6 (CLI)

| File | Changes |
|---|---|
| `src/scieasy/cli/main.py` | **Add** new `gui` command (after line 231, after existing `serve` command). Implementation: `@app.command() def gui(port: int = typer.Option(8000), no_browser: bool = typer.Option(False))` → starts uvicorn with `create_app` factory + opens browser via `threading.Timer(1.5, webbrowser.open, [url])`. **Add** imports: `threading`, `webbrowser` (inside function body to avoid top-level cost). **Update** existing `serve` command (lines 226–231): replace placeholder echo with actual uvicorn start: `uvicorn.run("scieasy.api.app:create_app", factory=True, host=host, port=port)`. |

#### Modified files — Build & CI

| File | Changes |
|---|---|
| `pyproject.toml` | **Add** `[tool.setuptools.package-data]` section: `scieasy = ["api/static/**/*"]` to include pre-built frontend in wheel. No change to `[tool.setuptools.packages.find]` (line 79–80) — `where = ["src"]` already picks up the `api/` package. |
| `.github/workflows/ci.yml` | **Add** a `build-frontend` job (runs before `build-wheel`): `cd frontend && npm ci && npm run build && cp -r dist/ ../src/scieasy/api/static/`. This job runs only on release tags (not on every PR). **Add** `needs: build-frontend` to the wheel/publish job so static files are available at wheel build time. |
| `.gitignore` | **Add** `src/scieasy/api/static/` to prevent committing build artifacts. Developers use `npm run dev` (Vite dev server) during development, not pre-built files. |

#### Modified files — Frontend

| File | Changes |
|---|---|
| `frontend/vite.config.ts` | **Add** (file may need to be created if not present): `export default defineConfig({ base: "./" })` to ensure all asset paths in the built output are relative (e.g., `./assets/main.js` not `/assets/main.js`). This is required for the SPA to work when served from any path prefix. |
| `frontend/package.json` | **Update** `"build"` script to output to `dist/` (Vite default). No path changes needed if already using default `vite build`. |

#### Modified files — Documentation

| File | Changes |
|---|---|
| `docs/architecture/ARCHITECTURE.md` | **Update** Section 7 (API layer): add paragraph describing static file serving and SPA fallback. Note that `/api/*` and `/ws` are reserved prefixes; all other paths serve the frontend. |
| `docs/architecture/PROJECT_TREE.md` | **Add** `api/spa.py` entry under `src/scieasy/api/` with annotation "SPA fallback: serves index.html for non-API routes". **Add** `api/static/` entry with annotation "(build artifact, not in git)". |
| `docs/adr/ADR.md` | This ADR (ADR-024). |
| `CHANGELOG.md` | **Add** entry under `[Unreleased]` → `### Added`. |

#### Modified files — Tests

| File | Changes |
|---|---|
| `tests/cli/test_cli.py` | **Add** tests for `gui` command: (1) `--help` prints usage. (2) Command with `--no-browser` starts uvicorn (mock uvicorn.run, verify called with correct args). (3) Default port is 8000. |
| `tests/api/test_app.py` | **Add** test: `create_app()` does NOT mount static files when `api/static/` directory does not exist (development mode). |

---

## ADR-025: Block package distribution protocol with entry-points

**Status**: accepted
**Date**: 2026-04-05

### Context

SciEasy's block system (ADR-009) currently discovers blocks via file-system scanning (Tier 1: drop-in `.py` files) and a placeholder entry-points scan (Tier 2). For the `pip install scieasy-blocks-srs` experience to work, we need a formal protocol for:

1. How external block packages register their blocks
2. How external packages register custom data types (subclasses of DataObject)
3. How external packages register custom IO adapters (for domain-specific file formats)
4. How the GUI groups and displays blocks from multiple packages

### Decision

#### 1. Three entry-point groups

External packages use Python's standard `entry_points` mechanism with three groups:

| Group | Purpose | Return type |
|-------|---------|-------------|
| `scieasy.blocks` | Block class discovery | `(PackageInfo, list[type[Block]])` or `list[type[Block]]` |
| `scieasy.types` | Custom DataObject subtype registration | `list[type[DataObject]]` |
| `scieasy.adapters` | Custom IO adapter registration | `list[type[FormatAdapter]]` |

Example `pyproject.toml` for an external package:

```toml
[project]
name = "scieasy-blocks-srs"
version = "0.1.0"
dependencies = ["scieasy>=0.1", "tifffile"]

[project.entry-points."scieasy.blocks"]
srs = "scieasy_blocks_srs:get_blocks"

[project.entry-points."scieasy.types"]
srs = "scieasy_blocks_srs.types:get_types"

[project.entry-points."scieasy.adapters"]
srs = "scieasy_blocks_srs.io:get_adapters"
```

#### 2. Block registration with package-level metadata

```python
from scieasy.blocks.base import PackageInfo

PACKAGE_INFO = PackageInfo(
    name="SRS Imaging",
    description="Stimulated Raman Scattering microscopy analysis toolkit",
    author="Dr. Wang Lab",
    version="0.1.0",
)

def get_blocks():
    from .processing.unmixing import SpectralUnmixingBlock
    from .processing.baseline import BaselineCorrectionBlock
    from .stat.pca import PCABlock
    from .io.srs_reader import SRSReaderBlock
    return PACKAGE_INFO, [SRSReaderBlock, SpectralUnmixingBlock, BaselineCorrectionBlock, PCABlock]
```

`PackageInfo` is a new dataclass in `scieasy.blocks.base`:

```python
@dataclass
class PackageInfo:
    name: str
    description: str = ""
    author: str = ""
    version: str = "0.1.0"
```

For backward compatibility, `get_blocks()` may also return a plain `list[type[Block]]` (without `PackageInfo`). In that case, the entry-point name is used as the package display name.

#### 3. Two-level block categorization

Blocks are organized in the GUI by **package** (top level) and **category** (second level):

```
Block Palette:
├── Core                         ← built-in (scieasy main package)
│   ├── code_block
│   ├── io_block
│   └── manual_review
├── SRS Imaging                  ← PackageInfo.name
│   ├── io                       ← BlockMetadata.category
│   │   └── SRS Reader
│   ├── processing
│   │   ├── Spectral Unmixing
│   │   └── Baseline Correction
│   └── stat
│       └── PCA
└── Genomics                     ← another pip package
    └── ...
```

The `category` field is a free-form string set by the block author in `BlockMetadata`. No fixed taxonomy — authors define categories that make sense for their domain.

#### 4. Type registration via entry-points

Custom DataObject subtypes must be registered so the engine can:
- Validate port type compatibility (e.g., `SRSImage` IS-A `Image` IS-A `Array`)
- Reconstruct typed objects from storage references during checkpoint restore
- Display type-appropriate previews in the frontend

```python
# scieasy_blocks_srs/types.py
from scieasy.core.types.array import Image

class SRSImage(Image):
    axes: ClassVar[list[str] | None] = ["y", "x", "wavenumber"]

def get_types():
    return [SRSImage]
```

`TypeRegistry` gains a `_scan_entrypoint_types()` method:

```python
def _scan_entrypoint_types(self) -> None:
    eps = entry_points(group="scieasy.types")
    for ep in eps:
        try:
            type_classes = ep.load()()
            for cls in type_classes:
                self.register_type(cls)
        except Exception:
            logger.warning("Failed to load types from '%s'", ep.name, exc_info=True)
```

#### 5. Custom type metadata persistence (sidecar protocol)

External types may define domain-specific fields (e.g., `wavenumbers: list[float]` on an SRSImage subclass). These fields are instance-level metadata that must survive save/load cycles.

**The core engine does NOT handle custom field persistence.** This is the package author's responsibility via one of two mechanisms:

**Mechanism A: Use `DataObject._metadata` dict** (simple, recommended for small metadata)

```python
class SRSReaderBlock(Block):
    def process_item(self, ...) -> SRSImage:
        data, wavenumbers = read_srs_file(path)
        img = SRSImage(shape=data.shape, ndim=3, dtype=str(data.dtype))
        img._data = data
        img.metadata["wavenumbers"] = wavenumbers.tolist()
        return img
```

The `_metadata` dict is JSON-serializable (ADR-017) and flows through the worker serialization pipeline via `StorageReference.metadata`.

**Mechanism B: Custom sidecar file** (for complex or large metadata)

The package author writes a custom save/load hook or a thin wrapper block that persists metadata alongside the data file. This is the author's design choice — the core provides no special mechanism.

**Rationale for keeping core small**: The engine's job is to route data between blocks and manage execution. Domain-specific metadata semantics (what `wavenumbers` means, how to validate it, how to display it) belong to the domain package, not the core.

#### 6. Adapter registration via entry-points

> **Status (2026-04-08): SUPERSEDED by ADR-028 §D4.** The `scieasy.adapters`
> entry-point group described in this section has been removed. Concrete IO is
> now provided by `IOBlock` ABC subclasses (`LoadData`, `SaveData`, plus
> plugin-owned loaders like `LoadImage` and `LoadMSRawFile`) registered under
> the existing `scieasy.blocks` entry-point group. The `FormatAdapter` protocol,
> the per-extension adapter registry, and the `get_adapters()` callable have
> all been deleted; the logic that previously lived in
> `src/scieasy/blocks/io/adapters/{csv,parquet,zarr,generic}_adapter.py` was
> absorbed into module-level private `_load_*` / `_save_*` functions inside
> `LoadData` and `SaveData` (ADR-028 Addendum 1 §C9). Plugin-owned IO blocks
> use the dynamic-port mechanism (ADR-028 Addendum 1 §C5) when one class needs
> to expose different effective output types based on user config. The text
> below is preserved verbatim for historical context — do not implement it.

Custom adapters handle domain-specific file formats:

```python
def get_adapters():
    from .io.srs_tiff import SRSTiffAdapter
    return [SRSTiffAdapter]
```

The adapter registry resolves by file extension. External adapters are checked **after** built-in adapters, so external packages cannot override `.csv` or `.parquet` handling (safety measure).

#### 7. Built-in blocks strategy (Strategy C)

`pip install scieasy` ships with general-purpose blocks:
- CodeBlock — execute Python/R code
- IOBlock — read/write standard formats
- ManualReviewBlock — human-in-the-loop
- SubWorkflowBlock — nested workflows
- AppBlock — external application wrapper

Domain-specific blocks (imaging, genomics, etc.) are distributed as separate packages.

### Alternatives considered

| Alternative | Why rejected |
|---|---|
| All blocks external (Strategy B) | Bad first experience — `pip install scieasy` alone can't do anything |
| All blocks internal (Strategy A) | Bloats main package with every domain's dependencies |
| Plugin YAML manifests instead of entry-points | Non-standard, reinvents what entry-points already solve |
| Single entry-point group for everything | Types, blocks, and adapters have different lifecycle and discovery patterns |

### Consequences

- External developers can `pip install` their blocks into any SciEasy installation
- Block discovery is lazy — entry-points are only loaded when the registry scans
- Type compatibility works across packages (SRSImage IS-A Image IS-A Array)
- No changes to the execution engine — blocks run the same regardless of origin
- BlockRegistry needs minor refactoring to support PackageInfo and two-level categorization

### Detailed impact scope

#### New files

| File | Contents |
|---|---|
| `src/scieasy/blocks/base/package_info.py` | `PackageInfo` dataclass with fields: `name: str`, `description: str = ""`, `author: str = ""`, `version: str = "0.1.0"`. Kept in a separate file (not `block.py`) to avoid circular imports when external packages import it for registration. |
| `tests/blocks/test_package_discovery.py` | Tests for the full entry-point discovery pipeline: (1) `get_blocks()` returning `(PackageInfo, list[Block])` tuple is parsed correctly. (2) `get_blocks()` returning plain `list[Block]` (backward compat) uses entry-point name as package name. (3) `get_types()` registers custom types into TypeRegistry. (4) `get_adapters()` registers adapters with correct extension mappings. (5) External adapter does not override built-in extensions. |

#### Modified files — Layer 2 (Block System)

| File | Changes |
|---|---|
| `src/scieasy/blocks/base/__init__.py` | **Add** import and re-export: `from scieasy.blocks.base.package_info import PackageInfo` (after line 5). **Add** `"PackageInfo"` to `__all__` list (line 23–37). |
| `src/scieasy/blocks/registry.py` | **Add** `import logging` and `logger = logging.getLogger(__name__)` at module level (after line 17). **Add** `package_name: str = ""` field to `BlockSpec` dataclass (after line 39, for GUI grouping). **Update** `BlockRegistry.__init__()` (line 52–54): **Add** `self._packages: dict[str, PackageInfo] = {}` to track registered package metadata. **Rewrite** `_scan_tier2()` (lines 101–121): load entry-point, call the callable, detect return type — if `tuple` of `(PackageInfo, list)`, extract package info and register each block with `block_spec.package_name = info.name`; if plain `list`, use `ep.name` as fallback package name. **Add** `logger.warning(...)` in all 3 exception handlers (lines 97, 107–108, 120–121) — this overlaps with issue #169 fix. **Add** `def packages(self) -> dict[str, PackageInfo]` public method for GUI to query available packages and their metadata. **Add** `def specs_by_package(self) -> dict[str, list[BlockSpec]]` method returning blocks grouped by `package_name` for the block palette two-level hierarchy. |
| `src/scieasy/blocks/registry.py` → `BlockSpec` | **Add** `package_name: str = ""` field to the dataclass (line 39). Populated during Tier 2 scan from `PackageInfo.name` or entry-point name. |

#### Modified files — Layer 1 (Data Foundation)

| File | Changes |
|---|---|
| `src/scieasy/core/types/registry.py` | **Add** `import importlib.metadata` (after line 9). **Add** `import logging` and `logger = logging.getLogger(__name__)` at module level. **Add** `_scan_entrypoint_types()` method to `TypeRegistry` class (after `scan_builtins()`, line 108): iterates `entry_points(group="scieasy.types")`, calls each callable, registers returned type classes via `self.register()`. Uses `try/except` with `logger.warning(...)` for robustness. **Update** `scan_builtins()` (line 67): optionally call `self._scan_entrypoint_types()` at the end, or provide a separate `scan_all()` method that calls both. |

#### Modified files — Layer 2 (IO Subsystem)

| File | Changes |
|---|---|
| `src/scieasy/blocks/io/adapter_registry.py` | **Add** `import logging` and `logger = logging.getLogger(__name__)` at module level (after line 6). **Update** `scan_entry_points()` (lines 49–65): **Add** priority enforcement — external adapters registered with `_register_external()` that skips extensions already claimed by `register_defaults()`. This prevents external packages from silently overriding `.csv`, `.parquet`, `.tiff`, `.zarr` handling. **Add** `logger.warning(...)` in exception handler (line 64) instead of bare `continue`. **Add** `logger.info("Registered external adapter %s for %s", ep.name, ...)` on success. |

#### Modified files — Build Configuration

| File | Changes |
|---|---|
| `pyproject.toml` | **No changes required** for core package. Entry-point groups `scieasy.blocks`, `scieasy.types`, `scieasy.adapters` already exist (lines 45–68). The `_scan_tier2` refactoring changes how loaded callables are interpreted, not the entry-point declaration format. |

#### Modified files — Documentation

| File | Changes |
|---|---|
| `docs/architecture/ARCHITECTURE.md` | **Update** Section 5.1 (Block base): add `PackageInfo` dataclass description and two-level categorization model (package → category → block). **Update** Section 5.2 (Block registry): describe `_scan_tier2()` callable protocol — return `(PackageInfo, list)` or `list`. Document `packages()` and `specs_by_package()` API. **Update** Section 3 (layer overview): mention that Layer 2 now supports package-level metadata for external block discovery. |
| `docs/architecture/PROJECT_TREE.md` | **Add** `blocks/base/package_info.py` entry with annotation "PackageInfo dataclass for external block package metadata". |
| `docs/adr/ADR.md` | This ADR (ADR-025). |
| `CHANGELOG.md` | **Add** entry under `[Unreleased]` → `### Added`. |

#### Modified files — Tests

| File | Changes |
|---|---|
| `tests/blocks/test_registry.py` | **Add** test: `_scan_tier2` with `(PackageInfo, [BlockClass])` return populates `package_name` on BlockSpec. **Add** test: `_scan_tier2` with plain `[BlockClass]` return uses entry-point name as `package_name`. **Add** test: `specs_by_package()` returns correctly grouped dict. **Add** test: `packages()` returns registered PackageInfo instances. |
| `tests/core/test_type_registry.py` | **Add** test: `_scan_entrypoint_types()` registers custom type subclass. **Add** test: entry-point load failure logs warning and does not crash. |
| `tests/blocks/test_adapter_registry.py` | **Add** test: external adapter cannot override built-in `.csv` extension. **Add** test: external adapter registers successfully for novel extension (e.g., `.srs`). **Add** test: entry-point load failure logs warning and does not crash. |

---

## ADR-026: Block SDK — scaffolding, test harness, and developer documentation

**Status**: accepted
**Date**: 2026-04-05

### Context

For the SciEasy ecosystem to grow, external developers must be able to create block packages without reading internal architecture documents. They need:

1. A project scaffolding tool that generates a working package structure
2. A test harness that validates blocks against the block contract without manual setup
3. Documentation that communicates the constraints from ADR-017 through ADR-022 in practical, actionable terms

### Decision

#### 1. `scieasy init-block-package` CLI command

Generates a complete, ready-to-develop block package:

```bash
$ scieasy init-block-package scieasy-blocks-srs

Package display name [SRS]: SRS Imaging
Author []: Dr. Wang Lab
Categories (comma-separated) [processing]: processing, stat, io

Created scieasy-blocks-srs/
  src/scieasy_blocks_srs/
    __init__.py                    # PackageInfo + get_blocks()
    types.py                       # Example custom type (optional)
    processing/example_block.py    # Example block per category
    stat/example_block.py
    io/example_block.py
  tests/
    test_example_block.py          # Example test using BlockTestHarness
  pyproject.toml                   # Pre-configured with entry-points
  README.md                        # Quick start guide
```

The generated `pyproject.toml` includes all three entry-point groups pre-configured. The example block is a minimal working implementation with inline comments explaining the contract.

#### 2. `BlockTestHarness` �� testing utility

A test helper that eliminates boilerplate for block testing:

```python
from scieasy.testing import BlockTestHarness

class TestMyBlock:
    def test_doubles_values(self, tmp_path):
        harness = BlockTestHarness(MyTransformBlock, work_dir=tmp_path)
        result = harness.run(
            inputs={"data": {"x": [1, 2, 3], "y": [4, 5, 6]}},
            params={"column": "x"},
        )
        # result is a dict of port_name -> materialized data
        assert result["output"].column("x").to_pylist() == [2, 4, 6]
```

`BlockTestHarness` responsibilities:
- Wrap raw Python data (dicts, lists, numpy arrays) into appropriate DataObjects
- Create a temporary project structure
- Call `process_item()` with properly constructed inputs
- Validate output types against the block's `BlockContract`
- Materialize output DataObjects for easy assertion
- Clean up temporary files

Location: `src/scieasy/testing/harness.py` (new module).

#### 3. Developer documentation structure

```
docs/block-development/
├── quickstart.md                     # 5-minute from-zero-to-running
├── architecture-for-block-devs.md    # Execution model explained
├── block-contract.md                 # inputs/outputs/params reference
├── data-types.md                     # Array, DataFrame, Text, Collection
├── custom-types.md                   # Subclassing core types, metadata
├── memory-safety.md                  # Three-tier processing model
├── collection-guide.md               # Working with Collections correctly
├── testing.md                        # BlockTestHarness reference
├── publishing.md                     # PyPI packaging and distribution
└── examples/
    ├── simple-transform.md           # Single block, single type
    ├── collection-processing.md      # Batch/multi-item workflows
    ├── custom-io-adapter.md          # Domain-specific file formats
    └── multi-block-package.md        # Full package with categories
```

#### 4. Critical documentation topics (translating ADR-017–022)

The following ADR constraints MUST be communicated to external developers through practical guides, not by referencing ADR numbers:

**From ADR-017 (Subprocess isolation):**

> Your block runs in a **separate subprocess** — not a thread, not the main process.
>
> ✅ You CAN: use any CPU/memory, import any library, read/write project files, return DataObjects, raise exceptions
>
> ❌ You CANNOT: access global mutable state across calls, share memory with other blocks, hold persistent connections, spawn background threads that outlive process_item()

**From ADR-020 (Collection transport):**

Three-tier memory safety model for processing multiple items:

| Tier | Method | Who manages iteration? | Memory bound? |
|------|--------|----------------------|---------------|
| 1 | `process_item()` | Engine | Yes (1 item at a time) |
| 2 | `map_items()` | Block (with batch_size) | Controllable |
| 3 | Manual `Collection` handling | Block | Developer responsibility |

Default recommendation: Tier 1. Authors opt into Tier 2/3 only when cross-item operations are required.

**From ADR-022 (Memory monitoring):**

Blocks should declare resource hints to help the scheduler:

```python
metadata = BlockMetadata(
    ...,
    resource_hints={
        "estimated_memory_per_item": "500MB",
        "gpu": False,
        "parallelizable": True,
    },
)
```

**From ADR-018 (Cancellation):**

Blocks do not need to explicitly handle cancellation. The engine terminates the subprocess. However, blocks that write partial output should use atomic patterns (write-to-temp-then-rename) so cancellation mid-write does not produce corrupt files.

#### 5. Custom data types guide

External developers may define domain-specific types by subclassing core types:

```python
from scieasy.core.types.array import Image

class SRSImage(Image):
    """SRS microscopy image with spectral wavenumber axis."""
    axes: ClassVar[list[str] | None] = ["y", "x", "wavenumber"]
```

Subclassing rules:
- Inherit from the nearest core type (Array, DataFrame, Text, etc.)
- Storage backend is determined by the base type (SRSImage → Array → ZarrBackend) — no custom storage needed
- `axes` is a `ClassVar` — it labels dimensions semantically, not their coordinate values
- Instance-specific metadata (e.g., wavenumber coordinates, spatial calibration) goes in `DataObject._metadata` dict
- Custom instance fields beyond `_metadata` are the package author's responsibility to persist (the core does not auto-serialize custom fields — see ADR-025 Section 5)
- Maximum inheritance depth: 3 levels from `DataObject` (e.g., DataObject → Array → Image → SRSImage)

Port type matching uses `isinstance`, so `SRSImage` auto-matches ports expecting `Image` or `Array`. A port expecting `SRSImage` will NOT accept a plain `Image`.

#### 6. Decision tree for IO blocks

Included in the documentation to help authors decide whether they need custom IO:

```
Do I need a custom IO adapter or block?

Is my data in a standard format (.csv, .parquet, .tiff, .zarr)?
  YES → Built-in adapter handles it. No custom IO needed.
  NO  → Write a custom FormatAdapter for your file extension.
         Register via scieasy.adapters entry-point.

Does the standard adapter return the wrong type?
  (e.g., TIFFAdapter returns Image but I need SRSImage)
  YES, and metadata is IN the file → Write a typed adapter that
       extends the built-in one, extracts metadata, returns your type.
  YES, but metadata is user-provided → Write a "promote" block
       that takes Image + params → SRSImage.
  NO  → No custom IO needed.
```

### Alternatives considered

| Alternative | Why rejected |
|---|---|
| No scaffolding (just docs) | Higher barrier to entry, more boilerplate errors |
| cookiecutter template | Extra dependency, less integrated than CLI command |
| No test harness (raw pytest) | Too much setup code per test, discourages testing |
| Document by ADR reference | External developers won't read internal ADRs |

### Consequences

- Lower barrier to entry for external block developers
- Consistent package structure across the ecosystem
- Test harness catches contract violations early
- Documentation prevents common pitfalls (memory, serialization, type compatibility)
- `scieasy.testing` becomes a new public module in the package

### Detailed impact scope

#### New files — Source

| File | Contents |
|---|---|
| `src/scieasy/testing/__init__.py` | Public module re-export: `from scieasy.testing.harness import BlockTestHarness`. |
| `src/scieasy/testing/harness.py` | `BlockTestHarness` class (~150 lines). Constructor takes `block_class: type[Block]`, `work_dir: Path`. Methods: `run(inputs: dict, params: dict) -> dict` (wraps raw data into DataObjects/Collections, constructs `BlockConfig`, calls `block.run()`, materializes outputs for assertion), `validate_contract(block_class)` (checks `input_ports`/`output_ports` declarations, verifies `run()` method signature). Internal helpers: `_wrap_input(raw_data) -> Collection` (dict → DataFrame, list → Collection of items, ndarray → Array), `_materialize_output(collection: Collection) -> Any` (Collection → native Python objects for easy assertion). |
| `src/scieasy/cli/templates/` | Directory containing Jinja2/string-template files for `init-block-package` scaffolding. |
| `src/scieasy/cli/templates/pyproject.toml.tpl` | Template for generated package's `pyproject.toml` with pre-configured `[project.entry-points."scieasy.blocks"]`, `[project.entry-points."scieasy.types"]`, `[project.entry-points."scieasy.adapters"]` sections. Placeholders: `{{package_name}}`, `{{display_name}}`, `{{author}}`, `{{categories}}`. |
| `src/scieasy/cli/templates/__init__.py.tpl` | Template for generated package's `__init__.py` with `PackageInfo` declaration and `get_blocks()` function that imports from each category submodule. |
| `src/scieasy/cli/templates/example_block.py.tpl` | Template for a minimal working block per category. Includes inline comments explaining: `input_ports`/`output_ports` declarations, `process_item()` vs `run()` choice, Collection handling, return type requirements. |
| `src/scieasy/cli/templates/test_block.py.tpl` | Template test file using `BlockTestHarness` with a working example test. |
| `src/scieasy/cli/templates/README.md.tpl` | Template README with quick-start instructions, development setup, and publishing checklist. |

#### New files — Documentation

| File | Contents |
|---|---|
| `docs/block-development/quickstart.md` | 5-minute guide from `pip install scieasy` to running a custom block. Covers: `scieasy init-block-package`, editing the example block, running tests with `BlockTestHarness`, installing locally with `pip install -e .`, verifying with `scieasy blocks`. |
| `docs/block-development/architecture-for-block-devs.md` | Execution model explained for external developers: subprocess isolation (ADR-017), one block = one subprocess, Collection transport (ADR-020), block lifecycle (instantiate → run → serialize outputs → exit). No ADR numbers in prose — concepts only. |
| `docs/block-development/block-contract.md` | Reference for block I/O contract: `input_ports`/`output_ports` declarations, `BlockConfig` and `params`, `process_item()` vs `run()`, return value requirements, error handling (raise exceptions, engine catches). |
| `docs/block-development/data-types.md` | Core type hierarchy: `DataObject` → `Array`/`DataFrame`/`Series`/`Text`/`Artifact`/`CompositeData`. `Collection` as transport wrapper. When to use each type. Port type matching rules (`isinstance`-based). |
| `docs/block-development/custom-types.md` | How to subclass core types. Rules: inherit from nearest core type, `axes` as `ClassVar`, instance metadata in `_metadata` dict, max depth 3, storage backend inherited. Registration via `scieasy.types` entry-point. |
| `docs/block-development/memory-safety.md` | Three-tier processing model (ADR-020 Addendum 5). Tier 1: `process_item()` (framework iterates, constant memory). Tier 2: `map_items()`/`parallel_map()` (block iterates with auto-flush). Tier 3: manual loop + `pack()` safety net. When to use each tier. `parallel_map` memory warning. |
| `docs/block-development/collection-guide.md` | Working with Collections: `pack()`/`unpack()`/`unpack_single()`, `map_items()`, `parallel_map()`, handling empty collections, type homogeneity enforcement. Examples for per-item processing vs whole-collection operations. |
| `docs/block-development/testing.md` | `BlockTestHarness` API reference. Example patterns: simple transform test, collection processing test, error case test, custom type test. Integration with pytest fixtures. |
| `docs/block-development/publishing.md` | PyPI packaging guide: `pyproject.toml` entry-points, `PackageInfo` metadata, version constraints on `scieasy>=0.1`, building and uploading to PyPI, testing in a clean virtualenv. |
| `docs/block-development/examples/simple-transform.md` | Complete walkthrough: single-input single-output block that doubles array values. Shows `process_item()` pattern. |
| `docs/block-development/examples/collection-processing.md` | Multi-item processing: spectral unmixing across a Collection of SRSImages. Shows `map_items()` and `parallel_map()`. |
| `docs/block-development/examples/custom-io-adapter.md` | Writing a `FormatAdapter` for `.srs` files. Registration via `scieasy.adapters` entry-point. Priority rules (external cannot override built-in). |
| `docs/block-development/examples/multi-block-package.md` | Full `scieasy-blocks-srs` package: multiple categories (`io`, `processing`, `stat`), custom `SRSImage` type, `PackageInfo`, tests, and `pyproject.toml`. |

#### New files — Tests

| File | Contents |
|---|---|
| `tests/testing/test_harness.py` | Tests for `BlockTestHarness`: (1) `run()` wraps dict input as DataFrame, returns materialized output. (2) `run()` wraps ndarray input as Array. (3) `run()` wraps list input as Collection. (4) `validate_contract()` catches block missing `output_ports`. (5) Error in block raises, not silently swallowed. (6) `work_dir` is cleaned up. |
| `tests/cli/test_init_block_package.py` | Tests for `init-block-package` CLI command: (1) Generates valid directory structure. (2) Generated `pyproject.toml` has correct entry-points. (3) Generated `__init__.py` has `PackageInfo` and `get_blocks()`. (4) Generated test file imports `BlockTestHarness`. (5) Multiple categories create per-category subdirectories with example blocks. |

#### Modified files — Layer 6 (CLI)

| File | Changes |
|---|---|
| `src/scieasy/cli/main.py` | **Add** `init_block_package` command (after `blocks` command, ~line 224). Implementation: `@app.command("init-block-package") def init_block_package(name: str, display_name: str = typer.Option(None), author: str = typer.Option(""), categories: str = typer.Option("processing"))`. Creates target directory, reads template files from `scieasy.cli.templates`, substitutes placeholders, writes output files. Creates per-category subdirectory with `example_block.py` for each comma-separated category. **Add** import `from scieasy.cli._scaffold import scaffold_block_package` (implementation extracted to helper to keep `main.py` focused on CLI wiring). |
| `src/scieasy/cli/_scaffold.py` | **Add** (new file) scaffolding logic: `scaffold_block_package(name, display_name, author, categories, target_dir)`. Reads `.tpl` files from `templates/`, performs string substitution, writes to `target_dir`. Handles per-category directory creation and example block generation. ~100 lines. |

#### Modified files — Build Configuration

| File | Changes |
|---|---|
| `pyproject.toml` | **Add** `[tool.setuptools.package-data]` entry: `scieasy = ["cli/templates/*.tpl", "api/static/**/*"]` to include template files in the wheel (line ~80, after `packages.find`). Templates must ship with the installed package so `init-block-package` works after `pip install scieasy`. |

#### Modified files — Documentation

| File | Changes |
|---|---|
| `docs/architecture/ARCHITECTURE.md` | **Update** Section 2 (layer overview): add "Layer 7: Developer SDK" or note in Layer 6 (CLI) about `init-block-package` scaffolding and `scieasy.testing` module. **Update** Section 5 (Block system): add reference to developer documentation for block authors. |
| `docs/architecture/PROJECT_TREE.md` | **Add** `testing/__init__.py` and `testing/harness.py` entries under `src/scieasy/`. **Add** `cli/templates/` directory entry with annotation "Jinja2 templates for init-block-package scaffolding". **Add** `cli/_scaffold.py` entry. **Add** `docs/block-development/` directory listing. |
| `docs/adr/ADR.md` | This ADR (ADR-026). |
| `CHANGELOG.md` | **Add** entry under `[Unreleased]` → `### Added`. |

---

## ADR-027: Phase 10 core type system and block runtime refinements

**Status**: proposed
**Date**: 2026-04-06

### Context

Phase 10 introduces the first domain plugin package (`scieasy-blocks-imaging`) and with it the first sustained contact between the core runtime and real 5D/6D scientific data. The planning discussion surfaced a set of gaps between the architecture described in ADRs 001–026 and the code actually needed to ship a working imaging pipeline:

1. **The current `Array` / `Image` hierarchy is not usable for routine microscopy data.** `src/scieasy/core/types/array.py` declares `axes` as `ClassVar[list[str] | None]` and hard-codes `Image.axes = ["y", "x"]`, `MSImage.axes = ["y", "x", "mz"]`, etc. There is no way to represent a 5D `(t, z, c, y, x)` fluorescence stack or a 6D hyperspectral time-course without inventing yet another subclass for every permutation. This is the literal opposite of what the architecture §4.1 promises about "extensibility through named axes".

2. **Domain subtypes leak into core.** `Image`, `FluorImage`, `SRSImage`, `MSImage` are all defined in `src/scieasy/core/types/array.py`. ADR-002 (named axes), ADR-003 (broadcast as utility), and CLAUDE.md §2.3 ("Core must stay small and stable") all pressure in the direction of core holding only base primitives. The current placement contradicts that goal and blocks `scieasy-blocks-imaging` from owning its own type definitions cleanly.

3. **No ergonomic metadata story.** `DataObject._metadata` is a free `dict[str, Any]` validated only as JSON-serialisable (`core/types/base.py:93`). A `FluorImage` author who wants to record pixel size, acquisition date, channel list, and objective lens has to cram everything into one flat untyped dict. There is no schema, no unit handling, no propagation rule, and no way for a downstream block to autocomplete `img.metadata["pix..."]`.

4. **`Block` has no setup/teardown lifecycle.** Running Cellpose (or any GPU model) inside a `ProcessBlock` currently requires loading the model inside `process_item`, which means reloading it for every item in a Collection — a 5-second penalty per item on a 100-item batch. The default `run()` implementation in `ProcessBlock` iterates and calls `process_item` directly with no hook for per-run setup.

5. **Thread policy was left implicit during earlier discussions.** ADR-017 requires subprocess isolation but says nothing about whether a block's own `run()` may use threads internally. A permissive reading allows threads (cellpose-style L3 parallelism inside a block); a restrictive reading forbids them. Phase 10 needs this policy written down.

6. **`ResourceManager` defaults are broken for GPU workloads.** `resources.py:70` sets `gpu_slots: int = 0`, and `can_dispatch` refuses any `requires_gpu=True` block when `_gpu_in_use >= gpu_slots`. With `gpu_slots=0`, every GPU block fails `can_dispatch` unconditionally. The fix is a one-line default change plus auto-detection.

7. **There is no common utility for "iterate over extra axes".** ADR-003 decided broadcast is a utility in `scieasy.utils.broadcast.broadcast_apply`, but that helper was designed for the "low-dim source + high-dim target" case (applying a 2D mask over an MSI hypercube), not the more common "single Array with axes I want to process one slice at a time" case. Phase 10 imaging blocks all need the latter.

8. **Worker subprocess cannot reconstruct domain types after they move out of core.** `engine/runners/worker.py:37-60` imports `TypeSignature` and `ViewProxy` but does not call any `TypeRegistry.scan()`. Once `Image` lives in `scieasy-blocks-imaging`, a worker running a Cellpose block must be able to `import` that package and find the `Image` class to reconstruct a typed instance from a `StorageReference`. Without a scan, the worker only has core base classes available.

9. **Collection-level parallelism pattern is undocumented.** With ADR-018 Addendum 1 restoring DAG-branch parallelism, the natural way to parallelise Cellpose over 100 images is `SplitCollection → 4 parallel Cellpose branches → MergeCollection`. This is the "L2 fan-out" pattern. It works with existing built-in blocks but has never been written down as the recommended approach, so block authors will invent ad-hoc alternatives.

10. **OptEasy's `iter_over(axis)` and `sel(**kwargs)` helpers on `ArrayData` are missed.** Block authors writing 5D processing code in SciEasy currently have to `to_memory()` the whole volume and manually index with `tuple(slice(None) ... 15 ... slice(None))`. Every Phase 10 imaging block would repeat this pattern.

These issues are cross-cutting and interdependent — for example, moving domain types to plugins (#2) requires worker TypeRegistry scanning (#8), and `iter_over` laziness (#10) interacts with the metadata inheritance story (#3). They are bundled into a single ADR because they form a coherent Phase 10 preparation package rather than a sequence of unrelated fixes.

### Discussion points and resolution

| # | Topic | Options discussed | Final decision |
|---|---|---|---|
| 1 | Should `Array.axes` be class-level, instance-level, or a hybrid? | (A) Keep class-level, users subclass for every new combination. (B) Move to instance-level; class declares only constraints. (C) OptEasy-style single `dims: str` per instance. | **Decision: (B).** `Array` instances carry their own `axes: list[str]`. Classes declare `required_axes: frozenset[str]` (minimum set any instance must have), `allowed_axes: frozenset[str] | None` (superset of axes the class accepts; `None` means any), and `canonical_order: tuple[str, ...]` (preferred ordering for reorder operations). Option (A) is the current broken state. Option (C) sacrifices the typed-class discipline that makes port validation work in SciEasy. |
| 2 | How large is the axis alphabet for Phase 10? | (A) Just `(y, x)` plus a couple extras. (B) 5D: `(t, z, c, y, x)`. (C) 6D including spectral: `(t, z, c, lambda, y, x)`. | **Decision: (C).** Spectral imaging (SRS, hyperspectral) is a first-class target modality, and the `lambda` axis semantically differs from `c` (continuous spectral vs. discrete channel). Allowing both supports rare-but-real combined modalities (e.g., multichannel hyperspectral). Axis name `lambda` is spelled out (not the Greek letter `λ`) for YAML/JSON/URL safety. Canonical order is `(t, z, c, lambda, y, x)` following OME convention with spectral inserted between channel and spatial. |
| 3 | Should `c` (discrete channel) and `lambda` (continuous spectral) coexist in one axes list? | (A) Forbid; a class picks one. (B) Allow; rare but valid. | **Decision: (B).** Allow. Block authors restrict via port `constraint` helpers (e.g., `has_axes("y", "x", "c")` for multichannel, `has_axes("y", "x", "lambda")` for spectral). Framework does not forbid the combination. |
| 4 | Where should domain subtypes (`Image`, `Spectrum`, `AnnData`, `PeakTable`, etc.) live? | (A) Stay in core alongside base types. (B) Move all domain subtypes out of `scieasy/core/types/` into plugin packages. | **Decision: (B).** Core keeps only the seven base types (`DataObject`, `Array`, `Series`, `DataFrame`, `Text`, `Artifact`, `CompositeData`). All domain subtypes move to their respective plugin packages. This includes `Image`, `FluorImage`, `SRSImage`, `MSImage` (→ `scieasy-blocks-imaging`), `Spectrum`, `RamanSpectrum`, `MassSpectrum`, `PeakTable`, `MetabPeakTable` (→ `scieasy-blocks-spectral`), `AnnData` (→ future `scieasy-blocks-singlecell`), `SpatialData` (→ future `scieasy-blocks-spatial-omics`). This is the purest reading of CLAUDE.md §2.3 and ADR-008's Tier 2 package model. |
| 5 | How is broadcast-like iteration exposed to block authors? | (A) New base class hierarchy (`SpatialBlock`, `SpectralBlock`, `AxisIteratingBlock`) with override points. (B) Utility function `iterate_over_axes(source, operates_on, func)` that block authors call explicitly inside `process_item`. | **Decision: (B).** A base class per dimensional pattern multiplies the Block inheritance tree without adding expressive power — the only thing that varies is the set of axes to iterate over, which is a function argument, not a type. Utility function places the decision in the block author's hands without class-level commitment. Matches CLAUDE.md §7.2 ("Favor composition over deep inheritance"). |
| 6 | Should the iteration utility be lazy, eager, or lazy-capable? | (A) Eager: load the whole Array, iterate in memory. (B) Level 1 lazy: `iter_over(axis)` is a generator that reads one slice per step. (C) Level 2 lazy: return new Array instances with `SlicedStorageReference` that read lazily at every subsequent access. | **Decision: (B) for Phase 10.** Level 1 laziness ensures peak memory is one slice, not the full volume. Each yielded slice is an in-memory Array instance (fresh `storage_ref=None`, data in `_data`), so downstream access is free. Level 2 (virtual slice refs threaded through ViewProxy) is deferred as a Phase 11+ optimisation under a separate ADR if profiling justifies it. |
| 7 | Must `iter_over`/`sel` preserve metadata? | (A) Return raw numpy arrays. (B) Return new Array instances with all metadata inherited. | **Decision: (B).** Yielded slices are same-class-as-source (e.g., iterating a `FluorImage` yields `FluorImage` slices). `framework` metadata is derived (with a lineage hint), `meta` (domain metadata) is shared by reference since it is frozen Pydantic, `user` metadata is shallow-copied, `axes` has the iterated dimension removed. Block authors never lose metadata just because they iterated. |
| 8 | How should metadata be structured? | (A) Free `dict[str, Any]` (current). (B) Structured per-subtype using dataclasses. (C) Structured per-subtype using Pydantic BaseModel with three slots (framework / domain / user). | **Decision: (C).** Three slots: `framework: FrameworkMeta` (immutable framework-managed fields — created_at, object_id, source, lineage hint), `meta: DomainMeta` (typed Pydantic BaseModel declared per subtype), `user: dict[str, Any]` (free-form escape hatch). Pydantic gives IDE autocompletion, type validation, clean JSON round-trip for subprocess transport, and painless schema evolution via field defaults. |
| 9 | How are physical units represented? | (A) Raw floats; unit lives in a sibling field. (B) Use `pint`. (C) Self-written `PhysicalQuantity` with a small unit table. | **Decision: (C).** `pint` is ~200–400 ms import time per subprocess worker — unacceptable when every block spawns a fresh interpreter. `PhysicalQuantity` is a ~50-line dataclass covering the ~15 units SciEasy actually needs (length, time, frequency, wavenumber). Drop-in replacement with `pint` remains possible in a future phase by swapping the `scieasy.core.units` module internals. |
| 10 | How does a block declare expensive one-time setup? | (A) Do it in `process_item`, pay the cost N times. (B) Add `setup(config)` / `teardown(state)` hooks to `ProcessBlock`. (C) Add a new `StatefulBlock` base class. | **Decision: (B).** Smallest surface change. Default `setup` returns `None`, default `teardown` does nothing. `process_item(item, config, state=None)` receives whatever `setup` returned. `ProcessBlock.run()` calls `setup` once, iterates, calls `teardown` in a `finally` block. Authors of stateless blocks ignore the hooks entirely. |
| 11 | Should `setup` receive the inputs dict? | (A) Yes, for data-driven setup. (B) No, only config. | **Decision: (B).** `setup(config)` sees only the config. Data-driven decisions (e.g. "pick the model based on the first image's modality") happen lazily inside `process_item` and cache their result on the `state` object. Keeping `setup` config-only prevents a tangled contract where `setup` becomes responsible for Collection-aware logic. |
| 12 | Are threads allowed inside a block's `run()`? | (A) Forbidden. (B) Allowed as an escape hatch, documented as not recommended. (C) Encouraged as the default parallelism pattern. | **Decision: (B).** Threads inside a block's worker subprocess are acceptable — SIGTERM/SIGKILL on the subprocess cleanly terminates all of its threads because OS-level process death releases thread resources. Threads CANNOT be interrupted cooperatively at sub-second granularity (there is no graceful "stop this thread mid-`cellpose.eval`"), so hard kill is the only reliable abort. Documentation must state: (1) threads are allowed, (2) L2 fan-out is preferred for Collection-level parallelism because it scales across machines and plays nicely with `ResourceManager`, (3) threads should be used only when a library releases the GIL (numpy/torch/cellpose C extensions) or for I/O-bound work, (4) cancellation is guaranteed only via subprocess kill, not via cooperative thread signalling. |
| 13 | What is the recommended pattern for Collection-level parallelism? | (A) Block-internal ThreadPool. (B) Block-internal ProcessPool. (C) L2 fan-out: `SplitCollection → N parallel branches → MergeCollection` at the workflow graph level. | **Decision: (C).** Pushing parallelism up to the workflow graph means each branch is a separate subprocess under `ProcessRegistry` supervision, gets its own `ResourceManager` GPU/CPU slot, benefits from DAG-level cancellation semantics, and scales naturally to multi-GPU and multi-machine execution (future). Block-internal pools are permitted as an escape hatch (per #12) but not the documented default. |
| 14 | Does `cellpose` specifically need block-internal parallelism? | (A) Yes, iterate items with a ThreadPool. (B) No, cellpose's own `model.eval([img1, img2, ...], batch_size=N)` uses GPU batching internally. | **Decision: (B).** Cellpose's parallelism is GPU-batched kernels inside a single `eval` call. A Phase 10 `CellposeSegment` block uses the Tier 2 pattern (override `run()`, call `setup()` once to load the model, then loop over the Collection in GPU-sized batches via `eval([...], batch_size=N)`). No thread pool or process pool needed at the block level. Multi-GPU parallelism uses L2 fan-out (per #13). |
| 15 | What is the default value of `ResourceManager.gpu_slots`? | (A) `0` (current — GPU blocks never dispatch). (B) `1` (always allow one GPU block). (C) Auto-detect via `torch.cuda.device_count()` or `nvidia-smi` with `0` fallback. | **Decision: (C) + fallback behaviour.** `ResourceManager.__init__` takes `gpu_slots: int | None = None`. If `None`, call `_auto_detect_gpu_slots()` which tries `torch.cuda.device_count()` first, then `nvidia-smi -L`, then returns `0`. If the detected value is `0` but any block declares `requires_gpu=True`, log a single warning explaining that the user can override via project config. Explicit integer values passed to `__init__` are respected unchanged. Auto-detect runs once per scheduler instantiation, not per dispatch. |
| 16 | Should the worker subprocess (`engine/runners/worker.py`) call `TypeRegistry.scan()` before reconstructing inputs? | (A) No — only core types are reconstructable, plugin types remain dict-like. (B) Yes — scan entry-points at worker startup so plugin types work. | **Decision: (B).** Once domain subtypes move to plugins (#4), the worker must be able to resolve `type_chain=["DataObject", "Array", "Image", "FluorImage"]` by importing `scieasy-blocks-imaging`. This means adding a `TypeRegistry.scan()` call at the top of `worker.main()` before `reconstruct_inputs()`. The scan is the same `scieasy.types` entry-point scan that the main process uses (ADR-025). Subprocess cold start grows by ~50 ms for a package with five types, acceptable given subprocess startup already dominates (~150 ms). |

### Decision

The Phase 10 decisions from the discussion table are codified below. Each section has a one-paragraph summary and a code-shape sketch where appropriate. Exact line-by-line impact is in the "Detailed impact scope" section further down.

#### D1. Instance-level axes with class-level schema (covers discussion #1–3)

`Array` holds `axes` as a per-instance list. Subclasses declare axis constraints at class level. The 6D axis alphabet is `{"t", "z", "c", "lambda", "y", "x"}`. `lambda` (spectral) and `c` (discrete channel) are distinct and may coexist in a single instance.

```python
class Array(DataObject):
    # Class-level schema (subclass overrides)
    required_axes:   ClassVar[frozenset[str]] = frozenset()
    allowed_axes:    ClassVar[frozenset[str] | None] = None   # None = any
    canonical_order: ClassVar[tuple[str, ...]] = ()

    def __init__(
        self,
        *,
        axes: list[str],            # now required
        shape: tuple[int, ...] | None = None,
        dtype: Any = None,
        chunk_shape: tuple[int, ...] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.axes = list(axes)
        self.shape = shape
        self.dtype = dtype
        self.chunk_shape = chunk_shape
        self._validate_axes()

    def _validate_axes(self) -> None:
        axes_set = set(self.axes)
        if not self.required_axes.issubset(axes_set):
            missing = self.required_axes - axes_set
            raise ValueError(
                f"{type(self).__name__} requires axes {sorted(self.required_axes)}, "
                f"missing: {sorted(missing)}"
            )
        if self.allowed_axes is not None and not axes_set.issubset(self.allowed_axes):
            extra = axes_set - self.allowed_axes
            raise ValueError(
                f"{type(self).__name__} accepts only {sorted(self.allowed_axes)}, "
                f"unexpected: {sorted(extra)}"
            )
        if len(set(self.axes)) != len(self.axes):
            raise ValueError(f"Duplicate axes in {self.axes}")
```

Domain subtypes (defined in plugins per D2):

```python
# In scieasy-blocks-imaging
class Image(Array):
    required_axes   = frozenset({"y", "x"})
    allowed_axes    = frozenset({"t", "z", "c", "lambda", "y", "x"})
    canonical_order = ("t", "z", "c", "lambda", "y", "x")

class FluorImage(Image):
    required_axes = frozenset({"y", "x", "c"})   # channel mandatory

class HyperspectralImage(Image):
    required_axes = frozenset({"y", "x", "lambda"})
```

`TypeSignature.from_type(cls)` additionally records `required_axes` as part of the signature so that port `port_accepts_signature` checks can enforce "incoming instance must have at least required_axes of target port type".

#### D2. Core contains only base types; all domain subtypes live in plugins (covers discussion #4)

`src/scieasy/core/types/` ends Phase 10 holding exactly these classes:

- `base.py` → `DataObject`, `TypeSignature`
- `array.py` → `Array` (no `Image`, no `MSImage`, no `SRSImage`, no `FluorImage`)
- `series.py` → `Series` (no `Spectrum`, `RamanSpectrum`, `MassSpectrum`)
- `dataframe.py` → `DataFrame` (no `PeakTable`, `MetabPeakTable`)
- `text.py` → `Text`
- `artifact.py` → `Artifact`
- `composite.py` → `CompositeData` (no `AnnData`, `SpatialData`)
- `collection.py` → `Collection` (unchanged)
- `registry.py` → `TypeRegistry` (unchanged behaviour, but becomes the sole source of truth for domain types)

Plugin package map:

| Domain type | Target plugin package |
|---|---|
| `Image`, `FluorImage`, `BrightfieldImage`, `HyperspectralImage`, `SRSImage` | `scieasy-blocks-imaging` |
| `MSImage`, `MALDIImage` | `scieasy-blocks-msi` (new) |
| `Spectrum`, `RamanSpectrum`, `MassSpectrum` | `scieasy-blocks-spectral` |
| `PeakTable`, `MetabPeakTable` | `scieasy-blocks-spectral` |
| `AnnData` | `scieasy-blocks-singlecell` (new) |
| `SpatialData` | `scieasy-blocks-spatial-omics` (new) |

Built-in blocks that currently reference `Image` directly (e.g. `MergeCollection`, `FilterCollection`, `SliceCollection`) are audited and changed to reference `Array` (or a plugin-provided type via entry-point import) — see impact scope.

#### D3. `iterate_over_axes` utility (covers discussion #5)

New module `src/scieasy/utils/axis_iter.py`:

```python
from typing import Callable
import numpy as np
from scieasy.core.types.array import Array
from scieasy.core.exceptions import BroadcastError

def iterate_over_axes(
    source: Array,
    operates_on: set[str],
    func: Callable[[np.ndarray, dict[str, int]], np.ndarray],
) -> Array:
    """Iterate `func` over all axes in source NOT in operates_on.

    For each combination of the non-operates_on axes, calls:
        func(slice_data, slice_coord)
    where slice_data is a numpy array containing only the operates_on
    dimensions, and slice_coord is a dict mapping extra-axis name to
    current integer index.

    Results are stacked back into a new instance of source's concrete
    class, preserving axes, shape, and metadata (framework/meta/user).

    Raises BroadcastError if slice outputs have inconsistent shapes or
    if operates_on is not a subset of source.axes.
    """
    ...
```

The function is serial. It does not use threads or subprocesses. Memory footprint is O(one slice + one result slice). Errors in user-provided `func` propagate unchanged. Metadata inheritance follows D5 (see below).

This utility is placed in `scieasy.utils.axis_iter`, adjacent to the existing `scieasy.utils.broadcast.broadcast_apply` (ADR-003). The two cover complementary use cases: `iterate_over_axes` handles "iterate a single Array's extra dims" (common case), `broadcast_apply` handles "project a low-dim object onto a high-dim object" (cross-modal fusion case).

#### D4. `Array.iter_over()` and `Array.sel()` with Level 1 laziness (covers discussion #6, #7)

New methods on `Array`:

```python
class Array(DataObject):
    def sel(self, **kwargs: int | slice) -> "Array":
        """Select a sub-array along named axes.

        Example:
            img.sel(z=15, c=0)        # single z index, single channel
            img.sel(z=slice(10, 20))  # z range

        Returns a new instance of self.__class__ with axes reduced by the
        scalar-index selections. Integer indices remove the axis; slice
        objects keep the axis. Supports integers and slice objects;
        does NOT support lists of indices or boolean masks in Phase 10.

        Metadata inheritance:
            framework: derived (lineage hint back to parent)
            meta: shared by reference (immutable Pydantic)
            user: shallow copy
            axes: reduced per the selection

        Laziness:
            If self.storage_ref is Zarr-backed and supports partial reads,
            only the requested chunk(s) are materialised. For other backends,
            falls back to self.view().to_memory() then numpy indexing.
        """
        ...

    def iter_over(self, axis: str) -> Iterator["Array"]:
        """Yield sub-arrays along one named axis.

        Example:
            for z_slice in img.iter_over("z"):
                ...

        Memory: O(one slice per iteration step). Each yielded Array has
        `axis` removed from its axes list, same class as self, metadata
        preserved per sel()'s rules.

        Implementation: generator that calls `self.sel(**{axis: k})` for
        k in range(axis_size). Lazy in the iteration sense — each step
        reads one chunk on demand.
        """
        ...
```

Phase 10 implements Level 1 laziness: lazy iteration (one slice per step) for Zarr-backed instances; for filesystem-backed instances, fall back to materialising once on first access. Level 2 laziness (persistent `SlicedStorageReference` carried through ViewProxy) is deferred.

#### D5. Stratified metadata with Pydantic (covers discussion #8)

`DataObject` gains three slots replacing the current flat `_metadata` dict:

```python
from pydantic import BaseModel, Field

class FrameworkMeta(BaseModel):
    """Framework-managed, block-authors do not mutate."""
    created_at: datetime
    object_id: str
    source: str = ""           # free-form origin description
    lineage_id: str | None = None   # links into LineageRecorder
    derived_from: str | None = None # parent object_id for derived slices

class DataObject:
    framework: FrameworkMeta
    meta: BaseModel              # subclass overrides with typed subclass
    user: dict[str, Any]         # free-form, framework does not interpret

    # Backward-compat shim: `metadata` property maps to `user` for the
    # duration of Phase 10, emitting a DeprecationWarning. Removed in Phase 11.
```

Each Array subtype declares its own `Meta` Pydantic model:

```python
# In scieasy-blocks-imaging
class FluorImage(Image):
    class Meta(BaseModel):
        pixel_size:       PhysicalQuantity              # see D6
        channels:         list[ChannelInfo] = []
        objective:        str | None = None
        acquisition_date: datetime | None = None
        instrument:       str | None = None
        exposure_ms:      dict[str, float] | None = None

    meta: "FluorImage.Meta"
```

New helper `with_meta(**changes)` on `DataObject` for immutable update:

```python
def with_meta(self, **changes: Any) -> "Self":
    """Return a new DataObject with meta fields changed.
    Other slots (framework, user, storage_ref, shape, etc.) preserved."""
    new_meta = self.meta.model_copy(update=changes)
    return self.__class__(..., meta=new_meta, ...)
```

Propagation rule in `iterate_over_axes` and `iter_over`:

- `framework`: new `framework` with `derived_from=parent.framework.object_id`, new `object_id`, `created_at=now()`.
- `meta`: shared by reference (Pydantic model is frozen).
- `user`: shallow copy.
- `axes`: reduced per the slicing operation.

Backward-compat: `DataObject.metadata` remains as a property that returns `self.user` with a `DeprecationWarning`. Removed after Phase 11.

#### D6. `PhysicalQuantity` (covers discussion #9)

New module `src/scieasy/core/units.py`:

```python
from dataclasses import dataclass

_LENGTH   = {"m": 1.0, "mm": 1e-3, "um": 1e-6, "nm": 1e-9, "pm": 1e-12, "A": 1e-10}
_TIME     = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "min": 60.0, "hr": 3600.0}
_FREQ     = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
_WAVENUM  = {"cm-1": 100.0, "m-1": 1.0}

_KIND = {
    **{u: "length"     for u in _LENGTH},
    **{u: "time"       for u in _TIME},
    **{u: "freq"       for u in _FREQ},
    **{u: "wavenumber" for u in _WAVENUM},
}
_SCALE = {**_LENGTH, **_TIME, **_FREQ, **_WAVENUM}

@dataclass(frozen=True)
class PhysicalQuantity:
    value: float
    unit: str

    def __post_init__(self) -> None:
        if self.unit not in _SCALE:
            raise ValueError(f"Unknown unit: {self.unit!r}")

    def to(self, target_unit: str) -> "PhysicalQuantity":
        if _KIND[self.unit] != _KIND[target_unit]:
            raise ValueError(f"Cannot convert {_KIND[self.unit]} to {_KIND[target_unit]}")
        return PhysicalQuantity(
            self.value * _SCALE[self.unit] / _SCALE[target_unit],
            target_unit,
        )

    def __lt__(self, other: "PhysicalQuantity") -> bool:
        if _KIND[self.unit] != _KIND[other.unit]:
            raise TypeError("Incompatible kinds")
        return self.value * _SCALE[self.unit] < other.value * _SCALE[other.unit]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PhysicalQuantity):
            return NotImplemented
        if _KIND[self.unit] != _KIND[other.unit]:
            return False
        return abs(self.value * _SCALE[self.unit] - other.value * _SCALE[other.unit]) < 1e-12
```

Pydantic validator ensures `PhysicalQuantity` fields serialise as `{"value": ..., "unit": ...}` for JSON transport across subprocesses. A custom serialiser/validator module inside `scieasy.core.units` handles the Pydantic integration.

#### D7. `ProcessBlock.setup()` and `teardown()` hooks (covers discussion #10, #11)

`ProcessBlock` base class gains two hooks and a three-argument `process_item`:

```python
class ProcessBlock(Block):
    def setup(self, config: BlockConfig) -> Any:
        """Called once per run() before iterating the Collection.
        Return value is passed to every process_item() as `state`.
        Default: returns None.
        Use for: loading ML models, opening DB connections, compiling
        regexes, anything expensive that should be reused across items."""
        return None

    def teardown(self, state: Any) -> None:
        """Called once per run() in a finally block, even on error.
        Default: no-op.
        Use for: releasing resources (close files, free GPU memory)."""
        pass

    def process_item(
        self,
        item: DataObject,
        config: BlockConfig,
        state: Any = None,
    ) -> DataObject:
        raise NotImplementedError

    def run(self, inputs, config):
        from scieasy.core.types.collection import Collection
        primary = next(iter(inputs.values()))
        state = self.setup(config)
        try:
            if isinstance(primary, Collection):
                results = []
                for item in primary:
                    result = self.process_item(item, config, state)
                    result = self._auto_flush(result)
                    results.append(result)
                output_name = self.output_ports[0].name if self.output_ports else "output"
                return {output_name: Collection(results, item_type=primary.item_type)}
            else:
                result = self.process_item(primary, config, state)
                output_name = self.output_ports[0].name if self.output_ports else "output"
                return {output_name: result}
        finally:
            self.teardown(state)
```

`setup` receives only `config`. It must not access `inputs`. Blocks that need data-driven initialisation do it lazily inside `process_item` and cache on the `state` object.

Existing blocks that override `process_item(self, item, config)` (two-argument form) remain source-compatible because the new third argument has a default of `None`. Adding `state` is purely additive.

#### D8. Thread policy (covers discussion #12)

Threads are permitted inside a block's `run()` as an escape hatch. They are NOT permitted in the engine, scheduler, event bus, process registry, or any core runtime component. The block-developer documentation must state:

1. A block's worker subprocess is killable as a unit. SIGTERM/SIGKILL terminates all threads within it. You do not need to manually cancel threads.
2. Threads cannot be interrupted cooperatively between `await` points or mid-function. If your block's thread is inside `cellpose.eval()` for 30 seconds, the only way to stop it before 30 seconds is to kill the whole subprocess.
3. Threads are worthwhile only when: (a) the library releases the GIL (numpy, torch, cellpose internals), (b) the work is I/O-bound (file or network reads).
4. For Collection-level parallelism, prefer L2 fan-out (D9) over block-internal threads. Fan-out scales across multiple GPUs and machines, threads do not.
5. If a block uses a thread pool, it should set `max_internal_workers` on its `ResourceRequest` so the `ResourceManager` can count the block's actual CPU footprint toward the scheduler-wide CPU pool. The existing `ResourceRequest.max_internal_workers` field (already present at `resources.py:27`, currently unused) is formally activated by this ADR.

#### D9. L2 fan-out as the recommended Collection-level parallelism pattern (covers discussion #13, #14)

Block authors who need N-way parallelism on a Collection express it in the workflow graph using existing built-in blocks:

```
[LoadImages]
    └─ Collection[Image] length=100
[SplitCollection n_parts=4]
    ├─ out_0 → [Cellpose A] ─┐
    ├─ out_1 → [Cellpose B] ─┤
    ├─ out_2 → [Cellpose C] ─┤
    └─ out_3 → [Cellpose D] ─┤
                             ↓
                    [MergeCollection]
```

Each `Cellpose*` branch is a separate subprocess under `ProcessRegistry` supervision, acquires its own GPU slot from `ResourceManager`, has its own setup/teardown cycle, and can be cancelled independently via ADR-018's cancel flow. Scheduler concurrency per ADR-018 Addendum 1 is a prerequisite.

`SplitCollection` and `MergeCollection` already exist as built-in blocks (`blocks/process/builtins/split_collection.py`, `merge_collection.py`). No new code is required for the pattern itself — only documentation and examples in the block developer guide.

Phase 10 `CellposeSegment` block uses Tier 2 (override `run()`) to exploit cellpose's built-in GPU batching:

```python
class CellposeSegment(ProcessBlock):
    input_ports  = [InputPort(name="images", accepted_types=[Image],
                              constraint=has_axes("y", "x"))]
    output_ports = [OutputPort(name="masks", accepted_types=[Image])]
    resource_request = ResourceRequest(
        requires_gpu=True, gpu_memory_gb=4.0, cpu_cores=2,
    )

    def setup(self, config):
        from cellpose import models
        return models.Cellpose(
            model_type=config.get("model", "cyto2"),
            gpu=True,
        )

    def run(self, inputs, config):
        state = self.setup(config)
        try:
            images = inputs["images"]
            batch_size = config.get("batch_size", 8)
            results = []
            item_list = list(images)
            for i in range(0, len(item_list), batch_size):
                batch_items = item_list[i:i+batch_size]
                batch_arrays = [it.to_memory() for it in batch_items]
                masks_list, _, _, _ = state.eval(
                    batch_arrays,
                    batch_size=batch_size,
                    diameter=config.get("diameter", 30),
                )
                for orig, mask in zip(batch_items, masks_list):
                    result = Image(
                        axes=orig.axes, shape=mask.shape, dtype=mask.dtype,
                        meta=orig.meta,
                    )
                    results.append(self._auto_flush(result))
            return {"masks": Collection(results, item_type=Image)}
        finally:
            import torch
            torch.cuda.empty_cache()
```

#### D10. `ResourceManager` auto-detects GPU slots (covers discussion #15)

`ResourceManager.__init__` signature change:

```python
class ResourceManager:
    def __init__(
        self,
        gpu_slots: int | None = None,      # was: int = 0
        cpu_workers: int = 4,
        memory_high_watermark: float = 0.80,
        memory_critical: float = 0.95,
        event_bus: Any | None = None,
    ) -> None:
        if gpu_slots is None:
            gpu_slots = _auto_detect_gpu_slots()
        self.gpu_slots = gpu_slots
        ...

def _auto_detect_gpu_slots() -> int:
    """Best-effort GPU count detection. Tries torch, then nvidia-smi, then 0."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.device_count()
    except ImportError:
        pass
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "-L"], capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            return sum(1 for line in result.stdout.splitlines() if line.startswith("GPU "))
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return 0
```

If auto-detection returns 0 but any block in the loaded workflow declares `requires_gpu=True`, log a single WARNING at scheduler start-up explaining that no GPU was detected and pointing the user at the project config override. Explicit integer values passed to `__init__` are respected unchanged.

**Important caveat**: auto-detection returns physical GPU count, not "how many cellpose instances can coexist in VRAM". Users with large models on small cards should override via project config. Phase 10 does NOT introduce VRAM-based slot calculation because `gpu_memory_gb` declarations are block-declared, not enforced, and VRAM is not reliably monitorable cross-platform per ADR-022.

#### D11. Worker subprocess TypeRegistry scan (covers discussion #16)

`src/scieasy/engine/runners/worker.py` `main()` gains an early call:

```python
def main() -> None:
    try:
        # ADR-027 D11: scan entry-points so plugin-provided DataObject
        # subtypes can be resolved during reconstruct_inputs.
        from scieasy.core.types.registry import TypeRegistry
        TypeRegistry.scan()

        raw = sys.stdin.read()
        payload = json.loads(raw)
        # ... rest unchanged ...
```

`reconstruct_inputs` is enhanced to look up `type_chain` in the registry and construct the correct subclass instance instead of always returning a bare `DataObject`:

```python
def reconstruct_inputs(payload):
    from scieasy.core.proxy import ViewProxy
    from scieasy.core.storage.ref import StorageReference
    from scieasy.core.types.base import TypeSignature
    from scieasy.core.types.registry import TypeRegistry

    raw_inputs = payload.get("inputs", {})
    result = {}
    for key, value in raw_inputs.items():
        if isinstance(value, dict) and "backend" in value and "path" in value:
            ref = StorageReference(...)
            type_chain = value.get("metadata", {}).get("type_chain", ["DataObject"])
            # Resolve the most specific class known to the registry.
            cls = TypeRegistry.resolve(type_chain) or DataObject
            sig = TypeSignature(type_chain=type_chain)
            # Wrap in ViewProxy; callers can upgrade to a typed instance via
            # their port-aware layer or by constructing cls from the ref.
            result[key] = ViewProxy(storage_ref=ref, dtype_info=sig)
        else:
            result[key] = value
    return result
```

(The exact mapping from `type_chain` back to a concrete subclass may need a small helper in `TypeRegistry`; that helper is listed in the impact scope.)

### Alternatives considered

- **Keep all domain subtypes in core (D2 Option A)**: preserves the current import paths and test layout. Rejected because it contradicts CLAUDE.md §2.3 and makes the core untestable without implicit assumptions about imaging. The audit of `src/scieasy/blocks/` to update `accepted_types=[Image]` → `accepted_types=[Array]` is routine.
- **Single `dims: str` like OptEasy (D1 Option C)**: one-line schema, zero validation. Rejected because it cannot express per-class required-axes constraints, cannot handle axis names longer than one character (`"lambda"`, `"wavenumber"`, `"mz"`), and gives up the typed-class contract that makes port checking work in SciEasy. OptEasy gets away with this because it is imaging-only.
- **New base class `SpatialBlock` / `SpectralBlock` / `AxisIteratingBlock` (D3 Option A)**: aesthetically tidy, but creates a new layer of the inheritance tree for every dimensional pattern and forces block authors to choose a base class before they understand their problem. A utility function gives the same capability without the commitment. CLAUDE.md §7.2 explicitly favours composition.
- **Use `pint` for units (D6 Option B)**: mature, well-tested, handles dimensional algebra. Rejected for Phase 10 on cold-start grounds: every subprocess worker imports Python fresh, and `pint` adds 200–400 ms to that. For a workflow with 50 blocks, that is 10–20 seconds of wall-clock overhead unconditionally. A 50-line self-written quantity class covers 99% of actual SciEasy metadata and can be swapped for pint later without API changes.
- **Forbid threads entirely (D8 Option A)**: simpler to explain but costs us the ability to use libraries like `torch.nn.DataParallel` or any numpy operation that internally spawns MKL/OpenBLAS threads. Those "threads" already exist implicitly in numpy code; forbidding explicit thread use in blocks would be arbitrary and inconsistent. Rejected.
- **Auto-detect VRAM-aware GPU slot count (D10)**: tried to match physical VRAM against declared `gpu_memory_gb` to compute "how many cellpose instances can coexist". Rejected for Phase 10 because `gpu_memory_gb` is block-declared, not enforced, and because VRAM monitoring requires nvml bindings (`pynvml`) which are platform-specific and another dependency. The simpler "physical GPU count with user override" covers 90% of cases.
- **Deep worker-side type reconstruction returning concrete subclass instances (D11 Option B maximalist)**: instead of leaving reconstructed inputs as `ViewProxy`, construct `Image(storage_ref=..., ...)` directly so that downstream code sees typed instances. Rejected because it would make `reconstruct_inputs` responsible for invoking each subclass's `__init__` with the right arguments, which we cannot generically do (different subclasses have different required metadata). The middle ground is: scan the registry (D11), map `type_chain` to a concrete class for signature matching, but still return a `ViewProxy`. Block authors call `item.view()` or `item.to_memory()` in the usual way; the registry-resolved class is used only for `TypeSignature` and port validation.

### Consequences

- **Phase 10 becomes a clean start for imaging.** The `scieasy-blocks-imaging` package can own its own type hierarchy without fighting core. 6D data is a first-class supported shape, not a cast-to-Array workaround.
- **Core shrinks by several files' worth of domain code.** `src/scieasy/core/types/array.py` loses four subclass definitions; `series.py`, `dataframe.py`, `composite.py` lose their domain subclasses similarly (audit will confirm exact counts). Each deleted class reappears inside the appropriate plugin package.
- **Every block that referenced a domain type directly must be updated.** Core built-in blocks (`MergeCollection`, `FilterCollection`, `SliceCollection`, maybe `TransformBlock`) currently declare `accepted_types=[Image]` in some test fixtures. These become `accepted_types=[Array]` with optional constraint helpers. Tests under `tests/blocks/` that `from scieasy.core.types.array import Image` must either switch to `Array` or be marked as requiring `scieasy-blocks-imaging` installed (see impact scope).
- **Metadata becomes typed.** Pydantic-validated fields are a breaking change to the current free-dict interface. `DataObject.metadata` becomes a property returning `self.user` with a `DeprecationWarning`; callers relying on it for domain metadata (e.g., `img.metadata["pixel_size"]`) will see warnings and should migrate to `img.meta.pixel_size` during Phase 10.
- **Subprocess cold start cost grows by ~50 ms per worker.** `TypeRegistry.scan()` adds the entry-point iteration to every worker startup. Acceptable because startup is already dominated by Python interpreter boot.
- **`ResourceManager` becomes meaningfully throttling.** With `gpu_slots > 0` by default and scheduler concurrency fixed (ADR-018 Addendum 1), GPU block dispatch is now actually gated. Users on multi-GPU machines see parallel execution; users on single-GPU machines see serial GPU access without spinning.
- **Cellpose parallelism story is documented.** Block authors have three clear options: (a) Tier 1 setup+process_item for simple per-item processing, (b) Tier 2 override `run()` for library-native batching (cellpose, stardist), (c) L2 fan-out via SplitCollection for multi-GPU.
- **Block-developer docs must be updated.** Thread policy, setup/teardown, metadata conventions, axis semantics, and the fan-out pattern all need explicit documentation. This is tracked as Deliverable B in issue #255 and will land in a separate PR.
- **Test fixtures across `tests/` need a one-shot migration.** Roughly 75 `Image(...)` instantiations across 17 test files must be updated to pass `axes=[...]`. A shim can be introduced temporarily (`def _test_image(...): return Image(axes=["y","x"], ...)`) to minimise diff noise.
- **AI block generator templates must be updated.** ADR-013 / ADR-027 cross-reference: AI-generated blocks in Phase 9 produced code using `Image` imported from core. Generated code must be regenerated to import from `scieasy_blocks_imaging.types`, or the validator (ADR-013 §7.1) must reject core-Image imports.

### Detailed impact scope

#### New files

| File | Contents |
|---|---|
| `src/scieasy/utils/axis_iter.py` | `iterate_over_axes(source, operates_on, func)` utility (D3). ~80 lines including docstrings and `BroadcastError` raises. |
| `src/scieasy/utils/constraints.py` | Port constraint helper factory functions (D4 context): `has_axes(*required)`, `has_exact_axes(*axes)`, `has_shape(ndim)`, etc. Small module, ~40 lines, used in port `constraint=` kwargs. |
| `src/scieasy/core/units.py` | `PhysicalQuantity` dataclass + unit tables + Pydantic integration (D6). ~120 lines. |
| `src/scieasy/core/meta/__init__.py` | Public exports for `FrameworkMeta`, `with_meta` helper, `ChannelInfo` BaseModel used by plugins (D5). |
| `src/scieasy/core/meta/framework.py` | `FrameworkMeta` BaseModel implementation. ~30 lines. |

#### Rewritten files

| File | Current state | New state | Detailed changes |
|---|---|---|---|
| `src/scieasy/core/types/array.py` | Defines `Array` with `axes: ClassVar`, plus `Image`, `MSImage`, `SRSImage`, `FluorImage` subclasses. 84 lines. | `Array` only, with instance-level `axes`, class-level `required_axes`/`allowed_axes`/`canonical_order`, `_validate_axes` method. New `sel()` and `iter_over()` methods per D4. No domain subclasses. | **Delete** lines 62–83 (all `Image`-family subclasses). **Change** `Array` constructor: `axes` becomes a required keyword argument (`axes: list[str]`). **Add** `required_axes`, `allowed_axes`, `canonical_order` ClassVars (all default to empty/None). **Add** `_validate_axes` method called from `__init__`. **Add** `sel(**kwargs)` method (~40 lines). **Add** `iter_over(axis)` generator method (~20 lines). **Remove** the class-level `axes: ClassVar` declaration. |
| `src/scieasy/core/types/base.py` | `DataObject.__init__(metadata, storage_ref)`, single free-dict metadata field, JSON validator. | `DataObject.__init__(framework, meta, user, storage_ref)` with three slots. Backward-compat `metadata` property delegating to `user`. | **Add** `framework: FrameworkMeta`, `meta: BaseModel`, `user: dict` fields. **Add** `with_meta(**changes)` method. **Keep** `metadata` as `@property` returning `self.user` with `DeprecationWarning`. **Update** JSON-serialisability check to cover `user` dict only (framework and meta use Pydantic's own serialisation). **Update** `TypeSignature.from_type` to include `required_axes` when the class has them (so the signature carries the constraint into port checks). |
| `src/scieasy/core/types/series.py` | `Series` base class; domain subclasses if present. | `Series` only. | **Delete** any `Spectrum`, `RamanSpectrum`, `MassSpectrum` class definitions (audit — some may not exist yet). |
| `src/scieasy/core/types/dataframe.py` | `DataFrame` base; domain subclasses. | `DataFrame` only. | **Delete** `PeakTable`, `MetabPeakTable` if present. |
| `src/scieasy/core/types/composite.py` | `CompositeData`; domain subclasses. | `CompositeData` only. | **Delete** `AnnData`, `SpatialData` if present. |
| `src/scieasy/blocks/process/process_block.py` | `ProcessBlock` with `process_item(self, item, config)` 2-arg signature, default `run()` iterates and calls `process_item`. | `ProcessBlock` with `setup(config)`, `teardown(state)`, `process_item(self, item, config, state=None)` 3-arg signature, default `run()` calls `setup`, iterates, calls `teardown` in finally. | **Add** `setup` and `teardown` methods (default no-op). **Change** `process_item` signature to accept `state=None` (backward-compatible — existing 2-arg overrides continue to work because they ignore the new parameter). **Change** `run()` to wrap iteration in `state = self.setup(config); try: ... finally: self.teardown(state)`. |
| `src/scieasy/engine/runners/worker.py` | `main()` parses stdin, imports block, runs it. `reconstruct_inputs` creates bare `ViewProxy` with `DataObject` type chain when registry info is absent. | `main()` scans `TypeRegistry` entry-points first. `reconstruct_inputs` resolves `type_chain` to the most specific registered class. | **Add** `TypeRegistry.scan()` call at the top of `main()` before `reconstruct_inputs`. **Add** import of `TypeRegistry`. **Change** `reconstruct_inputs` to call `TypeRegistry.resolve(type_chain)` (new helper) and pass the resolved class into `TypeSignature`. **No change** to output serialisation path. |
| `src/scieasy/engine/resources.py` | `ResourceManager.__init__(gpu_slots: int = 0, ...)`. `ResourceRequest.max_internal_workers` exists but is not officially enforced. | `ResourceManager.__init__(gpu_slots: int | None = None, ...)` with auto-detect. Formally document `max_internal_workers` as the block author's declaration of intended internal parallelism. | **Change** default of `gpu_slots` to `None`. **Add** `_auto_detect_gpu_slots()` module function. **Add** one-time WARNING log when detected slots is 0 but a GPU block is scheduled. **Update** docstrings of `ResourceRequest.max_internal_workers` and `effective_cpu` to point to ADR-027 D8 for the thread-policy context. |
| `src/scieasy/core/types/registry.py` | `TypeRegistry` with register/scan for core types. | `TypeRegistry` with a new `resolve(type_chain: list[str]) -> type | None` helper that finds the most specific registered class matching a chain. | **Add** `resolve(type_chain)` method that walks the chain from most-specific to least-specific and returns the first match. **Ensure** `scan()` is idempotent (safe to call from worker subprocess every startup). |

#### Modified files

| File | Changes |
|---|---|
| `src/scieasy/blocks/io/adapters/tiff_adapter.py` | **Change** line 26 `img = Image(...)` to import `Image` from `scieasy_blocks_imaging.types` (plugin) if available, else raise a clear error. Alternatively, the built-in TIFF adapter can be moved entirely to `scieasy-blocks-imaging` as part of Phase 10. Final decision deferred to the implementation ticket but captured here for visibility. |
| `src/scieasy/blocks/process/builtins/*.py` (MergeCollection, FilterCollection, SliceCollection, TransformBlock, MergeBlock, SplitBlock) | **Audit** each for `accepted_types=[Image]` or similar domain-type references. **Change** to `accepted_types=[Array]` with optional constraint helpers. These built-ins are domain-agnostic by design and must not import from plugins. |
| `src/scieasy/blocks/base/ports.py` | **Add** integration with `has_axes` constraint helper (constraint is the existing mechanism; no new field). **Update** `port_accepts_signature` to also check `TypeSignature.required_axes` compatibility (target port's required axes must be a subset of source type's required axes). |
| `src/scieasy/api/routes/blocks.py` | **Audit** endpoints that return block schemas. If any hardcode domain-type names, generalise to read from `TypeRegistry`. |
| `src/scieasy/ai/validators/*.py` (Phase 9 code generator validators) | **Update** type-reference checks so that AI-generated blocks cannot import `Image` from `scieasy.core.types.array` (it is no longer there). Validator must enforce plugin imports for domain types. |
| `tests/core/test_types.py` | **Update** ~3 `Image(...)` instantiations: either use `Array` directly with `axes=["y","x"]`, or install `scieasy-blocks-imaging` as a test dependency. Chosen approach: switch to `Array` where the test is actually about core behaviour, keep `Image` imports in imaging-specific tests that live under `scieasy-blocks-imaging/tests/`. |
| `tests/core/test_dataobject_extended.py` | **Update** ~1 instantiation per above. |
| `tests/core/test_composite.py` | **Update** ~1 instantiation. |
| `tests/core/test_proxy.py` | **Update** ~1 instantiation. |
| `tests/core/test_collection.py` | **Update** ~21 instantiations. Largest migration. Most use `Image` as a generic Collection fixture; all can switch to `Array(axes=["y","x"], ...)`. |
| `tests/blocks/test_block_base.py` | **Update** ~16 instantiations per above. |
| `tests/blocks/test_collection_blocks.py` | **Update** ~1 instantiation. |
| `tests/blocks/test_adapters.py` | **Update** ~1 instantiation. (May move entirely to imaging plugin tests.) |
| `tests/blocks/test_ports.py` | **Update** ~3 instantiations. |
| `tests/blocks/test_lazy_list.py` | **Update** ~3 instantiations. |
| `tests/blocks/test_app_block.py` | **Update** ~2 instantiations. |
| `tests/engine/test_checkpoint.py` | **Update** ~7 instantiations. |
| `tests/integration/test_block_sdk_e2e.py` | **Update** ~1 instantiation. |
| `tests/integration/test_multimodal_workflow.py` | **Update** ~7 instantiations OR move this test into `scieasy-blocks-imaging` as an integration test that requires all three plugin packages installed. Phase 10 decision: keep in core repo but mark with a pytest marker `@pytest.mark.requires_imaging` that is skipped when the plugin is not installed. |
| `tests/api/test_data.py` | **Update** ~1 instantiation. |
| `tests/workflow/test_validator.py` | **Update** 1 `from scieasy.core.types.array import Array, Image` → `Array` only. |
| `tests/ai/test_validator.py` | **Update** ~4 instantiations. AI validator tests verify the "you cannot import Image from core" rule. |
| `tests/ai/test_type_generator.py` | **Update** ~2 instantiations. |

#### Deleted files

No outright deletions. Domain subclasses are moved (deleted from core, recreated in plugins), but the Phase 10 plan tracks plugin-side additions as a separate work package in the `scieasy-blocks-imaging` repo scaffold task, not as file creations inside this repo.

#### New tests required

| Test file | Coverage |
|---|---|
| `tests/core/test_array_axes.py` | Instance-level axes, `required_axes` / `allowed_axes` validation, 6D instantiation, axis ordering, `sel()` single-index, `sel()` slice, `iter_over()` memory-bounded iteration, metadata inheritance across `sel`/`iter_over`. |
| `tests/utils/test_axis_iter.py` | `iterate_over_axes` happy path (3D input, iterate over `z`), shape-mismatch → BroadcastError, `operates_on` not a subset → BroadcastError, metadata preservation, `source.__class__` preservation on output. |
| `tests/core/test_units.py` | `PhysicalQuantity` construction, unit validation, `to()` conversion within a kind, cross-kind rejection, `__lt__` / `__eq__`, Pydantic integration (round-trip a model with a PhysicalQuantity field through `model_dump_json` / `model_validate_json`). |
| `tests/core/test_stratified_metadata.py` | `FrameworkMeta` auto-population, `with_meta()` immutable update, `metadata` deprecation warning, Pydantic-backed `meta` field round-trip. |
| `tests/blocks/test_process_block_lifecycle.py` | `setup` called once before iteration, `teardown` called once after, `state` passed to `process_item`, `teardown` called even on error via `finally`. |
| `tests/engine/test_worker_type_registry.py` | Worker subprocess can reconstruct a `FluorImage` instance from a `StorageReference` when the plugin is installed. Simulated by injecting a test-only type registration. |
| `tests/engine/test_resource_manager_gpu_autodetect.py` | `gpu_slots=None` triggers auto-detect; mocked `torch.cuda.device_count` returns various values; fallback to `nvidia-smi`; explicit integer respected. |

#### Documentation impact

| Document | Required changes |
|---|---|
| `docs/architecture/ARCHITECTURE.md` §4.1 (Base type hierarchy) | **Rewrite** the class diagram: core shows only the 7 base types with a "domain subtypes provided by plugin packages" annotation below. **Remove** references to `Image`, `MSImage`, `FluorImage`, `SRSImage`, `Spectrum`, `AnnData`, `SpatialData`, `PeakTable` from the core diagram. **Add** an "extended example (plugin-provided)" inset showing an imaging plugin's hierarchy as illustrative. |
| `docs/architecture/ARCHITECTURE.md` §4.1 (Named axes on Array) | **Rewrite** the `axes` example code to show instance-level axes: `Image(axes=["t","z","c","y","x"], shape=(10,30,4,512,512))`. **Add** discussion of `required_axes` / `allowed_axes` / `canonical_order`. **Add** the 6D axis alphabet table (`t, z, c, lambda, y, x`) with descriptions. |
| `docs/architecture/ARCHITECTURE.md` §4.5 (Broadcast utility) | **Add** cross-reference to `scieasy.utils.axis_iter.iterate_over_axes` (new sibling function). Describe the split of responsibility: `broadcast_apply` = low-dim → high-dim projection, `iterate_over_axes` = single Array extra-dim iteration. |
| `docs/architecture/ARCHITECTURE.md` §5.1 (Block base class) | **Add** `setup(config)` and `teardown(state)` to the ProcessBlock contract description. **Update** `process_item` signature to 3-arg. |
| `docs/architecture/ARCHITECTURE.md` §6.4 (Resource management) | **Update** to note that `gpu_slots` auto-detects by default in Phase 10 and references ADR-027 D10. |
| `docs/architecture/ARCHITECTURE.md` §4.4 / metadata discussion | **Rewrite** to describe the `framework` / `meta` / `user` three-slot model. **Add** example of a Pydantic `Meta` subclass on a domain type. |
| `docs/architecture/ARCHITECTURE.md` §5.4 (Block and type distribution) | **Add** note that Phase 10 moves all domain types out of core. Plugin packages are the only path. Core contains only base types. |
| `docs/architecture/ARCHITECTURE.md` Appendix A (multimodal example) | **Audit** code snippets that import `Image`, `MSImage`, etc. from core. Update to import from plugin packages with `from scieasy_blocks_imaging.types import FluorImage`. |
| `docs/architecture/PROJECT_TREE.md` | **Remove** `Image`, `MSImage`, `SRSImage`, `FluorImage` from `core/types/array.py` description. **Add** `utils/axis_iter.py`, `utils/constraints.py`, `core/units.py`, `core/meta/__init__.py`, `core/meta/framework.py` entries. |
| `docs/guides/block-sdk.md` | **Rewrite** all `from scieasy.core.types.array import Image` imports to use plugin packages. **Add** section on setup/teardown hooks. **Add** section on metadata conventions (`img.meta.pixel_size`, `with_meta()`). **Add** subsection on L2 fan-out as the recommended Collection-level parallelism pattern. **Add** explicit thread policy paragraph. |
| `docs/testing/phase-5-to-8-human-tests.md` and `phase-5-human-tests.md` | **Update** example snippets that import core `Image`. |
| `docs/adr/ADR.md` | This ADR (ADR-027). |
| `CHANGELOG.md` | **Add** entry under `[Unreleased]` → `### Added` for ADR-027. |

#### Out of scope

- **Level 2 laziness** (`SlicedStorageReference` threaded through ViewProxy). Deferred to Phase 11+.
- **`pint` integration**. `PhysicalQuantity` is the Phase 10 unit story; pint is a future option if dimensional algebra is ever needed.
- **Block-internal `parallel_slices` or `ThreadPoolExecutor` helpers** built into the framework. Block authors may use threads (D8) but the framework provides no blessed helper in Phase 10.
- **VRAM-aware GPU slot calculation**. Physical GPU count with user override is sufficient for Phase 10.
- **New block states, new BlockEvent types, new ExecutionMode variants**. All runtime protocols remain as ADR-018 defined them.
- **Changes to `Collection`, `ViewProxy`, or storage backends beyond the registry scan requirement**.
- **Any code changes in this PR**. This ADR is documentation only. Implementation lands under Phase 10 implementation tickets, each referencing specific ADR-027 sections.
- **Any updates to `docs/architecture/ARCHITECTURE.md`, `docs/guides/block-sdk.md`, or `docs/architecture/PROJECT_TREE.md` in this PR**. Those updates are tracked as Deliverable B of issue #255 and will ship in a follow-up PR with its own gate workflow.

---

## ~~ADR-027 Addendum 1: Worker subprocess type reconstruction returns typed DataObject instances, not ViewProxy~~

**Status**: ~~proposed~~ → **deprecated (superseded by ADR-031)**
**Date**: 2026-04-06

### Purpose

ADR-027 D11 (worker subprocess `TypeRegistry.scan()`) and ADR-027 D5 (stratified Pydantic metadata) are mutually inconsistent as written. This Addendum resolves the contradiction by formally adopting "Option B" — `worker.reconstruct_inputs` returns typed `DataObject` instances rather than `ViewProxy`. It also locks down the per-base-class reconstruction contract, the `Meta` Pydantic constraints, the `PhysicalQuantity` Pydantic integration approach, and the resulting role of `ViewProxy` after this Addendum.

This Addendum **does not** modify any of the other ADR-027 decisions (D1–D10 stand unchanged) and does **not** revise the discussion-table row for D11 (the high-level commitment "worker scans entry-points so plugin types can be resolved" remains correct). It supersedes only the specific pseudocode example inside D11's Decision section and the corresponding entry under "Alternatives considered" that rejected typed reconstruction.

### Context

ADR-027 D11's "Decision" section specifies that the worker subprocess should call `TypeRegistry.resolve(type_chain)` and use the resolved class — but the code sample then computes `cls` and immediately discards it, returning a bare `ViewProxy`:

```python
# From ADR-027 D11 (the version being clarified)
def reconstruct_inputs(payload):
    ...
    for key, value in raw_inputs.items():
        if isinstance(value, dict) and "backend" in value and "path" in value:
            ref = StorageReference(...)
            type_chain = value.get("metadata", {}).get("type_chain", ["DataObject"])
            cls = TypeRegistry.resolve(type_chain) or DataObject     # ← computed
            sig = TypeSignature(type_chain=type_chain)
            result[key] = ViewProxy(storage_ref=ref, dtype_info=sig) # ← cls discarded
        else:
            result[key] = value
    return result
```

D11's "Alternatives considered" then explicitly rejects "deep type reconstruction" with the rationale:

> Rejected because it would make `reconstruct_inputs` responsible for invoking each subclass's `__init__` with the right arguments, which we cannot generically do (different subclasses have different required metadata). The middle ground is: scan the registry (D11), map `type_chain` to a concrete class for signature matching, but still return a `ViewProxy`.

That rationale was correct **before** D5 unified the constructor surface. With D5 in effect, every `DataObject` subclass takes the same core fields (`framework: FrameworkMeta`, `meta: BaseModel`, `user: dict`, `storage_ref: StorageReference | None`) plus a small, base-class-specific set of geometry fields (e.g. `axes`, `shape`, `dtype`, `chunk_shape` for `Array`). Subclasses no longer have wildly divergent `__init__` signatures, so the rejection reason no longer applies.

Meanwhile, every other ADR-027 decision and every example in `docs/guides/block-sdk.md` (rewritten in PR #258) assumes block authors receive a real typed instance. The Cellpose example is representative:

```python
def process_item(self, item: FluorImage, config, state):
    if item.meta.pixel_size < Q(0.2, "um"):                  # ← item.meta
        ...
    new = item.with_meta(pixel_size=Q(0.216, "um"))           # ← with_meta()
    img_2d = item.to_memory()
    masks, _, _, _ = state.eval(img_2d, ...)
    return Image(axes=item.axes, shape=masks.shape, dtype=masks.dtype, meta=item.meta)
```

`ViewProxy` has none of `meta`, `with_meta`, or `Image`-typed isinstance compatibility. It was designed in ADR-007 as a thin lazy accessor with `slice / to_memory / iter_chunks / shape` only. If the worker really returned `ViewProxy`, every block in Phase 10 would have to:

1. Inspect `item.dtype_info.type_chain` instead of using `isinstance`.
2. Read metadata via a side channel (the `storage_ref.metadata` dict), bypassing all Pydantic validation.
3. Lose the `with_meta` immutable update path entirely.

This effectively cancels D5 and D7 inside the worker, which is the only place they matter.

The contradiction was not noticed during ADR-027 authoring because D5, D7, and D11 were drafted as independent table rows rather than as a single integrated contract. This Addendum integrates them.

### Discussion points and resolution

| # | Topic | Options discussed | Final decision |
|---|---|---|---|
| 1 | What should `worker.reconstruct_inputs` return for each input? | (A) `ViewProxy` (current ADR-027 D11). (B) Typed `DataObject` instance with `storage_ref` set but payload not yet read. (C) A new `LazyDataObject` mix-in: typed instance that masquerades as `FluorImage` but defers payload load through proxy semantics. | **Decision: (B).** D5 unified the constructor surface, removing the original rationale for rejecting (B). (B) makes the in-worker block API identical to the externally-tested API: `item.meta.pixel_size`, `item.with_meta(...)`, `item.iter_over("z")`, `isinstance(item, FluorImage)` all behave the same. Lazy loading is preserved because a `FluorImage(storage_ref=ref, ...)` with `storage_ref` set does not read its payload until `to_memory()` / `view()` / `sel()` / `iter_over()` is called — the lazy contract from ADR-007 is satisfied at the method level, not at the wrapper-class level. (A) cancels D5/D7 inside the worker, as documented in the Context section. (C) introduces a third concept (LazyDataObject) without solving any problem that (B) does not already solve. |
| 2 | Where lives the per-base-class knowledge of "how to reconstruct from a metadata sidecar"? | (A) A big `if cls is Array: ... elif cls is DataFrame: ...` chain inside `worker.py`. (B) A classmethod hook `_reconstruct_extra_kwargs(metadata: dict) -> dict` declared on each base class; worker.py invokes it generically. (C) Pydantic full reflection over class fields at runtime. | **Decision: (B).** (A) puts plugin-specific knowledge in the engine, violating CLAUDE.md §7.3 ("No mixing core contracts with plugin logic"). (C) is too magical and breaks for fields the framework deliberately keeps non-Pydantic, such as `Array.axes` (a list[str] that has class-level validation logic) and the geometry tuples. (B) is a small, explicit, well-documented contract: each base class declares what it needs to round-trip, the worker calls the hook generically. Plugin subclasses inherit the hook from their base class and almost never need to override it (the only exception is composite types whose slots have plugin-specific structure, which have their own slot reconstruction story). |
| 3 | What constraints does a subclass's `Meta` Pydantic model have to satisfy to be reconstructable across the subprocess boundary? | (A) Any `pydantic.BaseModel` works; we hope for the best. (B) Frozen, no `PrivateAttr`, all fields must round-trip through `model_dump_json` / `model_validate_json`. | **Decision: (B).** The framework round-trips `Meta` through JSON every time a block runs, because the engine and worker live in different processes. PrivateAttr fields, fields holding live file handles, and fields with arbitrary types that lack a serializer all break this round-trip silently or noisily. Documenting the constraint as part of the `Meta` contract prevents Phase 11+ plugin authors from hitting confusing reconstruction errors. The framework provides `PhysicalQuantity`, `ChannelInfo`, and a small set of other primitives that all comply; plugin authors compose their `Meta` from these and from primitive Python types (str/int/float/bool/datetime/list/dict). |
| 4 | How does `PhysicalQuantity` (ADR-027 D6) integrate with Pydantic so that `pixel_size: PhysicalQuantity` works without per-field boilerplate? | (A) Pydantic v2 `__get_pydantic_core_schema__` registered on the dataclass — fully transparent to plugin authors. (B) Per-field `field_serializer` / `field_validator` that each plugin author writes. | **Decision: (A).** Plugin authors writing `pixel_size: PhysicalQuantity` should not need to know anything about Pydantic internals. The integration cost is paid once inside `scieasy.core.units` (when ADR-027 D6 is implemented) and is invisible to downstream code. The serialised JSON form is `{"value": 0.108, "unit": "um"}`, which is what plugin authors see if they ever inspect the wire format. |
| 5 | What is the role of `ViewProxy` after this Addendum? | (A) Delete entirely, fold its methods into `Array`. (B) Keep `ViewProxy` as the return type of `Array.view()` for blocks that genuinely need explicit chunk-by-chunk reading without materialising the whole array. (C) Make `ViewProxy` strictly internal to backends. | **Decision: (B).** ViewProxy is still useful for blocks that read 100 GB Zarr stores chunk-by-chunk, where the block author wants explicit control over which chunks are touched. Examples: a streaming statistics block that computes per-chunk means, an ROI extraction block that reads only the requested spatial region. After this Addendum, `ViewProxy` is **demoted from "engine-injected input type"** to **"opt-in helper accessed via `item.view()`"**. The default block experience is `item.to_memory()` / `item.sel(...)` / `item.iter_over(...)`. Blocks that need ViewProxy explicitly call `item.view()`. |

### Decision

#### D11′. `worker.reconstruct_inputs` returns typed DataObject instances

Replace the D11 pseudocode with the following. The function dispatches three cases — `Collection`, single `DataObject`, scalar pass-through — and delegates per-item reconstruction to a private helper:

```python
# scieasy/engine/runners/worker.py

def reconstruct_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct typed DataObject inputs from the JSON wire payload.

    ADR-027 D11 + Addendum 1: Returns typed instances (e.g. FluorImage),
    not ViewProxy. Lazy loading is preserved at the method level: the
    returned instance has storage_ref set but does not read payload data
    until to_memory() / view() / sel() / iter_over() is called.
    """
    from scieasy.core.types.collection import Collection
    from scieasy.core.types.registry import TypeRegistry
    from scieasy.core.types.base import DataObject

    raw_inputs = payload.get("inputs", {})
    result: dict[str, Any] = {}

    for key, value in raw_inputs.items():
        if isinstance(value, dict) and value.get("_collection"):
            # Collection of typed items
            items = [_reconstruct_one(item) for item in value["items"]]
            item_type_name = value.get("item_type", "DataObject")
            item_type = TypeRegistry.resolve([item_type_name]) or DataObject
            result[key] = Collection(items, item_type=item_type)
        elif isinstance(value, dict) and "backend" in value and "path" in value:
            # Single typed DataObject
            result[key] = _reconstruct_one(value)
        else:
            # Scalar / pass-through (config-derived inputs that aren't DataObjects)
            result[key] = value

    return result


def _reconstruct_one(payload_item: dict) -> "DataObject":
    """Reconstruct one typed DataObject instance from a serialised payload item.

    The serialised form is the same JSON dict that worker.serialise_outputs
    produces, namely:
        {
            "backend": "zarr",
            "path":    "/path/to/store",
            "format":  "...",
            "metadata": {
                "type_chain":  ["DataObject", "Array", "Image", "FluorImage"],
                "framework":   { ...FrameworkMeta fields... },
                "meta":        { ...Meta-model fields, JSON-serialised... },
                "user":        { ...free-form dict... },
                # base-class extras (e.g. axes/shape/dtype/chunk_shape for Array)
                "axes":        ["t", "z", "c", "y", "x"],
                "shape":       [10, 30, 4, 512, 512],
                "dtype":       "uint16",
                "chunk_shape": [1, 1, 1, 512, 512],
            },
        }
    """
    from scieasy.core.types.registry import TypeRegistry
    from scieasy.core.types.base import DataObject
    from scieasy.core.storage.ref import StorageReference
    from scieasy.core.meta import FrameworkMeta

    ref = StorageReference(
        backend=payload_item["backend"],
        path=payload_item["path"],
        format=payload_item.get("format"),
        metadata=payload_item.get("metadata", {}),
    )
    md = payload_item.get("metadata", {})

    # 1. Resolve the most specific class registered for this type chain.
    type_chain = md.get("type_chain", ["DataObject"])
    cls = TypeRegistry.resolve(type_chain) or DataObject

    # 2. Reconstruct the three metadata slots.
    framework = FrameworkMeta.model_validate(md.get("framework", {}))

    meta_cls = getattr(cls, "Meta", None)
    if meta_cls is not None:
        meta = meta_cls.model_validate(md.get("meta", {}))
    else:
        meta = None

    user = dict(md.get("user", {}) or {})

    # 3. Ask the base class which extra kwargs it wants from the metadata.
    if hasattr(cls, "_reconstruct_extra_kwargs"):
        extra_kwargs = cls._reconstruct_extra_kwargs(md)
    else:
        extra_kwargs = {}

    # 4. Construct the typed instance. storage_ref is set but payload not read.
    return cls(
        storage_ref=ref,
        framework=framework,
        meta=meta,
        user=user,
        **extra_kwargs,
    )
```

#### D11′ companion. `_reconstruct_extra_kwargs` classmethod hook

Each of the six core base classes implements a `classmethod _reconstruct_extra_kwargs(metadata: dict) -> dict` that returns the keyword arguments that the class's `__init__` needs **beyond** the four core fields (`storage_ref`, `framework`, `meta`, `user`). The hook is called by `_reconstruct_one`. Plugin subclasses inherit the hook from their base class and almost never need to override it.

```python
# scieasy/core/types/base.py
class DataObject:
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        """Return base-class-specific kwargs to pass to __init__ during
        worker subprocess reconstruction. Default: no extra kwargs."""
        return {}


# scieasy/core/types/array.py
class Array(DataObject):
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        return {
            "axes":        list(metadata.get("axes", [])),
            "shape":       tuple(metadata["shape"]) if metadata.get("shape") else None,
            "dtype":       metadata.get("dtype"),
            "chunk_shape": tuple(metadata["chunk_shape"]) if metadata.get("chunk_shape") else None,
        }


# scieasy/core/types/series.py
class Series(DataObject):
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        return {
            "index_name": metadata.get("index_name"),
            "value_name": metadata.get("value_name"),
            "length":     metadata.get("length"),
        }


# scieasy/core/types/dataframe.py
class DataFrame(DataObject):
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        return {
            "columns":   list(metadata.get("columns", [])),
            "row_count": metadata.get("row_count"),
            "schema":    dict(metadata.get("schema", {})),
        }


# scieasy/core/types/text.py
class Text(DataObject):
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        return {
            "format":   metadata.get("format", "plain"),
            "encoding": metadata.get("encoding", "utf-8"),
        }


# scieasy/core/types/artifact.py
class Artifact(DataObject):
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        return {
            "mime_type":   metadata.get("mime_type"),
            "description": metadata.get("description", ""),
        }


# scieasy/core/types/composite.py
class CompositeData(DataObject):
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        """Composite types reconstruct nested slots recursively.

        The serialised form of a composite item carries a "slots" dict
        whose values are themselves single-DataObject payload items
        (with backend/path/metadata). We delegate to _reconstruct_one
        to rebuild each slot.
        """
        slot_payloads = metadata.get("slots", {}) or {}
        slots = {
            slot_name: _reconstruct_one(slot_payload)
            for slot_name, slot_payload in slot_payloads.items()
        }
        return {"slots": slots}
```

Plugin subclasses that add fields beyond their base class can override the hook and call `super()._reconstruct_extra_kwargs(metadata)` to pick up the parent class's extras:

```python
# Hypothetical plugin subclass that adds a wavenumber_axis numeric field
# (not a Meta field — it is geometry-like, so it lives outside Meta)
class HyperspectralImage(Image):
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        kwargs = super()._reconstruct_extra_kwargs(metadata)
        kwargs["wavenumber_axis"] = list(metadata.get("wavenumber_axis", []))
        return kwargs
```

In practice, almost all plugin types put their domain fields inside `Meta` (which round-trips automatically via Pydantic) and never need to override this hook. The override path exists for unusual cases.

#### D11′ companion. Symmetric `serialise_outputs` change

`worker.serialise_outputs` must be updated symmetrically so that the wire format `_reconstruct_one` reads is the wire format `serialise_outputs` writes. The output side already produces a metadata sidecar; this Addendum specifies its exact contents:

```python
# scieasy/engine/runners/worker.py

def serialise_outputs(outputs: dict[str, Any], output_dir: str) -> dict[str, Any]:
    """Serialise typed DataObject outputs to the JSON wire format.

    For each output value:
      - If Collection: serialise each item via _serialise_one,
        emit {"_collection": True, "item_type": ..., "items": [...]}
      - If DataObject:  serialise via _serialise_one
      - Else:           pass through scalar / list / dict
    """
    from scieasy.blocks.base.block import Block
    from scieasy.core.types.base import DataObject
    from scieasy.core.types.collection import Collection

    result: dict[str, Any] = {}
    for key, value in outputs.items():
        if isinstance(value, Collection):
            item_payloads = [_serialise_one(Block._auto_flush(item)) for item in value]
            result[key] = {
                "_collection": True,
                "item_type":   value.item_type.__name__ if value.item_type else "DataObject",
                "items":       item_payloads,
            }
        elif isinstance(value, DataObject):
            result[key] = _serialise_one(Block._auto_flush(value))
        elif isinstance(value, (str, int, float, bool, type(None), list, dict)):
            result[key] = value
        else:
            result[key] = str(value)
    return result


def _serialise_one(obj: "DataObject") -> dict:
    """Serialise one typed DataObject to a wire-format payload item.

    The metadata sidecar carries everything _reconstruct_one needs:
    type_chain (for class lookup), framework/meta/user (for metadata),
    and base-class extras (for __init__ kwargs).
    """
    if obj.storage_ref is None:
        # Should never happen — Block._auto_flush is called before us.
        raise RuntimeError(f"Cannot serialise {type(obj).__name__} without storage_ref")

    md: dict[str, Any] = {}

    # type_chain — used by TypeRegistry.resolve in the receiving worker
    md["type_chain"] = obj.dtype_info.type_chain

    # framework slot
    md["framework"] = obj.framework.model_dump(mode="json")

    # meta slot (Pydantic round-trip via JSON mode)
    if obj.meta is not None:
        md["meta"] = obj.meta.model_dump(mode="json")

    # user slot (free dict — already JSON-serialisable per ADR-017)
    md["user"] = dict(obj.user or {})

    # base-class extras: ask the class which fields it wants persisted.
    if hasattr(type(obj), "_serialise_extra_metadata"):
        md.update(type(obj)._serialise_extra_metadata(obj))

    ref = obj.storage_ref
    return {
        "backend":  ref.backend,
        "path":     ref.path,
        "format":   ref.format,
        "metadata": md,
    }
```

`_serialise_extra_metadata` is the symmetric counterpart of `_reconstruct_extra_kwargs`. Each base class implements both:

```python
class Array(DataObject):
    @classmethod
    def _serialise_extra_metadata(cls, obj: "Array") -> dict:
        return {
            "axes":        list(obj.axes),
            "shape":       list(obj.shape) if obj.shape is not None else None,
            "dtype":       str(obj.dtype) if obj.dtype is not None else None,
            "chunk_shape": list(obj.chunk_shape) if obj.chunk_shape is not None else None,
        }
```

The other five base classes implement their own `_serialise_extra_metadata` that mirrors their `_reconstruct_extra_kwargs`. The implementation ticket will write all six pairs.

#### `Meta` Pydantic constraints

Plugin subclasses declaring a `Meta` Pydantic model must obey:

1. **Inherit from `pydantic.BaseModel`**, not from `dataclass` or any other base.
2. **No `PrivateAttr`**. Private state cannot round-trip through JSON.
3. **All fields must be JSON-round-trippable** via `model_dump(mode="json")` and `model_validate`. Acceptable types are: primitive Python (`str`, `int`, `float`, `bool`, `None`), lists and dicts of acceptable types, `datetime`, other Pydantic `BaseModel` whose fields are themselves acceptable, `PhysicalQuantity` (which provides Pydantic v2 integration via `__get_pydantic_core_schema__` — see next subsection), and Pydantic-supplied custom types like `EmailStr`, `HttpUrl`, etc.
4. **Recommended `model_config = ConfigDict(frozen=True)`** so `with_meta(...)` immutability is enforced statically rather than relying on convention. The framework does not strictly require `frozen=True`, but `with_meta` only makes semantic sense if the existing `Meta` is treated as immutable.

The framework enforces (1) and (3) at registration time: when a plugin's `get_types()` callable returns a class with a non-conforming `Meta`, `TypeRegistry` rejects the registration with a clear error message pointing at the offending field. This prevents Phase 11+ plugin authors from discovering serialisation failures only at runtime.

Validation logic lives in `TypeRegistry.register` and is called once per class at scan time, so the cost is paid at startup, not per dispatch.

#### `PhysicalQuantity` Pydantic integration

ADR-027 D6 specified `PhysicalQuantity` as a frozen dataclass. To make `pixel_size: PhysicalQuantity` work inside a `Meta` BaseModel without per-field boilerplate, the `scieasy.core.units` module attaches a Pydantic v2 core schema to the dataclass:

```python
# scieasy/core/units.py (extends ADR-027 D6's specification)

from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from pydantic_core import core_schema
from pydantic import GetCoreSchemaHandler

@dataclass(frozen=True)
class PhysicalQuantity:
    value: float
    unit: str

    # ... existing methods (to, __lt__, __eq__) per ADR-027 D6 ...

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        """Pydantic v2 integration: PhysicalQuantity round-trips as
        {"value": float, "unit": str}.

        Plugin authors writing `pixel_size: PhysicalQuantity` get JSON
        serialisation, JSON validation, and OpenAPI schema generation
        automatically. No field_serializer / field_validator boilerplate
        required.
        """
        def _validate(v: Any) -> "PhysicalQuantity":
            if isinstance(v, PhysicalQuantity):
                return v
            if isinstance(v, dict) and "value" in v and "unit" in v:
                return cls(value=float(v["value"]), unit=str(v["unit"]))
            raise ValueError(
                f"PhysicalQuantity expects {{value, unit}} dict or PhysicalQuantity, got {type(v).__name__}"
            )

        return core_schema.no_info_plain_validator_function(
            _validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda obj: {"value": obj.value, "unit": obj.unit},
                return_schema=core_schema.dict_schema(),
            ),
        )
```

Plugin authors do not see any of this. They write:

```python
class FluorImage(Image):
    class Meta(Image.Meta):
        pixel_size: PhysicalQuantity
        exposure_ms: dict[str, float] | None = None
```

and the framework handles JSON round-trip transparently. When this `Meta` instance is serialised via `model_dump(mode="json")`, `pixel_size` becomes `{"value": 0.108, "unit": "um"}`. When `model_validate` reads it back in the receiving worker, it becomes a `PhysicalQuantity(0.108, "um")` instance again.

The implementation ticket for ADR-027 D6 must include this Pydantic integration, the corresponding test (`tests/core/test_units.py::test_physical_quantity_pydantic_round_trip`), and a smoke test that round-trips a full `FluorImage.Meta` containing several `PhysicalQuantity` fields through `model_dump_json` / `model_validate_json`.

#### `ViewProxy` role after this Addendum

`ViewProxy` is **not removed** by this Addendum. It is **demoted** from "the type the engine injects into block inputs" to "an opt-in helper accessed via `Array.view()` for blocks that need explicit chunk-level reading". Concretely:

- `Array.view()` continues to return `ViewProxy(storage_ref, dtype_info)`. The signature and behaviour of ViewProxy itself are unchanged.
- `Array.to_memory()`, `Array.sel()`, `Array.iter_over()`, and `Array.shape` are now methods on the `Array` instance directly (per ADR-027 D4), without needing to detour through ViewProxy.
- Blocks that read 100 GB Zarr stores chunk-by-chunk continue to call `item.view().slice(...)` or `item.view().iter_chunks(...)`. This is the same code they would have written before this Addendum; the only thing that changes is the **default** path is now `item.to_memory()` / `item.sel(...)` rather than `item.view().to_memory()` / `item.view().slice(...)`.
- `worker.reconstruct_inputs` no longer constructs `ViewProxy` instances at all. The `ViewProxy` import is removed from `worker.py`.

This demotion is consistent with ADR-007 (lazy loading): laziness is now expressed at the **method level** on the typed instance (`to_memory` / `sel` / `iter_over` defer I/O until called) rather than at the **wrapper-class level**. Both achieve the same memory behaviour; the typed-instance approach gives block authors a richer API with no extra cost.

### Alternatives considered

- **Option A: keep ViewProxy as the worker return type and patch around it.** Requires giving `ViewProxy` a `meta` attribute, a `with_meta` method, an `iter_over` / `sel` proxy that round-trips through the underlying type, and isinstance compatibility with plugin classes. Each of these is feasible individually; together they reconstruct most of `DataObject` on the `ViewProxy` side. At that point ViewProxy *is* a DataObject in all but name, and the simpler thing is to use the actual class. Rejected.
- **Option C: introduce `LazyDataObject` mix-in.** A new class that inherits from both `DataObject` and ViewProxy, providing typed-class identity AND proxy semantics. The mix-in could in principle solve the same problem as Option B, but introduces a third concept (alongside ViewProxy and the typed classes) that plugin authors must learn. There is no behaviour LazyDataObject would provide that a plain typed instance with a set `storage_ref` does not already provide. Rejected as unnecessary complexity.
- **Have the engine keep using ViewProxy and run a "type upgrade" pass before invoking the block's `run()`.** This is a variant of Option B that defers reconstruction by one step. It does not change the contract or the implementation cost meaningfully — the upgrade pass would do exactly what `_reconstruct_one` does in Option B. Rejected as a wash.
- **Rewrite D5 to make `DataObject.meta` optional / lazy on ViewProxy.** Reverses the wrong decision. D5 is the right design; D11's pseudocode is the wrong design. Rejected.
- **Defer the resolution to the implementation phase.** Tempting but dangerous: the contradiction is large enough that the implementation ticket would have to either re-litigate this decision or pick one of the bad options under time pressure. Resolving it now in an Addendum keeps the implementation ticket focused on writing code rather than re-arguing architecture.

### Consequences

- **`worker.py` becomes the canonical reference site for typed DataObject reconstruction.** Both `_reconstruct_one` and `_serialise_one` live there and dispatch to base-class hooks. The worker file grows by ~80 lines (the two helpers) but loses the discarded `cls` line and the `ViewProxy` import.
- **Six new pairs of classmethods on the base classes.** Each of `DataObject`, `Array`, `Series`, `DataFrame`, `Text`, `Artifact`, `CompositeData` gains `_reconstruct_extra_kwargs` and `_serialise_extra_metadata`. Total: 12 small classmethods, ~5 lines each. The hook contract is documented in the developer SDK guide as "rarely overridden by plugin authors; framework default is sufficient for almost all subtypes".
- **Plugin `Meta` classes have an explicit constraint set** (frozen, no PrivateAttr, JSON-round-trippable). The constraint is enforced at registration time by `TypeRegistry`, with a clear error message pointing at the offending field. This is a small cost paid once per class at startup, not per dispatch.
- **`PhysicalQuantity` integration with Pydantic is no longer hand-waved.** ADR-027 D6's implementation ticket will include the `__get_pydantic_core_schema__` method and a round-trip test. Plugin authors get transparent JSON serialisation for `pixel_size: PhysicalQuantity` without writing any boilerplate.
- **`ViewProxy` is demoted but not removed.** Existing code that calls `item.view().to_memory()` continues to work. New blocks should prefer `item.to_memory()` directly. The block-sdk.md guide will note (in a future PR — not in this Addendum's scope) that `view()` is the escape hatch for explicit chunk reading; the default path is direct method calls on the typed instance.
- **Tests that asserted `inputs["x"]` is a `ViewProxy` will fail.** I expect ~5–10 such assertions across `tests/`, mostly in early `test_proxy.py` and `test_block_base.py` tests written before D5 was specified. The implementation ticket for D11 must update these to assert `isinstance(inputs["x"], FluorImage)` (or `Array`, depending on the test's domain) instead.
- **No change to the wire format on the engine→worker direction.** The serialised payload already carries a `metadata` dict; this Addendum specifies its exact contents but does not introduce a new transport mechanism. Existing checkpoints continue to load (with a small forward-compat note: `framework`/`meta`/`user` defaults are filled in when loading older checkpoints whose metadata was a flat dict).
- **No change to `D5/D7/D9` decisions.** The metadata stratification, the `setup`/`teardown` hooks, the L2 fan-out pattern — all unchanged. This Addendum touches only the worker reconstruction layer.
- **No change to the `EventBus`, `BlockState`, `Collection`, or `ProcessRegistry` contracts.** This is a worker-internal clarification.

### Detailed impact scope

#### Rewritten files (in the eventual implementation ticket; not in this PR)

| File | Current state | New state | Detailed changes |
|---|---|---|---|
| `src/scieasy/engine/runners/worker.py` | `reconstruct_inputs` returns `ViewProxy`. `serialise_outputs` writes a metadata sidecar but does not split it into framework/meta/user. | `reconstruct_inputs` dispatches to `_reconstruct_one` per item, returns typed `DataObject` instances. `serialise_outputs` dispatches to `_serialise_one`, which writes `type_chain` + `framework` + `meta` + `user` + base-class extras into the metadata sidecar. | **Add** `_reconstruct_one(payload_item)` (~40 lines). **Add** `_serialise_one(obj)` (~30 lines). **Change** `reconstruct_inputs` to call `_reconstruct_one` instead of constructing `ViewProxy` (current ~30 lines → ~25 lines). **Change** `serialise_outputs` to call `_serialise_one` instead of inline serialisation (current ~50 lines → ~35 lines). **Remove** the `ViewProxy` import (no longer needed in worker.py). **Add** `TypeRegistry.scan()` call at top of `main()` per ADR-027 D11 (this part is unchanged from D11). |
| `src/scieasy/core/types/base.py` | `DataObject` has framework/meta/user slots per ADR-027 D5. | Adds `_reconstruct_extra_kwargs(metadata)` and `_serialise_extra_metadata(obj)` classmethods, both returning `{}` by default. | **Add** two classmethods, each ~3 lines (default empty implementation + docstring). |
| `src/scieasy/core/types/array.py` | `Array` per ADR-027 D1 with instance-level `axes`. | Adds `_reconstruct_extra_kwargs` and `_serialise_extra_metadata` covering `axes`, `shape`, `dtype`, `chunk_shape`. | **Add** two classmethods, ~10 lines each. |
| `src/scieasy/core/types/series.py` | `Series` base class. | Adds two classmethods covering `index_name`, `value_name`, `length`. | **Add** two classmethods, ~6 lines each. |
| `src/scieasy/core/types/dataframe.py` | `DataFrame` base class. | Adds two classmethods covering `columns`, `row_count`, `schema`. | **Add** two classmethods, ~6 lines each. |
| `src/scieasy/core/types/text.py` | `Text` base class. | Adds two classmethods covering `format`, `encoding`. | **Add** two classmethods, ~5 lines each. |
| `src/scieasy/core/types/artifact.py` | `Artifact` base class. | Adds two classmethods covering `mime_type`, `description`. | **Add** two classmethods, ~5 lines each. |
| `src/scieasy/core/types/composite.py` | `CompositeData` per ADR-027 D2. | Adds two classmethods covering `slots` — recursively delegates to `_reconstruct_one` / `_serialise_one` for each slot. | **Add** two classmethods, ~10 lines each. The recursive delegation needs an import of `worker._reconstruct_one`, which is acceptable because composite reconstruction is intrinsically tied to the worker reconstruction protocol. Alternative: move the helpers into a new module `scieasy.core.types.serialization` to avoid `core` importing `engine.runners`. The implementation ticket will pick the cleaner of the two import directions. |
| `src/scieasy/core/types/registry.py` | `TypeRegistry.register` and `TypeRegistry.resolve` per ADR-027 D11. | Adds validation in `register`: if the registered class declares a `Meta` attribute, check that it is a `BaseModel`, has no `PrivateAttr` fields, and that all fields round-trip through `model_dump(mode="json")` / `model_validate`. Reject with a clear error if not. | **Add** `_validate_meta_class(cls)` (~25 lines). **Call** from `register()`. The validation cost is paid once per class at registration; not per dispatch. |
| `src/scieasy/core/units.py` | `PhysicalQuantity` per ADR-027 D6. | Adds `__get_pydantic_core_schema__` for transparent Pydantic v2 integration. | **Add** the classmethod (~25 lines including the imported `core_schema` helpers). |

#### Tests

| Test file | Coverage |
|---|---|
| `tests/engine/test_worker_type_reconstruction.py` (new) | `_reconstruct_one` round-trip for each base class with synthetic `StorageReference`. Verifies returned instance is the correct subclass, `meta` is the correct Pydantic model, `framework` fields populated, `user` dict preserved. |
| `tests/engine/test_worker_serialise_outputs.py` (new or extended) | `_serialise_one` produces the wire format expected by `_reconstruct_one`. Round-trip test: serialise → reconstruct → assert deep equality. |
| `tests/core/test_stratified_metadata.py` (already in ADR-027) | Add a test that round-trips a `FluorImage.Meta` with a `PhysicalQuantity` field through `model_dump_json` / `model_validate_json`. |
| `tests/core/test_units.py` (already in ADR-027) | Add `test_physical_quantity_pydantic_round_trip`: assert that `BaseModel(pixel_size=Q(0.108, "um"))` serialises to `{"pixel_size": {"value": 0.108, "unit": "um"}}` and back. |
| `tests/core/test_type_registry.py` (existing or new) | Add `test_register_rejects_meta_with_private_attr`, `test_register_rejects_meta_with_arbitrary_field`, `test_register_accepts_well_formed_meta`. |
| `tests/blocks/test_block_base.py` (existing) | **Audit** for any test that asserts `isinstance(inputs["x"], ViewProxy)`. Update to assert the typed class (`Array` or a plugin type if available). |
| `tests/core/test_proxy.py` (existing) | **Audit** for the same. ViewProxy itself is unchanged, so tests that exercise `ViewProxy.slice` / `ViewProxy.to_memory` directly still pass; only tests that asserted "the input the worker delivers is a ViewProxy" need to change. |

#### Documentation impact

| Document | Required changes |
|---|---|
| `docs/architecture/ARCHITECTURE.md` §5.1 (Block base class) | **No change**. The §5.1 prose updated in PR #258 already says "the worker subprocess must be able to reconstruct the typed input via TypeRegistry.scan()" and does not commit to a specific return type. |
| `docs/architecture/ARCHITECTURE.md` §6.1 (DAG scheduler) | **No change**. The scheduler does not interact with worker input reconstruction. |
| `docs/architecture/ARCHITECTURE.md` §4.1 (Base type hierarchy) | **No change**. The §4.1 rewrite in PR #258 already shows block authors using `item.meta.pixel_size` and `item.with_meta(...)` directly, which this Addendum makes accurate. |
| `docs/guides/block-sdk.md` | **No change**. All examples in the guide already show typed-instance access. This Addendum makes those examples accurate without any edit. |
| `docs/adr/ADR.md` | This Addendum. |
| `CHANGELOG.md` | **Add** entry under `[Unreleased]` → `### Added` referencing this Addendum and #259. |

#### Out of scope

- **Any source code changes.** This Addendum is documentation only. The implementation lands under the Phase 10 ADR-027 D11 implementation ticket (to be opened) and references this Addendum.
- **ARCHITECTURE.md / PROJECT_TREE.md / block-sdk.md updates.** Those documents already match the post-Addendum contract because they were written assuming typed-instance access. Verified by re-reading PR #258 content during the change-plan phase of this issue.
- **Any change to the `BlockState`, `EventBus`, cancellation, or scheduler contracts.** ADR-018, ADR-018 Addendum 1, ADR-019, ADR-020, and ADR-027 D1–D10 stand unchanged.
- **Changing the wire format JSON keys.** The engine→worker payload structure is unchanged. This Addendum specifies the **contents** of the metadata sidecar precisely, but does not rename any top-level keys (`backend`, `path`, `format`, `metadata`, `_collection`, `items`, `item_type` all remain).
- **Changing `Collection` semantics.** Collection of typed items continues to work as ADR-020 specified. The only change is that the items inside a reconstructed `Collection` are now typed instances rather than `ViewProxy`.
- **Reopening D11's main "discussion table" row.** That row commits to `TypeRegistry.scan()` in the worker, which this Addendum keeps unchanged. Only the Decision-section pseudocode and the corresponding "Alternatives considered" entry are superseded.

## ADR-028: IOBlock architectural refactor — plugin-owned IO pattern

**Status**: proposed
**Date**: 2026-04-06

### Context

Phase 10 landed the final core type surface (ADR-027) with exactly seven base types — `DataObject`, `Array`, `Series`, `DataFrame`, `Text`, `Artifact`, `CompositeData` — and excised every domain subtype (`Image`, `Spectrum`, `PeakTable`, `AnnData`, ...) to plugin packages. The core's deliberate smallness is now load-bearing: `scieasy-blocks-imaging`, `scieasy-blocks-srs`, `scieasy-blocks-lcms`, and future plugins all depend on it as a stable foundation.

The IO layer, however, was not revised during Phase 10. It still follows the pre-Phase-10 "central adapter registry" pattern that was originally designed when domain types lived inside core:

1. `src/scieasy/blocks/io/adapters/` ships eight bundled format adapters: `csv_adapter.py`, `fcs_adapter.py`, `generic_adapter.py`, `h5ad_adapter.py`, `mzxml_adapter.py`, `parquet_adapter.py`, `tiff_adapter.py`, `zarr_adapter.py`.
2. `src/scieasy/blocks/io/adapter_registry.py` is a separate registry class that dispatches by file extension, completely parallel to the `BlockRegistry` in `scieasy.blocks.registry` and the `TypeRegistry` in `scieasy.core.types.registry`.
3. `src/scieasy/blocks/io/io_block.py::_run_input` (lines 78–106) loops files in a directory, asks `AdapterRegistry.get_for_extension(ext)` for a class, calls `adapter.create_reference(path)`, and wraps the result in a bare `DataObject(storage_ref=ref)` — *with no type information*. The loaded object has no `Image`/`SRSImage`/`PeakTable` identity; it is a generic `DataObject` whose only distinguishing feature is its `storage_ref.metadata` dict.
4. ADR-025 §6 (block package distribution protocol) specifies a `scieasy.adapters` entry-point group alongside `scieasy.blocks` and `scieasy.types`, intended so external packages can register additional adapters via `pyproject.toml`.

This model was coherent when `Image` lived in core: the TIFF adapter knew about `Image`, returned an `Image` instance, and the adapter registry was the single source of truth for format-to-type mapping. With Phase 10's domain types moved to plugins, the model is broken in several concrete ways that surfaced when planning Phase 11's three plugin packages.

#### Tension 1 — Core enumerates formats it cannot predict

The eight bundled adapters mix two orthogonal concerns:

| Adapter | Category | Belongs in |
|---|---|---|
| `csv_adapter.py` | Generic tabular | Core |
| `parquet_adapter.py` | Generic tabular | Core |
| `generic_adapter.py` | Opaque bytes | Core |
| `zarr_adapter.py` | Generic chunked array | Core |
| `tiff_adapter.py` | Image-specific | `scieasy-blocks-imaging` |
| `mzxml_adapter.py` | LC-MS-specific | `scieasy-blocks-lcms` |
| `h5ad_adapter.py` | Single-cell-specific | Future `scieasy-blocks-singlecell` |
| `fcs_adapter.py` | Flow-cytometry-specific | Future `scieasy-blocks-flow` |

Four of the eight adapters are plugin-domain concerns that core currently imports unconditionally. A user who installs only `scieasy` and wants to do single-cell analysis gets an `h5ad_adapter` they cannot meaningfully use (because `AnnData` was deleted from core in T-007). A user who installs `scieasy` plus `scieasy-blocks-lcms` gets the plugin's mzML support — but also the core's `mzxml_adapter`, which is a second, differently-behaving path to the same goal.

This is the literal opposite of "core stays small and stable" from CLAUDE.md §2.3, and it is the literal opposite of ADR-027 D2's "core contains only base types; all domain subtypes live in plugins".

#### Tension 2 — Typed reconstruction never happens in the IO path

The current `IOBlock._run_input` implementation (reproduced in full because it is load-bearing for this ADR):

```python
def _run_input(self, path: Path, registry: Any) -> dict[str, Any]:
    """Build a lazy Collection from *path* (file or directory)."""
    if path.is_dir():
        items: list[DataObject] = []
        for child in sorted(path.iterdir()):
            if child.is_file():
                ext = child.suffix.lower()
                try:
                    adapter_cls = registry.get_for_extension(ext)
                except KeyError:
                    continue
                adapter = adapter_cls()
                ref = adapter.create_reference(child)
                obj = DataObject(storage_ref=ref)   # <-- type information lost here
                items.append(obj)

        if not items:
            raise ValueError(f"No recognised files found in directory: {path}")

        collection = Collection(items=items, item_type=DataObject)
    else:
        ext = path.suffix.lower()
        adapter_cls = registry.get_for_extension(ext)
        adapter = adapter_cls()
        ref = adapter.create_reference(path)
        obj = DataObject(storage_ref=ref)           # <-- again here
        collection = Collection(items=[obj], item_type=DataObject)

    return {"data": collection}
```

Two lines, `obj = DataObject(storage_ref=ref)`, throw away every piece of type knowledge the adapter had. A plugin `LoadImage` block that wants to return `Collection[Image]` cannot use `IOBlock` as-is; it would have to bypass the registry entirely and re-implement format detection. Phase 10's `TypeRegistry.resolve(type_chain)` (T-012) and `_reconstruct_one` (T-014) — designed exactly to map a `type_chain` to a concrete class — are never reached from the IO path because the IO path never produces a `type_chain`.

#### Tension 3 — Two parallel registries for one concern

ADR-009 (registry stores specs), ADR-025 (plugin distribution), and Phase 10's `TypeRegistry` together establish that SciEasy has two registries:

- `BlockRegistry` — maps block name → `BlockSpec` → block class, scanned from `scieasy.blocks` entry-points plus Tier-1 drop-in files.
- `TypeRegistry` — maps type name → `TypeSpec` → `DataObject` subclass, scanned from `scieasy.types` entry-points plus core builtins.

The adapter layer adds a third:

- `AdapterRegistry` — maps file extension → adapter class, scanned from `scieasy.adapters` entry-points plus a hardcoded `register_defaults()` list in `adapter_registry.py`.

These three registries overlap substantially. An adapter IS a kind of block (specifically, an IO block). An adapter's output type IS a registered DataObject subclass. The extension → adapter lookup IS functionally a specialised form of "find the block that knows how to read this format". Keeping three registries requires plugin authors to understand three registration protocols, debug three scan paths when their plugin does not load, and read three sections of ADR-025 to register a single feature.

#### Tension 4 — No first-class ergonomics for pickle / TSV / ndarray / single-column Series

The user asked during Phase 11 planning for the following additional first-class load paths: Python pickle (`.pkl`), tab-separated values (`.tsv`), single numpy arrays (`.npy`, `.npz`), and pandas Series sidecars. None of these fits cleanly into the current adapter layer:

- `.pkl` requires a security-conscious `allow_pickle` opt-in (pickle is arbitrary code execution); the `generic_adapter` would happily read bytes but could not produce a typed Python object.
- `.tsv` is functionally CSV with a separator, but `csv_adapter.py` is hardcoded to `,` and the existing adapter protocol has no param-passing mechanism (parameters are block-level, not adapter-level).
- `.npy` / `.npz` need to return `Array` instances, but no current adapter binds to `Array`; the closest match is `generic_adapter.py` which returns `DataObject(storage_ref=ref)` with no `axes` field.
- Single-column Series have no adapter at all. `parquet_adapter` returns `DataFrame`; there is no path to `Series`.

Retrofitting the adapter layer to handle each of these requires either four new adapters (further bloating core) or an orthogonal "adapter params" mechanism (a protocol change with no existing consumers). Both options make the layer more complex in exchange for a feature the user explicitly prefers to own inside the loader block.

#### Tension 5 — Block authors want user-facing named blocks, not `IOBlock(format=...)`

OptEasy's experience directly informs this tension. OptEasy ships `LoadImage`, `SaveImage`, `LoadPeakTable`, `LoadSpectrum` as named blocks in the block palette. Each is self-explanatory; a non-programmer scientist picking `LoadImage` from the palette immediately understands what it will do. SciEasy's current `IOBlock(direction="input", path=..., format="tiff")` is strictly less expressive in the GUI: the same block name appears for every IO operation, and the user must set `format` correctly for the workflow to validate. The block palette's two-level grouping (ADR-025 §3) cannot help, because every IO block has the same `type_name = "io_block"`.

The user-facing fix is obvious: ship `LoadImage` as a concrete class whose `output_ports` declares `accepted_types=[Image]`. The current adapter layer stands directly in the way of doing this, because it forces the declaration of type into the `storage_ref.metadata` dict rather than into the block's port contract.

---

These five tensions are cross-cutting and reinforcing. Any one of them alone might be fixable inside the current adapter model; all five together compose an architectural pattern that no longer matches Phase 10's philosophy. This ADR resolves all five in a single coherent refactor.

### Discussion points and resolution

| # | Topic | Options discussed | Final decision |
|---|---|---|---|
| 1 | Should `IOBlock` be a concrete class (current state) or an abstract base? | (A) Concrete, with a `format` param and internal dispatch. (B) Abstract base class with `load()` / `save()` abstract methods; concrete loaders are subclasses. | **Decision: (B).** Abstract base forces every IO block to declare its input/output types via the standard `input_ports` / `output_ports` ClassVars. Type information flows through the block's port contract (ADR-016, Phase 10 port-check), not through a side-channel metadata dict. Concrete loaders are subclasses (one per loaded type for core, one per loaded type per plugin). This aligns the IO layer with every other block category: `ProcessBlock`, `CodeBlock`, `AppBlock` are all abstract-or-configurable bases with concrete subclasses carrying domain knowledge. |
| 2 | Should the central adapter registry survive? | (A) Keep it, add typed reconstruction. (B) Delete it entirely; adapters are absorbed into loader blocks. (C) Keep it as a soft-deprecated compatibility layer for one phase. | **Decision: (B).** The registry is a second source of truth for "how to load files". Its only consumer is `IOBlock._run_input`, which this ADR deletes. Option (C) doubles the plugin-author cognitive burden for a full phase with no long-term payoff. Deleting in one cut (per Phase 10's "first destructive change is the risk point" lesson — this ADR and its implementation are explicitly expected to be the risk point, not a plugin package's first integration) keeps the surface area small. |
| 3 | Which formats does core ship loader support for? | (A) Minimum: just Zarr for Array, Parquet for DataFrame/Series. (B) Pragmatic: all formats that are genuinely generic and not domain-specific, including CSV, TSV, Parquet, Pickle, NumPy, Zarr, plain text, opaque bytes. (C) Maximum: everything currently shipped, minus the four clearly plugin-specific ones. | **Decision: (B).** Pragmatic set. Users working with generic data (metadata CSVs, config files, numpy arrays from intermediate calculations, pickled sklearn models) should not need to install a domain plugin just to load their file. The specific format set is enumerated in Decision D3 below. |
| 4 | Should the `scieasy.adapters` entry-point group be kept or deleted? | (A) Keep it for plugin-provided adapters. (B) Delete it; plugins ship IO *blocks*, not adapters. | **Decision: (B).** The `scieasy.blocks` entry-point group already accepts any block class, including `IOBlock` subclasses. A plugin loading mzML files registers an `LoadMSRawFile(IOBlock)` through `scieasy.blocks`, not a `MzmlAdapter` through `scieasy.adapters`. One registration protocol instead of two. ADR-025 §6 is superseded. |
| 5 | What happens to the eight bundled adapters during implementation? | (A) Delete all eight, no migration. (B) Merge the four generic ones into core loaders; move the four domain-specific ones to their target plugin packages. | **Decision: (B).** The four generic adapters (`csv_adapter`, `parquet_adapter`, `zarr_adapter`, `generic_adapter`) contain logic that core needs — CSV parsing with pandas, Parquet reading, Zarr metadata handling, byte copy. That logic is absorbed into the corresponding `LoadDataFrame` / `LoadArray` / `LoadArtifact` core loaders. The four domain-specific adapters (`tiff_adapter`, `mzxml_adapter`, `h5ad_adapter`, `fcs_adapter`) are moved verbatim into their target plugin packages (`scieasy-blocks-imaging` / `scieasy-blocks-lcms` / future `scieasy-blocks-singlecell` / future `scieasy-blocks-flow`). The TIFF adapter's JSON-in-ImageDescription metadata round-trip logic is preserved as-is and becomes part of `scieasy-blocks-imaging`'s `LoadImage` block (Phase 11 Track 2). |
| 6 | Is pickle safe to support as a core loader path? | (A) No — pickle is arbitrary code execution, block authors should never load it. (B) Yes, with a mandatory opt-in flag and a prominent security warning. (C) Yes, unconditionally. | **Decision: (B).** Pickle is the de-facto serialisation format for sklearn models, intermediate pandas frames from notebooks, and arbitrary Python objects that cannot round-trip through parquet. Refusing to support it forces users to write `CodeBlock` script escape hatches to do something trivial, which is a worse outcome than a clearly-documented opt-in. The opt-in takes the form of an `allow_pickle: bool = False` config param on the relevant core loaders. When `allow_pickle` is `False` and the file extension is `.pkl` / `.pickle`, the block raises `ValueError` with a message pointing at the security implication and the opt-in path. This matches numpy's `np.load(..., allow_pickle=False)` convention and makes the decision auditable at workflow definition time. |
| 7 | How does a plugin loader declare its output type? | (A) Via `output_ports = [OutputPort(accepted_types=[Image])]` — the standard Phase 10 port contract. (B) Via a new sidecar protocol specific to IO blocks. | **Decision: (A).** No new protocol. Plugin `LoadImage` subclasses `IOBlock` and declares `output_ports = [OutputPort(name="data", accepted_types=[Image])]` exactly like every other block. The Phase 10 port-check system already handles type compatibility via `TypeSignature.matches()` (T-005/T-006). Downstream `process_item(self, item: Image, ...)` annotations become accurate, isinstance checks work, `item.meta.pixel_size` autocompletes in IDEs — everything Phase 10 promised for typed DataObjects finally applies to the IO path. |
| 8 | Does this ADR require changes to `_reconstruct_one` / `_serialise_one` (Phase 10 worker round-trip)? | (A) Yes — the IO block's output type needs a new field in the wire format. (B) No — the existing `type_chain` field in the metadata sidecar already handles this. | **Decision: (B).** No change required. When a plugin `LoadImage` block returns an `Image` instance, the worker's `serialise_outputs` calls `_serialise_one(image)`, which writes `md["type_chain"] = image.dtype_info.type_chain == ["DataObject", "Array", "Image"]` into the sidecar. The downstream block's worker calls `_reconstruct_one(payload_item)`, which calls `TypeRegistry.resolve(type_chain)` → `Image` class → constructs a typed `Image` instance. The wire format, the resolver, and the reconstruction hook contracts are all unchanged. This ADR interacts with Phase 10 only by *finally* making the IO path feed data into the Phase 10 pipeline in the typed form the pipeline was designed for. |
| 9 | How does the default `IOBlock.run()` dispatch between load and save modes? | (A) Keep the current `direction: str = "input"` class var. (B) Split into two separate abstract base classes, `LoaderBlock` and `SaverBlock`. | **Decision: (A).** The current `direction` ClassVar is sufficient. Concrete subclasses that load override `load()` and set `direction = "input"`; concrete subclasses that save override `save()` and set `direction = "output"`. The default `run()` branches once on `direction` and delegates. Splitting into two base classes would double the number of IO block classes shipped by core (seven loaders + seven savers = fourteen classes across two base classes, instead of fourteen classes across one base). It would also make "round-trip" blocks (rare but possible — e.g. a transcoder that reads one format and writes another) awkward to express. |
| 10 | What is the contract between `IOBlock.load()` and the engine's `Collection` wrapping? | (A) `load()` returns a `DataObject` (or list of them); the default `run()` wraps into a `Collection`. (B) `load()` returns a `Collection` directly. | **Decision: (A).** `load(config) -> DataObject \| list[DataObject]` is the simpler contract for block authors. Loader authors do not think about Collections; they think "given this path, produce this many objects of this type". The default `run()` handles the "one file → length-1 Collection" and "directory → length-N Collection" cases automatically. This matches the existing `ProcessBlock.process_item` pattern (author writes per-item logic, framework handles Collection). `save()` accepts a `Collection` because the save path by design iterates — a user saving `Collection[Image]` wants all N images saved, and the default `run()` handles the "single vs many" split via Collection length. |
| 11 | Do we ship concrete loaders for all seven core types, or only the subset that has a natural binary format? | (A) All seven (`DataObject`, `Array`, `Series`, `DataFrame`, `Text`, `Artifact`, `CompositeData`). (B) Only the five with obvious binary formats (`Array`, `Series`, `DataFrame`, `Text`, `Artifact`). `CompositeData` and bare `DataObject` do not ship loaders. | **Decision: (B) plus LoadCompositeData.** Bare `DataObject` has no reasonable "load" story — it is the abstract root. `CompositeData` does, because composites persist as a directory containing one storage ref per slot plus a `manifest.json` (per Phase 10's §4.2 backend table). `LoadCompositeData` is a thin wrapper that reads the manifest, recurses into `_reconstruct_one` for each slot, and returns the assembled composite. Six concrete loaders + six concrete savers ship from core. |
| 12 | Pickle only for DataFrame, or also Series / Array? | (A) Only DataFrame (most common pickle target — pandas.to_pickle). (B) DataFrame and Series (symmetric with parquet). (C) DataFrame, Series, Array, and bare DataObject (maximum flexibility). | **Decision: (B).** DataFrame and Series pickle are symmetric (both are pandas-native) and cover 95% of real-world `.pkl` usage. Array pickle is supported via numpy's native `np.load(allow_pickle=True)` path through `LoadArray`, not as a separate code path. Bare DataObject pickle is refused: anyone pickling a DataObject has enough framework knowledge to write a `CodeBlock` escape hatch, and loading a pickled DataObject would bypass Phase 10's typed reconstruction path entirely. |
| 13 | How are the per-format extensions registered inside each core loader? | (A) Class-level `supported_extensions: ClassVar[dict[str, str]]` mapping extension → internal format name. (B) Hardcoded `if ext == ".csv": ... elif ext == ".tsv": ...` chains. (C) A pluggable registry inside each loader class. | **Decision: (A).** Class-level ClassVar. Every core loader declares `supported_extensions` explicitly so the block palette can render "supported formats: .csv, .tsv, .parquet, .pkl" in the block description automatically. Format dispatch inside the loader is a simple dict lookup plus a call to a private per-format method (`_load_csv`, `_load_tsv`, ...). Option (C) is premature generality — no loader needs runtime-pluggable format support. |
| 14 | Is the change a breaking change, and if so, what is the migration story? | (A) Yes, breaking; ship a migration guide and a script. (B) No, keep `IOBlock(format=...)` as a deprecated shim for one phase. (C) Yes, breaking; no migration tooling needed because the pre-Phase-11 IOBlock usage base is small. | **Decision: (C).** SciEasy is still in pre-1.0 development; no external user has built production workflows on top of `IOBlock(format=...)`. The internal callers are the three bundled adapter tests plus `tests/blocks/test_adapter_registry.py`, which are migrated as part of this ADR's implementation PR. The CHANGELOG entry flags the break clearly. A migration shim that accepts the old `IOBlock(format=...)` form and re-routes to the new loaders would cost ~150 lines of code and add a permanent "did you mean the new loader?" ambiguity to every workflow file. |

### Decision

The Phase 11 decisions from the discussion table are codified below. Each decision has a one-paragraph summary, a code-shape sketch where useful, and a line-by-line impact reference in the "Detailed impact scope" section.

#### D1. `IOBlock` becomes an abstract base class (covers discussion #1, #9, #10)

`src/scieasy/blocks/io/io_block.py` is rewritten. The post-ADR-028 shape:

```python
# scieasy/blocks/io/io_block.py

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from scieasy.blocks.base.block import Block
from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection


class IOBlock(Block):
    """Abstract base class for data ingress and egress blocks.

    Per ADR-028, IOBlock is an ABC. Concrete subclasses declare their
    typed output via ``output_ports`` (for loaders) or accept typed
    input via ``input_ports`` (for savers), and implement ``load`` or
    ``save`` accordingly.

    Subclasses MUST set ``direction`` to either ``"input"`` or
    ``"output"`` and override the matching abstract method.

    The default ``run()`` method dispatches based on ``direction``,
    wraps single-object outputs into a length-1 Collection, and passes
    Collection inputs unchanged to ``save()``.
    """

    direction: ClassVar[str] = "input"   # subclasses override to "output"

    # Subclasses override with their typed ports.
    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = []

    # Subclasses declare supported extensions (ADR-028 D13).
    supported_extensions: ClassVar[dict[str, str]] = {}

    @abstractmethod
    def load(self, config: BlockConfig) -> DataObject | list[DataObject]:
        """Load data from ``config['path']``.

        Args:
            config: BlockConfig containing at least ``path: str``.
                Additional format-specific params (e.g. ``allow_pickle``,
                ``separator``, ``encoding``) are subclass-specific.

        Returns:
            A single ``DataObject`` (for single-file loads) or a list
            of ``DataObject`` instances (for directory/glob loads).
            Both are wrapped into a ``Collection`` by ``run()``.

        Raises:
            FileNotFoundError: path does not exist.
            ValueError: path extension is not in ``supported_extensions``,
                or a format-specific validation fails.
        """
        raise NotImplementedError(
            f"{type(self).__name__} is a loader but does not override load()"
        )

    @abstractmethod
    def save(self, data: Collection, config: BlockConfig) -> None:
        """Save ``data`` to ``config['path']``.

        Args:
            data: A Collection of DataObjects. Subclass decides how
                length > 1 is serialised (directory with indexed files,
                multi-page container, etc.).
            config: BlockConfig containing at least ``path: str``.

        Raises:
            ValueError: if the target extension is not supported or if
                ``data`` contains items of an unexpected type.
        """
        raise NotImplementedError(
            f"{type(self).__name__} is a saver but does not override save()"
        )

    def run(
        self,
        inputs: dict[str, Collection],
        config: BlockConfig,
    ) -> dict[str, Collection]:
        """Default dispatch: load or save based on ``direction``.

        - ``direction == "input"``: calls ``load(config)``, wraps result
          into ``Collection``, returns on first output port.
        - ``direction == "output"``: unwraps input Collection, calls
          ``save(data, config)``, returns empty dict.

        Subclasses that need custom run semantics (e.g. transcoder that
        reads one format and writes another) override ``run()`` directly.
        """
        if self.direction == "input":
            raw = self.load(config)
            if isinstance(raw, list):
                items = raw
            else:
                items = [raw]
            port_name = self.output_ports[0].name if self.output_ports else "data"
            # item_type is taken from the first output port's accepted_types[0]
            # so the Collection is correctly typed for downstream port checks.
            item_type: type[DataObject]
            if self.output_ports and self.output_ports[0].accepted_types:
                item_type = self.output_ports[0].accepted_types[0]
            else:
                item_type = DataObject
            return {port_name: Collection(items=items, item_type=item_type)}

        if self.direction == "output":
            data = next(iter(inputs.values()))
            if not isinstance(data, Collection):
                data = Collection(items=[data], item_type=type(data))
            self.save(data, config)
            return {}

        raise ValueError(
            f"{type(self).__name__}.direction must be 'input' or 'output', "
            f"got {self.direction!r}"
        )
```

Block authors write concrete loaders as small subclasses:

```python
class LoadDataFrame(IOBlock):
    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "load_dataframe"
    name: ClassVar[str] = "Load DataFrame"
    description: ClassVar[str] = "Load a DataFrame from CSV, TSV, Parquet, or Pickle."
    category: ClassVar[str] = "io"
    supported_extensions: ClassVar[dict[str, str]] = {
        ".csv": "csv",
        ".tsv": "tsv",
        ".txt": "tsv",
        ".parquet": "parquet",
        ".pq": "parquet",
        ".pkl": "pickle",
        ".pickle": "pickle",
    }
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="data",
            accepted_types=[DataFrame],
            description="Loaded DataFrame",
        ),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "title": "Path"},
            "allow_pickle": {
                "type": "boolean",
                "default": False,
                "title": "Allow pickle (security risk)",
                "description": "Required to load .pkl / .pickle files.",
            },
            "separator": {
                "type": "string",
                "default": ",",
                "title": "CSV separator (auto for .tsv)",
            },
            "encoding": {"type": "string", "default": "utf-8"},
        },
        "required": ["path"],
    }

    def load(self, config: BlockConfig) -> DataObject | list[DataObject]:
        path = Path(config["path"])
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        if path.is_dir():
            return [self._load_one(p, config) for p in sorted(path.iterdir()) if p.is_file()]
        return self._load_one(path, config)

    def _load_one(self, path: Path, config: BlockConfig) -> DataFrame:
        ext = path.suffix.lower()
        fmt = self.supported_extensions.get(ext)
        if fmt is None:
            raise ValueError(
                f"{type(self).__name__} does not support extension {ext!r}. "
                f"Supported: {sorted(self.supported_extensions.keys())}"
            )
        if fmt == "pickle" and not config.get("allow_pickle", False):
            raise ValueError(
                f"Loading {path} requires allow_pickle=True. Pickle is "
                f"arbitrary code execution; only enable for trusted files."
            )
        if fmt == "csv":
            return self._load_csv(path, config)
        if fmt == "tsv":
            return self._load_tsv(path, config)
        if fmt == "parquet":
            return self._load_parquet(path)
        if fmt == "pickle":
            return self._load_pickle(path)
        raise ValueError(f"Unknown format {fmt!r} for {path}")

    # ... _load_csv, _load_tsv, _load_parquet, _load_pickle implementations
```

Abstract base status is enforced via `ABC` inheritance in the implementation: `class IOBlock(Block, ABC)`. A direct instantiation of `IOBlock()` raises `TypeError` at construction time, matching Python's standard `abc` contract.

#### D2. `AdapterRegistry` and all bundled adapters are deleted (covers #2, #5)

The following files are **deleted** in the implementation PR (not this ADR PR):

```
src/scieasy/blocks/io/adapter_registry.py
src/scieasy/blocks/io/adapters/__init__.py
src/scieasy/blocks/io/adapters/base.py
src/scieasy/blocks/io/adapters/csv_adapter.py
src/scieasy/blocks/io/adapters/fcs_adapter.py
src/scieasy/blocks/io/adapters/generic_adapter.py
src/scieasy/blocks/io/adapters/h5ad_adapter.py
src/scieasy/blocks/io/adapters/mzxml_adapter.py
src/scieasy/blocks/io/adapters/parquet_adapter.py
src/scieasy/blocks/io/adapters/tiff_adapter.py
src/scieasy/blocks/io/adapters/zarr_adapter.py
tests/blocks/test_adapter_registry.py
tests/blocks/test_adapters.py  # migrated to tests/blocks/test_core_loaders.py
```

The per-adapter logic is preserved in one of two destinations per ADR-028 D5:

| Adapter | Destination | Receiving block |
|---|---|---|
| `csv_adapter.py` | Core, merged | `LoadDataFrame._load_csv` / `_load_tsv` |
| `parquet_adapter.py` | Core, merged | `LoadDataFrame._load_parquet`, `LoadSeries._load_parquet` |
| `zarr_adapter.py` | Core, merged | `LoadArray._load_zarr`, `SaveArray._save_zarr` |
| `generic_adapter.py` | Core, merged | `LoadArtifact._load_bytes` / `SaveArtifact._save_bytes` |
| `tiff_adapter.py` | `scieasy-blocks-imaging` | `LoadImage._load_tif` (verbatim) |
| `mzxml_adapter.py` | `scieasy-blocks-lcms` | `LoadMSRawFile._load_mzxml` (verbatim) |
| `h5ad_adapter.py` | Future `scieasy-blocks-singlecell` | `LoadAnnData._load_h5ad` |
| `fcs_adapter.py` | Future `scieasy-blocks-flow` | `LoadFCS._load_fcs` |

Moving the plugin adapters is the responsibility of the Phase 11 plugin-package implementation PRs. The core-merge of the four generic adapters is the responsibility of the ADR-028 implementation PR. Both are tracked separately from this ADR PR.

#### D3. Seven core loader/saver pairs (covers #3, #11)

Core ships seven concrete loader classes and seven concrete saver classes, one per base type, under `src/scieasy/blocks/io/loaders/` and `src/scieasy/blocks/io/savers/`. The table below locks the format set and the primary backend per ADR-027 D2 §4.2:

| Block | Base type | Supported extensions | Primary backend | Notes |
|---|---|---|---|---|
| `LoadArray` / `SaveArray` | `Array` | `.zarr`, `.npy`, `.npz` | Zarr (primary), numpy (sidecar for `.npy`/`.npz` + metadata JSON) | `axes` metadata JSON-encoded in Zarr `.attrs` or sidecar `.json` for numpy |
| `LoadDataFrame` / `SaveDataFrame` | `DataFrame` | `.parquet`, `.pq`, `.csv`, `.tsv`, `.txt`, `.pkl`, `.pickle` | Parquet (primary), pandas read_csv, pandas read_pickle | `.pkl` requires `allow_pickle=True`; `.txt` treated as TSV |
| `LoadSeries` / `SaveSeries` | `Series` | `.parquet`, `.pq`, `.csv`, `.pkl`, `.pickle` | Parquet single-column, pandas read_csv with single-column enforcement, pandas read_pickle | Loader rejects multi-column CSVs with a clear error |
| `LoadText` / `SaveText` | `Text` | `.txt`, `.json`, `.md`, `.html`, `.xml`, `.log`, `.yaml`, `.yml`, `.toml` | Filesystem (plain text), UTF-8 default, encoding param | JSON/XML/etc. stored as-is; parsing is downstream's concern |
| `LoadArtifact` / `SaveArtifact` | `Artifact` | `*` (any extension; fallback for unknown formats) | Filesystem (opaque byte copy) | Loader never parses content; sets `mime_type` from extension if known |
| `LoadCompositeData` / `SaveCompositeData` | `CompositeData` | `.composite/` (directory) | Directory containing `manifest.json` plus one sub-directory per slot | Recurses into `_reconstruct_one` per slot |

`DataObject` (the abstract root) has no loader or saver. Attempting to load a file with "no specific type" raises `ValueError` with a message suggesting the user pick the specific loader block; the `LoadArtifact` path catches the opaque-bytes case.

#### D4. Pickle security protocol (covers #6, #12)

Pickle support is opt-in via an `allow_pickle: bool = False` config parameter on `LoadDataFrame`, `LoadSeries`, and `LoadArray` (the three block classes that accept `.pkl`/`.pickle` or numpy pickled arrays). When the requested format is pickle and `allow_pickle` is `False`, the loader raises `ValueError` with this exact message template:

```
Loading {path} requires allow_pickle=True. Pickle is arbitrary code
execution; only enable for trusted files. If this file came from
an untrusted source, load it via LoadArtifact (opaque bytes) and
validate before unpickling.
```

The security warning is also reproduced in the block's `description` ClassVar so it appears in the GUI block palette: `"Load a DataFrame from CSV, TSV, Parquet, or Pickle. Warning: pickle loading is opt-in and runs arbitrary code — only enable for trusted files."`

`SaveDataFrame` / `SaveSeries` can write pickle unconditionally (writing pickle is safe). The asymmetry is intentional: writing is always safe, reading is a security boundary.

Downstream block authors who pipe loaded-pickle data into `CodeBlock` or `ProcessBlock` get no additional protection — if the pickle ran malicious code during `load()`, the damage is already done by the time the object reaches the next block. This matches numpy's security model.

#### D5. Plugin IO block contract (covers #4, #7)

Plugin packages ship their own IO blocks as subclasses of `scieasy.blocks.io.IOBlock`. The plugin's `LoadImage`:

```python
# scieasy_blocks_imaging/io/load_image.py

from scieasy.blocks.io import IOBlock
from scieasy.blocks.base.ports import OutputPort
from scieasy_blocks_imaging.types import Image

class LoadImage(IOBlock):
    direction = "input"
    type_name = "load_image"
    name = "Load Image"
    category = "io"
    supported_extensions = {
        ".tif": "tiff",
        ".tiff": "tiff",
        ".ome.tif": "ome_tiff",
        ".ome.tiff": "ome_tiff",
        ".png": "png",
        ".jpg": "jpeg",
        ".jpeg": "jpeg",
        ".zarr": "zarr",
        ".czi": "czi",       # optional, requires aicsimageio
        ".nd2": "nd2",       # optional, requires nd2reader
        ".lif": "lif",       # optional, requires readlif
        ".npy": "npy",
        ".npz": "npz",
    }
    output_ports = [
        OutputPort(name="data", accepted_types=[Image]),
    ]

    def load(self, config):
        path = Path(config["path"])
        if path.is_dir():
            return [self._load_one(p, config) for p in sorted(path.glob(config.get("pattern", "*"))) if p.is_file()]
        return self._load_one(path, config)

    def _load_one(self, path, config):
        ext = "".join(path.suffixes).lower()   # handles .ome.tif
        fmt = self.supported_extensions.get(ext) or self.supported_extensions.get(path.suffix.lower())
        if fmt == "tiff":
            return self._load_tif(path)
        if fmt == "ome_tiff":
            return self._load_ome_tif(path)
        # ... etc.
```

No new protocol, no new entry-point group. The plugin author lists `LoadImage` in `get_blocks()` alongside every other plugin block, and `BlockRegistry._scan_tier2()` picks it up via the `scieasy.blocks` entry-point group.

The plugin's output type (`Image`) must be registered via the `scieasy.types` entry-point group (ADR-025 §4). At scan time, the worker subprocess `TypeRegistry.resolve(["DataObject", "Array", "Image"])` finds the plugin class, and Phase 10's `_reconstruct_one` reconstructs typed instances from serialised payloads. This entire path is unchanged by ADR-028.

#### D6. `scieasy.adapters` entry-point group deletion (covers #4)

The `scieasy.adapters` entry-point group defined in ADR-025 §6 is formally deleted by this ADR. The implementation PR removes:

- `[project.entry-points."scieasy.adapters"]` section from `pyproject.toml` (if it currently has any entries; at the time of ADR-028 writing, the section is declared but empty).
- All mentions of `scieasy.adapters` from `src/scieasy/blocks/io/adapter_registry.py::scan_entry_points` (the whole file is deleted per D2).
- The ADR-025 §6 text is marked superseded with a pointer to ADR-028 (in a follow-up doc-update PR, not in this ADR PR).

External plugins that currently use `scieasy.adapters` (none at time of ADR-028 writing) must migrate to shipping an `IOBlock` subclass via `scieasy.blocks`. The migration is straightforward: the adapter class body becomes a `_load_<format>` private method on the new IO block.

#### D7. Default `run()` dispatch and Collection wrapping (covers #10)

Already sketched in D1 above. The normative rules:

1. `load()` returns either a single `DataObject` or a `list[DataObject]`. Both forms are legal; subclasses choose the shape that matches their semantics (a loader that always reads one file returns a single object; a loader that can read a directory returns a list).
2. `run()` for `direction == "input"` normalises the result into a list and wraps into a `Collection`, using the first `output_ports[0].accepted_types[0]` as the Collection's `item_type`. This makes downstream port checks see the correct item type.
3. `save()` accepts a `Collection` and does whatever it needs per-item (write N files, write one multi-page file, etc.). The subclass decides.
4. `run()` for `direction == "output"` wraps single-DataObject inputs into a length-1 Collection before calling `save()`, so `save()` never has to handle the "single or Collection" branching itself.
5. Subclasses that need custom dispatch (transcoder blocks that read one format and write another) override `run()` directly; the default is a convenience, not a contract.

#### D8. Supported extension declaration and lookup (covers #13)

Each concrete IOBlock subclass declares `supported_extensions: ClassVar[dict[str, str]]` mapping lowercase extension (including the leading dot) to a short internal format name. The internal format name is a dispatch key; the loader's `_load_one()` method does `fmt = self.supported_extensions.get(ext)` and branches to `_load_<fmt>()`.

Compound extensions like `.ome.tif` are handled by the subclass's lookup code, not by the framework. The pattern is `"".join(path.suffixes).lower()` first, then fallback to `path.suffix.lower()`:

```python
def _detect_format(self, path: Path) -> str | None:
    compound = "".join(path.suffixes).lower()
    if compound in self.supported_extensions:
        return self.supported_extensions[compound]
    single = path.suffix.lower()
    if single in self.supported_extensions:
        return self.supported_extensions[single]
    return None
```

The framework provides a helper `IOBlock._detect_format(path)` implementing this lookup so subclasses do not reimplement it. The helper is a regular method (not abstract) and lives on the base class.

#### D9. Metadata extraction protocol (informative, not normative)

ADR-028 does not specify a formal metadata extraction protocol for plugin loaders. Each plugin's `LoadImage` / `LoadPeakTable` / `LoadMSRawFile` extracts metadata from its source files using format-specific logic (e.g. `tifffile.TiffFile.pages[0].description` for TIFF, `pyopenms` for mzML) and populates the loaded DataObject's `meta: Meta` Pydantic model using the `cls.Meta(...)` constructor.

Best-practice guidance (non-binding, for the Phase 11 plugin spec docs):

- Extract whatever the source format provides.
- Normalise to `PhysicalQuantity` for physical fields (`pixel_size`, `laser_power`, `integration_time`).
- Fill unknowns with `None` rather than empty strings or sentinel values.
- Set `framework.source = str(path.resolve())` so Phase 10 lineage tracking works.
- For directory loads, set `framework.source` per item to the individual file path, not the parent directory.

A plugin's detailed metadata extraction protocol is documented in the plugin's own spec (e.g. `docs/specs/phase11-imaging-block-spec.md`), not in ADR-028.

#### D10. CLI surface (informative)

The `scieasy` CLI surface is unchanged by ADR-028. The existing `scieasy run <workflow.yaml>` command loads the workflow, instantiates blocks via `BlockRegistry`, and executes them — all block classes including IO blocks are resolved through the same `BlockRegistry` path. No CLI command needs to know about the old `AdapterRegistry`; deleting it has no user-visible CLI effect.

### Alternatives considered

**Alternative A — Typed reconstruction inside the existing adapter layer.** Retrofit `IOBlock._run_input` to call `TypeRegistry.resolve(type_chain)` using a new `type_chain` field on the adapter's `create_reference()` return value. Each adapter declares its output type, the registry dispatches, `_reconstruct_one` instantiates.

*Rejected because*:
- Solves tension 2 but leaves tensions 1, 3, 4, 5 untouched.
- Requires a new adapter protocol field (`type_chain`) that every existing adapter must be modified to supply.
- Keeps two parallel registries (`AdapterRegistry` + `BlockRegistry`), increasing cognitive load for plugin authors.
- Does not deliver user-facing named blocks (`LoadImage`, `LoadPeakTable`), which was an explicit Phase 11 requirement.
- Adds one more thing to maintain when the long-term direction is to reduce core surface.

**Alternative B — IOBlock stays concrete, gets a `subclass_of: type[DataObject]` ClassVar for typed dispatch.** Keep the adapter registry but add a single ClassVar to `IOBlock` so subclasses can specialise. `IOBlock(subclass_of=Image)` returns Image-typed Collections.

*Rejected because*:
- Still requires adapters underneath, so tensions 1 and 3 are untouched.
- Conflates two orthogonal dimensions: what type does the block produce (a class-level concern) and how does the block load it (a runtime format-dispatch concern). Bundling them into one ClassVar requires users to subclass whenever they need a different type OR a different format, creating a Cartesian explosion (`LoadImageFromTiff`, `LoadImageFromZarr`, `LoadImageFromNpy`, ...).
- Does not match the post-Phase-10 direction (core ships abstract bases, plugins ship concrete subclasses). This alternative proposes a third model (core ships concrete-but-configurable blocks).

**Alternative C — Gradual deprecation over two phases.** Keep `scieasy.adapters` and `AdapterRegistry` alive in Phase 11 as soft-deprecated compatibility shims. Ship the new `IOBlock` ABC pattern alongside them. Mark the old API with `DeprecationWarning`. Remove in Phase 12.

*Rejected because*:
- Doubles the surface area for a full phase. Every plugin author must learn both patterns to understand which one to use.
- Introduces "which registry should I write to?" as a permanent question during the deprecation window.
- Phase 10 deprecated the old `DataObject.metadata` dict with exactly this pattern, and the resulting dual-path code in `filter_collection.py:58` and `bridge.py:52` (tracked by issue #278) has already become a small maintenance burden. Repeating the pattern is a known failure mode.
- The Phase 11 plugin packages are the first consumers of the new IO path. There are no external users to protect from a breaking change — the change is fully internal to SciEasy at the time of landing.

**Alternative D — Keep adapters, rename to "format readers", integrate with `TypeRegistry`.** Unify the registries under a single umbrella: every type has one or more "format reader" classes attached to it, and `TypeRegistry.resolve(["DataObject", "Array", "Image"]).get_reader(".tif")` returns the correct loader class.

*Rejected because*:
- This is architecturally appealing but the plumbing is invasive: every `DataObject` subclass must know about its own readers, turning the type hierarchy into a bidirectional graph.
- The reader objects still need to be IO blocks (so they can run inside the workflow engine), so this alternative ships the same block classes as Option B plus a registry-to-block indirection.
- Plugin authors have to register both the type and the readers, doubling registration work.

### Consequences

**Breaking changes** (all internal to pre-Phase-11 SciEasy, no external users affected):

- `IOBlock()` is no longer instantiable directly; it is an ABC. Any test or code that constructs `IOBlock()` directly must migrate to one of the concrete loader/saver classes.
- `AdapterRegistry` class no longer exists. Any code that imports `from scieasy.blocks.io.adapter_registry import AdapterRegistry` breaks.
- Bundled adapters under `scieasy.blocks.io.adapters.*` no longer exist. Imports from that path break.
- `scieasy.adapters` entry-point group is removed from `pyproject.toml`. Plugins that declared entries here (none at time of writing) break.
- `IOBlock(direction="input", path=...)` no longer auto-dispatches by extension. Workflow YAML files using the old form must be migrated to specific loader blocks (e.g. `LoadDataFrame(path=...)`).

**Non-breaking consequences**:

- Block palette gains concrete loader entries: `LoadArray`, `LoadDataFrame`, `LoadSeries`, `LoadText`, `LoadArtifact`, `LoadCompositeData`, plus savers. GUI users see named blocks rather than a generic `IOBlock`.
- Plugin packages can ship their own IO blocks (`LoadImage`, `LoadPeakTable`, `LoadMSRawFile`) via the existing `scieasy.blocks` entry-point group. No new plugin registration protocol to learn.
- Typed reconstruction (Phase 10 `_reconstruct_one`) finally reaches the IO path. Downstream blocks can declare `process_item(self, item: Image, ...)` annotations and they will be accurate.
- Pickle support becomes first-class via the opt-in flag, without requiring a `CodeBlock` escape hatch.
- `.tsv`, `.pkl`, `.npy`, `.npz` all gain first-class load paths via the core loaders.
- The TIFF adapter's JSON-in-ImageDescription metadata round-trip is preserved verbatim in `scieasy-blocks-imaging.LoadImage` — no feature regression.
- Two registries (`BlockRegistry`, `TypeRegistry`) instead of three. Plugin author cognitive load decreases.
- ADR-025 §6 is superseded, leaving ADR-025 with two entry-point groups (`scieasy.blocks`, `scieasy.types`) instead of three.

**Known risks and mitigations**:

| Risk | Mitigation |
|---|---|
| The implementation PR will be large (deletions + new loader files + test migration). | Split into stacked PRs: (a) delete adapters + rewrite IOBlock ABC, (b) add seven concrete loaders, (c) add seven concrete savers, (d) update ARCHITECTURE.md and block-sdk.md. Each stacked PR is small and independently reviewable. The Phase 10 cascade methodology proved this pattern works. |
| Plugin authors reading ADR-025 §6 will be confused by the deletion. | Follow-up doc-update PR adds a "superseded by ADR-028" notice inside ADR-025 §6 pointing at this ADR. |
| The four generic adapters being merged into core loaders may introduce subtle behaviour drift (e.g. CSV quoting edge cases). | The implementation PR must include a regression test per adapter: load a known input file, assert the output matches the pre-refactor output byte-for-byte or (for CSV) row-for-row. |
| Pickle security footgun: a user might enable `allow_pickle=True` and then forget it is dangerous. | (1) The error message when `allow_pickle=False` reproduces the warning verbatim. (2) The block description in the GUI contains the warning. (3) A workflow validation pass can lint for `allow_pickle=True` in block configs and surface it during review. |
| TIFF adapter's existing behaviour (JSON-in-ImageDescription metadata round-trip) must be preserved in the `scieasy-blocks-imaging` move. | The move PR includes a regression test that writes a known Image, reads it back, and asserts metadata equality. The test file moves alongside the adapter code. |
| `scieasy.adapters` entry-point group deletion requires editing `pyproject.toml`. | The implementation PR updates `pyproject.toml`; the entry-point group declaration is trivially removable. |
| Tests under `tests/blocks/test_adapters.py` and `tests/blocks/test_adapter_registry.py` must be rewritten. | The ADR implementation PR deletes `test_adapter_registry.py` and replaces `test_adapters.py` with `test_core_loaders.py` (new file) covering the seven new concrete loaders, the seven savers, the pickle safety flag, the format-dispatch helper, and the default `run()` dispatch. |

### Detailed impact scope

Implementation of ADR-028 is **not** part of this ADR PR. The impact scope below describes what the follow-up implementation PR(s) must do so that the ADR stands as a clear, implementable spec.

#### Files to delete

| File | Reason |
|---|---|
| `src/scieasy/blocks/io/adapter_registry.py` | Replaced by per-block dispatch inside concrete loaders (D2). |
| `src/scieasy/blocks/io/adapters/__init__.py` | Directory deleted (D2). |
| `src/scieasy/blocks/io/adapters/base.py` | `FormatAdapter` protocol deleted; replaced by `IOBlock` ABC (D1). |
| `src/scieasy/blocks/io/adapters/csv_adapter.py` | Logic merged into `LoadDataFrame._load_csv` (D5). |
| `src/scieasy/blocks/io/adapters/fcs_adapter.py` | Moved verbatim to future `scieasy-blocks-flow` (D5). |
| `src/scieasy/blocks/io/adapters/generic_adapter.py` | Logic merged into `LoadArtifact._load_bytes` (D5). |
| `src/scieasy/blocks/io/adapters/h5ad_adapter.py` | Moved verbatim to future `scieasy-blocks-singlecell` (D5). |
| `src/scieasy/blocks/io/adapters/mzxml_adapter.py` | Moved verbatim to `scieasy-blocks-lcms` (D5). |
| `src/scieasy/blocks/io/adapters/parquet_adapter.py` | Logic merged into `LoadDataFrame._load_parquet`, `LoadSeries._load_parquet` (D5). |
| `src/scieasy/blocks/io/adapters/tiff_adapter.py` | Moved verbatim to `scieasy-blocks-imaging` (D5). |
| `src/scieasy/blocks/io/adapters/zarr_adapter.py` | Logic merged into `LoadArray._load_zarr`, `SaveArray._save_zarr` (D5). |
| `tests/blocks/test_adapter_registry.py` | Registry no longer exists (D2). |
| `tests/blocks/test_adapters.py` | Replaced by `tests/blocks/test_core_loaders.py` and `tests/blocks/test_core_savers.py` (D11). |

#### Files to rewrite

| File | Before | After |
|---|---|---|
| `src/scieasy/blocks/io/io_block.py` | 138 lines concrete class with `_run_input` / `_run_output` adapter-dispatch implementations | Abstract base class with `load()` / `save()` abstract methods, default `run()` dispatching on `direction`, `_detect_format()` helper (D1, D7, D8) |
| `src/scieasy/blocks/io/__init__.py` | Re-exports `IOBlock`, `AdapterRegistry` | Re-exports `IOBlock` only; adds re-exports for the seven concrete core loaders/savers |
| `pyproject.toml` | Contains `[project.entry-points."scieasy.adapters"]` section (empty) | Section removed (D6) |

#### Files to create

| File | Contents |
|---|---|
| `src/scieasy/blocks/io/loaders/__init__.py` | Re-exports the seven concrete loaders |
| `src/scieasy/blocks/io/loaders/array.py` | `LoadArray(IOBlock)` — supports `.zarr`, `.npy`, `.npz`. Metadata JSON sidecar for numpy formats |
| `src/scieasy/blocks/io/loaders/dataframe.py` | `LoadDataFrame(IOBlock)` — supports `.parquet`, `.pq`, `.csv`, `.tsv`, `.txt`, `.pkl`, `.pickle`. `allow_pickle` flag (D4) |
| `src/scieasy/blocks/io/loaders/series.py` | `LoadSeries(IOBlock)` — supports `.parquet`, `.pq`, `.csv`, `.pkl`, `.pickle`. Single-column enforcement on CSV. `allow_pickle` flag |
| `src/scieasy/blocks/io/loaders/text.py` | `LoadText(IOBlock)` — supports `.txt`, `.json`, `.md`, `.html`, `.xml`, `.log`, `.yaml`, `.yml`, `.toml`. UTF-8 default, `encoding` param |
| `src/scieasy/blocks/io/loaders/artifact.py` | `LoadArtifact(IOBlock)` — catch-all for any extension; opaque byte copy; sets `mime_type` from extension |
| `src/scieasy/blocks/io/loaders/composite.py` | `LoadCompositeData(IOBlock)` — reads `manifest.json`, recurses into `_reconstruct_one` per slot |
| `src/scieasy/blocks/io/savers/__init__.py` | Re-exports the seven concrete savers |
| `src/scieasy/blocks/io/savers/array.py` | `SaveArray(IOBlock)` — writes `.zarr`, `.npy`, `.npz`. Round-trips `axes`/`shape`/`dtype`/`chunk_shape` via sidecar JSON or Zarr `.attrs` |
| `src/scieasy/blocks/io/savers/dataframe.py` | `SaveDataFrame(IOBlock)` — writes `.parquet`, `.csv`, `.tsv`, `.pkl` |
| `src/scieasy/blocks/io/savers/series.py` | `SaveSeries(IOBlock)` — writes `.parquet`, `.csv`, `.pkl` |
| `src/scieasy/blocks/io/savers/text.py` | `SaveText(IOBlock)` — writes `.txt`, `.json`, etc. UTF-8 default |
| `src/scieasy/blocks/io/savers/artifact.py` | `SaveArtifact(IOBlock)` — byte copy to any destination |
| `src/scieasy/blocks/io/savers/composite.py` | `SaveCompositeData(IOBlock)` — writes `manifest.json` and per-slot sub-directories via `_serialise_one` |
| `tests/blocks/test_core_loaders.py` | Per-loader tests: happy path for each format, error on unknown extension, error on missing file, pickle opt-in enforcement, metadata round-trip |
| `tests/blocks/test_core_savers.py` | Per-saver tests: happy path for each format, round-trip equivalence with loaders, directory-mode for `Collection` length > 1 |
| `tests/blocks/test_ioblock_base.py` | `IOBlock()` direct instantiation raises `TypeError`; default `run()` dispatch branches correctly on `direction`; `_detect_format()` handles compound extensions |

#### Files to modify (documentation)

| File | Changes |
|---|---|
| `docs/adr/ADR.md` | This ADR (appended) |
| `docs/adr/ADR.md` (ADR-025 §6) | **Follow-up PR after this ADR lands**: insert a `**Superseded by**: ADR-028` line at the start of §6 linking to ADR-028. Not included in this ADR PR to keep scope minimal. |
| `docs/architecture/ARCHITECTURE.md` §4.2 (Storage backends) | **Follow-up PR**: clarify that loaders per base type now live at `scieasy.blocks.io.loaders.*` instead of `scieasy.blocks.io.adapters.*` |
| `docs/architecture/ARCHITECTURE.md` §5.1 (Block base) | **Follow-up PR**: add IOBlock ABC discussion alongside CodeBlock / AppBlock / ProcessBlock |
| `docs/architecture/PROJECT_TREE.md` | **Follow-up PR**: update to reflect new `loaders/` and `savers/` sub-directories, deletion of `adapters/` |
| `docs/guides/block-sdk.md` | **Follow-up PR**: add a "Shipping a format-specific IO block" section with the `LoadImage` example from D5 |
| `docs/specs/phase11-imaging-block-spec.md` | **New file, separate PR**: the Phase 11 imaging plugin spec consumes ADR-028's contract |
| `docs/specs/phase11-srs-block-spec.md` | **New file, separate PR** |
| `docs/specs/phase11-lcms-block-spec.md` | **New file, separate PR** |
| `CHANGELOG.md` | **This ADR PR**: entry under `[Unreleased]` → `### Added` per CLAUDE.md Appendix A Stage 6 |

#### Files NOT affected (explicitly)

The following files are NOT touched by ADR-028 or its implementation. Listing them explicitly to prevent scope creep in the implementation PR:

- `src/scieasy/core/types/*` — Phase 10's type hierarchy is unchanged.
- `src/scieasy/core/types/registry.py` — `TypeRegistry.resolve` is unchanged.
- `src/scieasy/core/types/serialization.py` — `_reconstruct_one` / `_serialise_one` are unchanged.
- `src/scieasy/engine/runners/worker.py` — worker subprocess reconstruction path is unchanged.
- `src/scieasy/engine/scheduler.py` — scheduler is unchanged.
- `src/scieasy/blocks/base/*` — `Block` ABC, `InputPort`, `OutputPort`, `BlockConfig`, `BlockSpec` are unchanged.
- `src/scieasy/blocks/process/*` — `ProcessBlock` is unchanged.
- `src/scieasy/blocks/code/*` — `CodeBlock` is unchanged.
- `src/scieasy/blocks/app/*` — `AppBlock` is unchanged.
- `src/scieasy/blocks/ai/*` — AI blocks are unchanged.
- Any test under `tests/core/`, `tests/engine/`, `tests/integration/` that does not currently import from `scieasy.blocks.io.adapters.*` or `scieasy.blocks.io.adapter_registry`.

#### Test impact

| Test file | Action |
|---|---|
| `tests/blocks/test_adapter_registry.py` | Delete |
| `tests/blocks/test_adapters.py` | Delete |
| `tests/blocks/test_core_loaders.py` | Create — covers D1, D3, D4, D8 |
| `tests/blocks/test_core_savers.py` | Create — covers D3, D7 |
| `tests/blocks/test_ioblock_base.py` | Create — covers D1 (ABC enforcement), D7 (default run dispatch), D8 (format detection helper) |
| Any test under `tests/blocks/test_io_block.py` that instantiates `IOBlock()` directly | Migrate to one of the concrete core loaders |
| `tests/integration/test_block_sdk_e2e.py` | Audit for `IOBlock(format=...)` usage; migrate any hits to specific loaders |

#### Migration guide for workflow YAML files

Pre-ADR-028 workflow YAML:

```yaml
blocks:
  - id: load
    type: io_block
    config:
      direction: input
      path: data/input.csv
```

Post-ADR-028 equivalent:

```yaml
blocks:
  - id: load
    type: load_dataframe
    config:
      path: data/input.csv
```

The block `type` field changes from the generic `io_block` to the specific loader name (`load_array`, `load_dataframe`, `load_series`, `load_text`, `load_artifact`, `load_composite_data`, or a plugin-provided name like `load_image`). The `direction` field is removed; the block class encodes it. The `path` field is unchanged.

For save blocks:

```yaml
# Before
- id: save
  type: io_block
  config:
    direction: output
    path: data/output.parquet

# After
- id: save
  type: save_dataframe
  config:
    path: data/output.parquet
```

The implementation PR ships a small `scieasy migrate-workflow <file.yaml>` helper that rewrites old workflow files in place. The helper is explicitly optional — not shipping it would also be acceptable because no production workflows exist yet.

### Open questions deferred to implementation

The following details are deliberately left for the implementation PR(s) to resolve, rather than being locked in this ADR. The implementation author is expected to pick the simplest option consistent with the ADR's decision text and document the choice in the PR body.

1. **Zarr `.attrs` key name for `axes` metadata**. `"axes"`, `"scieasy_axes"`, `"_axes"`, or nested under `"scieasy": {"axes": [...]}`? Low stakes; pick whichever matches the Phase 10 convention in `tiff_adapter.py::write`.

2. **Sidecar JSON filename for `.npy` / `.npz`**. `foo.npy` → `foo.npy.json` or `foo.json` or `foo_meta.json`? Low stakes; pick the least-ambiguous option.

3. **`LoadText` encoding auto-detection**. Ship `charset-normalizer` as a dependency, or require users to pass `encoding` explicitly? Decision: require explicit encoding (UTF-8 default), no auto-detection. This is lower-risk and avoids a new dependency. Documented here to save the implementation author from re-litigating.

4. **`LoadArtifact` `mime_type` detection**. Use Python's `mimetypes` stdlib module (always available) or add `python-magic` (libmagic binding) for content sniffing. Decision: `mimetypes` only. Extension-based is sufficient; content sniffing adds a system dependency.

5. **`SaveCompositeData` manifest file format**. JSON (per Phase 10's `backend_router.py`) or YAML? Decision: JSON. Keep consistency with existing composite persistence.

6. **Whether the default `run()` should catch `FileNotFoundError` and wrap with additional context**. Decision: no — let it propagate. Subclasses can wrap if they want, but the framework should not swallow.

7. **Whether the CLI `scieasy migrate-workflow` helper is part of the implementation PR or a follow-up**. Decision: follow-up, issue filed separately. The ADR implementation PR must not block on tooling.

### Relationship to other ADRs

- **Supersedes**: ADR-025 §6 "Adapter registration via entry-points". The `scieasy.adapters` entry-point group is removed. The rest of ADR-025 (blocks entry-point group §1, package metadata §2, two-level categorization §3, types entry-point group §4, custom metadata persistence §5, built-in blocks strategy §7) stands unchanged.
- **Depends on**: ADR-009 (registry stores specs) — `BlockRegistry` is the surviving registry for IO blocks. ADR-027 (Phase 10 core type system) — the seven base types this ADR provides loaders for. ADR-027 Addendum 1 §1 (typed reconstruction) — the downstream path for any loaded DataObject.
- **Does not affect**: ADR-017 (subprocess isolation), ADR-018 + Addendum 1 (scheduler), ADR-019 (ProcessHandle), ADR-020 + Addenda (Collection transport), ADR-021 (collection operations), ADR-022 (memory monitoring). These operate at the runtime layer which is orthogonal to how IO blocks are structured.
- **Enables**: Phase 11 Track 2 (`scieasy-blocks-imaging`), Track 3 (`scieasy-blocks-srs`), Track 4 (`scieasy-blocks-lcms`). All three plugin packages ship their primary user-facing blocks via the `IOBlock` ABC path specified here. The three plugin specs (`docs/specs/phase11-imaging-block-spec.md`, `phase11-srs-block-spec.md`, `phase11-lcms-block-spec.md`) will reference this ADR as their IO contract source of truth.

## ADR-028 Addendum 1: Dynamic port override mechanism and GUI consequences

**Status**: proposed
**Date**: 2026-04-07

### Purpose

ADR-028 (merged in PR #294) refactored `IOBlock` into an abstract base class and deleted the central adapter registry. Three cross-cutting concerns surfaced during the Phase 11 design review that ADR-028 itself did not cover:

1. **GUI hardcoding breakage** — `frontend/src/components/nodes/BlockNode.tsx` contains three hardcoded `blockType === "io_block"` special cases that break after ADR-028 because there is no longer a single `io_block` type_name.
2. **Dynamic port type for core IO** — During design review, the user chose a single-palette-entry design for core IO: one `Load Data` block with a dropdown to select the output type from the six core DataObject base types, rather than six separate loader classes in the palette.
3. **ADR-028 §D3 override** — The six concrete core loader/saver pairs specified in ADR-028 §D3 are replaced with two dynamic blocks (`LoadData`, `SaveData`) that dispatch internally via private module-level functions.

This Addendum resolves all three concerns in a single coherent document by introducing a minimal dynamic-port override mechanism on the `Block` ABC, locking the GUI changes required to consume it, and explicitly overriding ADR-028 §D3 for core IO. The mechanism is deliberately constrained to **enum-only declarative mapping** — it does not attempt to support variadic port count (user adds/removes ports via the GUI), which remains out of scope for this Addendum and is tracked in ADR-029 (preliminary, scope pending).

This Addendum **does not** modify any of the other ADR-028 decisions (D1, D2, D4-D14 stand unchanged) and does **not** touch any of the doc-phase scope boundaries ADR-028 set for ARCHITECTURE.md / block-sdk.md / PROJECT_TREE.md updates. Those updates remain scheduled for the Sprint A sub-1b PR-D follow-up. This Addendum does supersede ADR-028 §D3 ("Seven core loader/saver pairs") and documents that supersession explicitly.

### Context

#### Concern 1: GUI hardcoding breakage

`frontend/src/components/nodes/BlockNode.tsx` has three hardcoded checks against the string `"io_block"` that were added to handle the pre-ADR-028 generic `IOBlock` class. After ADR-028, `io_block` is no longer a concrete class in the palette — it is an abstract base with concrete subclasses like `LoadArray`, `LoadDataFrame`, and plugin-provided `LoadImage`. The three hardcoded hits break or produce surprising behaviour:

1. **`BlockNode.tsx:179`** — `const showBrowse = blockType === "io_block" && key === "path";` — renders a "Browse" button next to the `path` config field only when the block's type_name is exactly `"io_block"`. After ADR-028, `type_name` for core loaders will be `"load_array"`, `"load_dataframe"`, `"load_data"`, etc., so the browse button disappears entirely from every IO block. Plugin-provided `LoadImage` (`type_name = "load_image"`) also loses the browse button.

2. **`BlockNode.tsx:241-243`** — the inline config field filter hides the `direction` property specifically on `io_block` nodes. After ADR-028, `direction` is no longer a user-editable config field (it is a ClassVar `"input"` or `"output"` on the subclass). The hide logic must be generalised or else every loader/saver block will render a direction dropdown that has no effect.

3. **`BlockNode.tsx:247-249`** — computes `ioDirection = data.blockType === "io_block" ? data.config?.direction : undefined` and passes it to the `InlineConfigField` so the Browse button knows whether to open a file picker (load) or directory picker (save). After ADR-028, `data.config?.direction` does not exist because direction is a ClassVar, not a runtime config value. The Browse button would always default to file picker, breaking save blocks.

None of these checks can be left in place. All three must be generalised to rely on the `category === "io"` discriminator (which Stage 10.1 already added to `BlockSchemaResponse`) plus a new `direction` field on the schema payload that is populated from the backend ClassVar at scan time.

#### Concern 2: Dynamic port type for core IO

ADR-028 §D3 specified six concrete core loader classes (`LoadArray`, `LoadDataFrame`, `LoadSeries`, `LoadText`, `LoadArtifact`, `LoadCompositeData`) and six corresponding savers. This would produce twelve distinct palette entries for "core IO" alone, before plugin packages contribute their own loader blocks.

During design review the user observed that twelve palette items for core IO is visually dense and asked for a consolidated design: **one `Load Data` palette entry and one `Save Data` palette entry**, each with an internal "Data type" dropdown that picks which of the six base types the block produces. The output port's `accepted_types` must update when the dropdown selection changes, and the port's colour (inherited via `resolveTypeColor()` from the type hierarchy) must update to reflect the new type.

This is the first case in SciEasy where a block's ports depend on its instance configuration. The existing `Block.input_ports` and `Block.output_ports` are `ClassVar[list[...]]` — their values are frozen at class definition time and cannot change per-instance. To deliver the `Load Data` UX, the framework needs an override point for per-instance port resolution.

Two dimensions of dynamism exist in the Phase 11 block surface:

| Dimension | Static | Dynamic | Example |
|---|---|---|---|
| Port **type** | Fixed at class level | Chosen at instance level | `LoadData` picks type from dropdown |
| Port **count** | Fixed at class level | User adds/removes | `AIBlock` variadic inputs/outputs |

These two dimensions have the same underlying mechanism ("effective ports are computed per instance") but very different GUI requirements. The type dimension needs only a dropdown and an enum→type mapping. The count dimension needs "add port" / "remove port" UI controls and a richer per-port editor.

**This Addendum addresses the type dimension only.** The count dimension (AI variadic, CodeBlock variadic) is deferred to ADR-029, which will be a preliminary draft that records the problem without making decisions.

#### Concern 3: ADR-028 §D3 override

The original ADR-028 §D3 lists six concrete core loader/saver pairs as separate classes:

```
LoadArray / SaveArray
LoadDataFrame / SaveDataFrame
LoadSeries / SaveSeries
LoadText / SaveText
LoadArtifact / SaveArtifact
LoadCompositeData / SaveCompositeData
```

This Addendum replaces that with:

```
LoadData / SaveData  (two dynamic blocks)
  |
  +-- dispatches internally to private module-level functions:
      _load_array(config), _load_dataframe(config), _load_series(config),
      _load_text(config), _load_artifact(config), _load_composite_data(config)
      and the symmetric _save_* set
```

The six-pair structure disappears from the palette. The six internal format-handling functions still exist — they are where the adapter merge logic from ADR-028 §D2 lands — but they are private to the `load_data.py` / `save_data.py` modules and never appear as palette blocks or as importable classes.

**Why private functions and not helper classes** (Q-B from the design conversation): the six dispatch functions are called exactly once each per `load()` invocation, do not need state, do not need a common interface other than `(BlockConfig) -> DataObject`, and do not benefit from polymorphism (the dispatch is an `if-elif` chain on a config string). A helper class per function would add class-definition boilerplate, MRO lookups, and instance construction cost for no benefit. The user explicitly chose private functions; this Addendum locks that decision.

**Plugin IO blocks are unaffected.** `LoadImage` in `scieasy-blocks-imaging` remains a single concrete class with static `output_ports = [OutputPort(accepted_types=[Image])]`. Plugin authors who want to ship typed loaders continue to do so via the standard Phase 10 pattern. The dynamic mechanism is available to them via `get_effective_*_ports()` overrides if they want it, but plugin IO blocks for single-type formats (TIFF → Image, mzML → MSRawFile) stay static and get automatic port colouring from `resolveTypeColor()`'s type-hierarchy walk.

### Discussion points and resolution

| # | Topic | Options discussed | Final decision |
|---|---|---|---|
| 1 | Should dynamic ports be a new `DynamicBlock` base class, a mixin, or methods on `Block`? | (A) New `DynamicBlock(Block)` sibling base class alongside `ProcessBlock` / `CodeBlock` / `IOBlock` / `AppBlock` / `AIBlock`. (B) `DynamicPortsMixin` mixin for multiple inheritance. (C) Two default-implementation methods on `Block` itself that subclasses override when needed. | **Decision: (C).** Dynamic ports are orthogonal to execution model. A new base class would create Cartesian product problems (`DynamicIOBlock`, `DynamicAIBlock`, `DynamicCodeBlock`, ...). A mixin adds multiple-inheritance complexity. Two default methods on `Block` — `get_effective_input_ports(self)` and `get_effective_output_ports(self)` — add zero surface area for static blocks (default returns the ClassVar) and a clean override point for dynamic blocks. This mirrors Phase 10's "no `SpatialBlock` base class, use `iterate_over_axes` function" decision (ADR-027 D5). |
| 2 | How should the declarative mapping between a config field and port types be expressed? | (A) Enum-only mapping: `{source_config_key: str, output_port_mapping: dict[port_name, dict[enum_value, list[type_name]]]}`. (B) Mini-DSL with expressions: `"output_types": "[Array] if config.core_type == 'Array' else [DataFrame]"`. (C) Python lambda closures. | **Decision: (A).** Enum-only. The user explicitly restricted the mechanism to this simple case (Q-A). A mini-DSL invites parsing, security, and user-confusion problems for a benefit no one has asked for. Lambda closures cannot round-trip through JSON for frontend consumption. Dynamic blocks whose port rules are more complex than enum dispatch simply override `get_effective_*_ports(self)` in Python and skip the declarative mapping entirely — the frontend falls back to reading `output_ports` (the ClassVar placeholder) for palette display and calls the backend to recompute when config changes. The current Addendum does not implement that backend-round-trip path; it is explicitly deferred to ADR-029. |
| 3 | Where does `dynamic_ports` live on the block class? | (A) `ClassVar[dict[str, Any]] = {}` on `Block`. (B) A separate `PortPolicy` dataclass attached via `dynamic_ports: ClassVar[PortPolicy | None] = None`. (C) A decorator `@dynamic_ports(...)`. | **Decision: (A).** A `ClassVar[dict[str, Any] \| None] = None` on `Block`. Simplest possible form. Validation that the dict has the expected shape happens once at registry scan time via `BlockRegistry._validate_dynamic_ports(cls)`. A `PortPolicy` dataclass is overkill for the two-level nested dict structure the mechanism needs. A decorator adds magic for no benefit. |
| 4 | How does the frontend learn about `dynamic_ports`? | (A) Add a `dynamic_ports` field to `BlockSchemaResponse`. (B) Inline the mapping into `config_schema` as a custom `ui_widget` property. (C) Separate API endpoint `/api/blocks/<id>/dynamic_ports`. | **Decision: (A).** Add a `dynamic_ports: dict \| None = None` field to `BlockSchemaResponse` (Pydantic model in `src/scieasy/api/schemas.py`). The frontend reads the field once when the user drops the block onto the canvas and then recomputes ports locally whenever the driving config field changes. No API round-trip per change. |
| 5 | How does the backend compute `get_effective_output_ports()` for `LoadData`? | (A) Hardcode a `_CORE_TYPE_MAP` dict inside `load_data.py` mapping enum strings to classes. (B) Look up via `TypeRegistry.resolve`. (C) Use `importlib.import_module`. | **Decision: (A).** Hardcode the six core type mappings in a module-level `_CORE_TYPE_MAP: dict[str, type[DataObject]]` at the top of `load_data.py`. The six core types are stable Phase 10 contract, not user-extensible. Using `TypeRegistry.resolve` adds a registry dependency for no benefit; `importlib` adds runtime overhead. The hardcoded map is 6 lines and self-documenting. |
| 6 | Where does the framework read the effective ports? | (A) Every call site that currently reads `self.input_ports` / `self.output_ports` changes to `self.get_effective_*_ports()`. (B) Only the hot paths change. (C) Introduce a property setter that caches on change. | **Decision: (A).** Audit every read of `.input_ports` / `.output_ports` in the framework and update each one. Static blocks pay zero cost (default implementation returns the ClassVar list). Caching adds complexity for a mechanism that runs at most once per block instance per workflow execution. The audit is small: `Block.validate`, `ProcessBlock.run`, `workflow/validator.py`, `api/routes/blocks.py` plus a few peripheral call sites. |
| 7 | How does `workflow/validator.py` handle a dynamic block's port check? | (A) Use the class-level ClassVar (may be wrong for dynamic blocks). (B) Use `get_effective_*_ports()` on a temporary instance constructed with the workflow node's config. (C) Skip port validation for dynamic blocks. | **Decision: (B).** The workflow validator constructs a temporary `Block` instance from the workflow node's config (which it already has because it is validating a specific workflow), then calls `block.get_effective_input_ports()` / `get_effective_output_ports()` to get the effective port lists for that specific node. Static blocks still produce the same ClassVar values; dynamic blocks produce per-instance values that reflect the user's selection. |
| 8 | How does the GUI `Browse` button learn whether to open a file picker or directory picker? | (A) Read `data.config?.direction` (current, broken after ADR-028). (B) Read `data.schema?.direction` (new field, populated from the block class's `direction` ClassVar). (C) Infer from `type_name.startsWith("load_")` vs `"save_"`. | **Decision: (B).** Add a `direction: str \| None = None` field to `BlockSchemaResponse` that is populated from `cls.direction` at API response construction time. The frontend reads `data.schema?.direction` and branches accordingly. Option (C) is brittle because plugin authors might name their blocks anything. Option (A) is broken after ADR-028 because `direction` is no longer a runtime config value. |
| 9 | What happens to the six concrete loader/saver classes originally specified in ADR-028 §D3? | (A) Keep them as private classes, used internally by `LoadData` / `SaveData` via composition. (B) Replace with private module-level functions. (C) Keep six classes but hide from the palette via a `palette_hidden: ClassVar[bool] = True` flag. | **Decision: (B).** Private module-level functions `_load_array(config) -> Array`, `_load_dataframe(config) -> DataFrame`, etc. inside `load_data.py`. Symmetric `_save_*(obj, config)` functions inside `save_data.py`. No separate classes. The user explicitly chose this (Q-B). ADR-028 §D3 is superseded on this point. |
| 10 | Are plugin IO blocks required to use the dynamic mechanism? | (A) Required — plugins must use `dynamic_ports` if their loader produces more than one type. (B) Optional — plugins can be static (one class per type) or dynamic (one class with a dropdown) at the author's discretion. | **Decision: (B).** Plugin IO blocks are free to be static or dynamic. Most plugin loaders target a single file format that produces a single type (TIFF → Image, mzML → MSRawFile) and should stay static. The dynamic mechanism is available when it adds value. Static plugin blocks automatically inherit the correct port colour from the type hierarchy via `resolveTypeColor()`, so no frontend work is needed per plugin. |
| 11 | How does the Browse button generalise from `blockType === "io_block"` to a property-based discriminator? | (A) Use `data.category === "io"`. (B) Use `data.schema?.direction != null`. (C) Use a new `config_schema.properties.path.ui_widget = "path_picker"` annotation. | **Decision: (A) + per-field override**. Primary rule: any block with `data.category === "io"` that has a `path` config field gets a Browse button on that field. This covers core `LoadData` / `SaveData` and all plugin IO blocks that follow the standard `category = "io"` convention. A rare block that wants a path field without the Browse button can omit the `path` field name (rename to `file_location` etc.), but this is a degenerate case. Option (C) is a more explicit but more verbose opt-in; not needed for Phase 11. |
| 12 | Does the worker subprocess (`_reconstruct_one` / `_serialise_one`) need changes to handle dynamic blocks? | (A) Yes — add `dynamic_ports` to the wire format. (B) No — the worker receives the already-resolved effective ports from the engine. | **Decision: (B).** Dynamic port resolution happens in the engine (which has the block instance and its config). The worker subprocess receives already-resolved data with concrete types. When the worker reconstructs a `DataObject` via `_reconstruct_one`, the type comes from `metadata.type_chain`, not from any port-level information. The worker neither knows nor cares whether the block is dynamic. ADR-027 Addendum 1 §1 (worker reconstruction contract) is unaffected. |
| 13 | Is the variadic port count (AI variadic, CodeBlock variadic) in scope? | (A) Yes — design the full mechanism that handles both type and count dimensions. (B) No — defer to a separate ADR. | **Decision: (B).** Variadic port count requires frontend "add port" / "remove port" controls, per-instance port configuration storage, and a significantly more complex backend mechanism (the port list is variable length, each port has its own name and type). That work is large enough to warrant its own ADR. ADR-029 (preliminary) reserves the namespace and lists the open questions. This Addendum does not constrain ADR-029's design — it only provides the `get_effective_*_ports()` override mechanism that ADR-029 will build on. |

### Decision

The decisions from the discussion table are codified below as D1' through D9' (with prime marks to distinguish from ADR-028's D1-D14). Each decision has a one-paragraph summary, a code-shape sketch where appropriate, and a line-by-line impact reference in the "Detailed impact scope" section.

#### D1'. `get_effective_input_ports` / `get_effective_output_ports` override points on `Block` (covers #1, #6)

The `Block` ABC in `src/scieasy/blocks/base/block.py` gains two new methods with default implementations that return the class-level `input_ports` / `output_ports` ClassVar lists. Dynamic-port blocks override these methods to compute per-instance port lists from `self.config`.

```python
class Block(ABC):
    # ... existing ClassVars ...
    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = []

    # New Addendum 1 override points.
    def get_effective_input_ports(self) -> list[InputPort]:
        """Return the effective input ports for this block instance.

        ADR-028 Addendum 1 D1': default implementation returns
        ``type(self).input_ports``. Dynamic-port blocks (e.g. ``LoadData``)
        override this method to read ``self.config`` and compute a
        per-instance port list.

        The framework's port-check, scheduler, and workflow-validator
        read-paths use this method rather than reading the ClassVar
        directly, so static blocks pay zero cost while dynamic blocks
        get the override point they need.
        """
        return list(type(self).input_ports)

    def get_effective_output_ports(self) -> list[OutputPort]:
        """Return the effective output ports for this block instance.

        See :meth:`get_effective_input_ports` for the override contract.
        """
        return list(type(self).output_ports)
```

The defaults return a **copy** of the ClassVar list (via `list(...)`) rather than the list itself so that callers cannot mutate the class state by appending to the returned list. This matches the defensive-copy pattern used by Phase 10's `DataObject.user` property.

Static blocks pay one `type(self).input_ports` lookup and one `list(...)` copy per call. Dynamic blocks pay whatever they choose inside their override. Neither cost is on the hot path (port lookups happen at validation/dispatch time, not per-item).

#### D2'. `dynamic_ports` declarative ClassVar on `Block` (covers #2, #3)

`Block` gains a new ClassVar:

```python
class Block(ABC):
    # ... existing ClassVars ...
    dynamic_ports: ClassVar[dict[str, Any] | None] = None
```

The shape of the dict (when non-None) is strictly fixed to the enum-mapping form:

```python
dynamic_ports = {
    "source_config_key": "core_type",   # which config field drives the mapping
    "output_port_mapping": {            # per-port mapping
        "data": {                       # port name
            "Array":         ["Array"],         # enum value -> list of type names
            "DataFrame":     ["DataFrame"],
            "Series":        ["Series"],
            "Text":          ["Text"],
            "Artifact":      ["Artifact"],
            "CompositeData": ["CompositeData"],
        },
    },
    # optionally, "input_port_mapping" with the same shape for input ports
}
```

The enum values in the mapping must be the exact string values declared in `config_schema.properties[source_config_key].enum`. Type names in the value list must be strings that are resolvable via `TypeRegistry.resolve([type_name])` — core type names (`"Array"`, `"DataFrame"`, etc.) for core blocks, plugin type names (`"Image"`, `"FluorImage"`) for plugin blocks.

**Validation at registration time**: `BlockRegistry.register()` (or `_build_spec()`) calls a new helper `_validate_dynamic_ports(cls)` that checks:
1. If `cls.dynamic_ports is None`, return immediately (static block).
2. Otherwise, `cls.dynamic_ports` must be a dict with keys `source_config_key: str` and `output_port_mapping: dict[str, dict[str, list[str]]]` (input_port_mapping is optional, same shape).
3. `source_config_key` must exist as a property in `cls.config_schema["properties"]`.
4. The enum values in the mapping must match `cls.config_schema["properties"][source_config_key]["enum"]` exactly (set equality).
5. Every port name in the mapping must exist in `cls.output_ports` (or `cls.input_ports`) — the ClassVar list is the placeholder for the palette preview.
6. Every type name in the mapping's value lists must be importable (`TypeRegistry.resolve` returns non-None). Non-importable type names are logged as a warning at registration time but do not fail registration.

Validation failures raise `ValueError` at registration time with a clear message pointing at the offending block class and field.

#### D3'. `BlockSpec` and `BlockSchemaResponse` changes (covers #4, #8)

`BlockSpec` (the dataclass stored in `BlockRegistry`) gains a field:

```python
# src/scieasy/blocks/registry.py
@dataclass
class BlockSpec:
    # ... existing fields ...
    dynamic_ports: dict[str, Any] | None = None
    direction: str | None = None          # from cls.direction for IOBlock subclasses
```

The `direction` field on `BlockSpec` is populated at scan time via `getattr(cls, "direction", None)`. Non-IOBlock classes have no `direction` ClassVar and this field stays `None`.

`BlockSchemaResponse` (Pydantic model in `src/scieasy/api/schemas.py`) gains the same two fields:

```python
# src/scieasy/api/schemas.py
class BlockSchemaResponse(BlockSummary):
    """Detailed schema payload for a single block type."""
    config_schema: dict[str, Any] = Field(default_factory=dict)
    type_hierarchy: list[TypeHierarchyEntry] = Field(default_factory=list)
    # New Addendum 1 fields
    dynamic_ports: dict[str, Any] | None = None
    direction: str | None = None
```

`_schema_response()` (in `src/scieasy/api/routes/blocks.py`) and `_summary()` are updated to populate both fields from `BlockSpec`.

The frontend TypeScript types in `frontend/src/types/api.ts` are updated to match:

```typescript
export interface BlockSchemaResponse extends BlockSummary {
  config_schema: Record<string, unknown>;
  type_hierarchy: TypeHierarchyEntry[];
  dynamic_ports?: DynamicPortsMapping;
  direction?: "input" | "output";
}

export interface DynamicPortsMapping {
  source_config_key: string;
  output_port_mapping?: Record<string, Record<string, string[]>>;
  input_port_mapping?: Record<string, Record<string, string[]>>;
}
```

#### D4'. Framework read-path migration (covers #6, #7)

Every call site that currently reads `.input_ports` or `.output_ports` on a block instance changes to call `get_effective_*_ports()`. The audit:

| File | Before | After |
|---|---|---|
| `src/scieasy/blocks/base/block.py:92` | `port_map = {p.name: p for p in self.input_ports}` | `port_map = {p.name: p for p in self.get_effective_input_ports()}` |
| `src/scieasy/blocks/base/block.py:95` | `for port in self.input_ports:` | `for port in self.get_effective_input_ports():` |
| `src/scieasy/blocks/process/process_block.py:160` | `output_name = self.output_ports[0].name if self.output_ports else "output"` | `ports = self.get_effective_output_ports(); output_name = ports[0].name if ports else "output"` |
| `src/scieasy/blocks/process/process_block.py:165` | (same pattern) | (same pattern) |
| `src/scieasy/workflow/validator.py:190` | `for port in spec.input_ports:` (reads class spec) | For dynamic blocks: construct a temporary instance from the workflow node's config and call `block.get_effective_input_ports()`. For static blocks: fall through to the class-level list. See the validator implementation sketch below. |
| `src/scieasy/api/routes/blocks.py:54-55` | `input_ports=[_port_response(port, ...) for port in spec.input_ports]` | For static blocks: unchanged (reads class spec for palette preview). For dynamic blocks: palette preview shows the placeholder ports from the ClassVar, and the frontend recomputes per-instance ports from `dynamic_ports`. |

**Workflow validator sketch** (for `workflow/validator.py`):

```python
def _get_effective_ports(node: WorkflowNode, spec: BlockSpec) -> tuple[list[InputPort], list[OutputPort]]:
    """Return the effective input/output ports for a workflow node.

    Static blocks: return the BlockSpec's class-level lists.
    Dynamic blocks: construct a temporary Block instance from the node's
    config and call get_effective_*_ports().
    """
    if spec.dynamic_ports is None:
        return (spec.input_ports, spec.output_ports)

    # Dynamic block - instantiate from the node's config and ask the instance
    block_cls = BlockRegistry.load_class(spec.name)
    instance = block_cls(config=node.config or {})
    return (
        instance.get_effective_input_ports(),
        instance.get_effective_output_ports(),
    )
```

The validator's type-compatibility check for a workflow edge uses `_get_effective_ports(source_node, source_spec)` for the source side and `_get_effective_ports(target_node, target_spec)` for the target side. Static blocks produce the same ClassVar lists they produce today; dynamic blocks produce per-instance lists that reflect the node's configured state.

`BlockRegistry.register()` (or equivalent scan-time entry point) calls `_validate_dynamic_ports(cls)` per D2' so malformed `dynamic_ports` declarations fail loudly at startup rather than at workflow validation time.

#### D5'. LoadData and SaveData concrete design (covers #5, #9)

ADR-028 §D3's six loader classes become two concrete classes (`LoadData` and `SaveData`) plus twelve private module-level functions. The file layout:

```
src/scieasy/blocks/io/
|-- __init__.py            (re-exports IOBlock, LoadData, SaveData)
|-- io_block.py            (IOBlock ABC - per ADR-028 D1)
|-- loaders/
|   |-- __init__.py        (re-exports LoadData)
|   `-- load_data.py       (LoadData class + six private _load_* functions)
`-- savers/
    |-- __init__.py        (re-exports SaveData)
    `-- save_data.py       (SaveData class + six private _save_* functions)
```

`LoadData` exact shape is locked in the Sprint A sub-1b PR-B implementation ticket (summary: `type_name = "load_data"`, `category = "io"`, `direction = "input"`, a placeholder `output_ports = [OutputPort(name="data", accepted_types=[DataObject])]` for the palette preview, a `dynamic_ports` ClassVar with `source_config_key = "core_type"` and an `output_port_mapping` for the "data" port covering all six core type enum values, a `config_schema` declaring `core_type` enum + `path` + `allow_pickle` + `separator` + `encoding` properties, a `get_effective_output_ports()` override that reads `self.config["core_type"]` and returns a single `OutputPort` with `accepted_types=[_CORE_TYPE_MAP[type_name]]`, and a `load()` implementation that dispatches through six private functions `_load_array`/`_load_dataframe`/`_load_series`/`_load_text`/`_load_artifact`/`_load_composite_data`).

The six private functions absorb the format-handling logic from the deleted bundled adapters per ADR-028 §D2 and §D5:

- `_load_array(config)` — absorbs `zarr_adapter.py`, handles `.zarr` / `.npy` / `.npz` with metadata sidecar JSON.
- `_load_dataframe(config)` — absorbs `parquet_adapter.py` and `csv_adapter.py`, handles `.parquet` / `.pq` / `.csv` / `.tsv` / `.txt` / `.pkl` / `.pickle`. Pickle requires `allow_pickle=True`.
- `_load_series(config)` — absorbs the single-column Parquet/CSV path, enforces single-column, supports `.pkl` / `.pickle`.
- `_load_text(config)` — filesystem read, UTF-8 default, honours `encoding` config.
- `_load_artifact(config)` — absorbs `generic_adapter.py`, opaque byte copy, sets `mime_type` from extension.
- `_load_composite_data(config)` — reads a directory containing `manifest.json` and recurses into `_reconstruct_one` per slot.

`SaveData` has the symmetric structure in `src/scieasy/blocks/io/savers/save_data.py` with:
- `direction: ClassVar[str] = "output"`
- `type_name: ClassVar[str] = "save_data"`
- `input_ports` placeholder instead of output_ports placeholder
- `dynamic_ports` maps to `input_port_mapping` instead of `output_port_mapping`
- `save(obj, config)` method that dispatches to private `_save_array`, `_save_dataframe`, etc.
- `get_effective_input_ports()` override mirroring `LoadData.get_effective_output_ports()`

The private save functions are symmetric counterparts of the load functions and absorb the save-path logic from the same deleted adapters.

**Key clarification**: The six private `_load_*` / `_save_*` functions are the **only** place the format-handling logic from the deleted bundled adapters lives in core. They are not exported, not tested via import, and do not appear in the palette. ADR-028 §D3's "Seven core loader/saver pairs" (actually six pairs, because `DataObject` has no loader) is superseded — those classes do not exist in Phase 11 core.

**All implementation details for these six functions (format probing, metadata sidecar handling, pickle opt-in enforcement, compound extension detection for `.composite/` directories) are locked in ADR-028 §D3 and §D5 — this Addendum does not repeat them, it only changes where the logic lives (private functions in two modules, not methods on six classes).**

#### D6'. GUI hardcoding removal and Browse button generalisation (covers #1, #11)

`frontend/src/components/nodes/BlockNode.tsx` changes:

**Change 1** (around line 179): Browse button shows on any block with `category === "io"` that has a `path` config field, not just blocks with `blockType === "io_block"`.

```typescript
// Before
const showBrowse = blockType === "io_block" && key === "path";

// After (D6' / D11)
const showBrowse = data.category === "io" && key === "path";
```

**Change 2** (around lines 241-243): The hidden-direction filter generalises from `blockType === "io_block"` to `category === "io"`.

```typescript
// Before
const configProps = getTopConfigProperties(data.schema?.config_schema).filter(
  (prop) => !(data.blockType === "io_block" && prop.key === "direction"),
);

// After
const configProps = getTopConfigProperties(data.schema?.config_schema).filter(
  (prop) => !(data.category === "io" && prop.key === "direction"),
);
```

Note that after ADR-028, `direction` is no longer a runtime config field — it is a ClassVar on the block class. Therefore this filter is largely defensive (there should be no `direction` key in `config_schema.properties` for any post-ADR-028 IO block) but is kept as a safety net in case a plugin author accidentally adds a direction property.

**Change 3** (around lines 247-249): `ioDirection` reads from `data.schema?.direction` (new field from D3') instead of `data.config?.direction`.

```typescript
// Before
const ioDirection = data.blockType === "io_block"
  ? (data.config?.direction as string | undefined) ?? "input"
  : undefined;

// After (D6' / D8)
const ioDirection = data.category === "io"
  ? (data.schema?.direction as "input" | "output" | undefined) ?? "input"
  : undefined;
```

#### D7'. Frontend dynamic port recomputation (covers #2, #4)

When `BlockNode.tsx` renders a node whose schema has a non-null `dynamic_ports` field, the component watches the driving config field and recomputes the effective port list client-side whenever the user changes the selection.

Implementation sketch (pseudocode):

```typescript
function computeEffectivePorts(
  basePorts: BlockPortResponse[],
  dynamicMapping: DynamicPortsMapping | undefined,
  currentConfig: Record<string, unknown>,
): BlockPortResponse[] {
  if (!dynamicMapping || !dynamicMapping.output_port_mapping) {
    return basePorts;
  }
  const driverValue = currentConfig[dynamicMapping.source_config_key];
  if (typeof driverValue !== "string") {
    return basePorts;
  }
  return basePorts.map((port) => {
    const portMapping = dynamicMapping.output_port_mapping?.[port.name];
    if (!portMapping || !portMapping[driverValue]) {
      return port;
    }
    return {
      ...port,
      accepted_types: portMapping[driverValue],
    };
  });
}

// In BlockNode.tsx:
const effectiveOutputPorts = computeEffectivePorts(
  data.outputPorts,
  data.schema?.dynamic_ports,
  data.config ?? {},
);
// Use effectiveOutputPorts in the port-rendering loop instead of data.outputPorts.
```

Port colour updates automatically because `resolveTypeColor(effectivePorts[i].accepted_types, typeHierarchy)` is called with the freshly computed `accepted_types` list every render.

The palette preview (BlockPalette.tsx) does **not** use the dynamic recomputation — it shows the static `output_ports` / `input_ports` ClassVar placeholders (which is why `LoadData.output_ports` ships with a `DataObject`-typed placeholder that renders as light grey in the palette).

#### D8'. Plugin IO blocks remain static (documented non-change)

Plugin-provided IO blocks like `LoadImage` in `scieasy-blocks-imaging` continue to declare static `output_ports` ClassVars. They do not need to use the dynamic mechanism. Example (from the future Phase 11 imaging plugin spec):

```python
# scieasy_blocks_imaging/io/load_image.py

class LoadImage(IOBlock):
    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "load_image"
    name: ClassVar[str] = "Load Image"
    category: ClassVar[str] = "io"
    # Static output_ports - LoadImage always produces Image (or subclass).
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[Image], description="Loaded image"),
    ]
    # No dynamic_ports ClassVar - the default (None) means "static block".
    # ...
```

Port colour for `LoadImage` flows automatically via `resolveTypeColor(["Image"], typeHierarchy)` → walks the hierarchy → finds `Image → Array → blue`. No frontend work per plugin. The dynamic mechanism is opt-in.

#### D9'. ADR-028 §D3 supersession (covers #9)

This Addendum explicitly supersedes ADR-028 §D3 ("Seven core loader/saver pairs"). The original D3 listed:

```
LoadArray / SaveArray
LoadDataFrame / SaveDataFrame
LoadSeries / SaveSeries
LoadText / SaveText
LoadArtifact / SaveArtifact
LoadCompositeData / SaveCompositeData
```

as six distinct concrete classes shipped under `src/scieasy/blocks/io/loaders/` and `src/scieasy/blocks/io/savers/`. Per Addendum 1 D5' and D9' (this decision), those six pairs are replaced with:

```
LoadData (single class) + six private module-level _load_* functions
SaveData (single class) + six private module-level _save_* functions
```

living in `src/scieasy/blocks/io/loaders/load_data.py` and `src/scieasy/blocks/io/savers/save_data.py` respectively. The six private functions carry all the format-handling logic absorbed from the deleted bundled adapters per ADR-028 §D2 and §D5.

The ADR-028 §"Detailed impact scope" / "Files to create" table's rows for `loaders/array.py`, `loaders/dataframe.py`, `loaders/series.py`, `loaders/text.py`, `loaders/artifact.py`, `loaders/composite.py` (and the symmetric `savers/` rows) are **superseded** by this Addendum. The actual files created in the Sprint A sub-1b implementation PRs are only `loaders/load_data.py` and `savers/save_data.py`.

The ADR-028 §D3 table of "Supported extensions" per base type is **unchanged** — the same format set applies, just dispatched through the private functions instead of separate classes.

### Alternatives considered

**Alternative I — Don't introduce a dynamic port mechanism; keep six separate classes.** Under this alternative, ADR-028 §D3 stands as-is. The palette gets six `Load*` entries plus six `Save*` entries for core IO alone.

*Rejected because*:
- The user explicitly chose the consolidated single-palette-entry design.
- Twelve core IO palette entries is visually dense and makes the "Core > io" category crowded before plugin packages contribute their own loaders.
- The dynamic mechanism introduced by this Addendum is small (two methods, one ClassVar, one API field, one frontend helper). The cost of introducing it is lower than the cost of twelve palette entries.

**Alternative II — Hide the six loader classes from the palette via a `palette_hidden: bool` flag and add a meta-palette-entry that dispatches at drag time.** Under this alternative, the six classes exist but don't appear in the palette. A single "Load Data" palette item is a special kind of palette entry that, when dragged, spawns the concrete block class selected via the dropdown.

*Rejected because*:
- This requires a new "meta-palette-entry" concept distinct from blocks, which no other palette item uses. The frontend palette model becomes more complex.
- The spawned block class is fixed once the user selects the type, so changing the type requires deleting and re-creating the node. This is worse UX than a node whose type updates live.
- Hiding six classes from the palette but keeping them as importable classes creates a "visible from code, hidden from GUI" split that confuses documentation.

**Alternative III — Use a Pydantic discriminated union for the config and let FastAPI dispatch.** Under this alternative, `LoadData.config_schema` is a Pydantic discriminated union on `core_type`, and FastAPI returns the correct sub-schema in the API response.

*Rejected because*:
- The GUI problem is not schema dispatch — it is port type dispatch. The port types are not a Pydantic concept; they are `list[type[DataObject]]`. A discriminated union on the config does not tell the frontend what the port colour should be.
- Adding Pydantic discriminated-union machinery to a problem that a three-field ClassVar solves is complexity for no benefit.

**Alternative IV — Implement the full variadic port count mechanism in the same Addendum.** Under this alternative, Addendum 1 covers both the type dimension (LoadData) and the count dimension (AI variadic), landing both together.

*Rejected because*:
- The count dimension is significantly more complex and unlocks a much larger design space (GUI controls for add/remove port, per-port editor, constraint handling, scheduler routing, worker subprocess reconstruction).
- Bundling the two dimensions would balloon this Addendum to multi-thousand-line scope and delay the core IO refactor.
- ADR-029 is the right home for the count dimension because it deserves its own design conversation, not a sub-section of an Addendum.

### Consequences

**Non-breaking changes** (Addendum 1 is additive for static blocks):

- `Block.get_effective_input_ports()` and `get_effective_output_ports()` have default implementations that return the existing ClassVar lists. Static blocks get the new methods for free with zero behaviour change.
- `Block.dynamic_ports` defaults to `None`. Static blocks do not need to set it.
- `BlockSpec.dynamic_ports` defaults to `None`. `BlockSchemaResponse.dynamic_ports` defaults to `None`. Frontend checks `?? undefined` and falls back to static port rendering.
- `BlockSpec.direction` defaults to `None`. Non-IO blocks do not have a `direction` ClassVar and this field stays `None` in their spec.
- All existing tests of static blocks should continue to pass without modification.

**Breaking changes** (only affect ADR-028's implementation PRs, which are still pending):

- ADR-028 §D3's six concrete loader/saver pairs are replaced by two dynamic blocks. The Sprint A sub-1b PR-B implementation creates `LoadData` (not `LoadArray`, `LoadDataFrame`, etc.). The Sprint A sub-1b PR-C implementation creates `SaveData` (not the six individual savers).
- The ADR-028 "Files to create" table rows for `loaders/array.py`, `loaders/dataframe.py`, `loaders/series.py`, `loaders/text.py`, `loaders/artifact.py`, `loaders/composite.py` are deleted. Only `loaders/load_data.py` and `savers/save_data.py` are created.
- The Sprint A sub-1b PR-B/PR-C implementation agents must read this Addendum, not just ADR-028, to know the correct file layout.

**Frontend consequences**:

- `BlockNode.tsx` no longer has three hardcoded `blockType === "io_block"` checks. The generalised `category === "io"` discriminator works for any IO block, plugin-provided or core.
- The Browse button appears on any IO block's `path` config field (both core and plugin). Save blocks open a directory picker; load blocks open a file picker.
- The `direction` field is hidden from the inline config fields on any IO block (defensive, since it's no longer a runtime config value).
- Dynamic blocks (like `LoadData`) recompute their port colours live when the user changes the driving config field.
- Static plugin IO blocks (like `LoadImage`) get port colours via the existing `resolveTypeColor()` type-hierarchy walk — no per-plugin frontend work.

**Developer experience consequences**:

- Plugin authors writing simple single-type loaders (e.g. `LoadImage`, `LoadMSRawFile`) write no frontend code and declare no dynamic mechanism. They get the same consolidated UX as core `LoadData` automatically via the generic renderer.
- Plugin authors who want dynamic typed loaders declare a `dynamic_ports` ClassVar on their subclass. The declarative form is enum-only; more complex rules require a Python override of `get_effective_*_ports()`.
- The `get_effective_*_ports()` mechanism generalises to future use cases beyond IO (e.g., a plugin block that produces different types based on a "mode" config). The mechanism is available to any `Block` subclass, not just `IOBlock`.

**Known risks and mitigations**:

| Risk | Mitigation |
|---|---|
| Dynamic port recomputation client-side gets out of sync with backend state | The recomputation is purely deterministic given `dynamic_ports` mapping + current config. Backend re-derives the same port list via `get_effective_*_ports()` when it runs the block. Unit tests verify the two implementations agree for every enum value. |
| Plugin authors write malformed `dynamic_ports` ClassVars | Scan-time validation in `BlockRegistry._validate_dynamic_ports(cls)` catches malformed mappings before the block reaches the registry. Failures raise `ValueError` with the offending class name and field. |
| Workflow validator accidentally uses stale cached port lists | Workflow validator always instantiates a fresh `Block` from the node's config to call `get_effective_*_ports()`. No caching between workflow nodes. |
| `LoadData` dispatch function raises `NotImplementedError` for a valid core type | The six private dispatch functions are implementation placeholders until Sprint A sub-1b PR-B lands. The dispatch in `LoadData.load()` validates the core_type against `_CORE_TYPE_MAP` before calling the function, so unknown types raise a clear `ValueError` with the supported list. |
| Frontend recomputation fires on every keystroke for text fields that happen to have a mapping | `dynamic_ports.source_config_key` targets an enum field (dropdown), not a text field. Validation at registration time enforces this by checking that the driving config property has an `enum` list. |
| Existing static `IOBlock` tests break because the IOBlock ABC is already abstract | ADR-028 PR-A already made `IOBlock` abstract. This Addendum does not change that. Existing tests that instantiated a bare `IOBlock` were migrated to concrete loaders by PR-A. This Addendum inherits that migration. |
| Plugin tests break because the plugin's IOBlock subclass does not override `get_effective_*_ports()` | Default implementation returns the ClassVar. Plugin blocks with static `output_ports` and no `dynamic_ports` work without any additional method override. The mechanism is strictly additive for plugin authors. |

### Detailed impact scope

Implementation of Addendum 1 is **not** part of this ADR PR. The impact scope below describes what the Sprint A sub-1b implementation PR(s) must do.

#### Files to modify (backend, Phase 11 implementation PR)

| File | Changes |
|---|---|
| `src/scieasy/blocks/base/block.py` | **Add** `dynamic_ports: ClassVar[dict[str, Any] \| None] = None` ClassVar (around line 64). **Add** `get_effective_input_ports(self)` and `get_effective_output_ports(self)` methods with default implementations (after `input_ports` / `output_ports` declarations). **Update** `Block.validate()` (lines 92, 95) to use `self.get_effective_input_ports()` instead of `self.input_ports` directly. |
| `src/scieasy/blocks/process/process_block.py` | **Update** lines 160, 165 to read `self.get_effective_output_ports()` instead of `self.output_ports` directly. |
| `src/scieasy/blocks/io/io_block.py` | **Add** `direction: ClassVar[str] = "input"` at the class-body level (moved from subclass responsibility — it stays ClassVar but the IOBlock base class declares it so all subclasses inherit a default). |
| `src/scieasy/blocks/registry.py` | **Add** `dynamic_ports: dict[str, Any] \| None = None` and `direction: str \| None = None` fields to `BlockSpec` dataclass. **Add** `_validate_dynamic_ports(cls)` helper method on `BlockRegistry` that runs at registration time. **Update** `_build_spec(cls)` (or equivalent) to populate `dynamic_ports` and `direction` from the class attributes. |
| `src/scieasy/workflow/validator.py` | **Add** `_get_effective_ports(node, spec)` helper that constructs a temporary block instance for dynamic blocks. **Update** the edge type-compatibility check to use `_get_effective_ports()` instead of reading `spec.input_ports` / `spec.output_ports` directly. |
| `src/scieasy/api/schemas.py` | **Add** `dynamic_ports: dict[str, Any] \| None = None` and `direction: str \| None = None` fields to `BlockSchemaResponse` Pydantic model. |
| `src/scieasy/api/routes/blocks.py` | **Update** `_summary()` / `_schema_response()` to populate the two new fields from `BlockSpec`. |

#### Files to create (backend)

| File | Contents |
|---|---|
| `src/scieasy/blocks/io/loaders/__init__.py` | Re-export `LoadData` |
| `src/scieasy/blocks/io/loaders/load_data.py` | `LoadData` class + six private `_load_*` dispatch functions. Full implementation per D5'. |
| `src/scieasy/blocks/io/savers/__init__.py` | Re-export `SaveData` |
| `src/scieasy/blocks/io/savers/save_data.py` | `SaveData` class + six private `_save_*` dispatch functions. Symmetric counterpart of `load_data.py`. |

#### Files to modify (frontend)

| File | Changes |
|---|---|
| `frontend/src/components/nodes/BlockNode.tsx` | **Change 1** (line 179): `blockType === "io_block"` → `data.category === "io"` (Browse button). **Change 2** (line 241-243): same substitution (hide direction field). **Change 3** (line 247-249): `data.config?.direction` → `data.schema?.direction`. **Add** `computeEffectivePorts()` helper function that reads `data.schema?.dynamic_ports` and recomputes port types from current config. **Use** `effectiveOutputPorts` / `effectiveInputPorts` in the port rendering loops. |
| `frontend/src/types/api.ts` | **Add** `DynamicPortsMapping` interface. **Add** `dynamic_ports?: DynamicPortsMapping` and `direction?: "input" \| "output"` fields to `BlockSchemaResponse` interface. |

#### Files to create (tests)

| File | Contents |
|---|---|
| `tests/blocks/test_dynamic_ports_mechanism.py` | Tests for the generic mechanism: `Block.get_effective_*_ports()` default behaviour, ClassVar fallback, override semantics, defensive copy, `BlockRegistry._validate_dynamic_ports()` happy path + malformed cases. |
| `tests/blocks/test_load_data.py` | Tests for `LoadData`: palette placeholder ports, `get_effective_output_ports()` for each core_type enum value, unknown core_type raises ValueError, private `_load_*` functions raise NotImplementedError (placeholder marker for Sprint A sub-1b PR-B). |
| `tests/blocks/test_save_data.py` | Symmetric tests for `SaveData`. |
| `tests/api/test_block_schema_dynamic_ports.py` | Integration tests: `BlockSchemaResponse` includes `dynamic_ports` for `LoadData`, `direction` populated for `LoadData`/`SaveData`, static blocks produce `dynamic_ports=None` and `direction=None`. |
| `tests/integration/test_dynamic_ports_workflow.py` | End-to-end: construct a workflow with a `LoadData` node, change core_type config, verify workflow validator sees the correct effective ports. |

#### Files NOT affected (explicitly)

- `src/scieasy/core/types/*` — Phase 10 type hierarchy unchanged.
- `src/scieasy/core/types/registry.py` — TypeRegistry.resolve unchanged.
- `src/scieasy/core/types/serialization.py` — `_reconstruct_one` / `_serialise_one` unchanged (per Discussion #12).
- `src/scieasy/engine/runners/worker.py` — worker subprocess unchanged.
- `src/scieasy/engine/scheduler.py` — scheduler unchanged.
- `src/scieasy/blocks/code/*` — CodeBlock unchanged by this Addendum (variadic CodeBlock is ADR-029 scope).
- `src/scieasy/blocks/app/*` — AppBlock unchanged.
- `src/scieasy/blocks/ai/*` — AIBlock unchanged (variadic AIBlock is ADR-029 scope).
- `docs/architecture/ARCHITECTURE.md` — tracked by Sprint A sub-1b PR-D.
- `docs/architecture/PROJECT_TREE.md` — tracked by Sprint A sub-1b PR-D.
- `docs/guides/block-sdk.md` — tracked by Sprint A sub-1b PR-D.

### Open questions deferred to implementation

The following details are deliberately left for the implementation PR(s) to resolve. The implementation author picks the simplest option consistent with this Addendum's decisions.

1. **Defensive copy behaviour on `get_effective_*_ports()` default**: return `list(type(self).input_ports)` (shallow copy) or return the ClassVar directly? **Decision: shallow copy.** Prevents accidental mutation of class state. Implementation author follows this.
2. **Validator's temporary-instance construction**: does it use `block_cls(config=node.config)` or does it need a dedicated factory method? **Decision: direct constructor call** using the same `config=...` kwarg that runtime uses. No factory method needed.
3. **Frontend recomputation debouncing**: should the recomputation be throttled to avoid running on every dropdown re-render? **Decision: no debouncing**. The recomputation is pure, cheap, and the driving field is an enum dropdown that changes at most a few times per minute.
4. **Dispatching `load()` on a `LoadData` instance with an unknown `core_type`**: raise `ValueError` or fall back to `DataObject`? **Decision: raise `ValueError`** with a clear message listing the supported core types. Falling back to `DataObject` would mask typos silently.
5. **Should `BlockNode.tsx` display a warning badge when `dynamic_ports` is present but `source_config_key` resolves to an unknown value?** **Decision: no badge for now**. The current implementation falls back to the ClassVar placeholder ports. If this becomes confusing in practice, add a warning badge in a follow-up.
6. **Should `_CORE_TYPE_MAP` be exported from `load_data.py` for plugin authors who want to reuse it?** **Decision: no**. The map is private to the core IO module. Plugin authors who need the same mapping import the six core types directly and build their own map.

### Relationship to other ADRs

- **Builds on**: ADR-028 (IOBlock architectural refactor) — this Addendum is the first consumer of the dynamic-port mechanism and the first implementation of the new `IOBlock` ABC in core.
- **Supersedes**: ADR-028 §D3 "Seven core loader/saver pairs" — replaced by `LoadData` + `SaveData` + twelve private dispatch functions. The ADR-028 "Files to create" table rows for the six loader/saver class pairs are deleted.
- **Defers to**: ADR-029 (preliminary) — AI variadic port count, CodeBlock variadic port count, per-instance port editor UI. Addendum 1 provides the `get_effective_*_ports()` override mechanism that ADR-029 will build on, but makes no decisions about the count dimension.
- **Depends on**: Phase 10 core type system (ADR-027) — the six base types `LoadData` / `SaveData` dispatch over. ADR-027 Addendum 1 §1 (typed reconstruction) — not changed, worker subprocess continues to round-trip typed instances regardless of whether the producing block is dynamic or static.
- **Does not affect**: ADR-017 (subprocess isolation), ADR-018 + Addendum 1 (scheduler), ADR-019 (ProcessHandle), ADR-020 + Addenda (Collection transport), ADR-021 (collection operations), ADR-022 (memory monitoring), ADR-023-026 (frontend / distribution / SDK), ADR-024 (CLI). All orthogonal to the dynamic-port mechanism.
- **Enables**: Phase 11 Track 1 sub-1b PR-B/PR-C implementation agents have unambiguous instructions for `LoadData` / `SaveData` file layout. Phase 11 Track 2 imaging plugin's `LoadImage` block gets port colouring for free via the existing type-hierarchy walk. Phase 11 Track 3 SRS plugin's `SRSImage` port colouring via the same path. Phase 11 Track 4 LC-MS plugin's `LoadMSRawFile` port colouring via the same path.

---

## ADR-029: Variadic port count and per-instance port editor

**Status**: proposed
**Date**: 2026-04-11 (promoted from draft 2026-04-07)
**Issue**: #297, #567

> This ADR was promoted from `draft — scope pending` to `proposed` on
> 2026-04-11 after a design conversation resolved all eleven open questions
> (Q1–Q11). The Context and Open Questions sections below are preserved from
> the original draft for traceability; the Decision section records the
> chosen answer to each question.

### Purpose

ADR-028 Addendum 1 (merged 2026-04-07) introduced a minimal dynamic-port
override mechanism on the `Block` ABC: two methods
`get_effective_input_ports(self)` / `get_effective_output_ports(self)` plus an
enum-only declarative `dynamic_ports: ClassVar[dict | None]` mapping. That
mechanism handles the **type dimension** of dynamism — one block, one output
port, the output port's `accepted_types` is recomputed when an enum config
field changes. It is consumed first by core `LoadData` / `SaveData`, where the
single `core_type` dropdown ("Array" / "DataFrame" / "Series" / "Text" /
"Artifact" / "CompositeData") drives the single output port's type.

Addendum 1 explicitly **deferred the count dimension** (one block with a
variable number of input or output ports added by the user via GUI controls)
to this ADR. This ADR defines the architecture for variadic port count on
`AIBlock`, `CodeBlock`, and `AppBlock`.

### Context

#### What `AIBlock` is today

`src/scieasy/blocks/ai/ai_block.py` is a 30-line stub. The full body:

```python
class AIBlock(Block):
    """Block that uses a large language model to process data.

    *model* identifies the LLM backend; *prompt_template* holds the
    template string that is rendered with block inputs before inference.
    """

    model: ClassVar[str] = ""
    prompt_template: ClassVar[str] = ""

    def run(self, inputs, config):
        """Run the LLM inference pipeline.

        Not yet implemented — placeholder for AI-powered block execution.
        Per ADR-020, inputs and outputs will use Collection transport.
        """
        raise NotImplementedError
```

It has no `input_ports`, no `output_ports`, no `config_schema`, no `setup` /
`teardown`, no override of `get_effective_*_ports()`. The `run()` method
raises `NotImplementedError` unconditionally. Inheriting the empty
`input_ports: ClassVar[list[InputPort]] = []` from `Block` means the block
currently exposes nothing in the palette beyond its name and category.

`AIBlock` is intended to become the entry point for "this block uses an LLM
to process inputs and produce outputs". The user's eventual workflow looks
like *"give the AI block three images and a prompt; it returns one DataFrame
per cell type the model detects"*. That requires:

- a variable number of input ports (one per image, one per text annotation,
  one per reference table, ...);
- a variable number of output ports (one per output table the user expects);
- per-port type declaration (the user picks `Image` for input port 0,
  `DataFrame` for input port 1, `Text` for input port 2, etc.);
- per-port name (the user picks `microscopy_field_1`, `microscopy_field_2`,
  `cell_type_table`, ...) so the prompt template can interpolate them.

None of these requirements fit the existing `Block` ABC, where
`input_ports` and `output_ports` are `ClassVar` lists and therefore identical
across every instance of the class. ADR-028 Addendum 1's
`get_effective_*_ports()` override is one half of the answer (per-instance
port resolution at validation time), but Addendum 1 deliberately scoped
itself to the type dimension and left the count dimension (and the "where is
the per-instance state stored?" question) to this ADR.

#### What `CodeBlock` is today

`src/scieasy/blocks/code/code_block.py` is 163 lines. The relevant excerpts:

```python
class CodeBlock(Block):
    language: ClassVar[str] = "python"
    mode: ClassVar[str] = "inline"
    name: ClassVar[str] = "Code Block"
    description: ClassVar[str] = "Execute user-provided scripts"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data",
                  accepted_types=[DataObject],
                  required=False,
                  description="Primary input data"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="result",
                   accepted_types=[DataObject],
                   description="Script output"),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "language":     {...},
            "mode":         {...},
            "code":         {...},
            "script_path":  {...},
        },
    }
```

`CodeBlock` is functional today (subprocess-isolated runners per ADR-017,
auto-unpack/repack of Collection inputs per ADR-020-Add4) but is **constrained
to a single static input port and a single static output port**. Every code
block in the workflow graph has the same shape: one input named `data`, one
output named `result`, both typed as the maximally-broad `DataObject`.

This is too restrictive once users start writing real pipelines. A typical
research script looks like *"take a peak table and a sample-metadata table,
return three DataFrames (raw matrix, normalised matrix, statistics) and one
plot artifact"*. Today the user has to either:

- bundle everything into a single `CompositeData` and unpack it manually
  inside the script, or
- collapse multiple outputs into a list and lose the per-output type and
  port name, or
- chain three CodeBlocks sequentially and route each output through the
  single shared "result" port.

None of these options are good. The user wants to declare the inputs and
outputs of a code block in the same way they declare the inputs and outputs
of a regular block: explicit ports, explicit names, explicit types.

The mechanism for *how* the user declares those ports is the count-dimension
question this ADR sits on top of. It is closely related to but distinct from
the AIBlock case, because a code block's port list might be **inferred from
the script's source** (via Python AST analysis or R signature parsing)
rather than typed in by the user as a list of GUI controls. Both options
remain on the table, and both options need a backend data model that can
hold a per-instance port list.

#### Concrete use cases that motivate ADR-029

The following are real workflows the user wants to express. None of them is
expressible today.

1. **AI-driven image analysis with N inputs and M outputs.** The user drops
   an `AIBlock` onto the canvas, sets the prompt template to *"analyse the
   following microscopy fields and return one cell-count table per cell
   type you detect"*, then clicks "add input port" three times (each time
   typing `Image` and naming it `field_1`, `field_2`, `field_3`) and "add
   output port" twice (each time typing `DataFrame` and naming it
   `lymphocyte_counts`, `monocyte_counts`). The block runs once, the LLM
   inference returns two DataFrames, and the workflow validates each output
   edge against the user-declared port type.

2. **R-script ensemble averaging with a variable fan-in.** The user has
   five sibling blocks producing per-replicate peak tables and wants to
   merge them with an R script that computes the per-compound mean and
   standard deviation. They drop a `CodeBlock(language="r")`, click "add
   input port" five times (each time typing `DataFrame`), point each port
   at one upstream block, then write the R body. The script receives five
   named DataFrames and returns one DataFrame.

3. **Python preprocessing fork.** The user has one input image and wants
   one CodeBlock that returns three artifacts: the denoised image, a
   diagnostic histogram PNG, and a per-pixel statistics DataFrame. Today
   they can only return one of these. With variadic outputs they declare
   three output ports of types `Image`, `Artifact`, `DataFrame` and the
   script returns a dict.

4. **Future "ensemble" blocks that collect predictions from N sibling
   blocks.** Out of scope for the first cut of ADR-029, but the same
   variadic mechanism would support an `EnsembleVote` block whose input
   port list grows with the number of upstream models. Mentioned here so
   the design conversation can confirm that ADR-029's mechanism is not
   AIBlock-specific.

#### How this differs from ADR-028 Addendum 1's type dimension

ADR-028 Addendum 1 solves a narrower problem:

| Dimension              | Type (Addendum 1)                                  | Count (this ADR)                                                |
|------------------------|----------------------------------------------------|-----------------------------------------------------------------|
| Number of ports        | **Fixed** (one port, declared on the class)        | **Variable per instance**                                       |
| Per-port type          | Picked from a fixed enum at config time            | User-declared per port at edit time                             |
| Per-port name          | Fixed by the class                                 | User-declared per port at edit time                             |
| GUI control            | Existing dropdown driven by `dynamic_ports` enum   | New "add / remove / edit port" widget that does not exist yet   |
| Backend storage        | None — port list reconstructed from `config` enum  | Per-instance state, must be persisted in workflow YAML          |
| BlockSpec representation | One ClassVar `dynamic_ports` mapping             | Capability flag plus per-instance template                      |
| Validator handling     | Construct temporary instance, call `get_effective_output_ports()` | Same plus type-check user-declared port types          |
| Worker round-trip      | Unchanged — type is one of six core base classes   | Open question: how does `_reconstruct_one` know the output dict shape? |

The type dimension was tractable because the option set was finite (six core
base classes) and the per-instance state was already in `config` (the enum
value picked by the dropdown). The count dimension is harder because:

- the option set is unbounded (any non-negative integer count of ports);
- the per-port type is itself an open set (any registered `DataObject`
  subclass — including plugin-provided types not known at core build time);
- the per-instance state is genuinely new (the variable-length port list is
  not currently anywhere in `config` or in the `Block` ABC);
- the GUI widget for adding / removing / editing ports does not exist;
- the worker subprocess reconstruction contract (ADR-027 Addendum 1) was
  designed assuming the producing block has a static output schema.

Each of these gaps is an open question listed below.

#### Design timeline

The original draft (2026-04-07) deliberately deferred decisions until the
Phase 11 plugin cascade exercised the static-port machinery. On 2026-04-11
the design conversation resolved all open questions (Q1–Q11), promoting
this ADR to `proposed`. The original ten open questions are preserved below
for traceability; each now has a **Decision** annotation.

#### Explicit reference to ADR-028 Addendum 1 deferral

ADR-028 Addendum 1's "Relationship to other ADRs" section ends with:

> **Defers to**: ADR-029 (preliminary) — AI variadic port count, CodeBlock
> variadic port count, per-instance port editor UI. Addendum 1 provides the
> `get_effective_*_ports()` override mechanism that ADR-029 will build on,
> but makes no decisions about the count dimension.

This ADR is the reciprocal half of that pointer. Now that ADR-029 has
reached `proposed` status, that reference should be read as "Defers to
ADR-029 (proposed)".

### Open questions and resolutions

The following eleven questions were identified during the design process.
Each question lists the candidate answer directions from the original
draft; the **Decision** block records the chosen direction and rationale
from the 2026-04-11 design conversation.

#### Q1. Where is the variadic port list stored on a block instance?

The variable-length list of input ports and output ports for a single
`AIBlock` or `CodeBlock` instance has to live somewhere. Today the only
per-instance state on a block is `self.config` (a `BlockConfig` containing
the user-edited config dict). Candidates:

- **A. Inline in `self.config["input_ports"]` and `self.config["output_ports"]`.**
  Each entry is a small dict like `{"name": "field_1", "types": ["Image"]}`.
  The workflow YAML round-trips through the existing config serialiser
  unchanged. Pro: zero new framework state. Con: blurs the line between
  "user-tunable parameters" and "block topology", and the existing
  `config_schema` JSON Schema does not have a clean way to declare a
  variable-length list of structured dicts.

- **B. New top-level `self.port_config: PortConfig` field on `Block`.**
  Distinct from `self.config` so framework code can reason about port
  topology separately from runtime parameters. Pro: clean separation of
  concerns. Con: every persistence path (workflow YAML, checkpoint, REST
  API) needs to learn about a second field. Two write/read paths to keep
  in sync.

- **C. Separate sidecar JSON file under the workflow directory.**
  E.g., `workflows/foo/blocks/<block_id>.ports.json`. Pro: keeps the main
  YAML small. Con: introduces a multi-file workflow representation, which
  the rest of the system does not currently use; checkpoint and lineage
  paths get complicated.

- **D. Stored on the `BlockSpec` for the variadic block, with the spec
  itself becoming per-instance.** This is a category error in the current
  design (`BlockSpec` is shared across all instances of a class), but
  some variants of the design conversation have proposed a "variadic
  spec subclass" that holds per-instance state. Listed for completeness.

**Decision: A.** The variadic port list is stored inline in
`self.config["input_ports"]` and `self.config["output_ports"]` as a
JSON-serialisable list of `{"name": "...", "types": ["Image"]}` dicts.
This reuses the existing config serialisation path (workflow YAML
`nodes[].config`) with zero new persistence machinery. Option B was
rejected because it would require every persistence path (YAML, checkpoint,
REST API, worker payload) to learn a second field. Options C and D were
rejected as introducing unnecessary complexity (multi-file representation,
category error on BlockSpec).

#### Q2. How does the GUI render "add port" / "remove port" controls?

The frontend `BlockNode.tsx` today renders a fixed list of port handles
based on `data.schema?.input_ports` and `data.schema?.output_ports`. To
support variadic editing the node has to grow new UI affordances.
Candidates:

- **A. New `ui_widget: "variadic_port_list"` declared in the block's
  `config_schema`.** A generic widget rendered by `BlockNode.tsx` that
  shows a list of editable port rows with "+" / "-" buttons, name input,
  and a type dropdown. Pro: one widget covers AIBlock and CodeBlock and
  any future variadic block. Con: needs a widget registry on the
  frontend that does not exist yet, and the type dropdown's options have
  to be sourced from the backend's known type registry.

- **B. Custom React component per dynamic block type.** AIBlock gets its
  own `AIBlockNode.tsx`; CodeBlock gets its own `CodeBlockNode.tsx`.
  Each renders bespoke port-editing UI. Pro: maximum flexibility. Con:
  fragments the rendering code, every new variadic block ships its own
  React component, hard to keep visual consistency.

- **C. Open the port editor in a side panel / modal instead of inline on
  the node.** The node itself shows the current ports as handles; clicking
  a "configure ports" button opens a side panel with the add/remove/edit
  controls. Pro: keeps the node visually clean. Con: adds a navigation
  step, makes it less obvious that the ports are editable.

- **D. Pure-text declaration in a code editor (CodeBlock) plus auto-derived
  ports.** The user types port declarations as the first lines of the
  script (e.g., `# in: image: Image, mask: Mask` / `# out: result: DataFrame`)
  and the GUI re-parses on save. Pro: zero new GUI controls. Con:
  doesn't help AIBlock; couples the port list to the script body in a
  way that is awkward when the script is empty.

**Decision: A + D combination with dual entry point.**

1. **Canvas node `[+]` button**: each port list on the node itself has a
   `[+]` button at the bottom. Clicking it appends a new port with default
   name (`input_N` / `output_N`) and default type (`DataObject`). This
   gives users an immediate visual cue that the block supports dynamic
   ports and provides one-click port addition.

2. **Bottom Panel Config tab**: a full port editor table where users can
   rename ports, change types via dropdown, and delete ports via `[−]`
   button. This is the detailed editing surface.

3. **Port deletion safety**: when removing a port that has connected edges,
   the system disconnects those edges from the workflow graph first. The UI
   shows a confirmation dialog: *"This port has N connection(s). Remove
   port and disconnect?"*

4. **CodeBlock Python inference** (D): for `CodeBlock` with
   `language="python"` in script mode, the existing `introspect.py` parses
   the function signature (`def run(image: Image, mask: Image)`) and
   auto-populates the variadic port list. Users can still override
   manually. For R, Julia, and inline mode, the manual editor (A) is the
   only option.

Options B (per-block-type React components) and C (modal editor) were
rejected: B fragments rendering code, C adds a navigation step that makes
the variadic capability less discoverable.

#### Q3. How does validation handle variadic ports?

`workflow/validator.py` type-checks every edge in the graph by reading the
producer block's output ports and the consumer block's input ports and
running the existing `TypeSignature.is_compatible_with()` check. With
variadic ports, the port list is per-instance and the per-port type is
user-declared. Candidates:

- **A. Treat user-declared types exactly like class-declared types.** The
  validator constructs a temporary block instance (per Addendum 1's
  pattern), calls `get_effective_*_ports()`, and runs the existing edge
  type-compatibility check. Pro: no new validator code. Con: the user
  has to type-declare every port correctly; typos in the type name fail
  validation hard.

- **B. Allow `Any` / `DataObject` as a fallback type when the user has not
  declared one.** Variadic ports default to "accept anything"; the user
  can narrow if they want. Pro: easier authoring. Con: weakens type
  safety; pushes runtime errors into the block body where they are harder
  to diagnose.

- **C. Defer validation to runtime.** The graph validator skips variadic
  edges entirely; the runtime checks types just before invoking the
  block's `run()`. Pro: avoids the temporary-instance construction at
  validation time. Con: shifts errors from "graph won't save" to "workflow
  fails halfway through execution".

- **D. Hybrid: structural validation at graph time (port count and edge
  presence), type validation at runtime.** The validator confirms the
  variadic block's ports are wired but does not type-check; the runtime
  enforces types per item. Pro: progressive disclosure. Con: two places
  to maintain edge-checking logic.

**Decision: A.** User-declared types on variadic ports are treated
identically to class-declared types. The validator constructs a temporary
block instance per ADR-028 Addendum 1's pattern, calls
`get_effective_*_ports()`, and runs the standard
`TypeSignature.is_compatible_with()` edge check. If the user leaves a port
at the default `DataObject` type, any upstream type is accepted — this
provides the same ergonomics as Option B without any special-case code.
Options C (defer to runtime) and D (hybrid) were rejected because they
weaken the design-time validation guarantee.

#### Q4. How does the scheduler route through variadic ports at runtime?

`engine/scheduler.py` dispatches each block by reading its input edges,
constructing the input dict (`{port_name: Collection}`), calling
`block.run(inputs, config)`, then routing the output dict to downstream
blocks via the output edges. With variadic ports the input and output
dict shapes are per-instance. Candidates:

- **A. No scheduler change.** The scheduler already constructs `inputs`
  by walking edges; if the per-instance port list is the source of truth
  for port names, the existing edge-walk logic works unchanged. The
  scheduler never needs to know whether the port list is variadic.

- **B. Scheduler needs to load `get_effective_*_ports()` per dispatch.**
  Today the scheduler caches the class-level port list at registration
  time. With variadic ports it has to re-read the effective ports per
  block instance per dispatch. Pro: makes the variadic case explicit.
  Con: cache invalidation is finicky and needs to be wired through the
  whole engine.

- **C. Scheduler treats variadic blocks via a special "variadic dispatch"
  code path.** Different from static blocks, with its own `dispatch_variadic()`
  method on `DAGScheduler`. Pro: clean separation. Con: code duplication.

**Decision: A.** No scheduler change is required. The scheduler already
constructs the input dict by walking edges in the DAG; port names from the
per-instance port list are the edge endpoints. As long as the workflow
YAML's edge definitions use the user-declared port names, the existing
`_gather_inputs()` and output-routing logic works unchanged. The scheduler
never needs to know whether a port list is variadic or static.

#### Q5. How does `_reconstruct_one` (worker subprocess) handle variadic ports given ADR-027 Addendum 1's typed reconstruction contract?

ADR-027 Addendum 1 §1 defined `_reconstruct_one(payload)` and
`_serialise_one(obj)` as the worker subprocess's typed round-trip helpers.
Each is parameterised by a known target class (looked up from the
`type_chain` in the payload metadata). With static output ports the engine
already knows what classes to expect for each output port name. With
variadic output ports the producing block decides at instance time which
classes go in which output ports. Candidates:

- **A. Variadic output ports embed the class name in the per-port wire
  metadata.** The engine reads the per-port `type_chain` from the
  serialised output payload and dispatches to the matching class.
  Pro: no engine knowledge required up front. Con: requires the wire
  format to carry the class name; minor duplication with the existing
  `type_chain` field.

- **B. Variadic blocks declare their per-instance port-to-class mapping
  in a sidecar that the engine reads before invoking
  `_reconstruct_one`.** The engine pre-resolves classes from the
  per-instance port list and passes them down. Pro: keeps the wire format
  unchanged. Con: requires the engine to thread the per-instance port
  list through the worker subprocess boundary.

- **C. Variadic outputs are restricted to types whose class name is
  resolvable at scan time** (i.e., no plugin-provided types). The
  reconstruction is then identical to the static case. Pro: simplest.
  Con: massively limits the usefulness of variadic blocks (which is
  exactly the reason plugins exist).

**Decision: A.** Each port's payload already carries a `type_chain` field
per ADR-027 Addendum 1 §1. The worker calls `_reconstruct_one(payload)`,
which reads `type_chain` from the payload metadata and dispatches to the
matching class. Variadic ports do not change this mechanism — there are
simply more keys in the `{port_name: collection_payload}` dict. No
sidecar or wire-format change is needed.

#### Q6. Does AIBlock need a "port_template" for the palette preview?

The block palette in the frontend shows a small preview card for each
registered block, including its input and output port handles. For a
static block the preview reads `BlockSpec.input_ports` /
`BlockSpec.output_ports`. For a variadic block whose port list is
per-instance, the palette has nothing to read. Candidates:

- **A. Show zero ports in the palette preview.** The user only sees the
  ports after dropping the block onto the canvas and configuring it.
  Pro: simplest. Con: confusing for first-time users who can't tell what
  the block does.

- **B. Show a `port_template` declared on the class.** AIBlock declares
  e.g. `port_template = {"inputs": [{"name": "...", "types": ["DataObject"]}], "outputs": [...]}`
  that the palette renders as a "default shape" hint. The user can
  override after dropping. Pro: gives a meaningful preview. Con: yet
  another ClassVar to maintain.

- **C. Show a sentinel "variadic" badge on the port handle.** A single
  pseudo-port with a "+" decoration that signals "this block has variable
  ports". Pro: avoids lying about the actual port count. Con: requires
  bespoke palette rendering.

- **D. Render the palette card with no ports but show a tooltip
  explaining "this block has user-configured ports".** Pro: documents
  the variadic nature. Con: tooltip-only documentation is easy to miss.

**Decision: no special palette treatment required.** Variadic blocks
declare a default of 1 input port + 1 output port as their static
`input_ports` / `output_ports` ClassVars. The palette card displays
`1 in / 1 out` — which is accurate for the default state. Once the user
drops the block onto the canvas, the `[+]` buttons on the node reveal
that the block is variadic. No `port_template`, no sentinel badge, no
special tooltip needed.

#### Q7. CodeBlock — should it auto-infer ports from script AST, or user declares explicitly?

For `CodeBlock` specifically, the script body is itself a description of
what inputs and outputs the block expects. Candidates:

- **A. User declares explicitly via the same per-instance port editor as
  AIBlock.** Pro: consistent with AIBlock; supports R and Julia (where
  AST parsing is harder). Con: users have to declare ports twice (once
  in the editor, once in the script signature).

- **B. Python ports auto-inferred via AST analysis of the script's
  function signature.** The runner parses the `def run(image, mask, ...)`
  line and creates one input port per parameter. Type annotations
  (`image: Image`) drive the port type. Pro: zero duplication for the
  most common case. Con: only works for Python; needs a fallback for R
  and Julia.

- **C. Hybrid: auto-infer for Python, manual for R / Julia.** Pro: best
  ergonomics per language. Con: two code paths to maintain.

- **D. Side-load a `block.yaml` next to the script file declaring
  ports.** Used for `mode = "script"`. Pro: clean separation of script
  body and metadata. Con: introduces yet another file; doesn't help
  inline mode.

**Decision: C — hybrid.** Python scripts in script mode use auto-inference
via `introspect.py`: the function signature (`def run(image: Image, mask:
Image) -> DataFrame`) drives the port list. Type annotations map to port
types; untyped parameters default to `DataObject`. Users can override the
inferred ports manually via the port editor. For R, Julia, and inline mode,
the manual +/- editor (same as AIBlock) is the primary interface. Option A
(pure manual for all) was rejected because it forces Python users to
declare ports twice. Option B (Python-only auto) was subsumed by C. Option
D (sidecar YAML) was rejected as adding yet another file without helping
inline mode.

#### Q8. How does `BlockSpec` represent a variadic block at scan time?

`BlockRegistry.scan_builtins()` walks every registered block class at
import time and builds a `BlockSpec` capturing the class-level port list,
config schema, category, etc. The static `ClassVar` model assumes the
ports are known at scan time. For variadic blocks they are not.
Candidates:

- **A. New `BlockSpec.variadic: bool` flag.** Set to `True` for AIBlock /
  CodeBlock; the `input_ports` / `output_ports` fields then carry the
  palette template (per Q6). Frontend reads the flag to decide whether
  to render the variadic editor. Pro: minimal new state. Con: a single
  bool can't capture finer distinctions like "variadic inputs only" or
  "variadic outputs only".

- **B. New `BlockSpec.variadic_inputs: bool`, `variadic_outputs: bool`
  pair.** Same as A but more granular. Pro: supports the half-variadic
  case. Con: two new fields to populate and validate.

- **C. New `BlockSpec.port_capability: Literal["static", "variadic", "type_dynamic"]`
  enum.** A single enum that classifies the block's port behaviour.
  Pro: one source of truth. Con: closed enum; harder to extend if a
  fourth dimension shows up later.

- **D. No new field; the absence of `input_ports` / `output_ports`
  (empty lists) signals variadic.** Pro: zero new state. Con: ambiguous
  with "block has no ports at all".

**Decision: B — two booleans.** `BlockSpec` gains two new fields:

```python
variadic_inputs: bool = False
variadic_outputs: bool = False
```

Set by the registry at scan time from class-level `ClassVar` declarations.
The frontend reads these flags to decide whether to render `[+]` buttons
on the node. Option A (single bool) cannot distinguish "variadic inputs
only" from "variadic outputs only". Option C (enum) is less extensible.
Option D (infer from empty port list) is ambiguous with blocks that
genuinely have zero ports.

#### Q9. Does variadic mode mix with Addendum 1's enum `dynamic_ports` mapping?

A block could in principle be **both** type-dynamic (per Addendum 1, port
types driven by an enum config field) **and** count-dynamic (per this
ADR, port count driven by a per-instance editor). Example: an AIBlock
where the user picks a top-level "task" enum
(`segmentation` / `classification` / `extraction`) that determines the
output port count and the per-port types. Candidates:

- **A. Yes, the two mechanisms compose freely.** A block declares both
  `dynamic_ports` (enum mapping per Addendum 1) and the variadic
  capability (per this ADR). The framework reconciles at validation
  time. Pro: maximum flexibility. Con: hard to reason about; the
  product space of "enum value times port count" is large.

- **B. No, they are mutually exclusive.** A block is either type-dynamic
  or count-dynamic, never both. Pro: simpler mental model. Con:
  forecloses a legitimate use case.

- **C. They compose but with restrictions** — the enum mapping can only
  drive the *type* of variadic ports, not their *count*. Pro: keeps the
  count question entirely in the per-instance editor. Con: artificial
  restriction.

- **D. Defer the question.** First-cut ADR-029 lands variadic-only;
  type-dynamic-plus-variadic is a follow-up addendum if it proves
  necessary. Pro: ships sooner. Con: leaves a known gap.

**Decision: D — defer.** The `dynamic_ports` enum mechanism (ADR-028
Addendum 1) is designed specifically for IOBlock type-dimension switching
(`LoadData` / `SaveData`). There is no current use case where a block
needs both enum-driven type switching and user-driven port count
variability. If such a use case arises, a future Addendum will address the
composition rules. For now the two mechanisms are independent and do not
interact.

#### Q10. What's the wire format for variadic ports in the engine→worker payload?

The engine serialises block inputs into a payload, ships it to the
worker subprocess, and the worker reconstructs typed instances per
ADR-027 Addendum 1 §1. The payload schema today is essentially
`{port_name: collection_payload}`. Variadic ports keep that shape but
add the per-port name and type list. Candidates:

- **A. Same payload format.** The variadic per-instance port list is
  sent alongside the main payload as a sidecar field. The worker reads
  the sidecar to know how to dispatch. Pro: backward-compatible. Con:
  two parallel data structures to keep in sync.

- **B. Variadic-aware payload format.** Each port's payload entry
  carries its own type metadata (name, declared types) so the worker
  reconstructs purely from the payload. Pro: self-describing. Con:
  changes the wire format.

- **C. Variadic blocks pre-serialise their inputs to a single wrapper
  envelope** (e.g., a CompositeData with named slots per port). Pro:
  reuses the existing CompositeData round-trip. Con: forces every
  variadic block author to interact with CompositeData semantics.

**Decision: A.** The payload format is unchanged:
`{port_name: collection_payload}`. Variadic ports simply produce more keys
in the dict. The per-instance port list does not need to be sent as a
sidecar because each port's payload already self-describes via `type_chain`
(resolved in Q5). Options B and C were rejected as unnecessary complexity.

#### Q11. How does the block author constrain which types are allowed on variadic ports?

This question was not in the original draft. It was raised during the
2026-04-11 design conversation.

**Problem**: a variadic block that accepts arbitrary types on every port
undermines the user experience. For example, a `FijiBlock` should only
accept `Image`, `DataFrame`, and `ROI` on its input ports — not `Text` or
`Artifact`. Without block-author constraints, users could wire
incompatible data into variadic ports and only discover the error at
runtime.

**Decision: new ClassVar declarations.**

```python
class FijiBlock(AppBlock):
    variadic_inputs: ClassVar[bool] = True
    variadic_outputs: ClassVar[bool] = True
    allowed_input_types: ClassVar[list[type]] = [Image, DataFrame, ROI]
    allowed_output_types: ClassVar[list[type]] = [Image, DataFrame, Artifact]
```

- `allowed_input_types` / `allowed_output_types` are class-level
  declarations that constrain the type dropdown in the GUI port editor.
  The frontend only shows types in this list.
- Default is `[DataObject]` — no constraint, any type is allowed.
- The validator enforces this: if a user (or YAML import) declares a port
  type outside `allowed_*_types`, validation fails with a clear error.
- `BlockSpec` carries these lists so the frontend can populate the dropdown
  without constructing a block instance.

### Scope

The following work is in scope for the implementation phase of ADR-029.

#### In scope

- Extending `Block.get_effective_input_ports()` /
  `get_effective_output_ports()` to read a per-instance variadic port
  list from `self.config["input_ports"]` / `self.config["output_ports"]` (Q1).
- New `ClassVar` declarations on `Block`: `variadic_inputs`,
  `variadic_outputs`, `allowed_input_types`, `allowed_output_types` (Q8, Q11).
- Frontend: `[+]` button on canvas node port lists; port editor table in
  Bottom Panel Config tab; port deletion with edge cleanup (Q2).
- CodeBlock Python script introspection → auto-populate variadic port
  list from function signature (Q7).
- Updates to `BlockSpec` / `BlockSchemaResponse` to expose `variadic_inputs`,
  `variadic_outputs`, `allowed_input_types`, `allowed_output_types` (Q8, Q11).
- First consumers: `AIBlock`, `CodeBlock`, and `AppBlock` variadic forms.
- Tests for the new mechanism, the new GUI widget, the validator path,
  and the worker round-trip.
- Documentation updates: `docs/architecture/ARCHITECTURE.md` extended
  with a "variadic ports" section, `docs/guides/block-sdk.md` extended
  with a "writing a variadic block" recipe.

#### Explicitly out of scope (deferred to future ADRs)

- Per-port authentication / access control.
- Port lazy instantiation (creating ports on demand during a workflow run).
  All ports are declared before the workflow runs.
- Type inference from port data at runtime.
- AI-driven port suggestion (the LLM analyses the prompt and proposes a
  port shape).
- Composition of `dynamic_ports` enum mechanism with variadic port count (Q9).

### Decision

The decisions below correspond to Q1–Q11 in the "Open questions and
resolutions" section above. Each is summarised here for quick reference;
the full rationale is recorded inline with the question.

#### D1 — Variadic port list stored in `self.config` (Q1 → A)

Per-instance port declarations are stored as
`config["input_ports"]: list[dict]` and `config["output_ports"]: list[dict]`.
Each entry is `{"name": "field_1", "types": ["Image"]}`. The workflow
YAML round-trips through the existing config serialiser. No new
persistence path is needed.

#### D2 — Dual-entry GUI: canvas `[+]` and Bottom Panel editor (Q2 → A+D)

The canvas node renders a `[+]` button below the last port handle on
each side (input / output). The Bottom Panel Config tab renders a full
port editor table: `[name] [type ▼] [−]` per row, plus a `[+]` row at
the bottom. Port deletion disconnects any attached edges first (with
user confirmation). For `CodeBlock` Python script mode, `introspect.py`
auto-populates the port list from the function signature; users can
override manually.

#### D3 — Validation treats variadic ports identically to static ports (Q3 → A)

The validator calls `get_effective_*_ports()` on a temporary block
instance and runs the standard `TypeSignature.is_compatible_with()` edge
check. User-declared types at `DataObject` (the default) accept anything.

#### D4 — No scheduler change (Q4 → A)

The scheduler's `_gather_inputs()` and output routing already walk edges
by port name. Variadic ports add keys but do not change the dispatch
model.

#### D5 — Worker reconstruction unchanged; payload self-describes (Q5 → A)

Each port's payload carries `type_chain` per ADR-027 Addendum 1.
Variadic ports add more keys to the `{port_name: collection_payload}`
dict; the worker reconstructs each independently.

#### D6 — No special palette treatment (Q6)

Variadic blocks declare default 1 in / 1 out; the palette shows `1 in /
1 out` accurately. The `[+]` buttons on the canvas node reveal
variadic capability after the block is dropped.

#### D7 — CodeBlock hybrid inference (Q7 → C)

Python script mode: auto-infer ports from function signature via
`introspect.py`. R, Julia, and inline mode: manual `[+]/[−]` editor.

#### D8 — Two booleans on BlockSpec (Q8 → B)

`BlockSpec.variadic_inputs: bool` and `BlockSpec.variadic_outputs: bool`,
set from class-level `ClassVar` declarations. The frontend reads these to
decide whether to render `[+]` buttons.

#### D9 — `dynamic_ports` and variadic are independent (Q9 → D)

No composition rules are defined. The `dynamic_ports` enum mechanism
(ADR-028 Addendum 1) serves the type dimension for IOBlock; variadic
serves the count dimension for AIBlock/CodeBlock/AppBlock. If a
combined use case arises, a future Addendum will address it.

#### D10 — Payload format unchanged (Q10 → A)

The `{port_name: collection_payload}` wire format is unchanged. More
keys in the dict, same structure per key.

#### D11 — Block author declares allowed types for variadic ports (Q11)

New `ClassVar` declarations:

```python
allowed_input_types: ClassVar[list[type]] = [DataObject]   # default: no constraint
allowed_output_types: ClassVar[list[type]] = [DataObject]
```

The GUI type dropdown for variadic ports only shows types in the block's
`allowed_*_types` list. The validator rejects port type declarations
outside this range. `BlockSpec` carries these lists so the frontend can
populate the dropdown without constructing a block instance.

**Example**:

```python
class FijiBlock(AppBlock):
    variadic_inputs: ClassVar[bool] = True
    variadic_outputs: ClassVar[bool] = True
    allowed_input_types: ClassVar[list[type]] = [Image, DataFrame, ROI]
    allowed_output_types: ClassVar[list[type]] = [Image, DataFrame, Artifact]
```

#### D12 — Variadic port editor injected via MRO merge (ADR-030 pattern)

The variadic port editor fields (`input_ports`, `output_ports`) are
declared in the `config_schema` of base classes that enable variadic
mode (`AIBlock`, `CodeBlock`, `AppBlock` — or a shared mixin). Through
the ADR-030 MRO merge mechanism, these fields are automatically injected
into every subclass's config form. Block authors who set
`variadic_inputs = True` on their class do **not** need to manually
declare the port editor schema — the base class provides it, and
`_merge_config_schema()` merges it into the subclass's config form just
like `IOBlock` injects `path` and `AppBlock` injects `output_dir`.

```python
# In AIBlock (or a VariadicMixin):
config_schema: ClassVar[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "input_ports": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "types": {"type": "array", "items": {"type": "string"}},
                },
            },
            "ui_widget": "variadic_port_editor",
            "ui_priority": -1,
        },
        "output_ports": { ... },   # same structure
    },
}
```

The registry's `_merge_config_schema()` applies the same MRO walk
(base-first, child-wins-on-conflict) so that subclass-specific config
fields coexist with the injected port editor fields.

#### D13 — Multiple same-type ports for parallel branch fan-in

A variadic block may declare multiple input ports of the **same type**.
For example, a `FijiBlock` processing images from two parallel branches
declares two input ports both typed `Image`:

```python
# User configures via the port editor:
config["input_ports"] = [
    {"name": "images_branch_a", "types": ["Image"]},
    {"name": "images_branch_b", "types": ["Image"]},
]
```

Each port carries its own `Collection[Image]` independently. The block's
`run()` receives:

```python
inputs = {
    "images_branch_a": Collection[Image],   # 10 images from branch A
    "images_branch_b": Collection[Image],   # 5 images from branch B
}
```

This requires no special handling: port names are distinct keys in the
input dict, Collection homogeneity is per-port (not per-block), and the
scheduler routes each edge independently by port name. AppBlock's
`run()` serialises all inputs into the same exchange directory; the
external app sees a unified set of files.

### Alternatives considered

The primary design alternative was **runtime-discovered output ports**:
instead of users declaring ports before execution, the block would run
first and dynamically create output ports based on what the script or
app actually returned. This was rejected for three reasons:

1. **Downstream wiring is impossible before the first run.** The
   workflow graph cannot be fully connected until every block has run at
   least once, which defeats the purpose of a design-time DAG editor.
2. **Non-deterministic output shapes break reproducibility.** A script
   that returns different numbers of outputs depending on input data
   would produce different graph topologies across runs.
3. **Type safety is deferred to runtime.** Without pre-declared port
   types, downstream blocks cannot validate connections at design time.

A secondary alternative was **heterogeneous Collection** (allowing
`Collection` to hold mixed types). This was rejected because it
fundamentally breaks Collection's homogeneity invariant (ADR-020,
ADR-020 Addendum 6) and degrades port type safety across the entire
framework, not just for variadic blocks.

Per-question alternatives are recorded inline in the "Open questions and
resolutions" section.

### Consequences

**Backend changes**:

- `Block` ABC gains four new `ClassVar` declarations:
  `variadic_inputs: bool`, `variadic_outputs: bool`,
  `allowed_input_types: list[type]`, `allowed_output_types: list[type]`.
  All default to `False` / `[DataObject]` — fully backward-compatible
  with every existing block.
- Base classes that enable variadic mode (`AIBlock`, `CodeBlock`,
  `AppBlock`) declare `input_ports` / `output_ports` array fields in
  their `config_schema`. These are injected into subclasses via ADR-030
  MRO merge (D12) — block authors do not manually add them.
- `Block.get_effective_input_ports()` / `get_effective_output_ports()`
  must read `self.config.get("input_ports", [])` /
  `self.config.get("output_ports", [])` and construct `InputPort` /
  `OutputPort` instances from the dicts when the block is variadic.
- `BlockSpec` gains `variadic_inputs`, `variadic_outputs`,
  `allowed_input_types`, `allowed_output_types` fields. The registry's
  `_spec_from_class()` populates them at scan time.
- `BlockSchemaResponse` (REST API) includes the new fields so the
  frontend can render the variadic editor.
- `CodeBlock` introspection (script mode, Python) maps function
  parameters to variadic input ports and return annotations to variadic
  output ports.

**Frontend changes**:

- `BlockNode.tsx` renders `[+]` buttons on variadic block nodes (gated
  on `schema.variadic_inputs` / `schema.variadic_outputs`).
- Bottom Panel Config tab renders a port editor table for variadic
  blocks.
- Port deletion triggers edge cleanup in the ReactFlow graph state.
- Type dropdown for variadic ports is filtered by
  `allowed_input_types` / `allowed_output_types`.

**No changes to**:

- `engine/scheduler.py` — edge routing is port-name-based, unchanged.
- `engine/runners/worker.py` — payload format unchanged; `type_chain`
  self-describes.
- `core/types/collection.py` — homogeneity invariant preserved.
- `core/types/serialization.py` — `_reconstruct_one` / `_serialise_one`
  unchanged.
- Workflow YAML format — per-instance ports are in `nodes[].config`,
  which is already an arbitrary dict.

**First consumers**:

- `AIBlock` — variadic inputs (user picks N data objects + prompt) and
  variadic outputs (user declares expected result types).
- `CodeBlock` — variadic inputs and outputs; Python script mode
  auto-infers from function signature.
- `AppBlock` — variadic inputs (files to send to external app) and
  variadic outputs (files returned by app, grouped by type).

### Relationship to other ADRs

- **Builds on**: ADR-028 + Addendum 1 (IOBlock refactor + dynamic-port
  override mechanism). ADR-029 extends the `get_effective_*_ports()`
  mechanism that Addendum 1 introduced to support per-instance variadic
  port lists. ADR-029 does **not** replace the Addendum 1 mechanism —
  the type-dimension dispatch (used by `LoadData` / `SaveData`) is left
  untouched.
- **Builds on**: ADR-027 + Addendum 1 (Phase 10 core type system + worker
  reconstruction contract). The `type_chain`-based reconstruction
  handles variadic output ports without modification (D5).
- **Builds on**: ADR-020 + Addenda (Collection transport between blocks).
  Variadic ports do not change how Collections are constructed or
  shipped; they only change how many of them flow through a block.
- **Builds on**: ADR-017 (subprocess isolation) and ADR-018 + Addendum 1
  (scheduler concurrency). The scheduler dispatch model is unchanged (D4).
- **Does not supersede**: any existing ADR. ADR-029 adds new surface
  without removing anything.
- **Unblocks**: the full implementation of `AIBlock`, the variadic form
  of `CodeBlock`, and variadic `AppBlock` subclasses.
- **Defers from**: ADR-028 Addendum 1's "Relationship to other ADRs"
  section: *"Defers to ADR-029"*. This ADR is the destination of that
  pointer, now at `proposed` status.

### Next steps

1. Create implementation issues for the backend changes (Block ABC,
   BlockSpec, registry), frontend changes (BlockNode variadic editor,
   Bottom Panel port table), and first consumers (AIBlock, CodeBlock,
   AppBlock).
2. Implementation follows the standard workflow gate per issue.
3. Once all first consumers ship and tests pass, ADR-029 is promoted
   from `proposed` to `accepted`.

---

## ADR-029 Addendum 1: Variadic port count limits

**Status**: accepted
**Date**: 2026-04-11
**Parent**: ADR-029

### Context

ADR-029 defines variadic ports with `variadic_inputs: bool` /
`variadic_outputs: bool` but provides no mechanism for block authors to
constrain the minimum or maximum number of ports a user can add. Without
limits, a user could add 100 input ports to a PairEditor (intended for
2–8 inputs) or remove all ports from an AIBlock (which needs at least
one input).

Interactive blocks like PairEditor (#591) and DataRouter (#591) have
practical UI limits — the drag-and-drop interface becomes unusable
beyond ~8 ports. Other blocks have logical minimums (e.g. a merge block
needs at least 2 inputs).

### Decision

#### D1 — Optional min/max ClassVar declarations on Block

```python
class Block(ABC):
    # Existing:
    variadic_inputs: ClassVar[bool] = False
    variadic_outputs: ClassVar[bool] = False

    # New — port count limits (None = no limit):
    min_input_ports: ClassVar[int | None] = None
    max_input_ports: ClassVar[int | None] = None
    min_output_ports: ClassVar[int | None] = None
    max_output_ports: ClassVar[int | None] = None
```

- `None` means no constraint (unlimited). This is the default on `Block`.
- Subclasses declare limits only when needed.
- When `variadic_inputs` is `False`, the limits are ignored (static port
  list is fixed by the class).

**Example**:

```python
class PairEditor(ProcessBlock):
    variadic_inputs = True
    variadic_outputs = False
    min_input_ports = 2
    max_input_ports = 8

class DataRouter(ProcessBlock):
    variadic_inputs = True
    variadic_outputs = True
    min_input_ports = 1
    max_input_ports = 8
    min_output_ports = 1
    max_output_ports = 8

class AIBlock(Block):
    variadic_inputs = True
    variadic_outputs = True
    min_input_ports = 1     # need at least one input
    min_output_ports = 1    # need at least one output
    # max = None → unlimited
```

#### D2 — BlockSpec and frontend enforcement

- `BlockSpec` carries the four limit fields (set from ClassVar at scan
  time).
- `BlockSchemaResponse` exposes them to the frontend.
- Frontend: `[+]` button is disabled when current port count equals
  `max_*_ports`. `[−]` button is disabled when current count equals
  `min_*_ports`.
- Validator rejects workflows where a variadic block has port count
  outside `[min, max]`.

### Consequences

- Four new optional `ClassVar` fields on `Block`, all defaulting to
  `None`. Fully backward-compatible — existing blocks are unaffected.
- `BlockSpec` gains four optional `int | None` fields.
- Frontend port editor respects limits.
- No changes to scheduler, worker, or payload format.

### Relationship to other ADRs

- **Extends**: ADR-029 (variadic port count). This Addendum adds
  constraints to the mechanism ADR-029 introduced.
- **Motivated by**: #591 (DataRouter / PairEditor) which need bounded
  port counts for usable interactive UIs.

---

## ADR-030: config_schema MRO merge and base-class field injection

**Status**: accepted
**Date**: 2026-04-10
**Issue**: #558

### Context

Every block class declares a `config_schema: ClassVar[dict[str, Any]]` — a
JSON Schema dict whose `properties` map drives both the frontend inline config
UI and the BottomPanel full config form. Because `ClassVar` is a plain Python
class variable, a subclass that declares its own `config_schema` **completely
replaces** the parent's — Python performs no merge.

This creates three concrete problems.

#### Problem 1 — IOBlock subclasses redundantly declare `path`

`IOBlock` (the abstract base for all loaders and savers) declares a minimal
`config_schema` with a `path` field, but without `ui_widget`:

```python
# src/scieasy/blocks/io/io_block.py line 56-60
config_schema: ClassVar[dict[str, Any]] = {
    "type": "object",
    "properties": {"path": {"type": "string", "ui_priority": 1}},
    "required": ["path"],
}
```

Every concrete IOBlock subclass must redeclare `path` with the appropriate
`ui_widget` to get the browse button. All 9 existing subclasses do this
independently:

| Block | Direction | path type | ui_widget | Correct? |
|-------|-----------|-----------|-----------|----------|
| LoadData | input | `["string", "array"]` | `file_browser` | ✓ |
| LoadPeakTable | input | `["string", "array"]` | `file_browser` | ✓ |
| LoadMIDTable | input | `["string", "array"]` | `file_browser` | ✓ |
| LoadSampleMetadata | input | `["string", "array"]` | `file_browser` | ✓ |
| LoadMzMLFiles | input | `["string", "array"]` | `file_browser` | ✓ |
| LoadImage | input | `["string", "array"]` | `file_browser` | ✓ |
| SaveData | output | `"string"` | `directory_browser` | ✓ |
| SaveImage | output | `"string"` | `directory_browser` | ✓ |
| SaveTable | output | `"string"` | `file_browser` | **✗** — saver should use `directory_browser` |

All input-direction blocks converge on the same schema: `type: ["string", "array"]`,
`ui_widget: "file_browser"`, `items: {"type": "string"}`. This is pure
boilerplate that the base class should provide.

Output-direction blocks should uniformly use `directory_browser`, but one
block (SaveTable) incorrectly uses `file_browser`, precisely because there is
no base-class enforcement.

#### Problem 2 — AppBlock cannot inject `output_dir` into subclasses

AppBlocks launch external GUI applications (Fiji, ElMAVEN, Napari, QuPath,
CellProfiler). After launching, users must save their results to the
exchange `outputs/` directory, but they have no way to know where that
directory is. The solution is a "Save Outputs At" config field with a
browse button and a copy-to-clipboard button, pre-filled with the exchange
output path.

This field belongs in `AppBlock.config_schema` so every AppBlock subclass
inherits it automatically. But because `ClassVar` doesn't merge, every
subclass that declares its own `config_schema` (all of them) would lose the
injected field. Requiring every AppBlock author to manually include
`output_dir` defeats the purpose.

#### Problem 3 — No enforcement path for future base-class fields

The same problem will recur for any future base-class field: `CodeBlock`
might want a `timeout` field; `AIBlock` might want a `model` selector.
Without a general merge mechanism, every such addition requires manually
updating every subclass across every plugin package.

### Decision

#### D1 — Registry merges `config_schema` properties along MRO

The block registry's `_spec_from_class()` function (line 553 in
`src/scieasy/blocks/registry.py`) currently reads `config_schema` with a
simple `getattr(cls, "config_schema", ...)`. This will be replaced by a
merge function that walks the class's MRO and unions all `properties` dicts:

```python
def _merge_config_schema(cls: type) -> dict[str, Any]:
    """Merge config_schema properties along MRO (child wins on conflict)."""
    merged_properties: dict[str, Any] = {}
    merged_required: list[str] = []
    for klass in reversed(cls.__mro__):
        schema = klass.__dict__.get("config_schema")  # __dict__, not getattr
        if schema and isinstance(schema, dict):
            merged_properties.update(schema.get("properties", {}))
            merged_required.extend(schema.get("required", []))
    return {
        "type": "object",
        "properties": merged_properties,
        "required": list(dict.fromkeys(merged_required)),
    }
```

Key semantics:
- Uses `klass.__dict__` (own attributes only), not `getattr` (which would
  follow MRO itself and return the same dict for all classes that don't
  override).
- Walks MRO in reverse (base first), so **child properties override parent
  on name conflict**. A subclass that declares a `path` field overrides the
  base class's `path`.
- `required` lists are unioned and deduplicated.

#### D2 — IOBlock base injects direction-aware `path` field

The `IOBlock` base class `config_schema` will be updated to declare a
`path` field appropriate for each direction. Since `direction` is a ClassVar
that differs between input and output subclasses, the registry must read
`direction` to resolve which path schema to inject.

Two approaches were considered:

**Option A — Two intermediate base classes**: Split `IOBlock` into
`InputIOBlock` and `OutputIOBlock`, each with its own `config_schema`.
Rejected: breaks the existing `IOBlock` contract and forces all subclasses
to change their inheritance.

**Option B — Registry post-processing based on direction**: After MRO
merge, the registry checks `direction` and adjusts the `path` field's
`ui_widget` and `type` accordingly. This is the chosen approach.

The `IOBlock` base `config_schema` declares:

```python
# IOBlock.config_schema
config_schema: ClassVar[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "path": {
            "type": ["string", "array"],
            "items": {"type": "string"},
            "ui_priority": 0,
            "ui_widget": "file_browser",
        },
    },
    "required": ["path"],
}
```

In `_merge_config_schema()`, after merging, if the block has
`direction == "output"` and the `path` field was not overridden by the
subclass (i.e., it came from a base class), apply output-direction defaults:

```python
if direction == "output" and "path" in merged_properties:
    path_prop = merged_properties["path"]
    # Only override if the subclass didn't explicitly declare path
    if not _subclass_declares_field(cls, "path"):
        path_prop["type"] = "string"
        path_prop["ui_widget"] = "directory_browser"
        path_prop.pop("items", None)
```

This ensures:
- Input blocks: `path` is `["string", "array"]` with `file_browser` (multi-file select)
- Output blocks: `path` is `"string"` with `directory_browser` (single directory select)
- Subclass override: if a subclass explicitly declares `path` in its own
  `config_schema`, that declaration wins (MRO merge semantics).

#### D3 — AppBlock base injects `output_dir` field

`AppBlock.config_schema` adds:

```python
"output_dir": {
    "type": ["string", "null"],
    "default": None,
    "title": "Save Outputs At",
    "ui_widget": "directory_browser",
    "ui_priority": 0,
},
```

In `AppBlock.run()`, the field controls the FileWatcher directory:

```python
custom_output_dir = config.get("output_dir")
if custom_output_dir:
    output_dir = Path(custom_output_dir)
else:
    output_dir = exchange_dir / "outputs"
output_dir.mkdir(parents=True, exist_ok=True)
```

The imaging package's `_run_external_app()` helper must also read this field.

#### D4 — Frontend: copy button + PAUSED toast for AppBlock

When a block enters PAUSED state (via WebSocket event), the frontend shows a
toast notification with the output path and a copy-to-clipboard button.

The `directory_browser` widget gains a copy button alongside the existing
browse (`...`) button. This benefits all blocks that use `directory_browser`,
not just AppBlock.

#### D5 — Subclass config_schema cleanup

After MRO merge is implemented, IOBlock subclasses that only redeclare `path`
to add `ui_widget` can remove that redundant declaration. Subclasses that
declare `path` with additional fields (e.g., custom `title` like "Peak table
file(s)") may keep their override — the child declaration wins on merge.

The following subclasses can have their `path` field removed from
`config_schema` (they add no information beyond what the base provides):

- `LoadData` — path field is identical to base except for `ui_widget`
- `LoadImage` — same
- `SaveData` — same (for output direction)
- `SaveImage` — same

The following subclasses should keep `path` in their `config_schema` because
they add a custom `title`:

- `LoadPeakTable` — title: "Peak table file(s)"
- `LoadMIDTable` — title: "MID table file(s)"
- `LoadSampleMetadata` — title: "Sample metadata file(s)"
- `LoadMzMLFiles` — title: "Raw file path(s)"
- `SaveTable` — title: "Output file path" (but must change `ui_widget` to
  `directory_browser`, or remove and let base handle it)

### Alternatives considered

#### A — Frontend-side injection

Instead of merging in the registry, the frontend could detect block base
types (AppBlock, IOBlock) and inject fields client-side.

Rejected: duplicates block-type awareness between backend and frontend,
creates a second source of truth for config schema, and doesn't solve the
backend `config.get("output_dir")` problem (AppBlock.run() needs the field
to actually be in the config).

#### B — Explicit `_base_config_schema()` class method

Each base class provides a `_base_config_schema()` that subclasses must
call and merge manually:

```python
config_schema = {**AppBlock._base_config_schema(), **{...my fields...}}
```

Rejected: requires discipline from every block author, which is exactly the
problem we're solving. MRO merge is automatic and invisible.

#### C — Decorator-based schema composition

A `@merge_parent_schema` decorator that walks MRO at class creation time.

Rejected: adds metaclass-adjacent complexity. The registry already walks
classes at registration time — doing the merge there is simpler and more
debuggable.

### Consequences

#### Positive

1. Block authors who subclass `IOBlock` get a working `path` field with the
   correct browse button automatically, without declaring it.
2. Block authors who subclass `AppBlock` get `output_dir` automatically.
3. Future base-class config fields (e.g., `CodeBlock.timeout`) work the same
   way — declare once in the base, all subclasses inherit.
4. SaveTable's incorrect `file_browser` is fixed by removing its custom
   `path` and letting the output-direction base handle it.
5. Existing subclass overrides continue to work (child wins on conflict).

#### Negative

1. `__dict__`-based MRO walk is subtler than a simple `getattr`. Must be
   well-tested and documented.
2. A subclass that partially overrides a field (e.g., changes `title` but not
   `ui_widget`) will fully replace the base field — there is no deep merge
   within a single property. This is acceptable: JSON Schema properties are
   self-contained.
3. Debugging which class contributed which field requires understanding MRO.
   Mitigated: the registry can log the merge result at DEBUG level.

#### Migration

The rollout is backward-compatible. Existing subclasses with redundant `path`
declarations continue to work (their declaration wins on merge). Cleanup of
redundant declarations is a separate follow-up, not a prerequisite.

### Affected files

#### Must change

| File | Change |
|------|--------|
| `src/scieasy/blocks/registry.py` | Replace `getattr(cls, "config_schema", ...)` with `_merge_config_schema(cls)` in `_spec_from_class()`. Add direction-aware post-processing for IOBlock path field. |
| `src/scieasy/blocks/io/io_block.py` | Update `config_schema` to declare `path` with full `ui_widget`, `type`, `items` for input direction. |
| `src/scieasy/blocks/app/app_block.py` | Add `output_dir` field to `config_schema`. Update `run()` to use `config.get("output_dir")` for FileWatcher directory. |
| `packages/scieasy-blocks-imaging/.../interactive/__init__.py` | Update `_run_external_app()` to read `config.get("output_dir")` and use as FileWatcher directory if set. |
| `frontend/src/components/nodes/BlockNode.tsx` | Add copy-to-clipboard button for `directory_browser` widget. Add PAUSED toast for AppBlock. |
| `frontend/src/store/executionSlice.ts` | Ensure PAUSED block state events surface for toast rendering. |

#### Must verify / adapt

| File | Reason |
|------|--------|
| `src/scieasy/workflow/serializer.py` | `_path_config_keys()` identifies path fields via `ui_widget` — verify `output_dir` is handled for relative path conversion (#506). |
| `src/scieasy/api/runtime.py` | Path portability (relativify/absolutify) must work with merged schema. |
| `frontend/src/components/BottomPanel.tsx` | Full config panel must render merged schema correctly. |

#### Cleanup (follow-up, not blocking)

| File | Change |
|------|--------|
| `src/scieasy/blocks/io/loaders/load_data.py` | Remove redundant `path` from `config_schema` — inherited from IOBlock. |
| `src/scieasy/blocks/io/savers/save_data.py` | Remove redundant `path` — direction-aware injection provides `directory_browser`. |
| `packages/scieasy-blocks-imaging/.../io/load_image.py` | Remove redundant `path`. |
| `packages/scieasy-blocks-imaging/.../io/save_image.py` | Remove redundant `path`. |
| `packages/scieasy-blocks-lcms/.../io/load_peak_table.py` | Keep `path` (custom title), but remove `ui_widget` and `type` — inherited from base. |
| `packages/scieasy-blocks-lcms/.../io/load_mid_table.py` | Same as above. |
| `packages/scieasy-blocks-lcms/.../io/load_sample_metadata.py` | Same as above. |
| `packages/scieasy-blocks-lcms/.../io/load_mzml_files.py` | Same as above. |
| `packages/scieasy-blocks-lcms/.../io/save_table.py` | Remove `path` entirely — let output-direction base handle `directory_browser`. Fixes incorrect `file_browser` usage. |

### Implementation sequence

1. Implement `_merge_config_schema()` in registry with direction-aware
   post-processing. Add tests.
2. Update `IOBlock.config_schema` with full path declaration.
3. Update `AppBlock.config_schema` with `output_dir`. Update `run()`.
4. Update imaging `_run_external_app()` to read `output_dir`.
5. Frontend: add copy button to `directory_browser`, add PAUSED toast.
6. Verify path portability (serializer, runtime).
7. Follow-up PR: clean up redundant `path` declarations in subclasses.
## ADR-031: Data Object Reference-Only Contract, ViewProxy Elimination, and Lazy Loading Enforcement

**Status**: draft
**Date**: 2026-04-11
**Supersedes**: ADR-027 Addendum 1 (~~proposed~~ → **deprecated**)
**Amends**: ADR-007 (implementation alignment), ADR-017 (transport contract), ADR-028 (IOBlock contract)

---

### 1. Purpose

This ADR addresses a **critical divergence between architectural design and implementation** across the data storage, transport, and access layers. An independent audit (ref: `docs/data-storage-transport-audit.en.md`, 2026-04-11) confirmed that the "lazy by default" principle from ADR-007 is systematically violated in practice.

This ADR:

1. Establishes **DataObject as the single, definitive data reference type** — no secondary accessor classes.
2. **Eliminates `ViewProxy`** entirely — its methods are absorbed into DataObject/Array.
3. **Prohibits the `_data` / `_arrow_table` in-memory backdoor** on DataObject instances that cross block boundaries.
4. **Requires IOBlock loaders to persist data to storage and return reference-only objects.**
5. **Exempts Artifact/file-handle types from auto-flush** — path-only transport.
6. **Deprecates ADR-027 Addendum 1** in its entirety; correct decisions are restated here.
7. **Aligns documentation** to a single coherent model.

### 2. Context

#### 2.1 Design intent (ADR-007, ADR-017, ADR-027)

The architecture specifies:

> DataObject instances are lightweight wrappers (~KB) holding a StorageReference. Blocks never receive raw data directly. — ADR-007

> No scientific data crosses the process boundary. Only StorageReference pointers (~100 bytes each) and config dicts cross. — ADR-017

> `worker.reconstruct_inputs` returns typed DataObject instances, not ViewProxy. Lazy loading is preserved at the method level. — ADR-027 Addendum 1

#### 2.2 Actual implementation state (audit findings)

The independent audit (`docs/data-storage-transport-audit.en.md`) found:

1. **Almost all loaders are eager.** Only `LoadData(.zarr)` returns a storage-backed reference. All other paths (`LoadImage` TIFF/Zarr, `LoadData` .npy/.csv/.parquet/.json, plugin loaders) read full data into memory and attach it to an undeclared `_data` or `_arrow_table` attribute. Evidence: `load_data.py:233-427`, `load_image.py:76-141`.

2. **`_data` is not part of the DataObject contract.** The `DataObject.__init__` constructor has four declared slots: `framework`, `meta`, `user`, `storage_ref`. The `_data` attribute appears nowhere in the base class. It is monkey-patched onto instances by loader code: `img._data = np.asarray(...)`. The base class's `get_in_memory_data()` legitimizes this via `hasattr(self, "_data")` — a contract violation that the framework itself endorses.

3. **ViewProxy is vestigial.** ADR-027 Addendum 1 demoted ViewProxy from "engine-injected input type" to "opt-in helper via `item.view()`". In practice, **zero package-level blocks call `item.view()`**. ViewProxy's sole runtime role is as an unnecessary intermediary in `DataObject.to_memory()` → `self.view().to_memory()`. The class adds indirection without value.

4. **The transport layer is reference-based, but load/process/export are not.** The scheduler→worker JSON wire protocol correctly transmits StorageReference pointers. But data enters the system as in-memory blobs (load), gets processed as in-memory blobs (process), and gets exported from in-memory blobs (save). The reference-based transport is sandwiched between eager endpoints.

5. **SaveData cannot reliably export storage-backed objects.** `_save_array()` calls `obj.get_in_memory_data()`, which succeeds only if `_data` is set. A storage-backed Array (reconstructed in worker with only `storage_ref`) has no `_data`, causing `get_in_memory_data()` to raise. Evidence: `save_data.py:280-348`, `base.py:350-362`.

6. **`LoadData(Series)` loses payload.** `_load_series()` returns a `Series()` with neither `_data`, `_arrow_table`, nor `storage_ref`. The data is silently discarded. Evidence: `load_data.py:456-468`.

7. **`LoadPeakTable` stores pandas DataFrame in `user` metadata.** The `user` dict requires JSON-serializability per ADR-017. A pandas DataFrame is not JSON-serializable. This silently breaks cross-process transport. Evidence: `load_peak_table.py:123-134`.

8. **Artifact file semantics are broken by auto-flush.** `MSRawFile` is designed as a path handle, but `_auto_flush()` calls `get_in_memory_data()` which reads the file's raw bytes, then writes them to managed storage. The original file semantics are lost. Evidence: `block.py:374-403`, `artifact.py:44-48`.

9. **`Array.sel()` materializes full data before slicing.** The method that should enable lazy partial reads (`sel(z=5)`) starts by calling `self.to_memory()` to load the entire array. Evidence: `array.py:165-223`.

10. **Documentation mixes two generations.** `ARCHITECTURE.md:331-362` describes the old ViewProxy-injection model. `ADR.md:4659-5135` (ADR-027 Addendum 1) describes typed DataObject reconstruction. The code matches the newer model, but the architectural docs still reference the old one.

#### 2.3 Why ADR-027 Addendum 1 is deprecated

ADR-027 Addendum 1 made several correct observations but stopped short of the necessary conclusion:

- **Correct**: worker should return typed DataObject, not ViewProxy.
- **Correct**: `_reconstruct_extra_kwargs` / `_serialise_extra_metadata` hooks are the right per-class reconstruction pattern.
- **Correct**: Meta Pydantic constraints (frozen, JSON-round-trippable) are necessary.
- **Incorrect**: ViewProxy should be "demoted to opt-in helper." It should be **deleted** — no block uses it, and its functionality belongs on DataObject directly.
- **Incomplete**: Did not address the `_data` backdoor, loader eagerness, SaveData breakage, or Artifact semantics.
- **Incomplete**: Did not establish DataObject as the single source of truth for data access methods.

This ADR supersedes ADR-027 Addendum 1 in full. Decisions that remain correct are restated below with updated rationale.

---

### 3. Decisions

#### D1. DataObject is the single data reference type (source of truth)

**D1.1 Type hierarchy and per-class responsibilities**

```
DataObject (base)
├── Array          — N-dimensional numeric data (images, spectra, tensors)
│   ├── Image      — 2D/3D images (plugin)
│   ├── Label      — segmentation masks (plugin, CompositeData subclass)
│   └── ...
├── DataFrame      — tabular data (columns + rows)
├── Series         — single-column data
├── Text           — string content
├── Artifact       — opaque file handle (PDF, binary, raw instrument files)
│   └── MSRawFile  — mass spec raw data (plugin)
└── CompositeData  — named slots of DataObjects
    └── Label      — raster + metadata slots (plugin)
```

**D1.2 DataObject base class contract**

DataObject holds exactly four declared slots:
- `_framework: FrameworkMeta` — identity and lineage
- `_meta: BaseModel | None` — typed metadata
- `_user: dict[str, Any]` — free-form metadata (JSON-serializable)
- `_storage_ref: StorageReference | None` — pointer to persisted data

**DataObject MUST NOT carry raw data payloads.** There is no `_data` attribute, no `_arrow_table` attribute, no in-memory data container of any kind on DataObject instances that cross block boundaries.

**DataObject provides these data access methods** (all route through `storage_ref` → backend):

| Method | Defined on | Behavior |
|--------|-----------|----------|
| `to_memory()` | **DataObject** | Materialize full data from storage. Emits 2GB size warning. |
| `get_in_memory_data()` | **DataObject** | Alias for `to_memory()`. Subclasses may override (Text, Artifact). |
| `slice(*args)` | **DataObject** | Backend-specific sub-selection (zarr indexing, arrow column filter, etc.) |
| `iter_chunks(chunk_size)` | **DataObject** | Yield successive chunks from storage. |

**D1.3 Array subclass contract**

Array adds geometry metadata and array-specific access methods. These are **declared constructor parameters**, not monkey-patched attributes:

| Attribute/Method | Defined on | Type | Notes |
|-----------------|-----------|------|-------|
| `axes` | **Array** (constructor) | `list[str]` | Named axes, e.g. `["z", "y", "x", "c"]` |
| `shape` | **Array** (constructor) | `tuple[int, ...] \| None` | Data dimensions |
| `dtype` | **Array** (constructor) | `str \| None` | Element type |
| `chunk_shape` | **Array** (constructor) | `tuple[int, ...] \| None` | Storage chunk hint |
| `sel(**kwargs)` | **Array** | `-> Array` | Partial read along named axes. Reads from storage, not `_data`. |
| `iter_over(axis)` | **Array** | `-> Iterator[Array]` | Yield slices along one axis. Each slice has `storage_ref` set. |
| `__array__(dtype)` | **Array** | `-> np.ndarray` | NumPy protocol. Calls `to_memory()`. |

**Key change**: `sel()` and `iter_over()` no longer stash results in `_data`. Slice results are persisted to a temporary zarr store and returned with `storage_ref` set. This maintains the reference-only contract even for derived slices.

**D1.4 DataFrame subclass contract**

| Attribute/Method | Defined on | Notes |
|-----------------|-----------|-------|
| `to_memory()` | Inherited from **DataObject** | Returns `pyarrow.Table` from arrow backend |
| `get_in_memory_data()` | Inherited from **DataObject** | Same as `to_memory()` |

**Key change**: No `_arrow_table` attribute. All data access goes through `storage_ref` → ArrowBackend. The `_arrow_table` pattern is eliminated.

**D1.5 Text subclass contract**

| Attribute/Method | Defined on | Notes |
|-----------------|-----------|-------|
| `content` | **Text** (constructor) | String content. Small enough to hold in memory. |
| `get_in_memory_data()` | **Text** (override) | Returns `self.content` directly. |

Text is exempt from the "no in-memory data" rule because text content is inherently small (~KB) and is part of the object's identity (e.g., a prompt string). `storage_ref` is optional for Text.

**D1.6 Artifact subclass contract**

| Attribute/Method | Defined on | Notes |
|-----------------|-----------|-------|
| `file_path` | **Artifact** (constructor) | Path to the opaque file on disk. |
| `mime_type` | **Artifact** (constructor) | MIME type string. |
| `get_in_memory_data()` | **Artifact** (override) | Reads bytes from `file_path`. |

Artifact uses **path-only transport** — `file_path` is the reference, not `storage_ref`. Artifact is exempt from auto-flush (D5). `_auto_flush()` skips Artifact instances with `file_path` set.

**D1.7 CompositeData subclass contract**

CompositeData holds named slots, each of which is a DataObject. Each slot independently follows the storage-ref contract. The CompositeStore backend handles recursive persistence.

#### D2. ViewProxy is deleted

The `ViewProxy` class (`src/scieasy/core/proxy.py`) is deleted entirely. Its functionality is absorbed into the type hierarchy as follows:

| ViewProxy method | New location | Notes |
|---|---|---|
| `to_memory()` | **DataObject**.`to_memory()` | Direct backend read via `_get_backend(self._storage_ref).read(...)`. Includes 2GB size warning. |
| `slice(*args)` | **DataObject**.`slice(*args)` | Direct backend call. |
| `iter_chunks(chunk_size)` | **DataObject**.`iter_chunks(chunk_size)` | Direct backend call. |
| `shape` property | **Array**.`shape` | Already a constructor parameter on Array. Not on DataObject. |
| `axes` property | **Array**.`axes` | Already a constructor parameter on Array. Not on DataObject. |
| `from_file(path)` | Removed | Use `Artifact(file_path=Path(path))` or construct DataObject with appropriate `storage_ref`. |
| `_get_backend(ref)` | Module-level utility in `scieasy.core.storage.backend_router` | Shared backend resolution, used by DataObject methods internally. |

**`DataObject.view()` is deleted.** There is no ViewProxy path. Block authors call methods directly on the typed instance:

```python
# OLD (via ViewProxy):
data = image.view().to_memory()        # indirection through ViewProxy
chunk = image.view().slice(0, 100)     # indirection through ViewProxy

# NEW (direct on DataObject/Array):
data = image.to_memory()               # DataObject method, direct backend call
sub = image.sel(z=5)                   # Array method, direct backend call
for chunk in image.iter_chunks(1024):  # DataObject method, direct backend call
    ...
```

#### D3. `_data` and `_arrow_table` are prohibited on cross-boundary DataObjects

**Rule**: Any DataObject returned from `Block.run()` (or `IOBlock.load()`) MUST have `storage_ref` set (or `file_path` for Artifact). The framework enforces this at the IOBlock level (D4) and at the worker auto-flush boundary.

**Transient in-memory data within a single block's `run()` is allowed.** A block may compute results in memory (e.g., CellPose producing a mask ndarray). The framework's existing `_auto_flush()` mechanism persists these to storage before the data crosses the process boundary. This behavior is unchanged.

**Per-class elimination of in-memory backdoors:**

| Class | Attribute removed | Current usage | Migration |
|-------|------------------|---------------|-----------|
| **Array** | `_data` (monkey-patched, not declared) | Set by loaders: `img._data = np.asarray(...)`. Checked by `Array.to_memory()`, `Array.sel()`, `get_in_memory_data()`. | Remove all `_data` assignments and `hasattr` checks. All data access routes through `storage_ref` → ZarrBackend. |
| **DataFrame** | `_arrow_table` (monkey-patched, not declared) | Set by loaders: `df._arrow_table = table`. Checked by `get_in_memory_data()`, `_dataframe_to_arrow_table()`. | Remove all `_arrow_table` assignments and checks. All data access routes through `storage_ref` → ArrowBackend. |
| **Series** | `_arrow_table` (inherited pattern from DataFrame) | Set inconsistently. `_load_series()` currently loses payload entirely. | Fix payload loss first (write to arrow backend). Then same migration as DataFrame. |
| **Text** | `content` (declared constructor parameter) | **Exempt.** Text content is small (~KB) and is part of the object's identity. `content` is a legitimate declared field, not a monkey-patched backdoor. | No change. |
| **Artifact** | `file_path` (declared constructor parameter) | **Exempt.** File path is the transport mechanism. | No change. See D5. |
| **CompositeData** | Per-slot `_data`/`_arrow_table` on slot objects | Each slot is independently a DataObject. | Recursive: each slot follows its own class's migration. |

**What `_auto_flush()` handles after this ADR**: Only transient outputs from ProcessBlock/CodeBlock/AppBlock `run()` methods — block authors who compute results in memory and don't explicitly persist them. The framework flushes these to storage before serialization. IOBlock loaders are expected to handle their own persistence (D4).

#### D4. IOBlock base class guarantees storage-ref; provides persistence helpers for loader authors

The `load()` signature changes to accept an `output_dir` parameter. The IOBlock base class provides two guarantees:

1. **Correctness guarantee**: After `load()` returns, the base class checks every DataObject. If `storage_ref` is missing, the base class auto-flushes to storage. **No DataObject without `storage_ref` ever crosses the block boundary.** This is a safety net — loader authors who return in-memory objects still produce correct results.

2. **Helper API**: The base class provides `persist_array()` and `persist_table()` helpers for loader authors who want streaming writes (constant memory). **Loader authors who know their data is large SHOULD use these helpers.** Loader authors who don't care can return in-memory objects and let the base class handle persistence.

**The framework guarantees correctness. The loader author controls optimality.** Loader authors know their data characteristics — a 1KB CSV doesn't need streaming; a 100G TIFF does.

**New `IOBlock` contract:**

```python
class IOBlock(Block):
    @abstractmethod
    def load(self, config: BlockConfig, output_dir: str) -> DataObject | Collection:
        """Load data from source.

        Implementations may EITHER:

        (a) Return an in-memory DataObject (simple path):
            The base class auto-persists it to storage. Works for small/medium
            files. Will OOM on very large files.

            return Image(_data=np.array(...), axes=["y","x"], shape=shape, dtype=dtype)

        (b) Write to storage directly and return a reference (streaming path):
            Use self.persist_array() / self.persist_table() helpers for
            constant-memory writes. Required for large files.

            ref = self.persist_array(chunks_iter, shape, dtype, output_dir)
            return Image(storage_ref=ref, axes=["y","x"], shape=shape, dtype=dtype)

        Artifact subclasses are exempt — return with file_path, no storage write needed.
        """
        ...

    # -- persistence helpers for loader authors ---

    def persist_array(
        self, data_or_iterator, shape, dtype, output_dir, chunks=None,
    ) -> StorageReference:
        """Write array data to zarr storage, return StorageReference.

        data_or_iterator may be:
        - numpy ndarray (written in one shot)
        - iterator of (slice, chunk_array) tuples (streaming, constant memory)

        Memory usage: O(one chunk) for iterator mode, O(full array) for ndarray mode.
        """
        ...

    def persist_table(self, table, output_dir) -> StorageReference:
        """Write Arrow table to storage, return StorageReference."""
        ...

    # -- run() with auto-flush safety net ---

    def run(self, inputs, config):
        if self.direction == "input":
            output_dir = get_output_dir()
            result = self.load(config, output_dir=output_dir)
            if not isinstance(result, Collection):
                result = Collection(items=[result], item_type=type(result))
            # Safety net: auto-flush any item without storage_ref
            for item in result:
                if isinstance(item, DataObject) and item.storage_ref is None:
                    if not (isinstance(item, Artifact) and item.file_path is not None):
                        self._auto_flush(item)  # persist to zarr/arrow, set storage_ref
            return {self._resolved_load_output_port_name(): result}
```

**Example: LoadImage TIFF — streaming path (large files, constant memory):**

```python
def load(self, config, output_dir=None):
    path = Path(config.get("path"))

    with tifffile.TiffFile(str(path)) as tf:
        page0 = tf.pages[0]
        shape = (len(tf.pages), *page0.shape) if len(tf.pages) > 1 else page0.shape
        dtype = page0.dtype
        axes = _infer_axes(tf)

        # Stream page-by-page — memory = O(one page)
        def page_chunks():
            for i, page in enumerate(tf.pages):
                yield (i, page.asarray())

        ref = self.persist_array(page_chunks(), shape, dtype, output_dir)

    return Image(axes=axes, shape=shape, dtype=dtype, storage_ref=ref)
    # ← ~KB object. No _data, no in-memory payload.
```

**Example: LoadData CSV — simple path (small files, base class handles persistence):**

```python
def _load_dataframe(self, path, config, output_dir):
    import pyarrow.csv as pcsv
    table = pcsv.read_csv(str(path))
    # Return in-memory — base class will auto-persist via _auto_flush
    df = DataFrame()
    df._arrow_table = table  # OK for simple path; base class flushes this
    return df
```

**Example: LoadData CSV — streaming path (large files):**

```python
def _load_dataframe(self, path, config, output_dir):
    import pyarrow.csv as pcsv
    table = pcsv.read_csv(str(path))
    ref = self.persist_table(table, output_dir)
    return DataFrame(storage_ref=ref)
    # ← Reference only. No _arrow_table.
```

**Loader author's choice matrix:**

| Data size | Approach | Memory | Code complexity |
|-----------|----------|--------|-----------------|
| Small (< 1GB) | Return in-memory, base class auto-flushes | O(file size) | Minimal — same as today |
| Large (> 1GB) | Use `persist_array()` / `persist_table()` streaming helpers | O(chunk size) | Slightly more — iterate chunks |

**All 6 loader classes should be updated to use the new `load(config, output_dir)` signature.** Whether each individual loader function uses the simple path or streaming path is the loader author's decision based on expected data size:

| Loader | Recommended path | Rationale |
|--------|-----------------|-----------|
| `LoadImage` TIFF | Streaming | Scientific images routinely exceed 1GB |
| `LoadImage` Zarr | Reference | Zarr is already chunked storage — reference existing store |
| `LoadData` Array .zarr | Reference | Already lazy (only correct loader today) |
| `LoadData` Array .npy/.npz | Simple | Typically small; streaming .npy is not straightforward |
| `LoadData` DataFrame csv/parquet | Simple or Streaming | Author's choice based on expected table size |
| `LoadData` Text | Simple | Text files are small |
| `LoadData` Artifact | Exempt | Path-only transport (D5) |
| LCMS loaders | Simple | Domain-specific, typically small tables |

#### D5. Artifact and file-handle types skip auto-flush

`Artifact` and its subclasses (e.g., `MSRawFile`) use `file_path` as their transport mechanism, not `storage_ref`. They represent opaque files that should not be read into memory or copied into managed storage.

**`_auto_flush()` is modified to skip Artifact instances that have `file_path` set:**

```python
@staticmethod
def _auto_flush(obj: Any) -> Any:
    if not isinstance(obj, DataObject):
        return obj
    # NEW: Artifact with file_path uses path-only transport
    from scieasy.core.types.artifact import Artifact
    if isinstance(obj, Artifact) and obj.file_path is not None:
        return obj
    # ... existing flush logic ...
```

**Serialization**: `_serialise_one()` already handles Artifact via `_serialise_extra_metadata()` which writes `file_path` to the metadata sidecar. `_reconstruct_one()` already handles it via `_reconstruct_extra_kwargs()` which restores `file_path`. No changes needed to the wire protocol.

**SaveData for Artifact**: `_save_artifact()` copies the file via `shutil.copy2()`. This is correct behavior — it copies the file to the user-chosen path, not to managed storage.

#### D6. `get_in_memory_data()` per-class behavior

The current `get_in_memory_data()` on `DataObject` uses `hasattr` to check for undeclared attributes. This is replaced with a clean per-class dispatch:

**DataObject (base class):**
```python
def get_in_memory_data(self) -> Any:
    """Materialize data from storage for persistence/export."""
    return self.to_memory()  # storage_ref → backend → read
```

**Per-class overrides:**

| Class | `get_in_memory_data()` behavior | Rationale |
|-------|-------------------------------|-----------|
| **DataObject** (base) | `return self.to_memory()` | Default: read from storage via backend. |
| **Array** | Inherited from DataObject | `to_memory()` → ZarrBackend.read() → `np.ndarray` |
| **DataFrame** | Inherited from DataObject | `to_memory()` → ArrowBackend.read() → `pyarrow.Table` |
| **Series** | Inherited from DataObject | `to_memory()` → ArrowBackend.read() → `pyarrow.Table` (single column) |
| **Text** (override) | `return self.content` | Text content is in-memory by design (~KB). No storage round-trip needed. |
| **Artifact** (override) | `return self.file_path.read_bytes()` | Reads from original file. Not from managed storage. |
| **CompositeData** | Inherited from DataObject | `to_memory()` → CompositeStore.read() → reconstructs slot dict |

**Removed**: The `hasattr(self, "_data")` and `hasattr(self, "_arrow_table")` checks in the base class. No monkey-patched attributes are consulted.

This means SaveData's `_save_array()`, `_save_dataframe()`, etc. all work correctly with storage-backed objects — they call `get_in_memory_data()` → `to_memory()` → backend read.

#### D7. Worker reconstruction contract (restated from ADR-027 Add1)

`worker.reconstruct_inputs()` returns **typed DataObject instances** (e.g., `Image`, `DataFrame`), not `ViewProxy`. This decision from ADR-027 Addendum 1 is **correct and retained**.

The reconstruction hooks remain:
- `cls._reconstruct_extra_kwargs(metadata)` — per-base-class kwargs extraction
- `cls._serialise_extra_metadata(obj)` — per-base-class metadata serialization

The Meta Pydantic constraints remain:
- Frozen, no `PrivateAttr`, all fields must round-trip through `model_dump_json` / `model_validate_json`

#### D8. Checkpoint deserialization updated

`checkpoint.py`'s `deserialize_intermediate_refs()` currently constructs `ViewProxy` instances. This function is rewritten to construct typed `DataObject` instances using the same `_reconstruct_one()` path as the worker.

If type resolution fails (missing plugin), fall back to a base `DataObject(storage_ref=ref)` rather than a `ViewProxy`.

#### D9. Documentation is unified

All references to the old "engine injects ViewProxy" model are removed from:
- `docs/architecture/ARCHITECTURE.md:331-362` (and line 618)
- `docs/adr/ADR.md` ADR-007 discussion text
- Block SDK guide

The canonical documentation model is:
- Blocks receive **typed DataObject instances** with `storage_ref` set
- Data is lazy — `to_memory()` / `sel()` / `iter_chunks()` trigger reads on demand
- ViewProxy does not exist

---

### 4. Impact Scope

#### 4.1 Files deleted

| File | Reason |
|------|--------|
| `src/scieasy/core/proxy.py` | ViewProxy class eliminated |
| `tests/core/test_proxy.py` | Tests for deleted class |
| `tests/core/test_proxy_multi_backend.py` | Tests for deleted class |

#### 4.2 Core type system changes

**DataObject base class** (`src/scieasy/core/types/base.py`):

| Change | Detail |
|--------|--------|
| Delete `view()` method | Returns ViewProxy — ViewProxy no longer exists (D2) |
| Rewrite `to_memory()` | Direct: `_get_backend(self._storage_ref).read(self._storage_ref)`. Add 2GB size warning from ViewProxy. |
| Add `slice(*args)` | New method: `_get_backend(self._storage_ref).slice(self._storage_ref, *args)` |
| Add `iter_chunks(chunk_size)` | New method: `yield from _get_backend(self._storage_ref).iter_chunks(self._storage_ref, chunk_size)` |
| Rewrite `get_in_memory_data()` | Remove `hasattr(self, "_data")` and `hasattr(self, "_arrow_table")` checks. New body: `return self.to_memory()` (D6) |
| Remove `TYPE_CHECKING` ViewProxy import | Line 34: `from scieasy.core.proxy import ViewProxy` |

**Array subclass** (`src/scieasy/core/types/array.py`):

| Change | Detail |
|--------|--------|
| Remove `to_memory()` override | Delete the `if self._storage_ref is None and hasattr(self, "_data")` backdoor. Inherit DataObject's `to_memory()`. |
| Rewrite `sel(**kwargs)` | Remove `hasattr(self, "_data")` check (line 214). Always read from storage: `full_data = self.to_memory()`. Persist slice result to temp zarr with `storage_ref` instead of stashing in `_data`. |
| Rewrite `iter_over(axis)` | Delegates to `sel()` per-index — inherits sel()'s storage-based behavior. |
| `__array__()` | No change — already calls `self.to_memory()`. |
| `shape`, `axes`, `dtype` | No change — already declared constructor parameters. |

**DataFrame subclass** (`src/scieasy/core/types/dataframe.py`):

| Change | Detail |
|--------|--------|
| No `_arrow_table` attribute | All data access through inherited `to_memory()` → ArrowBackend |

**Text subclass** (`src/scieasy/core/types/text.py`):

| Change | Detail |
|--------|--------|
| `get_in_memory_data()` override | Returns `self.content`. No storage round-trip. (Existing behavior, no change.) |

**Artifact subclass** (`src/scieasy/core/types/artifact.py`):

| Change | Detail |
|--------|--------|
| `get_in_memory_data()` override | Returns `self.file_path.read_bytes()`. (Existing behavior, no change.) |
| Exempt from auto-flush | See D5. |

**CompositeData** (`src/scieasy/core/types/composite.py`):

| Change | Detail |
|--------|--------|
| Per-slot compliance | Each slot is an independent DataObject — follows its own class's contract. CompositeStore handles recursive persistence. |

#### 4.3 IOBlock and loader changes

| File | Changes |
|------|---------|
| `src/scieasy/blocks/io/io_block.py` | Change `load()` signature to `load(self, config, output_dir)`. Add `persist_array()` and `persist_table()` helper methods. Update `run()` to pass `output_dir` and auto-flush any item without `storage_ref` (D4 safety net). |
| `src/scieasy/blocks/io/loaders/load_data.py` | Update `load()` to accept `output_dir`. Per-function changes: `_load_array .zarr` (already lazy, no change). `_load_array .npy/.npz/.parquet` (simple path — base class auto-flushes). `_load_dataframe` (simple or streaming — author's choice). `_load_series` (fix payload loss — must write to arrow). `_load_text` (simple path). `_load_artifact` (exempt, path-only D5). `_load_composite_data` (recursive, pass output_dir). |
| `packages/scieasy-blocks-imaging/.../load_image.py` | Streaming path for `_load_tiff` (page-by-page via `persist_array()`). `_load_zarr` (reference existing zarr store, no copy). |
| `packages/scieasy-blocks-lcms/.../load_mzml_files.py` | Update `load()` signature. MSRawFile is Artifact subclass — path-only, exempt. |
| `packages/scieasy-blocks-lcms/.../load_peak_table.py` | Fix: write DataFrame to arrow via `persist_table()`, remove pandas from `user` dict. |
| `packages/scieasy-blocks-lcms/.../load_mid_table.py` | Update `load()` signature, use simple or streaming path. |
| `packages/scieasy-blocks-lcms/.../load_sample_metadata.py` | Update `load()` signature, use simple path. |
| `src/scieasy/blocks/io/savers/save_data.py` | Remove `_arrow_table` check. Phase 3: add chunked export for Parquet/CSV/Zarr. |
| `packages/scieasy-blocks-imaging/.../save_image.py` | No immediate change. Phase 3: add chunked TIFF write. |
| `packages/scieasy-blocks-lcms/.../save_table.py` | Update `save()` to use `get_in_memory_data()` consistently. |

#### 4.4 Block framework changes

| File | Changes |
|------|---------|
| `src/scieasy/blocks/base/block.py` | Remove `_is_view_proxy()` helper. Update `validate()` to remove ViewProxy branch. Update `_auto_flush()` to skip Artifact (D5). |
| `src/scieasy/blocks/process/process_block.py` | No change — already calls `_auto_flush()` on outputs. |
| `src/scieasy/blocks/process/utils.py` | Remove ViewProxy isinstance check in `to_arrow()`. |
| `src/scieasy/blocks/app/bridge.py` | Remove ViewProxy isinstance check. |
| `src/scieasy/blocks/process/builtins/split.py` | Replace `_arrow_table` assignments with `get_in_memory_data()` + storage write. |
| `src/scieasy/blocks/process/builtins/merge.py` | Same pattern. |

#### 4.5 Engine changes

| File | Changes |
|------|---------|
| `src/scieasy/engine/checkpoint.py` | Rewrite `deserialize_intermediate_refs()` to construct DataObject, not ViewProxy (D8). |
| `src/scieasy/engine/runners/worker.py` | Remove ViewProxy references from docstrings. No structural changes — already returns typed DataObject. |
| `src/scieasy/engine/runners/local.py` | `serialise_inputs()` added by PR #623 (P0 fix) remains as defense-in-depth. |
| `src/scieasy/engine/scheduler.py` | Remove ViewProxy comments. |

#### 4.6 SaveData and saver changes

SaveData is a **sink block** — it reads data from storage and writes to a user-chosen file format.

**Audit finding §2.2.5: SaveData currently cannot reliably export storage-backed objects.** `_save_array()` calls `obj.get_in_memory_data()`, which checks `hasattr(self, "_data")`. A storage-backed Array reconstructed in the worker has `storage_ref` set but no `_data`, so `get_in_memory_data()` raises `ValueError`. The same applies to `_dataframe_to_arrow_table()` which checks for `_arrow_table`.

**This is resolved by D6**: `get_in_memory_data()` is rewritten to route through `to_memory()` → storage backend read. SaveData works correctly with storage-backed objects without SaveData-specific code changes in Phase 1/2.

**Phase 3 optimization**: For large data, SaveData should read from storage chunk-by-chunk and write to the target format incrementally, avoiding full materialization. This is format-dependent — Parquet and Zarr support chunked writes; NPY and CSV do not.

| File | Changes |
|------|---------|
| `src/scieasy/blocks/io/savers/save_data.py` | Phase 1/2: Remove `_arrow_table` check in `_dataframe_to_arrow_table()`. All paths work via `get_in_memory_data()` → `to_memory()` → storage read. Phase 3: Add chunked export paths for formats that support it (Parquet, Zarr). |
| `packages/scieasy-blocks-imaging/.../save_image.py` | Phase 1/2: No change needed — SaveImage calls `to_memory()` which now routes through storage. Phase 3: Add chunked TIFF write (page-by-page from zarr). |

**Per-format SaveData behavior after this ADR:**

| Format | Phase 1/2 (correctness) | Phase 3 (streaming) |
|--------|------------------------|---------------------|
| `.zarr` | `get_in_memory_data()` → full read → zarr write | Direct zarr-to-zarr copy (zero materialization) |
| `.npy` | `get_in_memory_data()` → full read → `np.save()` | Full read required (NPY format is not chunked) |
| `.parquet` | `get_in_memory_data()` → full read → `pq.write_table()` | Chunked: read row groups from arrow → write row groups to parquet |
| `.csv` | `get_in_memory_data()` → full read → `write_csv()` | Chunked: read batches from arrow → write batches to CSV |
| TIFF | `get_in_memory_data()` → full read → `tifffile.imwrite()` | Chunked: read z-planes from zarr → write pages to TIFF |

#### 4.7 Utility changes

| File | Changes |
|------|---------|
| `src/scieasy/utils/axis_iter.py` | Replace `result._data = data` with persist-to-zarr + set storage_ref. |
| `src/scieasy/utils/broadcast.py` | Update ViewProxy references in docstrings/warnings. |

#### 4.8 Test changes

| File | Changes |
|------|---------|
| `tests/core/test_proxy.py` | Delete entirely. |
| `tests/core/test_proxy_multi_backend.py` | Delete entirely. |
| `tests/core/test_dataobject_extended.py` | Update: assert `storage_ref is not None` instead of `_data` checks. |
| `tests/core/test_storage.py` | Remove ViewProxy construction. |
| `tests/engine/test_checkpoint.py` | Update: assert DataObject instead of ViewProxy from deserialization. |
| `tests/engine/test_worker.py` | Remove ViewProxy assertion (already asserts `not isinstance(x, ViewProxy)`). |
| `tests/engine/test_worker_typed_reconstruction.py` | Remove ViewProxy imports and negative assertions. |
| `tests/blocks/test_block_base.py` | Remove ViewProxy validation tests. |
| `tests/blocks/test_process_utils.py` | Remove ViewProxy mock. |
| `tests/blocks/io/test_load_data.py` | Update: assert `storage_ref is not None` instead of `_data`/`_arrow_table` checks. |

#### 4.9 Documentation changes

| File | Changes |
|------|---------|
| `docs/architecture/ARCHITECTURE.md` | Remove ViewProxy-injection model (lines 331-362, 613-618). Update to DataObject-only model. |
| `docs/adr/ADR.md` (ADR-007) | Add note: "ViewProxy eliminated in ADR-031. Methods absorbed into DataObject." |
| `docs/adr/ADR.md` (ADR-027 Add1) | Mark as ~~deprecated~~ — superseded by ADR-031. |
| `docs/guides/block-sdk.md` | Update data access examples: `item.to_memory()` not `item.view().to_memory()`. |

---

### 5. Implementation Plan

#### Phase 1: Loader rewrite + core enforcement (all loaders write to storage directly)

1. **Change `IOBlock.load()` signature** — add `output_dir: str` parameter. Update `IOBlock.run()` to pass `output_dir` and enforce `storage_ref` on returned objects (D4).
2. **Rewrite all 6 loader classes (~12 functions)** to write directly to zarr/arrow storage and return reference-only DataObjects. Use streaming writes where the format supports it (TIFF page-by-page, CSV Arrow streaming, etc.).
3. **Artifact auto-flush skip** (D5) — `_auto_flush()` skips Artifact with `file_path`.
4. **Fix `_load_series()` payload loss** — write to arrow backend, return with `storage_ref`.
5. **Fix `LoadPeakTable` user-dict violation** — write DataFrame to arrow storage, not `user` dict.
6. **Update test fixtures** — mock loaders in `tests/` must comply with new `load()` signature.

#### Phase 2: ViewProxy elimination and `_data` cleanup

7. **Move `_get_backend()` and data access methods to DataObject** — `to_memory()`, `slice()`, `iter_chunks()`. Add 2GB size warning.
8. **Delete `ViewProxy` class** (`src/scieasy/core/proxy.py`) and `DataObject.view()` method.
9. **Rewrite `get_in_memory_data()`** — route through `to_memory()`, remove `hasattr(self, "_data")` / `_arrow_table` checks (D6).
10. **Update `Array.to_memory()`** — remove `_data` backdoor, always read from storage.
11. **Update `Array.sel()`** — remove `_data` check, read from storage. Persist slice result to temp zarr with storage_ref (no `_data` stashing).
12. **Update `checkpoint.py`** — `deserialize_intermediate_refs()` constructs typed DataObject, not ViewProxy (D8).
13. **Update `save_data.py`** — remove `_arrow_table` check in `_dataframe_to_arrow_table()`.
14. **Remove all ViewProxy imports, isinstance checks, and helpers** — `block.py:_is_view_proxy()`, `process/utils.py`, `app/bridge.py`, all comments.
15. **Update `split.py`, `merge.py`, `axis_iter.py`** �� replace `_arrow_table`/`_data` assignments with storage writes.
16. **Delete test files** — `test_proxy.py`, `test_proxy_multi_backend.py`. Update all tests asserting `_data` to assert `storage_ref`.

#### Phase 3: Process-side optimization (incremental)

17. **Array.sel() Zarr partial-read** — leverage Zarr backend's native slicing instead of full materialization + numpy indexing.
18. **SaveData streaming export** — for formats that support it, read from zarr chunk-by-chunk, write to target format chunk-by-chunk.
19. **Block SDK guidance** — document `iter_chunks()` / `sel()` as preferred over `to_memory()` for large data. Add framework-level memory warning when `to_memory()` on large data.

---

### 6. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Performance regression from format conversion** — loaders convert source format (TIFF/CSV/etc.) to zarr/arrow; downstream reads from zarr/arrow, SaveData converts back to target format | Medium | This is inherent to using zarr as universal intermediate format. Streaming writes minimize memory. For workflows where source and target format match, a future "passthrough" optimization can skip intermediate storage. |
| **Existing plugin blocks break** — blocks that set `_data` directly | Low | D4 enforcement is backward-compatible — it flushes `_data` objects to zarr automatically. Blocks don't need to change immediately. |
| **`Array.sel()` becomes slower** — currently reads from `_data` (in-memory), will read from zarr | Medium | Zarr partial-read (Phase 4) mitigates this. For small arrays, the overhead is negligible. |
| **Test breakage** — many tests assert `_data` presence | Low | Systematic update: assert `storage_ref is not None` instead. |
| **Checkpoint backward compatibility** — old checkpoints may have ViewProxy-format entries | Low | `deserialize_intermediate_refs()` rewritten to produce DataObject. Old wire format still parseable. |

---

### 7. Alternatives Considered

1. **Keep ViewProxy as opt-in helper (ADR-027 Add1 approach).** Rejected — no block uses it. Maintaining a class with zero consumers adds complexity without value.

2. **Keep `_data` but enforce it's always backed by storage_ref too.** Rejected — two sources of truth for the same data. Which wins when they disagree? The `_data` pattern invites bypass of the storage contract.

3. **Create per-format read-only backends (TiffBackend, NpyBackend, etc.) for true zero-copy lazy loading.** Deferred — not rejected, but not required for this ADR. Zarr as the universal intermediate format is sufficient. Per-format backends can be added incrementally when performance requires it.

4. **Make DataObject.to_memory() check `_data` first as fast-path cache.** Rejected — this is the existing backdoor that caused the regression. A single code path (storage_ref → backend → read) is simpler, more predictable, and debuggable.

---

### 8. Consequences

- **DataObject becomes the single, unambiguous data abstraction.** No ViewProxy, no `_data` backdoor, no dual code paths.
- **All loaders become compliant immediately** via D4 (IOBlock enforcement), without individual loader code changes.
- **SaveData works with storage-backed objects** because `get_in_memory_data()` routes through `to_memory()`.
- **100G+ data support becomes architecturally possible** once Phase 3 (streaming loaders) is implemented. Phase 1 alone does not solve the OOM problem but removes the architectural barriers to solving it.
- **The wire protocol is unchanged.** JSON payload format between scheduler and worker is not modified.
- **56+ code locations require updates** across 19 source files. The changes are mechanical (remove ViewProxy imports, remove `_data` checks, update assertions) except for the IOBlock enforcement (D4) and the `to_memory()` rewrite.
- **ADR-027 Addendum 1 is formally deprecated.** Its correct decisions (typed reconstruction, per-class hooks, Meta constraints) are restated in D7.

---

### Appendix A: Deprecated ADR-027 Addendum 1

**Status**: ~~proposed~~ → **deprecated (superseded by ADR-031)**

ADR-027 Addendum 1 ("Worker subprocess type reconstruction returns typed DataObject instances, not ViewProxy") is deprecated in its entirety. The following decisions from Addendum 1 are **restated in ADR-031** with updated scope:

| Addendum 1 Decision | ADR-031 Status |
|---|---|
| D11': typed DataObject reconstruction in worker | **Retained** (ADR-031 D7) |
| `_reconstruct_extra_kwargs` / `_serialise_extra_metadata` hooks | **Retained** (ADR-031 D7) |
| Meta Pydantic constraints (frozen, JSON-round-trippable) | **Retained** (ADR-031 D7) |
| ViewProxy "demoted to opt-in helper via `item.view()`" | **Rejected** — ViewProxy deleted entirely (ADR-031 D2) |
| PhysicalQuantity Pydantic integration via `__get_pydantic_core_schema__` | **Retained** — unchanged, not in scope of ADR-031 |

References to ADR-027 Addendum 1 in code comments should be updated to cite ADR-031 D7 for reconstruction contract and ADR-031 D2 for ViewProxy elimination.

---

### Appendix B: Audit Report Reference

This ADR was motivated by the independent data storage and transport audit documented in `docs/data-storage-transport-audit.en.md` (2026-04-11). Key audit findings are cited in §2.2 with evidence references to specific source files and line numbers.

The audit's summary:

> SciEasy's transport layer is mostly reference-based now, but its load, processing, and export layers still contain widespread eager materialization, payload-loss edge cases, and multiple mismatches with the stated design philosophy.

