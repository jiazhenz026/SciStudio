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
from scieasy.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scieasy.blocks.io.io_block import IOBlock
from scieasy.core.meta.framework import FrameworkMeta
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy_blocks_imaging.io.pillow_handler import _load_jpeg, _load_png
from scieasy_blocks_imaging.types import Image

# ADR-028 §D8 / issue #1075: module-level legacy constants
# (``_TIFF_EXTS`` / ``_ZARR_EXTS`` / ``_SUPPORTED_EXTS``) were removed
# in favor of the per-class :attr:`LoadImage.supported_extensions`
# ClassVar declared on the block. Format dispatch routes through
# :meth:`IOBlock._detect_format` (see ``LoadImage._load_single`` below).

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

    # ADR-043 / spec adr-043-package-migration FR-004: explicit per-format
    # capability declarations covering TIFF, vanilla Zarr, Pillow PNG/JPEG,
    # and the Bio-Formats vendor microscopy family (load-only). Every
    # capability declares ``level="format_specific"`` with
    # ``format_metadata_reads=("ome",)`` because the handlers populate
    # :attr:`Image.Meta.ome` to varying fidelity (full OME-XML for TIFF /
    # CZI / ND2 / LIF / OIR / OIB; EXIF DPI mapped to ome.physical_size_*
    # for PNG / JPEG; minimal for vanilla zarr stores). ``typed_meta_reads``
    # enumerates the typed ``Image.Meta`` fields the handler reliably
    # populates beyond ``ome``.
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id="scieasy-blocks-imaging.image.tiff.load",
            direction="load",
            data_type=Image,
            format_id="tiff",
            extensions=(".tif", ".tiff"),
            label="TIFF image",
            block_type="LoadImage",
            handler="_load_tiff",
            is_default=True,
            roundtrip_group="scieasy-blocks-imaging.image.tiff",
            metadata_fidelity=MetadataFidelity(
                level="format_specific",
                format_metadata_reads=("ome",),
                typed_meta_reads=("source_file",),
                notes=(
                    "Loads image payload and structural axes; OME-TIFF metadata"
                    " is detected inside the handler and populates Image.Meta.ome."
                ),
            ),
        ),
        FormatCapability(
            id="scieasy-blocks-imaging.image.zarr.load",
            direction="load",
            data_type=Image,
            format_id="zarr",
            extensions=(".zarr",),
            label="Zarr image",
            block_type="LoadImage",
            handler="_load_zarr",
            is_default=True,
            roundtrip_group="scieasy-blocks-imaging.image.zarr",
            metadata_fidelity=MetadataFidelity(
                level="format_specific",
                format_metadata_reads=("ome",),
                typed_meta_reads=("source_file",),
                notes=(
                    "Loads array payload + axes from the store; vanilla zarr"
                    " (OME-Zarr v0.4 first-class support is deferred)."
                ),
            ),
        ),
        FormatCapability(
            id="scieasy-blocks-imaging.image.png.load",
            direction="load",
            data_type=Image,
            format_id="png",
            extensions=(".png",),
            label="PNG image",
            block_type="LoadImage",
            handler="_load_png",
            is_default=True,
            roundtrip_group="scieasy-blocks-imaging.image.png",
            metadata_fidelity=MetadataFidelity(
                level="format_specific",
                format_metadata_reads=("ome",),
                typed_meta_reads=("source_file",),
                notes="Loads PNG via Pillow; EXIF DPI mapped onto Image.Meta.ome.",
            ),
        ),
        FormatCapability(
            id="scieasy-blocks-imaging.image.jpeg.load",
            direction="load",
            data_type=Image,
            format_id="jpeg",
            extensions=(".jpg", ".jpeg"),
            label="JPEG image",
            block_type="LoadImage",
            handler="_load_jpeg",
            is_default=True,
            roundtrip_group="scieasy-blocks-imaging.image.jpeg",
            metadata_fidelity=MetadataFidelity(
                level="format_specific",
                format_metadata_reads=("ome",),
                typed_meta_reads=("source_file",),
                notes="Loads JPEG via Pillow; EXIF DPI mapped onto Image.Meta.ome.",
            ),
        ),
        FormatCapability(
            id="scieasy-blocks-imaging.image.czi.load",
            direction="load",
            data_type=Image,
            format_id="czi",
            extensions=(".czi",),
            label="Zeiss CZI image",
            block_type="LoadImage",
            handler="_load_czi",
            is_default=True,
            roundtrip_group="scieasy-blocks-imaging.image.czi",
            metadata_fidelity=MetadataFidelity(
                level="format_specific",
                format_metadata_reads=("ome",),
                typed_meta_reads=("source_file",),
                notes="Loads Zeiss CZI via Bio-Formats; requires [bioformats] extras + JVM.",
            ),
        ),
        FormatCapability(
            id="scieasy-blocks-imaging.image.nd2.load",
            direction="load",
            data_type=Image,
            format_id="nd2",
            extensions=(".nd2",),
            label="Nikon ND2 image",
            block_type="LoadImage",
            handler="_load_nd2",
            is_default=True,
            roundtrip_group="scieasy-blocks-imaging.image.nd2",
            metadata_fidelity=MetadataFidelity(
                level="format_specific",
                format_metadata_reads=("ome",),
                typed_meta_reads=("source_file",),
                notes="Loads Nikon ND2 via Bio-Formats; requires [bioformats] extras + JVM.",
            ),
        ),
        FormatCapability(
            id="scieasy-blocks-imaging.image.lif.load",
            direction="load",
            data_type=Image,
            format_id="lif",
            extensions=(".lif",),
            label="Leica LIF image",
            block_type="LoadImage",
            handler="_load_lif",
            is_default=True,
            roundtrip_group="scieasy-blocks-imaging.image.lif",
            metadata_fidelity=MetadataFidelity(
                level="format_specific",
                format_metadata_reads=("ome",),
                typed_meta_reads=("source_file",),
                notes="Loads Leica LIF via Bio-Formats; requires [bioformats] extras + JVM.",
            ),
        ),
        FormatCapability(
            id="scieasy-blocks-imaging.image.oir.load",
            direction="load",
            data_type=Image,
            format_id="oir",
            extensions=(".oir",),
            label="Olympus OIR image",
            block_type="LoadImage",
            handler="_load_oir",
            is_default=True,
            roundtrip_group="scieasy-blocks-imaging.image.oir",
            metadata_fidelity=MetadataFidelity(
                level="format_specific",
                format_metadata_reads=("ome",),
                typed_meta_reads=("source_file",),
                notes="Loads Olympus OIR via Bio-Formats; requires [bioformats] extras + JVM.",
            ),
        ),
        FormatCapability(
            id="scieasy-blocks-imaging.image.oib.load",
            direction="load",
            data_type=Image,
            format_id="oib",
            extensions=(".oib",),
            label="Olympus OIB image",
            block_type="LoadImage",
            handler="_load_oib",
            is_default=True,
            roundtrip_group="scieasy-blocks-imaging.image.oib",
            metadata_fidelity=MetadataFidelity(
                level="format_specific",
                format_metadata_reads=("ome",),
                typed_meta_reads=("source_file",),
                notes="Loads Olympus OIB via Bio-Formats; requires [bioformats] extras + JVM.",
            ),
        ),
    )

    # ADR-028 §D8 / issue #1075: declarative mapping of file extensions
    # to a stable format identifier. ``_detect_format`` (inherited from
    # IOBlock) consults this mapping; ``BlockRegistry.find_loader``
    # (#1077) queries it for extension-based dispatch. The format ids
    # are passed through unchanged to the per-format dispatch arms in
    # :meth:`_load_single`. Per ADR-043 the per-class
    # ``format_capabilities`` declaration is authoritative; this mapping
    # stays in sync so the inherited ``IOBlock._detect_format`` keeps
    # working without recomputing capability lookups on every call.
    supported_extensions: ClassVar[dict[str, str]] = {
        ".tif": "tiff",
        ".tiff": "tiff",
        ".zarr": "zarr",
        ".png": "png",
        ".jpg": "jpeg",
        ".jpeg": "jpeg",
        ".czi": "czi",
        ".nd2": "nd2",
        ".lif": "lif",
        ".oir": "oir",
        ".oib": "oib",
    }

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="images", accepted_types=[Image], is_collection=True),
    ]
    _load_tiff = staticmethod(_load_tiff)
    _load_zarr = staticmethod(_load_zarr)
    _load_png = staticmethod(_load_png)
    _load_jpeg = staticmethod(_load_jpeg)

    # ADR-043 / spec adr-043-package-migration FR-008: Bio-Formats handlers
    # are bound as lazy-import wrappers on the class so the
    # ``BlockRegistry`` capability validation (which checks
    # ``hasattr(cls, capability.handler)`` at scan time) succeeds even
    # when the optional ``[bioformats]`` extras are not installed.
    # The wrappers defer the actual ``bioformats`` / ``javabridge`` /
    # ``ome_types`` imports to dispatch time and raise the clear
    # missing-extras :class:`ImportError` only when the user dispatches
    # a Bio-Formats capability without the extras.
    @staticmethod
    def _load_czi(path: Path, axes_override: list[str] | None = None, **kwargs: Any) -> Image:
        from scieasy_blocks_imaging.io import bioformats_handler

        return bioformats_handler._load_czi(path, axes_override, **kwargs)

    @staticmethod
    def _load_nd2(path: Path, axes_override: list[str] | None = None, **kwargs: Any) -> Image:
        from scieasy_blocks_imaging.io import bioformats_handler

        return bioformats_handler._load_nd2(path, axes_override, **kwargs)

    @staticmethod
    def _load_lif(path: Path, axes_override: list[str] | None = None, **kwargs: Any) -> Image:
        from scieasy_blocks_imaging.io import bioformats_handler

        return bioformats_handler._load_lif(path, axes_override, **kwargs)

    @staticmethod
    def _load_oir(path: Path, axes_override: list[str] | None = None, **kwargs: Any) -> Image:
        from scieasy_blocks_imaging.io import bioformats_handler

        return bioformats_handler._load_oir(path, axes_override, **kwargs)

    @staticmethod
    def _load_oib(path: Path, axes_override: list[str] | None = None, **kwargs: Any) -> Image:
        from scieasy_blocks_imaging.io import bioformats_handler

        return bioformats_handler._load_oib(path, axes_override, **kwargs)

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
        # Issue #1075: route format dispatch through the IOBlock contract
        # (ADR-028 §D8). ``_detect_format`` consults
        # :attr:`LoadImage.supported_extensions`.
        fmt = self._detect_format(path)
        if fmt is None:
            raise ValueError(
                f"LoadImage: unsupported image format {path.suffix.lower()!r}; "
                f"supported extensions are {sorted(LoadImage.supported_extensions.keys())}"
            )
        if fmt == "tiff":
            return _load_tiff(path, axes_override, block=self, output_dir=output_dir)
        if fmt == "zarr":
            return _load_zarr(path, axes_override)
        if fmt == "png":
            return _load_png(path, axes_override)
        if fmt == "jpeg":
            return _load_jpeg(path, axes_override)
        if fmt in {"czi", "nd2", "lif", "oir", "oib"}:
            # Dispatch through the class-level lazy-import wrapper
            # (e.g. ``LoadImage._load_czi``) so the registry's scan-time
            # handler-attribute validation matches the dispatch path.
            # The wrapper raises a clear ImportError naming the install
            # command (FR-008) when the [bioformats] extras or JVM are
            # missing.
            handler = getattr(LoadImage, f"_load_{fmt}")
            return handler(path, axes_override)
        # Defensive: every entry in :attr:`supported_extensions` is
        # expected to have a dispatch arm above; this branch becomes a
        # meaningful error if a future entry is added to the ClassVar
        # without a matching arm here.
        raise ValueError(f"LoadImage: format id {fmt!r} has no dispatch arm")

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
