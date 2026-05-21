<!--
  Sync Impact Report
  ===================
  Version change: (none) → 1.0.0
  Modified principles: N/A (initial constitution)
  Added sections:
    - Core Principles (I through VIII)
    - Architectural Boundaries
    - Development Workflow & Engineering Discipline
    - Governance
  Removed sections: N/A
  Templates requiring updates:
    - .specify/templates/plan-template.md        — ✅ compatible (Constitution Check section present)
    - .specify/templates/spec-template.md         — ✅ compatible (requirements, acceptance criteria align)
    - .specify/templates/tasks-template.md        — ✅ compatible (phased structure, parallel markers align)
  Follow-up TODOs: none
-->

# SciStudio Constitution

## Core Principles

### I. Workflow Graph Is the Source of Truth

The directed acyclic graph (DAG) definition, runtime state, block contracts,
data lineage, and execution semantics belong exclusively to the backend/runtime
layer. The frontend is an editor and viewer — it MUST NOT own or override
workflow semantics. All authoritative state lives in the graph; the UI reflects
it.

### II. Data Flows as References, Not Payloads

Data objects passed between blocks MUST be typed object references, lazy
handles, or persisted artifacts — never large in-memory payloads by default.
Blocks receive `ViewProxy` instances and choose when (and whether) to load
data into memory. This principle enables 100 GB+ datasets to flow through
workflows without exhausting system resources.

### III. Core Stays Small and Stable

The core framework defines minimal, stable contracts: base data types, block
base classes, port typing, execution semantics, and storage abstractions.
Domain-specific logic MUST NOT reside in core. Prefer stable primitive object
types, stable block contracts, and stable execution semantics. Avoid excessive
domain logic, deep inheritance trees, and premature specialization in core
modules.

### IV. Type Safety at Every Boundary

All block ports declare accepted types drawn from the `DataObject` hierarchy.
Connections are validated in two phases: design-time structural checks (class
hierarchy) and pre-execution semantic checks (runtime constraints). Invalid
connections MUST be rejected — silently accepting type mismatches is
prohibited. `TypeSignature` encodes the class hierarchy so that subtype
relationships (e.g., `SRSImage` accepted where `Image` or `Array` is
expected) are honoured automatically.

### V. Everything Is Connectable, Not Everything Is Native

The framework MUST NOT require users to migrate their entire existing
toolchain. Instead, it wraps existing tools as blocks: `CodeBlock` for
Python/R/Julia scripts, `AppBlock` for external GUI software (ElMAVEN, Fiji,
napari), and plugin-based extensions for community contributions. Inclusion
over replacement.

### VI. Manual Steps Are First-Class

Human review, editing, annotation, approval, and GUI-based intervention are
part of the formal workflow model — not workarounds. Interactive and external
execution modes (`ExecutionMode.INTERACTIVE`, `ExecutionMode.EXTERNAL`) are
supported natively in the block state machine. The engine pauses, checkpoints,
and resumes around manual steps exactly as it does for automated blocks.

### VII. AI May Propose, but Runtime Validates and Executes

AI-generated graphs, blocks, parameters, data types, or suggestions MUST
always pass through the formal validation pipeline: static analysis, dry run,
port contract verification, and user review. AI MUST NOT bypass type
contracts, lineage tracking, or execution policies. The runtime is the
authority; AI is an assistant.

### VIII. Community Extensibility by Design

The framework is designed for extension at every layer: new data types
(subclass `DataObject`), new blocks (subclass any block category), new storage
backends, new code runners, new format adapters, and reusable sub-workflows.
Two distribution tiers exist: drop-in files (zero config, project-local or
user-global) and pip-installable packages (entry_points-based, community
scale). Extension points MUST remain stable across minor versions.

## Architectural Boundaries

The system is organised into six horizontal layers. Each layer MUST depend
only on the layers below it. Violations of this dependency direction are
prohibited.

