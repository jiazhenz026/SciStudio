"""SaveImage IO block — TIFF/Zarr writer for the imaging plugin.

T-IMG-003 implementation (Sprint C impl phase, narrow pilot scope).
See ``docs/specs/phase11-imaging-block-spec.md`` §9 T-IMG-003.

Scope for this implementation: write a single :class:`Image` (or a
length-1 :class:`Collection`) to ``.tif``/``.tiff`` via ``tifffile`` or
``.zarr`` via ``zarr``. Format is auto-detected from the output path
suffix but may be overridden via ``config['format']``. Broader format
support remains deferred per the Sprint C pilot dispatch prompt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import numpy as np

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort
from scieasy.blocks.io.io_block import IOBlock
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy_blocks_imaging.types import Image

_TIFF_FORMAT = "tiff"
_ZARR_FORMAT = "zarr"
_SUPPORTED_FORMATS = frozenset({_TIFF_FORMAT, _ZARR_FORMAT})

_EXT_TO_FORMAT: dict[str, str] = {
    ".tif": _TIFF_FORMAT,
    ".tiff": _TIFF_FORMAT,
    ".zarr": _ZARR_FORMAT,
}


def _materialise(image: Image) -> np.ndarray:
    """Return the underlying ``numpy`` array backing *image*.

    ADR-031 Phase 3: always routes through :meth:`DataObject.to_memory`
    which reads from storage via the backend. The former ``_data``
    backdoor is removed per ADR-031 D3.
    """
    return np.asarray(image.to_memory())


def _unwrap_image(obj: DataObject | Collection) -> Image:
    """Extract a single :class:`Image` from either a bare instance or
    a length-1 :class:`Collection`."""
    if isinstance(obj, Image):
        return obj
    if isinstance(obj, Collection):
        if len(obj) == 0:
            raise ValueError("SaveImage: received an empty Collection")
        if len(obj) == 1:
            item = obj[0]
            if not isinstance(item, Image):
                raise ValueError(f"SaveImage: collection item is {type(item).__name__}, expected Image")
            return item
        raise ValueError("SaveImage: multi-item Collection; use save() which handles batch mode")
    raise ValueError(f"SaveImage: expected Image or Collection[Image], got {type(obj).__name__}")


def _resolve_format(path: Path, explicit: str | None) -> str:
    """Resolve the output format from an explicit config value or the
    path suffix. Raises :class:`ValueError` on unknown values."""
    if explicit is not None:
        fmt = explicit.lower()
        if fmt == "tif":
            fmt = _TIFF_FORMAT
        if fmt not in _SUPPORTED_FORMATS:
            raise ValueError(
                f"SaveImage: unsupported format {explicit!r}; supported formats are {sorted(_SUPPORTED_FORMATS)}"
            )
        return fmt
    ext = path.suffix.lower()
    if ext not in _EXT_TO_FORMAT:
        raise ValueError(
            f"SaveImage: cannot infer format from extension {ext!r}; "
            f"pass config['format'] explicitly (one of {sorted(_SUPPORTED_FORMATS)})"
        )
    return _EXT_TO_FORMAT[ext]


def _write_tiff(image: Image, path: Path) -> None:
    """Write an Image to TIFF.

    ADR-031 Phase 3 (Task 18): for zarr-backed images with a leading
    z/t axis, writes page-by-page from zarr to avoid full
    materialisation. Falls back to full materialisation for non-zarr
    backends or 2D images.
    """
    import tifffile

    ref = getattr(image, "_storage_ref", None)
    axes_str = "".join(image.axes).upper()

    # Streaming path: zarr-backed images with 3+ dimensions.
    # Read one plane at a time from zarr and write as TIFF pages.
    if ref is not None and ref.backend == "zarr" and image.shape is not None and len(image.shape) >= 3:
        import zarr as zarr_lib

        arr = zarr_lib.open_array(ref.path, mode="r")
        with tifffile.TiffWriter(str(path)) as tw:
            # Iterate over the first axis (typically z or t), writing
            # each 2D+ plane as a separate TIFF page.
            for i in range(arr.shape[0]):
                plane = np.asarray(arr[i])
                tw.write(plane, metadata={"axes": axes_str} if i == 0 else None)
        return

    # Fallback: full materialisation for non-zarr or 2D images.
    data = _materialise(image)
    tifffile.imwrite(str(path), data, metadata={"axes": axes_str})


def _write_zarr(image: Image, path: Path) -> None:
    import zarr

    data = _materialise(image)
    # Remove any previous store contents so repeated writes are
    # deterministic; zarr 3 refuses to overwrite an existing group by
    # default.
    if path.exists():
        import shutil

        shutil.rmtree(path)
    root = zarr.open_group(str(path), mode="w")
    arr = root.create_array(
        name="data",
        shape=data.shape,
        dtype=data.dtype,
    )
    arr[...] = data
    root.attrs["axes"] = list(image.axes)


class SaveImage(IOBlock):
    """TIFF/Zarr image writer.

    Accepts a single :class:`Image`, a length-1 :class:`Collection[Image]`,
    or a multi-item :class:`Collection[Image]` (batch mode) and writes to
    the configured path.  For batch mode the path is treated as a directory
    and files are auto-numbered (``image_0000.tif``, etc.).
    """

    direction: ClassVar[str] = "output"
    type_name: ClassVar[str] = "imaging.save_image"
    name: ClassVar[str] = "Save Image"
    description: ClassVar[str] = "Save an Image to a TIFF or Zarr store."
    subcategory: ClassVar[str] = "io"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="images", accepted_types=[Image], is_collection=True),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            # ADR-030: ``path`` is inherited from IOBlock base class via MRO merge.
            # Direction-aware post-processing auto-switches to directory_browser.
            "format": {
                "type": "string",
                "enum": ["tiff", "zarr"],
                "ui_priority": 1,
            },
        },
        "required": [],
    }

    def load(
        self, config: BlockConfig, output_dir: str = ""
    ) -> DataObject | Collection:  # pragma: no cover - output block
        """Direction is ``output``; ``load`` is unreachable via dispatch."""
        raise NotImplementedError("SaveImage is an output block; use save()")

    def _write_single(self, image: Image, path: Path, fmt: str) -> None:
        """Write a single :class:`Image` to *path* in the given format."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == _TIFF_FORMAT:
            _write_tiff(image, path)
        else:
            _write_zarr(image, path)

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Write *obj* to the configured path.

        Args:
            obj: An :class:`Image` or a :class:`Collection[Image]`.
                 Multi-item collections are saved in batch mode with
                 auto-numbered filenames.
            config: BlockConfig with ``path`` and optional ``format``.

        Raises:
            ValueError: If the collection is empty, contains non-Image
                items, or the format cannot be resolved.
        """
        raw_path = config.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError("SaveImage: config['path'] must be a non-empty string")
        path = Path(raw_path)

        fmt_cfg = config.get("format")
        if fmt_cfg is not None and not isinstance(fmt_cfg, str):
            raise ValueError(f"SaveImage: config['format'] must be a string or omitted, got {type(fmt_cfg).__name__}")

        # Handle Collection: save each item with auto-numbered filename
        if isinstance(obj, Collection):
            if len(obj) == 0:
                raise ValueError("SaveImage: empty Collection")
            if len(obj) == 1:
                # Single-item collection: use path as-is
                image = _unwrap_image(obj)
                fmt = _resolve_format(path, fmt_cfg)
                self._write_single(image, path, fmt)
                return

            # Multi-item collection: path is treated as directory
            out_dir = path if path.suffix == "" else path.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            ext = f".{fmt_cfg}" if fmt_cfg else ".tif"
            fmt = _resolve_format(Path(f"dummy{ext}"), fmt_cfg)
            for i, item in enumerate(obj):
                if not isinstance(item, Image):
                    raise ValueError(f"SaveImage: Collection item {i} is not an Image")
                item_path = out_dir / f"image_{i:04d}{ext}"
                self._write_single(item, item_path, fmt)
            return

        # Single image (not in Collection)
        image = _unwrap_image(obj)
        fmt = _resolve_format(path, fmt_cfg)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_single(image, path, fmt)
