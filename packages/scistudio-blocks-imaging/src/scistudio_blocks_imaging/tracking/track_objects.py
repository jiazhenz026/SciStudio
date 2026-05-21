"""TrackObjects — Phase 12 placeholder for object tracking across time.

T-IMG-023. The block is registered in the palette so users can discover
it, but ``process_item`` raises ``NotImplementedError`` until Phase 12
ships actual tracking algorithms (nearest-neighbour, trackpy, btrack).
See ``docs/specs/phase11-imaging-block-spec.md`` §9 T-IMG-023.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio_blocks_imaging.types import Label


class TrackObjects(ProcessBlock):
    """PLACEHOLDER for Phase 12 object tracking across time."""

    type_name: ClassVar[str] = "imaging.track_objects"
    name: ClassVar[str] = "Track Objects"
    description: ClassVar[str] = (
        "Phase 12 placeholder: link Label objects across time. Currently raises NotImplementedError."
    )
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "tracking"
    algorithm: ClassVar[str] = "track_objects"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="labels", accepted_types=[Label], description="Per-frame Label images (time-resolved)."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="tracks", accepted_types=[Label], description="Label image with track IDs."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["nearest_neighbour", "trackpy", "btrack"],
                "default": "nearest_neighbour",
            },
            "max_distance": {"type": "number", "default": 50.0, "minimum": 0.0},
        },
    }

    def process_item(self, item: Label, config: BlockConfig, state: Any = None) -> Label:
        # TODO: T-IMG-023 — implement object tracking across time (nearest-neighbour, trackpy, btrack backends) for Phase 12.
        raise NotImplementedError(
            "T-IMG-023: TrackObjects is planned for Phase 12 (skeleton continuation B). "
            "See docs/specs/phase11-imaging-block-spec.md §9 T-IMG-023."
        )
