"""Structured logging configuration (JSON formatter, level routing).

#827: replaces the original ``NotImplementedError`` stub with a small
adapter on top of :func:`scistudio.utils.event_logger.install_default_handler`.
The function stays intentionally small — its only job is to make
``configure_logging("INFO")`` work as the simplest entry point for a
process that wants engine events on stderr. Anything more complex
(rotating files, JSON shipping, per-module level routing) should be
configured by the application itself.

Out of scope per #827: refactoring the 30 ``logging.getLogger(__name__)``
callers across the codebase to use a unified logger, persistent
on-disk event archive, log-shipping infrastructure.
"""

from __future__ import annotations

import logging
import os

from scistudio.utils.event_logger import install_default_handler


def configure_logging(level: str = "INFO", json_output: bool | None = None) -> None:
    """Install a minimal stdlib-logging configuration.

    Parameters
    ----------
    level:
        Root logger level. Accepts both the standard string names
        (``"DEBUG"``, ``"INFO"``, ...) and integer values for
        symmetry with :mod:`logging`.
    json_output:
        When ``True`` install a one-line JSON formatter; when ``None``
        defer to the ``SCISTUDIO_LOG_JSON`` environment variable (any
        truthy value enables JSON); otherwise install the default
        human-readable formatter.
    """
    if isinstance(level, str):
        numeric_level = logging.getLevelName(level.upper())
        if not isinstance(numeric_level, int):
            raise ValueError(f"Unknown log level: {level!r}")
    else:
        numeric_level = int(level)

    if json_output is None:
        env = os.environ.get("SCISTUDIO_LOG_JSON", "").strip().lower()
        json_output = env in {"1", "true", "yes", "on"}

    install_default_handler(json_output=bool(json_output), level=numeric_level)


__all__ = ["configure_logging"]
