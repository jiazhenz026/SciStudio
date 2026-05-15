# SciEasy — Roadmap v0.3: Phase 10 — Integration & Domain Plugins

> **Scope**: Phase 10 — palette refinement, domain plugin packages, block-level
> testing, and end-to-end demo workflows with real data.
>
> **Prerequisite**: Phase 9 (AI services) complete. LLM providers, block/type
> generation, workflow synthesis, parameter optimization, and AI Chat frontend
> are all merged and CI-green.
>
> **Guiding rule**: each stage produces something testable. Every plugin package
> must have sample data, passing block tests, and at least one demo workflow
> before it is considered complete.

---

## Overview

Phase 10 is the **system integration and domain validation** phase. It proves
the entire SciEasy stack works end-to-end with real scientific data across
multiple modalities.

| Stage | Name | Goal |
|-------|------|------|
| 10.1 | Palette & Category Refinement | 3-level grouping, "Custom" classification |
| 10.2 | Domain Plugin Packages | 5 installable block packages |
| 10.3 | Block-Level Testing | Per-block validation with sample data |
| 10.4 | Demo Workflows | End-to-end multimodal scenarios with real data |

---

## Stage 10.1 — Palette & Category Refinement

**Goal**: the block palette supports 3-level grouping (Package > Category > Block)
and user-written drop-in blocks are classified under "Custom" — separate from
installed packages and base block classes.

### 10.1.1 Backend: Category ClassVar + Custom classification

- [ ] Add optional `category: ClassVar[str]` to `BlockBase` — blocks can declare
      their own category (e.g., `category = "segmentation"`) to override auto-inference
- [ ] Modify `_infer_category()` in `registry.py`:
  1. Check `category` ClassVar on the block class first
  2. Fall back to class-hierarchy inference (IOBlock -> "io", ProcessBlock -> "process", etc.)
- [ ] Classify user drop-in blocks (Tier 1: `project/blocks/`, `~/.scieasy/blocks/`)
      under the **"Custom"** category by default unless they explicitly declare a category
- [ ] Entry-points blocks (Tier 2: installed packages) retain their declared or
      inferred category — they are NOT mixed into "Custom"
- [ ] Update `BlockSpec` to include a `source` field: `"builtin"`, `"package"`, or `"custom"`
- [ ] API: `GET /api/blocks/` response includes `source` and `category` fields

### 10.1.2 Frontend: 3-level palette grouping

- [ ] `BlockPalette.tsx`: implement 3-level collapsible tree:
  - **Level 1**: Package name (e.g., "SciEasy Core", "scieasy-image", "Custom")
  - **Level 2**: Category within package (e.g., "io", "process", "segmentation")
  - **Level 3**: Individual blocks
- [ ] "Custom" package always appears at the bottom of the palette
- [ ] Packages are collapsible; categories within are collapsible
- [ ] Search/filter still works across all levels
- [ ] Empty categories are hidden

### 10.1.3 Tests

- [ ] Backend: block with explicit `category` ClassVar -> correct category in registry
- [ ] Backend: drop-in block without category ClassVar -> classified as "Custom"
- [ ] Backend: entry-points block -> NOT classified as "Custom"
- [ ] Frontend: palette renders 3-level tree correctly (component test)

### Deliverable

```
Palette shows:
  SciEasy Core
    io
      Load Block, Save Block
    process
      ProcessBlock (base)
    code
      Python Block
    ...
  scieasy-image (if installed)
    segmentation
      CellposeSegment
    preprocessing
      BackgroundSubtract
  Custom
    (user's drop-in blocks here)
```

---

## Stage 10.2 — Domain Plugin Packages

**Goal**: develop 5 domain-specific block packages as installable Python
packages following the entry-points protocol (ADR-025/026). Each package
provides domain blocks, adapters, and sample data.

> **Important**: each package requires a domain-specific spec before implementation.
> Specs will be written collaboratively with the project owner who provides
> scientific domain knowledge. The pointers below indicate where each spec will live.

