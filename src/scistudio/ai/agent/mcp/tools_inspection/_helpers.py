"""Shared constants + helpers for the ``tools_inspection`` sub-package.

ADR-040 §3.1 FastMCP migration. Extracted from the original single-file
``tools_inspection.py`` (#1431, umbrella #1427) so each sub-module stays
below the 750 LOC god-file threshold. No behavior change.

Public surface preserved at ``scistudio.ai.agent.mcp.tools_inspection``
via the package ``__init__`` re-exports.
"""

from __future__ import annotations

from typing import Any

from scistudio.core.storage.ref import StorageReference

_LOCK_TIMEOUT_SECONDS: float = 10.0
"""ADR-033 OQ7 file lock timeout."""

_MAX_PREVIEW_BYTES: int = 8 * 1024 * 1024
"""8 MiB hard cap (Phase 2 audit)."""

_THUMBNAIL_MAX_DIM: int = 256
_DATAFRAME_PREVIEW_ROWS: int = 100
_SERIES_PREVIEW_POINTS: int = 200
_TEXT_PREVIEW_CHARS: int = 4096
_BLOCK_LOG_TRUNCATE_BYTES: int = 16 * 1024  # 16 KiB per stream


def _ref_from_dict(ref: dict[str, Any]) -> StorageReference:
    """Build a :class:`StorageReference` from a JSON-safe dict envelope."""
    return StorageReference(
        backend=str(ref.get("backend", "filesystem")),
        path=str(ref.get("path", "")),
        format=ref.get("format"),
        metadata=ref.get("metadata"),
    )


__all__ = [
    "_BLOCK_LOG_TRUNCATE_BYTES",
    "_DATAFRAME_PREVIEW_ROWS",
    "_LOCK_TIMEOUT_SECONDS",
    "_MAX_PREVIEW_BYTES",
    "_SERIES_PREVIEW_POINTS",
    "_TEXT_PREVIEW_CHARS",
    "_THUMBNAIL_MAX_DIM",
    "_ref_from_dict",
]
