"""IO and utility blocks for the spectroscopy package."""

from __future__ import annotations

import glob
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any, ClassVar, cast

import pandas as pd
import pyarrow as pa

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.io.capabilities import (
    CapabilityDirection,
    FormatCapability,
    MetadataFidelity,
    MetadataFidelityLevel,
)
from scistudio.blocks.io.io_block import IOBlock
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.text import Text
from scistudio_blocks_spectroscopy._tables import dataframe_from_pandas, to_pandas_frame
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

_PACKAGE = "scistudio-blocks-spectroscopy"
_SPECTRUM_META_FIELDS = ("lambda_unit", "intensity_unit", "lambda_kind", "modality")
_DATASET_META_FIELDS = ("dataset_name", "dataset_role", "lambda_unit", "intensity_unit", "modality", "schema_version")
_VENDOR_DATASET_META_FIELDS = ("dataset_role", "lambda_unit", "intensity_unit", "modality")
_LAMBDA_ALIASES = ("lambda", "wavelength", "wavenumber", "raman_shift", "shift", "x")
_INTENSITY_ALIASES = ("intensity", "absorbance", "signal", "counts", "y")


def _typed_fidelity(
    direction: CapabilityDirection,
    fields: tuple[str, ...],
    *,
    level: MetadataFidelityLevel = "typed_meta",
) -> MetadataFidelity:
    if direction == "load":
        return MetadataFidelity(level=level, typed_meta_reads=fields)
    return MetadataFidelity(level=level, typed_meta_writes=fields)


def _cap(
    *,
    prefix: str,
    direction: CapabilityDirection,
    data_type: type[DataObject],
    format_id: str,
    id_format: str | None = None,
    extensions: tuple[str, ...],
    label: str,
    block_type: str,
    handler: str,
    fidelity: MetadataFidelity,
    roundtrip_group: str | None = None,
) -> FormatCapability:
    return FormatCapability(
        id=f"{_PACKAGE}.{prefix}.{id_format or format_id}.{direction}",
        direction=direction,
        data_type=data_type,
        format_id=format_id,
        extensions=extensions,
        label=label,
        block_type=block_type,
        handler=handler,
        is_default=True,
        priority=0,
        roundtrip_group=roundtrip_group,
        metadata_fidelity=fidelity,
    )


def _spectrum_load_capabilities() -> tuple[FormatCapability, ...]:
    return (
        _cap(
            prefix="spectrum",
            direction="load",
            data_type=Spectrum,
            format_id="txt",
            extensions=(".txt",),
            label="Text spectrum",
            block_type="LoadSpectrum",
            handler="_load_delimited_text",
            fidelity=MetadataFidelity(level="pixel_only"),
            roundtrip_group=f"{_PACKAGE}.spectrum.txt",
        ),
        _cap(
            prefix="spectrum",
            direction="load",
            data_type=Spectrum,
            format_id="csv",
            extensions=(".csv",),
            label="CSV spectrum",
            block_type="LoadSpectrum",
            handler="_load_delimited_text",
            fidelity=MetadataFidelity(level="pixel_only"),
            roundtrip_group=f"{_PACKAGE}.spectrum.csv",
        ),
        _cap(
            prefix="spectrum",
            direction="load",
            data_type=Spectrum,
            format_id="tsv",
            extensions=(".tsv",),
            label="TSV spectrum",
            block_type="LoadSpectrum",
            handler="_load_delimited_text",
            fidelity=MetadataFidelity(level="pixel_only"),
            roundtrip_group=f"{_PACKAGE}.spectrum.tsv",
        ),
        _cap(
            prefix="spectrum",
            direction="load",
            data_type=Spectrum,
            format_id="xlsx",
            extensions=(".xlsx", ".xls"),
            label="Excel spectrum workbook",
            block_type="LoadSpectrum",
            handler="_load_spectrum_xlsx",
            fidelity=_typed_fidelity("load", _SPECTRUM_META_FIELDS),
            roundtrip_group=f"{_PACKAGE}.spectrum.xlsx",
        ),
        _cap(
            prefix="spectrum",
            direction="load",
            data_type=Spectrum,
            format_id="spectrum_json",
            extensions=(".spectrum.json",),
            label="Native Spectrum JSON",
            block_type="LoadSpectrum",
            handler="_load_spectrum_json",
            fidelity=_typed_fidelity("load", _SPECTRUM_META_FIELDS, level="lossless"),
            roundtrip_group=f"{_PACKAGE}.spectrum.spectrum_json",
        ),
        _cap(
            prefix="spectrum",
            direction="load",
            data_type=Spectrum,
            format_id="jcamp_dx",
            extensions=(".jdx", ".dx", ".jcamp"),
            label="JCAMP-DX spectrum",
            block_type="LoadSpectrum",
            handler="_load_jcamp_dx",
            fidelity=_typed_fidelity("load", _SPECTRUM_META_FIELDS),
            roundtrip_group=f"{_PACKAGE}.spectrum.jcamp_dx",
        ),
        _cap(
            prefix="spectrum",
            direction="load",
            data_type=Spectrum,
            format_id="spc",
            extensions=(".spc",),
            label="SPC spectrum",
            block_type="LoadSpectrum",
            handler="_load_spc",
            fidelity=_typed_fidelity("load", _SPECTRUM_META_FIELDS),
            roundtrip_group=f"{_PACKAGE}.spectrum.spc",
        ),
        _cap(
            prefix="spectrum",
            direction="load",
            data_type=Spectrum,
            format_id="thermo_omnic_spa",
            extensions=(".spa",),
            label="Thermo OMNIC SPA spectrum",
            block_type="LoadSpectrum",
            handler="_load_thermo_omnic_spa",
            fidelity=_typed_fidelity("load", _SPECTRUM_META_FIELDS),
        ),
        _cap(
            prefix="spectrum",
            direction="load",
            data_type=Spectrum,
            format_id="bruker_opus",
            extensions=(".opus",),
            label="Bruker OPUS spectrum",
            block_type="LoadSpectrum",
            handler="_load_bruker_opus",
            fidelity=_typed_fidelity("load", _SPECTRUM_META_FIELDS),
        ),
        _cap(
            prefix="spectrum",
            direction="load",
            data_type=Spectrum,
            format_id="horiba_labspec",
            extensions=(".l6s", ".l5s", ".ngs", ".xml"),
            label="HORIBA LabSpec spectrum",
            block_type="LoadSpectrum",
            handler="_load_horiba_labspec",
            fidelity=_typed_fidelity("load", _SPECTRUM_META_FIELDS),
        ),
        _cap(
            prefix="spectrum",
            direction="load",
            data_type=Spectrum,
            format_id="renishaw_wdf",
            extensions=(".wdf",),
            label="Renishaw WiRE spectrum",
            block_type="LoadSpectrum",
            handler="_load_renishaw_wdf",
            fidelity=_typed_fidelity("load", _SPECTRUM_META_FIELDS),
        ),
        _cap(
            prefix="spectrum",
            direction="load",
            data_type=Spectrum,
            format_id="andor_solis",
            extensions=(".sif", ".fits", ".fit", ".asc"),
            label="Andor Solis spectrum",
            block_type="LoadSpectrum",
            handler="_load_andor_solis",
            fidelity=_typed_fidelity("load", _SPECTRUM_META_FIELDS),
        ),
        _cap(
            prefix="spectrum",
            direction="load",
            data_type=Spectrum,
            format_id="princeton_spe",
            extensions=(".spe",),
            label="Princeton/LightField SPE spectrum",
            block_type="LoadSpectrum",
            handler="_load_princeton_spe",
            fidelity=_typed_fidelity("load", _SPECTRUM_META_FIELDS),
        ),
    )