### Package architecture (common to all)

Each package follows the Block SDK template (ADR-026):

```
scieasy-{domain}/
  pyproject.toml          # entry_points: scieasy.blocks, scieasy.adapters, scieasy.types
  src/scieasy_{domain}/
    __init__.py           # PackageInfo descriptor
    blocks/               # domain-specific blocks
    adapters/             # file format adapters (if any)
    types/                # domain-specific DataObject subclasses (if any)
    sample_data/          # small test datasets bundled with the package
  tests/
    test_blocks.py        # block-level tests using sample_data
    test_adapters.py      # adapter round-trip tests
```

### 10.2.1 `scieasy-image` — Optical Microscopy Image Processing

**Spec**: `docs/specs/plugin-scieasy-image.md` *(to be written)*

Planned scope:
- [ ] **Types**: leverages core `Image` (y, x), `FluorImage` subtypes
- [ ] **Adapters**: TIFF / OME-TIFF reader/writer, CZI reader (zeiss), ND2 reader (nikon)
- [ ] **Blocks**:
  - Image preprocessing (background subtraction, flat-field correction, denoising)
  - Segmentation (Cellpose wrapper, thresholding, watershed)
  - Measurement (region properties, intensity quantification)
  - Visualization (overlay, montage, pseudo-color)
- [ ] **Sample data**: small fluorescence microscopy image (512x512, 3-channel)

### 10.2.2 `scieasy-raman` — Raman Spectroscopy

**Spec**: `docs/specs/plugin-scieasy-raman.md` *(to be written)*

Planned scope:
- [ ] **Types**: leverages core `RamanSpectrum(Spectrum)`
- [ ] **Adapters**: WDF reader (Renishaw), SPC reader, TXT/CSV spectral reader
- [ ] **Blocks**:
  - Preprocessing (baseline correction, cosmic ray removal, smoothing, normalization)
  - Peak analysis (peak detection, peak fitting, band assignment)
  - Multivariate analysis (PCA, MCR-ALS, spectral decomposition)
  - Classification (spectral matching, library search)
- [ ] **Sample data**: small Raman spectrum dataset (10-50 spectra, ~1000 wavenumber points)

### 10.2.3 `scieasy-lcms` — Liquid Chromatography - Mass Spectrometry

**Spec**: `docs/specs/plugin-scieasy-lcms.md` *(to be written)*

Planned scope:
- [ ] **Types**: leverages core `MassSpectrum(Spectrum)`, `MetabPeakTable(PeakTable)`
- [ ] **Adapters**: mzML reader, mzXML reader, CSV peak table import/export
- [ ] **Blocks**:
  - Raw data processing (chromatogram extraction, TIC/BPI generation)
  - Peak detection (XCMS-style, MZmine-style feature finding wrappers)
  - Alignment (retention time correction, sample alignment)
  - Annotation (compound identification, MS/MS matching, database search)
  - Statistics (fold change, t-test, volcano plot generation)
- [ ] **Sample data**: small mzML file (1 sample, limited m/z range)

### 10.2.4 `scieasy-srs-image` — Stimulated Raman Scattering Imaging

**Spec**: `docs/specs/plugin-scieasy-srs-image.md` *(to be written)*

Planned scope:
- [ ] **Types**: leverages core `SRSImage(Array)` (y, x, wavenumber)
- [ ] **Adapters**: hyperspectral SRS TIFF stack reader, HDF5 reader
- [ ] **Blocks**:
  - Preprocessing (background removal, signal normalization, hotpixel correction)
  - Spectral unmixing (MCR, NMF, phasor analysis)
  - Segmentation (spectral clustering, concentration mapping)
  - Quantification (component concentration maps, spatial statistics)
- [ ] **Sample data**: small SRS hyperspectral cube (128x128, 16 wavenumber channels)

### 10.2.5 `scieasy-ms-image` — Mass Spectrometry Imaging

