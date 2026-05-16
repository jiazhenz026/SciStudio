"""SciEasy MCP server (ADR-040 FastMCP migration).

This sub-package owns the Model Context Protocol (MCP) server that
SciEasy exposes to a locally installed Claude Code (or Codex) CLI. The
server is the *only* surface through which the embedded coding agent
reads workflow state, mutates configuration, or queries data — the
agent never imports SciEasy directly.

The 26 tools (25 baseline + ``finish_ai_block`` from ADR-035 §3.5) are
split across four modules by responsibility (ADR-040 §3.1):

* :mod:`scieasy.ai.agent.mcp.tools_workflow` — category (a):
  workflow inspection and execution (10 tools, includes
  ``finish_ai_block``).
* :mod:`scieasy.ai.agent.mcp.tools_authoring` — category (b):
  block authoring helpers (5 tools).
* :mod:`scieasy.ai.agent.mcp.tools_inspection` — category (c):
  run and data inspection (7 tools).
* :mod:`scieasy.ai.agent.mcp.tools_qa` — category (d): documentation
  and project Q&A (4 tools).

FastMCP discovers tools by ``@mcp.tool()`` decorator on the module-scope
:data:`scieasy.ai.agent.mcp.server.mcp` instance — there is no separate
``TOOL_REGISTRY`` tuple (the ``_registry.py`` module from the hand-rolled
JSON-RPC era is gone). Consumers that need the tool catalogue call
``mcp.list_tools()`` directly (see :mod:`scieasy.ai.agent.system_prompt`
for the rendering side).

See ``docs/adr/ADR-040.md`` §3.1-§3.3 for the full migration design.
"""

from __future__ import annotations

from scieasy.ai.agent.mcp.server import MCPServer

__all__ = ["MCPServer"]
