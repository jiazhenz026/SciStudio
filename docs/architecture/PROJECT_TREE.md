# SciStudio — Project Tree

> Maps 1:1 to the Architecture Document (ARCHITECTURE.md).
> Each file is annotated with its responsibility.

> **Note:** This tree shows the **target architecture**. Sections marked *"planned"* contain files that do not yet exist in the repository.

```
scistudio/                               # ← repo root
│
├── pyproject.toml                      # Package metadata, dependencies, entry_points
├── README.md
├── ARCHITECTURE.md
├── LICENSE
├── Makefile                            # dev shortcuts: make test, make lint, make serve
│
│
│ ══════════════════════════════════════════════════════════════════
│  PYTHON BACKEND  (src layout — `pip install -e .` installs scistudio)
│ ══════════════════════════════════════════════════════════════════
│
├── src/
│   └── scistudio/
│       ├── __init__.py                 # Package root, version string
│       │
│       │
│       │ ── Layer 1: Data Foundation ─────────────────────────────
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   │
│       │   ├── types/                  # DataObject type hierarchy — CORE BASE TYPES ONLY
│       │   │   │                       #   (ADR-027 D2): domain subtypes (Image, Spectrum,
│       │   │   │                       #   PeakTable, AnnData, etc.) live in plugin packages
│       │   │   │                       #   and register via the scistudio.types entry-point.
│       │   │   ├── __init__.py         # Re-exports the seven base types
│       │   │   ├── base.py             # DataObject ABC, TypeSignature, framework/meta/user
│       │   │   │                       #   slots (ADR-027 D5). No free-dict metadata;
│       │   │   │                       #   .metadata property is a backward-compat shim.
│       │   │   ├── array.py            # Array (wraps ndarray-like, Zarr-backed).
│       │   │   │                       #   Instance-level `axes` + class-level
│       │   │   │                       #   required_axes/allowed_axes/canonical_order
│       │   │   │                       #   (ADR-027 D1). Methods: sel(), iter_over()
│       │   │   │                       #   with Level 1 laziness and metadata preservation
│       │   │   │                       #   (ADR-027 D4). NO Image/MSImage/FluorImage/SRSImage.
│       │   │   ├── series.py           # Series (1D indexed data). NO Spectrum subclasses.
│       │   │   ├── dataframe.py        # DataFrame (columnar tabular data). NO PeakTable subclasses.
│       │   │   ├── text.py             # Text (plain text, markdown, JSON)
│       │   │   ├── artifact.py         # Artifact (opaque files: PDF, binary, etc.)
│       │   │   ├── composite.py        # CompositeData (named heterogeneous slots).
│       │   │   │                       #   NO AnnData/SpatialData subclasses — plugin-provided.
│       │   │   ├── collection.py       # Collection: homogeneous ordered transport wrapper
│       │   │   │                       #   for DataObjects between blocks (ADR-020).
│       │   │   │                       #   NOT a DataObject subclass — type identity from contents.
│       │   │   └── registry.py         # TypeRegistry: discovers types from
│       │   │                           #   Tier 1: {project}/types/ + ~/.scistudio/types/
│       │   │                           #   Tier 2: scistudio.types entry_points
│       │   │                           #   Resolves inheritance for port matching.
│       │   │                           #   resolve(type_chain) helper for worker subprocess
│       │   │                           #   type reconstruction (ADR-027 D11).
│       │   │
│       │   ├── meta/                   # Framework metadata slot (ADR-027 D5)
│       │   │   ├── __init__.py         # Public exports: FrameworkMeta, ChannelInfo,
│       │   │   │                       #   with_meta helper
│       │   │   └── framework.py        # FrameworkMeta Pydantic BaseModel
│       │   │                           #   (created_at, object_id, source, lineage_id,
│       │   │                           #   derived_from)
│       │   │
│       │   ├── units.py                # PhysicalQuantity dataclass + unit tables
│       │   │                           #   (length/time/freq/wavenumber). ~50 LOC.
│       │   │                           #   Pydantic integration for subprocess JSON round-trip.
│       │   │                           #   ADR-027 D6: not pint — cold-start sensitive.
│       │   │
│       │   ├── storage/                # Storage backends (per-type persistence)
│       │   │   ├── __init__.py
│       │   │   ├── base.py             # StorageBackend protocol (read/write/slice/iter_chunks)
│       │   │   ├── zarr_backend.py     # Zarr store for Array types (chunked, lazy)
│       │   │   ├── arrow_backend.py    # Apache Arrow / Parquet for DataFrame types
│       │   │   ├── filesystem.py       # Plain filesystem for Text, Artifact
│       │   │   ├── composite_store.py  # Directory-of-slots storage for CompositeData
│       │   │   └── ref.py              # StorageReference: pointer to a stored object
│       │   │
│       │   ├── proxy.py                # ViewProxy: lazy-loading accessor (slice, iter_chunks,
│       │   │                           #   to_memory, shape). Injected into block.run() inputs.
│       │   │
│       │   ├── lineage/                # Unified run lineage (ADR-038; supersedes metadata.db
│       │   │   │                       #   from ADR-032 + the dormant earlier lineage schema)
│       │   │   ├── __init__.py
│       │   │   ├── record.py           # RunRecord, BlockExecutionRecord, DataObjectRow,
│       │   │   │                       #   BlockIORow dataclasses (4 normalized tables)
│       │   │   ├── store.py            # LineageStore: SQLite WAL r/w for unified 4-table schema
│       │   │   ├── recorder.py         # LineageRecorder: subscribes to EventBus, writes runs +
│       │   │   │                       #   block_executions + data_objects + block_io rows;
│       │   │   │                       #   moved from engine/lineage_recorder.py
│       │   │   ├── environment.py      # EnvironmentSnapshot: full `uv pip freeze` by default
│       │   │   ├── run_context.py      # Thread-local RunContext (run_id, block_execution_id)
│       │   │   │                       #   for opt-in block access (ADR-038 §5.1)
│       │   │   ├── methods_export.py   # Render markdown methods section from a run record
│       │   │   └── graph.py            # Provenance graph queries (ancestors, diff, audit)
│       │   │
│       │   └── versioning/             # Source version control via bundled git CLI (ADR-039)
│       │       ├── __init__.py
│       │       ├── git_engine.py       # Subprocess wrapper around bundled `git` binary:
│       │       │                       #   commit / log / diff / restore / branches / status /
│       │       │                       #   merge / cherry-pick / stash. Plumbing parsers
│       │       │                       #   (--porcelain=v2, --format=...).
│       │       ├── git_binary.py       # Locate bundled git executable across platforms
│       │       │                       #   (resources/git/bin/git[.exe]). Falls back to system
│       │       │                       #   git for `scistudio gui` developer CLI.
│       │       ├── gitignore_template.py  # Default .gitignore content + write logic (ADR-039 §3.3)
│       │       ├── status.py           # Working-tree status helpers (dirty flag, modified files)
│       │       └── watcher.py          # Detect external git changes (HEAD / refs mtime;
│       │                               #   feeds workflow_watcher's git.head_changed event)
│       │
│       │
│       │ ── Layer 2: Block System ────────────────────────────────
│       │
│       ├── blocks/
│       │   ├── __init__.py
│       │   │
│       │   ├── base/                   # Block ABC and core machinery
│       │   │   ├── __init__.py
│       │   │   ├── package_info.py     # PackageInfo dataclass for external block package
│       │   │   │                       #   metadata (ADR-025). Fields: name, description,
│       │   │   │                       #   author, version. Kept in separate file to avoid
│       │   │   │                       #   circular imports when external packages import it.
│       │   │   ├── block.py            # Block ABC: validate(), run(), postprocess()
│       │   │   │                       #   Fields: name, version, input_ports, output_ports,
│       │   │   │                       #   execution_mode, resource_request,
│       │   │   │                       #   terminate_grace_sec (ADR-019). run() always
│       │   │   │                       #   executes in subprocess, not engine process (ADR-017).
│       │   │   │                       #   Utilities: pack(), unpack(), map_items(),
│       │   │   │                       #   parallel_map() for Collection handling (ADR-020).
│       │   │   │                       #   process_item() convenience method + _auto_flush()
│       │   │   │                       #   for memory-safe per-item processing (ADR-020 Addendum 5).
│       │   │   ├── ports.py            # Port, InputPort, OutputPort
│       │   │   │                       #   Type matching + optional constraint function
│       │   │   ├── config.py           # BlockConfig: validated param container (Pydantic)
│       │   │   ├── state.py            # BlockState enum (8 states incl. CANCELLED, SKIPPED;
│       │   │   │                       #   ADR-018), ExecutionMode, InputDelivery enums
│       │   │   │                       #   BatchMode/BatchErrorStrategy removed (ADR-020)
│       │   │   └── result.py           # BlockResult (BatchResult removed per ADR-020)
│       │   │
│       │   ├── _templates/              # Built-in code templates served via
│       │   │   │                        #   GET /api/blocks/template?kind=... (ADR-036 §3.12).
│       │   │   │                        #   Frontend "New .py in blocks/" action scaffolds
│       │   │   │                        #   from these into the project's blocks/ folder.
│       │   │   └── block_base_template.py
│       │   │                            # Minimal BlockBase + BlockSpec + named ports +
│       │   │                            # config_schema + run() NotImplementedError stub.
│       │   │                            # Comment marker `# >>> EDIT THIS <<<` highlights
│       │   │                            # the run body so users find the right line.
│       │   │
│       │   ├── io/                     # IOBlock — data ingress / egress
│       │   │   ├── __init__.py
│       │   │   ├── io_block.py         # IOBlock: abstract base class with abstract
│       │   │   │                       #   load()/save() methods + default run() dispatch
│       │   │   │                       #   on subclass `direction` ClassVar (ADR-028 §D2).
│       │   │   │                       #   The old format-adapter registry pattern is gone;
│       │   │   │                       #   concrete IO blocks subclass IOBlock directly.
│       │   │   ├── loaders/            # Concrete input-only IOBlock subclasses
│       │   │   │   ├── __init__.py
│       │   │   │   └── load_data.py    # LoadData: dynamic-port loader covering all six core
│       │   │   │                       #   DataObject types (Array, DataFrame, Series, Text,
│       │   │   │                       #   Artifact, CompositeData). Declares dynamic_ports
│       │   │   │                       #   ClassVar (ADR-028 Addendum 1 §C5) and overrides
│       │   │   │                       #   get_effective_output_ports() to narrow accepted_types
│       │   │   │                       #   per the core_type config enum. load() dispatches to
│       │   │   │                       #   six private module-level _load_* functions per §C9
│       │   │   │                       #   (no helper classes). Pickle is opt-in via allow_pickle.
│       │   │   └── savers/             # Concrete output-only IOBlock subclasses
│       │   │       ├── __init__.py
│       │   │       └── save_data.py    # SaveData: mirror of LoadData, six private _save_* funcs
│       │   │                           #   dispatched from save() per ADR-028 Addendum 1 §C9.
│       │   │
│       │   ├── process/                # ProcessBlock — data transformation
│       │   │   ├── __init__.py
│       │   │   ├── process_block.py    # ProcessBlock base (algorithm, params)
│       │   │   │                       #   Default run() iterates via process_item() + auto-flush
│       │   │   │                       #   (ADR-020 Addendum 5 Tier 1)
│       │   │   ├── builtins/           # Built-in process blocks shipped with framework
│       │   │   │   ├── __init__.py
│       │   │   │   ├── merge.py        # Merge / join / concatenate multi-input
│       │   │   │   ├── split.py        # Filter / subset / train-test split
│       │   │   │   ├── transform.py    # Generic column/array transforms
│       │   │   │   └── register.py     # Image registration (cross-modal alignment)
│       │   │   └── contrib/            # Community-contributed process blocks (examples)
│       │   │       ├── __init__.py
│       │   │       ├── cellpose_segment.py
│       │   │       ├── baseline_correction.py
│       │   │       └── spectral_pca.py
│       │   │
│       │   ├── code/                   # CodeBlock — user-provided scripts
│       │   │   ├── __init__.py
│       │   │   ├── code_block.py       # CodeBlock: inline mode + script mode
│       │   │   │                       #   Dispatches to CodeRunner by language
│       │   │   │                       #   Auto-unpack: Collection → native objects / LazyList
│       │   │   │                       #   Auto-repack: native objects → Collection (ADR-020 Addendum 4)
│       │   │   ├── lazy_list.py        # LazyList: looks like list, loads items on demand from
│       │   │   │                       #   Collection via ViewProxy. Memory-safe iteration for
│       │   │   │                       #   user scripts (ADR-020 Addendum 4)
│       │   │   ├── runners/            # Language-specific execution environments
│       │   │   │   ├── __init__.py
│       │   │   │   ├── base.py         # CodeRunner protocol (execute_inline, execute_script)
│       │   │   │   ├── python_runner.py    # Python: subprocess worker calls exec()/importlib (ADR-017)
│       │   │   │   ├── r_runner.py         # R: subprocess calling Rscript (ADR-017, no rpy2)
│       │   │   │   └── julia_runner.py     # Julia: subprocess calling julia (ADR-017, no juliacall)
│       │   │   ├── runner_registry.py  # Maps language string → runner class
│       │   │   └── introspect.py       # Script introspection: parse run() signature,
│       │   │                           #   extract configure() schema, auto-gen ports
│       │   │
│       │   ├── app/                    # AppBlock — external GUI software bridge
│       │   │   ├── __init__.py
│       │   │   ├── app_block.py        # AppBlock: launch → pause → watch → resume
│       │   │   ├── bridge.py           # ExternalAppBridge protocol (serialise, launch, watch)
│       │   │   │                       #   prepare() iterates Collection, writes files one at a
│       │   │   │                       #   time for memory safety (ADR-020 Addendum 5)
│       │   │   └── watcher.py          # File watcher (polling) for output detection
│       │   │                           #   + process death detection via ProcessHandle (ADR-019)
│       │   │
│       │   ├── ai/                     # AIBlock — LLM-driven processing
│       │   │   ├── __init__.py
│       │   │   ├── ai_block.py         # AIBlock: prompt template + model dispatch
│       │   │   ├── providers.py        # LLM provider abstraction (Anthropic, OpenAI, local)
│       │   │   └── parsers.py          # Structured output parsing (JSON → DataObject)
│       │   │
│       │   ├── subworkflow/            # SubWorkflowBlock — workflow-as-block
│       │   │   ├── __init__.py
│       │   │   └── subworkflow_block.py  # SubWorkflowBlock: load child workflow,
│       │   │                             #   inject inputs, run child DAG, extract outputs
│       │   │
│       │   └── registry.py             # BlockRegistry: discovers blocks from
│       │                               #   Tier 1: {project}/blocks/ + ~/.scistudio/blocks/
│       │                               #   Tier 2: scistudio.blocks entry_points (ADR-025 callable protocol)
│       │                               #   Callable protocol: get_blocks() → (PackageInfo, [Block])
│       │                               #   or plain list[Block] for backward compat.
│       │                               #   Methods: packages(), specs_by_package() for GUI grouping.
│       │                               #   Maintains palette metadata (name, icon, category,
│       │                               #   package_name, port schemas, config JSON Schema)
│       │
│       │
│       │ ── Layer 3: Execution Engine ────────────────────────────
│       │
│       ├── engine/
│       │   ├── __init__.py
│       │   │
│       │   ├── dag.py                  # DAG construction from workflow definition
│       │   │                           #   (topological sort, dependency resolution)
│       │   │
│       │   ├── scheduler.py            # DAGScheduler: event-driven DAG execution (ADR-018)
│       │   │                           #   Subscribes to EventBus for cancel/error/done events.
│       │   │                           #   Propagates SKIPPED to unreachable downstream blocks.
│       │   │
│       │   ├── resources.py            # ResourceManager: GPU slots, CPU workers, OS memory
│       │   │                           #   monitoring via psutil (ADR-022). ResourceRequest
│       │   │                           #   dataclass (no estimated_memory_gb). can_dispatch()/
│       │   │                           #   release(). Auto-release via EventBus (ADR-018).
│       │   │
│       │   ├── runners/                # BlockRunner protocol + implementations
│       │   │   ├── __init__.py
│       │   │   ├── base.py             # BlockRunner protocol (run→RunHandle, check_status, cancel)
│       │   │   ├── local.py            # LocalRunner: isolated subprocess execution (ADR-017)
│       │   │   ├── worker.py           # Subprocess entry point: receives payload via stdin,
│       │   │   │                       #   imports block, reconstructs ViewProxy from StorageRef,
│       │   │   │                       #   calls block.run(), writes outputs, returns refs (ADR-017)
│       │   │   ├── process_handle.py   # ProcessHandle, ProcessExitInfo, ProcessRegistry,
│       │   │   │                       #   spawn_block_process() factory (ADR-019)
│       │   │   ├── process_monitor.py  # ProcessMonitor: background polling loop detecting
│       │   │   │                       #   unexpected process exits (crash, OOM, task manager kill)
│       │   │   ├── platform.py         # PlatformOps protocol + PosixOps + WindowsOps (ADR-019)
│       │   │   │                       #   Isolates: signals, process groups, Job Objects,
│       │   │   │                       #   alive checks, zombie cleanup
│       │   │   # └── ssh.py            # (future) SSHRunner
│       │   │   # └── slurm.py          # (future) SlurmRunner
│       │   │
│       │   ├── checkpoint.py           # WorkflowCheckpoint: serialise/deserialise workflow state
│       │   │                           #   (block states incl. CANCELLED/SKIPPED, skip_reasons,
│       │   │                           #    intermediate data refs, pending block)
│       │   │
│       │   └── events.py              # EventBus: publish/subscribe backbone of the runtime (ADR-018)
│       │                               #   14 event types: BLOCK_READY/RUNNING/PAUSED/DONE/ERROR/
│       │                               #   CANCELLED/SKIPPED, CANCEL_BLOCK/WORKFLOW_REQUEST,
│       │                               #   PROCESS_SPAWNED/EXITED, WORKFLOW_STARTED/COMPLETED,
│       │                               #   CHECKPOINT_SAVED. All runtime components subscribe.
│       │
│       │
│       │ ── Layer 4: AI Services ─────────────────────────────────
│       │
│       ├── ai/                         # Layer 4 — embedded coding agent (ADR-033)
│       │   ├── __init__.py
│       │   │
│       │   └── agent/                   # Subprocess-based agent runtime + MCP server
│       │       ├── __init__.py
│       │       ├── provider.py          # AgentProvider Protocol; ProviderStatus dataclass
│       │       ├── claude_code.py       # ClaudeCodeProvider — wraps `claude` CLI
│       │       ├── codex.py             # CodexProvider — wraps OpenAI `codex` CLI (Phase 4)
│       │       ├── binary_discovery.py  # Cross-platform 8-fallback search (incl. Windows registry)
│       │       ├── session.py           # AgentSession + SessionManager (cap=5 per project)
│       │       ├── stream_json.py       # NDJSON parser for `--output-format stream-json`
│       │       ├── system_prompt.py     # Three-tier prompt composition (builtin/project/local)
│       │       ├── permission.py        # PreToolUse hook bridge — strict / bypass policy
│       │       ├── transcript.py        # Write-through snapshot to {project}/.scistudio/sessions/
│       │       └── mcp/                 # In-process MCP server (~25 tools, ADR-033 D2)
│       │           ├── __init__.py
│       │           ├── server.py        # Server scaffold + stdio transport
│       │           ├── tools_workflow.py     # Category (a): list_blocks, get_block_schema,
│       │           │                          #   list_types, get_workflow, validate_workflow,
│       │           │                          #   write_workflow, run_workflow, cancel_run,
│       │           │                          #   get_run_status
│       │           ├── tools_authoring.py    # Category (b): read_block_source,
│       │           │                          #   list_block_examples, scaffold_block,
│       │           │                          #   reload_blocks, run_block_tests
│       │           ├── tools_inspection.py   # Category (c): get_block_output, inspect_data,
│       │           │                          #   preview_data, get_lineage, get_block_config,
│       │           │                          #   update_block_config, get_block_logs
│       │           └── tools_qa.py            # Category (d): search_docs, get_doc, list_data,
│       │                                      #   get_project_info
│       │
│       │   # Deprecated by ADR-033 (deleted in Phase 4):
│       │   #   generation/ synthesis/ optimization/ config.py
│       │   # — single-call LLM pipelines superseded by the agent + MCP tools.
│       │
│       │
│       │ ── Layer 5: API ─────────────────────────────────────────
│       │
│       ├── api/
│       │   ├── __init__.py
│       │   ├── app.py                  # FastAPI app factory, lifespan, CORS, middleware
│       │   │                           #   Mounts SPAStaticFiles at "/" when api/static/ exists (ADR-024)
│       │   ├── spa.py                  # SPA fallback middleware (ADR-024): subclass of StaticFiles
│       │   │                           #   that returns index.html for non-API, non-WS,
│       │   │                           #   non-real-file paths. Enables client-side routing.
│       │   ├── static/                 # Pre-built React frontend (ADR-024, build artifact)
│       │   │                           #   Created by CI: npm run build → copy to here.
│       │   │                           #   .gitignore'd. Included in wheel as package data.
│       │   │                           #   Contains: index.html, assets/
│       │   │
│       │   ├── routes/                 # REST endpoints
│       │   │   ├── __init__.py
│       │   │   ├── workflows.py        # CRUD /api/workflows, execute, pause, resume, cancel
│       │   │   │                       #   + per-block cancel endpoint (ADR-018)
│       │   │   │                       #   bump_revision / If-Match ETag flow removed by ADR-039
│       │   │   │                       #   (git SHA + working-tree dirty state replaces it)
│       │   │   ├── blocks.py           # GET /api/blocks (palette), validate-connection
│       │   │   ├── data.py             # Upload, metadata, preview /api/data
│       │   │   ├── ai.py               # WS /api/ai/chat/{chat_id}, GET /api/ai/status,
│       │   │   │                       #   POST /api/ai/permission-{check,decision} (ADR-033)
│       │   │   ├── runs.py             # GET /api/runs, /api/runs/{run_id}, /api/runs/{run_id}/methods,
│       │   │   │                       #   POST /api/runs/{run_id}/rerun (ADR-038 §3.7-3.8)
│       │   │   ├── git.py              # ~15 endpoints: commit / log / diff / restore /
│       │   │   │                       #   branches CRUD / merge / cherry-pick / stash / status
│       │   │   │                       #   (ADR-039 §3.5)
│       │   │   └── projects.py         # Project CRUD, workspace management.
│       │   │                           #   create_project / open_project auto-init git (ADR-039 §3.2)
│       │   │
│       │   ├── ws.py                   # WebSocket handler: bidirectional event routing (ADR-018)
│       │   │                           #   Inbound: cancel_block, cancel_workflow, interactive_complete
│       │   │                           #   Outbound: block_state, cancel_propagation, interactive_prompt
│       │   │
│       │   ├── sse.py                  # Server-Sent Events: log streaming from execution
│       │   │
│       │   ├── schemas.py              # Pydantic models for all API request/response shapes
│       │   │                           #   Includes CancelBlockRequest, CancelWorkflowRequest,
│       │   │                           #   CancelBlockResponse, CancelWorkflowResponse (ADR-018)
│       │   │
│       │   └── deps.py                 # FastAPI dependency injection (engine, registry, etc.)
│       │
│       │
│       │ ── Workflow Definition ───────────────────────────────────
│       │
│       ├── workflow/
│       │   ├── __init__.py
│       │   ├── definition.py           # WorkflowDefinition: nodes, edges, metadata
│       │   ├── serializer.py           # YAML ↔ WorkflowDefinition (load/save)
│       │   ├── validator.py            # Validate workflow: type compatibility, cycles,
│       │   │                           #   missing connections, port constraint pre-check
│       │   └── layout.py              # Optional node position storage for ReactFlow restore
│       │
│       │
│       │ ── Utilities ─────────────────────────────────────────────
│       │
│       ├── utils/
│       │   ├── __init__.py
│       │   ├── hashing.py             # Content hashing for lineage (xxhash on data chunks)
│       │   ├── wrapping.py            # wrap_as_dataobject(): auto-detect type from raw data
│       │   ├── broadcast.py           # broadcast_apply(): named-axis-aware broadcast of
│       │   │                           #   low-dim arrays over high-dim arrays (e.g. mask → MSI)
│       │   ├── axis_iter.py           # iterate_over_axes(source, operates_on, func):
│       │   │                           #   iterate single Array over its non-operates_on axes,
│       │   │                           #   preserving metadata, class, and axis names
│       │   │                           #   (ADR-027 D3). Sibling of broadcast_apply.
│       │   ├── constraints.py         # Port constraint helper factories:
│       │   │                           #   has_axes(*required), has_exact_axes(*axes),
│       │   │                           #   has_shape(ndim), etc. Used in InputPort(constraint=...)
│       │   └── logging.py             # Structured logging config (JSON, levels, rotation)
│       │
│       │
│       │ ── Testing Utilities ──────────────────────────────────────
│       │
│       ├── testing/                    # Block SDK test utilities (ADR-026) [implemented]
│       │   ├── __init__.py             # Re-export: from scistudio.testing.harness import BlockTestHarness
│       │   └── harness.py             # BlockTestHarness: validate_block() checks port/name/run
│       │                               #   contract, validate_package_info() checks PackageInfo,
│       │                               #   validate_entry_point_callable() checks ADR-025 format,
│       │                               #   smoke_test(inputs, params) runs block and returns outputs.
│       │                               #
│       │
│       │
│       │ ── CLI ───────────────────────────────────────────────────
│       │
│       └── cli/
│           ├── __init__.py
│           ├── main.py                 # CLI entry point:
│           │                           #   scistudio serve      — start FastAPI server (headless)
│           │                           #   scistudio gui        — start server + open browser (ADR-024)
│           │                           #   scistudio run <wf>   — run workflow headless
│           │                           #   scistudio validate   — validate workflow YAML
│           │                           #   scistudio init       — create new project workspace
│           │                           #   scistudio blocks     — list installed blocks
│           │                           #   scistudio init-block-package — scaffold a block package (ADR-026)
│           ├── _scaffold.py            # Scaffolding logic for init-block-package (ADR-026):
│           │                           #   scaffold_block_package(name, display_name, author,
│           │                           #   categories, target_dir). Reads .tpl files, substitutes
│           │                           #   placeholders, writes output. ~100 lines.
│           └── templates/              # String templates for init-block-package (ADR-026)
│               └── block_package/      # {placeholder} substitution, no Jinja2 dependency
│                   ├── pyproject.toml.tpl  # Template with entry-points, {package_name}, {author}
│                   ├── __init__.py.tpl     # PackageInfo + get_blocks() callable protocol
│                   ├── blocks.py.tpl       # Example ProcessBlock with process_item()
│                   ├── test_block.py.tpl   # Example test verifying callable protocol
│                   └── README.md.tpl       # Quick start, dev setup, publishing checklist
│
│
│ ══════════════════════════════════════════════════════════════════
│  REACT FRONTEND  (Layer 6)
│ ══════════════════════════════════════════════════════════════════
│
├── frontend/                                        # Phase 8 — planned, not yet created (ADR-023)
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   │
│   └── src/
│       ├── main.tsx                    # React entry point
│       ├── App.tsx                     # Root layout: three-column + toolbar + bottom panel (ADR-023)
│       │
│       ├── components/
│       │   ├── Toolbar.tsx             # Projects dropdown, grouped buttons, shortcuts (ADR-023-Add1)
│       │   │                           #   ADR-039: mounts BranchPicker + GitStatusBadge + Commit button
│       │   ├── ProjectDialog.tsx       # New/Open project modal dialogs (ADR-023-Add1)
│       │   ├── WelcomeScreen.tsx       # Welcome screen when no project is open (ADR-023-Add1)
│       │   ├── BlockPalette.tsx        # Left column: searchable, categorised block list
│       │   ├── BottomPanel.tsx         # Bottom panel: AI Chat / Config / Logs / Lineage
│       │   │                           #   (Jobs tab removed by ADR-038 §3.8; subsumed into Lineage)
│       │   ├── DataPreview.tsx         # Right column: type-specific data preview
│       │   ├── TabBar.tsx              # Main-area tab strip — workflow tabs + file-editor tabs
│       │   │                           #   (ADR-036 §3.10 discriminated TabState).
│       │   ├── WorkflowCanvas.tsx      # ReactFlow instance, minimap, zoom, pan (kind=workflow tabs)
│       │   ├── CodeEditor.tsx          # Monaco-backed editor for kind=file tabs (ADR-036).
│       │   │                           #   Lazy-imported; lint via POST /api/lint/python.
│       │   │                           #   ADR-039 §3.5a: registers ConflictMarkerDecoration when
│       │   │                           #   the active file is in merge-conflict state.
│       │   ├── TypedEdge.tsx           # Custom edge: color-coded by source port type
│       │   ├── Lineage/                # Run lineage UI (ADR-038 §3.8)
│       │   │   ├── LineageTab.tsx          # Two-pane layout: runs list + run detail
│       │   │   ├── RunsList.tsx            # Left pane: reverse-chrono with live-updating "running" row
│       │   │   ├── RunDetail.tsx           # Right pane: blocks, params, I/O DataObjects, actions
│       │   │   ├── BlockExecutionCard.tsx  # Expandable per-block card (params + I/O)
│       │   │   ├── MethodsExportDialog.tsx # Markdown methods preview + copy + download
│       │   │   └── RerunDialog.tsx         # Input + env validation warnings + confirm (ADR-038 §3.6)
│       │   ├── Git/                    # Source version control UI (ADR-039 §3.5, §3.5a, §3.5b)
│       │   │   ├── CommitDialog.tsx        # Modal with pre-filled message template + Commit button
│       │   │   ├── GitHistoryList.tsx      # Reverse-chrono commit list with filter dropdown
│       │   │   │                           #   (Manual milestones / All / Auto only / Agent only)
│       │   │   ├── GitDiffModal.tsx        # Wraps react-diff-viewer-continued for text diffs
│       │   │   ├── BranchPicker.tsx        # Toolbar dropdown: list / create / switch / delete / merge / cherry-pick
│       │   │   ├── GitStatusBadge.tsx      # Toolbar dirty/clean indicator
│       │   │   ├── StashApplyDialog.tsx    # Stash-on-restore prompt
│       │   │   ├── StashListPanel.tsx      # Stash drawer: list / save / apply / drop
│       │   │   ├── MergeFlow.tsx           # FF / clean / conflict path orchestrator
│       │   │   ├── ConflictResolveView.tsx # Conflicted-file list with Mark Resolved / Complete Merge / Abort
│       │   │   ├── ConflictMarkerDecoration.ts  # Monaco decoration provider for <<<<<< ====== >>>>>>
│       │   │   │                                #   regions + inline action widgets (Accept Current /
│       │   │   │                                #   Accept Incoming / Accept Both / Manual edit)
│       │   │   └── GitGraph/                # Clean-room branch graph viz (ADR-039 §3.5b)
│       │   │       ├── laneAssign.ts        # DAG lane assignment via topo iteration + recycling
│       │   │       ├── edgeRouter.ts        # Bezier connectors between commits and parents
│       │   │       ├── GraphSVG.tsx         # SVG rendering: dots, edges, labels, filter dimming
│       │   │       ├── colorPalette.ts      # Branch color rotation
│       │   │       ├── interactions.ts      # Hover preview, click→diff/checkout, virtualization
│       │   │       └── integration.ts       # gitSlice consumption, filter state, theme
│       │   │
│       │   ├── nodes/                  # Custom ReactFlow node components
│       │   │   └── BlockNode.tsx       # 3-part node: header (icon+name+run/restart),
│       │   │                           #   inline config (top 3 params by ui_priority),
│       │   │                           #   footer (state badge). Per-port type colouring.
│       │   │
│       │   └── ui/                     # shadcn/ui component library (Radix UI primitives)
│       │       ├── button.tsx          # Button with toolbar/toolbar-dark variants
│       │       ├── dropdown-menu.tsx   # Radix dropdown menu (Projects menu)
│       │       ├── resizable.tsx       # react-resizable-panels wrapper (3-column layout)
│       │       ├── separator.tsx       # Vertical/horizontal separator
│       │       ├── tabs.tsx            # Radix tabs (bottom panel tabs)
│       │       └── tooltip.tsx         # Radix tooltip (keyboard shortcut hints)
│       │
│       ├── hooks/
│       │   ├── useWebSocket.ts         # WebSocket connection + event dispatch to Zustand
│       │   ├── useSSE.ts               # SSE connection for log streaming
│       │   ├── useBlockRegistry.ts     # Fetch and cache block palette data
│       │   └── useWorkflow.ts          # Workflow CRUD operations
│       │
│       ├── store/
│       │   ├── index.ts                # Zustand store with slices
│       │   ├── projectSlice.ts         # Current project, recent projects, isProjectOpen (ADR-023-Add1)
│       │   ├── workflowSlice.ts        # Nodes, edges, workflow metadata
│       │   ├── executionSlice.ts       # Per-block state, timing, output refs (WebSocket)
│       │   ├── uiSlice.ts              # Panel widths, collapsed states, selected block, active tab
│       │   ├── previewSlice.ts         # Cached preview data keyed by StorageReference
│       │   ├── paletteSlice.ts         # Available blocks from registry, search filter
│       │   ├── chatSlice.ts            # AI chat message history
│       │   ├── lineageSlice.ts         # Run list + selected run cache (ADR-038)
│       │   └── gitSlice.ts             # Branches, current branch, log cache, filter state,
│       │                               #   mergeInProgress state (ADR-039)
│       │
│       ├── config/
│       │   └── typeColorMap.ts         # Base type → colour hex mapping for port handles/edges
│       │
│       ├── lib/
│       │   └── api.ts                  # Typed REST API client (fetch wrappers)
│       │
│       └── types/
│           ├── workflow.ts             # TypeScript types mirroring backend workflow schema
│           ├── blocks.ts               # Block metadata, port definitions, config schemas
│           └── data.ts                 # DataObject type info, preview payloads
│
│
│ ══════════════════════════════════════════════════════════════════
│  TESTS
│ ══════════════════════════════════════════════════════════════════
│
├── tests/
│   ├── conftest.py                     # Shared fixtures: sample data, temp project workspace
│   │
│   ├── architecture/                   # Structural enforcement tests (Phase 2)
│   │   ├── test_layer_deps.py          # Layer import direction: core→blocks→engine→api
│   │   ├── test_type_system.py         # DataObject hierarchy, axes, expected_slots,
│   │   │                               #   Collection is NOT DataObject (ADR-020)
│   │   ├── test_block_system.py        # Block category inheritance, run() signature
│   │   │                               #   matches dict[str, Collection] (ADR-020),
│   │   │                               #   process_item() signature (ADR-020 Addendum 5),
│   │   │                               #   Collection utilities exist on Block base class
│   │   ├── test_registries.py          # BlockSpec/TypeSpec storage, entry_points valid
│   │   └── test_placement.py           # Module docstrings, file placement conventions
│   │
│   ├── core/
│   │   ├── test_types.py              # DataObject hierarchy, TypeSignature, inheritance matching
│   │   ├── test_composite.py          # CompositeData slot access, nested composites
│   │   ├── test_storage.py            # Zarr/Arrow/filesystem read/write round-trips
│   │   ├── test_proxy.py              # ViewProxy: lazy loading, slice, iter_chunks
│   │   ├── test_lineage.py            # LineageRecord creation, SQLite store, graph queries
│   │   └── test_collection.py         # Collection construction, homogeneity, pack/unpack,
│   │                                   #   auto-flush in pack/map_items (ADR-020)
│   │
│   ├── blocks/
│   │   ├── test_ports.py              # Port type matching, constraint validation
│   │   ├── test_io_block.py           # Load/save across formats via adapters
│   │   ├── test_process_block.py      # Built-in transforms: merge, split, transform
│   │   ├── test_code_block.py         # Inline + script mode, Python/R runners
│   │   ├── test_app_block.py          # Mock external app lifecycle (launch → watch → resume)
│   │   ├── test_ai_block.py           # Mock LLM responses, structured output parsing
│   │   ├── test_subworkflow.py        # Nested workflow execution, input/output mapping
│   │   ├── test_registry.py           # Block discovery via entry_points
│   │   └── test_lazy_list.py          # LazyList iteration, indexing, len, GC (ADR-020 Addendum 4)
│   │
│   ├── engine/
│   │   ├── test_dag.py                # DAG construction, topological sort, cycle detection
│   │   ├── test_scheduler.py          # Event-driven execution, cancel propagation, SKIPPED
│   │   ├── test_resources.py          # ResourceManager acquire/release, auto-release via EventBus
│   │   ├── test_checkpoint.py         # Serialise/restore with CANCELLED/SKIPPED states
│   │   ├── test_process_handle.py     # ProcessHandle terminate/kill, platform ops (ADR-019)
│   │   ├── test_process_monitor.py    # Death detection, event emission (ADR-019)
│   │   └── test_events.py            # EventBus emit/subscribe, error isolation (ADR-018)
│   │
│   ├── ai/                            # ADR-033 agent runtime + MCP server tests
│   │   ├── test_agent_provider.py     # AgentProvider protocol, binary discovery, ProviderStatus
│   │   ├── test_claude_code.py        # ClaudeCodeProvider — subprocess spawn, stream-json parse
│   │   ├── test_session_manager.py    # SessionManager — concurrency cap, persistence
│   │   ├── test_system_prompt.py      # Three-tier composition, builtin content sanity
│   │   ├── test_permission.py         # Hook bridge — strict, bypass, ask flow
│   │   ├── test_transcript.py         # Write-through snapshot semantics
│   │   └── test_mcp_tools.py          # All ~25 MCP tools — happy path + error cases
│   │
│   ├── api/
│   │   ├── test_workflow_routes.py    # REST CRUD, execute, pause, resume
│   │   ├── test_block_routes.py       # Block listing, connection validation
│   │   ├── test_ws.py                 # WebSocket message flow, interactive block signals
│   │   ├── test_spa_fallback.py       # SPA middleware tests (ADR-024): /api not intercepted,
│   │   │                               #   unknown paths → index.html, static assets served
│   │   └���─ test_app.py               # create_app() tests: static mount conditional on dir existence
│   │
│   ├── workflow/
│   │   ├── test_serializer.py         # YAML round-trip, layout preservation
│   │   └── test_validator.py          # Type mismatch detection, dangling ports
│   │
│   ├── testing/
│   │   └── test_harness.py            # BlockTestHarness tests (ADR-026): wrap dict/ndarray/list,
│   │                                   #   validate_contract catches missing output_ports,
│   │                                   #   error propagation, work_dir cleanup
│   ��
│   ├── cli/
│   │   ├── test_cli.py                # CLI command tests: gui --help, --no-browser, default port
│   │   └── test_new_block_package.py  # Scaffolding tests (ADR-026): directory structure,
│   │                                   #   pyproject.toml entry-points, callable protocol, CLI integration
│   │
│   ��── integration/
│       ├── test_multimodal_workflow.py # Full example: LC-MS + Raman + IF + SRS pipeline
│       └── test_subworkflow_nesting.py # Recursive SubWorkflowBlock composition
│
│
│ ══════════════════════════════════════════════════════════════════
│  DOCS & CONFIG
│ ══════════════════════════════════════════════════════════════════
│
├── docs/
│   ├── getting-started.md             # Installation, first workflow, tutorial
│   ├── block-development.md           # How to write a custom block (with examples)
│   ├── type-extension.md              # How to create new DataObject subtypes
│   ├── script-integration.md          # CodeBlock inline vs script mode guide
│   ├── external-apps.md              # How to configure AppBlock for your software
│   ├── api-reference.md              # Auto-generated from FastAPI OpenAPI schema
│   │
│   ├── block-development/             # Block SDK documentation (ADR-026)
│   │   ├── quickstart.md             # 5-minute from-zero-to-running guide
│   │   ├── architecture-for-block-devs.md  # Execution model for external developers
│   │   ├── block-contract.md         # Input/output/params reference
│   │   ├── data-types.md             # Core type hierarchy, Collection, when to use each
│   │   ├── custom-types.md           # Subclassing core types, metadata persistence
│   │   ├── memory-safety.md          # Three-tier processing model
│   │   ├── collection-guide.md       # Working with Collections correctly
│   │   ├── testing.md               # BlockTestHarness API reference
│   │   ├── publishing.md            # PyPI packaging and distribution guide
│   │   └── examples/
│   │       ├── simple-transform.md   # Single block, process_item() pattern
│   │       ├── collection-processing.md  # Multi-item, map_items()/parallel_map()
│   │       ├── custom-io-block.md    # IOBlock subclass for domain-specific formats (ADR-028)
│   │       └── multi-block-package.md # Full package with categories, types, tests
│   │
│   ├── adr/
│   │   └── ADR.md                    # Architecture Decision Records (ADR-001 through ADR-026)
│   │
│   └── roadmap/
│       ├── ROADMAP_v0.1.md           # Phase 0–2: bootstrap, skeleton, architecture tests
│       └── ROADMAP_v0.2.md           # Phase 1–3: frontend bundling, entry-points, Block SDK
│
├── examples/
│   ├── workflows/
│   │   ├── raman_preprocessing.yaml   # Simple: load → denoise → baseline → export
│   │   ├── lcms_elmaven.yaml          # With AppBlock: load → ElMAVEN → R annotation
│   │   └── multimodal_fusion.yaml     # Full: LC-MS + Raman + IF + SRS (from Appendix A)
│   │
│   ├── blocks/
│   │   ├── savgol_smooth.py           # Example ProcessBlock: Savitzky-Golay smoothing
│   │   └── deseq2_analysis.R          # Example CodeBlock script mode: DESeq2 in R
│   │
│   └── types/
│       └── maldi_image.py             # Example CompositeData subtype: MALDIImage
│
└── .github/
    └── workflows/
        ├── ci.yml                     # Lint + test on PR
        └── release.yml                # Build + publish to PyPI
