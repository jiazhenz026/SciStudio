"""Tests for ``SaveData`` (T-TRK-008, ADR-028 Addendum 1 §C5/§C9).

These tests cover the canonical core IO output block:

* Instantiation with each of the six ``core_type`` enum values.
* ``get_effective_input_ports()`` returning the correct
  ``InputPort.accepted_types`` for each enum value.
* End-to-end **round-trip** for each of the six core types via a
  ``tmp_path`` fixture: write the file via :class:`SaveData`, then
  read it back via the same library that wrote it (pyarrow / numpy /
  json / pickle / zarr) and assert equality on the recovered content.
  We do **not** depend on :class:`LoadData` (T-TRK-007) being landed
  yet — round-trip uses the underlying lib directly.
* ``allow_pickle=False`` rejects ``.pkl`` / ``.pickle`` writes with
  a clear ``ValueError``.
* ``allow_pickle=True`` writes pickle files and emits an explicit
  security warning at WARNING level.
* Mixed-type Collection raises (spec §j out-of-scope rule).
* Missing / unknown ``core_type`` raises.
* :meth:`SaveData.load` raises :class:`NotImplementedError` (output-only).
"""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.csv as pcsv
import pyarrow.parquet as pq
import pytest

from scistudio.blocks.io import SaveData
from scistudio.blocks.io.savers.save_data import _CORE_TYPE_MAP
from scistudio.core.meta.framework import FrameworkMeta
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

# ---------------------------------------------------------------------------
# Class-level shape tests
# ---------------------------------------------------------------------------


class TestSaveDataClassShape:
    """ADR-028 Addendum 1 §C5 / §C9: SaveData class-level invariants."""

    def test_direction_is_output(self) -> None:
        assert SaveData.direction == "output"

    def test_type_name_is_save_data(self) -> None:
        assert SaveData.type_name == "save_data"

    def test_subcategory_is_io(self) -> None:
        assert SaveData.subcategory == "io"

    def test_input_ports_have_one_data_port(self) -> None:
        assert len(SaveData.input_ports) == 1
        assert SaveData.input_ports[0].name == "data"
        assert SaveData.input_ports[0].required is True

    def test_no_output_ports(self) -> None:
        assert SaveData.output_ports == []

    def test_dynamic_ports_uses_input_port_mapping(self) -> None:
        """Per spec §C5: SaveData uses ``input_port_mapping``, not
        ``output_port_mapping`` (which belongs to LoadData)."""
        descriptor = SaveData.dynamic_ports
        assert descriptor is not None
        assert descriptor["source_config_key"] == "core_type"
        assert "input_port_mapping" in descriptor
        assert "output_port_mapping" not in descriptor
        mapping = descriptor["input_port_mapping"]
        assert set(mapping["data"].keys()) == set(_CORE_TYPE_MAP.keys())

    def test_core_type_map_has_six_entries(self) -> None:
        """The hardcoded _CORE_TYPE_MAP must contain exactly the six
        core DataObject types per ADR-027 D2."""
        assert set(_CORE_TYPE_MAP.keys()) == {
            "Array",
            "DataFrame",
            "Series",
            "Text",
            "Artifact",
            "CompositeData",
        }
        assert _CORE_TYPE_MAP["Array"] is Array
        assert _CORE_TYPE_MAP["DataFrame"] is DataFrame
        assert _CORE_TYPE_MAP["Series"] is Series
        assert _CORE_TYPE_MAP["Text"] is Text
        assert _CORE_TYPE_MAP["Artifact"] is Artifact
        assert _CORE_TYPE_MAP["CompositeData"] is CompositeData

    def test_config_schema_required_fields(self) -> None:
        # ADR-030: ``path`` is now inherited from IOBlock via MRO merge,
        # so ``required`` on the SaveData class-level schema only lists ``core_type``.
        schema = SaveData.config_schema
        assert schema["required"] == ["core_type"]
        assert schema["properties"]["core_type"]["default"] == "DataFrame"
        assert "allow_pickle" not in schema["properties"]
        # core_type enum exposes all six core types.
        assert set(schema["properties"]["core_type"]["enum"]) == set(_CORE_TYPE_MAP.keys())


# ---------------------------------------------------------------------------
# get_effective_input_ports parametrized over each core type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("core_type", "expected_cls"),
    [
        ("Array", Array),
        ("DataFrame", DataFrame),
        ("Series", Series),
        ("Text", Text),
        ("Artifact", Artifact),
        ("CompositeData", CompositeData),
    ],
)
def test_save_data_instantiates_with_each_core_type(
    core_type: str, expected_cls: type[DataObject], tmp_path: Path
) -> None:
    """SaveData can be instantiated with each of the six core_type enum
    values, and ``get_effective_input_ports()`` returns the correct
    accepted_types for each enum value."""
    block = SaveData(config={"params": {"core_type": core_type, "path": str(tmp_path / "out.bin")}})
    effective = block.get_effective_input_ports()
    assert len(effective) == 1
    port = effective[0]
    assert port.name == "data"
    assert port.required is True
    assert port.accepted_types == [expected_cls]