def _spectrum_save_capabilities() -> tuple[FormatCapability, ...]:
    return (
        _cap(
            prefix="spectrum",
            direction="save",
            data_type=Spectrum,
            format_id="txt",
            extensions=(".txt",),
            label="Text spectrum",
            block_type="SaveSpectrum",
            handler="_save_delimited_text",
            fidelity=MetadataFidelity(level="pixel_only"),
            roundtrip_group=f"{_PACKAGE}.spectrum.txt",
        ),
        _cap(
            prefix="spectrum",
            direction="save",
            data_type=Spectrum,
            format_id="csv",
            extensions=(".csv",),
            label="CSV spectrum",
            block_type="SaveSpectrum",
            handler="_save_delimited_text",
            fidelity=MetadataFidelity(level="pixel_only"),
            roundtrip_group=f"{_PACKAGE}.spectrum.csv",
        ),
        _cap(
            prefix="spectrum",
            direction="save",
            data_type=Spectrum,
            format_id="tsv",
            extensions=(".tsv",),
            label="TSV spectrum",
            block_type="SaveSpectrum",
            handler="_save_delimited_text",
            fidelity=MetadataFidelity(level="pixel_only"),
            roundtrip_group=f"{_PACKAGE}.spectrum.tsv",
        ),
        _cap(
            prefix="spectrum",
            direction="save",
            data_type=Spectrum,
            format_id="xlsx",
            extensions=(".xlsx",),
            label="Excel spectrum workbook",
            block_type="SaveSpectrum",
            handler="_save_spectrum_xlsx",
            fidelity=_typed_fidelity("save", _SPECTRUM_META_FIELDS),
            roundtrip_group=f"{_PACKAGE}.spectrum.xlsx",
        ),
        _cap(
            prefix="spectrum",
            direction="save",
            data_type=Spectrum,
            format_id="spectrum_json",
            extensions=(".spectrum.json",),
            label="Native Spectrum JSON",
            block_type="SaveSpectrum",
            handler="_save_spectrum_json",
            fidelity=_typed_fidelity("save", _SPECTRUM_META_FIELDS, level="lossless"),
            roundtrip_group=f"{_PACKAGE}.spectrum.spectrum_json",
        ),
        _cap(
            prefix="spectrum",
            direction="save",
            data_type=Spectrum,
            format_id="jcamp_dx",
            extensions=(".jdx", ".dx", ".jcamp"),
            label="JCAMP-DX spectrum",
            block_type="SaveSpectrum",
            handler="_save_jcamp_dx",
            fidelity=_typed_fidelity("save", _SPECTRUM_META_FIELDS),
            roundtrip_group=f"{_PACKAGE}.spectrum.jcamp_dx",
        ),
        _cap(
            prefix="spectrum",
            direction="save",
            data_type=Spectrum,
            format_id="spc",
            extensions=(".spc",),
            label="SPC spectrum",
            block_type="SaveSpectrum",
            handler="_save_spc",
            fidelity=_typed_fidelity("save", _SPECTRUM_META_FIELDS),
            roundtrip_group=f"{_PACKAGE}.spectrum.spc",
        ),
    )


def _dataset_load_capabilities() -> tuple[FormatCapability, ...]:
    return (
        _cap(
            prefix="spectral_dataset",
            direction="load",
            data_type=SpectralDataset,
            format_id="spectral_dataset_manifest_json",
            id_format="manifest_json",
            extensions=(".json",),
            label="SpectralDataset manifest (JSON)",
            block_type="LoadSpectralDataset",
            handler="_load_manifest_json",
            fidelity=_typed_fidelity("load", _DATASET_META_FIELDS, level="lossless"),
            roundtrip_group=f"{_PACKAGE}.spectral_dataset.manifest_json",
        ),
        _cap(
            prefix="spectral_dataset",
            direction="load",
            data_type=SpectralDataset,
            format_id="xlsx",
            extensions=(".xlsx", ".xls"),
            label="SpectralDataset Excel workbook",
            block_type="LoadSpectralDataset",
            handler="_load_dataset_xlsx",
            fidelity=_typed_fidelity("load", _DATASET_META_FIELDS),
            roundtrip_group=f"{_PACKAGE}.spectral_dataset.xlsx",
        ),
        _cap(
            prefix="spectral_dataset",
            direction="load",
            data_type=SpectralDataset,
            format_id="spc",
            extensions=(".spc",),
            label="SPC spectral dataset",
            block_type="LoadSpectralDataset",
            handler="_load_spc_dataset",
            fidelity=_typed_fidelity("load", _DATASET_META_FIELDS),
            roundtrip_group=f"{_PACKAGE}.spectral_dataset.spc",
        ),
        _cap(
            prefix="spectral_dataset",
            direction="load",
            data_type=SpectralDataset,
            format_id="thermo_omnic_spg",
            extensions=(".spg",),
            label="Thermo OMNIC SPG dataset",
            block_type="LoadSpectralDataset",
            handler="_load_thermo_omnic_spg",
            fidelity=_typed_fidelity("load", _VENDOR_DATASET_META_FIELDS),
        ),
        _cap(
            prefix="spectral_dataset",
            direction="load",
            data_type=SpectralDataset,
            format_id="renishaw_wdf",
            extensions=(".wdf",),
            label="Renishaw WiRE dataset",
            block_type="LoadSpectralDataset",
            handler="_load_renishaw_wdf_dataset",
            fidelity=_typed_fidelity("load", _VENDOR_DATASET_META_FIELDS),
        ),
        _cap(
            prefix="spectral_dataset",
            direction="load",
            data_type=SpectralDataset,
            format_id="bruker_opus",
            extensions=(".opus",),
            label="Bruker OPUS dataset",
            block_type="LoadSpectralDataset",
            handler="_load_bruker_opus_dataset",
            fidelity=_typed_fidelity("load", _VENDOR_DATASET_META_FIELDS),
        ),
        _cap(
            prefix="spectral_dataset",
            direction="load",
            data_type=SpectralDataset,
            format_id="horiba_labspec",
            extensions=(".l6s", ".l5s", ".ngc", ".xml", ".txt"),
            label="HORIBA LabSpec dataset",
            block_type="LoadSpectralDataset",
            handler="_load_horiba_labspec_dataset",
            fidelity=_typed_fidelity("load", _VENDOR_DATASET_META_FIELDS),
        ),
        _cap(
            prefix="spectral_dataset",
            direction="load",
            data_type=SpectralDataset,
            format_id="witec_project",
            extensions=(".wip", ".wid"),
            label="WITec project dataset",
            block_type="LoadSpectralDataset",
            handler="_load_witec_project",
            fidelity=_typed_fidelity("load", _VENDOR_DATASET_META_FIELDS),
        ),
        _cap(
            prefix="spectral_dataset",
            direction="load",
            data_type=SpectralDataset,
            format_id="andor_solis",
            extensions=(".sif", ".fits", ".fit"),
            label="Andor Solis dataset",
            block_type="LoadSpectralDataset",
            handler="_load_andor_solis_dataset",
            fidelity=_typed_fidelity("load", _VENDOR_DATASET_META_FIELDS),
        ),
        _cap(
            prefix="spectral_dataset",
            direction="load",
            data_type=SpectralDataset,
            format_id="princeton_spe",
            extensions=(".spe",),
            label="Princeton/LightField SPE dataset",
            block_type="LoadSpectralDataset",
            handler="_load_princeton_spe_dataset",
            fidelity=_typed_fidelity("load", _VENDOR_DATASET_META_FIELDS),
        ),
    )


