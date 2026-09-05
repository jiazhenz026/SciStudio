"""Shared API file-editing contract constants."""

from __future__ import annotations

FILE_CHANGED_EVENT_TYPE: str = "file.changed"
"""ADR-045 file-tab state-change websocket event type."""

FILE_ENTITY_CLASS: str = "file"
"""ADR-045 entity class for project-file state-version payloads."""

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
    # ADR-054 spec 1 FR-032: a panel's entry document is ``index.html``, and the
    # reload trigger must fire for panel files — including ones the agent writes
    # on the person's behalf, not only ones the person edits directly. Without
    # this entry ``_ProjectFileHandler._entity_id_for`` filtered every panel
    # document out, so a panel that changed on disk produced no signal at all
    # (``panel.json`` beside it did fire, which made the gap read as a flaky
    # reload rather than as a missing extension). The same entry is what lets
    # ``PUT /api/projects/{id}/file`` accept the person's own save of a panel
    # document instead of answering 415.
    ".html",
)
"""Allowed file extensions for ADR-036 file GET/PUT and ADR-045 file events."""
