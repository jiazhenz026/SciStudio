"""Provider and session Protocols for the embedded coding agent runtime.

This module defines the structural types exchanged across the agent
subsystem boundary. The concrete provider implementations
(``ClaudeCodeProvider`` in :mod:`scieasy.ai.agent.claude_code`, the
future ``CodexProvider``) conform to :class:`AgentProvider`; the
sessions they return conform to :class:`AgentSession`.

The Protocols here intentionally contain no business logic — they are
the contract surface that downstream code (API routes, session manager,
permission policy) programs against. The classes whose bodies use
``...`` are :pep:`544` Protocols; runtime implementations are provided
in sibling modules.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Protocol


class PermissionMode(Enum):
    """User-selected permission policy mode for a chat session.

    Values are the strings persisted in
    ``{project}/.scieasy/sessions/<chat_id>.json`` and exchanged over
    the WebSocket protocol; do not rename without a migration.

    Attributes
    ----------
    STRICT
        Every write-class tool call (Edit / Write / Bash / WebFetch /
        every write MCP tool) requires per-call user approval. This is
        the default for new chats.
    BYPASS
        All tool calls are auto-approved, equivalent to launching
        Claude Code with ``--dangerously-skip-permissions``. The
        frontend renders a persistent red banner while bypass is
        active.
    """

    STRICT = "strict"
    BYPASS = "bypass"


@dataclass(frozen=True)
class ProviderStatus:
    """Discovery result for an agent provider on the current machine.

    Returned by :meth:`AgentProvider.discover`. Consumed by the
    ``GET /api/ai/status`` route to drive the frontend's status banner.

    Attributes
    ----------
    name
        Stable provider identifier (e.g. ``"claude-code"``,
        ``"codex"``). Matches ``AgentProvider.name``.
    available
        ``True`` if the binary was located AND a ``--version`` probe
        succeeded.
    binary_path
        Absolute path to the discovered binary, or ``None`` if not
        found.
    version
        ``--version`` output trimmed of whitespace, or ``None`` if not
        probed.
    logged_in
        Heuristic login-state probe result; ``False`` if the binary is
        not available or the probe failed.
    install_hint
        Platform-appropriate install command to surface in the UI when
        ``available`` is ``False``.
    """

    name: str
    available: bool
    binary_path: Path | None
    version: str | None
    logged_in: bool
    install_hint: str | None


@dataclass
class AgentEvent:
    """Canonical event emitted by an :class:`AgentSession` event stream.

    The base envelope carries the canonical ``kind`` and the original
    parsed JSON payload as ``raw``. T-ECA-103 adds the typed sub-events
    below (``InitEvent``, ``AssistantTextDeltaEvent`` …) plus the
    ``OtherEvent`` catch-all for unknown kinds (spec §3 OQ5).

    Attributes
    ----------
    kind
        Canonical event kind string. Unknown kinds are surfaced as
        ``"other"`` with the original ``kind`` value preserved in
        ``raw["kind"]`` (or ``raw["type"]`` if the provider used that
        field name).
    raw
        The original parsed JSON payload as a dict. Provider-specific
        fields are preserved here for forensic logging.
    """

    kind: str
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Typed canonical event subclasses (T-ECA-103)
#
# Subclasses inherit ``kind`` and ``raw`` from the base. ``kw_only=True`` is
# used so we can declare additional non-default fields after ``raw`` (which
# has a ``default_factory``). All subclasses are dataclasses; consumers
# match on ``isinstance`` or on ``kind``.
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class InitEvent(AgentEvent):
    """First event in every session; carries the provider-assigned session id."""

    session_id: str
    schema_version: str | None = None
    model: str | None = None


@dataclass(kw_only=True)
class AssistantTextDeltaEvent(AgentEvent):
    """Streaming assistant-text chunk. Multiple deltas concatenate into a turn's text."""

    delta: str


@dataclass(kw_only=True)
class ToolUseEvent(AgentEvent):
    """Agent announced a tool invocation; the matching ``ToolResultEvent`` follows."""

    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str


@dataclass(kw_only=True)
class ToolResultEvent(AgentEvent):
    """Result of a previously announced tool invocation, correlated by ``tool_use_id``."""

    tool_use_id: str
    output: str | dict[str, Any]
    is_error: bool = False


