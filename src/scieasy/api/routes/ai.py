"""AI endpoints.

ADR-033 Phase 4 (T-ECA-401) removed the legacy single-call endpoints
(``POST /api/ai/generate-block``, ``POST /api/ai/suggest-workflow``,
``POST /api/ai/optimize-params``) along with their backing modules under
``scieasy.ai.{generation,synthesis,optimization,config}``. The embedded
coding agent (Phase 1+) replaces them.

Endpoints exposed by this module:

* ``GET /api/ai/status`` — discovery results for every registered agent
  provider (T-ECA-107).
* ``WS /api/ai/chat/{chat_id}`` — bidirectional chat WebSocket carrying
  the canonical :class:`scieasy.ai.agent.provider.AgentEvent` stream
  (T-ECA-107).
* ``POST /api/ai/permission-check`` / ``POST /api/ai/permission-decision``
  — hook-bridge / frontend permission flow (T-ECA-110).
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
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from scieasy.ai.agent import permission as permission_module
from scieasy.api.deps import get_agent_session_manager
from scieasy.api.schemas import (
    AgentEventEnvelope,
    ChatClientMessage,
    ErrorEnvelope,
    PermissionCheckRequest,
    PermissionCheckResponse,
    PermissionDecisionRequest,
    PermissionRequestEnvelope,
    ProviderStatusItem,
    ProviderStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Module-level singletons for ``Depends(...)`` and ``Query(...)`` defaults
# — keeps the function signatures clean of B008 violations.
_ProjectDirQuery = Query(..., description="Absolute path to the SciEasy project workspace")
_PermissionModeQuery = Query(
    "strict",
    description="Permission policy for tool calls: 'strict' (prompt for every tool) or 'bypass' (auto-approve)",
    pattern="^(strict|bypass)$",
)
_SessionManagerDep = Depends(get_agent_session_manager)


# Issue #791: STRICT is the safe-by-default; BYPASS must be opted into.
_VALID_PERMISSION_MODES: frozenset[str] = frozenset({"strict", "bypass"})


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


# ---------------------------------------------------------------------------
# T-ECA-107 — Embedded coding agent status + chat WebSocket.
# ---------------------------------------------------------------------------


def _discover_providers() -> list[ProviderStatusItem]:
    """Return ``ProviderStatusItem`` records for every registered agent provider.

    Phase 1 shipped only Claude Code; Phase 4 (T-ECA-402) adds Codex.
    Both providers are reported by ``GET /api/ai/status`` so the
    frontend's Provider selector knows which CLIs are installed. This
    helper is also reused by tests via DI override.
    """
    from scieasy.ai.agent.claude_code import ClaudeCodeProvider
    from scieasy.ai.agent.codex import CodexProvider

    providers: list[ProviderStatusItem] = []
    for provider_cls in (ClaudeCodeProvider, CodexProvider):
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
    permission_mode: str = _PermissionModeQuery,
    manager: Any = _SessionManagerDep,
) -> None:
    """Bidirectional chat WebSocket (ADR-033 §3 D5.2 / T-ECA-107).

    Query parameters:
        * ``project_dir`` — absolute path of the project workspace.
        * ``permission_mode`` — ``"strict"`` (default; prompt for every
          tool) or ``"bypass"`` (auto-approve). Issue #791: the previous
          implementation hardcoded ``BYPASS`` regardless of the frontend
          setting; the mode is now plumbed through from the WS query
          string. STRICT is the safe-by-default.

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
        await websocket.send_json(ErrorEnvelope(message=str(exc)).model_dump())
        await websocket.close(code=1008, reason="invalid project_dir")
        return
    # Issue #791: Defensive re-validation of permission_mode in case a
    # caller bypasses FastAPI's pattern validation (e.g. older proxies
    # that don't honour the regex constraint).
    if permission_mode not in _VALID_PERMISSION_MODES:
        logger.warning("chat_ws: rejecting permission_mode=%r", permission_mode)
        await websocket.send_json(
            ErrorEnvelope(
                message=f"invalid permission_mode: {permission_mode!r} (expected 'strict' or 'bypass')"
            ).model_dump()
        )
        await websocket.close(code=1008, reason="invalid permission_mode")
        return
    project_path = project_key
    # T-ECA-110: register this socket so ``POST /api/ai/permission-check``
    # can broadcast ``permission_request`` frames to it. Removed in the
    # ``finally`` block below so dead sockets do not leak into broadcasts.
    _active_chat_sockets[(project_key, chat_id)] = websocket
    session: Any | None = manager.get_session(project_path, chat_id)

    # #783 P2/P3: lazy resume. If no live session exists but we have
    # metadata on disk, spawn a resumed session now so the user does
    # not have to send a message to get the transcript replay+continue
    # flow working. Falls back to a fresh session if --resume fails.
    if session is None:
        metadata = manager.load_metadata(project_path, chat_id)
        if metadata is not None and metadata.session_id is not None:
            try:
                session = await _start_default_session(
                    manager=manager,
                    project_dir=project_path,
                    chat_id=chat_id,
                    resume_session_id=metadata.session_id,
                    permission_mode_str=permission_mode,
                )
            except Exception as exc:
                logger.warning(
                    "chat_ws: --resume of %s failed (%s); user must send a message to spawn a fresh session",
                    metadata.session_id,
                    exc,
                )
                # Surface an info banner so the user understands.
                with contextlib.suppress(Exception):
                    await websocket.send_json(
                        AgentEventEnvelope(
                            event={
                                "kind": "info",
                                "raw": {
                                    "message": (
                                        "Could not resume prior conversation; next message will start a fresh session."
                                    ),
                                },
                            }
                        ).model_dump()
                    )

    pump_task: asyncio.Task[None] | None = None

    async def _pump_subscriber(runtime: Any) -> None:
        """Forward every event from the runtime's subscriber queue to the WS.

        #783: replaces the old per-WS ``stream_events()`` consumer.
        Subscribing to the session runtime's fan-out queue means the
        background drain task remains the single consumer of the live
        stream — claude's stdout pipe stays drained even when no WS is
        attached.
        """
        # Snapshot + subscribe atomically (single asyncio tick — no
        # ``await`` between them — so the drain task cannot interleave
        # an event into the buffer or queue between snapshot and
        # subscribe). This avoids the duplicate/missed-event seam.
        snapshot = runtime.snapshot_buffer()
        q = runtime.subscribe()
        # Replay the ring buffer so a reconnecting WS sees the tail of
        # activity it missed.
        for event in snapshot:
            with contextlib.suppress(Exception):
                await websocket.send_json(AgentEventEnvelope(event=_serialise_agent_event(event)).model_dump())
        try:
            while True:
                event = await q.get()
                await websocket.send_json(AgentEventEnvelope(event=_serialise_agent_event(event)).model_dump())
        except (WebSocketDisconnect, asyncio.CancelledError):
            return
        except Exception as exc:  # pragma: no cover - defensive log
            logger.error("chat_ws.pump_subscriber: %s", exc, exc_info=True)
            with contextlib.suppress(Exception):
                await websocket.send_json(ErrorEnvelope(message=str(exc)).model_dump())
        finally:
            runtime.unsubscribe(q)

    # Reattach flow: subscribe to the runtime so we receive ongoing
    # events plus a replay of the recent ring buffer.
    if session is not None:
        runtime = manager.get_runtime(project_path, chat_id)
        if runtime is not None:
            pump_task = asyncio.create_task(_pump_subscriber(runtime))

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
                await websocket.send_json(ErrorEnvelope(message="invalid message").model_dump())
                continue

            if msg.type == "user_message":
                if session is None:
                    # First user_message on this WS — spawn the session.
                    try:
                        session = await _start_default_session(
                            manager=manager,
                            project_dir=project_path,
                            chat_id=chat_id,
                            permission_mode_str=permission_mode,
                        )
                    except Exception as exc:
                        logger.error("chat_ws: start_session failed: %s", exc)
                        await websocket.send_json(ErrorEnvelope(message=f"start_session failed: {exc}").model_dump())
                        break
                    runtime = manager.get_runtime(project_path, chat_id)
                    if runtime is not None:
                        pump_task = asyncio.create_task(_pump_subscriber(runtime))
                content = msg.content or ""
                try:
                    await session.send_user_message(content)
                except Exception as exc:
                    logger.error("chat_ws: send_user_message failed: %s", exc)
                    await websocket.send_json(ErrorEnvelope(message=str(exc)).model_dump())
            elif msg.type == "cancel":
                if session is not None:
                    # #783: ``cancel`` is the explicit teardown signal.
                    # Close the session so the user's intent (stop this
                    # conversation) is honoured even though plain WS
                    # disconnect no longer reaps the session.
                    try:
                        await session.cancel()
                    except Exception as exc:
                        logger.warning("chat_ws: session.cancel raised: %s", exc)
                    try:
                        await manager.close_session(project_path, chat_id)
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.warning("chat_ws: close_session after cancel raised: %s", exc)
                    session = None
            elif msg.type == "permission_decision":
                # T-ECA-110: signal the pending Event for this request_id.
                # Either the REST endpoint or the WS message is sufficient;
                # the frontend may choose either path.
                if msg.request_id is None or msg.decision is None:
                    await websocket.send_json(
                        ErrorEnvelope(message="permission_decision requires request_id and decision").model_dump()
                    )
                elif msg.decision not in ("approve", "deny"):
                    await websocket.send_json(
                        ErrorEnvelope(message=f"invalid permission decision: {msg.decision!r}").model_dump()
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
                await websocket.send_json(ErrorEnvelope(message=f"unknown message type: {msg.type!r}").model_dump())
    finally:
        # Remove the socket first so an in-flight broadcast cannot try to
        # send to a closing connection.
        _active_chat_sockets.pop((project_key, chat_id), None)
        # #783: cancel the WS pump only — the session stays alive so the
        # next attach can pick up the conversation. ``cancel`` is still
        # the explicit teardown path; idle TTL eviction is a follow-up
        # (issue tracked separately).
        if pump_task is not None:
            pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await pump_task
        # NOTE: ``close_session`` is deliberately NOT called here. The
        # background drain task in the session manager continues to
        # consume claude's stdout into the ring buffer + transcript
        # while the WS is disconnected. The session is reaped by:
        #   * explicit ``cancel`` message above, or
        #   * ``shutdown_all`` at FastAPI lifespan teardown.


async def _start_default_session(
    *,
    manager: Any,
    project_dir: Path,
    chat_id: str,
    resume_session_id: str | None = None,
    permission_mode_str: str = "strict",
) -> Any:
    """Spawn a Claude Code session with the real SciEasy system prompt + MCP config.

    Issue #775: replaced Phase 1 placeholders with calls to the real
    composers — without these the spawned agent has no idea what
    SciEasy is and zero MCP tools to call (mcpServers was empty).

    #783: added ``resume_session_id`` so the WS reattach path can
    rehydrate a prior conversation via ``claude --resume <id>``.

    Issue #791: ``permission_mode_str`` is now plumbed in from the WS
    query string (default ``"strict"``). The previous implementation
    hardcoded :attr:`PermissionMode.BYPASS` regardless of the user's
    frontend selection, which made STRICT mode unreachable.
    """
    from scieasy.ai.agent.claude_code import ClaudeCodeProvider
    from scieasy.ai.agent.provider import PermissionMode
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    provider = ClaudeCodeProvider()
    # Re-run the trusted-root sanitiser so CodeQL's taint flow stops
    # at this function boundary even though the WS route already
    # validated the same value. ``os.path.realpath`` +
    # ``os.path.commonpath`` is the pattern the ``py/path-injection``
    # query recognises — ``Path.resolve()`` is not.
    safe_project_dir = _resolve_project_key(project_dir)
    # Resolve the real system prompt + MCP config. The system prompt
    # contains tool documentation; the MCP config tells claude how to
    # spawn `scieasy mcp-bridge` for the 25 SciEasy tools.
    system_prompt = compose_system_prompt(safe_project_dir)
    mcp_config: dict[str, Any] = {
        "mcpServers": {
            "scieasy": {
                "command": "scieasy",
                "args": ["mcp-bridge"],
                "env": {
                    "SCIEASY_CHAT_ID": chat_id,
                    "SCIEASY_PROJECT_DIR": str(safe_project_dir),
                },
            }
        }
    }
    # Map the wire-format string to the enum value.
    permission_mode = PermissionMode.BYPASS if permission_mode_str == "bypass" else PermissionMode.STRICT
    return await manager.start_session(
        project_dir=project_dir,
        chat_id=chat_id,
        provider=provider,
        system_prompt=system_prompt,
        mcp_config=mcp_config,
        permission_mode=permission_mode,
        resume_session_id=resume_session_id,
    )


# ---------------------------------------------------------------------------
# #783 — Session persistence endpoints.
# ---------------------------------------------------------------------------


@router.get("/sessions")
async def list_sessions(
    project_dir: str = _ProjectDirQuery,
    manager: Any = _SessionManagerDep,
) -> dict[str, Any]:
    """List persisted session metadata for *project_dir* (#783).

    Reads every ``<project>/.scieasy/sessions/<chat_id>.json`` file and
    returns the parsed metadata, sorted by ``last_active`` descending.
    Drives the sessions sidebar so the user can see and reopen prior
    conversations after a backend restart.
    """
    try:
        safe_project_dir = _resolve_project_key(project_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sessions = manager.list_sessions(safe_project_dir)
    return {"sessions": [m.model_dump() for m in sessions]}


@router.get("/sessions/{chat_id}/transcript")
async def get_session_transcript(
    chat_id: str,
    project_dir: str = _ProjectDirQuery,
    manager: Any = _SessionManagerDep,
) -> StreamingResponse:
    """Stream a chat's full transcript as NDJSON (#783).

    Each emitted line is one historical ``AgentEvent`` dict. The
    streaming format keeps memory bounded for very long chats. The
    frontend replays the events to restore the chat view when a
    session is opened from the sidebar.
    """
    try:
        safe_project_dir = _resolve_project_key(project_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    import json as _json

    def _iter() -> Any:
        for entry in manager.iter_transcript_events(safe_project_dir, chat_id):
            yield (_json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")

    return StreamingResponse(_iter(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# #786 — Slash command discovery endpoint.
# ---------------------------------------------------------------------------


_FRONTMATTER_RE = None  # Lazy compile in helper below.


def _parse_slash_command_file(path: Path, *, default_name: str | None = None) -> dict[str, str]:
    """Extract ``name`` + ``description`` from a slash-command markdown file.

    Best-effort frontmatter parse:
    * If the file starts with ``---``, the YAML block up to the closing
      ``---`` is parsed and ``name`` / ``description`` keys are
      extracted.
    * Otherwise: ``default_name`` (or the filename stem) is used as the
      name, and the first non-empty / non-heading line is used as the
      description.

    Returns ``{"name": ..., "description": ...}``. Errors fall through
    to filename-based defaults so a malformed file never breaks the
    listing.
    """
    name = default_name if default_name is not None else path.stem
    description = ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return {"name": name, "description": description}

    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        # Walk to closing fence.
        body_start: int | None = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                body_start = i + 1
                break
        if body_start is not None:
            frontmatter = "\n".join(lines[1 : body_start - 1])
            try:
                import yaml as _yaml

                meta = _yaml.safe_load(frontmatter) or {}
            except Exception:
                meta = {}
            if isinstance(meta, dict):
                if isinstance(meta.get("name"), str):
                    name = meta["name"]
                if isinstance(meta.get("description"), str):
                    description = meta["description"]
            # Fallback description from first body line if still empty.
            if not description:
                for body_line in lines[body_start:]:
                    s = body_line.strip()
                    if s and not s.startswith("#"):
                        description = s
                        break
            return {"name": name, "description": description}

    # No frontmatter — first heading or first content line is the desc.
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("# "):
            description = s.lstrip("#").strip()
            break
        if not s.startswith("#"):
            description = s
            break
    return {"name": name, "description": description}


def _discover_slash_commands(project_dir: Path) -> list[dict[str, str]]:
    """Walk the 4 known slash-command roots and return a unified list.

    Sources (#786):

    * ``~/.claude/commands/*.md`` — user commands
    * ``~/.claude/skills/*/SKILL.md`` or ``skill.md`` — user skills
    * ``<project>/.claude/commands/*.md`` — project commands
    * ``~/.claude/plugins/*/commands/*.md`` — plugin commands

    ``project_dir`` is re-validated through :func:`_resolve_project_key`
    here so CodeQL's ``py/path-injection`` taint flow stops at this
    function boundary even though the route handler already sanitised
    the value. The sanitised result is stored in a fresh local
    (``safe_project_dir``) so CodeQL does not re-taint the parameter
    name on subsequent uses.
    """
    safe_project_dir = _resolve_project_key(project_dir)
    home = Path.home()
    out: list[dict[str, str]] = []

    def _add(source: str, file_path: Path, default_name: str | None = None) -> None:
        try:
            parsed = _parse_slash_command_file(file_path, default_name=default_name)
        except Exception as exc:
            logger.debug("slash command parse skipped %s: %s", file_path, exc)
            return
        out.append({**parsed, "source": source, "path": str(file_path)})

    # ~/.claude/commands/*.md
    user_cmds = home / ".claude" / "commands"
    if user_cmds.is_dir():
        for f in user_cmds.glob("*.md"):
            _add("user-commands", f)

    # ~/.claude/skills/<name>/SKILL.md or skill.md
    user_skills = home / ".claude" / "skills"
    if user_skills.is_dir():
        for skill_dir in user_skills.iterdir():
            if not skill_dir.is_dir():
                continue
            for candidate in ("SKILL.md", "skill.md"):
                f = skill_dir / candidate
                if f.is_file():
                    # Skills are keyed by directory name; the file stem
                    # is always "SKILL" or "skill" which is useless.
                    _add("user-skills", f, default_name=skill_dir.name)
                    break

    # <project>/.claude/commands/*.md
    # CodeQL: re-apply the explicit realpath + commonpath sanitiser
    # inline here. The query does NOT track sanitisation through the
    # ``_resolve_project_key`` helper call, so we inline the pattern at
    # the path-join site to make the taint clearance visible.
    candidate = os.path.realpath(os.fspath(safe_project_dir))
    safe_root = None
    for root in _PROJECT_DIR_ALLOWED_ROOTS:
        try:
            if os.path.commonpath([root, candidate]) == root:
                safe_root = candidate
                break
        except ValueError:
            continue
    if safe_root is not None:
        project_cmds = Path(safe_root) / ".claude" / "commands"
        if project_cmds.is_dir():
            for f in project_cmds.glob("*.md"):
                _add("project", f)

    # ~/.claude/plugins/*/commands/*.md
    plugins_root = home / ".claude" / "plugins"
    if plugins_root.is_dir():
        for plugin_dir in plugins_root.iterdir():
            cmds = plugin_dir / "commands"
            if cmds.is_dir():
                for f in cmds.glob("*.md"):
                    _add("plugin", f)

    return out


@router.get("/slash_commands")
async def list_slash_commands(
    project_dir: str = _ProjectDirQuery,
) -> dict[str, Any]:
    """List slash commands discoverable from the user's local Claude config (#786).

    Synchronous + cheap: reads filenames + frontmatter only. No caching
    so newly added files appear on the next dropdown open.
    """
    try:
        safe_project_dir = _resolve_project_key(project_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"commands": _discover_slash_commands(safe_project_dir)}


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
                    PermissionRequestEnvelope(
                        request_id=request_id,
                        tool={
                            "name": body.tool_name,
                            "input": body.tool_input,
                        },
                    ).model_dump()
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