def _dataset_save_capabilities() -> tuple[FormatCapability, ...]:
    return (
        _cap(
            prefix="spectral_dataset",
            direction="save",
            data_type=SpectralDataset,
            format_id="spectral_dataset_manifest_json",
            id_format="manifest_json",
            extensions=(".json",),
            label="SpectralDataset manifest (JSON)",
            block_type="SaveSpectralDataset",
            handler="_save_manifest_json",
            fidelity=_typed_fidelity("save", _DATASET_META_FIELDS, level="lossless"),
            roundtrip_group=f"{_PACKAGE}.spectral_dataset.manifest_json",
        ),
        _cap(
            prefix="spectral_dataset",
            direction="save",
            data_type=SpectralDataset,
            format_id="xlsx",
            extensions=(".xlsx",),
            label="SpectralDataset Excel workbook",
            block_type="SaveSpectralDataset",
            handler="_save_dataset_xlsx",
            fidelity=_typed_fidelity("save", _DATASET_META_FIELDS),
            roundtrip_group=f"{_PACKAGE}.spectral_dataset.xlsx",
        ),
        _cap(
            prefix="spectral_dataset",
            direction="save",
            data_type=SpectralDataset,
            format_id="spc",
            extensions=(".spc",),
            label="SPC spectral dataset",
            block_type="SaveSpectralDataset",
            handler="_save_spc_dataset",
            fidelity=_typed_fidelity("save", _DATASET_META_FIELDS),
            roundtrip_group=f"{_PACKAGE}.spectral_dataset.spc",
        ),
    )


def _match_capability(
    capabilities: tuple[FormatCapability, ...],
    path: Path | None,
    config: BlockConfig,
) -> FormatCapability:
    capability_id = config.get("capability_id")
    if capability_id:
        for capability in capabilities:
            if capability.id == capability_id:
                return capability
        raise ValueError(f"Unknown capability_id {capability_id!r}")

    format_id = config.get("format") or config.get("format_id")
    if format_id:
        matches = [capability for capability in capabilities if capability.format_id == str(format_id).lower()]
        if len(matches) == 1:
            return matches[0]
        if matches:
            return sorted(matches, key=lambda cap: cap.id)[0]
        raise ValueError(f"Unknown format {format_id!r}")

    if path is None:
        raise ValueError("Format selection requires path, format, or capability_id")
    path_text = path.name.lower()
    matches = [
        capability for capability in capabilities if any(path_text.endswith(ext) for ext in capability.extensions)
    ]
    if not matches:
        raise ValueError(f"No declared capability matches {path}")
    matches.sort(key=lambda cap: max(len(ext) for ext in cap.extensions if path_text.endswith(ext)), reverse=True)
    return matches[0]


def _resolve_paths(raw_path: Any, capabilities: tuple[FormatCapability, ...], config: BlockConfig) -> list[Path]:
    if isinstance(raw_path, list):
        paths = [Path(str(item)) for item in raw_path if str(item)]
    elif isinstance(raw_path, str) and raw_path:
        candidate = Path(raw_path)
        if any(char in raw_path for char in "*?[]"):
            paths = [Path(path) for path in glob.glob(raw_path)]
        elif candidate.is_dir():
            extensions = tuple(ext for capability in capabilities for ext in capability.extensions)
            paths = [path for path in candidate.iterdir() if path.is_file() and path.name.lower().endswith(extensions)]
        else:
            paths = [candidate]
    else:
        raise ValueError("path must be a non-empty string or list of strings")
    if not paths:
        raise ValueError("no input files matched")
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"source file not found: {missing[0]}")
    if config.get("capability_id"):
        return sorted(paths)
    return sorted(paths, key=lambda path: str(path))


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _metadata_from_comments(lines: list[str]) -> tuple[dict[str, Any], list[str]]:
    metadata: dict[str, Any] = {}
    data_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("##"):
            key_value = stripped[2:]
            if "=" in key_value:
                key, value = key_value.split("=", 1)
                metadata[key.strip().lower()] = value.strip()
            continue
        if stripped.startswith("#"):
            key_value = stripped[1:]
            if ":" in key_value:
                key, value = key_value.split(":", 1)
                metadata[key.strip()] = value.strip()
            elif "=" in key_value:
                key, value = key_value.split("=", 1)
                metadata[key.strip()] = value.strip()
            continue
        data_lines.append(line)
    return metadata, data_lines


