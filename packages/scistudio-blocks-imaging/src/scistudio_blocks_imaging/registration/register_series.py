"""RegisterSeries — register a time-series or z-stack to a reference frame.

See ``docs/specs/phase11-imaging-block-spec.md`` §9 T-IMG-029.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio_blocks_imaging.registration.apply_transform import _apply_matrix_to_image
from scistudio_blocks_imaging.registration.compute_registration import (
    _estimate_shift,
    _image_data,
    _matrix_from_shift,
    _require_single_image,
)
from scistudio_blocks_imaging.types import Image

_SERIES_AXES = frozenset({"t", "z"})
_METHODS = frozenset({"phase_correlation", "rigid", "affine"})


class RegisterSeries(ProcessBlock):
    """Register a time-series or z-stack so all frames align to a reference frame."""

    type_name: ClassVar[str] = "imaging.register_series"
    name: ClassVar[str] = "Register Series"
    description: ClassVar[str] = "Register a time-series or z-stack so each frame aligns to a chosen reference frame."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "registration"
    algorithm: ClassVar[str] = "register_series"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="series", accepted_types=[Image], description="Time-series / z-stack Image."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="registered", accepted_types=[Image], description="Aligned series."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "axis": {"type": "string", "enum": ["t", "z"], "default": "t"},
            "reference_frame": {"type": "integer", "default": 0, "minimum": 0},
            "method": {
                "type": "string",
                "enum": ["phase_correlation", "rigid", "affine"],
                "default": "phase_correlation",
            },
        },
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        series = _require_single_image(inputs.get("series"), "series")
        registered = self.process_item(series, config)
        return {"registered": Collection(items=cast(list[DataObject], [registered]), item_type=Image)}

    def process_item(
        self,
        item: Image,
        config: BlockConfig,
        state: Any = None,
    ) -> Image:
        axis = str(config.get("axis", "t"))
        if axis not in _SERIES_AXES:
            raise ValueError(f"RegisterSeries: axis must be one of {sorted(_SERIES_AXES)}, got {axis!r}")
        if axis not in item.axes:
            raise ValueError(f"RegisterSeries: axis {axis!r} not present in image axes {item.axes}")

        method = str(config.get("method", "phase_correlation"))
        if method not in _METHODS:
            raise ValueError(f"RegisterSeries: method must be one of {sorted(_METHODS)}, got {method!r}")

        data = _image_data(item)
        axis_index = item.axes.index(axis)
        axis_length = data.shape[axis_index]
        reference_frame = int(config.get("reference_frame", 0))
        if reference_frame < 0 or reference_frame >= axis_length:
            raise ValueError(
                f"RegisterSeries: reference_frame must be in [0, {axis_length - 1}], got {reference_frame}"
            )

        frame_axes = [name for name in item.axes if name != axis]
        reference_data = np.take(data, reference_frame, axis=axis_index)
        reference_image = _frame_image(item, np.asarray(reference_data), frame_axes)

        registered_frames: list[np.ndarray] = []
        for index in range(axis_length):
            frame_data = np.take(data, index, axis=axis_index)
            if index == reference_frame:
                registered_frames.append(np.asarray(frame_data))
                continue

            frame_image = _frame_image(item, np.asarray(frame_data), frame_axes)
            shift = _estimate_shift(frame_image, reference_image)
            matrix = _matrix_from_shift(shift, method)
            registered = _apply_matrix_to_image(frame_image, matrix, interpolation="nearest")
            registered_frames.append(np.asarray(_image_data(registered)))

        stacked = np.stack(registered_frames, axis=axis_index)
        result = Image(
            axes=list(item.axes),
            shape=tuple(stacked.shape),
            dtype=stacked.dtype,
            framework=item.framework.derive(),
            meta=item.meta,
            user=dict(item.user),
            storage_ref=None,
        )
        result._data = stacked  # type: ignore[attr-defined]
        return result


def _frame_image(source: Image, data: np.ndarray, axes: list[str]) -> Image:
    image = Image(
        axes=axes,
        shape=tuple(data.shape),
        dtype=data.dtype,
        framework=source.framework.derive(),
        meta=source.meta,
        user=dict(source.user),
        storage_ref=None,
    )
    image._data = data  # type: ignore[attr-defined]
    return image


__all__ = ["RegisterSeries"]