def test_get_effective_input_ports_falls_back_to_dataframe_for_unknown(
    tmp_path: Path,
) -> None:
    """An unknown ``core_type`` value falls back to DataFrame (the
    documented default in config_schema)."""
    block = SaveData(config={"params": {"core_type": "NotAType", "path": str(tmp_path / "out.bin")}})
    effective = block.get_effective_input_ports()
    assert effective[0].accepted_types == [DataFrame]


# ---------------------------------------------------------------------------
# Round-trip tests for each core type
# ---------------------------------------------------------------------------


def _make_arrow_table() -> pa.Table:
    return pa.table({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})


def _make_dataframe(**kwargs: object) -> DataFrame:
    """Build a DataFrame DataObject with an in-memory _arrow_table."""
    table = _make_arrow_table()
    df = DataFrame(columns=table.column_names, row_count=table.num_rows, **kwargs)
    df._arrow_table = table  # type: ignore[attr-defined]
    return df


class TestRoundTripDataFrame:
    """SaveData → file → manual read round-trip for DataFrame."""

    def test_dataframe_round_trip_csv(self, tmp_path: Path) -> None:
        path = tmp_path / "df.csv"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path)}})
        df = _make_dataframe()
        block.save(df, block.config)

        assert path.exists()
        recovered = pcsv.read_csv(str(path))
        assert recovered.column_names == ["x", "y"]
        assert recovered.to_pydict() == {"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}

    def test_dataframe_round_trip_tsv(self, tmp_path: Path) -> None:
        path = tmp_path / "df.tsv"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path)}})
        block.save(_make_dataframe(), block.config)

        assert path.exists()
        # pyarrow reads TSV via the parse_options delimiter argument.
        recovered = pcsv.read_csv(
            str(path),
            parse_options=pcsv.ParseOptions(delimiter="\t"),
        )
        assert recovered.column_names == ["x", "y"]

    def test_dataframe_path_without_extension_defaults_to_csv(self, tmp_path: Path) -> None:
        path = tmp_path / "df"
        expected = tmp_path / "df.csv"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path)}})
        block.save(_make_dataframe(), block.config)

        assert expected.exists()
        assert block.config.get("path") == str(expected)
        recovered = pcsv.read_csv(str(expected))
        assert recovered.column_names == ["x", "y"]

    def test_dataframe_directory_path_uses_source_filename(self, tmp_path: Path) -> None:
        source = tmp_path / "input.tsv"
        expected = tmp_path / "input.csv"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(tmp_path)}})
        block.save(_make_dataframe(framework=FrameworkMeta(source=str(source))), block.config)

        assert expected.exists()
        assert block.config.get("path") == str(expected)
        recovered = pcsv.read_csv(str(expected))
        assert recovered.column_names == ["x", "y"]

    def test_dataframe_directory_path_refuses_existing_source_file(self, tmp_path: Path) -> None:
        source = tmp_path / "input.csv"
        expected = tmp_path / "input.csv"
        expected.write_text("existing\n", encoding="utf-8")
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(tmp_path)}})

        with pytest.raises(ValueError, match="refuses to overwrite existing output"):
            block.save(_make_dataframe(framework=FrameworkMeta(source=str(source))), block.config)

        assert expected.read_text(encoding="utf-8") == "existing\n"

    def test_dataframe_directory_path_can_overwrite_when_explicit(self, tmp_path: Path) -> None:
        source = tmp_path / "input.csv"
        expected = tmp_path / "input.csv"
        expected.write_text("existing\n", encoding="utf-8")
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(tmp_path), "overwrite": True}})
        block.save(_make_dataframe(framework=FrameworkMeta(source=str(source))), block.config)

        recovered = pcsv.read_csv(str(expected))
        assert recovered.column_names == ["x", "y"]

    def test_dataframe_path_without_extension_uses_explicit_tsv_format(self, tmp_path: Path) -> None:
        path = tmp_path / "df"
        expected = tmp_path / "df.tsv"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path), "format": "tsv"}})
        block.save(_make_dataframe(), block.config)

        assert expected.exists()
        assert block.config.get("path") == str(expected)
        recovered = pcsv.read_csv(
            str(expected),
            parse_options=pcsv.ParseOptions(delimiter="\t"),
        )
        assert recovered.column_names == ["x", "y"]

    def test_dataframe_directory_path_uses_explicit_tsv_format(self, tmp_path: Path) -> None:
        source = tmp_path / "input.csv"
        expected = tmp_path / "input.tsv"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(tmp_path), "format": "tsv"}})
        block.save(_make_dataframe(framework=FrameworkMeta(source=str(source))), block.config)

        assert expected.exists()
        assert block.config.get("path") == str(expected)
        recovered = pcsv.read_csv(
            str(expected),
            parse_options=pcsv.ParseOptions(delimiter="\t"),
        )
        assert recovered.column_names == ["x", "y"]

    def test_dataframe_path_without_extension_uses_capability_id(self, tmp_path: Path) -> None:
        path = tmp_path / "df"
        expected = tmp_path / "df.tsv"
        block = SaveData(
            config={
                "params": {
                    "core_type": "DataFrame",
                    "path": str(path),
                    "capability_id": "core.dataframe.tsv.save",
                }
            }
        )
        block.save(_make_dataframe(), block.config)

        assert expected.exists()
        assert block.config.get("path") == str(expected)

    def test_dataframe_round_trip_parquet(self, tmp_path: Path) -> None:
        path = tmp_path / "df.parquet"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path)}})
        block.save(_make_dataframe(), block.config)

        assert path.exists()
        recovered = pq.read_table(str(path))
        assert recovered.column_names == ["x", "y"]
        assert recovered.to_pydict() == {"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}

    def test_dataframe_round_trip_json(self, tmp_path: Path) -> None:
        path = tmp_path / "df.json"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path)}})
        block.save(_make_dataframe(), block.config)

        assert path.exists()
        recovered = json.loads(path.read_text(encoding="utf-8"))
        assert recovered == [
            {"x": 1, "y": 4.0},
            {"x": 2, "y": 5.0},
            {"x": 3, "y": 6.0},
        ]

    def test_dataframe_unsupported_extension_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "df.weird"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path)}})
        with pytest.raises(ValueError, match="Unsupported DataFrame file extension"):
            block.save(_make_dataframe(), block.config)