```

## Module dependency graph

```
                 cli/main.py
                      │
                      ▼
                  api/app.py
                 ╱    │    ╲
                ▼     ▼     ▼
          api/routes  api/ws  api/sse
                        │
                  api/spa.py ← SPA fallback (serves index.html for non-API routes)
                  api/static/ ← (build artifact, not in git)
                ╲     │     ╱
                 ▼    ▼    ▼
              engine/scheduler.py
              ╱      │       ╲
             ▼       ▼        ▼
      engine/    engine/
      resources  runners/
                     │
              ┌──────┼──────────────────┐
              ▼      ▼                  ▼
         blocks/  blocks/base/     workflow/
         registry  (Block ABC,      definition.py
              │     ports, state)    serializer.py
              │         │
              │    ┌────┼────┬────┬────┬────┐
              │    ▼    ▼    ▼    ▼    ▼    ▼
              │   io/ process/ code/ app/ ai/ subworkflow/
              │
              └──────────────┐
                             ▼
                         core/types/        ← everything depends on this
                         core/storage/
                         core/proxy.py
                         core/lineage/      ← unified 4-table SQLite (ADR-038)
                         core/versioning/   ← bundled git CLI engine (ADR-039)
```

## Key entry_points (pyproject.toml)

```toml
[project.scripts]
scistudio = "scistudio.cli.main:app"

