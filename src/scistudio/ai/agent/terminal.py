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

logger = logging.getLogger(__name__)

# Public re-exports for the route layer.
__all__ = ["PtyProcess", "spawn_claude", "spawn_codex"]


class PtyProcess:
    """Platform-uniform wrapper around a PTY-attached subprocess.

    The route layer interacts with this class only; ``_impl`` holds the
    backend-specific handle (a :class:`winpty.PtyProcess` on Windows,
    or a master file descriptor + :class:`subprocess.Popen` on POSIX).

    Lifecycle: callers spawn via :func:`spawn_claude` /
    :func:`spawn_codex`, then read / write / resize until the subprocess
    exits or :meth:`kill_tree` is invoked.

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
        child_env = os.environ.copy()
        child_env["TERM"] = "xterm-256color"
        child_env["COLORTERM"] = "truecolor"
        # Some Node-based TUIs respect FORCE_COLOR for 24-bit output
        # even when stdout is detected as not-a-tty during nested
        # spawns. Harmless when ignored.
        child_env.setdefault("FORCE_COLOR", "3")
        # Caller-supplied per-invocation env (e.g. SCISTUDIO_AI_BLOCK_RUN_DIR
        # from open_engine_initiated_tab so the spawned mcp-bridge
        # subprocess can resolve the active run dir for finish_ai_block,
        # ADR-035 §3.5 path a). These override anything inherited above
        # so each PTY gets the right per-block context without polluting
        # the engine's global environment.
        if extra_env:
            child_env.update(extra_env)

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
            popen = subprocess.Popen(
                argv,
                cwd=str(cwd),
                env=child_env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,  # fresh process group for killpg
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
    """
    import json

    from scistudio.cli.install import MCP_SERVER_NAME, _mcp_entry_payload

    config_path = project_dir / ".scistudio" / "mcp.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"mcpServers": {MCP_SERVER_NAME: _mcp_entry_payload(project_dir)}}
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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


def spawn_claude(
    *,
    project_dir: Path,
    dangerous: bool,
    cols: int = 120,
    rows: int = 30,
    extra_env: dict[str, str] | None = None,
    _spawn_argv: list[str] | None = None,
) -> PtyProcess:
    """Spawn ``claude`` inside a PTY, anchored at ``project_dir``.

    Argv:
        ``["claude", "--append-system-prompt", "@<prompt_file>",
            "--mcp-config", "<project>/.scistudio/mcp.json"]``
        plus ``--dangerously-skip-permissions`` when ``dangerous``.

    The system prompt file is composed via
    :func:`scistudio.ai.agent.system_prompt.compose_system_prompt` and
    deleted automatically on PTY teardown.

    Parameters
    ----------
    project_dir
        Absolute project root.  Becomes the PTY's working directory and
        anchors the MCP config path lookup.
    dangerous
        When ``True`` adds ``--dangerously-skip-permissions``.  Must be
        a deliberate user opt-in upstream.
    cols, rows
        Initial viewport.
    _spawn_argv
        Test seam — when set, replaces the real argv (used by the WS
        integration tests to spawn a tiny echo subprocess instead of
        the real claude binary).  Production callers leave it ``None``.
    """
    prompt_path = _write_system_prompt_tempfile(project_dir)
    mcp_config = _ensure_mcp_config(project_dir)

    if _spawn_argv is not None:
        argv = list(_spawn_argv)
    else:
        argv = [
            "claude",
            "--append-system-prompt",
            f"@{prompt_path}",
            "--mcp-config",
            str(mcp_config),
        ]
        if dangerous:
            argv.append("--dangerously-skip-permissions")

    return PtyProcess(
        argv,
        cwd=project_dir,
        cols=cols,
        rows=rows,
        cleanup_paths=[prompt_path],
        extra_env=extra_env,
    )


def spawn_codex(
    *,
    project_dir: Path,
    dangerous: bool,
    cols: int = 120,
    rows: int = 30,
    extra_env: dict[str, str] | None = None,
    _spawn_argv: list[str] | None = None,
) -> PtyProcess:
    """Spawn ``codex`` inside a PTY, anchored at ``project_dir``.

    Argv:
        ``["codex"]`` plus
        ``--dangerously-bypass-approvals-and-sandbox`` when
        ``dangerous``.

    Note that codex does **not** accept ``--mcp-config`` — per spike
    finding 6, it walks from project root to cwd loading every
    ``.codex/config.toml`` plus ``~/.codex/config.toml``. ADR-040 §3.7
    auto-provisions ``<project>/.codex/config.toml`` with the SciStudio MCP
    server entry; the user's ``scistudio install --target codex`` populates
    the user-scope ``~/.codex/config.toml`` as a fallback. Both paths
    converge on the same ``[mcp_servers.scistudio]`` block rendered by
    ``scistudio.cli.install._render_codex_block``.

    Codex also does not accept ``--append-system-prompt``; the SciStudio
    skill is picked up via the project-scope ``.agents/skills/scistudio/``
    tree (auto-provisioned per ADR-040 §3.5 + §3.8) and falls back to
    ``~/.agents/skills/scistudio/`` (registered by ``scistudio install``).

    Parameters
    ----------
    project_dir, dangerous, cols, rows
        See :func:`spawn_claude`.
    _spawn_argv
        Test seam (same semantics as :func:`spawn_claude`).
    """
    if _spawn_argv is not None:
        argv = list(_spawn_argv)
    else:
        argv = ["codex"]
        if dangerous:
            argv.append("--dangerously-bypass-approvals-and-sandbox")

    return PtyProcess(
        argv,
        cwd=project_dir,
        cols=cols,
        rows=rows,
        cleanup_paths=[],
        extra_env=extra_env,
    )