def _read_delimited_frame(path: Path, *, sep: str | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    metadata, data_lines = _metadata_from_comments(lines)
    if not data_lines:
        raise ValueError(f"{path} does not contain spectral data rows")
    raw = "\n".join(data_lines)
    parse_sep = sep
    if parse_sep is None:
        parse_sep = "\t" if path.suffix.lower() == ".tsv" else "," if path.suffix.lower() == ".csv" else None
    try:
        frame = pd.read_csv(io.StringIO(raw), sep=parse_sep, engine="python")
    except Exception:
        frame = pd.read_csv(io.StringIO(raw), sep=r"\s+", engine="python", header=None)
    if frame.shape[1] < 2:
        frame = pd.read_csv(io.StringIO(raw), sep=r"\s+", engine="python", header=None)
    if frame.empty:
        raise ValueError(f"{path} contains an empty spectrum table")
    return frame, metadata


def _normalise_spectrum_columns(frame: pd.DataFrame) -> pd.DataFrame:
    clean = frame.copy()
    clean.columns = [str(column).strip() for column in clean.columns]
    lower_to_original = {column.lower(): column for column in clean.columns}

    lambda_col = next((lower_to_original[name] for name in _LAMBDA_ALIASES if name in lower_to_original), None)
    intensity_col = next((lower_to_original[name] for name in _INTENSITY_ALIASES if name in lower_to_original), None)
    if lambda_col is None or intensity_col is None:
        numeric_cols = [
            column for column in clean.columns if pd.to_numeric(clean[column], errors="coerce").notna().any()
        ]
        if len(numeric_cols) < 2:
            raise ValueError("spectrum table requires lambda and intensity columns")
        lambda_col = lambda_col or numeric_cols[0]
        intensity_col = intensity_col or numeric_cols[1]

    renamed = clean.rename(columns={lambda_col: "lambda", intensity_col: "intensity"})
    renamed["lambda"] = pd.to_numeric(renamed["lambda"], errors="coerce")
    renamed["intensity"] = pd.to_numeric(renamed["intensity"], errors="coerce")
    renamed = renamed.dropna(subset=["lambda", "intensity"]).reset_index(drop=True)
    if renamed.empty:
        raise ValueError("spectrum table has no numeric lambda/intensity rows")
    return renamed


def _typed_spectrum_meta(mapping: dict[str, Any]) -> Spectrum.Meta:
    payload = {field: mapping.get(field) for field in _SPECTRUM_META_FIELDS if mapping.get(field) not in (None, "")}
    # Common JCAMP key aliases.
    if "xunits" in mapping and "lambda_unit" not in payload:
        payload["lambda_unit"] = mapping["xunits"]
    if "yunits" in mapping and "intensity_unit" not in payload:
        payload["intensity_unit"] = mapping["yunits"]
    return cast(Spectrum.Meta, Spectrum.Meta.model_validate(payload))


def _typed_dataset_meta(mapping: dict[str, Any]) -> SpectralDataset.Meta:
    payload = {field: mapping.get(field) for field in _DATASET_META_FIELDS if mapping.get(field) not in (None, "")}
    return cast(SpectralDataset.Meta, SpectralDataset.Meta.model_validate(payload))


def _spectrum_frame(spectrum: Spectrum) -> pd.DataFrame:
    data = spectrum.get_in_memory_data()
    if isinstance(data, pa.Table):
        frame = data.to_pandas()
    elif isinstance(data, pd.DataFrame):
        frame = data.copy()
    elif isinstance(data, (dict, list)):
        frame = pd.DataFrame(data)
    else:
        frame = pd.DataFrame(data)
    return _normalise_spectrum_columns(frame)[["lambda", "intensity"]]


def _new_spectrum(
    frame: pd.DataFrame,
    *,
    meta: Spectrum.Meta | None = None,
    user: dict[str, Any] | None = None,
) -> Spectrum:
    clean = _normalise_spectrum_columns(frame)[["lambda", "intensity"]]
    return Spectrum(
        length=len(clean),
        meta=meta if meta is not None else Spectrum.Meta(),
        user=_json_safe(user or {}),
        data=pa.Table.from_pandas(clean, preserve_index=False),
    )


def _stable_spectrum_id(path: Path, ordinal: int, frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    digest.update(path.name.encode("utf-8"))
    digest.update(str(ordinal).encode("utf-8"))
    digest.update(frame[["lambda", "intensity"]].to_csv(index=False).encode("utf-8"))
    return f"spectrum-{digest.hexdigest()[:12]}"


def _with_identity(spectrum: Spectrum, *, path: Path, ordinal: int) -> Spectrum:
    frame = _spectrum_frame(spectrum)
    user = dict(spectrum.user)
    if not user.get("spectrum_id"):
        user["spectrum_id"] = _stable_spectrum_id(path, ordinal, frame)
    user.setdefault("source_file", path.name)
    user.setdefault("filename", path.name)
    return _new_spectrum(
        frame, meta=spectrum.meta if isinstance(spectrum.meta, Spectrum.Meta) else Spectrum.Meta(), user=user
    )


def _spectra_from_frame(frame: pd.DataFrame, metadata: dict[str, Any]) -> list[Spectrum]:
    normal = _normalise_spectrum_columns(frame)
    typed_meta = _typed_spectrum_meta(metadata)
    if "spectrum_id" in normal.columns:
        spectra = []
        for spectrum_id, group in normal.groupby("spectrum_id", sort=False):
            user = {key: value for key, value in metadata.items() if key not in _SPECTRUM_META_FIELDS}
            user["spectrum_id"] = str(spectrum_id)
            spectra.append(_new_spectrum(group[["lambda", "intensity"]], meta=typed_meta, user=user))
        return spectra
    user = {key: value for key, value in metadata.items() if key not in _SPECTRUM_META_FIELDS}
    if metadata.get("spectrum_id"):
        user["spectrum_id"] = str(metadata["spectrum_id"])
    return [_new_spectrum(normal[["lambda", "intensity"]], meta=typed_meta, user=user)]


def _dataset_from_frames(
    index_frame: pd.DataFrame,
    spectra_frame: pd.DataFrame,
    *,
    meta: SpectralDataset.Meta | None = None,
    user: dict[str, Any] | None = None,
) -> SpectralDataset:
    index_clean = index_frame.copy()
    spectra_clean = spectra_frame.copy()
    index_clean["spectrum_id"] = index_clean["spectrum_id"].astype(str)
    spectra_clean["spectrum_id"] = spectra_clean["spectrum_id"].astype(str)
    index: DataFrame = dataframe_from_pandas(index_clean)
    spectra: DataFrame = dataframe_from_pandas(spectra_clean)
    return SpectralDataset(
        slots={"index": index, "spectra": spectra},
        meta=meta if meta is not None else SpectralDataset.Meta(),
        user=_json_safe(user or {}),
    )


def _dataset_frames(dataset: SpectralDataset) -> tuple[pd.DataFrame, pd.DataFrame]:
    return to_pandas_frame(dataset.index), to_pandas_frame(dataset.spectra)


def _dataset_meta(dataset: SpectralDataset) -> SpectralDataset.Meta:
    return dataset.meta if isinstance(dataset.meta, SpectralDataset.Meta) else SpectralDataset.Meta()


def _write_metadata_comments(handle: Any, metadata: dict[str, Any]) -> None:
    for key, value in metadata.items():
        if value not in (None, ""):
            handle.write(f"# {key}: {value}\n")


class LoadSpectrum(IOBlock):
    """Load one or more spectra from a file, folder, or glob path."""

    type_name: ClassVar[str] = "spectroscopy.load_spectrum"
    direction: ClassVar[str] = "input"
    name: ClassVar[str] = "Load Spectrum"
    description: ClassVar[str] = "Load ordinary 1-D spectra into Collection[Spectrum]."
    subcategory: ClassVar[str] = "io"
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = _spectrum_load_capabilities()
    supported_extensions: ClassVar[dict[str, str]] = {
        extension: capability.format_id for capability in format_capabilities for extension in capability.extensions
    }
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="spectra", accepted_types=[Spectrum], is_collection=True),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {"type": ["string", "array"], "items": {"type": "string"}, "ui_widget": "file_browser"},
            "format": {"type": ["string", "null"], "default": None},
            "capability_id": {"type": ["string", "null"], "default": None},
        },
        "required": ["path"],
    }

    def load(self, config: BlockConfig, output_dir: str = "") -> Collection:
        paths = _resolve_paths(config.get("path"), self.format_capabilities, config)
        loaded: list[DataObject] = []
        ordinal = 0
        for path in paths:
            capability = _match_capability(self.format_capabilities, path, config)
            handler = getattr(self, capability.handler)
            spectra = handler(path, config)
            if isinstance(spectra, Spectrum):
                spectra = [spectra]
            for spectrum in spectra:
                loaded.append(_with_identity(spectrum, path=path, ordinal=ordinal))
                ordinal += 1
        return Collection(items=loaded, item_type=Spectrum)

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError("LoadSpectrum is input-only; use SaveSpectrum to write spectra.")

    def _load_delimited_text(self, path: Path, config: BlockConfig) -> list[Spectrum]:
        frame, metadata = _read_delimited_frame(path)
        return _spectra_from_frame(frame, metadata)

    def _load_spectrum_xlsx(self, path: Path, config: BlockConfig) -> list[Spectrum]:
        sheet_name = config.get("sheet_name", 0)
        frame = pd.read_excel(path, sheet_name=sheet_name)
        metadata: dict[str, Any] = {}
        try:
            meta_frame = pd.read_excel(path, sheet_name="meta")
            if {"key", "value"} <= set(meta_frame.columns):
                metadata = dict(zip(meta_frame["key"].astype(str), meta_frame["value"], strict=False))
        except ValueError:
            metadata = {}
        return _spectra_from_frame(frame, metadata)

    def _load_spectrum_json(self, path: Path, config: BlockConfig) -> list[Spectrum]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = _typed_spectrum_meta(dict(payload.get("meta") or {}))
        user = dict(payload.get("user") or {})
        data = payload.get("data") or {}
        frame = pd.DataFrame(data)
        return [_new_spectrum(frame, meta=meta, user=user)]

    def _load_jcamp_dx(self, path: Path, config: BlockConfig) -> list[Spectrum]:
        lines = path.read_text(encoding="utf-8").splitlines()
        metadata, data_lines = _metadata_from_comments(lines)
        rows: list[tuple[float, float]] = []
        for line in data_lines:
            numbers = [float(value) for value in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", line)]
            if len(numbers) >= 2:
                rows.append((numbers[0], numbers[1]))
        if not rows:
            frame, metadata = _read_delimited_frame(path)
            return _spectra_from_frame(frame, metadata)
        return _spectra_from_frame(pd.DataFrame(rows, columns=["lambda", "intensity"]), metadata)

    def _load_spc(self, path: Path, config: BlockConfig) -> list[Spectrum]:
        return self._load_vendor_text(path, config)

    def _load_thermo_omnic_spa(self, path: Path, config: BlockConfig) -> list[Spectrum]:
        return self._load_vendor_text(path, config)

    def _load_bruker_opus(self, path: Path, config: BlockConfig) -> list[Spectrum]:
        return self._load_vendor_text(path, config)

    def _load_horiba_labspec(self, path: Path, config: BlockConfig) -> list[Spectrum]:
        return self._load_vendor_text(path, config)

    def _load_renishaw_wdf(self, path: Path, config: BlockConfig) -> list[Spectrum]:
        return self._load_vendor_text(path, config)

    def _load_andor_solis(self, path: Path, config: BlockConfig) -> list[Spectrum]:
        return self._load_vendor_text(path, config)

    def _load_princeton_spe(self, path: Path, config: BlockConfig) -> list[Spectrum]:
        return self._load_vendor_text(path, config)

    def _load_vendor_text(self, path: Path, config: BlockConfig) -> list[Spectrum]:
        frame, metadata = _read_delimited_frame(path)
        return _spectra_from_frame(frame, metadata)


class SaveSpectrum(IOBlock):
    """Save a Spectrum or Collection[Spectrum]."""

    type_name: ClassVar[str] = "spectroscopy.save_spectrum"
    direction: ClassVar[str] = "output"
    name: ClassVar[str] = "Save Spectrum"
    description: ClassVar[str] = "Persist spectra to spectroscopy boundary formats."
    subcategory: ClassVar[str] = "io"
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = _spectrum_save_capabilities()
    supported_extensions: ClassVar[dict[str, str]] = {
        extension: capability.format_id for capability in format_capabilities for extension in capability.extensions
    }
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="spectra", accepted_types=[Spectrum], is_collection=True, required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="path", accepted_types=[Text])]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "ui_widget": "file_browser"},
            "format": {"type": ["string", "null"], "default": None},
            "capability_id": {"type": ["string", "null"], "default": None},
        },
        "required": ["path"],
    }

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError("SaveSpectrum is output-only; use LoadSpectrum to read spectra.")

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        spectra = list(obj) if isinstance(obj, Collection) else [obj]
        if not all(isinstance(item, Spectrum) for item in spectra):
            raise TypeError("SaveSpectrum requires Spectrum inputs")
        target = Path(str(config.get("path")))
        capability = _match_capability(self.format_capabilities, target, config)
        paths = self._target_paths(target, capability, [item for item in spectra if isinstance(item, Spectrum)])
        for spectrum, path in zip(spectra, paths, strict=True):
            path.parent.mkdir(parents=True, exist_ok=True)
            getattr(self, capability.handler)(spectrum, path, config)

    def _target_paths(self, target: Path, capability: FormatCapability, spectra: list[Spectrum]) -> list[Path]:
        if len(spectra) == 1 and target.suffix:
            return [target]
        target.mkdir(parents=True, exist_ok=True)
        extension = capability.extensions[0]
        paths = []
        for index, spectrum in enumerate(spectra):
            spectrum_id = str(spectrum.user.get("spectrum_id") or f"spectrum-{index + 1}")
            safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", spectrum_id)
            paths.append(target / f"{safe_id}{extension}")
        return paths

    def _save_delimited_text(self, spectrum: Spectrum, path: Path, config: BlockConfig) -> None:
        sep = "\t" if path.suffix.lower() in {".tsv", ".txt"} else ","
        with path.open("w", encoding="utf-8", newline="") as handle:
            metadata = dict(spectrum.user)
            metadata.update(spectrum.meta.model_dump() if spectrum.meta is not None else {})
            _write_metadata_comments(handle, metadata)
            _spectrum_frame(spectrum).to_csv(handle, index=False, sep=sep)

    def _save_spectrum_xlsx(self, spectrum: Spectrum, path: Path, config: BlockConfig) -> None:
        metadata = dict(spectrum.user)
        metadata.update(spectrum.meta.model_dump() if spectrum.meta is not None else {})
        with pd.ExcelWriter(path) as writer:
            _spectrum_frame(spectrum).to_excel(writer, sheet_name="data", index=False)
            pd.DataFrame({"key": list(metadata), "value": list(metadata.values())}).to_excel(
                writer,
                sheet_name="meta",
                index=False,
            )

    def _save_spectrum_json(self, spectrum: Spectrum, path: Path, config: BlockConfig) -> None:
        payload = {
            "type": "Spectrum",
            "schema_version": 1,
            "meta": spectrum.meta.model_dump() if spectrum.meta is not None else {},
            "user": dict(spectrum.user),
            "data": _spectrum_frame(spectrum).to_dict(orient="records"),
        }
        path.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _save_jcamp_dx(self, spectrum: Spectrum, path: Path, config: BlockConfig) -> None:
        meta = spectrum.meta if isinstance(spectrum.meta, Spectrum.Meta) else Spectrum.Meta()
        with path.open("w", encoding="utf-8") as handle:
            handle.write(f"##TITLE={spectrum.user.get('spectrum_id', path.stem)}\n")
            if meta.lambda_unit:
                handle.write(f"##XUNITS={meta.lambda_unit}\n")
            if meta.intensity_unit:
                handle.write(f"##YUNITS={meta.intensity_unit}\n")
            handle.write("##XYDATA=(X++(Y..Y))\n")
            for row in _spectrum_frame(spectrum).itertuples(index=False):
                handle.write(f"{row[0]} {row[1]}\n")
            handle.write("##END=\n")

    def _save_spc(self, spectrum: Spectrum, path: Path, config: BlockConfig) -> None:
        self._save_delimited_text(spectrum, path, config)


