"""``scieasy mcp-bridge`` — stdio proxy between an external CLI and the MCP server.

This subprocess is spawned by an MCP client (Claude Code, Codex, or any
other compatible CLI) when the user opens an agent session that
references the SciEasy MCP server. The bridge connects the client's
stdin/stdout to a SciEasy MCP server over either:

* a Unix domain socket at ``<project>/.scieasy/mcp.sock`` (POSIX), or
* a TCP loopback whose port is written to
  ``<project>/.scieasy/mcp.sock.port`` (Windows).

It operates in one of two modes:

1. **Attached mode** — a SciEasy backend (FastAPI app, ``scieasy gui``
   or ``scieasy serve``) is already running for this project. The
   bridge discovers the socket via ``--socket`` or the conventional
   path under ``$SCIEASY_PROJECT_DIR``, probes that it accepts a
   connection, and pumps bytes in both directions. Multiple CLIs
   (e.g. the embedded GUI agent + an external ``claude``) can share
   one backend's state in this mode.

2. **Standalone mode** (#787) — no backend is running. The bridge
   spins up an in-process :class:`MCPServer` (loading block + type
   registries from disk), binds a per-process socket, and serves
   exactly itself for the lifetime of this bridge process. Tear-down
   happens on stdin EOF.

Mode selection is automatic: if a known socket / port file exists and
its server accepts a connection, attached mode wins; otherwise the
bridge falls into standalone mode.

Per ADR-033 §3 D2 / spec OQ2 / issue #787.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import sys
from pathlib import Path
from typing import cast

import typer

_DEFAULT_SOCKET_FILENAME = "mcp.sock"


def _candidate_socket_paths(socket: str | None) -> list[Path]:
    """Return candidate socket paths in preference order.

    1. Explicit ``--socket`` argument.
    2. ``$SCIEASY_PROJECT_DIR/.scieasy/mcp.sock`` (the spec'd location).
    3. ``~/.scieasy/.scieasy/mcp.sock`` (the backend's fallback when no
       project was active when it started).
    """
    out: list[Path] = []
    if socket:
        out.append(Path(socket))
    project_dir = os.environ.get("SCIEASY_PROJECT_DIR")
    if project_dir:
        out.append(Path(project_dir) / ".scieasy" / _DEFAULT_SOCKET_FILENAME)
    out.append(Path.home() / ".scieasy" / ".scieasy" / _DEFAULT_SOCKET_FILENAME)
    return out


def _socket_advertises_live_server(socket_path: Path) -> bool:
    """Return ``True`` when *socket_path* points at a live MCP server.

    On POSIX the socket file must exist. On Windows the sibling
    ``<socket_path>.port`` file must exist and contain a parseable
    port. We do not yet attempt a TCP probe — the port file is
    written atomically by ``MCPServer.start()`` and cleaned up by
    ``MCPServer.stop()``, so its mere existence is a strong signal.
    Stale port files left behind by a crashed backend are the main
    failure mode; the actual connect attempt in
    :func:`_open_connection` provides the second layer of detection.
    """
    if sys.platform == "win32":
        port_file = socket_path.with_suffix(socket_path.suffix + ".port")
        if not port_file.is_file():
            return False
        try:
            int(port_file.read_text(encoding="utf-8").strip())
            return True
        except (OSError, ValueError):
            return False
    return socket_path.exists()


def _resolve_live_socket(socket: str | None) -> Path | None:
    """Pick the first candidate that looks like a live backend, or ``None``."""
    for cand in _candidate_socket_paths(socket):
        if _socket_advertises_live_server(cand):
            return cand
    return None


def _resolve_project_dir() -> Path | None:
    """Resolve the project directory for standalone-mode setup.

    Preference order: ``$SCIEASY_PROJECT_DIR``, then the current
    working directory if it contains a ``project.yaml`` (signalling a
    SciEasy project). Returns ``None`` when neither is available —
    the in-process server still starts so ``tools/list`` works, but
    project-scoped tools will surface a clear error.
    """
    env_val = os.environ.get("SCIEASY_PROJECT_DIR")
    if env_val:
        candidate = Path(env_val).expanduser().resolve()
        if candidate.is_dir():
            return candidate
    cwd = Path.cwd()
    if (cwd / "project.yaml").is_file():
        return cwd
    return None


async def _open_connection(
    socket_path: Path,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to the MCP transport.

    On Windows: read ``<socket_path>.port`` and open a TCP loopback
    connection. On POSIX: open the Unix domain socket directly.
    """
    if sys.platform == "win32":
        port_file = socket_path.with_suffix(socket_path.suffix + ".port")
        if not port_file.is_file():
            raise RuntimeError(f"scieasy mcp-bridge: port file {port_file} not found — is the SciEasy backend running?")
        port = int(port_file.read_text(encoding="utf-8").strip())
        return await asyncio.open_connection("127.0.0.1", port)
    if not socket_path.exists():
        raise RuntimeError(f"scieasy mcp-bridge: socket {socket_path} not found — is the SciEasy backend running?")
    return await asyncio.open_unix_connection(str(socket_path))


async def _pump_stdin_to_socket(
    sock_writer: asyncio.StreamWriter,
) -> None:
    """Read stdin in a thread; forward chunks to socket.

    We use ``run_in_executor`` instead of ``loop.connect_read_pipe`` because
    on Windows the ProactorEventLoop's IOCP registration fails on real
    stdin handles ([WinError 6] invalid handle) — both for terminal stdin
    and for the anonymous pipe Claude Code attaches when spawning us as
    an MCP server subprocess. Threaded blocking reads work on every
    platform.
    """
    loop = asyncio.get_running_loop()
    # sys.stdin.buffer is typed as BinaryIO which lacks .read1; the actual
    # runtime object is io.BufferedReader (or BufferedRWPair under -u). Use
    # a small helper so mypy stops complaining and we still get the
    # short-read semantics of read1.
    stdin_buf = sys.stdin.buffer

    def _read_chunk() -> bytes:
        reader = cast(io.BufferedReader, stdin_buf)
        return reader.read1(65536)

    while True:
        chunk = await loop.run_in_executor(None, _read_chunk)
        if not chunk:
            break
        sock_writer.write(chunk)
        await sock_writer.drain()
    try:
        if sock_writer.can_write_eof():
            sock_writer.write_eof()
    except OSError:
        pass


async def _pump_socket_to_stdout(
    sock_reader: asyncio.StreamReader,
) -> None:
    """Read socket chunks; write to stdout synchronously and flush.

    Same rationale as :func:`_pump_stdin_to_socket` — we avoid
    ``connect_write_pipe`` and just write to the underlying buffered
    stream, flushing after every chunk so framed JSON-RPC frames don't
    sit in Python's userspace buffer.
    """
    stdout_buf = sys.stdout.buffer
    while True:
        chunk = await sock_reader.read(65536)
        if not chunk:
            break
        stdout_buf.write(chunk)
        stdout_buf.flush()


async def _pump_both_directions(
    sock_reader: asyncio.StreamReader,
    sock_writer: asyncio.StreamWriter,
) -> None:
    """Pump bytes both directions until both sides close.

    Termination semantics:

    * When stdin closes (CLI exits), :func:`_pump_stdin_to_socket` writes
      EOF to the socket and returns. We then wait for the server-side
      pump to drain any responses already in flight before tearing down.
    * If the server side closes first (e.g. server crash), we cancel the
      stdin pump so we don't hang waiting on a dead connection.
    """
    pump_in = asyncio.create_task(_pump_stdin_to_socket(sock_writer))
    pump_out = asyncio.create_task(_pump_socket_to_stdout(sock_reader))

    # Phase 1: wait for the FIRST side to close.
    done, pending = await asyncio.wait([pump_in, pump_out], return_when=asyncio.FIRST_COMPLETED)

    # If stdin closed first, we want to let the server drain its in-flight
    # responses before tearing down. Otherwise (server closed first), the
    # stdin pump has nothing to do — cancel it.
    if pump_in in done and pump_out in pending:
        # Stdin EOF: server may still be processing the last request.
        # Wait (bounded) for the output pump to finish naturally.
        try:
            await asyncio.wait_for(pump_out, timeout=5.0)
        except TimeoutError:
            pump_out.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await pump_out
    elif pump_out in done and pump_in in pending:
        # Server-side closed first; cancel the stdin reader.
        pump_in.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await pump_in

    # Surface the first exception, if any, but always exit 0 on clean EOF.
    for task in done:
        if task.exception() is not None:
            raise task.exception()  # type: ignore[misc]

    with contextlib.suppress(Exception):
        sock_writer.close()
        await sock_writer.wait_closed()


async def _serve_attached(socket_path: Path) -> int:
    """Connect to an already-running backend and pump bytes."""
    sock_reader, sock_writer = await _open_connection(socket_path)
    await _pump_both_directions(sock_reader, sock_writer)
    return 0


async def _serve_standalone(project_dir: Path | None) -> int:
    """Spin up an in-process MCP server, then pump bytes against it.

    Used when no live backend is detected. The server's lifetime is
    bounded by stdin EOF — when the parent CLI closes the pipe, we
    tear it down cleanly.
    """
    from scieasy.ai.agent.mcp.runtime import start_inprocess_server, stop_inprocess_server

    server, _ = await start_inprocess_server(project_dir)
    try:
        # Connect a client side of the same socket so we can pump the
        # stdio bytes through the standard JSON-RPC path. Reuses the
        # exact same code path as attached mode below this point.
        sock_reader, sock_writer = await _open_connection(server.socket_path)
        try:
            await _pump_both_directions(sock_reader, sock_writer)
        finally:
            with contextlib.suppress(Exception):
                sock_writer.close()
                await sock_writer.wait_closed()
    finally:
        await stop_inprocess_server(server)
    return 0


def run(socket: str | None) -> int:
    """Execute the bridge once; return the process exit code.

    Behavior (#787):

    * If a live backend is detected at a candidate socket path, connect
      and pump bytes — same as the pre-#787 behavior.
    * Otherwise, spin up an in-process MCP server scoped to
      ``$SCIEASY_PROJECT_DIR`` (or the current dir if it contains
      ``project.yaml``) and serve from there.

    Exit codes:
      0 — clean EOF.
      1 — unexpected I/O error.
      2 — configuration error (e.g. explicit ``--socket`` was given but
          unreachable, AND we couldn't fall back to standalone).
    """
    # 1. Try attached mode first: if a known live socket exists, use it.
    live_socket = _resolve_live_socket(socket)
    if live_socket is not None:
        try:
            return asyncio.run(_serve_attached(live_socket))
        except RuntimeError as exc:
            # The socket looked live (file existed) but the connect
            # failed — typically a stale socket from a crashed backend.
            # Fall through to standalone mode rather than giving up.
            print(
                f"scieasy mcp-bridge: attached connect to {live_socket} failed "
                f"({exc}); falling back to standalone mode",
                file=sys.stderr,
            )
        except Exception as exc:  # pragma: no cover - defensive
            print(f"scieasy mcp-bridge: unexpected error: {exc}", file=sys.stderr)
            return 1

    # 2. Standalone mode.
    if socket is not None:
        # The user explicitly asked for a socket path that doesn't
        # look live. Honour their intent rather than silently
        # switching modes.
        print(
            f"scieasy mcp-bridge: --socket {socket} not advertising a live "
            "backend; refusing to start standalone (omit --socket to fall "
            "back to standalone mode automatically).",
            file=sys.stderr,
        )
        return 2

    project_dir = _resolve_project_dir()
    try:
        return asyncio.run(_serve_standalone(project_dir))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"scieasy mcp-bridge: standalone mode failed: {exc}", file=sys.stderr)
        return 1


def _typer_command(
    socket: str = typer.Option(
        None,
        "--socket",
        help="Path to a running MCP server's Unix socket (POSIX) or sentinel "
        "(Windows). When omitted, the bridge auto-detects a live backend; "
        "if none is running, it falls back to spinning up an in-process "
        "server scoped to $SCIEASY_PROJECT_DIR.",
    ),
) -> None:
    raise typer.Exit(code=run(socket))


def register(app: typer.Typer) -> None:
    """Register the ``mcp-bridge`` subcommand on the given Typer app."""
    app.command(
        "mcp-bridge",
        help="Proxy MCP JSON-RPC frames between a CLI's stdio and a SciEasy MCP server.",
    )(_typer_command)


if __name__ == "__main__":
    sys.exit(run(None))
