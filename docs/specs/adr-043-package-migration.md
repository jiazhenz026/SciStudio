---
spec_id: adr-043-package-migration
title: "ADR-043 In-Tree, Imaging, and SRS Migration to IO Format Capabilities"
status: Draft
feature_branch: track/adr-043/core-blocks-and-imaging
created: 2026-05-20
input: "Owner directive (2026-05-20): coordinate migration of in-tree LoadData/SaveData and the shipped scistudio-blocks-imaging + scistudio-blocks-srs packages to ADR-043 explicit FormatCapability records; add new imaging formats (PNG/JPEG via Pillow, Bio-Formats microscopy formats via cellprofiler/python-bioformats as an optional install extra); make Image.Meta carry a unified OME metadata object (ome_types.model.OME); codify ProcessBlock metadata propagation contract so OME metadata persists end-to-end; add frontend UI for capability selection, lossy-save warning, and OME metadata browsing."
owners:
  - "@jiazhenz026"
related_adrs:
  - 41
  - 43
related_specs: []
scope:
  in:
    - "Declare explicit format_capabilities ClassVar on LoadData/SaveData covering all six core DataObject types"
    - "Delete the legacy supported_extensions ClassVar on LoadData/SaveData; reroute dispatch through the capability registry"
    - "Declare explicit format_capabilities on imaging.LoadImage/SaveImage; add PNG/JPEG (Pillow), Bio-Formats microscopy family (load-only)"
    - "Add ome: ome_types.model.OME | None typed field to Image.Meta and Label.Meta"
    - "Ship Bio-Formats handler under the imaging[bioformats] optional install extra (cellpose pattern); lazy import + clear missing-dependency error"
    - "Codify ProcessBlock OME metadata propagation contract (modes A/B/C) in the spec; audit and fix every Image-domain ProcessBlock in imaging and SRS packages"
    - "Add frontend capability dropdown on AppBlock/CodeBlock/IO port editors; metadata fidelity warning at lossy save; OME metadata browser button on Image previews"
  out:
    - "lcms package migration (separate sub-issue under #1204)"
    - "OME-Zarr v0.4 first-class file-format support (current zarr capability stays vanilla zarr)"
    - "Adding LoadSRSImage IO block (SRS package currently has no IO block; separate issue if desired)"
    - "Bio-Formats save support (cellprofiler/python-bioformats is load-only by design)"
    - "Engine, registry, validator, materialisation changes (already migrated as part of ADR-043 foundations)"
    - "Removing IOBlock base class supported_extensions ClassVar (required as synthesis fallback for unmigrated third-party blocks)"