class LoadSpectralDataset(IOBlock):
    """Load a SpectralDataset from a canonical two-table representation."""

    type_name: ClassVar[str] = "spectroscopy.load_spectral_dataset"
    direction: ClassVar[str] = "input"
    name: ClassVar[str] = "Load Spectral Dataset"
    description: ClassVar[str] = "Load spectral datasets with index and spectra table slots."
    subcategory: ClassVar[str] = "io"
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = _dataset_load_capabilities()
    supported_extensions: ClassVar[dict[str, str]] = {
        extension: capability.format_id for capability in format_capabilities for extension in capability.extensions
    }
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="dataset", accepted_types=[SpectralDataset]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {"type": ["string", "null"], "default": None, "ui_widget": "file_browser"},
            "index_path": {"type": ["string", "null"], "default": None},
            "spectra_path": {"type": ["string", "null"], "default": None},
            "format": {"type": ["string", "null"], "default": None},
            "capability_id": {"type": ["string", "null"], "default": None},
        },
    }

    def load(self, config: BlockConfig, output_dir: str = "") -> SpectralDataset:
        if config.get("index_path") and config.get("spectra_path"):
            return self._load_two_table_paths(config)
        raw_path = config.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError("LoadSpectralDataset requires path or index_path/spectra_path")
        path = Path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"source file not found: {path}")
        capability = _match_capability(self.format_capabilities, path, config)
        dataset = getattr(self, capability.handler)(path, config)
        if not isinstance(dataset, SpectralDataset):
            raise TypeError(f"{capability.handler} returned {type(dataset).__name__}, expected SpectralDataset")
        return dataset

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError("LoadSpectralDataset is input-only; use SaveSpectralDataset to write datasets.")

    def _load_two_table_paths(self, config: BlockConfig) -> SpectralDataset:
        index_path = Path(str(config.get("index_path")))
        spectra_path = Path(str(config.get("spectra_path")))
        index_frame = pd.read_csv(index_path)
        spectra_frame = pd.read_csv(spectra_path)
        meta = SpectralDataset.Meta(dataset_name=config.get("dataset_name"))
        return _dataset_from_frames(index_frame, spectra_frame, meta=meta, user={"source_file": index_path.name})

    def _load_manifest_json(self, path: Path, config: BlockConfig) -> SpectralDataset:
        payload = json.loads(path.read_text(encoding="utf-8"))
        slots = payload.get("slots") or {}
        if not {"index", "spectra"} <= set(slots):
            raise ValueError("SpectralDataset manifest requires index and spectra slots")
        index_path = path.parent / str(slots["index"])
        spectra_path = path.parent / str(slots["spectra"])
        index_frame = pd.read_csv(index_path)
        spectra_frame = pd.read_csv(spectra_path)
        meta = _typed_dataset_meta(dict(payload.get("meta") or {}))
        user = dict(payload.get("user") or {})
        user.setdefault("source_file", path.name)
        return _dataset_from_frames(index_frame, spectra_frame, meta=meta, user=user)

    def _load_dataset_xlsx(self, path: Path, config: BlockConfig) -> SpectralDataset:
        index_frame = pd.read_excel(path, sheet_name="index")
        spectra_frame = pd.read_excel(path, sheet_name="spectra")
        metadata: dict[str, Any] = {}
        try:
            meta_frame = pd.read_excel(path, sheet_name="meta")
            if {"key", "value"} <= set(meta_frame.columns):
                metadata = dict(zip(meta_frame["key"].astype(str), meta_frame["value"], strict=False))
        except ValueError:
            metadata = {}
        metadata.setdefault("dataset_name", path.stem)
        return _dataset_from_frames(
            index_frame, spectra_frame, meta=_typed_dataset_meta(metadata), user={"source_file": path.name}
        )

    def _load_spc_dataset(self, path: Path, config: BlockConfig) -> SpectralDataset:
        return self._load_pseudo_dataset(path, config)

    def _load_thermo_omnic_spg(self, path: Path, config: BlockConfig) -> SpectralDataset:
        return self._load_pseudo_dataset(path, config)

    def _load_renishaw_wdf_dataset(self, path: Path, config: BlockConfig) -> SpectralDataset:
        return self._load_pseudo_dataset(path, config)

    def _load_bruker_opus_dataset(self, path: Path, config: BlockConfig) -> SpectralDataset:
        return self._load_pseudo_dataset(path, config)

    def _load_horiba_labspec_dataset(self, path: Path, config: BlockConfig) -> SpectralDataset:
        return self._load_pseudo_dataset(path, config)

    def _load_witec_project(self, path: Path, config: BlockConfig) -> SpectralDataset:
        return self._load_pseudo_dataset(path, config)

    def _load_andor_solis_dataset(self, path: Path, config: BlockConfig) -> SpectralDataset:
        return self._load_pseudo_dataset(path, config)

    def _load_princeton_spe_dataset(self, path: Path, config: BlockConfig) -> SpectralDataset:
        return self._load_pseudo_dataset(path, config)

    def _load_pseudo_dataset(self, path: Path, config: BlockConfig) -> SpectralDataset:
        frame, metadata = _read_delimited_frame(path)
        spectra = _normalise_spectrum_columns(frame)
        if "spectrum_id" not in spectra.columns:
            spectra["spectrum_id"] = _stable_spectrum_id(path, 0, spectra)
        metadata_columns = [
            column
            for column in spectra.columns
            if column not in {"lambda", "intensity"} and not column.startswith("Unnamed")
        ]
        if "spectrum_id" not in metadata_columns:
            metadata_columns.insert(0, "spectrum_id")
        index = spectra[metadata_columns].drop_duplicates(subset=["spectrum_id"]).reset_index(drop=True)
        spectra = spectra[["spectrum_id", "lambda", "intensity"]].reset_index(drop=True)
        metadata.setdefault("dataset_name", path.stem)
        return _dataset_from_frames(index, spectra, meta=_typed_dataset_meta(metadata), user={"source_file": path.name})


