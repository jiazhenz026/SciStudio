"""Per-run diagnostic log files (#1741).

Each workflow run gets its own ``run-<run_id>.log`` (JSON-line) under the
resolved log directory, capturing the engine events, worker stdout/stderr, and
tracebacks emitted while that run executes — exactly the artifact a developer
needs to reproduce a tester's failing run offline.

Implemented as a root-logger ``FileHandler`` scoped by the ``run_id`` contextvar
(:data:`scistudio.utils.log_setup.run_id_var`) so concurrent runs never
cross-contaminate. Best-effort: a failure to open the file degrades to the
process-level log, never crashing the run.
"""

from __future__ import annotations

import contextlib
import logging
import re
from collections.abc import Iterator
from pathlib import Path

from scistudio.utils.log_setup import ContextFilter, HumanFormatter, resolve_log_dir, run_id_var

logger = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_run_id(run_id: object) -> str:
    return _UNSAFE.sub("_", str(run_id))[:128] or "run"


class _RunFilter(logging.Filter):
    """Accept only records emitted within the matching run's context."""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self._run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        current = getattr(record, "run_id", None) or run_id_var.get()
        return current == self._run_id


def attach_run_logger(
    run_id: object,
    *,
    project_root: str | Path | None = None,
    level: int = logging.NOTSET,
) -> logging.Handler | None:
    """Install a per-run file handler on the root logger; return it (or None)."""
    try:
        log_dir = resolve_log_dir(project_root=project_root)
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"run-{_safe_run_id(run_id)}.log"
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setLevel(level)
        handler.setFormatter(HumanFormatter())
        handler.addFilter(ContextFilter())
        handler.addFilter(_RunFilter(str(run_id)))
        logging.getLogger().addHandler(handler)
        return handler
    except Exception:
        logger.warning("per-run logging unavailable for run %s", run_id, exc_info=True)
        return None


def detach_run_logger(handler: logging.Handler | None) -> None:
    """Remove and close a per-run handler (no-op for ``None``)."""
    if handler is None:
        return
    try:
        logging.getLogger().removeHandler(handler)
        handler.close()
    except Exception:
        pass


@contextlib.contextmanager
def run_log_context(
    run_id: object,
    *,
    project_root: str | Path | None = None,
    level: int = logging.NOTSET,
) -> Iterator[Path | None]:
    """Set the run-id contextvar and attach a per-run log handler for the block.

    Wrap the body that executes a run (engine dispatch / worker calls) so every
    record emitted in that context is correlated and copied into the per-run
    file. Returns the run-log path (or ``None`` if file logging is unavailable).
    """
    token = run_id_var.set(str(run_id))
    handler = attach_run_logger(run_id, project_root=project_root, level=level)
    path = Path(handler.baseFilename) if isinstance(handler, logging.FileHandler) else None
    try:
        yield path
    finally:
        detach_run_logger(handler)
        run_id_var.reset(token)


__all__ = ["attach_run_logger", "detach_run_logger", "run_log_context"]
