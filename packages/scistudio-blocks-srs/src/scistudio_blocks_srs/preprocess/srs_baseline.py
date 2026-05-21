"""SRSBaseline - spectral baseline correction."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.block import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.utils.constraints import has_axes
from scistudio_blocks_srs.types import SRSImage

ALLOWED_METHODS: tuple[str, ...] = ("polynomial", "rubber_band", "rolling_ball_spectral")


class SRSBaseline(ProcessBlock):
    """Subtract a fitted baseline from each per-pixel spectrum."""

    name: ClassVar[str] = "SRS Baseline Correct"
    type_name: ClassVar[str] = "srs.baseline"
    description: ClassVar[str] = (
        "Subtract a fitted spectral baseline (polynomial / rubber_band / rolling_ball_spectral). "
        "ALS is intentionally not supported."
    )
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "spectral_baseline"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="image",
            accepted_types=[SRSImage],
            description="SRSImage with y/x/lambda axes.",
            constraint=has_axes("y", "x", "lambda"),
            constraint_description="image must carry y/x/lambda axes",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="image",
            accepted_types=[SRSImage],
            description="Baseline-subtracted SRSImage with preserved meta.",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": list(ALLOWED_METHODS),
                "default": "polynomial",
            },
            "order": {"type": "integer", "default": 3, "minimum": 1},
            "window": {"type": "integer", "default": 50, "minimum": 1},
        },
    }

    def process_item(self, item: SRSImage, config: BlockConfig, state: Any = None) -> SRSImage:
        """Dispatch on ``method`` and return a baseline-subtracted SRSImage."""
        method = str(config.get("method", "polynomial"))
        order = int(config.get("order", 3))
        window = int(config.get("window", 50))

        if method not in ALLOWED_METHODS:
            raise ValueError(
                f"SRSBaseline: method must be one of {ALLOWED_METHODS}; ALS is intentionally unsupported, got {method!r}"
            )
        if order < 1:
            raise ValueError(f"SRSBaseline: order must be >= 1, got {order}")
        if window < 1:
            raise ValueError(f"SRSBaseline: window must be >= 1, got {window}")

        lambda_pos = item.axes.index("lambda")
        moved = np.moveaxis(np.asarray(item.to_memory(), dtype=np.float64), lambda_pos, -1)

        if method == "polynomial":
            corrected = _baseline_polynomial(moved, order=order)
        elif method == "rubber_band":
            corrected = _baseline_rubber_band(moved)
        else:
            corrected = _baseline_rolling_ball(moved, window=window)

        out_data = np.moveaxis(np.asarray(corrected, dtype=np.float32), -1, lambda_pos)
        out = SRSImage(
            axes=list(item.axes),
            shape=out_data.shape,
            dtype=out_data.dtype,
            chunk_shape=item.chunk_shape,
            framework=item.framework.derive(),
            meta=item.meta,
            user=dict(item.user),
            storage_ref=None,
        )
        out._data = out_data  # type: ignore[attr-defined]
        return out


def _baseline_polynomial(spec: np.ndarray, *, order: int) -> np.ndarray:
    n_w = spec.shape[-1]
    x = np.arange(n_w, dtype=np.float64)
    design = np.vander(x, N=order + 1, increasing=False)
    flat = spec.reshape(-1, n_w)
    coeffs, *_ = np.linalg.lstsq(design, flat.T, rcond=None)
    fitted = (design @ coeffs).T.reshape(spec.shape)
    return cast(np.ndarray, spec - fitted)


def _baseline_rubber_band(spec: np.ndarray) -> np.ndarray:
    n_w = spec.shape[-1]
    x = np.arange(n_w, dtype=np.float64)
    flat = spec.reshape(-1, n_w)
    corrected = np.empty_like(flat)
    for idx, row in enumerate(flat):
        hull_idx = _lower_hull_indices(x, row)
        baseline = np.interp(x, x[hull_idx], row[hull_idx])
        corrected[idx] = row - baseline
    return cast(np.ndarray, corrected.reshape(spec.shape))


def _lower_hull_indices(x: np.ndarray, y: np.ndarray) -> list[int]:
    hull: list[int] = []
    for idx in range(len(x)):
        while len(hull) >= 2:
            i, j = hull[-2], hull[-1]
            cross = (x[j] - x[i]) * (y[idx] - y[i]) - (y[j] - y[i]) * (x[idx] - x[i])
            if cross <= 0:
                hull.pop()
            else:
                break
        hull.append(idx)
    return hull


def _baseline_rolling_ball(spec: np.ndarray, *, window: int) -> np.ndarray:
    size = [1] * spec.ndim
    size[-1] = window
    from scipy import ndimage

    baseline = ndimage.grey_opening(spec, size=tuple(size))
    return cast(np.ndarray, spec - baseline)


__all__ = ["ALLOWED_METHODS", "SRSBaseline"]