class TestRoundTripArray:
    """SaveData → file → manual read round-trip for Array."""

    def _make_1d_array(self) -> Array:
        arr = Array(axes=["x"], shape=(5,), dtype=np.dtype("float64"))
        arr._data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])  # type: ignore[attr-defined]
        return arr

    def _make_2d_array(self) -> Array:
        arr = Array(axes=["y", "x"], shape=(2, 3), dtype=np.dtype("int64"))
        arr._data = np.array([[1, 2, 3], [4, 5, 6]])  # type: ignore[attr-defined]
        return arr

    def test_array_round_trip_npy(self, tmp_path: Path) -> None:
        path = tmp_path / "arr.npy"
        block = SaveData(config={"params": {"core_type": "Array", "path": str(path)}})
        block.save(self._make_2d_array(), block.config)

        assert path.exists()
        recovered = np.load(str(path))
        np.testing.assert_array_equal(recovered, np.array([[1, 2, 3], [4, 5, 6]]))

    def test_array_round_trip_npz(self, tmp_path: Path) -> None:
        path = tmp_path / "arr.npz"
        block = SaveData(config={"params": {"core_type": "Array", "path": str(path)}})
        block.save(self._make_2d_array(), block.config)

        assert path.exists()
        with np.load(str(path)) as recovered:
            np.testing.assert_array_equal(recovered["data"], np.array([[1, 2, 3], [4, 5, 6]]))

    def test_array_round_trip_parquet_1d(self, tmp_path: Path) -> None:
        path = tmp_path / "arr.parquet"
        block = SaveData(config={"params": {"core_type": "Array", "path": str(path)}})
        block.save(self._make_1d_array(), block.config)

        assert path.exists()
        table = pq.read_table(str(path))
        assert table.column_names == ["value"]
        assert table.to_pydict()["value"] == [1.0, 2.0, 3.0, 4.0, 5.0]

    def test_array_parquet_rejects_2d(self, tmp_path: Path) -> None:
        path = tmp_path / "arr.parquet"
        block = SaveData(config={"params": {"core_type": "Array", "path": str(path)}})
        with pytest.raises(ValueError, match="single-column Parquet"):
            block.save(self._make_2d_array(), block.config)

    def test_array_round_trip_zarr(self, tmp_path: Path) -> None:
        zarr = pytest.importorskip("zarr")
        path = tmp_path / "arr.zarr"
        block = SaveData(config={"params": {"core_type": "Array", "path": str(path)}})
        block.save(self._make_2d_array(), block.config)

        assert path.exists()
        recovered = zarr.load(str(path))
        np.testing.assert_array_equal(recovered, np.array([[1, 2, 3], [4, 5, 6]]))


