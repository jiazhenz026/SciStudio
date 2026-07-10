# How SciStudio works

This is a user-facing overview of how SciStudio works. For full architectural
detail, see the
[SciStudio Architecture Document](https://github.com/jiazhenz026/SciStudio/blob/main/docs/architecture/ARCHITECTURE.md).

## 3. Architecture Overview

| Layer | Responsibility |
|---|---|
| Frontend | User interaction |
| API | Validated access and updates |
| AI agents | Project assistance |
| Execution engine | Scheduling and processes |
| Block system | Typed work units |
| Data foundation | Types, storage, and lineage |

Plugins extend the stack; the backend remains the source of truth.

## 4. Data Foundation

`DataObject` carries type, metadata, and storage across six forms:

| Type | Meaning | Canonical storage |
|---|---|---|
| `Array` | Named-axis N-dimensional numeric data | Zarr |
| `Series` | Labelled one-dimensional data | Arrow / Parquet |
| `DataFrame` | Schema-defined table | Arrow / Parquet |
| `Text` | Small text | Memory or filesystem |
| `Artifact` | External-format file | Filesystem |
| `CompositeData` | Named mixed-data bundle | Directory of slot backends |

**Canonical zone.** Typed objects and storage references move between blocks.
Load, save, code, app, and agent boundaries convert files.

**Inheritance.** Domain types extend basic forms: `Image` extends `Array`,
`Spectrum` extends `Series`, and `PeakTable` extends `DataFrame`. The registry
uses these relationships for port validation.

## 5. Block System

Blocks declare typed ports, configuration, and execution:

| Block type | Use |
|---|---|
| `IOBlock` | Load or save files |
| `ProcessBlock` | Transform typed data |
| `AppBlock` | Use an external GUI or CLI |
| `CodeBlock` | Run a script or notebook |
| `AIBlock` | Run a bounded AI step |
| `SubWorkflowBlock` | Reuse a workflow node |

Custom blocks extend these forms at project, user, or package scope.

## 6. Lineage and Reproducibility

| Surface | Role |
|---|---|
| Lineage record | Connects the workflow snapshot, parameters, block executions, inputs, outputs, environment, and status |
| Run history | Shows how a result was produced and which steps ran, failed, or skipped |
| Re-runs | Create linked lineage records so attempts can be inspected and compared |
| Git branches | Keep parallel workflow variants for different batches, instruments, cohorts, or experiments |

## 7. AI Agents

Four project agent surfaces:

| Surface | Role |
|---|---|
| Agent session | Interactive project help in Claude Code or Codex |
| MCP server | 34 tools for blocks, types, workflows, runs, data, lineage, plots, and project information |
| Skills | Task guidance for workflows, block authoring, debugging, data inspection, and project QA |
| `AIBlock` | Bounded graph node with typed inputs, outputs, and completion |

All four share project context and backend contracts.

## 10. Plot System

Plot cards turn workflow results into figures for exploration and communication.

| Surface | Role |
|---|---|
| Plot card | Saves a visualization connected to one workflow output |
| Authoring | Uses Python or R and supports several views of one result |
| Preview and export | Displays figures in the preview panel and exports SVG, PNG, PDF, or JPEG |
| Relinking | Connects a card to a new output after workflow changes |
| AI assistance | Creates, explains, validates, runs, and relinks plot cards |

Workflows focus on producing data. Plot cards support fast visual exploration.

## 12. Extensibility

Domain extension surfaces:

| Surface | Adds | Lives in |
|---|---|---|
| Blocks | Workflow steps | Project, user, or package |
| Data types and formats | Data contracts and boundary conversions | Project, user, or package |
| Previewers | Type-specific views | Project or package |

Extensions use shared registries and the public API.
