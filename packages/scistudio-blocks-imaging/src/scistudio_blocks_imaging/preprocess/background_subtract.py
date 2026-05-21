"""BackgroundSubtract — rollingball / tophat / polynomial / constant (T-IMG-005).

Sprint C imaging preprocess subset A. See
``docs/specs/phase11-imaging-block-spec.md`` §9 T-IMG-005.

Operates on 2D ``(y, x)`` slices; N-D inputs broadcast via
:func:`scistudio.utils.axis_iter.iterate_over_axes`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.utils.axis_iter import iterate_over_axes
from scistudio_blocks_imaging.types import Image

_ALLOWED_METHODS = frozenset({"rollingball", "tophat", "polynomial", "constant"})

_SliceFn = Callable[[np.ndarray, dict[str, int]], np.ndarray]


class BackgroundSubtract(ProcessBlock):
    """Subtract estimated background from each ``(y, x)`` slice."""

    type_name: ClassVar[str] = "imaging.background_subtract"
    name: ClassVar[str] = "Background Subtract"
    description: ClassVar[str] = "Subtract image background via rolling-ball / top-hat / polynomial / constant."
    subcategory: ClassVar[str] = "preprocess"
    algorithm: ClassVar[str] = "background_subtract"

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
                "enum": sorted(_ALLOWED_METHODS),
                "default": "rollingball",
            },
            "radius": {"type": "integer", "default": 25, "minimum": 1},
            "degree": {"type": "integer", "default": 2, "minimum": 0},
            "value": {"type": "number", "default": 0.0},
            "clip_to_zero": {"type": "boolean", "default": True},
        },
        "required": ["method"],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        """Subtract background slice-wise.

        Raises:
            ValueError: If ``method`` is unknown, ``radius < 1``, or
                ``degree < 0``.
        """
        method = config.get("method", "rollingball")
        radius = int(config.get("radius", 25))
        degree = int(config.get("degree", 2))
        clip_to_zero = bool(config.get("clip_to_zero", True))
        value = float(config.get("value", 0.0))
        if method not in _ALLOWED_METHODS:
            raise ValueError(
                f"BackgroundSubtract: unknown method {method!r}; expected one of {sorted(_ALLOWED_METHODS)}"
            )
        if radius < 1:
            raise ValueError(f"BackgroundSubtract: radius must be >= 1, got {radius}")
        if degree < 0:
            raise ValueError(f"BackgroundSubtract: degree must be >= 0, got {degree}")
        fn = _build_background_fn(
            method,
            radius=radius,
            degree=degree,
            value=value,
            clip_to_zero=clip_to_zero,
        )
        return cast(Image, iterate_over_axes(item, frozenset({"y", "x"}), fn))


def _maybe_clip(out: np.ndarray, clip_to_zero: bool) -> np.ndarray:
    if clip_to_zero:
        return np.asarray(np.clip(out, 0, None))
    return out


def _build_background_fn(
    method: str,
    *,
    radius: int,
    degree: int,
    value: float,
    clip_to_zero: bool,
) -> _SliceFn:
    """Return a per-slice numpy callable for ``method``."""
    if method == "rollingball":
        from skimage.restoration import rolling_ball

        def _roll(slice_2d: np.ndarray, _coord: dict[str, int]) -> np.ndarray:
            bg = np.asarray(rolling_ball(slice_2d, radius=radius))
            out = slice_2d.astype(np.float64) - bg.astype(np.float64)
            return _maybe_clip(out, clip_to_zero)

        return _roll
    if method == "tophat":
        from skimage.morphology import disk, white_tophat

        footprint = disk(radius)

        def _th(slice_2d: np.ndarray, _coord: dict[str, int]) -> np.ndarray:
            out = np.asarray(white_tophat(slice_2d, footprint=footprint))
            return _maybe_clip(out, clip_to_zero)

        return _th
    if method == "polynomial":
        return _polynomial_background_fn(degree=degree, clip_to_zero=clip_to_zero)
    if method == "constant":

        def _const(slice_2d: np.ndarray, _coord: dict[str, int]) -> np.ndarray:
            out = slice_2d.astype(np.float64) - value
            return _maybe_clip(out, clip_to_zero)

        return _const
    raise ValueError(f"BackgroundSubtract: unknown method {method!r}")  # pragma: no cover


def _polynomial_background_fn(*, degree: int, clip_to_zero: bool) -> _SliceFn:
    def _poly(slice_2d: np.ndarray, _coord: dict[str, int]) -> np.ndarray:
        h, w = slice_2d.shape
        yy, xx = np.mgrid[0:h, 0:w]
        features: list[np.ndarray] = []
        for i in range(degree + 1):
            for j in range(degree + 1 - i):
                features.append((xx.astype(np.float64) ** i * yy.astype(np.float64) ** j).ravel())
        a_matrix = np.stack(features, axis=1)
        b_vec = slice_2d.astype(np.float64).ravel()
        coeffs, *_ = np.linalg.lstsq(a_matrix, b_vec, rcond=None)
        bg = (a_matrix @ coeffs).reshape(h, w)
        out = slice_2d.astype(np.float64) - bg
        return _maybe_clip(out, clip_to_zero)

    return _poly
