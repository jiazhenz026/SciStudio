"""Session manager for concurrent agent chats.

Tracks live :class:`scieasy.ai.agent.provider.AgentSession` instances
keyed by ``(project_dir, chat_id)`` and enforces the per-project
concurrent-chat cap (default 5; spec §3 OQ3). Persists per-session
metadata under ``{project_dir}/.scieasy/sessions/<chat_id>.json``.

Implementation notes (spec §5 T-ECA-106):

* :class:`SessionMetadata` is a Pydantic v2 model used to validate the
  on-disk JSON before write and after read.
* Metadata is written BEFORE the subprocess is spawned so a crash of
  the manager process still leaves a forensic record of the attempted
  session.
* :func:`get_session_manager` returns the module-level singleton used
  by API routes (registered through ``api/deps.py``).
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from scieasy.ai.agent.errors import AgentSessionError
from scieasy.ai.agent.provider import (
    AgentProvider,
    AgentSession,
    PermissionMode,
)

logger = logging.getLogger(__name__)


def _utc_now_isoformat() -> str:
    """Return current UTC time formatted as ISO-8601 with the ``+00:00`` suffix."""
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


class SessionMetadata(BaseModel):
    """Per-chat metadata persisted at ``{project_dir}/.scieasy/sessions/<chat_id>.json``.

    Validated by Pydantic v2; unknown fields are rejected to keep the
    on-disk format strict.
    """

    model_config = ConfigDict(extra="forbid")

    chat_id: str
    title: str = ""
    created: str = Field(default_factory=_utc_now_isoformat)
    last_active: str = Field(default_factory=_utc_now_isoformat)
    provider: str
    model: str | None = None
    system_prompt_hash: str
    session_id: str | None = None
    bypass_mode: bool = False
    total_turns: int = 0


def _metadata_path(project_dir: Path, chat_id: str) -> Path:
    return project_dir.resolve() / ".scieasy" / "sessions" / f"{chat_id}.json"


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


class AgentSessionManager:
    """Owns and arbitrates live agent sessions for one or more projects.

    Invariants
    ----------
    * At most :attr:`DEFAULT_CONCURRENT_CAP` live sessions per resolved
      ``project_dir``; the cap-1th ``start_session`` raises
      :class:`scieasy.ai.agent.errors.AgentSessionError`.
    * Session metadata is written to disk BEFORE the subprocess is
      spawned, so a crashed manager can still inspect what was
      attempted.
    * :meth:`shutdown_all` is safe to call during FastAPI lifespan
      teardown; it awaits every live session's ``close()`` even if
      individual sessions raise.
    """

    DEFAULT_CONCURRENT_CAP: ClassVar[int] = 5

    def __init__(self, *, concurrent_cap: int | None = None) -> None:
        self._sessions: dict[tuple[Path, str], AgentSession] = {}
        self._cap: int = concurrent_cap or self.DEFAULT_CONCURRENT_CAP

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_session(
        self,
        *,
        project_dir: Path,
        chat_id: str,
        provider: AgentProvider,
        system_prompt: str,
        mcp_config: dict[str, Any],
        permission_mode: PermissionMode = PermissionMode.STRICT,
        resume_session_id: str | None = None,
        model: str | None = None,
        title: str = "",
    ) -> AgentSession:
        """Spawn a new session for ``(project_dir, chat_id)``.

        Writes the metadata file before spawning so a manager crash is
        recoverable.

        Raises
        ------
        AgentSessionError
            If the concurrent-chat cap is reached, or if a live session
            already exists for ``(project_dir, chat_id)``.
        """
        resolved = project_dir.resolve()
        key = (resolved, chat_id)
        if key in self._sessions:
            raise AgentSessionError(f"session already exists for chat_id={chat_id!r} in {resolved}")

        live_in_project = sum(1 for (p, _c) in self._sessions if p == resolved)
        if live_in_project >= self._cap:
            raise AgentSessionError("concurrent chat cap reached")

        # Persist metadata BEFORE spawning so a crash leaves a record.
        metadata = SessionMetadata(
            chat_id=chat_id,
            title=title,
            provider=getattr(provider, "name", "claude-code"),
            model=model,
            system_prompt_hash=_hash_prompt(system_prompt),
            session_id=None,
            bypass_mode=permission_mode is PermissionMode.BYPASS,
            total_turns=0,
        )
        self._write_metadata(resolved, chat_id, metadata)
        logger.info(
            "AgentSessionManager.start_session: spawning chat_id=%s in %s",
            chat_id,
            resolved,
        )
        session = await provider.start_session(
            project_dir=resolved,
            system_prompt=system_prompt,
            mcp_config=mcp_config,
            resume_session_id=resume_session_id,
            permission_mode=permission_mode,
            model=model,
        )
        self._sessions[key] = session
        return session

    def get_session(self, project_dir: Path, chat_id: str) -> AgentSession | None:
        """Return the live session for ``(project_dir, chat_id)`` or ``None``."""
        return self._sessions.get((project_dir.resolve(), chat_id))

    async def close_session(self, project_dir: Path, chat_id: str) -> None:
        """Close one session; leave its on-disk metadata in place."""
        key = (project_dir.resolve(), chat_id)
        session = self._sessions.pop(key, None)
        if session is None:
            return
        # Update last_active before closing.
        try:
            metadata = self.load_metadata(project_dir, chat_id)
            if metadata is not None:
                metadata.last_active = _utc_now_isoformat()
                if session.session_id is not None:
                    metadata.session_id = session.session_id
                self._write_metadata(project_dir.resolve(), chat_id, metadata)
        except Exception as exc:  # pragma: no cover - metadata writes are best-effort here
            logger.warning("AgentSessionManager.close_session: failed to update metadata: %s", exc)
        try:
            await session.close()
        except Exception as exc:
            logger.error("AgentSessionManager.close_session: session.close() raised: %s", exc)

    async def shutdown_all(self) -> None:
        """Close every live session; called from FastAPI lifespan teardown."""
        keys = list(self._sessions.keys())
        await asyncio.gather(
            *(self.close_session(p, c) for (p, c) in keys),
            return_exceptions=True,
        )

    @property
    def live_count(self) -> int:
        """Total number of live sessions across all projects."""
        return len(self._sessions)

    def live_count_for(self, project_dir: Path) -> int:
        """Live-session count for one resolved project directory."""
        resolved = project_dir.resolve()
        return sum(1 for (p, _c) in self._sessions if p == resolved)

    # ------------------------------------------------------------------
    # Metadata I/O
    # ------------------------------------------------------------------

    def _write_metadata(self, project_dir: Path, chat_id: str, metadata: SessionMetadata) -> None:
        target = _metadata_path(project_dir, chat_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(metadata.model_dump(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def load_metadata(self, project_dir: Path, chat_id: str) -> SessionMetadata | None:
        """Read metadata from disk for ``(project_dir, chat_id)``.

        Returns ``None`` if the file does not exist.
        """
        path = _metadata_path(project_dir, chat_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SessionMetadata.model_validate(data)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("AgentSessionManager.load_metadata: failed to read %s: %s", path, exc)
            return None


# ---------------------------------------------------------------------------
# Module-level singleton used by FastAPI DI (see ``api/deps.py``).
# ---------------------------------------------------------------------------


_GLOBAL_MANAGER: AgentSessionManager | None = None


def get_session_manager() -> AgentSessionManager:
    """Return the process-wide :class:`AgentSessionManager` singleton.

    Created lazily on first call; subsequent calls return the same
    instance. Tests may pin a fresh instance via :func:`set_session_manager`.
    """
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        _GLOBAL_MANAGER = AgentSessionManager()
    return _GLOBAL_MANAGER


def set_session_manager(manager: AgentSessionManager | None) -> None:
    """Pin a manager instance (or ``None`` to clear) — test hook only."""
    global _GLOBAL_MANAGER
    _GLOBAL_MANAGER = manager
