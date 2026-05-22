"""Shared API file-editing contract constants."""

from __future__ import annotations

FILE_CHANGED_EVENT_TYPE: str = "file.changed"
"""ADR-045 file-tab state-change websocket event type."""

FILE_ENTITY_CLASS: str = "file"
"""ADR-045 entity class for project-file state-version payloads."""

ADR036_FILE_ALLOWLIST: tuple[str, ...] = (
    ".py",
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".csv",
    ".log",
)
"""Allowed file extensions for ADR-036 file GET/PUT and ADR-045 file events."""