class TestRoundTripSeries:
    """SaveData → file → manual read round-trip for Series."""

    def _make_series(self) -> Series:
        s = Series(
            index_name="time",
            value_name="intensity",
            length=4,
        )
        s._data = [10.0, 20.0, 30.0, 40.0]  # type: ignore[attr-defined]
        return s

    def test_series_round_trip_csv(self, tmp_path: Path) -> None:
        path = tmp_path / "s.csv"
        block = SaveData(config={"params": {"core_type": "Series", "path": str(path)}})
        block.save(self._make_series(), block.config)

        assert path.exists()
        recovered = pcsv.read_csv(str(path))
        assert recovered.column_names == ["intensity"]
        assert recovered.to_pydict() == {"intensity": [10.0, 20.0, 30.0, 40.0]}

    def test_series_round_trip_parquet(self, tmp_path: Path) -> None:
        path = tmp_path / "s.parquet"
        block = SaveData(config={"params": {"core_type": "Series", "path": str(path)}})
        block.save(self._make_series(), block.config)

        recovered = pq.read_table(str(path))
        assert recovered.column_names == ["intensity"]


class TestRoundTripText:
    """SaveData → file → manual read round-trip for Text."""

    def test_text_round_trip_txt(self, tmp_path: Path) -> None:
        path = tmp_path / "doc.txt"
        block = SaveData(config={"params": {"core_type": "Text", "path": str(path)}})
        text = Text(content="hello\nworld\n", format="plain")
        block.save(text, block.config)

        assert path.exists()
        assert path.read_text(encoding="utf-8") == "hello\nworld\n"

    @pytest.mark.parametrize(
        "ext",
        [
            ".txt",
            ".md",
            ".markdown",
            ".html",
            ".htm",
            ".xml",
            ".log",
            ".yaml",
            ".toml",
            ".json",
        ],
    )
    def test_text_round_trip_supported_extensions(self, tmp_path: Path, ext: str) -> None:
        path = tmp_path / f"doc{ext}"
        block = SaveData(config={"params": {"core_type": "Text", "path": str(path)}})
        text = Text(content="payload", format="plain")
        block.save(text, block.config)
        assert path.read_text(encoding="utf-8") == "payload"

    def test_text_capability_advertises_markdown_and_htm(self) -> None:
        """#1110: ``.markdown`` and ``.htm`` are accepted by ``_save_text``
        and must be advertised by the Text save capability so
        ``find_saver_capability`` can discover SaveData for those paths.
        """
        from scistudio.blocks.io.savers.save_data import _SAVE_EXTENSION_MAP

        text_extensions = {
            ext
            for capability in SaveData.format_capabilities
            if capability.data_type is Text and capability.format_id == "text"
            for ext in capability.extensions
        }
        assert text_extensions == {
            ".txt",
            ".log",
            ".md",
            ".markdown",
            ".html",
            ".htm",
            ".xml",
            ".yaml",
            ".yml",
            ".toml",
        }
        # Capability-derived extension map must include the new entries
        # so extension-based dispatch / discovery picks them up.
        for ext in (".markdown", ".htm"):
            assert _SAVE_EXTENSION_MAP[ext] == "text"

    def test_text_unsupported_extension_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "doc.weird"
        block = SaveData(config={"params": {"core_type": "Text", "path": str(path)}})
        with pytest.raises(ValueError, match="Unsupported Text file extension"):
            block.save(Text(content="x"), block.config)

    def test_text_with_none_content_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "doc.txt"
        block = SaveData(config={"params": {"core_type": "Text", "path": str(path)}})
        with pytest.raises(ValueError, match="content=None"):
            block.save(Text(content=None), block.config)


class TestRoundTripArtifact:
    """SaveData → file → manual read round-trip for Artifact (raw bytes + sidecar)."""

    def test_artifact_round_trip_bin_via_in_memory_bytes(self, tmp_path: Path) -> None:
        path = tmp_path / "blob.bin"
        block = SaveData(config={"params": {"core_type": "Artifact", "path": str(path)}})

        # Build an Artifact with no file_path; we override
        # get_in_memory_data to return the bytes directly.
        class _ByteArtifact(Artifact):
            def get_in_memory_data(self) -> bytes:
                return b"\x00\x01\x02\x03"

        artifact = _ByteArtifact(mime_type="application/octet-stream", description="test")
        block.save(artifact, block.config)

        assert path.exists()
        assert path.read_bytes() == b"\x00\x01\x02\x03"

        sidecar = path.with_suffix(path.suffix + ".meta.json")
        assert sidecar.exists()
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        assert meta["mime_type"] == "application/octet-stream"
        assert meta["description"] == "test"

    def test_artifact_round_trip_via_existing_file_path(self, tmp_path: Path) -> None:
        # Source file we will copy via the Artifact.file_path branch.
        source = tmp_path / "src.bin"
        source.write_bytes(b"copied bytes")

        path = tmp_path / "out" / "dest.bin"
        block = SaveData(config={"params": {"core_type": "Artifact", "path": str(path)}})
        artifact = Artifact(file_path=source, mime_type="application/octet-stream")
        block.save(artifact, block.config)

        assert path.exists()
        assert path.read_bytes() == b"copied bytes"

        sidecar = path.with_suffix(path.suffix + ".meta.json")
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        assert meta["original_file_path"] == str(source)


