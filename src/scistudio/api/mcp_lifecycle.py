"""MCP server lifecycle helpers for the FastAPI app."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from scistudio.api.runtime import ApiRuntime

logger = logging.getLogger(__name__)


def _server_requested_socket(server: object) -> Path | None:
    raw = getattr(server, "_requested_socket_path", None)
    return raw if isinstance(raw, Path) else None


def _server_bound_socket(server: object) -> Path | None:
    raw = getattr(server, "socket_path", None)
    return raw if isinstance(raw, Path) else None


async def ensure_project_mcp_server(app: Any, runtime: ApiRuntime, project_dir: Path) -> None:
    """Ensure the live MCP server is reachable through the active project."""
    target_socket = project_dir / ".scistudio" / "mcp.sock"
    current = getattr(app.state, "mcp_server", None)

    bound_socket = _server_bound_socket(current) if current is not None else None
    if current is not None and _server_requested_socket(current) == target_socket and bound_socket is not None:
        if bound_socket.exists():
            runtime.set_mcp_port(getattr(current, "port", None), socket_path=bound_socket)
            return
        logger.warning("MCP server socket path disappeared; rebinding %s", target_socket)

    if (
        current is not None
        and _server_requested_socket(current) == target_socket
        and getattr(current, "port", None) is not None
    ):
        runtime.set_mcp_port(getattr(current, "port", None), socket_path=target_socket)
        return

    if current is not None:
        try:
            await current.stop()
        except Exception:
            logger.warning("MCP server stop before project rebind raised", exc_info=True)
        finally:
            app.state.mcp_server = None

    try:
        from scistudio.ai.agent.mcp.server import MCPServer

        server = MCPServer(socket_path=target_socket, project_dir=project_dir)
        await server.start()
        app.state.mcp_server = server
        runtime.set_mcp_port(server.port, socket_path=server.socket_path)
    except Exception:
        logger.error("MCP server failed to start for project %s", project_dir, exc_info=True)
        app.state.mcp_server = None
        runtime.set_mcp_port(None)


async def stop_project_mcp_server(app: Any, runtime: ApiRuntime) -> None:
    """Stop the app-owned MCP server and clear project transport files."""
    current = getattr(app.state, "mcp_server", None)
    if current is None:
        runtime.set_mcp_port(None)
        return
    try:
        await current.stop()
    except Exception:
        logger.warning("MCP server stop raised", exc_info=True)
    finally:
        app.state.mcp_server = None
        runtime.set_mcp_port(None)
