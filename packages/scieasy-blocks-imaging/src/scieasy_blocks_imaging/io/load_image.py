"""LoadImage IO block — TIFF/Zarr loader for the imaging plugin.

T-IMG-002 implementation (Sprint C impl phase, narrow pilot scope).
See ``docs/specs/phase11-imaging-block-spec.md`` §9 T-IMG-002.

Scope for this implementation: ``.tif``/``.tiff`` via ``tifffile`` and
``.zarr`` via ``zarr``. Broader format support (PNG/JPG/NPY/CZI/ND2/LIF)
remains deferred per the Sprint C pilot dispatch prompt and is tracked
as out-of-scope on issue #354.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import numpy as np

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import OutputPort
from scieasy.blocks.io.io_block import IOBlock
from scieasy.core.meta.framework import FrameworkMeta
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy_blocks_imaging.types import Image

_TIFF_EXTS = frozenset({".tif", ".tiff"})
_ZARR_EXTS = frozenset({".zarr"})
_SUPPORTED_EXTS = _TIFF_EXTS | _ZARR_EXTS

# Mapping from tifffile single-letter axis codes to the SciEasy axis
# alphabet declared on :class:`Image`. ``S`` (samples) is treated as a
# discrete channel, matching the OME convention.
_TIFF_AXIS_MAP: dict[str, str] = {
    "T": "t",
    "Z": "z",
    "C": "c",
    "S": "c",
    "Y": "y",
    "X": "x",
}


def _default_axes_for_ndim(ndim: int) -> list[str]:
    """Return a reasonable default axis labelling for an N-D array.

    Used when the backend does not carry an axis annotation of its own
    (raw numpy round-trip, axis-less Zarr group, etc.). The defaults
    follow the common microscopy convention of spatial axes last.
    """
    if ndim == 2:
        return ["y", "x"]
    if ndim == 3:
        return ["c", "y", "x"]
    if ndim == 4:
        return ["t", "c", "y", "x"]
    if ndim == 5:
        return ["t", "z", "c", "y", "x"]
    if ndim == 6:
        return ["t", "z", "c", "lambda", "y", "x"]
    raise ValueError(f"LoadImage: cannot infer default axes for ndim={ndim}")


def _normalise_tiff_axes(tiff_axes: str, ndim: int) -> list[str]:
    """Translate tifffile's axis string into the SciEasy alphabet.

    Falls back to :func:`_default_axes_for_ndim` if the tiff axis string
    is empty or contains only characters outside the known mapping.
    """
    mapped = [_TIFF_AXIS_MAP[ch] for ch in tiff_axes if ch in _TIFF_AXIS_MAP]
    if len(mapped) == ndim and mapped:
        return mapped
    return _default_axes_for_ndim(ndim)


def _load_tiff(path: Path, axes_override: list[str] | None, block: Any = None, output_dir: str = "") -> Image:
    """Load a TIFF file into an :class:`Image`.

    ADR-031 D4: when ``block`` and ``output_dir`` are provided, uses
    streaming page-by-page writes via :meth:`IOBlock.persist_array`
    for constant-memory loading of large TIFFs. Falls back to eager
    in-memory loading (with base-class auto-flush) when no block is
    available.
    """
    import tifffile

    with tifffile.TiffFile(str(path)) as tf:
        series_axes = tf.series[0].axes if tf.series else ""
        n_pages = len(tf.pages)

        if n_pages == 0:
            raise ValueError(f"LoadImage: TIFF file has no pages: {path}")

        page0 = tf.pages[0]
        page_shape = page0.shape
        page_dtype = page0.dtype

        # Determine overall shape: multi-page TIFFs get a leading page dimension.
        if n_pages > 1:
            shape: tuple[int, ...] = (n_pages, *page_shape)
        else:
            shape = page_shape

        ndim = len(shape)
        axes = axes_override if axes_override is not None else _normalise_tiff_axes(series_axes, ndim)
        if len(axes) != ndim:
            raise ValueError(f"LoadImage: axes override {axes!r} does not match array ndim={ndim} for {path}")

        # ADR-031 D4 + Addendum 1: persist path for both multi-page and single-page.
        if block is not None and output_dir:
            if n_pages > 1:
                # Streaming path — write pages to zarr one at a time.
                def page_chunks() -> Any:
                    for i, page in enumerate(tf.pages):
                        yield (i, page.asarray())

                ref = block.persist_array(page_chunks(), shape, page_dtype, output_dir)
            else:
                # Single page: one-shot persist.
                data = tf.asarray()
                ref = block.persist_array(data, shape, page_dtype, output_dir)
            return Image(
                axes=axes,
                shape=shape,
                dtype=str(np.dtype(page_dtype)),
                framework=FrameworkMeta(source=str(path)),
                meta=Image.Meta(source_file=str(path)),
                storage_ref=ref,
            )
        else:
            # Fallback: no block context (direct call outside workflow).
            data_arr: np.ndarray = tf.asarray()
            img = Image(
                axes=axes,
                shape=tuple(data_arr.shape),
                dtype=str(data_arr.dtype),
                framework=FrameworkMeta(source=str(path)),
                meta=Image.Meta(source_file=str(path)),
            )
            img._data = data_arr  # type: ignore[attr-defined]
            return img


def _load_zarr(path: Path, axes_override: list[str] | None) -> Image:
    """Load a ``.zarr`` store as a reference-only :class:`Image`.

    ADR-031 D4: creates a :class:`StorageReference` pointing at the
    existing zarr store. Does NOT copy or eagerly read data. The zarr
    store is used in-place as the backing storage.

    Supports both a top-level array store and a group containing a
    single array named ``"data"``. Axis metadata is read from the group
    attribute ``"axes"`` when present.
    """
    import zarr

    from scieasy.core.storage.ref import StorageReference

    node = zarr.open(str(path), mode="r")
    attrs_axes: list[str] | None = None
    if isinstance(node, zarr.Array):
        arr_node: zarr.Array = node
    else:
        # group
        raw_attrs = dict(node.attrs)
        raw_axes = raw_attrs.get("axes")
        if isinstance(raw_axes, list):
            attrs_axes = [str(x) for x in raw_axes]
        if "data" not in node:
            raise ValueError(
                f"LoadImage: zarr group at {path} has no 'data' array (found keys: {sorted(node.array_keys())})"
            )
        data_node = node["data"]
        if not isinstance(data_node, zarr.Array):
            raise ValueError(f"LoadImage: zarr group at {path} 'data' entry is not an array")
        arr_node = data_node

    shape = tuple(arr_node.shape)
    dtype_str = str(arr_node.dtype)
    ndim = len(shape)
    if axes_override is not None:
        axes = axes_override
    elif attrs_axes is not None:
        axes = attrs_axes
    else:
        axes = _default_axes_for_ndim(ndim)
    if len(axes) != ndim:
        raise ValueError(f"LoadImage: axes {axes!r} do not match array ndim={ndim} for {path}")

    # ADR-031: reference-only — point at existing zarr store, no copy.
    # For group-backed stores with a "data" sub-array, point the ref at the
    # actual array node so ZarrBackend.read() (zarr.open_array) succeeds.
    arr_path = str(path) if isinstance(node, zarr.Array) else str(path / "data")
    ref = StorageReference(
        backend="zarr",
        path=arr_path,
        format="zarr",
        metadata={"shape": list(shape), "dtype": dtype_str},
    )
    return Image(
        axes=axes,
        shape=shape,
        dtype=dtype_str,
        framework=FrameworkMeta(source=str(path)),
        meta=Image.Meta(source_file=str(path)),
        storage_ref=ref,
    )


class LoadImage(IOBlock):
    """TIFF/Zarr image loader (pilot scope).

    Returns a single-item :class:`Collection` of :class:`Image`. Per
    ADR-028 Addendum 1 §D6' this block is STATIC: fixed ``output_ports``,
    no ``dynamic_ports``. The output type is always :class:`Image`.
    """

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "imaging.load_image"
    name: ClassVar[str] = "Load Image"
    description: ClassVar[str] = "Load a TIFF or Zarr image into an Image data object."
    subcategory: ClassVar[str] = "io"

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="images", accepted_types=[Image], is_collection=True),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            # ADR-030: ``path`` is inherited from IOBlock base class via MRO merge.
            "axes": {"type": "string", "ui_priority": 1},
        },
        "required": [],
    }

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """Load the configured file(s) into a ``Collection[Image]``.

        ADR-031 D4: ``output_dir`` is used for streaming TIFF persistence.

        Args:
            config: BlockConfig with ``path`` (str or list[str]) and optional
                ``axes`` (axis string override, e.g. ``"cyx"``). When
                ``path`` is a list, each file is loaded and all images are
                packed into a single :class:`Collection`.
            output_dir: Directory for persisting loaded data to storage.

        Returns:
            A :class:`Collection` of :class:`Image`. Length-1 for a single
            path, length-N for a list of N paths.

        Raises:
            FileNotFoundError: If any path does not exist.
            ValueError: If any extension is not in {.tif, .tiff, .zarr},
                or if ``path`` is neither a string nor a list of strings.
        """
        raw_path = config.get("path")

        axes_cfg = config.get("axes")
        axes_override: list[str] | None
        if axes_cfg is None:
            axes_override = None
        elif isinstance(axes_cfg, str):
            # Support both single-char ("cyx") and comma-separated ("lambda,y,x")
            axes_override = [a.strip() for a in axes_cfg.split(",")] if "," in axes_cfg else [ch for ch in axes_cfg]
        else:
            raise ValueError(f"LoadImage: config['axes'] must be a string or omitted, got {type(axes_cfg).__name__}")

        if isinstance(raw_path, list):
            # Multi-path: load each file and return a combined Collection.
            images: list[DataObject] = []
            for single_raw in raw_path:
                if not isinstance(single_raw, str) or not single_raw:
                    raise ValueError("LoadImage: each entry in path list must be a non-empty string")
                images.append(self._load_single(Path(single_raw), axes_override, output_dir))
            return Collection(items=images, item_type=Image)

        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError("LoadImage: config['path'] must be a non-empty string or list of strings")
        image = self._load_single(Path(raw_path), axes_override, output_dir)
        return Collection(items=[image], item_type=Image)

    def _load_single(self, path: Path, axes_override: list[str] | None, output_dir: str = "") -> Image:
        """Load a single image file into an :class:`Image`.

        Args:
            path: Absolute or relative path to a TIFF or Zarr file.
            axes_override: Optional per-axis label override list.
            output_dir: Directory for persisting loaded data to storage.

        Returns:
            A loaded :class:`Image`.

        Raises:
            FileNotFoundError: If the path does not exist.
            ValueError: If the extension is not supported.
        """
        if not path.exists():
            raise FileNotFoundError(f"LoadImage: no file at {path}")
        ext = path.suffix.lower()
        if ext not in _SUPPORTED_EXTS:
            raise ValueError(
                f"LoadImage: unsupported image format {ext!r}; supported extensions are {sorted(_SUPPORTED_EXTS)}"
            )
        if ext in _TIFF_EXTS:
            return _load_tiff(path, axes_override, block=self, output_dir=output_dir)
        return _load_zarr(path, axes_override)

    def save(
        self,
        obj: DataObject | Collection,
        config: BlockConfig,
    ) -> None:  # pragma: no cover - input block
        """LoadImage is an input block; ``save`` is unreachable via dispatch.

        The method is required only to satisfy the :class:`IOBlock` ABC;
        runtime dispatch in :meth:`IOBlock.run` routes on ``direction``
        and never invokes :meth:`save` on an ``input`` block.
        """
        raise NotImplementedError("LoadImage is an input block; use load()")
