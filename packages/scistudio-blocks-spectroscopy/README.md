# scistudio-blocks-spectroscopy

General 1-D spectroscopy blocks for SciStudio (Raman, FTIR, UV-Vis,
fluorescence, NIR). Implements the design recorded in
`docs/specs/spectroscopy-package.md` (spec `001-spectroscopy-package`).

This package is independent of `scistudio-blocks-srs`; SRS imaging workflows and
SRS spectral cubes are out of scope (FR-002).

## Status

Skeleton (issue #1661): every block declares its full, stable port/config/
capability contract; executable bodies raise `NotImplementedError` with a
structured implementation plan referencing the spec FRs. Implementers fill the
bodies. The two foundation types and the previewers are functional.

## Data types

- `Spectrum(Series)` — one 1-D spectrum (`lambda` index, `intensity` value).
  Build/read through `_support.build_spectrum` / `spectrum_arrays` /
  `derive_spectrum`.
- `SpectralDataset(CompositeData)` — many spectra as an `index` table plus a
  long-form `spectra` table. A spectral library is a dataset with the
  appropriate `dataset_role`.

## Block groups (26 blocks)

| Group | Blocks |
| --- | --- |
| utilities | LoadSpectrum, SaveSpectrum, LoadSpectralDataset, SaveSpectralDataset, SpectrumToSpectralDataset, SpectralDatasetToSpectrum, FilterSpectralDataset, MergeSpectralDataset, AttachFeaturesToSpectralDataset |
| preprocessing | CropSpectrumRange, ShiftSpectralAxis, BaselineCorrection, SmoothSpectrum, AlignAndResampleSpectra, NormalizeSpectrum, SubtractPeakComponent |
| feature_extraction | ExtractIntensity, CalculateAUC, CalculateCentroid, CalculateRatio, FindPeaks |
| peak_fitting | FitPeak |
| reference_correction | SubtractReferenceSpectrum, DivideByReferenceSpectrum |
| library_matching | MatchSpectralLibrary |
| unmixing | SpectralUnmixing |

## Previewers

- `spectroscopy.spectrum.viewer` (`Spectrum`, SERIES envelope).
- `spectroscopy.spectral_dataset.viewer` (`SpectralDataset`, COMPOSITE envelope).

## Dependencies

`scistudio`, `numpy`, `scipy`, `pandas`, `pyarrow`, `pydantic`. scipy is
lazy-imported inside block bodies; importing the package never requires scipy.
