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

from typing import Any, ClassVar, cast

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scistudio.blocks.io.io_block import IOBlock
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.io_handlers import (
    dataset_formats,
    spectrum_formats,
)
from scistudio_blocks_spectroscopy.types import (
    INTENSITY_COLUMN,
    LAMBDA_COLUMN,
    SPECTRUM_ID_COLUMN,
    SpectralDataset,
    Spectrum,
)

_PKG = "scistudio-blocks-spectroscopy"

# Typed ``Spectrum.Meta`` field names. Index columns matching one of these are
# mapped back onto ``Spectrum.Meta`` on split; everything else is user metadata.
_SPECTRUM_META_KEYS: tuple[str, ...] = tuple(Spectrum.Meta.model_fields.keys())

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

        Implementation plan (FR-038, FR-135..FR-139):
          1. Resolve config['path'] + optional capability_id.
          2. fmt = self._detect_format(path); dispatch to the matching
             _load_*_dataset / _load_manifest_json / _load_dataset_xlsx handler.
          3. Validate required columns: index.spectrum_id; spectra
             spectrum_id/lambda/intensity; report orphan rows.
          4. Return Collection(items=[dataset], item_type=SpectralDataset).
        Edge cases: vendor multi-spectrum files; missing required sheet/column.
        Test plan: test_spectral_dataset_io.py::test_load_manifest_json,
          ::test_load_validates_required_columns.
        """
        raise NotImplementedError("skeleton — implement per FR-038/FR-135..FR-139; see comment above")

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

        Implementation plan (FR-039, FR-135..FR-138):
          1. Resolve config['path'] (+ optional output_dir / capability_id).
          2. Resolve fmt via _detect_format(path) or explicit capability_id.
          3. Dispatch to _save_manifest_json / _save_dataset_xlsx /
             _save_spc_dataset, preserving index.spectrum_id,
             spectra.spectrum_id, coordinates, intensities, dataset + index meta.
        Edge cases: empty dataset; unsupported save extension; archive (.zip)
          must be rejected (FR-136).
        Test plan: test_spectral_dataset_io.py::test_save_manifest_json,
          ::test_save_rejects_zip_bundle.
        """
        raise NotImplementedError("skeleton — implement per FR-039/FR-135..FR-138; see comment above")


# ==========================================================================
# Conversion / transport process blocks (FR-040..FR-051, FR-084, FR-085)
# ==========================================================================
#
# These five blocks only move data between Collection[Spectrum] and
# SpectralDataset shapes; they perform NO scientific processing (FR-052).


def _resolve_spectrum_id(spectrum: Spectrum) -> str:
    """Return the spectrum's existing id, generating a fresh one if absent.

    Never derives the id from a filename (FR-044); ``source_file`` stays
    metadata-only on the index row.
    """
    sid = spectrum.spectrum_id
    return sid if sid else _support.new_spectrum_id()


def _index_row_from_spectrum(spectrum: Spectrum, sid: str) -> dict[str, Any]:
    """Build one index row from a spectrum's typed Meta + user metadata."""
    row: dict[str, Any] = {SPECTRUM_ID_COLUMN: sid}
    meta = spectrum.meta
    if isinstance(meta, Spectrum.Meta):
        for field, value in meta.model_dump().items():
            if field == "spectrum_id":
                continue
            if value is not None:
                row[field] = value
    user = spectrum.user
    if user:
        for key, value in user.items():
            if key not in row:
                row[key] = value
    return row


def _join_metadata(index_pdf: Any, meta_pdf: Any, join_key: str, block: str) -> Any:
    """Left-join a user metadata frame onto the index by ``join_key`` (FR-042/043)."""
    import pandas as pd  # noqa: F401  (kept lazy; pandas already imported by caller)

    if join_key not in index_pdf.columns:
        raise ValueError(f"{block}: index has no join column {join_key!r}")
    if join_key not in meta_pdf.columns:
        raise ValueError(f"{block}: metadata table has no join column {join_key!r}")
    # Drop overlapping non-key columns from the index so metadata fills them in
    # (metadata table is the authoritative side for the joined columns).
    overlap = [c for c in meta_pdf.columns if c != join_key and c in index_pdf.columns]
    left = index_pdf.drop(columns=overlap) if overlap else index_pdf
    return left.merge(meta_pdf, on=join_key, how="left")


