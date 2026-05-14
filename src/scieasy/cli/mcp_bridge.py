"""``scieasy mcp-bridge`` — stdio proxy between an external MCP client and SciEasy.

Per ADR-033 §3 D2 / spec OQ2, an external MCP client (Claude Code, Codex,
etc.) is configured (via the generated ``mcp.json``) to spawn this
subprocess when the user opens a chat session. The bridge supports two
modes:

* **Attached mode** — if the SciEasy backend is already running and has
  bound its in-process :class:`scieasy.ai.agent.mcp.server.MCPServer` to
  the project-local socket (``<project>/.scieasy/mcp.sock`` on POSIX,
  ``mcp.sock.port`` on Windows), the bridge connects to it and proxies
  JSON-RPC frames bidirectionally between its own stdin/stdout and the
  socket.

* **Standalone mode** — if no backend is running (or the socket is
  unreachable), the bridge spawns an in-process MCP server inside its
  own event loop via
  :func:`scieasy.ai.agent.mcp.runtime.start_inprocess_server` and proxies
  through that. This lets external CLIs use SciEasy's MCP tools even
  when the GUI/API isn't running, which is the model #787 introduced.

Project discovery: the env var ``SCIEASY_PROJECT_DIR`` (set by the
``mcp.json`` written by ``scieasy install``) tells the bridge which
SciEasy project to scope the registries to. If unset, ``run()`` exits
with code 2 so the calling CLI surfaces a clear configuration error
rather than a silent fail-open.

Framing: line-delimited JSON over the socket, matching
:class:`MCPServer`'s framing.

The proxy uses a threaded stdin reader because Windows asyncio's
``loop.connect_read_pipe`` does not support ``sys.stdin``. Both
platforms therefore share the same ``run_in_executor`` pump.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket as socket_mod
import sys
from pathlib import Path

import typer

logger = logging.getLogger(__name__)


def _project_dir_from_env() -> Path | None:
    """Resolve the active project dir from ``SCIEASY_PROJECT_DIR``.

    Returns ``None`` when the env var is unset or empty so callers can
    decide how to fail (the bridge ``run()`` exits 2 in this case).
    """
    raw = os.environ.get("SCIEASY_PROJECT_DIR", "").strip()
    if not raw:
        return None
    return Path(raw)


def _attached_socket_path(project_dir: Path) -> Path:
    """Conventional path the backend writes its socket / port file to."""
    return project_dir / ".scieasy" / "mcp.sock"


def _try_connect_attached(project_dir: Path) -> socket_mod.socket | None:
    """Try to connect to a running backend's MCP socket; return None on failure.

    Synchronous so the caller can decide which mode to enter before
    constructing the asyncio loop.
    """
    sock_path = _attached_socket_path(project_dir)
    try:
        if sys.platform == "win32":
            port_file = sock_path.with_suffix(sock_path.suffix + ".port")
            if not port_file.exists():
                return None
            try:
                port = int(port_file.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                return None
            s = socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect(("127.0.0.1", port))
            s.settimeout(None)
            return s
        else:
            if not sock_path.exists():
                return None
            s = socket_mod.socket(socket_mod.AF_UNIX, socket_mod.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect(str(sock_path))
            s.settimeout(None)
            return s
    except OSError as exc:
        logger.info("mcp-bridge: no running backend at %s (%s); falling back to standalone", sock_path, exc)
        return None


async def _proxy_stdio_to_socket(sock: socket_mod.socket) -> int:
    """Pump frames between this process's stdin/stdout and *sock*.

    Returns 0 on clean stdin EOF. Uses an executor-backed reader for
    stdin (Windows asyncio cannot ``connect_read_pipe(sys.stdin)``) and
    asyncio streams for the socket side.
    """
    loop = asyncio.get_running_loop()
    sock.setblocking(False)
    reader, writer = await asyncio.open_connection(sock=sock)

    async def stdin_to_socket() -> None:
        """Read from blocking stdin in a thread; forward to the socket.

        On EOF, half-close the socket's write side so the server knows
        we're done sending. We do NOT cancel the reader side here — we
        want to keep reading any final responses the server is about to
        flush.
        """
        stdin_buffer = sys.stdin.buffer
        # ``BinaryIO`` doesn't declare ``read1`` but every concrete
        # buffered stdin we see (BufferedReader, BytesIO) has it.
        read1 = stdin_buffer.read1  # type: ignore[union-attr]
        try:
            while True:
                chunk = await loop.run_in_executor(None, read1, 65536)
                if not chunk:
                    break
                writer.write(chunk)
                try:
                    await writer.drain()
                except (ConnectionResetError, BrokenPipeError):
                    return
        finally:
            # Half-close so the server sees EOF on its read side and
            # eventually closes its write side too. That EOF on the
            # reader is what terminates ``socket_to_stdout``. Some
            # transports don't support half-close; the outer
            # writer.close() at function exit will still propagate the
            # disconnect.
            with contextlib.suppress(OSError, NotImplementedError):
                writer.write_eof()

    async def socket_to_stdout() -> None:
        """Read from the socket; forward to stdout (line-buffered)."""
        stdout_buffer = sys.stdout.buffer
        while True:
            try:
                data = await reader.read(65536)
            except (ConnectionResetError, asyncio.IncompleteReadError):
                break
            if not data:
                break
            stdout_buffer.write(data)
            stdout_buffer.flush()

    stdin_task = asyncio.create_task(stdin_to_socket(), name="mcp-bridge:stdin->socket")
    out_task = asyncio.create_task(socket_to_stdout(), name="mcp-bridge:socket->stdout")
    try:
        # Drive both pumps until the socket reader hits EOF — that's
        # the only definitive end-of-conversation signal. ``stdin_task``
        # finishing is necessary but not sufficient; we still need to
        # let any in-flight server response flush to stdout.
        await out_task
    finally:
        # If stdin is still pumping (e.g. server closed early), cancel
        # it; we won't get any more responses anyway.
        if not stdin_task.done():
            stdin_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await stdin_task
        with contextlib.suppress(Exception):
            writer.close()
            await writer.wait_closed()
    return 0


async def _run_attached(project_dir: Path, sock: socket_mod.socket) -> int:
    """Attached-mode entry point: proxy stdio through *sock*."""
    logger.info("mcp-bridge: attached to backend socket for project_dir=%s", project_dir)
    return await _proxy_stdio_to_socket(sock)


async def _run_standalone(project_dir: Path | None) -> int:
    """Standalone-mode entry point: spawn in-process server, proxy through it."""
    from scieasy.ai.agent.mcp.runtime import start_inprocess_server, stop_inprocess_server

    server, _runtime = await start_inprocess_server(project_dir)
    logger.info("mcp-bridge: started in-process MCP server at %s", server.socket_path)
    try:
        # Connect to the server we just started. On POSIX it's a Unix
        # socket; on Windows it's a TCP loopback whose port the server
        # wrote into ``<socket_path>.port``.
        if sys.platform == "win32":
            port = server.port
            if port is None:
                # Defensive — start() always sets _port on win32, but
                # if it ever doesn't, fail loud rather than hanging.
                raise RuntimeError("in-process MCP server started without a port on Windows")
            client_sock = socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_STREAM)
            client_sock.connect(("127.0.0.1", port))
        else:
            client_sock = socket_mod.socket(socket_mod.AF_UNIX, socket_mod.SOCK_STREAM)
            client_sock.connect(str(server.socket_path))
        return await _proxy_stdio_to_socket(client_sock)
    finally:
        await stop_inprocess_server(server)


def run(socket: str | None) -> int:
    """Execute the bridge once; return the process exit code.

    Behaviour:

    1. Resolve the active project dir from ``SCIEASY_PROJECT_DIR``.
       If unset, return 2 (clear configuration error — the caller's
       ``mcp.json`` must set it).
    2. Probe the conventional backend socket. If reachable, enter
       **attached mode** and proxy stdin↔socket until stdin EOF.
    3. Otherwise enter **standalone mode**: spawn an in-process
       :class:`MCPServer` via :mod:`scieasy.ai.agent.mcp.runtime` and
       proxy through that.

    Parameters
    ----------
    socket
        Explicit socket path override from the ``--socket`` flag. When
        provided, skips the project-dir probe and connects directly.
        Used mostly by tests and power users; production callers rely
        on the env-var-driven path.

    Returns
    -------
    int
        ``0`` on clean stdin EOF; ``2`` on configuration error
        (no project dir, or explicit socket unreachable).
    """
    # Explicit --socket bypasses all discovery; used by tests and
    # power users wanting to point at a specific transport.
    if socket is not None:
        explicit_path = Path(socket)
        try:
            if sys.platform == "win32":
                port_file = explicit_path.with_suffix(explicit_path.suffix + ".port")
                if port_file.exists():
                    port = int(port_file.read_text(encoding="utf-8").strip())
                    sock_obj = socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_STREAM)
                    sock_obj.connect(("127.0.0.1", port))
                else:
                    print(
                        f"scieasy mcp-bridge: --socket {socket} unreachable (no .port file)",
                        file=sys.stderr,
                    )
                    return 2
            else:
                sock_obj = socket_mod.socket(socket_mod.AF_UNIX, socket_mod.SOCK_STREAM)
                sock_obj.connect(str(explicit_path))
        except OSError as exc:
            print(f"scieasy mcp-bridge: cannot connect to {socket}: {exc}", file=sys.stderr)
            return 2
        try:
            return asyncio.run(_proxy_stdio_to_socket(sock_obj))
        except KeyboardInterrupt:
            return 0

    project_dir = _project_dir_from_env()
    if project_dir is None:
        print(
            "scieasy mcp-bridge: SCIEASY_PROJECT_DIR is not set. The bridge needs "
            "a project root to scope its block/type registries. Re-run "
            "`scieasy install` or set SCIEASY_PROJECT_DIR in your MCP client config.",
            file=sys.stderr,
        )
        return 2

    attached_sock = _try_connect_attached(project_dir)
    try:
        if attached_sock is not None:
            return asyncio.run(_run_attached(project_dir, attached_sock))
        return asyncio.run(_run_standalone(project_dir))
    except KeyboardInterrupt:
        return 0


def _typer_command(
    socket: str = typer.Option(
        None,
        "--socket",
        help="Explicit socket path / .port-file location override (skips backend discovery).",
    ),
) -> None:
    """Typer entry-point wrapper around :func:`run`.

    Translates the Typer-parsed arguments into a :class:`typer.Exit`
    with the bridge's return code so ``scieasy mcp-bridge`` exits with
    the exact integer returned by :func:`run`.
    """
    raise typer.Exit(code=run(socket))


def register(app: typer.Typer) -> None:
    """Register the ``mcp-bridge`` subcommand on the given Typer app.

    Called from :mod:`scieasy.cli.main` at module import time so the
    existing ``scieasy`` console script gains the subcommand without a
    new ``[project.scripts]`` entry. Mirrors the pattern used by
    :func:`scieasy.cli.hook_bridge.register`.
    """
    app.command(
        "mcp-bridge",
        help="Proxy MCP JSON-RPC frames between the calling MCP client and SciEasy.",
    )(_typer_command)


if __name__ == "__main__":
    sys.exit(run(None))
