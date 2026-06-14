"""Per-format handler stubs for ``SpectralDataset`` load/save (FR-135..FR-139).

Each function corresponds to one ``handler=`` named in a
``LoadSpectralDataset`` / ``SaveSpectralDataset`` ``FormatCapability`` record
(spec §"SpectralDataset load/save capabilities"). The block methods delegate
here; implementers fill the bodies.

Loaders return a single :class:`SpectralDataset` (two ``DataFrame`` slots:
``index`` and ``spectra``). Savers write *dataset* to *path* and return
``None``. Heavy/optional parsers must be lazy-imported inside the body.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scistudio_blocks_spectroscopy.types import SpectralDataset

# --------------------------------------------------------------------------
# Package-owned load + save formats
# --------------------------------------------------------------------------


def load_manifest_json(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load the package-native JSON manifest dataset (lossless).

    Implementation plan (FR-135, FR-141):
      1. Read the CompositeData-compatible JSON manifest (boundary file).
      2. Resolve sidecar slot files for `index` and `spectra` tables.
      3. Reconstruct SpectralDataset(slots={"index": df, "spectra": df},
         meta=SpectralDataset.Meta(dataset_name, dataset_role, units, modality,
         schema_version)).
    Edge cases: missing sidecar; required-column absence; schema-version drift.
    Test plan: test_spectral_dataset_io.py::test_manifest_json_lossless_roundtrip.
    """
    raise NotImplementedError("skeleton — implement per FR-135/FR-141 (manifest_json load); see comment above")


def save_manifest_json(dataset: SpectralDataset, path: Path, **kwargs: Any) -> None:
    """Save the package-native JSON manifest dataset (lossless).

    Implementation plan (FR-135, FR-141):
      1. Write `index` and `spectra` slot tables as sidecar files.
      2. Write the JSON manifest (.json) referencing sidecars + dataset Meta.
    Edge cases: parent dir missing; empty dataset; non-default filename hint.
    Test plan: test_spectral_dataset_io.py::test_manifest_json_lossless_roundtrip.
    """
    raise NotImplementedError("skeleton — implement per FR-135/FR-141 (manifest_json save); see comment above")


