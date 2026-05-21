"""RidgeFilter - frangi / meijering / sato / hessian (T-IMG-014)."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.utils.axis_iter import iterate_over_axes
from scistudio_blocks_imaging.types import Image

_METHODS = frozenset({"frangi", "meijering", "sato", "hessian"})


class RidgeFilter(ProcessBlock):
    """Ridge / vesselness filters on 2D ``(y, x)`` slices."""

    type_name: ClassVar[str] = "imaging.ridge_filter"
    name: ClassVar[str] = "Ridge Filter"
    description: ClassVar[str] = "Ridge / vesselness filtering (Frangi / Meijering / Sato / Hessian)."
    subcategory: ClassVar[str] = "filter"
    algorithm: ClassVar[str] = "ridge_filter"

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
                "enum": ["frangi", "meijering", "sato", "hessian"],
                "default": "frangi",
            },
            "sigma_min": {"type": "number", "default": 1.0},
            "sigma_max": {"type": "number", "default": 10.0},
            "num_sigma": {"type": "integer", "default": 10},
        },
        "required": ["method"],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        method = str(config.get("method", "frangi"))
        sigma_min = float(config.get("sigma_min", 1.0))
        sigma_max = float(config.get("sigma_max", 10.0))
        num_sigma = int(config.get("num_sigma", 10))

        if method not in _METHODS:
            raise ValueError(f"RidgeFilter: unknown method {method!r}; expected one of {sorted(_METHODS)}")
        if sigma_min <= 0 or sigma_max <= 0:
            raise ValueError("RidgeFilter: sigma_min and sigma_max must be > 0")
        if sigma_min > sigma_max:
            raise ValueError("RidgeFilter: sigma_min must be <= sigma_max")
        if num_sigma < 1:
            raise ValueError("RidgeFilter: num_sigma must be >= 1")

        sigmas = tuple(np.linspace(sigma_min, sigma_max, num_sigma, dtype=np.float64))
        return cast(Image, iterate_over_axes(item, frozenset({"y", "x"}), _build_ridge_fn(method, sigmas)))


def _build_ridge_fn(method: str, sigmas: tuple[float, ...]) -> Any:
    from skimage.filters import frangi, hessian, meijering, sato

    if method == "frangi":
        return lambda slice_2d, _coord: np.asarray(frangi(slice_2d, sigmas=sigmas))
    if method == "meijering":
        return lambda slice_2d, _coord: np.asarray(meijering(slice_2d, sigmas=sigmas))
    if method == "sato":
        return lambda slice_2d, _coord: np.asarray(sato(slice_2d, sigmas=sigmas))
    if method == "hessian":
        return lambda slice_2d, _coord: np.asarray(hessian(slice_2d, sigmas=sigmas))
    raise ValueError(f"RidgeFilter: unknown method {method!r}")  # pragma: no cover
