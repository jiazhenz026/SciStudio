"""Engine-agnostic helpers for the ``scistudio.events`` audit log.

ADR-018 / #827 introduced a structured audit trail of engine activity on the
``scistudio.events`` stdlib logger. This module holds the **engine-agnostic**
half of that machinery:

* :func:`_sanitize_data` / :func:`_sanitize_value` — render arbitrary event
  payloads logger-safe (truncate large strings, drop heavy numpy/pyarrow/pandas
  payloads behind a type marker);
* :class:`_JsonLineFormatter` — render a :class:`logging.LogRecord` as a single
  JSON line, promoting the ``event_type`` / ``block_id`` / ``workflow_id`` /
  ``event_data`` extras to top-level keys;
* :func:`install_default_handler` — install a default ``StreamHandler`` (plain
  or JSON) on the root logger.

Each emitted engine event becomes one ``INFO`` record on the
``scistudio.events`` logger:

* default (human-readable) format::

    block_running block_id=load_csv_1 workflow_id=wf-abc data={}

* JSON-line format::

    {"event_type":"block_running","block_id":"load_csv_1",
     "workflow_id":"wf-abc","data":{}}

Round-4 no-cycles: the engine-coupled subscriber (``install_event_logger``,
which imports :mod:`scistudio.engine.events`) moved to
:mod:`scistudio.engine.event_logger` so this bottom ``utils`` layer no longer
imports ``engine``. The records remain a pure observability sink; nothing reads
them back programmatically.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

LOGGER_NAME = "scistudio.events"
"""Logger name for the engine event audit trail."""

_PAYLOAD_TRUNCATION_LIMIT = 1024
"""Per-value truncation limit in stringified bytes (1 KB)."""


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
        items = [_sanitize_value(item) for item in value]
        return items if isinstance(value, list) else tuple(items)
    if isinstance(value, (str, int, float, bool)) or value is None:
        # Truncate long strings only — small numeric values pass through
        # untouched so JSON output stays human-readable.
        if isinstance(value, str) and len(value) > _PAYLOAD_TRUNCATION_LIMIT:
            return f"<truncated len={len(value)}>"
        return value

    # Fallback: stringify and truncate.
    rendered_repr = repr(value)
    if len(rendered_repr) > _PAYLOAD_TRUNCATION_LIMIT:
        return f"<truncated len={len(rendered_repr)}>"
    return rendered_repr


def _sanitize_data(data: Any) -> Any:
    """Public-facing wrapper to sanitize ``EngineEvent.data``."""
    if isinstance(data, dict):
        return {str(k): _sanitize_value(v) for k, v in data.items()}
    return _sanitize_value(data)


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
]
