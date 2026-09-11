"""Guarded panel operations and the single self-authenticating asset prefix."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from scistudio.panels.contexts import PANEL_EVENTS, READ_BYTES, PanelContext, get_panel_contexts
from scistudio.panels.files import content_policy, media_type, resolve_panel_file
from scistudio.panels.reads import read_context
from scistudio.panels.targets import PanelError
from scistudio.previewers.models import PreviewError

router = APIRouter(prefix="/api/panels", tags=["panels"])
_STATIC_ROOT = Path(__file__).resolve().parents[2] / "panels"


class ContextCreate(BaseModel):
    """A host opens a panel from backend-owned target or waiting block identity."""

    model_config = ConfigDict(extra="forbid")
    kind: str
    panel_id: str | None = None
    target: dict[str, Any] | None = None
    preview_session_id: str | None = None
    parent_context_id: str | None = None
    workflow_id: str | None = None
    block_id: str | None = None
    view_state: Any = None
    query: dict[str, Any] = Field(default_factory=dict)


class ContextRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    op: str
    params: dict[str, Any] = Field(default_factory=dict)


class PanelIdentity(BaseModel):
    id: str
    api_version: str
    name: str


class ContextResponse(BaseModel):
    context_id: str
    panel: PanelIdentity
    kind: Literal["preview", "interactive"]
    operations: list[Literal["read", "writeBack"]]
    services: list[Literal["open", "save"]]
    input: dict[str, Any]
    view_state: Any = None
    token: str
    expires_at: float
    entry_url: str
    sdk_url: str
    lib_base_url: str


class ReadResult(BaseModel):
    """Operation-specific bounded payload plus mandatory sampling flags."""

    model_config = ConfigDict(extra="allow")
    sampled: bool
    truncated: bool
    complete: bool


class PanelFailureDetail(BaseModel):
    code: str
    message: str


class PanelFailureResponse(BaseModel):
    detail: PanelFailureDetail


_ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": PanelFailureResponse} for code in (400, 403, 404, 409, 413, 422, 429)
}
_READ_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/ReadResult"}},
            "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
        },
        "headers": {
            "X-Panel-Dtype": {"schema": {"type": "string"}, "description": "Little-endian NumPy dtype"},
            "X-Panel-Shape": {"schema": {"type": "string"}, "description": "JSON array of dimensions"},
            "X-Panel-Metadata": {
                "schema": {"type": "string"},
                "description": "JSON metadata including sampled, truncated, complete flags",
            },
        },
    },
    **_ERRORS,
}


def _failure(exc: PanelError) -> HTTPException:
    return HTTPException(exc.status, detail={"code": exc.code, "message": exc.message})


def _base(request: Request) -> str:
    return str(request.scope.get("root_path", "")).rstrip("/")


def _context_response(request: Request, context: PanelContext) -> dict[str, Any]:
    base = f"{_base(request)}/api/panels/t/{context.token}"
    return {
        "context_id": context.context_id,
        "panel": {"id": context.panel.id, "api_version": context.panel.api_version, "name": context.panel.name},
        "kind": context.kind,
        "operations": ["read"] if context.kind == "preview" else ["writeBack"],
        "services": ["open", "save"] if context.kind == "preview" else ["save"],
        "input": context.input,
        "view_state": context.view_state,
        "token": context.token,
        "expires_at": context.expires_at,
        "entry_url": f"{base}/assets/{context.panel.id}/{quote(context.panel.entry, safe='/')}",
        "sdk_url": f"{base}/sdk/1/scistudio-panel.js",
        "lib_base_url": f"{base}/lib/",
    }


@router.get("/catalog")
def catalog(request: Request) -> dict[str, Any]:
    registry = request.app.state.runtime.get_preview_service().registry.panels
    return {
        "panels": [
            p.to_dict() | {"owner_kind": p.owner_kind.value, "shadowed": False} for p in registry.panels.values()
        ]
        + [p.to_dict() | {"owner_kind": p.owner_kind.value, "shadowed": True} for p in registry.shadowed],
        "diagnostics": registry.diagnostics,
    }


@router.post("/contexts", response_model=ContextResponse, responses=_ERRORS)
def create_context(payload: ContextCreate, request: Request) -> dict[str, Any]:
    try:
        _bounded_json(payload.model_dump())
        return _context_response(request, get_panel_contexts(request.app.state.runtime).create(payload.model_dump()))
    except PanelError as exc:
        raise _failure(exc) from exc
    except PreviewError as exc:
        raise _failure(PanelError(409, exc.code.value, exc.message)) from exc
    except (ValueError, TypeError) as exc:
        raise _failure(PanelError(422, "invalid_request", str(exc))) from exc


@router.delete("/contexts/{context_id}", status_code=204)
def close_context(context_id: str, request: Request) -> Response:
    get_panel_contexts(request.app.state.runtime).close(context_id)
    return Response(status_code=204)


@router.post("/contexts/{context_id}/renew", response_model=ContextResponse, responses=_ERRORS)
def renew_context(context_id: str, request: Request) -> dict[str, Any]:
    try:
        return _context_response(request, get_panel_contexts(request.app.state.runtime).renew(context_id))
    except PanelError as exc:
        raise _failure(exc) from exc


@router.post("/contexts/{context_id}/read", response_model=ReadResult, responses=_READ_RESPONSE)
def panel_read(context_id: str, payload: ContextRead, request: Request) -> Response:
    try:
        _bounded_json(payload.params, limit=8192)
        if payload.params.get("format", "json") not in ("json", "binary"):
            raise PanelError(422, "invalid_request", "Read format must be json or binary")
        store = get_panel_contexts(request.app.state.runtime)
        context = store.get(context_id)
        result = read_context(store, context, payload.ref, payload.op, payload.params)
        # A close/project switch while the worker was reading cannot deliver stale bytes.
        store.get(context_id)
        if hasattr(result, "to_bytes"):
            if payload.params.get("format") == "binary":
                data = result.to_bytes()
                if len(data) > READ_BYTES:
                    raise PanelError(413, "read_budget", "Numeric response exceeds panel byte budget")
                return Response(
                    data,
                    media_type="application/octet-stream",
                    headers={
                        "X-Panel-Dtype": str(result.metadata["dtype"]),
                        "X-Panel-Shape": json.dumps(result.metadata["shape"]),
                        "X-Panel-Metadata": json.dumps(result.metadata, allow_nan=False),
                        "Cache-Control": "no-store",
                    },
                )
            result = result.to_json()
            if payload.op == "series.points":
                pairs = result.pop("values")
                result.update(index=[row[0] for row in pairs], values=[row[1] for row in pairs])
        elif payload.params.get("format") == "binary":
            raise PanelError(400, "unsupported", "Binary is supported only for array and series reads")
        result = {"sampled": False, "truncated": False, "complete": True, **result}
        if payload.op == "artifact.file":
            result["url"] = _base(request) + result["url"]
        _bounded_json(result)
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except PanelError as exc:
        raise _failure(exc) from exc
    except (ValueError, TypeError, OSError, KeyError) as exc:
        raise _failure(PanelError(422, "invalid_request", str(exc))) from exc


def _bounded_json(value: Any, *, limit: int = READ_BYTES) -> None:
    if len(json.dumps(value, allow_nan=False).encode()) > limit:
        raise PanelError(413, "read_budget", "Panel JSON exceeds its byte budget")


def _static_response(request: Request, path: Path, token: str) -> Response:
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    # CSP host-sources must be absolute URLs. root_path occurs exactly once.
    origin = f"{request.url.scheme}://{request.url.netloc}"
    headers["Content-Security-Policy"] = content_policy(f"{origin}{_base(request)}/api/panels/t/{token}/")
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=headers)
    return FileResponse(path, media_type=media_type(path), headers=headers)


@router.get("/t/{token}/assets/{panel_id}/{path:path}")
@router.options("/t/{token}/assets/{panel_id}/{path:path}", include_in_schema=False)
def panel_asset(token: str, panel_id: str, path: str, request: Request) -> Response:
    try:
        context = get_panel_contexts(request.app.state.runtime).by_token(token)
        if context.panel.id != panel_id:
            raise PanelError(403, "invalid_token", "Token does not authorize this panel")
        return _static_response(request, resolve_panel_file(context.panel.root, path), token)
    except PanelError as exc:
        raise _failure(exc) from exc
    except ValueError as exc:
        raise _failure(PanelError(404, "invalid_asset", str(exc))) from exc


@router.get("/t/{token}/sdk/{major}/scistudio-panel.js")
@router.options("/t/{token}/sdk/{major}/scistudio-panel.js", include_in_schema=False)
def panel_sdk(token: str, major: str, request: Request) -> Response:
    try:
        get_panel_contexts(request.app.state.runtime).by_token(token)
        if major != "1":
            raise ValueError("Unsupported SDK major")
        return _static_response(request, resolve_panel_file(_STATIC_ROOT / "sdk", "1/scistudio-panel.js"), token)
    except PanelError as exc:
        raise _failure(exc) from exc
    except ValueError as exc:
        raise _failure(PanelError(404, "invalid_asset", str(exc))) from exc


@router.get("/t/{token}/lib/{library}/{path:path}")
@router.options("/t/{token}/lib/{library}/{path:path}", include_in_schema=False)
def panel_library(token: str, library: str, path: str, request: Request) -> Response:
    try:
        get_panel_contexts(request.app.state.runtime).by_token(token)
        root = (_STATIC_ROOT / "lib").resolve()
        index = json.loads((root / "index.json").read_text())
        entry = next((e for e in index["libraries"] if f"{e['name']}@{e['version']}" == library), None)
        if entry is None or path not in entry["files"]:
            raise ValueError("Library file is not in the pinned index")
        file = (root / library / path).resolve()
        if not file.is_relative_to(root / library) or not file.is_file():
            raise ValueError("Library path escapes confinement root")
        return _static_response(request, file, token)
    except PanelError as exc:
        raise _failure(exc) from exc
    except (ValueError, OSError) as exc:
        raise _failure(PanelError(404, "invalid_asset", str(exc))) from exc


@router.get("/t/{token}/artifact/{grant_id}")
@router.options("/t/{token}/artifact/{grant_id}", include_in_schema=False)
def panel_artifact(token: str, grant_id: str, request: Request) -> Response:
    try:
        target = get_panel_contexts(request.app.state.runtime).artifact(token, grant_id)
        from scistudio.panels.contexts import read_access

        if target.storage is None:
            raise PanelError(403, "unauthorized_ref", "Artifact grant has no storage")
        path = read_access().artifact_file(target.storage)
        response = _static_response(request, path, token)
        # Artifacts are data, never executable application documents.
        response.headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
        response.headers["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(path.name)
        return response
    except PanelError as exc:
        raise _failure(exc) from exc
    except (ValueError, OSError) as exc:
        raise _failure(PanelError(404, "invalid_artifact", str(exc))) from exc


def install_panels(app: FastAPI) -> None:
    """Mount routes and register only the authenticated static token prefix."""
    from scistudio.api.seam import register_self_authenticating_prefix

    register_self_authenticating_prefix("/api/panels/t/")
    app.include_router(router)


@asynccontextmanager
async def panels_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Listen before workflows run; close runtime contexts at shutdown."""
    store = get_panel_contexts(app.state.runtime)
    try:
        yield
    finally:
        store.close_all()
        for event in PANEL_EVENTS:
            app.state.runtime.event_bus.unsubscribe(event, store.on_event)
