# SciStudio

**AI-native, inclusive workflow runtime for multimodal scientific data.**

[![CI](https://github.com/zjzcpj/SciStudio/actions/workflows/ci.yml/badge.svg)](https://github.com/zjzcpj/SciStudio/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Development Status](https://img.shields.io/badge/status-pre--alpha-orange.svg)]()

---

## What is SciStudio?

Modern biomedical research generates multi-modal datasets -- RNA/DNA sequencing, LC-MS metabolomics, spatial transcriptomics, immunofluorescence microscopy, SRS imaging, mass spectrometry imaging, and more. Each modality demands its own processing software, programming language, and data format. Researchers face two compounding problems:

1. **Fragmented processing**: tools are scattered across R scripts, Python notebooks, standalone GUI applications (ElMAVEN, Fiji, napari), and command-line pipelines. Exchanging intermediate results is manual, error-prone, and poorly documented.
2. **High barrier for non-developers**: researchers without strong programming backgrounds cannot efficiently chain together complex multi-step analyses, let alone integrate data across modalities.

SciStudio is a **modality-agnostic, building-block workflow framework** where:

- Every processing step is encapsulated as a **Block** with standardized inputs and outputs.
- All data flows through a small set of **base data types** that are extensible via inheritance.
- Users compose workflows visually by wiring blocks together on a canvas -- no code required for standard pipelines.
- Existing tools are **included, not replaced**: users can embed R/Python scripts, launch GUI applications, or call CLI tools as blocks within the same workflow.
- Multiple data modalities coexist in a **single workflow graph**, enabling true cross-modal fusion analysis.
- The framework is **AI-native**: AI can generate blocks, synthesize workflows, and optimize parameters at runtime.

> **Status**: SciStudio is in **pre-alpha** (v0.3.2a0). The core runtime, block system, execution engine, API layer, and frontend workflow editor are implemented and under active development. See [Current Status](#current-status) for details.

---

## Key Features

### Type-Safe Data Model

Six base data types -- `Array`, `Series`, `DataFrame`, `Text`, `Artifact`, and `CompositeData` -- cover the full spectrum of scientific data. Domain-specific types (e.g., `Image`, `Spectrum`, `PeakTable`, `AnnData`, `SpatialData`) extend these bases. Port-level type checking prevents invalid connections at design time.

### Lazy by Default

Data objects hold references, not payloads. A 100 GB dataset stays on disk (Zarr, Parquet, or filesystem) until a block requests a specific slice. Lazy loading is built into `DataObject` and `Array` directly — there is no separate accessor class (ADR-031). Memory usage stays bounded even for enormous datasets.

### Six Block Categories + Composition

| Category | Purpose |
|----------|---------|
| **IOBlock** | Load and save data in any format (mzXML, TIFF, CSV, h5ad, Zarr, etc.) |
| **ProcessBlock** | Deterministic data transformations (denoise, segment, merge, filter) |
| **CodeBlock** | Run user-provided Python, R, or Julia scripts |
| **AppBlock** | Bridge external GUI software (ElMAVEN, Fiji, napari, MestReNova) via file exchange |
| **AIBlock** | LLM-powered classification, summarization, and parameter suggestion |
| **SubWorkflowBlock** | Encapsulate an entire workflow as a single reusable block |

### Manual Steps Are First-Class

Human review, annotation, and approval are part of the formal workflow model -- not hacks. AppBlock pauses the workflow while the user operates external software, then automatically resumes when output files appear.

### Subprocess Isolation

All blocks execute in isolated subprocesses. The engine process is a pure orchestrator that never executes block logic directly. This provides reliable cancellation (OS-level process signals), crash isolation (a segfault in one block does not affect others), and hang protection.

### Event-Driven Execution Engine

The DAG scheduler reacts to block completion, errors, cancellation, and process death events via an `EventBus`. Features include parallel execution of independent branches, cancellation with automatic skip propagation to downstream blocks, pause/resume with checkpoint persistence, and resource-aware dispatch gating (GPU slots, CPU cores, OS memory monitoring via psutil).

### Community-Extensible Plugin System

- **Tier 1 (drop-in)**: place a `.py` file in `{project}/blocks/` or `~/.scistudio/blocks/` -- it appears in the palette immediately.
- **Tier 2 (pip install)**: publish a block package to PyPI with `scistudio.blocks` entry-points. Users install with `pip install scistudio-yourpackage` and blocks register automatically.
- **Block SDK**: `scistudio init-block-package` scaffolds a complete package; `BlockTestHarness` simplifies testing.

### Visual Workflow Editor

A React + ReactFlow frontend provides a drag-and-drop canvas for composing workflows, with real-time execution state updates via WebSocket, inline block configuration, type-colored port handles, and data preview panels.

---

## Architecture Overview

SciStudio is organized into six horizontal layers, each depending only on the layers below it:

```
+-------------------------------------------------------------+
|  Layer 6: Frontend                                          |
|  ReactFlow canvas, block palette, monitoring dashboard      |
+-------------------------------------------------------------+
|  Layer 5: API + SPA Serving                                 |
|  FastAPI REST, WebSocket, SSE, SPA fallback middleware      |
+-------------------------------------------------------------+
|  Layer 4: AI Services                                       |
|  Embedded coding agent, MCP server, AI block runtime       |
+-------------------------------------------------------------+
|  Layer 3: Execution Engine                                  |
|  DAG scheduler, process lifecycle, resource management      |
+-------------------------------------------------------------+
|  Layer 2: Block System                                      |
|  Port typing, block registry, state machine, runners        |
+-------------------------------------------------------------+
|  Layer 1: Data Foundation                                   |
|  Type hierarchy, storage backends, lazy loading, lineage    |
+-------------------------------------------------------------+
|  Plugin Ecosystem (cross-cutting)                           |
|  Entry-points protocol, Block SDK, community blocks         |
+-------------------------------------------------------------+
```

**Workflow graph is the source of truth.** The graph definition, runtime state, block contracts, lineage, and execution semantics belong to the backend/runtime layer. The frontend is an editor and viewer, not the source of truth.

**Data flows as references, not large in-memory payloads.** Objects passed between blocks are typed object references backed by storage (Zarr for arrays, Parquet for tables, filesystem for files). The `Collection` transport wrapper carries batches of items between blocks without the engine ever unpacking or inspecting the contents.

For the full architecture document, see [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md).

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Web framework | FastAPI (REST + WebSocket + SSE) |
| Data validation | Pydantic v2 |
| Array storage | Zarr v3 (chunked, compressed) |
| Tabular storage | Apache Arrow / Parquet |
| Metadata DB | SQLite (lineage records, project metadata) |
| Process lifecycle | Cross-platform: POSIX signals + process groups, Windows Job Objects |
| System monitoring | psutil (OS memory for dispatch gating) |
| Frontend framework | React 18 + TypeScript |
| Workflow canvas | ReactFlow (`@xyflow/react`) |
| State management | Zustand |
| UI toolkit | shadcn/ui + Tailwind CSS |
| Data visualization | Plotly.js (inline previews) |
| Build tool | Vite |
| AI integration | Anthropic / OpenAI API |
| Package format | PyPI with `scistudio.*` entry-points |

---

## Quick Start

### Prerequisites

- Python 3.11 or later
- Node.js 18+ (only for frontend development; not needed for `pip install`)

### Installation

**End users** — one command from PyPI:

```bash
pip install scistudio
scistudio gui
```

The wheel ships with the prebuilt React SPA, so `scistudio gui` opens the full
workflow editor directly. No Node.js required at install time.

**Developers** — clone and run from source in an isolated environment:

```powershell
git clone https://github.com/zjzcpj/SciStudio.git
cd SciStudio
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
python -m pip install -U pip
python -m pip install ".[dev]"
Push-Location frontend; npm install; npm run build; Pop-Location   # one-time SPA build
$env:PYTHONPATH = "src"
python -m scistudio.cli.main gui
```

The dev path serves the SPA from `frontend/dist/` automatically, so you can
iterate on Python + SPA without an editable install. For hot-reload frontend dev,
run `npm run dev` from `frontend/` against a separate
`python -m scistudio.cli.main serve` process with `PYTHONPATH=src` set.
backend — Vite proxies `/api/*` to `http://localhost:8000`.

> If `scistudio gui` lands on the FastAPI `/docs` page instead of the workflow
> editor, the SPA bundle is missing. Run `(cd frontend && npm run build)` in
> your dev checkout, or reinstall from a wheel that includes `scistudio/api/static/index.html`.

### Launch the GUI

```bash
scistudio gui
```

This starts the FastAPI backend and opens the workflow editor in your default browser at `http://localhost:8000`.

### CLI Commands

```bash
scistudio --help          # Show all available commands
scistudio init            # Initialize a new project workspace
scistudio validate FILE   # Validate a workflow YAML file
scistudio run FILE        # Execute a workflow from a YAML file
scistudio blocks          # List all registered blocks
scistudio serve           # Start API server (headless, no browser)
scistudio gui             # Start API server and open browser
```

---

## Project Structure

```
SciStudio/
├── src/scistudio/                    # Python backend (pip-installable)
│   ├── core/                       # Layer 1: Data foundation
│   │   ├── types/                  #   DataObject hierarchy + TypeRegistry
│   │   ├── storage/                #   Zarr, Arrow/Parquet, filesystem backends
│   │   └── lineage/                #   Provenance tracking (SQLite)
│   ├── blocks/                     # Layer 2: Block system
│   │   ├── base/                   #   Block ABC, ports, state machine, config
│   │   ├── io/                     #   IOBlock + format adapters
│   │   ├── process/                #   ProcessBlock + built-in operations
│   │   ├── code/                   #   CodeBlock + language runners
│   │   ├── app/                    #   AppBlock + file exchange bridge
│   │   ├── ai/                     #   AIBlock
│   │   └── subworkflow/            #   SubWorkflowBlock
│   ├── engine/                     # Layer 3: Execution engine
│   │   ├── dag.py                  #   DAG construction + topological sort
│   │   ├── scheduler.py            #   Event-driven DAG scheduler
│   │   ├── events.py               #   EventBus pub/sub
│   │   ├── resources.py            #   ResourceManager (GPU/CPU/memory)
│   │   ├── checkpoint.py           #   Checkpoint save/load/resume
│   │   └── runners/                #   LocalRunner, ProcessHandle, worker.py
│   ├── ai/                         # Layer 4: AI services
│   │   └── agent/                  #   Embedded coding agent + MCP server
│   ├── api/                        # Layer 5: FastAPI backend
│   │   ├── app.py                  #   App factory + SPA static file serving
│   │   ├── routes/                 #   REST endpoints (workflows, blocks, data, projects)
│   │   └── ws.py                   #   WebSocket handler
│   ├── workflow/                   # Workflow definition + YAML serialization
│   ├── cli/                        # Typer CLI (scistudio command)
│   └── utils/                      # Hashing, broadcast, wrapping utilities
├── frontend/                       # Layer 6: React + TypeScript frontend
│   ├── src/
│   │   ├── components/             #   React components (canvas, palette, panels)
│   │   ├── stores/                 #   Zustand state management
│   │   └── config/                 #   Type color map, constants
│   └── package.json
├── tests/                          # Test suite (pytest)
│   ├── architecture/               #   Structural / layer dependency tests
│   ├── core/                       #   Data layer tests
│   ├── blocks/                     #   Block system tests
│   ├── engine/                     #   Execution engine tests
│   └── integration/                #   End-to-end integration tests
├── docs/                           # Documentation
│   ├── architecture/               #   ARCHITECTURE.md, PROJECT_TREE.md
│   ├── adr/                        #   Architecture Decision Records
│   └── roadmap/                    #   Phased development roadmap
├── .github/                        # CI/CD workflows, issue/PR templates
├── CLAUDE.md                       # Project governance and AI assistant rules
├── CHANGELOG.md                    # Keep-a-Changelog format
└── pyproject.toml                  # Package metadata, dependencies, tool config
```

---

## Project Workspace

When you create a project in SciStudio, it generates a self-contained directory:

```
my_project/
├── project.yaml              # Project metadata and settings
├── workflows/                # Workflow DAG definitions (YAML)
├── data/
│   ├── raw/                  # Original uploaded files (read-only after import)
│   ├── zarr/                 # Zarr stores for Array-type data
│   ├── parquet/              # Parquet files for DataFrame-type data
│   ├── artifacts/            # PDFs, reports, images, other files
│   └── exchange/             # File handoff area for AppBlock / CodeBlock
├── blocks/                   # Project-local custom blocks (drop-in .py files)
├── types/                    # Project-local custom data types (drop-in .py files)
├── .scistudio/               # Per-project runtime state (gitignored by default)
│                             #   lineage.db, pause/, mcp.sock, session markers
└── logs/                     # Execution logs
```

---

## Writing Custom Blocks

### Drop-in Block (Tier 1)

Save a `.py` file in your project's `blocks/` directory:

```python
import numpy as np

from scistudio.blocks.base import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.array import Array

class RamanDenoise(ProcessBlock):
    name = "Raman denoise"
    description = "Savitzky-Golay smoothing for Raman spectra"
    version = "0.1.0"
    subcategory = "spectroscopy"

    input_ports = [InputPort(name="spectrum", accepted_types=[Array])]
    output_ports = [OutputPort(name="smoothed", accepted_types=[Array])]

    def process_item(self, item, config, state=None):
        from scipy.signal import savgol_filter
        data = np.asarray(item.to_memory())
        smoothed = savgol_filter(
            data, config.get("window", 11), config.get("order", 3)
        )
        return Array(
            axes=list(item.axes),
            shape=smoothed.shape,
            dtype=str(smoothed.dtype),
            data=smoothed,
        )
```

See the [generated API reference](docs/user/reference/index.md) for the public
block-authoring surface (stability tier + `Since` per symbol, ADR-052). The
hand-written developer guides are being rewritten (#1825); the generated
reference and `docs/specs/adr-052-public-api-surface.md` are the authoritative
contract.

Click "Reload Blocks" in the GUI and it appears in the palette.

### Publishable Package (Tier 2)

For community distribution:

```bash
scistudio init-block-package scistudio-blocks-mylab
```

This scaffolds a complete package with entry-points, example blocks, tests using `BlockTestHarness`, and a README. Publish to PyPI and users install with `pip install scistudio-blocks-mylab`.

---

## Development Setup

### Backend

```bash
# Install dev dependencies in an isolated environment.
# AI-authored repository work must use the gate workflow in AGENTS.md instead
# of installing editable packages into a shared environment.
python -m pip install ".[dev]"

# Run the repository-owned local gate.
PYTHONPATH=src python -m scistudio.qa.governance.gate_record check --mode local

# During development, targeted tests are still useful before the full gate.
PYTHONPATH=src pytest <targeted-tests-or-test-directory>
```

### Frontend

```bash
cd frontend
npm install
npm run dev     # Vite dev server with HMR (proxies /api to backend)
```

### Pre-commit Hooks

```bash
pre-commit install
```

### CI

The GitHub Actions CI pipeline runs on every PR:
- Ruff lint + format check
- mypy type checking
- pytest with coverage enforcement (70% minimum, enforced on the Python 3.13 CI leg only)
- Import contract verification (layer dependency rules)

---

## Developer integrations

Drive SciStudio projects from your own terminal CLI (`claude` or `codex`),
outside the SciStudio GUI, with the full 27-tool MCP surface and a
SciStudio-aware skill installed:

```bash
pip install scistudio
scistudio install --all          # wires claude + codex + skill at user scope
cd ~/work/my-project && claude # your CLI now has SciStudio tools
```

The bridge auto-detects whether a SciStudio backend is running and either
shares its state (attached mode) or stands up an in-process MCP server
itself (standalone mode). See [`docs/cli-integration.md`](docs/cli-integration.md)
for the full guide, including project vs user scope, Codex caveats, and
troubleshooting.

---

## Contributing

SciStudio follows a structured development workflow to ensure traceability and architectural consistency. Please read [`CLAUDE.md`](CLAUDE.md) for the full set of development rules, including:

- **Branch discipline**: all changes go through PRs; no direct push to main.
- **Gate workflow**: every task follows a 6-stage pipeline (issue, change plan, branch, PR, docs, changelog).
- **Focused commits**: use conventional commit messages (`feat(module):`, `fix(module):`, `docs:`, etc.).
- **Tests are part of the change**: bug fixes include regression tests; new features include validation tests.
- **Architecture boundaries**: enforced by import-linter contracts in CI.

### Architecture Decision Records

Significant design decisions are documented as ADRs in [`docs/adr/`](docs/adr/). Notable decisions include:

| ADR | Decision |
|-----|----------|
| ADR-017 | Subprocess isolation for all blocks |
| ADR-018 | Event-driven scheduler with CANCELLED/SKIPPED states |
| ADR-019 | Cross-platform ProcessHandle abstraction |
| ADR-020 | Collection-based data transport between blocks |
| ADR-021 | Collection operation blocks (merge, split, filter, slice) |
| ADR-022 | psutil-based OS memory monitoring (replacing per-block estimates) |
| ADR-023 | Frontend layout redesign (three-column with bottom panel) |
| ADR-024 | Frontend bundling into Python wheel + `scistudio gui` command |
| ADR-025 | Plugin entry-points callable protocol with PackageInfo |
| ADR-026 | Block SDK (scaffolding, test harness, developer docs) |

---

## Current Status

SciStudio is in **pre-alpha** (v0.3.2a0). The following is implemented and under active development:

**Implemented:**
- Core data type hierarchy with six base types and domain-specific subtypes
- Storage backends: Zarr (arrays), Arrow/Parquet (tables), filesystem (text/artifacts), composite store
- Reference-only lazy loading built into `DataObject`/`Array` directly (ADR-031; ViewProxy eliminated)
- Lineage tracking with SQLite-backed provenance graph
- All six block categories (IO, Process, Code, App, AI, SubWorkflow)
- Block registry with Tier 1 (drop-in) and Tier 2 (entry-points) discovery
- IO format capability registry with structured `FormatCapability` declarations, aggregate IOBlocks, and deterministic loader/saver lookup (ADR-043)
- CodeBlock v2 backend system (ADR-041): Python (`.py`), shell (`.sh`), Jupyter notebook (`.ipynb`), R/Quarto (`.qmd`), and MATLAB backends; R (`RRunner`, via `Rscript`) and Julia (`JuliaRunner`, via `julia`) runners for legacy inline/script execution paths
- Collection-based data transport (ADR-020)
- Event-driven DAG scheduler with cancellation and skip propagation
- Subprocess isolation with cross-platform ProcessHandle
- ResourceManager with GPU/CPU slot counting and psutil memory watermarks
- Checkpoint save/load/resume
- FastAPI REST + WebSocket API
- React + ReactFlow frontend with live execution, block palette, config panels, data previews
- CLI commands: init, validate, run, blocks, serve, gui
- Plugin entry-points protocol with PackageInfo (ADR-025)
- Block SDK: `scistudio init-block-package` scaffold command and `BlockTestHarness` contract-validation / smoke-test helper (ADR-026)
- 70%+ test coverage enforced in CI (Python 3.13 leg only; see pyproject.toml `fail_under`)

**Planned / In Progress:**
- AI block generation and workflow synthesis (templates exist, runtime integration in progress)
- Runtime parameter optimization
- Additional CodeBlock backends and extended R/Julia integration (conda/renv environments, streaming output)
- Remote execution runners (SSH, Slurm, cloud -- interfaces designed)
- Block marketplace and version pinning
- Streaming/pipelined data transfer (StreamPort)
- Container and WASM sandboxing

---

## Limitations and Operational Posture

SciStudio is pre-alpha software designed for single-user, local use. The following
constraints are intentional for this stage and will be addressed in future releases:

- **Single active project**: the API runtime (`ApiRuntime`) holds a single
  `active_project` reference at a time. Opening a second project replaces the
  first. Multi-project concurrent access, project switching without server
  restart, and shared-server multi-tenant operation are not currently supported.
  (`src/scistudio/api/runtime/_projects.py`)

- **Unauthenticated WebSocket cancel**: the WebSocket endpoint (`/api/ws`)
  accepts `cancel_block` and `cancel_workflow` messages from any connected
  client without authentication or session validation. Any browser tab that
  can reach the backend can cancel running blocks or workflows. This is
  intentional for a local single-user deployment; adding authentication is
  tracked for the multi-user roadmap. (`src/scistudio/api/ws.py`)

- **Local single-user deployment**: there is no user management, access
  control, or network isolation built in. Do not expose a SciStudio backend
  on a shared network without an external authentication proxy.

---

## Roadmap

Development follows a phased plan. Completed phases:

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Repository bootstrap and tooling | Done |
| 1 | Interface skeleton (all ABCs and Protocols) | Done |
| 2 | Architecture tests and CI hardening | Done |
| 3 | Core data layer (types, storage, lineage) | Done |
| 4 | Block system (all categories, registries, adapters) | Done |
| 5 | Execution engine (DAG scheduler, subprocess isolation, events) | Done |
| 6 | Workflow serialization and CLI | Done |
| 7-8 | API layer and frontend workflow editor | Done |

---

## License

SciStudio is released under the MIT License. See the [LICENSE](LICENSE) file for
the full text.
