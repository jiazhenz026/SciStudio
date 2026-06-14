# scistudio-blocks-spectroscopy

General spectroscopy package for ordinary 1-D spectra such as Raman, FTIR,
UV-Vis, fluorescence, and NIR data.

This package exposes exactly two public data types in this implementation
slice:

- `Spectrum`, a `Series` subclass with canonical `lambda` and `intensity`
  axes.
- `SpectralDataset`, a `CompositeData` subclass with `index` and `spectra`
  table slots.

The utility block set includes load/save blocks for spectra and spectral
datasets, conversion between `Collection[Spectrum]` and `SpectralDataset`,
dataset filtering and merging, and feature-table attachment. File support is
declared through ADR-043 `FormatCapability` records on IO blocks; the data types
do not declare file extensions.

Vendor and instrument-native formats are load-only in this package. Until
native binary readers are added under a tracked owner-approved follow-up, those
handlers accept deterministic pseudo text fixtures so package tests and workflow
examples can exercise the declared boundary contracts without depending on
vendor SDKs.
