"""Vision-capable MCP results must survive the installed local transport."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from scistudio.ai.agent.mcp import _context
from scistudio.ai.agent.mcp.server import MCPServer, mcp
from scistudio.ai.agent.mcp.tools_gui import screenshot_gui
from scistudio.panels.gui_debug import GuiDebugError, get_gui_debug
from tests.panels.test_gui_debug import png_payload


async def _test_screenshot_is_native_image_on_real_mcp_dispatch(tmp_path: Path) -> None:
    runtime = SimpleNamespace(project_dir=tmp_path)
    previous = _context._current_context
    adapter = SimpleNamespace(project_dir=tmp_path, event_bus=SimpleNamespace(runtime=runtime))
    _context.set_context(adapter)
    try:
        broker = get_gui_debug(runtime)
        assert get_gui_debug(adapter) is broker
        messages = []
        key = broker.connect("desktop", messages.append)
        broker.advertise(key, str(tmp_path), True)
        server = MCPServer(tmp_path / "mcp.sock", tmp_path)
        task = asyncio.create_task(
            server.dispatch(
                {
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "screenshot_gui",
                        "arguments": {"target": "workspace", "wait_ms": 0},
                    },
                }
            )
        )
        for _ in range(100):
            if messages:
                break
            await asyncio.sleep(0.01)
        broker.reply(key, {**messages[0], **png_payload(), "state": "visible"})
        response = await task
        blocks = response["result"]["content"]
        assert [block["type"] for block in blocks] == ["text", "image"]
        assert blocks[1]["mimeType"] == "image/png"
        assert base64.b64decode(blocks[1]["data"]).startswith(b"\x89PNG")
        assert "desktop" in blocks[0]["text"]
        stale = MCPServer(tmp_path / "old.sock", tmp_path / "old")
        denied = await stale.dispatch({"id": 2, "method": "tools/call", "params": {"name": "screenshot_gui"}})
        assert "another project" in denied["error"]["message"]
    finally:
        _context.set_context(previous)


async def _test_schema_and_text_only_host_refusal() -> None:
    tool = next(tool for tool in await mcp.list_tools() if tool.name == "screenshot_gui")
    assert "read" in tool.tags
    assert tool.parameters["properties"]["wait_ms"]["maximum"] == 5000
    with _context.bridge_call_scope(), pytest.raises(GuiDebugError, match="text only"):
        await screenshot_gui()


def test_schema_and_text_only_host_refusal() -> None:
    asyncio.run(_test_schema_and_text_only_host_refusal())


def test_screenshot_is_native_image_on_real_mcp_dispatch(tmp_path: Path) -> None:
    asyncio.run(_test_screenshot_is_native_image_on_real_mcp_dispatch(tmp_path))
