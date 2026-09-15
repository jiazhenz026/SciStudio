"""Guarded panel operations and the single self-authenticating asset prefix."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from scistudio.api.schemas import PreviewEnvelopeModel
from scistudio.panels.contexts import READ_BYTES, PanelContext, get_panel_contexts
from scistudio.panels.files import MAX_SOURCE_BYTES, bootstrap_entry, content_policy, media_type, resolve_panel_file
from scistudio.panels.process_config import max_result_bytes
from scistudio.panels.reads import read_context
from scistudio.panels.service import get_panel_service
from scistudio.panels.targets import PanelError
from scistudio.previewers.models import PreviewError

logger = logging.getLogger(__name__)

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
    # MiniApp (miniapp kind): the block output to open on, and the realtime
    # client the context binds to (FR-004/FR-013).
    source: dict[str, Any] | None = None
    ws_client_id: str | None = None


class ContextRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    op: str
    params: dict[str, Any] = Field(default_factory=dict)


class ContextOpen(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str


class PanelIdentity(BaseModel):
    id: str
    api_version: str
    name: str


class ContextResponse(BaseModel):
    context_id: str
    panel: PanelIdentity
    kind: Literal["preview", "interactive", "miniapp"]
    operations: list[Literal["read", "writeBack", "call", "submitAnswers"]]
    services: list[Literal["open", "save"]]
    input: dict[str, Any]
    view_state: Any = None
    token: str
    bootstrap_proof: str
    expires_at: float
    entry_url: str
    sdk_url: str
    lib_base_url: str
    process: dict[str, Any] | None = None


class ContextCall(BaseModel):
    """A MiniApp page calls one of its ``panel.py`` functions by name."""

    model_config = ConfigDict(extra="forbid")
    fn: str
    args: dict[str, Any] = Field(default_factory=dict)


class ContextCallResult(BaseModel):
    """A ``panel.py`` function returned; the value is whatever it returned."""

    result: Any = None


class ContextCallErrorDetail(BaseModel):
    """The exception a ``panel.py`` function raised, as the page receives it."""

    type: str
    message: str
    traceback: str


class ContextCallError(BaseModel):
    """A call that raised. The HTTP status is still 200 and the process lives."""

    # A call that raised. The HTTP status is still 200 and the process lives.
    #
    # FR-011: an exception in a panel function is an answer, not a transport
    # failure — the process keeps running and the next call still works. The
    # client turns this body into a rejected promise.

    error: ContextCallErrorDetail


class ContextAnswers(BaseModel):
    """A MiniApp page submits its questionnaire."""

    # MiniApp FR-050.

    model_config = ConfigDict(extra="forbid")
    answers: dict[str, Any] = Field(description="One answer per question id; a question left out is skipped.")


class SubmitAnswersResult(BaseModel):
    """What a questionnaire submit did."""

    # MiniApp FR-050/FR-051.

    saved: bool
    path: str | None = Field(description="Where answers.json was written: project-relative inside the project.")
    submitted_at: str | None = None
    notified: bool = Field(description="True when the line reached the MiniApp's open agent session.")
    reason: Literal["no_session", "session_ended"] | None = Field(
        default=None,
        description="Why no session was notified: none was recorded for this MiniApp, or it has ended.",
    )
    message: str = Field(description="What the page shows the user under the Submit button.")


class ReadResult(BaseModel):
    """Operation-specific payload plus mandatory paging flags.

    A panel read is never sampled: ``truncated`` means more pages, windows, or
    chunks remain to be read, and ``complete`` means this read reached the end.
    """

    model_config = ConfigDict(extra="allow")
    truncated: bool
    complete: bool


class MiniAppTarget(BaseModel):
    """The block output a MiniApp opens on."""

    # The block output a MiniApp opens on (MiniApp FR-004).

    model_config = ConfigDict(extra="forbid")
    workflow_id: str
    block_id: str
    port: str


class MiniAppSummary(BaseModel):
    """One MiniApp in the MiniApps tab."""

    # One MiniApp in the MiniApps tab (MiniApp FR-031/FR-032).

    panel_id: str
    name: str
    description: str
    type: str = Field(description="The single declared type, verbatim from panel.json.")
    tier: Literal["project", "user", "package", "core"]
    directory: str = Field(description="Absolute path of the MiniApp directory, for the hover popover.")
    has_python: bool


class MiniAppListResponse(BaseModel):
    miniapps: list[MiniAppSummary]


class MiniAppSource(BaseModel):
    """One openable block output for a MiniApp's declared type."""

    # One openable block output for a MiniApp's declared type (MiniApp FR-034).

    workflow_id: str
    workflow_name: str
    block_id: str
    block_name: str
    port: str
    type: str


