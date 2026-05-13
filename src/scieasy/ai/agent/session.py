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
import collections
import contextlib
import datetime as _dt
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from scieasy.ai.agent.errors import AgentSessionError
from scieasy.ai.agent.provider import (
    AgentEvent,
    AgentProvider,
    AgentSession,
    PermissionMode,
)
from scieasy.ai.agent.transcript import TranscriptWriter

logger = logging.getLogger(__name__)


# #783 P1/P2 ring buffer cap. Bounded so a long agent run with WS
# disconnected does not balloon memory. 500 events ≈ a typical multi-
# turn conversation worth; the transcript file is the durable record.
_RING_BUFFER_CAP: int = 500


class _SessionRuntime:
    """In-memory runtime state for one live session (#783).

    Owns the background drain task that consumes ``stream_events()``
    even when no WebSocket is attached. Events are mirrored to:

    * the on-disk :class:`TranscriptWriter`, and
    * a bounded :class:`collections.deque` ring buffer so a reattaching
      WS can replay recent activity without re-reading the full
      transcript file.

    Single-consumer model: when a WS is attached, the WS pump calls
    :meth:`attach_consumer` to take over event consumption from the
    drain task. When the WS detaches, :meth:`detach_consumer` releases
    the consumer slot and the drain task resumes (so claude's stdout
    pipe never blocks).
    """

    def __init__(
        self,
        session: AgentSession,
        transcript: TranscriptWriter,
    ) -> None:
        self.session = session
        self.transcript = transcript
        self.ring_buffer: collections.deque[AgentEvent] = collections.deque(
            maxlen=_RING_BUFFER_CAP,
        )
        # Single async queue fed by the drain loop. Both the drain task
        # (when no WS is attached) and any attached WS consumer read
        # from this queue. To preserve the single-consumer invariant,
        # only one of {drain_task, ws_consumer} is "draining" the queue
        # at a time — the other simply produces.
        self._stream_task: asyncio.Task[None] | None = None
        self._ws_consumer_active: bool = False
        # Event waiters for new buffer entries when the WS is detached.
        # The drain loop sets this; WS consumers may consult it.
        self._ws_attached_event: asyncio.Event = asyncio.Event()
        self._closed: bool = False

    def start(self) -> None:
        """Spawn the background stream-consumer task (idempotent)."""
        if self._stream_task is None:
            self._stream_task = asyncio.create_task(self._drain_loop())

    async def _drain_loop(self) -> None:
        """Consume the session's event stream forever.

        Every event is appended to the on-disk transcript and the
        in-memory ring buffer. This loop is the single consumer of
        ``stream_events()`` — WS pumps read from the ring buffer +
        a subscriber fan-out rather than competing for the iterator.
        """
        try:
            async for event in self.session.stream_events():
                self.ring_buffer.append(event)
                try:
                    await self.transcript.write_event(event)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("drain_loop: transcript.write_event raised: %s", exc)
                # Fan-out: notify any active WS subscriber.
                self._notify_subscribers(event)
        except (asyncio.CancelledError, GeneratorExit):
            return
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("drain_loop: terminating on error: %s", exc, exc_info=True)

    # Subscriber fan-out for WS consumers. Each subscriber gets its own
    # asyncio.Queue; the drain loop ``put_nowait``s every event to every
    # subscriber. This preserves the single-consumer invariant on the
    # underlying stream while allowing multiple readers.
    def _get_subscribers(self) -> list[asyncio.Queue[AgentEvent]]:
        if not hasattr(self, "_subscribers_list"):
            self._subscribers_list: list[asyncio.Queue[AgentEvent]] = []
        return self._subscribers_list

    def subscribe(self) -> asyncio.Queue[AgentEvent]:
        """Register a new WS subscriber and return its private queue."""
        q: asyncio.Queue[AgentEvent] = asyncio.Queue()
        self._get_subscribers().append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[AgentEvent]) -> None:
        """Remove a WS subscriber's queue."""
        subs = self._get_subscribers()
        if q in subs:
            subs.remove(q)

    def _notify_subscribers(self, event: AgentEvent) -> None:
        for q in list(self._get_subscribers()):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover - unbounded queues
                logger.warning("drain_loop: subscriber queue full; dropping event")

    def snapshot_buffer(self) -> list[AgentEvent]:
        """Return a list copy of the ring buffer (oldest first)."""
        return list(self.ring_buffer)

    async def close(self) -> None:
        """Cancel the drain task and close the transcript writer."""
        self._closed = True
        task = self._stream_task
        self._stream_task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        try:
            self.transcript.close()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("_SessionRuntime.close: transcript.close raised: %s", exc)


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


