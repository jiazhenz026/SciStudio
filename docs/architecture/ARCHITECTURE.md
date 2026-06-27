---
doc_type: architecture
title: "SciStudio Architecture Document"
status: living
owner: "@jiazhenz026"
last_updated: 2026-05-20
governed_by:
  - ADR-042
  - ADR-043
related_adrs:
  - 25
  - 26
  - 27
  - 28
  - 31
  - 38
  - 39
  - 40
  - 41
  - 42
  - 43
summary: "Stable architecture overview for SciStudio runtime, data, block, registry, boundary IO, frontend, and extension layers."
---

# SciStudio Architecture Document

> Status: Living architecture reference
> Last updated: 2026-05-20
> Audit rule: implementation contracts must match current repository facts

---

## 1. Introduction

### 1.1 Introduction

SciStudio is a scientific data analysis framework for AI-native, traceable,
reproducible, multimodal, and streaming data workflows.

SciStudio is designed for scientific data:

- It uses a typed scientific data model to describe the shape, storage,
  metadata, and movement of data across workflow steps.
- It uses a block-based workflow system to compose analysis steps into graphs.
- It uses a plugin system so domains can add new data types, processing blocks,
  file adapters, and tool integrations without moving domain logic into the core
  runtime.
- It is AI-native: it provides MCP tools so AI agents can create and run
  workflows, create dedicated blocks, tune parameters, inspect results, optimize
  analysis, and participate in workflows as blocks.
- It tracks lineage for each workflow run and uses native Git version and branch
  management for reproducibility.

### 1.2 Contents

| Section | Topic | Contract source |
|---|---|---|
| 1 | Introduction | Product purpose, document conventions |
| 2 | Scope | In-scope runtime architecture and out-of-scope future work |
| 3 | Architecture overview | ADR-025, ADR-026, ADR-038, ADR-039 |
| 4 | Data foundation | ADR-027, ADR-028, ADR-031, ADR-038, ADR-039, ADR-041 |
| 5 | Block system | ADR-020, ADR-025, ADR-026, ADR-027, ADR-028 |
| 6 | Execution engine | ADR-020, ADR-038 |
| 7 | AI Agents | ADR-034, ADR-040 |
| 8 | API | ADR-023, ADR-024, ADR-033 |
| 9 | Frontend | ADR-023, ADR-024, ADR-036 |
| 10 | Plot system | ADR-048 |
| 11 | Project workspace structure | ADR-023, ADR-038, ADR-039, ADR-040 |
| 12 | Extensibility | ADR-025, ADR-026, ADR-028 |
| 13 | Desktop app | Electron shell + bundled backend |
| 14 | Dependencies list | Repository dependency manifests |
| 15 | Technology stack summary | Current repository dependencies |

### 1.3 Architecture Index

| Area | Primary responsibility | Expected evidence |
|---|---|---|
| Data foundation | Data object model, storage references, lazy access, lineage, boundary format handling | ADRs, specs, public type contracts, storage tests |
| Block system | Block base behavior, port semantics, registry, package discovery, SDK expectations | ADRs, public block contracts, registry tests |
| Execution engine | Graph scheduling, collection transport, process lifecycle, resource coordination, checkpoint behavior | Runtime modules, engine tests, lineage checks |
| AI Agents | Production agent boundaries, MCP surface, project provisioning, skills, hooks, provider parity | ADRs, API contracts, governance checks |
| API layer | REST, WebSocket, SPA serving, project and workflow orchestration | API modules, route tests, frontend integration checks |
| Frontend | Canvas layout, palette, node UI, preview panels, tab behavior, run controls | Frontend source, UI tests, ADR-backed interaction rules |
| Workspace | Project files, workflow definitions, local runtime state, source history | Workspace docs, ADRs, serialization tests |
| Extension points | Plugin entry points, block packages, custom type packages, developer scaffolding | Specs, entry point contracts, SDK tests |

---

## 2. Scope

### 2.1 Why SciStudio Exists

Scientific data analysis increasingly combines many modalities, tools, file
formats, programming languages, and review steps. A single study may involve
images, tables, spectra, omics matrices, notebooks, command-line tools, GUI
applications, and AI-assisted interpretation. Researchers need the flexibility
of this ecosystem, but also need analysis to be repeatable, inspectable, and
recoverable.

SciStudio exists to make that workflow shape explicit. It treats analysis as a
typed, traceable workflow rather than a loose collection of scripts, notebooks,
manual exports, and undocumented intermediate files.

### 2.2 Weaknesses In Existing Workflows

SciStudio is designed around several common weaknesses in current scientific data
analysis practice:

- Analysis steps often live in disconnected tools, scripts, notebooks, and GUI
  applications.
- Existing pipelines are valuable, but many workflow systems require users to
  rewrite them before they can be tracked, composed, or reviewed.
- Intermediate data movement is frequently manual, hidden in local files, or
  encoded in ad hoc naming conventions.
- Parameters, tool versions, data provenance, and review decisions are often
  difficult to reconstruct after the analysis is complete.
- Multimodal workflows require repeated conversion between domain-specific
  formats and tool-specific assumptions.
- File extensions and format labels are often treated as if they were reliable
  data contracts, even though real analysis tools may disagree about the same
  nominal format.
- Large datasets make eager loading and full-copy processing expensive or
  impossible.
- AI assistance is often outside the workflow record, making suggestions,
  generated code, and parameter changes hard to audit later.

### 2.3 What SciStudio Provides

SciStudio provides a framework for building and running scientific workflows with
clear contracts between steps:

- A typed data model for describing scientific data, metadata, storage, and
  movement across workflow steps.
- A block-based workflow model for composing analysis steps into reusable,
  reviewable graphs.
- Inclusive execution blocks for existing work: CodeBlock and AppBlock let
  users run familiar scripts, command-line tools, GUI applications, and
  pipelines inside SciStudio with near-zero migration cost.
- Lineage tracking for workflow runs so inputs, parameters, outputs, source
  state, and execution context can be connected.
- Native source-history integration so workflow definitions and project files
  can be versioned and branched.
- Plugin extension points for domain packages, file adapters, processing tools,
  and custom blocks.
- A canonical-zone data handling model where internal workflow data uses
  explicit typed contracts, while file-format and extension conversion happen at
  import/export or external-tool boundaries.
- API and frontend layers that expose the same runtime truth instead of
  inventing separate workflow state.
- AI-native orchestration surfaces so agents can assist with workflow creation,
  execution, block generation, parameter tuning, and result review while staying
  inside the project record.

### 2.4 What SciStudio Does Not Provide

SciStudio is not intended to replace every scientific tool or analysis library.
It provides the workflow runtime around those tools.

SciStudio does not try to:

- Replace domain-specific analysis packages, statistical methods, or scientific
  validation.
- Guarantee that an analysis is scientifically correct without human review and
  domain expertise.
- Hide all complexity from advanced users who need custom code, external tools,
  or domain-specific tuning.
- Move all domain logic into the core runtime.
- Make large data cheap by itself; it provides contracts and execution patterns
  that let blocks avoid unnecessary loading and copying.

### 2.5 Future Plans

Future work should extend SciStudio without weakening the core boundaries:

- Broader domain plugin packages for common scientific modalities.
- More streaming and partial-read execution patterns for large data.
- Stronger collaboration workflows for sharing project state, lineage, and
  review decisions across machines or teams.
- Richer AI-assisted workflow design, debugging, and result interpretation.
- More external tool adapters for established GUI, CLI, and service-based
  scientific software.
- Marketplace-style discovery and version resolution for reusable blocks and
  data types.

---

---

## 3. Architecture Overview

SciStudio is organized as a layered runtime with cross-cutting plugin and
governance systems. The layers describe responsibility boundaries; the runtime
architecture describes how those parts cooperate while a workflow is edited,
validated, executed, paused, reviewed, resumed, and inspected.

### 3.1 Layer Architecture

The layer model keeps user-facing tools, API orchestration, execution behavior,
block contracts, and data handling separate. Higher layers depend on lower
layers, while plugin and cross-cutting systems extend or observe the stack
without becoming a hidden seventh layer.

<table>
  <tbody>
    <tr>
      <td colspan="2" style="text-align:center; padding:10px; border:1px solid #999;"><strong>Layer 6: Frontend</strong><br />Workflow canvas, block palette, previews, run controls, review panels</td>
    </tr>
    <tr>
      <td colspan="2" style="text-align:center; padding:10px; border:1px solid #999;"><strong>Layer 5: API</strong><br />REST, realtime updates, project and workflow orchestration, static app serving</td>
    </tr>
    <tr>
      <td colspan="2" style="text-align:center; padding:10px; border:1px solid #999;"><strong>Layer 4: AI Agents</strong><br />Production agent runtime, MCP contracts, project provisioning, skills, hooks, provider parity</td>
    </tr>
    <tr>
      <td colspan="2" style="text-align:center; padding:10px; border:1px solid #999;"><strong>Layer 3: Execution Engine</strong><br />Event-driven scheduling, process lifecycle, resource coordination, pause/resume, checkpoint behavior</td>
    </tr>
    <tr>
      <td colspan="2" style="text-align:center; padding:10px; border:1px solid #999;"><strong>Layer 2: Block System</strong><br />Block lifecycle, ports, validation, CodeBlock, AppBlock, AIBlock, subworkflows, registry metadata</td>
    </tr>
    <tr>
      <td colspan="2" style="text-align:center; padding:10px; border:1px solid #999;"><strong>Layer 1: Data Foundation</strong><br />Typed scientific data model, storage references, lazy access, lineage, canonical-zone boundary handling</td>
    </tr>
    <tr>
      <td style="text-align:center; padding:10px; border:1px solid #999; width:50%;"><strong>Plugin Ecosystem</strong><br />Domain blocks, data types, file adapters, external-tool bridges, package discovery</td>
      <td style="text-align:center; padding:10px; border:1px solid #999; width:50%;"><strong>Cross-Cutting Systems</strong><br />Lineage, Git-backed history, governance, audit, permissions, environment capture</td>
    </tr>
  </tbody>
</table>

The plugin ecosystem and cross-cutting systems sit on the same conceptual row:
plugins extend what SciStudio can do, while cross-cutting systems record, govern,
or constrain work across all layers. Neither should collapse into frontend
state or bypass the lower runtime contracts.

### 3.2 Runtime Architecture

At runtime, SciStudio is event-driven. The frontend and API submit workflow
changes and run requests to the runtime. The runtime validates the workflow
against block and data-type contracts, resolves plugin-provided capabilities,
dispatches ready work through the execution engine, and emits events that keep
UI, API clients, AI tools, lineage, and review surfaces synchronized.

<table>
  <tbody>
    <tr>
      <td style="text-align:center; padding:10px; border:1px solid #999;"><strong>Frontend</strong><br />Canvas, controls, previews, review UI</td>
      <td style="text-align:center; padding:10px; border:1px solid #999;"><strong>AI / MCP Clients</strong><br />Workflow authoring, block creation, tuning, result review</td>
    </tr>
    <tr>
      <td colspan="2" style="text-align:center; padding:10px; border:1px solid #999;"><strong>API Boundary</strong><br />Receives user and agent intent; exposes runtime state without becoming the source of truth</td>
    </tr>
    <tr>
      <td colspan="2" style="text-align:center; padding:10px; border:1px solid #999;"><strong>Workflow Runtime</strong><br />Validates graphs, resolves block/type contracts, manages run state, coordinates reviews</td>
    </tr>
    <tr>
      <td style="text-align:center; padding:10px; border:1px solid #999;"><strong>Event Bus</strong><br />Run events, block state changes, progress, logs, review gates, file boundary events</td>
      <td style="text-align:center; padding:10px; border:1px solid #999;"><strong>Plugin Registry</strong><br />Discovers blocks, types, adapters, capabilities, and external-tool bridges</td>
    </tr>
    <tr>
      <td colspan="2" style="text-align:center; padding:10px; border:1px solid #999;"><strong>Execution Engine</strong><br />Schedules ready blocks, reserves resources, starts local or external work, handles pause/resume/failure</td>
    </tr>
    <tr>
      <td style="text-align:center; padding:10px; border:1px solid #999;"><strong>Block Runtime</strong><br />Process blocks, IO blocks, CodeBlock, AppBlock, AIBlock, subworkflows</td>
      <td style="text-align:center; padding:10px; border:1px solid #999;"><strong>Type And Data Runtime</strong><br />Typed objects, storage references, canonical-zone data, import/export boundaries</td>
    </tr>
    <tr>
      <td colspan="2" style="text-align:center; padding:10px; border:1px solid #999;"><strong>Project Record</strong><br />Workflow definitions, artifacts, lineage, Git history, environment snapshots, logs, audit evidence</td>
    </tr>
  </tbody>
</table>

The most important runtime coupling is between blocks and data types. Blocks do
not merely pass opaque files to each other; they declare what kind of data they
accept and produce. Data types describe shape, storage, metadata, and access
patterns. The execution engine uses those contracts to validate connections,
materialize data at external-tool boundaries, avoid unnecessary full loads, and
persist enough lineage to reconstruct what happened.

The API and frontend are presentation and orchestration surfaces over this
runtime. They may cache view state for interaction, but workflow truth belongs
to the runtime and project record. AI agents use the same API and MCP-facing
capabilities as other clients, so AI-authored actions can be reviewed, traced,
and reproduced instead of living only in chat history.

---

## 4. Layer 1: Data Foundation

The **data foundation** is the bottom layer of SciStudio. It gives workflow blocks
a common way to describe **scientific data**, move data between steps, avoid
unnecessary copies, cross **file-format boundaries**, and preserve enough
context to reproduce an analysis later.