class SaveSpectralDataset(IOBlock):
    """Save a SpectralDataset in canonical supported formats."""

    type_name: ClassVar[str] = "spectroscopy.save_spectral_dataset"
    direction: ClassVar[str] = "output"
    name: ClassVar[str] = "Save Spectral Dataset"
    description: ClassVar[str] = "Persist SpectralDataset index and spectra slots."
    subcategory: ClassVar[str] = "io"
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = _dataset_save_capabilities()
    supported_extensions: ClassVar[dict[str, str]] = {
        extension: capability.format_id for capability in format_capabilities for extension in capability.extensions
    }
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="dataset", accepted_types=[SpectralDataset], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="path", accepted_types=[Text])]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "ui_widget": "file_browser"},
            "format": {"type": ["string", "null"], "default": None},
            "capability_id": {"type": ["string", "null"], "default": None},
        },
        "required": ["path"],
    }

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError("SaveSpectralDataset is output-only; use LoadSpectralDataset to read datasets.")

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        dataset = self._unwrap_dataset(obj)
        target = Path(str(config.get("path")))
        capability = _match_capability(self.format_capabilities, target, config)
        target.parent.mkdir(parents=True, exist_ok=True)
        getattr(self, capability.handler)(dataset, target, config)

    def _unwrap_dataset(self, obj: DataObject | Collection) -> SpectralDataset:
        item = obj[0] if isinstance(obj, Collection) else obj
        if not isinstance(item, SpectralDataset):
            raise TypeError(f"SaveSpectralDataset requires SpectralDataset, got {type(item).__name__}")
        return item

    def _save_manifest_json(self, dataset: SpectralDataset, path: Path, config: BlockConfig) -> None:
        index_frame, spectra_frame = _dataset_frames(dataset)
        index_path = path.with_suffix("")
        index_file = index_path.with_name(f"{index_path.name}.index.csv")
        spectra_file = index_path.with_name(f"{index_path.name}.spectra.csv")
        index_frame.to_csv(index_file, index=False)
        spectra_frame.to_csv(spectra_file, index=False)
        payload = {
            "type": "SpectralDataset",
            "schema_version": 1,
            "slots": {"index": index_file.name, "spectra": spectra_file.name},
            "meta": dataset.meta.model_dump() if dataset.meta is not None else {},
            "user": dict(dataset.user),
        }
        path.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _save_dataset_xlsx(self, dataset: SpectralDataset, path: Path, config: BlockConfig) -> None:
        metadata = dict(dataset.user)
        metadata.update(dataset.meta.model_dump() if dataset.meta is not None else {})
        with pd.ExcelWriter(path) as writer:
            index_frame, spectra_frame = _dataset_frames(dataset)
            index_frame.to_excel(writer, sheet_name="index", index=False)
            spectra_frame.to_excel(writer, sheet_name="spectra", index=False)
            pd.DataFrame({"key": list(metadata), "value": list(metadata.values())}).to_excel(
                writer,
                sheet_name="meta",
                index=False,
            )

    def _save_spc_dataset(self, dataset: SpectralDataset, path: Path, config: BlockConfig) -> None:
        index_frame, spectra_frame = _dataset_frames(dataset)
        merged = spectra_frame.merge(index_frame, on="spectrum_id", how="left", suffixes=("", "_index"))
        merged.to_csv(path, index=False)


