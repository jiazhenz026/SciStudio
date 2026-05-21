"""MorphologyOp - erode/dilate/open/close/tophat/bottomhat (T-IMG-012)."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.utils.axis_iter import iterate_over_axes
from scistudio_blocks_imaging.types import Image

_OPS = frozenset({"erode", "dilate", "open", "close", "tophat", "bottomhat"})
_SELEM_SHAPES = frozenset({"disk", "square", "cross"})


class MorphologyOp(ProcessBlock):
    """Morphological operations on 2D ``(y, x)`` slices."""

    type_name: ClassVar[str] = "imaging.morphology_op"
    name: ClassVar[str] = "Morphology Op"
    description: ClassVar[str] = "Morphological operations: erode/dilate/open/close/tophat/bottomhat."
    subcategory: ClassVar[str] = "filter"
    algorithm: ClassVar[str] = "morphology"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["erode", "dilate", "open", "close", "tophat", "bottomhat"],
                "default": "erode",
            },
            "selem_shape": {
                "type": "string",
                "enum": ["disk", "square", "cross"],
                "default": "disk",
            },
            "selem_size": {"type": "integer", "default": 3, "minimum": 1},
        },
        "required": ["op"],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        """Apply a grayscale morphological operation per 2D slice."""
        op = str(config.get("op", "erode"))
        selem_shape = str(config.get("selem_shape", "disk"))
        selem_size = int(config.get("selem_size", 3))

        if op not in _OPS:
            raise ValueError(f"MorphologyOp: unknown op {op!r}; expected one of {sorted(_OPS)}")
        if selem_shape not in _SELEM_SHAPES:
            raise ValueError(f"MorphologyOp: selem_shape must be one of {sorted(_SELEM_SHAPES)}, got {selem_shape!r}")
        if selem_size < 1:
            raise ValueError(f"MorphologyOp: selem_size must be >= 1, got {selem_size}")

        footprint = _build_footprint(selem_shape, selem_size)
        return cast(
            Image,
            iterate_over_axes(item, frozenset({"y", "x"}), _build_op_fn(op, footprint)),
        )


def _build_footprint(selem_shape: str, selem_size: int) -> np.ndarray:
    from skimage.morphology import disk

    width = selem_size * 2 + 1
    if selem_shape == "disk":
        return np.asarray(disk(selem_size), dtype=bool)
    if selem_shape == "square":
        return np.ones((width, width), dtype=bool)
    if selem_shape == "cross":
        footprint = np.zeros((width, width), dtype=bool)
        center = selem_size
        footprint[center, :] = True
        footprint[:, center] = True
        return footprint
    raise ValueError(f"MorphologyOp: unknown selem_shape {selem_shape!r}")  # pragma: no cover


def _build_op_fn(op: str, footprint: np.ndarray) -> Any:
    from skimage.morphology import black_tophat, closing, dilation, erosion, opening, white_tophat

    if op == "erode":
        return lambda slice_2d, _coord: np.asarray(erosion(slice_2d, footprint=footprint))
    if op == "dilate":
        return lambda slice_2d, _coord: np.asarray(dilation(slice_2d, footprint=footprint))
    if op == "open":
        return lambda slice_2d, _coord: np.asarray(opening(slice_2d, footprint=footprint))
    if op == "close":
        return lambda slice_2d, _coord: np.asarray(closing(slice_2d, footprint=footprint))
    if op == "tophat":
        return lambda slice_2d, _coord: np.asarray(white_tophat(slice_2d, footprint=footprint))
    if op == "bottomhat":
        return lambda slice_2d, _coord: np.asarray(black_tophat(slice_2d, footprint=footprint))
    raise ValueError(f"MorphologyOp: unknown op {op!r}")  # pragma: no cover
