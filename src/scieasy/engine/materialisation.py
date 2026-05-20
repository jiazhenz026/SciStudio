"""Compatibility exports for file materialisation helpers.

ADR-043 moves the canonical implementation to
``scieasy.blocks.io.materialisation`` so ``scieasy.blocks`` does not depend on
``scieasy.engine``. Existing imports from this module remain supported.
"""

from __future__ import annotations

from scieasy.blocks.io.materialisation import materialise_to_file, reconstruct_from_file

__all__ = ["materialise_to_file", "reconstruct_from_file"]
