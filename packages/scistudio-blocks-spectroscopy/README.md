# scistudio-blocks-spectroscopy

General 1-D spectroscopy blocks for SciStudio (Raman, FTIR, UV-Vis,
fluorescence, NIR). Implements the design recorded in
`docs/specs/spectroscopy-package.md` (spec `001-spectroscopy-package`).

This package is independent of `scistudio-blocks-srs`; SRS imaging workflows and
SRS spectral cubes are out of scope (FR-002). Importing this package never
imports `scistudio_blocks_srs`.

## Data types

- `Spectrum(Series)` - one 1-D spectrum (`lambda` index, `intensity` value;
  FR-003/004). Typed `Meta` carries `lambda_unit`, `intensity_unit`,
  `lambda_kind`, `modality`, plus `spectrum_id`/`source_file` provenance. Build
  and read it through the package helpers in `scistudio_blocks_spectroscopy._support`
  (`build_spectrum`, `spectrum_arrays`, `derive_spectrum`).
- `SpectralDataset(CompositeData)` - many spectra as an `index` table (one row
  per spectrum, unique `spectrum_id` plus arbitrary metadata) plus a long-form
  `spectra` table (`spectrum_id`, `lambda`, `intensity`). A spectral library is
  a dataset with `meta.dataset_role="library"` (FR-014); there is no separate
  library type.

Format support is not declared on the types (FR-131); it lives on the IO blocks
as ADR-043 `FormatCapability` records.

## Blocks (26)

| Group | Blocks |
| --- | --- |
| utilities | LoadSpectrum, SaveSpectrum, LoadSpectralDataset, SaveSpectralDataset, SpectrumToSpectralDataset, SpectralDatasetToSpectrum, FilterSpectralDataset, MergeSpectralDataset, AttachFeaturesToSpectralDataset |
| preprocessing | CropSpectrumRange, ShiftSpectralAxis, BaselineCorrection, SmoothSpectrum, AlignAndResampleSpectra, NormalizeSpectrum, SubtractPeakComponent |
| feature_extraction | ExtractIntensity, CalculateAUC, CalculateCentroid, CalculateRatio, FindPeaks |
| peak_fitting | FitPeak |
| reference_correction | SubtractReferenceSpectrum, DivideByReferenceSpectrum |
| library_matching | MatchSpectralLibrary |
| unmixing | SpectralUnmixing |

Preprocessing, feature extraction, peak fitting, reference correction, and
unmixing operate on `Collection[Spectrum]`. Dataset workflows convert with
`SpectralDatasetToSpectrum` / `SpectrumToSpectralDataset` around them. Feature
and diagnostics outputs are flat `DataFrame`s keyed by `spectrum_id`, mergeable
back onto `SpectralDataset.index` with `AttachFeaturesToSpectralDataset`.

## IO format support (ADR-043)

The four IO blocks declare explicit `FormatCapability` records (FR-128..FR-143).

- **Round-trippable and advertised:** delimited text `.txt`/`.csv`/`.tsv`,
  Excel `.xlsx`, package-native lossless `.spectrum.json` for `Spectrum`,
  package-native JSON manifest plus Parquet sidecars for `SpectralDataset`, and
  JCAMP-DX `.jdx`/`.dx`/`.jcamp` for `Spectrum`.
- **Deferred and not advertised:** SPC (`.spc`) and vendor/instrument-native
  formats are intentionally not exposed through `FormatCapability` records in
  this draft. Direct handler entry points remain tracked with `TODO(#1661)` and
  raise informative `NotImplementedError` until fixture data or an optional SDK
  proves real load/save behavior. Unsupported suffix selection through the IO
  blocks fails before a deferred handler is selected.

## Previewers (ADR-048)

- `spectroscopy.spectrum.viewer` (`Spectrum`, SERIES envelope) - bounded
  two-column read, axis units, pan/zoom hoverable line plot, honest sampling
  metadata, diagnostics, and SVG/PNG/PDF/points exports.
- `spectroscopy.spectral_dataset.viewer` (`SpectralDataset`, COMPOSITE envelope)
  - paginated/searchable/selectable index table, group/color controls, bounded
  overlay/selected/group mean/group band/heatmap plot payloads, dataset health
  diagnostics (duplicate/orphan/missing coverage/unit/heatmap-alignment), and
  preview exports.

## Dependencies

`scistudio`, `numpy`, `scipy`, `pandas`, `pyarrow`, `pydantic`, `openpyxl`
(for `.xlsx`). Heavy scientific libraries (`scipy`, `openpyxl`) are
lazy-imported inside block bodies, so importing the package and registering its
blocks never requires them.

## Testing

```bash
pytest packages/scistudio-blocks-spectroscopy/tests
```

Covers type/packaging/previewer-registration contracts, ADR-043 format
capabilities, per-block contract tests (SC-001..SC-055), and an end-to-end
`tests/e2e/` suite of pseudo-spectra generators plus load/block/save workflows,
boundary cases, and chained pipelines.
