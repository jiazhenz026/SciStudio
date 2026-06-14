"""Spectroscopy utility blocks (FR-032..FR-052).

Nine utility blocks that move data between files, ``Collection[Spectrum]``, and
``SpectralDataset`` values without performing scientific processing (FR-052):

- Four ADR-043 IO blocks: :class:`LoadSpectrum`, :class:`SaveSpectrum`,
  :class:`LoadSpectralDataset`, :class:`SaveSpectralDataset`. Their per-format
  handler methods delegate to :mod:`..io_handlers`.
- Five conversion/transport blocks: :class:`SpectrumToSpectralDataset`,
  :class:`SpectralDatasetToSpectrum`, :class:`FilterSpectralDataset`,
  :class:`MergeSpectralDataset`, :class:`AttachFeaturesToSpectralDataset`.

Executable bodies are skeleton stubs that raise ``NotImplementedError``; the
ports, config schemas, and capability records are the real stable contract.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scistudio.blocks.io.io_block import IOBlock
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy.blocks.io_handlers import (
    dataset_formats,
    spectrum_formats,
)
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

_PKG = "scistudio-blocks-spectroscopy"

# Typed-meta field tuples reused across capability records.
_SPECTRUM_META_FIELDS = ("lambda_unit", "intensity_unit", "lambda_kind", "modality")
_DATASET_META_FIELDS = (
    "dataset_name",
    "dataset_role",
    "lambda_unit",
    "intensity_unit",
    "modality",
    "schema_version",
)
_DATASET_VENDOR_META_FIELDS = ("dataset_role", "lambda_unit", "intensity_unit", "modality")

# Shared file-path config schema fragment for IO blocks.
_PATH_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": ["string", "array"],
            "items": {"type": "string"},
            "title": "Path",
            "ui_widget": "file_browser",
            "ui_priority": 0,
        },
        "capability_id": {
            "type": "string",
            "title": "Format capability id",
            "description": "Optional explicit FormatCapability.id (ADR-043 selection).",
        },
    },
    "required": ["path"],
}


def _resolve_dataset_io_capability(
    block_instance: IOBlock,
    config: BlockConfig,
    path: Any,
    *,
    direction: str,
    block: str,
) -> FormatCapability:
    """Resolve the ADR-043 ``FormatCapability`` for a SpectralDataset IO call.

    Selection rules (FR-143): an explicit ``config['capability_id']`` wins; else
    a unique extension match in the correct ``direction`` is used; unresolved
    ambiguity or an unsupported extension fails rather than falling back to
    registration order. Used only by ``LoadSpectralDataset.load`` and
    ``SaveSpectralDataset.save``.
    """
    from pathlib import Path

    candidates = [c for c in block_instance.get_format_capabilities() if c.direction == direction]

    capability_id = config.get("capability_id")
    if capability_id:
        for capability in candidates:
            if capability.id == capability_id:
                return capability
        raise ValueError(f"{block}: capability_id {capability_id!r} not found among {direction} capabilities")

    fmt = block_instance._detect_format(Path(str(path)))
    if fmt is None:
        raise ValueError(
            f"{block}: unsupported extension for {Path(str(path)).name!r}; "
            f"declared extensions: {sorted(block_instance.supported_extensions)}"
        )
    matches = [c for c in candidates if c.format_id == fmt]
    if not matches:
        raise ValueError(f"{block}: no {direction} capability declared for format {fmt!r}")
    if len(matches) > 1:
        raise ValueError(
            f"{block}: ambiguous {direction} capability for format {fmt!r}; pass an explicit capability_id (ADR-043)"
        )
    return matches[0]


# ==========================================================================
# LoadSpectrum (FR-034..FR-036, FR-132..FR-134)
# ==========================================================================


class LoadSpectrum(IOBlock):
    """Load one or more files into a ``Collection[Spectrum]`` (FR-034)."""

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "spectroscopy.load_spectrum"
    name: ClassVar[str] = "Load Spectrum"
    description: ClassVar[str] = "Load one or more spectra from files into a Collection[Spectrum]."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "io"

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="spectra",
            accepted_types=[Spectrum],
            is_collection=True,
            description="Loaded spectra.",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = _PATH_CONFIG_SCHEMA

    supported_extensions: ClassVar[dict[str, str]] = {
        ".txt": "txt",
        ".csv": "csv",
        ".tsv": "tsv",
        ".xlsx": "xlsx",
        ".xls": "xlsx",
        ".spectrum.json": "spectrum_json",
        ".jdx": "jcamp_dx",
        ".dx": "jcamp_dx",
        ".jcamp": "jcamp_dx",
        ".spc": "spc",
        ".spa": "thermo_omnic_spa",
        ".opus": "bruker_opus",
        ".l6s": "horiba_labspec",
        ".l5s": "horiba_labspec",
        ".ngs": "horiba_labspec",
        ".xml": "horiba_labspec",
        ".wdf": "renishaw_wdf",
        ".sif": "andor_solis",
        ".fits": "andor_solis",
        ".fit": "andor_solis",
        ".asc": "andor_solis",
        ".spe": "princeton_spe",
    }

    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id=f"{_PKG}.spectrum.txt.load",
            direction="load",
            data_type=Spectrum,
            format_id="txt",
            extensions=(".txt",),
            label="Text spectrum",
            block_type="LoadSpectrum",
            handler="_load_delimited_text",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectrum.txt",
            metadata_fidelity=MetadataFidelity(level="pixel_only"),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.csv.load",
            direction="load",
            data_type=Spectrum,
            format_id="csv",
            extensions=(".csv",),
            label="CSV spectrum",
            block_type="LoadSpectrum",
            handler="_load_delimited_text",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectrum.csv",
            metadata_fidelity=MetadataFidelity(level="pixel_only"),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.tsv.load",
            direction="load",
            data_type=Spectrum,
            format_id="tsv",
            extensions=(".tsv",),
            label="TSV spectrum",
            block_type="LoadSpectrum",
            handler="_load_delimited_text",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectrum.tsv",
            metadata_fidelity=MetadataFidelity(level="pixel_only"),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.xlsx.load",
            direction="load",
            data_type=Spectrum,
            format_id="xlsx",
            extensions=(".xlsx", ".xls"),
            label="Excel spectrum workbook",
            block_type="LoadSpectrum",
            handler="_load_spectrum_xlsx",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectrum.xlsx",
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_SPECTRUM_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.spectrum_json.load",
            direction="load",
            data_type=Spectrum,
            format_id="spectrum_json",
            extensions=(".spectrum.json",),
            label="Native Spectrum JSON",
            block_type="LoadSpectrum",
            handler="_load_spectrum_json",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectrum.spectrum_json",
            metadata_fidelity=MetadataFidelity(level="lossless", typed_meta_reads=_SPECTRUM_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.jcamp_dx.load",
            direction="load",
            data_type=Spectrum,
            format_id="jcamp_dx",
            extensions=(".jdx", ".dx", ".jcamp"),
            label="JCAMP-DX spectrum",
            block_type="LoadSpectrum",
            handler="_load_jcamp_dx",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectrum.jcamp_dx",
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_SPECTRUM_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.spc.load",
            direction="load",
            data_type=Spectrum,
            format_id="spc",
            extensions=(".spc",),
            label="SPC spectrum",
            block_type="LoadSpectrum",
            handler="_load_spc",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectrum.spc",
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_SPECTRUM_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.thermo_omnic_spa.load",
            direction="load",
            data_type=Spectrum,
            format_id="thermo_omnic_spa",
            extensions=(".spa",),
            label="Thermo OMNIC SPA spectrum",
            block_type="LoadSpectrum",
            handler="_load_thermo_omnic_spa",
            is_default=True,
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_SPECTRUM_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.bruker_opus.load",
            direction="load",
            data_type=Spectrum,
            format_id="bruker_opus",
            extensions=(".opus",),
            label="Bruker OPUS spectrum",
            block_type="LoadSpectrum",
            handler="_load_bruker_opus",
            is_default=True,
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_SPECTRUM_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.horiba_labspec.load",
            direction="load",
            data_type=Spectrum,
            format_id="horiba_labspec",
            extensions=(".l6s", ".l5s", ".ngs", ".xml"),
            label="HORIBA LabSpec spectrum",
            block_type="LoadSpectrum",
            handler="_load_horiba_labspec",
            is_default=True,
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_SPECTRUM_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.renishaw_wdf.load",
            direction="load",
            data_type=Spectrum,
            format_id="renishaw_wdf",
            extensions=(".wdf",),
            label="Renishaw WiRE spectrum",
            block_type="LoadSpectrum",
            handler="_load_renishaw_wdf",
            is_default=True,
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_SPECTRUM_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.andor_solis.load",
            direction="load",
            data_type=Spectrum,
            format_id="andor_solis",
            extensions=(".sif", ".fits", ".fit", ".asc"),
            label="Andor Solis spectrum",
            block_type="LoadSpectrum",
            handler="_load_andor_solis",
            is_default=True,
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_SPECTRUM_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.princeton_spe.load",
            direction="load",
            data_type=Spectrum,
            format_id="princeton_spe",
            extensions=(".spe",),
            label="Princeton/LightField SPE spectrum",
            block_type="LoadSpectrum",
            handler="_load_princeton_spe",
            is_default=True,
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_SPECTRUM_META_FIELDS),
        ),
    )

    # Handler methods delegate to io_handlers.spectrum_formats.
    _load_delimited_text = staticmethod(spectrum_formats.load_delimited_text)
    _load_spectrum_xlsx = staticmethod(spectrum_formats.load_spectrum_xlsx)
    _load_spectrum_json = staticmethod(spectrum_formats.load_spectrum_json)
    _load_jcamp_dx = staticmethod(spectrum_formats.load_jcamp_dx)
    _load_spc = staticmethod(spectrum_formats.load_spc)
    _load_thermo_omnic_spa = staticmethod(spectrum_formats.load_thermo_omnic_spa)
    _load_bruker_opus = staticmethod(spectrum_formats.load_bruker_opus)
    _load_horiba_labspec = staticmethod(spectrum_formats.load_horiba_labspec)
    _load_renishaw_wdf = staticmethod(spectrum_formats.load_renishaw_wdf)
    _load_andor_solis = staticmethod(spectrum_formats.load_andor_solis)
    _load_princeton_spe = staticmethod(spectrum_formats.load_princeton_spe)

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """Load one or more spectra into a Collection[Spectrum].

        Implementation plan (FR-034..FR-036):
          1. Resolve config['path'] (str | list[str]); expand folder/glob.
          2. For each file: fmt = self._detect_format(path) or explicit
             capability_id; dispatch to the matching _load_* handler.
          3. Preserve a source-provided spectrum_id, else generate a unique
             package-managed spectrum_id; keep source_file as metadata only
             (never default spectrum_id to the filename).
          4. Return _support.spectra_collection(list_of_spectra).
        Edge cases: unsupported extension; extensionless OPUS via capability_id;
          empty path list; mixed formats in one load.
        Test plan: test_spectrum_io.py::test_load_generates_unique_ids,
          ::test_load_keeps_source_file_as_metadata.
        """
        raise NotImplementedError("skeleton — implement per FR-034..FR-036; see comment above")

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:  # pragma: no cover
        raise NotImplementedError("LoadSpectrum is an input block; use load()")


# ==========================================================================
# SaveSpectrum (FR-037, FR-132)
# ==========================================================================


class SaveSpectrum(IOBlock):
    """Persist a ``Spectrum`` or ``Collection[Spectrum]`` to file (FR-037)."""

    direction: ClassVar[str] = "output"
    type_name: ClassVar[str] = "spectroscopy.save_spectrum"
    name: ClassVar[str] = "Save Spectrum"
    description: ClassVar[str] = "Save a Spectrum or Collection[Spectrum] to a supported file format."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "io"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="spectra",
            accepted_types=[Spectrum],
            is_collection=True,
            required=True,
            description="Spectrum or Collection[Spectrum] to save.",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="path", accepted_types=[DataObject], description="Save receipt path."),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "title": "Output path",
                "ui_widget": "file_browser",
                "ui_priority": 0,
            },
            "output_dir": {"type": "string", "title": "Output directory"},
            "capability_id": {
                "type": "string",
                "title": "Format capability id",
                "description": "Optional explicit FormatCapability.id (ADR-043 selection).",
            },
        },
        "required": ["path"],
    }

    supported_extensions: ClassVar[dict[str, str]] = {
        ".txt": "txt",
        ".csv": "csv",
        ".tsv": "tsv",
        ".xlsx": "xlsx",
        ".spectrum.json": "spectrum_json",
        ".jdx": "jcamp_dx",
        ".dx": "jcamp_dx",
        ".jcamp": "jcamp_dx",
        ".spc": "spc",
    }

    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id=f"{_PKG}.spectrum.txt.save",
            direction="save",
            data_type=Spectrum,
            format_id="txt",
            extensions=(".txt",),
            label="Text spectrum",
            block_type="SaveSpectrum",
            handler="_save_delimited_text",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectrum.txt",
            metadata_fidelity=MetadataFidelity(level="pixel_only"),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.csv.save",
            direction="save",
            data_type=Spectrum,
            format_id="csv",
            extensions=(".csv",),
            label="CSV spectrum",
            block_type="SaveSpectrum",
            handler="_save_delimited_text",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectrum.csv",
            metadata_fidelity=MetadataFidelity(level="pixel_only"),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.tsv.save",
            direction="save",
            data_type=Spectrum,
            format_id="tsv",
            extensions=(".tsv",),
            label="TSV spectrum",
            block_type="SaveSpectrum",
            handler="_save_delimited_text",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectrum.tsv",
            metadata_fidelity=MetadataFidelity(level="pixel_only"),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.xlsx.save",
            direction="save",
            data_type=Spectrum,
            format_id="xlsx",
            extensions=(".xlsx",),
            label="Excel spectrum workbook",
            block_type="SaveSpectrum",
            handler="_save_spectrum_xlsx",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectrum.xlsx",
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_writes=_SPECTRUM_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.spectrum_json.save",
            direction="save",
            data_type=Spectrum,
            format_id="spectrum_json",
            extensions=(".spectrum.json",),
            label="Native Spectrum JSON",
            block_type="SaveSpectrum",
            handler="_save_spectrum_json",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectrum.spectrum_json",
            metadata_fidelity=MetadataFidelity(level="lossless", typed_meta_writes=_SPECTRUM_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.jcamp_dx.save",
            direction="save",
            data_type=Spectrum,
            format_id="jcamp_dx",
            extensions=(".jdx", ".dx", ".jcamp"),
            label="JCAMP-DX spectrum",
            block_type="SaveSpectrum",
            handler="_save_jcamp_dx",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectrum.jcamp_dx",
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_writes=_SPECTRUM_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectrum.spc.save",
            direction="save",
            data_type=Spectrum,
            format_id="spc",
            extensions=(".spc",),
            label="SPC spectrum",
            block_type="SaveSpectrum",
            handler="_save_spc",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectrum.spc",
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_writes=_SPECTRUM_META_FIELDS),
        ),
    )

    _save_delimited_text = staticmethod(spectrum_formats.save_delimited_text)
    _save_spectrum_xlsx = staticmethod(spectrum_formats.save_spectrum_xlsx)
    _save_spectrum_json = staticmethod(spectrum_formats.save_spectrum_json)
    _save_jcamp_dx = staticmethod(spectrum_formats.save_jcamp_dx)
    _save_spc = staticmethod(spectrum_formats.save_spc)

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:  # pragma: no cover
        raise NotImplementedError("SaveSpectrum is an output block; use save()")

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Persist a Spectrum / Collection[Spectrum] (FR-037).

        Implementation plan (FR-037, FR-134):
          1. Resolve config['path'] (+ optional output_dir / capability_id).
          2. Resolve fmt via _detect_format(path) or explicit capability_id;
             reject vendor load-only formats as save targets (FR-134).
          3. Single item -> one file; multi-item Collection -> numbered files in
             output_dir. Dispatch each to the matching _save_* handler,
             preserving spectrum_id/axis/intensity/typed+user metadata where
             the format allows.
        Edge cases: unsupported save extension; collection vs single; meta=None.
        Test plan: test_spectrum_io.py::test_save_single_and_collection,
          ::test_save_rejects_vendor_load_only_format.
        """
        raise NotImplementedError("skeleton — implement per FR-037/FR-134; see comment above")