class MiniAppSourcesResponse(BaseModel):
    sources: list[MiniAppSource]


class MiniAppCreate(BaseModel):
    """Request body for ``POST /api/panels/miniapps``."""

    # Request body for ``POST /api/panels/miniapps`` (MiniApp FR-024).

    model_config = ConfigDict(extra="forbid")
    request: str = Field(max_length=4000, description="What the user wants to see or do, in their own words.")
    source: MiniAppTarget
    provider: str | None = Field(default=None, description="Agent provider key; the first ready one when omitted.")
    permission_mode: str | None = Field(
        default=None,
        description="'safe', 'auto', or 'bypass'; 'dangerous' means 'bypass'. Auto requires provider support. Defaults to safe.",
    )
    name: str | None = Field(default=None, description="Display name; derived from the request when omitted.")


class MiniAppCreated(BaseModel):
    """Response body for ``POST /api/panels/miniapps``.

    ``session_tab_id`` is null when the directory was created but the agent
    session could not be spawned: the template is on disk and the tab opens on
    it, so the create succeeded and only the agent did not start.
    """

    panel_id: str
    name: str
    source: MiniAppTarget
    session_tab_id: str | None = None
    provider: str | None = None
    permission_mode: str | None = None
    directory: str


class MiniAppConvertOutput(BaseModel):
    """One output the converted interactive block must produce."""

    # One output the converted interactive block must produce (MiniApp FR-036).

    model_config = ConfigDict(extra="forbid")
    name: str
    type: str
    port: str


class MiniAppConvert(BaseModel):
    """Request body for ``POST /api/panels/miniapps/{panel_id}/convert``."""

    model_config = ConfigDict(extra="forbid")
    outputs: list[MiniAppConvertOutput] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=4000)
    provider: str | None = None
    permission_mode: str | None = None


class MiniAppConverted(BaseModel):
    session_tab_id: str | None = None
    provider: str | None = None
    permission_mode: str | None = None


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
                "description": "JSON metadata including truncated and complete flags",
            },
        },
    },
    **_ERRORS,
}
# MiniApp FR-010: the call route's own declared contract. It shares the read
# route's octet-stream branch and dtype/shape headers, but its JSON 200 is
# ``{result}`` or ``{error}`` — never ``ReadResult``, which carries sampling
# flags no call ever returns — and it declares the 504 a call timeout produces.
_CALL_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {
            "application/json": {
                # ``anyOf``, not ``oneOf``: an ``{error}`` body also satisfies
                # ``ContextCallResult``, whose single field is optional, so an
                # exclusive union would reject the very body it describes.
                "schema": {
                    "anyOf": [
                        {"$ref": "#/components/schemas/ContextCallResult"},
                        {"$ref": "#/components/schemas/ContextCallError"},
                    ]
                }
            },
            "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
        },
        "headers": {
            "X-Panel-Dtype": {"schema": {"type": "string"}, "description": "Little-endian NumPy dtype"},
            "X-Panel-Shape": {"schema": {"type": "string"}, "description": "JSON array of dimensions"},
            "X-Panel-Metadata": {"schema": {"type": "string"}, "description": "JSON metadata with dtype and shape"},
        },
    },
    **_ERRORS,
    504: {"model": PanelFailureResponse},
}


def _failure(exc: PanelError) -> HTTPException:
    return HTTPException(exc.status, detail={"code": exc.code, "message": exc.message})


def _base(request: Request) -> str:
    return str(request.scope.get("root_path", "")).rstrip("/")


def _context_response(request: Request, context: PanelContext) -> dict[str, Any]:
    base = f"{_base(request)}/api/panels/t/{context.token}"
    operations, services = context.provides()
    process = context.process.status() if getattr(context, "process", None) is not None else None
    return {
        "context_id": context.context_id,
        "panel": {"id": context.panel.id, "api_version": context.panel.api_version, "name": context.panel.name},
        "kind": context.kind,
        "operations": operations,
        "services": services,
        "input": context.input,
        "view_state": context.view_state,
        "token": context.token,
        "bootstrap_proof": context.bootstrap_proof,
        "expires_at": context.expires_at,
        "entry_url": f"{base}/assets/{context.panel.id}/{quote(context.panel.entry, safe='/')}",
        "sdk_url": f"{base}/sdk/1/scistudio-panel.js",
        "lib_base_url": f"{base}/lib/",
        "process": process,
    }


