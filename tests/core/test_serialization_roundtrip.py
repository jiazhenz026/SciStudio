"""Layer 1: Serialization round-trip tests for all core + plugin DataObject types.

Exercises the _serialise_one -> _reconstruct_one -> to_memory() path
that objects traverse across the subprocess boundary (ADR-027 Addendum 1).

Covers #441.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pytest

from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.collection import Collection
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.serialization import _reconstruct_one, _serialise_one
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

# ---------------------------------------------------------------------------
# Plugin type imports (imaging plugin)
# ---------------------------------------------------------------------------
try:
    from scistudio_blocks_imaging.types import Image, Label, Mask

    HAS_IMAGING = True
except ImportError:
    HAS_IMAGING = False

# ---------------------------------------------------------------------------
# Sample factories: each returns a (DataObject, save_func) pair.
# save_func(obj, tmp_path) persists the object and returns it with
# storage_ref set.
# ---------------------------------------------------------------------------


def _make_array(tmp_path: Path) -> Array:
    """4x4 float32 array."""
    arr = Array(axes=["y", "x"], shape=(4, 4), dtype="float32")
    arr._data = np.random.rand(4, 4).astype(np.float32)  # type: ignore[attr-defined]
    arr.save(str(tmp_path / "array.zarr"))
    return arr


def _make_series(tmp_path: Path) -> Series:
    """3-element series."""
    s = Series(index_name="wavenumber", value_name="intensity", length=3)
    s._arrow_table = pa.table({"intensity": [10.0, 20.0, 30.0]})  # type: ignore[attr-defined]
    s.save(str(tmp_path / "series.parquet"))
    return s


def _make_dataframe(tmp_path: Path) -> DataFrame:
    """3-row DataFrame."""
    import pyarrow as pa

    df = DataFrame(columns=["a", "b"], row_count=3)
    table = pa.table({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
    df._arrow_table = table  # type: ignore[attr-defined]
    df.save(str(tmp_path / "dataframe.parquet"))
    return df


def _make_text(tmp_path: Path) -> Text:
    """Simple text object."""
    t = Text(content="Hello, SciStudio!", format="plain", encoding="utf-8")
    t.save(str(tmp_path / "text.txt"))
    return t


def _make_artifact(tmp_path: Path) -> Artifact:
    """Binary artifact."""
    artifact_file = tmp_path / "sample.bin"
    artifact_file.write_bytes(b"\x00\x01\x02\x03")
    a = Artifact(file_path=artifact_file, mime_type="application/octet-stream", description="test artifact")
    a.save(str(tmp_path / "artifact.txt"))
    return a


def _make_composite(tmp_path: Path) -> CompositeData:
    """CompositeData with one Array slot."""
    inner = Array(axes=["y", "x"], shape=(2, 2), dtype="float32")
    inner._data = np.ones((2, 2), dtype=np.float32)  # type: ignore[attr-defined]
    inner.save(str(tmp_path / "composite_inner.zarr"))

    comp = CompositeData(slots={"raster": inner})
    comp.save(str(tmp_path / "composite"))
    return comp


# Imaging plugin factories (only available when plugin is installed)
def _make_image(tmp_path: Path) -> Any:
    """8x8 Image (imaging plugin)."""
    img = Image(axes=["y", "x"], shape=(8, 8), dtype="float32")
    img._data = np.random.rand(8, 8).astype(np.float32)  # type: ignore[attr-defined]
    img.save(str(tmp_path / "image.zarr"))
    return img


def _make_mask(tmp_path: Path) -> Any:
    """4x4 boolean Mask (imaging plugin)."""
    m = Mask(axes=["y", "x"], shape=(4, 4), dtype="bool")
    m._data = np.ones((4, 4), dtype=bool)  # type: ignore[attr-defined]
    m.save(str(tmp_path / "mask.zarr"))
    return m


def _make_label(tmp_path: Path) -> Any:
    """Label with raster Array slot (imaging plugin)."""
    raster = Array(axes=["y", "x"], shape=(4, 4), dtype="int32")
    raster._data = np.arange(16, dtype=np.int32).reshape(4, 4)  # type: ignore[attr-defined]
    raster.save(str(tmp_path / "label_raster.zarr"))
    label = Label(slots={"raster": raster}, meta=Label.Meta(n_objects=16))
    label.save(str(tmp_path / "label"))
    return label


# ---------------------------------------------------------------------------
# Parametrized core type round-trip tests
# ---------------------------------------------------------------------------

CORE_FACTORIES: list[tuple[str, Any]] = [
    ("Array", _make_array),
    ("Series", _make_series),
    ("DataFrame", _make_dataframe),
    ("Text", _make_text),
    ("Artifact", _make_artifact),
    ("CompositeData", _make_composite),
]

if HAS_IMAGING:
    CORE_FACTORIES.extend(
        [
            ("Image", _make_image),
            ("Mask", _make_mask),
            ("Label", _make_label),
        ]
    )


@pytest.mark.parametrize("type_name,factory", CORE_FACTORIES, ids=[f[0] for f in CORE_FACTORIES])
def test_serialise_deserialise_roundtrip(type_name: str, factory: Any, tmp_path: Path) -> None:
    """Each core DataObject type must survive _serialise_one -> _reconstruct_one -> to_memory()."""
    obj = factory(tmp_path)

    # Serialise
    wire = _serialise_one(obj)
    assert isinstance(wire, dict)
    assert "backend" in wire
    assert "path" in wire
    assert "metadata" in wire

    md = wire["metadata"]
    assert "type_chain" in md
    assert isinstance(md["type_chain"], list)
    assert len(md["type_chain"]) >= 1

    # Reconstruct
    reconstructed = _reconstruct_one(wire)
    assert type(reconstructed).__name__ == type(obj).__name__
    assert reconstructed.storage_ref is not None

    # to_memory() must succeed (unless composite — composites delegate to slots)
    if not isinstance(reconstructed, CompositeData):
        data = reconstructed.to_memory()
        assert data is not None


# ---------------------------------------------------------------------------
# Composite slot round-trip
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_IMAGING, reason="scistudio_blocks_imaging not installed")
def test_composite_slot_roundtrip(tmp_path: Path) -> None:
    """Label (CompositeData with raster Array slot) must round-trip with slots intact."""
    label = _make_label(tmp_path)

    # Serialise
    wire = _serialise_one(label)
    md = wire["metadata"]
    assert "slots" in md
    assert "raster" in md["slots"]
    raster_wire = md["slots"]["raster"]
    assert raster_wire["backend"] is not None

    # Reconstruct
    reconstructed = _reconstruct_one(wire)
    assert isinstance(reconstructed, Label)
    assert "raster" in reconstructed.slot_names

    raster_slot = reconstructed.get("raster")
    assert raster_slot.storage_ref is not None

    # Slot to_memory must succeed
    raster_data = raster_slot.to_memory()
    assert raster_data is not None
    assert raster_data.shape == (4, 4)


# ---------------------------------------------------------------------------
# Collection round-trip
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_IMAGING, reason="scistudio_blocks_imaging not installed")
def test_collection_roundtrip(tmp_path: Path) -> None:
    """Collection[Image] must survive serialise_outputs -> reconstruct_inputs."""
    from scistudio.engine.runners.worker import reconstruct_inputs, serialise_outputs

    images = []
    for i in range(3):
        img = Image(axes=["y", "x"], shape=(4, 4), dtype="float32")
        img._data = np.random.rand(4, 4).astype(np.float32)  # type: ignore[attr-defined]
        img.save(str(tmp_path / f"img_{i}.zarr"))
        images.append(img)

    collection = Collection(images)
    assert collection.length == 3

    # serialise_outputs
    wire = serialise_outputs({"port": collection}, str(tmp_path))
    assert "port" in wire
    assert wire["port"]["_collection"] is True
    assert len(wire["port"]["items"]) == 3

    # reconstruct_inputs
    result = reconstruct_inputs({"inputs": wire})
    reconstructed = result["port"]
    assert isinstance(reconstructed, Collection)
    assert len(reconstructed) == 3

    for item in reconstructed:
        data = item.to_memory()
        assert data is not None
        assert data.shape == (4, 4)


def test_serialise_one_rejects_none_storage_ref() -> None:
    """ADR-031 Addendum 1 S3: _serialise_one raises ValueError when storage_ref is None."""
    arr = Array(axes=["y", "x"], shape=(3, 3), dtype="float64")
    # No storage_ref, no _data — should raise
    with pytest.raises(ValueError, match="storage_ref is None"):
        _serialise_one(arr)


def test_serialise_one_allows_artifact_without_storage_ref() -> None:
    """Artifact with file_path but no storage_ref is allowed (path-only transport)."""
    art = Artifact(file_path=Path("/tmp/test.bin"), mime_type="application/octet-stream")
    wire = _serialise_one(art)
    assert wire["backend"] is None
    assert wire["path"] is None


@pytest.mark.parametrize(
    "dtype_input,expected_persisted",
    [
        (bool, "bool"),
        (np.bool_, "bool"),
        (np.dtype(bool), "bool"),
        ("bool", "bool"),
        (np.uint8, "uint8"),
        (np.dtype("float32"), "float32"),
    ],
)
def test_dtype_persisted_as_canonical_string(tmp_path: Path, dtype_input: Any, expected_persisted: str) -> None:
    """Array dtype must serialise as the canonical numpy short form.

    Regression: ``str(bool)`` returns ``"<class 'bool'>"`` which round-trips
    into ``np.dtype("<class 'bool'>")`` and crashes Mask reconstruction with
    ``data type ... not understood``.  ``_serialise_extra_metadata`` must
    normalise via ``np.dtype()`` first so the persisted dtype is always a
    string ``np.dtype()`` will accept on the reverse trip.
    """
    arr = Array(axes=["y", "x"], shape=(2, 2), dtype=dtype_input)
    arr._data = np.zeros((2, 2), dtype=np.dtype(dtype_input))  # type: ignore[attr-defined]
    arr.save(str(tmp_path / "arr.zarr"))

    wire = _serialise_one(arr)
    persisted = wire["metadata"]["dtype"]
    assert persisted == expected_persisted, (
        f"dtype={dtype_input!r} persisted as {persisted!r}, expected {expected_persisted!r}"
    )
    # Round trip back through np.dtype() must succeed.
    assert np.dtype(persisted) == np.dtype(dtype_input)

    # And the full reconstruct path must not raise.
    reconstructed = _reconstruct_one(wire)
    assert reconstructed is not None
