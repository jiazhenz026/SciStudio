"""ADR-052 §9 plot ``render(collection)`` behaviour-pinning contract.

The §9 plot contract is an import-free, duck-typed, dual-interpreter (Python + R)
authoring contract: a plot script defines exactly ``def render(collection):``, the
harness injects a ``collection`` object, calls ``render(collection)``, and collects
the return value. ADR-052 §15 freezes it with a *behaviour-pinning contract test*
that asserts the injected SHAPE (``collection.types`` / ``.items`` /
``.items.open()`` / ``.open_one()``; ``item.type`` / ``.metadata`` strip-list /
``.open()`` native-payload-by-type) and the RETURN contract (figure /
in-working-dir path / list / ``None`` -> ``ValueError`` / other -> ``TypeError`` /
escaping path -> ``PermissionError`` / missing path -> ``FileNotFoundError``).

The §9 engine was relocated to the first-class ``scistudio.plot`` package in
**#1824** (behaviour-preserving). The implementing classes ``_PlotCollection`` /
``_PlotItem`` / ``_PlotItems`` and the ``_collect_artifacts`` return handler live in
the harness program text ``scistudio.plot._harness.PYTHON_HARNESS`` (run in a
confined CodeBlock subprocess, importing nothing from ``scistudio``); the input
envelope ``{schema_version, collection: {types, items}}`` is built by
``scistudio.plot.runtime._input_envelope``. This test exercises the harness exactly
as the runtime does: it builds the envelope with ``_input_envelope`` over real
persisted artifacts, materialises the harness classes/return-handler from
``PYTHON_HARNESS`` (the same program text the subprocess executes), and pins the
shape + return contract. The R reference half is a tracked, clearly-skipped
placeholder (no R interpreter is assumed in CI); the §9 shape/return contract is
interpreter-agnostic and is pinned here by the Python reference.
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

_BIG_LIMIT = 1_000_000_000  # well above the tiny fixtures; byte-budget not under test here
_ALL_FORMATS = ["svg", "pdf", "png", "jpeg"]


def _harness_namespace() -> dict[str, Any]:
    """Execute the harness program text and return its module namespace.

    This is the exact ``PYTHON_HARNESS`` the plot subprocess runs; executing it
    with a non-``"__main__"`` ``__name__`` defines ``_PlotCollection`` /
    ``_PlotItem`` / ``_PlotItems`` and ``_collect_artifacts`` without invoking
    ``main()``.
    """
    namespace: dict[str, Any] = {"__name__": "scistudio_plot_harness_under_test"}
    exec(compile(PYTHON_HARNESS, "<plot_harness>", "exec"), namespace)
    return namespace


def _write_fixture_artifacts(work: Path) -> dict[str, Any]:
    """Persist one artifact per supported core type and return reference dicts.

    The ref-dict keys (``item_type`` / ``path`` / ``format`` / ``backend`` /
    ``metadata``) mirror what the plot runtime hands ``_input_envelope``. The
    Array metadata deliberately carries storage/lineage-internal keys
    (``storage_ref`` / ``backend`` / ``path``) so the §9 strip-list is exercised.
    """
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
    return {
        "array": {
            "item_type": "Array",
            "path": str(work / "arr.npy"),
            "format": "npy",
            "backend": "numpy",
            "metadata": {
                "shape": [2, 3],
                "dtype": "float64",
                "title": "demo array",
                # strip-list keys (must NOT reach item.metadata):
                "storage_ref": "secret-ref",
                "backend": "zarr",
                "path": "/secret/path",
            },
        },
        "dataframe": {
            "item_type": "DataFrame",
            "path": str(work / "df.parquet"),
            "format": "parquet",
            "backend": "arrow",
            "metadata": {"row_count": 3},
        },
        "series": {
            "item_type": "Series",
            "path": str(work / "series.parquet"),
            "format": "parquet",
            "backend": "arrow",
            "metadata": {},
        },
        "text": {
            "item_type": "Text",
            "path": str(work / "note.txt"),
            "format": "txt",
            "backend": "filesystem",
            "metadata": {},
        },
        "artifact": {
            "item_type": "Artifact",
            "path": str(work / "artifact.bin"),
            "format": "bin",
            "backend": "filesystem",
            "metadata": {},
        },
        "composite": {
            "item_type": "CompositeData",
            "metadata": {"slots": {"arr": arr_slot}},
        },
    }


def _build_collection(namespace: dict[str, Any], refs: list[dict[str, Any]]) -> Any:
    envelope = _input_envelope(refs)
    assert envelope["schema_version"] == 1
    return namespace["_PlotCollection"](envelope, _BIG_LIMIT)


# ---------------------------------------------------------------------------
# Injected `collection` shape.
# ---------------------------------------------------------------------------


def test_plot_render_collection_injected_shape(tmp_path: Path) -> None:
    """Pin the injected ``collection`` shape and ``item.open()`` native payloads."""
    namespace = _harness_namespace()
    fixtures = _write_fixture_artifacts(tmp_path)
    ordered = ["array", "dataframe", "series", "text", "artifact", "composite"]
    refs = [fixtures[key] for key in ordered]

    collection = _build_collection(namespace, refs)

    # collection.types -> tuple of distinct, non-"DataObject" type names present.
    assert isinstance(collection.types, tuple)
    assert collection.types == (
        "Array",
        "DataFrame",
        "Series",
        "Text",
        "Artifact",
        "CompositeData",
    )
    assert len(set(collection.types)) == len(collection.types)
    assert "DataObject" not in collection.types

    # collection.items: ordered container supporting len() / iterate / [i].
    items = collection.items
    assert len(items) == 6
    iterated = [item.type for item in items]
    assert iterated == list(collection.types)
    assert items[0].type == "Array"

    # item.type is a str drawn from the supported set.
    supported = {"Array", "DataFrame", "Series", "Text", "Artifact", "CompositeData"}
    for item in items:
        assert isinstance(item.type, str)
        assert item.type in supported

    # item.metadata: read-only MappingProxyType with the strip-list removed.
    array_md = items[0].metadata
    assert isinstance(array_md, MappingProxyType)
    assert dict(array_md) == {"shape": [2, 3], "dtype": "float64", "title": "demo array"}
    for stripped in ("storage_ref", "backend", "path", "format", "storage", "type_chain", "item_type", "slots"):
        assert stripped not in array_md
    with pytest.raises(TypeError):
        array_md["title"] = "mutated"  # type: ignore[index]

    # items.open(max_items=None) -> list of opened payloads; open_one() -> first.
    opened = items.open(max_items=None)
    assert isinstance(opened, list) and len(opened) == 6
    assert isinstance(items.open_one(), np.ndarray)

    by_type = {item.type: item for item in items}

    # item.open() returns the NATIVE payload per item.type (never a DataObject).
    arr_payload = by_type["Array"].open()
    assert isinstance(arr_payload, np.ndarray)
    np.testing.assert_array_equal(arr_payload, np.arange(6, dtype="float64").reshape(2, 3))

    df_payload = by_type["DataFrame"].open()
    assert isinstance(df_payload, pd.DataFrame)
    assert list(df_payload.columns) == ["x", "y"]

    series_payload = by_type["Series"].open()
    # single-column Series -> pandas.Series (>=2 columns -> DataFrame, #1750).
    assert isinstance(series_payload, (pd.Series, pd.DataFrame))
    assert isinstance(series_payload, pd.Series)

    text_payload = by_type["Text"].open()
    assert isinstance(text_payload, str) and text_payload == "hello plot"

    artifact_payload = by_type["Artifact"].open()
    assert isinstance(artifact_payload, Path) and artifact_payload.is_file()

    composite_payload = by_type["CompositeData"].open()
    assert isinstance(composite_payload, dict)
    assert set(composite_payload) == {"arr"}
    assert isinstance(composite_payload["arr"], np.ndarray)


def test_plot_render_collection_empty_open_one_raises(tmp_path: Path) -> None:
    """An empty collection -> ``open_one()`` raises ``IndexError`` (§9)."""
    namespace = _harness_namespace()
    collection = namespace["_PlotCollection"]({"collection": {"types": [], "items": []}}, _BIG_LIMIT)
    assert len(collection.items) == 0
    assert collection.items.open(max_items=None) == []
    with pytest.raises(IndexError):
        collection.items.open_one()


# ---------------------------------------------------------------------------
# render(collection) return contract.
# ---------------------------------------------------------------------------


def test_plot_render_collection_return_contract(tmp_path: Path) -> None:
    """Pin the ``render(collection)`` return handling (§9)."""
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    namespace = _harness_namespace()
    collect = namespace["_collect_artifacts"]
    out_dir = tmp_path / "work"
    out_dir.mkdir()
    preferred = "png"

    # (1) a Matplotlib figure (duck-typed: has .savefig) is saved to the work dir.
    fig = plt.figure()
    fig.add_subplot(111).plot([0, 1, 2], [2, 1, 0])
    saved = collect(fig, str(out_dir), preferred, _ALL_FORMATS)
    assert saved == ["figure.png"]
    assert (out_dir / "figure.png").is_file()

    # (2) an in-working-dir path (str AND Path) is collected.
    (out_dir / "made.png").write_bytes(b"x")
    assert collect("made.png", str(out_dir), preferred, _ALL_FORMATS) == ["made.png"]
    assert collect(out_dir / "made.png", str(out_dir), preferred, _ALL_FORMATS) == ["made.png"]

    # (3) a list/tuple of the above -> each collected (mixed figure + path).
    fig2 = plt.figure()
    fig2.add_subplot(111).plot([0, 1], [1, 0])
    mixed = collect([fig2, "made.png"], str(out_dir), preferred, _ALL_FORMATS)
    assert mixed == ["figure.png", "made.png"]

    # (4) None -> ValueError; any other type -> TypeError.
    with pytest.raises(ValueError):
        collect(None, str(out_dir), preferred, _ALL_FORMATS)
    with pytest.raises(ValueError):
        collect([None], str(out_dir), preferred, _ALL_FORMATS)
    with pytest.raises(TypeError):
        collect(12345, str(out_dir), preferred, _ALL_FORMATS)

    # (5) a path resolving OUTSIDE the working dir -> PermissionError.
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"x")
    with pytest.raises(PermissionError):
        collect(str(outside), str(out_dir), preferred, _ALL_FORMATS)

    # (6) a missing in-dir path -> FileNotFoundError.
    with pytest.raises(FileNotFoundError):
        collect("absent.png", str(out_dir), preferred, _ALL_FORMATS)


# ---------------------------------------------------------------------------
# R reference half (deferred placeholder).
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="§9 R reference render(collection): requires an R interpreter + jsonlite/"
    "ggplot2/arrow, not assumed in CI. The interpreter-agnostic §9 shape/return "
    "contract is pinned by the Python reference above. TODO(#1824)."
)
def test_plot_render_collection_r_reference() -> None:
    """Placeholder for the R reference ``render <- function(collection)`` (§9).

    The R harness (``scistudio.plot._harness.R_HARNESS``) mirrors the Python
    shape/return contract (``collection$types`` / ``collection$items$open()`` /
    ``open_one()``; ``item$type`` / ``item$metadata`` strip-list / ``item$open()``
    native payloads; figure / in-dir path / list return handling). Running it
    needs a real Rscript with jsonlite/ggplot2/arrow, which CI does not provide.

    # TODO(#1824): implement the R reference render(collection) behaviour test
    #   when an R interpreter is available in CI; the §9 contract shape is
    #   unchanged from the Python reference (ADR-052 §9 / §15).
    #   Followup: https://github.com/jiazhenz026/SciStudio/issues/1824
    """
    raise NotImplementedError("R reference deferred; see TODO(#1824)")  # pragma: no cover
