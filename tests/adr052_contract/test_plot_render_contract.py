"""§9 plot render(collection) behaviour-pinning contract test (#1833 / #1824).

ADR-052 §9 / spec §9 + §15 define the import-free, dual-interpreter (Python + R)
``render(collection)`` authoring contract and require a *behaviour-pinning*
contract test (a reference ``render(collection)`` asserting the injected shape --
``collection.types`` / ``.items`` / ``.open()`` / ``.open_one()``;
``item.type`` / ``.metadata`` strip-list / ``.open()`` native-payload-by-type --
and the return handling: figure / in-working-dir path / list / rejects).

The §9 engine was relocated to the first-class ``scistudio.plot`` package in
**#1824** (behaviour-preserving). The implementing classes (``_PlotCollection`` /
``_PlotItem`` / ``_PlotItems``) and the ``_collect_artifacts`` return handler live
in the harness program text ``scistudio.plot._harness.PYTHON_HARNESS`` (run in a
confined CodeBlock subprocess that imports nothing from ``scistudio``); the input
envelope ``{schema_version, collection: {types, items}}`` is built by
``scistudio.plot.runtime._input_envelope``. This test drives the harness as the
runtime does: build the envelope with ``_input_envelope`` over real persisted
artifacts, materialise the harness classes/return-handler from ``PYTHON_HARNESS``
(the exact program text the subprocess executes), and pin the shape + return
contract. The R reference half is a tracked, clearly-skipped placeholder (no R
interpreter is assumed in CI); the §9 contract is interpreter-agnostic and is
pinned here by the Python reference.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scistudio.plot._harness import PYTHON_HARNESS
from scistudio.plot.runtime import _input_envelope

_BIG_LIMIT = 1_000_000_000
_ALL_FORMATS = ["svg", "pdf", "png", "jpeg"]
_SUPPORTED = {"Array", "DataFrame", "Series", "Text", "Artifact", "CompositeData"}
_STRIP_LIST = {
    "backend",
    "format",
    "path",
    "storage_ref",
    "storage",
    "type_chain",
    "item_type",
    "slots",
}


def _harness_namespace() -> dict[str, Any]:
    """Execute ``PYTHON_HARNESS`` (the program text the subprocess runs) and
    return its namespace, exposing ``_PlotCollection`` / ``_collect_artifacts``
    without invoking ``main()`` (``__name__`` is not ``"__main__"``)."""
    namespace: dict[str, Any] = {"__name__": "adr052_plot_harness_under_test"}
    exec(compile(PYTHON_HARNESS, "<plot_harness>", "exec"), namespace)
    return namespace


def _refs(work: Path) -> list[dict[str, Any]]:
    np.save(work / "arr.npy", np.arange(6, dtype="float64").reshape(2, 3))
    pq.write_table(pa.table({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}), work / "df.parquet")
    pq.write_table(pa.table({"sig": [1.0, 2.0, 3.0]}), work / "series.parquet")
    (work / "note.txt").write_text("hello plot", encoding="utf-8")
    (work / "artifact.bin").write_bytes(b"\x00\x01\x02\x03")

    arr_slot = {
        "item_type": "Array",
        "path": str(work / "arr.npy"),
        "format": "npy",
        "backend": "numpy",
        "metadata": {"shape": [2, 3], "dtype": "float64"},
    }
    return [
        {
            "item_type": "Array",
            "path": str(work / "arr.npy"),
            "format": "npy",
            "backend": "numpy",
            "metadata": {
                "shape": [2, 3],
                "dtype": "float64",
                "title": "demo array",
                # storage/lineage-internal keys -> must be stripped from item.metadata:
                "storage_ref": "secret-ref",
                "backend": "zarr",
                "path": "/secret/path",
            },
        },
        {
            "item_type": "DataFrame",
            "path": str(work / "df.parquet"),
            "format": "parquet",
            "backend": "arrow",
            "metadata": {"row_count": 3},
        },
        {
            "item_type": "Series",
            "path": str(work / "series.parquet"),
            "format": "parquet",
            "backend": "arrow",
            "metadata": {},
        },
        {
            "item_type": "Text",
            "path": str(work / "note.txt"),
            "format": "txt",
            "backend": "filesystem",
            "metadata": {},
        },
        {
            "item_type": "Artifact",
            "path": str(work / "artifact.bin"),
            "format": "bin",
            "backend": "filesystem",
            "metadata": {},
        },
        {"item_type": "CompositeData", "metadata": {"slots": {"arr": arr_slot}}},
    ]


def test_plot_render_collection_contract(tmp_path: Path) -> None:
    """The §9 render(collection) injected-shape + return-handling contract."""
    namespace = _harness_namespace()
    envelope = _input_envelope(_refs(tmp_path))
    assert envelope["schema_version"] == 1
    collection = namespace["_PlotCollection"](envelope, _BIG_LIMIT)

    # --- injected shape ---------------------------------------------------- #
    assert isinstance(collection.types, tuple)
    assert collection.types == ("Array", "DataFrame", "Series", "Text", "Artifact", "CompositeData")
    assert "DataObject" not in collection.types
    assert len(set(collection.types)) == len(collection.types)

    items = collection.items
    assert len(items) == 6
    assert [item.type for item in items] == list(collection.types)
    assert items[0].type == "Array"
    for item in items:
        assert isinstance(item.type, str) and item.type in _SUPPORTED

    # item.metadata: read-only MappingProxyType with the strip-list removed.
    array_md = items[0].metadata
    assert isinstance(array_md, MappingProxyType)
    assert dict(array_md) == {"shape": [2, 3], "dtype": "float64", "title": "demo array"}
    assert _STRIP_LIST.isdisjoint(array_md.keys())
    with pytest.raises(TypeError):
        array_md["title"] = "mutated"  # type: ignore[index]

    # items.open(max_items=None) -> list; open_one() -> first.
    opened = items.open(max_items=None)
    assert isinstance(opened, list) and len(opened) == 6
    assert isinstance(items.open_one(), np.ndarray)

    by_type = {item.type: item for item in items}

    # item.open() native payload per item.type (never a DataObject).
    arr = by_type["Array"].open()
    assert isinstance(arr, np.ndarray)
    np.testing.assert_array_equal(arr, np.arange(6, dtype="float64").reshape(2, 3))
    assert isinstance(by_type["DataFrame"].open(), pd.DataFrame)
    series_payload = by_type["Series"].open()
    assert isinstance(series_payload, (pd.Series, pd.DataFrame))
    assert isinstance(series_payload, pd.Series)  # single-column -> Series (#1750)
    assert by_type["Text"].open() == "hello plot"
    assert isinstance(by_type["Text"].open(), str)
    artifact_path = by_type["Artifact"].open()
    assert isinstance(artifact_path, Path) and artifact_path.is_file()
    composite = by_type["CompositeData"].open()
    assert isinstance(composite, dict) and set(composite) == {"arr"}
    assert isinstance(composite["arr"], np.ndarray)

    # empty collection -> open_one() raises IndexError.
    empty = namespace["_PlotCollection"]({"collection": {"types": [], "items": []}}, _BIG_LIMIT)
    assert empty.items.open(max_items=None) == []
    with pytest.raises(IndexError):
        empty.items.open_one()

    # --- return contract --------------------------------------------------- #
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    collect = namespace["_collect_artifacts"]
    out_dir = tmp_path / "work"
    out_dir.mkdir()
    preferred = "png"

    fig = plt.figure()
    fig.add_subplot(111).plot([0, 1, 2], [2, 1, 0])
    # The return value is still the single preferred-format primary, but the
    # harness now also writes one sibling file per allowed format so the
    # previewer can save/export any of them without re-rendering (#1918).
    assert collect(fig, str(out_dir), preferred, _ALL_FORMATS) == ["figure.png"]
    assert (out_dir / "figure.png").is_file()
    for sibling in ("figure.svg", "figure.pdf", "figure.jpg"):
        assert (out_dir / sibling).is_file(), sibling
    # PNG magic bytes for the primary; PDF magic bytes for the sibling.
    assert (out_dir / "figure.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert (out_dir / "figure.pdf").read_bytes()[:5] == b"%PDF-"

    # With no allowed set only the preferred format is rendered (no siblings).
    single_dir = tmp_path / "single"
    single_dir.mkdir()
    fig_single = plt.figure()
    fig_single.add_subplot(111).plot([0, 1], [0, 1])
    assert collect(fig_single, str(single_dir), preferred, []) == ["figure.png"]
    assert sorted(p.name for p in single_dir.iterdir()) == ["figure.png"]

    (out_dir / "made.png").write_bytes(b"x")
    assert collect("made.png", str(out_dir), preferred, _ALL_FORMATS) == ["made.png"]
    assert collect(out_dir / "made.png", str(out_dir), preferred, _ALL_FORMATS) == ["made.png"]

    fig2 = plt.figure()
    fig2.add_subplot(111).plot([0, 1], [1, 0])
    assert collect([fig2, "made.png"], str(out_dir), preferred, _ALL_FORMATS) == ["figure.png", "made.png"]

    with pytest.raises(ValueError):
        collect(None, str(out_dir), preferred, _ALL_FORMATS)
    with pytest.raises(ValueError):
        collect([None], str(out_dir), preferred, _ALL_FORMATS)
    with pytest.raises(TypeError):
        collect(12345, str(out_dir), preferred, _ALL_FORMATS)

    outside = tmp_path / "outside.png"
    outside.write_bytes(b"x")
    with pytest.raises(PermissionError):
        collect(str(outside), str(out_dir), preferred, _ALL_FORMATS)
    with pytest.raises(FileNotFoundError):
        collect("absent.png", str(out_dir), preferred, _ALL_FORMATS)


@pytest.mark.skip(
    reason="§9 R reference render(collection): requires an R interpreter + jsonlite/"
    "ggplot2/arrow, not assumed in CI. The interpreter-agnostic §9 shape/return "
    "contract is pinned by the Python reference above. TODO(#1824)."
)
def test_plot_render_collection_r_reference() -> None:
    """Placeholder for the R reference ``render <- function(collection)`` (§9).

    The R harness (``scistudio.plot._harness.R_HARNESS``) mirrors the Python
    shape/return contract; running it needs a real Rscript with jsonlite/ggplot2/
    arrow, which CI does not provide.

    # TODO(#1824): implement the R reference render(collection) behaviour test
    #   when an R interpreter is available in CI; the §9 contract shape is
    #   unchanged from the Python reference (ADR-052 §9 / §15).
    #   Followup: https://github.com/jiazhenz026/SciStudio/issues/1824
    """
    raise NotImplementedError("R reference deferred; see TODO(#1824)")  # pragma: no cover
