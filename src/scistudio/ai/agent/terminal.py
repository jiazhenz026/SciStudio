"""Cross-platform PTY wrapper for ADR-034 PTY-tab agents.

This module hosts the production successor to the Phase 1.1 spike
(``scripts/spike_pty_claude.py``). It provides a platform-uniform
bytes-in / bytes-out interface for embedding claude / codex CLIs
inside SciStudio via xterm.js — the WebSocket route in
:mod:`scistudio.api.routes.ai_pty` calls ``PtyProcess.read`` / ``write``
/ ``resize`` and pipes the frames to the browser.

Spike findings applied here (see Phase 1.1 spike report on issue #816):

* **Ctrl+C must pass through verbatim** — claude and codex both require
  *double* Ctrl+C to exit (first occurrence triggers the "Press Ctrl-C
  again to exit" banner). The wrapper does NO byte filtering — every
  byte the client sends goes to the PTY unchanged.
* **``winpty.PtyProcess.read()`` is non-blocking** and returns whatever
  is in the buffer right now (often nothing).  :meth:`PtyProcess.read`
  therefore loops with ``time.sleep(0.05)`` between probes so we
  accumulate banner output instead of returning empty strings.
  POSIX uses ``select.select(timeout=…)`` which blocks until data
  or timeout elapses.
* **``winpty`` returns ``str``, POSIX ``os.read`` returns ``bytes``** —
  normalised to ``bytes`` here so the route layer never has to care.
* **Process-tree kill on Windows** uses ``taskkill /T /F /PID <pid>``
  (the ``/T`` flag terminates the whole tree).  POSIX uses
  ``os.killpg(pgid, SIGTERM)`` followed by ``SIGKILL`` after a 1 s
  grace period.  ``start_new_session=True`` on :func:`subprocess.Popen`
  gives us a fresh process group to target.
* **codex.cmd on Windows** spawns cleanly via ``winpty.PtyProcess.spawn``
  — no ``shell=True`` shim required.
* **codex auto-reads ``~/.codex/config.toml``** for its MCP config and
  does not accept ``--mcp-config``; the codex factory therefore omits
  that flag (the user's ``scistudio install --target codex`` writes the
  TOML entry).
* **claude needs ``--append-system-prompt @<path>``** — claude does not
  understand stdin-piped prompts in TUI mode; we write the composed
  prompt to a temp file under ``<project>/.scistudio/.tmp/`` and pass
  the absolute path via the ``@``-indirection.

ADR-034 multi-provider (issue #1994): every per-CLI fact above now lives in
:mod:`scistudio.ai.agent.providers_registry` instead of in per-provider spawn
functions. This module keeps :class:`PtyProcess` unchanged and exposes one
descriptor-driven :func:`spawn_agent` covering Claude Code, Codex, Kimi Code,
and both Qoder channels, plus :func:`spawn_user_terminal` for the shell
pseudo-provider. There is deliberately no ``if provider == …`` chain left here.

macOS notes (verified separately by user):

* NFD vs NFC unicode: macOS HFS+/APFS normalises filenames to NFD; tests
  comparing CLI-reported cwd paths should normalise both sides through
  :func:`unicodedata.normalize`.
* ``/tmp`` is a symlink to ``/private/tmp``; resolve via
  :meth:`Path.resolve` if asserting on paths.
* App Sandbox: codex-cli builds signed for the App Sandbox may refuse
  PTY spawn — users running from a sandboxed parent will see spawn
  failure.  Document this in the user-facing error path.
* SIGWINCH is delivered automatically on resize when we call
  ``ioctl(TIOCSWINSZ)`` on POSIX, so the CLI repaints on viewport change
  without further plumbing.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from scistudio.ai.agent.providers_registry import (
    McpStrategy,
    ProviderDescriptor,
    ProviderKind,
    SystemPromptStrategy,
    resolve_binary,
    resolve_executable,
)

logger = logging.getLogger(__name__)

# Public re-exports for the route layer.
__all__ = [
    "PtyProcess",
    "resolve_windows_executable",
    "spawn_agent",
    "spawn_user_terminal",
]

#: Environment variables never handed to a PTY-hosted agent CLI.
#:
#: ``ELECTRON_RUN_AS_NODE`` is the original entry: inherited from the desktop
#: shell it would make a Node-based CLI re-exec as a bare Node process.
#:
#: The rest are **agent-session markers** (#1994 finding 1). SciStudio inherits
#: the environment of whatever launched it, and when the backend is started
#: from inside an agent CLI session — a developer running it from a Claude Code
#: or Codex terminal — that parent session's private markers are still in the
#: environment and get copied wholesale into the CLI we spawn. The child then
#: believes it is a nested invocation of its own parent and silently degrades:
#: the owner saw Claude Code announce ``Transcript saving is off — inherited
#: CLAUDE_CODE_CHILD_SESSION marker``, meaning the spawned agent's conversation
#: was not being recorded at all.
#:
#: The list is explicit rather than a ``CLAUDE_*`` / ``CODEX_*`` prefix sweep,
#: because those namespaces also hold deliberate user configuration —
#: ``CLAUDE_CONFIG_DIR`` and ``ANTHROPIC_*`` credentials among them — that the
#: spawned CLI needs. Only per-session identity and nesting markers belong
#: here; add a name when a CLI is observed to change behaviour because of it.
_PTY_BLOCKED_ENV_VARS = frozenset(
    {
        "ELECTRON_RUN_AS_NODE",
        # Claude Code session identity / nesting markers.
        "CLAUDECODE",
        "CLAUDE_CODE_CHILD_SESSION",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_EXECPATH",
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_CODE_SSE_PORT",
        "CLAUDE_AGENT_SDK_VERSION",
        "CLAUDE_PID",
        "CLAUDE_PLUGIN_DATA",
        # Codex session identity / sandbox markers.
        "CODEX_COMPANION_SESSION_ID",
        "CODEX_SANDBOX",
        "CODEX_SANDBOX_NETWORK_DISABLED",
    }
)

# ADR-034 multi-provider (FR-004): the by-name executable resolver moved into
# ``providers_registry`` so ``resolve_binary`` can call it without importing
# this module (which would be an import cycle — ``terminal`` already imports the
# registry). It is re-exported here unchanged, rather than wrapped, because
# ``scistudio.api.routes.ai`` and the spec's ``governs.contracts`` both address
# the name at this location, and a delegating wrapper would be pure duplication.
#
# The signature gained a keyword-only ``well_known_dirs``: the well-known
# install directories are now supplied per provider by the registry descriptor
# instead of read from a module-level constant list. Callers holding a
# descriptor should prefer ``providers_registry.resolve_binary``, which passes
# ``descriptor.well_known_directories()`` for them; this name stays for callers
# that only have a binary name.
resolve_windows_executable = resolve_executable


def _build_child_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build a clean environment for PTY-hosted agent CLIs."""
    child_env = os.environ.copy()
    for name in _PTY_BLOCKED_ENV_VARS:
        child_env.pop(name, None)

    child_env["TERM"] = "xterm-256color"
    child_env["COLORTERM"] = "truecolor"
    child_env.setdefault("FORCE_COLOR", "3")

    if extra_env:
        child_env.update(extra_env)
        for name in _PTY_BLOCKED_ENV_VARS:
            child_env.pop(name, None)

    return child_env


