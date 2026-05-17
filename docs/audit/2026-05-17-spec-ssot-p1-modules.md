# S1-enumerate — Phase 1 module taxonomy report

Date: 2026-05-17
Auditor: S1-enumerate
Baseline SHA: a4b8b5f (post-ADR-040)
Umbrella issue: #1090

---

## Summary

- N = 13
- N halving rule: N > 8, so Phase 1.5 = ceil(13/2) = **7 code agents** (some owning 2 modules) + 1 docs agent + 1 xcheck agent
- All 13 modules derive from a combination of ARCHITECTURE.md §§3–12, actual code at `src/scieasy/**`, and `frontend/src/types/**`.
- 3 modules are assessed as likely **d-class** (code exists without matching doc section): `versioning-git`, `agent-provisioning`, `code-runners`.

---

## Module taxonomy

| # | Module ID (kebab-case) | Surface description (1 sentence) | Code root(s) | Estimated # interfaces | Surface kinds |
|---|---|---|---|---|---|
| 1 | block-abc | Abstract base classes and 8-state machine for all block categories (Block, ProcessBlock, IOBlock, CodeBlock, AppBlock, AIBlock, SubWorkflowBlock) plus the variadic port contract | `src/scieasy/blocks/base/`, `src/scieasy/blocks/process/process_block.py`, `src/scieasy/blocks/io/io_block.py`, `src/scieasy/blocks/code/code_block.py`, `src/scieasy/blocks/app/app_block.py`, `src/scieasy/blocks/ai/ai_block.py`, `src/scieasy/blocks/subworkflow/subworkflow_block.py` | ~20 | ABC, Protocol |
| 2 | port-system | InputPort / OutputPort / constraint callable / dynamic-port descriptor (ADR-028 Addendum 1) and the two-phase connection validation contract | `src/scieasy/blocks/base/ports.py`, `src/scieasy/blocks/base/result.py`, `src/scieasy/utils/constraints.py` | ~8 | dataclass, Pydantic, Protocol |
| 3 | data-types | Core DataObject hierarchy (7 primitives: DataObject, Array, Series, DataFrame, Text, Artifact, CompositeData), TypeSignature, named-axis schema, and lazy data-access methods | `src/scieasy/core/types/` | ~14 | ABC, dataclass, Pydantic |
| 4 | storage-backends | StorageBackend protocol plus Zarr, Arrow/Parquet, filesystem, and composite-directory backends; StorageReference wire format | `src/scieasy/core/storage/` | ~10 | Protocol, Pydantic, FileFormat |
| 5 | collection-transport | Collection wrapper (homogeneous DataObject transport unit), LazyList, auto-flush mechanism, block pack/unpack utilities | `src/scieasy/core/types/collection.py`, `src/scieasy/blocks/code/lazy_list.py`, `src/scieasy/core/storage/flush_context.py` | ~7 | dataclass, Protocol |
| 6 | block-registry | BlockRegistry + TypeRegistry discovery (Tier 1 drop-in scan + Tier 2 entry-point callable protocol), PackageInfo, BlockSpec, `scieasy.blocks` / `scieasy.types` / `scieasy.runners` entry-point groups | `src/scieasy/blocks/registry.py`, `src/scieasy/core/types/registry.py`, `src/scieasy/core/types/serialization.py`, `pyproject.toml` (entry-point declarations) | ~12 | EntryPoint, Pydantic, Protocol |
| 7 | execution-engine | DAGScheduler, EventBus, ResourceManager, ProcessHandle / ProcessRegistry / ProcessMonitor, BlockRunner protocol, LocalRunner, worker stdout envelope, checkpoint format | `src/scieasy/engine/` | ~18 | Protocol, Pydantic, FileFormat |
| 8 | lineage-db | Unified run lineage SQLite schema (4 tables: runs, block_executions, data_objects, block_io), LineageRecorder write-flow, EnvironmentSnapshot, methods-export | `src/scieasy/core/lineage/`, `src/scieasy/engine/lineage_recorder.py` | ~10 | Pydantic, FileFormat |
| 9 | rest-api | FastAPI REST routes (`/api/workflows`, `/api/blocks`, `/api/data`, `/api/projects`, `/api/runs`, `/api/git`, `/api/lint`, `/api/ai`, filesystem browsing), Pydantic request/response schemas, SPA serving | `src/scieasy/api/routes/`, `src/scieasy/api/schemas.py`, `src/scieasy/api/app.py`, `src/scieasy/api/spa.py`, `src/scieasy/api/runtime.py` | ~30 | FastAPI, Pydantic, FE-BE |
| 10 | ws-sse-protocol | WebSocket message protocol (block state push, interactive_prompt, cancel_block/workflow, cancel_propagation, git events, AI chat streaming) and SSE log-stream contract | `src/scieasy/api/ws.py`, `src/scieasy/api/sse.py`, `src/scieasy/engine/events.py` | ~12 | WS, Pydantic, FE-BE |
| 11 | mcp-tools | FastMCP server (~25 tools across 4 categories: workflow design/execution, block authoring, result inspection, project Q&A), tool input/output schemas, MCP bridge transport contract (Unix socket / TCP), `mcp.json` wire format | `src/scieasy/ai/agent/mcp/`, `src/scieasy/cli/mcp_bridge.py` | ~28 | MCP, Pydantic, FileFormat |
| 12 | versioning-git | Bundled-git engine (subprocess wrapper around portable git CLI), GitEngine public API (commit, log, status, diff, branches, stash, merge, cherry-pick, restore), `git_author.json` and `.gitignore` template, AI agent commit-prefix convention | `src/scieasy/core/versioning/` | ~15 | Protocol, Pydantic, Convention |
| 13 | agent-provisioning | Idempotent project provisioning of prod-env agent reliability files (CLAUDE.md/AGENTS.md template, `.claude/settings.json` hook matchers, 6 hook scripts, 6 skills, `.codex/config.toml`), version-marker format, hook stdin protocol | `src/scieasy/agent_provisioning/`, `src/scieasy/_skills/scieasy/` | ~10 | Pydantic, FileFormat, Convention, EntryPoint |

