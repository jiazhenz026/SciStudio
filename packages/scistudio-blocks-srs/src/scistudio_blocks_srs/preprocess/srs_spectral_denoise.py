"""SRSSpectralDenoise - Savitzky-Golay spectral smoothing."""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.block import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.utils.constraints import has_axes
from scistudio_blocks_srs.types import SRSImage


class SRSSpectralDenoise(ProcessBlock):
    """Denoise an :class:`SRSImage` along the spectral (lambda) axis with Savitzky-Golay."""

    name: ClassVar[str] = "SRS Spectral Denoise"
    type_name: ClassVar[str] = "srs.spectral_denoise"
    description: ClassVar[str] = "Per-pixel Savitzky-Golay smoothing along the spectral axis."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "savitzky_golay"

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
            description="Denoised SRSImage with preserved meta.",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "window_length": {
                "type": "integer",
                "default": 7,
                "minimum": 3,
                "title": "Window Length",
                "description": "Must be odd integer",
                "ui_priority": 0,
            },
            "polyorder": {
                "type": "integer",
                "default": 3,
                "minimum": 1,
                "title": "Polynomial Order",
                "ui_priority": 1,
            },
        },
    }

    def process_item(self, item: SRSImage, config: BlockConfig, state: Any = None) -> SRSImage:
        """Apply Savitzky-Golay filter along the spectral (lambda) axis."""
        window_length = int(config.get("window_length", 7))
        polyorder = int(config.get("polyorder", 3))

        if window_length % 2 == 0:
            raise ValueError(f"SRSSpectralDenoise: window_length must be odd, got {window_length}")
        if polyorder >= window_length:
            raise ValueError(
                f"SRSSpectralDenoise: polyorder ({polyorder}) must be less than window_length ({window_length})"
            )

        lambda_axis = item.axes.index("lambda")
        data = np.asarray(item.to_memory(), dtype=np.float64)

        n_lambda = data.shape[lambda_axis]
        if window_length > n_lambda:
            raise ValueError(
                f"SRSSpectralDenoise: window_length ({window_length}) exceeds lambda axis size ({n_lambda})"
            )

        from scipy.signal import savgol_filter

        denoised = savgol_filter(data, window_length=window_length, polyorder=polyorder, axis=lambda_axis)
        out_data = np.asarray(denoised, dtype=np.float32)

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


__all__ = ["SRSSpectralDenoise"]