@router.get("/catalog")
def catalog(request: Request) -> dict[str, Any]:
    # The panel service brings the catalog up to date with the panel folders
    # first, so a panel written a moment ago is listed (#2421).
    return get_panel_service(request.app.state.runtime).catalog()


# ---------------------------------------------------------------------------
# MiniApps (ADR-054 MiniApp FR-024, FR-026, FR-027, FR-034, FR-036)
# ---------------------------------------------------------------------------

#: Normalize the frontend bypass alias at the request boundary. Auto remains
#: distinct and is accepted only when the selected provider supports it.
_PERMISSION_MODES = {"safe": "safe", "auto": "auto", "bypass": "bypass", "dangerous": "bypass"}


def _miniapps(request: Request) -> dict[str, Any]:
    return get_panel_service(request.app.state.runtime).miniapps()


def _miniapp(request: Request, panel_id: str) -> Any:
    panel = _miniapps(request).get(panel_id)
    if panel is None:
        raise PanelError(404, "unknown_panel", f"MiniApp {panel_id!r} is not registered")
    return panel


@router.get("/miniapps", response_model=MiniAppListResponse, responses=_ERRORS)
def list_miniapps(request: Request) -> dict[str, Any]:
    """Every registered panel declaring ``miniapp``, for the MiniApps tab."""
    # Every registered panel declaring ``miniapp``, for the MiniApps tab (FR-031).
    return {
        "miniapps": [
            {
                "panel_id": panel.id,
                "name": panel.name or panel.id,
                "description": panel.description,
                "type": panel.types[0] if panel.types else "",
                "tier": panel.owner_kind.value,
                "directory": str(panel.root),
                "has_python": panel.has_python,
            }
            for panel in sorted(_miniapps(request).values(), key=lambda p: (p.name or p.id).lower())
        ]
    }


@router.get("/miniapps/sources", response_model=MiniAppSourcesResponse, responses=_ERRORS)
def list_project_miniapp_sources(request: Request) -> dict[str, Any]:
    """List available outputs across the project before a MiniApp exists."""
    from scistudio.panels.miniapp_create import iter_source_candidates

    return {"sources": [candidate.as_dict() for candidate in iter_source_candidates(request.app.state.runtime)]}


@router.get("/miniapps/{panel_id}/sources", response_model=MiniAppSourcesResponse, responses=_ERRORS)
def list_miniapp_sources(panel_id: str, request: Request) -> dict[str, Any]:
    """The outputs this MiniApp can open on, for the target picker."""
    # The outputs this MiniApp can open on, for the target picker (FR-034).
    from scistudio.panels.miniapp_create import matching_sources

    try:
        panel = _miniapp(request, panel_id)
        return {"sources": matching_sources(request.app.state.runtime, panel)}
    except PanelError as exc:
        raise _failure(exc) from exc


def _permission_mode(raw: str | None) -> str:
    mode = _PERMISSION_MODES.get((raw or "safe").strip().lower())
    if mode is None:
        raise PanelError(422, "invalid_request", f"Unknown permission mode {raw!r}")
    return mode


def _graded_reason(row: Any, report: Any) -> str:
    """The availability report's own sentence for why a session cannot start."""
    # The availability report's own sentence for why a session cannot start.
    #
    # Quoted rather than paraphrased (ADR-053 §5.2): the report already decided
    # which of install, sign in, or "the call failed because …" is the actionable
    # one, and a second wording here would give the user two accounts of one fact.
    if row is None:
        row = next((p for p in report.providers if p.state == report.state), None)
    if row is None:
        return "No agent provider is configured, so no MiniApp session can start."
    for sentence in (row.session_unsupported_reason, row.next_step, row.cause):
        if sentence:
            return str(sentence)
    return f"{row.label} cannot start a session right now."


