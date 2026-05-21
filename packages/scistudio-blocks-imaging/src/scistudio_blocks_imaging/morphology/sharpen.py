"""Sharpen - unsharp mask / laplacian (T-IMG-015)."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.utils.axis_iter import iterate_over_axes
from scistudio_blocks_imaging.types import Image

_METHODS = frozenset({"unsharp", "laplacian"})


class Sharpen(ProcessBlock):
    """Sharpen 2D ``(y, x)`` slices via unsharp mask or Laplacian."""

    type_name: ClassVar[str] = "imaging.sharpen"
    name: ClassVar[str] = "Sharpen"
    description: ClassVar[str] = "Image sharpening (unsharp mask or Laplacian)."
    subcategory: ClassVar[str] = "filter"
    algorithm: ClassVar[str] = "sharpen"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["unsharp", "laplacian"],
                "default": "unsharp",
            },
            "amount": {"type": "number", "default": 1.0},
            "radius": {"type": "number", "default": 1.0},
        },
        "required": ["method"],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        method = str(config.get("method", "unsharp"))
        amount = float(config.get("amount", 1.0))
        radius = float(config.get("radius", 1.0))

        if method not in _METHODS:
            raise ValueError(f"Sharpen: unknown method {method!r}; expected one of {sorted(_METHODS)}")
        if amount < 0:
            raise ValueError(f"Sharpen: amount must be >= 0, got {amount}")
        if radius <= 0:
            raise ValueError(f"Sharpen: radius must be > 0, got {radius}")

        return cast(Image, iterate_over_axes(item, frozenset({"y", "x"}), _build_sharpen_fn(method, amount, radius)))


def _build_sharpen_fn(method: str, amount: float, radius: float) -> Any:
    from skimage.filters import laplace, unsharp_mask

    if method == "unsharp":
        return lambda slice_2d, _coord: np.asarray(
            unsharp_mask(slice_2d, radius=radius, amount=amount, preserve_range=True)
        )
    if method == "laplacian":
        ksize = max(1, round(radius) * 2 + 1)
        return lambda slice_2d, _coord: np.asarray(slice_2d - amount * laplace(slice_2d, ksize=ksize))
    raise ValueError(f"Sharpen: unknown method {method!r}")  # pragma: no cover
