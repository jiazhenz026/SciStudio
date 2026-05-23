"""Structured stdlib-logging subscriber for the engine EventBus.

ADR-018 / #827: the engine's :class:`scistudio.engine.events.EventBus`
publishes ~18 distinct event types (see :mod:`scistudio.engine.events`).
Prior to this helper only seven of them were observed by
``api.runtime.ApiRuntime._bind_event_logging`` and the observations went
only to the in-memory :class:`api.runtime.LogBroadcaster` (the
WS-frontend channel). There was no persistent or stdlib-logging audit
trail of engine activity.

This module fills the gap by subscribing a single structured logger to
every event constant defined in :mod:`scistudio.engine.events`. Each
emitted event becomes one log record at ``INFO`` level on the
``scistudio.events`` logger:

* default (human-readable) format::

    block_running block_id=load_csv_1 workflow_id=wf-abc data={}

* JSON-line format (set ``SCISTUDIO_LOG_JSON=1`` before configuring
  logging, or pass ``json_output=True`` to :func:`configure_logging`)::

    {"event_type":"block_running","block_id":"load_csv_1",
     "workflow_id":"wf-abc","data":{}}

Engine internals are unchanged — the helper is a pure subscriber.
The existing ``ApiRuntime._bind_event_logging`` callback for the WS
broadcaster continues to fire independently.

Out of scope per #827: API HTTP access middleware, frontend
``console.*`` upload, persistent on-disk event archive, refactor of
ad-hoc ``logging.getLogger(__name__)`` callers across the 30 module
sites. See the issue's "Out of scope" section.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

from scistudio.engine import events as _events_module

if TYPE_CHECKING:
    from scistudio.engine.events import EngineEvent, EventBus

LOGGER_NAME = "scistudio.events"
"""Logger name for the engine event audit trail."""

_INSTALL_SENTINEL = "_scistudio_event_logger_installed"
"""Attribute set on an :class:`EventBus` once the logger is installed.

