"""Session manager for concurrent agent chats.

Tracks live :class:`scieasy.ai.agent.provider.AgentSession` instances
keyed by ``(project_dir, chat_id)`` and enforces the per-project
concurrent-chat cap (default 5; spec §3 OQ3). Persists per-session
metadata under ``{project_dir}/.scieasy/sessions/<chat_id>.json``.

Phase 1 ships the stub class; T-ECA-106 implements the actual lifecycle
management, metadata persistence, and FastAPI lifespan integration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from scieasy.ai.agent.provider import AgentSession


class AgentSessionManager:
    """Owns and arbitrates live agent sessions for one or more projects.

    Invariants (enforced by the T-ECA-106 implementation):

    * At most :attr:`DEFAULT_CONCURRENT_CAP` live sessions per
      ``project_dir``; the 6th ``start_session`` raises
      :class:`scieasy.ai.agent.errors.AgentSessionError`.
    * Session metadata is written to disk BEFORE the subprocess is
      spawned, so a crashed manager can still inspect what was
      attempted.
    * ``shutdown_all`` is safe to call during FastAPI lifespan
      teardown; it awaits every live session's ``close()`` even if
      individual sessions raise.

    Class attributes
    ----------------
    DEFAULT_CONCURRENT_CAP
        Default per-project concurrent-chat cap. Overridable via
        ``{project}/.scieasy/settings.json``.
    """

    DEFAULT_CONCURRENT_CAP: ClassVar[int] = 5

    def start_session(
        self,
        *,
        project_dir: Path,
        chat_id: str,
        **kwargs: Any,
    ) -> AgentSession:
        """Spawn a new session for ``(project_dir, chat_id)``.

        Parameters
        ----------
        project_dir
            Absolute path to the SciEasy project workspace.
        chat_id
            Stable chat identifier; the same id may be reused only
            after the prior session is closed.
        **kwargs
            Additional spawn parameters forwarded to the provider's
            ``start_session`` (system prompt, MCP config, resume id,
            permission mode).

        Returns
        -------
        AgentSession
            Live session handle.

        Raises
        ------
        NotImplementedError
            Always, in Phase 1. Implementation lands in T-ECA-106.
        """
        raise NotImplementedError("AgentSessionManager.start_session is implemented in T-ECA-106")

    def get_session(self, project_dir: Path, chat_id: str) -> AgentSession | None:
        """Return the live session for ``(project_dir, chat_id)`` or ``None``.

        Raises
        ------
        NotImplementedError
            Always, in Phase 1. Implementation lands in T-ECA-106.
        """
        raise NotImplementedError("AgentSessionManager.get_session is implemented in T-ECA-106")

    async def close_session(self, project_dir: Path, chat_id: str) -> None:
        """Close one session; leave its on-disk metadata in place.

        Raises
        ------
        NotImplementedError
            Always, in Phase 1. Implementation lands in T-ECA-106.
        """
        raise NotImplementedError("AgentSessionManager.close_session is implemented in T-ECA-106")

    async def shutdown_all(self) -> None:
        """Close every live session; called from FastAPI lifespan teardown.

        Raises
        ------
        NotImplementedError
            Always, in Phase 1. Implementation lands in T-ECA-106.
        """
        raise NotImplementedError("AgentSessionManager.shutdown_all is implemented in T-ECA-106")