class TestRoundTripCompositeData:
    """SaveData → manifest + sidecars round-trip for CompositeData."""

    def test_composite_data_round_trip_manifest(self, tmp_path: Path) -> None:
        path = tmp_path / "comp.json"
        block = SaveData(config={"params": {"core_type": "CompositeData", "path": str(path)}})

        # Build a CompositeData with two slots: a Text and a DataFrame.
        text = Text(content="readme content", format="plain")
        df = _make_dataframe()
        comp = CompositeData(slots={"readme": text, "table": df})
        block.save(comp, block.config)

        assert path.exists()
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["kind"] == "CompositeData"
        assert manifest["version"] == 1
        assert set(manifest["slots"].keys()) == {"readme", "table"}
        assert manifest["slots"]["readme"]["core_type"] == "Text"
        assert manifest["slots"]["table"]["core_type"] == "DataFrame"

        # The sidecar files exist on disk and round-trip via their
        # underlying libraries.
        slots_dir = path.parent / f"{path.stem}_slots"
        assert slots_dir.is_dir()
        readme_path = slots_dir / "readme.txt"
        assert readme_path.read_text(encoding="utf-8") == "readme content"
        table_path = slots_dir / "table.csv"
        recovered = pcsv.read_csv(str(table_path))
        assert recovered.column_names == ["x", "y"]

    def test_composite_data_requires_json_extension(self, tmp_path: Path) -> None:
        path = tmp_path / "comp.bin"
        block = SaveData(config={"params": {"core_type": "CompositeData", "path": str(path)}})
        comp = CompositeData(slots={"x": Text(content="hi")})
        with pytest.raises(ValueError, match=r"must use the \.json extension"):
            block.save(comp, block.config)


# ---------------------------------------------------------------------------
# allow_pickle gating
# ---------------------------------------------------------------------------


class TestAllowPickleGate:
    """Pickle writes are opt-in via the ``allow_pickle`` config flag."""

    def test_allow_pickle_false_rejects_pkl(self, tmp_path: Path) -> None:
        path = tmp_path / "df.pkl"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path)}})
        with pytest.raises(ValueError, match="pickle is opt-in"):
            block.save(_make_dataframe(), block.config)
        assert not path.exists()

    def test_allow_pickle_true_writes_pkl_with_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        path = tmp_path / "df.pkl"
        block = SaveData(
            config={
                "params": {
                    "core_type": "DataFrame",
                    "path": str(path),
                    "allow_pickle": True,
                }
            }
        )
        with caplog.at_level(logging.WARNING, logger="scistudio.blocks.io.savers.save_data"):
            block.save(_make_dataframe(), block.config)

        assert path.exists()
        # Pickle round-trip recovers a pyarrow Table whose contents
        # match the original.
        with path.open("rb") as fh:
            recovered = pickle.load(fh)
        assert isinstance(recovered, pa.Table)
        assert recovered.to_pydict() == {"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}

        # The security warning was emitted.
        assert any("pickle" in rec.message.lower() for rec in caplog.records)

    def test_allow_pickle_false_rejects_pickle_extension(self, tmp_path: Path) -> None:
        path = tmp_path / "df.pickle"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path)}})
        with pytest.raises(ValueError, match="pickle is opt-in"):
            block.save(_make_dataframe(), block.config)


# ---------------------------------------------------------------------------
# Mixed-type Collection rejection (spec §j out-of-scope rule)
# ---------------------------------------------------------------------------