---

## Notes & boundary calls

### 1. block-abc vs port-system (modules 1 and 2)
The port system (`InputPort`, `OutputPort`, constraint callables, dynamic-port descriptors) is used by ALL block categories but is not itself a block — it has a distinct lifecycle (design-time + pre-execution) vs the block state machine (runtime). Splitting them avoids one very large module and lets Phase 1.5 agents focus; the cross-reference is one-directional (blocks import ports, ports do not import blocks).

### 2. data-types vs storage-backends vs collection-transport (modules 3, 4, 5)
Three distinct contracts at Layer 1. `data-types` owns the class hierarchy and lazy-access method signatures. `storage-backends` owns the backend-specific implementations and StorageReference. `collection-transport` owns the transport wrapper that crosses block boundaries (Collection, LazyList, auto-flush). They are separated because:
- plugins that define new DataObject subclasses only touch module 3
- plugins that define new storage backends only touch module 4
- the engine/scheduler touches module 5 (Collection as its unit of transport) but does not touch storage-backends directly

### 3. block-registry (module 6) is independent of the block ABCs (module 1)
The registry is discovery infrastructure (scan, entry-points, BlockSpec, PackageInfo). The ABCs define the contract a block must satisfy. Phase 1.5 agents can audit both surfaces without conflating them. Note: `pyproject.toml` is listed as a code root because it declares the entry-point groups — this is the canonical source of truth for which groups exist and which callables they point to.

### 4. execution-engine (module 7) boundary
Module 7 covers everything the scheduler does: DAG execution, EventBus, resource gating, process lifecycle, checkpoint format, BlockRunner protocol. The lineage recorder (`src/scieasy/engine/lineage_recorder.py`) is an engine-internal subscriber but its write-contract (the SQL schema) belongs to module 8 (`lineage-db`). The engine module keeps `lineage_recorder.py` for the wiring, but module 8 owns its interface inventory.

### 5. rest-api vs ws-sse-protocol (modules 9 and 10)
Both live under `src/scieasy/api/` but have different surface kinds:
- REST routes are request/response pairs with Pydantic models → inventory of ~30 REST endpoints + their wire shapes
- WebSocket / SSE are stream protocols with JSON message envelopes → inventory of ~12 message types

Splitting them gives Phase 1.5 agents a cleaner per-file assignment (REST agent reads `routes/*.py` + `schemas.py`; WS/SSE agent reads `ws.py` + `sse.py` + `events.py`). Both agents will see the FE-BE boundary since `frontend/src/types/api.ts` and `frontend/src/types/lineage.ts` mirror both surfaces.

### 6. mcp-tools (module 11) is separated from rest-api (module 9)
The MCP server is a distinct protocol (JSON-RPC over domain socket or TCP loopback, not HTTP), exposes a different set of operations (agent-semantic vs user-UI-semantic), and runs partially in-process with FastAPI but partially as a standalone bridge subprocess. Merging it with rest-api would conflate two audiences (AI agents vs browser frontend) and two transports.

### 7. versioning-git (module 12) is likely d-class
ARCHITECTURE.md §4.6 documents the bundled-git design decision, but the concrete API surface of `GitEngine` (method signatures, return shapes) is described only in `frontend/src/types/api.ts` wire-shape comments and inline docstrings in `src/scieasy/core/versioning/git_engine.py`. ARCHITECTURE.md does not enumerate the public method list. Phase 1.5 should flag this as a candidate for a new `docs/specs/git-engine-interface.md` section.

