"""Bio-Formats handlers for microscopy vendor formats (CZI/ND2/LIF/OIR/OIB).

ADR-043 / spec adr-043-package-migration FR-004 / FR-008:

* Load-only handlers for ``.czi`` / ``.nd2`` / ``.lif`` / ``.oir`` /
  ``.oib`` via ``cellprofiler/python-bioformats`` (load-only by library
  design; ``SaveImage`` MUST NOT declare bioformats capabilities — FR-005).

* Lazy imports of ``bioformats`` / ``javabridge`` / ``ome_types``. When
  the optional ``imaging[bioformats]`` extras are not installed (and the
  underlying JVM is not present), the handlers raise a clear
  :class:`ImportError` naming the install command. The registry hides
  Bio-Formats capabilities from ``list_format_capabilities`` results
  when the handler module cannot be imported (handled by the registry
  layer; this module just surfaces the failure mode).

* Pixel data is materialised eagerly into a numpy array (Bio-Formats
  returns one plane at a time; we stitch them in-memory). Per ADR-031
  D4 the resulting :class:`Image` is returned without a
  ``storage_ref``; the IOBlock's ``run()`` auto-flush layer persists it
  to the workflow's output directory.

* OME metadata is read via ``bioformats.get_omexml_metadata`` and parsed
  through :func:`ome_types.from_xml` into a typed :class:`OME` object,
  which becomes :attr:`Image.Meta.ome`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from scieasy.core.meta.framework import FrameworkMeta
from scieasy_blocks_imaging.types import Image

_MISSING_EXTRAS_HINT: str = (
    "Bio-Formats handlers require the [bioformats] extra and a Java Runtime "
    "Environment (JRE 8+). Install via:\n"
    "    pip install scieasy-blocks-imaging[bioformats]\n"
    "and ensure `java -version` resolves on PATH."
)


def _import_bioformats() -> Any:
    """Lazy-import the ``bioformats`` module.

    Raises a clear :class:`ImportError` when the optional extras are not
    installed (or when the JVM cannot be located by ``javabridge``).
    """
    try:
        import bioformats  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised in tests via mock
        raise ImportError(_MISSING_EXTRAS_HINT) from exc
    return bioformats


def _import_javabridge() -> Any:
    """Lazy-import the ``javabridge`` module."""
    try:
        import javabridge  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised in tests via mock
        raise ImportError(_MISSING_EXTRAS_HINT) from exc
    return javabridge


def _ensure_jvm_started(javabridge: Any, bioformats: Any) -> None:
    """Start the JVM if it isn't already running.

    Bio-Formats requires a live JVM. ``javabridge.start_vm`` is
    idempotent for our purposes — we guard with the
    ``_JVM_STARTED`` module-level flag because ``javabridge`` raises if
    ``start_vm`` is called twice in some configurations.
    """
    if _BIOFORMATS_STATE["jvm_started"]:
        return
    javabridge.start_vm(class_path=bioformats.JARS, run_headless=True)
    _BIOFORMATS_STATE["jvm_started"] = True


_BIOFORMATS_STATE: dict[str, bool] = {"jvm_started": False}


def _parse_ome_xml(xml_str: str) -> Any:
    """Parse an OME-XML string into an :class:`ome_types.model.OME` object.

    Wraps :func:`ome_types.from_xml`; isolated so tests can stub.
    """
    from ome_types import from_xml

    return from_xml(xml_str)


def _axes_from_ome(ome: Any) -> list[str]:
    """Return SciEasy axis labels from an OME ``Pixels`` block.

    Bio-Formats canonically reports ``dimension_order`` like ``"XYCZT"``;
    we map to SciEasy's lowercase alphabet and reverse so the leading
    SciEasy axis matches the slowest-varying Bio-Formats axis.
    """
    if not ome.images:
        return ["y", "x"]
    pixels = ome.images[0].pixels
    order_str = str(pixels.dimension_order) if pixels.dimension_order else "XYCZT"
    # Strip the ``DimensionOrder.`` enum prefix if present (ome-types 0.5+
    # returns a string-valued enum).
    if "." in order_str:
        order_str = order_str.split(".")[-1]
    char_to_axis = {"X": "x", "Y": "y", "C": "c", "Z": "z", "T": "t"}
    size_attr = {"x": pixels.size_x, "y": pixels.size_y, "c": pixels.size_c, "z": pixels.size_z, "t": pixels.size_t}
    # SciEasy convention: slowest-varying first. OME dimension_order is
    # fastest-varying first, so reverse.
    reversed_order = list(reversed(order_str))
    axes: list[str] = []
    for ch in reversed_order:
        if ch in char_to_axis:
            axis = char_to_axis[ch]
            size = size_attr.get(axis, 1) or 1
            if size > 1 or axis in {"x", "y"}:
                axes.append(axis)
    # Always include x and y at the end if missing
    for required in ("y", "x"):
        if required not in axes:
            axes.append(required)
    return axes


def _read_pixels(reader: Any, ome: Any, axes: list[str]) -> np.ndarray:
    """Read the full pixel volume from a bioformats ``ImageReader``.

    Iterates Bio-Formats plane indices (Z, C, T) and stacks into a
    single numpy array shaped per ``axes``.
    """
    if not ome.images:
        raise ValueError("Bio-Formats reader returned no OME image element")
    pixels = ome.images[0].pixels
    size_x = int(pixels.size_x or 1)
    size_y = int(pixels.size_y or 1)
    size_z = int(pixels.size_z or 1)
    size_c = int(pixels.size_c or 1)
    size_t = int(pixels.size_t or 1)

    # Shape per SciEasy axes order
    axis_size = {"x": size_x, "y": size_y, "z": size_z, "c": size_c, "t": size_t}
    shape = tuple(axis_size[a] for a in axes)

    # Allocate output array
    sample = reader.read(z=0, c=0, t=0, rescale=False)
    out = np.empty(shape, dtype=sample.dtype)

    # Index into out by axis label
    axis_to_idx = {a: axes.index(a) for a in axes}
    base_index: list[slice | int] = [slice(None)] * len(axes)

    for t in range(size_t):
        for z in range(size_z):
            for c in range(size_c):
                plane = reader.read(z=z, c=c, t=t, rescale=False)
                idx: list[slice | int] = list(base_index)
                if "t" in axis_to_idx:
                    idx[axis_to_idx["t"]] = t
                if "z" in axis_to_idx:
                    idx[axis_to_idx["z"]] = z
                if "c" in axis_to_idx:
                    idx[axis_to_idx["c"]] = c
                out[tuple(idx)] = plane
    return out


def _load_bioformats(path: Path, fmt: str) -> Image:
    """Load a Bio-Formats vendor file into an :class:`Image`.

    Args:
        path: Filesystem path to the input file.
        fmt: Format identifier (``"czi"`` / ``"nd2"`` / ``"lif"`` /
            ``"oir"`` / ``"oib"``); used only in error messages — Bio-Formats
            auto-detects the actual format from the file contents.

    Returns:
        An :class:`Image` with pixel data materialised in-memory and
        :attr:`Image.Meta.ome` populated from the file's OME-XML.

    Raises:
        ImportError: If the ``imaging[bioformats]`` extras are missing
            or the JVM cannot be located.
        FileNotFoundError: If *path* does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Bio-Formats handler ({fmt}): no file at {path}")

    bioformats = _import_bioformats()
    javabridge = _import_javabridge()
    _ensure_jvm_started(javabridge, bioformats)

    xml_str = bioformats.get_omexml_metadata(path=str(path))
    ome = _parse_ome_xml(xml_str)
    axes = _axes_from_ome(ome)

    with bioformats.ImageReader(str(path)) as reader:
        array = _read_pixels(reader, ome, axes)

    img = Image(
        axes=axes,
        shape=tuple(array.shape),
        dtype=str(array.dtype),
        framework=FrameworkMeta(source=str(path)),
        meta=Image.Meta(source_file=str(path), ome=ome),
    )
    img._data = array  # type: ignore[attr-defined]
    return img


