"""ApplyTransform — warp an Image using a Transform.

See ``docs/specs/phase11-imaging-block-spec.md`` §9 T-IMG-028.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.utils.axis_iter import iterate_over_axes
from scistudio_blocks_imaging.types import Image, Transform

_INTERPOLATION_ORDERS = {"nearest": 0, "linear": 1, "cubic": 3}


class ApplyTransform(ProcessBlock):
    """Apply a :class:`Transform` to an :class:`Image`, returning a warped Image."""

    type_name: ClassVar[str] = "imaging.apply_transform"
    name: ClassVar[str] = "Apply Transform"
    description: ClassVar[str] = "Warp an Image using a precomputed Transform."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "registration"
    algorithm: ClassVar[str] = "apply_transform"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], description="Image to warp."),
        InputPort(name="transform", accepted_types=[Transform], description="Transform to apply."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="warped", accepted_types=[Image], description="Warped Image."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "interpolation": {
                "type": "string",
                "enum": ["nearest", "linear", "cubic"],
                "default": "linear",
            },
        },
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        image = _require_single_image(inputs.get("image"), "image")
        transform = _require_single_transform(inputs.get("transform"))
        warped = self.process_item(image, config, transform)
        return {"warped": Collection(items=cast(list[DataObject], [warped]), item_type=Image)}

    def process_item(
        self,
        item: Image,
        config: BlockConfig,
        state: Any = None,
    ) -> Image:
        if not isinstance(state, Transform):
            raise ValueError("ApplyTransform: process_item requires the Transform as state")
        interpolation = _require_interpolation(config)
        matrix = _transform_matrix(state)
        return _apply_matrix_to_image(item, matrix, interpolation=interpolation)


def _require_single_image(value: Any, name: str) -> Image:
    if value is None:
        raise ValueError(f"ApplyTransform: missing required input {name!r}")
    if isinstance(value, Image):
        return value
    if not isinstance(value, Collection):
        raise ValueError("ApplyTransform: image input must be an Image or Collection[Image]")
    if len(value) != 1:
        raise ValueError("ApplyTransform: image Collection must contain exactly one Image")
    item = value[0]
    if not isinstance(item, Image):
        raise ValueError("ApplyTransform: image Collection must contain Image items")
    return item


def _require_single_transform(value: Any) -> Transform:
    if value is None:
        raise ValueError("ApplyTransform: missing required input 'transform'")
    if isinstance(value, Transform):
        return value
    if not isinstance(value, Collection):
        raise ValueError("ApplyTransform: transform input must be a Transform or Collection[Transform]")
    if len(value) != 1:
        raise ValueError("ApplyTransform: transform Collection must contain exactly one Transform")
    item = value[0]
    if not isinstance(item, Transform):
        raise ValueError("ApplyTransform: transform Collection must contain Transform items")
    return item


def _require_interpolation(config: BlockConfig) -> str:
    interpolation = str(config.get("interpolation", "linear"))
    if interpolation not in _INTERPOLATION_ORDERS:
        raise ValueError(
            f"ApplyTransform: interpolation must be one of {sorted(_INTERPOLATION_ORDERS)}, got {interpolation!r}"
        )
    return interpolation


def _transform_matrix(transform: Transform) -> np.ndarray:
    if transform.storage_ref is None and hasattr(transform, "_data") and getattr(transform, "_data", None) is not None:
        matrix = np.asarray(transform._data, dtype=np.float64)  # type: ignore[attr-defined]
    else:
        matrix = np.asarray(transform.to_memory(), dtype=np.float64)

    if matrix.shape == (2, 3):
        out = np.eye(3, dtype=np.float64)
        out[:2, :] = matrix
        return out
    if matrix.shape == (3, 3):
        return matrix
    raise ValueError(f"ApplyTransform: transform matrix must be shape (2, 3) or (3, 3), got {matrix.shape}")


def _apply_matrix_to_image(image: Image, matrix: np.ndarray, *, interpolation: str) -> Image:
    from skimage.transform import AffineTransform, warp

    if "y" not in image.axes or "x" not in image.axes:
        raise ValueError(f"ApplyTransform: image must include 'y' and 'x' axes, got {image.axes}")

    order = _INTERPOLATION_ORDERS[interpolation]
    affine_matrix = matrix
    if affine_matrix.shape == (2, 3):
        lifted = np.eye(3, dtype=np.float64)
        lifted[:2, :] = affine_matrix
        affine_matrix = lifted
    elif affine_matrix.shape != (3, 3):
        raise ValueError(f"ApplyTransform: transform matrix must be shape (2, 3) or (3, 3), got {affine_matrix.shape}")

    affine = AffineTransform(matrix=affine_matrix)
    return cast(
        Image,
        iterate_over_axes(
            image,
            frozenset({"y", "x"}),
            lambda slice_2d, _coord: np.asarray(
                warp(
                    slice_2d,
                    affine.inverse,
                    order=order,
                    preserve_range=True,
                )
            ),
        ),
    )


__all__ = ["ApplyTransform", "_apply_matrix_to_image", "_require_single_transform", "_transform_matrix"]
