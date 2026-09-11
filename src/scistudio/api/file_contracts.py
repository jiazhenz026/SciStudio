"""Shared API file-editing contract constants."""

from __future__ import annotations

FILE_CHANGED_EVENT_TYPE: str = "file.changed"
"""File-tab state-change websocket event type."""
# Development references: ADR-045.

FILE_ENTITY_CLASS: str = "file"
"""Entity class for project-file state-version payloads."""
# Development references: ADR-045.

ADR036_FILE_ALLOWLIST: tuple[str, ...] = (
    ".py",
    ".r",
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".csv",
    ".log",
)
"""Allowed file extensions for file GET/PUT and file events."""
# Development references: ADR-036, ADR-045.
