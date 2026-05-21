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

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort
from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scistudio.blocks.io.io_block import IOBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio_blocks_imaging.io.pillow_handler import _save_jpeg, _save_png
from scistudio_blocks_imaging.types import Image

# ADR-028 §D8 / issue #1075: module-level legacy constants
# (``_TIFF_FORMAT`` / ``_ZARR_FORMAT`` / ``_SUPPORTED_FORMATS`` /
# ``_EXT_TO_FORMAT``) were removed in favor of the per-class
# :attr:`SaveImage.supported_extensions` ClassVar. Internal format
# string literals ``"tiff"`` / ``"zarr"`` survive as the ClassVar's
# values (the stable format identifier).


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


def _save_image_extension_map() -> dict[str, str]:
    """Derive ``extension -> format_id`` mapping from SaveImage capabilities.

    P2-03 / ADR-043 (Phase C1 audit follow-up, issue #1296): the
    canonical source of truth for SaveImage's writable formats is
    :attr:`SaveImage.format_capabilities`. Walking it here keeps
    ``_resolve_format`` from drifting away from the declared capabilities
    if a future contributor adds a writer record to ``format_capabilities``
    without updating the legacy ``supported_extensions`` ClassVar. Mirror
    of the A1 pattern in ``scistudio.blocks.io.savers.save_data
    ._legacy_save_extension_map``.

    Conflicting ``format_id`` for the same extension surfaces as
    :class:`RuntimeError` so misconfiguration fails loudly at import.
    """
    mapping: dict[str, str] = {}
    for capability in SaveImage.format_capabilities:
        for extension in capability.extensions:
            normalized = extension.lower()
            existing = mapping.get(normalized)
            if existing is not None and existing != capability.format_id:
                raise RuntimeError(
                    "SaveImage format_capabilities declare conflicting "
                    f"format_id for extension {normalized!r}: "
                    f"{existing!r} vs {capability.format_id!r}"
                )
            mapping[normalized] = capability.format_id
    return mapping


def _resolve_format(
    path: Path,
    explicit: str | None,
    block: SaveImage | None = None,
    capability_id: str | None = None,
) -> str:
    """Resolve the output format from an explicit config value, a
    capability id, or the path suffix.

    P2-03 (Phase C1 audit, issue #1296) / ADR-043 FR-005: the
    canonical source of truth for writable formats is
    :attr:`SaveImage.format_capabilities`. Both extension dispatch and
    the ``explicit`` config-string cross-check derive their inputs from
    ``format_capabilities`` via :func:`_save_image_extension_map`. The
    legacy ``SaveImage.supported_extensions`` mapping is left in place
    as documented scaffolding for the wider migration (see P2-02 in the
    Phase C1 audit report). Raises :class:`ValueError` on unknown
    values.

    Resolution order:
      1. ``explicit`` (legacy ``config['format']`` string) — wins for
         backward compatibility with workflow YAMLs that pin the format
         directly. Pre-existing field; new workflows configure the
         format via ``capability_id`` instead.
      2. ``capability_id`` (ADR-043 unified capability selector,
         surfaced via the Format dropdown in the bottom panel) — looked
         up in :attr:`SaveImage.format_capabilities` to get the
         declared ``format_id``.
      3. Extension dispatch on ``path.suffix``.
    """
    extension_map = _save_image_extension_map()
    supported_format_ids = set(extension_map.values())
    if explicit is not None:
        fmt = explicit.lower()
        if fmt == "tif":
            fmt = "tiff"
        elif fmt == "jpg":
            fmt = "jpeg"
        if fmt not in supported_format_ids:
            raise ValueError(
                f"SaveImage: unsupported format {explicit!r}; supported formats are {sorted(supported_format_ids)}"
            )
        return fmt
    if capability_id is not None:
        for cap in SaveImage.format_capabilities:
            if cap.id == capability_id:
                return cap.format_id
        raise ValueError(
            f"SaveImage: capability_id {capability_id!r} is not declared in SaveImage.format_capabilities; "
            f"valid ids are {sorted(c.id for c in SaveImage.format_capabilities)}"
        )
    if block is not None:
        detected = block._detect_format(path)
    else:
        # Walk Path.suffixes longest-first to match IOBlock._detect_format
        # semantics without needing an instance.
        detected = None
        suffixes = [s.lower() for s in path.suffixes]
        for start in range(len(suffixes)):
            candidate = "".join(suffixes[start:])
            if candidate in extension_map:
                detected = extension_map[candidate]
                break
    if detected is None:
        ext = path.suffix.lower()
        raise ValueError(
            f"SaveImage: cannot infer format from extension {ext!r}; "
            f"pass config['format'] explicitly (one of {sorted(supported_format_ids)})"
        )
    return detected