| Layer | Responsibility | Key Contracts |
|-------|---------------|---------------|
| 6. Frontend | ReactFlow canvas, block palette, monitoring | Reads/reflects backend state only |
| 5. API | FastAPI REST, WebSocket, SSE | Workflow CRUD, live status, log streaming |
| 4. AI services | Block generation, workflow synthesis, param optimisation | All output validated by runtime |
| 3. Execution engine | DAG scheduler, batch executor, process/resource manager | `BlockRunner` protocol, checkpoints |
| 2. Block system | Port typing, block registry, state machine, runners | `Block` ABC, `Port`, `BlockConfig` |
| 1. Data foundation | Type hierarchy, storage backends, lazy loading, lineage | `DataObject`, `ViewProxy`, `StorageReference` |
| Cross-cutting | Plugin ecosystem | Community blocks, custom types, external adapters |

**Boundary rules**:

- Frontend state MUST NOT serve as source of truth for any workflow semantic.
- Plugin logic MUST NOT be inserted into core without an ADR.
- Storage mechanics MUST NOT assume specific UI behaviour.
- AI prompting logic MUST NOT embed runtime policy decisions.
- Block contracts (ports, config schemas) MUST remain declarative and
  schema-validatable.

**Composition over inheritance**: Domain-specific behaviour SHOULD be layered
via wrappers, metadata, adapters, or plugins — not deep inheritance trees.
`CompositeData` exists precisely for multi-modal containers (AnnData,
SpatialData) that do not fit single-parent inheritance.

## Development Workflow & Engineering Discipline

All meaningful work follows the traceability chain:

**Idea -> Issue -> Spec/ADR -> Branch -> Commit -> PR -> Review -> CI/Test -> Merge -> Release**

### Mandatory Practices

1. **No direct push to main.** All changes go through PR.
2. **Focused commits.** Use conventional format:
   `feat(runtime): add pause state for manual block`.
   Vague messages (`fix`, `update`, `misc`) are prohibited.
3. **Tests are part of the change.** Bug fixes include regression tests. New
   contracts include validation or integration tests.
4. **Documentation is part of the product.** If behaviour changes,
   documentation MUST be updated.
5. **Scoped changes only.** Do not smuggle unrelated refactors, unplanned
   features, or architecture drift into a PR.

### When a Spec or ADR Is Required

A **spec** is required when work changes: object model, block protocol,
runtime execution behaviour, storage behaviour, API contracts, plugin
contracts, major UI semantics, AI orchestration behaviour, or external app
integration model.

An **ADR** is required when making a decision that is: architectural, hard to
reverse, affects multiple modules, likely to be questioned later, or a
tradeoff between competing long-term options.

### Workflow Gate Protocol

Every implementation task MUST pass through the 6-stage gate system
(`.workflow/gate.py`): `start` -> `create_issue` -> `write_change_plan` ->
`create_branch` -> `submit_pr` -> `update_docs` -> `update_changelog`. Gates
are sequential and non-skippable. Small changes still use gates — the
overhead ensures traceability.

### SpecKit Integration

For significant features requiring design, use the SpecKit pipeline
(`/speckit.specify` -> `/speckit.clarify` -> `/speckit.plan` ->
`/speckit.tasks`) before entering the Workflow Gate per-task execution loop.
Skip SpecKit only for small, well-understood changes that require no design
decisions.

## Governance

This constitution is the highest-authority document governing development
practices, architectural decisions, and engineering standards in the SciStudio
repository. It supersedes all other practice documents when conflicts arise.

### Amendment Procedure

1. Propose the amendment as an issue with rationale.
2. Draft the change as a PR modifying this file.
3. Obtain review and approval.
4. Update version using semantic versioning:
   - **MAJOR**: backward-incompatible principle removals or redefinitions.
   - **MINOR**: new principle/section added or materially expanded.
   - **PATCH**: clarifications, wording, or non-semantic refinements.
5. Record the amendment date.

### Compliance

- All PRs and reviews MUST verify compliance with these principles.
- Complexity that violates a principle MUST be justified in writing (ADR or
  PR description) and tracked.
- AI assistants operating in this repository MUST follow CLAUDE.md, which
  operationalises this constitution for AI-assisted development.

**Version**: 1.0.0 | **Ratified**: 2026-04-02 | **Last Amended**: 2026-04-02