def load_dataset_xlsx(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a ``.xlsx``/``.xls`` workbook dataset (index/spectra/meta sheets).

    Implementation plan (FR-137):
      1. Lazy-import the workbook reader.
      2. Read `index` sheet (one row per spectrum, spectrum_id required),
         `spectra` sheet (long-form spectrum_id/lambda/intensity), optional
         `meta` sheet -> SpectralDataset.Meta.
    Edge cases: missing required sheet; orphan spectra rows; duplicate ids.
    Test plan: test_spectral_dataset_io.py::test_load_dataset_xlsx_three_sheets.
    """
    raise NotImplementedError("skeleton — implement per FR-137 (dataset xlsx load); see comment above")


def save_dataset_xlsx(dataset: SpectralDataset, path: Path, **kwargs: Any) -> None:
    """Save a dataset to an ``.xlsx`` workbook (index/spectra/meta sheets).

    Implementation plan (FR-137, FR-039):
      1. Write `index` sheet, `spectra` long-form sheet, `meta` sheet.
    Edge cases: meta=None; very large spectra table (row limit per sheet).
    Test plan: test_spectral_dataset_io.py::test_save_dataset_xlsx_three_sheets.
    """
    raise NotImplementedError("skeleton — implement per FR-137 (dataset xlsx save); see comment above")


def load_spc_dataset(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a multi-spectrum SPC (``.spc``) dataset.

    Implementation plan (FR-138):
      1. Parse SPC header; iterate all subfiles into long-form spectra rows.
      2. Build an `index` row per subfile (generated spectrum_id) + `spectra`.
    Edge cases: single-subfile SPC (still a 1-row dataset); shared x-axis.
    Test plan: test_spectral_dataset_io.py::test_load_spc_dataset_multi.
    """
    raise NotImplementedError("skeleton — implement per FR-138 (spc dataset load); see comment above")


def save_spc_dataset(dataset: SpectralDataset, path: Path, **kwargs: Any) -> None:
    """Save a dataset as multi-subfile SPC (``.spc``).

    Implementation plan (FR-138, FR-039):
      1. Group `spectra` by spectrum_id; write one SPC subfile each.
    Edge cases: irregular per-spectrum grids; >2^16 subfiles.
    Test plan: test_spectral_dataset_io.py::test_save_spc_dataset_multi.
    """
    raise NotImplementedError("skeleton — implement per FR-138 (spc dataset save); see comment above")


# --------------------------------------------------------------------------
# Vendor / instrument-native LOAD-ONLY dataset formats (FR-139, FR-140)
# --------------------------------------------------------------------------


def load_thermo_omnic_spg(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a Thermo OMNIC ``.spg`` multi-spectrum group (load-only).

    Implementation plan (FR-139, FR-140):
      1. Parse SPG container; iterate member spectra into long-form rows.
      2. Build `index` (generated ids + titles) and `spectra` slots.
    Edge cases: heterogeneous ranges across members.
    Test plan: test_spectral_dataset_io.py::test_load_thermo_omnic_spg.
    """
    raise NotImplementedError("skeleton — implement per FR-139 (thermo_omnic_spg load); see comment above")


def load_renishaw_wdf_dataset(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a Renishaw WiRE ``.wdf`` map/series as a dataset (load-only).

    Implementation plan (FR-139, FR-140):
      1. Parse WDF; read xlist + all spectra; map ORGN coords into `index`.
    Edge cases: large maps (bounded read); 2-D map flattening.
    Test plan: test_spectral_dataset_io.py::test_load_renishaw_wdf_map.
    """
    raise NotImplementedError("skeleton — implement per FR-139 (renishaw_wdf dataset load); see comment above")


def load_bruker_opus_dataset(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a Bruker OPUS file holding multiple spectra as a dataset (load-only).

    Implementation plan (FR-139, FR-140):
      1. Parse OPUS block directory; collect each data block as one spectrum.
    Edge cases: single-block OPUS -> 1-row dataset; extensionless via capability_id.
    Test plan: test_spectral_dataset_io.py::test_load_bruker_opus_dataset.
    """
    raise NotImplementedError("skeleton — implement per FR-139 (bruker_opus dataset load); see comment above")


def load_horiba_labspec_dataset(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a HORIBA LabSpec map/group export as a dataset (load-only).

    Implementation plan (FR-139, FR-140):
      1. Detect l6s/l5s/ngc/xml/txt flavour; iterate all spectra in the export.
    Edge cases: map coordinate metadata -> `index` columns.
    Test plan: test_spectral_dataset_io.py::test_load_horiba_labspec_dataset.
    """
    raise NotImplementedError("skeleton — implement per FR-139 (horiba_labspec dataset load); see comment above")


def load_witec_project(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a WITec project (``.wip``/``.wid``) as a dataset (load-only).

    Implementation plan (FR-139, FR-140):
      1. Parse the WITec project container; extract spectra graphs/maps.
    Edge cases: image vs spectrum objects; nested data containers.
    Test plan: test_spectral_dataset_io.py::test_load_witec_project.
    """
    raise NotImplementedError("skeleton — implement per FR-139 (witec_project load); see comment above")


def load_andor_solis_dataset(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load an Andor Solis (``.sif``/``.fits``/``.fit``) multi-spectrum file (load-only).

    Implementation plan (FR-139, FR-140):
      1. Read all frames/rows; build one spectrum per frame into the dataset.
    Edge cases: single-frame file -> 1-row dataset; kinetic series.
    Test plan: test_spectral_dataset_io.py::test_load_andor_solis_dataset.
    """
    raise NotImplementedError("skeleton — implement per FR-139 (andor_solis dataset load); see comment above")


def load_princeton_spe_dataset(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a Princeton/LightField ``.spe`` multi-frame file as a dataset (load-only).

    Implementation plan (FR-139, FR-140):
      1. Read all frames; one spectrum per frame into the dataset.
    Edge cases: v2 vs v3 SPE; ROI/region handling.
    Test plan: test_spectral_dataset_io.py::test_load_princeton_spe_dataset.
    """
    raise NotImplementedError("skeleton — implement per FR-139 (princeton_spe dataset load); see comment above")


__all__ = [
    "load_andor_solis_dataset",
    "load_bruker_opus_dataset",
    "load_dataset_xlsx",
    "load_horiba_labspec_dataset",
    "load_manifest_json",
    "load_princeton_spe_dataset",
    "load_renishaw_wdf_dataset",
    "load_spc_dataset",
    "load_thermo_omnic_spg",
    "load_witec_project",
    "save_dataset_xlsx",
    "save_manifest_json",
    "save_spc_dataset",
]
