"""Alpha IO load+save coverage matrix for the six core types.

For every core type this exercises the full ``load_ext x save_ext``
matrix the alpha readiness plan asks for:

    for load_ext in type.load_extensions:
        obj = load(write(build(), load_ext), load_ext)   # LOAD under test
        for save_ext in type.save_extensions:
            path = save(obj, save_ext)                    # SAVE under test
            assert path is a correct, non-empty file
            if save_ext is reloadable: assert data survives

It also verifies each type round-trips as a **10-item collection** via
``LoadData`` multi-path loading (single-file and collection forms are
both required for alpha).

Scoped to the core ``LoadData`` / ``SaveData`` registry (no plugin
scan), mirroring ``tests/engine/test_materialisation.py``. Slots with a
known engine round-trip break are ``xfail`` and documented in the test
project's ``alpha-test-suite/FINDINGS.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.io.loaders.load_data import LoadData
from scistudio.blocks.io.savers.save_data import SaveData
from scistudio.blocks.registry import BlockRegistry, _spec_from_class
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text
from scistudio.engine.materialisation import materialise_to_file, reconstruct_from_file

PICKLE_EXTS = {".pkl", ".pickle"}

# (core_type, extension) slots that SAVE but cannot RELOAD due to engine
# round-trip defects. See alpha-test-suite/FINDINGS.md.
#   FIND-A: composite .json saver writes slot key 'file', loader reads 'path'.
#   FIND-B: tabular .pkl/.pickle saves the Arrow Table, loader wants the object.
BROKEN_RELOAD: set[tuple[str, str]] = {
    ("CompositeData", ".json"),
    ("DataFrame", ".pkl"),
    ("DataFrame", ".pickle"),
    ("Series", ".pkl"),
    ("Series", ".pickle"),
}


def _core_registry() -> BlockRegistry:
    reg = BlockRegistry()
    reg._register_spec(_spec_from_class(LoadData, source="alpha-suite"))
    reg._register_spec(_spec_from_class(SaveData, source="alpha-suite"))
    return reg


REG = _core_registry()


# ---------------------------------------------------------------------------
# Builders (self-contained; mirror the generator construction contracts)
# ---------------------------------------------------------------------------


def _build_array(ext: str, i: int = 0) -> Array:
    # 1-D so every save extension works: Array .parquet is single-column-only
    # by design. N-D coverage for .npy/.npz/.zarr is in test_array_nd_roundtrip.
    arr = np.arange(8, dtype=np.float64) + i
    return Array(axes=["x"], shape=arr.shape, dtype=str(arr.dtype), data=arr)


def _build_dataframe(ext: str, i: int = 0) -> DataFrame:
    table = pa.table({"id": [0 + i, 1 + i, 2 + i], "value": [0.5, 1.5, 2.5]})
    return DataFrame(columns=["id", "value"], row_count=3, data=table)


def _build_series(ext: str, i: int = 0) -> Series:
    table = pa.table({"value": pa.array([1.0 + i, 2.0 + i, 3.0 + i], type=pa.float64())})
    return Series(value_name="value", length=3, data=table)


def _build_text(ext: str, i: int = 0) -> Text:
    return Text(content=f"sample {i} content\nsecond line\n", format="plain")


def _build_composite(ext: str, i: int = 0) -> CompositeData:
    sub = Array(axes=["x"], shape=(3,), dtype="float64", data=np.array([1.0, 2.0, 3.0]) + i)
    return CompositeData(slots={"array_slot": sub})


# core_type -> (builder, type, load_exts, save_exts)
MATRIX: dict[str, dict[str, Any]] = {
    "Array": {
        "build": _build_array,
        "type": Array,
        "load": [".npy", ".npz", ".zarr", ".parquet", ".pq", ".pkl", ".pickle"],
        "save": [".npy", ".npz", ".zarr", ".parquet", ".pq", ".pkl", ".pickle"],
    },
    "DataFrame": {
        "build": _build_dataframe,
        "type": DataFrame,
        "load": [".csv", ".tsv", ".parquet", ".pq", ".json", ".pkl", ".pickle"],
        "save": [".csv", ".tsv", ".parquet", ".pq", ".json", ".pkl", ".pickle"],
    },
    "Series": {
        "build": _build_series,
        "type": Series,
        "load": [".csv", ".tsv", ".parquet", ".pq", ".pkl", ".pickle"],
        "save": [".csv", ".tsv", ".parquet", ".pq", ".pkl", ".pickle", ".json"],
    },
    "Text": {
        "build": _build_text,
        "type": Text,
        "load": [".txt", ".md", ".markdown", ".html", ".htm", ".xml", ".yaml", ".yml", ".toml", ".log"],
        "save": [".txt", ".md", ".markdown", ".html", ".htm", ".xml", ".yaml", ".yml", ".toml", ".log", ".json"],
    },
    "CompositeData": {
        "build": _build_composite,
        "type": CompositeData,
        "load": [".json"],
        "save": [".json"],
    },
}


# ---------------------------------------------------------------------------
# IO helpers (pickle needs the allow_pickle opt-in on both ends)
# ---------------------------------------------------------------------------


def _save(obj: Any, dest_dir: Path, stem: str, ext: str, core_type: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    if ext in PICKLE_EXTS:
        path = dest_dir / f"{stem}{ext}"
        params = {"path": str(path), "core_type": core_type, "allow_pickle": True}
        SaveData(config={"params": params}).save(obj, BlockConfig(params=params))
        return path
    return materialise_to_file(obj, dest_dir, ext, filename_stem=stem, registry=REG)


def _load(path: Path, target: type, core_type: str, ext: str) -> Any:
    if ext in PICKLE_EXTS:
        params = {"path": str(path), "core_type": core_type, "allow_pickle": True}
        return LoadData(config={"params": params}).load(BlockConfig(params=params))
    return reconstruct_from_file(path, target, registry=REG)


def _assert_table_values(loaded_tbl: Any, src_tbl: Any) -> None:
    """Compare two Arrow tables by column names AND values (numeric-tolerant)."""
    assert isinstance(loaded_tbl, pa.Table), f"reload payload is {type(loaded_tbl).__name__}, not a Table"
    assert isinstance(src_tbl, pa.Table)
    assert sorted(loaded_tbl.column_names) == sorted(src_tbl.column_names), (
        f"columns {loaded_tbl.column_names} != {src_tbl.column_names}"
    )
    for col in src_tbl.column_names:
        got = loaded_tbl.column(col).to_pylist()
        want = src_tbl.column(col).to_pylist()
        assert len(got) == len(want), f"column {col}: length {len(got)} != {len(want)}"
        non_null = [x for x in want if x is not None]
        if non_null and all(isinstance(x, (int, float)) for x in non_null):
            np.testing.assert_allclose(
                [float(x) for x in got],
                [float(x) for x in want],
                rtol=1e-6,
                atol=1e-9,
                err_msg=f"column {col!r} values differ",
            )
        else:
            assert got == want, f"column {col!r} values differ: {got} != {want}"


def _assert_invariant(core_type: str, src: Any, loaded: Any) -> None:
    assert type(loaded).__name__ == core_type, f"{core_type}: reload type {type(loaded).__name__}"
    if core_type == "Array":
        # Compare payload values, not just shape: a saver that preserves shape
        # but corrupts values must fail. zarr restores data via to_memory() even
        # though it drops the .shape attribute (FIND-D); the data must be intact.
        np.testing.assert_array_equal(np.asarray(loaded.to_memory()), np.asarray(src.to_memory()))
    elif core_type in ("DataFrame", "Series"):
        _assert_table_values(loaded.get_in_memory_data(), src.get_in_memory_data())
    elif core_type == "Text":
        assert loaded.content == src.content
    elif core_type == "CompositeData":
        # Forward-looking (the only composite IO path is broken — FIND-A — so
        # this is reached only once that is fixed and unmarked): every child
        # slot's values must survive.
        assert set(loaded._slots) == set(src._slots)
        for name in src._slots:
            np.testing.assert_array_equal(
                np.asarray(loaded.get(name).to_memory()),
                np.asarray(src.get(name).to_memory()),
            )


# Build the parametrized (core_type, load_ext, save_ext) id-list.
def _matrix_params() -> list[Any]:
    params: list[Any] = []
    for core_type, spec in MATRIX.items():
        for load_ext in spec["load"]:
            for save_ext in spec["save"]:
                marks = []
                # Cannot LOAD the source file -> whole combo is expected-broken.
                if (core_type, load_ext) in BROKEN_RELOAD:
                    marks.append(pytest.mark.xfail(reason=f"FINDINGS: load {core_type}{load_ext}", strict=False))
                params.append(
                    pytest.param(
                        core_type,
                        load_ext,
                        save_ext,
                        marks=marks,
                        id=f"{core_type}:{load_ext.lstrip('.')}->{save_ext.lstrip('.')}",
                    )
                )
    return params


@pytest.mark.parametrize(("core_type", "load_ext", "save_ext"), _matrix_params())
def test_load_save_matrix(tmp_path: Path, core_type: str, load_ext: str, save_ext: str) -> None:
    spec = MATRIX[core_type]
    src = spec["build"](load_ext)

    # LOAD under test: write a load_ext file, read it back.
    load_file = _save(src, tmp_path / "in", "seed", load_ext, core_type)
    loaded = _load(load_file, spec["type"], core_type, load_ext)
    if isinstance(loaded, type(loaded)) and hasattr(loaded, "items"):
        # LoadData may return a single-item Collection for the pickle path.
        loaded = loaded[0] if not isinstance(loaded, spec["type"]) else loaded
    assert loaded is not None

    # SAVE under test: write the loaded object to save_ext.
    out_file = _save(loaded, tmp_path / "out", "out", save_ext, core_type)
    assert out_file.exists(), f"{core_type} save to {save_ext} produced no file"
    # zarr is a directory store; everything else is a non-empty file.
    if out_file.is_file():
        assert out_file.stat().st_size > 0
    else:
        assert any(out_file.rglob("*")), f"{core_type} {save_ext} store is empty"

    # If save_ext is reloadable, confirm the data survived the save.
    if save_ext in spec["load"] and (core_type, save_ext) not in BROKEN_RELOAD:
        reloaded = _load(out_file, spec["type"], core_type, save_ext)
        if hasattr(reloaded, "items") and not isinstance(reloaded, spec["type"]):
            reloaded = reloaded[0]
        _assert_invariant(core_type, src, reloaded)


# ---------------------------------------------------------------------------
# Collection (10-item) round-trip via LoadData multi-path
# ---------------------------------------------------------------------------

# Representative loadable extension per type for the collection check.
_COLLECTION_EXT = {
    "Array": ".npy",
    "DataFrame": ".csv",
    "Series": ".csv",
    "Text": ".txt",
    "CompositeData": ".json",  # xfail: FIND-A
}


@pytest.mark.parametrize(
    "core_type",
    [
        pytest.param(
            ct,
            marks=(
                [pytest.mark.xfail(reason="FINDINGS FIND-A composite .json", strict=False)]
                if (ct, _COLLECTION_EXT[ct]) in BROKEN_RELOAD
                else []
            ),
            id=ct,
        )
        for ct in MATRIX
    ],
)
def test_collection_roundtrip_10(tmp_path: Path, core_type: str) -> None:
    spec = MATRIX[core_type]
    ext = _COLLECTION_EXT[core_type]
    paths: list[str] = []
    for i in range(10):
        obj = spec["build"](ext, i)
        p = _save(obj, tmp_path / "coll", f"item_{i:02d}", ext, core_type)
        paths.append(str(p))

    # LoadData multi-path -> Collection of 10.
    params = {"core_type": core_type, "path": paths}
    result = LoadData(config={"params": params}).load(BlockConfig(params=params))
    items = list(result)
    assert len(items) == 10, f"{core_type}: collection load returned {len(items)} of 10"
    for item in items:
        assert type(item).__name__ == core_type


# ---------------------------------------------------------------------------
# N-D Array coverage (the matrix uses 1-D; .parquet is single-column-only)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape", [(3, 4), (2, 3, 4)], ids=["2d", "3d"])
@pytest.mark.parametrize("ext", [".npy", ".npz", ".zarr"])
def test_array_nd_roundtrip(tmp_path: Path, shape: tuple[int, ...], ext: str) -> None:
    axes = ["y", "x"] if len(shape) == 2 else ["z", "y", "x"]
    data = np.arange(int(np.prod(shape)), dtype=np.float64).reshape(shape)
    src = Array(axes=axes, shape=shape, dtype="float64", data=data)
    path = _save(src, tmp_path, "nd", ext, "Array")
    back = reconstruct_from_file(path, Array, registry=REG)
    # Verify the materialised payload (zarr reload restores data but not the
    # .shape attribute — FIND-D); to_memory() is the authoritative readback.
    np.testing.assert_array_equal(np.asarray(back.to_memory()), data)


# ---------------------------------------------------------------------------
# Artifact (opaque passthrough): bytes in must equal bytes out
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ext", [".bin", ".dat", ".json", ".csv", ".png", ".txt"])
def test_artifact_passthrough_preserves_bytes(tmp_path: Path, ext: str) -> None:
    raw = b"\x00\x01OPAQUE-" + ext.encode("ascii") + b"\xfe\xff\n"
    src_path = tmp_path / f"in{ext}"
    src_path.write_bytes(raw)
    art = Artifact(file_path=src_path, mime_type="application/octet-stream")

    out = materialise_to_file(art, tmp_path / "out", ext, filename_stem="a", registry=REG)
    back = reconstruct_from_file(out, Artifact, registry=REG)

    assert type(back).__name__ == "Artifact"
    assert back.get_in_memory_data() == raw, f"{ext}: artifact bytes changed in round-trip"