def _ome_xml_from_image(image: Image) -> str | None:
    """Serialise ``image.meta.ome`` to OME-XML when populated.

    P2-05 (Phase C1 audit, issue #1296) / ADR-043 FR-005 + SC-003: the
    ``scistudio-blocks-imaging.image.tiff.save`` capability advertises
    ``format_metadata_writes=("ome",)`` and the notes say "OME-XML
    written to the ImageDescription tag when Image.Meta.ome is
    populated". This helper produces the string that
    :func:`tifffile.imwrite` writes to TIFF tag 270 via its
    ``description=`` kwarg, so the advertised fidelity matches the
    implementation and the SC-003 round-trip (CZI/.ome.tif source →
    Resize Mode B → SaveImage(.ome.tif) → LoadImage → assert OME
    preserved) closes end-to-end.

    Returns ``None`` when there is no OME to write so callers can fall
    back to ``tifffile``'s default ``axes``-only metadata.
    """
    meta = getattr(image, "meta", None)
    ome = getattr(meta, "ome", None) if meta is not None else None
    if ome is None:
        return None
    # Prefer the function form for stability across ome_types versions.
    from ome_types import to_xml

    return to_xml(ome)


def _write_tiff(image: Image, path: Path) -> None:
    """Write an Image to TIFF.

    ADR-031 Phase 3 (Task 18): for zarr-backed images with a leading
    z/t axis, writes page-by-page from zarr to avoid full
    materialisation. Falls back to full materialisation for non-zarr
    backends or 2D images.

    P2-05 (Phase C1 audit, issue #1296) / ADR-043 FR-005 + SC-003: when
    ``image.meta.ome`` is populated, the serialised OME-XML is written
    to the TIFF ``ImageDescription`` tag via :func:`tifffile.imwrite`'s
    ``description`` kwarg. ``tifffile.imread`` auto-detects an OME-XML
    ``ImageDescription`` and exposes it on the resulting series; the
    matching ``LoadImage`` capability parses it back through
    :func:`ome_types.from_xml`.
    """
    import tifffile

    ref = getattr(image, "_storage_ref", None)
    axes_str = "".join(image.axes).upper()
    ome_xml = _ome_xml_from_image(image)

    # Streaming path: zarr-backed images with 3+ dimensions.
    # Read one plane at a time from zarr and write as TIFF pages.
    if ref is not None and ref.backend == "zarr" and image.shape is not None and len(image.shape) >= 3:
        import zarr as zarr_lib

        arr = zarr_lib.open_array(ref.path, mode="r")
        with tifffile.TiffWriter(str(path)) as tw:
            # Iterate over the first axis (typically z or t), writing
            # each 2D+ plane as a separate TIFF page. The OME-XML
            # description belongs only on page 0; subsequent pages get
            # no separate description (tifffile would otherwise emit
            # one ImageDescription per page).
            for i in range(arr.shape[0]):
                plane = np.asarray(arr[i])
                if i == 0:
                    write_kwargs: dict[str, Any] = {"metadata": {"axes": axes_str}}
                    if ome_xml is not None:
                        write_kwargs["description"] = ome_xml
                    tw.write(plane, **write_kwargs)
                else:
                    tw.write(plane, metadata=None)
        return

    # Fallback: full materialisation for non-zarr or 2D images.
    data = _materialise(image)
    write_kwargs: dict[str, Any] = {"metadata": {"axes": axes_str}}
    if ome_xml is not None:
        write_kwargs["description"] = ome_xml
    tifffile.imwrite(str(path), data, **write_kwargs)


