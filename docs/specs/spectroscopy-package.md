---
spec_id: 001-spectroscopy-package
title: "Spectroscopy Package Specification"
status: Clarifying
feature_branch: codex/spectroscopy-package-spec
created: 2026-06-14
input: "Owner-directed design session for scistudio-blocks-spectroscopy: define the Spectroscopy package as an independent general spectroscopy package, starting with Spectrum and SpectralDataset data types, SpectrumPreviewer and SpectralDatasetPreviewer requirements, accepted utility/preprocessing block sets, the feature-table mapping contract, feature extraction/measurement blocks, peak fitting, reference correction blocks, spectral library matching, and spectral unmixing blocks before block-by-block design continues."
owners:
  - "@jiazhenz026"
related_adrs:
  - 27
  - 43
  - 48
related_specs:
  - adr-048-preview-system
  - adr-043-package-migration
scope:
  in:
    - "General spectroscopy package identity for Raman, FTIR, UV-Vis, fluorescence, NIR, and other ordinary 1-D spectral data."
    - "The accepted type design for Spectrum and SpectralDataset."
    - "The accepted previewer design for SpectrumPreviewer and SpectralDatasetPreviewer, including first-class export/save behavior."
    - "The accepted utility blocks for loading, saving, converting, filtering, merging, and attaching feature tables to Spectrum and SpectralDataset values."
    - "The accepted ADR-043-compliant IO format capability matrix for Spectrum and SpectralDataset load/save blocks."
    - "The accepted preprocessing blocks for Collection[Spectrum] workflows."
    - "The accepted feature extraction and measurement blocks for intensity, AUC, centroid, peak-to-peak ratio, and peak finding."
    - "The accepted peak fitting block for Gaussian, Lorentzian, and Voigt peak fits with fitted curves, residuals, and parameter/feature outputs."
    - "The accepted reference correction blocks for subtracting or dividing Collection[Spectrum] values by one reference Spectrum."
    - "The accepted spectral library matching block with selectable matching methods."
    - "The accepted spectral unmixing block with method selection, wide coefficient-matrix output, and separate fit-quality output."
    - "Owner-approved utility, IO, preprocessing, analysis, and reporting blocks as they are added through continuing design discussion."
    - "Explicit separation between preview-only exploration and workflow-producing processing blocks."
  out:
    - "SRS package behavior, SRS imaging cubes, and SRS-specific block contracts."
    - "Specific spectroscopy block names and algorithms beyond the accepted utility, preprocessing, feature extraction, peak fitting, reference correction, library matching, and spectral unmixing blocks; calibration, clustering, reporting, and additional analysis blocks otherwise remain pending owner discussion."
    - "A FeatureTable type; feature outputs should remain ordinary DataFrame instances unless a later owner decision changes this."
    - "A separate SpectralLibrary type; spectral libraries are represented as SpectralDataset instances."
    - "Implementation, package skeleton, PR sequencing, or release planning beyond the planned affected surfaces listed here."
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/spectroscopy-package.md
  excludes: []