governs:
  modules:
    - scistudio.blocks.io.loaders.load_data
    - scistudio.blocks.io.savers.save_data
    - scistudio_blocks_imaging
    - scistudio_blocks_imaging.types
    - scistudio_blocks_imaging.io.load_image
    - scistudio_blocks_imaging.io.save_image
    - scistudio_blocks_srs
  contracts:
    - scistudio.blocks.io.loaders.load_data.LoadData.format_capabilities
    - scistudio.blocks.io.savers.save_data.SaveData.format_capabilities
    - scistudio_blocks_imaging.types.Image.Meta.ome
    - scistudio_blocks_imaging.types.Label.Meta.ome
    - scistudio_blocks_imaging.io.load_image.LoadImage.format_capabilities
    - scistudio_blocks_imaging.io.save_image.SaveImage.format_capabilities
  files:
    - src/scistudio/blocks/io/loaders/load_data.py
    - src/scistudio/blocks/io/savers/save_data.py
    - packages/scistudio-blocks-imaging/src/**
    - packages/scistudio-blocks-imaging/pyproject.toml
    - packages/scistudio-blocks-srs/src/**
    - frontend/src/**
    - tests/blocks/io/**
    - packages/scistudio-blocks-imaging/tests/**
    - packages/scistudio-blocks-srs/tests/**
    - docs/specs/adr-043-package-migration.md
tests:
  - tests/blocks/io/test_load_data_capabilities.py
  - tests/blocks/io/test_save_data_capabilities.py
  - packages/scistudio-blocks-imaging/tests/test_format_capabilities.py
  - packages/scistudio-blocks-imaging/tests/test_image_meta_ome.py
  - packages/scistudio-blocks-imaging/tests/test_bioformats_handler.py
  - packages/scistudio-blocks-imaging/tests/test_processblock_meta_propagation.py
  - packages/scistudio-blocks-srs/tests/test_processblock_meta_propagation.py
  - frontend/src/__tests__/CapabilityDropdown.test.tsx
  - frontend/src/__tests__/OMEMetadataPanel.test.tsx
  - frontend/src/__tests__/LossySaveWarning.test.tsx
acceptance_source: manual
language_source: en
---

# Spec: ADR-043 In-Tree, Imaging, and SRS Migration to IO Format Capabilities

## 1. Change Summary

This spec coordinates the migration of in-tree core IO blocks (`LoadData` / `SaveData`)
and the shipped `scistudio-blocks-imaging` + `scistudio-blocks-srs` packages from the
legacy `supported_extensions` model to explicit ADR-043 `FormatCapability`
declarations. It also expands the imaging package to support PNG/JPEG (via Pillow)
and microscopy vendor formats (CZI/ND2/LIF/OIR/OIB via `cellprofiler/python-bioformats`
as an optional install extra), introduces a unified `Image.Meta.ome: ome_types.model.OME | None`
metadata carrier, codifies a ProcessBlock OME-metadata propagation contract so
domain metadata survives end-to-end across workflow pipelines, and adds frontend
UI for capability selection and metadata fidelity.

This spec is driven by a manual owner request from @jiazhenz026 on 2026-05-20 and
serves as the implementation plan for a new sub-issue to be opened under tracking
issue #1204 ("Track ADR-043 package migration to explicit IO format capabilities").
It does not introduce new architectural decisions — every design choice is grounded
in ADR-041 and ADR-043 — but it commits to specific implementation choices ADR-043
left to package authors: capability ID naming, metadata carrier shape, optional-extras
strategy, and ProcessBlock propagation contract.

### 1.1 Change Items

The spec body details these changes. Every row maps to one or more
`FR-NNN` requirements in §3 and one or more files in §4.2.

| # | Change | Surface | Driving FR(s) |
|---:|---|---|---|
| 1 | Declare explicit `LoadData.format_capabilities` covering all six core types × supported extensions (capability id `core.{type}.{format}.load`, fidelity `pixel_only`) | in-tree core IO | FR-001 |
| 2 | Declare explicit `SaveData.format_capabilities` (mirror of LoadData, fidelity `pixel_only`) | in-tree core IO | FR-002 |
| 3 | Delete `supported_extensions` ClassVar from `LoadData` / `SaveData`; rewire `_resolve_format` / `_resolve_save_format` and user-facing error messages through capability records | in-tree core IO | FR-003 |
| 4 | Declare explicit `LoadImage.format_capabilities`: tifffile (`.tif`/`.tiff`), zarr, Pillow (`.png`/`.jpg`/`.jpeg`), Bio-Formats family (`.czi`/`.nd2`/`.lif`/`.oir`/`.oib` minimum); all `format_specific` with `format_metadata_reads=("ome",)` | imaging IO | FR-004 |
| 5 | Declare explicit `SaveImage.format_capabilities`: tifffile, zarr, Pillow (PNG/JPEG) only — Bio-Formats family is load-only and MUST NOT appear here | imaging IO | FR-005 |
| 6 | Add typed field `ome: ome_types.model.OME \| None = None` to `Image.Meta` | imaging types | FR-006 |
| 7 | Add typed field `ome: ome_types.model.OME \| None = None` to `Label.Meta` (Label.Meta currently inherits BaseModel directly, not Image.Meta) | imaging types | FR-007 |
| 8 | Ship Bio-Formats handler under `imaging[bioformats]` optional install extra (cellpose pattern); lazy imports; clear install-command error when extras missing; registry hides bioformats capabilities when extras unavailable | imaging deps + IO | FR-008 |
| 9 | Codify ProcessBlock OME metadata propagation contract (Mode A transparent / Mode B helper transform / Mode C per-block field selection) | spec contract | FR-009 |
| 10 | Audit + fix every Image-domain ProcessBlock in imaging package; commit `docs/audit/adr-043-imaging-propagation-audit.md` | imaging blocks | FR-010 |
| 11 | Audit + fix every Image-domain ProcessBlock in SRS package; commit `docs/audit/adr-043-srs-propagation-audit.md` | srs blocks | FR-011 |
| 12 | Frontend capability dropdown on AppBlock / CodeBlock / IO port editors when capability lookup is ambiguous; persists `capability_id` on port config | frontend UI | FR-012 |
| 13 | Frontend "OME metadata" button on output preview opens navigable OME tree panel | frontend UI | FR-013 |
| 14 | Frontend lossy-save warning chip on SaveImage node listing OME fields that the target capability will drop | frontend UI | FR-014 |
| 15 | Capability ID naming convention: `core.{type}.{format}.{load\|save}` (in-tree), `imaging.image.{format}.{load\|save}` (imaging), `srs.srsimage.{format}.{load\|save}` (SRS reserved) | spec contract | FR-015 |
| 16 | Test coverage: per-block capability declarations, ome field round-trip, Mode A/B/C propagation, ambiguity error, missing-extras failure mode | tests | FR-016 |
| 17 | Add `ome-types>=0.5,<0.6` as non-optional dependency of `scistudio-blocks-imaging` | imaging deps | FR-017 |

## 2. User Scenarios & Testing

### User Story 1 - Existing core IO workflows keep working after capability migration (Priority: P1)

As a scientist who has saved SciStudio workflows using the six core DataObject types
(Array, DataFrame, Series, Text, Artifact, CompositeData), I need every existing
workflow to keep running with byte-identical output after `LoadData` / `SaveData`
adopt explicit `FormatCapability` declarations and drop the legacy
`supported_extensions` ClassVar.

**Why this priority:** The migration cannot break the existing six-core-type IO
pipeline. All current SciStudio users — whether they wrote workflows or just consume
them — depend on this baseline behavior. If migration causes regressions here,
every downstream worker breaks. P1 is unconditional.

**Independent Test:** Take an existing workflow that uses
`LoadData(core_type=DataFrame, path=...csv)` upstream and
`SaveData(core_type=DataFrame, path=...csv)` downstream; run it before and after
the migration; verify the saved file is byte-identical and the workflow run record
looks the same except for the new gate-record evidence.

**Acceptance Scenarios:**

1. **Given** an existing CSV-based DataFrame workflow saved as workflow YAML before
   this migration, **When** the same workflow YAML is loaded and executed after
   migration, **Then** the workflow runs to completion without errors and the saved
   CSV is byte-identical to the pre-migration output.

2. **Given** a workflow that loads a `.zarr` Array, **When** executed against the
   migrated `LoadData`, **Then** the produced Array has the same shape, dtype, and
   `storage_ref` semantics as the pre-migration baseline.

3. **Given** a workflow node that previously relied on `LoadData.supported_extensions`
   programmatically (e.g. in tests), **When** the ClassVar is removed, **Then** the
   equivalent capability query
   (`registry.list_format_capabilities(direction="load", data_type=DataFrame)`)
   returns at least one matching capability per legacy extension.

4. **Given** a workflow with `LoadData(path="foo.unknown_ext")`, **When** executed,
   **Then** the failure mode is "no matching capability" (typed
   `CapabilityLookupError`) rather than a silent path through dispatch.

### User Story 2 - imaging package supports PNG/JPEG and microscopy vendor formats (Priority: P1)

As a microscopy researcher, I need to drop existing `.czi` / `.nd2` / `.lif` /
`.oir` / `.oib` acquisition files directly into a SciStudio workflow without manual
conversion to TIFF; I also need to load consumer `.png` / `.jpg` images for
annotation reference or visualization.

**Why this priority:** Format coverage is the practical reason the imaging package
exists. CZI/ND2/LIF/OIR cover the Zeiss/Nikon/Leica/Olympus market — anyone running
a modern microscopy lab. PNG/JPEG covers reference plate captures and annotation
images. Without these, users have to convert outside SciStudio, losing reproducibility.

**Independent Test:** With `imaging[bioformats]` extras installed and the
`python-bioformats` JVM dependency satisfied, run a workflow
`LoadImage(path="sample.czi")` and verify the returned `Image` carries a populated
`Image.Meta.ome` with non-empty `ome.images[0].pixels.physical_size_x`.

**Acceptance Scenarios:**

1. **Given** a workflow with `LoadImage(path="sample.png", capability_id="imaging.image.png.load")`,
   **When** executed, **Then** an `Image` is returned with the array data populated
   and `Image.Meta.ome` populated to the extent the PNG file's metadata
   (EXIF / text chunks / ICC profile) supports.

2. **Given** a workflow with
   `LoadImage(path="sample.czi", capability_id="imaging.image.czi.load")` **and**
   the `imaging[bioformats]` extras installed, **When** executed, **Then** an
   `Image` is returned with `Image.Meta.ome` populated with
   `physical_size_x/y/z`, `channels`, `acquisition_date`, and any vendor-specific
   OME StructuredAnnotations from the CZI metadata.

3. **Given** a workflow with `LoadImage(path="sample.czi")` **and**
   `imaging[bioformats]` extras NOT installed, **When** executed, **Then** the
   failure mode is a clear ImportError-equivalent message naming
   `imaging[bioformats]` as the install target.

4. **Given** an in-memory `Image` produced from a `.czi` load, **When** routed to
   `SaveImage(path="output.czi")`, **Then** validation fails with an
   "this capability is load-only" error before any IO occurs.

5. **Given** an `Image` with full OME metadata loaded from a CZI, **When** routed
   to `SaveImage(path="output.png")`, **Then** the save succeeds and the saved PNG
   carries only the EXIF-mappable fields; the UI surfaces a lossy-save warning
   (User Story 5).

### User Story 3 - Image-domain OME metadata persists end-to-end through the ProcessBlock pipeline (Priority: P1)

As a researcher running a workflow `LoadImage → Resize → Gaussian Filter → SaveImage`,
I need the OME metadata (pixel_size, channels, acquisition_date, instrument identification)
loaded at the boundary to survive every intermediate ProcessBlock and reach
`SaveImage` so the saved file is still semantically annotated.

**Why this priority:** Without propagation, OME metadata is lost after the first
ProcessBlock. The whole "unified zarr + OME" internal representation design
collapses — every save becomes lossy regardless of source format. P1 because this
is the design vision agreed to in this spec's planning phase; cutting it gives the
worst of both worlds (carrier model without persistence guarantee).

**Independent Test:** Run a golden-path workflow
`LoadImage(czi) → Resize(factor=0.5) → SaveImage(tif)`; reload the saved TIFF and
verify `image.meta.ome.images[0].pixels.physical_size_x` matches the source value
scaled by the resize factor (the Resize helper updates pixel_size accordingly).

**Acceptance Scenarios:**

1. **Given** a workflow `LoadImage → ImageCalculator(add 100) → SaveImage`,
   **When** executed, **Then** the SaveImage output has the same `Image.Meta.ome`
   as the LoadImage output (Mode A — transparent propagation).

2. **Given** a workflow `LoadImage → Resize(factor=0.5) → SaveImage`, **When**
   executed, **Then** the SaveImage output has
   `Image.Meta.ome.images[0].pixels.physical_size_x` doubled (the `_resize_meta`
   helper updates pixel_size to reflect the new sampling — Mode B).

3. **Given** a workflow `LoadImage → CellposeSegment(produces Label + mask Image) → SaveImage(mask)`,
   **When** executed, **Then** the mask Image preserves OME metadata from the
   source Image (Mode C decision: shape-preserving cross-type derivation must
   carry ome).

4. **Given** a `Label` instance produced by a segmentation block, **When**
   serialized via `model_dump()`, **Then** the `ome` field is present and matches
   the source Image's ome (Label.Meta.ome added per FR-007).

5. **Given** a workflow that calls `Image.with_meta(...)` somewhere, **When**
   executed, **Then** the resulting Image preserves `ome` because `with_meta`
   propagates all existing typed Meta fields.

### User Story 4 - SRS workflows preserve OME metadata through component analysis (Priority: P2)

As an SRS spectroscopy researcher running
`SRSSpectralDenoise → SRSCalibrate → SRSPCA → SRSKMeansCluster`, I need the OME
metadata loaded with the source `SRSImage` to flow through each block where the
output is shape-preserving and image-shaped; lossy points (PCA scores, abundance
map dimensionality reduction) may legitimately drop ome but must do so deliberately,
not by accident.

**Why this priority:** Same propagation principle as US3, but SRS has narrower user
base and several legitimately-lossy blocks; the audit/fix scope is real but
smaller. P2 because the SRS subgraph is acceptable as second wave after the
imaging wave proves the pattern.

**Independent Test:** Run
`LoadImage(czi → cast to SRSImage) → SRSSpectralDenoise → SRSCalibrate → ExtractSpectrum`;
verify `SRSImage.Meta.ome` flows through SRSSpectralDenoise and SRSCalibrate
unchanged.

**Acceptance Scenarios:**

1. **Given** an `SRSImage` with `Image.Meta.ome` populated, **When** routed through
   `SRSSpectralDenoise`, **Then** the output has the same ome (Mode A).

2. **Given** an `SRSImage`, **When** routed through `SRSCalibrate` (which rebuilds
   Meta via `model_dump() + override`), **Then** the output has the same ome
   (model_dump already preserves unmentioned fields — Mode C variant via
   model_dump).

3. **Given** an `SRSImage`, **When** routed through `SRSPCA` (output is a DataFrame
   of PC scores, not image-shaped), **Then** the output may legitimately have
   `meta=None` because PC scores have no image coordinate system; this is
   documented in the propagation contract as a Mode C legitimate-drop case.

4. **Given** an `SRSImage`, **When** routed through `SRSKMeansCluster` (output is
   `Label` shape-aligned with input), **Then** the output `Label.Meta.ome` matches
   the input SRSImage's ome (Mode C: ome required because output and input share
   spatial layout).

### User Story 5 - UI exposes capability selection, OME browser, and lossy-save warnings (Priority: P2)

As a scientist using the SciStudio frontend block editor, I need (a) a dropdown to
select between multiple compatible capabilities when ambiguous
`(type, extension)` combinations exist, (b) a button to browse the OME metadata
attached to a workflow output, (c) a clear warning when a SaveImage capability has
lower metadata fidelity than the source object's filled OME fields.

**Why this priority:** Capability ambiguity in workflows must be resolvable in the
UI (otherwise validation fails the workflow at run time, which is too late). OME
browsing is a quality-of-life feature important for trust in pipeline correctness.
Lossy-save warning is a per-action UI cue. P2 because backend correctness (US1-4)
gates the frontend; once backend is right, the frontend can land in parallel.

**Independent Test:** Open Chrome to the frontend; create an AppBlock workflow
node with port `type=Image` and extension `.tif`; verify the capability dropdown
shows multiple options (one for each TIFF-capable saver) and selecting one
persists `capability_id` on the port.

**Acceptance Scenarios:**

1. **Given** a workflow port editor with declared `type=Image, extension=.tif`,
   **When** the user opens the port editor, **Then** the capability dropdown shows
   the available TIFF capabilities (imaging.image.tiff.load/save) with format
   label, metadata fidelity badge, and a one-line description.

2. **Given** a workflow output `Image` with populated
   `ome.images[0].pixels.physical_size_x` and `channels`, **When** the user clicks
   the "OME metadata" button on the output preview, **Then** a panel opens showing
   the OME structure as a navigable tree.

3. **Given** an `Image` with populated `ome` (typed_meta + format-specific OME
   StructuredAnnotations) routed to `SaveImage(path="out.png")` (PNG fidelity =
   format_specific but most OME fields not writable), **When** the user is editing
   the workflow, **Then** a lossy-save warning chip appears on the SaveImage node
   listing which OME fields will be dropped on save.

4. **Given** an ambiguous capability situation that the UI cannot pre-resolve,
   **When** the user attempts to save the workflow, **Then** the workflow save is
   blocked with an inline error listing the unresolved `capability_id` selections.

### Edge Cases

- **Missing bioformats extras:** `imaging[bioformats]` not installed. Lazy import
  in the Bio-Formats handler raises a clear ImportError-equivalent message naming
  `imaging[bioformats]` as the install target; the Block registry hides those
  capabilities from the dropdown until extras install is detected.
- **Cross-format save:** Loading CZI → saving TIFF. The OME-XML is written to the
  TIFF `ImageDescription` tag; cross-vendor StructuredAnnotations that have no TIFF
  representation are dropped silently (lossy warning surfaced in UI per FR-014).
- **Compound extension `.ome.tif`:** Per design decision (not split from `.tif`),
  a single `imaging.image.tiff.{load,save}` capability handles both `.ome.tif` and
  `.tif` extensions. Internal handler auto-detects OME-XML presence and routes
  accordingly.
- **Pickle gating:** `.pkl` extensions on LoadData/SaveData remain gated behind
  `allow_pickle=True`. The FormatCapability record carries a `notes` field flagging
  the opt-in requirement; runtime gate is enforced by existing
  `_check_pickle_allowed` / `_check_pickle_gate` helpers.
- **Empty Collection on save:** `SaveImage` receiving an empty Collection raises
  `ValueError` ("nothing to save") before any IO call.
- **ProcessBlock mode-C legitimate drop:** `SRSPCA` / `SRSUnmix` produce
  dimensionality-reduced outputs whose pixel coordinate system no longer matches
  the source — the propagation contract allows `meta=None` on output, but the
  audit step must mark these blocks as deliberately-lossy in the spec's
  propagation matrix table.
- **`Image.with_meta(...)` calls:** Existing `with_meta` already propagates all
  typed Meta fields including the new `ome` (per
  `src/scistudio/core/types/base.py` `with_meta` immutable update mechanism). No
  DataObject base change required.
- **OME schema version drift:** `ome-types` periodically tracks OME schema
  upgrades; the spec pins a version range in the imaging package's
  pyproject.toml. Major OME schema upgrades that break ome-types pydantic models
  are tracked in Risks (4.5).

## 3. Requirements

### Functional Requirements

- **FR-001:** `LoadData.format_capabilities` MUST be an explicit
  `ClassVar[tuple[FormatCapability, ...]]` declaration covering all six core
  DataObject types (Array, DataFrame, Series, Text, Artifact, CompositeData) ×
  supported extensions. Every record MUST have `is_synthesized=False`. Capability
  IDs MUST follow the convention `core.{lower(type)}.{format_id}.load`.

- **FR-002:** `SaveData.format_capabilities` MUST mirror FR-001 with
  `direction="save"` and `is_synthesized=False`. Capability IDs MUST follow the
  convention `core.{lower(type)}.{format_id}.save`.

- **FR-003:** The legacy `supported_extensions: ClassVar[dict[str, str]]` MUST be
  removed from `LoadData` and `SaveData` class bodies. The module-level helper
  functions `_resolve_format` / `_resolve_save_format` MUST be rewired to consult
  `format_capabilities` via the active registry or via
  `cls.get_format_capabilities()`. User-facing error messages that previously
  enumerated `sorted(LoadData.supported_extensions.keys())` MUST be re-sourced
  from the capability list.

- **FR-004:** `scistudio_blocks_imaging.io.LoadImage.format_capabilities` MUST be an
  explicit declaration covering:
  - `imaging.image.tiff.load` (handler: tifffile; extensions `.tif` and `.tiff`
    including OME-TIFF detection inside the handler);
  - `imaging.image.zarr.load` (handler: zarr; vanilla zarr, OME-Zarr deferred);
  - `imaging.image.png.load` (handler: Pillow);
  - `imaging.image.jpeg.load` (handler: Pillow; extensions `.jpg` and `.jpeg`);
  - Bio-Formats family: at minimum `imaging.image.czi.load`,
    `imaging.image.nd2.load`, `imaging.image.lif.load`, `imaging.image.oir.load`,
    `imaging.image.oib.load` (handler: cellprofiler/python-bioformats).
  
  Every record MUST declare
  `metadata_fidelity=MetadataFidelity(level="format_specific", format_metadata_reads=("ome",), typed_meta_reads=(...))`
  where the typed_meta_reads enumerate which Image.Meta fields the handler
  reliably populates beyond `ome` (typically `pixel_size`, `z_spacing`, `channels`).

- **FR-005:** `scistudio_blocks_imaging.io.SaveImage.format_capabilities` MUST be an
  explicit declaration covering ONLY writable formats:
  - `imaging.image.tiff.save` (handler: tifffile; writes OME-XML to
    ImageDescription tag);
  - `imaging.image.zarr.save` (handler: zarr);
  - `imaging.image.png.save` (handler: Pillow; writes EXIF-mappable OME fields
    only);
  - `imaging.image.jpeg.save` (handler: Pillow; writes EXIF-mappable OME fields
    only).
  
  Bio-Formats family (CZI/ND2/LIF/OIR/OIB) MUST NOT appear in SaveImage
  capabilities (load-only per cellprofiler/python-bioformats library scope). Each
  save capability MUST declare `format_metadata_writes=("ome",)` with
  `typed_meta_writes` matching what the handler reliably persists.

- **FR-006:** `scistudio_blocks_imaging.types.Image.Meta` MUST gain a typed field
  `ome: ome_types.model.OME | None = None`. The field MUST be readable and
  writable via `Image.Meta(ome=...)` construction and via
  `Image.with_meta(ome=...)`.

- **FR-007:** `scistudio_blocks_imaging.types.Label.Meta` MUST gain a typed field
  `ome: ome_types.model.OME | None = None`. Label.Meta inheritance is from
  BaseModel directly (not from Image.Meta — Image and Label have sibling Meta
  models in current code), so the field is added explicitly to Label.Meta.

- **FR-008:** The Bio-Formats handler MUST ship under the `imaging[bioformats]`
  optional install extra, following the existing `imaging[cellpose]` pattern. The
  handler module MUST defer the `python-bioformats` / `javabridge` / `ome-types`
  imports to lazy load time. When extras are missing, the handler MUST raise a
  clear error naming the install command
  `pip install scistudio-blocks-imaging[bioformats]`. The registry MUST hide
  Bio-Formats capabilities from `list_format_capabilities` results when the
  extras are not importable.

- **FR-009:** The spec codifies a ProcessBlock OME metadata propagation contract
  with three modes:
  - **Mode A — Shape-preserving same-type derivation.** Block constructs output
    via `OutputClass(..., meta=source.meta, ...)`. The `ome` field propagates
    transparently because the entire Meta object is passed through.
  - **Mode B — Shape-changing same-type derivation.** Block constructs output
    via `OutputClass(..., meta=transform_helper(source.meta, ...), ...)`. The
    transform helper (e.g. `_resize_meta`, `_projected_meta`, `_split_meta`)
    MUST handle the `ome` field — if pixel_size changes (resize), the helper
    updates `ome.images[0].pixels.physical_size_*` accordingly; if dimensions
    are dropped (projection), the helper rewrites
    `ome.images[0].pixels.size_*` and dimension ordering.
  - **Mode C — Cross-type derivation.** Block constructs output via
    `OutputClass.Meta(field1=..., field2=..., ...)`. The block author chooses
    which fields to propagate. Per this spec, **when the cross-type output
    preserves the spatial coordinate system of the source** (e.g.
    `Image → Label` from segmentation, `Image → Mask`), `ome` MUST be among the
    propagated fields. When the output drops spatial structure entirely (e.g.
    `Image → DataFrame` for measurements, `SRSImage → DataFrame` for PC scores),
    `meta=None` or a domain-specific Meta without `ome` is permitted.

- **FR-010:** Every ProcessBlock in `scistudio-blocks-imaging` whose output type
  inherits from `Image` (including `Label`, `Mask`, `Transform`) MUST be audited
  against FR-009 and updated to propagate `ome` when the mode/output shape
  requires it. The audit's findings MUST be recorded in
  `docs/audit/adr-043-imaging-propagation-audit.md` (committed as repository
  evidence).

- **FR-011:** Every ProcessBlock in `scistudio-blocks-srs` MUST be audited against
  FR-009. The audit MUST classify each block as Mode A / B / C and (for Mode C)
  explicitly justify the propagate-vs-drop choice for `ome`. Findings MUST be
  recorded in `docs/audit/adr-043-srs-propagation-audit.md`.

- **FR-012:** The frontend port editor for AppBlock, CodeBlock, and IOBlock ports
  MUST render a capability dropdown when more than one `FormatCapability` matches
  the declared `(direction, type, extension)`. The dropdown options MUST show
  capability label, format_id, and metadata fidelity badge. Selecting an option
  MUST persist `capability_id` on the port's port-config object.

- **FR-013:** The frontend output preview panel for any DataObject whose
  `meta.ome` is non-None MUST surface an "OME metadata" button. Clicking opens a
  side panel rendering the `OME` model as a navigable tree (images → pixels /
  channels / annotations) with copy-to-clipboard support for individual fields.

- **FR-014:** When a workflow edge connects a source object with populated
  `meta.ome` fields to a SaveImage capability whose `metadata_fidelity` does not
  declare those fields in `format_metadata_writes` / `typed_meta_writes`, the
  frontend MUST surface a lossy-save warning on the SaveImage node listing the
  OME fields that will be dropped.

- **FR-015:** Capability ID naming MUST follow these conventions:
  - In-tree core blocks: `core.{lower(type)}.{format_id}.{load|save}`. Examples:
    `core.dataframe.csv.load`, `core.array.zarr.save`.
  - imaging package blocks: `imaging.image.{format_id}.{load|save}`. Examples:
    `imaging.image.tiff.load`, `imaging.image.czi.load`.
  - srs package blocks (if any IO capabilities are added later):
    `srs.srsimage.{format_id}.{load|save}` — reserved for future use.

- **FR-016:** Tests MUST cover at minimum:
  - capability count, IDs, defaults, and metadata fidelity per migrated IOBlock
    (one test file per block);
  - typed Meta `ome` field round-trip via `model_dump` / construction;
  - ProcessBlock propagation: at least one test per Mode (A/B/C) per affected
    package proving `ome` survives or is deliberately handled;
  - Ambiguity error for type+extension combinations that match multiple
    capabilities;
  - Missing-extras failure mode for Bio-Formats (mocked import failure asserts
    the install-command message).

- **FR-017:** `ome-types>=0.5,<0.6` MUST be added as a non-optional dependency of
  `scistudio-blocks-imaging` in `pyproject.toml`. ome-types is pydantic v2-native
  from 0.4+ and has stable API since 0.5.

### Key Entities

- **FormatCapability declarations (per IOBlock class):** explicit
  `ClassVar[tuple[FormatCapability, ...]]` replacing legacy
  `supported_extensions`. Each record carries `id`, `direction`, `data_type`,
  `format_id`, `extensions`, `label`, `block_type`, `handler`, `is_default`,
  `priority`, `roundtrip_group`, `metadata_fidelity`, `is_synthesized=False`.
  Attributes: `id` (string, package-qualified), `direction` ("load"|"save"),
  `data_type` (DataObject subclass), `format_id` (string), `extensions` (tuple of
  lowercase dotted extensions), `metadata_fidelity` (MetadataFidelity instance).
  Relationships: each record belongs to exactly one IOBlock class; the registry
  indexes records at scan time.

- **Image.Meta.ome field (new):** typed `ome_types.model.OME | None` carrier for
  the canonical OME-XML metadata structure populated by IO handlers and
  propagated through ProcessBlocks. Required by FR-006. Inherited transparently
  by SRSImage.Meta because SRSImage.Meta declares
  `class Meta(Image.Meta)` (verified in
  `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/types.py`).

- **Label.Meta.ome field (new):** explicit `ome_types.model.OME | None` field
  on Label.Meta to support shape-preserving cross-type derivation
  (Image → Label). Required by FR-007.

- **ProcessBlock propagation mode classification (per block, audit deliverable):**
  each ProcessBlock in imaging + srs is classified as Mode A / B / C per FR-009;
  for Mode B/C, the propagation decision for `ome` is recorded in the audit
  report. The classification has fields: `block_name`, `module_path`,
  `mode` (A|B|C), `ome_decision` (carry|transform|drop), `justification`.

## 4. Implementation Plan

### 4.1 Technical Approach

The implementation runs along three parallel lines (Phase A) followed by two
sequential audit phases (Phase B) and an integration phase (Phase C):

- **Phase A (parallel)** — three implementation surfaces can land independently
  because they don't share files:
  - A1: in-tree core IO migration (`src/scistudio/blocks/io/loaders/load_data.py`,
    `src/scistudio/blocks/io/savers/save_data.py`).
  - A2: imaging IO + Image.Meta.ome + Bio-Formats extras + new format handlers
    (`packages/scistudio-blocks-imaging/src/**`, `pyproject.toml`).
  - A3: frontend UI (`frontend/src/**`).
  
  Each agent owns an isolated worktree, a feature branch off the umbrella branch,
  and its own PR targeting the umbrella branch.

- **Phase B (sequential after A2)** — ProcessBlock OME propagation audit + fix.
  Cannot start before A2 lands because the `Image.Meta.ome` field must exist
  before blocks can propagate it. Two independent sub-phases:
  - B1: imaging package ProcessBlock audit + fix.
  - B2: srs package ProcessBlock audit + fix.

- **Phase C** — no-context audit agent verifies the spec contract is met, commits
  audit report, and integration verification runs (golden-path workflow, Chrome
  smoke test, ADR-043 §9 package validity scan, CI green).

The implementation reuses existing scaffolding from the ADR-043 foundations
(`FormatCapability`, `MetadataFidelity`, `SimpleLoader`/`SimpleSaver`, registry
capability indexing, materialisation helpers, validator) — no engine, registry,
or materialisation changes are in scope.

### 4.2 Affected Files

| File | Action | Rationale |
|---|---|---|
| `src/scistudio/blocks/io/loaders/load_data.py` | modify | FR-001, FR-003 — explicit format_capabilities; delete supported_extensions; rewire `_resolve_format` |
| `src/scistudio/blocks/io/savers/save_data.py` | modify | FR-002, FR-003 — mirror of load_data |
| `tests/blocks/io/test_load_data_capabilities.py` | create | FR-016 — capability coverage tests for LoadData |
| `tests/blocks/io/test_save_data_capabilities.py` | create | FR-016 — capability coverage tests for SaveData |
| `packages/scistudio-blocks-imaging/pyproject.toml` | modify | FR-008, FR-017 — add bioformats extras + ome-types required dep |
| `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/types.py` | modify | FR-006, FR-007 — Image.Meta.ome, Label.Meta.ome fields |
| `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/load_image.py` | modify | FR-004 — declare format_capabilities; add PNG/JPEG/Bio-Formats branches |
| `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/save_image.py` | modify | FR-005 — declare format_capabilities; add PNG/JPEG; no bioformats |
| `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/bioformats_handler.py` | create | FR-008 — Bio-Formats lazy-import handler |
| `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/pillow_handler.py` | create | FR-004/005 — PNG/JPEG handlers via Pillow |
| `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/preprocess/geometry.py` | modify | FR-009/010 — `_resize_meta` helper updates ome.images[0].pixels |
| `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/preprocess/axis_ops.py` | modify | FR-009/010 — `_split_meta` helper propagates ome |
| `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/projection/projection.py` | modify | FR-009/010 — `_projected_meta` helper rewrites ome dimensions |
| `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/segmentation/cellpose_segment.py` | modify | FR-009/010 Mode C — mask_img and Label.Meta carry ome |
| `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/segmentation/*.py` | modify | FR-009/010 Mode C — every Image→Label / Image→Mask block carries ome |
| `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/math/*.py` | modify | FR-009/010 Mode A — verify `meta=source.meta` intact |
| `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/registration/*.py` | modify | FR-009/010 Mode A — verify |
| `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/morphology/*.py` | modify | FR-009/010 Mode A — verify |
| `packages/scistudio-blocks-imaging/tests/test_format_capabilities.py` | create | FR-016 — imaging IO capability tests |
| `packages/scistudio-blocks-imaging/tests/test_image_meta_ome.py` | create | FR-016 — Image.Meta.ome / Label.Meta.ome round-trip tests |
| `packages/scistudio-blocks-imaging/tests/test_bioformats_handler.py` | create | FR-008, FR-016 — Bio-Formats handler tests (gated by extras availability) |
| `packages/scistudio-blocks-imaging/tests/test_processblock_meta_propagation.py` | create | FR-010, FR-016 — propagation Mode A/B/C tests for imaging |
| `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_pca.py` | modify | FR-009/011 Mode C — document deliberate ome drop |
| `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_unmix.py` | modify | FR-009/011 Mode C — same |
| `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_kmeans.py` | modify | FR-009/011 Mode C — Label output must carry ome |
| `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocess/*.py` | modify | FR-009/011 Mode A — verify `meta=item.meta` intact |
| `packages/scistudio-blocks-srs/tests/test_processblock_meta_propagation.py` | create | FR-011, FR-016 — propagation tests for SRS |
| `frontend/src/components/PortEditor/CapabilityDropdown.tsx` | create | FR-012 — capability dropdown component |
| `frontend/src/components/OutputPreview/OMEMetadataPanel.tsx` | create | FR-013 — OME metadata browser panel |
| `frontend/src/components/WorkflowEditor/LossySaveWarning.tsx` | create | FR-014 — lossy-save warning chip |
| `frontend/src/api/capabilities.ts` | modify | FR-012 — capability listing API client |
| `frontend/src/__tests__/CapabilityDropdown.test.tsx` | create | FR-012, FR-016 — unit tests |
| `frontend/src/__tests__/OMEMetadataPanel.test.tsx` | create | FR-013, FR-016 — unit tests |
| `frontend/src/__tests__/LossySaveWarning.test.tsx` | create | FR-014, FR-016 — unit tests |
| `docs/audit/adr-043-imaging-propagation-audit.md` | create | FR-010 — committed audit report from Phase B1 |
| `docs/audit/adr-043-srs-propagation-audit.md` | create | FR-011 — committed audit report from Phase B2 |
| `docs/audit/adr-043-package-migration-final-audit-<sha>.md` | create | Phase C audit deliverable |
| `docs/planning/adr-043-package-migration-checklist.md` | create | manager checklist (per agent-dispatch.md §2) |
| `CHANGELOG.md` | modify | [Unreleased] entry per CHANGELOG CI enforcement |

### 4.3 Implementation Sequence

**Phase A (parallel-OK after umbrella branch + checklist + sub-issue exist):**

- **A1 — Core IO migration** (agent: implementer; branch:
  `track/adr-043/core-blocks-and-imaging/a1-core-io`)
  - T-001 Declare `LoadData.format_capabilities` (~22 records across 6 core types,
    all `metadata_fidelity=pixel_only`).
  - T-002 Declare `SaveData.format_capabilities` (mirror).
  - T-003 Delete `supported_extensions` ClassVars; rewire `_resolve_format` /
    `_resolve_save_format`.
  - T-004 Update error messages to source supported extensions from capabilities.
  - T-005 Add `test_load_data_capabilities.py` / `test_save_data_capabilities.py`.
  - T-006 CHANGELOG entry.
  - Open A1 PR targeting umbrella.

- **A2 — imaging IO + Image.Meta.ome + Bio-Formats extras** (agent: implementer;
  branch: `track/adr-043/core-blocks-and-imaging/a2-imaging-io`)
  - T-010 Add `ome-types>=0.5,<0.6` to imaging `pyproject.toml` required deps.
  - T-011 Add `[project.optional-dependencies] bioformats = ["python-bioformats", "javabridge"]`
    extras to `pyproject.toml`.
  - T-012 Add `ome: OME | None = None` field to `Image.Meta` and `Label.Meta`.
  - T-013 Create `io/pillow_handler.py` with PNG/JPEG load/save handlers.
  - T-014 Create `io/bioformats_handler.py` with lazy-import load handlers
    (CZI/ND2/LIF/OIR/OIB).
  - T-015 Declare `LoadImage.format_capabilities` per FR-004.
  - T-016 Declare `SaveImage.format_capabilities` per FR-005 (no bioformats).
  - T-017 Add capability + ome tests.
  - T-018 CHANGELOG entry.
  - Open A2 PR targeting umbrella.

- **A3 — Frontend UI** (agent: implementer; branch:
  `track/adr-043/core-blocks-and-imaging/a3-frontend`)
  - T-020 Capability listing API client (`frontend/src/api/capabilities.ts`).
  - T-021 `CapabilityDropdown.tsx` component + unit tests + integration into
    PortEditor.
  - T-022 `OMEMetadataPanel.tsx` + unit tests + integration into output preview.
  - T-023 `LossySaveWarning.tsx` + unit tests + integration into WorkflowEditor.
  - T-024 Chrome smoke test (per recorded feedback: mandatory Chrome smoke for
    any UI dispatch).
  - Open A3 PR targeting umbrella.

**Phase B (sequential, depends on A2 merged into umbrella):**

- **B1 — imaging ProcessBlock propagation audit + fix** (agent: implementer;
  branch: `track/adr-043/core-blocks-and-imaging/b1-imaging-propagation`)
  - T-030 Audit each block file under
    `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/{math,morphology,preprocess,projection,registration,segmentation,measurement}/`;
    classify A/B/C.
  - T-031 For Mode B helpers (`_resize_meta`, `_projected_meta`, `_split_meta`):
    update to handle `ome` field (axes/pixel_size adjustment).
  - T-032 For Mode C blocks (segmentation/*.py): add `ome=source.meta.ome` to the
    rebuilt Meta where shape-preserving.
  - T-033 Add `test_processblock_meta_propagation.py` with one test per Mode per
    affected block.
  - T-034 Commit `docs/audit/adr-043-imaging-propagation-audit.md`.
  - Open B1 PR targeting umbrella.

- **B2 — SRS ProcessBlock propagation audit + fix** (agent: implementer;
  branch: `track/adr-043/core-blocks-and-imaging/b2-srs-propagation`)
  - T-040 Audit each block under
    `packages/scistudio-blocks-srs/src/scistudio_blocks_srs/{preprocess,component_analysis,spectral_extraction}/`.
  - T-041 Confirm Mode A blocks (`srs_baseline.py`, `srs_spectral_denoise.py`)
    are correct (no-op fix expected).
  - T-042 Fix `srs_kmeans.py` (Label output: add `ome=item.meta.ome`).
  - T-043 Confirm `srs_calibrate.py` Mode C via `model_dump+override` is correct.
  - T-044 For `srs_pca.py` / `srs_unmix.py`: document deliberate drop in audit
    report.
  - T-045 Add `test_processblock_meta_propagation.py` for SRS.
  - T-046 Commit `docs/audit/adr-043-srs-propagation-audit.md`.
  - Open B2 PR targeting umbrella.

**Phase C — Audit + integration (sequential after all of Phase A + B merged into umbrella):**

- **C1 — No-context audit** (agent: audit_reviewer; mode: no-context;
  branch: `track/adr-043/core-blocks-and-imaging/c1-audit`)
  - Verify FR-001 through FR-017 acceptance.
  - Verify ADR-043 §9 package validity scan green.
  - Verify capability synthesis is no longer required for in-tree
    LoadData/SaveData (registry indexes records with `is_synthesized=False`).
  - Codex auto-review consumed; P1/P2 reconciled.
  - Commit `docs/audit/adr-043-package-migration-final-audit-<sha>.md`.

- **C2 — Integration verification** (manager)
  - Run golden-path workflow: CZI → resize → save TIFF; verify pixel_size
    preserved end-to-end.
  - Run Chrome smoke test verifying capability dropdown + OME panel +
    lossy-save warning.
  - Verify CI green on umbrella PR.
  - Verify all sub-PRs are merged into umbrella.

**Phase D — Owner-authored end-to-end test cases (sequential after Phase C):**

This phase is a hard gate before final merge. The manager pauses Phase D entry
and requests the owner to provide end-to-end test scenarios that go beyond the
golden-path smoke covered in C2. The implementer agent then exercises every
owner-provided scenario against the integrated umbrella branch.

- **D1 — Owner test-case authoring** (owner-driven; manager pauses dispatch)
  - Manager notifies owner that Phase A + B + C are green on umbrella.
  - Owner provides e2e test case set covering: real-world workflow paths,
    cross-package interactions, UI flows, regression scenarios from prior
    incidents, and any spec-specific edge cases the owner wants validated.
  - Owner provides expected behavior / acceptance criteria per case.
  - Test cases are recorded in `docs/audit/adr-043-package-migration-e2e-cases.md`.

- **D2 — E2E execution** (agent: implementer or manager; branch:
  `track/adr-043/core-blocks-and-imaging/d2-e2e`)
  - Translate owner test cases into runnable e2e scenarios (Playwright /
    pytest / manual checklist as appropriate).
  - Execute each case against the integrated umbrella branch.
  - Record pass/fail per case in the audit doc.
  - For any failure: open targeted bug-fix issue, dispatch fix, re-run.

- **D3 — E2E gate** (manager)
  - All owner test cases MUST pass before umbrella PR is marked ready for
    final review.
  - Final umbrella PR rebase + final review request to owner.

### 4.4 Verification Plan

**Per-PR verification (every Phase A/B PR):**

- `ruff check .` + `ruff format --check .`.
- Targeted `pytest` against new test files (with `--timeout=60`).
- ADR-043 §9 package validity scan on the affected package.
- `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json`.
- Sentrux applicability check.
- All checks recorded via
  `python -m scistudio.qa.governance.gate_record check ...`.

**Integration verification (Phase C):**

- **SC-001 evidence:** ADR-043 §9 package validity scan returns 0 violations on
  LoadData/SaveData/LoadImage/SaveImage capability declarations.
- **SC-002 evidence:** Pytest fixture loads sample CZI/ND2/LIF/OIR files
  (committed under
  `packages/scistudio-blocks-imaging/tests/fixtures/microscopy/` or downloaded at
  test time); assertion `image.meta.ome.images[0].pixels.physical_size_x is not None`.
- **SC-003 evidence:** Golden-path test loads CZI → applies Resize(factor=0.5) →
  saves OME-TIFF → reloads saved file → asserts
  `loaded.meta.ome.images[0].pixels.physical_size_x == source_physical_size * 2.0`.
- **SC-004 evidence:** Test loads PNG with EXIF DPI → saves TIFF → reload →
  asserts pixel_size populated.
- **SC-005 evidence:** Chrome smoke test navigates to a workflow with ambiguous
  Image+TIFF port, verifies capability dropdown shows >=1 options, clicks OME
  panel button, verifies pixel_size renders.

**CI gates:**

- Pre-commit hooks: `python -m scistudio.qa.governance.gate_record pre-commit --staged`.
- Commit-msg hook: trailers present (`Gate-Record:`, `Task-Kind:`, `Issue:`,
  `Assisted-by:`).
- Pre-push hook: validate gate record.
- CI: full audit + ADR-043 §9 scan + Sentrux + frontend lint + frontend test.

### 4.5 Risks And Rollback

| Risk | Likelihood | Impact | Mitigation / Rollback |
|---|---|---|---|
| `cellprofiler/python-bioformats` is in maintenance mode (last release approximately 2-3 years ago); the JVM wrapper may regress on macOS Apple Silicon or break on python 3.13. | Medium | High (Bio-Formats family broken) | Mitigation: pin a tested release. Rollback target candidates: (1) `scyjava` + `bioformats_jar` (more modern Java bridge), (2) `bioio` family (per-format native readers). If wrapper is unmaintainable, file a follow-up issue under #1204 to migrate; Bio-Formats capabilities can stay declared but raise "deprecated handler" until migrated. |
| JVM cold start (3-5s) is paid once per block process; if SciStudio moves to short-lived worker subprocesses (one block per process), the JVM startup dominates microscopy load times. | Low | Medium | Mitigation: spec calls out the dependency on block process longevity. If worker model changes, JVM pooling or pre-warm subprocess strategy needs to be designed (separate issue). |
| `ome-types` major version drift breaking pydantic v2 model API. | Low | Medium | Mitigation: pin `ome-types>=0.5,<0.6` in pyproject.toml; integration tests assert at least one OME read survives version churn. Rollback: if 0.5.x has a regression, downgrade pin to last known good. |
| ProcessBlock propagation audit may surface unforeseen edge cases (e.g. a block both projects axes AND drops type — Mode B + Mode C interleaved). | Medium | Medium | Mitigation: Mode C explicitly allows per-block decision; audit reports record the decision. Rollback: any single block's propagation can be deferred to a follow-up issue without blocking other phases. |
| Image.Meta.ome field addition may break existing pydantic model_dump tests that count fields. | Medium | Low | Mitigation: pre-emptive grep for `model_dump` / `Image.Meta` usages in tests during A2; update fixtures accordingly. |
| Bio-Formats handler lazy import strategy must coordinate with `BlockRegistry`'s capability indexing (capabilities indexed at scan time but handler import deferred). | Medium | Medium | Mitigation: capability records declare the import target separately from the handler symbol; registry surfaces capability metadata even when handler is not importable, but `find_loader_capability` raises if the user tries to dispatch a capability whose handler module is unimportable. |
| Frontend UI work (A3) may diverge from backend capability schema if developed in parallel without close coordination. | Low | Medium | Mitigation: manager checklist row tracks A2's API contract changes; A3 agent reads A2's capability-API schema before implementing dropdown. Chrome smoke test in Phase C catches drift. |

**Rollback strategy:**

- The umbrella branch + per-phase PRs structure means any single PR can be
  reverted without unblocking the others (modulo Phase B depending on A2).
- Capability migration is additive: explicit `format_capabilities` declarations
  supersede the synthesized fallback. If a regression appears, the legacy
  `supported_extensions` ClassVar can be restored temporarily (FR-003 reverted),
  and the synthesized fallback re-engages.
- `Image.Meta.ome` field defaults to `None`; adding the field is
  backward-compatible with existing pydantic deserialization (missing field
  defaults to None). If `ome-types` is uninstallable in some environment, the
  field type can be downgraded to `dict | None` as an emergency fallback (typed
  Meta declaration downgraded to `format_specific` with
  `format_metadata_reads=("ome_xml_str",)`).

## 5. Success Criteria

### Measurable Outcomes

- **SC-001:** ADR-043 §9 package validity scan returns 0 violations on
  `LoadData`, `SaveData`, `LoadImage`, `SaveImage`. Measurement: run
  `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json`
  and grep for `"adr043"` violations in the output. Target: zero entries.

- **SC-002:** With `imaging[bioformats]` extras installed, loading a
  CZI/ND2/LIF/OIR test fixture returns an `Image` whose
  `meta.ome.images[0].pixels.physical_size_x` is non-None. Measurement: pytest
  fixture in `packages/scistudio-blocks-imaging/tests/test_bioformats_handler.py`.
  Target: green for each Bio-Formats subset member with a committed or
  downloadable fixture.

- **SC-003:** End-to-end OME propagation golden path: load CZI →
  `Resize(factor=0.5)` → `SaveImage(out.ome.tif)` → reload out.ome.tif. After
  reload, `image.meta.ome.images[0].pixels.physical_size_x` equals the original
  `physical_size_x * 2.0` within numerical tolerance (1e-6). Measurement:
  integration test. Target: green.

- **SC-004:** PNG / JPEG round-trip preserves EXIF-mappable OME fields. Load a
  PNG with EXIF DPI → save to TIFF → reload TIFF → assert
  `meta.ome.images[0].pixels.physical_size_*` is populated. Measurement:
  integration test. Target: green.

- **SC-005:** Frontend Chrome smoke test passes: open a workflow with an
  ambiguous Image+TIFF port, verify capability dropdown shows >=2 options when
  the registry has multiple capabilities for
  `(direction=load, data_type=Image, extension=.tif)`; click OME button on an
  output preview, verify the panel renders at least one OME field.
  Measurement: Chrome MCP smoke test scripted in the test harness. Target:
  green.

- **SC-006:** Every owner-authored end-to-end test case in Phase D (recorded in
  `docs/audit/adr-043-package-migration-e2e-cases.md`) passes against the
  integrated umbrella branch. Measurement: per-case pass/fail recorded in the
  audit doc and reflected in the umbrella PR final-review checklist. Target:
  100% pass on owner-provided cases; any failure blocks final merge until
  fixed.

## 6. Assumptions

- **A1 (inferred):** `ome-types>=0.5,<0.6` pydantic v2 model is stable across the
  spec implementation lifetime (approximately 2-3 weeks). Source: ome-types
  current release cadence on PyPI.

- **A2 (existing-system):** imaging + SRS ProcessBlock audit fan-out is
  approximately 30 files total (initial grep showed approximately 25 in imaging
  + approximately 10 in SRS). Source: file inspection on 2026-05-20.

- **A3 (existing-system):** Frontend block port editor surface
  (AppBlock / CodeBlock / IO blocks) shares one `PortEditor` React component
  such that the new `CapabilityDropdown` is reusable across all three. Source:
  existing-system inferred; the A3 agent verifies before coding.

- **A4 (inferred):** `cellprofiler/python-bioformats` continues to install and
  run on the targeted SciStudio CI environment (Linux + Windows + macOS Intel;
  macOS Apple Silicon verified on best-effort basis). Source: community
  evidence on the project's GitHub issue tracker.

- **A5 (adr):** ADR-043's existing scaffolding (`FormatCapability`,
  `MetadataFidelity`, `SimpleLoader`/`SimpleSaver`,
  `BlockRegistry.find_loader_capability`/`find_saver_capability`,
  `materialise_to_file`/`reconstruct_from_file`) is functionally complete and
  does not require schema-level changes. Source: ADR-043 Accepted 2026-05-19;
  verified by grep on 2026-05-20.

- **A6 (spec):** The legacy `supported_extensions` ClassVar on `IOBlock` base
  class is intentionally NOT removed (per scope.out); it remains the synthesis
  fallback for unmigrated third-party packages. Source: this spec's scope.out
  declaration.

- **A7 (existing-system):** Existing `Image.with_meta()` immutable update
  mechanism propagates new typed Meta fields automatically as long as the new
  field is declared on `Image.Meta`. No DataObject base class change required.
  Source: `src/scistudio/core/types/base.py` `with_meta` implementation read on
  2026-05-20.