### 4.1 Base Types

SciStudio keeps the **core data model** intentionally small. The **base types**
are not a catalog of every scientific modality. They are the common shapes that
many domain types can build on.

#### 4.1.1 DataObject

`DataObject` is the **common wrapper** for data moving through a workflow. It exists
so every block can receive data with a consistent envelope for framework
metadata, user metadata, type information, and storage references.

It normally appears as a lightweight object that points to stored data instead
of carrying the full payload in memory. Examples include an object representing
a table persisted in Parquet, an image stack persisted in Zarr, or a file-backed
artifact produced by an external tool.

#### 4.1.2 Array

`Array` represents **N-dimensional numeric data with named axes**. It exists
because scientific imaging, spectra, volumes, time series, and other dense
measurements need axis-aware slicing and iteration rather than anonymous
positional indexing.

An `Array` records shape, dtype, axes, chunking expectations, and storage
reference information. Examples include microscopy images, volumetric stacks,
hyperspectral cubes, matrix-like measurements, and other dense numeric payloads.

#### 4.1.3 Series

`Series` represents **one-dimensional labelled data**. It exists for values that
are naturally ordered or indexed but do not need the full table model.

A `Series` may be used for spectra, traces, measurements over time, calibration
curves, or other single-axis scientific values.

#### 4.1.4 DataFrame

`DataFrame` represents **tabular data**. It exists because many scientific
results are row-and-column records: observations, features, peaks, measurements,
sample metadata, quality-control tables, and summary outputs.

A `DataFrame` records columns, schema, row count, and a storage reference to a
columnar backend when data is persisted.

#### 4.1.5 Text

`Text` represents **small textual payloads**. It exists for prompts, notes, logs,
plain text outputs, structured text snippets, and other small content that is
better carried directly than stored as a large data object.

Unlike large scientific arrays or tables, a `Text` object may keep its content
in memory because it is expected to be small.

#### 4.1.6 Artifact

`Artifact` represents **files whose internal format is not part of the SciStudio
canonical data model**. It exists for interoperability with scientific tools
that produce reports, images, PDFs, archives, logs, or other file outputs.

An `Artifact` usually preserves the original file and carries descriptive
metadata, MIME information, and a file path or storage reference.

#### 4.1.7 CompositeData

`CompositeData` represents a **named bundle of heterogeneous data objects**. It
exists because many real scientific objects are containers rather than a single
array or table.

A composite object may bundle a matrix, feature table, observation metadata,
images, coordinate tables, masks, annotations, or other related data slots while
keeping the bundle addressable as one workflow value.

### 4.2 Type Hierarchy

The **type hierarchy** lets SciStudio validate workflow connections at the level
of scientific meaning without forcing every modality into the core package.

**Core types** provide broad categories. **Plugin packages** define
domain-specific types by building on those categories. A workflow port can
accept a broad type when it only needs generic behavior, or a narrower
plugin-provided type when the block requires domain-specific structure.

This separation keeps core stable while allowing new domains to extend SciStudio
with their own types. The core does not need to know every image, spectrum,
omics, or instrument-specific class in advance. It only needs the registered
type relationship and the contracts needed for validation, preview, storage,
and execution.

Examples:

- **`Image` -> `Array`**: image data specializes the dense named-axis array
  model.
- **`FluorImage` -> `Image`**: fluorescence image data specializes image data
  with channel-aware metadata and axis requirements.
- **`Spectrum` -> `Series`**: spectrum data specializes one-dimensional labelled
  values.
- **`PeakTable` -> `DataFrame`**: peak tables specialize row-and-column
  scientific results.
- **single-cell data / spatial-omics data -> `CompositeData`**: multimodal
  containers specialize named bundles of heterogeneous data slots.

### 4.3 Data Management

#### 4.3.1 Storage Backends

SciStudio stores data in **backends chosen for the access pattern** of each base
type. The goal is to keep workflow values **lightweight** while allowing blocks
to load only the data they actually need.

| Base type | Primary backend | Rationale |
|---|---|---|
| `Array` | Zarr | Chunked, compressed, cloud-compatible storage for large numeric data. |
| `Series` | Apache Arrow / Parquet | Columnar storage for indexed one-dimensional values while preserving label/value schema. |
| `DataFrame` | Apache Arrow / Parquet | Columnar storage for filtering, aggregation, and memory mapping. |
| `Text` | In memory or filesystem | Small textual payloads can usually travel directly. |
| `Artifact` | Filesystem | Original files are preserved for interoperability. |
| `CompositeData` | Directory of slot backends | Each slot uses the backend appropriate to its own type. |

`Series` storage is table-shaped even when the logical value is one-dimensional.
Generic `Series` values normally persist as a one-column Arrow table named by
`value_name`; domain-specific `Series` subclasses may use additional columns
when their type contract requires explicit coordinates, such as `Spectrum`
storing `lambda` and `intensity`.

#### 4.3.2 Canonical Zone And Boundary Formats

SciStudio separates **internal workflow data** from **external file formats**.
Inside the workflow, data moves through a **canonical zone**: arrays, tables,
text, artifacts, and composite objects use explicit typed contracts and storage
references. File extensions and external formats are not used as the internal
compatibility model.

**Format handling happens at boundaries:**

- Load boundaries convert user files into canonical typed data.
- Save boundaries convert canonical typed data into user-requested output
  formats.
- AppBlock and CodeBlock boundaries materialize canonical inputs for external
  tools or scripts, then reconstruct declared outputs back into canonical typed
  data.
- AIBlock boundaries follow the same model when an agent workflow needs file
  exchange.

```text
+--------------------+     +--------------------+
| User files         |     | User outputs       |
| instrument formats |     | requested formats  |
+---------+----------+     +----------+---------+
          |                           ^
          v                           |
+---------+----------+     +----------+---------+
| Load boundary      |     | Save boundary      |
| selected capability|     | selected capability|
+---------+----------+     +----------+---------+
          |                           ^
          v                           |
+---------+---------------------------+---------+
| Canonical zone                               |
| typed data objects + storage references      |
| format is not an internal edge contract      |
+---------+---------------------------+---------+
          ^                           ^
          |                           |
+---------+---------------------------+---------+
| External-tool boundaries                     |
| AppBlock / CodeBlock / AIBlock               |
| materialize inputs, reconstruct outputs      |
+------------------------------------------------+
```

This model avoids treating **file extensions as data contracts**. A filename may
be useful for humans, but the replayable decision is the selected **boundary
capability**: the declared direction, target type, format identity, extensions,
handler, priority/default metadata, and fidelity expectations.

Within the **canonical zone**, blocks connect by type and declared data
contract. When a user needs a different file format, SciStudio models that as an
explicit **boundary conversion** rather than a hidden edge between ordinary
processing blocks.

#### 4.3.3 Lazy Loading, Slicing, And Broadcast

SciStudio avoids loading **large datasets** until a block asks for data. Data
objects can point to persisted storage and expose methods for **full
materialization**, **partial reads**, and **chunked iteration**.

**Lazy loading** has three practical effects:

- Large arrays and tables can move through the workflow as references.
- Blocks can process slices or chunks instead of copying entire datasets.
- External-tool boundaries can materialize only the files needed for that tool.

**Named axes** make slicing and broadcast meaningful for scientific data. A
block can operate over spatial axes while iterating over time, depth, channel,
or spectral dimensions. **Broadcast helpers** support cross-modal patterns where
a lower-dimensional object is applied across a higher-dimensional target, while
the block remains responsible for the scientific validity of the operation.

### 4.4 Metadata Management

ADR-043 uses metadata management in a narrow IO-boundary sense. It governs how
external file metadata is represented, declared, validated, and surfaced when
data crosses between SciStudio's canonical zone and files, scripts, notebooks, or
external applications.

The central rule is that **DataObject types do not own file formats**. Format
knowledge belongs to IO capabilities. A `FormatCapability` describes one
boundary conversion with a **direction**, **data type**, **format id**,
**extensions**, **label**, **owning block type**, **handler**, **default or
priority**, optional **round-trip group**, and a **metadata fidelity** contract.

`MetadataFidelity` records what domain metadata survives that conversion:

| Fidelity level | Meaning |
|---|---|
| `pixel_only` | Preserves only the primary payload and minimum structural fields needed to build the target object. |
| `typed_meta` | Preserves declared fields from the target type's typed `meta` model. |
| `format_specific` | Preserves declared format-native metadata through typed fields, a typed sidecar, or a package-defined metadata object. |
| `lossless` | Preserves the declared boundary representation for a compatible round-trip group. |

This metadata is validated at registry scan time. The registry checks that
handlers exist, extensions are normalized, capability IDs are stable, defaults
do not conflict, round-trip claims have compatible load/save sides, and
declared typed `meta` fields exist on the target type's metadata model.

AppBlock and CodeBlock boundary ports use this same model. An extension remains
a filename and UI hint, but the selected **`capability_id`** is the stable IO
selection for replay and validation when multiple packages can handle the same
type and extension.

Run IDs, block execution rows, resolved configs, environment snapshots, and
input/output object edges are **Lineage**, not ADR-043 metadata management.
Free-form user metadata is also outside ADR-043 and belongs to a future
metadata package.

### 4.5 Data Lineage

SciStudio records workflow execution as **lineage** rather than treating outputs
as isolated files. A run record connects the workflow definition, source state,
resolved block parameters, block executions, inputs, outputs, environment
information, and termination state.

**Lineage is separate from content storage.** Intermediate outputs may be
managed by their natural storage backends and may be overwritten by later runs.
The durable asset is the **recipe**: which workflow ran, with which parameters,
against which inputs, in which environment, and from which source state.

This lets SciStudio answer questions such as:

- Which workflow produced this result?
- Which blocks ran and which were skipped, cancelled, or failed?
- Which parameters and inputs were used?
- Which source version was executed?
- What should be re-run to reproduce or inspect the result?

The lineage store is `<project>/.scistudio/lineage.db`, a SQLite database using
WAL mode for project-local concurrent writes. ADR-038 defines four normalized
tables:

| Table | What it records |
|---|---|
| `runs` | One workflow execution, including workflow id, source commit, workflow snapshot, status, trigger, parent run, execute-from block, and environment snapshot. |
| `block_executions` | One row per block execution in a run, including block id, block type, block version, resolved config, timing, duration, and terminal status. |
| `data_objects` | DataObject identity and reference payloads, including type name, backend, best-effort storage path, size, mtime, wire payload, derivation, and producer execution. |
| `block_io` | Port-to-object edges for each execution, including direction, port name, object id, and collection position. |

Worker subprocesses do not write to `lineage.db`. The engine process observes
block inputs and outputs, reads their wire-format references, and records the
lineage rows externally. This keeps block authoring unchanged while making run
history queryable.

Collections are stored as item-level lineage edges rather than as one opaque
row. A collection output with many items becomes many `data_objects` rows plus
ordered `block_io.position` entries, so the UI can reconstruct the collection
shape without storing the collection wrapper as a separate database object.

Each run also records an environment snapshot. The snapshot captures the Python
version, platform, full package freeze, and derived key packages so re-run
checks can warn when the current environment has drifted from the historical
run.

**Re-runs** create new lineage records linked back to the earlier run. That
makes reproducibility visible as a chain of attempts rather than an overwrite of
history.

### 4.6 Version Control

Every SciStudio project can be managed as a **Git-backed project**. Workflow
files, custom block code, notes, and project configuration can be committed,
compared, restored, branched, and merged using ordinary version-control
semantics.

**Git history** and **run lineage** solve different problems:

- Git records changes to source files, workflow definitions, custom code, and
  project notes.
- Lineage records executions, parameters, inputs, outputs, environment context,
  and run status.

The connection between them is the **source state captured for a run**. From a
run, a user can recover the workflow source that was executed. From a source
state, a user can inspect which runs used it.

Branches are also useful for scientific analysis itself, not only software
development. Scientists often adapt nearly identical pipelines for different
batches, instruments, cohorts, or experiments. A branch can represent one
parallel workflow variant for one data context. Users can switch quickly between
branches, compare what changed, and keep each adapted workflow recoverable. In
this usage, branches are primarily a way to manage parallel analysis variants;
merging is optional and often not the main goal.

Project runtime state and **large data** are not automatically treated as Git
content. They are managed through storage and lineage. This keeps Git useful for
human-readable project history and parallel workflow variants while avoiding
large binary churn in ordinary commits.

---

## 5. Layer 2: Block System

A **Block** is the unit of work in a SciStudio workflow. It wraps one analysis
step behind a typed contract: what it accepts, what it produces, how it is
configured, and how the runtime should execute it. Blocks can represent pure
computation, data loading and saving, external applications, project-local
scripts, AI agents, or nested workflows.

### 5.1 Base Class Definition

The `Block` base class defines the common contract shared by every block. The
full implementation contains validation details and helper methods; the public
surface below is the architecture-level contract.

```python
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.base.state import ExecutionMode
from scistudio.core.types.collection import Collection

class Block(ABC):
    name: ClassVar[str] = "Unnamed Block"
    description: ClassVar[str] = ""
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = ""

    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = []

    variadic_inputs: ClassVar[bool] = False
    variadic_outputs: ClassVar[bool] = False
    allowed_input_types: ClassVar[list[type]] = []
    allowed_output_types: ClassVar[list[type]] = []

    min_input_ports: ClassVar[int | None] = None
    max_input_ports: ClassVar[int | None] = None
    min_output_ports: ClassVar[int | None] = None
    max_output_ports: ClassVar[int | None] = None

    dynamic_ports: ClassVar[dict[str, Any] | None] = None
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.AUTO
    terminate_grace_sec: ClassVar[float] = 5.0
    key_dependencies: ClassVar[list[str]] = []
    config_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    def get_effective_input_ports(self) -> list[InputPort]: ...
    def get_effective_output_ports(self) -> list[OutputPort]: ...
    def validate(self, inputs: dict[str, Any]) -> bool: ...

    @abstractmethod
    def run(
        self,
        inputs: dict[str, Collection],
        config: BlockConfig,
    ) -> dict[str, Collection]: ...

    def postprocess(
        self,
        outputs: dict[str, Collection],
    ) -> dict[str, Collection]: ...
```