# ==========================================================================
# LoadSpectralDataset (FR-038, FR-135..FR-139)
# ==========================================================================


class LoadSpectralDataset(IOBlock):
    """Load a dataset-shaped representation into a ``SpectralDataset`` (FR-038)."""

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "spectroscopy.load_spectral_dataset"
    name: ClassVar[str] = "Load Spectral Dataset"
    description: ClassVar[str] = "Load a SpectralDataset from a manifest, workbook, SPC, or vendor file."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "io"

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="dataset", accepted_types=[SpectralDataset], description="Loaded dataset."),
    ]

    config_schema: ClassVar[dict[str, Any]] = _PATH_CONFIG_SCHEMA

    supported_extensions: ClassVar[dict[str, str]] = {
        ".json": "spectral_dataset_manifest_json",
        ".xlsx": "xlsx",
        ".xls": "xlsx",
        ".spc": "spc",
        ".spg": "thermo_omnic_spg",
        ".wdf": "renishaw_wdf",
        ".opus": "bruker_opus",
        ".l6s": "horiba_labspec",
        ".l5s": "horiba_labspec",
        ".ngc": "horiba_labspec",
        ".xml": "horiba_labspec",
        ".txt": "horiba_labspec",
        ".wip": "witec_project",
        ".wid": "witec_project",
        ".sif": "andor_solis",
        ".fits": "andor_solis",
        ".fit": "andor_solis",
        ".spe": "princeton_spe",
    }

    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id=f"{_PKG}.spectral_dataset.manifest_json.load",
            direction="load",
            data_type=SpectralDataset,
            format_id="spectral_dataset_manifest_json",
            extensions=(".json",),
            label="SpectralDataset manifest (JSON)",
            block_type="LoadSpectralDataset",
            handler="_load_manifest_json",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectral_dataset.manifest_json",
            metadata_fidelity=MetadataFidelity(level="lossless", typed_meta_reads=_DATASET_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectral_dataset.xlsx.load",
            direction="load",
            data_type=SpectralDataset,
            format_id="xlsx",
            extensions=(".xlsx", ".xls"),
            label="SpectralDataset Excel workbook",
            block_type="LoadSpectralDataset",
            handler="_load_dataset_xlsx",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectral_dataset.xlsx",
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_DATASET_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectral_dataset.spc.load",
            direction="load",
            data_type=SpectralDataset,
            format_id="spc",
            extensions=(".spc",),
            label="SPC spectral dataset",
            block_type="LoadSpectralDataset",
            handler="_load_spc_dataset",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectral_dataset.spc",
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_DATASET_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectral_dataset.thermo_omnic_spg.load",
            direction="load",
            data_type=SpectralDataset,
            format_id="thermo_omnic_spg",
            extensions=(".spg",),
            label="Thermo OMNIC SPG dataset",
            block_type="LoadSpectralDataset",
            handler="_load_thermo_omnic_spg",
            is_default=True,
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_DATASET_VENDOR_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectral_dataset.renishaw_wdf.load",
            direction="load",
            data_type=SpectralDataset,
            format_id="renishaw_wdf",
            extensions=(".wdf",),
            label="Renishaw WiRE dataset",
            block_type="LoadSpectralDataset",
            handler="_load_renishaw_wdf_dataset",
            is_default=True,
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_DATASET_VENDOR_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectral_dataset.bruker_opus.load",
            direction="load",
            data_type=SpectralDataset,
            format_id="bruker_opus",
            extensions=(".opus",),
            label="Bruker OPUS dataset",
            block_type="LoadSpectralDataset",
            handler="_load_bruker_opus_dataset",
            is_default=True,
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_DATASET_VENDOR_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectral_dataset.horiba_labspec.load",
            direction="load",
            data_type=SpectralDataset,
            format_id="horiba_labspec",
            extensions=(".l6s", ".l5s", ".ngc", ".xml", ".txt"),
            label="HORIBA LabSpec dataset",
            block_type="LoadSpectralDataset",
            handler="_load_horiba_labspec_dataset",
            is_default=True,
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_DATASET_VENDOR_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectral_dataset.witec_project.load",
            direction="load",
            data_type=SpectralDataset,
            format_id="witec_project",
            extensions=(".wip", ".wid"),
            label="WITec project dataset",
            block_type="LoadSpectralDataset",
            handler="_load_witec_project",
            is_default=True,
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_DATASET_VENDOR_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectral_dataset.andor_solis.load",
            direction="load",
            data_type=SpectralDataset,
            format_id="andor_solis",
            extensions=(".sif", ".fits", ".fit"),
            label="Andor Solis dataset",
            block_type="LoadSpectralDataset",
            handler="_load_andor_solis_dataset",
            is_default=True,
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_DATASET_VENDOR_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectral_dataset.princeton_spe.load",
            direction="load",
            data_type=SpectralDataset,
            format_id="princeton_spe",
            extensions=(".spe",),
            label="Princeton/LightField SPE dataset",
            block_type="LoadSpectralDataset",
            handler="_load_princeton_spe_dataset",
            is_default=True,
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=_DATASET_VENDOR_META_FIELDS),
        ),
    )

    _load_manifest_json = staticmethod(dataset_formats.load_manifest_json)
    _load_dataset_xlsx = staticmethod(dataset_formats.load_dataset_xlsx)
    _load_spc_dataset = staticmethod(dataset_formats.load_spc_dataset)
    _load_thermo_omnic_spg = staticmethod(dataset_formats.load_thermo_omnic_spg)
    _load_renishaw_wdf_dataset = staticmethod(dataset_formats.load_renishaw_wdf_dataset)
    _load_bruker_opus_dataset = staticmethod(dataset_formats.load_bruker_opus_dataset)
    _load_horiba_labspec_dataset = staticmethod(dataset_formats.load_horiba_labspec_dataset)
    _load_witec_project = staticmethod(dataset_formats.load_witec_project)
    _load_andor_solis_dataset = staticmethod(dataset_formats.load_andor_solis_dataset)
    _load_princeton_spe_dataset = staticmethod(dataset_formats.load_princeton_spe_dataset)

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """Load a dataset-shaped file into a SpectralDataset (FR-038).

        Resolves ``config['path']`` and optional ``capability_id``, dispatches to
        the matching ``_load_*`` handler (manifest JSON / xlsx workbook / SPC /
        vendor) via ADR-043 selection, and returns the loaded
        :class:`SpectralDataset`. The handlers validate the canonical two-table
        layout (FR-038, FR-135..FR-139); the ``IOBlock.run`` wrapper packs the
        single dataset into a Collection.
        """
        from pathlib import Path

        block = "LoadSpectralDataset"
        raw_path = config.get("path")
        if isinstance(raw_path, (list, tuple)):
            if len(raw_path) != 1:
                raise ValueError(f"{block}: expected a single dataset path, got {len(raw_path)} paths")
            raw_path = raw_path[0]
        if not raw_path:
            raise ValueError(f"{block}: missing required 'path' config")
        path = Path(str(raw_path))

        capability = _resolve_dataset_io_capability(self, config, path, direction="load", block=block)
        handler = getattr(self, capability.handler)
        dataset: SpectralDataset = handler(path)
        return dataset

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:  # pragma: no cover
        raise NotImplementedError("LoadSpectralDataset is an input block; use load()")