# --- Entry-point groups (ADR-025 callable protocol, amended by ADR-028 §D4) ---
# Each entry-point value is a callable (function or class).
# The registry invokes the callable at scan time.
# For scistudio.blocks: callable returns (PackageInfo, list[type[Block]])
#   or plain list[type[Block]] for backward compat. Concrete IOBlock
#   subclasses (LoadData, SaveData, plus plugin loaders like LoadImage)
#   register through this group too — there is no longer a separate
#   `scistudio.adapters` group (ADR-028 §D4 supersedes ADR-025 §6).
# For scistudio.types: callable returns list[type[DataObject]].

[project.entry-points."scistudio.blocks"]
# Built-in blocks (these are direct class references — core package
# does not use the callable protocol for its own blocks)
load_data = "scistudio.blocks.io.loaders.load_data:LoadData"
save_data = "scistudio.blocks.io.savers.save_data:SaveData"
process_merge = "scistudio.blocks.process.builtins.merge:MergeBlock"
process_split = "scistudio.blocks.process.builtins.split:SplitBlock"
code_block = "scistudio.blocks.code:CodeBlock"
app_block = "scistudio.blocks.app:AppBlock"
ai_block = "scistudio.blocks.ai:AIBlock"
subworkflow_block = "scistudio.blocks.subworkflow:SubWorkflowBlock"

