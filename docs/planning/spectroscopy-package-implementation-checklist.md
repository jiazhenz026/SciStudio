# Spectroscopy Package Implementation Checklist

Issue: #1660
Branch: `codex/spectroscopy-package-20260614`
Protected base: `main`
Umbrella PR: #1663 (`[DO NOT MERGE] [codex] Implement spectroscopy package`)
Gate record: `.workflow/records/1660-codex-spectroscopy-package-20260614.json`

This checklist is the manager-facing coordination artifact for the codex
umbrella PR implementing `docs/specs/spectroscopy-package.md`.

## Source Documents

- [x] `docs/specs/spectroscopy-package.md`
- [x] `docs/block-development/quickstart.md`
- [x] `docs/block-development/block-contract.md`
- [x] `docs/block-development/data-types.md`
- [x] `docs/block-development/custom-types.md`
- [x] `docs/block-development/previewers-and-plots.md`
- [x] `docs/block-development/publishing.md`
- [x] `docs/block-development/testing.md`
- [x] `docs/specs/adr-043-io-format-capability-registry.md`
- [x] `docs/specs/adr-048-preview-system.md`
- [x] `docs/adr/ADR-025.md`
- [x] `docs/adr/ADR-027.md`
- [x] `docs/adr/ADR-043.md`
- [x] `docs/adr/ADR-047.md`
- [x] `docs/adr/ADR-048.md`

## Non-Negotiable Package Scope

- [ ] Create package `packages/scistudio-blocks-spectroscopy`.
- [ ] Do not depend on the SRS package.
- [ ] Export exactly the public types required by the spec: `Spectrum` and
  `SpectralDataset`.
- [ ] Export exactly the 26 required public blocks. Do not add calibration,
  clustering, PCA, reporting, or unstated convenience blocks.
- [ ] Use formal block contracts, typed inputs and outputs, deterministic
  metadata behavior, and no frontend-state runtime truth.
- [ ] Register previewers through `scistudio.previewers`; previewers remain
  display-only and perform no scientific processing.
- [ ] Implement ADR-043 format capability declarations for spectroscopy IO.

## Required Types

- [ ] `Spectrum(Series)` uses canonical `index_name="lambda"` and
  `value_name="intensity"`.
- [ ] `Spectrum.Meta` records `lambda_unit`, `intensity_unit`, `lambda_kind`,
  and `modality`.
- [ ] `SpectralDataset(CompositeData)` has exactly slots `index: DataFrame`
  and `spectra: DataFrame`.
- [ ] Dataset `index` has required column `spectrum_id`.
- [ ] Dataset `spectra` has required columns `spectrum_id`, `lambda`,
  `intensity`.
- [ ] `SpectralDataset.Meta` records `dataset_name`, `dataset_role`,
  `lambda_unit`, `intensity_unit`, `modality`, and `schema_version`.

## Agent Slices

### IO-UTIL Implementer

- [x] Dispatched to Mencius (`019ec527-3ea9-7872-bebd-f8f80691d446`).
- [ ] Package skeleton, README, exports, format capabilities, and previewers.
- [ ] `LoadSpectrum`
- [ ] `SaveSpectrum`
- [ ] `LoadSpectralDataset`
- [ ] `SaveSpectralDataset`
- [ ] `SpectrumToSpectralDataset`
- [ ] `SpectralDatasetToSpectrum`
- [ ] `FilterSpectralDataset`
- [ ] `MergeSpectralDataset`
- [ ] `AttachFeaturesToSpectralDataset`

### PREPROC Implementer

- [x] Dispatched to Carver (`019ec527-8553-7f22-963e-f410a74306c4`).
- [ ] `CropSpectrumRange`
- [ ] `ShiftSpectralAxis`
- [ ] `BaselineCorrection`
- [ ] `SmoothSpectrum`
- [ ] `AlignAndResampleSpectra`
- [ ] `NormalizeSpectrum`
- [ ] `SubtractPeakComponent`

### FEAT-FIT-REF Implementer

- [x] Dispatched to Huygens (`019ec527-d286-7fa3-82ad-7e31564aacb4`).
- [ ] `ExtractIntensity`
- [ ] `CalculateAUC`
- [ ] `CalculateCentroid`
- [ ] `CalculateRatio`
- [ ] `FindPeaks`
- [ ] `FitPeak`
- [ ] `SubtractReferenceSpectrum`
- [ ] `DivideByReferenceSpectrum`

### LIB-UNMIX Implementer

- [x] Dispatched to Ramanujan (`019ec528-712a-7070-ac36-be844a659108`).
- [ ] `MatchSpectralLibrary`
- [ ] `SpectralUnmixing`

## Test Engineering Slices

### Contract Test Engineer

- [ ] Assert public exports, exact block list, and no unstated public blocks.
- [ ] Assert type metadata, required dataset slots, and required columns.
- [ ] Assert IO format capability matrix, including load-only vendor formats.
- [ ] Assert every block has formal contract inputs, outputs, and stable
  parameters matching the spec.
- [ ] Assert edge behavior for empty spectra, single-point spectra, unsorted
  axes, duplicated wavelengths, zero denominators, missing ids, and missing
  feature values where applicable.

### E2E Test Engineer

- [ ] Generate deterministic pseudo-spectrum fixtures.
- [ ] For each of the 26 public blocks, build a load-block-save workflow test.
- [ ] For every workflow, assert saved output data and metadata match expected
  values.
- [ ] Include boundary workflows for short spectra, negative intensities, flat
  baselines, non-overlapping ranges, unmatched references, and ill-conditioned
  unmixing inputs.

## Integration Gates

- [x] Manager umbrella branch created before dispatch.
- [x] `[DO NOT MERGE]` umbrella PR #1663 opened before dispatch.
- [x] Initial draft PR was created with the gate-aware wrapper and
  `SCISTUDIO_SKIP_PREFLIGHT=1` because implementation was intentionally not
  complete yet.
- [ ] All package tests pass locally.
- [ ] Gate record `check --mode pre-pr` passes.
- [ ] Gate record `finalize` records the PR URL.
- [ ] Umbrella PR closes #1660.
- [ ] CI passes before the work is considered complete.
- [ ] After implementation, test design, gate checks, and CI complete, retitle
  PR #1663 from `[DO NOT MERGE]` to `[READY FOR REVIEW]`.
