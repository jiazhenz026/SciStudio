"""Core DataFrame/Series Excel (.xlsx) IO — multi-sheet fan-out + grouped save (#1810).

The :mod:`test_io_coverage_matrix` suite covers the single-object .xlsx
round-trip alongside the other formats. This module covers the .xlsx-specific
collection semantics that the matrix does not:

- reading an n-sheet workbook fans out into a Collection of n DataObjects, one
  per sheet, each carrying ``framework.source`` (the workbook) and
  ``user['sheet_name']`` / ``user['display_name']``;
- loading several multi-sheet files flattens every sheet into one Collection;
- saving a Collection groups by source workbook: each source file -> one
  multi-sheet workbook; source-less items -> one workbook (owner decision);
- Series sheets; the Excel row/column overflow guard.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import interactive_item_label
from scistudio.blocks.io.loaders.load_data import LoadData
from scistudio.blocks.io.savers._helpers import _check_xlsx_dimensions
from scistudio.blocks.io.savers.save_data import SaveData
from scistudio.core.types.collection import Collection


def _write_workbook(path: Path, sheets: dict[str, dict[str, list]]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, cols in sheets.items():
            pd.DataFrame(cols).to_excel(writer, sheet_name=name, index=False)


def _load(paths, core_type: str, output_dir: Path):
    raw = [str(p) for p in paths] if isinstance(paths, list) else str(paths)
    params = {"core_type": core_type, "path": raw}
    return LoadData(config={"params": params}).load(BlockConfig(params=params), output_dir=str(output_dir))


def test_single_multisheet_file_fans_out_into_a_collection(tmp_path: Path) -> None:
    _write_workbook(
        tmp_path / "exp.xlsx",
        {"alpha": {"a": [1, 2], "b": [3, 4]}, "beta": {"a": [5], "b": [6]}},
    )
    out = _load(tmp_path / "exp.xlsx", "DataFrame", tmp_path / "store")
    assert isinstance(out, Collection)
    assert len(out) == 2
    sheets = [item.user.get("sheet_name") for item in out]
    assert sheets == ["alpha", "beta"]
    # All sheets of one workbook share the source file (the save-grouping key).
    assert {Path(item.framework.source).name for item in out} == {"exp.xlsx"}


def test_single_sheet_file_is_a_length_one_collection(tmp_path: Path) -> None:
    _write_workbook(tmp_path / "solo.xlsx", {"only": {"x": [1, 2, 3]}})
    out = _load(tmp_path / "solo.xlsx", "DataFrame", tmp_path / "store")
    assert isinstance(out, Collection)
    assert len(out) == 1
    assert out[0].user.get("sheet_name") == "only"


def test_output_port_is_collection_for_xlsx(tmp_path: Path) -> None:
    params = {"core_type": "DataFrame", "path": str(tmp_path / "x.xlsx")}
    ports = LoadData(config={"params": params}).get_effective_output_ports()
    assert ports[0].is_collection is True
    # Non-xlsx single path stays a bare object (is_collection=False).
    params_csv = {"core_type": "DataFrame", "path": str(tmp_path / "x.csv")}
    ports_csv = LoadData(config={"params": params_csv}).get_effective_output_ports()
    assert ports_csv[0].is_collection is False


def test_multiple_multisheet_files_flatten_into_one_collection(tmp_path: Path) -> None:
    _write_workbook(tmp_path / "f1.xlsx", {"s1": {"a": [1]}, "s2": {"a": [2]}, "s3": {"a": [3]}})
    _write_workbook(tmp_path / "f2.xlsx", {"t1": {"a": [4]}, "t2": {"a": [5]}})
    out = _load([tmp_path / "f1.xlsx", tmp_path / "f2.xlsx"], "DataFrame", tmp_path / "store")
    assert isinstance(out, Collection)
    # 3 sheets + 2 sheets, flattened, in file then sheet order.
    assert len(out) == 5
    assert [item.user.get("sheet_name") for item in out] == ["s1", "s2", "s3", "t1", "t2"]


def test_save_collection_regroups_by_source_workbook(tmp_path: Path) -> None:
    # Owner semantics 1 + 2: 3 sheets from f1 and 2 sheets from f2 must save back
    # as f1.xlsx (3 sheets) and f2.xlsx (2 sheets).
    _write_workbook(tmp_path / "f1.xlsx", {"s1": {"a": [1]}, "s2": {"a": [2]}, "s3": {"a": [3]}})
    _write_workbook(tmp_path / "f2.xlsx", {"t1": {"a": [4]}, "t2": {"a": [5]}})
    loaded = _load([tmp_path / "f1.xlsx", tmp_path / "f2.xlsx"], "DataFrame", tmp_path / "store")

    out_dir = tmp_path / "saved"
    sp = {"core_type": "DataFrame", "path": str(out_dir)}
    SaveData(config={"params": sp}).save(loaded, BlockConfig(params=sp))

    written = {p.name: pd.ExcelFile(p).sheet_names for p in sorted(out_dir.glob("*.xlsx"))}
    assert written == {"f1.xlsx": ["s1", "s2", "s3"], "f2.xlsx": ["t1", "t2"]}


def test_save_collection_five_single_sheet_files_round_trip_to_five_files(tmp_path: Path) -> None:
    # Owner semantics 2: five single-sheet workbooks -> five separate files back.
    for i in range(5):
        _write_workbook(tmp_path / f"w{i}.xlsx", {f"sheet{i}": {"a": [i]}})
    loaded = _load([tmp_path / f"w{i}.xlsx" for i in range(5)], "DataFrame", tmp_path / "store")
    assert len(loaded) == 5

    out_dir = tmp_path / "saved"
    sp = {"core_type": "DataFrame", "path": str(out_dir)}
    SaveData(config={"params": sp}).save(loaded, BlockConfig(params=sp))
    assert sorted(p.name for p in out_dir.glob("*.xlsx")) == [f"w{i}.xlsx" for i in range(5)]


def test_save_sourceless_collection_into_one_workbook(tmp_path: Path) -> None:
    # Owner decision: source-less items all land in ONE workbook named by filename.
    import pyarrow as pa

    from scistudio.core.types.dataframe import DataFrame

    items = [DataFrame(columns=["a"], row_count=1, data=pa.table({"a": [i]})) for i in range(3)]
    coll = Collection(items=items, item_type=DataFrame)

    out_dir = tmp_path / "saved"
    sp = {"core_type": "DataFrame", "path": str(out_dir), "filename": "bundle.xlsx"}
    SaveData(config={"params": sp}).save(coll, BlockConfig(params=sp))

    files = list(out_dir.glob("*.xlsx"))
    assert [p.name for p in files] == ["bundle.xlsx"]
    assert len(pd.ExcelFile(files[0]).sheet_names) == 3


def test_series_sheets_round_trip(tmp_path: Path) -> None:
    _write_workbook(tmp_path / "s.xlsx", {"one": {"v": [1.0, 2.0]}, "two": {"v": [3.0]}})
    out = _load(tmp_path / "s.xlsx", "Series", tmp_path / "store")
    assert isinstance(out, Collection)
    assert len(out) == 2
    assert [item.user.get("sheet_name") for item in out] == ["one", "two"]

    out_dir = tmp_path / "saved"
    sp = {"core_type": "Series", "path": str(out_dir)}
    SaveData(config={"params": sp}).save(out, BlockConfig(params=sp))
    assert pd.ExcelFile(out_dir / "s.xlsx").sheet_names == ["one", "two"]


def test_series_rejects_multi_column_sheet(tmp_path: Path) -> None:
    _write_workbook(tmp_path / "bad.xlsx", {"sheet": {"a": [1], "b": [2]}})
    with pytest.raises(ValueError, match="single-column"):
        _load(tmp_path / "bad.xlsx", "Series", tmp_path / "store")


def test_display_name_disambiguates_same_file_sheets(tmp_path: Path) -> None:
    _write_workbook(tmp_path / "exp.xlsx", {"alpha": {"a": [1]}, "beta": {"a": [2]}})
    out = _load(tmp_path / "exp.xlsx", "DataFrame", tmp_path / "store")
    labels = [interactive_item_label(item, i) for i, item in enumerate(out)]
    assert labels == ["exp.xlsx — alpha", "exp.xlsx — beta"]
    # No collision even though framework.source is identical.
    assert len(set(labels)) == len(labels)


def test_xlsx_dimension_guard() -> None:
    _check_xlsx_dimensions(1_048_575, 16_384)  # the exact maxima are allowed
    with pytest.raises(ValueError, match="rows exceed"):
        _check_xlsx_dimensions(1_048_576, 1)
    with pytest.raises(ValueError, match="columns exceed"):
        _check_xlsx_dimensions(1, 16_385)
