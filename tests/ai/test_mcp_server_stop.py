"""Issue #2019 — ``MCPServer.stop()`` must not wait on attached clients.

``AbstractServer.close()`` only retires the listener; connections that are
already established keep running. Since Python 3.12 ``wait_closed()`` waits for
every connection handler to finish, and ``MCPServer._handle_client`` sits in
``await reader.readline()`` until its peer hangs up. So a ``stop()`` that only
did ``close()`` + ``wait_closed()`` blocked forever whenever a client was
attached.

That mattered because ``stop()`` runs inline on ``POST /api/projects/`` (via
``ensure_project_mcp_server``) when the server is rebound to a newly created or
opened project. A stalled ``stop()`` meant the request never returned and the
GUI stayed wedged behind its project modal with the busy indicator up.

Async tests use ``asyncio.run`` to match the convention in
``tests/ai/test_mcp_fastmcp.py`` (no ``pytest-asyncio`` dependency).
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
import time
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, TypeVar

from scistudio.ai.agent.mcp.server import _STOP_GRACE_SECONDS, MCPServer

# Outer guard so a regression fails the suite instead of hanging it.
_HANG_GUARD_SECONDS = 30.0

_T = TypeVar("_T")


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(coro)


async def _aclose(writer: asyncio.StreamWriter) -> None:
    """Close a client transport and wait for it, rather than leaving it to GC.

    A transport finalized by the collector emits a ResourceWarning, and a
    server-attached one reaped after its server cleared the waiter list raises
    out of ``__del__``. Draining here keeps each test self-contained.
    """
    writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()


async def _connect(server: MCPServer) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Open a client connection over whichever transport this platform uses."""
    if sys.platform == "win32":
        assert server.port is not None
        return await asyncio.open_connection("127.0.0.1", server.port)
    return await asyncio.open_unix_connection(str(server.socket_path))


async def _started_server(tmp_path: Path) -> MCPServer:
    server = MCPServer(socket_path=tmp_path / ".scistudio" / "mcp.sock", project_dir=tmp_path)
    await server.start()
    return server


def test_stop_returns_while_a_client_is_still_attached(tmp_path: Path) -> None:
    """The regression: an idle attached client must not pin ``stop()``."""

    async def scenario() -> float:
        server = await _started_server(tmp_path)
        _, writer = await _connect(server)
        # The client stays connected and sends nothing, so the handler is
        # parked in readline() — exactly the state that used to deadlock.
        await asyncio.sleep(0.05)

        started = time.monotonic()
        try:
            await asyncio.wait_for(server.stop(), timeout=_HANG_GUARD_SECONDS)
        finally:
            await _aclose(writer)
        return time.monotonic() - started

    elapsed = _run(scenario())
    # Returning at all proves the deadlock is gone; returning well inside the
    # grace period proves it hung up on the client rather than falling through
    # to the timeout backstop.
    assert elapsed < _STOP_GRACE_SECONDS, (
        f"stop() took {elapsed:.2f}s — it waited out the grace period instead of closing the attached client transport"
    )


def test_stop_disconnects_the_client(tmp_path: Path) -> None:
    """The client observes EOF, so the hang-up is real rather than abandoned."""

    async def scenario() -> bytes:
        server = await _started_server(tmp_path)
        reader, writer = await _connect(server)
        await asyncio.sleep(0.05)
        await asyncio.wait_for(server.stop(), timeout=_HANG_GUARD_SECONDS)
        try:
            # Server-side close -> EOF (or a reset, which is also a hang-up).
            return await asyncio.wait_for(reader.read(), timeout=5.0)
        except ConnectionError:
            return b""
        finally:
            await _aclose(writer)

    assert _run(scenario()) == b""


def test_stop_clears_client_registry(tmp_path: Path) -> None:
    """No transports are retained after stop, so a rebind starts clean."""

    async def scenario() -> set[asyncio.StreamWriter]:
        server = await _started_server(tmp_path)
        _, writer = await _connect(server)
        await asyncio.sleep(0.05)
        await asyncio.wait_for(server.stop(), timeout=_HANG_GUARD_SECONDS)
        await _aclose(writer)
        return server._clients

    assert _run(scenario()) == set()


def test_stop_without_clients_still_returns(tmp_path: Path) -> None:
    """The no-client path is unchanged, and stop stays idempotent."""

    async def scenario() -> None:
        server = await _started_server(tmp_path)
        await asyncio.wait_for(server.stop(), timeout=_HANG_GUARD_SECONDS)
        # Second stop is a no-op rather than an error.
        await asyncio.wait_for(server.stop(), timeout=_HANG_GUARD_SECONDS)

    _run(scenario())


def test_server_can_rebind_after_stopping_with_a_client_attached(tmp_path: Path) -> None:
    """The real flow: tear down project A's server, bind project B's.

    This is what ``ensure_project_mcp_server`` does on new/open project.
    """

    async def scenario() -> bool:
        project_a = tmp_path / "a"
        project_b = tmp_path / "b"
        server_a = await _started_server(project_a)
        _, writer = await _connect(server_a)
        await asyncio.sleep(0.05)
        await asyncio.wait_for(server_a.stop(), timeout=_HANG_GUARD_SECONDS)
        await _aclose(writer)

        server_b = MCPServer(socket_path=project_b / ".scistudio" / "mcp.sock", project_dir=project_b)
        await server_b.start()
        try:
            _, writer_b = await _connect(server_b)
            await _aclose(writer_b)
            return True
        finally:
            await asyncio.wait_for(server_b.stop(), timeout=_HANG_GUARD_SECONDS)

    assert _run(scenario()) is True
