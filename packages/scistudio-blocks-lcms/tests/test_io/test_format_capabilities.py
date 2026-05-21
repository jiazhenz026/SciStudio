"""ADR-043 explicit format capability tests for LCMS IOBlocks."""

from __future__ import annotations

from scistudio_blocks_lcms.io.load_mid_table import LoadMIDTable
from scistudio_blocks_lcms.io.load_mzml_files import LoadMzMLFiles
from scistudio_blocks_lcms.io.load_peak_table import LoadPeakTable
from scistudio_blocks_lcms.io.load_sample_metadata import LoadSampleMetadata
from scistudio_blocks_lcms.io.save_table import SaveTable
from scistudio_blocks_lcms.types import MIDTable, MSRawFile, PeakTable, SampleMetadata

from scistudio.core.types.dataframe import DataFrame


def _ids(block: type) -> set[str]:
    capabilities = block.get_format_capabilities()
    assert all(not capability.is_synthesized for capability in capabilities)
    return {capability.id for capability in capabilities}


def test_load_mzml_files_declares_one_way_raw_capabilities() -> None:
    capabilities = {capability.id: capability for capability in LoadMzMLFiles.get_format_capabilities()}

    assert set(capabilities) == {
        "scistudio-blocks-lcms.ms_raw.mzml.load",
        "scistudio-blocks-lcms.ms_raw.mzxml.load",
        "scistudio-blocks-lcms.ms_raw.raw.load",
        "scistudio-blocks-lcms.ms_raw.d.load",
    }
    assert all(not capability.is_synthesized for capability in capabilities.values())
    assert all(capability.direction == "load" for capability in capabilities.values())
    assert all(capability.data_type is MSRawFile for capability in capabilities.values())
    assert all(capability.roundtrip_group is None for capability in capabilities.values())

    assert capabilities["scistudio-blocks-lcms.ms_raw.mzml.load"].metadata_fidelity.typed_meta_fields == (
        "format",
        "polarity",
        "instrument",
        "acquisition_date",
        "sample_id",
    )
    assert capabilities["scistudio-blocks-lcms.ms_raw.raw.load"].metadata_fidelity.typed_meta_fields == (
        "format",
        "sample_id",
    )


def test_lcms_table_loaders_declare_explicit_table_capabilities() -> None:
    assert _ids(LoadPeakTable) == {
        "scistudio-blocks-lcms.peak_table.csv.load",
        "scistudio-blocks-lcms.peak_table.tsv.load",
        "scistudio-blocks-lcms.peak_table.xlsx.load",
    }
    assert _ids(LoadMIDTable) == {
        "scistudio-blocks-lcms.mid_table.csv.load",
        "scistudio-blocks-lcms.mid_table.tsv.load",
        "scistudio-blocks-lcms.mid_table.xlsx.load",
    }
    assert _ids(LoadSampleMetadata) == {
        "scistudio-blocks-lcms.sample_metadata.csv.load",
        "scistudio-blocks-lcms.sample_metadata.tsv.load",
        "scistudio-blocks-lcms.sample_metadata.xlsx.load",
    }

    peak_csv = LoadPeakTable.get_format_capabilities()[0]
    assert peak_csv.data_type is PeakTable
    assert peak_csv.metadata_fidelity.level == "typed_meta"
    assert peak_csv.metadata_fidelity.typed_meta_fields == ("source", "polarity")

    mid_csv = LoadMIDTable.get_format_capabilities()[0]
    assert mid_csv.data_type is MIDTable
    assert mid_csv.metadata_fidelity.level == "typed_meta"
    assert mid_csv.metadata_fidelity.typed_meta_fields == (
        "tracer_atoms",
        "sample_columns",
        "corrected",
        "correction_tool",
    )

    metadata_csv = LoadSampleMetadata.get_format_capabilities()[0]
    assert metadata_csv.data_type is SampleMetadata
    assert metadata_csv.metadata_fidelity.level == "typed_meta"
    assert metadata_csv.metadata_fidelity.typed_meta_fields == ("sample_id_column",)


def test_save_table_declares_explicit_lossy_table_capabilities() -> None:
    capabilities = {capability.id: capability for capability in SaveTable.get_format_capabilities()}

    assert set(capabilities) == {
        "scistudio-blocks-lcms.table.csv.save",
        "scistudio-blocks-lcms.table.tsv.save",
        "scistudio-blocks-lcms.table.xlsx.save",
    }
    assert all(not capability.is_synthesized for capability in capabilities.values())
    assert all(capability.direction == "save" for capability in capabilities.values())
    assert all(capability.data_type is DataFrame for capability in capabilities.values())
    assert all(capability.metadata_fidelity.level == "pixel_only" for capability in capabilities.values())
    assert capabilities["scistudio-blocks-lcms.table.xlsx.save"].extensions == (".xlsx",)