class TestMixedTypeRejection:
    """Per spec §j: Collections of mixed types must raise."""

    def test_mixed_type_collection_raises(self, tmp_path: Path) -> None:
        """SaveData(core_type=DataFrame) given a Collection containing
        a Text item must raise (mixed-type Collection rejection)."""
        path = tmp_path / "df.csv"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path)}})
        # Note: Collection itself enforces a single item_type at
        # construction, so the only way to get mixed types into
        # SaveData.save is to pass a Collection whose item_type does
        # not match the SaveData core_type. We do that here.
        text_collection = Collection(items=[Text(content="hello")], item_type=Text)
        with pytest.raises(ValueError, match="Collection item of type Text"):
            block.save(text_collection, block.config)

    def test_multi_item_collection_writes_one_file_per_item(self, tmp_path: Path) -> None:
        """A Collection of >1 same-type items writes a batch of files."""
        block = SaveData(
            config={
                "params": {
                    "core_type": "DataFrame",
                    "path": str(tmp_path),
                    "capability_id": "core.dataframe.tsv.save",
                }
            }
        )
        df1 = _make_dataframe(framework=FrameworkMeta(source=str(tmp_path / "first.csv")))
        df2 = _make_dataframe(framework=FrameworkMeta(source=str(tmp_path / "second.csv")))
        coll = Collection(items=[df1, df2], item_type=DataFrame)

        block.save(coll, block.config)

        assert (tmp_path / "first.tsv").exists()
        assert (tmp_path / "second.tsv").exists()

    def test_multi_item_collection_gui_filename_adds_index(self, tmp_path: Path) -> None:
        block = SaveData(
            config={
                "params": {
                    "core_type": "DataFrame",
                    "path": str(tmp_path),
                    "capability_id": "core.dataframe.csv.save",
                    "filename": "batch",
                }
            }
        )
        coll = Collection(items=[_make_dataframe(), _make_dataframe()], item_type=DataFrame)

        block.save(coll, block.config)

        assert (tmp_path / "batch-1.csv").exists()
        assert (tmp_path / "batch-2.csv").exists()

    def test_multi_item_collection_without_source_or_filename_raises(self, tmp_path: Path) -> None:
        block = SaveData(
            config={
                "params": {
                    "core_type": "DataFrame",
                    "path": str(tmp_path),
                    "capability_id": "core.dataframe.csv.save",
                }
            }
        )
        coll = Collection(items=[_make_dataframe(), _make_dataframe()], item_type=DataFrame)

        with pytest.raises(ValueError, match="no source filename"):
            block.save(coll, block.config)

    def test_empty_collection_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "df.csv"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path)}})
        coll = Collection(items=[], item_type=DataFrame)
        with pytest.raises(ValueError, match="empty Collection"):
            block.save(coll, block.config)

    def test_single_item_collection_unwraps_transparently(self, tmp_path: Path) -> None:
        path = tmp_path / "df.csv"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(path)}})
        df = _make_dataframe()
        coll = Collection(items=[df], item_type=DataFrame)
        # Must not raise — the single-item Collection is unwrapped.
        block.save(coll, block.config)
        assert path.exists()


class TestSaveDataFilename:
    def test_directory_target_uses_configured_filename(self, tmp_path: Path) -> None:
        block = SaveData(
            config={
                "params": {
                    "core_type": "DataFrame",
                    "path": str(tmp_path),
                    "capability_id": "core.dataframe.tsv.save",
                    "filename": "custom-name",
                }
            }
        )

        block.save(_make_dataframe(), block.config)

        assert (tmp_path / "custom-name.tsv").exists()

    def test_directory_target_uses_source_filename_when_filename_blank(self, tmp_path: Path) -> None:
        source = tmp_path / "input.csv"
        df = _make_dataframe(framework=FrameworkMeta(source=str(source)))
        block = SaveData(
            config={
                "params": {
                    "core_type": "DataFrame",
                    "path": str(tmp_path),
                    "capability_id": "core.dataframe.tsv.save",
                }
            }
        )

        block.save(df, block.config)

        assert (tmp_path / "input.tsv").exists()

    def test_directory_target_without_source_or_filename_raises(self, tmp_path: Path) -> None:
        block = SaveData(
            config={
                "params": {
                    "core_type": "DataFrame",
                    "path": str(tmp_path),
                    "capability_id": "core.dataframe.tsv.save",
                }
            }
        )

        with pytest.raises(ValueError, match="no source filename"):
            block.save(_make_dataframe(), block.config)

    def test_package_owned_capability_delegates_to_registered_saver(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCISTUDIO_DEV", "1")
        source = tmp_path / "input.csv"
        df = _make_dataframe(framework=FrameworkMeta(source=str(source)))
        block = SaveData(
            config={
                "params": {
                    "core_type": "DataFrame",
                    "path": str(tmp_path),
                    "capability_id": "scistudio-blocks-lcms.table.xlsx.save",
                }
            }
        )

        block.save(df, block.config)

        output = tmp_path / "input.xlsx"
        assert output.exists()
        import pandas as pd

        frame = pd.read_excel(output)
        assert list(frame.columns) == ["x", "y"]
        assert frame["x"].tolist() == [1, 2, 3]


# ---------------------------------------------------------------------------
# Misc dispatch / contract tests
# ---------------------------------------------------------------------------


class TestSaveDataDispatchContract:
    """Misc invariants on SaveData.save() and SaveData.load()."""

    def test_load_raises_not_implemented(self, tmp_path: Path) -> None:
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(tmp_path / "x")}})
        with pytest.raises(NotImplementedError, match="output-only"):
            block.load(block.config)

    def test_unknown_core_type_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "x.csv"
        block = SaveData(config={"params": {"core_type": "NotAType", "path": str(path)}})
        with pytest.raises(ValueError, match="Unknown core_type"):
            block.save(_make_dataframe(), block.config)

    def test_missing_path_raises(self) -> None:
        block = SaveData(config={"params": {"core_type": "DataFrame"}})
        with pytest.raises(ValueError, match="non-empty 'path'"):
            block.save(_make_dataframe(), block.config)

    def test_save_data_wrong_type_for_core_type_raises(self, tmp_path: Path) -> None:
        """SaveData(core_type=Array) given a DataFrame must raise."""
        path = tmp_path / "x.npy"
        block = SaveData(config={"params": {"core_type": "Array", "path": str(path)}})
        with pytest.raises(ValueError, match="must be a Array instance"):
            block.save(_make_dataframe(), block.config)


