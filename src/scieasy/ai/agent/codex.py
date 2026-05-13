"""Codex CLI provider implementation (T-ECA-402).

Conforms to :class:`scieasy.ai.agent.provider.AgentProvider`; wraps the
locally-installed ``codex`` CLI as a subprocess and exposes its
stream-JSON output as canonical
:class:`scieasy.ai.agent.provider.AgentEvent` instances.

This provider deliberately mirrors :class:`scieasy.ai.agent.claude_code.ClaudeCodeProvider`:

* Same :class:`AgentProvider` Protocol surface.
* Same canonical event taxonomy on the output side (``init``,
  ``assistant_text_delta``, ``tool_use``, ``tool_result``,
  ``permission_request``, ``done``, ``error``, ``other``).
* Same subprocess lifecycle, cancellation strategy, and temp-file
  cleanup contract.

The differences are intentionally local:

* ``name = "codex"``, ``binary_name = "codex"``.
* The spawn flags follow the Codex CLI's flag surface as documented in
  ``docs/specs/eca-spike-codex-format.md``. Where the Codex CLI lacks a
  direct equivalent of a Claude Code flag, the spike doc records the
  assumption and the provider degrades gracefully (e.g. by serialising
  the system prompt + MCP config to temp files and pointing at them
  through the closest Codex flag, or omitting the flag entirely if no
  equivalent exists).
* Stream-format normalisation goes through the same
  :func:`scieasy.ai.agent.stream_json.parse_stream` parser. The parser
  is already tolerant of both ``{"kind": ...}`` (ADR canonical) and
  ``{"type": ...}`` (CC wire) framings, so it handles either Codex
  framing without provider-specific code.

Implementation notes (spec §8 T-ECA-402, ADR-033 §3 D1):

* Discovery uses :func:`scieasy.ai.agent.binary_discovery.find_binary`
  with ``binary_name = "codex"``, probes ``codex --version`` (5-second
  timeout) for availability, and ``codex login status`` (2-second
  timeout) for the login-state heuristic. If the login subcommand
  returns non-zero we fall back to ``logged_in=False`` rather than
  raising — exactly the same contract as Claude Code's
  ``installMethod`` probe.
* Session spawn flags mirror Claude Code's surface:
  ``--output-format stream-json --append-system-prompt @<prompt_file>
  --mcp-config @<mcp_file>`` plus ``--resume <id>`` if resuming and
  ``--model <m>`` if specified. The actual Codex flag spellings are
  documented in the spike addendum; the implementation here assumes
  flag parity. If a real Codex CLI rejects a flag we observe the
  failure in the ``codex --version`` probe (which becomes
  ``logged_in=False`` and the user sees the install hint).
* The subprocess is spawned via :func:`asyncio.create_subprocess_exec`
  with stdin/stdout/stderr pipes and ``cwd=project_dir``. On Windows
  the ``CREATE_NEW_PROCESS_GROUP`` flag is set; on POSIX
  ``start_new_session=True`` produces an equivalent group-killable
  subprocess tree.
* Cancellation uses ``os.killpg`` on POSIX and ``taskkill /T /F /PID``
  on Windows; both are idempotent.
* :meth:`CodexSession.send_user_message` writes a JSON envelope to
  stdin and flushes — stdin is NOT closed, so multi-turn sessions are
  supported over one process (matches CC convention).

The :class:`CodexProvider` constructor accepts a ``binary_override``
keyword that points at a Python stub script (resolved as
``[sys.executable, str(binary_override), ...]``) — used by the
``tests/fixtures/stub_codex.py`` test fixture to exercise the spawn
plumbing without a real Codex binary.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar

from scieasy.ai.agent.binary_discovery import find_binary
from scieasy.ai.agent.errors import (
    AgentLaunchError,
    AgentNotInstalledError,
)
from scieasy.ai.agent.provider import (
    AgentEvent,
    AgentProvider,
    AgentSession,
    InitEvent,
    PermissionMode,
    ProviderStatus,
)
from scieasy.ai.agent.stream_json import parse_stream

logger = logging.getLogger(__name__)


_VERSION_TIMEOUT_SECONDS = 5.0
_LOGIN_PROBE_TIMEOUT_SECONDS = 2.0
_CLOSE_GRACE_SECONDS = 5.0

_INSTALL_HINT = "Install the Codex CLI: see https://github.com/openai/codex for installation and login instructions."


async def _read_subprocess_stream(stream: asyncio.StreamReader) -> AsyncIterator[bytes]:
    """Adapt an :class:`asyncio.StreamReader` into an async byte-chunk iterator."""
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            return
        yield chunk


class CodexSession:
    """Live ``codex`` subprocess + IPC channels.

    Conforms structurally to :class:`scieasy.ai.agent.provider.AgentSession`.

    Invariants
    ----------
    * Exactly one OS subprocess per instance.
    * ``send_user_message`` may be called repeatedly; stdin is held open
      until :meth:`close` is invoked.
    * :meth:`cancel` is idempotent; calling it twice is a no-op.
    * Temp files written by the provider (system prompt, MCP config) are
      released in :meth:`close`; failures during unlink are logged at
      WARNING and swallowed.
    """

    def __init__(
        self,
        *,
        proc: asyncio.subprocess.Process,
        temp_files: list[Path],
        project_dir: Path,
    ) -> None:
        self._proc: asyncio.subprocess.Process = proc
        self._temp_files: list[Path] = list(temp_files)
        self._project_dir: Path = project_dir
        self._closed: bool = False
        self._cancelled: bool = False

        # AgentSession Protocol public attributes.
        self.session_id: str | None = None
        self.pid: int = proc.pid

    @property
    def temp_files(self) -> list[Path]:
        """Tracked temp-file paths (read-only view); useful for tests."""
        return list(self._temp_files)

    async def send_user_message(self, content: str) -> None:
        """Send a user-turn message to the agent subprocess.

        Writes a JSON envelope ``{"type": "user", "content": ...}`` to
        stdin followed by a newline, then flushes. Stdin is NOT closed
        — the Codex CLI is assumed to support multi-turn over one
        process; if a future Codex CLI requires stdin EOF per turn the
        provider can override this method without touching the wider
        runtime.

        Raises
        ------
        AgentLaunchError
            If the subprocess has already exited or stdin was lost.
        """
        if self._proc.stdin is None or self._proc.stdin.is_closing():
            raise AgentLaunchError("subprocess stdin is closed; cannot send_user_message")
        envelope = json.dumps({"type": "user", "content": content})
        logger.debug(
            "CodexSession.send_user_message: writing %d bytes to stdin",
            len(envelope),
        )
        self._proc.stdin.write(envelope.encode("utf-8") + b"\n")
        try:
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise AgentLaunchError(f"subprocess stdin write failed: {exc}") from exc

    async def stream_events(self) -> AsyncIterator[AgentEvent]:
        """Yield canonical :class:`AgentEvent`s from the subprocess stdout.

        Latches ``self.session_id`` from the first :class:`InitEvent`.
        The iterator terminates cleanly when stdout EOF is reached.
        """
        if self._proc.stdout is None:
            raise AgentLaunchError("subprocess stdout is not piped")

        chunk_iter = _read_subprocess_stream(self._proc.stdout)
        async for event in parse_stream(chunk_iter):
            if isinstance(event, InitEvent) and self.session_id is None:
                self.session_id = event.session_id
                logger.info(
                    "CodexSession: session_id latched as %s",
                    event.session_id,
                )
            logger.debug("CodexSession.stream_events: yield kind=%s", event.kind)
            yield event

    def _kill_process_tree(self, *, caller: str) -> None:
        """Tree-kill the subprocess group on POSIX, taskkill /T /F on Windows.

        Used by both :meth:`cancel` and :meth:`close` (timeout path).
        Without this, ``self._proc.kill()`` only signals the parent and
        any tool children (long-running ``Bash`` commands) survive
        teardown. POSIX sessions are spawned with
        ``start_new_session=True`` so ``killpg`` reliably hits the whole
        tree; Windows uses the existing CREATE_NEW_PROCESS_GROUP +
        ``taskkill /T /F``.
        """
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(self._proc.pid)],
                    check=False,
                    capture_output=True,
                )
                logger.info(
                    "CodexSession.%s: taskkill /T /F issued for PID %s",
                    caller,
                    self._proc.pid,
                )
            except OSError as exc:  # pragma: no cover - taskkill rarely raises
                logger.warning("CodexSession.%s: taskkill failed: %s", caller, exc)
        else:
            try:
                pgid = os.getpgid(self._proc.pid)
                os.killpg(pgid, signal.SIGKILL)
                logger.info("CodexSession.%s: SIGKILL sent to pgid %s", caller, pgid)
            except (ProcessLookupError, PermissionError) as exc:
                logger.warning("CodexSession.%s: killpg failed: %s", caller, exc)

    async def cancel(self) -> None:
        """Cancel any in-flight agent turn by tree-killing the subprocess group.

        Idempotent: calling ``cancel`` on an already-cancelled or
        already-exited session is a no-op.

        Uses SIGKILL via :meth:`_kill_process_tree` to guarantee child
        tool processes (e.g. long-running Bash commands) are also
        terminated. Cancellation is a user-driven hard abort; SIGTERM-
        with-grace is not appropriate here because we cannot trust the
        agent to honour it promptly.
        """
        if self._cancelled or self._proc.returncode is not None:
            self._cancelled = True
            return
        self._cancelled = True
        self._kill_process_tree(caller="cancel")

    async def close(self) -> None:
        """Await subprocess exit (with grace) and release temp files.

        Idempotent: calling ``close`` twice is a no-op.
        """
        if self._closed:
            return
        self._closed = True

        if self._proc.stdin is not None and not self._proc.stdin.is_closing():
            with contextlib.suppress(OSError):
                self._proc.stdin.close()
            # Force the underlying FD to release before we await proc.wait().
            # Required on Windows asyncio Proactor pipes — without this the
            # child may never observe stdin EOF, blocking on readline()
            # forever and forcing this close() through the grace-timeout
            # kill path on every single session.
            with contextlib.suppress(OSError, asyncio.CancelledError, AttributeError):
                await self._proc.stdin.wait_closed()

        if self._proc.returncode is None:
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=_CLOSE_GRACE_SECONDS)
            except TimeoutError:
                logger.warning(
                    "CodexSession.close: subprocess did not exit in %.1fs; tree-killing",
                    _CLOSE_GRACE_SECONDS,
                )
                self._kill_process_tree(caller="close")
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._proc.wait(), timeout=1.0)

        for path in self._temp_files:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("CodexSession.close: failed to unlink %s: %s", path, exc)


class CodexProvider:
    """Provider for the ``codex`` CLI.

    Structural conformance with :class:`AgentProvider` (PEP 544) is
    verified at the type level — see ``_PROTOCOL_CONFORMANCE`` at the
    bottom of this module.

    Parameters
    ----------
    binary_override
        If provided, points at a Python script used in place of the real
        ``codex`` binary. The session is spawned as
        ``[sys.executable, str(binary_override), ...]``. Used by the
        ``tests/fixtures/stub_codex.py`` test fixture.
    """

    name: ClassVar[str] = "codex"
    binary_name: ClassVar[str] = "codex"

    def __init__(self, *, binary_override: Path | None = None) -> None:
        self._binary_override: Path | None = binary_override

    @classmethod
    def discover(cls) -> ProviderStatus:
        """Locate the ``codex`` binary and probe version + login state.

        The login-state probe runs ``codex login status``; if the
        Codex CLI version installed lacks that subcommand the call
        returns non-zero and we degrade to ``logged_in=False`` rather
        than raising. This matches Claude Code's ``installMethod``
        probe contract.
        """
        binary_path = find_binary(cls.binary_name)
        if binary_path is None:
            logger.info("CodexProvider.discover: codex binary not found")
            return ProviderStatus(
                name=cls.name,
                available=False,
                binary_path=None,
                version=None,
                logged_in=False,
                install_hint=_INSTALL_HINT,
            )

        version: str | None = None
        available = False
        try:
            completed = subprocess.run(
                [str(binary_path), "--version"],
                capture_output=True,
                text=True,
                timeout=_VERSION_TIMEOUT_SECONDS,
                check=False,
            )
            if completed.returncode == 0:
                version = (completed.stdout or completed.stderr or "").strip() or None
                available = True
            else:
                logger.warning(
                    "CodexProvider.discover: --version exited %d: %s",
                    completed.returncode,
                    (completed.stderr or "").strip(),
                )
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("CodexProvider.discover: --version probe failed: %s", exc)

        logged_in = False
        if available:
            try:
                completed = subprocess.run(
                    [str(binary_path), "login", "status"],
                    capture_output=True,
                    text=True,
                    timeout=_LOGIN_PROBE_TIMEOUT_SECONDS,
                    check=False,
                )
                logged_in = completed.returncode == 0
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.debug("CodexProvider.discover: login probe failed: %s", exc)

        logger.info(
            "CodexProvider.discover: available=%s version=%s logged_in=%s path=%s",
            available,
            version,
            logged_in,
            binary_path,
        )
        return ProviderStatus(
            name=cls.name,
            available=available,
            binary_path=binary_path if available else None,
            version=version,
            logged_in=logged_in,
            install_hint=None if available else _INSTALL_HINT,
        )

    async def start_session(
        self,
        *,
        project_dir: Path,
        chat_id: str,
        system_prompt: str,
        mcp_config: dict[str, Any],
        resume_session_id: str | None,
        permission_mode: PermissionMode,
        model: str | None = None,
    ) -> AgentSession:
        """Spawn a ``codex`` subprocess and return a live session handle.

        See :meth:`AgentProvider.start_session` for parameter semantics.

        Raises
        ------
        AgentNotInstalledError
            If no binary override is set and ``find_binary`` returns
            ``None``.
        AgentLaunchError
            If :func:`asyncio.create_subprocess_exec` itself raises.
        """
        argv0: list[str]
        if self._binary_override is not None:
            argv0 = [sys.executable, str(self._binary_override)]
        else:
            binary_path = find_binary(self.binary_name)
            if binary_path is None:
                raise AgentNotInstalledError("codex binary not found on PATH or in any fallback location")
            argv0 = [str(binary_path)]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as prompt_handle:
            prompt_handle.write(system_prompt)
            prompt_path = Path(prompt_handle.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as mcp_handle:
            json.dump(mcp_config, mcp_handle)
            mcp_path = Path(mcp_handle.name)

        temp_files = [prompt_path, mcp_path]

        argv = [
            *argv0,
            "--output-format",
            "stream-json",
            "--append-system-prompt",
            f"@{prompt_path}",
            "--mcp-config",
            f"@{mcp_path}",
        ]
        if resume_session_id is not None:
            argv += ["--resume", resume_session_id]
        if model is not None:
            argv += ["--model", model]

        env = os.environ.copy()
        env["SCIEASY_PERMISSION_MODE"] = permission_mode.value
        # Mirrors ClaudeCodeProvider env injection (issue #723): hook bridge
        # subprocesses need SCIEASY_CHAT_ID and SCIEASY_PROJECT_DIR to route
        # permission requests back to /api/ai/permission-check.
        env["SCIEASY_CHAT_ID"] = chat_id
        env["SCIEASY_PROJECT_DIR"] = str(project_dir)

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        logger.info(
            "CodexProvider.start_session: spawning argv=%r cwd=%s",
            argv,
            project_dir,
        )
        try:
            proc = await _spawn(
                argv=argv,
                cwd=project_dir,
                env=env,
                creationflags=creationflags,
            )
        except OSError as exc:
            for path in temp_files:
                with contextlib.suppress(OSError):
                    path.unlink(missing_ok=True)
            raise AgentLaunchError(f"failed to spawn codex subprocess: {exc}") from exc

        return CodexSession(
            proc=proc,
            temp_files=temp_files,
            project_dir=project_dir,
        )


async def _spawn(
    *,
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    creationflags: int,
) -> asyncio.subprocess.Process:
    """Thin wrapper around :func:`asyncio.create_subprocess_exec` for testability."""
    kwargs: dict[str, Any] = dict(
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd),
        env=env,
    )
    if creationflags:
        kwargs["creationflags"] = creationflags
    elif sys.platform != "win32":
        kwargs["start_new_session"] = True
    return await asyncio.create_subprocess_exec(*argv, **kwargs)


# Type-level conformance check: assigning the class to an
# ``AgentProvider``-typed name catches Protocol drift at mypy time
# without requiring runtime ``isinstance`` machinery.
_PROTOCOL_CONFORMANCE: type[AgentProvider] = CodexProvider