class SpectrumToSpectralDataset(ProcessBlock):
    """Convert Collection[Spectrum] plus optional metadata to one SpectralDataset."""

    type_name: ClassVar[str] = "spectroscopy.spectrum_to_spectral_dataset"
    name: ClassVar[str] = "Spectrum To Spectral Dataset"
    description: ClassVar[str] = "Expand spectra into long-form rows and build a dataset index."
    subcategory: ClassVar[str] = "utilities"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="spectra", accepted_types=[Spectrum], is_collection=True, required=True),
        InputPort(name="metadata", accepted_types=[DataFrame], required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="dataset", accepted_types=[SpectralDataset])]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "metadata_join_key": {"type": "string", "default": "spectrum_id"},
            "dataset_name": {"type": ["string", "null"], "default": None},
            "dataset_role": {"type": "string", "default": "experiment"},
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        spectra = list(inputs["spectra"])
        if not spectra:
            raise ValueError("SpectrumToSpectralDataset requires at least one Spectrum")
        index_rows: list[dict[str, Any]] = []
        spectra_rows: list[dict[str, Any]] = []
        for ordinal, item in enumerate(spectra):
            if not isinstance(item, Spectrum):
                raise TypeError("SpectrumToSpectralDataset requires Spectrum inputs")
            frame = _spectrum_frame(item)
            spectrum_id = str(item.user.get("spectrum_id") or f"spectrum-{ordinal + 1}")
            typed_meta = item.meta.model_dump() if item.meta is not None else {}
            row = {"spectrum_id": spectrum_id, **typed_meta, **dict(item.user)}
            row["spectrum_id"] = spectrum_id
            index_rows.append(row)
            for point in frame.to_dict(orient="records"):
                spectra_rows.append({"spectrum_id": spectrum_id, **point})

        index_frame = pd.DataFrame(index_rows)
        metadata_coll = inputs.get("metadata")
        if metadata_coll is not None and len(metadata_coll) > 0:
            metadata = metadata_coll[0]
            if not isinstance(metadata, DataFrame):
                raise TypeError("metadata input must be a DataFrame")
            metadata_frame = to_pandas_frame(metadata)
            join_key = str(config.get("metadata_join_key", "spectrum_id"))
            if join_key not in index_frame.columns or join_key not in metadata_frame.columns:
                raise ValueError(f"metadata join key {join_key!r} must exist in both tables")
            index_frame = index_frame.merge(metadata_frame, on=join_key, how="left", suffixes=("", "_metadata"))

        meta = SpectralDataset.Meta(
            dataset_name=config.get("dataset_name"),
            dataset_role=str(config.get("dataset_role", "experiment")),
        )
        dataset = _dataset_from_frames(index_frame, pd.DataFrame(spectra_rows), meta=meta)
        return {"dataset": Collection(items=[dataset], item_type=SpectralDataset)}


class SpectralDatasetToSpectrum(ProcessBlock):
    """Split one SpectralDataset into Collection[Spectrum]."""

    type_name: ClassVar[str] = "spectroscopy.spectral_dataset_to_spectrum"
    name: ClassVar[str] = "Spectral Dataset To Spectrum"
    description: ClassVar[str] = "Split a dataset by spectrum_id and attach index metadata to each Spectrum."
    subcategory: ClassVar[str] = "utilities"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="dataset", accepted_types=[SpectralDataset], required=True)
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="spectra", accepted_types=[Spectrum], is_collection=True),
    ]

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        dataset = inputs["dataset"][0]
        if not isinstance(dataset, SpectralDataset):
            raise TypeError("SpectralDatasetToSpectrum requires SpectralDataset input")
        index_frame, spectra_frame = _dataset_frames(dataset)
        outputs: list[DataObject] = []
        dataset_meta = dataset.meta if isinstance(dataset.meta, SpectralDataset.Meta) else SpectralDataset.Meta()
        for row in index_frame.to_dict(orient="records"):
            spectrum_id = str(row["spectrum_id"])
            points = spectra_frame[spectra_frame["spectrum_id"].astype(str) == spectrum_id][["lambda", "intensity"]]
            typed = {
                "lambda_unit": row.get("lambda_unit") or dataset_meta.lambda_unit,
                "intensity_unit": row.get("intensity_unit") or dataset_meta.intensity_unit,
                "lambda_kind": row.get("lambda_kind"),
                "modality": row.get("modality") or dataset_meta.modality,
            }
            typed = {key: value for key, value in typed.items() if pd.notna(value)}
            meta = Spectrum.Meta(**typed)
            user = {key: _json_safe(value) for key, value in row.items() if key not in _SPECTRUM_META_FIELDS}
            user["spectrum_id"] = spectrum_id
            outputs.append(_new_spectrum(points, meta=meta, user=user))
        return {"spectra": Collection(items=outputs, item_type=Spectrum)}


class FilterSpectralDataset(ProcessBlock):
    """Filter SpectralDataset index rows and matching spectra rows."""

    type_name: ClassVar[str] = "spectroscopy.filter_spectral_dataset"
    name: ClassVar[str] = "Filter Spectral Dataset"
    description: ClassVar[str] = "Filter dataset rows by metadata predicates."
    subcategory: ClassVar[str] = "utilities"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="dataset", accepted_types=[SpectralDataset], required=True)
    ]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="dataset", accepted_types=[SpectralDataset])]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "filters": {"type": ["object", "array"], "default": {}},
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        dataset = inputs["dataset"][0]
        if not isinstance(dataset, SpectralDataset):
            raise TypeError("FilterSpectralDataset requires SpectralDataset input")
        index_frame, spectra_frame = _dataset_frames(dataset)
        mask = pd.Series(True, index=index_frame.index)
        for predicate in _coerce_predicates(config.get("filters", {})):
            column = predicate["column"]
            if column not in index_frame.columns:
                raise ValueError(f"filter column {column!r} is not present")
            mask &= _apply_predicate(index_frame[column], predicate)
        kept = index_frame[mask].reset_index(drop=True)
        kept_ids = set(kept["spectrum_id"].astype(str))
        spectra = spectra_frame[spectra_frame["spectrum_id"].astype(str).isin(kept_ids)].reset_index(drop=True)
        user = dict(dataset.user)
        user["filtered"] = True
        filtered = _dataset_from_frames(kept, spectra, meta=_dataset_meta(dataset), user=user)
        return {"dataset": Collection(items=[filtered], item_type=SpectralDataset)}


