"""FFTFilter - frequency-domain low/high/band-pass (T-IMG-016)."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.utils.axis_iter import iterate_over_axes
from scistudio_blocks_imaging.types import Image

_FILTER_TYPES = frozenset({"lowpass", "highpass", "bandpass"})


class FFTFilter(ProcessBlock):
    """Frequency-domain filtering with circular masks."""

    type_name: ClassVar[str] = "imaging.fft_filter"
    name: ClassVar[str] = "FFT Filter"
    description: ClassVar[str] = "FFT lowpass / highpass / bandpass filter."
    subcategory: ClassVar[str] = "filter"
    algorithm: ClassVar[str] = "fft_filter"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["lowpass", "highpass", "bandpass"],
                "default": "lowpass",
            },
            "cutoff_low": {"type": "number", "default": 0.1},
            "cutoff_high": {"type": "number", "default": 0.5},
        },
        "required": ["type"],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        filter_type = str(config.get("type", "lowpass"))
        cutoff_low = float(config.get("cutoff_low", 0.1))
        cutoff_high = float(config.get("cutoff_high", 0.5))

        if filter_type not in _FILTER_TYPES:
            raise ValueError(f"FFTFilter: unknown type {filter_type!r}; expected one of {sorted(_FILTER_TYPES)}")
        if not (0.0 <= cutoff_low <= 1.0 and 0.0 <= cutoff_high <= 1.0):
            raise ValueError("FFTFilter: cutoff_low and cutoff_high must be between 0 and 1")
        if cutoff_low > cutoff_high:
            raise ValueError("FFTFilter: cutoff_low must be <= cutoff_high")

        return cast(
            Image,
            iterate_over_axes(
                item,
                frozenset({"y", "x"}),
                lambda slice_2d, _coord: _fft_filter_slice(slice_2d, filter_type, cutoff_low, cutoff_high),
            ),
        )


def _fft_filter_slice(
    slice_2d: np.ndarray,
    filter_type: str,
    cutoff_low: float,
    cutoff_high: float,
) -> np.ndarray:
    arr = np.asarray(slice_2d, dtype=np.float64)
    freq = np.fft.fftshift(np.fft.fft2(arr))
    mask = _radial_mask(arr.shape, filter_type, cutoff_low, cutoff_high)
    filtered = np.fft.ifft2(np.fft.ifftshift(freq * mask))
    return np.asarray(np.real(filtered), dtype=arr.dtype)


def _radial_mask(shape: tuple[int, int], filter_type: str, cutoff_low: float, cutoff_high: float) -> np.ndarray:
    yy, xx = np.ogrid[: shape[0], : shape[1]]
    cy = (shape[0] - 1) / 2.0
    cx = (shape[1] - 1) / 2.0
    radius = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    radius /= radius.max() if radius.max() else 1.0

    if filter_type == "lowpass":
        return radius <= cutoff_high
    if filter_type == "highpass":
        return radius >= cutoff_low
    if filter_type == "bandpass":
        return (radius >= cutoff_low) & (radius <= cutoff_high)
    raise ValueError(f"FFTFilter: unknown type {filter_type!r}")  # pragma: no cover
