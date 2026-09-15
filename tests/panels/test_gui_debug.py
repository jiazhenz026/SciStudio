"""Project/socket isolation and bounded native image validation for GUI tools."""

from __future__ import annotations

import asyncio
import base64
import struct
import zlib
from pathlib import Path

import pytest

from scistudio.panels.gui_debug import GuiDebugBroker, GuiDebugError, decode_screenshot


def png_payload() -> dict:
    def chunk(name: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))

    raw = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    raw += chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00\xff")) + chunk(b"IEND", b"")
    return {"png_base64": base64.b64encode(raw).decode(), "width": 1, "height": 1}


def test_png_is_validated_instead_of_forwarding_arbitrary_base64() -> None:
    payload = png_payload()
    assert decode_screenshot(payload)[1:] == (1, 1)
    for bad in [
        dict(payload, width=2),
        dict(payload, png_base64="invalid!"),
        dict(payload, png_base64=base64.b64encode(b"not a png").decode()),
        dict(payload, png_base64=payload["png_base64"][:-4]),
    ]:
        with pytest.raises(GuiDebugError):
            decode_screenshot(bad)


async def _test_broker_requires_current_project_and_exact_socket(tmp_path: Path) -> None:
    broker = GuiDebugBroker()
    messages = []
    a = broker.connect("window-a", messages.append)
    b = broker.connect("window-b", messages.append)
    broker.advertise(a, str(tmp_path / "a"), True)
    broker.advertise(b, str(tmp_path / "b"), True)
    with pytest.raises(GuiDebugError, match="No connected"):
        await broker.request(tmp_path / "empty", {}, None)
    task = asyncio.create_task(broker.request(tmp_path / "a", {"target": "workspace"}, None))
    await asyncio.sleep(0)
    reply = {**messages[-1], **png_payload()}
    broker.reply(b, reply)
    assert not task.done()
    broker.reply(a, reply)
    assert (await task)["client_id"] == "window-a"
    assert not broker.pending


async def _test_project_switch_disconnect_and_ambiguity_invalidate(tmp_path: Path) -> None:
    broker = GuiDebugBroker()
    messages = []
    key = broker.connect("one", messages.append)
    broker.advertise(key, str(tmp_path), True)
    task = asyncio.create_task(broker.request(tmp_path, {}, None))
    await asyncio.sleep(0)
    broker.advertise(key, str(tmp_path / "new"), True)
    with pytest.raises(GuiDebugError, match="project changed"):
        await task
    broker.advertise(key, str(tmp_path), True)
    other = broker.connect("two", messages.append)
    broker.advertise(other, str(tmp_path), True)
    with pytest.raises(GuiDebugError, match="Several GUI"):
        await broker.request(tmp_path, {}, None)
    task = asyncio.create_task(broker.request(tmp_path, {}, "one"))
    await asyncio.sleep(0)
    broker.disconnect(key)
    with pytest.raises(GuiDebugError, match="disconnected"):
        await task


async def _test_browser_gui_is_actionably_unsupported(tmp_path: Path) -> None:
    broker = GuiDebugBroker()
    key = broker.connect("browser", lambda _: None)
    broker.advertise(key, str(tmp_path), False)
    with pytest.raises(GuiDebugError, match="desktop app"):
        await broker.request(tmp_path, {}, None)


def test_browser_gui_is_actionably_unsupported(tmp_path: Path) -> None:
    asyncio.run(_test_browser_gui_is_actionably_unsupported(tmp_path))


def test_project_switch_disconnect_and_ambiguity_invalidate(tmp_path: Path) -> None:
    asyncio.run(_test_project_switch_disconnect_and_ambiguity_invalidate(tmp_path))


def test_broker_requires_current_project_and_exact_socket(tmp_path: Path) -> None:
    asyncio.run(_test_broker_requires_current_project_and_exact_socket(tmp_path))
