"""Scalar arithmetic bundle for the imaging plugin."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio_blocks_imaging.types import Image


def _scalar_schema(default: float = 0.0) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "value": {"type": "number", "default": default},
        },
    }


class AddScalar(ProcessBlock):
    """Add a scalar to every pixel of an :class:`Image`."""

    type_name: ClassVar[str] = "imaging.add_scalar"
    name: ClassVar[str] = "Add Scalar"
    description: ClassVar[str] = "Add a scalar to every pixel."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "math"
    algorithm: ClassVar[str] = "add_scalar"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], description="Input image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image], description="Output image."),
    ]
    config_schema: ClassVar[dict[str, Any]] = _scalar_schema(0.0)

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        return _apply_scalar_op(item, config, lambda data, value: np.asarray(data + value))


class SubtractScalar(ProcessBlock):
    """Subtract a scalar from every pixel of an :class:`Image`."""

    type_name: ClassVar[str] = "imaging.subtract_scalar"
    name: ClassVar[str] = "Subtract Scalar"
    description: ClassVar[str] = "Subtract a scalar from every pixel."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "math"
    algorithm: ClassVar[str] = "subtract_scalar"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], description="Input image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image], description="Output image."),
    ]
    config_schema: ClassVar[dict[str, Any]] = _scalar_schema(0.0)

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        return _apply_scalar_op(item, config, lambda data, value: np.asarray(data - value))


class MultiplyScalar(ProcessBlock):
    """Multiply every pixel of an :class:`Image` by a scalar."""

    type_name: ClassVar[str] = "imaging.multiply_scalar"
    name: ClassVar[str] = "Multiply Scalar"
    description: ClassVar[str] = "Multiply every pixel by a scalar."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "math"
    algorithm: ClassVar[str] = "multiply_scalar"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], description="Input image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image], description="Output image."),
    ]
    config_schema: ClassVar[dict[str, Any]] = _scalar_schema(1.0)

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        return _apply_scalar_op(item, config, lambda data, value: np.asarray(data * value))


class DivideScalar(ProcessBlock):
    """Divide every pixel of an :class:`Image` by a scalar."""

    type_name: ClassVar[str] = "imaging.divide_scalar"
    name: ClassVar[str] = "Divide Scalar"
    description: ClassVar[str] = "Divide every pixel by a scalar with optional epsilon."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "math"
    algorithm: ClassVar[str] = "divide_scalar"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], description="Input image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image], description="Output image."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "value": {"type": "number", "default": 1.0},
            "epsilon": {"type": "number", "default": 1e-9},
        },
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        value = _scalar_value(config)
        epsilon = float(config.get("epsilon", 1e-9))
        denominator = value + epsilon
        if np.isclose(denominator, 0.0):
            raise ValueError("DivideScalar: value + epsilon must be non-zero")
        return _make_derived_image(item, np.asarray(_image_data(item) / denominator))


def _apply_scalar_op(
    image: Image,
    config: BlockConfig,
    op: Callable[[np.ndarray, float], np.ndarray],
) -> Image:
    value = _scalar_value(config)
    return _make_derived_image(image, op(_image_data(image), value))


def _scalar_value(config: BlockConfig) -> float:
    value = config.get("value", 0.0)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"Scalar value must be a number, got {type(value).__name__}")
    return float(value)


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


__all__ = ["AddScalar", "DivideScalar", "MultiplyScalar", "SubtractScalar"]