async def _agent_for_session(provider: str | None, permission_mode: str | None) -> tuple[str, str]:
    """Return the provider and mode a session may start with, or refuse."""
    # Return the provider and mode a session may start with, or refuse (FR-024).
    #
    # This runs FIRST, before anything is written: a MiniApp whose agent never
    # started is a directory the user did not ask for and has to find and delete
    # themselves. ``session_unsupported_reason`` refuses a provider however
    # ``ready`` it is — the opening instruction is a positional argument its CLI
    # cannot take, and no amount of signing in changes that.
    from scistudio.ai.agent import availability as agent_availability
    from scistudio.ai.agent.availability import AvailabilityState
    from scistudio.ai.agent.providers_registry import get as get_descriptor
    from scistudio.api.routes.ai import _status_rows

    def usable(row: Any) -> bool:
        return row.state is AvailabilityState.READY and not row.session_unsupported_reason

    mode = _permission_mode(permission_mode)
    report = await agent_availability.probe_availability(_status_rows)
    if provider is None:
        chosen = next((row for row in report.providers if usable(row)), None)
        if chosen is None:
            raise PanelError(409, "agent_unavailable", _graded_reason(None, report))
    else:
        chosen = next((row for row in report.providers if row.key == provider), None)
        if chosen is None:
            raise PanelError(422, "invalid_request", f"Unknown agent provider {provider!r}")
        if not usable(chosen):
            raise PanelError(409, "agent_unavailable", _graded_reason(chosen, report))
    if mode == "auto":
        descriptor = get_descriptor(chosen.key)
        if not descriptor.supports_auto_mode:
            raise PanelError(
                400,
                "invalid_request",
                f"{descriptor.label} has no Auto permission mode; choose Manual or Yolo/Bypass.",
            )
    return chosen.key, mode


#: The agent session last started for each MiniApp, keyed by panel id, with the
#: project directory it runs in (MiniApp FR-051). In memory only: the sessions
#: are PTYs of this process and do not outlive it either.
_MINIAPP_SESSION_TABS: dict[str, tuple[str, Path]] = {}

_NOTIFIED_MESSAGE = "Sent. The agent is building your MiniApp from these answers."
_RETURN_MESSAGE = "Your answers are saved. Go back to your AI chat and tell it you have submitted the questionnaire."


def _remember_session(panel_id: str, tab_id: str | None, project_dir: Path) -> None:
    if tab_id:
        _MINIAPP_SESSION_TABS[panel_id] = (tab_id, project_dir)


def _session_tab(*, provider: str, project_dir: Path, brief_relpath: str, permission_mode: str) -> str | None:
    """Spawn the agent session, or report that it did not start.

    Last, and never fatal: the directory and the brief are already on disk and
    the tab opens on them, so a provider binary that vanished between the
    availability probe and this call leaves the user with a MiniApp they can
    still see and an agent they can start by hand.
    """
    from scistudio.panels.miniapp_create import opening_message

    try:
        from scistudio.api.routes.ai_pty import engine as _engine

        return _engine.open_work_import_tab(
            provider=provider,
            cwd=str(project_dir),
            opening_message=opening_message(brief_relpath),
            permission_mode=permission_mode,
        )
    except (FileNotFoundError, RuntimeError, OSError):
        logger.warning("MiniApp session did not start for provider %s", provider, exc_info=True)
        return None


def _project_dir(runtime: Any) -> Path:
    from scistudio.api.routes.ai_pty.validation import _validate_project_dir

    raw = getattr(getattr(runtime, "active_project", None), "path", None)
    if not raw:
        raise PanelError(409, "no_project", "Open a project before creating a MiniApp")
    try:
        return _validate_project_dir(str(raw))
    except (RuntimeError, PermissionError, OSError) as exc:
        raise PanelError(400, "invalid_project", f"Invalid project directory: {exc}") from exc


def _display_name(payload: MiniAppCreate) -> str:
    if payload.name and payload.name.strip():
        return payload.name.strip()[:80]
    first = payload.request.strip().splitlines()[0] if payload.request.strip() else ""
    return (first[:60].strip() or "MiniApp").capitalize()


def _refresh_panels(runtime: Any) -> None:
    """Rescan the panels so the MiniApp just written is registered before the tab opens.

    Only the panel catalog: writing a MiniApp changes no block, type or legacy
    previewer, and the rescan is incremental, so open panels stay open.
    """
    # Development references: #2465.
    try:
        get_panel_service(runtime).rescan()
    except Exception:
        logger.exception("MiniApp create: panel rescan raised")


