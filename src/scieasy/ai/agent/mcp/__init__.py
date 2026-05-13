"""SciEasy MCP server skeleton (ADR-033 §3 D2, Phase 2 scaffold).

This sub-package owns the Model Context Protocol (MCP) server that
SciEasy exposes to a locally installed Claude Code (or Codex) CLI. The
server is the *only* surface through which the embedded coding agent
reads workflow state, mutates configuration, or queries data — the
agent never imports SciEasy directly.

Phase 2 ships in two stages:

* **T-ECA-201 (this scaffold)** — class signatures, typed tool
  stubs, and a CLI entry-point stub. All bodies raise
  ``NotImplementedError``. No business logic.
* **T-ECA-202..205 (implementation)** — fills in the 25 tool
  functions, finalises the stdio transport over a Unix domain socket
  (POSIX) / named pipe (Windows) per ADR-033 OQ2, and wires the server
  into the FastAPI lifespan.

The 25 tools are split across four modules by responsibility:

* :mod:`scieasy.ai.agent.mcp.tools_workflow` — category (a):
  workflow inspection and execution (9 tools).
* :mod:`scieasy.ai.agent.mcp.tools_authoring` — category (b):
  block authoring helpers (5 tools).
* :mod:`scieasy.ai.agent.mcp.tools_inspection` — category (c):
  run and data inspection (7 tools).
* :mod:`scieasy.ai.agent.mcp.tools_qa` — category (d): documentation
  and project Q&A (4 tools).

See ``docs/specs/embedded-coding-agent-spec.md`` §6 T-ECA-201..205 for
the per-ticket contract.
"""

from __future__ import annotations

from scieasy.ai.agent.mcp.server import MCPServer

__all__ = ["MCPServer"]
