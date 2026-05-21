"""T-IMG-003 tests — SaveImage TIFF/Zarr pilot scope."""

from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest
from scistudio_blocks_imaging.io.load_image import LoadImage
from scistudio_blocks_imaging.io.save_image import SaveImage
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection


def _make_image(arr: np.ndarray, axes: list[str]) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype)
    img._data = arr
    return img


def test_t_img_003_module_importable() -> None:
    """The T-IMG-003 module imports cleanly."""
    importlib.import_module("scistudio_blocks_imaging.io.save_image")


def test_t_img_003_class_has_required_classvars() -> None:
    """SaveImage declares the mandatory IOBlock ClassVars."""
    assert SaveImage.type_name == "imaging.save_image"
    assert SaveImage.name == "Save Image"
    assert SaveImage.subcategory == "io"
    assert SaveImage.direction == "output"
    assert "path" in SaveImage.config_schema["properties"]
    assert len(SaveImage.input_ports) == 1


def test_save_single_image_to_tiff(tmp_path: Path) -> None:
    """Writing a bare Image to a .tif path materialises a valid TIFF."""
    arr = np.arange(12, dtype=np.uint16).reshape(3, 4)
    img = _make_image(arr, ["y", "x"])

    out_path = tmp_path / "out.tif"
    SaveImage().save(img, BlockConfig(params={"path": str(out_path)}))

    assert out_path.is_file()
    import tifffile

    back = tifffile.imread(str(out_path))
    assert np.array_equal(back, arr)


def test_save_collection_tiff_round_trip_preserves_data_and_axes(
    tmp_path: Path,
) -> None:
    """Length-1 Collection round-trip preserves data, axes, dtype."""
    arr = np.arange(30, dtype=np.int16).reshape(2, 3, 5)
    img = _make_image(arr, ["c", "y", "x"])
    col = Collection(items=[img], item_type=Image)

    out_path = tmp_path / "rt.tif"
    SaveImage().save(col, BlockConfig(params={"path": str(out_path)}))

    loaded = LoadImage().load(BlockConfig(params={"path": str(out_path)}))
    out = loaded[0]
    assert out.axes == ["c", "y", "x"]
    assert out.shape == (2, 3, 5)
    assert out.dtype == np.int16
    assert np.array_equal(out._data, arr)


def test_save_zarr_round_trip(tmp_path: Path) -> None:
    """Zarr save then LoadImage returns equal data."""
    arr = np.arange(60, dtype=np.float32).reshape(3, 4, 5)
    img = _make_image(arr, ["c", "y", "x"])

    out_path = tmp_path / "store.zarr"
    SaveImage().save(img, BlockConfig(params={"path": str(out_path)}))

    loaded = LoadImage().load(BlockConfig(params={"path": str(out_path)}))
    out = loaded[0]
    assert out.axes == ["c", "y", "x"]
    assert np.array_equal(out._data, arr)


def test_save_format_override_forces_tiff(tmp_path: Path) -> None:
    """An explicit config['format']='tiff' writes a TIFF even with a .dat suffix."""
    arr = np.zeros((2, 2), dtype=np.uint8)
    img = _make_image(arr, ["y", "x"])

    out_path = tmp_path / "forced.dat"
    SaveImage().save(
        img,
        BlockConfig(params={"path": str(out_path), "format": "tiff"}),
    )
    assert out_path.is_file()
    import tifffile

    back = tifffile.imread(str(out_path))
    assert np.array_equal(back, arr)


def test_save_unknown_extension_raises(tmp_path: Path) -> None:
    """An unknown extension with no explicit format raises ValueError."""
    arr = np.zeros((2, 2), dtype=np.uint8)
    img = _make_image(arr, ["y", "x"])
    with pytest.raises(ValueError, match="cannot infer format"):
        SaveImage().save(img, BlockConfig(params={"path": str(tmp_path / "mystery.xyz")}))


def test_save_invalid_format_value_raises(tmp_path: Path) -> None:
    """An unsupported explicit format raises ValueError.

    ADR-043 / FR-005 expanded SaveImage to write PNG/JPEG via Pillow;
    Bio-Formats vendor formats remain load-only and so are still
    rejected on save.
    """
    arr = np.zeros((2, 2), dtype=np.uint8)
    img = _make_image(arr, ["y", "x"])
    with pytest.raises(ValueError, match="unsupported format"):
        SaveImage().save(
            img,
            BlockConfig(params={"path": str(tmp_path / "x.czi"), "format": "czi"}),
        )


def test_save_batch_collection_to_directory(tmp_path: Path) -> None:
    """Multi-item Collection is saved as auto-numbered files in a directory."""
    arr = np.zeros((2, 2), dtype=np.uint8)
    imgs = [_make_image(arr.copy(), ["y", "x"]) for _ in range(2)]
    col = Collection(items=imgs, item_type=Image)
    out_dir = tmp_path / "batch_out"
    SaveImage().save(col, BlockConfig(params={"path": str(out_dir)}))
    assert (out_dir / "image_0000.tif").exists()
    assert (out_dir / "image_0001.tif").exists()


def test_save_batch_collection_with_format_override(tmp_path: Path) -> None:
    """Multi-item Collection respects explicit format config."""
    arr = np.zeros((2, 2), dtype=np.uint8)
    imgs = [_make_image(arr.copy(), ["y", "x"]) for _ in range(3)]
    col = Collection(items=imgs, item_type=Image)
    out_dir = tmp_path / "batch_zarr"
    SaveImage().save(col, BlockConfig(params={"path": str(out_dir), "format": "zarr"}))
    assert (out_dir / "image_0000.zarr").exists()
    assert (out_dir / "image_0001.zarr").exists()
    assert (out_dir / "image_0002.zarr").exists()