# ==========================================================================
# SaveSpectralDataset (FR-039, FR-135..FR-138)
# ==========================================================================


class SaveSpectralDataset(IOBlock):
    """Persist a ``SpectralDataset`` in a canonical two-table layout (FR-039)."""

    direction: ClassVar[str] = "output"
    type_name: ClassVar[str] = "spectroscopy.save_spectral_dataset"
    name: ClassVar[str] = "Save Spectral Dataset"
    description: ClassVar[str] = "Save a SpectralDataset to a JSON manifest, workbook, or SPC file."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "io"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="dataset",
            accepted_types=[SpectralDataset],
            required=True,
            description="SpectralDataset to save.",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="path", accepted_types=[DataObject], description="Save receipt path."),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "title": "Output path",
                "ui_widget": "file_browser",
                "ui_priority": 0,
            },
            "output_dir": {"type": "string", "title": "Output directory"},
            "capability_id": {
                "type": "string",
                "title": "Format capability id",
                "description": "Optional explicit FormatCapability.id (ADR-043 selection).",
            },
        },
        "required": ["path"],
    }

    supported_extensions: ClassVar[dict[str, str]] = {
        ".json": "spectral_dataset_manifest_json",
        ".xlsx": "xlsx",
        ".spc": "spc",
    }

    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id=f"{_PKG}.spectral_dataset.manifest_json.save",
            direction="save",
            data_type=SpectralDataset,
            format_id="spectral_dataset_manifest_json",
            extensions=(".json",),
            label="SpectralDataset manifest (JSON)",
            block_type="SaveSpectralDataset",
            handler="_save_manifest_json",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectral_dataset.manifest_json",
            metadata_fidelity=MetadataFidelity(level="lossless", typed_meta_writes=_DATASET_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectral_dataset.xlsx.save",
            direction="save",
            data_type=SpectralDataset,
            format_id="xlsx",
            extensions=(".xlsx",),
            label="SpectralDataset Excel workbook",
            block_type="SaveSpectralDataset",
            handler="_save_dataset_xlsx",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectral_dataset.xlsx",
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_writes=_DATASET_META_FIELDS),
        ),
        FormatCapability(
            id=f"{_PKG}.spectral_dataset.spc.save",
            direction="save",
            data_type=SpectralDataset,
            format_id="spc",
            extensions=(".spc",),
            label="SPC spectral dataset",
            block_type="SaveSpectralDataset",
            handler="_save_spc_dataset",
            is_default=True,
            roundtrip_group=f"{_PKG}.spectral_dataset.spc",
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_writes=_DATASET_META_FIELDS),
        ),
    )

    _save_manifest_json = staticmethod(dataset_formats.save_manifest_json)
    _save_dataset_xlsx = staticmethod(dataset_formats.save_dataset_xlsx)
    _save_spc_dataset = staticmethod(dataset_formats.save_spc_dataset)

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:  # pragma: no cover
        raise NotImplementedError("SaveSpectralDataset is an output block; use save()")

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Persist a SpectralDataset (FR-039).

        Resolves ``config['path']`` (+ optional ``output_dir``/``capability_id``),
        dispatches to ``_save_manifest_json`` / ``_save_dataset_xlsx`` /
        ``_save_spc_dataset`` (the only declared savers — there is no archive/zip
        capability, FR-136), and writes the canonical two-table layout preserving
        ``index.spectrum_id``, ``spectra.spectrum_id``, coordinates, intensities,
        and dataset/index metadata (FR-039, FR-135..FR-138).
        """
        from pathlib import Path

        from scistudio_blocks_spectroscopy import _support

        block = "SaveSpectralDataset"
        dataset = _support.coerce_dataset(obj, block=block, port="dataset")

        raw_path = config.get("path")
        if isinstance(raw_path, (list, tuple)):
            raise ValueError(f"{block}: save expects a single output path, got a list")
        if not raw_path:
            raise ValueError(f"{block}: missing required 'path' config")
        path = Path(str(raw_path))
        output_dir = config.get("output_dir")
        if output_dir and not path.is_absolute():
            path = Path(str(output_dir)) / path

        capability = _resolve_dataset_io_capability(self, config, path, direction="save", block=block)
        handler = getattr(self, capability.handler)
        handler(dataset, path)


# ==========================================================================
# Conversion / transport process blocks (FR-040..FR-051, FR-084, FR-085)
# ==========================================================================


class SpectrumToSpectralDataset(ProcessBlock):
    """Build a ``SpectralDataset`` from ``Collection[Spectrum]`` + metadata (FR-040)."""

    type_name: ClassVar[str] = "spectroscopy.spectrum_to_spectral_dataset"
    name: ClassVar[str] = "Spectrum to Spectral Dataset"
    description: ClassVar[str] = "Build a SpectralDataset from spectra plus an optional metadata table."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "utilities"
    algorithm: ClassVar[str] = "spectrum_to_spectral_dataset"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="spectra", accepted_types=[Spectrum], is_collection=True, required=True),
        InputPort(name="metadata", accepted_types=[DataFrame], required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="dataset", accepted_types=[SpectralDataset]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "metadata_join_key": {
                "type": "string",
                "default": "spectrum_id",
                "title": "Metadata join key",
            },
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Assemble a SpectralDataset (FR-040..FR-044).

        Implementation plan:
          1. spectra = inputs['spectra']; optional metadata = inputs.get('metadata').
          2. Build long-form `spectra` slot (spectrum_id, lambda, intensity) from
             each Spectrum via _support.spectrum_arrays (FR-041).
          3. Build `index` slot: one row per spectrum (id + Spectrum.Meta/user),
             then left-join metadata on config['metadata_join_key']
             (default 'spectrum_id'); never use filename as spectrum_id (FR-044).
          4. Return {'dataset': Collection([SpectralDataset(slots=...)],
             item_type=SpectralDataset)}.
        Edge cases: missing join column; duplicate join keys; empty collection.
        Test plan: test_utility_blocks.py::test_spectrum_to_dataset_join_by_source_file.
        """
        raise NotImplementedError("skeleton — implement per FR-040..FR-044; see comment above")