**Spec**: `docs/specs/plugin-scieasy-ms-image.md` *(to be written)*

Planned scope:
- [ ] **Types**: leverages core `MSImage(Array)` (y, x, mz)
- [ ] **Adapters**: imzML reader, SCiLS export reader
- [ ] **Blocks**:
  - Preprocessing (spectral normalization, baseline removal, peak picking)
  - Ion image extraction (single ion, multi-ion overlay)
  - Segmentation (spatial clustering, region-of-interest extraction)
  - Co-localization (spatial correlation, multi-modal registration)
  - Annotation (lipid identification, metabolite mapping)
- [ ] **Sample data**: small imzML dataset (64x64 pixels, limited m/z range)

---

## Stage 10.3 — Block-Level Testing with Sample Data

**Goal**: every block in every plugin package has automated tests that run
with bundled sample data. Tests verify both correctness and contract compliance.

### 10.3.1 Test harness enhancements

- [ ] Extend `BlockTestHarness` (from Phase 8.5) to support plugin package testing:
  - Automatic discovery of `sample_data/` directory within packages
  - Fixture generation: `sample_image()`, `sample_spectrum()`, etc.
  - Contract assertion helpers: verify output types, port contracts, Collection wrapping
- [ ] CI integration: plugin packages can run `pytest` independently with their bundled data
- [ ] Cross-package test: blocks from different packages can be wired together

### 10.3.2 Per-package test matrix

For each of the 5 plugin packages:

- [ ] **Unit tests**: each block class runs with sample data, produces expected output type
- [ ] **Contract tests**: output Collection structure matches declared port types
- [ ] **Round-trip tests**: adapters can read and write the same format without data loss
- [ ] **Edge cases**: empty input, single-item Collection, mismatched types -> clear error messages
- [ ] **Performance baseline**: record wall-clock time for each block on sample data (not a pass/fail gate, but logged)

### 10.3.3 CI pipeline extension

- [ ] Add `[test-plugins]` optional dependency group for running plugin tests
- [ ] CI job: install all 5 plugin packages + run their test suites
- [ ] Plugin tests are isolated from core tests (can fail independently)

### Deliverable

```bash
# Run all plugin tests
pip install -e ".[test-plugins]"
pytest tests/plugins/ -v

# Run a single package's tests
pip install scieasy-image
pytest --pyargs scieasy_image.tests
```

---

## Stage 10.4 — Demo Workflows with Real Data

**Goal**: build end-to-end workflow YAML files that chain blocks from multiple
plugin packages, run them on real scientific datasets, and verify the full
stack (CLI + API + frontend + lineage + checkpoints).

### 10.4.1 Demo workflow definitions

Each demo workflow is a YAML file (location TBD — see Phase 10.4 deliverable)
with accompanying documentation:

- [ ] **Demo 1: Fluorescence Image Analysis**
  - Load TIFF -> Background Subtract -> Cellpose Segment -> Measure Regions -> Export CSV
  - Packages: `scieasy-image`
  - Validates: serial pipeline, image I/O, subprocess isolation (Cellpose)

- [ ] **Demo 2: Raman Spectral Processing**
  - Load Spectra -> Baseline Correct -> Normalize -> PCA -> Export Results
  - Packages: `scieasy-raman`
  - Validates: batch processing (Collection of spectra), multivariate analysis

- [ ] **Demo 3: LC-MS Metabolomics**
  - Load mzML -> Feature Detection -> RT Alignment -> Annotation -> Statistics -> Export
  - Packages: `scieasy-lcms`
  - Validates: multi-step pipeline, external tool wrappers

- [ ] **Demo 4: SRS Hyperspectral Imaging**
  - Load Hypercube -> Preprocess -> Spectral Unmix -> Segment -> Quantify -> Export Maps
  - Packages: `scieasy-srs-image`
  - Validates: large array handling, spectral decomposition

