"""Label/Mask cleanup bundle (T-IMG-022)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.array import Array
from scistudio.utils.axis_iter import iterate_over_axes
from scistudio_blocks_imaging.types import Label, Mask


class RemoveSmallObjects(ProcessBlock):
    """Remove connected components smaller than ``min_size`` pixels."""

    type_name: ClassVar[str] = "imaging.remove_small_objects"
    name: ClassVar[str] = "Remove Small Objects"
    description: ClassVar[str] = "Drop labels/mask blobs below min_size pixels."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "cleanup"
    algorithm: ClassVar[str] = "remove_small_objects"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="label", accepted_types=[Label, Mask], description="Label or Mask."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="label", accepted_types=[Label, Mask], description="Filtered Label or Mask."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "min_size": {"type": "integer", "default": 64, "minimum": 1},
        },
    }

    def process_item(self, item: Label | Mask, config: BlockConfig, state: Any = None) -> Label | Mask:
        from skimage.morphology import remove_small_objects

        min_size = int(config.get("min_size", 64))
        if min_size < 1:
            raise ValueError(f"RemoveSmallObjects: min_size must be >= 1, got {min_size}")

        if isinstance(item, Mask):
            mask_result = cast(
                Array,
                iterate_over_axes(
                    item,
                    frozenset({"y", "x"}),
                    lambda slice_2d, _coord: np.asarray(
                        remove_small_objects(np.asarray(slice_2d, dtype=bool), min_size=min_size),
                        dtype=bool,
                    ),
                ),
            )
            return _mask_from_array(item, np.asarray(mask_result.to_memory(), dtype=bool))

        raster = _label_raster(item, "RemoveSmallObjects")
        result = iterate_over_axes(
            raster,
            frozenset({"y", "x"}),
            lambda slice_2d, _coord: np.asarray(
                remove_small_objects(np.asarray(slice_2d, dtype=np.int32), min_size=min_size),
                dtype=np.int32,
            ),
        )
        return _label_from_array(item, np.asarray(result.to_memory(), dtype=np.int32))


class RemoveBorderObjects(ProcessBlock):
    """Remove labels that touch the image border."""

    type_name: ClassVar[str] = "imaging.remove_border_objects"
    name: ClassVar[str] = "Remove Border Objects"
    description: ClassVar[str] = "Drop labels that touch the image border (clear_border)."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "cleanup"
    algorithm: ClassVar[str] = "clear_border"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="label", accepted_types=[Label], description="Input Label image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="label", accepted_types=[Label], description="Border-cleared Label."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    def process_item(self, item: Label, config: BlockConfig, state: Any = None) -> Label:
        from skimage.segmentation import clear_border

        raster = _label_raster(item, "RemoveBorderObjects")
        result = iterate_over_axes(
            raster,
            frozenset({"y", "x"}),
            lambda slice_2d, _coord: np.asarray(clear_border(np.asarray(slice_2d, dtype=np.int32)), dtype=np.int32),
        )
        return _label_from_array(item, np.asarray(result.to_memory(), dtype=np.int32))


class FillHoles(ProcessBlock):
    """Fill interior holes in a binary :class:`Mask`."""

    type_name: ClassVar[str] = "imaging.fill_holes"
    name: ClassVar[str] = "Fill Holes"
    description: ClassVar[str] = "Fill interior holes of a binary Mask (binary_fill_holes)."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "cleanup"
    algorithm: ClassVar[str] = "binary_fill_holes"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="mask", accepted_types=[Mask], description="Input Mask."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="mask", accepted_types=[Mask], description="Hole-filled Mask."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    def process_item(self, item: Mask, config: BlockConfig, state: Any = None) -> Mask:
        from scipy.ndimage import binary_fill_holes

        result = cast(
            Mask,
            iterate_over_axes(
                item,
                frozenset({"y", "x"}),
                lambda slice_2d, _coord: np.asarray(binary_fill_holes(np.asarray(slice_2d, dtype=bool)), dtype=bool),
            ),
        )
        return _mask_from_array(item, np.asarray(result.to_memory(), dtype=bool))


class ExpandLabels(ProcessBlock):
    """Dilate labels by ``distance_px`` pixels (skimage expand_labels)."""

    type_name: ClassVar[str] = "imaging.expand_labels"
    name: ClassVar[str] = "Expand Labels"
    description: ClassVar[str] = "Dilate labels outwards by distance_px pixels."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "cleanup"
    algorithm: ClassVar[str] = "expand_labels"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="label", accepted_types=[Label], description="Input Label image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="label", accepted_types=[Label], description="Expanded Label image."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "distance_px": {"type": "integer", "default": 5, "minimum": 1},
        },
    }

    def process_item(self, item: Label, config: BlockConfig, state: Any = None) -> Label:
        from skimage.segmentation import expand_labels

        distance_px = int(config.get("distance_px", 5))
        if distance_px < 1:
            raise ValueError(f"ExpandLabels: distance_px must be >= 1, got {distance_px}")

        raster = _label_raster(item, "ExpandLabels")
        result = iterate_over_axes(
            raster,
            frozenset({"y", "x"}),
            lambda slice_2d, _coord: np.asarray(
                expand_labels(np.asarray(slice_2d, dtype=np.int32), distance=distance_px),
                dtype=np.int32,
            ),
        )
        return _label_from_array(item, np.asarray(result.to_memory(), dtype=np.int32))


class ShrinkLabels(ProcessBlock):
    """Erode each label inwards by ``distance_px`` pixels."""

    type_name: ClassVar[str] = "imaging.shrink_labels"
    name: ClassVar[str] = "Shrink Labels"
    description: ClassVar[str] = "Erode labels inwards by distance_px pixels."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "cleanup"
    algorithm: ClassVar[str] = "shrink_labels"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="label", accepted_types=[Label], description="Input Label image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="label", accepted_types=[Label], description="Shrunk Label image."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "distance_px": {"type": "integer", "default": 1, "minimum": 1},
        },
    }

    def process_item(self, item: Label, config: BlockConfig, state: Any = None) -> Label:
        distance_px = int(config.get("distance_px", 1))
        if distance_px < 1:
            raise ValueError(f"ShrinkLabels: distance_px must be >= 1, got {distance_px}")

        raster = _label_raster(item, "ShrinkLabels")
        result = iterate_over_axes(
            raster,
            frozenset({"y", "x"}),
            _build_shrink_fn(distance_px),
        )
        return _label_from_array(item, np.asarray(result.to_memory(), dtype=np.int32))


def _build_shrink_fn(distance_px: int) -> Callable[[np.ndarray, dict[str, int]], np.ndarray]:
    from skimage.morphology import disk, erosion

    footprint = np.asarray(disk(distance_px), dtype=bool)

    def _shrink(slice_2d: np.ndarray, _coord: dict[str, int]) -> np.ndarray:
        labels = np.asarray(slice_2d, dtype=np.int32)
        shrunk = np.zeros(labels.shape, dtype=np.int32)
        for label_id in sorted(int(value) for value in np.unique(labels) if value > 0):
            eroded = erosion(labels == label_id, footprint=footprint)
            shrunk[np.asarray(eroded, dtype=bool)] = label_id
        return shrunk

    return _shrink


def _label_raster(item: Label, block_name: str) -> Array:
    raster = item.slots.get("raster")
    if raster is None or not isinstance(raster, Array):
        raise ValueError(f"{block_name}: label input requires a populated 'raster' slot")
    return cast(Array, raster)


def _label_from_array(item: Label, data: np.ndarray) -> Label:
    raster_axes = list(_label_raster(item, "cleanup").axes)
    raster = Array(axes=raster_axes, shape=data.shape, dtype=data.dtype)
    raster._data = data  # type: ignore[attr-defined]
    meta_kwargs = item.meta.model_dump() if item.meta is not None else {}
    meta_kwargs["n_objects"] = _count_objects(data)
    return Label(
        slots={"raster": raster},
        framework=item.framework.derive(),
        meta=Label.Meta(**meta_kwargs),
        user=dict(item.user),
    )


def _mask_from_array(item: Mask, data: np.ndarray) -> Mask:
    mask = Mask(
        axes=list(item.axes),
        shape=data.shape,
        dtype=bool,
        chunk_shape=item.chunk_shape,
        framework=item.framework.derive(),
        meta=item.meta,
        user=dict(item.user),
        storage_ref=None,
    )
    mask._data = np.asarray(data, dtype=bool)  # type: ignore[attr-defined]
    return mask


def _count_objects(data: np.ndarray) -> int:
    positive = np.asarray(data) > 0
    if not positive.any():
        return 0
    return len({int(value) for value in np.unique(np.asarray(data)[positive])})


__all__ = [
    "ExpandLabels",
    "FillHoles",
    "RemoveBorderObjects",
    "RemoveSmallObjects",
    "ShrinkLabels",
]
