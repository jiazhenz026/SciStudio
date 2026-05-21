"""EdgeDetect - sobel / scharr / canny / prewitt (T-IMG-013)."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.utils.axis_iter import iterate_over_axes
from scistudio_blocks_imaging.types import Image

_METHODS = frozenset({"sobel", "scharr", "canny", "prewitt"})


class EdgeDetect(ProcessBlock):
    """Edge detection on 2D ``(y, x)`` slices."""

    type_name: ClassVar[str] = "imaging.edge_detect"
    name: ClassVar[str] = "Edge Detect"
    description: ClassVar[str] = "Detect edges via Sobel / Scharr / Canny / Prewitt."
    subcategory: ClassVar[str] = "filter"
    algorithm: ClassVar[str] = "edge_detect"

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
                "enum": ["sobel", "scharr", "canny", "prewitt"],
                "default": "sobel",
            },
            "sigma": {"type": "number", "default": 1.0},
            "low_threshold": {"type": "number", "default": 0.1},
            "high_threshold": {"type": "number", "default": 0.2},
        },
        "required": ["method"],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        method = str(config.get("method", "sobel"))
        sigma = float(config.get("sigma", 1.0))
        low_threshold = float(config.get("low_threshold", 0.1))
        high_threshold = float(config.get("high_threshold", 0.2))

        if method not in _METHODS:
            raise ValueError(f"EdgeDetect: unknown method {method!r}; expected one of {sorted(_METHODS)}")
        if sigma < 0:
            raise ValueError(f"EdgeDetect: sigma must be >= 0, got {sigma}")
        if low_threshold < 0 or high_threshold < 0:
            raise ValueError("EdgeDetect: thresholds must be >= 0")
        if low_threshold > high_threshold:
            raise ValueError("EdgeDetect: low_threshold must be <= high_threshold")

        return cast(
            Image,
            iterate_over_axes(
                item, frozenset({"y", "x"}), _build_edge_fn(method, sigma, low_threshold, high_threshold)
            ),
        )


def _build_edge_fn(method: str, sigma: float, low_threshold: float, high_threshold: float) -> Any:
    from skimage.feature import canny
    from skimage.filters import prewitt, scharr, sobel

    if method == "sobel":
        return lambda slice_2d, _coord: np.asarray(sobel(slice_2d))
    if method == "scharr":
        return lambda slice_2d, _coord: np.asarray(scharr(slice_2d))
    if method == "prewitt":
        return lambda slice_2d, _coord: np.asarray(prewitt(slice_2d))
    if method == "canny":
        return lambda slice_2d, _coord: np.asarray(
            canny(
                np.asarray(slice_2d, dtype=np.float64),
                sigma=sigma,
                low_threshold=low_threshold,
                high_threshold=high_threshold,
            )
        )
    raise ValueError(f"EdgeDetect: unknown method {method!r}")  # pragma: no cover
