from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from scistudio_blocks_lcms.types import MIDTable, MSRawFile, PeakTable, SampleMetadata, get_types


def test_msrawfile_subclass_of_artifact() -> None:
    assert issubclass(MSRawFile, object)
    raw = MSRawFile(file_path=Path("sample.mzML"), meta=MSRawFile.Meta(format="mzML"))
    assert raw.meta.format == "mzML"


def test_msrawfile_meta_frozen() -> None:
    meta = MSRawFile.Meta(format="mzML")
    with pytest.raises(ValidationError):
        meta.format = "raw"  # type: ignore[misc]


def test_msrawfile_meta_required_format() -> None:
    with pytest.raises(ValidationError):
        MSRawFile.Meta()


def test_get_types_returns_all_four_classes() -> None:
    assert get_types() == [MSRawFile, PeakTable, MIDTable, SampleMetadata]


@pytest.mark.parametrize(
    ("cls", "instance", "field", "updated_value"),
    [
        (
            MSRawFile,
            MSRawFile(
                file_path=Path("sample.mzML"),
                mime_type="application/x-mzml+xml",
                description="sample",
                meta=MSRawFile.Meta(format="mzML", sample_id="sample"),
            ),
            "sample_id",
            "sample_b",
        ),
        (
            PeakTable,
            PeakTable(
                columns=["compound", "intensity"],
                row_count=1,
                schema={"compound": "object", "intensity": "float64"},
                meta=PeakTable.Meta(source="ElMAVEN", polarity="+"),
            ),
            "source",
            "XCMS",
        ),
        (
            MIDTable,
            MIDTable(
                columns=["Compound", "C13", "S1"],
                row_count=1,
                schema={"Compound": "object", "C13": "int64", "S1": "float64"},
                meta=MIDTable.Meta(sample_columns=["S1"]),
            ),
            "correction_tool",
            "Manual",
        ),
        (
            SampleMetadata,
            SampleMetadata(
                columns=["sample_id", "group"],
                row_count=1,
                schema={"sample_id": "object", "group": "object"},
                meta=SampleMetadata.Meta(sample_id_column="sample_id"),
            ),
            "sample_id_column",
            "sample",
        ),
    ],
)
def test_types_round_trip_with_meta(cls: type, instance: object, field: str, updated_value: object) -> None:
    updated = instance.with_meta(**{field: updated_value})
    assert isinstance(updated, cls)
    assert getattr(updated.meta, field) == updated_value


@pytest.mark.parametrize(
    "meta",
    [
        MSRawFile.Meta(format="mzML", polarity="+", instrument="QE", sample_id="S1"),
        PeakTable.Meta(source="ElMAVEN", polarity="-"),
        MIDTable.Meta(tracer_atoms=["C13", "H2"], sample_columns=["S1", "S2"]),
        SampleMetadata.Meta(sample_id_column="sample_id"),
    ],
)
def test_meta_json_round_trip(meta: object) -> None:
    encoded = meta.model_dump_json()
    restored = type(meta).model_validate_json(encoded)
    assert restored == meta


def test_no_forbidden_scan_level_types_added() -> None:
    import scistudio_blocks_lcms.types as module

    assert not hasattr(module, "MSSpectrum")
    assert not hasattr(module, "MSRun")
