"""Structural tests for the ``io/savers`` and ``io/loaders`` sub-packages.

These tests guard the Path D refactor from issue #1459 (Phase 2 of
backend god-file refactor umbrella #1427):

1. ADR-028 Addendum 1 §C9 ("private functions, not helper classes") —
   no helper class may be introduced into the new ``_capability.py`` /
   ``_helpers.py`` / ``_streaming.py`` sibling modules. Only ``SaveData``
   and ``LoadData`` remain as classes.

2. Public import surface — :class:`SaveData` and :class:`LoadData` must
   continue to be importable from their canonical sub-package and from
   the legacy ``save_data`` / ``load_data`` module paths.

3. End-to-end behaviour — the dispatch functions exercise every new
   sibling module (capability + helpers + streaming) by writing and
   reading a few core types through the public ``SaveData.save()`` /
   ``LoadData.load()`` API. The tests never import private symbols
   directly from sibling modules so the package-private contract stays
   honest.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from scistudio.blocks.io.loaders import LoadData
from scistudio.blocks.io.savers import SaveData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.text import Text

# ---------------------------------------------------------------------------
# 1. §C9 compliance: only ``SaveData`` and ``LoadData`` are classes
# ---------------------------------------------------------------------------


_SAVER_MODULES = (
    "scistudio.blocks.io.savers._capability",
    "scistudio.blocks.io.savers._helpers",
    "scistudio.blocks.io.savers._streaming",
)

_LOADER_MODULES = (
    "scistudio.blocks.io.loaders._capability",
    "scistudio.blocks.io.loaders._helpers",
)


def _module_class_names(module_name: str) -> list[str]:
    """Return the names of every ``class ...:`` top-level definition in *module_name*."""
    module = importlib.import_module(module_name)
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=module.__file__)
    return [node.name for node in tree.body if isinstance(node, ast.ClassDef)]


@pytest.mark.parametrize("module_name", _SAVER_MODULES + _LOADER_MODULES)
def test_sibling_helper_modules_define_no_classes(module_name: str) -> None:
    """ADR-028 Addendum 1 §C9 — helper siblings hold private functions only."""
    assert _module_class_names(module_name) == [], (
        f"{module_name} introduces helper classes; ADR-028 Addendum 1 §C9 forbids "
        "this. Refactor the helper back into module-level private functions."
    )


def test_save_data_module_defines_only_save_data_class() -> None:
    """The ``save_data`` module owns exactly one class: ``SaveData``."""
    assert _module_class_names("scistudio.blocks.io.savers.save_data") == ["SaveData"]


def test_load_data_module_defines_only_load_data_class() -> None:
    """The ``load_data`` module owns exactly one class: ``LoadData``."""
    assert _module_class_names("scistudio.blocks.io.loaders.load_data") == ["LoadData"]


# ---------------------------------------------------------------------------
# 2. Import surface preservation
# ---------------------------------------------------------------------------


def test_savedata_importable_from_subpackage_root() -> None:
    """``from scistudio.blocks.io.savers import SaveData`` keeps working."""
    from scistudio.blocks.io.savers import SaveData as SaveDataRoot

    assert SaveDataRoot is SaveData


def test_loaddata_importable_from_subpackage_root() -> None:
    """``from scistudio.blocks.io.loaders import LoadData`` keeps working."""
    from scistudio.blocks.io.loaders import LoadData as LoadDataRoot

    assert LoadDataRoot is LoadData


def test_savedata_importable_from_legacy_module_path() -> None:
    """Legacy callers that target the module path keep working."""
    from scistudio.blocks.io.savers.save_data import SaveData as SaveDataLegacy

    assert SaveDataLegacy is SaveData


def test_loaddata_importable_from_legacy_module_path() -> None:
    """Legacy callers that target the module path keep working."""
    from scistudio.blocks.io.loaders.load_data import LoadData as LoadDataLegacy

    assert LoadDataLegacy is LoadData


@pytest.mark.parametrize(
    "symbol",
    [
        "_CORE_TYPE_MAP",
        "_SAVE_CAPABILITIES",
        "_SAVE_EXTENSION_MAP",
        "_supported_save_extensions",
        "_resolve_save_format",
        "_legacy_save_extension_map",
        "_save_capability",
        "_check_pickle_gate",
        "_require_path",
        "_unwrap_for_save",
        "_dataframe_to_arrow_table",
        "_resolve_core_type_name",
        "_slot_path_for",
        "_zarr_store_copy",
        "_streaming_save_dataframe_csv",
        "_streaming_save_dataframe_parquet",
        "logger",
    ],
)
def test_savedata_legacy_private_symbols_reexported(symbol: str) -> None:
    """Symbols that used to live in ``save_data.py`` remain importable from it."""
    module = importlib.import_module("scistudio.blocks.io.savers.save_data")
    assert hasattr(module, symbol), (
        f"scistudio.blocks.io.savers.save_data.{symbol} disappeared; existing tests "
        "and external callers may break. Re-export it from the sibling module."
    )


@pytest.mark.parametrize(
    "symbol",
    [
        "_CORE_TYPE_MAP",
        "_LOAD_CAPABILITIES",
        "_LOAD_EXTENSION_MAP",
        "_supported_load_extensions",
        "_resolve_format",
        "_legacy_extension_map",
        "_load_capability",
        "_resolve_path",
        "_check_pickle_allowed",
        "_TEXT_FORMAT_MAP",
        # _MIME_GUESS removed with mime-type auto-guessing in the ADR-052 landing
        # (dropped from the loaders _helpers.__all__); no longer re-exported.
        "_PICKLE_NOTE",
        "_LOGGER",
    ],
)
def test_loaddata_legacy_private_symbols_reexported(symbol: str) -> None:
    """Symbols that used to live in ``load_data.py`` remain importable from it."""
    module = importlib.import_module("scistudio.blocks.io.loaders.load_data")
    assert hasattr(module, symbol), (
        f"scistudio.blocks.io.loaders.load_data.{symbol} disappeared; existing tests "
        "and external callers may break. Re-export it from the sibling module."
    )


# ---------------------------------------------------------------------------
# 3. End-to-end exercise of each sibling module via the public API
# ---------------------------------------------------------------------------


def test_capability_sibling_drives_save_dataframe_csv_dispatch(tmp_path: Path) -> None:
    """``SaveData.save()`` walks ``_capability._SAVE_EXTENSION_MAP`` for ``.csv``.

    Exercises the ``_capability.py`` sibling: format dispatch resolves
    through :func:`_resolve_save_format`, which is owned by that module.
    Also exercises the streaming sibling because DataFrame + CSV goes
    through ``_streaming_save_dataframe_csv``.
    """
    import pyarrow as pa

    df = DataFrame(columns=["a", "b"], row_count=2)
    df._arrow_table = pa.table({"a": [1, 2], "b": [10, 20]})  # type: ignore[attr-defined]

    out_path = tmp_path / "table.csv"
    saver = SaveData(config={"params": {"core_type": "DataFrame", "path": str(out_path)}})
    saver.save(df, saver.config)
    assert out_path.exists()
    contents = out_path.read_text(encoding="utf-8")
    # pyarrow.csv writes ``"a","b"`` for the header row, ``1,10`` for data.
    assert '"a"' in contents and '"b"' in contents
    assert "1,10" in contents and "2,20" in contents


def test_helpers_sibling_drives_save_text(tmp_path: Path) -> None:
    """``SaveData.save()`` for Text exercises ``_helpers._require_path``.

    The Text save path does not touch the streaming sibling. It still
    walks :func:`_require_path` (helpers sibling) and the
    capability-derived ``_supported_save_extensions`` error-message tail.
    """
    text = Text(content="hello", format="plain", encoding="utf-8")
    out_path = tmp_path / "msg.txt"
    saver = SaveData(config={"params": {"core_type": "Text", "path": str(out_path)}})
    saver.save(text, saver.config)
    assert out_path.read_text(encoding="utf-8") == "hello"


def test_loader_capability_sibling_drives_load_dataframe(tmp_path: Path) -> None:
    """``LoadData.load()`` walks the loader capability sibling for ``.csv``."""
    src = tmp_path / "tab.csv"
    src.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")

    loader = LoadData(config={"params": {"core_type": "DataFrame", "path": str(src)}})
    out = loader.load(loader.config)
    assert isinstance(out, DataFrame)
    assert out.columns == ["x", "y"]
    assert out.row_count == 2


def test_loader_helpers_sibling_pickle_gate_rejects(tmp_path: Path) -> None:
    """``LoadData.load()`` runs ``_helpers._check_pickle_allowed`` on ``.pkl``."""
    pkl_path = tmp_path / "data.pkl"
    pkl_path.write_bytes(b"\x80\x04N.")  # raw "None" pickle, valid bytes
    loader = LoadData(config={"params": {"core_type": "DataFrame", "path": str(pkl_path)}})
    with pytest.raises(ValueError, match="Refusing to load pickle file"):
        loader.load(loader.config)


def test_streaming_sibling_used_for_zarr_to_zarr_copy(tmp_path: Path) -> None:
    """``_save_array`` zarr-to-zarr path calls ``_streaming._zarr_store_copy``.

    Validates that the streaming sibling is reachable through the
    public ``SaveData.save()`` entry point for the zarr fast path.
    """
    zarr = pytest.importorskip("zarr")

    src_dir = tmp_path / "src.zarr"
    arr = zarr.open(str(src_dir), mode="w", shape=(4,), dtype="i4")
    arr[:] = [10, 20, 30, 40]

    from scistudio.core.storage.ref import StorageReference
    from scistudio.core.types.array import Array

    a = Array(axes=["axis_0"], shape=(4,), dtype="int32")
    a._storage_ref = StorageReference(backend="zarr", path=str(src_dir), format="zarr")

    out_dir = tmp_path / "out.zarr"
    saver = SaveData(config={"params": {"core_type": "Array", "path": str(out_dir)}})
    saver.save(a, saver.config)
    assert out_dir.exists()
    assert (out_dir / ".zarray").exists() or list(out_dir.iterdir())
