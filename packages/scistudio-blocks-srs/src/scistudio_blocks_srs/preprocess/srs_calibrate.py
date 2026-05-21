"""SRSCalibrate - digitizer inversion + ``Image`` to ``SRSImage`` conversion."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np
from scistudio_blocks_imaging.types import Image  # type: ignore[import-not-found]

from scistudio.blocks.base.block import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.utils.constraints import has_axes
from scistudio_blocks_srs.types import SRSImage


class SRSCalibrate(ProcessBlock):
    """Invert the digitizer formula and re-type ``Image`` to ``SRSImage``."""

    name: ClassVar[str] = "SRS Calibrate"
    type_name: ClassVar[str] = "srs.calibrate"
    description: ClassVar[str] = (
        "Invert digitizer formula and convert Image to SRSImage. Entry point of the SRS preprocessing pipeline."
    )
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "digitizer_inversion"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="image",
            accepted_types=[Image],
            description="Raw digitizer-counts Image with y/x/lambda axes.",
            constraint=has_axes("y", "x", "lambda"),
            constraint_description="image must carry y/x/lambda axes",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="srs_image",
            accepted_types=[SRSImage],
            description="Calibrated SRSImage with digitizer meta populated.",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "scale": {"type": "number", "default": 1.0, "ui_priority": 0},
            "offset": {"type": "number", "default": 0.0, "ui_priority": 1},
            "bit_depth": {"type": "integer", "default": 4096, "minimum": 1, "ui_priority": 10},
            "voltage_range": {"type": "number", "default": 10.0, "ui_priority": 11},
            "wavenumbers_cm1": {
                "type": ["array", "null"],
                "items": {"type": "number"},
                "default": None,
                "ui_priority": 12,
            },
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Override Tier 1 run so the output collection carries ``SRSImage`` items."""
        images = _coerce_images(inputs.get("image"))
        outputs: list[SRSImage] = [cast(SRSImage, self._auto_flush(self.process_item(item, config))) for item in images]
        return {"srs_image": Collection(items=cast(list[DataObject], outputs), item_type=SRSImage)}

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> SRSImage:
        """Apply digitizer inversion and return a typed :class:`SRSImage`."""
        if isinstance(item, SRSImage):
            raise ValueError("SRSCalibrate: got SRSImage input; chained two SRSCalibrate blocks?")
        if item.meta is not None and getattr(item.meta, "digitizer_bit_depth", None) is not None:
            raise ValueError("SRSCalibrate: input image already has digitizer fields populated")

        bit_depth = int(config.get("bit_depth", 4096))
        voltage_range = float(config.get("voltage_range", 10.0))
        offset = float(config.get("offset", 0.0))
        scale = float(config.get("scale", 1.0))
        wavenumbers_cm1 = config.get("wavenumbers_cm1")

        if scale == 0.0:
            raise ValueError("SRSCalibrate: scale must be non-zero")

        pixel = np.asarray(item.to_memory(), dtype=np.float64)
        signal = ((pixel / bit_depth) * voltage_range - offset) / scale
        signal = np.asarray(signal, dtype=np.float32)

        if wavenumbers_cm1 is not None:
            lambda_axis = item.axes.index("lambda")
            if item.shape is None or len(wavenumbers_cm1) != item.shape[lambda_axis]:
                raise ValueError("SRSCalibrate: len(wavenumbers_cm1) must match the lambda axis size")

        old_meta = item.meta.model_dump() if item.meta is not None else {}
        new_meta = SRSImage.Meta(
            **old_meta,
            wavenumbers_cm1=list(wavenumbers_cm1) if wavenumbers_cm1 is not None else None,
            digitizer_bit_depth=bit_depth,
            digitizer_voltage_range=voltage_range,
            digitizer_offset=offset,
            digitizer_scale=scale,
        )
        out = SRSImage(
            axes=list(item.axes),
            shape=signal.shape,
            dtype=signal.dtype,
            chunk_shape=item.chunk_shape,
            framework=item.framework.derive(),
            meta=new_meta,
            user=dict(item.user),
            storage_ref=None,
        )
        out._data = signal  # type: ignore[attr-defined]
        return out


def _coerce_images(value: Collection | Image | None) -> list[Image]:
    if value is None:
        raise ValueError("SRSCalibrate: missing required 'image' input")
    if isinstance(value, Image):
        return [value]
    if not isinstance(value, Collection):
        raise ValueError(f"SRSCalibrate: expected Image or Collection[Image], got {type(value).__name__}")

    images: list[Image] = []
    for item in value:
        if not isinstance(item, Image):
            raise ValueError(f"SRSCalibrate: image collection must contain Image items, got {type(item).__name__}")
        images.append(item)
    if not images:
        raise ValueError("SRSCalibrate: image collection is empty")
    return images


__all__ = ["SRSCalibrate"]