def _transcript_path(project_dir: Path, chat_id: str) -> Path:
    """Return the canonical transcript path for ``(project_dir, chat_id)``.

    Layout (spec §3 D7.1 / T-ECA-106):
    ``{project_dir}/.scieasy/sessions/<chat_id>/transcript.jsonl``.

    Note the directory name uses ``<chat_id>`` whereas the metadata file
    is the sibling ``<chat_id>.json``; they cannot collide because the
    metadata is a file and the transcript root is a directory.
    """
    return project_dir.resolve() / ".scieasy" / "sessions" / chat_id / "transcript.jsonl"


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
        self._transcripts: dict[tuple[Path, str], TranscriptWriter] = {}
        # #783: per-session runtime owning the drain task + ring buffer.
        self._runtimes: dict[tuple[Path, str], _SessionRuntime] = {}
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
            chat_id=chat_id,
            system_prompt=system_prompt,
            mcp_config=mcp_config,
            resume_session_id=resume_session_id,
            permission_mode=permission_mode,
            model=model,
        )
        self._sessions[key] = session
        # T-ECA-106 closeout (#778): attach a TranscriptWriter so the WS
        # event pump in ``api/routes/ai.py`` can mirror every emitted
        # event to ``.scieasy/sessions/<chat_id>/transcript.jsonl``.
        # Construction is cheap (no I/O until the first write); failures
        # to open are absorbed by the writer itself so they cannot leak
        # into ``start_session`` and abort the spawn.
        transcript = TranscriptWriter(_transcript_path(resolved, chat_id))
        self._transcripts[key] = transcript
        # #783: spin up the per-session drain task so stdout flows even
        # when no WS is attached.
        runtime = _SessionRuntime(session, transcript)
        runtime.start()
        self._runtimes[key] = runtime
        return session

    def get_session(self, project_dir: Path, chat_id: str) -> AgentSession | None:
        """Return the live session for ``(project_dir, chat_id)`` or ``None``."""
        return self._sessions.get((project_dir.resolve(), chat_id))

    def get_runtime(self, project_dir: Path, chat_id: str) -> _SessionRuntime | None:
        """Return the :class:`_SessionRuntime` for ``(project_dir, chat_id)``.

        #783: WS attach uses this to subscribe to live events and replay
        the ring buffer. Returns ``None`` if no live session exists.
        """
        return self._runtimes.get((project_dir.resolve(), chat_id))

    def get_transcript_writer(self, project_dir: Path, chat_id: str) -> TranscriptWriter | None:
        """Return the :class:`TranscriptWriter` for ``(project_dir, chat_id)``.

        Returns ``None`` if no live session exists for that key. The
        WS event pump in ``api/routes/ai.py`` calls this for every
        emitted event so the on-disk JSONL mirror stays in sync with
        what the frontend sees (spec §3 D7.1 / T-ECA-106).
        """
        return self._transcripts.get((project_dir.resolve(), chat_id))

    async def close_session(self, project_dir: Path, chat_id: str) -> None:
        """Close one session; leave its on-disk metadata in place."""
        key = (project_dir.resolve(), chat_id)
        session = self._sessions.pop(key, None)
        # T-ECA-106 closeout (#778): close the transcript writer in lock
        # step with the session. Pop unconditionally so a stray writer
        # without a matching session (theoretically impossible, but
        # defensive) is still cleaned up.
        transcript = self._transcripts.pop(key, None)
        # #783: cancel the drain task before the session goes away so it
        # cannot keep producing into a dead transcript.
        runtime = self._runtimes.pop(key, None)
        if runtime is not None:
            try:
                await runtime.close()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "AgentSessionManager.close_session: runtime.close raised: %s",
                    exc,
                )
        elif transcript is not None:
            # No runtime (legacy code path); close the transcript directly.
            try:
                transcript.close()
            except Exception as exc:  # pragma: no cover - close swallows internally
                logger.warning(
                    "AgentSessionManager.close_session: transcript.close() raised: %s",
                    exc,
                )
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

    def list_sessions(self, project_dir: Path) -> list[SessionMetadata]:
        """Enumerate persisted session metadata for ``project_dir`` (#783).

        Reads every ``<project>/.scieasy/sessions/<chat_id>.json`` file
        and returns the parsed :class:`SessionMetadata`, sorted by
        ``last_active`` descending. Malformed files are skipped with a
        WARNING — they do not poison the listing.
        """
        sessions_dir = project_dir.resolve() / ".scieasy" / "sessions"
        if not sessions_dir.is_dir():
            return []
        out: list[SessionMetadata] = []
        for entry in sessions_dir.iterdir():
            if not entry.is_file() or entry.suffix != ".json":
                continue
            try:
                data = json.loads(entry.read_text(encoding="utf-8"))
                out.append(SessionMetadata.model_validate(data))
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "AgentSessionManager.list_sessions: skipping %s: %s",
                    entry,
                    exc,
                )
        out.sort(key=lambda m: m.last_active, reverse=True)
        return out

    def iter_transcript_events(self, project_dir: Path, chat_id: str) -> collections.abc.Iterator[dict[str, Any]]:
        """Stream the on-disk transcript line-by-line as decoded dicts (#783).

        Yields one dict per JSON line; malformed lines are skipped. Used
        by the ``GET /api/ai/sessions/{chat_id}/transcript`` route to
        replay history without loading the whole file into memory.
        """
        path = _transcript_path(project_dir.resolve(), chat_id)
        if not path.is_file():
            return
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as exc:
                        logger.warning(
                            "iter_transcript_events: skipping malformed line in %s: %s",
                            path,
                            exc,
                        )
        except OSError as exc:
            logger.warning("iter_transcript_events: read failure for %s: %s", path, exc)
            return


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
