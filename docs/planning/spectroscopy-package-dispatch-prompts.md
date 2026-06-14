# Spectroscopy Package Dispatch Prompts

Use these prompts for manager-controlled sub-agent work on
`codex/spectroscopy-package-20260614`. Every agent must create or use its own
dedicated worktree/branch and must not write in the main checkout.

All agents must read:

- `AGENTS.md`
- `docs/ai-developer/rules.md`
- `docs/ai-developer/specific_rules/gated-workflow.md`
- `docs/specs/spectroscopy-package.md`
- the package development manuals under `docs/block-development/`
- ADR-043 and ADR-048 related docs/specs

## IO-UTIL Implementer

Persona: `implementer`
Task kind: `feature`
Allowed paths: `packages/scistudio-blocks-spectroscopy/**`

Implement the package skeleton, `Spectrum`, `SpectralDataset`, previewer
registration, spectroscopy format capabilities, and these utility blocks:

- `LoadSpectrum`
- `SaveSpectrum`
- `LoadSpectralDataset`
- `SaveSpectralDataset`
- `SpectrumToSpectralDataset`
- `SpectralDatasetToSpectrum`
- `FilterSpectralDataset`
- `MergeSpectralDataset`
- `AttachFeaturesToSpectralDataset`

Hard boundaries:

- Do not add public spectroscopy types beyond `Spectrum` and
  `SpectralDataset`.
- Do not add blocks outside the spec list.
- Implement vendor load-only handlers as deterministic, permissive parsers for
  pseudo text fixtures when native binary parsing is not available.
- Do not declare roundtrip or lossless support for vendor load-only formats.
- Add focused tests for type invariants, IO roundtrip formats, capability
  declarations, previewer registration, and utility behavior.

## PREPROC Implementer

Persona: `implementer`
Task kind: `feature`
Allowed paths: `packages/scistudio-blocks-spectroscopy/**`

Implement preprocessing blocks:

- `CropSpectrumRange`
- `ShiftSpectralAxis`
- `BaselineCorrection`
- `SmoothSpectrum`
- `AlignAndResampleSpectra`
- `NormalizeSpectrum`
- `SubtractPeakComponent`

Hard boundaries:

- Use only the `Spectrum` and `SpectralDataset` types from the package.
- Preserve metadata unless the spec requires a deterministic update.
- Handle single-spectrum and dataset inputs where required by the spec.
- Add focused tests for sorted and unsorted axes, empty ranges, zero norms,
  small windows, duplicated wavelengths, and dataset-wide processing.

## FEAT-FIT-REF Implementer

Persona: `implementer`
Task kind: `feature`
Allowed paths: `packages/scistudio-blocks-spectroscopy/**`

Implement feature extraction, peak fitting, and reference correction blocks:

- `ExtractIntensity`
- `CalculateAUC`
- `CalculateCentroid`
- `CalculateRatio`
- `FindPeaks`
- `FitPeak`
- `SubtractReferenceSpectrum`
- `DivideByReferenceSpectrum`

Hard boundaries:

- Feature outputs must use existing SciStudio `DataFrame` contracts.
- Reference correction must align spectra deterministically before arithmetic.
- Division must handle zero denominators according to explicit block
  parameters.
- Add focused tests for interpolation, integration windows, peak bounds,
  missing peaks, flat spectra, zero denominators, and reference axis mismatch.

## LIB-UNMIX Implementer

Persona: `implementer`
Task kind: `feature`
Allowed paths: `packages/scistudio-blocks-spectroscopy/**`

Implement library matching and spectral unmixing blocks:

- `MatchSpectralLibrary`
- `SpectralUnmixing`

Hard boundaries:

- Represent libraries with existing `SpectralDataset`/`DataFrame` contracts;
  do not create `SpectralLibrary` as a public type.
- Matching must be deterministic and expose scores in a `DataFrame`.
- Unmixing must expose coefficients and residuals in stable typed outputs.
- Add focused tests for cosine/correlation style scoring, no matches,
  duplicate references, non-negative coefficients, and ill-conditioned inputs.

## Contract Test Engineer

Persona: `test_engineer`
Task kind: `feature`
Allowed paths: `packages/scistudio-blocks-spectroscopy/tests/**`

Design and implement complete contract tests for the spectroscopy package:

- exact public type and block exports
- block contracts and parameter defaults
- type metadata and dataset slot invariants
- ADR-043 format capability matrix
- previewer registration through `scistudio.previewers`
- edge behavior for all blocks

Do not change production code unless the manager asks you to fix a localized
test-discovered defect.

## E2E Test Engineer

Persona: `test_engineer`
Task kind: `feature`
Allowed paths: `packages/scistudio-blocks-spectroscopy/tests/**`

Create deterministic pseudo spectroscopy fixtures and a load-block-save workflow
test for every public block:

- load a pseudo spectrum or spectral dataset
- execute one target block
- save the result
- reload or inspect the saved output
- assert exact output data and metadata

Cover all 26 public blocks and include boundary workflows for empty or tiny
spectra, non-overlapping ranges, negative intensities, flat baselines, reference
axis mismatches, unmatched library entries, and ill-conditioned unmixing.