def _create_miniapp(runtime: Any, payload: MiniAppCreate, provider: str, mode: str) -> dict[str, Any]:
    from scistudio.panels.miniapp_create import (
        CORE_SENTINEL_TYPES,
        compose_create_brief,
        create_from_template,
        iter_source_candidates,
        slugify,
        write_brief,
    )

    project_dir = _project_dir(runtime)
    wanted = payload.source.model_dump()
    target = (payload.source.workflow_id, payload.source.block_id, payload.source.port)
    candidate = next(
        (c for c in iter_source_candidates(runtime) if (c.workflow_id, c.block_id, c.port) == target),
        None,
    )
    if candidate is None:
        raise PanelError(409, "no_output", "That block has no output from a successful run to open on")
    if not candidate.type or candidate.type in CORE_SENTINEL_TYPES:
        raise PanelError(
            409,
            "unsupported_type",
            "That output has no registered type, so a MiniApp cannot declare what it opens on",
        )

    name = _display_name(payload)
    try:
        panel_id, directory = create_from_template(
            project_dir,
            base_id=slugify(name),
            name=name,
            description=payload.request.strip(),
            type_name=candidate.type,
        )
        brief_path = write_brief(
            project_dir,
            compose_create_brief(
                panel_id=panel_id,
                directory_relpath=directory.relative_to(project_dir).as_posix(),
                request=payload.request,
                type_name=candidate.type,
                source=wanted,
            ),
        )
    except OSError as exc:
        raise PanelError(500, "write_failed", f"Could not create the MiniApp: {exc}") from exc

    _refresh_panels(runtime)
    tab_id = _session_tab(
        provider=provider,
        project_dir=project_dir,
        brief_relpath=brief_path.relative_to(project_dir).as_posix(),
        permission_mode=mode,
    )
    _remember_session(panel_id, tab_id, project_dir)
    return {
        "panel_id": panel_id,
        "name": name,
        "source": wanted,
        "session_tab_id": tab_id,
        "provider": provider,
        "permission_mode": mode,
        "directory": str(directory),
    }


@router.post("/miniapps", response_model=MiniAppCreated, status_code=201, responses=_ERRORS)
async def create_miniapp(payload: MiniAppCreate, request: Request) -> dict[str, Any]:
    """Create a MiniApp directory and start the agent session that writes it."""
    # Create a MiniApp directory and start the agent session that writes it.
    #
    # The order is normative (FR-024): the graded availability check comes first
    # and nothing is created when it refuses, then the template directory, then
    # the brief — closed and fsynced — and the agent session last, pointed at a
    # brief that is already complete on disk.
    try:
        provider, mode = await _agent_for_session(payload.provider, payload.permission_mode)
        return await asyncio.to_thread(_create_miniapp, request.app.state.runtime, payload, provider, mode)
    except PanelError as exc:
        raise _failure(exc) from exc
    except (ValueError, TypeError) as exc:
        raise _failure(PanelError(422, "invalid_request", str(exc))) from exc


def _convert_miniapp(runtime: Any, panel: Any, payload: MiniAppConvert, provider: str, mode: str) -> dict[str, Any]:
    from scistudio.panels.miniapp_create import compose_convert_brief, write_brief

    project_dir = _project_dir(runtime)
    directory = Path(panel.root)
    try:
        relpath = directory.relative_to(project_dir).as_posix()
    except ValueError:
        # A user, package, or core MiniApp lives outside the project; the brief
        # names the absolute path so the agent can still read it.
        relpath = str(directory)
    try:
        brief_path = write_brief(
            project_dir,
            compose_convert_brief(
                panel_id=panel.id,
                directory_relpath=relpath,
                outputs=[o.model_dump() for o in payload.outputs],
                note=payload.note,
            ),
        )
    except OSError as exc:
        raise PanelError(500, "write_failed", f"Could not write the conversion brief: {exc}") from exc
    tab_id = _session_tab(
        provider=provider,
        project_dir=project_dir,
        brief_relpath=brief_path.relative_to(project_dir).as_posix(),
        permission_mode=mode,
    )
    _remember_session(panel.id, tab_id, project_dir)
    return {"provider": provider, "permission_mode": mode, "session_tab_id": tab_id}


@router.post("/miniapps/{panel_id}/convert", response_model=MiniAppConverted, status_code=201, responses=_ERRORS)
async def convert_miniapp(panel_id: str, payload: MiniAppConvert, request: Request) -> dict[str, Any]:
    """Start the agent session that turns a MiniApp into an interactive block."""
    # Start the agent session that turns a MiniApp into an interactive block (FR-036).
    #
    # The MiniApp is read, never written: the user keeps the thing they explored
    # with, and the block is a second artefact beside it.
    try:
        panel = _miniapp(request, panel_id)
        provider, mode = await _agent_for_session(payload.provider, payload.permission_mode)
        return await asyncio.to_thread(_convert_miniapp, request.app.state.runtime, panel, payload, provider, mode)
    except PanelError as exc:
        raise _failure(exc) from exc