def _dataset_meta_from_spectra(spectra: list[Spectrum]) -> SpectralDataset.Meta:
    """Derive dataset-level unit/modality defaults from the input spectra.

    Only adopts a value when every spectrum that declares it agrees; otherwise
    the dataset-level field is left None (per-spectrum units stay authoritative).
    """
    fields = ("lambda_unit", "intensity_unit", "modality")
    resolved: dict[str, Any] = {}
    for field in fields:
        values = set()
        for spectrum in spectra:
            meta = spectrum.meta
            if isinstance(meta, Spectrum.Meta):
                value = getattr(meta, field, None)
                if value is not None:
                    values.add(value)
        if len(values) == 1:
            resolved[field] = next(iter(values))
    return SpectralDataset.Meta(**resolved)


def _split_index_row(row: dict[str, Any], unit_defaults: dict[str, Any]) -> tuple[Spectrum.Meta, dict[str, Any]]:
    """Split an index row into a typed ``Spectrum.Meta`` plus a user dict (FR-046)."""
    meta_kwargs: dict[str, Any] = dict(unit_defaults)
    user: dict[str, Any] = {}
    for key, value in row.items():
        if key == SPECTRUM_ID_COLUMN:
            continue
        if _is_missing(value):
            continue
        if key in _SPECTRUM_META_KEYS:
            meta_kwargs[key] = value  # row value overrides dataset default
        else:
            user[key] = value
    return Spectrum.Meta(**meta_kwargs), user


def _normalise_predicates(raw: Any, block: str) -> list[dict[str, Any]]:
    """Normalise the predicate config into a list of ``{column, op, value}`` dicts.

    Supported forms (FR-047):
      - mapping ``{column: value}`` -> equality (value may be a list -> ``in``)
      - mapping ``{column: {op: value}}`` with op in eq/ne/in/lt/le/gt/ge
      - list of ``{"column": .., "op": .., "value": ..}`` dicts
    """
    if raw is None:
        return []
    predicates: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        for column, spec in raw.items():
            predicates.append(_predicate_from_spec(str(column), spec))
    elif isinstance(raw, (list, tuple)):
        for entry in raw:
            if not isinstance(entry, dict) or "column" not in entry:
                raise ValueError(f"{block}: list predicates need a 'column' key, got {entry!r}")
            column = str(entry["column"])
            if "op" in entry or "value" in entry:
                predicates.append({"column": column, "op": str(entry.get("op", "eq")), "value": entry.get("value")})
            else:
                predicates.append(_predicate_from_spec(column, {k: v for k, v in entry.items() if k != "column"}))
    else:
        raise ValueError(f"{block}: predicates must be a mapping or list, got {type(raw).__name__}")
    return predicates


def _predicate_from_spec(column: str, spec: Any) -> dict[str, Any]:
    _ops = {"eq", "ne", "in", "lt", "le", "gt", "ge"}
    if isinstance(spec, dict) and spec and all(k in _ops for k in spec):
        op, value = next(iter(spec.items()))
        return {"column": column, "op": op, "value": value}
    if isinstance(spec, (list, tuple, set)):
        return {"column": column, "op": "in", "value": list(spec)}
    return {"column": column, "op": "eq", "value": spec}


def _eval_predicate(series: Any, pred: dict[str, Any]) -> list[bool]:
    op = pred["op"]
    value = pred["value"]
    if op == "in":
        choices = set(value if isinstance(value, (list, tuple, set)) else [value])
        return [v in choices for v in series.tolist()]
    if op == "eq":
        return [v == value for v in series.tolist()]
    if op == "ne":
        return [v != value for v in series.tolist()]
    numeric = series.astype(float)
    if op == "lt":
        return [bool(v < value) for v in numeric.tolist()]
    if op == "le":
        return [bool(v <= value) for v in numeric.tolist()]
    if op == "gt":
        return [bool(v > value) for v in numeric.tolist()]
    if op == "ge":
        return [bool(v >= value) for v in numeric.tolist()]
    raise ValueError(f"FilterSpectralDataset: unsupported predicate op {op!r}")


def _coerce_datasets(value: Any, block: str) -> list[SpectralDataset]:
    """Normalise the variadic ``datasets`` port to a list of >=2 SpectralDatasets."""
    if value is None:
        raise ValueError(f"{block}: missing required 'datasets' input")
    items: list[Any]
    if isinstance(value, Collection):
        items = list(value)
    elif isinstance(value, SpectralDataset):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise ValueError(f"{block}: 'datasets' expected Collection[SpectralDataset], got {type(value).__name__}")
    datasets: list[SpectralDataset] = []
    for item in items:
        if not isinstance(item, SpectralDataset):
            raise ValueError(f"{block}: every input must be a SpectralDataset, got {type(item).__name__}")
        datasets.append(item)
    if len(datasets) < 2:
        raise ValueError(f"{block}: merge requires at least 2 datasets, got {len(datasets)}")
    return datasets


