"""Per-format handler stubs for ``SpectralDataset`` load/save (FR-135..FR-139).

Each function corresponds to one ``handler=`` named in a
``LoadSpectralDataset`` / ``SaveSpectralDataset`` ``FormatCapability`` record
(spec §"SpectralDataset load/save capabilities"). The block methods delegate
here; implementers fill the bodies.

Loaders return a single :class:`SpectralDataset` (two ``DataFrame`` slots:
``index`` and ``spectra``). Savers write *dataset* to *path* and return
``None``. Heavy/optional parsers must be lazy-imported inside the body.

Package-owned formats implemented here:

- ``manifest_json`` (``.json``) — lossless package-native manifest aligned with
  the core ``CompositeData`` JSON-manifest + sidecar slot model (FR-135,
  FR-141). The boundary ``.json`` carries dataset ``Meta`` plus references to
  two sidecar Parquet files (one per slot table). Parquet round-trips the
  ``index``/``spectra`` Arrow tables losslessly, so the manifest preserves
  ``index.spectrum_id``, the long-form ``spectra`` columns
  (``spectrum_id``/``lambda``/``intensity``), and every ``SpectralDataset.Meta``
  field.
- ``xlsx`` (``.xlsx``/``.xls``) — explicit ``index``, ``spectra``, and optional
  ``meta`` sheets (``typed_meta`` fidelity, FR-137).

Vendor / instrument-native multi-spectrum formats and ``.spc`` are deferred
(``NotImplementedError`` with a tracked ``TODO(#1661)``) because they need a
fixture or an optional binary SDK that is not available in this draft.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa

from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.types import (
    INTENSITY_COLUMN,
    LAMBDA_COLUMN,
    SPECTRUM_ID_COLUMN,
    SpectralDataset,
)

# Package-native manifest schema marker (FR-135, FR-141). Bumping this is a
# schema-version change; the loader accepts manifests it understands and raises
# on unknown future major shapes.
_MANIFEST_SCHEMA = "scistudio-blocks-spectroscopy.spectral_dataset_manifest/1"

# Excel sheet names for the workbook layout (FR-137).
_SHEET_INDEX = "index"
_SHEET_SPECTRA = "spectra"
_SHEET_META = "meta"

# SpectralDataset.Meta fields carried by the lossless/typed-meta capabilities
# (matches the capability-record typed_meta tuples in utilities.py).
_DATASET_META_FIELDS = (
    "dataset_name",
    "dataset_role",
    "lambda_unit",
    "intensity_unit",
    "modality",
    "schema_version",
)


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------


def _dataset_meta(dataset: SpectralDataset) -> dict[str, Any]:
    """Return the dataset's typed Meta as a plain JSON-serialisable dict."""
    meta = dataset.meta
    if meta is None or not isinstance(meta, SpectralDataset.Meta):
        return {field: None for field in _DATASET_META_FIELDS}
    return {field: getattr(meta, field, None) for field in _DATASET_META_FIELDS}


def _meta_from_mapping(values: dict[str, Any]) -> SpectralDataset.Meta:
    """Build a :class:`SpectralDataset.Meta` from a mapping (ignores extras)."""
    kwargs = {field: values.get(field) for field in _DATASET_META_FIELDS}
    return SpectralDataset.Meta(**kwargs)


def _validate_dataset_tables(index_table: pa.Table, spectra_table: pa.Table) -> None:
    """Validate the canonical two-table layout (FR-038, FR-009..FR-012)."""
    if SPECTRUM_ID_COLUMN not in index_table.column_names:
        raise ValueError(
            f"SpectralDataset index table must contain a {SPECTRUM_ID_COLUMN!r} column; "
            f"got {list(index_table.column_names)}"
        )
    required_spectra = {SPECTRUM_ID_COLUMN, LAMBDA_COLUMN, INTENSITY_COLUMN}
    missing = required_spectra.difference(spectra_table.column_names)
    if missing:
        raise ValueError(
            f"SpectralDataset spectra table must contain {sorted(required_spectra)} columns; missing {sorted(missing)}"
        )
    index_ids = set(index_table.column(SPECTRUM_ID_COLUMN).to_pylist())
    spectra_ids = set(spectra_table.column(SPECTRUM_ID_COLUMN).to_pylist())
    orphans = spectra_ids.difference(index_ids)
    if orphans:
        raise ValueError(
            f"SpectralDataset spectra rows reference unknown spectrum_id(s) {sorted(orphans)}; "
            "every spectra.spectrum_id must join to index.spectrum_id (FR-012)"
        )