def _write_zarr(image: Image, path: Path) -> None:
    """Write an Image to a Zarr store.

    Persists array data plus ``axes`` as a group attribute. No OME
    metadata or typed ``Image.Meta`` fields are written — the matching
    capability declaration in :attr:`SaveImage.format_capabilities` uses
    ``level="pixel_only"`` to reflect that (issue #1371). OME-Zarr v0.4
    first-class support is deferred.
    """
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

    # ADR-043 / spec adr-043-package-migration FR-005: explicit per-format
    # SAVE capabilities. Bio-Formats family (CZI/ND2/LIF/OIR/OIB) is
    # intentionally absent — python-bioformats is load-only by library
    # design.
    #
    # Capability metadata fidelity must match what each writer actually
    # persists. Issue #1371 narrowed previously broad
    # ``format_metadata_writes=("ome",)`` declarations to the subset each
    # writer really preserves:
    #
    # * TIFF — ``_write_tiff`` serialises full OME-XML via
    #   :func:`ome_types.to_xml` and writes it to the ``ImageDescription``
    #   tag, so ``format_metadata_writes=("ome",)`` is honest.
    # * Zarr — ``_write_zarr`` writes array data + ``attrs["axes"]`` only;
    #   no OME or typed Meta field is persisted. The capability drops to
    #   ``level="pixel_only"`` to match that behaviour.
    # * PNG / JPEG — Pillow writes only EXIF DPI on save, which is the
    #   OME ``physical_size_x`` / ``physical_size_y`` round-trip. The
    #   declaration uses hierarchical OME field paths so downstream
    #   lossy-save warnings (``lossyOmeFields``) report the truth.
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id="scistudio-blocks-imaging.image.tiff.save",
            direction="save",
            data_type=Image,
            format_id="tiff",
            extensions=(".tif", ".tiff"),
            label="TIFF image",
            block_type="SaveImage",
            handler="_write_tiff",
            is_default=True,
            roundtrip_group="scistudio-blocks-imaging.image.tiff",
            metadata_fidelity=MetadataFidelity(
                level="format_specific",
                format_metadata_writes=("ome",),
                typed_meta_writes=("pixel_size", "z_spacing", "channels"),
                notes=(
                    "Writes image payload + axes; OME-XML written to the"
                    " ImageDescription tag when Image.Meta.ome is populated."
                ),
            ),
        ),
        FormatCapability(
            id="scistudio-blocks-imaging.image.zarr.save",
            direction="save",
            data_type=Image,
            format_id="zarr",
            extensions=(".zarr",),
            label="Zarr image",
            block_type="SaveImage",
            handler="_write_zarr",
            is_default=True,
            roundtrip_group="scistudio-blocks-imaging.image.zarr",
            # Issue #1371: ``_write_zarr`` writes array data and the
            # ``axes`` group attribute only; no OME or typed Meta field
            # is persisted. ``pixel_only`` advertises that honestly.
            metadata_fidelity=MetadataFidelity(
                level="pixel_only",
                notes=(
                    "Writes array payload + axes group attribute; vanilla"
                    " zarr carries no OME or typed Image.Meta fields (OME-"
                    "Zarr v0.4 first-class support is deferred)."
                ),
            ),
        ),
        FormatCapability(
            id="scistudio-blocks-imaging.image.png.save",
            direction="save",
            data_type=Image,
            format_id="png",
            extensions=(".png",),
            label="PNG image",
            block_type="SaveImage",
            handler="_save_png",
            is_default=True,
            roundtrip_group="scistudio-blocks-imaging.image.png",
            # Issue #1371: PNG writer persists only EXIF DPI via Pillow,
            # i.e. ``ome.images[0].pixels.physical_size_x`` /
            # ``physical_size_y``. Declaring the precise field paths
            # prevents the lossy-save warning chip from claiming broad
            # OME write support.
            metadata_fidelity=MetadataFidelity(
                level="format_specific",
                format_metadata_writes=(
                    "ome.pixels.physical_size_x",
                    "ome.pixels.physical_size_y",
                ),
                typed_meta_writes=("pixel_size", "channels"),
                notes=("Writes PNG via Pillow; only EXIF DPI (OME physical_size_x/y) is persisted."),
            ),
        ),
        FormatCapability(
            id="scistudio-blocks-imaging.image.jpeg.save",
            direction="save",
            data_type=Image,
            format_id="jpeg",
            extensions=(".jpg", ".jpeg"),
            label="JPEG image",
            block_type="SaveImage",
            handler="_save_jpeg",
            is_default=True,
            roundtrip_group="scistudio-blocks-imaging.image.jpeg",
            # Issue #1371: JPEG writer persists only EXIF DPI. See PNG
            # note above for the field-path rationale.
            metadata_fidelity=MetadataFidelity(
                level="format_specific",
                format_metadata_writes=(
                    "ome.pixels.physical_size_x",
                    "ome.pixels.physical_size_y",
                ),
                typed_meta_writes=("pixel_size", "channels"),
                notes=("Writes JPEG via Pillow; only EXIF DPI (OME physical_size_x/y) is persisted. Alpha is dropped."),
            ),
        ),
    )

    # ADR-028 §D8 / issue #1075: mirror of
    # :attr:`LoadImage.supported_extensions` for round-trip discoverability.
    # ``_detect_format`` (inherited from IOBlock) consults this mapping;
    # ``BlockRegistry.find_saver`` (#1077) queries it for extension-based
    # dispatch. Per ADR-043 the per-class ``format_capabilities``
    # declaration is authoritative; this mapping stays in sync.
    supported_extensions: ClassVar[dict[str, str]] = {
        ".tif": "tiff",
        ".tiff": "tiff",
        ".zarr": "zarr",
        ".png": "png",
        ".jpg": "jpeg",
        ".jpeg": "jpeg",
    }

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="images", accepted_types=[Image], is_collection=True),
    ]
    _write_tiff = staticmethod(_write_tiff)
    _write_zarr = staticmethod(_write_zarr)
    _save_png = staticmethod(_save_png)
    _save_jpeg = staticmethod(_save_jpeg)

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            # Issue #1369: SaveImage writes single-image outputs to a
            # concrete file path (``out.tif``, ``out.zarr``, ``out.png``,
            # ``out.jpg``), so the bottom panel must open the **file**
            # picker, not the directory picker. The base ``IOBlock``
            # declares ``path`` as ``ui_widget="file_browser"``, but the
            # ADR-030 registry post-processor flips that to
            # ``directory_browser`` for any direction=="output" subclass
            # that does NOT declare ``path`` in its own ``config_schema``
            # (see ``scistudio.blocks.registry._subclass_declares_field``).
            # Multi-image batch mode treats ``path`` as a directory and
            # auto-numbers entries, but SaveImage's primary single-image
            # path needs a file. Declaring ``path`` here pins
            # ``ui_widget="file_browser"`` and short-circuits the
            # post-processor override. Workflow YAMLs that pass a
            # directory for batch mode still work — only the UI picker
            # changes; the runtime path resolution in ``save()`` is
            # unchanged.
            "path": {
                "type": "string",
                "ui_priority": 0,
                "ui_widget": "file_browser",
                "title": "Output path",
            },
            # Format selection: surfaced as the ADR-043 ``capability_id``
            # dropdown (FormatCapabilityConfig in BottomPanel) — the
            # backend resolves ``capability_id -> format_id`` via
            # :func:`_resolve_format`. The legacy ``format`` enum field
            # was removed here so the UI does not display two parallel
            # format selectors; existing workflow YAMLs that set
            # ``config['format']`` continue to load because
            # :func:`_resolve_format` still honours the ``explicit`` arg
            # (highest precedence) for backward compatibility.
        },
        "required": ["path"],
    }

    def load(
        self, config: BlockConfig, output_dir: str = ""
    ) -> DataObject | Collection:  # pragma: no cover - output block
        """Direction is ``output``; ``load`` is unreachable via dispatch."""
        raise NotImplementedError("SaveImage is an output block; use save()")

    def _write_single(self, image: Image, path: Path, fmt: str) -> None:
        """Write a single :class:`Image` to *path* in the given format."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "tiff":
            _write_tiff(image, path)
        elif fmt == "zarr":
            _write_zarr(image, path)
        elif fmt == "png":
            _save_png(image, path)
        elif fmt == "jpeg":
            _save_jpeg(image, path)
        else:
            # Defensive: every format id in :attr:`supported_extensions`
            # is expected to have a dispatch arm above.
            raise ValueError(f"SaveImage: format id {fmt!r} has no dispatch arm")

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
        capability_id = config.get("capability_id")
        if capability_id is not None and not isinstance(capability_id, str):
            raise ValueError(
                f"SaveImage: config['capability_id'] must be a string or omitted, got {type(capability_id).__name__}"
            )

        # Handle Collection: save each item with auto-numbered filename
        if isinstance(obj, Collection):
            if len(obj) == 0:
                raise ValueError("SaveImage: empty Collection")
            if len(obj) == 1:
                # Single-item collection: use path as-is
                image = _unwrap_image(obj)
                fmt = _resolve_format(path, fmt_cfg, block=self, capability_id=capability_id)
                self._write_single(image, path, fmt)
                return

            # Multi-item collection: path resolution.
            # Issue #1369: the config UI now exposes ``path`` via the
            # file picker (``ui_widget="file_browser"`` declared above),
            # so a user typing ``out.tif`` for a node that turns out to
            # receive a multi-item Collection at runtime should NOT
            # silently lose their filename. Two cases:
            #   * ``path`` has a suffix (e.g. ``out.tif``) → treat
            #     ``path.parent`` as ``out_dir`` and ``path.stem`` as
            #     the per-item filename prefix. Batch writes go to
            #     ``out_dir/<stem>_0000.<ext>``,
            #     ``out_dir/<stem>_0001.<ext>``, etc.
            #   * ``path`` has no suffix (e.g. ``batch_out``) → legacy
            #     behaviour: treat ``path`` as ``out_dir`` and use the
            #     default ``image`` prefix. This preserves backward
            #     compatibility for workflow YAMLs that pass a bare
            #     directory.
            # Codex review on PR #1395 flagged the silent filename drop;
            # this resolution honours both the file-picker UX and the
            # legacy directory-path workflows.
            if path.suffix:
                out_dir = path.parent
                stem = path.stem
            else:
                out_dir = path
                stem = "image"
            out_dir.mkdir(parents=True, exist_ok=True)
            # Resolve format first so the batch extension can mirror it
            # (extension dispatch needs a real path, so we hand a dummy
            # with the chosen suffix once we know the format id).
            if fmt_cfg is not None or capability_id is not None:
                fmt = _resolve_format(path, fmt_cfg, block=self, capability_id=capability_id)
                ext = f".{fmt}"
            else:
                ext = ".tif"
                fmt = _resolve_format(Path(f"dummy{ext}"), None, block=self)
            for i, item in enumerate(obj):
                if not isinstance(item, Image):
                    raise ValueError(f"SaveImage: Collection item {i} is not an Image")
                item_path = out_dir / f"{stem}_{i:04d}{ext}"
                self._write_single(item, item_path, fmt)
            return

        # Single image (not in Collection)
        image = _unwrap_image(obj)
        fmt = _resolve_format(path, fmt_cfg, block=self, capability_id=capability_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_single(image, path, fmt)
