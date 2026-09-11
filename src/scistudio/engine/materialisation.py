"""Compatibility exports for file materialisation helpers."""
# Maintainer context (kept outside generated API documentation):
# Compatibility exports for file materialisation helpers.
#
# ADR-043 moves the canonical implementation to
# ``scistudio.blocks.io.materialisation`` so ``scistudio.blocks`` does not depend on
# ``scistudio.engine``. Existing imports from this module remain supported.
# Development references: ADR-043.

from __future__ import annotations

from scistudio.blocks.io.materialisation import materialise_to_file, reconstruct_from_file

__all__ = ["materialise_to_file", "reconstruct_from_file"]
