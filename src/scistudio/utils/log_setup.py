"""Persistent file logging, correlation ids, and boundary instrumentation.

#1741. The unified logging *base* for the alpha closed-beta observability work.
It complements two existing modules without duplicating them:

* :mod:`scistudio.utils.event_logger` owns the JSON-line formatter and the
  payload sanitizer (``_JsonLineFormatter`` / ``_sanitize_value``).
* :mod:`scistudio.utils.logging` is the thin ``configure_logging`` entry point.

This module adds the pieces those two intentionally left out of scope in #827:

* on-disk human-readable, per-layer ``.log`` files with rotation + 7-day
  retention (owner direction: no JSON files on disk);
* log-directory resolution (explicit -> ``SCISTUDIO_LOG_DIR`` -> bundled
  ``logs_dir()`` -> ``<project>/.scistudio/logs`` -> user ``logs_dir()``);
* a correlation-id contextvar (surfaced as ``X-Request-ID``) and a run-id
  contextvar (per-run diagnostic logs), injected into every record;
* a :func:`log_call` boundary decorator (sync + async) that emits DEBUG on
  enter (sanitized args) and exit (duration), and ERROR with traceback on
  failure;
* :func:`redact_sensitive` for config payloads.

Apply ``log_call`` at *layer boundaries* (API handlers, engine dispatch,
runners, the frontend ``apiFetch`` wrapper) — the design goal is fine-grained
DEBUG coverage without rewriting every internal function (owner direction
2026-06-21).
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import logging
import os
import time
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, TypeVar

from scistudio.utils.event_logger import _sanitize_value

# ---------------------------------------------------------------------------
# Context variables — correlation id (per request) and run id (per workflow run)
# ---------------------------------------------------------------------------

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("scistudio_request_id", default=None)
run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("scistudio_run_id", default=None)

REQUEST_ID_HEADER = "X-Request-ID"

_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
_DEFAULT_BACKUP_COUNT = 9  # keep ~10 rotated files per process log
_RETENTION_DAYS = 7
_FILE_HANDLER_FLAG = "_scistudio_file_handler"
_LOG_GLOBS = ("scistudio-*.log*", "api-*.log*", "engine-*.log*", "frontend-*.log*", "run-*.log*")

# #1741: physical per-layer routing. Each layer's records go to their own file
# (in addition to the combined scistudio-<pid>.log timeline), so the four layers
# are recorded separately: backend API, engine/engine-events, frontend, and
# desktop. Desktop is the Electron process's own scistudio-desktop.log.
_LAYERS: dict[str, tuple[str, ...]] = {
    "api": ("scistudio.api", "uvicorn"),
    "engine": (
        "scistudio.engine",
        "scistudio.events",
        "scistudio.core",
        "scistudio.blocks",
        "scistudio.workflow",
    ),
    "frontend": ("scistudio.frontend",),
}

_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
)


class ContextFilter(logging.Filter):
    """Inject ``request_id`` / ``run_id`` contextvars into each record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            rid = request_id_var.get()
            if rid is not None:
                record.request_id = rid
        if not hasattr(record, "run_id"):
            run = run_id_var.get()
            if run is not None:
                record.run_id = run
        return True


class _LayerFilter(logging.Filter):
    """Accept only records whose logger belongs to one of *prefixes* (the layer)."""

    def __init__(self, prefixes: tuple[str, ...]) -> None:
        super().__init__()
        self._prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        name = record.name
        return any(name == prefix or name.startswith(prefix + ".") for prefix in self._prefixes)