class SpectralDatasetToSpectrum(ProcessBlock):
    """Split a ``SpectralDataset`` into ``Collection[Spectrum]`` (FR-045)."""

    type_name: ClassVar[str] = "spectroscopy.spectral_dataset_to_spectrum"
    name: ClassVar[str] = "Spectral Dataset to Spectrum"
    description: ClassVar[str] = "Split a SpectralDataset into one Spectrum per index row."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "utilities"
    algorithm: ClassVar[str] = "spectral_dataset_to_spectrum"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="dataset", accepted_types=[SpectralDataset], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="spectra", accepted_types=[Spectrum], is_collection=True),
    ]
    config_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Split a dataset into spectra (FR-045, FR-046).

        Implementation plan:
          1. dataset = inputs['dataset']; read `index` + `spectra` slot tables.
          2. Group `spectra` by spectrum_id; for each index row build a Spectrum
             via _support.build_spectrum with the row's metadata mapped into
             Spectrum.Meta (known fields) and user (extra columns) (FR-046).
          3. Return {'spectra': _support.spectra_collection(list)}.
        Edge cases: orphan spectra rows; index row with no spectra; ordering.
        Test plan: test_utility_blocks.py::test_dataset_to_spectrum_attaches_metadata.
        """
        raise NotImplementedError("skeleton — implement per FR-045/FR-046; see comment above")


class FilterSpectralDataset(ProcessBlock):
    """Filter a ``SpectralDataset`` by index-metadata predicates (FR-047)."""

    type_name: ClassVar[str] = "spectroscopy.filter_spectral_dataset"
    name: ClassVar[str] = "Filter Spectral Dataset"
    description: ClassVar[str] = "Keep only index rows matching metadata predicates and their spectra."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "utilities"
    algorithm: ClassVar[str] = "filter_spectral_dataset"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="dataset", accepted_types=[SpectralDataset], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="dataset", accepted_types=[SpectralDataset]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "predicates": {
                "type": ["object", "array"],
                "title": "Filter predicates",
                "description": "Index-column metadata predicates to keep matching rows.",
            },
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Filter a dataset by index predicates (FR-047, FR-048).

        Implementation plan:
          1. dataset = inputs['dataset']; evaluate config['predicates'] against
             the `index` table -> kept spectrum_id set.
          2. Restrict both `index` and `spectra` slots to kept ids; do not
             change coordinates/intensities/units (FR-048).
          3. Return {'dataset': Collection([filtered], item_type=SpectralDataset)}.
        Edge cases: empty result; unknown predicate column; no predicates (pass-through).
        Test plan: test_utility_blocks.py::test_filter_dataset_restricts_both_slots.
        """
        raise NotImplementedError("skeleton — implement per FR-047/FR-048; see comment above")


