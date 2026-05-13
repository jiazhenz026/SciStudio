"""Threshold - otsu / li / yen / isodata / mean / triangle / adaptive_otsu / manual (T-IMG-017)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar, cast

import numpy as np

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy.utils.axis_iter import iterate_over_axes
from scieasy_blocks_imaging.types import Image, Mask

_THRESHOLD_METHODS = frozenset(
    {
        "otsu",
        "li",
        "yen",
        "isodata",
        "mean",
        "triangle",
        "adaptive_otsu",
        "manual",
    }
)


class Threshold(ProcessBlock):
    """Single threshold block with multiple methods. Outputs a :class:`Mask`."""

    type_name: ClassVar[str] = "imaging.threshold"
    name: ClassVar[str] = "Threshold"
    description: ClassVar[str] = (
        "Threshold an image into a binary mask (otsu/li/yen/isodata/mean/triangle/adaptive_otsu/manual)."
    )
    subcategory: ClassVar[str] = "segmentation"
    algorithm: ClassVar[str] = "threshold"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="mask", accepted_types=[Mask]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": [
                    "otsu",
                    "li",
                    "yen",
                    "isodata",
                    "mean",
                    "triangle",
                    "adaptive_otsu",
                    "manual",
                ],
                "default": "otsu",
            },
            "value": {
                "type": "number",
                "description": "Manual threshold value (for method=manual).",
            },
            "block_size": {
                "type": "integer",
                "default": 35,
                "description": "Window size for adaptive_otsu.",
            },
        },
        "required": ["method"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Override Tier 1 run so the output collection carries ``Mask`` items."""
        images = _coerce_images(inputs.get("image"))
        masks = [cast(Mask, self._auto_flush(self.process_item(image, config))) for image in images]
        return {"mask": Collection(items=cast(list[DataObject], masks), item_type=Mask)}

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Mask:
        """Threshold to a binary mask."""
        method = str(config.get("method", "otsu"))
        if method not in _THRESHOLD_METHODS:
            raise ValueError(f"Threshold: unknown method {method!r}; expected one of {sorted(_THRESHOLD_METHODS)}")

        threshold_fn = _build_threshold_fn(method, config)
        result = cast(Image, iterate_over_axes(item, frozenset({"y", "x"}), threshold_fn))
        mask = Mask(
            axes=list(result.axes),
            shape=result.shape,
            dtype=bool,
            chunk_shape=result.chunk_shape,
            framework=result.framework,
            meta=result.meta,
            user=dict(result.user),
            storage_ref=None,
        )
        mask._data = np.asarray(result.to_memory(), dtype=bool)  # type: ignore[attr-defined]
        return mask


def _build_threshold_fn(method: str, config: BlockConfig) -> Callable[[np.ndarray, dict[str, int]], np.ndarray]:
    from skimage import filters

    if method == "manual":
        value = config.get("value")
        if value is None:
            raise ValueError("Threshold: method='manual' requires 'value'")
        threshold_value = float(value)
        return lambda slice_2d, _coord: np.asarray(slice_2d > threshold_value, dtype=bool)

    if method == "adaptive_otsu":
        block_size = int(config.get("block_size", 35))
        if block_size < 3:
            raise ValueError(f"Threshold: block_size must be >= 3, got {block_size}")
        if block_size % 2 == 0:
            block_size += 1
        return lambda slice_2d, _coord: np.asarray(
            slice_2d > filters.threshold_local(np.asarray(slice_2d, dtype=np.float64), block_size=block_size),
            dtype=bool,
        )

    fn_map: dict[str, Callable[[np.ndarray], float]] = {
        "otsu": filters.threshold_otsu,
        "li": filters.threshold_li,
        "yen": filters.threshold_yen,
        "isodata": filters.threshold_isodata,
        "mean": filters.threshold_mean,
        "triangle": filters.threshold_triangle,
    }
    threshold_scalar = fn_map[method]
    return lambda slice_2d, _coord: np.asarray(slice_2d > threshold_scalar(np.asarray(slice_2d)), dtype=bool)


def _coerce_images(value: Collection | Image | None) -> list[Image]:
    if value is None:
        raise ValueError("Threshold: missing required 'image' input")
    if isinstance(value, Image):
        return [value]
    if not isinstance(value, Collection):
        raise ValueError(f"Threshold: expected Image or Collection[Image], got {type(value).__name__}")

    images: list[Image] = []
    for item in value:
        if not isinstance(item, Image):
            raise ValueError(f"Threshold: image collection must contain Image items, got {type(item).__name__}")
        images.append(item)
    return images


__all__ = ["Threshold"]