class PtyProcess:
    """Platform-uniform wrapper around a PTY-attached subprocess.

    The route layer interacts with this class only; ``_impl`` holds the
    backend-specific handle (a :class:`winpty.PtyProcess` on Windows,
    or a master file descriptor + :class:`subprocess.Popen` on POSIX).

    Lifecycle: callers spawn via :func:`spawn_agent` (any registered agent
    CLI) or :func:`spawn_user_terminal`, then read / write / resize until the
    subprocess exits or :meth:`kill_tree` is invoked.

    Parameters
    ----------
    argv
        Argument vector for the subprocess (binary path + flags).
    cwd
        Working directory for the spawned process.
    cols, rows
        Initial PTY viewport.  Frontend will issue a resize frame
        almost immediately, but a sensible default avoids one frame of
        wrong-size TUI rendering.
    cleanup_paths
        Files to delete in :meth:`kill_tree` (typically the per-PTY
        temp system-prompt file).  Tolerates missing files.
    """

    def __init__(
        self,
        argv: list[str],
        cwd: Path,
        *,
        cols: int = 120,
        rows: int = 30,
        cleanup_paths: Iterable[Path] | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self._argv = argv
        self._cwd = cwd
        self._cleanup_paths: list[Path] = list(cleanup_paths or [])
        self._closed = False
        self._lock = threading.Lock()
        # ``_impl`` holds the winpty.PtyProcess handle on Windows (None on
        # POSIX).  Typed as ``Any`` because pywinpty has no type stubs and
        # because the attribute is only dereferenced on the platform that
        # set it.
        self._impl: Any = None
        self._master_fd: int | None = None
        self._popen: subprocess.Popen[bytes] | None = None

        # Build the child env. The PTY subprocess inherits the FastAPI
        # server's environment by default, which on Windows typically
        # lacks ``TERM``. Claude Code's TUI auto-detects safe defaults,
        # but Codex's TUI is stricter: when ``TERM`` is missing/unknown
        # it falls back to a "naive" rendering path that emits absolute
        # cursor positions without the alt-screen / scroll-region
        # handshake xterm.js expects, so scrolled-past content gets
        # clipped or overwritten. Advertising ``xterm-256color`` (the
        # de-facto modern terminal type that xterm.js fully implements)
        # makes both CLIs use their proper full-featured render path.
        child_env = _build_child_env(extra_env)
        # Some Node-based TUIs respect FORCE_COLOR for 24-bit output
        # even when stdout is detected as not-a-tty during nested
        # spawns. Harmless when ignored.
        # Caller-supplied per-invocation env (e.g. SCISTUDIO_AI_BLOCK_RUN_DIR
        # from open_engine_initiated_tab so the spawned mcp-bridge
        # subprocess can resolve the active run dir for finish_ai_block,
        # ADR-035 §3.5 path a). These override anything inherited above
        # so each PTY gets the right per-block context without polluting
        # the engine's global environment.
        if sys.platform == "win32":
            try:
                import winpty  # type: ignore
            except ImportError as exc:  # pragma: no cover - dep enforced by pyproject
                raise RuntimeError(
                    "pywinpty is required on Windows for PTY-based agents. "
                    "Reinstall scistudio: `pip install -e .` (pywinpty is a "
                    "platform-conditional dependency)."
                ) from exc

            self._impl = winpty.PtyProcess.spawn(
                argv,
                cwd=str(cwd),
                env=child_env,
                dimensions=(rows, cols),
            )
            self._pid: int = self._impl.pid
        else:
            import fcntl
            import pty
            import struct
            import termios

            master_fd, slave_fd = pty.openpty()
            # Set initial winsize before spawning so the TUI lays out
            # correctly on the very first paint.
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

            def _preexec() -> None:
                # Child side (post-fork, pre-exec), async-signal-safe syscalls
                # only. setsid() starts a fresh session/process group so
                # kill_tree can killpg the whole subtree. TIOCSCTTY then makes
                # the slave PTY the child's CONTROLLING terminal.
                #
                # #1946: without a controlling terminal the kernel has no
                # foreground process group to deliver SIGWINCH to, so a
                # subsequent TIOCSWINSZ resize on the master never reaches the
                # agent's process at all. The
                # agent still reads the initial winsize (TIOCGWINSZ needs no
                # ctty) so its first paint is correct, but fullscreen /
                # alt-screen TUIs (Claude Code's fullscreen mode) that repaint
                # only on SIGWINCH then stay stuck at the spawn-time size and
                # render ghosted at the wrong width on every panel resize.
                # start_new_session=True only does setsid(); it never sets the
                # controlling terminal, which is why this regressed silently.
                os.setsid()
                # Best-effort: never fail the spawn over ctty acquisition
                # (already-a-ctty / EPERM).
                with contextlib.suppress(OSError):  # pragma: no cover
                    fcntl.ioctl(0, termios.TIOCSCTTY, 0)

            popen = subprocess.Popen(
                argv,
                cwd=str(cwd),
                env=child_env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=_preexec,  # setsid + controlling tty (see above)
                close_fds=True,
            )
            os.close(slave_fd)
            self._popen = popen
            self._master_fd = master_fd
            self._pid = popen.pid

    @property
    def pid(self) -> int:
        return self._pid

    def is_alive(self) -> bool:
        """Return ``True`` while the underlying subprocess is running."""
        if self._closed:
            return False
        if sys.platform == "win32":
            try:
                return bool(self._impl.isalive())
            except Exception:
                return False
        assert self._popen is not None
        return self._popen.poll() is None

    def read(self, timeout: float = 0.1) -> bytes:
        """Read whatever PTY output is currently buffered.

        Always returns ``bytes`` (POSIX ``os.read`` is bytes-native;
        ``winpty`` returns ``str`` which we encode to UTF-8).  Returns
        ``b""`` on a normal "no data available" path and lets the
        caller poll again — the WebSocket pump task uses an asyncio
        executor + this method as a blocking read with bounded latency.

        Parameters
        ----------
        timeout
            Maximum seconds to wait for data.  On Windows we
            poll-loop because ``winpty.read`` is non-blocking; on POSIX
            we delegate to ``select.select``.
        """
        if self._closed:
            return b""
        if sys.platform == "win32":
            return self._read_windows(timeout)
        return self._read_posix(timeout)

    def _read_windows(self, timeout: float) -> bytes:
        """Accumulate ``winpty`` output up to ``timeout`` seconds.

        Per spike finding 2, ``winpty.PtyProcess.read`` returns
        immediately with whatever's available — often the empty string.
        We loop with a short sleep so the banner accrues into one
        meaningful frame instead of being chopped into 50 empty WS
        messages per second.
        """
        deadline = time.monotonic() + max(timeout, 0.0)
        chunks: list[bytes] = []
        while True:
            try:
                data = self._impl.read(4096)
            except EOFError:
                break
            except Exception:  # pragma: no cover - winpty edge
                break
            if data:
                # winpty returns str; normalise to UTF-8 bytes (spike finding 3).
                chunks.append(data.encode("utf-8", errors="replace"))
                # Got something — return promptly so the WS pump can flush it.
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        return b"".join(chunks)

    def _read_posix(self, timeout: float) -> bytes:
        """POSIX: ``select`` waits, then a single non-blocking read."""
        import select

        assert self._master_fd is not None
        try:
            rlist, _, _ = select.select([self._master_fd], [], [], timeout)
        except (OSError, ValueError):
            return b""
        if self._master_fd not in rlist:
            return b""
        try:
            data = os.read(self._master_fd, 4096)
        except OSError:
            return b""
        return data or b""

    def write(self, data: bytes) -> None:
        """Send ``data`` to the PTY's stdin.

        ``data`` is forwarded verbatim — no byte filtering, no
        Ctrl+C de-duplication.  The spike confirmed claude / codex
        require *double* Ctrl+C (``\\x03\\x03``) to exit; that must be
        a client-side decision, not a wrapper-side one.
        """
        if self._closed:
            return
        if sys.platform == "win32":
            # winpty.write accepts str; decode our bytes back to str.
            try:
                self._impl.write(data.decode("utf-8", errors="replace"))
            except Exception:  # pragma: no cover - winpty broken-pipe path
                logger.debug("PTY write failed (process likely exited)", exc_info=True)
            return
        assert self._master_fd is not None
        try:
            os.write(self._master_fd, data)
        except OSError:  # pragma: no cover - broken pipe path
            logger.debug("PTY write failed (process likely exited)", exc_info=True)

    def resize(self, cols: int, rows: int) -> None:
        """Update PTY viewport.  POSIX triggers SIGWINCH automatically."""
        if self._closed:
            return
        # Defensive clamps — protect against bogus client frames.
        cols = max(1, min(int(cols), 1000))
        rows = max(1, min(int(rows), 500))
        if sys.platform == "win32":
            try:
                self._impl.setwinsize(rows, cols)
            except Exception:  # pragma: no cover
                logger.debug("PTY resize failed", exc_info=True)
            return
        import fcntl
        import struct
        import termios

        assert self._master_fd is not None
        try:
            fcntl.ioctl(
                self._master_fd,
                termios.TIOCSWINSZ,
                struct.pack("HHHH", rows, cols, 0, 0),
            )
        except OSError:  # pragma: no cover
            logger.debug("PTY resize ioctl failed", exc_info=True)

    def kill_tree(self) -> None:
        """Terminate the PTY subprocess and all its descendants.

        Idempotent: subsequent calls are no-ops.  Always cleans up the
        temp system-prompt file (best-effort).
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True

        try:
            if sys.platform == "win32":
                self._kill_windows()
            else:
                self._kill_posix()
        finally:
            for path in self._cleanup_paths:
                try:
                    path.unlink(missing_ok=True)
                except Exception:  # pragma: no cover - best-effort cleanup
                    logger.debug("Failed to clean up temp file %s", path, exc_info=True)

    def _kill_windows(self) -> None:
        """Per spike finding 4: taskkill /T /F /PID covers the whole tree.

        We do NOT call ``self._impl.kill()`` here because pywinpty's
        ``kill`` blocks on internal locks while a concurrent ``read``
        is still in flight (the read loop in the WS route only stops
        when the read returns EOFError after the process dies). The
        taskkill /T /F alone reliably terminates the tree on Windows,
        and the read loop will exit on the next iteration when the
        PTY pipe closes.
        """
        pid = self._pid
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                check=False,
                capture_output=True,
                timeout=5,
            )
        except Exception:  # pragma: no cover - taskkill missing
            logger.warning("taskkill failed for PID %s", pid, exc_info=True)

    def _kill_posix(self) -> None:
        """SIGTERM the group, escalate to SIGKILL after 1 s."""
        import signal

        assert self._popen is not None
        pid = self._pid
        try:
            pgid = os.getpgid(pid)  # type: ignore[attr-defined]
        except ProcessLookupError:
            return
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, signal.SIGTERM)  # type: ignore[attr-defined]
        try:
            self._popen.wait(timeout=1)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(pgid, signal.SIGKILL)  # type: ignore[attr-defined]
            try:
                self._popen.wait(timeout=1)
            except subprocess.TimeoutExpired:
                logger.warning("PID %s survived SIGKILL — possible orphan", pid)
        if self._master_fd is not None:
            with contextlib.suppress(OSError):
                os.close(self._master_fd)


# ---------------------------------------------------------------------------
# Provider factories
# ---------------------------------------------------------------------------


def _ensure_tmp_dir(project_dir: Path) -> Path:
    tmp = project_dir / ".scistudio" / ".tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


def _ensure_mcp_config(project_dir: Path) -> Path:
    """Make sure ``<project>/.scistudio/mcp.json`` exists for ``--mcp-config``.

    Without this file, claude exits immediately because it cannot load
    the MCP bridge.  We write a project-scoped entry pointing at
    ``scistudio mcp-bridge`` so the embedded TUI sees SciStudio's tools.
    Idempotent: rewrites the file each call so a stale path / renamed
    project picks up the current ``project_dir`` automatically.

    Whole-file replacement is correct **only** here: ``.scistudio/`` is
    SciStudio's own directory and no other tool writes into it. It is
    forbidden for provider-owned config files — see
    :func:`_merge_provider_mcp_config` (FR-017a).
    """
    from scistudio.cli.install import MCP_SERVER_NAME, _mcp_entry_payload

    config_path = project_dir / ".scistudio" / "mcp.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"mcpServers": {MCP_SERVER_NAME: _mcp_entry_payload(project_dir)}}
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return config_path


def _read_text_with_retry(path: Path) -> str:
    """``path.read_text``, retrying briefly while the file is busy.

    This is the read half of the same Windows defect that
    :func:`scistudio.cli.install._replace_with_retry` fixes from the write side,
    and it is one mechanism seen from both ends: ``os.replace`` briefly makes
    the destination unopenable, and Python's ``open()`` does not pass
    ``FILE_SHARE_DELETE``, so a concurrent *reader* gets ``PermissionError``
    even though nothing is wrong with the file.

    Measured on Windows with 240 overlapping :func:`_merge_provider_mcp_config`
    calls against one config file, after the rename fix had landed: 27, 16 and
    21 failures across three runs, **every one of them raised here** and none in
    the rename.

    The user-visible effect is milder than the lost write that motivated the
    write-side fix — the launch fails loudly instead of silently starting an
    agent with no SciStudio tools — but it is still a spurious failure from a
    transient, self-clearing condition, so it gets the same treatment: spend a
    bounded budget, then let the real error surface.

    The delay schedule is imported from :mod:`scistudio.cli.install` rather than
    restated, so the two halves of one defect cannot drift to different budgets.
    Only ``PermissionError`` is retried: a missing file is already excluded by
    the caller's ``is_file()`` guard, and every other ``OSError`` (a directory
    where a file was expected, a real I/O error) is permanent and is raised on
    the first attempt rather than after a pointless wait.
    """
    from scistudio.cli.install import _REPLACE_RETRY_DELAYS

    for delay in _REPLACE_RETRY_DELAYS:
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError:
            time.sleep(delay)
    # Budget spent. Unguarded on purpose: a file that is still unreadable is a
    # real failure and must surface carrying the OS's own message, never be
    # swallowed into a silent partial launch.
    return path.read_text(encoding="utf-8")


def _merge_provider_mcp_config(descriptor: ProviderDescriptor, project_dir: Path) -> Path:
    """Merge the SciStudio MCP entry into a **provider-owned** config file.

    Used by the :attr:`~...McpStrategy.PROJECT_FILE` strategy, currently only
    Kimi Code (``<project>/.kimi-code/mcp.json``). That path belongs to Kimi,
    not to SciStudio, and the user may have registered their own MCP servers
    there, so :func:`_ensure_mcp_config`'s whole-file rewrite would silently
    destroy configuration with no recovery path.

    This function therefore reads, merges only the SciStudio server entry, and
    atomically replaces the file (FR-017a), following the merge-preserving
    precedent in :mod:`scistudio.cli.install` rather than the clobbering
    helper. A zero-byte or whitespace-only file carries no user content to
    preserve and is treated as absent.

    Three shapes raise instead of being overwritten (FR-017b), because each
    would otherwise destroy content SciStudio does not own and the user cannot
    recover: a document that does not parse as JSON, a document that parses to
    something other than an object, and an ``mcpServers`` key whose value is
    not an object. The last one is the quietest of the three — coercing it to
    a fresh ``{}`` would change a key outside the SciStudio entry with no
    error and no trace — so it is rejected on the same terms as the others.

    The written payload is the provider-agnostic
    :func:`~scistudio.cli.install._mcp_entry_payload` used by every other
    strategy (FR-018); only the location differs.

    Both file operations tolerate a concurrent SciStudio process working on the
    same file: the read through :func:`_read_text_with_retry`, the write through
    ``_atomic_write_json``'s unique staging name and retrying rename. A
    transient busy file and a corrupt one stay firmly separate — the first is
    retried and then raises the OS error, the second raises immediately and is
    never retried, because waiting cannot make malformed JSON parse.
    """
    from scistudio.cli.install import MCP_SERVER_NAME, _atomic_write_json, _mcp_entry_payload

    config_path = descriptor.mcp.project_file_path(project_dir)
    if config_path is None:  # pragma: no cover - guarded by descriptor validation
        raise ValueError(f"provider {descriptor.key!r} declares no project-scope MCP file")

    data: dict[str, object] = {}
    if config_path.is_file():
        # Retried while busy: a concurrent writer's ``os.replace`` makes this
        # file transiently unopenable on Windows. See _read_text_with_retry.
        raw = _read_text_with_retry(config_path)
        if raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"refusing to overwrite malformed JSON at {config_path}: {exc}. "
                    f"This file belongs to {descriptor.label}, not to SciStudio. "
                    "Fix or move it, then relaunch so SciStudio can register its "
                    "MCP server without discarding your own entries."
                ) from exc
            if not isinstance(parsed, dict):
                raise RuntimeError(
                    f"refusing to overwrite non-object JSON at {config_path}. "
                    f"This file belongs to {descriptor.label}, not to SciStudio."
                )
            data = parsed

    servers = data.get("mcpServers")
    if servers is None:
        servers = {}
    elif not isinstance(servers, dict):
        # Parseable JSON whose ``mcpServers`` is a string, list, or number.
        # Replacing it with a fresh object would silently discard a key
        # SciStudio does not own — exactly the destruction FR-017a exists to
        # prevent, which permits changing only the SciStudio server entry.
        raise RuntimeError(
            f"refusing to replace the non-object 'mcpServers' value at {config_path} "
            f"(found {type(servers).__name__}). This file belongs to {descriptor.label}, "
            "not to SciStudio. Fix or move it, then relaunch so SciStudio can register "
            "its MCP server without discarding your own entries."
        )
    data["mcpServers"] = servers
    servers[MCP_SERVER_NAME] = _mcp_entry_payload(project_dir)

    _atomic_write_json(config_path, data)
    return config_path


def _write_system_prompt_tempfile(project_dir: Path) -> Path:
    """Render the system prompt and persist it to a temp file.

    Returns the absolute path; caller passes it to claude as
    ``--append-system-prompt @<path>`` and registers it for cleanup.
    """
    from scistudio.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(project_dir)
    tmp_dir = _ensure_tmp_dir(project_dir)
    # ``delete=False`` because the spawned subprocess owns the file
    # lifetime — :meth:`PtyProcess.kill_tree` cleans it up.
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        prefix="scistudio-prompt-",
        dir=str(tmp_dir),
        delete=False,
        encoding="utf-8",
    ) as handle:
        handle.write(prompt)
        name = handle.name
    return Path(name)


def spawn_agent(
    descriptor: ProviderDescriptor,
    *,
    project_dir: Path,
    dangerous: bool,
    cols: int = 120,
    rows: int = 30,
    extra_env: dict[str, str] | None = None,
    prompt: str = "",
    _spawn_argv: list[str] | None = None,
) -> PtyProcess:
    """Spawn any registered agent CLI inside a PTY, anchored at ``project_dir``.

    This is the **single** spawn function for every agent provider (FR-007).
    It contains no ``if provider == …`` chain: every per-CLI difference — the
    binary name and where to find it, the system-prompt mechanism, the MCP
    injection mechanism, and the bypass-permission flag spelling — is read off
    ``descriptor``. Adding a sixth provider adds a registry row, not a branch.

    Argv is assembled in a fixed order::

        <binary> [<system-prompt flag> @<file>] [<mcp argv>]
                 [<bypass argv> | <manual argv>] [-- <prompt>]

    The ``--`` end-of-options separator before an AI Block prompt is required,
    not cosmetic (#1789): ``--mcp-config`` is variadic, so without it Claude
    Code swallows the trailing prompt as another MCP config path ("Invalid MCP
    configuration") and exits. Ordering it after the MCP argv is what makes
    ask mode work, not only bypass mode where the bypass flag happened to
    separate them.

    #1994 changed two things about the tail of that line:

    * The permission fragment is now a *choice*, never an omission. Safe mode
      appends ``descriptor.manual_argv`` instead of appending nothing, so the
      CLI cannot fall back to a persisted auto-accept mode behind a user who
      asked to approve every action.
    * The prompt fragment is skipped entirely for a provider whose
      ``prompt_argv_prefix`` is ``None``. Kimi Code has no positional prompt
      argument, so appending one made it exit 1 before the TUI ever painted.

    Parameters
    ----------
    descriptor
        Registry descriptor for the provider to launch. Must be
        :attr:`~...ProviderKind.AGENT` kind; the ``user-terminal``
        pseudo-provider is spawned by :func:`spawn_user_terminal`.
    project_dir
        Absolute project root. Becomes the PTY's working directory and anchors
        every MCP config path.
    dangerous
        When ``True`` appends ``descriptor.bypass_argv``; when ``False``
        appends ``descriptor.manual_argv``. Must be a deliberate user opt-in
        upstream.
    cols, rows
        Initial viewport.
    extra_env
        Per-invocation environment additions (e.g.
        ``SCISTUDIO_AI_BLOCK_RUN_DIR`` from ``open_engine_initiated_tab``).
    prompt
        AI Block prompt delivered as the agent's positional argument.
    _spawn_argv
        Test seam — when set, replaces the resolved argv (used by the WS
        integration tests to spawn a tiny echo subprocess instead of a real
        agent binary). Production callers leave it ``None``. Side effects that
        the provider needs regardless of argv — the system-prompt temp file and
        the MCP config write — still run, matching the previous behaviour.
    """
    if descriptor.kind is not ProviderKind.AGENT:
        raise ValueError(f"spawn_agent requires an agent provider; {descriptor.key!r} is {descriptor.kind.value}")

    cleanup_paths: list[Path] = []
    prompt_argv: list[str] = []
    if descriptor.system_prompt.strategy is SystemPromptStrategy.FLAG_FILE:
        # Only a flag with ``@<file>`` indirection may carry the composed
        # prompt; a literal-text flag would put an unbounded string on the
        # command line (spec §4.1), so those providers stay ambient.
        flag = descriptor.system_prompt.flag
        if not flag:  # pragma: no cover - guarded by registry completeness tests
            raise ValueError(f"provider {descriptor.key!r} declares FLAG_FILE with no flag")
        prompt_path = _write_system_prompt_tempfile(project_dir)
        cleanup_paths.append(prompt_path)
        prompt_argv = [flag, f"@{prompt_path}"]

    mcp_argv = _mcp_argv(descriptor, project_dir)

    if _spawn_argv is not None:
        argv = list(_spawn_argv)
    else:
        # #1994 finding 3: SciStudio wrote the project's hooks, so a CLI that
        # gates them behind a trust review is asking the user to vouch for
        # SciStudio's own files — through a prompt the embedded tab never
        # shows. Empty for every provider without such a gate.
        argv = [_resolve_agent_binary(descriptor), *descriptor.hook_trust_argv, *prompt_argv, *mcp_argv]
        # #1994 finding 2: state the permission mode in both directions. The
        # previous ``if dangerous:`` left safe mode flagless, which reads as
        # "no opinion" to every one of these CLIs and lets a persisted
        # auto-accept mode win over the user's Manual Approve selection.
        argv.extend(descriptor.bypass_argv if dangerous else descriptor.manual_argv)

    if prompt:
        argv.extend(_initial_prompt_argv(descriptor, prompt, argv[0] if argv else ""))

    return PtyProcess(
        argv,
        cwd=project_dir,
        cols=cols,
        rows=rows,
        cleanup_paths=cleanup_paths,
        extra_env=extra_env,
    )


#: Windows launcher extensions that are *batch scripts*, not real executables.
#: ``CreateProcess`` cannot run these directly; it silently re-launches them
#: through ``cmd.exe``, whose command-line parser ends the command at the first
#: line feed. Anything after it is discarded before the target program is
#: reached, so an argument containing a newline arrives truncated.
_BATCH_LAUNCHER_SUFFIXES = frozenset({".cmd", ".bat"})


def _is_batch_launcher(binary: str) -> bool:
    """Whether *binary* is a Windows batch launcher rather than a real exe.

    Deliberately not gated on ``sys.platform``: a ``.cmd`` argv[0] only ever
    occurs on Windows, and keying off the resolved name instead of the host
    keeps the behaviour reproducible on a Linux CI runner.
    """
    return Path(binary).suffix.lower() in _BATCH_LAUNCHER_SUFFIXES


def _initial_prompt_argv(descriptor: ProviderDescriptor, prompt: str, binary: str) -> list[str]:
    """Render the trailing ``[-- <prompt>]`` fragment for *descriptor*.

    Two #1994 live-test failures are handled here, both of which produced a
    launch that looked like SciStudio's fault but was really a mismatch between
    one fixed argv shape and two very different CLI surfaces.

    **No positional prompt at all.** ``prompt_argv_prefix is None`` means the
    CLI parses its first positional as a subcommand. Kimi Code does, so
    ``kimi -- "<task>"`` exits 1 with ``unknown command`` before painting
    anything. Appending nothing would launch a task-less agent that looks
    healthy and does nothing, which is worse than the crash, so this raises
    instead and lets the AI Block surface the descriptor's own explanation.

    **Newline truncation through a batch launcher.** ``codex`` installs from
    npm as ``codex.cmd``; there is no ``codex.exe`` on PATH (the real binary
    lives under a hashed ``node_modules`` path). ``CreateProcess`` therefore
    runs it via ``cmd.exe``, which terminates its command line at the first line
    feed — so the AI Block's multi-line prompt reached codex cut off after its
    first line, exactly the ``manifest at:`` cut the owner observed. Claude Code
    resolves to ``claude.exe`` and was never affected, which is why this looked
    codex-specific.

    Collapsing the newlines is the only fix available at this layer: cmd.exe has
    no escape for a literal line feed in a command line, and the real
    ``codex.exe`` is not at a stable, registry-nameable path. Collapsing keeps
    every word of the prompt — only the line structure is lost — where the
    status quo silently dropped most of the text. Providers that resolve to a
    real executable keep their exact multi-line prompt, so this changes nothing
    for them.
    """
    prefix = descriptor.prompt_argv_prefix
    if prefix is None:
        raise ValueError(
            f"provider {descriptor.key!r} cannot receive an initial prompt on its command line: "
            f"{descriptor.prompt_unsupported_reason or 'no positional prompt argument.'}"
        )
    return [*prefix, _flatten_for_batch_launcher(prompt) if _is_batch_launcher(binary) else prompt]


def _flatten_for_batch_launcher(prompt: str) -> str:
    """Collapse newlines so a ``cmd.exe``-mediated spawn keeps the whole text.

    Every run of CR/LF becomes a single space. Blank-line paragraph breaks and
    indentation therefore disappear, which is a real loss of readability, and a
    smaller one than the current behaviour of losing every line but the first.

    ``str.splitlines`` is the splitter on purpose: it covers ``\\r\\n``, bare
    ``\\r`` and the other control characters a command line cannot carry, so no
    line terminator survives to reach ``cmd.exe``.
    """
    return " ".join(segment.strip() for segment in prompt.splitlines() if segment.strip())


def _resolve_agent_binary(descriptor: ProviderDescriptor) -> str:
    """Resolve ``descriptor``'s binary, falling back to the bare name.

    The bare-name fallback keeps the failure inside the PTY (where the user
    sees the OS's own "not found" message in the terminal they opened) rather
    than raising out of the spawn call, which is the pre-existing behaviour.
    """
    resolved = resolve_binary(descriptor)
    if resolved is not None:
        return str(resolved)
    return descriptor.binary_candidates[0]


def _mcp_argv(descriptor: ProviderDescriptor, project_dir: Path) -> list[str]:
    """Apply ``descriptor``'s MCP injection strategy and return its argv share.

    Three observed shapes, all carrying the same provider-agnostic payload
    (FR-018):

    ``FLAG``
        Pass ``--mcp-config <project>/.scistudio/mcp.json``. SciStudio owns
        that file, so it is rewritten wholesale each launch and a renamed
        project picks up the new path automatically.
    ``CODEX_OVERRIDES``
        Codex has no ``--mcp-config``; it walks project-scope and user-scope
        ``config.toml``. The embedded chat owns the spawn, so it passes the
        current entry explicitly via ``-c`` overrides rather than trusting
        discovery to find a non-stale file.
    ``PROJECT_FILE``
        Write the entry into the provider's own project-scope discovery
        location before the process starts (FR-017), merge-preserving because
        the file is provider-owned.
    """
    strategy = descriptor.mcp.strategy
    if strategy is McpStrategy.FLAG:
        flag = descriptor.mcp.flag
        if not flag:  # pragma: no cover - guarded by registry completeness tests
            raise ValueError(f"provider {descriptor.key!r} declares an MCP flag strategy with no flag")
        return [flag, str(_ensure_mcp_config(project_dir))]
    if strategy is McpStrategy.CODEX_OVERRIDES:
        return _codex_mcp_config_overrides(project_dir)
    if strategy is McpStrategy.PROJECT_FILE:
        _merge_provider_mcp_config(descriptor, project_dir)
        return []
    return []


# There is deliberately no ``spawn_provider(key, …)`` convenience wrapper: it
# would only re-forward every keyword argument, which is byte-for-byte the
# duplication this change exists to remove. A caller holding a provider key
# builds its own spawner map straight off the registry, e.g.
#
#     {d.key: (spawn_user_terminal if d.kind is ProviderKind.TERMINAL
#              else functools.partial(spawn_agent, d)) for d in REGISTRY}
#
# which stays registry-derived and needs no edit for a sixth provider (FR-006).


def spawn_user_terminal(
    *,
    project_dir: Path,
    dangerous: bool,
    cols: int = 120,
    rows: int = 30,
    extra_env: dict[str, str] | None = None,
    # A user shell has no initial prompt; accepted for a uniform spawner signature.
    prompt: str = "",
    _spawn_argv: list[str] | None = None,
) -> PtyProcess:
    """Spawn a desktop user shell with SciStudio's user dependency env."""
    del dangerous
    from scistudio.desktop.paths import user_python_terminal_env, user_terminal_post_rc_invocation

    env = user_python_terminal_env(sys.executable)
    if extra_env:
        env.update(extra_env)

    # #1838: run the shell against a post-rc shim so the bundled Python bin is
    # re-prepended AFTER the user's dotfiles (conda init) run; otherwise a
    # `(base)` conda env shadows our wrappers and `pip install` lands in conda
    # base with no effect on the app.
    argv = list(_spawn_argv or _user_shell_argv())
    argv, env = user_terminal_post_rc_invocation(argv, env)

    return PtyProcess(
        argv,
        cwd=project_dir,
        cols=cols,
        rows=rows,
        cleanup_paths=[],
        extra_env=env,
    )


def _user_shell_argv() -> list[str]:
    if sys.platform == "win32":
        for name, args in (
            ("pwsh", ["-NoLogo"]),
            ("powershell", ["-NoLogo"]),
            ("cmd", []),
        ):
            resolved = resolve_windows_executable(name)
            if resolved:
                return [resolved, *args]
        return ["cmd"]

    shell = os.environ.get("SHELL")
    if shell and Path(shell).is_file():
        return [shell]
    for candidate in ("/bin/zsh", "/bin/bash", "/bin/sh"):
        if Path(candidate).is_file():
            return [candidate]
    return ["sh"]


def _codex_mcp_config_overrides(project_dir: Path) -> list[str]:
    """Render Codex ``-c`` overrides for the SciStudio MCP server.

    Codex project-scope config loading has changed across 2026 CLI builds,
    and stale user-scope config can point at the wrong Python interpreter.
    The embedded SciStudio chat owns the process spawn, so pass the current
    project MCP entry explicitly, just as the :attr:`McpStrategy.FLAG`
    providers pass ``--mcp-config``.
    """
    from scistudio.cli.install import MCP_SERVER_NAME, _mcp_entry_payload

    entry = _mcp_entry_payload(project_dir)
    command = entry["command"]
    args = entry["args"]
    env = entry.get("env")

    if not isinstance(command, str):
        raise TypeError("Codex MCP command must be a string")
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise TypeError("Codex MCP args must be a list of strings")
    if not isinstance(env, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in env.items()
    ):
        raise TypeError("Codex MCP env must be a string map")

    env_literal = "{" + ",".join(f"{key}={json.dumps(value)}" for key, value in env.items()) + "}"
    prefix = f"mcp_servers.{MCP_SERVER_NAME}"
    return [
        "-c",
        f"{prefix}.command={json.dumps(command)}",
        "-c",
        f"{prefix}.args={json.dumps(args)}",
        "-c",
        f"{prefix}.env={env_literal}",
    ]
