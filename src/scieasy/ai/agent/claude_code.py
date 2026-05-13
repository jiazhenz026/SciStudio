"""Claude Code provider implementation.

Conforms to :class:`scieasy.ai.agent.provider.AgentProvider`; wraps the
locally-installed ``claude`` CLI as a subprocess and exposes its
stream-JSON output as canonical :class:`scieasy.ai.agent.provider.AgentEvent`
instances.

Implementation notes (spec §5 T-ECA-104, ADR-033 §3 D1.3):

* Discovery uses :func:`scieasy.ai.agent.binary_discovery.find_binary` and probes
  the binary with ``--version`` (5-second timeout) plus ``config get -g
  installMethod`` for the login-state heuristic (OQ4; 2-second timeout).
* Session spawn flags: ``--output-format stream-json --verbose
  --append-system-prompt @<prompt_file> --mcp-config @<mcp_file>`` plus
  ``--resume <id>`` if resuming and ``--model <m>`` if specified.
* Prompt and MCP config are serialised to ``tempfile.NamedTemporaryFile``
  paths and tracked on the session for cleanup at :meth:`ClaudeCodeSession.close`.
* The subprocess is spawned via :func:`asyncio.create_subprocess_exec`
  with stdin/stdout/stderr pipes and ``cwd=project_dir``. On Windows the
  ``CREATE_NEW_PROCESS_GROUP`` flag is set so the process group can be
  signalled together with its children; on POSIX ``start_new_session=True``
  produces an equivalent group-killable subprocess tree.
* Cancellation uses ``os.killpg`` on POSIX and ``taskkill /T /F /PID`` on
  Windows; both are idempotent.
* ``ClaudeCodeSession.send_user_message`` writes a JSON envelope to stdin
  and flushes — stdin is NOT closed, so multi-turn sessions are
  supported over one process (CC convention).
* The event stream wraps :func:`scieasy.ai.agent.stream_json.parse_stream`
  and latches the provider-assigned session id from the first ``init``
  event.

The :class:`ClaudeCodeProvider` constructor accepts a ``binary_override``
keyword that points at a Python stub script (resolved as
``[sys.executable, str(binary_override), ...]``) — used by the
``tests/fixtures/stub_claude.py`` test fixture to exercise the spawn
plumbing without a real CC binary.
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

_INSTALL_HINT = "Install the Claude Code CLI: see https://docs.claude.com/en/docs/claude-code/quickstart"


async def _read_subprocess_stream(stream: asyncio.StreamReader) -> AsyncIterator[bytes]:
    """Adapt an :class:`asyncio.StreamReader` into an async byte-chunk iterator."""
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            return
        yield chunk


class ClaudeCodeSession:
    """Live ``claude`` subprocess + IPC channels.

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
        — Claude Code supports multi-turn conversations over one
        process.

        Raises
        ------
        AgentLaunchError
            If the subprocess has already exited or stdin was lost.
        """
        if self._proc.stdin is None or self._proc.stdin.is_closing():
            raise AgentLaunchError("subprocess stdin is closed; cannot send_user_message")
        # Claude Code stream-json input format: wrap content in a
        # message.role+content envelope, matching the Anthropic SDK
        # message shape. Issue (no number) — without the wrapper the
        # subprocess silently ignores stdin and produces no output.
        envelope = json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": content},
            }
        )
        logger.debug(
            "ClaudeCodeSession.send_user_message: writing %d bytes to stdin",
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
                    "ClaudeCodeSession: session_id latched as %s",
                    event.session_id,
                )
            logger.debug("ClaudeCodeSession.stream_events: yield kind=%s", event.kind)
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
                    "ClaudeCodeSession.%s: taskkill /T /F issued for PID %s",
                    caller,
                    self._proc.pid,
                )
            except OSError as exc:  # pragma: no cover - taskkill rarely raises
                logger.warning("ClaudeCodeSession.%s: taskkill failed: %s", caller, exc)
        else:
            try:
                pgid = os.getpgid(self._proc.pid)
                os.killpg(pgid, signal.SIGKILL)
                logger.info("ClaudeCodeSession.%s: SIGKILL sent to pgid %s", caller, pgid)
            except (ProcessLookupError, PermissionError) as exc:
                logger.warning("ClaudeCodeSession.%s: killpg failed: %s", caller, exc)

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
                    "ClaudeCodeSession.close: subprocess did not exit in %.1fs; tree-killing",
                    _CLOSE_GRACE_SECONDS,
                )
                # Tree-kill — `self._proc.kill()` alone signals only the
                # parent and leaves child tool processes alive on POSIX
                # (and would not catch Windows process-group children).
                self._kill_process_tree(caller="close")
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._proc.wait(), timeout=1.0)

        for path in self._temp_files:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("ClaudeCodeSession.close: failed to unlink %s: %s", path, exc)


class ClaudeCodeProvider:
    """Provider for the ``@anthropic-ai/claude-code`` CLI.

    Structural conformance with :class:`AgentProvider` (PEP 544) is
    verified at the type level — see ``_PROTOCOL_CONFORMANCE`` at the
    bottom of this module.

    Parameters
    ----------
    binary_override
        If provided, points at a Python script used in place of the real
        ``claude`` binary. The session is spawned as
        ``[sys.executable, str(binary_override), ...]``. Used by the
        ``tests/fixtures/stub_claude.py`` test fixture.
    """

    name: ClassVar[str] = "claude-code"
    binary_name: ClassVar[str] = "claude"

    def __init__(self, *, binary_override: Path | None = None) -> None:
        self._binary_override: Path | None = binary_override

    @classmethod
    def discover(cls) -> ProviderStatus:
        """Locate the ``claude`` binary and probe version + login state."""
        binary_path = find_binary(cls.binary_name)
        if binary_path is None:
            logger.info("ClaudeCodeProvider.discover: claude binary not found")
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
                    "ClaudeCodeProvider.discover: --version exited %d: %s",
                    completed.returncode,
                    (completed.stderr or "").strip(),
                )
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("ClaudeCodeProvider.discover: --version probe failed: %s", exc)

        logged_in = False
        if available:
            try:
                completed = subprocess.run(
                    [str(binary_path), "config", "get", "-g", "installMethod"],
                    capture_output=True,
                    text=True,
                    timeout=_LOGIN_PROBE_TIMEOUT_SECONDS,
                    check=False,
                )
                logged_in = completed.returncode == 0
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.debug("ClaudeCodeProvider.discover: login probe failed: %s", exc)

        logger.info(
            "ClaudeCodeProvider.discover: available=%s version=%s logged_in=%s path=%s",
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
        """Spawn a ``claude`` subprocess and return a live session handle.

        See :meth:`AgentProvider.start_session` for parameter semantics.
        Awaitable because the subprocess is created via
        :func:`asyncio.create_subprocess_exec`.

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
                raise AgentNotInstalledError("claude binary not found on PATH or in any fallback location")
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
            # Tell claude that stdin will be stream-json envelopes too.
            # Without this, claude treats stdin as a one-shot plain-text
            # prompt and silently ignores the JSON envelopes we write,
            # producing no events on stdout (manual verification, 2026-05-13).
            "--input-format",
            "stream-json",
            "--verbose",
            # --append-system-prompt expects a literal string. We tried
            # `@path` indirection but claude treats the `@` as part of
            # the path. Read the file contents and pass them inline.
            "--append-system-prompt",
            system_prompt,
            # --mcp-config takes a file PATH (or inline JSON), no `@`.
            "--mcp-config",
            str(mcp_path),
        ]
        if resume_session_id is not None:
            argv += ["--resume", resume_session_id]
        if model is not None:
            argv += ["--model", model]

        env = os.environ.copy()
        env["SCIEASY_PERMISSION_MODE"] = permission_mode.value
        # Required by `scieasy hook-bridge` (T-ECA-110): CC inherits this env
        # into PreToolUse hook subprocesses, so the bridge can route the
        # permission request to /api/ai/permission-check (issue #723).
        env["SCIEASY_CHAT_ID"] = chat_id
        env["SCIEASY_PROJECT_DIR"] = str(project_dir)

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        logger.info(
            "ClaudeCodeProvider.start_session: spawning argv=%r cwd=%s",
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
            raise AgentLaunchError(f"failed to spawn claude subprocess: {exc}") from exc

        return ClaudeCodeSession(
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
        # On POSIX, start a new session so killpg(pgid, SIGTERM) cleans up
        # children spawned by the agent (Bash tool subprocesses, etc.).
        kwargs["start_new_session"] = True
    return await asyncio.create_subprocess_exec(*argv, **kwargs)


# Type-level conformance check: assigning the class to an
# ``AgentProvider``-typed name catches Protocol drift at mypy time
# without requiring runtime ``isinstance`` machinery.
_PROTOCOL_CONFORMANCE: type[AgentProvider] = ClaudeCodeProvider
