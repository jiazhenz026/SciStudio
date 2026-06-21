"""Structured stdlib-logging subscriber for the engine EventBus.

ADR-018 / #827: the engine's :class:`scistudio.engine.events.EventBus`
publishes ~18 distinct event types (see :mod:`scistudio.engine.events`).
:func:`install_event_logger` subscribes one sync callback per event type and
turns every emitted event into a structured log record (``INFO`` level on the
``scistudio.events`` logger). It is a pure observability sink — nothing reads
the records back programmatically; they flow into whatever stdlib logging
handler the application installed (see
:func:`scistudio.utils.event_logger.install_default_handler`).

Round-4 no-cycles: the engine-coupled half of the former
``scistudio.utils.event_logger`` lives here, in ``engine``, because it imports
``scistudio.engine.events``. Hosting it in ``utils`` made the bottom ``utils``
layer import ``engine`` (a layering inversion). The generic, engine-agnostic
log helpers (``_sanitize_data``, the JSON-line formatter, and
``install_default_handler``) stay in ``scistudio.utils.event_logger``; this
module reuses them via the natural ``engine -> utils`` direction.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scistudio.engine import events as _events_module
from scistudio.utils.event_logger import LOGGER_NAME, _sanitize_data

if TYPE_CHECKING:
    from scistudio.engine.events import EngineEvent, EventBus

_INSTALL_SENTINEL = "_scistudio_event_logger_installed"
"""Attribute set on an :class:`EventBus` once the logger is installed.

Used by :func:`install_event_logger` to keep the install idempotent —
calling it twice on the same bus does not double-subscribe.
"""


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


def install_event_logger(event_bus: EventBus, *, level: int = logging.INFO) -> bool:
    """Subscribe a structured logger to every event type on *event_bus*.

    Returns ``True`` if the logger was installed by this call, ``False``
    when the bus already had a logger installed (idempotent re-entry).

    The logger writes one record per event on the
    ``scistudio.events`` stdlib logger at *level* (default ``INFO``).
    The handler is up to the application — calling
    :func:`scistudio.utils.event_logger.install_default_handler` once at
    process start is the simplest way to route records to stderr.

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


__all__ = [
    "install_event_logger",
]