@dataclass(kw_only=True)
class PermissionRequestEvent(AgentEvent):
    """Synthetic event surfaced by the hook bridge when user approval is required.

    Note: Claude Code emits this through the ``PreToolUse`` hook, not the
    raw stream-json. The hook bridge is responsible for synthesising this
    event onto the canonical stream (T-ECA-110).
    """

    tool_name: str
    tool_input: dict[str, Any]
    request_id: str


@dataclass(kw_only=True)
class ErrorEvent(AgentEvent):
    """Stream-level error reported by the provider subprocess."""

    message: str
    error_type: str | None = None


@dataclass(kw_only=True)
class DoneEvent(AgentEvent):
    """Terminal event marking the end of an agent turn."""


@dataclass(kw_only=True)
class OtherEvent(AgentEvent):
    """Catch-all for unknown event kinds (spec §3 OQ5).

    Unknown kinds are surfaced to the frontend transparently; the original
    payload lives in ``raw`` for forensic logging.
    """


class AgentProvider(Protocol):
    """Structural type for an embedded coding agent provider.

    Implementations wrap a locally-installed coding-agent CLI (Claude
    Code, Codex) and expose a uniform discovery / session-spawn
    surface. Providers do NOT carry per-session state; sessions live in
    the returned :class:`AgentSession` instances and are owned by
    :class:`scieasy.ai.agent.session.AgentSessionManager`.

    Class attributes
    ----------------
    name
        Stable identifier persisted in session metadata.
    binary_name
        Bare binary filename to search for on PATH and the fallback
        list (``"claude"``, ``"codex"``).
    """

    name: ClassVar[str]
    binary_name: ClassVar[str]

    @classmethod
    def discover(cls) -> ProviderStatus:
        """Locate the provider's binary and probe its availability + login state.

        Returns
        -------
        ProviderStatus
            Discovery result. ``available`` is ``False`` if the binary
            cannot be found; ``logged_in`` is a best-effort heuristic
            (spec §3 OQ4).
        """
        ...

    def start_session(
        self,
        *,
        project_dir: Path,
        system_prompt: str,
        mcp_config: dict[str, Any],
        resume_session_id: str | None,
        permission_mode: PermissionMode,
    ) -> AgentSession:
        """Spawn a new agent subprocess and return an active session handle.

        Parameters
        ----------
        project_dir
            Absolute path to the SciEasy project directory; used as the
            subprocess ``cwd`` and as the root for ``.scieasy/``
            artefacts (mcp.json, hook config, session metadata).
        system_prompt
            Already-composed three-tier system prompt to pass via
            ``--append-system-prompt``.
        mcp_config
            MCP configuration dict; serialized to a temp file and
            passed via ``--mcp-config``.
        resume_session_id
            If provided, passed as ``--resume <id>`` to continue a
            prior conversation.
        permission_mode
            Selects strict per-call approval vs. bypass mode.

        Returns
        -------
        AgentSession
            Live session whose ``stream_events()`` is ready to be
            iterated.
        """
        ...


class AgentSession(Protocol):
    """Structural type for a live agent subprocess + its IPC channels.

    One :class:`AgentSession` corresponds to exactly one running CLI
    subprocess. The session may be multi-turn: ``send_user_message`` is
    callable repeatedly without closing stdin.

    Attributes
    ----------
    session_id
        Provider-assigned session identifier, populated from the first
        ``init`` event in the stream. ``None`` before the init event
        arrives.
    pid
        Operating-system process id of the spawned subprocess.
    """

    session_id: str | None
    pid: int

    async def send_user_message(self, content: str) -> None:
        """Send a user-turn message to the agent subprocess.

        Parameters
        ----------
        content
            The user message text. Written to the subprocess stdin as
            a JSON envelope; stdin is NOT closed afterwards (CC
            supports multi-turn over one process).
        """
        ...

    async def cancel(self) -> None:
        """Cancel any in-flight agent turn.

        Implementations tree-kill the subprocess group so that any
        ``Bash`` child processes spawned by the agent are also
        terminated.
        """
        ...

    def stream_events(self) -> AsyncIterator[AgentEvent]:
        """Asynchronously yield canonical :class:`AgentEvent`s.

        The iterator terminates when the subprocess exits cleanly or
        raises :class:`scieasy.ai.agent.errors.AgentStreamError` on
        unrecoverable parse failure.
        """
        ...

    async def close(self) -> None:
        """Await subprocess exit and release any provider-owned resources.

        Idempotent: calling ``close()`` on an already-closed session is
        a no-op. Implementations should release temp files (mcp.json,
        prompt file) here.
        """
        ...
