"""Project-bound request/reply channel to a connected SciStudio workspace.

The GUI supplies compositor screenshots; this broker never captures the desktop.
Connections and replies are bound to the socket instance, not a reusable client
id. Project switches and disconnects invalidate outstanding requests.
"""

from __future__ import annotations

import asyncio
import base64
import secrets
import struct
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_PNG_BYTES = 4 * 1024 * 1024


class GuiDebugError(RuntimeError):
    """An actionable GUI capability or target failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class GuiConnection:
    client_id: str
    send: Callable[[dict[str, Any]], None]
    project: str | None = None
    screenshot: bool = False


class GuiDebugBroker:
    """Bounded in-process broker shared by the API socket and MCP tools."""

    def __init__(self) -> None:
        self.connections: dict[str, GuiConnection] = {}
        self.pending: dict[str, tuple[str, str, asyncio.Future[dict[str, Any]]]] = {}

    def connect(self, client_id: str, send: Callable[[dict[str, Any]], None]) -> str:
        key = secrets.token_urlsafe(24)
        self.connections[key] = GuiConnection(client_id, send)
        return key

    def disconnect(self, key: str) -> None:
        self.connections.pop(key, None)
        self._invalidate(key, "GUI disconnected; reconnect the SciStudio workspace and retry.")

    def _invalidate(self, key: str, message: str) -> None:
        for connection, _, future in list(self.pending.values()):
            if connection == key and not future.done():
                future.set_exception(GuiDebugError("gui_changed", message))

    def advertise(self, key: str, project: Any, screenshot: Any) -> None:
        connection = self.connections.get(key)
        if connection is None:
            return
        path = str(Path(project).resolve()) if isinstance(project, str) and project else None
        if connection.project != path:
            self._invalidate(key, "GUI project changed during the request; retry in the intended project.")
        connection.project = path
        connection.screenshot = screenshot is True

    def reply(self, key: str, payload: dict[str, Any]) -> None:
        request_id = payload.get("request_id")
        if not isinstance(request_id, str):
            return
        item = self.pending.get(request_id)
        if item is None or item[0] != key or item[2].done():
            return
        if payload.get("project") != item[1]:
            item[2].set_exception(GuiDebugError("project_changed", "GUI replied from a different project."))
            return
        item[2].set_result(payload)

    def receive(self, key: str, payload: dict[str, Any], project: Path | None) -> bool:
        """Consume only GUI debug frames, with current runtime project matching."""
        if payload.get("type") == "gui.debug.hello":
            requested = payload.get("project")
            self.advertise(
                key, requested if project is not None and str(project) == requested else None, payload.get("screenshot")
            )
            return True
        if payload.get("type") == "gui.debug.response":
            self.reply(key, payload)
            return True
        return False

    async def request(self, project: Path, payload: dict[str, Any], client_id: str | None) -> dict[str, Any]:
        project_path = str(project.resolve())
        candidates = [
            (key, connection)
            for key, connection in self.connections.items()
            if connection.project == project_path and (client_id is None or connection.client_id == client_id)
        ]
        if not candidates:
            raise GuiDebugError("no_gui", "No connected SciStudio GUI is showing this project. Open it and retry.")
        capable = [(key, connection) for key, connection in candidates if connection.screenshot]
        if not capable:
            raise GuiDebugError(
                "unsupported_gui", "This GUI cannot capture screenshots. Use the SciStudio desktop app."
            )
        if len(capable) != 1:
            ids = ", ".join(connection.client_id for _, connection in capable)
            raise GuiDebugError("ambiguous_gui", f"Several GUI windows show this project; pass client_id: {ids}")
        if len(self.pending) >= 8:
            raise GuiDebugError("busy", "Too many GUI requests are pending; wait for the current request to finish.")
        key, connection = capable[0]
        request_id = secrets.token_urlsafe(24)
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self.pending[request_id] = (key, project_path, future)
        try:
            connection.send({"type": "gui.debug.request", **payload, "request_id": request_id, "project": project_path})
            try:
                result = await asyncio.wait_for(future, timeout=10)
            except TimeoutError as exc:
                raise GuiDebugError(
                    "gui_timeout", "The GUI did not answer within 10 seconds. Check it is responsive."
                ) from exc
            if error := result.get("error"):
                raise GuiDebugError(
                    str(error.get("code", "capture_failed")), str(error.get("message", "GUI capture failed"))
                )
            return {**result, "client_id": connection.client_id}
        finally:
            self.pending.pop(request_id, None)


def decode_screenshot(payload: dict[str, Any]) -> tuple[bytes, int, int]:
    """Validate the bounded PNG and its dimensions before forwarding an image."""
    encoded = payload.get("png_base64")
    if not isinstance(encoded, str) or len(encoded) > (MAX_PNG_BYTES + 2) // 3 * 4:
        raise GuiDebugError("invalid_image", "GUI returned an absent or oversized PNG.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise GuiDebugError("invalid_image", "GUI returned invalid PNG encoding.") from exc
    if len(raw) < 33 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise GuiDebugError("invalid_image", "GUI did not return a PNG image.")
    width, height = struct.unpack(">II", raw[16:24])
    if not (0 < width <= 2560 and 0 < height <= 2560) or width * height > 4_000_000:
        raise GuiDebugError("invalid_image", "GUI image dimensions exceed the capture bounds.")
    if payload.get("width") != width or payload.get("height") != height:
        raise GuiDebugError("invalid_image", "GUI image dimensions do not match its metadata.")
    offset = 8
    has_data = False
    while offset + 12 <= len(raw):
        length = struct.unpack(">I", raw[offset : offset + 4])[0]
        end = offset + 12 + length
        if end > len(raw):
            break
        chunk = raw[offset + 4 : end - 4]
        if zlib.crc32(chunk) != struct.unpack(">I", raw[end - 4 : end])[0]:
            break
        has_data = has_data or chunk[:4] == b"IDAT"
        if chunk[:4] == b"IEND" and length == 0 and end == len(raw) and has_data:
            return raw, width, height
        offset = end
    raise GuiDebugError("invalid_image", "GUI returned an incomplete or corrupt PNG.")


def resolve_gui_runtime(context: Any) -> Any:
    """Resolve the API's MCP adapter through its existing event-bus capability."""
    runtime = getattr(getattr(context, "event_bus", None), "runtime", None)
    return context if runtime is None else runtime


def get_gui_debug(runtime: Any) -> GuiDebugBroker:
    """Return this runtime's broker without importing the API layer."""
    runtime = resolve_gui_runtime(runtime)
    broker = getattr(runtime, "_gui_debug_broker", None)
    if broker is None:
        broker = GuiDebugBroker()
        runtime._gui_debug_broker = broker
    return broker