def _check_unit_compatibility(datasets: list[SpectralDataset], block: str) -> None:
    """Fail on mixed lambda/intensity units across datasets (FR-051)."""
    for field in ("lambda_unit", "intensity_unit"):
        seen: set[Any] = set()
        for dataset in datasets:
            meta = dataset.meta
            if isinstance(meta, SpectralDataset.Meta):
                value = getattr(meta, field, None)
                if value is not None:
                    seen.add(value)
        if len(seen) > 1:
            raise ValueError(
                f"{block}: incompatible {field} across datasets {sorted(seen)!r}; "
                "unit reconciliation is not performed (FR-051)"
            )


def _build_id_map(ids: list[str], seen_ids: set[str], policy: str, position: int) -> dict[str, str]:
    """Build a per-dataset spectrum_id remap for duplicates (FR-050)."""
    id_map: dict[str, str] = {}
    taken = set(seen_ids)
    for sid in ids:
        if sid not in seen_ids:
            continue
        if policy == "prefix":
            candidate = f"ds{position}_{sid}"
            while candidate in taken or candidate in seen_ids:
                candidate = f"ds{position}_{_support.new_spectrum_id()}"
        else:  # remap
            candidate = _support.new_spectrum_id()
            while candidate in taken or candidate in seen_ids:
                candidate = _support.new_spectrum_id()
        id_map[sid] = candidate
        taken.add(candidate)
    return id_map


def _clone_dataset_meta(meta: Any) -> SpectralDataset.Meta:
    """Return the dataset meta if typed, else a fresh empty one."""
    if isinstance(meta, SpectralDataset.Meta):
        return meta
    return SpectralDataset.Meta()


def _reject_object_cells(pdf: Any, block: str) -> None:
    """Reject DataObject/Spectrum object cells in a feature frame (FR-083)."""
    for column in pdf.columns:
        for value in pdf[column].tolist():
            if isinstance(value, DataObject):
                raise ValueError(
                    f"{block}: feature column {column!r} contains a {type(value).__name__} object; "
                    "feature tables must be flat and columnar (FR-083)"
                )


