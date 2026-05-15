"""Deconvolve — Phase 12 placeholder block (T-IMG-011).

Skeleton (Sprint C continuation A). The class ships in 0.1.0 so the
palette has the entry, but the body raises ``NotImplementedError`` —
the actual deconvolution algorithms (Richardson-Lucy, Wiener,
Tikhonov) are deferred to Phase 12. See
``docs/specs/phase11-imaging-block-spec.md`` §9 T-IMG-011.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy_blocks_imaging.types import Image


class Deconvolve(ProcessBlock):
    """PLACEHOLDER for Phase 12 deconvolution.

    Ships in 0.1.0 so the palette has the entry. Calling
    :meth:`process_item` raises ``NotImplementedError`` with a
    Phase 12 message.
    """

    type_name: ClassVar[str] = "imaging.deconvolve"
    name: ClassVar[str] = "Deconvolve"
    description: ClassVar[str] = "Image deconvolution (Phase 12 placeholder)."
    subcategory: ClassVar[str] = "preprocess"
    algorithm: ClassVar[str] = "deconvolve"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["richardson_lucy", "wiener", "tikhonov"],
                "default": "richardson_lucy",
            },
            "iterations": {"type": "integer", "default": 30},
        },
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        """Deconvolve the image (Phase 12 — not implemented)."""
        # TODO: T-IMG-011 — implement deconvolution algorithms (Richardson-Lucy, Wiener, Tikhonov) for Phase 12.
        raise NotImplementedError(
            "T-IMG-011 Deconvolve is planned for Phase 12. "
            "Currently a palette placeholder; see "
            "docs/specs/phase11-imaging-block-spec.md §9 T-IMG-011."
        )
