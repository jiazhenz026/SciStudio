"""Geometry bundle - Rotate / Flip / Crop / Pad / Resize (T-IMG-008)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.units import PhysicalQuantity
from scistudio.utils.axis_iter import iterate_over_axes
from scistudio_blocks_imaging.types import Image, Mask

_ROTATE_INTERPOLATION_ORDERS: dict[str, int] = {
    "nearest": 0,
    "bilinear": 1,
    "bicubic": 3,
}
_PAD_MODES = frozenset({"constant", "reflect", "edge"})
_SPATIAL_AXES = ("y", "x")


class Rotate(ProcessBlock):
    """Rotate by an arbitrary angle in degrees."""

    type_name: ClassVar[str] = "imaging.rotate"
    name: ClassVar[str] = "Rotate"
    description: ClassVar[str] = "Rotate image by an arbitrary angle (degrees)."
    subcategory: ClassVar[str] = "geometry"
    algorithm: ClassVar[str] = "rotate"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "angle": {"type": "number", "default": 90.0},
            "interpolation": {
                "type": "string",
                "enum": list(_ROTATE_INTERPOLATION_ORDERS),
                "default": "bilinear",
            },
        },
        "required": ["angle"],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        angle = float(config.get("angle", 90.0))
        interpolation = str(config.get("interpolation", "bilinear"))
        if interpolation not in _ROTATE_INTERPOLATION_ORDERS:
            raise ValueError(
                f"Rotate: interpolation must be one of {sorted(_ROTATE_INTERPOLATION_ORDERS)}, got {interpolation!r}"
            )

        quarter_turns = _quarter_turn_count(angle)
        if quarter_turns is not None:
            return cast(
                Image,
                iterate_over_axes(
                    item,
                    frozenset(_SPATIAL_AXES),
                    lambda slice_2d, _coord: np.rot90(slice_2d, k=quarter_turns),
                ),
            )

        from skimage.transform import rotate as skimage_rotate

        order = _ROTATE_INTERPOLATION_ORDERS[interpolation]
        rotated = cast(
            Image,
            iterate_over_axes(
                item,
                frozenset(_SPATIAL_AXES),
                lambda slice_2d, _coord: np.asarray(
                    skimage_rotate(
                        slice_2d,
                        angle=angle,
                        resize=False,
                        order=order,
                        preserve_range=True,
                    )
                ),
            ),
        )
        return _make_derived_image(item, _image_data(rotated))


class Flip(ProcessBlock):
    """Flip along a single axis."""

    type_name: ClassVar[str] = "imaging.flip"
    name: ClassVar[str] = "Flip"
    description: ClassVar[str] = "Flip an image along one axis."
    subcategory: ClassVar[str] = "geometry"
    algorithm: ClassVar[str] = "flip"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "axis": {
                "type": "string",
                "enum": ["t", "z", "c", "lambda", "y", "x"],
            },
        },
        "required": ["axis"],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        axis = str(config.get("axis"))
        if axis not in item.axes:
            raise ValueError(f"Flip: axis {axis!r} not in image axes {item.axes}")

        data = _image_data(item)
        flipped = np.flip(data, axis=item.axes.index(axis))
        return _make_derived_image(item, flipped)


class Crop(ProcessBlock):
    """Crop to an explicit bounding box or a mask-derived bounding box."""

    type_name: ClassVar[str] = "imaging.crop"
    name: ClassVar[str] = "Crop"
    description: ClassVar[str] = "Crop image to bounding box (or mask bbox)."
    subcategory: ClassVar[str] = "geometry"
    algorithm: ClassVar[str] = "crop"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
        InputPort(name="mask", accepted_types=[Mask], required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "bbox": {
                "type": "array",
                "description": "[y_start, y_end, x_start, x_end]",
            },
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        images = _image_items(inputs.get("image"), "image")
        masks = _mask_items(inputs.get("mask"))
        bbox_value = config.get("bbox")

        cropped_items: list[Image] = []
        for index, image in enumerate(images):
            bbox = (
                _coerce_bbox(bbox_value)
                if bbox_value is not None
                else _mask_bbox(_select_mask(masks, len(images), index))
            )
            cropped_items.append(self._crop_one(image, bbox))

        return {"image": Collection(items=cast(list[DataObject], cropped_items), item_type=Image)}

    def _crop_one(self, image: Image, bbox: tuple[int, int, int, int]) -> Image:
        if image.shape is None:
            raise ValueError("Crop: image.shape is required")
        _validate_spatial_axes(image)

        y_axis = image.axes.index("y")
        x_axis = image.axes.index("x")
        y_size = image.shape[y_axis]
        x_size = image.shape[x_axis]

        y_start, y_end, x_start, x_end = bbox
        if not (0 <= y_start < y_end <= y_size and 0 <= x_start < x_end <= x_size):
            raise ValueError(
                "Crop: bbox must satisfy "
                f"0 <= y_start < y_end <= {y_size} and 0 <= x_start < x_end <= {x_size}; "
                f"got {bbox}"
            )

        slicer: list[slice | int] = [slice(None)] * len(image.axes)
        slicer[y_axis] = slice(y_start, y_end)
        slicer[x_axis] = slice(x_start, x_end)
        cropped = np.asarray(_image_data(image)[tuple(slicer)])
        return _make_derived_image(image, cropped)


class Pad(ProcessBlock):
    """Pad an image in the spatial dimensions."""

    type_name: ClassVar[str] = "imaging.pad"
    name: ClassVar[str] = "Pad"
    description: ClassVar[str] = "Pad image edges (constant / reflect / edge)."
    subcategory: ClassVar[str] = "geometry"
    algorithm: ClassVar[str] = "pad"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "pad": {
                "type": "array",
                "description": "[top, bottom, left, right]",
            },
            "mode": {
                "type": "string",
                "enum": sorted(_PAD_MODES),
                "default": "constant",
            },
            "value": {"type": "number", "default": 0.0},
        },
        "required": ["pad"],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        pad = _coerce_pad(config.get("pad"))
        mode = str(config.get("mode", "constant"))
        value = float(config.get("value", 0.0))

        if mode not in _PAD_MODES:
            raise ValueError(f"Pad: mode must be one of {sorted(_PAD_MODES)}, got {mode!r}")

        _validate_spatial_axes(item)
        pad_width: list[tuple[int, int]] = [(0, 0)] * len(item.axes)
        pad_width[item.axes.index("y")] = (pad[0], pad[1])
        pad_width[item.axes.index("x")] = (pad[2], pad[3])

        data = _image_data(item)
        pad_width_tuple = tuple(pad_width)
        if mode == "constant":
            padded = np.pad(data, pad_width_tuple, mode="constant", constant_values=value)
        elif mode == "reflect":
            padded = np.pad(data, pad_width_tuple, mode="reflect")
        else:
            padded = np.pad(data, pad_width_tuple, mode="edge")
        return _make_derived_image(item, np.asarray(padded))


class Resize(ProcessBlock):
    """Resize an image and update ``pixel_size`` when present."""

    type_name: ClassVar[str] = "imaging.resize"
    name: ClassVar[str] = "Resize"
    description: ClassVar[str] = "Resize image to a target shape or scale factor."
    subcategory: ClassVar[str] = "geometry"
    algorithm: ClassVar[str] = "resize"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "target_shape": {"type": "array"},
            "factor": {"type": "number"},
            "interpolation": {
                "type": "string",
                "enum": list(_ROTATE_INTERPOLATION_ORDERS),
                "default": "bilinear",
            },
        },
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        _validate_spatial_axes(item)
        if item.shape is None:
            raise ValueError("Resize: image.shape is required")

        interpolation = str(config.get("interpolation", "bilinear"))
        if interpolation not in _ROTATE_INTERPOLATION_ORDERS:
            raise ValueError(
                f"Resize: interpolation must be one of {sorted(_ROTATE_INTERPOLATION_ORDERS)}, got {interpolation!r}"
            )

        target_shape = config.get("target_shape")
        factor = config.get("factor")
        if (target_shape is None) == (factor is None):
            raise ValueError("Resize: exactly one of target_shape or factor must be provided")

        new_yx_shape = _resize_target_shape(item, target_shape, factor)
        old_yx_shape = _spatial_shape(item)

        from skimage.transform import resize as skimage_resize

        order = _ROTATE_INTERPOLATION_ORDERS[interpolation]
        resized = cast(
            Image,
            iterate_over_axes(
                item,
                frozenset(_SPATIAL_AXES),
                lambda slice_2d, _coord: np.asarray(
                    skimage_resize(
                        slice_2d,
                        new_yx_shape,
                        order=order,
                        preserve_range=True,
                        anti_aliasing=order > 0,
                    )
                ),
            ),
        )
        new_meta = _resize_meta(cast(Image.Meta | None, item.meta), old_yx_shape, new_yx_shape)
        return _make_derived_image(item, _image_data(resized), meta=new_meta)


def _image_data(image: Image) -> np.ndarray:
    """Return image data as a numpy array without changing semantics."""
    if image.storage_ref is None and hasattr(image, "_data") and getattr(image, "_data", None) is not None:
        return np.asarray(image._data)  # type: ignore[attr-defined]
    return np.asarray(image.to_memory())


def _make_derived_image(
    source: Image,
    data: np.ndarray,
    *,
    axes: Sequence[str] | None = None,
    meta: Image.Meta | None = None,
) -> Image:
    result = Image(
        axes=list(source.axes if axes is None else axes),
        shape=tuple(data.shape),
        dtype=data.dtype,
        framework=source.framework.derive(),
        meta=source.meta if meta is None else meta,
        user=dict(source.user),
        storage_ref=None,
    )
    result._data = data  # type: ignore[attr-defined]
    return result


def _quarter_turn_count(angle: float) -> int | None:
    turns = angle / 90.0
    rounded = round(turns)
    if np.isclose(turns, rounded):
        return rounded % 4
    return None


def _validate_spatial_axes(image: Image) -> None:
    if "y" not in image.axes or "x" not in image.axes:
        raise ValueError(f"{type(image).__name__}: image must carry 'y' and 'x' axes, got {image.axes}")


def _image_items(value: Collection | Image | None, port_name: str) -> list[Image]:
    if value is None:
        raise ValueError(f"Crop: missing required input {port_name!r}")
    if isinstance(value, Image):
        return [value]
    if not isinstance(value, Collection):
        raise ValueError(f"Crop: {port_name!r} must be an Image or Collection[Image]")

    items: list[Image] = []
    for item in value:
        if not isinstance(item, Image):
            raise ValueError(f"Crop: {port_name!r} must contain Image items, got {type(item).__name__}")
        items.append(item)
    if not items:
        raise ValueError(f"Crop: {port_name!r} collection is empty")
    return items


def _mask_items(value: Collection | Mask | None) -> list[Mask]:
    if value is None:
        return []
    if isinstance(value, Mask):
        return [value]
    if not isinstance(value, Collection):
        raise ValueError("Crop: 'mask' must be a Mask or Collection[Mask]")

    items: list[Mask] = []
    for item in value:
        if not isinstance(item, Mask):
            raise ValueError(f"Crop: 'mask' must contain Mask items, got {type(item).__name__}")
        items.append(item)
    return items


def _select_mask(masks: Sequence[Mask], image_count: int, index: int) -> Mask:
    if not masks:
        raise ValueError("Crop: bbox is required when no mask input is provided")
    if len(masks) == 1:
        return masks[0]
    if len(masks) != image_count:
        raise ValueError("Crop: mask collection length must be 1 or match the image collection length")
    return masks[index]


def _coerce_bbox(value: object) -> tuple[int, int, int, int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 4:
        raise ValueError("Expected a four-element [y_start, y_end, x_start, x_end] sequence")

    coords: list[int] = []
    for coord in value:
        if isinstance(coord, bool) or not isinstance(coord, (int, np.integer)):
            raise ValueError("Bounding-box values must be integers")
        coords.append(int(coord))
    return tuple(coords[0:4])  # type: ignore[return-value]


def _coerce_pad(value: object) -> tuple[int, int, int, int]:
    pad = _coerce_bbox(value)
    if any(part < 0 for part in pad):
        raise ValueError("Pad values must be >= 0")
    return pad


def _mask_bbox(mask: Mask) -> tuple[int, int, int, int]:
    _validate_spatial_axes(mask)
    data = _image_data(mask).astype(bool)

    non_spatial_axes = tuple(i for i, axis in enumerate(mask.axes) if axis not in _SPATIAL_AXES)
    collapsed = np.any(data, axis=non_spatial_axes) if non_spatial_axes else data

    if collapsed.ndim != 2:
        raise ValueError(f"Crop: mask must collapse to 2D over (y, x), got shape {collapsed.shape}")

    rows = np.where(np.any(collapsed, axis=1))[0]
    cols = np.where(np.any(collapsed, axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        raise ValueError("Crop: mask contains no positive pixels")
    return (int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1)


def _spatial_shape(image: Image) -> tuple[int, int]:
    if image.shape is None:
        raise ValueError(f"{type(image).__name__}: image.shape is required")
    return (image.shape[image.axes.index("y")], image.shape[image.axes.index("x")])


def _resize_target_shape(
    image: Image,
    target_shape: object,
    factor: object,
) -> tuple[int, int]:
    old_y, old_x = _spatial_shape(image)
    if target_shape is not None:
        if not isinstance(target_shape, Sequence) or isinstance(target_shape, (str, bytes)):
            raise ValueError("Resize: target_shape must be a sequence")
        values = list(target_shape)
        if len(values) == 2:
            new_y, new_x = (_positive_int(values[0], "target_shape[0]"), _positive_int(values[1], "target_shape[1]"))
            return (new_y, new_x)
        if len(values) == len(image.axes):
            return (
                _positive_int(values[image.axes.index("y")], "target_shape[y]"),
                _positive_int(values[image.axes.index("x")], "target_shape[x]"),
            )
        raise ValueError("Resize: target_shape must have length 2 or match the image rank")

    scale = _positive_float(factor, "factor")
    new_y = max(1, round(old_y * scale))
    new_x = max(1, round(old_x * scale))
    return (new_y, new_x)


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"Resize: {name} must be an integer")
    out = int(value)
    if out <= 0:
        raise ValueError(f"Resize: {name} must be > 0")
    return out


def _positive_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.floating, np.integer)):
        raise ValueError(f"Resize: {name} must be numeric")
    out = float(value)
    if out <= 0:
        raise ValueError(f"Resize: {name} must be > 0")
    return out


def _resize_meta(meta: Image.Meta | None, old_shape: tuple[int, int], new_shape: tuple[int, int]) -> Image.Meta | None:
    if meta is None:
        return None
    updates: dict[str, object] = {}

    pixel_size = getattr(meta, "pixel_size", None)
    if pixel_size is not None:
        updates["pixel_size"] = _scale_pixel_size(pixel_size, old_shape, new_shape)

    # ADR-043 / spec FR-009 Mode B: resize is a shape-changing same-type
    # derivation, so the helper MUST rewrite the OME pixel-size and
    # spatial-dimension counts to match the new sampling. We deep-copy the
    # source OME object so the frozen source Meta is not mutated; pydantic
    # v2 ``model_copy(deep=True)`` is the idiomatic clone.
    ome = getattr(meta, "ome", None)
    if ome is not None:
        updates["ome"] = _resize_ome(ome, old_shape, new_shape)

    if not updates:
        return meta
    return meta.model_copy(update=updates)


def _resize_ome(ome: Any, old_shape: tuple[int, int], new_shape: tuple[int, int]) -> Any:
    """Return a deep-copied OME with pixel_size + size_x/size_y rewritten.

    - ``size_y`` / ``size_x`` are replaced with the new spatial extents.
    - ``physical_size_y`` / ``physical_size_x`` are scaled by
      ``old_extent / new_extent`` (smaller pixels when upsampling, larger
      when downsampling — physical extent of the image is preserved).
    """
    new_y, new_x = new_shape
    old_y, old_x = old_shape

    new_ome = ome.model_copy(deep=True)
    if not new_ome.images:
        return new_ome
    pixels = new_ome.images[0].pixels
    pixels.size_y = int(new_y)
    pixels.size_x = int(new_x)
    if pixels.physical_size_y is not None and new_y > 0:
        pixels.physical_size_y = float(pixels.physical_size_y) * (old_y / new_y)
    if pixels.physical_size_x is not None and new_x > 0:
        pixels.physical_size_x = float(pixels.physical_size_x) * (old_x / new_x)
    return new_ome


def _scale_pixel_size(pixel_size: object, old_shape: tuple[int, int], new_shape: tuple[int, int]) -> object:
    y_factor = old_shape[0] / new_shape[0]
    x_factor = old_shape[1] / new_shape[1]

    if isinstance(pixel_size, PhysicalQuantity):
        if np.isclose(y_factor, x_factor):
            return PhysicalQuantity(value=float(pixel_size.value) * y_factor, unit=pixel_size.unit)
        return pixel_size
    if isinstance(pixel_size, tuple):
        if len(pixel_size) != 2:
            return pixel_size
        return (cast(float, pixel_size[0]) * y_factor, cast(float, pixel_size[1]) * x_factor)
    if isinstance(pixel_size, list):
        if len(pixel_size) != 2:
            return pixel_size
        return [cast(float, pixel_size[0]) * y_factor, cast(float, pixel_size[1]) * x_factor]
    if isinstance(pixel_size, (int, float, np.integer, np.floating)):
        if np.isclose(y_factor, x_factor):
            return float(pixel_size) * y_factor
        return (float(pixel_size) * y_factor, float(pixel_size) * x_factor)
    return pixel_size


__all__ = ["Crop", "Flip", "Pad", "Resize", "Rotate"]
