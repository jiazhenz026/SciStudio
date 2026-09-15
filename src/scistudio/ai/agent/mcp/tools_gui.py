"""Read-only images of the active project's SciStudio GUI over local MCP."""

from __future__ import annotations

import base64
import json
from typing import Annotated, Literal

from fastmcp.tools import ToolResult
from mcp.types import ImageContent, TextContent
from pydantic import Field

from scistudio.ai.agent.mcp._context import get_context, invoked_through_bridge
from scistudio.ai.agent.mcp.server import mcp
from scistudio.panels.gui_debug import GuiDebugError, decode_screenshot, get_gui_debug, resolve_gui_runtime


@mcp.tool(name="screenshot_gui", tags={"category:panels", "read"}, annotations={"readOnlyHint": True})
async def screenshot_gui(
    target: Literal["workspace", "miniapp"] = "miniapp",
    panel_id: Annotated[str | None, Field(description="MiniApp id; omitted selects the visible MiniApp.")] = None,
    context_id: Annotated[str | None, Field(description="Exact mounted MiniApp context, when known.")] = None,
    client_id: Annotated[
        str | None, Field(description="Workspace client id, required when multiple windows match.")
    ] = None,
    wait_ms: Annotated[
        int, Field(ge=0, le=5000, description="Wait for layout before capture; not proof of readiness.")
    ] = 500,
) -> ToolResult:
    """See the current project's rendered SciStudio desktop workspace or visible MiniApp.

    Returns target, dimensions and observed state plus a real PNG image content
    block that the model can inspect. Captures the app compositor, including
    iframe canvas and WebGL; never captures the desktop or another application.
    The tool is read-only: it does not open/focus tabs, click controls or start
    processes. Use open_miniapp first, then inspect this image and its state.
    A screenshot alone does not verify interactions or Python defaults.

    Requires a connected SciStudio desktop GUI on this project and local MCP
    (the installed Claude Code/Codex bridge). Ordinary web GUIs and the text-only
    external WebMCP host are explicitly unsupported. Hidden/unknown targets,
    ambiguous windows, project changes, and timeouts return actionable errors.
    """
    if invoked_through_bridge():
        raise GuiDebugError(
            "unsupported_transport", "This WebMCP host accepts text only. Use local MCP for screenshot images."
        )
    runtime = resolve_gui_runtime(get_context())
    project = runtime.project_dir
    project_instance = getattr(runtime, "active_project", None)
    if project is None:
        raise GuiDebugError("no_project", "Open the intended SciStudio project before taking a screenshot.")
    if target == "workspace" and (panel_id or context_id):
        raise ValueError("panel_id and context_id apply only to target='miniapp'")
    result = await get_gui_debug(runtime).request(
        project,
        {"action": "screenshot", "target": target, "panel_id": panel_id, "context_id": context_id, "wait_ms": wait_ms},
        client_id,
    )
    if runtime.project_dir != project or getattr(runtime, "active_project", None) is not project_instance:
        raise GuiDebugError(
            "project_changed", "The active project changed while capturing; retry in the intended project."
        )
    if result.get("target") != target or any(
        requested is not None and result.get(key) != requested
        for key, requested in (("panel_id", panel_id), ("context_id", context_id))
    ):
        raise GuiDebugError("target_changed", "GUI returned a different target; no image was forwarded.")
    raw, width, height = decode_screenshot(result)
    metadata = {key: value for key, value in result.items() if key not in {"png_base64", "type", "request_id"}}
    metadata.update(width=width, height=height, mime_type="image/png")
    return ToolResult(
        content=[
            TextContent(type="text", text=json.dumps(metadata)),
            ImageContent.model_validate(
                {"type": "image", "data": base64.b64encode(raw).decode("ascii"), "mimeType": "image/png"}
            ),
        ]
    )