### 8. agent-provisioning (module 13) is partly d-class
The general behavior is documented in ARCHITECTURE.md §10.2 and `docs/agent-provisioning.md`. However, the specific interface contracts (hook stdin JSON schema, `mcp.json` format, `.claude/settings.json` hook-matcher schema, skill SKILL.md structure, `.scieasy-provision-version` marker format, `ProvisionResult` API) are documented only in code-level docstrings and inline comments in `src/scieasy/agent_provisioning/`. No doc-spec enumerates all these sub-contracts.

### 9. code-runners (merged into block-abc)
`src/scieasy/blocks/code/runners/` defines a `CodeRunner` Protocol (base.py) with implementations for Python, R, and Julia. This is a small sub-surface (~5 interfaces). Rather than a standalone module, it is most naturally an interface cluster within block-abc (the CodeBlock's execution delegation point). Phase 1.5 agents auditing block-abc should cover it. The `scieasy.runners` entry-point group in `pyproject.toml` is listed under block-registry (module 6) since all three entry-point groups have the same discovery pattern.

### 10. frontend types (FE-BE boundary)
`frontend/src/types/api.ts`, `frontend/src/types/lineage.ts`, and `frontend/src/types/ui.ts` are treated as part of modules 9 and 10 (they mirror the REST + WS + lineage surfaces). They are NOT a standalone module because they are derivative of the backend contracts — a Phase 1.5 code agent auditing `rest-api` or `ws-sse-protocol` should cross-check the FE types for drift. Listing them under module 9/10 is the correct framing.

### 11. CLI surface (merged into rest-api module)
`src/scieasy/cli/main.py` exposes CLI commands (`scieasy gui`, `scieasy serve`, `scieasy validate`, `scieasy run`, `scieasy install`, `scieasy mcp-bridge`, `scieasy init-block-package`). These are a Typer-based CLI surface. Given that the CLI mostly wraps the same semantics as REST endpoints (and the `mcp-bridge` sub-command belongs more naturally to module 11), the CLI surface is small enough to fold into `rest-api` rather than stand alone. Phase 1.5 can decide whether the CLI warrants its own INTERFACE_SPEC section.

### 12. utils sub-modules (excluded — internal helpers)
`src/scieasy/utils/` (axis_iter, broadcast, constraints, hashing, logging, wrapping) are **utility functions** used internally by blocks and the engine. They do not define ABCs, Protocols, REST endpoints, or entry-points. `constraints.py` is notable — `has_axes()` and friends form a mini-DSL used in port declarations — but it is most naturally documented as part of the port-system module (module 2) rather than a standalone surface.

---

## Recommended Phase 1.5 module pairing (halving rule)

N = 13 → ceil(13/2) = 7 code agents. Recommended pairings for 6 agents (one agent per pair + one solo):

| Pair | Modules | Why structurally similar |
|---|---|---|
| C1 | `block-abc` + `port-system` | Both live under `src/scieasy/blocks/base/`; port declarations are declared on block classes; same audit domain (block contract) |
| C2 | `data-types` + `storage-backends` | Both live under `src/scieasy/core/`; DataObject.storage_ref references StorageReference which lives in storage-backends; tightly coupled contracts |
| C3 | `collection-transport` + `block-registry` | Both are horizontal concerns used by all block categories; neither belongs to a single block class; code roots are small (<5 files each) |
| C4 | `execution-engine` (solo) | Largest module (~18 interfaces, 14 files under `src/scieasy/engine/`); deserves a dedicated agent to avoid depth-of-context overrun |
| C5 | `lineage-db` + `versioning-git` | Both are persistence/history subsystems at Layer 1; both define SQLite/file schemas; both involve time-ordered records |
| C6 | `rest-api` + `ws-sse-protocol` | Both live under `src/scieasy/api/`; FE-BE boundary types in `frontend/src/types/` cross both; same audit context (API layer) |
| C7 | `mcp-tools` + `agent-provisioning` | Both are agent-facing surfaces (ADR-033 + ADR-040); both define file-format contracts (mcp.json, settings.json, hook stdin, provision version); same conceptual domain (AI agent integration) |

---

## Gaps + caveats

1. **`workflow.yaml` Pydantic schema**: ARCHITECTURE.md §10.1 shows the workflow YAML format, but `src/scieasy/workflow/` is referenced in CLI code (`from scieasy.workflow.serializer import load_yaml`, `from scieasy.workflow.validator import validate_workflow`) yet the directory does not appear in the glob results. These modules raise `NotImplementedError`. The workflow YAML schema contract (nodes, edges, config nesting, execution_mode) is described in ARCHITECTURE.md but has no Pydantic model in core at baseline SHA. This is either a d-class gap (code stub without implemented spec) or an orphan reference. Phase 1.5 C6 agent should check `src/scieasy/api/schemas.py` `WorkflowCreate` / `WorkflowResponse` and `src/scieasy/api/routes/workflows.py` for the currently-live schema, since those ARE implemented.

2. **`project.yaml` format**: ARCHITECTURE.md §10 mentions `project.yaml` as git-tracked project metadata, but no Pydantic model or spec for its fields was found in the code scan. This is a candidate d-class surface — used by `ApiRuntime` but not formally specified.

3. **`scieasy.runners` entry-point group**: Declared in `pyproject.toml` and implemented (3 runners registered). ARCHITECTURE.md §12 mentions it in the extension-points table but gives no formal API contract for the CodeRunner Protocol. Module 3 (block-abc) or module 6 (block-registry) should pick this up.

4. **AIBlock run-dir protocol**: `src/scieasy/blocks/ai/run_dir.py` defines a file-exchange protocol for AIBlock (the workflow-graph LLM node). ARCHITECTURE.md §7.6 mentions AIBlock is preserved but gives no contract for its run-dir layout. This is a d-class sub-surface within block-abc (module 1).

5. **`src/scieasy/engine/pty_control.py`**: Defines the AIBlock → engine IPC surface (PTY tab allocation). Referenced in pyproject.toml import-linter exceptions. ARCHITECTURE.md §7.1 covers PTY only for the embedded coding agent (ADR-034). This module's protocol is documented only in code docstrings — d-class candidate.

6. **`src/scieasy/core/metadata_store.py`**: Present in code but described only as superseded by the unified `lineage.db` (ADR-038). May be a migration stub or legacy compatibility shim. Should be flagged by Phase 1.5 lineage-db agent.

7. **`src/scieasy/blocks/process/builtins/`**: Contains 8 built-in ProcessBlock implementations (MergeCollection, SplitCollection, FilterCollection, SliceCollection, MergeBlock, SplitBlock, DataRouter, PairEditor, ExpressionEvaluator). These are concrete blocks, not ABCs, so they do not themselves define new interface surfaces — they implement the ProcessBlock contract from module 1. Not listed as a module; Phase 1.5 block-abc agent should note them as part of the "what ships in core" inventory.

8. **`src/scieasy/blocks/_templates/block_base_template.py`**: A code template (not an ABC). Part of the Block SDK / `scieasy init-block-package` scaffolding. Belongs to block-registry context (module 6 `block-registry` covers the SDK surface).

9. **`frontend/src/types/ui.ts`**: Defines `BottomTab`, `BlockNodeData`, `BlockCanvasNode`, `AnnotationNodeData`, `GroupNodeData`. These are frontend-only UI types and do not mirror backend contracts — excluded from FE-BE boundary. Not listed as a module; internal to the frontend.

---

## Anti-recommendations

Items intentionally excluded from the module list and why:

- **`packages/scieasy-blocks-*/`**: Out of scope per dispatch constraints. Plugin packages are consumers of the interfaces defined in modules 1–13; they do not define new core contracts.
- **`docs/specs/phase*`, `docs/specs/appblock-variadic-ports.md`**, etc.: Out of scope per dispatch constraints. Legacy specs may contradict current code; Phase 2+ will reconcile.
- **`docs/adr/*.md`**: Out of scope per dispatch constraints. ADRs are noisy and some are superseded; ARCHITECTURE.md is the primary authority for Phase 1.
- **`docs/audit/`**: Peer audit reports; out of scope to avoid cross-contamination.
- **`tests/` tree**: Test infrastructure is not an interface surface. `scieasy.testing` (BlockTestHarness) is part of the Block SDK — its public surface is captured under block-registry (module 6).
- **`src/scieasy/utils/`**: Internal utility functions (`axis_iter`, `broadcast`, `constraints`, `hashing`, `logging`, `wrapping`). No ABCs, no entry-points, no REST endpoints. `constraints.py` is referenced by port declarations and is documented as part of port-system (module 2).
- **`src/scieasy/core/meta/`**: Internal helpers for typed metadata construction (`_with_meta`, `channel`, `framework`). These are implementation details of `DataObject.meta` and `FrameworkMeta` — covered under data-types (module 3), not standalone.
- **`src/scieasy/core/units.py`**: `PhysicalQuantity` is a helper for typed metadata; used in DataObject subclass Meta declarations. Not a standalone interface module — internal to data-types (module 3).
- **`frontend/src/types/ui.ts`**: Frontend-internal UI types. No backend contract mirrored. Not a FE-BE boundary surface.
- **`.github/`**: CI history; out of scope per dispatch constraints.