def _coerce_predicates(raw: Any) -> list[dict[str, Any]]:
    if raw in (None, {}, []):
        return []
    if isinstance(raw, dict):
        if "column" in raw:
            return [raw]
        return [{"column": key, "op": "eq", "value": value} for key, value in raw.items()]
    if isinstance(raw, list):
        return [dict(item) for item in raw]
    raise ValueError("filters must be a dict or list of predicate dicts")


def _apply_predicate(series: pd.Series, predicate: dict[str, Any]) -> pd.Series:
    op = str(predicate.get("op", "eq"))
    value = predicate.get("value")
    if op == "eq":
        return series == value
    if op == "ne":
        return series != value
    if op == "in":
        return series.isin(value if isinstance(value, list) else [value])
    if op == "not_in":
        return ~series.isin(value if isinstance(value, list) else [value])
    if op == "contains":
        return series.astype(str).str.contains(str(value), regex=False, na=False)
    if op in {"gt", "ge", "lt", "le"}:
        if value is None:
            raise ValueError(f"filter op {op!r} requires a value")
        numeric = pd.to_numeric(series, errors="coerce")
        target = float(value)
        if op == "gt":
            return numeric > target
        if op == "ge":
            return numeric >= target
        if op == "lt":
            return numeric < target
        return numeric <= target
    raise ValueError(f"unsupported filter op {op!r}")


class MergeSpectralDataset(ProcessBlock):
    """Merge two or more SpectralDataset values."""

    type_name: ClassVar[str] = "spectroscopy.merge_spectral_dataset"
    name: ClassVar[str] = "Merge Spectral Dataset"
    description: ClassVar[str] = "Append compatible spectral datasets."
    subcategory: ClassVar[str] = "utilities"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="datasets", accepted_types=[SpectralDataset], is_collection=True, required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="dataset", accepted_types=[SpectralDataset])]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "duplicate_id_policy": {"type": "string", "enum": ["error", "prefix", "remap"], "default": "error"},
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        datasets = list(inputs["datasets"])
        if len(datasets) < 2:
            raise ValueError("MergeSpectralDataset requires at least two datasets")
        if not all(isinstance(item, SpectralDataset) for item in datasets):
            raise TypeError("MergeSpectralDataset requires SpectralDataset inputs")

        first_meta = datasets[0].meta if isinstance(datasets[0].meta, SpectralDataset.Meta) else SpectralDataset.Meta()
        index_frames: list[pd.DataFrame] = []
        spectra_frames: list[pd.DataFrame] = []
        policy = str(config.get("duplicate_id_policy", "error"))
        seen: set[str] = set()
        for dataset_index, dataset in enumerate(datasets):
            assert isinstance(dataset, SpectralDataset)
            meta = dataset.meta if isinstance(dataset.meta, SpectralDataset.Meta) else SpectralDataset.Meta()
            if (meta.lambda_unit, meta.intensity_unit, meta.modality) != (
                first_meta.lambda_unit,
                first_meta.intensity_unit,
                first_meta.modality,
            ):
                raise ValueError("MergeSpectralDataset refuses mixed units or modalities")
            index_frame, spectra_frame = _dataset_frames(dataset)
            duplicates = set(index_frame["spectrum_id"].astype(str)) & seen
            if duplicates and policy == "error":
                raise ValueError(f"duplicate spectrum_id values: {sorted(duplicates)}")
            if duplicates and policy in {"prefix", "remap"}:
                index_frame, spectra_frame = _rename_dataset_ids(index_frame, spectra_frame, dataset_index, policy)
            seen.update(index_frame["spectrum_id"].astype(str))
            index_frames.append(index_frame)
            spectra_frames.append(spectra_frame)
        merged = _dataset_from_frames(
            pd.concat(index_frames, ignore_index=True),
            pd.concat(spectra_frames, ignore_index=True),
            meta=first_meta,
        )
        return {"dataset": Collection(items=[merged], item_type=SpectralDataset)}


def _rename_dataset_ids(
    index_frame: pd.DataFrame,
    spectra_frame: pd.DataFrame,
    dataset_index: int,
    policy: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    mapping: dict[str, str] = {}
    for ordinal, value in enumerate(index_frame["spectrum_id"].astype(str)):
        if policy == "prefix":
            mapping[value] = f"ds{dataset_index + 1}_{value}"
        else:
            mapping[value] = f"{value}_{dataset_index + 1}_{ordinal + 1}"
    index_copy = index_frame.copy()
    spectra_copy = spectra_frame.copy()
    index_copy["spectrum_id"] = index_copy["spectrum_id"].astype(str).map(mapping)
    spectra_copy["spectrum_id"] = spectra_copy["spectrum_id"].astype(str).map(mapping)
    return index_copy, spectra_copy


class AttachFeaturesToSpectralDataset(ProcessBlock):
    """Join flat feature rows onto SpectralDataset.index."""

    type_name: ClassVar[str] = "spectroscopy.attach_features_to_spectral_dataset"
    name: ClassVar[str] = "Attach Features To Spectral Dataset"
    description: ClassVar[str] = "Join feature columns onto dataset index metadata."
    subcategory: ClassVar[str] = "utilities"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="dataset", accepted_types=[SpectralDataset], required=True),
        InputPort(name="features", accepted_types=[DataFrame], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="dataset", accepted_types=[SpectralDataset])]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "join_key": {"type": "string", "default": "spectrum_id"},
            "conflict_policy": {"type": "string", "enum": ["error", "overwrite", "suffix"], "default": "error"},
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        dataset = inputs["dataset"][0]
        features = inputs["features"][0]
        if not isinstance(dataset, SpectralDataset) or not isinstance(features, DataFrame):
            raise TypeError("AttachFeaturesToSpectralDataset requires SpectralDataset and DataFrame inputs")
        join_key = str(config.get("join_key", "spectrum_id"))
        conflict_policy = str(config.get("conflict_policy", "error"))
        index_frame, spectra_frame = _dataset_frames(dataset)
        feature_frame = to_pandas_frame(features)
        if join_key not in index_frame.columns or join_key not in feature_frame.columns:
            raise ValueError(f"join key {join_key!r} must exist in dataset index and feature table")
        conflicts = (set(index_frame.columns) & set(feature_frame.columns)) - {join_key}
        if conflicts and conflict_policy == "error":
            raise ValueError(f"feature columns conflict with dataset index: {sorted(conflicts)}")
        if conflicts and conflict_policy == "overwrite":
            index_frame = index_frame.drop(columns=sorted(conflicts))
        suffixes = ("", "_feature") if conflict_policy == "suffix" else ("", "")
        joined = index_frame.merge(feature_frame, on=join_key, how="left", suffixes=suffixes)
        attached = _dataset_from_frames(joined, spectra_frame, meta=_dataset_meta(dataset), user=dict(dataset.user))
        return {"dataset": Collection(items=[attached], item_type=SpectralDataset)}


__all__ = [
    "AttachFeaturesToSpectralDataset",
    "FilterSpectralDataset",
    "LoadSpectralDataset",
    "LoadSpectrum",
    "MergeSpectralDataset",
    "SaveSpectralDataset",
    "SaveSpectrum",
    "SpectralDatasetToSpectrum",
    "SpectrumToSpectralDataset",
]