- [ ] **Demo 5: MS Imaging**
  - Load imzML -> Normalize -> Extract Ion Images -> Cluster -> Annotate -> Export
  - Packages: `scieasy-ms-image`
  - Validates: sparse spatial data, ion image extraction

- [ ] **Demo 6: Multimodal Integration (Capstone)**
  - Combine outputs from Demo 1 + Demo 2 + Demo 5 -> Cross-modal Registration -> Merge -> Report
  - Packages: `scieasy-image` + `scieasy-raman` + `scieasy-ms-image`
  - Validates: Collection transport across packages, merge blocks, lineage tracking across modalities

### 10.4.2 End-to-end verification checklist

For each demo workflow, verify:

- [ ] CLI execution: `scieasy run <demo-N.yaml>` completes successfully
- [ ] API execution: POST `/api/workflows/{id}/execute` triggers and completes
- [ ] Frontend execution: load workflow in GUI -> Run -> see progress + results
- [ ] Data preview: intermediate and final outputs visible in preview panel
- [ ] Lineage: full provenance graph traces from final output back to raw input
- [ ] Checkpoints: pause mid-workflow -> resume -> same final result
- [ ] "Start from here": re-run from a middle block -> correct partial execution
- [ ] Cancel + SKIPPED propagation: cancel a running block -> downstream marked SKIPPED
- [ ] Error handling: inject a bad parameter -> block fails gracefully with clear error

### 10.4.3 Performance profiling

- [ ] Run each demo workflow on progressively larger datasets
- [ ] Record: total wall-clock time, peak memory, per-block timing
- [ ] Identify bottlenecks: I/O bound vs compute bound vs overhead
- [ ] Optimize critical paths (deferred to Phase 11 if non-trivial)

### 10.4.4 Documentation

- [ ] `docs/getting-started.md` — tutorial based on Demo 1 (simplest)
- [ ] `examples/README.md` — overview of all demo workflows with setup instructions
- [ ] Per-demo README with expected output and screenshots

### Deliverable

```bash
# Full end-to-end capstone demo
scieasy gui
# Open browser -> Load "Multimodal Integration" workflow
# -> Run -> Watch all blocks execute -> Inspect lineage graph
# -> Verify all modalities merged correctly
```

---

## Milestone Summary

| Stage | Deliverable | Depends on |
|-------|-------------|------------|
| 10.1 | 3-level palette, "Custom" category | Phase 9 merged |
| 10.2 | 5 plugin packages (structure + blocks) | 10.1 (for category display) |
| 10.3 | Automated block tests with sample data | 10.2 (packages exist) |
| 10.4 | Demo workflows running end-to-end | 10.2 + 10.3 (blocks tested) |

**Phase 10 is complete when Demo 6 (Multimodal Integration) runs end-to-end
through CLI, API, and frontend with full lineage tracking.**

---

## Execution Notes

### Spec-first approach for plugin packages

Each of the 5 plugin packages in Stage 10.2 requires a domain-specific spec
before implementation begins. The spec defines:

- Exact block list with input/output port types
- Adapter formats and libraries
- Sample data requirements and sources
- Scientific workflow patterns the package must support

These specs are written collaboratively with the project owner who provides
domain expertise. Implementation agents receive the spec as their primary
requirement document.

### Parallelism opportunities

- Stage 10.1 is a small, focused change — can be done by a single agent
- Stage 10.2 packages are independent — up to 5 agents in parallel (after specs exist)
- Stage 10.3 tests can begin per-package as soon as that package is complete
- Stage 10.4 demos build incrementally (Demo 1-5 are independent; Demo 6 requires all)

### Risk assessment

| Risk | Mitigation |
|------|------------|
| Domain specs require project owner input | Pointer files created now; specs written before coding |
| External library dependencies (Cellpose, XCMS, etc.) | Wrap as AppBlock (subprocess isolation per ADR-017) |
| Large test data bloats the repo | Sample data is minimal; real data for 10.4 stored externally |
| Plugin package API may need iteration | Block SDK (ADR-026) provides stable contracts; iterate within packages |
