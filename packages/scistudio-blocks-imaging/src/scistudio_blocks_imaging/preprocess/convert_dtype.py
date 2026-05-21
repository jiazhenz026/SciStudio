"""ConvertDType - uint8 / uint16 / float32 / float64 / bool (T-IMG-009)."""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio_blocks_imaging.types import Image

_TARGET_DTYPES: dict[str, np.dtype[Any]] = {
    "uint8": np.dtype(np.uint8),
    "uint16": np.dtype(np.uint16),
    "float32": np.dtype(np.float32),
    "float64": np.dtype(np.float64),
    "bool": np.dtype(bool),
}


class ConvertDType(ProcessBlock):
    """Convert image dtype with optional rescaling or clipping."""

    type_name: ClassVar[str] = "imaging.convert_dtype"
    name: ClassVar[str] = "Convert DType"
    description: ClassVar[str] = "Convert image dtype (uint8/uint16/float32/float64/bool)."
    subcategory: ClassVar[str] = "preprocess"
    algorithm: ClassVar[str] = "convert_dtype"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "target_dtype": {
                "type": "string",
                "enum": ["uint8", "uint16", "float32", "float64", "bool"],
                "default": "float32",
            },
            "rescale": {
                "type": "string",
                "enum": ["linear", "clip"],
                "default": "linear",
            },
        },
        "required": ["target_dtype"],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        """Convert dtype while preserving image axes / shape / metadata."""
        target_name = str(config.get("target_dtype", "float32"))
        rescale = str(config.get("rescale", "linear"))
        if target_name not in _TARGET_DTYPES:
            raise ValueError(f"ConvertDType: unsupported target_dtype {target_name!r}")
        if rescale not in {"linear", "clip"}:
            raise ValueError(f"ConvertDType: unsupported rescale mode {rescale!r}")

        data = _image_data(item)
        converted = _convert_array(data, _TARGET_DTYPES[target_name], rescale=rescale)
        return _make_derived_image(item, converted)


def _image_data(image: Image) -> np.ndarray:
    if image.storage_ref is None and hasattr(image, "_data") and getattr(image, "_data", None) is not None:
        return np.asarray(image._data)  # type: ignore[attr-defined]
    return np.asarray(image.to_memory())


def _make_derived_image(source: Image, data: np.ndarray) -> Image:
    result = Image(
        axes=list(source.axes),
        shape=tuple(data.shape),
        dtype=data.dtype,
        framework=source.framework.derive(),
        meta=source.meta,
        user=dict(source.user),
        storage_ref=None,
    )
    result._data = data  # type: ignore[attr-defined]
    return result


def _convert_array(arr: np.ndarray, target: np.dtype[Any], *, rescale: str) -> np.ndarray:
    if np.issubdtype(target, np.bool_):
        return np.asarray(arr > 0, dtype=target)
    if rescale == "linear":
        return _convert_linear(arr, target)
    return _convert_clip(arr, target)


def _convert_linear(arr: np.ndarray, target: np.dtype[Any]) -> np.ndarray:
    arr_np = np.asarray(arr)
    arr_float = arr_np.astype(np.float64, copy=False)

    info_in = _dtype_info(arr_np.dtype)
    info_out = _dtype_info(target)

    if info_in is not None and info_out is not None:
        in_min, in_max = info_in
        out_min, out_max = info_out
        if in_max == in_min:
            return np.zeros_like(arr_float, dtype=target)
        normalized = (arr_float - in_min) / (in_max - in_min)
        scaled = normalized * (out_max - out_min) + out_min
        return np.asarray(np.clip(scaled, out_min, out_max), dtype=target)

    if info_in is not None:
        in_min, in_max = info_in
        if in_max == in_min:
            return np.zeros_like(arr_float, dtype=target)
        normalized = (arr_float - in_min) / (in_max - in_min)
        return np.asarray(normalized, dtype=target)

    if info_out is not None:
        out_min, out_max = info_out
        scaled = np.clip(arr_float, 0.0, 1.0) * (out_max - out_min) + out_min
        return np.asarray(np.clip(scaled, out_min, out_max), dtype=target)

    return np.asarray(arr_float, dtype=target)


def _convert_clip(arr: np.ndarray, target: np.dtype[Any]) -> np.ndarray:
    arr_np = np.asarray(arr)
    info_out = _dtype_info(target)
    if info_out is not None:
        out_min, out_max = info_out
        return np.asarray(np.clip(arr_np, out_min, out_max), dtype=target)
    return np.asarray(arr_np, dtype=target)


def _dtype_info(dtype: np.dtype[Any]) -> tuple[float, float] | None:
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        return (float(info.min), float(info.max))
    return None


__all__ = ["ConvertDType"]