def _load_czi(path: Path, axes_override: list[str] | None = None, **_: Any) -> Image:
    """Load a Zeiss ``.czi`` file via Bio-Formats."""
    img = _load_bioformats(path, fmt="czi")
    return _apply_axes_override(img, axes_override)


def _load_nd2(path: Path, axes_override: list[str] | None = None, **_: Any) -> Image:
    """Load a Nikon ``.nd2`` file via Bio-Formats."""
    img = _load_bioformats(path, fmt="nd2")
    return _apply_axes_override(img, axes_override)


def _load_lif(path: Path, axes_override: list[str] | None = None, **_: Any) -> Image:
    """Load a Leica ``.lif`` file via Bio-Formats."""
    img = _load_bioformats(path, fmt="lif")
    return _apply_axes_override(img, axes_override)


def _load_oir(path: Path, axes_override: list[str] | None = None, **_: Any) -> Image:
    """Load an Olympus ``.oir`` file via Bio-Formats."""
    img = _load_bioformats(path, fmt="oir")
    return _apply_axes_override(img, axes_override)


def _load_oib(path: Path, axes_override: list[str] | None = None, **_: Any) -> Image:
    """Load an Olympus ``.oib`` file via Bio-Formats."""
    img = _load_bioformats(path, fmt="oib")
    return _apply_axes_override(img, axes_override)


def _apply_axes_override(image: Image, axes_override: list[str] | None) -> Image:
    """Optionally relabel an image's axes after a Bio-Formats load."""
    if axes_override is None:
        return image
    if len(axes_override) != len(image.axes):
        raise ValueError(f"Bio-Formats handler: axes override {axes_override!r} does not match ndim={len(image.axes)}")
    relabeled = Image(
        axes=axes_override,
        shape=image.shape,
        dtype=image.dtype,
        framework=image.framework,
        meta=image.meta,
    )
    if hasattr(image, "_data"):
        relabeled._data = image._data  # type: ignore[attr-defined]
    return relabeled


__all__ = [
    "_MISSING_EXTRAS_HINT",
    "_apply_axes_override",
    "_import_bioformats",
    "_import_javabridge",
    "_load_bioformats",
    "_load_czi",
    "_load_lif",
    "_load_nd2",
    "_load_oib",
    "_load_oir",
]