class MergeSpectralDataset(ProcessBlock):
    """Merge multiple ``SpectralDataset`` inputs by appending rows (FR-049)."""

    type_name: ClassVar[str] = "spectroscopy.merge_spectral_dataset"
    name: ClassVar[str] = "Merge Spectral Dataset"
    description: ClassVar[str] = "Append multiple SpectralDatasets, applying a duplicate-ID policy."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "utilities"
    algorithm: ClassVar[str] = "merge_spectral_dataset"
    variadic_inputs: ClassVar[bool] = True

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="datasets", accepted_types=[SpectralDataset], is_collection=True, required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="dataset", accepted_types=[SpectralDataset]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "duplicate_id_policy": {
                "type": "string",
                "enum": ["error", "prefix", "remap"],
                "default": "error",
                "title": "Duplicate ID policy",
            },
        },
        "required": ["duplicate_id_policy"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Merge datasets by appending rows (FR-049..FR-051).

        Implementation plan:
          1. datasets = inputs['datasets'] (variadic). Concatenate `index` and
             `spectra` slots in input order.
          2. Resolve duplicate spectrum_id per config['duplicate_id_policy']:
             'error' fail; 'prefix' add per-dataset prefix; 'remap' assign new ids
             consistently across both slots (FR-050).
          3. Refuse silent unit reconciliation -> fail on unit mismatch (FR-051).
          4. Return {'dataset': Collection([merged], item_type=SpectralDataset)}.
        Edge cases: single input; disjoint index columns; unit mismatch.
        Test plan: test_utility_blocks.py::test_merge_dataset_duplicate_policies.
        """
        raise NotImplementedError("skeleton — implement per FR-049..FR-051; see comment above")


class AttachFeaturesToSpectralDataset(ProcessBlock):
    """Join a feature ``DataFrame`` onto ``SpectralDataset.index`` (FR-084)."""

    type_name: ClassVar[str] = "spectroscopy.attach_features_to_spectral_dataset"
    name: ClassVar[str] = "Attach Features to Spectral Dataset"
    description: ClassVar[str] = "Join flat feature columns onto the dataset index by spectrum_id."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "utilities"
    algorithm: ClassVar[str] = "attach_features_to_spectral_dataset"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="dataset", accepted_types=[SpectralDataset], required=True),
        InputPort(name="features", accepted_types=[DataFrame], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="dataset", accepted_types=[SpectralDataset]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "join_key": {"type": "string", "default": "spectrum_id", "title": "Join key"},
            "conflict_policy": {
                "type": "string",
                "enum": ["error", "prefix", "suffix", "replace"],
                "default": "error",
                "title": "Column-conflict policy",
            },
        },
        "required": ["conflict_policy"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Attach feature columns to the dataset index (FR-084, FR-085).

        Implementation plan:
          1. dataset = inputs['dataset']; features = inputs['features'].
          2. Left-join feature columns onto `index` by config['join_key']
             (default 'spectrum_id'); resolve column collisions per
             config['conflict_policy'] (error/prefix/suffix/replace) — never
             silently overwrite (FR-085).
          3. Leave `spectra` slot unchanged.
          4. Return {'dataset': Collection([updated], item_type=SpectralDataset)}.
        Edge cases: feature rows with no matching id; missing join column;
          column collision under each policy.
        Test plan: test_utility_blocks.py::test_attach_features_conflict_policies.
        """
        raise NotImplementedError("skeleton — implement per FR-084/FR-085; see comment above")


BLOCKS: list[type] = [
    LoadSpectrum,
    SaveSpectrum,
    LoadSpectralDataset,
    SaveSpectralDataset,
    SpectrumToSpectralDataset,
    SpectralDatasetToSpectrum,
    FilterSpectralDataset,
    MergeSpectralDataset,
    AttachFeaturesToSpectralDataset,
]

__all__ = [
    "BLOCKS",
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