[project.entry-points."scistudio.types"]
# Built-in domain types (base types are always available, no entry_point needed)
image = "scistudio.core.types.array:Image"
spectrum = "scistudio.core.types.series:Spectrum"
peak_table = "scistudio.core.types.dataframe:PeakTable"

[project.entry-points."scistudio.runners"]
python = "scistudio.blocks.code.runners.python_runner:PythonRunner"
r = "scistudio.blocks.code.runners.r_runner:RRunner"
julia = "scistudio.blocks.code.runners.julia_runner:JuliaRunner"
```

## Example external package entry_points (ADR-025, amended by ADR-028 §D4)

```toml
# In scistudio-blocks-srs/pyproject.toml:
[project.entry-points."scistudio.blocks"]
srs = "scistudio_blocks_srs:get_blocks"          # → (PackageInfo, [Block, ...])
                                               # The returned list includes any
                                               # plugin-owned IOBlock subclasses
                                               # (e.g. LoadSRSImage / SaveSRSImage)
                                               # alongside ProcessBlocks etc.

[project.entry-points."scistudio.types"]
srs = "scistudio_blocks_srs.types:get_types"     # → [SRSImage]
```

## File count summary

| Directory | Python files | Purpose |
|---|---|---|
| `core/` | ~22 | Data types, Collection transport, storage, proxy, **unified lineage (ADR-038, 7 files)**, **versioning (ADR-039, 6 files)** |
| `blocks/` | 30 | All block categories, IO loaders/savers (ADR-028), code runners, registry, lazy_list (process_mgr.py deleted per ADR-019, lazy_list.py added per ADR-020, io/adapters/ + adapter_registry.py deleted per ADR-028 §D2/§D4) |
| `engine/` | 9 | Scheduler, resources, checkpoint (relocated to `.scistudio/pause/`), events, runners. `engine/lineage_recorder.py` moved to `core/lineage/recorder.py` per ADR-038. |
| `ai/` | ~14 | Embedded coding agent — provider/session/stream-json/permission/transcript + in-process MCP server with ~25 tools (ADR-033). Old generation/synthesis/optimization modules deleted. |
| `api/` | 12 | FastAPI routes incl. **runs.py (ADR-038)** + **git.py (ADR-039)**, WebSocket, SSE, SPA fallback (ADR-024). `bump_revision` / `If-Match` ETag flow removed per ADR-039 (replaced by git SHA + working-tree dirty state). |
| `workflow/` | 4 | Definition, serialization, validation, layout |
| `utils/` | 3 | Hashing, wrapping, logging |
| `testing/` | 2 | BlockTestHarness for external block developers (ADR-026) |
| `cli/` | 3+5tpl | CLI entry point (incl. git-init parity on `scistudio init` per ADR-039), scaffolding, templates |
| **Total backend** | **~99** | |
| `frontend/src/` | ~55 `.tsx/.ts` | React components incl. **Lineage/ (6 files, ADR-038)** + **Git/ + Git/GitGraph/ (~15 files, ADR-039)**, hooks, stores incl. lineageSlice + gitSlice, API client. |
| `docs/block-development/` | 13 `.md` | Block SDK developer documentation (ADR-026) |
| `desktop/scripts/` | 2 + electron-builder config | **fetch-git-portable.ps1 (Windows MinGit) + .sh (mac/Linux static)** per ADR-039 + ADR-037 |
| `tests/` | ~50 | Architecture enforcement, unit, integration, harness, CLI tests, incl. **lineage 4-table schema tests** + **git engine subprocess tests** |

**Removed by ADR-038/039 (2026-05-15):**
- `src/scistudio/core/metadata_store.py` → 6-month deprecation shim re-exporting unified store + `DeprecationWarning` (function lives in `core/lineage/`)
- `src/scistudio/engine/lineage_recorder.py` → moved to `core/lineage/recorder.py`
- `ApiRuntime.bump_revision` / `current_revision` + workflow routes' `If-Match` handling
- Top-level `<project>/metadata.db` and `<project>/checkpoints/` (replaced by `<project>/.scistudio/lineage.db` and `<project>/.scistudio/pause/`)
- Frontend Jobs tab (subsumed by Lineage tab; `"jobs"` removed from `BottomTab` discriminated union)