Important class attributes:

- **`name` / `description` / `version`** identify the block in the palette and
  in lineage records.
- **`input_ports` / `output_ports`** declare the static typed interface.
- **`variadic_inputs` / `variadic_outputs`** allow a block instance to expose a
  user-edited port list.
- **`allowed_input_types` / `allowed_output_types`** constrain port-editor type
  choices for variadic blocks.
- **`dynamic_ports`** describes enum-driven port changes such as load/save
  blocks whose selected data type changes the effective port type.
- **`execution_mode`** tells the runtime whether the block is automatic,
  interactive, or external.
- **`terminate_grace_sec`** gives the runtime a cancellation grace period before
  forced termination.
- **`config_schema`** drives the configuration form exposed through the API and
  frontend.

### 5.2 State Machine

Every block moves through a small state machine during a workflow run. The
state machine is owned by the engine — `DAGScheduler` is the authoritative
source per ADR-018 §8.1 (`DAGScheduler.set_state` / `block_states()`). Worker
subprocesses do not carry their own block-state field; cancellation from
inside `run()` surfaces as the typed `BlockCancelledByAppError` exception, which
the worker forwards via the `final_state` envelope (#1334). Terminal states
describe the result of one execution attempt; returning to `IDLE` happens
when the workflow is reset for another run.

```text
IDLE      -> READY | SKIPPED | ERROR
READY     -> RUNNING | SKIPPED | ERROR
RUNNING   -> DONE | PAUSED | ERROR | CANCELLED
PAUSED    -> RUNNING | ERROR | CANCELLED
DONE      -> IDLE
ERROR     -> IDLE
CANCELLED -> IDLE
SKIPPED   -> IDLE
```

```text
+------+      +-------+      +---------+      +------+
| IDLE | ---> | READY | ---> | RUNNING | ---> | DONE |
+--+---+      +---+---+      +----+----+      +--+---+
   |              |               |              |
   |              |               v              |
   |              |          +----+----+         |
   |              |          | PAUSED  | --------+
   |              |          +----+----+
   |              |               |
   v              v               v
+--+---+      +---+---+      +----+-----+
|ERROR |      |SKIPPED|      |CANCELLED |
+--+---+      +---+---+      +----+-----+
   |              |               |
   +--------------+---------------+
                  |
                  v
                +----+
                |IDLE|
                +----+
```

#### 5.2.1 IDLE

`IDLE` means the block is not part of an active execution attempt. A reset
places completed, failed, cancelled, or skipped blocks back into this state.

#### 5.2.2 READY

`READY` means all required upstream inputs are available and the scheduler may
dispatch the block.

#### 5.2.3 RUNNING

`RUNNING` means the block has been dispatched and is actively executing or
waiting inside its worker process.

#### 5.2.4 PAUSED

`PAUSED` means execution is intentionally suspended while waiting for an
external action, such as a GUI application, human review, or agent completion.

#### 5.2.5 DONE

`DONE` means the block completed successfully and produced its declared outputs.

#### 5.2.6 ERROR

`ERROR` means the block failed because validation, runtime execution, external
process handling, or output reconstruction failed.

#### 5.2.7 CANCELLED

`CANCELLED` means the user or runtime explicitly terminated the block before it
completed.

#### 5.2.8 SKIPPED

`SKIPPED` means the block could not run because required upstream output was not
available. Skip propagation lets the workflow finish with a clear causal chain
instead of hiding the downstream effects of an earlier failure.

### 5.3 Subprocess Isolation

Subprocess isolation is the **default execution path for non-interactive
blocks**. For these blocks, block logic runs outside the engine process. The
engine remains an orchestrator: it validates workflow state, starts workers,
records transitions, handles cancellation, and collects outputs. The worker
process reconstructs typed inputs from references, executes the block, and
returns typed outputs.

Subprocess isolation provides three guarantees for **every** block, interactive
or not:

- **Reliable cancellation**: the runtime can terminate a block without killing
  the engine.
- **Crash isolation**: a crash, memory leak, or native-library failure is
  contained to the worker or external process.
- **Low data-copy overhead**: large payloads stay in storage; cross-process
  exchange carries references and metadata rather than full data whenever
  possible.

#### 5.3.1 Interactive blocks run as two subprocess phases

Interactive blocks (for example `DataRouter` and `PairEditor`, identified by
`execution_mode == ExecutionMode.INTERACTIVE` plus the `InteractiveMixin`
capability) are **not** an exception to subprocess isolation. Since ADR-051 they
run as **two worker-subprocess phases around an engine-held pause**, so a block
is only ever executing inside a subprocess that runs to completion, never while
a human is in the loop.

The flow is: a **prompt phase** worker runs `prepare_prompt(inputs, config)` to
build a JSON-safe, window-sized view of the data and exits; the engine
transitions the block to `PAUSED` and holds the wait with **nothing resident**,
emitting an `INTERACTIVE_PROMPT` event (carrying the block's panel manifest and
the panel payload) over the WebSocket; when the user confirms, a fresh
**compute phase** worker runs `run(inputs, config)` with the decision merged
into config and exits. Heavy intermediate work may cross the pause as
engine-held storage references (never through the browser), and the user's
decision is recorded in lineage through `block_config_resolved` (ADR-038).

Because no block code is resident during the pause, the crash-isolation and
cancellation guarantees above apply to interactive blocks too: cancelling a
paused interaction releases any intermediate scratch and starts no compute
phase. See `scistudio/engine/scheduler/_dispatch.py` (`_run_interactive`),
`scistudio/engine/runners/worker.py` (the phase marker), and
`scistudio/blocks/base/interactive.py` (the capability) for the implementation.

### 5.4 Core Block Classes

The core block classes define common execution shapes. Domain packages and
project-local custom blocks build on these shapes instead of inventing their own
workflow runtime.

#### 5.4.1 IOBlock

`IOBlock` handles **data ingress and egress**. Loader blocks convert external
files into canonical typed data. Saver blocks convert canonical typed data into
user-requested external formats.

Important class attributes include **`direction`**, **`supported_extensions`**,
**`format_capabilities`**, static or dynamic ports, and format-related config
schema. `IOBlock` is where file format capability metadata attaches to block
execution.

#### 5.4.2 ProcessBlock

`ProcessBlock` is the normal class for deterministic data transformations. It
is used for algorithms that consume typed inputs and produce typed outputs.

Important class attributes include **`input_ports`**, **`output_ports`**,
**`algorithm`**, **`subcategory`**, and **`config_schema`**. Block authors can
implement per-item processing for simple cases or override full run behavior for
custom batching, streaming, or multi-port logic.

#### 5.4.3 Custom Block

**Custom Block** is a user-facing concept rather than a separate required base
class in the current runtime. A custom block is a project-local or user-global
block file that subclasses one of the core block classes and is discovered by
the registry.

Custom blocks usually declare **`name`**, **`description`**, **`version`**,
**`input_ports`**, **`output_ports`**, **`config_schema`**, and optional
**`subcategory`**. They let a lab add local logic without publishing a package.

#### 5.4.4 AppBlock

`AppBlock` bridges external GUI or CLI applications through file exchange. It
materializes canonical inputs for the tool, launches or coordinates the tool,
watches for declared outputs, and reconstructs those outputs into canonical
typed data.

Important class attributes include **`app_command`**, **`output_patterns`**,
**`variadic_inputs`**, **`variadic_outputs`**, **`input_ports`**,
**`output_ports`**, and **`config_schema`**. `AppBlock` usually runs in external
mode and may enter `PAUSED` while waiting for user or tool output.

#### 5.4.5 CodeBlock

`CodeBlock` runs project-local scripts through the same external-boundary model
as app integration. Conceptually, it is part of the **AppBlock-shaped boundary
family**: canonical inputs are materialized for a script, the script runs in a
resolved backend, and declared outputs are reconstructed. In the current code,
`CodeBlock` directly subclasses `Block` while sharing the AppBlock-style
boundary behavior.

Important class attributes include **`input_ports`**, **`output_ports`**,
**`variadic_inputs`**, **`variadic_outputs`**, and script/backend configuration
schema. `CodeBlock` is for existing scripts and notebooks, not for moving
plugin logic into core.

Supported script suffixes are defined by the registered CodeBlock backends:

| Backend | Supported suffixes |
|---|---|
| Python script | `.py` |
| Shell script | `.sh` |
| R / Quarto script | `.R`, `.Rmd`, `.qmd` |
| Notebook | `.ipynb` |
| MATLAB-family script | `.m`, `.mlx` |

#### 5.4.6 AIBlock

`AIBlock` runs an AI agent as a workflow node. It presents declared inputs to
the agent, waits for completion, and validates declared outputs before the
workflow continues. Conceptually, it is also part of the **AppBlock-shaped
boundary family**: it crosses from canonical workflow data into an external
agent session and back. In the current code, `AIBlock` directly subclasses
`Block` while sharing this boundary behavior.

Important class attributes include **`type_name`**, **`name`**,
**`description`**, **`subcategory`**, **`input_ports`**, **`output_ports`**,
**`variadic_inputs`**, **`variadic_outputs`**, and agent/provider configuration
schema.

#### 5.4.7 SubWorkflowBlock

`SubWorkflowBlock` lets an entire workflow be referenced as a single node
inside another workflow. It is the **composition and canvas-readability**
mechanism: it collapses a reusable sub-pipeline into one node so large graphs
stay legible, and a workflow authored once can be reused across many parents.

It is an **authoring-time container, not a runtime executor** — the defining
design decision. A `SubWorkflowBlock` node carries only a reference to an
external subworkflow file (**`config.ref.path`**) and owns no child scheduler.
At run start, a parser-layer flattener
(`WorkflowDefinition.flatten_subworkflows`) replaces every `SubWorkflowBlock`
node with a prefixed copy of the referenced subworkflow's blocks and edges
before scheduler dispatch. The execution engine therefore always receives a
flat DAG and never observes a `SubWorkflowBlock` at runtime. This is why the
design flattens at the parser layer rather than nesting executors: it keeps
subworkflows out of the scheduler entirely and reuses the existing
single-graph execution path.

The editor keeps the container intact so authoring and storage stay stable.
Per-node port handles and dangling-edge detection come from the
**dynamic-ports** mechanism, deriving ports from the referenced subworkflow's
**`exposed_ports`** rather than from whole-graph flattening, and
double-clicking the canvas node opens the referenced file in its own editor
tab. When a reference cannot be resolved the editor renders a broken-reference
placeholder (a `subworkflow_broken` node) so the rest of the canvas still
loads, and run start rejects any unresolved reference rather than dispatching
it. Because the lineage record's `workflow_yaml_snapshot` captures the
flattened YAML, past runs stay reproducible automatically; reproducibility of
a reference against future edits is delegated to git branches or tags rather
than embedded in the tool.

Important class attributes include **`config.ref.path`** (the referenced
subworkflow file), dynamic port derivation from the referenced subworkflow's
**`exposed_ports`**, and the standard **`input_ports`** / **`output_ports`**
surface shared with other blocks. The full contract is defined by ADR-044
(`docs/adr/ADR-044.md`) and its implementation spec
(`docs/specs/adr-044-subworkflow-block.md`).

### 5.5 Port System

Ports define where data can enter or leave a block. They are the visible
connection points in the frontend and the runtime contract used by validation
and scheduling.

#### 5.5.1 Static Ports

Static ports are declared on the block class. They are appropriate when the
block always has the same input and output shape, such as one image in and one
image out.

Each static port declares a **name**, **accepted types**, **required/default
behavior**, and optional human-readable description.

#### 5.5.2 Variadic Ports

Variadic ports are edited per block instance. They are appropriate for blocks
where users choose the number or type of inputs and outputs at workflow design
time, such as AppBlock, CodeBlock, AIBlock, or routing blocks.

Variadic behavior is controlled by **`variadic_inputs`**,
**`variadic_outputs`**, **`allowed_input_types`**, **`allowed_output_types`**,
and optional min/max port-count constraints. Effective port methods convert the
instance configuration into the port list consumed by validation and execution.

#### 5.5.3 Port Validation

Port validation happens in layers:

- **Design-time validation** rejects impossible connections in the frontend.
- **Workflow validation** checks graph structure and port compatibility before
  execution.
- **Block validation** checks required inputs, accepted types, port constraints,
  and variadic port limits for the specific block instance.

---

## 6. Layer 3: Execution Engine

The execution engine turns a validated workflow graph into coordinated runtime
work. It owns graph scheduling, event propagation, subprocess dispatch,
checkpoint updates, resource gating, data transport, and terminal-state
handling. It does not own scientific algorithms; those live inside blocks.

### 6.1 Engine Responsibilities And Scope

The engine is responsible for moving a workflow from **requested** to
**completed, failed, cancelled, or partially skipped** while preserving enough
state for the UI, API, lineage system, and checkpoint system to agree on what
happened.

In scope:

- Build and execute a typed DAG from the workflow definition.
- Track block state transitions and emit runtime events.
- Dispatch blocks through a `BlockRunner`, normally `LocalRunner`.
- Coordinate subprocess lifecycle through `ProcessHandle` and
  `ProcessRegistry`.
- Apply resource gating through `ResourceManager` before starting work.
- Preserve pause/resume and latest-run checkpoint state through
  `CheckpointManager` and `WorkflowCheckpoint`.
- Move data between blocks as `Collection` transport units.
- Surface block-level terminal outcomes to API, frontend, lineage, and audit
  surfaces.

Out of scope:

- Scientific correctness of a block's algorithm.
- Per-item retry policy inside a collection. That belongs to the block.
- Hidden conversion between file formats on ordinary workflow edges.
- Long-term run provenance storage. The engine emits and observes events, but
  durable run history belongs to the lineage layer in Section 4.5.

The engine therefore acts as the runtime coordinator. It keeps orchestration
explicit while letting blocks, data types, lineage, and UI components keep their
own responsibilities.

### 6.2 Event Bus

`EventBus` is the runtime publish/subscribe backbone defined by ADR-018.
Schedulers, resource managers, process monitors, checkpoint handlers, lineage
recorders, WebSocket handlers, and API surfaces coordinate by emitting and
subscribing to `EngineEvent` values.

Core mechanisms:

| Mechanism | Responsibility |
|---|---|
| `EngineEvent` | Carries event type, optional block id, payload data, and timestamp. |
| `EventBus.subscribe` | Registers sync or async callbacks for one event type. |
| `EventBus.emit` | Broadcasts an event to subscribers, awaits async callbacks, and isolates callback failures. |
| `EventBus.unsubscribe` | Removes a callback from an event type. |

Important runtime event families:

| Event family | Examples | Main use |
|---|---|---|
| Workflow lifecycle | `WORKFLOW_STARTED`, `WORKFLOW_COMPLETED` | Run-level UI/API updates and completion handling. |
| Block lifecycle | `BLOCK_READY`, `BLOCK_RUNNING`, `BLOCK_PAUSED`, `BLOCK_DONE`, `BLOCK_ERROR`, `BLOCK_CANCELLED`, `BLOCK_SKIPPED` | State propagation, downstream scheduling, checkpointing, lineage writes. |
| Cancellation requests | `CANCEL_BLOCK_REQUEST`, `CANCEL_WORKFLOW_REQUEST` | User/API initiated cancellation routed to the scheduler and process layer. |
| Process lifecycle | `PROCESS_SPAWNED` | Register active process handles for lookup and cancellation. |
| Checkpointing | `CHECKPOINT_SAVED` | Notify UI and runtime surfaces that latest-run state was persisted. |
| Interactive workflow | `INTERACTIVE_PROMPT`, `INTERACTIVE_COMPLETE` | Bridge human/tool interaction for blocks that pause for input. |
| Project change | `WORKFLOW_CHANGED`, `GIT_HEAD_CHANGED` | Invalidate cached workflow or Git views after source changes. |

Event handling is deliberately resilient. One subscriber failure is logged and
isolated; it must not prevent later subscribers from receiving the same event.
This keeps a WebSocket push failure from blocking resource release, checkpoint
updates, or scheduler progress.

The main subscriber pattern is:

| Subscriber | Typical events consumed | Result |
|---|---|---|
| `DAGScheduler` | Block terminal events and cancellation requests | Dispatch successors, cancel running work, or mark downstream blocks skipped. |
| `ResourceManager` | Terminal block events | Release GPU and CPU allocations. |
| `ProcessRegistry` | Process spawn and cancellation requests | Track active handles and terminate requested processes. |
| `CheckpointManager` | Terminal block events | Writes latest-run checkpoint state. |
| Lineage recorder | Terminal block events and run lifecycle context | Writes durable run, block, object, and port-edge records. |
| WebSocket/API handlers | Workflow and block state events | Push runtime status to clients. |

### 6.3 DAG Scheduler

`DAGScheduler` executes the workflow graph. It treats each workflow node as a
block execution unit and each edge as a typed dependency. A block can run only
after required upstream outputs are available and the resource manager allows
dispatch.

Scheduler responsibilities:

- Build an execution order from the DAG.
- Initialize block states and move ready nodes into `READY`.
- Dispatch ready blocks by creating independent async tasks.
- Await block completion through the runner result path.
- Store block outputs for downstream inputs.
- Emit terminal events for done, error, cancelled, or skipped blocks.
- Retry ready-but-resource-blocked nodes after resources are released.
- Propagate `SKIPPED` to downstream nodes whose required inputs can no longer be
  produced.

The concurrency model is event-driven. Dispatch does not wait inline for a
subprocess to finish; it starts a task and returns control to the event loop.
Independent DAG branches can therefore run in parallel, while blocks with data
dependencies still wait for their predecessors.

Cancellation also flows through the scheduler. A block cancellation request asks
the process layer to terminate the active process, moves the block to
`CANCELLED`, emits the terminal event, and marks unreachable downstream blocks
as `SKIPPED`. Workflow cancellation repeats the same pattern for every active or
pending block.

### 6.4 Checkpointing And Resource Management

The engine keeps two runtime control systems close to scheduling: latest-run
checkpointing and resource gating. Both are deliberately operational; neither is
the durable lineage record described in Section 4.5.

`CheckpointManager` saves the latest known workflow state after terminal block
events. `WorkflowCheckpoint` records block states, intermediate references,
pending block information, config snapshot, and skip reasons. The checkpoint
lives under `<project>/.scistudio/pause/` and is a **latest-run recovery artifact**.
It supports pause/resume, crash recovery, and run-from-here on the latest
available intermediate state.

A checkpoint is not a historical run database. Once newer runs overwrite
intermediate outputs, older intermediate states are not guaranteed to be
loadable from the checkpoint. Historical reproducibility comes from the lineage
recipe plus re-execution, not from storing every intermediate payload forever.

`ResourceManager` gates dispatch before a block starts. It tracks discrete GPU
slots and CPU worker budget, and it checks current system memory before allowing
new subprocesses to launch. Resource release happens from terminal events and
process-exit events.

The resource model has three layers:

| Layer | Responsibility |
|---|---|
| Dispatch gating | `ResourceManager` decides whether a block may start based on GPU, CPU, and memory state. |
| Block-local memory behavior | Collection helpers, lazy loading, and block logic decide how much data is loaded at once. |
| OS/process fallback | If a subprocess crashes or is killed by the OS, the runner observes the non-zero exit and the scheduler marks the block failed. |

Blocks declare resource needs through resource request metadata. The scheduler
uses those declarations as an admission-control signal, not as proof that a
scientific method is safe or efficient.

### 6.5 Process Lifecycle Management

SciStudio runs blocks in isolated subprocesses per ADR-017 and ADR-019. The goal
is simple: a block can crash, be cancelled, or exhaust memory without taking
down the engine process.

The process lifecycle components are:

| Component | Role |
|---|---|
| `BlockRunner` | Abstract runner interface used by the scheduler. |
| `LocalRunner` | Default runner that executes blocks as local subprocesses. |
| `RunHandle` | Scheduler-level handle for a running block, including process and result tracking. |
| `ProcessHandle` | Cross-platform abstraction for observing, terminating, and killing one process tree. |
| `ProcessRegistry` | Registry of active process handles, used for lookup, cancellation, and shutdown. |

All subprocess creation goes through the process lifecycle layer. On POSIX
systems, child processes are grouped so termination can reach the process tree.
On Windows, the implementation uses the platform process primitives needed to
terminate the launched process tree. Platform details stay behind
`ProcessHandle`; the scheduler only asks for cancellation or observes terminal
state.

The worker-to-engine result path uses a stdout envelope. A successful worker
returns serialized outputs and environment information. A worker can also report
a non-DONE terminal state through the terminal-state path, which `LocalRunner`
turns into `BlockTerminalStateReportedError` so the scheduler finalizes the
block as cancelled, errored, or skipped instead of treating empty output as a
successful run.

### 6.6 Data Flow And Collection Management

All inter-block values move as `Collection` transport units from ADR-020. A
single object is represented as a length-one collection; multiple objects are a
longer homogeneous collection. `Collection` is not a base data type. Its type
identity for ports comes from the item type.

Engine-level rules:

- The scheduler schedules block nodes, not collection items.
- The engine treats each collection as an opaque transport unit.
- Port validation compares the collection item type with the port's accepted
  data types.
- Worker serialization preserves the collection envelope across subprocess
  boundaries.
- Checkpoint and lineage paths preserve collection structure through ordered
  item references.

Block-level rules:

- A block decides whether to process one item, iterate over many items, or treat
  the whole collection as a unit.
- Per-item error strategy belongs inside the block.
- Memory safety comes from lazy loading, chunking, item-wise flushing, and block
  helper utilities.
- CodeBlock may present collections to user scripts as native single objects or
  lazy iterable lists so users do not need to handle framework internals.

Collection utility blocks such as merge, split, filter, and slice operate at the
workflow level. They make collection structure explicit in the graph instead of
hiding batching behavior inside the scheduler.

### 6.7 Error Management

The engine reports errors at block and workflow boundaries. It does not try to
interpret scientific partial failure inside a collection unless the block
chooses to expose that failure as an output or terminal state.

Main error classes:

| Error class | Engine behavior |
|---|---|
| Block exception | Mark block `ERROR`, emit `BLOCK_ERROR`, release resources, checkpoint, and skip unreachable downstream blocks. |
| User cancellation | Mark block or workflow `CANCELLED`, terminate active processes, emit cancellation events, and skip dependent work. |
| Missing required upstream output | Mark downstream block `SKIPPED` with a skip reason. |
| Subprocess crash or OS kill | The runner observes the non-zero subprocess exit, marks the block `ERROR`, and propagates skip where needed. |
| Subscriber failure | `EventBus` logs and isolates the callback failure so other subscribers still run. |
| Block-reported terminal state | `LocalRunner` converts the worker report into scheduler-visible terminal handling. |

For collection processing, partial success is a block contract. A robust block
may catch per-item failures, emit a smaller collection, or return a structured
artifact describing rejected items. A block that crashes before returning loses
that block's in-process partial work, while already-flushed outputs and the
latest checkpoint remain available according to their normal storage rules.

This error model keeps the runtime predictable: the engine owns block-level
state, process cleanup, skip propagation, and event delivery; blocks own domain
recovery choices.

---

## 7. Layer 4: AI Agents

Layer 4 is the production AI-agent layer. It lets a scientist work with a
Claude Code or Codex agent inside a SciStudio project while keeping the agent on
SciStudio's normal workflow, data, lineage, and project-management rails.

ADR-040 is the governing decision for this layer. The older model treated the
agent mostly as an embedded chat surface with a static prompt and a loose tool
catalog. The current model treats agent reliability as a project-level stack:
project instructions, task skills, FastMCP-backed tools, project context,
provider configuration, and deterministic hooks where the provider supports
them.

### 7.1 Production Agent Boundary

ADR-040 separates two environments that must not be confused:

| Environment | Meaning | Governed here? |
|---|---|---|
| Development environment | The SciStudio source repository used by framework contributors. | No. Contributor agents follow repository AI developer rules, gate records, ADR workflow, and source-repo policy. |
| Production environment | A user's SciStudio project workspace opened through the GUI or created by `scistudio init`. | Yes. This layer governs the agent that helps the user build, run, inspect, and maintain project workflows. |

Production agents work in the user's project root. Their job is to help with
scientific workflow authoring, custom block creation, run debugging, data
inspection, and project questions. They should use SciStudio semantic surfaces for
workflow and data operations instead of bypassing the GUI and runtime through
ad hoc shell commands.

This boundary matters because production agents and development agents need very
different instructions. A production agent should understand workflows, blocks,
data refs, lineage, and project files. It should not inherit the full SciStudio
source-repository contributor process.

### 7.2 Agent Runtime

The GUI opens agent sessions as PTY-backed tabs inside the active project.
Provider-specific launch code is intentionally thin:

| Provider | Runtime shape |
|---|---|
| Claude Code | Spawned in the project root with SciStudio MCP config and composed project prompt. |
| Codex | Spawned in the project root and configured through project-scope Codex files. |

The PTY model keeps the upstream provider responsible for the agent loop,
authentication, transcript behavior, and provider-native UX. SciStudio is
responsible for project anchoring, MCP availability, project context, and the
files that steer provider behavior.

Agent sessions are separate from workflow execution. The agent can author or
modify workflow definitions, inspect runs, create custom blocks, or participate
in an AIBlock, but the workflow runtime remains the source of execution truth.
When an agent starts a workflow run, observes outputs, or updates block config,
those actions still flow through the same backend, registry, lineage, and Git
surfaces as human-initiated actions.

### 7.3 MCP Tool Surface

The MCP surface is the agent's semantic interface to SciStudio. ADR-040 moves this
surface to a FastMCP-backed implementation so schemas, descriptions, and return
models are generated from typed tool definitions rather than hand-written loose
JSON-RPC descriptions.

The MCP layer is used for operations that need SciStudio semantics:

- discovering blocks and data types;
- reading, validating, and writing workflow definitions;
- starting, cancelling, or inspecting runs;
- scaffolding and reloading custom blocks;
- inspecting data references, previews, and lineage;
- reading project-aware documentation or project state.

MCP is served by the running SciStudio backend. During FastAPI startup, the API
process creates the FastMCP-backed `MCPServer`, installs a project-aware runtime
context, and binds a project-local transport. On POSIX systems this transport is
a Unix socket under the active project's `.scistudio/` directory. On Windows it is
a loopback TCP listener, with the chosen port written beside the project-local
socket sentinel so bridge processes can discover it.

Agent providers do not import SciStudio internals directly. They connect through
provider-specific MCP configuration:

| Provider | How it reaches the MCP server |
|---|---|
| Claude Code | SciStudio writes `<project>/.scistudio/mcp.json`; the spawned `claude` process receives that config and invokes `scistudio mcp-bridge`, which forwards MCP traffic to the backend server. |
| Codex | SciStudio writes `<project>/.codex/config.toml`; Codex discovers the project-scope MCP entry and invokes the same bridge path. |
| Standalone bridge | When no live backend socket is available, `scistudio mcp-bridge` can build a minimal project-scoped MCP runtime for read-oriented tooling, while backend-dependent run control reports that the SciStudio backend must be running. |

Tool handlers receive the same project root, block registry, type registry, run
state, and event bus context that the backend uses. This is why MCP calls can
validate workflows, reload blocks, start runs, inspect lineage, and reflect live
runtime state instead of operating as disconnected file edits.

The production MCP surface contains 33 tools:

| Area | MCP tool | Purpose | Access |
|---|---|---|---|
| Workflow | <code>mcp&#95;&#95;scistudio&#95;&#95;list_blocks</code> | List registered blocks and palette metadata. | Read |
| Workflow | <code>mcp&#95;&#95;scistudio&#95;&#95;get_block_schema</code> | Read one block's ports, config schema, and description. | Read |
| Workflow | <code>mcp&#95;&#95;scistudio&#95;&#95;list_types</code> | List registered data types for port and workflow authoring. | Read |
| Workflow | <code>mcp&#95;&#95;scistudio&#95;&#95;get_workflow</code> | Read a project workflow definition. | Read |
| Workflow | <code>mcp&#95;&#95;scistudio&#95;&#95;validate_workflow</code> | Validate workflow structure before execution or save. | Read |
| Workflow | <code>mcp&#95;&#95;scistudio&#95;&#95;write_workflow</code> | Persist schema-validated workflow YAML. | Write |
| Workflow | <code>mcp&#95;&#95;scistudio&#95;&#95;run_workflow</code> | Start a workflow run through the SciStudio runtime. | Write |
| Workflow | <code>mcp&#95;&#95;scistudio&#95;&#95;cancel_run</code> | Cancel an active workflow run. | Write |
| Workflow | <code>mcp&#95;&#95;scistudio&#95;&#95;get_run_status</code> | Poll run state, block state, and terminal outcome. | Read |
| Workflow | <code>mcp&#95;&#95;scistudio&#95;&#95;finish_ai_block</code> | Signal completion from inside an AIBlock run. | Write |
| Workflow | <code>mcp&#95;&#95;scistudio&#95;&#95;get_active_workflow_context</code> | Read the workflow id the GUI editor currently has open (ADR-040 Addendum 5). | Read |
| Authoring | <code>mcp&#95;&#95;scistudio&#95;&#95;read_block_source</code> | Read project or package block source for reuse or inspection. | Read |
| Authoring | <code>mcp&#95;&#95;scistudio&#95;&#95;list_block_examples</code> | List scaffold/example block templates. | Read |
| Authoring | <code>mcp&#95;&#95;scistudio&#95;&#95;scaffold_block</code> | Create a custom block skeleton with typed ports and config. | Write |
| Authoring | <code>mcp&#95;&#95;scistudio&#95;&#95;reload_blocks</code> | Reload project-local blocks after authoring changes. | Write |
| Authoring | <code>mcp&#95;&#95;scistudio&#95;&#95;run_block_tests</code> | Run block-level verification for authored blocks. | Write |
| Inspection | <code>mcp&#95;&#95;scistudio&#95;&#95;get_block_output</code> | Locate output references for a block or run. | Read |
| Inspection | <code>mcp&#95;&#95;scistudio&#95;&#95;inspect_data</code> | Inspect data reference metadata without loading full payloads. | Read |
| Inspection | <code>mcp&#95;&#95;scistudio&#95;&#95;preview_data</code> | Produce a type-appropriate preview for UI or agent review. | Read |
| Inspection | <code>mcp&#95;&#95;scistudio&#95;&#95;get_lineage</code> | Query lineage records for runs, blocks, and data objects. | Read |
| Inspection | <code>mcp&#95;&#95;scistudio&#95;&#95;get_block_config</code> | Read a block instance's effective configuration. | Read |
| Inspection | <code>mcp&#95;&#95;scistudio&#95;&#95;update_block_config</code> | Update a block config through schema-aware workflow mutation. | Write |
| Inspection | <code>mcp&#95;&#95;scistudio&#95;&#95;get_block_logs</code> | Read block or run logs for debugging. | Read |
| Plot | <code>mcp&#95;&#95;scistudio&#95;&#95;list_plot_targets</code> | List workflow outputs a plot can bind to (node id + output port). | Read |
| Plot | <code>mcp&#95;&#95;scistudio&#95;&#95;list_plot_examples</code> | List available plot scaffold/example templates. | Read |
| Plot | <code>mcp&#95;&#95;scistudio&#95;&#95;scaffold_plot</code> | Create a preview-only plot job (manifest + render script) bound to a workflow output. | Write |
| Plot | <code>mcp&#95;&#95;scistudio&#95;&#95;read_plot_source</code> | Read a plot's manifest and render script. | Read |
| Plot | <code>mcp&#95;&#95;scistudio&#95;&#95;validate_plot</code> | Validate a plot manifest and its workflow-output binding. | Read |
| Plot | <code>mcp&#95;&#95;scistudio&#95;&#95;run_plot_job</code> | Render a plot preview through the plot harness. | Write |
| Project QA | <code>mcp&#95;&#95;scistudio&#95;&#95;search_docs</code> | Search project and SciStudio documentation. | Read |
| Project QA | <code>mcp&#95;&#95;scistudio&#95;&#95;get_doc</code> | Read a selected documentation page or section. | Read |
| Project QA | <code>mcp&#95;&#95;scistudio&#95;&#95;list_data</code> | List project data files and references. | Read |
| Project QA | <code>mcp&#95;&#95;scistudio&#95;&#95;get_project_info</code> | Read project metadata, paths, and high-level state. | Read |

The important architectural rule is not the exact tool list. The rule is that
agent actions touching **blocks**, **workflows**, **runs**, **data**, or
**lineage** should go through MCP-backed SciStudio contracts. Generic file reading
can remain provider-native, but direct edits to workflow YAML or shelling out to
alternate runtime paths bypass validation, GUI refresh, and lineage expectations.

Tool results may include next-step guidance and warnings. This creates a local
feedback loop: after a write-like action, the agent is nudged toward validation,
status polling, reload, or type correction without requiring another global
prompt rewrite.

### 7.4 Project Context And Skills

Agent behavior is shaped at session start by project-aware context. The composed
prompt can include project facts such as project name, project root, available
workflows, installed plugins, Git state, and recently modified workflow files.
This makes the agent aware of the actual project instead of operating from a
static generic SciStudio prompt.

ADR-040 also replaces a monolithic skill file with task-scoped skills. The base
SciStudio skill acts as a compact index, while task skills provide detailed
instructions only when relevant.

| Skill area | Use |
|---|---|
| Workflow building | Turn a user's analysis intent into a valid workflow graph. |
| Custom block authoring | Reuse existing blocks first, then scaffold new project-specific blocks when needed. |
| Run debugging | Inspect failed or cancelled runs and suggest concrete repairs. |
| Data inspection | Explore data references, previews, lineage, and output meaning. |
| Project QA | Answer questions about project structure, files, configuration, and documentation. |

Skills are packaged with SciStudio so wheel installs can provision them reliably.
Project provisioning writes provider-specific skill trees so Claude Code and
Codex can discover the same task guidance.

### 7.5 Project Provisioning

Production agent reliability is installed into the user's project, not into the
SciStudio source repository. Project creation and project opening perform an
idempotent provisioning pass.

Provisioned assets include:

| Asset | Purpose |
|---|---|
| `CLAUDE.md` | Project-level instructions for Claude Code. |
| `AGENTS.md` | Equivalent project-level instructions for Codex and generic agents. |
| `.claude/settings.json` | Claude Code hook configuration. |
| `.claude/hooks/` | Hook scripts that block or flag known unsafe production-agent actions. |
| `.claude/skills/` | Claude-discoverable SciStudio task skills. |
| `.agents/skills/` | Codex/generic-agent discoverable SciStudio task skills. |
| `.codex/config.toml` | Project-scope Codex MCP and provider configuration. |

Provisioning is non-fatal and conservative. Missing assets are created; existing
user-edited files are not silently overwritten. This lets older projects receive
the reliability stack while preserving user customizations.

The same asset model is also available through install commands for power users
who want to configure user-scope or project-scope provider assets manually.

### 7.6 Hooks And Guardrails

Hooks are a defense-in-depth layer for production projects. They do not replace
MCP schemas, skills, or human review, but they catch known drift patterns at the
moment a provider attempts a risky action.

Key behaviors:

- block direct shell use of the SciStudio CLI when an MCP-backed path should be
  used instead;
- block direct edits to workflow YAML that would bypass schema-aware workflow
  writing;
- require block discovery before authoring a new custom block;
- remind agents to poll run status after starting a run;
- flag overly generic or unregistered port types in custom block code.

Hook coverage is provider-dependent. Claude Code uses the project `.claude`
hook configuration directly. Codex discovers its project config separately and
may support a different subset of hook behavior depending on provider version.
The architecture therefore treats hooks as enforcement where available and
advisory where provider support is weaker.

### 7.7 Provider Parity

ADR-040 makes Claude Code and Codex first-class production-agent providers. They
have different discovery mechanisms, so SciStudio provisions both instead of
pretending one provider's files will govern the other.

Parity principles:

- Both providers get project-level instructions.
- Both providers get SciStudio task skills.
- Both providers get MCP configuration for the active project.
- Both providers run inside the project root.
- Both providers are expected to use SciStudio semantic operations for workflows,
  blocks, runs, and data.

The implementation details differ. Claude Code can receive explicit MCP and
prompt arguments at spawn time. Codex relies more heavily on project-scope
configuration and standard discovery files. The architectural contract is that a
fresh SciStudio project should not require a user to manually wire basic agent
access before an embedded production agent can help.

### 7.8 AIBlock Relationship

`AIBlock` is still a workflow block, not the whole agent layer. It lets an agent
participate as a node in a workflow graph, with declared inputs, declared
outputs, and workflow-visible terminal state. That makes AI participation
composable with ordinary blocks rather than a separate side channel.

The distinction is:

| Surface | Role |
|---|---|
| Agent tab | Interactive project assistant for editing, inspecting, debugging, and explaining. |
| AIBlock | Workflow node that invokes an agent-like step as part of a run. |
| MCP layer | Shared semantic tool surface used by agents to interact with SciStudio safely. |
| Runtime engine | Source of truth for execution state, events, checkpoints, and lineage. |

An example AIBlock use is **experiment metadata extraction from filenames**.
A workflow may load a collection of microscopy image artifacts whose filenames
encode experiment structure, such as treatment group, sample id, replicate id,
time point, or imaging channel. An AIBlock can receive the file references and a
prompt such as:

> Infer experiment metadata from the input filenames. Produce a CSV table with
> columns `file`, `group`, `sample`, `replicate`, `timepoint`, `channel`, and
> `confidence`. Flag ambiguous names instead of guessing silently.

The block declares one input collection and one output table artifact. During
execution, the engine writes an AIBlock run manifest containing the block name,
per-port inputs, expected output paths, declared output types, the user prompt,
and the completion contract. The spawned agent reads that manifest, writes the
CSV to the declared output path, then calls the AIBlock completion MCP tool so the workflow can continue.

The AIBlock agent differs from a normal agent tab:

| Aspect | Normal agent tab | AIBlock agent |
|---|---|---|
| Trigger | User opens or talks to a chat tab. | Workflow execution reaches an AIBlock node. |
| Scope | Open-ended project assistance. | One declared block task with typed inputs and outputs. |
| Context | Project prompt, project context, skills, MCP, and user conversation. | Same production agent context plus an AIBlock manifest and initial task message. |
| I/O contract | No declared workflow ports. | Input and output ports are part of the workflow graph. |
| Completion | User and agent decide when the conversation is done. | Agent must produce declared outputs and signal completion. |
| Failure handling | Conversation error or user-visible failed action. | Block becomes `ERROR`, `CANCELLED`, or `SKIPPED` according to runtime rules. |

In the current implementation, the AIBlock does not replace the production
agent system prompt with a separate provider prompt. It reuses the same
project-aware prompt and MCP configuration where the provider supports them,
then adds AIBlock-specific runtime context through the initial message and
manifest. Functionally, that manifest acts as the extra block-scoped instruction
layer: it tells the agent where inputs are, what outputs are expected, what the
deadline is, and how to finish the block.

This keeps AI-native behavior inside the same architecture as the rest of
SciStudio. Agents can help build and improve workflows, and agents can also appear
inside workflows, but neither case bypasses block contracts, data contracts,
lineage, or project governance.

---

## 8. Layer 5: API

### 8.1 API Role And Scope

The **API layer** is the entry point used by the frontend, agents, and external
clients to reach the SciStudio runtime. It presents project, workflow, block,
data, run, and agent operations through stable service boundaries.

The API layer does **not** own workflow truth. Workflow structure, execution
state, type validation, lineage, and artifact records remain runtime-owned. The
API layer also does **not** perform scientific computation or replace the
engine. It validates requests, calls runtime services, serializes responses, and
streams runtime events to clients.

### 8.2 REST Resources

REST resources are organized by domain instead of by a long endpoint list:

| Resource domain | Responsibility |
|---|---|
| **Projects** | Opens, creates, lists, and updates project workspaces and project-scoped files. |
| **Workflows** | Reads and mutates workflow definitions while preserving backend validation as the source of truth. |
| **Blocks** | Exposes the block registry, block schemas, templates, and connection validation. |
| **Data previews** | Provides lightweight, type-aware previews and metadata for data objects without loading full artifacts into the frontend. |
| **Runs** | Lists recorded runs, exposes run details, and starts runtime-approved rerun flows from recorded state. |
| **Agent status and permissions** | Reports provider availability, terminal-agent status, and pending human approval decisions. |

These resources are **facades over runtime contracts**. A REST response may be
formatted for the frontend, but the underlying meaning comes from workflow,
block, data, run, and permission schemas owned by the backend.

### 8.3 Realtime Updates

Realtime channels use **WebSocket** and streaming responses to keep clients in
sync with runtime activity. They carry block state, run progress, interactive
prompts, workflow changes, Git-head changes, logs, and agent-terminal updates.
The WebSocket protocol also supports an application-level `ping` -> `pong`
heartbeat so the browser can detect an OPEN-but-stale socket and reconnect.

The event source is the backend **EventBus** and runtime services. The frontend
does not infer execution state locally, manufacture block transitions, or treat
its cached view as authoritative. When the frontend receives a realtime update,
it reconciles its display with backend-emitted events.

### 8.4 Agent-Facing MCP

**MCP** is the agent-facing API. **REST** and **WebSocket** are primarily
frontend-facing APIs. Both surfaces share the same backend runtime context:
project root, block registry, type registry, workflow state, run state, event
bus, and permission checks.

Agents should use MCP or approved API surfaces when creating workflows,
editing blocks, reading outputs, tuning configuration, inspecting lineage, or
starting runs. They should not bypass SciStudio by editing workflow truth directly
or by invoking the CLI as an untracked control plane. This keeps agent work
inside the same schemas, lineage boundaries, permission model, and audit trail
as frontend-driven work.

### 8.5 Static App Serving And Contract Boundaries

FastAPI also serves the bundled **SPA** for packaged desktop and local-server
use. Backend routes under `/api/*` and WebSocket routes are handled by backend
route handlers. Other browser paths fall back to the SPA so client-side routing
can open project, workflow, run, and settings views directly.

The stable API contracts are the **workflow**, **block**, **data**, and **run**
schemas plus the runtime events emitted by the backend. Frontend state slices,
React providers, cache keys, component props, terminal-provider internals, and
other UI implementation details are not API contracts.

---

## 9. Layer 6: Frontend

The frontend is the human workspace for SciStudio. It presents the backend-owned
project, workflow, execution, preview, lineage, Git, and agent state in one
local application shell. It does **not** own workflow truth; it edits through API
contracts and reconciles its view from backend responses and realtime events.

### 9.1 Technology Stack

| Area | Current frontend choice | Role |
|---|---|---|
| **Application framework** | React 18 + TypeScript + Vite | Local SPA shell, fast development loop, typed UI state. |
| **Workflow canvas** | ReactFlow | Node graph editor, typed edges, minimap, controls, drag/drop block creation. |
| **Resizable layout** | react-resizable-panels | Horizontal app columns and vertical canvas/bottom-panel split. |
| **State management** | Zustand slices | Project, workflow, execution, UI, palette, preview, tabs, terminal tabs, lineage, and Git state. |
| **UI primitives** | shadcn-style Radix wrappers, Tailwind, lucide-react | Buttons, menus, tabs, tooltips, separators, icons, and responsive styling. |
| **Editors and terminals** | Monaco and xterm, both lazy-loaded | Project file editing, workflow source viewing, and embedded agent terminals. |
| **Data visualization** | Plotly and custom image/table viewers | Charts, server-paginated tables, image LUTs, zoom/pan, and slice navigation. |

### 9.2 Application Shell

The current shell has a compact fixed toolbar and a resizable three-column
workspace. When no project is open, the body shows a **Welcome** screen with New
Project, Open Project, and recent projects.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ SciStudio · project/workflow title │ Projects │ New/Import/Save │ Run controls │ WS Logs │
├───────────────┬───────────────────────────────────────────────┬──────────────┤
│ Blocks/Project│ Main tabs: workflow canvases + file editors    │ Preview      │
│ sidebar       ├───────────────────────────────────────────────┤ panel        │
│               │ ReactFlow canvas or Monaco editor              │              │
│ 📦 Blocks     │                                               │ 🖼 output     │
│ 📁 Project    │                                               │ previews     │
│               ├───────────────────────────────────────────────┤              │
│               │ 💬 AI Chat │ 📋 Config │ 📜 Logs │ 📈 Plots │ 🔗 Lineage │ Git │
└───────────────┴───────────────────────────────────────────────┴──────────────┘
```

**Toolbar** behavior depends on the active main tab. Workflow tabs show run,
pause, stop, reset, delete, reload, note, group, and view-source actions. File
editor tabs keep the toolbar focused on New, Import, and Save so workflow-only
actions do not apply to source files.

**Git controls** live in the bottom Git tab rather than in the toolbar. This
keeps the toolbar usable on narrow screens and makes commit history, branch
graphs, stashes, commits, and merge flows reachable from a dedicated surface.

### 9.3 Navigation And Project Surface

The left sidebar has two modes:

| Mode | Purpose |
|---|---|
| **Blocks** | Searchable block palette populated from the backend block registry. Dragging a block creates a workflow node, with default parameters filled where the block category requires them. |
| **Project** | Project tree browser with lazy directory loading, file icons, context-menu copy/reveal actions, workflow loading, and editable file opening. |

The project tree watches backend file-change signals. When an agent or external
editor changes a workflow file, the frontend refreshes the project tree and, for
new workflow files, can open the workflow tab automatically.

The center workspace has a browser-style main tab strip:

| Main tab kind | What it hosts |
|---|---|
| **Workflow** | A ReactFlow canvas snapshot for one open workflow. |
| **File** | A Monaco editor tab for project-local editable files. |
| **Workflow source** | A read-only Monaco view of the active workflow YAML, opened from View source. |

Dirty markers are per tab. Closing a dirty workflow or file tab asks for user
confirmation. File editor tabs are loaded lazily from the backend and save back
through the project-file API.

### 9.4 Workflow Canvas

The workflow canvas is a controlled ReactFlow surface. It renders backend
workflow nodes and edges, but local drag state is used while the user moves a
node so the UI follows the cursor smoothly before the final layout is written
back to the workflow store.

Canvas responsibilities:

- **Drag/drop block creation** from the palette into canvas coordinates.
- **Backend-validated connections** before an edge is accepted.
- **Typed edges** colored from the source port type.
- **Annotation nodes** and **group nodes** for workflow readability.
- **MiniMap**, pan/zoom controls, and a type legend for active data types.
- **Delete**, run-block, restart-block, and error-click actions routed back to
  the application shell.

The canvas can collapse the bottom panel when the user clicks empty space. The
bottom panel pin disables that behavior, which is especially useful while an AI
terminal session is open.

### 9.5 Block Nodes And Ports

Per ADR-050, block nodes on the workflow canvas are fixed-size **square
topology glyphs** (default 104×104 CSS px; width equals height). The node body
shows block identity only — a centered block-kind category icon, with a single
unified status surface in its bottom-right corner. The display label renders
outside the body, below the square (capped to two visual lines). The body never
grows for config fields, port count, runtime messages, errors, warnings, or
action buttons. Run/restart/delete actions float in a toolbar above the square
on hover/selected and do not change the node's measured geometry.

```
          ┌───────────────┐
          │  ▶   ↻   🗑   │   ← action toolbar: floats above on hover / selected
          └───────────────┘
      ┌────────────────────┐
   ──◯│                    │◯──   ← input ports (left rail) / output ports (right rail)
      │          ▣         │      ← category icon, centered — block identity only
   ──◯│                (!) │◯──   ← unified status surface, bottom-right corner
      └────────────────────┘
              Cellpose            ← display label outside, below the node
              Segment               (max two lines, truncated)

  fixed 104×104; body never grows; rails may extend for port-heavy blocks; +/- for variadic
```

| Node area | Behavior |
|---|---|
| **Body** | Square, fixed-size. Shows a centered category icon and, in its bottom-right corner, the unified status surface. The display label renders outside, below the node. No inline configuration, no status footer, no inline error/warning text. |
| **Action toolbar** | Run, restart, and delete float in a toolbar above the square on hover/selected; they do not consume body space or change geometry. |
| **Ports** | Input ports on the left rail, output ports on the right rail, colored by accepted type. Rails may extend beyond the square for port-heavy blocks; the body stays fixed. Dynamic ports resolve from the active configuration value. Port labels render outside the body (hover/selected/zoom/accessibility). |
| **Variadic ports** | Blocks with configurable port counts keep the canvas add/remove (`+`/`-`) controls (ADR-029); removing a connected port preserves the existing disconnect confirmation. Full port naming/type editing lives in the BottomPanel port editor. |
| **Unified status surface** | One fixed-geometry surface in the node's bottom-right corner for runtime state (idle, ready, running, paused, done, error, cancelled, skipped) and problem severity (none, warning, error). Error has highest priority and routes to Logs; warning routes to the BottomPanel Config detail. Status rendering never changes node width or height. |

Computational configuration — schema-driven fields, capability selectors,
file/directory pickers, CodeBlock config, full variadic port editing, and
lossy-save/validation detail — is owned by the **BottomPanel Config** tab, not
the node body (ADR-050 §2.3). Selecting a node opens its config there.

The canvas also provides two readability controls (ADR-050 §3): **focus mode**,
a frontend-only view state that dims or hides nodes outside the selected node's
neighborhood without changing the workflow definition, and a **tidy** action
that computes deterministic left-to-right positions through a layered
graph-layout adapter (`elkjs`) and writes only `node.layout` metadata.

Port colors come from the frontend type-color map plus backend-supplied type
hierarchy. Known scientific types use stable colors; plugin or unknown types use
a deterministic hash color. Subtypes can use ring colors so, for example, an
image-derived type can share the image fill color while remaining visually
separable.

### 9.6 Previewer System

The previewer system is the frontend module that displays a block's output
data, and it is plugin-extensible. The core ships a set of generic previewers
keyed by data kind, and plugins — or a project — extend it with richer
previewers for specific data types. When the selected block has previewable
outputs, the right-hand preview panel renders them, deriving user-facing labels
from output metadata where possible (so file outputs can show names like source
filenames instead of opaque data references).

**Core previewers.** The core provides one generic previewer per data kind.
They are deliberately generic: each reads only the bounded preview payload and
its metadata, and surfaces flags (sampled, truncated, cached, …) so the user can
tell whether the displayed data is complete.

| Core previewer | UI behavior |
|---|---|
| **DataFrame** | Paginated, sortable table with sticky headers and page controls. |
| **Array** | Generic numeric inspection: shape, dtype, and axes, rendered as a scalar, a 1-D chart, or a 2-D heatmap table (actual values with a per-cell background color and a min–max legend), plus a per-axis slice selector for every non-displayed dimension. |
| **Series** | Line or scatter chart for a one-dimensional series. |
| **Text** | Read-only preformatted text. |
| **Composite** | Slot list where each slot exposes its own previewable value. |
| **Collection** | Entry list where each item opens its own preview. |
| **Plot** | Renders a generated plot artifact, with export. |
| **Artifact** | File-path and MIME-type fallback when no richer previewer applies. |

**Plugin previewers.** Plugins extend the system with richer, type-specific
previewers. For example, an imaging package contributes an image viewer with
LUT, channel, and label semantics that the generic Array previewer deliberately
omits. The generic core previewers remain the baseline for the data kinds a
plugin does not specialize.

**Project previewers.** The same extension works at the project level: a user
can add a previewer for a project-local data type without publishing a plugin.

How previewers are registered, discovered, and prioritized is covered in §12
(Extensibility).

### 9.7 Bottom Panel

The bottom panel is a first-class work surface, not a log drawer. It is
resizable, collapsible, and pinnable.

| Tab | Current role |
|---|---|
| **💬 AI Chat** | Multi-tab embedded agent terminal. User-created tabs start from setup; AI Block tabs can be opened by the engine and keep block status in the tab strip. Inactive terminal tabs stay mounted so subprocesses and WebSocket sessions survive tab switches. |
| **📋 Config** | Full schema-driven configuration editor for the selected block. Variadic ports, format capabilities, CodeBlock ports, and environment variables are edited here when the schema requires richer controls than inline node config. |
| **📜 Logs** | Real-time log viewer backed by the log stream, with level filtering and unread count when the user is not viewing Logs. |
| **📈 Plots** | Card-style panel for the workflow-wide plot list. Each card shows the plot's name, linked block (node id + output port), language, and a broken badge when its bound output is missing, with relink, run, and new-plot actions. |
| **🔗 Lineage** | Two-pane run history and run detail surface. It fetches runs on mount, refreshes after workflow completion, and owns methods-export and rerun dialogs. |
| **Git** | Branch picker, status badge, commit dialog, stash panel, commit history, branch graph, and merge-entry point. Long-running merge resolution is mounted at the application level so it survives tab switches and project visibility changes. |

Interactive block prompts appear as modal flows when the backend pauses for user
input, including data routing and pair editing. Completion and cancellation go
back through the WebSocket control channel instead of being inferred by the UI.

### 9.8 Realtime State Flow

The frontend listens to two realtime channels:

| Channel | Frontend use |
|---|---|
| **WebSocket** | Workflow events, block state, output references, interactive prompts, workflow file changes, Git HEAD changes, and AI Block terminal lifecycle events. |
| **Log stream** | Execution log rows scoped to the active workflow and, when Logs is focused on a block, the selected block. |

Realtime events update Zustand slices, not independent frontend truth. For
example, workflow-file changes from the backend can refresh the loaded workflow,
clear a deleted workflow, open newly-created workflows, bump the project-tree
refresh counter, or invalidate Git history. Execution events update block state,
outputs, errors, log rows, interactive prompts, and running status.

### 9.9 Frontend Boundaries

The frontend may cache, debounce, and present user-friendly UI state, but stable
meaning stays in backend contracts:

- **Workflow definitions** are saved and loaded through backend workflow APIs.
- **Connections** are accepted only after backend validation.
- **Execution state** is driven by runtime events, not local simulation.
- **Data previews** are fetched by reference and rendered according to backend
  preview payloads.
- **Project files** are opened and saved through project-file APIs, with read-only
  source views kept distinct from editable file tabs.
- **Agent work** enters the frontend through MCP/API-backed events and terminal
  sessions rather than direct frontend mutation of workflow truth.

---

## 10. Plot System

### 10.1 Introduction

Plotting the scientific data a workflow produces is an essential part of
analysis. The plot system lets a user connect any block's output to a plot of
their own choosing, so they can see the statistical or analytical figure they
want at any time — without turning that visualization into a workflow step.

The system is made of **plot cards**. A plot card pairs a user-authored render
function with a binding to one block output. Plot cards reuse the block
execution structure — the same subprocess run model CodeBlock uses — but they
are **not part of the workflow DAG**: a plot is a preview-only job that never
becomes a graph node, never enters the scheduler, and never claims lineage.
Keeping exploratory, frequently-rewritten plot code out of the reproducible
data pipeline is the reason the plot system is a separate system rather than a
block, while still giving it the runtime's data access and language support.

Each plot card supports a user-defined Python or R plot function and links that
function to the output data of any block, so one output can be visualized in as
many ways as the user wants.

### 10.2 Language Support

A plot is rendered by a single user-authored `render` function that receives the
bound output as a read-only `collection` and returns a figure. Two languages are
supported:

- **Python** — `def render(collection):`, drawn with matplotlib (seaborn is
  available). It returns a matplotlib `Figure`, or a path to an image it wrote.
- **R** — `render <- function(collection)`, drawn with ggplot2 or base graphics.
  It returns a ggplot object or draws to the open device; a top-level
  `figure_size(width, height)` helper sets the figure dimensions.

Both languages run through the same harness. The runtime resolves the bound
output to its current data references, writes the user's render script together
with an input envelope into a temporary working directory, and runs it in a
subprocess (`python` for Python, `Rscript` for R). The script receives its data
lazily: the `collection` exposes `types`, `items`, and `open()` / `open_one()`
helpers that materialize native values (a DataFrame, an array, …) only when the
render function asks for them. The harness serializes the returned figure to the
plot's chosen format. Four output formats are supported — **svg** (the default),
**png**, **pdf**, and **jpeg** — constrained per plot by an allowed-formats list.

### 10.3 Linking And Relinking

A plot binds to a block output by **stable identity**, not by display label. The
plot manifest's target records the workflow path, the **node id**, and the
**output port**; the binding key is `node_id` + `output_port`. A human-readable
display label is stored for the UI but is never used to resolve the target,
because labels repeat across duplicated blocks and drift when blocks are renamed.

When the bound block is removed and recreated it receives a new node id, so the
plot's target no longer resolves and the plot is flagged **broken**. The user
relinks it through a dialog that lists the current workflow's available outputs
and points the plot at a new target.

### 10.4 Display

Plot cards live in the bottom panel's Plots tab (§9.7) as a workflow-wide list.
Each card shows the plot's name, its linked block (node id + output port), the
language, and — when its target no longer resolves — a broken badge, alongside
run, relink, and new-plot actions.

Running a plot renders its figure into the right-hand preview panel. A rendered
plot is a preview artifact of kind `plot`, shown by the previewer system (§9.6)
with the renderer appropriate to its format (inline SVG, an image for png/jpeg,
an embedded PDF) plus export. The artifact is written to the project's preview
cache: it is a transient preview, overwritten by the next run, and never a
workflow result.

### 10.5 Plot MCP Tools

Agents work with plots through six MCP tools (the Plot category of §7.3). They
mirror the user flow — discover a target, scaffold, learn from examples, read,
validate, then run:

| Tool | Purpose |
|---|---|
| `list_plot_targets` | Enumerate the workflow outputs a plot can bind to, each with a stable target id (node id + output port), so a plot never binds by label. |
| `scaffold_plot` | Create `plots/<id>/plot.yaml` and a render-script skeleton for a chosen target and language. |
| `list_plot_examples` | Return curated matplotlib/seaborn (Python) and ggplot2 (R) render examples to start from. |
| `read_plot_source` | Read an existing plot's manifest and render script for inspection or editing. |
| `validate_plot` | Check a plot's manifest, script, entrypoint, target resolution, and formats before running. |
| `mcp__scistudio__run_plot_job` | Render the plot in a subprocess and return the preview artifact; the run stays preview-only and never touches the DAG or lineage. |

---

## 11. Project Workspace Structure

A SciStudio user project is a normal filesystem directory with a small set of
well-known paths. The **project root** is identified by `project.yaml`; opening a
directory without that file is rejected as an invalid SciStudio project.

### 11.1 Created Project Layout

`ApiRuntime.create_project` creates the baseline layout below. The
`previewers/` and `plots/` directories are added on first use by the previewer
and plot subsystems rather than at project creation:

```
my_project/
├── project.yaml
├── workflows/
│   └── main.yaml
├── blocks/
├── types/
├── previewers/
├── plots/
├── data/
│   ├── raw/
│   ├── zarr/
│   ├── parquet/
│   ├── artifacts/
│   └── exchange/
├── .scistudio/
└── logs/
```

| Path | Purpose |
|---|---|
| `project.yaml` | Project identity: id, name, description, version, and creation timestamp. |
| `workflows/main.yaml` | Default workflow scaffold written with the canonical workflow serializer. |
| `workflows/` | User workflow YAML files. Workflow IDs map to `workflows/<id>.yaml`. |
| `blocks/` | Project-local custom blocks. Saving a clean Python file here can hot-reload the block registry. |
| `types/` | Project-local custom data type definitions. |
| `previewers/` | Project-local previewer drop-ins (`previewers/*.py` exposing get_previewers()); a `.scistudio/previewers.json` manifest can also register them (§9.6). Created on first use. |
| `plots/` | Plot cards — each plot is `plots/<id>/plot.yaml` plus its render script (§10). Created on first use. |
| `data/raw/` | Uploaded or imported raw files. File uploads land here after filename sanitization. |
| `data/zarr/` | Zarr-backed array-style data. |
| `data/parquet/` | Parquet-backed table-style data. |
| `data/artifacts/` | Reports, images, PDFs, and other artifact files. |
| `data/exchange/` | Exchange area used by external app/code style blocks for file handoff. |
| `.scistudio/` | Per-project runtime state. This directory is local and gitignored by default. |
| `logs/` | Project log directory reserved for user-visible logs and diagnostics. |

`notes/` is **not** part of the required scaffold. The frontend can create notes
under `notes/` when that directory exists, and otherwise falls back to creating
the note at the project root.

### 11.2 Runtime State Under `.scistudio`

The `.scistudio/` directory is for local runtime coordination. It is excluded by
the default SciStudio `.gitignore` and should not be treated as portable project
source.

| Runtime path | Producer | Purpose |
|---|---|---|
| `.scistudio/lineage.db` | API/runtime lineage initialization | SQLite lineage store for runs, block executions, data objects, and I/O joins. |
| `.scistudio/pause/<workflow_id>/` | Checkpoint manager | Single-slot pause/resume and run-from-here checkpoint files for a workflow. |
| `.scistudio/ai-block-runs/<block_execution_id>/` | AIBlock runtime | Per-AIBlock manifest, completion signals, and copied terminal transcript. |
| `.scistudio/.session-state/<session_id>/` | Agent hooks | Session markers such as whether `list_blocks` was called before block authoring. |
| `.scistudio/mcp.sock` | MCP server on POSIX | Project-local MCP socket endpoint when the backend is running. |
| `.scistudio/mcp.sock.port` | MCP server on Windows | Loopback TCP port sentinel for the project-local MCP bridge. |
| `.scistudio/mcp.json` | Claude terminal spawn path | Project-scoped MCP config written when spawning Claude Code from SciStudio. |
| `.scistudio/no_git` | User/project marker | Opt-out marker checked before automatic Git re-initialization on project open. |

Legacy root-level `metadata.db`, `lineage/`, and `checkpoints/` paths are not the
current layout. Existing files may remain in old projects, but current runtime
state is under `.scistudio/`.

### 11.3 Versioned Source Boundary

On project creation, SciStudio best-effort initializes Git with `main` as the
initial branch, writes a default `.gitignore`, stages the project, and creates an
initial commit. If Git is unavailable, project creation and open still proceed in
degraded mode.

The default `.gitignore` excludes:

- `data/`
- `.scistudio/`
- Python caches
- OS noise files
- plugin virtual environments
- editor cache files

This means workflow YAML, project metadata, project-local blocks, project-local
types, notes, and agent configuration files are source-like project artifacts
unless the user edits `.gitignore` differently. Large data payloads and local
runtime state stay outside Git by default.

### 11.4 Agent And MCP Project Assets

SciStudio provisions production-agent assets on project creation and on every
project open. Provisioning is idempotent with `force=false`: existing files are
preserved, missing files are restored, and failures are non-fatal.

```
my_project/
├── CLAUDE.md
├── AGENTS.md
├── .claude/
│   ├── settings.json
│   ├── .scistudio-provision-version
│   ├── hooks/
│   └── skills/scistudio/
├── .agents/
│   └── skills/scistudio/
└── .codex/
    └── config.toml
```

| Path | Purpose |
|---|---|
| `CLAUDE.md` | Project-scoped guide for Claude Code sessions using SciStudio. |
| `AGENTS.md` | Project-scoped guide for Codex and generic agent sessions. |
| `.claude/settings.json` | Claude Code hook matcher configuration. |
| `.claude/hooks/` | Hook scripts that steer agents toward MCP-backed workflow and block operations. |
| `.claude/skills/scistudio/` | Claude Code SciStudio skills. |
| `.agents/skills/scistudio/` | Codex/generic agent SciStudio skills. |
| `.codex/config.toml` | Project-scope Codex MCP server configuration. |

These files are different from the SciStudio source repository's developer-facing
agent rules. A user project receives short operating guidance for agents that are
using SciStudio, not the full contributor workflow for developing SciStudio itself.

### 11.5 User-Wide Extension Paths

In addition to project-local extensions, SciStudio also scans user-wide extension
locations:

```
~/.scistudio/
├── blocks/
└── types/
```

Project-local `blocks/` and `types/` are useful for one project or one family of
related analyses. User-wide locations are useful for reusable personal blocks and
types shared across projects. Packaged plugins remain the preferred mechanism for
distribution beyond one user machine.

---
## 12. Extensibility

SciStudio keeps the **core runtime** small and lets scientific capability grow
through stable extension boundaries. Two questions organize this chapter: **what
can be extended** (§12.2) and **at which level an extension ships**
(§12.3–§12.5).

### 12.1 Extension Philosophy

Extensibility follows a few rules:

- **Core owns runtime contracts.** Scheduling, validation, lineage, versioning,
  storage boundaries, and event delivery remain framework responsibilities.
- **Domain science enters at a boundary.** New capability is added as a block, a
  data type, or a previewer — not by editing core.
- **Extensions compose.** Project-local, user-wide, and packaged extensions
  register into the same registries the core uses, so one typed graph can mix
  native blocks, project-local logic, and community packages.
- **Existing tools stay useful.** Scripts, notebooks, command-line tools, GUI
  applications, and agents are wrapped as blocks instead of rewritten.

### 12.2 Extensible Modules

Three runtime modules accept extensions — **blocks**, **data types**, and
**previewers**. Each has a stable contract and a registry. Which module an
extension targets is independent of the level it ships at (§12.3).

#### 12.2.1 Blocks

Most extension work enters SciStudio as a block. The block class should match
the integration boundary:

| Block class | Use when |
|---|---|
| **Custom `Block` subclass** | The user writes project-local Python logic and wants direct control over `run()`. |
| **ProcessBlock** | The block transforms one typed item or a Collection using framework iteration. |
| **IOBlock** | The block loads or saves external file formats and participates in format-capability selection. |
| **CodeBlock** | The user runs an existing script, notebook, or analysis file with declared input/output exchange. |
| **AppBlock** | The workflow launches an external GUI or CLI application and reconstructs outputs from files. |
| **AIBlock** | An agent performs a bounded workflow step and returns declared outputs through the runtime boundary. |
| **SubWorkflowBlock** | A reusable workflow appears as a single block inside a larger workflow. |

This lets users migrate gradually: a familiar script can start as a CodeBlock,
become a custom `Block` subclass when it needs tighter integration, and later
move into a package when it becomes reusable.

#### 12.2.2 Data Types And Formats

SciStudio separates **data type identity** from **external file format**. A new
domain adds typed `DataObject` subclasses, while IO blocks declare the external
formats they can load or save.

| Concern | Extension responsibility |
|---|---|
| **File extension and format ID** | Make the external boundary explicit and stable. |
| **Target data type** | State which `DataObject` subclass is produced or consumed. |
| **Metadata fidelity** | Record whether metadata is preserved exactly, partially, or only in a sidecar. |
| **Priority and defaults** | Let the runtime choose among multiple capable loaders or savers predictably. |

The **canonical zone** remains the internal storage boundary: format conversion
happens at IO and app boundaries, and workflow internals prefer typed objects
with stable storage references.

#### 12.2.3 Previewers

A previewer renders a data type in the preview panel (§9.6). The core ships a
generic previewer per data kind; an extension adds a richer, type-specific
previewer for a particular `DataObject` type — for example an imaging package's
image viewer with LUT, channel, and label semantics. A previewer provider
exposes a get_previewers() callable returning a list of `PreviewerSpec`, and each spec binds
a target type to a frontend renderer. Project previewers take precedence over
package previewers, which take precedence over the core fallback.

### 12.3 Extension Levels

An extension to any of those modules can ship at one of three levels, trading
reach for ceremony:

| Level | Where it lives | Best for |
|---|---|---|
| **Package** | An installed Python package, shared across machines | Reusable, tested, dependency-carrying plugins and community science. |
| **User** | `~/.scistudio/`, shared across one user's projects | Personal blocks and types reused across projects on one workstation. |
| **Project** | `<project>/`, one project only | One-off preprocessing, lab-private analysis, dataset adaptation, fast prototyping. |

When the same target is provided at more than one level, the most specific level
wins: a project-local extension takes precedence, and the core implementation is
the fallback.

### 12.4 Package Extensions

Packaged extensions are distributed as Python packages and discovered through
**entry points**; the runtime registers them into the same registries the core
and local extensions use.

| Entry point group | Registers |
|---|---|
| `scistudio.blocks` | Block classes, plus optional `PackageInfo` for palette grouping. |
| `scistudio.types` | Additional `DataObject` subclasses for typed ports and storage. |
| `scistudio.previewers` | Type-specific previewers via get_previewers(). |
| `scistudio.runners` | CodeBlock runner backends for more script environments. |

Use the package level when a block or type set is reusable across projects, has
its own tests, carries external dependencies, or belongs to a community plugin.
`PackageInfo` supplies display metadata and `BlockTestHarness` validates block
contracts; both are public helper surfaces.

### 12.5 User And Project Extensions

User-wide and project-local extensions are **drop-in directories** scanned into
the registries at startup and on project open — no packaging required.

| Location | Modules | Notes |
|---|---|---|
| `<project>/blocks/`, `<project>/types/` | blocks, types | Drop-in `*.py`; saving a clean file can hot-reload the block registry. |
| `<project>/previewers/` | previewers | `*.py` exposing get_previewers(); a `.scistudio/previewers.json` manifest can also register them. |
| `~/.scistudio/blocks/`, `~/.scistudio/types/` | blocks, types | User-wide drop-ins reused across that user's projects. |

Project-local extension is the lowest-friction path: the code lives with the
dataset and workflow branch that needs it, stays inside the project repository,
and can be iterated before deciding whether it belongs in a package. User-wide
`blocks/` and `types/` cover code a user reuses across projects; previewers are
extended at the project or package level rather than user-wide.

---

## 13. Desktop App

SciStudio ships as a desktop application that bundles the frontend, the Python
backend, and a Python runtime into one installable package, so a scientist can
run it without setting up a Python environment.

### 13.1 Packaging

The desktop app is an **Electron** shell packaged with **electron-builder**. It
targets **Windows** (an NSIS installer) and **macOS** (a DMG), both x64 builds.
Packaging stages the app's resources and then produces the platform installer:

- `build:frontend` builds the SPA;
- `stage` copies resources into `desktop/resources/` — the built `frontend/`,
  the backend `src/`, a `python/` runtime (§13.2), pre-staged `packages/`, and a
  portable `git/`;
- `dist:win` / `dist:dmg` produce the platform installer.

At runtime the Electron main process starts the bundled backend rather than a
developer's environment: it launches `python -m scistudio.cli.main gui --port 0
--bundled` with `SCISTUDIO_BUNDLED=1` and the resources directory exported,
waits for the backend's JSON "ready" signal and its chosen port, and only then
opens the application window. Closing the app terminates the backend subprocess.
(The development flow — a Vite dev server plus Electron — is separate and not
part of the shipped build.)

### 13.2 Python Runtime Bundle

The app carries its own Python interpreter so it does not depend on a system
Python. On **Windows** the runtime is the official embeddable Python
distribution; on **macOS** it is a `python-build-standalone` build matched to the
machine architecture. A build script (`build-python-runtime.*`) downloads the
interpreter into `desktop/resources/python/`, enables `site-packages`,
bootstraps `pip`, installs SciStudio and its **core dependencies** (declared in
`pyproject.toml`) into the bundled `site-packages`, and verifies the key imports.

Core runtime dependencies therefore ship inside the app. **Package (plugin)
dependencies are not pre-installed into the bundle** — that keeps the app small
and keeps the bundled interpreter's `site-packages` owned by the core. Plugin
dependencies are installed separately, at the user scope, by the package
installer (§13.3).

### 13.3 Package Installer

The desktop app can install scientific block/type packages after the fact,
without a developer toolchain. Installation is a backend operation
(`POST /api/packages/local`, available only in the bundled app) that accepts a
source directory, a wheel, or a source archive, installs it, and refreshes the
block registry so the new blocks appear immediately.

**Where packages live.** Installed packages are stored at the **user scope**,
under `~/.scistudio/plugins/packages/<name>-<version>/`, each with a
`scistudio-local-package.json` manifest recording its name, version, modules, and
the Python build it was installed against. Keeping them outside the app bundle
means they survive app upgrades and never modify the bundled runtime.

**How they are discovered.** Desktop packages are **not** registered through
setuptools entry points (§12.4). Instead the registry scans the user package
directories (plus any bundled or development package directories) and imports
each source package through the package protocol (a get_block_package() entry
point, with get_blocks as a fallback). After an install the runtime refreshes the registry and
invalidates import caches so discovery is immediate.

**How dependencies are injected.** A package's dependencies are installed with
`pip install --target` into a user-scope `site-packages`, never into the bundled
interpreter. Core runtime dependencies are filtered out so a plugin can never
override the app's own SciStudio or its pinned core libraries. Because compiled
dependencies are tied to a specific Python ABI, each package records the build it
was installed against; when the bundled Python changes across an app upgrade, the
runtime repairs affected packages by reinstalling their dependencies for the new
ABI. Updating or removing a package is a directory replace or delete followed by
a registry refresh, and each package's isolated directory keeps installs from
interfering with one another.

---

## 14. Dependencies List

This section summarizes the dependency surface declared by the repository. It is not a lockfile; exact resolved versions belong to the Python and frontend package managers.

### 14.1 Python Runtime Dependencies

| Dependency | Role |
|---|---|
| `pydantic` | Data validation for configs, API models, and runtime schemas. |
| `fastapi` | Backend API framework for REST, WebSocket, and static app serving. |
| `python-multipart` | File upload parsing for API routes. |
| `uvicorn[standard]` | ASGI server used to run the API. |
| `zarr` | Chunked array storage backend. |
| `pyarrow` | Arrow and Parquet table storage and exchange. |
| `watchdog` | Filesystem change watching for project and frontend update flows. |
| `typer` | CLI command framework. |
| `xxhash` | Fast content hashing. |
| `httpx` | HTTP client utility. |
| `pyyaml` | YAML parsing and writing for workflow/project files. |
| `psutil` | OS-level memory and process monitoring. |
| `filelock` | Cross-process file locking for agent and MCP write paths. |
| `ruamel.yaml` | Round-trip YAML editing when comments and ordering must be preserved. |
| `pywinpty` | Windows-only PTY support for embedded terminal agents. |
| `fastmcp` | MCP server implementation for agent-facing tools. |

### 14.2 Optional Python Dependencies

| Extra | Dependencies | Role |
|---|---|---|
| `ai` | `anthropic`, `openai` | Optional provider SDKs for AI agent integrations. |
| `dev` | `pytest`, `pytest-cov`, `pytest-xdist`, `pytest-timeout`, `ruff`, `mypy`, `types-PyYAML`, `import-linter`, `griffe`, `pre-commit` | Test, lint, type-check, architecture, and governance tooling. |

### 14.3 Frontend Runtime Dependencies

| Dependency | Role |
|---|---|
| `react`, `react-dom` | React application runtime. |
| `@xyflow/react` | Workflow canvas and node graph interactions. |
| `zustand` | Frontend state management for UI and runtime views. |
| `@radix-ui/react-*` | Accessible UI primitives used by shadcn-style components. |
| `lucide-react` | Icon set for toolbars, buttons, and panels. |
| `react-resizable-panels` | Resizable application shell panels. |
| `@monaco-editor/react` | Embedded code editor. |
| `@xterm/xterm` and xterm addons | Embedded terminal tabs and terminal affordances. |
| `plotly.js`, `react-plotly.js` | Interactive chart preview rendering. |
| `class-variance-authority`, `clsx`, `tailwind-merge`, `tailwindcss-animate` | UI class composition and animation helpers. |

### 14.4 Frontend Build And Test Dependencies

| Dependency | Role |
|---|---|
| `typescript` | Type checking and compilation. |
| `vite`, `@vitejs/plugin-react` | Frontend build and development server. |
| `vitest`, `jsdom` | Frontend unit test runtime. |
| `@testing-library/*` | React component and user-event testing helpers. |
| `tailwindcss`, `postcss`, `autoprefixer` | Styling build pipeline. |
| `@types/*` | TypeScript type packages for React and Plotly bindings. |

### 14.5 External Tool Expectations

Some runtime paths depend on tools installed outside the Python or frontend dependency set:

| Tool family | Used by |
|---|---|
| Git | Project source versioning and workflow branch management. |
| Python, shell, R/Quarto, Jupyter, MATLAB-family interpreters | CodeBlock execution backends when a workflow uses those script formats. |
| User-selected GUI or CLI applications | AppBlock integrations. |
| Claude or Codex CLI | Terminal agent sessions and AIBlock agent runs when those providers are selected. |

---

## 15. Technology Stack Summary

| Layer | Technology | Version / Notes |
|---|---|---|
| Language | Python 3.11+ | Core runtime, CLI, API, block system, agents, and governance tooling. |
| API framework | FastAPI + Uvicorn | REST resources, WebSocket updates, static SPA serving, and local backend serving. |
| Validation | Pydantic v2 | API models, block configs, workflow/runtime schemas. |
| Workflow graph | YAML + typed registry contracts | Workflow source is stored under `workflows/`; backend/runtime remains source of truth. |
| YAML handling | PyYAML + ruamel.yaml | Standard YAML read/write plus round-trip editing where comments and order matter. |
| Event runtime | EventBus + asyncio | Runtime event propagation, WebSocket updates, run progress, prompts, and status changes. |
| File watching | watchdog | Project file and Git-head change detection bridged into runtime events. |
| Process lifecycle | ProcessHandle, ProcessRegistry | Cross-platform subprocess isolation and cancellation. |
| Lineage store | SQLite with WAL | Project-local `.scistudio/lineage.db` for runs, block executions, data objects, and block IO. |
| Storage | Zarr, Arrow/Parquet, file artifacts | Canonical storage backends for arrays, tables, and external artifacts. |
| Version control | Bundled or system git | Project workflow/source tracking, branches for parallel workflow variants, pre-run source snapshots. |
| Block discovery | Project files + Python entry points | Project-local `blocks/` and package-level `scistudio.blocks` discovery. |
| Type discovery | Core registry + Python entry points | Core `DataObject` types plus package-level `scistudio.types` extensions. |
| Code execution | CodeBlock backends | Python, POSIX shell, R/Quarto, Jupyter notebooks, and MATLAB-family files through declared exchange contracts. |
| MCP server | FastMCP | Agent-facing tool server used by Claude/Codex sessions and AIBlock runs. |
| Frontend | React 18 + TypeScript + Vite | Bundled SPA served by the backend. |
| Workflow canvas | React Flow via `@xyflow/react` | Node graph editing, typed ports, edges, annotations, grouping, and canvas controls. |
| Frontend state | Zustand | Client-side UI state; not workflow truth. |
| UI toolkit | Tailwind, Radix/shadcn-style components, lucide icons | Application shell, panels, dialogs, forms, and toolbar controls. |
| Code editor | Monaco via `@monaco-editor/react` | Project file tabs, Python lint markers, and Git conflict editing. |
| Terminal UI | xterm.js | Embedded Claude/Codex terminal tabs over PTY-backed WebSocket sessions. |
| Previewer system | Plotly + core/plugin previewers | Plugin-extensible preview of tables, arrays, series, text, composites, collections, plots, and artifacts (§9.6). |
| Plotting | matplotlib + seaborn (Python), ggplot2 + base graphics (R via Rscript) | User render functions for plot cards; SVG/PNG/PDF/JPEG output (§10). |
| Agent integration | Claude/Codex CLI + MCP bridge | Project agents and AIBlock agent runs use runtime-scoped MCP tools. |
| Desktop shell | Electron + electron-builder | Cross-platform desktop app — Windows NSIS installer, macOS DMG — wrapping the bundled backend and frontend (§13.1). |
| Bundled Python | Embeddable Python (Windows), python-build-standalone (macOS) | Self-contained interpreter so the desktop app needs no system Python (§13.2). |
| Packaging | Python wheel / PyPI | Core installation, bundled frontend assets, templates, skills, and third-party block packages. |
| Testing helpers | pytest, Vitest, BlockTestHarness | Runtime tests, frontend tests, and block package contract/smoke-test support. |
