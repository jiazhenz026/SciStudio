"""Diagnostics endpoints: version, client-log reflux, diagnostic bundle.

#1741 / #1742. Three boundary endpoints for the alpha closed-beta:

* ``GET  /api/version``        — structured version for bug reports.
* ``POST /api/client-logs``    — frontend logs/errors persisted on the backend
  (logger ``scistudio.frontend``) so the file sink captures them — no third
  party.
* ``GET  /api/diagnostics/bundle`` — a zip of recent log files + an environment
  manifest + per-run logs, for one-click bug reports.
"""

from __future__ import annotations

import io
import json
import logging
import platform
import sys
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from scistudio.api.routes.filesystem import _resolve_safe_path
from scistudio.utils.log_setup import resolve_log_dir
from scistudio.version import get_version

router = APIRouter(prefix="/api", tags=["diagnostics"])

frontend_logger = logging.getLogger("scistudio.frontend")

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


class ClientLogRecord(BaseModel):
    """A single frontend log record refluxed to the backend."""

    level: str = "info"
    message: str
    ts: str | None = None
    url: str | None = None
    request_id: str | None = None
    context: dict[str, Any] | None = None


class ClientLogBatch(BaseModel):
    records: list[ClientLogRecord] = Field(default_factory=list)


@router.get("/version")
async def version_info() -> dict[str, Any]:
    """Return the structured version (base/channel/build/pep440/semver/display)."""
    return get_version().as_dict()


@router.post("/client-logs")
async def client_logs(batch: ClientLogBatch) -> dict[str, int]:
    """Persist a batch of frontend log records through the backend logger."""
    for record in batch.records:
        level = _LEVELS.get(record.level.lower(), logging.INFO)
        frontend_logger.log(
            level,
            "[frontend] %s",
            record.message,
            extra={
                "request_id": record.request_id,
                "event_data": {"url": record.url, "ts": record.ts, "context": record.context},
            },
        )
    return {"accepted": len(batch.records)}


def _log_dirs(request: Request) -> list[Path]:
    """Resolve log directories to include in a bundle (process + active project)."""
    dirs: list[Path] = [resolve_log_dir()]
    runtime = getattr(request.app.state, "runtime", None)
    project = getattr(runtime, "active_project", None) if runtime is not None else None
    project_path = getattr(project, "path", None) if project is not None else None
    if project_path:
        dirs.append(Path(project_path) / ".scistudio" / "logs")
    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[Path] = []
    for directory in dirs:
        key = str(directory)
        if key not in seen:
            seen.add(key)
            unique.append(directory)
    return unique


def _format_frontend_log(records: object) -> str:
    """Render posted frontend records as a human-readable .log (owner: no JSON)."""
    lines: list[str] = []
    items = records if isinstance(records, list) else []
    for record in items:
        if not isinstance(record, dict):
            lines.append(str(record))
            continue
        timestamp = record.get("ts", "")
        level = str(record.get("level", "info")).upper()
        message = record.get("message", "")
        line = f"{timestamp} {level:<7} frontend {message}"
        extras: list[str] = []
        if record.get("request_id"):
            extras.append(f"req={record['request_id']}")
        if record.get("url"):
            extras.append(f"url={record['url']}")
        if record.get("context"):
            extras.append(f"context={json.dumps(record['context'], default=str)}")
        if extras:
            line = f"{line}  [{' '.join(extras)}]"
        lines.append(line)
    return "\n".join(lines) + ("\n" if lines else "")


def _build_bundle_bytes(frontend_records: object, log_dirs: list[Path]) -> bytes:
    """Build the diagnostics zip in-memory (synchronous, CPU/IO-bound).

    Kept as a plain function so the route can run it off the event loop via
    :func:`run_in_threadpool`. Walking + DEFLATE-compressing the rotating log
    files (10 MB x N per layer + run logs) is the slow step; doing it inside the
    async handler blocked the event loop and — for the native-dialog export —
    delayed the save dialog until the whole bundle was built (#1760 bug2).
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        manifest = {
            "version": get_version().as_dict(),
            "python": sys.version,
            "platform": platform.platform(),
            "executable": sys.executable,
        }
        archive.writestr("environment.json", json.dumps(manifest, indent=2))
        if frontend_records is not None:
            archive.writestr("frontend-logs.log", _format_frontend_log(frontend_records))
        for log_dir in log_dirs:
            if not log_dir.is_dir():
                continue
            for pattern, prefix in (
                ("scistudio-*.log*", "logs"),
                ("api-*.log*", "logs"),
                ("engine-*.log*", "logs"),
                ("frontend-*.log*", "logs"),
                ("run-*.log*", "runs"),
            ):
                for path in sorted(log_dir.glob(pattern)):
                    try:
                        archive.write(path, arcname=f"{prefix}/{path.name}")
                    except OSError:
                        continue
    return buffer.getvalue()


def _resolve_bundle_destination(raw_path: object) -> Path:
    """Validate a native-dialog-chosen save path for the diagnostics bundle.

    Mirrors the preview-export contract (``data.save_preview_resource``): the
    path must be an absolute file path under an allowed root (user home / temp),
    with an existing parent directory. The path originates from the OS native
    save dialog, so this is intent confirmation, not a trust boundary by itself.
    """
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise HTTPException(status_code=400, detail="save destination must be a non-empty path")
    if not Path(raw_path).is_absolute():
        raise HTTPException(status_code=400, detail="save destination must be an absolute file path")
    try:
        destination = _resolve_safe_path(raw_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if destination.exists() and destination.is_dir():
        raise HTTPException(status_code=400, detail="save destination must be a file path")
    if not destination.parent.is_dir():
        raise HTTPException(status_code=400, detail="save destination parent directory does not exist")
    return destination


@router.api_route("/diagnostics/bundle", methods=["GET", "POST"])
async def diagnostics_bundle(request: Request) -> Any:
    """Return a zip with recent logs, an environment manifest, and run logs.

    On POST, an optional JSON body ``{"records": [...]}`` of frontend log records
    is bundled as ``frontend-logs.log`` so the entire report is a *single*
    download — browsers block consecutive auto-downloads, so the frontend posts
    its in-memory ring buffer here instead of downloading a second file itself.

    When the body also carries ``{"path": "/abs/dest.zip"}`` (a path the user
    picked via the native save dialog), the bundle is written directly to that
    path and a small JSON receipt is returned instead of streaming the bytes
    back. This lets the desktop export show the save dialog *first* and build the
    (potentially large) bundle afterwards, so the dialog no longer waits for the
    whole zip to be assembled (#1760 bug2). The bundle build always runs off the
    event loop via :func:`run_in_threadpool`.
    """
    frontend_records = None
    destination_raw: object = None
    if request.method == "POST":
        try:
            body = await request.json()
            if isinstance(body, dict):
                frontend_records = body.get("records")
                destination_raw = body.get("path")
        except Exception:
            frontend_records = None

    log_dirs = _log_dirs(request)
    data = await run_in_threadpool(_build_bundle_bytes, frontend_records, log_dirs)

    if destination_raw is not None:
        destination = _resolve_bundle_destination(destination_raw)
        await run_in_threadpool(destination.write_bytes, data)
        return {"status": "written", "path": str(destination), "bytes": len(data)}

    headers = {"Content-Disposition": "attachment; filename=scistudio-diagnostics.zip"}
    return StreamingResponse(io.BytesIO(data), media_type="application/zip", headers=headers)


__all__ = ["router"]