def test_save_empty_collection_raises(tmp_path: Path) -> None:
    """Empty collections are rejected."""
    col = Collection(items=[], item_type=Image)
    with pytest.raises(ValueError, match="empty"):
        SaveImage().save(col, BlockConfig(params={"path": str(tmp_path / "e.tif")}))


def test_save_creates_parent_directory(tmp_path: Path) -> None:
    """Missing parent directories are created automatically."""
    arr = np.zeros((2, 2), dtype=np.uint8)
    img = _make_image(arr, ["y", "x"])
    out_path = tmp_path / "nested" / "deeper" / "image.tif"
    SaveImage().save(img, BlockConfig(params={"path": str(out_path)}))
    assert out_path.is_file()


# ---------------------------------------------------------------------------
# Issue #1075: supported_extensions ClassVar declaration mirrors LoadImage
# ---------------------------------------------------------------------------


class TestSupportedExtensionsClassVar:
    """SaveImage declares the canonical ``supported_extensions`` mapping
    (ADR-028 §D8 / #1075). Per ADR-043 FR-005, SaveImage covers only
    writable formats — TIFF / Zarr / PNG / JPEG — so the SaveImage set
    is a STRICT SUBSET of :attr:`LoadImage.supported_extensions` (the
    Bio-Formats vendor formats are load-only by library design).
    Module-level legacy constants (``_TIFF_FORMAT`` / ``_ZARR_FORMAT`` /
    ``_SUPPORTED_FORMATS`` / ``_EXT_TO_FORMAT``) have been removed in
    favor of routing through :meth:`IOBlock._detect_format`."""

    def test_classvar_equals_expected_mapping(self) -> None:
        """SaveImage.supported_extensions exactly matches the spec.

        Covers writable formats only (FR-005). Bio-Formats vendor
        formats are intentionally absent because python-bioformats is
        load-only.
        """
        assert SaveImage.supported_extensions == {
            ".tif": "tiff",
            ".tiff": "tiff",
            ".zarr": "zarr",
            ".png": "png",
            ".jpg": "jpeg",
            ".jpeg": "jpeg",
        }

    def test_save_image_is_subset_of_load_image_extensions(self) -> None:
        """SaveImage.supported_extensions ⊆ LoadImage.supported_extensions.

        Save extensions are a STRICT subset: Bio-Formats vendor formats
        (CZI/ND2/LIF/OIR/OIB) appear in LoadImage but not in SaveImage
        because python-bioformats is load-only (FR-005).
        """
        save_exts = set(SaveImage.supported_extensions.keys())
        load_exts = set(LoadImage.supported_extensions.keys())
        assert save_exts.issubset(load_exts)
        load_only = load_exts - save_exts
        assert load_only == {".czi", ".nd2", ".lif", ".oir", ".oib"}

    def test_module_level_legacy_constants_removed(self) -> None:
        """Pre-#1075 module-level constants are gone from save_image."""
        from scistudio_blocks_imaging.io import save_image

        assert not hasattr(save_image, "_TIFF_FORMAT"), "_TIFF_FORMAT must be removed per #1075"
        assert not hasattr(save_image, "_ZARR_FORMAT"), "_ZARR_FORMAT must be removed per #1075"
        assert not hasattr(save_image, "_SUPPORTED_FORMATS"), "_SUPPORTED_FORMATS must be removed per #1075"
        assert not hasattr(save_image, "_EXT_TO_FORMAT"), "_EXT_TO_FORMAT must be removed per #1075"

    def test_detect_format_resolves_known_extensions(self, tmp_path: Path) -> None:
        block = SaveImage()
        assert block._detect_format(tmp_path / "x.tif") == "tiff"
        assert block._detect_format(tmp_path / "x.tiff") == "tiff"
        assert block._detect_format(tmp_path / "x.zarr") == "zarr"
        assert block._detect_format(tmp_path / "x.xyz") is None

    def test_classvar_is_inherited_from_ioblock(self) -> None:
        from scistudio.blocks.io.io_block import IOBlock

        assert IOBlock.supported_extensions == {}
        assert SaveImage.supported_extensions != IOBlock.supported_extensions

    def test_unsupported_extension_error_message(self, tmp_path: Path) -> None:
        """Saving with an unknown suffix raises ValueError citing the format set."""
        arr = np.zeros((2, 2), dtype=np.uint8)
        img = _make_image(arr, ["y", "x"])
        out_path = tmp_path / "bogus.xyz"
        with pytest.raises(ValueError) as excinfo:
            SaveImage().save(img, BlockConfig(params={"path": str(out_path)}))
        msg = str(excinfo.value)
        # The error message references the supported format identifiers.
        assert "tiff" in msg
        assert "zarr" in msg

    def test_tiff_smoke_save_writes_file(self, tmp_path: Path) -> None:
        """A .tif save through the new dispatch produces a file on disk."""
        arr = np.zeros((2, 3), dtype=np.uint8)
        img = _make_image(arr, ["y", "x"])
        out = tmp_path / "smoke.tif"
        SaveImage().save(img, BlockConfig(params={"path": str(out)}))
        assert out.exists()
        assert out.stat().st_size > 0

    def test_zarr_smoke_save_writes_store(self, tmp_path: Path) -> None:
        """A .zarr save through the new dispatch produces a store directory."""
        arr = np.arange(6, dtype=np.float32).reshape(2, 3)
        img = _make_image(arr, ["y", "x"])
        out = tmp_path / "smoke.zarr"
        SaveImage().save(img, BlockConfig(params={"path": str(out)}))
        assert out.is_dir()
