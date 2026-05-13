"""``scieasy mcp-bridge`` — stdio proxy between CC and the MCP socket.

Claude Code (configured via ``mcp.json``) spawns this subprocess when the
user opens a chat session. The bridge connects CC's stdin/stdout to the
SciEasy in-process MCP server (started in ``api/app.py`` lifespan) over
either:

* a Unix domain socket at ``<project>/.scieasy/mcp.sock`` (POSIX), or
* a TCP loopback whose port is written to
  ``<project>/.scieasy/mcp.sock.port`` (Windows).

The bridge:

1. Resolves the socket path from ``--socket`` or, if absent, from
   ``$SCIEASY_PROJECT_DIR`` (set by the agent provider when spawning CC).
2. Connects.
3. Pumps bytes both directions (stdin → socket, socket → stdout) until
   either side closes.

Per ADR-033 §3 D2 / spec OQ2.
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

    The first that exists (or has a sibling ``.port`` file on Windows) wins.
    """
    out: list[Path] = []
    if socket:
        out.append(Path(socket))
    project_dir = os.environ.get("SCIEASY_PROJECT_DIR")
    if project_dir:
        out.append(Path(project_dir) / ".scieasy" / _DEFAULT_SOCKET_FILENAME)
    out.append(Path.home() / ".scieasy" / ".scieasy" / _DEFAULT_SOCKET_FILENAME)
    return out


def _resolve_socket_path(socket: str | None) -> Path:
    """Pick the first candidate that the backend has actually exposed."""
    candidates = _candidate_socket_paths(socket)
    for cand in candidates:
        if sys.platform == "win32":
            port_file = cand.with_suffix(cand.suffix + ".port")
            if port_file.is_file():
                return cand
        elif cand.exists():
            return cand
    raise RuntimeError(
        "scieasy mcp-bridge: no MCP socket found at any candidate path: "
        + ", ".join(str(p) for p in candidates)
        + " — is the SciEasy backend running?"
    )


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


async def _serve(socket_path: Path) -> int:
    """Connect and pump bytes both directions until either side closes."""
    sock_reader, sock_writer = await _open_connection(socket_path)

    pump_in = asyncio.create_task(_pump_stdin_to_socket(sock_writer))
    pump_out = asyncio.create_task(_pump_socket_to_stdout(sock_reader))

    done, pending = await asyncio.wait([pump_in, pump_out], return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    # Surface the first exception, if any, but always exit 0 on clean EOF.
    for task in done:
        if task.exception() is not None:
            raise task.exception()  # type: ignore[misc]

    with contextlib.suppress(Exception):
        sock_writer.close()
        await sock_writer.wait_closed()

    return 0


def run(socket: str | None) -> int:
    """Execute the bridge once; return the process exit code.

    Exits 0 on clean EOF, 2 on configuration error (no socket / port
    file missing / backend not running), 1 on unexpected I/O error.
    """
    try:
        socket_path = _resolve_socket_path(socket)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        return asyncio.run(_serve(socket_path))
    except RuntimeError as exc:
        # Surfaced from _open_connection — missing socket / port file.
        print(f"scieasy mcp-bridge: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        print(f"scieasy mcp-bridge: unexpected error: {exc}", file=sys.stderr)
        return 1


def _typer_command(
    socket: str = typer.Option(
        None,
        "--socket",
        help="Path to the MCP server's Unix socket (POSIX) or named pipe (Windows). "
        "Defaults to $SCIEASY_PROJECT_DIR/.scieasy/mcp.sock.",
    ),
) -> None:
    raise typer.Exit(code=run(socket))


def register(app: typer.Typer) -> None:
    """Register the ``mcp-bridge`` subcommand on the given Typer app."""
    app.command(
        "mcp-bridge",
        help="Proxy MCP JSON-RPC frames between CC stdio and the SciEasy MCP socket.",
    )(_typer_command)


if __name__ == "__main__":
    sys.exit(run(None))
