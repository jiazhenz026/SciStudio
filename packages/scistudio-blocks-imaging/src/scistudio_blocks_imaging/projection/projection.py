"""Axis projection bundle (T-IMG-030).

Two related blocks:

- :class:`AxisProjection` — collapse one axis with max/mean/sum/min/std
- :class:`SelectSlice` — single replacement for the OptEasy
  ``SelectChannel`` / ``CropTimeRange`` family; pick a single index
  along an arbitrary axis.

See ``docs/specs/phase11-imaging-block-spec.md`` §9 T-IMG-030.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio_blocks_imaging.types import Image

_METHODS = frozenset({"max", "mean", "sum", "min", "std"})


class AxisProjection(ProcessBlock):
    """Collapse one axis of an :class:`Image` using a reducer."""

    type_name: ClassVar[str] = "imaging.axis_projection"
    name: ClassVar[str] = "Axis Projection"
    description: ClassVar[str] = (
        "Collapse one axis (max / mean / sum / min / std) and return a lower-dimensional Image."
    )
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "projection"
    algorithm: ClassVar[str] = "axis_projection"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], description="Input image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="projected", accepted_types=[Image], description="Projected image."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "axis": {"type": "string", "default": "z"},
            "method": {
                "type": "string",
                "enum": ["max", "mean", "sum", "min", "std"],
                "default": "max",
            },
        },
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        axis = str(config.get("axis", "z"))
        method = str(config.get("method", "max"))
        if axis not in item.axes:
            raise ValueError(f"AxisProjection: axis {axis!r} not in image axes {item.axes}")
        if method not in _METHODS:
            raise ValueError(f"AxisProjection: method must be one of {sorted(_METHODS)}, got {method!r}")

        axis_index = item.axes.index(axis)
        data = _image_data(item)
        projected = _reduce(data, method, axis_index)
        projected_axes = [name for name in item.axes if name != axis]
        projected_meta = _projected_meta(cast(Image.Meta | None, item.meta), axis)
        return _make_image(item, projected, projected_axes, meta=projected_meta)


class SelectSlice(ProcessBlock):
    """Pick a single index (or slice) along an arbitrary axis of an :class:`Image`."""

    type_name: ClassVar[str] = "imaging.select_slice"
    name: ClassVar[str] = "Select Slice"
    description: ClassVar[str] = (
        "Select a single index along an axis (replaces SelectChannel / CropTimeRange / SelectZ)."
    )
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "projection"
    algorithm: ClassVar[str] = "select_slice"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], description="Input image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="slice", accepted_types=[Image], description="Selected slice."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "axis": {"type": "string", "default": "c"},
            "index": {"type": "integer", "default": 0, "minimum": 0},
        },
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        axis = str(config.get("axis", "c"))
        if axis not in item.axes:
            raise ValueError(f"SelectSlice: axis {axis!r} not in image axes {item.axes}")
        if axis in {"y", "x"}:
            raise ValueError("SelectSlice: selecting over spatial axes would violate the Image axis contract")

        index = config.get("index", 0)
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError("SelectSlice: index must be an integer")

        data = _image_data(item)
        axis_index = item.axes.index(axis)
        axis_length = data.shape[axis_index]
        if index < 0 or index >= axis_length:
            raise IndexError(f"SelectSlice: index {index} out of bounds for axis {axis!r} with length {axis_length}")

        selected = item.sel(**{axis: index})
        projected_meta = _projected_meta(cast(Image.Meta | None, item.meta), axis)
        return _make_image(item, np.asarray(selected.to_memory()), list(selected.axes), meta=projected_meta)


def _image_data(image: Image) -> np.ndarray:
    if image.storage_ref is None and hasattr(image, "_data") and getattr(image, "_data", None) is not None:
        return np.asarray(image._data)  # type: ignore[attr-defined]
    return np.asarray(image.to_memory())


def _make_image(source: Image, data: np.ndarray, axes: list[str], *, meta: Image.Meta | None) -> Image:
    result = Image(
        axes=axes,
        shape=tuple(data.shape),
        dtype=data.dtype,
        framework=source.framework.derive(),
        meta=meta,
        user=dict(source.user),
        storage_ref=None,
    )
    result._data = data  # type: ignore[attr-defined]
    return result


def _projected_meta(meta: Image.Meta | None, axis: str) -> Image.Meta | None:
    if meta is None:
        return None

    updates: dict[str, object] = {}
    if axis == "c":
        updates["channels"] = None
    if axis == "lambda":
        updates["wavelengths_nm"] = None

    # ADR-043 / spec FR-009 Mode B: projection drops one axis. We deep-copy
    # the OME object (so the frozen source Meta is not mutated) and rewrite
    # the dropped-axis size to 1 in OME's ``size_<axis>`` and remove that
    # axis from ``dimension_order`` when it is present. Per-axis pixel
    # sizes for remaining axes are left unchanged (the in-plane sampling
    # is unaffected by a projection along an orthogonal axis).
    ome = getattr(meta, "ome", None)
    if ome is not None:
        updates["ome"] = _project_ome(ome, axis)

    return meta.model_copy(update=updates) if updates else meta


def _project_ome(ome: Any, axis: str) -> Any:
    """Return a deep-copied OME with ``size_<axis>`` collapsed to 1.

    The OME dimension_order is left as-is when the projected axis is not
    present in it (some loaders omit singleton-dim characters); when the
    axis character IS in dimension_order we keep the order string but
    collapse the size to 1 so consumers can still tell a projection
    happened by reading ``size_<axis>``.
    """
    new_ome = ome.model_copy(deep=True)
    if not new_ome.images:
        return new_ome
    pixels = new_ome.images[0].pixels

    # Map SciStudio axis name -> OME pixel-size attribute.
    axis_to_size_attr: dict[str, str] = {
        "t": "size_t",
        "z": "size_z",
        "c": "size_c",
        "lambda": "size_c",  # spectral axis maps to channel count in OME
    }
    size_attr = axis_to_size_attr.get(axis)
    if size_attr is not None and hasattr(pixels, size_attr):
        setattr(pixels, size_attr, 1)
    return new_ome


def _reduce(data: np.ndarray, method: str, axis_index: int) -> np.ndarray:
    if method == "max":
        return np.asarray(np.max(data, axis=axis_index))
    if method == "mean":
        return np.asarray(np.mean(data, axis=axis_index))
    if method == "sum":
        return np.asarray(np.sum(data, axis=axis_index))
    if method == "min":
        return np.asarray(np.min(data, axis=axis_index))
    return np.asarray(np.std(data, axis=axis_index))


__all__ = ["AxisProjection", "SelectSlice"]