@router.post("/contexts", response_model=ContextResponse, responses=_ERRORS)
def create_context(payload: ContextCreate, request: Request) -> dict[str, Any]:
    try:
        _bounded_json(payload.model_dump())
        service = get_panel_service(request.app.state.runtime)
        registry = getattr(request.app.state, "registry", None)
        context = service.open_context(payload.model_dump(), process_registry=registry)
        return _context_response(request, context)
    except PanelError as exc:
        raise _failure(exc) from exc
    except PreviewError as exc:
        raise _failure(PanelError(409, exc.code.value, exc.message)) from exc
    except (ValueError, TypeError) as exc:
        raise _failure(PanelError(422, "invalid_request", str(exc))) from exc


_CALL_STATUS = {"busy": 429, "timeout": 504, "too_large": 413, "process_exited": 409, "start_failed": 409}


@router.post("/contexts/{context_id}/call", responses=_CALL_RESPONSE)
async def panel_call(context_id: str, payload: ContextCall, request: Request) -> Response:
    """Forward a MiniApp page call to its resident panel.py (session-authenticated)."""
    # Forward a MiniApp page call to its resident panel.py (session-authenticated).
    #
    # Runs the blocking pipe call on a dedicated executor off the API event loop. Returns ``{result}`` as JSON, ``application/octet-stream`` with
    # dtype/shape headers for a NumPy array, or ``{error}`` for an author
    # exception, which does not end the process (FR-010/FR-011).
    from scistudio.panels.process import PanelCallError

    try:
        _bounded_json(payload.args, limit=8192)
        store = get_panel_contexts(request.app.state.runtime)
        context = store.get(context_id)
        if context.kind != "miniapp" or getattr(context, "process", None) is None:
            raise PanelError(400, "unsupported", "This context does not provide call")
        try:
            job = await asyncio.to_thread(context.process.call, payload.fn, payload.args)
        except PanelCallError as exc:
            raise PanelError(_CALL_STATUS.get(exc.code, 409), exc.code, exc.message) from exc
        # A close/project switch while the call ran must not deliver stale bytes.
        store.get(context_id)
        header = job.header or {}
        if header.get("type") == "error":
            return JSONResponse({"error": header.get("error")}, headers={"Cache-Control": "no-store"})
        if header.get("binary"):
            metadata = {"dtype": header["dtype"], "shape": header["shape"]}
            return Response(
                job.payload,
                media_type="application/octet-stream",
                headers={
                    "X-Panel-Dtype": str(header["dtype"]),
                    "X-Panel-Shape": json.dumps(header["shape"]),
                    "X-Panel-Metadata": json.dumps(metadata, allow_nan=False),
                    "Cache-Control": "no-store",
                },
            )
        result = {"result": header.get("result")}
        # FR-011: the subprocess is the authority on how large a result may be
        # (``max_result_bytes``, 64 MiB by default), and it already refused
        # anything over it with ``too_large``. Measuring again against the
        # read route's 20 MiB budget turned a legal 30 MiB result into a
        # ``read_budget`` refusal — one user-visible condition reported under
        # two different codes, and a limit no configuration could raise.
        _bounded_json(result, limit=max_result_bytes())
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except PanelError as exc:
        raise _failure(exc) from exc
    except (ValueError, TypeError) as exc:
        raise _failure(PanelError(422, "invalid_request", str(exc))) from exc


_WRITABLE_TIERS = ("project", "user")


def _save_answers(context: PanelContext, answers: dict[str, Any]) -> tuple[str, str, str | None]:
    """Normalize and write one submit; return ``(display path, submitted_at, project dir)``."""
    from scistudio.panels.questionnaire import QuestionnaireError, answers_document, load_spec, write_answers

    panel = context.panel
    if panel.owner_kind.value not in _WRITABLE_TIERS:
        raise PanelError(400, "unsupported", "Only a project or user MiniApp can take questionnaire answers")
    directory = Path(panel.root)
    spec, problems = load_spec(directory)
    if spec is None:
        detail = "; ".join(problems) if problems else "This MiniApp has no questionnaire.json"
        raise PanelError(409, "no_questionnaire", detail)
    try:
        document = answers_document(panel.id, spec, answers)
    except QuestionnaireError as exc:
        raise PanelError(422, "invalid_answers", str(exc)) from exc
    try:
        written = write_answers(directory, document)
    except OSError as exc:
        raise PanelError(500, "write_failed", f"Could not save the answers: {exc}") from exc
    project_dir = context.project_dir
    display = str(written)
    if project_dir:
        with contextlib.suppress(ValueError):
            display = written.resolve().relative_to(Path(project_dir).resolve()).as_posix()
    return display, str(document["submitted_at"]), (str(project_dir) if project_dir else None)