# ---------------------------------------------------------------------------
# ADR-031 Phase 3 (Task 18): Streaming export tests
# ---------------------------------------------------------------------------


def _make_storage_backed_array(tmp_path: Path, data: np.ndarray, axes: list[str]) -> Array:
    """Create a zarr-backed Array for testing streaming export."""
    import uuid

    import zarr

    from scistudio.core.storage.ref import StorageReference

    zarr_path = str(tmp_path / f"{uuid.uuid4()}.zarr")
    zarr.save(zarr_path, data)
    ref = StorageReference(
        backend="zarr",
        path=zarr_path,
        metadata={"shape": list(data.shape), "dtype": str(data.dtype)},
    )
    return Array(axes=axes, shape=data.shape, dtype=str(data.dtype), storage_ref=ref)


def _make_storage_backed_dataframe(tmp_path: Path) -> DataFrame:
    """Create an arrow-backed DataFrame for testing streaming export."""
    import uuid

    from scistudio.core.storage.ref import StorageReference

    table = _make_arrow_table()
    parquet_path = str(tmp_path / f"{uuid.uuid4()}.parquet")
    pq.write_table(table, parquet_path)
    ref = StorageReference(
        backend="arrow",
        path=parquet_path,
        format="parquet",
        metadata={"columns": table.column_names, "num_rows": table.num_rows},
    )
    return DataFrame(columns=table.column_names, row_count=table.num_rows, storage_ref=ref)


class TestStreamingExportZarrToZarr:
    """ADR-031 Phase 3: zarr-to-zarr copy via store copy (zero materialisation)."""

    def test_zarr_to_zarr_streaming_copy(self, tmp_path: Path) -> None:
        zarr = pytest.importorskip("zarr")
        data = np.array([[1, 2, 3], [4, 5, 6]], dtype="int64")
        arr = _make_storage_backed_array(tmp_path, data, ["y", "x"])

        out_path = tmp_path / "output.zarr"
        block = SaveData(config={"params": {"core_type": "Array", "path": str(out_path)}})
        block.save(arr, block.config)

        assert out_path.exists()
        recovered = zarr.load(str(out_path))
        np.testing.assert_array_equal(recovered, data)