planned_governs:
  modules:
    - scistudio_blocks_spectroscopy
  contracts:
    - scistudio_blocks_spectroscopy.types.Spectrum
    - scistudio_blocks_spectroscopy.types.SpectralDataset
    - scistudio_blocks_spectroscopy.previewers.get_previewers
    - scistudio_blocks_spectroscopy.blocks.utilities.LoadSpectrum
    - scistudio_blocks_spectroscopy.blocks.utilities.LoadSpectrum.format_capabilities
    - scistudio_blocks_spectroscopy.blocks.utilities.SaveSpectrum
    - scistudio_blocks_spectroscopy.blocks.utilities.SaveSpectrum.format_capabilities
    - scistudio_blocks_spectroscopy.blocks.utilities.LoadSpectralDataset
    - scistudio_blocks_spectroscopy.blocks.utilities.LoadSpectralDataset.format_capabilities
    - scistudio_blocks_spectroscopy.blocks.utilities.SaveSpectralDataset
    - scistudio_blocks_spectroscopy.blocks.utilities.SaveSpectralDataset.format_capabilities
    - scistudio_blocks_spectroscopy.blocks.utilities.SpectrumToSpectralDataset
    - scistudio_blocks_spectroscopy.blocks.utilities.SpectralDatasetToSpectrum
    - scistudio_blocks_spectroscopy.blocks.utilities.FilterSpectralDataset
    - scistudio_blocks_spectroscopy.blocks.utilities.MergeSpectralDataset
    - scistudio_blocks_spectroscopy.blocks.utilities.AttachFeaturesToSpectralDataset
    - scistudio_blocks_spectroscopy.blocks.preprocessing.CropSpectrumRange
    - scistudio_blocks_spectroscopy.blocks.preprocessing.ShiftSpectralAxis
    - scistudio_blocks_spectroscopy.blocks.preprocessing.BaselineCorrection
    - scistudio_blocks_spectroscopy.blocks.preprocessing.SmoothSpectrum
    - scistudio_blocks_spectroscopy.blocks.preprocessing.AlignAndResampleSpectra
    - scistudio_blocks_spectroscopy.blocks.preprocessing.NormalizeSpectrum
    - scistudio_blocks_spectroscopy.blocks.preprocessing.SubtractPeakComponent
    - scistudio_blocks_spectroscopy.blocks.feature_extraction.ExtractIntensity
    - scistudio_blocks_spectroscopy.blocks.feature_extraction.CalculateAUC
    - scistudio_blocks_spectroscopy.blocks.feature_extraction.FindPeaks
    - scistudio_blocks_spectroscopy.blocks.feature_extraction.CalculateCentroid
    - scistudio_blocks_spectroscopy.blocks.feature_extraction.CalculateRatio
    - scistudio_blocks_spectroscopy.blocks.peak_fitting.FitPeak
    - scistudio_blocks_spectroscopy.blocks.reference_correction.SubtractReferenceSpectrum
    - scistudio_blocks_spectroscopy.blocks.reference_correction.DivideByReferenceSpectrum
    - scistudio_blocks_spectroscopy.blocks.library_matching.MatchSpectralLibrary
    - scistudio_blocks_spectroscopy.blocks.unmixing.SpectralUnmixing
  entry_points:
    - scistudio.blocks
    - scistudio.types
    - scistudio.previewers
  files:
    - packages/scistudio-blocks-spectroscopy/**
  excludes: []
tests:
  - packages/scistudio-blocks-spectroscopy/tests/test_types.py
  - packages/scistudio-blocks-spectroscopy/tests/test_previewer_registration.py
  - packages/scistudio-blocks-spectroscopy/tests/test_spectrum_previewer.py
  - packages/scistudio-blocks-spectroscopy/tests/test_spectral_dataset_previewer.py
  - packages/scistudio-blocks-spectroscopy/tests/test_spectrum_io.py
  - packages/scistudio-blocks-spectroscopy/tests/test_spectral_dataset_io.py
  - packages/scistudio-blocks-spectroscopy/tests/test_format_capabilities.py
  - packages/scistudio-blocks-spectroscopy/tests/test_utility_blocks.py
  - packages/scistudio-blocks-spectroscopy/tests/test_preprocessing_blocks.py
  - packages/scistudio-blocks-spectroscopy/tests/test_preprocessing_fit_outputs.py
  - packages/scistudio-blocks-spectroscopy/tests/test_feature_extraction_blocks.py
  - packages/scistudio-blocks-spectroscopy/tests/test_peak_fitting_blocks.py
  - packages/scistudio-blocks-spectroscopy/tests/test_reference_correction_blocks.py
  - packages/scistudio-blocks-spectroscopy/tests/test_library_matching_blocks.py
  - packages/scistudio-blocks-spectroscopy/tests/test_unmixing_blocks.py
acceptance_source: manual
language_source: en
---
# Spectroscopy Package Specification

## 1. Change Summary

This spec records the owner-accepted design for `scistudio-blocks-spectroscopy`,
the SciStudio Spectroscopy package. The current draft captures the accepted
type design, previewer design, first utility block set, first preprocessing
block set, feature extraction/measurement blocks, peak fitting, reference
correction blocks, spectral library matching, and spectral unmixing blocks;
additional owner-approved blocks will be added to this same package spec as the
design discussion continues. The package is
independent from `scistudio-blocks-srs`; SRS imaging workflows, SRS spectral
cubes, and SRS-specific processing remain out of scope.

The accepted data model has two public data types:

- `Spectrum(Series)` for one 1-D spectrum.
- `SpectralDataset(CompositeData)` for many spectra with metadata-aware
  grouping, plotting, filtering, and library-style use.

`SpectralDataset` replaces the earlier separate library concept. A reference
library is represented as a dataset whose index table carries source,
material, citation, license, and other reference metadata.

The accepted utility block set is deliberately small: load/save `Spectrum`,
load/save `SpectralDataset`, convert between `Collection[Spectrum]` and
`SpectralDataset`, filter a dataset, merge datasets, and attach feature tables
back to dataset metadata.

The accepted IO format support is expressed as ADR-043 `FormatCapability`
records owned by the four load/save utility blocks. Format support must not be
declared on the `Spectrum` or `SpectralDataset` types themselves. User-visible
workflow config may persist a selected `capability_id`, which is the selected
`FormatCapability.id`; it is not a separate capability-record field.

The accepted preprocessing block set operates on `Collection[Spectrum]` rather
than `SpectralDataset`. It includes range cropping, manual axis shifting,
baseline correction, smoothing, combined alignment/resampling, normalization,
and fitted peak/component subtraction.

The accepted feature extraction and measurement block set also operates on
`Collection[Spectrum]` and outputs ordinary feature `DataFrame` values keyed by
`spectrum_id` that can be merged back into `SpectralDataset.index`. It includes
intensity, AUC, centroid, peak-to-peak ratio, and peak finding measurements.

The accepted peak fitting block set contains `FitPeak`. It fits Gaussian,
Lorentzian, or Voigt peak models without modifying the input spectra and emits
fitted curves, residual spectra, and a parameter/feature table.

The accepted reference correction block set operates on `Collection[Spectrum]`
plus one reference `Spectrum`. It includes reference subtraction and reference
division only; reference-based normalization is not accepted in this draft.

The accepted spectral library matching block set contains one block that
matches sample spectra against a library represented as `SpectralDataset` and
lets users choose the matching method.

The accepted spectral unmixing block set contains one block with selectable
linear unmixing methods. It outputs an interoperability-friendly wide
coefficient `DataFrame` plus a separate fit-quality `DataFrame`; it does not
introduce a new result type or fitted/residual spectrum outputs.

Calibration, clustering, reporting, and additional analysis blocks remain
pending owner discussion.

## 2. User Scenarios & Testing

### User Story 1 - Preview and process a single spectrum (Priority: P1)

As a scientist working with one Raman, FTIR, UV-Vis, fluorescence, NIR, or
similar spectrum, I need SciStudio to treat the object as a concrete 1-D
spectral type so ordinary spectral processing blocks can operate on it and the
preview panel can plot it directly.

Why this priority: A single spectrum is the smallest useful spectroscopy data
object. If it is not a first-class type, every block has to rediscover the
meaning of the index and value columns.

Independent Test: Create a `Spectrum` with `index_name="lambda"` and
`value_name="intensity"`, persist it, route it through preview resolution, and
verify the selected previewer plots bounded points with axis labels and units.

Acceptance Scenarios:

1. Given a `Spectrum` with a numeric `lambda` index and numeric `intensity`
   values, when the previewer opens it, then the user sees an interactive line
   plot with zoom, pan, hover values, reset view, and axis units.
2. Given a large `Spectrum`, when the previewer opens it, then the plot uses a
   bounded sampled or decimated read and clearly reports that the displayed
   points are not the complete payload.
3. Given a `Spectrum` with missing unit metadata, when the previewer opens it,
   then the plot still renders but displays an explicit unit diagnostic.

### User Story 2 - Explore and group many spectra by sample metadata (Priority: P1)

As a scientist comparing spectra by material, preparation method, batch,
condition, replicate, or other experimental metadata, I need a tabular dataset
shape that lets the previewer filter, group, color, and aggregate spectra
without forcing me to manage many separate `Spectrum` refs manually.

Why this priority: `Collection[Spectrum]` is good for transport and per-spectrum
processing, but it is awkward for grouped exploratory plotting because the
metadata needed for grouping lives beside the spectra rather than inside one
queryable table.

Independent Test: Create a `SpectralDataset` with an `index` table containing
`spectrum_id`, `material`, and `manufacturing_method`, plus a long-form
`spectra` table. Open the dataset previewer, group by `material`, color by
`manufacturing_method`, and verify linked table selection and plot highlighting.

Acceptance Scenarios:

1. Given a `SpectralDataset` with arbitrary metadata columns in `index`, when
   the previewer opens it, then those columns are available for filtering,
   searching, grouping, coloring, and row selection.
2. Given selected rows in the index table, when the plot is in selected mode,
   then only those spectra are displayed and table/plot highlighting remains
   linked.
3. Given group-by selection on an index column, when the user chooses group
   mean or group mean with band mode, then the previewer aggregates by the
   selected metadata column without mutating the dataset.
4. Given spectra on non-aligned `lambda` grids, when the user requests heatmap
   mode, then the previewer warns that the heatmap requires aligned coordinates
   or preview-side interpolation and reports what it displayed.

### User Story 3 - Treat spectral libraries as datasets (Priority: P1)

As a scientist using a curated spectral reference library, I need to store the
reference spectra and their source metadata in the same type system as
experimental spectral datasets.

Why this priority: A separate library type adds another schema and previewer
surface without adding a distinct data shape. The owner accepted a simpler
dataset representation.

Independent Test: Create a `SpectralDataset` with
`meta.dataset_role="library"` and index columns such as `material`,
`source_file`, `citation`, and `license`; verify the dataset previewer can
search, filter, select, and export the visible library subset.

Acceptance Scenarios:

1. Given a library-shaped `SpectralDataset`, when the previewer opens it, then
   source metadata appears in the index table and can be searched or filtered.
2. Given a selected library subset, when the user exports the current view,
   then the exported dataset view preserves both selected spectra and their
   index metadata.
3. Given experimental and library datasets, when future library-matching blocks
   are designed, then they use `SpectralDataset` inputs rather than introducing
   a separate `SpectralLibrary` type.

### User Story 4 - Export and save preview views completely (Priority: P1)

As a scientist using spectroscopy previews for exploratory analysis and figure
preparation, I need export/save behavior to be first-class, not an afterthought.

Why this priority: The owner explicitly called out export and save as important.
Spectroscopy users often need to export figures, visible subsets, grouped
summaries, and diagnostic tables while keeping workflow-producing saves
separate from preview-only exports.

Independent Test: Open both previewers, create a filtered or zoomed view, and
verify figure export and visible-data export are available and clearly labeled
as preview exports.

Acceptance Scenarios:

1. Given a `SpectrumPreviewer` line plot, when the user exports the current
   view, then PNG, SVG, PDF, and visible-points CSV exports are available where
   the platform supports them.
2. Given a `SpectralDatasetPreviewer` grouped plot, when the user exports the
   current view, then the figure export records the selected plot mode, grouping,
   color mapping, filters, and visible axis range in export metadata.
3. Given a selected or filtered dataset view, when the user exports table data,
   then the previewer can export the selected index rows and corresponding
   spectra rows without claiming to create a workflow lineage output.

### User Story 5 - Move spectra between files, collections, and datasets (Priority: P1)

As a scientist moving from raw spectra files into grouped analysis, I need a
small set of utility blocks that load and save spectra, build datasets from a
`Collection[Spectrum]` plus metadata, split datasets back to spectra, filter
datasets, and merge datasets.

Why this priority: These utilities form the transport layer for every later
spectroscopy workflow. Without them, analysis blocks either have to duplicate
loading and metadata-join behavior or force users to hand-build dataset tables.

Independent Test: Load multiple spectra, convert them into a `SpectralDataset`
with an external metadata table joined by `source_file`, split the dataset back
to `Collection[Spectrum]`, filter by one metadata column, merge two compatible
datasets, and save the results.

Acceptance Scenarios:

1. Given a set of spectral files with no explicit IDs, when `LoadSpectrum`
   loads them, then each output `Spectrum` has a generated unique
   `spectrum_id` and a separate `source_file` metadata value.
2. Given a `Collection[Spectrum]` and a metadata `DataFrame`, when
   `SpectrumToSpectralDataset` runs with `metadata_join_key="source_file"`,
   then the output `SpectralDataset.index` contains one row per spectrum with
   joined metadata and the output `spectra` slot contains long-form spectral
   points.
3. Given a `SpectralDataset`, when `SpectralDatasetToSpectrum` runs, then it
   emits a `Collection[Spectrum]` where each spectrum carries the corresponding
   index-row metadata.
4. Given a `SpectralDataset`, when `FilterSpectralDataset` filters by index
   metadata, then both `index` and `spectra` slots are restricted to the kept
   `spectrum_id` values without changing spectral intensities.
5. Given multiple compatible `SpectralDataset` values, when
   `MergeSpectralDataset` runs, then it appends their index and spectra rows
   and handles duplicate `spectrum_id` values according to its configured
   duplicate-ID policy.
6. Given a feature `DataFrame` produced from `Collection[Spectrum]`, when
   `AttachFeaturesToSpectralDataset` runs with a matching `spectrum_id` key,
   then feature columns are joined onto `SpectralDataset.index` without storing
   `Spectrum` objects inside the table.

### User Story 6 - Preprocess spectrum collections before analysis (Priority: P1)

As a scientist preparing Raman, FTIR, UV-Vis, fluorescence, NIR, or similar
spectra for downstream measurements, I need preprocessing blocks that operate
directly on `Collection[Spectrum]` and preserve per-spectrum identity while
cropping, shifting, correcting baseline, smoothing, aligning/resampling,
normalizing, or subtracting fitted peak components.

Why this priority: The owner accepted `Spectrum` as the processing type and
`SpectralDataset` as the organization/preview type. Preprocessing must
therefore run on spectra collections so dataset grouping concerns do not leak
into scientific transformations.

Independent Test: Convert a `SpectralDataset` to `Collection[Spectrum]`, run
crop, baseline correction, smoothing, align/resample, normalization, and peak
component subtraction, then convert the spectra back to a `SpectralDataset`.
Verify IDs and metadata are preserved, fitting blocks expose fitted-curve
outputs, and diagnostics tables contain one status row per spectrum.

Acceptance Scenarios:

1. Given a `Collection[Spectrum]`, when `CropSpectrumRange`,
   `ShiftSpectralAxis`, `SmoothSpectrum`, or `NormalizeSpectrum` runs, then the
   output is another `Collection[Spectrum]` with the same item count, order, and
   `spectrum_id` values.
2. Given a `BaselineCorrection` run, when any accepted baseline method is used,
   then the block emits `corrected`, `baseline`, and `fit_diagnostics` output
   ports.
3. Given an `AlignAndResampleSpectra` run, when `alignment_method="peak_fit"`,
   then the block emits aligned spectra, fitted peak curves, and fit
   diagnostics; when no fit is performed, the same output ports still exist and
   diagnostics report the non-fit method status.
4. Given a `SubtractPeakComponent` run, when `gaussian`, `lorentzian`, or
   `voigt` fitting is selected, then the block emits corrected spectra, fitted
   component spectra, and fit diagnostics.
5. Given a `SpectralDataset`, when the user wants preprocessing, then the
   workflow uses `SpectralDatasetToSpectrum` before preprocessing and
   `SpectrumToSpectralDataset` afterward; preprocessing blocks do not accept
   `SpectralDataset` directly.

### User Story 7 - Extract spectral measurement features (Priority: P1)

As a scientist measuring spectral features across many samples, I need blocks
that calculate common spectroscopy measurements from `Collection[Spectrum]`
while preserving a direct mapping back to the original spectra and dataset
metadata.

Why this priority: Intensity, peak-to-peak ratio, AUC, centroid, and peak
location/intensity are common spectroscopy measurements. They should be workflow
outputs, not preview-only interactions, and their results need to map back to
dataset metadata for grouped plotting and downstream analysis.

Independent Test: Run `ExtractIntensity`, `CalculateRatio`, `CalculateAUC`,
`CalculateCentroid`, and `FindPeaks` on a `Collection[Spectrum]`, verify each
output is a flat `DataFrame` keyed by `spectrum_id`, then use
`AttachFeaturesToSpectralDataset` to join feature columns back onto
`SpectralDataset.index`.

Acceptance Scenarios:

1. Given a `Collection[Spectrum]` and a user-specified target peak or
   coordinate, when `ExtractIntensity` runs, then it emits one mergeable feature
   row per spectrum with the measured intensity and source `spectrum_id`.
2. Given a `Collection[Spectrum]` and two user-specified peaks, when
   `CalculateRatio` runs, then it emits one mergeable feature row per spectrum
   with numerator peak intensity, denominator peak intensity, ratio, and status.
3. Given a `Collection[Spectrum]` and a configured `lambda_min`/`lambda_max`
   range, when `CalculateAUC` runs, then it emits one mergeable feature row per
   spectrum with AUC and status for that range.
4. Given a `Collection[Spectrum]` and a configured `lambda_min`/`lambda_max`
   range, when `CalculateCentroid` runs, then it emits one feature row per
   spectrum with the centroid coordinate for that range.
5. Given configured peak-detection parameters and an optional range, when
   `FindPeaks` runs, then it records the selected peak coordinate, intensity,
   and status in a mergeable feature table.
6. Given a feature table from any measurement block, when a user needs dataset-level
   grouping or plotting, then `AttachFeaturesToSpectralDataset` can join those
   features back to a `SpectralDataset` by `spectrum_id`.

### User Story 8 - Correct spectra against one reference spectrum (Priority: P1)

As a scientist correcting a set of spectra against a blank, background,
control, or other reference spectrum, I need simple blocks that subtract or
divide every spectrum by one selected reference without introducing dataset
matching rules or hidden reference selection behavior.

Why this priority: Reference subtraction and reference division are common
operations across ordinary spectroscopy workflows. They should be workflow
blocks with explicit inputs, not preview controls or implicit dataset behavior.

Independent Test: Run reference subtraction and reference division on a
`Collection[Spectrum]` plus one `Spectrum` reference. Verify the output keeps
the same item count, order, `spectrum_id` values, spectral coordinates, and
metadata while changing only intensities.

Acceptance Scenarios:

1. Given a `Collection[Spectrum]` and a reference `Spectrum` on the same
   `lambda` grid, when `SubtractReferenceSpectrum` runs, then each output
   intensity equals the sample intensity minus the reference intensity.
2. Given the same inputs, when `DivideByReferenceSpectrum` runs, then each
   output intensity equals the sample intensity divided by the reference
   intensity.
3. Given a sample and reference on different coordinate grids, when no explicit
   interpolation policy is configured, then the block fails with a clear grid
   mismatch diagnostic instead of silently interpolating.
4. Given a `SpectralDataset`, when the user wants reference correction, then
   the workflow first converts it with `SpectralDatasetToSpectrum`; reference
   correction blocks do not accept datasets directly.

### User Story 9 - Unmix spectra into reference coefficients (Priority: P1)

As a scientist estimating the contribution of known reference components in
sample spectra, I need one unmixing block that can choose among accepted linear
unmixing methods and produce coefficient tables that are easy to copy into
Excel, GraphPad, R, Python, or downstream SciStudio table blocks.

Why this priority: Spectral unmixing is a common analysis step, but users
usually need the component coefficients and fit quality, not a new SciStudio
result object.

Independent Test: Run `SpectralUnmixing` on sample spectra and reference
spectra. Verify the block emits a wide coefficient matrix with one row per
sample and one numeric coefficient column per reference component, plus a
separate fit-quality table with one row per sample.

Acceptance Scenarios:

1. Given sample spectra and reference spectra on a compatible grid, when
   `SpectralUnmixing` runs with `method="least_squares"`, then it emits wide
   coefficient columns for the selected references.
2. Given the same inputs, when `method="non_negative_least_squares"` or
   `method="sum_to_one_non_negative_least_squares"` is selected, then the
   coefficients obey the selected constraints where the fit succeeds.
3. Given duplicate or unsafe reference labels, when coefficient columns are
   generated, then the block creates deterministic, collision-free column names
   rather than overwriting columns.
4. Given any unmixing run, when the fit completes or fails for a sample, then
   `fit_quality` contains one status row for that sample with residual and RMSE
   fields.
5. Given a user who needs fitted or residual spectra, when they inspect the
   accepted block contract, then they see that fitted/residual spectrum outputs
   are not part of this draft and require a later owner-approved amendment.

### User Story 10 - Fit peak models without modifying spectra (Priority: P1)

As a scientist measuring peak parameters, I need a peak fitting block that fits
Gaussian, Lorentzian, or Voigt models and returns fitted curves, residuals, and
parameter/feature rows without changing the input spectra.

Why this priority: FWHM, fitted center, amplitude, area, and fit quality are
common spectroscopy outputs. Users often need those values without subtracting
the fitted peak from the spectrum.

Independent Test: Run `FitPeak` on a `Collection[Spectrum]` with each accepted
model. Verify it emits fitted curves, residual spectra, and a parameter/feature
`DataFrame` with one status row per attempted fit.

Acceptance Scenarios:

1. Given a `Collection[Spectrum]` and a configured fit range, when `FitPeak`
   runs with `model="gaussian"`, `model="lorentzian"`, or `model="voigt"`,
   then it emits fitted curves on the input grid and residual spectra equal to
   input intensity minus fitted intensity.
2. Given a successful fit, when the parameter/feature table is inspected, then
   it contains `spectrum_id`, model, status, fitted center, amplitude, width
   parameters, FWHM, area, and fit-quality fields where available.
3. Given an unsuccessful fit, when `FitPeak` completes, then it records a
   non-success status for that spectrum without silently emitting misleading
   fitted parameters.

### User Story 11 - Match spectra against a spectral library (Priority: P1)

As a scientist comparing experimental spectra to known references, I need a
library matching block that searches a `SpectralDataset` library using a
user-selected similarity or distance method and returns ranked match rows.

Why this priority: Library matching is a common spectroscopy analysis step, and
the package already represents libraries as `SpectralDataset` values rather
than a separate type.

Independent Test: Run `MatchSpectralLibrary` on query spectra and a
library-shaped `SpectralDataset`. Verify it emits ranked match rows with query
IDs, library spectrum IDs, scores, ranks, method, and status.

Acceptance Scenarios:

1. Given query spectra and a library `SpectralDataset` on a compatible grid,
   when `MatchSpectralLibrary` runs with a selected method, then it emits one
   or more ranked matches per query spectrum.
2. Given different accepted methods, when the user changes the method, then the
   block records the selected method and rank ordering in the output table.
3. Given incompatible grids or units and no explicit compatibility policy, when
   matching is requested, then the block fails or reports non-success status
   rather than silently comparing inconsistent spectra.

### Edge Cases

- `lambda` is the canonical data column name even though implementation code
  must avoid using `lambda` as a Python variable name.
- Raman shift, FTIR wavenumber, UV-Vis wavelength, fluorescence emission, and
  NIR wavelength may all use the `lambda` coordinate column; `lambda_kind` and
  `lambda_unit` metadata disambiguate the physical meaning.
- A dataset may contain irregular grids, duplicate coordinate points, missing
  intensity values, mixed units, orphan spectra rows, or index rows with no
  matching spectra rows; the dataset previewer reports diagnostics rather than
  failing silently.
- Collections remain valid for transport, including `Collection[Spectrum]`,
  but collection preview is not a substitute for `SpectralDataset` grouping.
- Previewer export is display/export behavior only. Workflow output saves
  belong to the accepted `SaveSpectrum` and `SaveSpectralDataset` utility
  blocks.
- `spectrum_id` is an internal unique ID, not a filename. Loaders and
  conversion blocks preserve an existing ID when available and generate one
  when absent.
- `source_file` or `filename` may be used as metadata join keys, but they do
  not become `spectrum_id` by default.
- Library datasets may use existing reference IDs or generated IDs and may have
  no filename-derived identity at all.
- IO format support is an ADR-043 IOBlock capability contract. It must not be
  modeled as `Spectrum` or `SpectralDataset` type attributes.
- `capability_id` in workflow config refers to `FormatCapability.id`.
  Capability records themselves use the formal `id` field.
- `SpectralDataset` is a `CompositeData` subtype. Its package-owned native
  dataset format must follow the core CompositeData JSON manifest plus sidecar
  slot-file model unless a later ADR or owner-approved amendment adds another
  package-owned bundle format.
- A `.spectraldataset.zip` or other single-archive bundle is not accepted in
  this draft because core CompositeData currently exposes `.json` manifest
  load/save capabilities rather than a zip capability.
- Preprocessing blocks operate on `Collection[Spectrum]`, not
  `SpectralDataset`. Dataset metadata can be round-tripped through the utility
  conversion blocks around preprocessing.
- Any preprocessing block that performs fitting or baseline estimation must
  expose both a fitted-curve output and a `fit_diagnostics` `DataFrame` output.
  Users may ignore those ports, but the ports must exist.
- Baseline correction is limited to `polynomial`, `asls`, `arpls`, and
  `airpls` in this draft.
- Normalization is limited to `max` and `minmax` in this draft.
- Fitted peak/component subtraction must support `gaussian`, `lorentzian`, and
  `voigt` component models.
- Feature extraction blocks output ordinary `DataFrame` values, not
  `FeatureTable` or object-cell tables. Feature rows map back through
  `spectrum_id`.
- Feature extraction and measurement blocks accept `Collection[Spectrum]` and
  output mergeable flat feature tables. They do not accept `SpectralDataset`
  directly.
- `FindPeaks` supports optional range parameters. It covers targeted
  peak-in-range measurement, so there is no separate `MeasurePeakInRange`
  block in this draft.
- `CalculateRatio` is peak-to-peak ratio only: users provide two peak
  definitions, and the block measures the two peak intensities before computing
  the ratio.
- `CalculateCentroid` must report an explicit status when a requested range has
  no usable points or no usable intensity denominator.
- FWHM is not a standalone feature extraction block in this draft. Peak fit
  outputs report FWHM through their parameter, feature, or fit-output tables.
- `FitPeak` does not subtract or otherwise modify input spectra. It outputs
  fitted curves, residual spectra, and a parameter/feature table.
- `FitPeak` uses a parameter/feature output table, not a `fit_diagnostics`
  output port name.
- Spectral library matching uses `SpectralDataset` libraries and does not
  introduce a separate `SpectralLibrary` type.
- Library matching must use an explicit method and grid compatibility policy;
  it must not silently compare mismatched units or incompatible grids.
- Calibration modeling and clustering are intentionally not accepted in this
  draft.
- Reference correction accepts `Collection[Spectrum]` plus one `Spectrum`
  reference. It does not select references from a dataset, match references by
  metadata, or accept `SpectralDataset` directly.
- `NormalizeByReferenceSpectrum` is not accepted in this draft.
- Reference correction defaults to an error on mismatched `lambda` grids.
  Interpolating the reference onto each sample grid is allowed only through an
  explicit `reference_grid_policy`.
- Reference division must not silently divide by zero. The default zero-policy
  is an error; any non-error behavior must be selected explicitly.
- Spectral unmixing emits ordinary `DataFrame` values only: one wide
  coefficient matrix and one fit-quality table. It does not define
  `SpectralUnmixingResult` or another package data type.
- The coefficient table is wide by default for interoperability with Excel,
  GraphPad, R, Python, and matrix-oriented table workflows. Long-form
  coefficients can be derived later through generic table reshaping, but are
  not the default unmixing output.
- Spectral unmixing does not output fitted spectra or residual spectra in this
  draft. Those outputs require a later owner-approved amendment.

## 3. Requirements

### Functional Requirements

- FR-001: The package must be named `scistudio-blocks-spectroscopy` and must
  cover general 1-D spectroscopy data such as Raman, FTIR, UV-Vis,
  fluorescence, and NIR.
- FR-002: The package must not depend on, specialize, migrate, or redefine
  `scistudio-blocks-srs` behavior.
- FR-003: The package must define `Spectrum` as a subclass of core `Series`,
  not as `Array` or `CompositeData`.
- FR-004: `Spectrum` must use `index_name="lambda"` and
  `value_name="intensity"` as its canonical semantic names.
- FR-005: `Spectrum.Meta` must expose `lambda_unit` and `intensity_unit` fields.
  Values may be null when unknown, but the fields must exist.
- FR-006: `Spectrum.Meta` must expose enough typed metadata to distinguish
  coordinate meaning across modalities, including at minimum `lambda_kind` and
  `modality`.
- FR-007: The package must define `SpectralDataset` as a subclass of core
  `CompositeData`.
- FR-008: `SpectralDataset.expected_slots` must require exactly two semantic
  slots: `index: DataFrame` and `spectra: DataFrame`.
- FR-009: The `SpectralDataset.index` table must have one row per spectrum and
  must contain a unique `spectrum_id` column.
- FR-010: The `SpectralDataset.index` table must allow arbitrary additional
  source, grouping, acquisition, material, manufacturing, condition, replicate,
  citation, license, and user-defined metadata columns.
- FR-011: The `SpectralDataset.spectra` table must be long-form and must
  contain `spectrum_id`, `lambda`, and `intensity` columns.
- FR-012: `SpectralDataset.spectra.spectrum_id` values must join to
  `SpectralDataset.index.spectrum_id`; previewers and validators must report
  orphan rows and missing spectra coverage.
- FR-013: `SpectralDataset.Meta` must include dataset-level unit defaults for
  `lambda_unit` and `intensity_unit`, plus `dataset_role` so experiment,
  reference, calibration, and library datasets share one type.
- FR-014: A spectral library must be represented as `SpectralDataset` with an
  appropriate `dataset_role`, not as a separate `SpectralLibrary` type.
- FR-015: The package must not define `SpectraTable` as a package type.
  Multiple independent spectra can move as `Collection[Spectrum]` or as
  `SpectralDataset` depending on workflow needs.
- FR-016: The package must not define `FeatureTable` as a package type in this
  spec. Feature outputs remain ordinary `DataFrame` instances so block authors
  can choose schemas appropriate to each analysis.
- FR-017: The package must register package-owned previewers through
  `scistudio.previewers`.
- FR-018: `SpectrumPreviewer` must route exact `Spectrum` targets to an
  interactive 2-D line plot.
- FR-019: `SpectrumPreviewer` must provide zoom, pan/drag, box zoom, reset
  view, hover coordinate/intensity readout, axis labels, and unit display.
- FR-020: `SpectrumPreviewer` must use bounded reads or decimation for large
  spectra and must display sampling/truncation metadata honestly.
- FR-021: `SpectrumPreviewer` must expose preview export/save actions for the
  current figure and the visible points.
- FR-022: `SpectralDatasetPreviewer` must route exact `SpectralDataset` targets
  to a metadata-aware spectral explorer.
- FR-023: `SpectralDatasetPreviewer` must show the index table with pagination,
  sorting, search, filtering, and row selection.
- FR-024: `SpectralDatasetPreviewer` must allow filter, group-by, and color-by
  controls over arbitrary columns from the `index` slot.
- FR-025: `SpectralDatasetPreviewer` must provide overlay, selected, group
  mean, group mean with band, and heatmap plot modes.
- FR-026: `SpectralDatasetPreviewer` must link table selection and plot
  highlight state.
- FR-027: `SpectralDatasetPreviewer` must report dataset health diagnostics,
  including duplicate IDs, missing required columns, orphan spectra rows,
  missing spectra coverage, missing numeric coordinates or intensities, unit
  inconsistency, and heatmap alignment issues.
- FR-028: `SpectralDatasetPreviewer` must use bounded reads, pagination,
  sampling, or preview-side aggregation and must not materialize a large full
  dataset just to render a preview.
- FR-029: `SpectralDatasetPreviewer` must expose preview export/save actions
  for figures, visible spectra rows, selected index rows, and grouped summary
  tables.
- FR-030: Previewers must not perform scientific processing such as baseline
  correction, smoothing, normalization, PCA, clustering, peak detection, or
  library matching. Those operations belong to owner-approved workflow block
  groups, including preprocessing where this spec explicitly accepts it.
- FR-031: Block groups beyond the accepted utility, preprocessing, feature
  extraction, peak fitting, reference correction, library matching, and
  spectral unmixing groups remain unresolved in this draft. No implementation
  agent may infer additional analysis, calibration, clustering, or reporting
  block names or behavior from exploratory discussion until this spec is amended
  with owner-approved block requirements.
- FR-032: The accepted utility block set must contain exactly
  `LoadSpectrum`, `SaveSpectrum`, `LoadSpectralDataset`,
  `SaveSpectralDataset`, `SpectrumToSpectralDataset`,
  `SpectralDatasetToSpectrum`, `FilterSpectralDataset`,
  `MergeSpectralDataset`, and `AttachFeaturesToSpectralDataset`.
- FR-033: The package must not expose separate public utility blocks for
  dataset validation, metadata joining, or unit setting in this accepted set.
  Those behaviors may exist inside the accepted utilities where needed.
- FR-034: `LoadSpectrum` must load one or more source files into
  `Collection[Spectrum]`.
- FR-035: `LoadSpectrum` must preserve an existing source spectrum ID when the
  input format provides one and must generate a package-managed unique
  `spectrum_id` when no ID is available.
- FR-036: `LoadSpectrum` must not default `spectrum_id` to the filename.
  Filename-derived values such as `source_file` or `filename` must be kept as
  metadata only.
- FR-037: `SaveSpectrum` must persist a single `Spectrum` or
  `Collection[Spectrum]` while preserving each spectrum's `spectrum_id`,
  spectral axis values, intensity values, typed metadata, and user metadata
  where the target format can carry them.
- FR-038: `LoadSpectralDataset` must load a dataset-shaped representation into
  `SpectralDataset`, including at minimum a canonical two-table layout with
  `index` and `spectra` tables.
- FR-039: `SaveSpectralDataset` must persist a `SpectralDataset` in the
  canonical two-table layout and preserve `index.spectrum_id`,
  `spectra.spectrum_id`, spectral coordinates, intensities, dataset metadata,
  and index metadata.
- FR-040: `SpectrumToSpectralDataset` must accept `Collection[Spectrum]` plus
  an optional metadata `DataFrame` and must produce one `SpectralDataset`.
- FR-041: `SpectrumToSpectralDataset` must build the output `spectra` slot in
  long form with `spectrum_id`, `lambda`, and `intensity` columns.
- FR-042: `SpectrumToSpectralDataset` must build the output `index` slot from
  each spectrum's ID and metadata, then join the optional metadata `DataFrame`
  using a configurable join key.
- FR-043: `SpectrumToSpectralDataset` must default metadata joins to
  `spectrum_id` when no override is supplied, and must support joins by
  `source_file`, `filename`, or another user-selected metadata column.
- FR-044: `SpectrumToSpectralDataset` must not use filename as the default
  `spectrum_id`; filename-based joins remain metadata joins only.
- FR-045: `SpectralDatasetToSpectrum` must split a `SpectralDataset` into
  `Collection[Spectrum]`, one `Spectrum` per `index.spectrum_id`.
- FR-046: `SpectralDatasetToSpectrum` must copy each matching index row's
  metadata onto the emitted `Spectrum`, mapping known typed fields into
  `Spectrum.Meta` and arbitrary extra columns into `user` metadata.
- FR-047: `FilterSpectralDataset` must filter the `index` slot by configured
  metadata predicates and must keep only matching `spectrum_id` rows in the
  `spectra` slot.
- FR-048: `FilterSpectralDataset` must not change spectral coordinates,
  intensities, units, or processing metadata except for recording that the
  dataset was filtered.
- FR-049: `MergeSpectralDataset` must merge multiple `SpectralDataset` inputs
  by appending compatible `index` and `spectra` rows.
- FR-050: `MergeSpectralDataset` must default to an error on duplicate
  `spectrum_id` values and may offer explicit duplicate-ID policies such as
  prefixing or remapping.
- FR-051: `MergeSpectralDataset` must not silently convert or reconcile mixed
  units; unit mismatch must fail or require an explicit owner-approved behavior
  in a later amendment.
- FR-052: Utility blocks must not perform scientific spectral processing such
  as baseline correction, smoothing, normalization, peak finding, integration,
  calibration modeling, PCA, clustering, or library matching.
- FR-053: The accepted preprocessing block set must contain exactly
  `CropSpectrumRange`, `ShiftSpectralAxis`, `BaselineCorrection`,
  `SmoothSpectrum`, `AlignAndResampleSpectra`, `NormalizeSpectrum`, and
  `SubtractPeakComponent`.
- FR-054: Every accepted preprocessing block must accept
  `Collection[Spectrum]` and must not accept `SpectralDataset` directly.
- FR-055: Every accepted preprocessing block must preserve collection item
  count, item order, and `spectrum_id` values unless a later owner-approved
  amendment explicitly changes that behavior.
- FR-056: Every accepted preprocessing block must return its primary processed
  result as `Collection[Spectrum]`.
- FR-057: `CropSpectrumRange` must crop each spectrum to a configured
  `lambda_min` and `lambda_max` range and must not change intensity values
  beyond dropping out-of-range points.
- FR-058: `ShiftSpectralAxis` must shift each spectrum's `lambda` axis by a
  configured amount and must not change intensity values.
- FR-059: `BaselineCorrection` must support exactly four methods in this
  draft: `polynomial`, `asls`, `arpls`, and `airpls`.
- FR-060: `BaselineCorrection` must not expose `rubber_band`, `snip`, or other
  baseline methods unless a later owner-approved amendment adds them.
- FR-061: `BaselineCorrection` must expose stable output ports named
  `corrected`, `baseline`, and `fit_diagnostics`.
- FR-062: `BaselineCorrection.corrected` must be `Collection[Spectrum]`
  containing the baseline-corrected spectra.
- FR-063: `BaselineCorrection.baseline` must be `Collection[Spectrum]`
  containing one fitted or estimated baseline curve per input spectrum on the
  same `lambda` grid as the corresponding input.
- FR-064: `BaselineCorrection.fit_diagnostics` must be a `DataFrame` with one
  row per input spectrum and must include at minimum `spectrum_id`, `method`,
  `status`, `parameters`, `converged`, `iterations`, and an error or residual
  quality field such as `rmse` when available.
- FR-065: `SmoothSpectrum` must support exactly `savitzky_golay`,
  `moving_average`, `gaussian`, and `median` smoothing methods in this draft.
- FR-066: `SmoothSpectrum` must change intensity values only and must not
  change the `lambda` grid.
- FR-067: `AlignAndResampleSpectra` must combine alignment and resampling in
  one block.
- FR-068: `AlignAndResampleSpectra` must support `alignment_method` values
  `none`, `peak_fit`, and `cross_correlation`.
- FR-069: `AlignAndResampleSpectra` must support target-grid modes including
  explicit grid, first spectrum, reference spectrum, and range plus step.
- FR-070: `AlignAndResampleSpectra` must expose stable output ports named
  `aligned`, `fit_curves`, and `fit_diagnostics`.
- FR-071: `AlignAndResampleSpectra.aligned` must be `Collection[Spectrum]`
  containing spectra on the target grid.
- FR-072: `AlignAndResampleSpectra.fit_curves` must be `Collection[Spectrum]`
  containing fitted peak curves when `alignment_method="peak_fit"` and an
  empty or status-compatible collection when no fit is performed.
- FR-073: `AlignAndResampleSpectra.fit_diagnostics` must be a `DataFrame`
  recording one row per input spectrum with alignment method, status, applied
  shift, and fit or correlation quality fields where available.
- FR-074: `NormalizeSpectrum` must support exactly `max` and `minmax`
  normalization methods in this draft.
- FR-075: `NormalizeSpectrum` must not expose a `min` normalization method in
  this draft.
- FR-076: `SubtractPeakComponent` must support exactly `gaussian`,
  `lorentzian`, and `voigt` component models in this draft.
- FR-077: `SubtractPeakComponent` must expose stable output ports named
  `corrected`, `component`, and `fit_diagnostics`.
- FR-078: `SubtractPeakComponent.corrected` must be `Collection[Spectrum]`
  containing spectra after the fitted component is subtracted.
- FR-079: `SubtractPeakComponent.component` must be `Collection[Spectrum]`
  containing the fitted component curve for each input spectrum on the same
  `lambda` grid as the corresponding input.
- FR-080: `SubtractPeakComponent.fit_diagnostics` must be a `DataFrame` with
  one row per input spectrum and must include model, status, fitted center,
  amplitude, width parameters, FWHM, area, and fit-quality fields where
  available.
- FR-081: Any preprocessing block that performs fitting or baseline estimation
  must expose both a fitted-curve `Collection[Spectrum]` output and a
  `fit_diagnostics` `DataFrame` output. Users may ignore these ports, but the
  ports must exist.
- FR-082: Feature extraction and measurement blocks that measure features from
  spectra must accept `Collection[Spectrum]` and output ordinary `DataFrame`
  feature tables keyed by `spectrum_id`, unless a later owner-approved
  amendment defines a different contract.
- FR-083: Feature output tables must remain flat, columnar SciStudio
  `DataFrame` values and must not store `Spectrum`, `DataObject`, or other
  Python object instances in table cells.
- FR-084: `AttachFeaturesToSpectralDataset` must accept a `SpectralDataset`
  plus a feature `DataFrame`, join rows by a configurable key that defaults to
  `spectrum_id`, and add feature columns to `SpectralDataset.index` without
  modifying `SpectralDataset.spectra`.
- FR-085: `AttachFeaturesToSpectralDataset` must require explicit conflict
  behavior when feature columns collide with existing `index` columns, such as
  error, prefix, suffix, or replace policies; silent overwrite is not allowed.
- FR-086: The accepted feature extraction and measurement block set must
  contain exactly `ExtractIntensity`, `CalculateAUC`, `CalculateCentroid`,
  `CalculateRatio`, and `FindPeaks` until a later owner-approved amendment adds
  more feature extraction blocks.
- FR-087: Every accepted feature extraction and measurement block must accept
  `Collection[Spectrum]`, must not accept `SpectralDataset` directly, and must
  output a flat `DataFrame` that can be merged into `SpectralDataset.index` by
  `spectrum_id`.
- FR-088: `ExtractIntensity` must measure intensity from each input spectrum at
  a user-specified peak, coordinate, or coordinate range and output at minimum
  `spectrum_id`, measured coordinate, intensity, and status columns.
- FR-089: `CalculateAUC` must calculate area under the curve for a configured
  `lambda_min`/`lambda_max` range and output at minimum `spectrum_id`,
  `lambda_min`, `lambda_max`, `auc`, and status columns.
- FR-090: `CalculateCentroid` must calculate an intensity-weighted centroid for
  a configured `lambda_min`/`lambda_max` range and output at minimum
  `spectrum_id`, `lambda_min`, `lambda_max`, `centroid_lambda`, and status
  columns.
- FR-091: `CalculateRatio` must calculate peak-to-peak ratio only. It must
  accept two user-specified peak definitions, `numerator_peak` and
  `denominator_peak`, measure both peak intensities from each input spectrum,
  and output at minimum `spectrum_id`, numerator peak coordinate/intensity,
  denominator peak coordinate/intensity, ratio, and status columns.
- FR-092: `CalculateRatio` must report explicit non-success status when either
  requested peak cannot be measured or when the denominator peak intensity is
  zero or otherwise unusable.
- FR-093: `FindPeaks` must detect peaks from each input spectrum with
  configurable detection parameters and optional `lambda_min`/`lambda_max`
  range bounds. Targeted peak-in-range measurement belongs in `FindPeaks`; the
  package must not define a separate `MeasurePeakInRange` block in this draft.
- FR-094: The package must not define `CalculateFWHM` as a standalone
  feature-extraction block in this draft. FWHM belongs in peak fitting
  parameter/feature outputs or existing fit-output tables such as
  `SubtractPeakComponent.fit_diagnostics`.
- FR-095: The accepted reference correction block set must contain exactly
  `SubtractReferenceSpectrum` and `DivideByReferenceSpectrum` in this draft.
- FR-096: The package must not expose `NormalizeByReferenceSpectrum` in this
  draft unless a later owner-approved amendment adds it.
- FR-097: `SubtractReferenceSpectrum` and `DivideByReferenceSpectrum` must
  accept `spectra: Collection[Spectrum]` and `reference: Spectrum`, and must
  output `corrected: Collection[Spectrum]`.
- FR-098: Reference correction blocks must not accept `SpectralDataset`
  directly. Dataset workflows must use `SpectralDatasetToSpectrum` before
  reference correction and `SpectrumToSpectralDataset` afterward when grouped
  metadata needs to be restored.
- FR-099: Reference correction blocks must preserve collection item count, item
  order, `spectrum_id` values, typed metadata, user metadata, and each sample
  spectrum's `lambda` grid.
- FR-100: `SubtractReferenceSpectrum` must calculate each corrected intensity
  as `sample_intensity - reference_intensity`.
- FR-101: `DivideByReferenceSpectrum` must calculate each corrected intensity
  as `sample_intensity / reference_intensity`.
- FR-102: Reference correction blocks must default to
  `reference_grid_policy="error"` when the sample and reference `lambda` grids
  differ, and may allow `reference_grid_policy="interpolate_reference_to_sample"`
  as an explicit configuration.
- FR-103: `DivideByReferenceSpectrum` must default to an error when reference
  intensities contain zero values at used coordinates. Any non-error zero
  handling must be selected explicitly and must be visible in block config.
- FR-104: The accepted spectral unmixing block set must contain exactly
  `SpectralUnmixing` in this draft.
- FR-105: `SpectralUnmixing` must accept `spectra: Collection[Spectrum]` and
  `references: Collection[Spectrum]`.
- FR-106: `SpectralUnmixing` must expose exactly two required output ports in
  this draft: `coefficients: DataFrame` and `fit_quality: DataFrame`.
- FR-107: `SpectralUnmixing` must support exactly these methods in this draft:
  `least_squares`, `non_negative_least_squares`, and
  `sum_to_one_non_negative_least_squares`.
- FR-108: `SpectralUnmixing.coefficients` must be a wide table with one row per
  sample spectrum. It must include `spectrum_id` and `method` columns plus one
  numeric coefficient column per reference component.
- FR-109: `SpectralUnmixing` must generate coefficient column names from a
  configured `component_label_source`, such as `spectrum_id`, a reference name,
  or a selected metadata field. Generated names must be deterministic,
  table-safe, and collision-free.
- FR-110: `SpectralUnmixing.fit_quality` must contain one row per sample
  spectrum and must include at minimum `spectrum_id`, `method`, `status`,
  `residual_norm`, `rmse`, and `n_components`; it should include `r2` when
  computable.
- FR-111: `SpectralUnmixing` must use an explicit grid compatibility policy for
  sample/reference alignment. The default policy must fail on incompatible
  grids; interpolation requires an explicit configuration.
- FR-112: `SpectralUnmixing` must not define or output
  `SpectralUnmixingResult`, fitted spectra, residual spectra, or component
  spectra in this draft.
- FR-113: The accepted peak fitting block set must contain exactly `FitPeak` in
  this draft.
- FR-114: `FitPeak` must accept `Collection[Spectrum]` plus fit configuration,
  including at minimum a fit range and model selection.
- FR-115: `FitPeak` must support exactly `gaussian`, `lorentzian`, and `voigt`
  peak models in this draft.
- FR-116: `FitPeak` must expose exactly these required output ports in this
  draft: `fit_curves: Collection[Spectrum]`,
  `residuals: Collection[Spectrum]`, and `parameters: DataFrame`.
- FR-117: `FitPeak.fit_curves` must contain the fitted peak curve for each
  input spectrum on the same `lambda` grid used for the fit.
- FR-118: `FitPeak.residuals` must contain residual spectra for each input
  spectrum, with intensity equal to input intensity minus fitted intensity on
  the same grid.
- FR-119: `FitPeak.parameters` must be a flat `DataFrame` with one row per
  attempted fit and must include at minimum `spectrum_id`, `model`, `status`,
  fitted center, amplitude, width parameters, FWHM, area, and fit-quality fields
  such as RMSE where available.
- FR-120: `FitPeak` must not expose a `fit_diagnostics` output port name in
  this draft. The parameter/feature table is the accepted tabular fit output.
- FR-121: The accepted spectral library matching block set must contain exactly
  `MatchSpectralLibrary` in this draft.
- FR-122: `MatchSpectralLibrary` must accept
  `spectra: Collection[Spectrum]` and `library: SpectralDataset`; the package
  must not introduce a separate `SpectralLibrary` type for matching.
- FR-123: `MatchSpectralLibrary` must support selectable matching methods,
  including exactly `cosine_similarity`, `pearson_correlation`,
  `spectral_angle`, and `euclidean_distance` in this draft.
- FR-124: `MatchSpectralLibrary` must output `matches: DataFrame` with at
  minimum `spectrum_id`, `library_spectrum_id`, `method`, `rank`, `score`, and
  `status` columns.
- FR-125: `MatchSpectralLibrary` must support a configurable `top_k` or
  equivalent rank limit and must define rank 1 as the best match regardless of
  whether the selected method is similarity- or distance-oriented.
- FR-126: `MatchSpectralLibrary` must use an explicit grid and unit
  compatibility policy. The default policy must fail or report non-success
  status for incompatible grids or units; silent interpolation or unit
  conversion is not allowed.
- FR-127: Calibration modeling blocks, clustering blocks, PCA/embedding blocks,
  and other analysis/reporting blocks beyond the accepted sets are not accepted
  in this draft.
- FR-128: `LoadSpectrum`, `SaveSpectrum`, `LoadSpectralDataset`, and
  `SaveSpectralDataset` must declare explicit ADR-043
  `format_capabilities` records. New package code must not rely on legacy
  `supported_extensions` as its published package contract.
- FR-129: Each spectroscopy `FormatCapability` record must use the formal
  ADR-043 fields: `id`, `direction`, `data_type`, `format_id`, `extensions`,
  `label`, `block_type`, `handler`, `is_default`, `priority`,
  `roundtrip_group`, and `metadata_fidelity`.
- FR-130: The spec and implementation must treat workflow `capability_id` as a
  reference to `FormatCapability.id`, not as a field on the capability record.
- FR-131: The package must not declare file extensions or format support on
  `Spectrum`, `SpectralDataset`, or their typed `Meta` models.
- FR-132: `LoadSpectrum` and `SaveSpectrum` must provide load/save
  capabilities for `.txt`, `.csv`, `.tsv`, `.xlsx`, package-owned
  `.spectrum.json`, JCAMP-DX (`.jdx`, `.dx`, `.jcamp`), and SPC (`.spc`)
  according to the accepted capability matrix.
- FR-133: `LoadSpectrum` must provide load-only capabilities for accepted
  single-spectrum vendor or instrument formats, including Thermo OMNIC `.spa`,
  Bruker OPUS through explicit capability selection, HORIBA LabSpec single
  spectrum exports, Andor/ASCII-style spectra, and Princeton/LightField SPE
  where the handler can return one `Spectrum`.
- FR-134: `SaveSpectrum` must not declare saver capabilities for accepted
  vendor or instrument-native load-only formats unless a later owner-approved
  amendment accepts a tested writer for that exact format.
- FR-135: `LoadSpectralDataset` and `SaveSpectralDataset` must provide
  package-owned load/save capabilities for a `SpectralDataset` JSON manifest
  format aligned with the core `CompositeData` JSON manifest plus sidecar slot
  model.
- FR-136: `SaveSpectralDataset` must not define or imply a `.zip`,
  `.spectraldataset.zip`, or other archive bundle capability in this draft.
- FR-137: `LoadSpectralDataset` and `SaveSpectralDataset` must provide
  load/save capabilities for `.xlsx` workbooks that use explicit `index`,
  `spectra`, and optional `meta` sheets.
- FR-138: SPC (`.spc`) must be available as both load and save capability for
  `Spectrum` and `SpectralDataset` where the handler can represent the target
  as a single-spectrum or multi-spectrum SPC payload.
- FR-139: `LoadSpectralDataset` must provide load-only capabilities for
  accepted multi-spectrum vendor or instrument formats, including Thermo OMNIC
  `.spg`, Renishaw WiRE `.wdf`, WITec `.wip`/`.wid`, HORIBA LabSpec map or
  group exports, Andor/FITS-style multi-spectrum outputs, and
  Princeton/LightField SPE where the handler returns multiple spectra.
- FR-140: Vendor or instrument-native load-only capabilities must not declare a
  matching saver, must not set a `roundtrip_group`, and must not claim
  `lossless` metadata fidelity.
- FR-141: Package-owned native JSON manifest capabilities may claim
  `lossless` only when both load and save capabilities share a
  `roundtrip_group` and tests prove preservation of the primary payload,
  required typed `Meta` fields, and required `SpectralDataset` slot schemas.
- FR-142: Delimited text, Excel, JCAMP-DX, and SPC capabilities must declare
  conservative `metadata_fidelity` values that match tested behavior. They
  must not imply preservation of arbitrary vendor-native metadata.
- FR-143: Capability lookup for spectroscopy IO must follow ADR-043 selection
  rules: explicit `capability_id` wins, unique matches are allowed, and
  unresolved ambiguity must fail instead of using registration order.

### Key Entities

`Spectrum` is a single 1-D indexed spectrum.

| Field or concept | Contract |
|---|---|
| Base type | `Series` |
| Canonical index | `lambda` |
| Canonical value | `intensity` |
| Required Meta fields | `lambda_unit`, `intensity_unit`, `lambda_kind`, `modality` |
| Optional Meta fields | source file, instrument, acquisition time, sample label, processing history summary |
| Previewer | `SpectrumPreviewer` |

`SpectralDataset` is a many-spectrum composite.

| Slot | Type | Required columns | Meaning |
|---|---|---|---|
| `index` | `DataFrame` | `spectrum_id` | One row per spectrum plus arbitrary grouping/source metadata. |
| `spectra` | `DataFrame` | `spectrum_id`, `lambda`, `intensity` | Long-form spectral points joined to `index`. |

`SpectralDataset.Meta` describes dataset-level defaults.

| Field | Meaning |
|---|---|
| `dataset_name` | Human-readable dataset label. |
| `dataset_role` | `experiment`, `library`, `reference`, `calibration`, or `unknown`. |
| `lambda_unit` | Dataset-level coordinate unit default. |
| `intensity_unit` | Dataset-level intensity unit default. |
| `modality` | Dataset-level modality default when all rows share one modality. |
| `schema_version` | Package schema version for future migrations. |

`SpectrumPreviewer` is the package previewer for single spectra.

| Capability | Required behavior |
|---|---|
| `plot` | Render intensity versus lambda as an interactive line plot. |
| `navigate` | Zoom, pan, box zoom, hover, and reset. |
| `diagnostics` | Report missing units, empty data, nonnumeric values, and sampling. |
| `export` | Export current figure and visible points. |

`SpectralDatasetPreviewer` is the package previewer for many spectra.

| Capability | Required behavior |
|---|---|
| `table` | Paginated/searchable/sortable index table. |
| `filter` | Filter by arbitrary index columns. |
| `group` | Group and color by arbitrary index columns. |
| `plot` | Overlay, selected, group mean, group band, and heatmap modes. |
| `diagnostics` | Join, schema, unit, numeric, and heatmap-alignment diagnostics. |
| `export` | Export figure, selected rows, visible spectra, and grouped summaries. |

The accepted utility block set moves data between files, spectra collections,
and spectral datasets.

| Block | Input | Output | Required behavior |
|---|---|---|---|
| `LoadSpectrum` | File, folder, or glob path plus format config | `Collection[Spectrum]` | Load one or more spectra; preserve existing IDs when present; otherwise generate unique `spectrum_id` values; keep `source_file` or `filename` as metadata. |
| `SaveSpectrum` | `Spectrum` or `Collection[Spectrum]` plus destination config | Files or artifact refs | Persist spectra while preserving IDs, axis values, intensities, typed metadata, and user metadata where possible. |
| `LoadSpectralDataset` | Dataset path or canonical `index` + `spectra` table paths | `SpectralDataset` | Load the two-table dataset shape and validate required columns. |
| `SaveSpectralDataset` | `SpectralDataset` plus destination config | Files or artifact refs | Save the canonical `index` and `spectra` tables with dataset metadata. |
| `SpectrumToSpectralDataset` | `Collection[Spectrum]` plus optional metadata `DataFrame` | `SpectralDataset` | Expand each spectrum into long-form rows, build one index row per spectrum, and join optional metadata by configurable key. |
| `SpectralDatasetToSpectrum` | `SpectralDataset` | `Collection[Spectrum]` | Split by `spectrum_id` and attach each index row's metadata to the emitted spectrum. |
| `FilterSpectralDataset` | `SpectralDataset` plus metadata predicates | `SpectralDataset` | Filter index rows and keep corresponding spectra rows without changing spectral values. |
| `MergeSpectralDataset` | Two or more `SpectralDataset` inputs | `SpectralDataset` | Append compatible datasets and handle duplicate IDs according to explicit policy. |
| `AttachFeaturesToSpectralDataset` | `SpectralDataset` plus feature `DataFrame` | `SpectralDataset` | Join flat feature columns onto the dataset index by `spectrum_id` or another configured key without changing spectral rows. |

Accepted spectroscopy IO format support is an ADR-043 capability contract. The
tables below describe planned `FormatCapability` records. `Capability id` maps
to the formal `FormatCapability.id` field. Workflow config may persist that
value under `capability_id` when user selection is required.

All capability records must reference an existing `block_type` and `handler` on
the implementing IOBlock. `is_default/priority` is written as
`<is_default>/<priority>`. Load-only instrument formats must not declare a
`roundtrip_group`.

The `metadata_fidelity` column uses compact notation. For example,
`typed_meta(lambda_unit,intensity_unit)` means
`MetadataFidelity(level="typed_meta", typed_meta_reads=(...), typed_meta_writes=(...))`
with the appropriate read/write side for the capability direction; `lossless`
uses the same explicit field lists plus `level="lossless"`.

`Spectrum` load/save capabilities:

| Capability id | direction | data_type | format_id | extensions | label | block_type | handler | is_default/priority | roundtrip_group | metadata_fidelity |
|---|---|---|---|---|---|---|---|---|---|---|
| `scistudio-blocks-spectroscopy.spectrum.txt.load` | `load` | `Spectrum` | `txt` | `(".txt",)` | Text spectrum | `LoadSpectrum` | `_load_delimited_text` | `true/0` | `scistudio-blocks-spectroscopy.spectrum.txt` | `pixel_only` |
| `scistudio-blocks-spectroscopy.spectrum.txt.save` | `save` | `Spectrum` | `txt` | `(".txt",)` | Text spectrum | `SaveSpectrum` | `_save_delimited_text` | `true/0` | `scistudio-blocks-spectroscopy.spectrum.txt` | `pixel_only` |
| `scistudio-blocks-spectroscopy.spectrum.csv.load` | `load` | `Spectrum` | `csv` | `(".csv",)` | CSV spectrum | `LoadSpectrum` | `_load_delimited_text` | `true/0` | `scistudio-blocks-spectroscopy.spectrum.csv` | `pixel_only` |
| `scistudio-blocks-spectroscopy.spectrum.csv.save` | `save` | `Spectrum` | `csv` | `(".csv",)` | CSV spectrum | `SaveSpectrum` | `_save_delimited_text` | `true/0` | `scistudio-blocks-spectroscopy.spectrum.csv` | `pixel_only` |
| `scistudio-blocks-spectroscopy.spectrum.tsv.load` | `load` | `Spectrum` | `tsv` | `(".tsv",)` | TSV spectrum | `LoadSpectrum` | `_load_delimited_text` | `true/0` | `scistudio-blocks-spectroscopy.spectrum.tsv` | `pixel_only` |
| `scistudio-blocks-spectroscopy.spectrum.tsv.save` | `save` | `Spectrum` | `tsv` | `(".tsv",)` | TSV spectrum | `SaveSpectrum` | `_save_delimited_text` | `true/0` | `scistudio-blocks-spectroscopy.spectrum.tsv` | `pixel_only` |
| `scistudio-blocks-spectroscopy.spectrum.xlsx.load` | `load` | `Spectrum` | `xlsx` | `(".xlsx", ".xls")` | Excel spectrum workbook | `LoadSpectrum` | `_load_spectrum_xlsx` | `true/0` | `scistudio-blocks-spectroscopy.spectrum.xlsx` | `typed_meta(lambda_unit,intensity_unit,lambda_kind,modality)` |
| `scistudio-blocks-spectroscopy.spectrum.xlsx.save` | `save` | `Spectrum` | `xlsx` | `(".xlsx",)` | Excel spectrum workbook | `SaveSpectrum` | `_save_spectrum_xlsx` | `true/0` | `scistudio-blocks-spectroscopy.spectrum.xlsx` | `typed_meta(lambda_unit,intensity_unit,lambda_kind,modality)` |
| `scistudio-blocks-spectroscopy.spectrum.spectrum_json.load` | `load` | `Spectrum` | `spectrum_json` | `(".spectrum.json",)` | Native Spectrum JSON | `LoadSpectrum` | `_load_spectrum_json` | `true/0` | `scistudio-blocks-spectroscopy.spectrum.spectrum_json` | `lossless(lambda_unit,intensity_unit,lambda_kind,modality)` |
| `scistudio-blocks-spectroscopy.spectrum.spectrum_json.save` | `save` | `Spectrum` | `spectrum_json` | `(".spectrum.json",)` | Native Spectrum JSON | `SaveSpectrum` | `_save_spectrum_json` | `true/0` | `scistudio-blocks-spectroscopy.spectrum.spectrum_json` | `lossless(lambda_unit,intensity_unit,lambda_kind,modality)` |
| `scistudio-blocks-spectroscopy.spectrum.jcamp_dx.load` | `load` | `Spectrum` | `jcamp_dx` | `(".jdx", ".dx", ".jcamp")` | JCAMP-DX spectrum | `LoadSpectrum` | `_load_jcamp_dx` | `true/0` | `scistudio-blocks-spectroscopy.spectrum.jcamp_dx` | `typed_meta(lambda_unit,intensity_unit,lambda_kind,modality)` |
| `scistudio-blocks-spectroscopy.spectrum.jcamp_dx.save` | `save` | `Spectrum` | `jcamp_dx` | `(".jdx", ".dx", ".jcamp")` | JCAMP-DX spectrum | `SaveSpectrum` | `_save_jcamp_dx` | `true/0` | `scistudio-blocks-spectroscopy.spectrum.jcamp_dx` | `typed_meta(lambda_unit,intensity_unit,lambda_kind,modality)` |
| `scistudio-blocks-spectroscopy.spectrum.spc.load` | `load` | `Spectrum` | `spc` | `(".spc",)` | SPC spectrum | `LoadSpectrum` | `_load_spc` | `true/0` | `scistudio-blocks-spectroscopy.spectrum.spc` | `typed_meta(lambda_unit,intensity_unit,lambda_kind,modality)` |
| `scistudio-blocks-spectroscopy.spectrum.spc.save` | `save` | `Spectrum` | `spc` | `(".spc",)` | SPC spectrum | `SaveSpectrum` | `_save_spc` | `true/0` | `scistudio-blocks-spectroscopy.spectrum.spc` | `typed_meta(lambda_unit,intensity_unit,lambda_kind,modality)` |
| `scistudio-blocks-spectroscopy.spectrum.thermo_omnic_spa.load` | `load` | `Spectrum` | `thermo_omnic_spa` | `(".spa",)` | Thermo OMNIC SPA spectrum | `LoadSpectrum` | `_load_thermo_omnic_spa` | `true/0` | `null` | `typed_meta(lambda_unit,intensity_unit,lambda_kind,modality)` |
| `scistudio-blocks-spectroscopy.spectrum.bruker_opus.load` | `load` | `Spectrum` | `bruker_opus` | `(".opus",)` | Bruker OPUS spectrum | `LoadSpectrum` | `_load_bruker_opus` | `true/0` | `null` | `typed_meta(lambda_unit,intensity_unit,lambda_kind,modality)` |
| `scistudio-blocks-spectroscopy.spectrum.horiba_labspec.load` | `load` | `Spectrum` | `horiba_labspec` | `(".l6s", ".l5s", ".ngs", ".xml")` | HORIBA LabSpec spectrum | `LoadSpectrum` | `_load_horiba_labspec` | `true/0` | `null` | `typed_meta(lambda_unit,intensity_unit,lambda_kind,modality)` |
| `scistudio-blocks-spectroscopy.spectrum.renishaw_wdf.load` | `load` | `Spectrum` | `renishaw_wdf` | `(".wdf",)` | Renishaw WiRE spectrum | `LoadSpectrum` | `_load_renishaw_wdf` | `true/0` | `null` | `typed_meta(lambda_unit,intensity_unit,lambda_kind,modality)` |
| `scistudio-blocks-spectroscopy.spectrum.andor_solis.load` | `load` | `Spectrum` | `andor_solis` | `(".sif", ".fits", ".fit", ".asc")` | Andor Solis spectrum | `LoadSpectrum` | `_load_andor_solis` | `true/0` | `null` | `typed_meta(lambda_unit,intensity_unit,lambda_kind,modality)` |
| `scistudio-blocks-spectroscopy.spectrum.princeton_spe.load` | `load` | `Spectrum` | `princeton_spe` | `(".spe",)` | Princeton/LightField SPE spectrum | `LoadSpectrum` | `_load_princeton_spe` | `true/0` | `null` | `typed_meta(lambda_unit,intensity_unit,lambda_kind,modality)` |

`SpectralDataset` load/save capabilities:

| Capability id | direction | data_type | format_id | extensions | label | block_type | handler | is_default/priority | roundtrip_group | metadata_fidelity |
|---|---|---|---|---|---|---|---|---|---|---|
| `scistudio-blocks-spectroscopy.spectral_dataset.manifest_json.load` | `load` | `SpectralDataset` | `spectral_dataset_manifest_json` | `(".json",)` | SpectralDataset manifest (JSON) | `LoadSpectralDataset` | `_load_manifest_json` | `true/0` | `scistudio-blocks-spectroscopy.spectral_dataset.manifest_json` | `lossless(dataset_name,dataset_role,lambda_unit,intensity_unit,modality,schema_version)` |
| `scistudio-blocks-spectroscopy.spectral_dataset.manifest_json.save` | `save` | `SpectralDataset` | `spectral_dataset_manifest_json` | `(".json",)` | SpectralDataset manifest (JSON) | `SaveSpectralDataset` | `_save_manifest_json` | `true/0` | `scistudio-blocks-spectroscopy.spectral_dataset.manifest_json` | `lossless(dataset_name,dataset_role,lambda_unit,intensity_unit,modality,schema_version)` |
| `scistudio-blocks-spectroscopy.spectral_dataset.xlsx.load` | `load` | `SpectralDataset` | `xlsx` | `(".xlsx", ".xls")` | SpectralDataset Excel workbook | `LoadSpectralDataset` | `_load_dataset_xlsx` | `true/0` | `scistudio-blocks-spectroscopy.spectral_dataset.xlsx` | `typed_meta(dataset_name,dataset_role,lambda_unit,intensity_unit,modality,schema_version)` |
| `scistudio-blocks-spectroscopy.spectral_dataset.xlsx.save` | `save` | `SpectralDataset` | `xlsx` | `(".xlsx",)` | SpectralDataset Excel workbook | `SaveSpectralDataset` | `_save_dataset_xlsx` | `true/0` | `scistudio-blocks-spectroscopy.spectral_dataset.xlsx` | `typed_meta(dataset_name,dataset_role,lambda_unit,intensity_unit,modality,schema_version)` |
| `scistudio-blocks-spectroscopy.spectral_dataset.spc.load` | `load` | `SpectralDataset` | `spc` | `(".spc",)` | SPC spectral dataset | `LoadSpectralDataset` | `_load_spc_dataset` | `true/0` | `scistudio-blocks-spectroscopy.spectral_dataset.spc` | `typed_meta(dataset_name,dataset_role,lambda_unit,intensity_unit,modality,schema_version)` |
| `scistudio-blocks-spectroscopy.spectral_dataset.spc.save` | `save` | `SpectralDataset` | `spc` | `(".spc",)` | SPC spectral dataset | `SaveSpectralDataset` | `_save_spc_dataset` | `true/0` | `scistudio-blocks-spectroscopy.spectral_dataset.spc` | `typed_meta(dataset_name,dataset_role,lambda_unit,intensity_unit,modality,schema_version)` |
| `scistudio-blocks-spectroscopy.spectral_dataset.thermo_omnic_spg.load` | `load` | `SpectralDataset` | `thermo_omnic_spg` | `(".spg",)` | Thermo OMNIC SPG dataset | `LoadSpectralDataset` | `_load_thermo_omnic_spg` | `true/0` | `null` | `typed_meta(dataset_role,lambda_unit,intensity_unit,modality)` |
| `scistudio-blocks-spectroscopy.spectral_dataset.renishaw_wdf.load` | `load` | `SpectralDataset` | `renishaw_wdf` | `(".wdf",)` | Renishaw WiRE dataset | `LoadSpectralDataset` | `_load_renishaw_wdf_dataset` | `true/0` | `null` | `typed_meta(dataset_role,lambda_unit,intensity_unit,modality)` |
| `scistudio-blocks-spectroscopy.spectral_dataset.bruker_opus.load` | `load` | `SpectralDataset` | `bruker_opus` | `(".opus",)` | Bruker OPUS dataset | `LoadSpectralDataset` | `_load_bruker_opus_dataset` | `true/0` | `null` | `typed_meta(dataset_role,lambda_unit,intensity_unit,modality)` |
| `scistudio-blocks-spectroscopy.spectral_dataset.horiba_labspec.load` | `load` | `SpectralDataset` | `horiba_labspec` | `(".l6s", ".l5s", ".ngc", ".xml", ".txt")` | HORIBA LabSpec dataset | `LoadSpectralDataset` | `_load_horiba_labspec_dataset` | `true/0` | `null` | `typed_meta(dataset_role,lambda_unit,intensity_unit,modality)` |
| `scistudio-blocks-spectroscopy.spectral_dataset.witec_project.load` | `load` | `SpectralDataset` | `witec_project` | `(".wip", ".wid")` | WITec project dataset | `LoadSpectralDataset` | `_load_witec_project` | `true/0` | `null` | `typed_meta(dataset_role,lambda_unit,intensity_unit,modality)` |
| `scistudio-blocks-spectroscopy.spectral_dataset.andor_solis.load` | `load` | `SpectralDataset` | `andor_solis` | `(".sif", ".fits", ".fit")` | Andor Solis dataset | `LoadSpectralDataset` | `_load_andor_solis_dataset` | `true/0` | `null` | `typed_meta(dataset_role,lambda_unit,intensity_unit,modality)` |
| `scistudio-blocks-spectroscopy.spectral_dataset.princeton_spe.load` | `load` | `SpectralDataset` | `princeton_spe` | `(".spe",)` | Princeton/LightField SPE dataset | `LoadSpectralDataset` | `_load_princeton_spe_dataset` | `true/0` | `null` | `typed_meta(dataset_role,lambda_unit,intensity_unit,modality)` |

The `SpectralDataset` JSON manifest capability is package-owned but must remain
compatible with core `CompositeData` IO semantics: the boundary file is a JSON
manifest, slot payloads are sidecar files, and the required slots are the
package-defined `index` and `spectra` tables. The package may recommend a
filename such as `sample.spectraldataset.json`, but the declared ADR-043
extension remains `.json` unless a later architecture decision accepts a
compound or archive dataset format.

The `.ls6` extension is not accepted in this matrix. HORIBA LabSpec 6 is
represented by `.l6s` for single-spectrum data and by `.xml`/`.txt` transfer
profiles where those exports are selected. A future amendment may add `.ls6`
only if fixture data and owner review prove that it is a real file extension
that should be supported.

Bruker OPUS files may be extensionless or use numeric suffixes in practice.
The ADR-043 capability still declares `.opus` as the registry-visible
extension, and loaders must also support explicit `capability_id` selection for
extensionless OPUS inputs. They must not rely on engine-level suffix guessing.

`spectrum_id` is the join key inside `SpectralDataset`, not a filename. Source
filenames are ordinary metadata and may be selected as metadata join keys.
Feature tables are ordinary `DataFrame` values, not a package type. They must
carry `spectrum_id` so feature rows can be mapped back to spectra and datasets.

The accepted preprocessing block set processes `Collection[Spectrum]` values.

| Block | Input | Output ports | Accepted methods or modes | Required behavior |
|---|---|---|---|---|
| `CropSpectrumRange` | `Collection[Spectrum]` | `cropped: Collection[Spectrum]` | Range bounds `lambda_min`, `lambda_max` | Drop out-of-range coordinate points without changing kept intensities. |
| `ShiftSpectralAxis` | `Collection[Spectrum]` | `shifted: Collection[Spectrum]` | Configured shift amount | Shift the `lambda` axis without changing intensity values. |
| `BaselineCorrection` | `Collection[Spectrum]` | `corrected: Collection[Spectrum]`; `baseline: Collection[Spectrum]`; `fit_diagnostics: DataFrame` | `polynomial`, `asls`, `arpls`, `airpls` | Estimate baseline curves, subtract them, and report fit/estimation diagnostics. |
| `SmoothSpectrum` | `Collection[Spectrum]` | `smoothed: Collection[Spectrum]` | `savitzky_golay`, `moving_average`, `gaussian`, `median` | Smooth intensities without changing the `lambda` grid. |
| `AlignAndResampleSpectra` | `Collection[Spectrum]` | `aligned: Collection[Spectrum]`; `fit_curves: Collection[Spectrum]`; `fit_diagnostics: DataFrame` | Alignment `none`, `peak_fit`, `cross_correlation`; target grid explicit, first spectrum, reference spectrum, or range plus step | Align and/or resample spectra to a shared grid while reporting shifts and fit/correlation quality. |
| `NormalizeSpectrum` | `Collection[Spectrum]` | `normalized: Collection[Spectrum]` | `max`, `minmax` | Normalize intensities with only the accepted methods. |
| `SubtractPeakComponent` | `Collection[Spectrum]` | `corrected: Collection[Spectrum]`; `component: Collection[Spectrum]`; `fit_diagnostics: DataFrame` | `gaussian`, `lorentzian`, `voigt` | Fit a known peak/component, subtract it, output the fitted component curve, and report diagnostics. |

Preprocessing blocks deliberately do not accept `SpectralDataset`. Dataset
workflows use `SpectralDatasetToSpectrum` before preprocessing and
`SpectrumToSpectralDataset` after preprocessing when grouped metadata needs to
be restored.

The accepted feature extraction and measurement block set processes
`Collection[Spectrum]` values and emits ordinary feature `DataFrame` values
that can be merged into `SpectralDataset.index` by `spectrum_id`.

| Block | Input | Output | Required behavior |
|---|---|---|---|
| `ExtractIntensity` | `Collection[Spectrum]` plus one target peak, coordinate, or range definition | Feature `DataFrame` | Measure intensity for each spectrum and emit mergeable scalar columns with source `spectrum_id` and status. |
| `CalculateAUC` | `Collection[Spectrum]` plus `lambda_min` and `lambda_max` | Feature `DataFrame` | Calculate area under the curve for each spectrum over the requested range and emit mergeable scalar columns with status. |
| `CalculateCentroid` | `Collection[Spectrum]` plus `lambda_min` and `lambda_max` | Feature `DataFrame` | Calculate range centroid for each spectrum and emit mergeable scalar columns with status. |
| `CalculateRatio` | `Collection[Spectrum]` plus `numerator_peak` and `denominator_peak` definitions | Feature `DataFrame` | Measure two user-specified peak intensities for each spectrum and emit peak-to-peak ratio plus status. |
| `FindPeaks` | `Collection[Spectrum]` plus detection config and optional range bounds | Feature `DataFrame` | Find requested peaks, including peak-in-range measurements, and emit mergeable peak coordinate/intensity columns plus status and available detection metrics. |

The accepted peak fitting block set processes `Collection[Spectrum]` values and
emits fitted curves, residuals, and parameter/feature rows without modifying the
input spectra.

| Block | Inputs | Output ports | Accepted models | Required behavior |
|---|---|---|---|---|
| `FitPeak` | `Collection[Spectrum]` plus fit range and model config | `fit_curves: Collection[Spectrum]`; `residuals: Collection[Spectrum]`; `parameters: DataFrame` | `gaussian`, `lorentzian`, `voigt` | Fit the selected peak model, emit fitted curves and residual spectra on the fit grid, and record fitted parameters, FWHM, area, and fit-quality fields in `parameters`. |

The accepted reference correction block set processes `Collection[Spectrum]`
values against one explicit reference `Spectrum`.

| Block | Inputs | Output ports | Required behavior |
|---|---|---|---|
| `SubtractReferenceSpectrum` | `spectra: Collection[Spectrum]`; `reference: Spectrum` | `corrected: Collection[Spectrum]` | Subtract the reference intensity from each sample intensity after applying the explicit grid policy. |
| `DivideByReferenceSpectrum` | `spectra: Collection[Spectrum]`; `reference: Spectrum` | `corrected: Collection[Spectrum]` | Divide each sample intensity by the reference intensity after applying the explicit grid and zero policies. |

Reference correction blocks do not accept `SpectralDataset` directly and do not
select references by metadata. Users select or create one `Spectrum` reference
upstream, then pass it to the correction block.

The accepted spectral library matching block set compares query spectra against
library spectra stored as a `SpectralDataset`.

| Block | Inputs | Output ports | Accepted methods | Required behavior |
|---|---|---|---|---|
| `MatchSpectralLibrary` | `spectra: Collection[Spectrum]`; `library: SpectralDataset` | `matches: DataFrame` | `cosine_similarity`, `pearson_correlation`, `spectral_angle`, `euclidean_distance` | Rank library spectra for each query spectrum, emit one or more match rows per query, and record method, rank, score, library spectrum ID, and status. |

The accepted spectral unmixing block set contains one configurable block.

| Block | Inputs | Output ports | Accepted methods | Required behavior |
|---|---|---|---|---|
| `SpectralUnmixing` | `spectra: Collection[Spectrum]`; `references: Collection[Spectrum]` | `coefficients: DataFrame`; `fit_quality: DataFrame` | `least_squares`, `non_negative_least_squares`, `sum_to_one_non_negative_least_squares` | Fit each sample spectrum as a linear combination of reference spectra and emit wide coefficients plus per-sample fit quality. |

`SpectralUnmixing.coefficients` is the user-facing coefficient matrix.

| Column pattern | Required | Meaning |
|---|---:|---|
| `spectrum_id` | yes | The sample spectrum ID. |
| `method` | yes | The selected unmixing method. |
| `<coefficient column per reference>` | yes | Numeric contribution for one reference component. Column names are generated from the configured component label source and made deterministic, table-safe, and collision-free. |

Example coefficient shape:

| spectrum_id | method | coeff_uracil | coeff_uridine | coeff_background |
|---|---|---:|---:|---:|
| sample_001 | non_negative_least_squares | 0.73 | 0.18 | 0.04 |
| sample_002 | non_negative_least_squares | 0.21 | 0.61 | 0.10 |

`SpectralUnmixing.fit_quality` carries one diagnostics row per sample.

| Column | Required | Meaning |
|---|---:|---|
| `spectrum_id` | yes | The sample spectrum ID. |
| `method` | yes | The selected unmixing method. |
| `status` | yes | Fit status such as `ok`, `failed`, or `ill_conditioned`. |
| `residual_norm` | yes | Norm of the fit residual. |
| `rmse` | yes | Root mean squared fit error. |
| `n_components` | yes | Number of reference components used. |
| `r2` | no | Coefficient of determination when computable. |
| `condition_number` | no | Design-matrix condition number when available. |
| `message` | no | Human-readable diagnostic or failure reason. |

The unmixing output is intentionally tabular. Fitted spectra, residual spectra,
and component spectra are not part of this draft's output contract.

## 4. Implementation Plan

### 4.1 Technical Approach

Implement the package as a normal SciStudio plugin package once the full spec is
accepted. The package should register types through `scistudio.types`,
processing and IO blocks through `scistudio.blocks`, and previewers through
`scistudio.previewers`.

The type implementation should stay thin:

1. `Spectrum` constrains the semantic names and metadata of core `Series`.
2. `SpectralDataset` constrains composite slots and table schemas.
3. Validation helpers check required columns, ID uniqueness, joins, numeric
   coordinate/intensity columns, and unit consistency.
4. Previewers consume those contracts through bounded `PreviewDataAccess`.

The accepted utility blocks should stay similarly narrow. They own loading,
saving, conversion, filtering, merging, and feature-table attachment between
`Spectrum`, `Collection[Spectrum]`, `SpectralDataset`, and ordinary
`DataFrame` feature tables. They may validate schemas and join metadata tables,
but they must not perform spectral processing.

The accepted preprocessing blocks are the first scientific-transform block
group. They operate on `Collection[Spectrum]` only, preserve per-spectrum
identity, and keep fitted curves and diagnostics as first-class outputs for
all fitting or baseline-estimation behavior.

The accepted feature extraction and measurement blocks also operate on
`Collection[Spectrum]` only, but they produce feature tables instead of
transformed spectra. `ExtractIntensity`, `CalculateAUC`, `CalculateCentroid`,
`CalculateRatio`, and `FindPeaks` emit flat, index-mergeable feature tables.
`CalculateRatio` is peak-to-peak ratio only, and FWHM is recorded through peak
fit outputs rather than a separate measurement block.

The accepted peak fitting block operates on `Collection[Spectrum]` only. It
does not modify spectra; it emits fitted curves, residuals, and one
parameter/feature table named `parameters`.

The accepted reference correction blocks are narrow scientific transforms.
They operate on `Collection[Spectrum]` plus one explicit reference `Spectrum`,
preserve sample identity and metadata, and output corrected spectra only.

The accepted spectral library matching block compares `Collection[Spectrum]`
queries against a `SpectralDataset` library using one selected matching method.
It is not a calibration model, clustering block, or separate library type.

The accepted spectral unmixing block is an analysis block. It operates on
sample and reference `Collection[Spectrum]` values, exposes a closed method
enum in this draft, and outputs only ordinary `DataFrame` values: a wide
coefficient matrix for interoperability and a fit-quality table for diagnostics.

Previewers should be package-owned and may ship frontend assets when the core
fallback renderer cannot provide the agreed interactivity. They must remain
preview-only surfaces and must not write workflow outputs or mutate data refs.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `docs/specs/spectroscopy-package.md` | create | Owner-approved type and previewer design record. |
| `packages/scistudio-blocks-spectroscopy/pyproject.toml` | planned create | Package metadata, dependencies, and entry points. |
| `packages/scistudio-blocks-spectroscopy/src/scistudio_blocks_spectroscopy/types.py` | planned create | `Spectrum` and `SpectralDataset` definitions. |
| `packages/scistudio-blocks-spectroscopy/src/scistudio_blocks_spectroscopy/previewers/**` | planned create | Package-owned previewer providers and frontend assets. |
| `packages/scistudio-blocks-spectroscopy/src/scistudio_blocks_spectroscopy/blocks/utilities.py` | planned create | Accepted utility blocks for load/save, conversion, filtering, merging, and feature attachment. |
| `packages/scistudio-blocks-spectroscopy/src/scistudio_blocks_spectroscopy/blocks/preprocessing.py` | planned create | Accepted preprocessing blocks for `Collection[Spectrum]`. |
| `packages/scistudio-blocks-spectroscopy/src/scistudio_blocks_spectroscopy/blocks/feature_extraction.py` | planned create | Accepted intensity, AUC, centroid, peak-to-peak ratio, and peak-finding measurement blocks. |
| `packages/scistudio-blocks-spectroscopy/src/scistudio_blocks_spectroscopy/blocks/peak_fitting.py` | planned create | Accepted `FitPeak` block with fitted curves, residuals, and parameter/feature outputs. |
| `packages/scistudio-blocks-spectroscopy/src/scistudio_blocks_spectroscopy/blocks/reference_correction.py` | planned create | Accepted reference subtraction and reference division blocks. |
| `packages/scistudio-blocks-spectroscopy/src/scistudio_blocks_spectroscopy/blocks/library_matching.py` | planned create | Accepted `MatchSpectralLibrary` block and method-selection contract. |
| `packages/scistudio-blocks-spectroscopy/src/scistudio_blocks_spectroscopy/blocks/unmixing.py` | planned create | Accepted `SpectralUnmixing` block and coefficient/fit-quality table contracts. |
| `packages/scistudio-blocks-spectroscopy/src/scistudio_blocks_spectroscopy/blocks/**` | planned create | Later unaccepted analysis, calibration, clustering, and reporting blocks after owner approval. |
| `packages/scistudio-blocks-spectroscopy/tests/**` | planned create | Type, previewer, block, IO, and integration tests. |
| `packages/scistudio-blocks-spectroscopy/tests/test_format_capabilities.py` | planned create | ADR-043 `FormatCapability` field, direction, fidelity, round-trip, load-only, and ambiguity tests for spectroscopy IO. |
| `packages/scistudio-blocks-spectroscopy/tests/test_spectrum_io.py` | planned create | `LoadSpectrum` and `SaveSpectrum` tests. |
| `packages/scistudio-blocks-spectroscopy/tests/test_spectral_dataset_io.py` | planned create | `LoadSpectralDataset` and `SaveSpectralDataset` tests. |
| `packages/scistudio-blocks-spectroscopy/tests/test_utility_blocks.py` | planned create | Conversion, filtering, merging, feature attachment, and ID-policy tests. |
| `packages/scistudio-blocks-spectroscopy/tests/test_preprocessing_blocks.py` | planned create | Accepted preprocessing behavior and method coverage tests. |
| `packages/scistudio-blocks-spectroscopy/tests/test_preprocessing_fit_outputs.py` | planned create | Fitted-curve and diagnostics output-port tests. |
| `packages/scistudio-blocks-spectroscopy/tests/test_feature_extraction_blocks.py` | planned create | `ExtractIntensity`, `CalculateAUC`, `CalculateCentroid`, `CalculateRatio`, `FindPeaks`, and feature-table schema tests. |
| `packages/scistudio-blocks-spectroscopy/tests/test_peak_fitting_blocks.py` | planned create | `FitPeak` model, fitted-curve, residual, parameter-table, and FWHM tests. |
| `packages/scistudio-blocks-spectroscopy/tests/test_reference_correction_blocks.py` | planned create | Reference subtraction/division formulas, identity preservation, grid-policy, and zero-policy tests. |
| `packages/scistudio-blocks-spectroscopy/tests/test_library_matching_blocks.py` | planned create | `MatchSpectralLibrary` methods, rank ordering, grid/unit policy, and output schema tests. |
| `packages/scistudio-blocks-spectroscopy/tests/test_unmixing_blocks.py` | planned create | `SpectralUnmixing` method, wide coefficients, fit-quality, label collision, and grid-policy tests. |
| `packages/scistudio-blocks-spectroscopy/README.md` | planned create | Human-facing package usage and installation docs. |

### 4.3 Implementation Sequence

1. Continue owner discussion for remaining unaccepted analysis, calibration,
   clustering, and reporting blocks and amend this spec only when another block
   group is accepted.
2. Create the package skeleton with type, block, and previewer entry points but
   no placeholder block behavior.
3. Implement `Spectrum` and `SpectralDataset` plus schema validation tests.
4. Implement accepted utility blocks and their IO, conversion, filter, merge,
   feature-attachment, ID-policy, and metadata-join tests.
5. Implement accepted preprocessing blocks and their method, output-port,
   identity-preservation, fitted-curve, and diagnostics tests.
6. Implement accepted feature extraction and measurement blocks and their flat
   feature-table, `spectrum_id`, intensity, AUC, centroid, peak-to-peak ratio,
   peak-finding, range, and status tests.
7. Implement accepted peak fitting block and its model, fitted-curve, residual,
   parameter-table, FWHM, and failure-status tests.
8. Implement accepted reference correction blocks and their formula,
   grid-policy, zero-policy, and identity-preservation tests.
9. Implement accepted library matching block and its method, rank-ordering,
   grid/unit policy, and match-table schema tests.
10. Implement accepted `SpectralUnmixing` and its method, wide coefficient
   matrix, fit-quality, label-collision, and failure-status tests.
11. Implement `SpectrumPreviewer` and `SpectralDatasetPreviewer` registration and
   backend provider tests.
12. Add preview frontend assets only as needed to meet interaction and export
   requirements.
13. Implement later accepted analysis, calibration, clustering, and reporting
   blocks in the owner-approved dependency order.
14. Add package smoke tests, entry-point tests, previewer routing tests, and
   end-to-end spectroscopy workflow tests.

### 4.4 Verification Plan

Expected verification after implementation:

- Type tests prove `Spectrum` subclasses `Series`, exposes the required Meta
  fields, and records the concrete type chain.
- Type tests prove `SpectralDataset` subclasses `CompositeData`, requires
  `index` and `spectra` slots, validates required columns, and reports join
  problems.
- Previewer registration tests prove both package previewers are discoverable
  through `scistudio.previewers`.
- Previewer tests prove large spectra and large datasets use bounded reads.
- Previewer tests prove every accepted plot mode renders a bounded envelope with
  honest sampling/truncation metadata.
- Export tests prove figure and table exports are available and labeled as
  preview exports.
- Format capability tests prove all spectroscopy IO format support is declared
  through ADR-043 `FormatCapability` records on the four accepted IO utility
  blocks, with stable package-qualified `id` values and no extension support
  declared on data types.
- Utility block tests prove load/save, conversion, filtering, merging,
  feature attachment, generated-ID behavior, metadata joins by `spectrum_id`
  and `source_file`, and duplicate-ID policies.
- IO tests prove SPC has both load and save capabilities, accepted
  vendor/native instrument formats are load-only, and `SpectralDataset` native
  save/load follows the core `CompositeData` JSON manifest plus sidecar slot
  model rather than a zip or archive format.
- Preprocessing tests prove every accepted preprocessing block accepts
  `Collection[Spectrum]`, rejects `SpectralDataset`, preserves item count,
  order, and `spectrum_id`, and supports only the accepted methods.
- Fit-output tests prove `BaselineCorrection`, `AlignAndResampleSpectra` when
  peak fitting is used, and `SubtractPeakComponent` expose fitted-curve
  collection outputs plus `fit_diagnostics` `DataFrame` outputs, and that peak
  fit-output tables include FWHM where available.
- Feature extraction tests prove `ExtractIntensity`, `CalculateAUC`,
  `CalculateCentroid`, `CalculateRatio`, and `FindPeaks` accept
  `Collection[Spectrum]`, output flat `DataFrame` values with `spectrum_id`,
  can be merged into `SpectralDataset.index`, and do not output `Spectrum` or
  other object-cell values.
- Measurement tests prove intensity, AUC, centroid, and peak-to-peak ratio
  calculations record explicit status for missing peaks, empty ranges, unusable
  denominators, or other non-success cases.
- Peak-finding tests prove `FindPeaks` supports optional range bounds and covers
  targeted peak-in-range measurement without a separate `MeasurePeakInRange`
  block.
- Peak fitting tests prove `FitPeak` accepts `Collection[Spectrum]`, supports
  exactly Gaussian, Lorentzian, and Voigt models, emits fitted curves and
  residual spectra, and uses `parameters: DataFrame` rather than a
  `fit_diagnostics` output port.
- Reference correction tests prove `SubtractReferenceSpectrum` and
  `DivideByReferenceSpectrum` accept `Collection[Spectrum]` plus one
  `Spectrum` reference, reject `SpectralDataset`, preserve identity and
  metadata, apply the correct formula, fail by default on grid mismatch, and
  require explicit zero handling for division by zero.
- Library matching tests prove `MatchSpectralLibrary` accepts query spectra and
  a `SpectralDataset` library, supports only the accepted selectable methods,
  emits ranked match rows, and fails or reports non-success status for
  incompatible grids or units by default.
- Unmixing tests prove `SpectralUnmixing` accepts sample and reference
  `Collection[Spectrum]` values, supports only the accepted methods, emits a
  wide coefficient table with deterministic component columns, emits a
  per-sample fit-quality table, handles duplicate labels without overwriting,
  and does not emit fitted/residual spectrum outputs.
- Package entry-point tests prove `scistudio.types`, `scistudio.blocks`, and
  `scistudio.previewers` resolve the package without importing SRS.

For this documentation-only draft, implementation tests are not expected until
package code exists.

### 4.5 Risks And Rollback

Risk: The `lambda` column name is concise but physically overloaded across
wavelength, wavenumber, Raman shift, and emission coordinates.

Mitigation: Keep the owner-selected column name and require `lambda_kind` plus
unit metadata. Implementation code can use internal names such as
`lambda_values` to avoid Python keyword conflicts.

Risk: `SpectralDataset` could grow into a general analytics table and constrain
future feature outputs too much.

Mitigation: Keep `SpectralDataset` narrowly scoped to raw or processed spectral
points plus per-spectrum metadata. Feature outputs remain ordinary flat
`DataFrame` instances keyed by `spectrum_id`, and
`AttachFeaturesToSpectralDataset` performs explicit joins back to the dataset
index when users need grouped plotting or downstream metadata access.

Risk: Dataset preview export could be mistaken for workflow lineage output.

Mitigation: Label preview exports clearly and keep workflow-producing saves in
the accepted `SaveSpectrum` and `SaveSpectralDataset` utility blocks.

Risk: File names are convenient join handles, but using them as default
`spectrum_id` values would make library datasets and non-file-backed datasets
fragile.

Mitigation: Treat `spectrum_id` as a managed internal ID. Preserve source file
names as metadata and allow filename-based metadata joins, but never make
filename the default ID.

Risk: The previewer may tempt implementation agents to add processing controls
directly in the preview UI.

Mitigation: FR-030 forbids scientific processing in previewers. Previewers may
filter, group, aggregate for display, and export the current view, but durable
scientific transformations must be blocks.

Risk: Utility blocks may become a dumping ground for analysis behavior.

Mitigation: FR-052 keeps the utility set limited to loading, saving,
conversion, filtering, merging, and feature-table attachment. Scientific
transformations must be added as separate owner-approved block groups.

Risk: Peak finding can become modality-specific or overstate ambiguous peak
detection results.

Mitigation: `FindPeaks` is specified as a feature extraction block with
configurable detection parameters and explicit output status/metrics. It does
not replace fitted peak modeling or library matching.

Risk: Centroid calculations can produce misleading values when the configured
range has no usable signal.

Mitigation: `CalculateCentroid` must include range bounds and status fields in
its output and must report empty or unusable-denominator cases explicitly.

Risk: Preprocessing blocks may accidentally accept `SpectralDataset` directly,
mixing scientific transformations with dataset organization and grouped
metadata behavior.

Mitigation: FR-054 requires accepted preprocessing blocks to accept only
`Collection[Spectrum]`. Dataset workflows must use utility conversion blocks
around preprocessing.

Risk: Implementers may treat fitted curves and fit-output tables as optional
extras for fitting or estimation blocks.

Mitigation: FR-061 through FR-064, FR-070 through FR-073, FR-077 through
FR-081 require stable fitted-curve and diagnostics output ports for the
preprocessing fit/estimation blocks. FR-116 through FR-120 require `FitPeak` to
emit fitted curves, residuals, and `parameters: DataFrame` instead of a
`fit_diagnostics` port. Tests must assert the ports exist even when users do
not consume them.

Risk: Baseline correction, smoothing, normalization, and component subtraction
could expand into broad algorithm menus before core behavior is stable.

Mitigation: The accepted method sets are closed in this draft. New methods
require an owner-approved spec amendment.

Risk: Reference correction could grow hidden reference-selection behavior that
duplicates dataset filtering or library matching.

Mitigation: The accepted reference correction blocks take one explicit
`Spectrum` reference. Selecting that reference from a dataset or library is an
upstream workflow concern, not part of these blocks.

Risk: Reference division can produce invalid values when the reference contains
zero or near-zero intensities.

Mitigation: Division by zero defaults to an error. Any non-error behavior must
be explicit in block config and covered by tests.

Risk: Library matching scores can be misleading when spectra use incompatible
grids, units, or preprocessing states.

Mitigation: `MatchSpectralLibrary` requires an explicit matching method and grid
or unit compatibility policy. The default behavior must fail or report
non-success status for incompatible inputs rather than silently interpolating or
converting.

Risk: Library matching and calibration/clustering could be conflated as one
general analysis surface.

Mitigation: This draft accepts only `MatchSpectralLibrary` for ranked library
matches. Calibration modeling, clustering, PCA, embedding, and reporting blocks
remain out of scope until a later owner-approved amendment.

Risk: Unmixing coefficient column names can collide or become awkward when
reference labels contain spaces, punctuation, or duplicate names.

Mitigation: The block must generate deterministic, table-safe, collision-free
coefficient column names from the configured component label source.

Risk: Wide coefficient output is less tidy than long-form output for some
statistical workflows.

Mitigation: Wide output is accepted because it improves copy/paste and
matrix-oriented interoperability. Long-form tables can be derived later through
generic table reshaping, but the unmixing block's default output stays wide.

Risk: Users may expect unmixing to output fitted spectra, residual spectra, or
a composite result object.

Mitigation: This draft intentionally limits unmixing outputs to coefficients
and fit quality. Additional outputs require a later owner-approved amendment.

Rollback: Because no package implementation exists yet, rollback for this draft
is a spec edit. Remove or amend the affected type, previewer, utility,
preprocessing, feature extraction, peak fitting, reference correction, library
matching, or unmixing requirement before implementation starts.

## 5. Success Criteria

### Measurable Outcomes

- SC-001: The final accepted spec names exactly two package data types:
  `Spectrum` and `SpectralDataset`.
- SC-002: `Spectrum` implementation tests prove the class subclasses `Series`
  and exposes `lambda_unit` and `intensity_unit` metadata.
- SC-003: `SpectralDataset` implementation tests prove the composite requires
  `index` and `spectra` slots and validates the required table columns.
- SC-004: Preview routing tests prove exact `Spectrum` refs route to
  `SpectrumPreviewer` and exact `SpectralDataset` refs route to
  `SpectralDatasetPreviewer`.
- SC-005: Previewer tests prove grouped plotting works using arbitrary index
  table columns, including at least `material` and one preparation or condition
  column.
- SC-006: Previewer tests prove export/save controls exist for figures and
  visible data in both previewers.
- SC-007: No package code imports from `scistudio_blocks_srs`, and no SRS type
  or block is required for spectroscopy package import or tests.
- SC-008: The accepted utility block set contains exactly the nine utility
  blocks named in FR-032.
- SC-009: Utility tests prove `LoadSpectrum` generates unique `spectrum_id`
  values when inputs lack IDs and preserves `source_file` separately from the
  ID.
- SC-010: Utility tests prove `SpectrumToSpectralDataset` can join metadata by
  `spectrum_id` and by `source_file` or `filename`.
- SC-011: Utility tests prove `SpectralDatasetToSpectrum` round-trips index-row
  metadata onto emitted spectra.
- SC-012: Utility tests prove `FilterSpectralDataset` filters both slots by
  `spectrum_id` without changing spectral values.
- SC-013: Utility tests prove `MergeSpectralDataset` rejects duplicate IDs by
  default and respects explicit duplicate-ID policies.
- SC-014: Utility tests prove `AttachFeaturesToSpectralDataset` joins flat
  feature tables onto `SpectralDataset.index` by `spectrum_id`, rejects missing
  join keys, and does not modify `SpectralDataset.spectra`.
- SC-015: The remaining calibration, reporting, and additional analysis block
  catalog, beyond the accepted feature extraction, peak fitting, reference
  correction, library matching, and spectral unmixing blocks, is not treated as
  accepted until this spec is amended with owner-approved block requirements.
- SC-016: The accepted preprocessing block set contains exactly the seven
  preprocessing blocks named in FR-053.
- SC-017: Preprocessing tests prove each accepted preprocessing block accepts
  `Collection[Spectrum]` and does not accept `SpectralDataset` directly.
- SC-018: Preprocessing tests prove item count, order, and `spectrum_id` values
  are preserved across every accepted preprocessing block.
- SC-019: Baseline correction tests prove only `polynomial`, `asls`, `arpls`,
  and `airpls` are exposed in this draft.
- SC-020: Smoothing tests prove only `savitzky_golay`, `moving_average`,
  `gaussian`, and `median` are exposed in this draft.
- SC-021: Alignment/resampling tests prove `none`, `peak_fit`, and
  `cross_correlation` alignment modes plus the accepted target-grid modes.
- SC-022: Normalization tests prove only `max` and `minmax` are exposed in this
  draft.
- SC-023: Peak-component subtraction tests prove `gaussian`, `lorentzian`, and
  `voigt` component models are exposed.
- SC-024: Fit-output tests prove `BaselineCorrection` always emits
  `corrected`, `baseline`, and `fit_diagnostics`; `AlignAndResampleSpectra`
  always emits `aligned`, `fit_curves`, and `fit_diagnostics`; and
  `SubtractPeakComponent` always emits `corrected`, `component`, and
  `fit_diagnostics` including FWHM where available.
- SC-025: The accepted feature extraction and measurement block set contains
  exactly `ExtractIntensity`, `CalculateAUC`, `CalculateCentroid`,
  `CalculateRatio`, and `FindPeaks`.
- SC-026: Feature extraction tests prove every accepted measurement block
  accepts `Collection[Spectrum]`, rejects `SpectralDataset` directly, and emits
  flat `DataFrame` outputs that can merge into `SpectralDataset.index` by
  `spectrum_id`.
- SC-027: Measurement tests prove `ExtractIntensity`, `CalculateAUC`, and
  `CalculateCentroid` compute the requested scalar measurements and report
  explicit status for missing coordinates, empty ranges, or unusable
  denominators.
- SC-028: Ratio and peak tests prove `CalculateRatio` is peak-to-peak ratio
  only, `FindPeaks` supports optional range bounds, and no standalone
  `CalculateFWHM` or `MeasurePeakInRange` block is registered.
- SC-029: The accepted reference correction block set contains exactly
  `SubtractReferenceSpectrum` and `DivideByReferenceSpectrum`.
- SC-030: Reference correction tests prove both blocks accept
  `Collection[Spectrum]` plus one `Spectrum` reference and reject
  `SpectralDataset` directly.
- SC-031: Reference correction tests prove subtraction and division apply the
  specified formulas while preserving item count, item order, `spectrum_id`,
  metadata, and sample `lambda` grids.
- SC-032: Reference correction tests prove mismatched grids fail by default and
  division by zero requires explicit non-default handling.
- SC-033: The accepted spectral unmixing block set contains exactly
  `SpectralUnmixing`.
- SC-034: Unmixing tests prove `SpectralUnmixing` exposes exactly two required
  output ports: `coefficients` and `fit_quality`.
- SC-035: Unmixing tests prove `coefficients` is a wide table with one row per
  sample spectrum, `spectrum_id`, `method`, and one deterministic numeric
  coefficient column per reference component.
- SC-036: Unmixing tests prove `fit_quality` is a per-sample table with
  `spectrum_id`, `method`, `status`, `residual_norm`, `rmse`, and
  `n_components`.
- SC-037: Unmixing tests prove only `least_squares`,
  `non_negative_least_squares`, and
  `sum_to_one_non_negative_least_squares` are exposed in this draft.
- SC-038: Unmixing tests prove the block does not define or emit a
  `SpectralUnmixingResult`, fitted spectra, residual spectra, or component
  spectra.
- SC-039: The accepted peak fitting block set contains exactly `FitPeak`.
- SC-040: Peak fitting tests prove `FitPeak` supports exactly `gaussian`,
  `lorentzian`, and `voigt` models.
- SC-041: Peak fitting tests prove `FitPeak` emits `fit_curves`, `residuals`,
  and `parameters`, and does not expose a `fit_diagnostics` output port.
- SC-042: Peak fitting tests prove `FitPeak.parameters` includes fitted center,
  amplitude, width parameters, FWHM, area, status, and fit-quality fields where
  available.
- SC-043: The accepted spectral library matching block set contains exactly
  `MatchSpectralLibrary`.
- SC-044: Library matching tests prove only `cosine_similarity`,
  `pearson_correlation`, `spectral_angle`, and `euclidean_distance` are exposed
  in this draft.
- SC-045: Library matching tests prove `MatchSpectralLibrary.matches` contains
  `spectrum_id`, `library_spectrum_id`, `method`, `rank`, `score`, and `status`
  columns and ranks best matches as rank 1.
- SC-046: Library matching tests prove incompatible grids or units fail or
  report non-success status by default, and calibration, clustering, PCA, and
  reporting blocks are not registered in this draft.
- SC-047: Package smoke tests prove block registration includes the accepted
  utility, preprocessing, feature extraction, peak fitting, reference
  correction, library matching, and spectral unmixing blocks and does not
  register unaccepted calibration, clustering, reporting, or additional analysis
  blocks.
- SC-048: Format capability tests prove `LoadSpectrum`, `SaveSpectrum`,
  `LoadSpectralDataset`, and `SaveSpectralDataset` expose explicit ADR-043
  `FormatCapability` records with the formal fields required by ADR-043.
- SC-049: Format capability tests prove `capability_id` is used only as a
  workflow or lookup reference to `FormatCapability.id`, and no package type
  declares file extensions or format support.
- SC-050: Spectrum IO tests prove `.txt`, `.csv`, `.tsv`, `.xlsx`,
  `.spectrum.json`, JCAMP-DX, and SPC capabilities can load and save according
  to their declared metadata fidelity.
- SC-051: Spectrum and dataset format tests prove SPC (`.spc`) has both load
  and save capabilities, including the dataset case when the SPC payload
  contains multiple spectra.
- SC-052: Format capability tests prove vendor/native instrument formats
  accepted in this draft are load-only and do not declare saver capabilities,
  `roundtrip_group`, or `lossless` metadata fidelity.
- SC-053: Dataset IO tests prove `SpectralDataset` native JSON save/load uses
  a package-owned JSON manifest plus sidecar `index` and `spectra` table slots,
  aligned with core `CompositeData` IO semantics.
- SC-054: Format capability tests prove no `.zip` or `.spectraldataset.zip`
  capability is declared for `SpectralDataset` in this draft.
- SC-055: Format capability tests prove workflow lookup fails on unresolved
  ambiguity rather than choosing by registration order.

## 6. Assumptions

- The owner wants the package document written in the repo's normalized English
  spec style even though the design discussion is in Chinese.
- `lambda` remains the canonical coordinate column and Series index name unless
  the owner explicitly changes it later.
- `SpectralDataset` is the right shape for both experimental datasets and
  reference/library datasets.
- Preview-side grouping and aggregation are acceptable when they are clearly
  display-only and do not create workflow lineage outputs.
- The nine utility blocks recorded in this draft are accepted.
- The seven preprocessing blocks recorded in this draft are accepted.
- The five feature extraction and measurement blocks recorded in this draft are
  accepted: `ExtractIntensity`, `CalculateAUC`, `CalculateCentroid`,
  `CalculateRatio`, and `FindPeaks`.
- The peak fitting block recorded in this draft is accepted: `FitPeak`.
- The two reference correction blocks recorded in this draft are accepted:
  `SubtractReferenceSpectrum` and `DivideByReferenceSpectrum`.
- `NormalizeByReferenceSpectrum` is intentionally not accepted in this draft.
- The spectral library matching block recorded in this draft is accepted:
  `MatchSpectralLibrary`.
- The spectral unmixing block recorded in this draft is accepted:
  `SpectralUnmixing`.
- ADR-043 is the governing contract for spectroscopy IO format support. The
  accepted matrix is a planned `FormatCapability` matrix, not a declaration of
  extensions on data types.
- Core `CompositeData` IO currently supports JSON manifest load/save with
  sidecar slot files. `SpectralDataset` native IO should align with that model
  unless a later architecture decision adds another composite bundle format.
- HORIBA LabSpec 6 single-spectrum support is assumed to use `.l6s` rather than
  `.ls6`; `.ls6` remains unaccepted until fixture evidence proves otherwise.
- Bruker OPUS support is assumed to require explicit `capability_id` selection
  for extensionless or numeric-extension files because ADR-043 does not allow
  engine-level suffix guessing.
- Calibration, clustering, reporting, and additional analysis blocks beyond the
  accepted feature extraction, peak fitting, reference correction, library
  matching, and spectral unmixing blocks remain pending discussion and will be
  added in later amendments.
