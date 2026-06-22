"""Structured logging configuration (level routing, layered file sink).

#827 introduced the minimal stderr entry point. #1741 extends it:
``configure_logging`` now also installs rotating human-readable file handlers
(via :mod:`scistudio.utils.log_setup`) so backend / engine / event-bus /
websocket logs persist to disk for alpha closed-beta bug reproduction. On-disk
output is a combined ``scistudio-<pid>.log`` plus one file per layer
(``api`` / ``engine`` / ``frontend``), human-readable with correlation/run ids
(owner direction: no JSON files on disk). File logging is best-effort and
degrades to stderr-only when the log directory is unwritable, so it never
crashes a process.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from scistudio.utils.event_logger import install_default_handler


def configure_logging(
    level: str | int = "INFO",
    json_output: bool | None = None,
    *,
    log_dir: str | Path | None = None,
    project_root: str | Path | None = None,
    log_to_file: bool | None = None,
) -> Path | None:
    """Install console + (optional) on-disk logging.

    Parameters
    ----------
    level:
        Root logger level. Accepts standard string names (``"DEBUG"``,
        ``"INFO"``, ...) and integer values.
    json_output:
        Console formatter: ``True`` = one-line JSON; ``None`` = defer to the
        ``SCISTUDIO_LOG_JSON`` environment variable; ``False`` = human-readable.
        Affects the console stream only; on-disk files are always human-readable.
    log_dir / project_root:
        Override / hint for the file-sink directory (see
        :func:`scistudio.utils.log_setup.resolve_log_dir`).
    log_to_file:
        Force file logging on/off; ``None`` defers to ``SCISTUDIO_LOG_TO_FILE``.

    Returns the active log file path, or ``None`` when file logging is disabled
    or unavailable.
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

    # #1741: add the persistent rotating JSON-line file sink. Imported lazily so
    # the simplest stderr-only callers do not pay for it until they opt in.
    from scistudio.utils.log_setup import install_file_logging

    return install_file_logging(
        level=numeric_level,
        log_dir=log_dir,
        project_root=project_root,
        enabled=log_to_file,
    )


__all__ = ["configure_logging"]
