---
spec_id: adr-043-io-format-capability-registry
title: "ADR-043 IO Format Capability Registry Implementation Specification"
status: Draft
feature_branch: feat/issue-1113/frontmatter-griffe-facts-main
created: 2026-05-19
input: "Owner-approved ADR-043 design for IO format capabilities, aggregate IOBlocks, custom IO ergonomics, and typed meta fidelity."
owners:
  - "@jiazhenz026"
related_adrs:
  - 43
  - 42
related_specs: []
scope:
  in:
    - Structured IO format capability declarations for loader and saver IOBlocks.
    - Ergonomic SimpleLoader and SimpleSaver base classes for local custom IOBlocks.
    - Registry indexing and deterministic lookup for loader and saver capabilities.
    - Capability-aware AppBlock and CodeBlock boundary validation.
    - Typed meta fidelity declarations and metadata-loss visibility.
    - Migration scaffolding from supported_extensions to format capabilities.
    - Frontend format selection and capability_id persistence.
  out:
    - Moving extension support onto DataObject types.
    - Engine-level semantic guessing, extension alias prediction, or special TIFF behavior.
    - Automatic conversion across canonical workflow edges.
    - Free-form user metadata package implementation.
    - Full migration of every package format in one implementation step.
governs:
  modules:
    - scieasy.blocks.io
    - scieasy.blocks.registry
    - scieasy.engine.materialisation
    - scieasy.blocks.app
    - scieasy.workflow
  contracts:
    - scieasy.blocks.io.capabilities.FormatCapability
    - scieasy.blocks.io.capabilities.MetadataFidelity
    - scieasy.blocks.io.simple_io.SimpleLoader
    - scieasy.blocks.io.simple_io.SimpleSaver
    - scieasy.blocks.io.io_block.IOBlock.get_format_capabilities
    - scieasy.blocks.registry.BlockRegistry.list_format_capabilities
    - scieasy.blocks.registry.BlockRegistry.find_loader_capability
    - scieasy.blocks.registry.BlockRegistry.find_saver_capability
    - scieasy.engine.materialisation.reconstruct_from_file
    - scieasy.engine.materialisation.materialise_to_file
  files:
    - src/scieasy/blocks/io/capabilities.py
    - src/scieasy/blocks/io/simple_io.py
    - src/scieasy/blocks/io/io_block.py
    - src/scieasy/blocks/registry.py
    - src/scieasy/engine/materialisation.py
    - src/scieasy/blocks/app/app_block.py
    - src/scieasy/blocks/app/bridge.py
    - src/scieasy/workflow/validator.py
    - frontend/src/**
    - packages/scieasy-blocks-imaging/src/**
    - packages/scieasy-blocks-lcms/src/**
    - docs/architecture/ARCHITECTURE.md
    - docs/block-development/**
tests:
  - tests/blocks/io/test_format_capabilities.py
  - tests/blocks/io/test_simple_io.py
  - tests/blocks/test_block_registry_capabilities.py
  - tests/engine/test_materialisation_capabilities.py
  - tests/blocks/app/test_app_block_capabilities.py
  - tests/workflow/test_io_boundary_validation.py
  - frontend/src/**/__tests__/**
acceptance_source: adr
language_source: en
---

# ADR-043 IO Format Capability Registry Implementation Specification

## 1. Change Summary

This spec translates ADR-043 into implementation requirements for SciEasy's IO
format capability registry. The core change is to make external file format
support an explicit IOBlock capability instead of a DataObject property or an
engine guess.

The implementation must preserve ADR-043's boundaries:

- DataObject types remain format-independent.
- IOBlocks declare supported boundary conversions.
- The registry resolves capabilities deterministically.
- AppBlock and CodeBlock boundaries validate type, extension, and capability
  before execution.
- Simple local custom IOBlocks remain easy to write.
- Metadata promises are expressed as typed `meta` fidelity, not as runtime
  lineage metadata.

## 2. User Scenarios & Testing

### User Story 1 - Aggregate IOBlocks keep the palette small (Priority: P1)

As a workflow author, I need one Load Image block with a format dropdown instead
of one palette block per image format.

Why this priority: ADR-043 Section 3 requires package authors to aggregate
format handlers behind small user-facing IOBlock surfaces.

Independent Test: Register a `LoadImage` IOBlock with TIFF and PNG
capabilities; verify the registry lists both capabilities while the block
catalog still exposes one user-facing block.

Acceptance Scenarios:

1. Given a block with two load capabilities, when the frontend requests block
   schema, then the schema exposes a single block and a format option list.
2. Given a selected format, when the workflow is saved, then the selected
   `capability_id` is persisted.
3. Given the workflow is reopened, when the config panel renders, then the same
   capability is selected.

### User Story 2 - Custom local IOBlocks remain simple (Priority: P1)

As a scientist writing a local loader, I need to provide an output type,
extensions, a format id, and one load method without writing a full package
manifest.

Why this priority: ADR-043 Section 4 defines SimpleLoader and SimpleSaver as
the ergonomic path for custom IO.

Independent Test: Define fixture SimpleLoader and SimpleSaver classes; verify
their generated capabilities and handler dispatch.

Acceptance Scenarios:

1. Given a SimpleLoader with `output_type`, `extensions`, and `format_id`, when
   `get_format_capabilities()` runs, then it returns one conservative
   `pixel_only` load capability.
2. Given a SimpleSaver with `input_type`, `extensions`, and `format_id`, when
   `get_format_capabilities()` runs, then it returns one conservative
   `pixel_only` save capability.
3. Given a missing required SimpleLoader declaration, when the registry scans
   the block, then it reports a validation error.

### User Story 3 - AppBlock boundaries fail before external tools run (Priority: P1)

As a user running Fiji or another external tool, I need invalid output
contracts such as `Label + .tif` without a loader to fail before the app block
waits for files.

Why this priority: ADR-043 Section 7 moves late reconstruction crashes into
workflow boundary validation.

Independent Test: Validate AppBlock fixture ports for missing, unique, and
ambiguous loader/saver capabilities.

Acceptance Scenarios:

1. Given an AppBlock output port with no matching loader capability, when
   validation runs, then it fails with a clear missing-capability error.
2. Given multiple matching loader capabilities and no `capability_id`, when
   validation runs, then it fails with an ambiguity error.
3. Given a matching explicit `capability_id`, when validation runs, then the
   workflow is accepted.

### User Story 4 - Metadata fidelity is visible and testable (Priority: P2)

As a package author, I need to declare whether a format handler preserves only
payload data, typed `meta`, format-specific metadata, or a lossless round-trip.

Why this priority: ADR-043 Section 8 defines metadata fidelity as an IO
capability contract.

Independent Test: Register capabilities for each metadata fidelity level and
verify validation of typed meta fields, format metadata declarations, and
round-trip group requirements.

Acceptance Scenarios:

1. Given `typed_meta_reads=("pixel_size",)`, when the target type has that
   `Meta` field, then capability validation passes.
2. Given `typed_meta_reads=("missing_field",)`, when the target type lacks that
   field, then capability validation fails.
3. Given a `lossless` capability without a `roundtrip_group`, when validation
   runs, then it fails.

### User Story 5 - Ambiguity is explicit, not registration-order dependent (Priority: P2)

As a maintainer, I need two packages that support the same extension and type
to produce deterministic selection or a user-visible ambiguity, never silent
first-registered dispatch.

Why this priority: ADR-043 Section 6 rejects first-registered semantic
dispatch.

Independent Test: Register two matching capabilities with and without defaults
or explicit IDs.

Acceptance Scenarios:

1. Given exactly one matching capability, when lookup runs, then it returns that
   capability.
2. Given two matching capabilities and one default, when lookup runs, then it
   returns the default.
3. Given two matching capabilities and no default or explicit ID, when lookup
   runs, then it raises a typed ambiguity exception.

### Edge Cases

- Extension case and missing leading dot normalization.
- Same extension maps to different DataObject types.
- A subclass type such as `Label` has no exact loader but a parent `Image`
  loader exists.
- Existing blocks still define `supported_extensions`.
- One-way formats such as raw instrument inputs.
- A lossy saver is selected for an object with populated typed `meta`.
- Workflow YAML contains a stale `capability_id`.
- AppBlock output directory contains files with the right extension but no
  reconstructing loader for the declared type.

## 3. Requirements

### Functional Requirements

- FR-001: The system MUST define `FormatCapability` with direction, data type,
  format id, extensions, label, block type, handler, default flag, priority,
  round-trip group, and metadata fidelity.
- FR-002: The system MUST define `MetadataFidelity` with levels `pixel_only`,
  `typed_meta`, `format_specific`, and `lossless`.
- FR-003: IOBlocks MUST expose `get_format_capabilities()` returning normalized
  capability records.
- FR-004: SimpleLoader MUST synthesize one load capability from `output_type`,
  `extensions`, `format_id`, and `load_file`.
- FR-005: SimpleSaver MUST synthesize one save capability from `input_type`,
  `extensions`, `format_id`, and `save_file`.
- FR-006: The registry MUST index capabilities by direction, data type,
  extension, format id, and capability id.
- FR-007: Capability lookup MUST prefer explicit `capability_id` over inferred
  matching.
- FR-008: Capability lookup MUST fail on unresolved ambiguity instead of using
  registration order for semantic dispatch.
- FR-009: The registry MUST validate handler existence, extension
  normalization, capability id stability, default conflicts, and typed meta
  field references.
- FR-010: `reconstruct_from_file` MUST resolve a loader capability before
  invoking a handler.
- FR-011: `materialise_to_file` MUST resolve a saver capability before writing
  external boundary files.
- FR-012: AppBlock and CodeBlock input ports with declared type and extension
  MUST validate to a saver capability before execution.
- FR-013: AppBlock and CodeBlock output ports with declared type and extension
  MUST validate to a loader capability before execution.
- FR-014: Workflow config MAY omit `capability_id` only when lookup has exactly
  one deterministic match.
- FR-015: Workflow config MUST persist `capability_id` once a user chooses among
  multiple matching capabilities.
- FR-016: Existing `supported_extensions` declarations MAY synthesize
  compatibility capabilities during migration.
- FR-017: Synthesized compatibility capabilities MUST be marked as migration
  scaffolding and SHOULD NOT be treated as the final package authoring model.
- FR-018: The frontend MUST render format choices from capability metadata when
  available.
- FR-019: The frontend MUST surface ambiguity and metadata-loss warnings without
  changing runtime truth locally.
- FR-020: The implementation MUST NOT add extension support to DataObject
  classes.

### Metadata Fidelity Requirements

- FR-021: `pixel_only` capabilities MUST NOT claim preservation of domain
  metadata beyond minimum structural fields.
- FR-022: `typed_meta` capabilities MUST list typed meta fields they read or
  write.
- FR-023: `format_specific` capabilities MUST declare format metadata fields or
  sidecar schemas they read or write.
- FR-024: `lossless` capabilities MUST declare a `roundtrip_group`.
- FR-025: `lossless` round-trip groups MUST have both loader and saver
  capabilities unless the package marks the format as one-way and does not
  claim losslessness.
- FR-026: Package tests for `typed_meta`, `format_specific`, and `lossless`
  MUST cover the fields claimed by the capability.

### Non-Functional Requirements

- NFR-001: Capability lookup MUST be deterministic for the same registry state.
- NFR-002: Capability errors MUST identify direction, type, extension, format
  id, capability id, and matching candidates where available.
- NFR-003: Simple local IO authoring MUST require no package manifest.
- NFR-004: Published package capabilities MUST use stable package-qualified
  capability ids.
- NFR-005: Registry scan errors MUST be actionable enough for package authors
  to fix declarations without reading engine internals.

### Key Entities

| Entity | Description | Attributes | Relationships |
|---|---|---|---|
| `FormatCapability` | One external boundary conversion | id, direction, data_type, format_id, extensions, handler, metadata_fidelity | Owned by IOBlock or package manifest |
| `MetadataFidelity` | Metadata preservation contract | level, typed_meta_reads, typed_meta_writes, format metadata fields | Attached to FormatCapability |
| `SimpleLoader` | Ergonomic local loader base | output_type, extensions, format_id, load_file | Synthesizes load capability |
| `SimpleSaver` | Ergonomic local saver base | input_type, extensions, format_id, save_file | Synthesizes save capability |
| `CapabilityIndex` | Registry lookup index | direction, type, extension, format_id, capability_id | Built by BlockRegistry |
| `CapabilitySelection` | Workflow-selected IO route | capability_id, format_id, extension | Stored in workflow config |
| `CapabilityError` | Missing or ambiguous capability finding | direction, data_type, extension, candidates | Raised by registry and validator |

## 4. Implementation Plan

### 4.1 Technical Approach

Introduce capability models in `scieasy.blocks.io.capabilities`, then teach
IOBlock classes to expose explicit or synthesized capabilities. The registry
builds a capability index during block registration and exposes query methods
for loader and saver selection.

Materialisation and reconstruction should call registry lookup instead of
matching only extension strings. AppBlock and CodeBlock validation should call
the same lookup path before execution. The frontend should consume capability
metadata from backend schemas and persist stable `capability_id` values when
needed for replay.

Compatibility with existing `supported_extensions` should be implemented as a
migration layer. New package code should use explicit `FormatCapability`
records or SimpleLoader/SimpleSaver.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scieasy/blocks/io/capabilities.py` | create | Capability and metadata fidelity models, validation helpers, typed errors |
| `src/scieasy/blocks/io/simple_io.py` | create | SimpleLoader and SimpleSaver ergonomic base classes |
| `src/scieasy/blocks/io/io_block.py` | modify | Add `format_capabilities` and compatibility synthesis |
| `src/scieasy/blocks/registry.py` | modify | Index capabilities and expose deterministic lookup APIs |
| `src/scieasy/engine/materialisation.py` | modify | Resolve loader and saver capabilities for file boundaries |
| `src/scieasy/blocks/app/app_block.py` | modify | Reconstruct AppBlock outputs through capability lookup |
| `src/scieasy/blocks/app/bridge.py` | modify | Materialise AppBlock inputs through capability lookup |
| `src/scieasy/workflow/validator.py` | modify | Validate AppBlock and CodeBlock boundary IO before execution |
| `frontend/src/**` | modify | Render format dropdowns, ambiguity states, and metadata warnings |
| `packages/scieasy-blocks-imaging/src/**` | modify | Migrate image and label IO declarations to capabilities |
| `packages/scieasy-blocks-lcms/src/**` | modify | Migrate LCMS IO declarations where applicable |
| `docs/architecture/ARCHITECTURE.md` | modify | Align format and metadata architecture text with ADR-043 |
| `docs/block-development/**` | modify | Document simple local IO and published package capability authoring |

### 4.3 Implementation Sequence

1. Add capability dataclasses, fidelity models, normalization helpers, and
   typed missing/ambiguous capability exceptions.
2. Add SimpleLoader and SimpleSaver and tests for synthesized capabilities.
3. Extend IOBlock to expose explicit capabilities and synthesized compatibility
   capabilities from existing `supported_extensions`.
4. Extend BlockRegistry to index capabilities and implement lookup rules.
5. Update `reconstruct_from_file` and `materialise_to_file` to accept
   `capability_id` and use registry lookup.
6. Add workflow boundary validation for AppBlock and CodeBlock ports.
7. Migrate the minimal imaging capabilities needed to cover Image and Label
   TIFF use cases.
8. Update frontend schemas and controls for format dropdowns and persisted
   `capability_id`.
9. Update architecture and block-development docs.

### 4.4 Verification Plan

- Run unit tests for capability normalization and metadata fidelity validation.
- Run SimpleLoader and SimpleSaver tests for valid and invalid declarations.
- Run registry tests for unique, defaulted, explicit, missing, and ambiguous
  lookup cases.
- Run materialisation tests for loader/saver capability dispatch.
- Run AppBlock validation tests for missing and ambiguous boundary
  capabilities.
- Run imaging package tests for Image and Label TIFF capability declarations.
- Run frontend tests for format dropdown and persisted capability selection.
- Run docs frontmatter lint for ADR-043 and this spec.

### 4.5 Risks And Rollback

The main risk is broadening engine behavior into implicit format guessing. The
implementation must keep all format knowledge in package declarations and
registry records. Rollback is to disable capability-aware lookup behind the
migration layer while leaving explicit models in place.

The second risk is breaking existing blocks that only define
`supported_extensions`. Mitigate this with compatibility synthesis and focused
tests before package migrations.

The third risk is confusing users with too many format details. Mitigate this
by rendering one aggregate block and only surfacing ambiguity or metadata-loss
warnings when they affect execution or output fidelity.

### 4.6 Signature-Level Contracts

Capability models:

```python
from dataclasses import dataclass, field
from typing import Literal

from scieasy.core.types.base import DataObject


CapabilityDirection = Literal["load", "save"]
MetadataFidelityLevel = Literal[
    "pixel_only",
    "typed_meta",
    "format_specific",
    "lossless",
]


@dataclass(frozen=True)
class MetadataFidelity:
    level: MetadataFidelityLevel = "pixel_only"
    typed_meta_reads: tuple[str, ...] = ()
    typed_meta_writes: tuple[str, ...] = ()
    format_metadata_reads: tuple[str, ...] = ()
    format_metadata_writes: tuple[str, ...] = ()
    notes: str | None = None


@dataclass(frozen=True)
class FormatCapability:
    id: str
    direction: CapabilityDirection
    data_type: type[DataObject]
    format_id: str
    extensions: tuple[str, ...]
    label: str
    block_type: str
    handler: str
    is_default: bool = False
    priority: int = 0
    roundtrip_group: str | None = None
    metadata_fidelity: MetadataFidelity = field(default_factory=MetadataFidelity)
```

Capability exceptions:

```python
class CapabilityLookupError(LookupError):
    direction: CapabilityDirection
    data_type: type[DataObject]
    extension: str | None
    format_id: str | None
    capability_id: str | None


class MissingCapabilityError(CapabilityLookupError):
    ...


class AmbiguousCapabilityError(CapabilityLookupError):
    candidates: tuple[FormatCapability, ...]
```

IOBlock and simple bases:

```python
class IOBlock(Block):
    supported_extensions: ClassVar[dict[str, str]] = {}
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = ()

    @classmethod
    def get_format_capabilities(cls) -> tuple[FormatCapability, ...]:
        ...


class SimpleLoader(IOBlock):
    direction: ClassVar[str] = "input"
    output_type: ClassVar[type[DataObject]]
    extensions: ClassVar[list[str]]
    format_id: ClassVar[str]
    metadata_fidelity: ClassVar[MetadataFidelity] = MetadataFidelity()

    def load_file(self, path: Path, config: dict[str, Any]) -> DataObject:
        ...


class SimpleSaver(IOBlock):
    direction: ClassVar[str] = "output"
    input_type: ClassVar[type[DataObject]]
    extensions: ClassVar[list[str]]
    format_id: ClassVar[str]
    metadata_fidelity: ClassVar[MetadataFidelity] = MetadataFidelity()

    def save_file(
        self,
        obj: DataObject,
        path: Path,
        config: dict[str, Any],
    ) -> None:
        ...
```

Registry queries:

```python
class BlockRegistry:
    def list_format_capabilities(
        self,
        *,
        direction: CapabilityDirection | None = None,
        data_type: type[DataObject] | None = None,
        extension: str | None = None,
        format_id: str | None = None,
    ) -> list[FormatCapability]:
        ...

    def find_loader_capability(
        self,
        data_type: type[DataObject],
        extension: str | None = None,
        *,
        format_id: str | None = None,
        capability_id: str | None = None,
    ) -> FormatCapability:
        ...

    def find_saver_capability(
        self,
        data_type: type[DataObject],
        extension: str | None = None,
        *,
        format_id: str | None = None,
        capability_id: str | None = None,
    ) -> FormatCapability:
        ...
```

Materialisation helpers:

```python
def reconstruct_from_file(
    path: Path,
    target_type: type[DataObject],
    extension: str | None = None,
    *,
    capability_id: str | None = None,
    registry: BlockRegistry | None = None,
) -> DataObject:
    ...


def materialise_to_file(
    obj: DataObject,
    dest_dir: Path,
    extension: str | None = None,
    *,
    filename_stem: str = "data",
    capability_id: str | None = None,
    registry: BlockRegistry | None = None,
) -> Path:
    ...
```

Workflow validation:

```python
def validate_io_boundary_capabilities(
    workflow: Workflow,
    *,
    registry: BlockRegistry,
) -> list[CapabilityLookupError]:
    ...
```

## 5. Acceptance Criteria

- AC-001: ADR-043 and this spec pass ADR-042 frontmatter and first-section
  checks.
- AC-002: A SimpleLoader fixture produces a valid load capability without a
  package manifest.
- AC-003: A SimpleSaver fixture produces a valid save capability without a
  package manifest.
- AC-004: Registry lookup never falls back to first-registered semantic
  dispatch for ambiguous matches.
- AC-005: AppBlock `Label + .tif` output validation fails before execution when
  no loader capability exists.
- AC-006: AppBlock `Label + .tif` output reconstruction succeeds when an
  explicit compatible loader capability exists.
- AC-007: `typed_meta`, `format_specific`, and `lossless` declarations are
  validated against declared fields and round-trip requirements.
- AC-008: The frontend persists `capability_id` when user selection is needed.
- AC-009: Existing `supported_extensions` blocks continue to work during the
  migration phase through synthesized compatibility capabilities.

## 6. Open Questions

- Should package-level manifests be supported in the first implementation, or
  should ADR-043 start with class-level declarations only?
- Should type compatibility allow parent-type loaders for subtype outputs, and
  if so, what explicit adapter contract is required before accepting the result?
- Should metadata fidelity field paths be strings in v1 or structured validated
  paths against each type's `Meta` model?
- Which frontend endpoint should expose capability metadata: block schema,
  registry schema, or a dedicated `/api/capabilities` endpoint?