class TestStreamingExportDataFrame:
    """ADR-031 Phase 3: streaming DataFrame export for CSV/TSV/Parquet."""

    def test_streaming_dataframe_csv(self, tmp_path: Path) -> None:
        df = _make_storage_backed_dataframe(tmp_path)
        out_path = tmp_path / "out.csv"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(out_path)}})
        block.save(df, block.config)

        assert out_path.exists()
        recovered = pcsv.read_csv(str(out_path))
        assert recovered.column_names == ["x", "y"]
        assert recovered.to_pydict() == {"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}

    def test_streaming_dataframe_tsv(self, tmp_path: Path) -> None:
        df = _make_storage_backed_dataframe(tmp_path)
        out_path = tmp_path / "out.tsv"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(out_path)}})
        block.save(df, block.config)

        assert out_path.exists()
        recovered = pcsv.read_csv(
            str(out_path),
            parse_options=pcsv.ParseOptions(delimiter="\t"),
        )
        assert recovered.column_names == ["x", "y"]

    def test_streaming_dataframe_parquet(self, tmp_path: Path) -> None:
        df = _make_storage_backed_dataframe(tmp_path)
        out_path = tmp_path / "out.parquet"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(out_path)}})
        block.save(df, block.config)

        assert out_path.exists()
        recovered = pq.read_table(str(out_path))
        assert recovered.column_names == ["x", "y"]
        assert recovered.to_pydict() == {"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}


# ---------------------------------------------------------------------------
# ADR-043 / spec ``adr-043-package-migration`` FR-003 (formerly issue #1074):
# the legacy ``supported_extensions`` ClassVar has been deleted on SaveData.
# Extension dispatch is derived from ``SaveData.format_capabilities`` at
# module load time and exposed via :data:`_SAVE_EXTENSION_MAP` and
# :func:`_supported_save_extensions`. Tests below assert the
# capability-derived contract mirrors LoadData's discoverable set.
# ---------------------------------------------------------------------------


class TestCapabilityDerivedExtensionDispatch:
    """SaveData derives the per-extension dispatch map from explicit
    :attr:`SaveData.format_capabilities` records (ADR-043 FR-002 / FR-003)
    instead of the deleted legacy ``supported_extensions`` ClassVar.
    The derived map MUST mirror :data:`LoadData._LOAD_EXTENSION_MAP` so
    a Load -> Save round-trip shares the same discoverable suffix set."""

    def test_extension_map_is_populated(self) -> None:
        """``_SAVE_EXTENSION_MAP`` is a non-empty derived dict."""
        from scistudio.blocks.io.savers.save_data import _SAVE_EXTENSION_MAP

        assert isinstance(_SAVE_EXTENSION_MAP, dict)
        assert len(_SAVE_EXTENSION_MAP) > 0

    def test_save_extension_map_mirrors_load(self) -> None:
        """``_SAVE_EXTENSION_MAP`` mirrors ``_LOAD_EXTENSION_MAP`` so Load -> Save round-trip
        keeps the same discoverable suffix set per spec FR-001 / FR-002."""
        from scistudio.blocks.io.loaders.load_data import _LOAD_EXTENSION_MAP
        from scistudio.blocks.io.savers.save_data import _SAVE_EXTENSION_MAP

        assert _SAVE_EXTENSION_MAP == _LOAD_EXTENSION_MAP, (
            "SaveData and LoadData capability-derived extension maps must mirror "
            "each other for round-trip discoverability per ADR-043 FR-001 / FR-002."
        )

    def test_extension_map_contains_array_extensions(self) -> None:
        from scistudio.blocks.io.savers.save_data import _SAVE_EXTENSION_MAP

        for ext in (".npy", ".npz", ".zarr", ".parquet", ".pq"):
            assert ext in _SAVE_EXTENSION_MAP, f"missing {ext!r}"

    def test_extension_map_contains_pickle_extensions(self) -> None:
        from scistudio.blocks.io.savers.save_data import _SAVE_EXTENSION_MAP

        for ext in (".pkl", ".pickle"):
            assert ext in _SAVE_EXTENSION_MAP, f"missing {ext!r}"

    def test_extension_map_contains_tabular_extensions(self) -> None:
        from scistudio.blocks.io.savers.save_data import _SAVE_EXTENSION_MAP

        for ext in (".csv", ".tsv", ".json"):
            assert ext in _SAVE_EXTENSION_MAP, f"missing {ext!r}"

    def test_extension_map_contains_text_extensions(self) -> None:
        from scistudio.blocks.io.savers.save_data import _SAVE_EXTENSION_MAP

        for ext in (".txt", ".md", ".html", ".xml", ".yaml", ".yml", ".toml", ".log"):
            assert ext in _SAVE_EXTENSION_MAP, f"missing {ext!r}"

    def test_detect_format_resolves_known_extensions(self, tmp_path: Path) -> None:
        block = SaveData(config={"params": {"core_type": "Array", "path": str(tmp_path / "x.npy")}})
        assert block._detect_format(tmp_path / "x.npy") == "npy"
        assert block._detect_format(tmp_path / "x.csv") == "csv"
        assert block._detect_format(tmp_path / "x.unknown") is None

    def test_unknown_extension_error_message_lists_supported_set(self, tmp_path: Path) -> None:
        """The ValueError on an unknown Array extension lists the
        sorted, capability-derived supported extension set."""
        import re

        from scistudio.blocks.io.savers.save_data import _supported_save_extensions

        arr = Array(axes=["x"], shape=(3,), dtype="float64")
        arr._data = np.array([1.0, 2.0, 3.0])  # type: ignore[attr-defined]
        out = tmp_path / "bogus.xyz"
        block = SaveData(config={"params": {"core_type": "Array", "path": str(out)}})
        with pytest.raises(ValueError) as excinfo:
            block.save(arr, block.config)
        msg = str(excinfo.value)
        for key in _supported_save_extensions(Array):
            assert re.search(re.escape(repr(key)), msg), f"missing {key!r} in error: {msg}"

    def test_unknown_extension_dataframe_error_lists_supported_set(self, tmp_path: Path) -> None:
        df = DataFrame(columns=["a"], row_count=2)
        df._arrow_table = pa.table({"a": [1, 2]})  # type: ignore[attr-defined]
        out = tmp_path / "bogus.xyz"
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(out)}})
        with pytest.raises(ValueError) as excinfo:
            block.save(df, block.config)
        msg = str(excinfo.value)
        assert ".csv" in msg
        assert ".tsv" in msg
        assert ".parquet" in msg

    def test_supported_extensions_inherits_empty_default_from_ioblock(self) -> None:
        """Per ADR-043 FR-003, the legacy ``supported_extensions`` ClassVar
        is removed from ``SaveData``; the base ``IOBlock`` default (empty
        dict) is now what an MRO lookup returns. The capability-derived
        mapping lives in :data:`_SAVE_EXTENSION_MAP` instead."""
        from scistudio.blocks.io.io_block import IOBlock
        from scistudio.blocks.io.savers.save_data import _SAVE_EXTENSION_MAP

        assert IOBlock.supported_extensions == {}
        # SaveData no longer overrides the ClassVar — the override has been
        # replaced by an explicit ``format_capabilities`` declaration.
        assert SaveData.supported_extensions is IOBlock.supported_extensions
        # The runtime dispatch map (derived from capabilities) is populated.
        assert len(_SAVE_EXTENSION_MAP) > 0
