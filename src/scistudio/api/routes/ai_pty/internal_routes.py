"""Internal HTTP routes — worker → engine IPC (ADR-035 §3.10).

These two endpoints are private to the engine process. The token comes
from the env var ``SCISTUDIO_ENGINE_IPC_TOKEN`` which the engine sets at
startup; child worker subprocesses inherit it via ``os.environ`` and
attach it on the ``X-SciStudio-IPC-Token`` request header.

The :func:`_ensure_ipc_token` helper is also called from
``scistudio.api.app.lifespan`` so the env var is populated before any
worker is spawned (Audit P1-B fix).
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Annotated, Any

from fastapi import Body, Header, HTTPException

from scistudio.api.routes.ai_pty import _state as _pkg
from scistudio.api.routes.ai_pty import engine as _engine
from scistudio.api.routes.ai_pty.subscribers import broadcast_ai_pty_message

logger = logging.getLogger(__name__)


def _ensure_ipc_token() -> str:
    """Return the live IPC token, generating a per-process one if missing.

    The first call sets ``SCISTUDIO_ENGINE_IPC_TOKEN`` if unset so a child
    process can inherit the same value. Production engines that fork
    workers BEFORE this is touched should call it eagerly during
    startup; tests can rely on lazy generation.
    """
    tok = os.environ.get("SCISTUDIO_ENGINE_IPC_TOKEN")
    if tok:
        return tok
    tok = secrets.token_urlsafe(24)
    os.environ["SCISTUDIO_ENGINE_IPC_TOKEN"] = tok
    return tok


def _check_ipc_token(provided: str | None) -> None:
    """Raise 401 if *provided* doesn't match the live IPC token."""
    expected = os.environ.get("SCISTUDIO_ENGINE_IPC_TOKEN", "")
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="invalid SciStudio IPC token")


_HeaderToken = Annotated[str | None, Header(alias="X-SciStudio-IPC-Token")]
_BodyDict = Annotated[dict[str, Any], Body()]


@_pkg.router.post("/pty/internal/request-tab")  # type: ignore[has-type]
async def _internal_request_tab(
    payload: _BodyDict,
    x_scistudio_ipc_token: _HeaderToken = None,
) -> dict[str, Any]:
    """Engine-internal endpoint: AI Block worker requests a new PTY tab.

    Returns ``{"tab_id": str, "error": null}`` on success, or
    ``{"tab_id": null, "error": <message>}`` on a soft failure such as
    cap exceeded. Hard transport failures (auth, malformed body) raise
    :class:`HTTPException` with the appropriate status.
    """
    _check_ipc_token(x_scistudio_ipc_token)

    if payload.get("type") != "request_pty_tab":
        raise HTTPException(status_code=400, detail="payload.type must be 'request_pty_tab'")
    spec = payload.get("spec")
    if not isinstance(spec, dict):
        raise HTTPException(status_code=400, detail="payload.spec must be a dict")

    try:
        # Late-bound lookup on the ``engine`` module so tests can
        # monkeypatch.setattr(ai_pty.engine, "open_engine_initiated_tab", ...).
        tab_id = _engine.open_engine_initiated_tab(
            title=str(spec.get("title", "")),
            spawn_argv=list(spec.get("spawn_argv", [])),
            cwd=str(spec.get("cwd", "")),
            initial_stdin=str(spec.get("initial_stdin", "")),
            block_run_id=str(spec.get("block_run_id", "")),
            permission_mode=str(spec.get("permission_mode", "safe")),
            run_dir_path=(str(spec["run_dir_path"]) if spec.get("run_dir_path") else None),
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "cap" in msg.lower():
            # 503 — soft failure surface that the worker can interpret
            # as "queue and retry later" if it cared to.
            raise HTTPException(status_code=503, detail=msg) from exc
        return {"tab_id": None, "error": msg}
    except Exception as exc:
        logger.exception("internal_request_tab: spawn failed")
        return {"tab_id": None, "error": str(exc)}

    return {"tab_id": tab_id, "error": None}


@_pkg.router.post("/pty/internal/notify", status_code=204)  # type: ignore[has-type]
async def _internal_notify(
    payload: _BodyDict,
    x_scistudio_ipc_token: _HeaderToken = None,
) -> None:
    """Engine-internal endpoint: AI Block worker reports completion.

    Fire-and-forget on the worker side. We update the tab→run map and
    broadcast a ``block_pty_closed`` frame so the frontend can decorate
    the tab title with status ✓/✗ per ADR-035 §3.9. The PTY itself
    stays open (per ADR-035 §3.9: "tab survives DONE/ERROR").
    """
    _check_ipc_token(x_scistudio_ipc_token)

    if payload.get("type") != "notify_block_pty_event":
        raise HTTPException(status_code=400, detail="payload.type must be 'notify_block_pty_event'")
    block_run_id = payload.get("block_run_id")
    event = payload.get("event")
    if not isinstance(block_run_id, str) or not block_run_id:
        raise HTTPException(status_code=400, detail="block_run_id must be a non-empty string")
    if event not in ("completed", "cancelled_by_user_close", "error"):
        raise HTTPException(status_code=400, detail=f"unknown event {event!r}")

    # Resolve tab_id from the run_id — best effort; the broadcast still
    # carries block_run_id so the frontend can match independently.
    tab_id = None
    for tid, rid in _pkg._engine_tab_to_run.items():
        if rid == block_run_id:
            tab_id = tid
            break

    detail = payload.get("detail") or {}
    message = {
        "type": "block_pty_closed",
        "block_run_id": block_run_id,
        "tab_id": tab_id,
        "event": event,
        "detail": detail if isinstance(detail, dict) else {},
    }
    await broadcast_ai_pty_message(message)
    logger.info(
        "internal_notify: block_run_id=%s event=%s tab_id=%s",
        block_run_id,
        event,
        tab_id,
    )