class HumanFormatter(logging.Formatter):
    """Human-readable on-disk format: ``ts LEVEL logger message [req/run] (+exc)``.

    On-disk logs are human-readable ``.log`` files only (owner direction: no JSON
    files); the request/run correlation ids are appended in brackets (#1741).
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} {record.levelname:<7} {record.name} {record.getMessage()}"
        context: list[str] = []
        request_id = getattr(record, "request_id", None)
        run_id = getattr(record, "run_id", None)
        if request_id:
            context.append(f"req={request_id}")
        if run_id:
            context.append(f"run={run_id}")
        if context:
            line = f"{line}  [{' '.join(context)}]"
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


def redact_sensitive(value: Any) -> Any:
    """Return *value* with sensitive-looking dict fields replaced.

    Keys whose lowercased name contains a sensitive token (``password``,
    ``secret``, ``token``, ``api_key``, ...) have their value replaced with
    ``"<redacted>"``. Recurses into nested dicts/lists. Use this before logging
    config payloads (FR-015).
    """
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for key, val in value.items():
            if any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS):
                out[key] = "<redacted>"
            else:
                out[key] = redact_sensitive(val)
        return out
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    return value


def resolve_log_dir(*, log_dir: str | Path | None = None, project_root: str | Path | None = None) -> Path:
    """Resolve the directory where logs are persisted.

    Priority: explicit *log_dir* -> ``SCISTUDIO_LOG_DIR`` -> bundled
    ``logs_dir()`` (desktop) -> ``<project_root>/.scistudio/logs`` -> user
    ``logs_dir()`` fallback.
    """
    if log_dir:
        return Path(log_dir)
    env_dir = os.environ.get("SCISTUDIO_LOG_DIR")
    if env_dir:
        return Path(env_dir)
    if os.environ.get("SCISTUDIO_BUNDLED"):
        bundled = _user_logs_dir()
        if bundled is not None:
            return bundled
    if project_root:
        return Path(project_root) / ".scistudio" / "logs"
    user_dir = _user_logs_dir()
    if user_dir is not None:
        return user_dir
    return Path.home() / ".scistudio" / "logs"


def _user_logs_dir() -> Path | None:
    # Lazy import keeps the bottom ``utils`` layer free of a top-level
    # dependency edge onto ``scistudio.desktop``.
    try:
        from scistudio.desktop.paths import logs_dir

        return logs_dir()
    except Exception:
        return None


def prune_old_logs(log_dir: Path, *, days: int = _RETENTION_DAYS) -> int:
    """Delete log files older than *days* in *log_dir*; return the count removed."""
    cutoff = time.time() - days * 86400
    removed = 0
    candidates: list[Path] = []
    for pattern in _LOG_GLOBS:
        try:
            candidates.extend(log_dir.glob(pattern))
        except OSError:
            continue
    for path in candidates:
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def _file_logging_enabled(enabled: bool | None) -> bool:
    if enabled is not None:
        return enabled
    raw = os.environ.get("SCISTUDIO_LOG_TO_FILE", "1").strip().lower()
    return raw not in {"0", "false", "no", "off", ""}


def install_file_logging(
    *,
    level: int = logging.INFO,
    log_dir: str | Path | None = None,
    project_root: str | Path | None = None,
    enabled: bool | None = None,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    backup_count: int = _DEFAULT_BACKUP_COUNT,
) -> Path | None:
    """Install rotating human-readable ``.log`` file handlers on the root logger.

    Writes a combined ``scistudio-<pid>.log`` plus one file per layer
    (``api-`` / ``engine-`` / ``frontend-<pid>.log``) so the four layers are
    recorded separately (#1741). On-disk output is human-readable only (owner:
    no JSON files). Idempotent (a second call is a no-op once a SciStudio file
    handler exists) and best-effort: an unwritable directory degrades to
    stderr-only and never raises. Returns the combined log path, or ``None``
    when disabled/failed.
    """
    if not _file_logging_enabled(enabled):
        return None
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, _FILE_HANDLER_FLAG, False):
            return Path(getattr(handler, "baseFilename", "")) or None
    try:
        target_dir = resolve_log_dir(log_dir=log_dir, project_root=project_root)
        target_dir.mkdir(parents=True, exist_ok=True)
        prune_old_logs(target_dir)
        pid = os.getpid()

        def _add_handler(filename: str, layer_prefixes: tuple[str, ...] | None) -> Path:
            path = target_dir / filename
            file_handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(HumanFormatter())
            file_handler.addFilter(ContextFilter())
            if layer_prefixes is not None:
                file_handler.addFilter(_LayerFilter(layer_prefixes))
            setattr(file_handler, _FILE_HANDLER_FLAG, True)
            root.addHandler(file_handler)
            return path

        # Combined cross-layer timeline + one human-readable file per layer.
        combined_log = _add_handler(f"scistudio-{pid}.log", None)
        for layer, prefixes in _LAYERS.items():
            _add_handler(f"{layer}-{pid}.log", prefixes)
        if root.level == logging.NOTSET or root.level > level:
            root.setLevel(level)
        return combined_log
    except Exception:
        logging.getLogger(__name__).warning("file logging unavailable; continuing with stderr only", exc_info=True)
        return None


def _summarize_args(args: tuple[Any, ...], kwargs: dict[str, Any], *, limit: int = 300) -> str:
    parts: list[str] = []
    for index, value in enumerate(args):
        # Skip the bound ``self``/``cls`` of methods to keep lines readable.
        if index == 0 and type(value).__module__.startswith("scistudio"):
            continue
        parts.append(repr(_sanitize_value(value)))
    for key, value in kwargs.items():
        parts.append(f"{key}={_sanitize_value(value)!r}")
    rendered = ", ".join(parts)
    if len(rendered) > limit:
        return rendered[:limit] + "..."
    return rendered


F = TypeVar("F", bound=Callable[..., Any])


def log_call(
    func: F | None = None,
    *,
    logger: logging.Logger | None = None,
    level: int = logging.DEBUG,
    name: str | None = None,
) -> Any:
    """Boundary decorator: DEBUG on enter/exit, ERROR with traceback on failure.

    Works on sync and async callables. Args are sanitized before logging
    (metadata only for heavy scientific payloads). Intended for layer
    boundaries, not every internal function.
    """

    def decorator(target: F) -> F:
        log = logger or logging.getLogger(target.__module__)
        label = name or target.__qualname__

        if asyncio.iscoroutinefunction(target):

            @functools.wraps(target)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                log.log(level, "→ %s(%s)", label, _summarize_args(args, kwargs))
                start = time.perf_counter()
                try:
                    result = await target(*args, **kwargs)
                except Exception:
                    log.error(
                        "✗ %s raised after %.1fms",
                        label,
                        (time.perf_counter() - start) * 1000,
                        exc_info=True,
                    )
                    raise
                log.log(level, "← %s ok %.1fms", label, (time.perf_counter() - start) * 1000)
                return result

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(target)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            log.log(level, "→ %s(%s)", label, _summarize_args(args, kwargs))
            start = time.perf_counter()
            try:
                result = target(*args, **kwargs)
            except Exception:
                log.error(
                    "✗ %s raised after %.1fms",
                    label,
                    (time.perf_counter() - start) * 1000,
                    exc_info=True,
                )
                raise
            log.log(level, "← %s ok %.1fms", label, (time.perf_counter() - start) * 1000)
            return result

        return sync_wrapper  # type: ignore[return-value]

    if func is not None:
        return decorator(func)
    return decorator


__all__ = [
    "REQUEST_ID_HEADER",
    "ContextFilter",
    "HumanFormatter",
    "install_file_logging",
    "log_call",
    "prune_old_logs",
    "redact_sensitive",
    "request_id_var",
    "resolve_log_dir",
    "run_id_var",
]