Used by :func:`install_event_logger` to keep the install idempotent —
calling it twice on the same bus does not double-subscribe.
"""

_PAYLOAD_TRUNCATION_LIMIT = 1024
"""Per-value truncation limit in stringified bytes (1 KB)."""


def _all_event_types() -> list[str]:
    """Return every event-type string constant defined in ``engine.events``.

    Discovery is dynamic so that new event types added in
    :mod:`scistudio.engine.events` are picked up automatically without
    requiring a parallel update here. A module-level attribute is
    considered an event-type constant when:

    1. Its name is upper-snake-case (``A-Z``, ``0-9``, ``_``).
    2. Its value is a non-empty ``str``.
    3. It is not a private helper (does not start with ``_``).
    """
    discovered: list[str] = []
    for name, value in vars(_events_module).items():
        if name.startswith("_"):
            continue
        if not isinstance(value, str) or not value:
            continue
        if not name.isupper() or not all(c.isalnum() or c == "_" for c in name):
            continue
        discovered.append(value)
    # De-duplicate while preserving discovery order so the install order
    # is deterministic on Python 3.7+ insertion-ordered dict semantics.
    seen: set[str] = set()
    unique: list[str] = []
    for event_type in discovered:
        if event_type in seen:
            continue
        seen.add(event_type)
        unique.append(event_type)
    return unique


def _sanitize_value(value: Any) -> Any:
    """Return a logger-safe rendering of *value*.

    Large stringified payloads are truncated; opaque scientific
    payloads (numpy arrays, pyarrow Tables) are replaced with a type
    marker so log lines never blow up on real workflow outputs.
    """
    type_name = type(value).__name__
    module = type(value).__module__

    # Drop numpy arrays / pyarrow Tables / pandas DataFrames entirely.
    # We probe by module so we don't pull these heavy deps in just to
    # check ``isinstance``.
    if module.startswith("numpy") or module.startswith("pyarrow") or module.startswith("pandas"):
        shape = getattr(value, "shape", None)
        if shape is not None:
            return f"<{type_name} shape={tuple(shape)!r}>"
        return f"<{type_name}>"

    if isinstance(value, dict):
        return {str(k): _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        rendered = [_sanitize_value(item) for item in value]
        return rendered if isinstance(value, list) else tuple(rendered)
    if isinstance(value, (str, int, float, bool)) or value is None:
        # Truncate long strings only — small numeric values pass through
        # untouched so JSON output stays human-readable.
        if isinstance(value, str) and len(value) > _PAYLOAD_TRUNCATION_LIMIT:
            return f"<truncated len={len(value)}>"
        return value

    # Fallback: stringify and truncate.
    rendered = repr(value)
    if len(rendered) > _PAYLOAD_TRUNCATION_LIMIT:
        return f"<truncated len={len(rendered)}>"
    return rendered


def _sanitize_data(data: Any) -> Any:
    """Public-facing wrapper to sanitize ``EngineEvent.data``."""
    if isinstance(data, dict):
        return {str(k): _sanitize_value(v) for k, v in data.items()}
    return _sanitize_value(data)


def install_event_logger(event_bus: EventBus, *, level: int = logging.INFO) -> bool:
    """Subscribe a structured logger to every event type on *event_bus*.

    Returns ``True`` if the logger was installed by this call, ``False``
    when the bus already had a logger installed (idempotent re-entry).

    The logger writes one record per event on the
    ``scistudio.events`` stdlib logger at *level* (default ``INFO``).
    The handler is up to the application — calling
    :func:`configure_logging` once at process start is the simplest
    way to route records to stderr.

    The helper subscribes one sync callback per event type discovered
    from :mod:`scistudio.engine.events`. ``EventBus.emit`` accepts
    sync callbacks (see :meth:`EventBus.emit`) so no async wrapper is
    required.
    """
    if getattr(event_bus, _INSTALL_SENTINEL, False):
        return False

    audit_logger = logging.getLogger(LOGGER_NAME)
    audit_logger.setLevel(level)

    def _log_event(event: EngineEvent) -> None:
        # Sanitize the payload before constructing the log record so a
        # heavy data dict never gets serialised by the default formatter.
        sanitized = _sanitize_data(getattr(event, "data", {}) or {})
        workflow_id = sanitized.get("workflow_id") if isinstance(sanitized, dict) else None

        # ``extra`` ships the structured fields through to the JSON
        # formatter without altering the human-readable message.
        audit_logger.log(
            level,
            "%s block_id=%s workflow_id=%s data=%s",
            event.event_type,
            event.block_id,
            workflow_id,
            sanitized,
            extra={
                "event_type": event.event_type,
                "block_id": event.block_id,
                "workflow_id": workflow_id,
                "event_data": sanitized,
            },
        )

    for event_type in _all_event_types():
        event_bus.subscribe(event_type, _log_event)

    # Mark the bus so a second install is a silent no-op.
    setattr(event_bus, _INSTALL_SENTINEL, True)
    return True


class _JsonLineFormatter(logging.Formatter):
    """Render an :class:`logging.LogRecord` as a single JSON line.

    Recognises the ``event_type`` / ``block_id`` / ``workflow_id`` /
    ``event_data`` extras set by :func:`install_event_logger` and
    promotes them to top-level keys for downstream log shippers.
    """

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload: dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("event_type", "block_id", "workflow_id", "event_data"):
            if hasattr(record, key):
                payload[key if key != "event_data" else "data"] = getattr(record, key)
        return json.dumps(payload, default=str)


def install_default_handler(*, json_output: bool = False, level: int = logging.INFO) -> None:
    """Install a single ``StreamHandler`` on the root logger if absent.

    The check is intentionally permissive — the root logger may already
    have handlers from a test runner, application entry point, or
    Jupyter; we do not stack a second handler on top in that case. To
    force an additional handler, configure the logger explicitly.
    """
    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    if json_output:
        handler.setFormatter(_JsonLineFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)


__all__ = [
    "LOGGER_NAME",
    "install_default_handler",
    "install_event_logger",
]
