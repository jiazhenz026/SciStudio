"""Spectroscopy block group aggregation.

``BLOCKS`` is the concatenation of every block-group module's ``BLOCKS`` list,
in spec section order. The package ``__init__`` returns ``list(BLOCKS)`` from
``get_blocks()``.
"""

from __future__ import annotations

from scistudio_blocks_spectroscopy.blocks import (
    feature_extraction,
    library_matching,
    peak_fitting,
    preprocessing,
    reference_correction,
    unmixing,
    utilities,
)

BLOCKS: list[type] = [
    *utilities.BLOCKS,
    *preprocessing.BLOCKS,
    *feature_extraction.BLOCKS,
    *peak_fitting.BLOCKS,
    *reference_correction.BLOCKS,
    *library_matching.BLOCKS,
    *unmixing.BLOCKS,
]

__all__ = ["BLOCKS"]
