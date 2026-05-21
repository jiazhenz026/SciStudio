"""ComputeRegistration — estimate a Transform aligning a moving Image to a fixed Image.

See ``docs/specs/phase11-imaging-block-spec.md`` §9 T-IMG-027.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio_blocks_imaging.types import Image, Transform

_METHODS = frozenset({"phase_correlation", "rigid", "affine"})
_SPATIAL_AXES = frozenset({"y", "x"})


class ComputeRegistration(ProcessBlock):
    """Estimate a :class:`Transform` aligning ``moving`` to ``fixed``."""

    type_name: ClassVar[str] = "imaging.compute_registration"
    name: ClassVar[str] = "Compute Registration"
    description: ClassVar[str] = (
        "Estimate a Transform that aligns a moving Image to a fixed Image (rigid / affine / phase correlation)."
    )
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "registration"
    algorithm: ClassVar[str] = "compute_registration"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="moving", accepted_types=[Image], description="Moving image to be aligned."),
        InputPort(name="fixed", accepted_types=[Image], description="Reference image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="transform", accepted_types=[Transform], description="Estimated transform."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["phase_correlation", "rigid", "affine"],
                "default": "phase_correlation",
            },
        },
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        moving = _require_single_image(inputs.get("moving"), "moving")
        fixed = _require_single_image(inputs.get("fixed"), "fixed")
        transform = self.process_item(moving, config, fixed)
        return {"transform": Collection(items=cast(list[DataObject], [transform]), item_type=Transform)}

    def process_item(
        self,
        item: Image,
        config: BlockConfig,
        state: Any = None,
    ) -> Transform:
        if not isinstance(state, Image):
            raise ValueError("ComputeRegistration: process_item requires the fixed Image as state")

        method = _require_method(config)
        shift = _estimate_shift(item, state)
        matrix = _matrix_from_shift(shift, method)
        transform = Transform(
            axes=["row", "col"],
            shape=tuple(matrix.shape),
            dtype=matrix.dtype,
            framework=state.framework.derive(),
            meta=Transform.Meta(
                transform_type=method,
                reference_shape=tuple(state.shape) if state.shape is not None else None,
            ),
            user=dict(state.user),
        )
        transform._data = matrix  # type: ignore[attr-defined]
        return transform


def _require_single_image(value: Any, name: str) -> Image:
    if value is None:
        raise ValueError(f"ComputeRegistration: missing required input {name!r}")
    if isinstance(value, Image):
        return value
    if not isinstance(value, Collection):
        raise ValueError(f"ComputeRegistration: input {name!r} must be an Image or Collection[Image]")
    if len(value) != 1:
        raise ValueError(f"ComputeRegistration: input {name!r} must contain exactly one Image")
    item = value[0]
    if not isinstance(item, Image):
        raise ValueError(f"ComputeRegistration: input {name!r} must contain Image items")
    return item


def _require_method(config: BlockConfig) -> str:
    method = str(config.get("method", "phase_correlation"))
    if method not in _METHODS:
        raise ValueError(f"ComputeRegistration: method must be one of {sorted(_METHODS)}, got {method!r}")
    return method


def _estimate_shift(moving: Image, fixed: Image) -> np.ndarray:
    from skimage.registration import phase_cross_correlation

    moving_plane = _representative_plane(moving)
    fixed_plane = _representative_plane(fixed)
    if moving_plane.shape != fixed_plane.shape:
        raise ValueError(
            "ComputeRegistration: moving and fixed representative planes must have matching shape "
            f"(got {moving_plane.shape} vs {fixed_plane.shape})"
        )
    shift, _, _ = phase_cross_correlation(fixed_plane, moving_plane, upsample_factor=10)
    return np.asarray(shift, dtype=np.float64)


def _representative_plane(image: Image) -> np.ndarray:
    _validate_spatial_axes(image)
    data = _image_data(image)
    if data.ndim == 2:
        return data.astype(np.float64, copy=False)

    shape = image.shape if image.shape is not None else tuple(data.shape)
    indexer: list[int | slice] = []
    for axis_name, axis_size in zip(image.axes, shape, strict=True):
        if axis_name in _SPATIAL_AXES:
            indexer.append(slice(None))
        else:
            indexer.append(axis_size // 2)
    return np.asarray(data[tuple(indexer)], dtype=np.float64)


def _matrix_from_shift(shift: np.ndarray, method: str) -> np.ndarray:
    tx = float(shift[1])
    ty = float(shift[0])
    if method == "phase_correlation":
        return np.asarray([[1.0, 0.0, tx], [0.0, 1.0, ty]], dtype=np.float64)

    return np.asarray(
        [
            [1.0, 0.0, tx],
            [0.0, 1.0, ty],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def _image_data(image: Image) -> np.ndarray:
    if image.storage_ref is None and hasattr(image, "_data") and getattr(image, "_data", None) is not None:
        return np.asarray(image._data)  # type: ignore[attr-defined]
    return np.asarray(image.to_memory())


def _validate_spatial_axes(image: Image) -> None:
    if "y" not in image.axes or "x" not in image.axes:
        raise ValueError(f"ComputeRegistration: image must include 'y' and 'x' axes, got {image.axes}")


__all__ = ["ComputeRegistration", "_estimate_shift", "_image_data", "_matrix_from_shift", "_require_single_image"]
