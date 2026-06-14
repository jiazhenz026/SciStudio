# Spectroscopy Package Implementation Checklist

Issue: #1660
Branch: `codex/spectroscopy-package-20260614`
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

- [ ] `CropSpectrumRange`
- [ ] `ShiftSpectralAxis`
- [ ] `BaselineCorrection`
- [ ] `SmoothSpectrum`
- [ ] `AlignAndResampleSpectra`
- [ ] `NormalizeSpectrum`
- [ ] `SubtractPeakComponent`

### FEAT-FIT-REF Implementer

- [ ] `ExtractIntensity`
- [ ] `CalculateAUC`
- [ ] `CalculateCentroid`
- [ ] `CalculateRatio`
- [ ] `FindPeaks`
- [ ] `FitPeak`
- [ ] `SubtractReferenceSpectrum`
- [ ] `DivideByReferenceSpectrum`

### LIB-UNMIX Implementer

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

- [ ] All package tests pass locally.
- [ ] Gate record `check --mode pre-pr` passes.
- [ ] Gate record `finalize` records the PR URL.
- [ ] Umbrella PR closes #1660.
- [ ] CI passes before the work is considered complete.
