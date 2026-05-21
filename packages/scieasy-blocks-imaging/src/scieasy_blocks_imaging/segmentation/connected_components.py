"""ConnectedComponents - label connected components in a binary :class:`Mask`."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.array import Array
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy_blocks_imaging.types import Label, Mask


class ConnectedComponents(ProcessBlock):
    """Label connected foreground components of a :class:`Mask` into :class:`Label`."""

    type_name: ClassVar[str] = "imaging.connected_components"
    name: ClassVar[str] = "Connected Components"
    description: ClassVar[str] = "Label connected foreground components in a binary Mask, returning a Label."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "segmentation"
    algorithm: ClassVar[str] = "connected_components"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="mask",
            accepted_types=[Mask],
            description="Binary mask whose foreground will be labelled.",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="label",
            accepted_types=[Label],
            description="Label image with raster slot populated.",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "connectivity": {
                "type": "integer",
                "enum": [1, 2],
                "default": 1,
                "description": "1 = 4-connectivity (2D) / face; 2 = 8-connectivity / corner",
            },
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Override Tier 1 run so the output collection carries ``Label`` items."""
        masks = _coerce_masks(inputs.get("mask"))
        labels = [cast(Label, self._auto_flush(self.process_item(mask, config))) for mask in masks]
        return {"label": Collection(items=cast(list[DataObject], labels), item_type=Label)}

    def process_item(
        self,
        item: Mask,
        config: BlockConfig,
        state: Any = None,
    ) -> Label:
        """Run skimage connected-component labelling and wrap as :class:`Label`."""
        from skimage.measure import label as cc_label

        connectivity = int(config.get("connectivity", 1))
        if connectivity not in (1, 2):
            raise ValueError(f"ConnectedComponents: connectivity must be 1 or 2, got {connectivity}")

        labels = np.asarray(
            cc_label(np.asarray(item.to_memory(), dtype=bool), connectivity=connectivity), dtype=np.int32
        )
        raster = Array(axes=list(item.axes), shape=labels.shape, dtype=labels.dtype)
        raster._data = labels  # type: ignore[attr-defined]
        # ADR-043 / spec FR-009 Mode C: Label output is shape-aligned with
        # the input Mask (same axes / raster shape), so ``ome`` MUST be
        # carried from the source Mask's Image.Meta into the rebuilt
        # ``Label.Meta``.
        return Label(
            slots={"raster": raster},
            framework=item.framework.derive(),
            meta=Label.Meta(
                source_file=getattr(item.meta, "source_file", None),
                n_objects=int(labels.max()) if labels.size else 0,
                ome=getattr(item.meta, "ome", None),
            ),
            user=dict(item.user),
        )


def _coerce_masks(value: Collection | Mask | None) -> list[Mask]:
    if value is None:
        raise ValueError("ConnectedComponents: missing required 'mask' input")
    if isinstance(value, Mask):
        return [value]
    if not isinstance(value, Collection):
        raise ValueError(f"ConnectedComponents: expected Mask or Collection[Mask], got {type(value).__name__}")

    masks: list[Mask] = []
    for item in value:
        if not isinstance(item, Mask):
            raise ValueError(f"ConnectedComponents: mask collection must contain Mask items, got {type(item).__name__}")
        masks.append(item)
    return masks


__all__ = ["ConnectedComponents"]