def _notify_session(panel_id: str, answers_path: str, project_dir: str | None) -> str | None:
    """Type the submit line into the MiniApp's agent session; return why not, or None."""
    from scistudio.api.routes.ai_pty import engine as _engine
    from scistudio.panels.questionnaire import notification_text

    recorded = _MINIAPP_SESSION_TABS.get(panel_id)
    if recorded is None or project_dir is None or Path(recorded[1]).resolve() != Path(project_dir).resolve():
        return "no_session"
    tab_id, cwd = recorded
    if not _engine.type_line_into_tab(tab_id, notification_text(panel_id, answers_path), expected_cwd=cwd):
        _MINIAPP_SESSION_TABS.pop(panel_id, None)
        return "session_ended"
    return None


@router.post(
    "/contexts/{context_id}/answers",
    response_model=SubmitAnswersResult,
    responses={**_ERRORS, 500: {"model": PanelFailureResponse}},
)
async def submit_answers(context_id: str, payload: ContextAnswers, request: Request) -> dict[str, Any]:
    """Save a MiniApp questionnaire submit and tell its agent session."""
    # Save a MiniApp questionnaire submit and tell its agent session (MiniApp FR-050/FR-051).
    #
    # The answers file is written first and is the source of truth: a session
    # that is gone, or an External AI mode with no session at all, still leaves
    # the answers where ``wait_for_answers`` and the agent read them, and the
    # page is told to send the user back to their AI chat.
    try:
        _bounded_json(payload.answers, limit=256 * 1024)
        store = get_panel_contexts(request.app.state.runtime)
        context = store.get(context_id)
        if context.kind != "miniapp":
            raise PanelError(400, "unsupported", "This context does not provide submitAnswers")
        path, submitted_at, project_dir = await asyncio.to_thread(_save_answers, context, payload.answers)
        reason = await asyncio.to_thread(_notify_session, context.panel.id, path, project_dir)
        return {
            "saved": True,
            "path": path,
            "submitted_at": submitted_at,
            "notified": reason is None,
            "reason": reason,
            "message": _NOTIFIED_MESSAGE if reason is None else _RETURN_MESSAGE,
        }
    except PanelError as exc:
        raise _failure(exc) from exc
    except (ValueError, TypeError) as exc:
        raise _failure(PanelError(422, "invalid_request", str(exc))) from exc


@router.get("/contexts/{context_id}/process", responses=_ERRORS)
def panel_process_status(context_id: str, request: Request) -> dict[str, Any]:
    try:
        context = get_panel_contexts(request.app.state.runtime).get(context_id)
        if context.kind != "miniapp" or getattr(context, "process", None) is None:
            raise PanelError(404, "no_process", "This context has no panel process")
        status: dict[str, Any] = context.process.status()
        return status
    except PanelError as exc:
        raise _failure(exc) from exc


@router.post("/contexts/{context_id}/process/restart", response_model=ContextResponse, responses=_ERRORS)
def panel_process_restart(context_id: str, request: Request) -> dict[str, Any]:
    try:
        store = get_panel_contexts(request.app.state.runtime)
        registry = getattr(request.app.state, "registry", None)
        return _context_response(request, store.restart(context_id, registry))
    except PanelError as exc:
        raise _failure(exc) from exc


@router.post("/contexts/{context_id}/process/stop", response_model=ContextResponse, responses=_ERRORS)
def panel_process_stop(context_id: str, request: Request) -> dict[str, Any]:
    try:
        store = get_panel_contexts(request.app.state.runtime)
        return _context_response(request, store.stop_process(context_id))
    except PanelError as exc:
        raise _failure(exc) from exc


@router.delete("/contexts/{context_id}", status_code=204)
def close_context(context_id: str, request: Request) -> Response:
    get_panel_contexts(request.app.state.runtime).close(context_id)
    return Response(status_code=204)