def _is_missing(value: Any) -> bool:
    """Return True for None / pandas-NaN-like scalar cells."""
    if value is None:
        return True
    try:
        import math

        return isinstance(value, float) and math.isnan(value)
    except Exception:  # pragma: no cover - defensive
        return False


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
        block = "SpectrumToSpectralDataset"
        spectra = _support.coerce_spectra(inputs.get("spectra"), block=block, port="spectra")
        join_key = str(config.get("metadata_join_key", SPECTRUM_ID_COLUMN))

        # Build long-form spectra table + one index row per spectrum (FR-041, FR-042).
        spectra_rows: list[dict[str, Any]] = []
        index_rows: list[dict[str, Any]] = []
        for spectrum in spectra:
            sid = _resolve_spectrum_id(spectrum)
            lam, inten = _support.spectrum_arrays(spectrum)
            for lam_val, inten_val in zip(lam.tolist(), inten.tolist(), strict=True):
                spectra_rows.append({SPECTRUM_ID_COLUMN: sid, LAMBDA_COLUMN: lam_val, INTENSITY_COLUMN: inten_val})
            index_rows.append(_index_row_from_spectrum(spectrum, sid))

        import pandas as pd

        index_pdf = pd.DataFrame(index_rows)
        if SPECTRUM_ID_COLUMN not in index_pdf.columns:
            index_pdf[SPECTRUM_ID_COLUMN] = [r[SPECTRUM_ID_COLUMN] for r in index_rows]

        # Optional metadata join (FR-042, FR-043). Default join column is
        # spectrum_id; source_file/filename (or any user column) also supported.
        metadata = inputs.get("metadata")
        if metadata is not None:
            meta_df = _support.coerce_dataframe(metadata, block=block, port="metadata")
            meta_pdf = _support.dataframe_pandas(meta_df)
            index_pdf = _join_metadata(index_pdf, meta_pdf, join_key, block)

        spectra_df = _support.dataframe_from_rows(
            spectra_rows, columns=[SPECTRUM_ID_COLUMN, LAMBDA_COLUMN, INTENSITY_COLUMN]
        )
        index_df = _support.dataframe_from_pandas(index_pdf)
        ds_meta = _dataset_meta_from_spectra(spectra)
        dataset = _support.build_spectral_dataset(index_df, spectra_df, meta=ds_meta)
        return {"dataset": Collection(items=cast(list[DataObject], [dataset]), item_type=SpectralDataset)}


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
        block = "SpectralDatasetToSpectrum"
        dataset = _support.coerce_dataset(inputs.get("dataset"), block=block, port="dataset")
        index_tbl, spectra_tbl = _support.dataset_frames(dataset)
        index_pdf = index_tbl.to_pandas()
        spectra_pdf = spectra_tbl.to_pandas()

        for required, table_name in ((SPECTRUM_ID_COLUMN, "index"),):
            if required not in index_pdf.columns:
                raise ValueError(f"{block}: {table_name} table missing required '{required}' column")
        for required in (SPECTRUM_ID_COLUMN, LAMBDA_COLUMN, INTENSITY_COLUMN):
            if required not in spectra_pdf.columns:
                raise ValueError(f"{block}: spectra table missing required '{required}' column")

        # Dataset-level unit/modality defaults carried onto each Spectrum.Meta
        # when the index row does not supply its own (FR-046).
        ds_meta = dataset.meta
        unit_defaults: dict[str, Any] = {}
        if isinstance(ds_meta, SpectralDataset.Meta):
            for field in ("lambda_unit", "intensity_unit", "modality"):
                value = getattr(ds_meta, field, None)
                if value is not None:
                    unit_defaults[field] = value

        grouped = {sid: group for sid, group in spectra_pdf.groupby(SPECTRUM_ID_COLUMN, sort=False)}

        spectra_out: list[Spectrum] = []
        for row in index_pdf.to_dict(orient="records"):
            sid = row[SPECTRUM_ID_COLUMN]
            group = grouped.get(sid)
            if group is None:
                # Index row with no spectra rows: emit an empty-grid spectrum so
                # the id/metadata still round-trips (FR-045).
                lam: list[float] = []
                inten: list[float] = []
            else:
                lam = group[LAMBDA_COLUMN].to_numpy(dtype=float).tolist()
                inten = group[INTENSITY_COLUMN].to_numpy(dtype=float).tolist()
            meta, user = _split_index_row(row, unit_defaults)
            spectra_out.append(_support.build_spectrum(lam, inten, meta=meta, user=user or None, spectrum_id=sid))

        return {"spectra": _support.spectra_collection(spectra_out)}


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
        block = "FilterSpectralDataset"
        dataset = _support.coerce_dataset(inputs.get("dataset"), block=block, port="dataset")
        index_tbl, spectra_tbl = _support.dataset_frames(dataset)
        index_pdf = index_tbl.to_pandas()
        spectra_pdf = spectra_tbl.to_pandas()
        if SPECTRUM_ID_COLUMN not in index_pdf.columns:
            raise ValueError(f"{block}: index table missing required '{SPECTRUM_ID_COLUMN}' column")

        predicates = _normalise_predicates(config.get("predicates"), block)

        # Evaluate each predicate against the index table (AND semantics).
        # Coordinates/intensities/units are never touched (FR-048).
        mask = [True] * len(index_pdf)
        for pred in predicates:
            column = pred["column"]
            if column not in index_pdf.columns:
                raise ValueError(f"{block}: unknown predicate column {column!r}")
            mask = [keep and ok for keep, ok in zip(mask, _eval_predicate(index_pdf[column], pred), strict=True)]

        kept_index = index_pdf[mask]
        kept_ids = set(kept_index[SPECTRUM_ID_COLUMN].tolist())
        kept_spectra = spectra_pdf[spectra_pdf[SPECTRUM_ID_COLUMN].isin(kept_ids)]

        index_df = _support.dataframe_from_pandas(kept_index.reset_index(drop=True))
        spectra_df = _support.dataframe_from_pandas(kept_spectra.reset_index(drop=True))
        filtered = _support.build_spectral_dataset(index_df, spectra_df, meta=_clone_dataset_meta(dataset.meta))
        return {"dataset": Collection(items=cast(list[DataObject], [filtered]), item_type=SpectralDataset)}


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
        block = "MergeSpectralDataset"
        datasets = _coerce_datasets(inputs.get("datasets"), block)
        policy = str(config.get("duplicate_id_policy", "error"))
        if policy not in {"error", "prefix", "remap"}:
            raise ValueError(
                f"{block}: duplicate_id_policy must be one of ['error', 'prefix', 'remap'], got {policy!r}"
            )

        import pandas as pd

        # Refuse silent unit reconciliation across datasets (FR-051).
        _check_unit_compatibility(datasets, block)

        index_parts: list[Any] = []
        spectra_parts: list[Any] = []
        seen_ids: set[str] = set()
        for position, dataset in enumerate(datasets):
            index_tbl, spectra_tbl = _support.dataset_frames(dataset)
            index_pdf = index_tbl.to_pandas()
            spectra_pdf = spectra_tbl.to_pandas()
            if SPECTRUM_ID_COLUMN not in index_pdf.columns:
                raise ValueError(f"{block}: index table missing required '{SPECTRUM_ID_COLUMN}' column")

            ids = [str(v) for v in index_pdf[SPECTRUM_ID_COLUMN].tolist()]
            duplicates = [sid for sid in ids if sid in seen_ids]
            id_map: dict[str, str] = {}
            if duplicates:
                if policy == "error":
                    raise ValueError(
                        f"{block}: duplicate spectrum_id across inputs {sorted(set(duplicates))!r}; "
                        "set duplicate_id_policy to 'prefix' or 'remap'"
                    )
                id_map = _build_id_map(ids, seen_ids, policy, position)

            if id_map:
                index_pdf = index_pdf.copy()
                spectra_pdf = spectra_pdf.copy()
                index_pdf[SPECTRUM_ID_COLUMN] = [id_map.get(str(v), str(v)) for v in index_pdf[SPECTRUM_ID_COLUMN]]
                spectra_pdf[SPECTRUM_ID_COLUMN] = [id_map.get(str(v), str(v)) for v in spectra_pdf[SPECTRUM_ID_COLUMN]]

            seen_ids.update(str(v) for v in index_pdf[SPECTRUM_ID_COLUMN].tolist())
            index_parts.append(index_pdf)
            spectra_parts.append(spectra_pdf)

        merged_index = pd.concat(index_parts, ignore_index=True, sort=False)
        merged_spectra = pd.concat(spectra_parts, ignore_index=True, sort=False)
        index_df = _support.dataframe_from_pandas(merged_index)
        spectra_df = _support.dataframe_from_pandas(merged_spectra)
        merged = _support.build_spectral_dataset(index_df, spectra_df, meta=_clone_dataset_meta(datasets[0].meta))
        return {"dataset": Collection(items=cast(list[DataObject], [merged]), item_type=SpectralDataset)}


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
        block = "AttachFeaturesToSpectralDataset"
        dataset = _support.coerce_dataset(inputs.get("dataset"), block=block, port="dataset")
        features = _support.coerce_dataframe(inputs.get("features"), block=block, port="features")
        join_key = str(config.get("join_key", SPECTRUM_ID_COLUMN))
        conflict_policy = str(config.get("conflict_policy", "error"))
        if conflict_policy not in {"error", "prefix", "suffix", "replace"}:
            raise ValueError(
                f"{block}: conflict_policy must be one of ['error', 'prefix', 'suffix', 'replace'], "
                f"got {conflict_policy!r}"
            )

        index_tbl, spectra_tbl = _support.dataset_frames(dataset)
        index_pdf = index_tbl.to_pandas()
        feat_pdf = _support.dataframe_pandas(features)

        if join_key not in index_pdf.columns:
            raise ValueError(f"{block}: index table missing join key {join_key!r}")
        if join_key not in feat_pdf.columns:
            raise ValueError(f"{block}: features table missing join key {join_key!r}")

        # Reject Spectrum/object cells in the feature table (FR-083).
        _reject_object_cells(feat_pdf, block)

        feat_cols = [c for c in feat_pdf.columns if c != join_key]
        existing = set(index_pdf.columns) - {join_key}
        collisions = [c for c in feat_cols if c in existing]

        rename: dict[str, str] = {}
        drop_existing: list[str] = []
        if collisions:
            if conflict_policy == "error":
                raise ValueError(
                    f"{block}: feature columns {sorted(collisions)!r} collide with existing index columns; "
                    "set conflict_policy to 'prefix', 'suffix', or 'replace'"
                )
            if conflict_policy == "prefix":
                rename = {c: f"feature_{c}" for c in collisions}
            elif conflict_policy == "suffix":
                rename = {c: f"{c}_feature" for c in collisions}
            elif conflict_policy == "replace":
                drop_existing = collisions

        feat_join = feat_pdf.rename(columns=rename)
        index_join = index_pdf.drop(columns=drop_existing) if drop_existing else index_pdf
        merged = index_join.merge(feat_join, on=join_key, how="left")

        index_df = _support.dataframe_from_pandas(merged)
        # spectra slot is left untouched (FR-084).
        spectra_df = _support.dataframe_from_arrow(spectra_tbl)
        updated = _support.build_spectral_dataset(index_df, spectra_df, meta=_clone_dataset_meta(dataset.meta))
        return {"dataset": Collection(items=cast(list[DataObject], [updated]), item_type=SpectralDataset)}


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
