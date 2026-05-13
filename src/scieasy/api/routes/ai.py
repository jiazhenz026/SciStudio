"""AI endpoints.

Legacy (Phase 0) endpoints under ``POST /api/ai/{generate-block,suggest-workflow,optimize-params}``
remain here untouched — they are slated for deletion in Phase 4 of the
embedded coding agent rollout (ADR-033), not now.

New (Phase 1 / ADR-033 / T-ECA-107) endpoints added in this module:

* ``GET /api/ai/status`` — discovery results for every registered agent
  provider.
* ``WS /api/ai/chat/{chat_id}`` — bidirectional chat WebSocket carrying
  the canonical :class:`scieasy.ai.agent.provider.AgentEvent` stream.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import ValidationError

from scieasy.ai.agent import permission as permission_module
from scieasy.api.deps import get_agent_session_manager
from scieasy.api.schemas import (
    AIGenerateBlockRequest,
    AIGenerateBlockResponse,
    AIOptimizeParamsRequest,
    AIOptimizeParamsResponse,
    AISuggestWorkflowRequest,
    AISuggestWorkflowResponse,
    ChatClientMessage,
    PermissionCheckRequest,
    PermissionCheckResponse,
    PermissionDecisionRequest,
    ProviderStatusItem,
    ProviderStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Module-level singletons for ``Depends(...)`` and ``Query(...)`` defaults
# — keeps the function signatures clean of B008 violations.
_ProjectDirQuery = Query(..., description="Absolute path to the SciEasy project workspace")
_SessionManagerDep = Depends(get_agent_session_manager)


# ---------------------------------------------------------------------------
# T-ECA-110 — Active chat WebSocket registry.
#
# When ``POST /api/ai/permission-check`` needs to ask the user, it must
# push a ``permission_request`` frame to the WebSocket connection for
# the relevant ``(project_dir, chat_id)``. The chat_ws handler inserts
# itself on accept and removes itself on close.
#
# Single-process, single-user deployment per ADR-033 §3 D5.2 — for
# multi-process this registry would need to move out-of-process.
# ---------------------------------------------------------------------------


_active_chat_sockets: dict[tuple[Path, str], WebSocket] = {}


_PROJECT_DIR_ALLOWED_ROOTS: tuple[str, ...] = (
    os.path.realpath(os.path.expanduser("~")),
    os.path.realpath(tempfile.gettempdir()),
)


def _resolve_project_key(project_dir: str | Path) -> Path:
    """Normalise a ``project_dir`` query argument into the registry key shape.

    The value flows from a WebSocket query string straight into a
    subprocess ``cwd`` (via ``AgentSessionManager.start_session``) and
    into a process registry keyed by absolute path. Without a sanity
    bound, a malicious client could ask the agent to spawn ``claude``
    in arbitrary filesystem locations (``/etc``, ``C:\\Windows``, ...).

    Sanitiser contract: resolve to an absolute path and require it to
    fall under one of the trusted roots — the user's home directory
    (where SciEasy projects live) or the system temp directory (where
    ``pytest`` ``tmp_path`` fixtures land). Anything else is rejected
    with ``ValueError``, which the route translates to a
    ``WebSocketDisconnect`` / HTTP 400.

    Uses the ``os.path.realpath`` + ``os.path.commonpath`` pattern that
    CodeQL ``py/path-injection`` recognises as a sanitiser.
    ``pathlib.Path.is_relative_to`` is functionally equivalent but is
    not recognised by the query.
    """
    candidate = os.path.realpath(os.fspath(project_dir))
    for root in _PROJECT_DIR_ALLOWED_ROOTS:
        try:
            if os.path.commonpath([root, candidate]) == root:
                return Path(candidate)
        except ValueError:
            # commonpath raises ValueError when paths are on different
            # drives (Windows) or when one is absolute and one relative.
            continue
    raise ValueError(f"project_dir must be under user home or system temp; got {candidate}")


@router.post("/generate-block", response_model=AIGenerateBlockResponse)
async def generate_block(body: AIGenerateBlockRequest) -> dict[str, Any]:
    """Generate a block from a natural-language description.

    Calls the AI block generator pipeline: category inference, prompt
    construction, LLM call, code extraction, validation, and retry.

    Returns
    -------
    dict
        Generated code, block name, validation status, report, and category.

    Raises
    ------
    HTTPException 503
        When the AI optional dependencies are not installed.
    HTTPException 500
        On any other generation error.
    """
    try:
        from scieasy.ai.generation.block_generator import generate_block as ai_generate_block

        result = ai_generate_block(body.description, body.block_category)
        return {
            "code": result.code,
            "block_name": result.block_name,
            "validation_passed": result.validation_report.get("passed", False),
            "validation_report": result.validation_report,
            "category": result.category,
        }
    except ImportError as exc:
        logger.warning("AI features unavailable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="AI features require: pip install scieasy[ai]",
        ) from exc
    except Exception as exc:
        logger.error("Block generation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/suggest-workflow", response_model=AISuggestWorkflowResponse)
async def suggest_workflow(body: AISuggestWorkflowRequest) -> dict[str, Any]:
    """Return a clear Phase 9 placeholder for workflow suggestion.

    The wired implementation lives in PR #245 and will replace this stub
    once that PR merges.
    """
    raise HTTPException(status_code=501, detail="AI workflow suggestion will arrive in Phase 9.")


@router.post("/optimize-params", response_model=AIOptimizeParamsResponse)
async def optimize_params_endpoint(body: AIOptimizeParamsRequest) -> dict[str, Any]:
    """Suggest improved parameter values for a block using AI.

    Analyses intermediate results and the block's config schema to
    propose parameter changes that may improve workflow outcomes.
    """
    try:
        from scieasy.ai.optimization.param_optimizer import optimize_params

        result = optimize_params(
            block_id=body.block_id,
            intermediate_results=body.intermediate_results,
            search_space=body.search_space,
        )
        return result
    except ImportError:
        raise HTTPException(status_code=503, detail="AI dependencies not installed") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# T-ECA-107 — Embedded coding agent status + chat WebSocket.
# ---------------------------------------------------------------------------


def _discover_providers() -> list[ProviderStatusItem]:
    """Return ``ProviderStatusItem`` records for every registered agent provider.

    Phase 1 ships only the Claude Code provider; the Codex provider lands
    in Phase 4 (T-ECA-410). This helper is invoked by the
    ``GET /api/ai/status`` route and is also reused by tests via DI
    override.
    """
    from scieasy.ai.agent.claude_code import ClaudeCodeProvider

    providers: list[ProviderStatusItem] = []
    for provider_cls in (ClaudeCodeProvider,):
        status = provider_cls.discover()
        providers.append(
            ProviderStatusItem(
                name=status.name,
                available=status.available,
                binary_path=str(status.binary_path) if status.binary_path else None,
                version=status.version,
                logged_in=status.logged_in,
                install_hint=status.install_hint,
            )
        )
    return providers


@router.get("/status", response_model=ProviderStatusResponse)
async def ai_status() -> ProviderStatusResponse:
    """Return discovery results for every registered agent provider (T-ECA-107)."""
    return ProviderStatusResponse(providers=_discover_providers())


def _serialise_agent_event(event: Any) -> dict[str, Any]:
    """Convert an ``AgentEvent`` (dataclass) to a JSON-serialisable dict."""
    if dataclasses.is_dataclass(event):
        try:
            return dataclasses.asdict(event)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pass
    kind = getattr(event, "kind", "other")
    raw = getattr(event, "raw", {})
    return {"kind": kind, "raw": raw}


@router.websocket("/chat/{chat_id}")
async def chat_ws(
    websocket: WebSocket,
    chat_id: str,
    project_dir: str = _ProjectDirQuery,
    manager: Any = _SessionManagerDep,
) -> None:
    """Bidirectional chat WebSocket (ADR-033 §3 D5.2 / T-ECA-107).

    Inbound messages (client → server):
        * ``{"type": "user_message", "content": str}``
        * ``{"type": "cancel"}``
        * ``{"type": "permission_decision", ...}`` — accepted for forward
          compat but ignored in Phase 1 (T-ECA-110 wires the handler).

    Outbound messages (server → client):
        * ``{"type": "agent_event", "event": {...}}``
        * ``{"type": "session_ended", "reason": "..."}``
        * ``{"type": "error", "message": "..."}``

    The first ``user_message`` triggers session creation (or attaches to
    an existing session for the same ``chat_id``). Disconnection closes
    the session via ``manager.close_session`` (metadata file is left in
    place).
    """
    await websocket.accept()
    try:
        project_key = _resolve_project_key(project_dir)
    except ValueError as exc:
        logger.warning("chat_ws: rejecting project_dir=%r: %s", project_dir, exc)
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close(code=1008, reason="invalid project_dir")
        return
    project_path = project_key
    # T-ECA-110: register this socket so ``POST /api/ai/permission-check``
    # can broadcast ``permission_request`` frames to it. Removed in the
    # ``finally`` block below so dead sockets do not leak into broadcasts.
    _active_chat_sockets[(project_key, chat_id)] = websocket
    session: Any | None = manager.get_session(project_path, chat_id)
    pump_task: asyncio.Task[None] | None = None

    async def _pump_events(active_session: Any) -> None:
        """Forward every canonical event from the session stream to the WebSocket."""
        try:
            async for event in active_session.stream_events():
                await websocket.send_json({"type": "agent_event", "event": _serialise_agent_event(event)})
        except (WebSocketDisconnect, asyncio.CancelledError):
            return
        except Exception as exc:  # pragma: no cover - defensive log
            logger.error("chat_ws.pump_events: %s", exc, exc_info=True)
            with contextlib.suppress(Exception):
                await websocket.send_json({"type": "error", "message": str(exc)})

    # Reattach flow: if a live session already exists for (project, chat_id),
    # start the event pump now so reconnecting clients receive ongoing /
    # subsequent agent_event frames. Without this, the pump_task was only
    # created on the first user_message path and reattach hung silently.
    if session is not None:
        pump_task = asyncio.create_task(_pump_events(session))

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            try:
                msg = ChatClientMessage.model_validate_json(raw)
            except ValidationError as exc:
                logger.warning("chat_ws: invalid client message: %s", exc)
                await websocket.send_json({"type": "error", "message": "invalid message"})
                continue

            if msg.type == "user_message":
                if session is None:
                    # First user_message on this WS — spawn the session.
                    try:
                        session = await _start_default_session(
                            manager=manager,
                            project_dir=project_path,
                            chat_id=chat_id,
                        )
                    except Exception as exc:
                        logger.error("chat_ws: start_session failed: %s", exc)
                        await websocket.send_json({"type": "error", "message": f"start_session failed: {exc}"})
                        break
                    pump_task = asyncio.create_task(_pump_events(session))
                content = msg.content or ""
                try:
                    await session.send_user_message(content)
                except Exception as exc:
                    logger.error("chat_ws: send_user_message failed: %s", exc)
                    await websocket.send_json({"type": "error", "message": str(exc)})
            elif msg.type == "cancel":
                if session is not None:
                    await session.cancel()
            elif msg.type == "permission_decision":
                # T-ECA-110: signal the pending Event for this request_id.
                # Either the REST endpoint or the WS message is sufficient;
                # the frontend may choose either path.
                if msg.request_id is None or msg.decision is None:
                    await websocket.send_json(
                        {"type": "error", "message": "permission_decision requires request_id and decision"}
                    )
                elif msg.decision not in ("approve", "deny"):
                    await websocket.send_json(
                        {"type": "error", "message": f"invalid permission decision: {msg.decision!r}"}
                    )
                else:
                    ok = permission_module.signal_decision(
                        msg.request_id,
                        msg.decision,
                        reason=None,
                    )
                    if not ok:
                        logger.warning(
                            "chat_ws: unknown permission request_id %s",
                            msg.request_id,
                        )
            else:
                logger.warning("chat_ws: unknown message type: %s", msg.type)
    finally:
        # Remove the socket first so an in-flight broadcast cannot try to
        # send to a closing connection.
        _active_chat_sockets.pop((project_key, chat_id), None)
        if pump_task is not None:
            pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await pump_task
        if session is not None:
            try:
                await manager.close_session(project_path, chat_id)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("chat_ws: close_session failed: %s", exc)


async def _start_default_session(
    *,
    manager: Any,
    project_dir: Path,
    chat_id: str,
) -> Any:
    """Spawn a Claude Code session with placeholder system prompt + MCP config.

    Encapsulated so tests can monkey-patch it; the real composition lives
    in T-ECA-204 (system prompt builder) and uses the static config-file
    emitter (T-ECA-108). For Phase 1 a minimal placeholder is
    sufficient.
    """
    from scieasy.ai.agent.claude_code import ClaudeCodeProvider
    from scieasy.ai.agent.provider import PermissionMode

    provider = ClaudeCodeProvider()
    return await manager.start_session(
        project_dir=project_dir,
        chat_id=chat_id,
        provider=provider,
        system_prompt="SciEasy agent (Phase 1 placeholder prompt).",
        mcp_config={"mcpServers": {}},
        permission_mode=PermissionMode.STRICT,
    )


# ---------------------------------------------------------------------------
# T-ECA-110 — Permission endpoints.
#
# ``scieasy hook-bridge`` POSTs to /permission-check; the frontend POSTs
# to /permission-decision (or sends the equivalent WS message).
# ---------------------------------------------------------------------------


def _resolve_policy(
    manager: Any,
    project_dir: str | None,
    chat_id: str,
) -> Any:
    """Construct a :class:`PermissionPolicy` for a chat session.

    Read the session's metadata file (if it exists) to detect bypass mode;
    fall back to STRICT if the metadata is missing or unreadable (the
    safe default). The metadata path is canonical:
    ``{project_dir}/.scieasy/sessions/{chat_id}.json``.
    """
    from scieasy.ai.agent.permission import PermissionPolicy
    from scieasy.ai.agent.provider import PermissionMode

    mode = PermissionMode.STRICT
    if project_dir is not None:
        try:
            metadata = manager.load_metadata(Path(project_dir), chat_id)
        except Exception:  # pragma: no cover - defensive
            metadata = None
        if metadata is not None and getattr(metadata, "bypass_mode", False):
            mode = PermissionMode.BYPASS
    return PermissionPolicy(mode)


@router.post("/permission-check", response_model=PermissionCheckResponse)
async def permission_check(
    body: PermissionCheckRequest,
    manager: Any = _SessionManagerDep,
) -> PermissionCheckResponse:
    """Decide whether a tool call should be approved.

    Called by ``scieasy hook-bridge`` for every PreToolUse hook. Two
    paths:

    * Auto-approve (``policy.should_auto_approve`` returns True): respond
      immediately with ``{"action": "approve"}``.
    * Ask: register a pending decision, broadcast a ``permission_request``
      frame on the chat WebSocket, and await the user's reply with the
      :data:`permission_module.DECISION_TIMEOUT_SECONDS` timeout. On
      timeout, respond with ``{"action": "deny", "reason": "timed_out"}``.
    """
    policy = _resolve_policy(manager, body.project_dir, body.chat_id)
    if policy.should_auto_approve(body.tool_name, body.tool_input):
        logger.info(
            "permission_check: auto-approve tool=%s chat_id=%s",
            body.tool_name,
            body.chat_id,
        )
        return PermissionCheckResponse(action="approve")

    # Ask path. Register first so a fast WS reply cannot race the wait().
    request_id, event = permission_module.register_pending_decision()

    # Best-effort broadcast: if the WS is missing, the frontend cannot
    # deliver an answer and we time out — but other operational paths
    # (e.g. POST /permission-decision driven by a test or admin tool)
    # are still viable, so we do not return early.
    if body.project_dir is not None:
        try:
            key = (_resolve_project_key(body.project_dir), body.chat_id)
        except ValueError as exc:
            logger.warning("permission_check: rejecting project_dir=%r: %s", body.project_dir, exc)
            permission_module.consume_pending_decision(request_id)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        ws = _active_chat_sockets.get(key)
        if ws is not None:
            try:
                await ws.send_json(
                    {
                        "type": "permission_request",
                        "request_id": request_id,
                        "tool": {
                            "name": body.tool_name,
                            "input": body.tool_input,
                        },
                    }
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "permission_check: failed to broadcast permission_request: %s",
                    exc,
                )
        else:
            logger.warning(
                "permission_check: no active WS for chat_id=%s (will rely on REST decision)",
                body.chat_id,
            )

    timeout = permission_module.DECISION_TIMEOUT_SECONDS
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except TimeoutError:
        permission_module.consume_pending_decision(request_id)
        logger.warning(
            "permission_check: timed out chat_id=%s tool=%s (after %.1fs)",
            body.chat_id,
            body.tool_name,
            timeout,
        )
        return PermissionCheckResponse(
            action="deny",
            reason="timed_out",
            request_id=request_id,
        )

    payload = permission_module.consume_pending_decision(request_id) or {}
    decision = payload.get("decision", "deny")
    reason = payload.get("reason")
    if decision not in ("approve", "deny"):
        # Defensive: signal_decision validates upstream, but if a future
        # path lets a malformed value through, treat it as deny so we
        # fail closed.
        logger.error(
            "permission_check: invalid decision %r for request_id=%s; coercing to deny",
            decision,
            request_id,
        )
        decision = "deny"
        reason = "invalid_decision"
    return PermissionCheckResponse(action=decision, reason=reason, request_id=request_id)


@router.post("/permission-decision", status_code=204)
async def permission_decision(body: PermissionDecisionRequest) -> None:
    """Receive the user's permission decision and unblock the hook.

    The frontend POSTs here when the user clicks Approve / Deny in the
    permission UI. Equivalent in effect to the
    ``permission_decision`` WS message, but a separate REST endpoint is
    useful for non-WS clients (e.g. an admin script) and for the test
    matrix.

    Returns
    -------
    204 No Content
        On success.

    Raises
    ------
    HTTPException 400
        If the decision is not one of ``"approve"`` / ``"deny"``.
    HTTPException 404
        If the request_id is unknown (already consumed or never registered).
    """
    if body.decision not in ("approve", "deny"):
        raise HTTPException(status_code=400, detail=f"invalid decision: {body.decision!r}")
    ok = permission_module.signal_decision(body.request_id, body.decision, reason=body.reason)
    if not ok:
        raise HTTPException(status_code=404, detail=f"unknown request_id: {body.request_id}")