def _sidecar_paths(path: Path) -> tuple[Path, Path]:
    """Return the (index, spectra) Parquet sidecar paths for a manifest *path*."""
    stem = path.name
    # Strip a trailing ``.json`` (and a ``.spectraldataset`` infix when present)
    # so ``sample.spectraldataset.json`` -> ``sample`` sidecar stems.
    if stem.lower().endswith(".json"):
        stem = stem[: -len(".json")]
    if stem.lower().endswith(".spectraldataset"):
        stem = stem[: -len(".spectraldataset")]
    base = path.parent / stem
    return (
        base.with_name(f"{base.name}.index.parquet"),
        base.with_name(f"{base.name}.spectra.parquet"),
    )


# --------------------------------------------------------------------------
# Package-owned load + save formats
# --------------------------------------------------------------------------


def load_manifest_json(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load the package-native JSON manifest dataset (lossless).

    The boundary ``.json`` carries dataset ``Meta`` plus references to two
    sidecar Parquet files (``index`` and ``spectra`` slot tables). Parquet
    round-trips the Arrow tables losslessly, so all coordinates, intensities,
    ids, and typed ``Meta`` survive (FR-135, FR-141).
    """
    import pyarrow.parquet as pq

    path = Path(path)
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))

    schema = manifest.get("schema_version") or manifest.get("schema")
    if schema is not None and str(schema).rsplit("/", 1)[0] != _MANIFEST_SCHEMA.rsplit("/", 1)[0]:
        raise ValueError(f"Unsupported SpectralDataset manifest schema {schema!r}; expected {_MANIFEST_SCHEMA!r}")

    slots = manifest.get("slots", {})

    def _resolve(slot_name: str) -> Path:
        ref = slots.get(slot_name)
        if not ref or "path" not in ref:
            raise ValueError(f"SpectralDataset manifest is missing the {slot_name!r} slot reference")
        sidecar = Path(ref["path"])
        if not sidecar.is_absolute():
            sidecar = path.parent / sidecar
        if not sidecar.exists():
            raise FileNotFoundError(f"SpectralDataset manifest {slot_name!r} sidecar not found: {sidecar}")
        return sidecar

    index_table = pq.read_table(_resolve("index"))
    spectra_table = pq.read_table(_resolve("spectra"))
    _validate_dataset_tables(index_table, spectra_table)

    meta = _meta_from_mapping(manifest.get("meta", {}))
    return _support.build_spectral_dataset(index_table, spectra_table, meta=meta)


def save_manifest_json(dataset: SpectralDataset, path: Path, **kwargs: Any) -> None:
    """Save the package-native JSON manifest dataset (lossless).

    Writes ``index`` and ``spectra`` slot tables as sidecar Parquet files next
    to the manifest, then a JSON manifest referencing them plus dataset ``Meta``
    (FR-135, FR-141).
    """
    import pyarrow.parquet as pq

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    index_table, spectra_table = _support.dataset_frames(dataset)
    _validate_dataset_tables(index_table, spectra_table)

    index_sidecar, spectra_sidecar = _sidecar_paths(path)
    pq.write_table(index_table, index_sidecar)
    pq.write_table(spectra_table, spectra_sidecar)

    manifest = {
        "schema_version": _MANIFEST_SCHEMA,
        "data_type": "SpectralDataset",
        "meta": _dataset_meta(dataset),
        "slots": {
            "index": {"backend": "parquet", "format": "parquet", "path": index_sidecar.name},
            "spectra": {"backend": "parquet", "format": "parquet", "path": spectra_sidecar.name},
        },
    }
    path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")


def load_dataset_xlsx(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a ``.xlsx``/``.xls`` workbook dataset (index/spectra/meta sheets).

    Reads the ``index`` sheet (one row per spectrum, ``spectrum_id`` required),
    the long-form ``spectra`` sheet (``spectrum_id``/``lambda``/``intensity``),
    and an optional ``meta`` sheet of dataset-level typed metadata (FR-137).
    """
    import pandas as pd  # lazy: pandas pulls openpyxl for .xlsx

    path = Path(path)
    sheets = pd.read_excel(path, sheet_name=None)

    if _SHEET_INDEX not in sheets:
        raise ValueError(f"SpectralDataset workbook is missing the required {_SHEET_INDEX!r} sheet")
    if _SHEET_SPECTRA not in sheets:
        raise ValueError(f"SpectralDataset workbook is missing the required {_SHEET_SPECTRA!r} sheet")

    index_df = sheets[_SHEET_INDEX]
    spectra_df = sheets[_SHEET_SPECTRA]

    index_table = pa.Table.from_pandas(index_df, preserve_index=False)
    spectra_table = pa.Table.from_pandas(spectra_df, preserve_index=False)
    _validate_dataset_tables(index_table, spectra_table)

    meta_values: dict[str, Any] = {}
    if _SHEET_META in sheets:
        meta_df = sheets[_SHEET_META]
        # The meta sheet is a two-column key/value table (field, value).
        cols = [str(c) for c in meta_df.columns]
        if len(cols) >= 2:
            key_col, value_col = meta_df.columns[0], meta_df.columns[1]
            for _, row in meta_df.iterrows():
                key = row[key_col]
                value = row[value_col]
                if key is None or (isinstance(value, float) and pd.isna(value)):
                    value = None
                meta_values[str(key)] = None if value is None else value

    meta = _meta_from_mapping(meta_values)
    return _support.build_spectral_dataset(index_table, spectra_table, meta=meta)


def save_dataset_xlsx(dataset: SpectralDataset, path: Path, **kwargs: Any) -> None:
    """Save a dataset to an ``.xlsx`` workbook (index/spectra/meta sheets).

    Writes the ``index`` sheet, the long-form ``spectra`` sheet, and a ``meta``
    sheet of dataset-level typed metadata as key/value rows (FR-137, FR-039).
    """
    import pandas as pd  # lazy: pandas pulls openpyxl for .xlsx

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    index_table, spectra_table = _support.dataset_frames(dataset)
    _validate_dataset_tables(index_table, spectra_table)

    index_df = index_table.to_pandas()
    spectra_df = spectra_table.to_pandas()
    meta_items = list(_dataset_meta(dataset).items())
    meta_df = pd.DataFrame(meta_items, columns=["field", "value"])

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        index_df.to_excel(writer, sheet_name=_SHEET_INDEX, index=False)
        spectra_df.to_excel(writer, sheet_name=_SHEET_SPECTRA, index=False)
        meta_df.to_excel(writer, sheet_name=_SHEET_META, index=False)


def load_spc_dataset(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a multi-spectrum SPC (``.spc``) dataset.

    Deferred: a faithful multi-subfile SPC reader needs a real ``.spc`` fixture
    or an optional SPC parsing library, neither of which is available in this
    draft.
    """
    # TODO(#1661): SPC multi-spectrum needs a fixture/lib
    #   Out of scope per spec FR-138 (no fixture / optional SPC SDK available).
    #   Followup: https://github.com/zjzcpj/scistudio/issues/1661
    raise NotImplementedError("SPC multi-spectrum dataset load — no fixture/optional SPC library")


def save_spc_dataset(dataset: SpectralDataset, path: Path, **kwargs: Any) -> None:
    """Save a dataset as multi-subfile SPC (``.spc``).

    Deferred: a faithful multi-subfile SPC writer needs a real ``.spc`` fixture
    or an optional SPC library to validate the binary container against.
    """
    # TODO(#1661): SPC multi-spectrum needs a fixture/lib
    #   Out of scope per spec FR-138 (no fixture / optional SPC SDK available).
    #   Followup: https://github.com/zjzcpj/scistudio/issues/1661
    raise NotImplementedError("SPC multi-spectrum dataset save — no fixture/optional SPC library")


# --------------------------------------------------------------------------
# Vendor / instrument-native LOAD-ONLY dataset formats (FR-139, FR-140)
#
# Each is genuinely a proprietary multi-spectrum binary container. Without a
# fixture file or an optional vendor SDK they cannot be implemented or tested,
# so each raises an informative NotImplementedError with a tracked TODO. They
# remain load-only (no saver, no roundtrip_group, no lossless fidelity) per
# FR-140.
# --------------------------------------------------------------------------


def load_thermo_omnic_spg(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a Thermo OMNIC ``.spg`` multi-spectrum group (load-only)."""
    # TODO(#1661): Thermo OMNIC SPG multi-spectrum needs a fixture/lib
    #   Out of scope per spec FR-139 (vendor binary, no fixture/optional SDK).
    #   Followup: https://github.com/zjzcpj/scistudio/issues/1661
    raise NotImplementedError("vendor binary multi-spectrum — no fixture/optional SDK")


def load_renishaw_wdf_dataset(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a Renishaw WiRE ``.wdf`` map/series as a dataset (load-only)."""
    # TODO(#1661): Renishaw WDF multi-spectrum needs a fixture/lib
    #   Out of scope per spec FR-139 (vendor binary, no fixture/optional SDK).
    #   Followup: https://github.com/zjzcpj/scistudio/issues/1661
    raise NotImplementedError("vendor binary multi-spectrum — no fixture/optional SDK")


def load_bruker_opus_dataset(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a Bruker OPUS file holding multiple spectra as a dataset (load-only)."""
    # TODO(#1661): Bruker OPUS multi-spectrum needs a fixture/lib
    #   Out of scope per spec FR-139 (vendor binary, no fixture/optional SDK).
    #   Followup: https://github.com/zjzcpj/scistudio/issues/1661
    raise NotImplementedError("vendor binary multi-spectrum — no fixture/optional SDK")


def load_horiba_labspec_dataset(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a HORIBA LabSpec map/group export as a dataset (load-only)."""
    # TODO(#1661): HORIBA LabSpec multi-spectrum needs a fixture/lib
    #   Out of scope per spec FR-139 (vendor binary, no fixture/optional SDK).
    #   Followup: https://github.com/zjzcpj/scistudio/issues/1661
    raise NotImplementedError("vendor binary multi-spectrum — no fixture/optional SDK")


def load_witec_project(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a WITec project (``.wip``/``.wid``) as a dataset (load-only)."""
    # TODO(#1661): WITec project multi-spectrum needs a fixture/lib
    #   Out of scope per spec FR-139 (vendor binary, no fixture/optional SDK).
    #   Followup: https://github.com/zjzcpj/scistudio/issues/1661
    raise NotImplementedError("vendor binary multi-spectrum — no fixture/optional SDK")


def load_andor_solis_dataset(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load an Andor Solis (``.sif``/``.fits``/``.fit``) multi-spectrum file (load-only)."""
    # TODO(#1661): Andor Solis multi-spectrum needs a fixture/lib
    #   Out of scope per spec FR-139 (vendor binary, no fixture/optional SDK).
    #   Followup: https://github.com/zjzcpj/scistudio/issues/1661
    raise NotImplementedError("vendor binary multi-spectrum — no fixture/optional SDK")


def load_princeton_spe_dataset(path: Path, **kwargs: Any) -> SpectralDataset:
    """Load a Princeton/LightField ``.spe`` multi-frame file as a dataset (load-only)."""
    # TODO(#1661): Princeton SPE multi-spectrum needs a fixture/lib
    #   Out of scope per spec FR-139 (vendor binary, no fixture/optional SDK).
    #   Followup: https://github.com/zjzcpj/scistudio/issues/1661
    raise NotImplementedError("vendor binary multi-spectrum — no fixture/optional SDK")


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
