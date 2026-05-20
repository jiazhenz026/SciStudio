"""AxisSplit / AxisMerge - split or merge images along an axis (T-IMG-010)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, cast

import numpy as np

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy_blocks_imaging.types import Image

_SUPPORTED_AXES = ("t", "z", "c", "lambda")


class AxisSplit(ProcessBlock):
    """Split an Image along one axis into a Collection of (N-1)D images."""

    type_name: ClassVar[str] = "imaging.axis_split"
    name: ClassVar[str] = "Axis Split"
    description: ClassVar[str] = "Split an image along an axis into a Collection."
    subcategory: ClassVar[str] = "preprocess"
    algorithm: ClassVar[str] = "axis_split"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="images", accepted_types=[Image], is_collection=True),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "axis": {
                "type": "string",
                "enum": list(_SUPPORTED_AXES),
            },
        },
        "required": ["axis"],
    }

    def run(
        self,
        inputs: dict[str, Collection],
        config: BlockConfig,
    ) -> dict[str, Collection]:
        image = _require_single_image(inputs.get("image"))
        axis = _require_axis(config)
        if axis not in image.axes:
            raise ValueError(f"AxisSplit: axis {axis!r} not in image axes {image.axes}")
        if image.shape is None:
            raise ValueError("AxisSplit: image.shape is required")

        axis_index = image.axes.index(axis)
        out_axes = [name for name in image.axes if name != axis]
        data = _image_data(image)

        split_items: list[Image] = []
        for index in range(image.shape[axis_index]):
            sliced = np.take(data, index, axis=axis_index)
            split_items.append(
                _make_image(
                    image,
                    np.asarray(sliced),
                    axes=out_axes,
                    meta=_split_meta(cast(Image.Meta | None, image.meta), axis, index),
                )
            )

        return {"images": Collection(items=cast(list[DataObject], split_items), item_type=Image)}


class AxisMerge(ProcessBlock):
    """Merge a Collection of (N-1)D Image objects along a new axis."""

    type_name: ClassVar[str] = "imaging.axis_merge"
    name: ClassVar[str] = "Axis Merge"
    description: ClassVar[str] = "Merge a Collection of images into a single N-D image."
    subcategory: ClassVar[str] = "preprocess"
    algorithm: ClassVar[str] = "axis_merge"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="images", accepted_types=[Image], is_collection=True, required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "axis": {
                "type": "string",
                "enum": list(_SUPPORTED_AXES),
            },
            "ordering": {
                "type": "array",
                "items": {"type": "integer"},
            },
        },
        "required": ["axis"],
    }

    def run(
        self,
        inputs: dict[str, Collection],
        config: BlockConfig,
    ) -> dict[str, Collection]:
        axis = _require_axis(config)
        images = _coerce_image_collection(inputs.get("images"), "images")
        ordering = _resolve_ordering(config.get("ordering"), len(images))
        ordered_images = [images[index] for index in ordering]
        merged = _merge_images(ordered_images, axis)
        return {"image": Collection(items=cast(list[DataObject], [merged]), item_type=Image)}


def _require_axis(config: BlockConfig) -> str:
    axis = str(config.get("axis"))
    if axis not in _SUPPORTED_AXES:
        raise ValueError(f"Axis operation: axis must be one of {list(_SUPPORTED_AXES)}, got {axis!r}")
    return axis


def _coerce_image_collection(value: Collection | Image | None, port_name: str) -> list[Image]:
    if value is None:
        raise ValueError(f"Missing required input {port_name!r}")
    if isinstance(value, Image):
        return [value]
    if not isinstance(value, Collection):
        raise ValueError(f"{port_name!r} must be a Collection[Image] or Image")

    images: list[Image] = []
    for item in value:
        if not isinstance(item, Image):
            raise ValueError(f"{port_name!r} must contain Image items, got {type(item).__name__}")
        images.append(item)
    if not images:
        raise ValueError(f"{port_name!r} collection is empty")
    return images


def _require_single_image(value: Collection | Image | None) -> Image:
    images = _coerce_image_collection(value, "image")
    if len(images) != 1:
        raise ValueError(f"AxisSplit: expected a single Image, got Collection length {len(images)}")
    return images[0]


def _resolve_ordering(raw_ordering: Any, length: int) -> list[int]:
    if raw_ordering is None:
        return list(range(length))
    if not isinstance(raw_ordering, list):
        raise ValueError("AxisMerge: ordering must be a list of integers")
    if len(raw_ordering) != length:
        raise ValueError("AxisMerge: ordering length must match collection length")

    ordering: list[int] = []
    for index in raw_ordering:
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError("AxisMerge: ordering must contain only integers")
        ordering.append(index)
    if sorted(ordering) != list(range(length)):
        raise ValueError("AxisMerge: ordering must be a permutation of collection indices")
    return ordering


def _merge_images(images: list[Image], axis: str) -> Image:
    first = images[0]
    if axis in first.axes:
        raise ValueError(f"AxisMerge: axis {axis!r} already present in input axes {first.axes}")
    if first.shape is None:
        raise ValueError("AxisMerge: image.shape is required")

    for image in images[1:]:
        if image.axes != first.axes:
            raise ValueError("AxisMerge: all images must have identical axis ordering")
        if image.shape != first.shape:
            raise ValueError("AxisMerge: all images must have identical shapes")

    merged_axes = _merged_axes(first.axes, axis)
    insert_at = merged_axes.index(axis)
    data = np.stack([_image_data(image) for image in images], axis=insert_at)
    return _make_image(first, data, axes=merged_axes, meta=_merge_meta(images, axis))


def _merged_axes(existing_axes: list[str], axis: str) -> list[str]:
    axes = [*list(existing_axes), axis]
    return [name for name in Image.canonical_order if name in axes]


def _image_data(image: Image) -> np.ndarray:
    if image.storage_ref is None and hasattr(image, "_data") and getattr(image, "_data", None) is not None:
        return np.asarray(image._data)  # type: ignore[attr-defined]
    return np.asarray(image.to_memory())


def _make_image(source: Image, data: np.ndarray, *, axes: list[str], meta: Image.Meta | None) -> Image:
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


def _split_meta(meta: Image.Meta | None, axis: str, index: int) -> Image.Meta | None:
    if meta is None:
        return None

    updates: dict[str, object] = {"source_file": _split_source_file(meta.source_file, axis, index)}
    if axis == "c" and meta.channels is not None and index < len(meta.channels):
        updates["channels"] = [meta.channels[index]]
    if axis == "lambda" and meta.wavelengths_nm is not None and index < len(meta.wavelengths_nm):
        updates["wavelengths_nm"] = [meta.wavelengths_nm[index]]

    # ADR-043 / spec FR-009 Mode B: split is a shape-changing same-type
    # derivation. The per-split slice still represents the same physical
    # sampling (a single channel/time/z plane), so OME pixel-size and
    # other spatial-coordinate-system fields are preserved verbatim. We
    # only collapse the split axis's size to 1 in the OME pixel record so
    # downstream consumers can tell a slice happened. Deep-copied so the
    # frozen source Meta is not mutated.
    if meta.ome is not None:
        updates["ome"] = _split_ome(meta.ome, axis)

    return cast(Image.Meta, meta.model_copy(update=updates))


def _split_ome(ome: Any, axis: str) -> Any:
    """Return a deep-copied OME with ``size_<axis>`` collapsed to 1.

    For split-along-channel / split-along-time / split-along-z, each
    output slice represents one position along the split axis, so OME's
    size_<axis> is set to 1 and the rest of the structure (in-plane
    pixel sizes, channels, instrument, etc.) is preserved.
    """
    new_ome = ome.model_copy(deep=True)
    if not new_ome.images:
        return new_ome
    pixels = new_ome.images[0].pixels
    axis_to_size_attr: dict[str, str] = {
        "t": "size_t",
        "z": "size_z",
        "c": "size_c",
        "lambda": "size_c",
    }
    size_attr = axis_to_size_attr.get(axis)
    if size_attr is not None and hasattr(pixels, size_attr):
        setattr(pixels, size_attr, 1)
    return new_ome


def _merge_meta(images: list[Image], axis: str) -> Image.Meta | None:
    first_meta = images[0].meta
    if not isinstance(first_meta, Image.Meta):
        return None

    updates: dict[str, object] = {}
    if axis == "c":
        channels = [image.meta.channels for image in images if isinstance(image.meta, Image.Meta)]
        if len(channels) == len(images) and all(values is not None and len(values) == 1 for values in channels):
            updates["channels"] = [values[0] for values in channels if values is not None]
    if axis == "lambda":
        wavelengths = [image.meta.wavelengths_nm for image in images if isinstance(image.meta, Image.Meta)]
        if len(wavelengths) == len(images) and all(values is not None and len(values) == 1 for values in wavelengths):
            updates["wavelengths_nm"] = [values[0] for values in wavelengths if values is not None]

    return first_meta.model_copy(update=updates) if updates else first_meta


def _split_source_file(source_file: str | None, axis: str, index: int) -> str:
    if source_file:
        path = Path(source_file)
        return str(path.with_name(f"{path.stem}__{axis}={index}{path.suffix}"))
    return f"axis_split__{axis}={index}"


__all__ = ["AxisMerge", "AxisSplit"]
