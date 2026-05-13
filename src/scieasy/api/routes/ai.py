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

from scieasy.api.deps import get_agent_session_manager
from scieasy.api.schemas import (
    AIGenerateBlockRequest,
    AIGenerateBlockResponse,
    AIOptimizeParamsRequest,
    AIOptimizeParamsResponse,
    AISuggestWorkflowRequest,
    AISuggestWorkflowResponse,
    ChatClientMessage,
    ProviderStatusItem,
    ProviderStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Module-level singletons for ``Depends(...)`` and ``Query(...)`` defaults
# — keeps the function signatures clean of B008 violations.
_ProjectDirQuery = Query(..., description="Absolute path to the SciEasy project workspace")
_SessionManagerDep = Depends(get_agent_session_manager)


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
    project_path = Path(project_dir)
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
                # Forward-compatible: handled by T-ECA-110.
                logger.debug("chat_ws: ignoring permission_decision (T-ECA-110)")
            else:
                logger.warning("chat_ws: unknown message type: %s", msg.type)
    finally:
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
