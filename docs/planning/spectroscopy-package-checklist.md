# scistudio-blocks-spectroscopy Implementation Checklist

> Mandatory tracking doc for the claudecode umbrella implementation of
> `docs/specs/spectroscopy-package.md` (spec 001). Single source of truth.
> Every agent edits ONLY the rows it owns and appends `→ <branch/commit/test>`
> to each tick. Drift = protocol violation.
>
> - Issue: #1661 `[claudecode]`
> - Integration branch: `claudecode/spectroscopy-package` (umbrella; PR → main closes #1661)
> - Gate ledger: `.workflow/records/1661-spectroscopy-package.json` (feature, manager, Tier-1)
> - Contract reference (out-of-repo, read-only): `C:/Users/jiazh/desktop/workspace/spectro-contract-digest.md`
> - Independent of #1660 `[codex]`; ignore that effort.

## Conventions
- `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked
- Feature branches: `claudecode/spectro/<track>` off the integration branch.
- Implementers own ONE disjoint group module each; tests/ is owned by test engineers.

## Phase 0 — Foundation (manager-authored, in integration worktree)
- [ ] pyproject.toml (hatchling, 3 entry points, deps)
- [ ] `__init__.py` (get_blocks/get_types/get_block_package/get_package_info/get_previewers, BLOCKS aggregation)
- [ ] `types.py` — `Spectrum(Series)` + `SpectralDataset(CompositeData)` + Meta + validation helpers + get_types [FR-003..FR-016]
- [ ] `_support.py` — shared Spectrum build/read/derive helpers, dataframe_from_rows, grid utils (encodes data model)
- [ ] `blocks/__init__.py` — aggregate group `BLOCKS`
- [ ] `blocks/{utilities,preprocessing,feature_extraction,peak_fitting,reference_correction,library_matching,unmixing}.py` stubs (`BLOCKS=[]` + planned-class docstring)
- [ ] `previewers/__init__.py` (get_previewers wiring) + `previewers/providers.py` (functional providers) + `previewers/assets/viewer.js`
- [ ] README.md, tests/__init__.py, tests/conftest.py (sys.path shim)
- [ ] Foundation imports clean, ruff-clean, `pytest --collect-only` ok → push integration branch

## Phase 1 — Implementation (parallel, branch from integration after Phase 0)
### I-IO-A — Spectrum IO (Owner: io-spectrum) [blocks/io_spectrum.py]
- [ ] `LoadSpectrum` + `SaveSpectrum` with ADR-043 `format_capabilities` matrix [FR-034..FR-037, FR-128..FR-134, FR-142..FR-143]
- [ ] capabilities: txt/csv/tsv/xlsx/spectrum_json/jcamp_dx/spc load+save; vendor load-only (spa/opus/labspec/wdf/andor/spe)

### I-IO-B — SpectralDataset IO (Owner: io-dataset) [blocks/io_dataset.py]
- [ ] `LoadSpectralDataset` + `SaveSpectralDataset` + capabilities [FR-038/039, FR-135..FR-141]
- [ ] capabilities: manifest_json (CompositeData manifest+sidecar), xlsx (index/spectra/meta sheets), spc load+save; vendor load-only

### I-UTIL — conversion/filter/merge/attach (Owner: util) [blocks/utilities.py]
- [ ] `SpectrumToSpectralDataset`, `SpectralDatasetToSpectrum`, `FilterSpectralDataset`, `MergeSpectralDataset`, `AttachFeaturesToSpectralDataset` [FR-040..FR-052, FR-084/085]

### I-PRE — preprocessing (Owner: pre) [blocks/preprocessing.py]
- [ ] `CropSpectrumRange`, `ShiftSpectralAxis`, `BaselineCorrection`, `SmoothSpectrum`, `AlignAndResampleSpectra`, `NormalizeSpectrum`, `SubtractPeakComponent` [FR-053..FR-081]

### I-FEAT — feature extraction + peak fitting (Owner: feat) [blocks/feature_extraction.py, blocks/peak_fitting.py]
- [ ] `ExtractIntensity`, `CalculateAUC`, `CalculateCentroid`, `CalculateRatio`, `FindPeaks` [FR-082..FR-094]
- [ ] `FitPeak` [FR-113..FR-120]

### I-ANALYSIS — reference/library/unmixing (Owner: analysis) [blocks/reference_correction.py, blocks/library_matching.py, blocks/unmixing.py]
- [ ] `SubtractReferenceSpectrum`, `DivideByReferenceSpectrum` [FR-095..FR-103]
- [ ] `MatchSpectralLibrary` [FR-121..FR-126]
- [ ] `SpectralUnmixing` [FR-104..FR-112]

### I-PREV — previewers (Owner: prev) [previewers/providers.py, previewers/assets/]
- [ ] `SpectrumPreviewer` + `SpectralDatasetPreviewer` backend providers (bounded reads, diagnostics, export resources, honest metadata) + viewer.js [FR-017..FR-030]

## Phase 2 — Tests (parallel, branch from integration after Phase 1 merged)
### TE-CONTRACT — contract tests (Owner: te-contract) [tests/test_*]
- [ ] test_types, test_packaging, test_previewer_registration, test_format_capabilities
- [ ] test_spectrum_io, test_spectral_dataset_io, test_utility_blocks
- [ ] test_preprocessing_blocks, test_preprocessing_fit_outputs
- [ ] test_feature_extraction_blocks, test_peak_fitting_blocks
- [ ] test_reference_correction_blocks, test_library_matching_blocks, test_unmixing_blocks
- [ ] Assert SC-001..SC-055 coverage

### TE-E2E — e2e load-block-save workflows (Owner: te-e2e) [tests/e2e/, tests/test_e2e_*]
- [ ] pseudo-spectra generators (fixtures): gaussian/lorentzian peaks, baseline drift, noise, multi-sample datasets, library, vendor-ish text files
- [ ] per-block load→block→save workflow test with asserted outputs (every block group)
- [ ] boundary cases: empty range, grid mismatch, zero-division, duplicate IDs, missing peaks, single-point, NaN intensities
- [ ] test_spectrum_previewer, test_spectral_dataset_previewer

## Phase 3 — Integration & gate (manager)
- [ ] Merge all implementer branches into integration (disjoint group modules)
- [ ] Merge both test branches; finalize `get_blocks()` count == 26; `get_types()`==[Spectrum,SpectralDataset]
- [ ] `gate_record check` green (Tier-1 full mirror); fix cycles as needed
- [ ] README final; audit report committed (docs/audit/2026-06-14-spectroscopy-package.md)
- [ ] `gate_record finalize` (pre-PR) → open umbrella PR via `scripts/scistudio_pr_create.py` (Closes #1661) → finalize (post-PR) → CI green

## Acceptance criteria
- [ ] Package imports with no `scistudio_blocks_srs` dependency (SC-007)
- [ ] Exactly the spec-accepted blocks registered; no unaccepted analysis/calibration/clustering/reporting blocks (SC-047)
- [ ] All FR-001..FR-143 + SC-001..SC-055 satisfied
- [ ] One umbrella PR, CI green, #1661 closed on merge

## Drift log (append-only)
(empty)