@router.post("/contexts/{context_id}/open", response_model=PreviewEnvelopeModel, responses=_ERRORS)
def open_child(context_id: str, payload: ContextOpen, request: Request) -> PreviewEnvelopeModel:
    try:
        envelope = get_panel_contexts(request.app.state.runtime).open_child(context_id, payload.ref)
        return PreviewEnvelopeModel(**envelope.to_dict())
    except PanelError as exc:
        raise _failure(exc) from exc


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
        result = {"truncated": False, "complete": True, **result}
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


def _static_response(request: Request, path: Path, token: str, *, bootstrap_proof: str | None = None) -> Response:
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
    if bootstrap_proof is not None:
        with path.open("rb") as source:
            if os.fstat(source.fileno()).st_size > MAX_SOURCE_BYTES:
                raise PanelError(413, "read_budget", "Panel entry exceeds 16 MiB source budget")
            document = source.read(MAX_SOURCE_BYTES + 1)
        if len(document) > MAX_SOURCE_BYTES:
            raise PanelError(413, "read_budget", "Panel entry exceeds 16 MiB source budget")
        return Response(bootstrap_entry(document, bootstrap_proof), media_type="text/html", headers=headers)
    return FileResponse(path, media_type=media_type(path), headers=headers)


@router.get("/t/{token}/assets/{panel_id}/{path:path}")
@router.options("/t/{token}/assets/{panel_id}/{path:path}", include_in_schema=False)
def panel_asset(token: str, panel_id: str, path: str, request: Request) -> Response:
    try:
        context = get_panel_contexts(request.app.state.runtime).by_token(token)
        if context.panel.id != panel_id:
            raise PanelError(403, "invalid_token", "Token does not authorize this panel")
        file = resolve_panel_file(context.panel.root, path)
        proof = context.bootstrap_proof if path == context.panel.entry else None
        return _static_response(request, file, token, bootstrap_proof=proof)
    except PanelError as exc:
        raise _failure(exc) from exc
    except ValueError as exc:
        raise _failure(PanelError(404, "invalid_asset", str(exc))) from exc


# The SDK major serves a fixed, reviewed file set: the dependency-free client,
# the shared stylesheet every panel links for the application's look, and the
# Preact component set panels assemble their interface from.
_SDK_FILES = (
    "scistudio-panel.js",
    "panel.css",
    "panel-ui.js",
    "renderers.js",
    "renderers.css",
    "renderer-array.js",
    "renderer-dataframe.js",
    "renderer-series.js",
    "renderer-text.js",
    "renderer-artifact.js",
    "renderer-plot.js",
    "renderer-collection.js",
    "renderer-composite.js",
    "renderer-base.js",
)


@router.get("/t/{token}/sdk/{major}/{name}")
@router.options("/t/{token}/sdk/{major}/{name}", include_in_schema=False)
def panel_sdk(token: str, major: str, name: str, request: Request) -> Response:
    try:
        get_panel_contexts(request.app.state.runtime).by_token(token)
        if major != "1":
            raise ValueError("Unsupported SDK major")
        if name not in _SDK_FILES:
            raise ValueError("Unknown SDK asset")
        return _static_response(request, resolve_panel_file(_STATIC_ROOT / "sdk", f"1/{name}"), token)
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
        if path.suffix.lower() == ".svg":
            # SVG is the one artifact format that is also a document. The
            # compiled Save path scrubbed it before writing the reader's file,
            # and these bytes are what a panel now saves, so scrubbing has to
            # happen here or that protection would have been dropped in the
            # move to panels. Display is unaffected: what this strips is scripts,
            # event handlers, and remote references.
            from scistudio.previewers.helpers import sanitize_svg

            sanitized, _removed = sanitize_svg(path.read_text(encoding="utf-8", errors="replace"))
            response: Response = Response(sanitized.encode("utf-8"), media_type="image/svg+xml")
            for header, value in _static_response(request, path, token).headers.items():
                if header.lower() not in ("content-type", "content-length"):
                    response.headers[header] = value
        else:
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
    """Start the panel service before workflows run; stop it at shutdown.

    Starting loads the catalog, subscribes the context store to the workflow
    events, and watches the panel tiers; stopping closes every context.
    """
    service = get_panel_service(app.state.runtime)
    try:
        await asyncio.to_thread(service.start, asyncio.get_running_loop())
    except Exception:
        logger.warning("panel service: start failed; the catalog loads on first use", exc_info=True)
    try:
        yield
    finally:
        service.stop()
