"""MCP tool registry — single source of truth for the 25 tools.

T-ECA-202..205. Drives three things:

1. :class:`MCPServer.dispatch` resolves a ``tools/call`` request by
   looking up the tool name here and invoking the bound function.
2. :class:`MCPServer.dispatch` answers ``tools/list`` from the entries
   declared here (name, description, mutation flag).
3. :func:`scieasy.ai.agent.system_prompt.compose_system_prompt` reads
   the same entries to generate the builtin prompt's Section C tool
   enumeration. Adding or removing a tool here therefore auto-updates
   both the dispatcher and the system prompt — they cannot drift.

The mutation flag (``"read"`` vs ``"write"``) mirrors ADR-033 §3 D2.2
and feeds the permission policy: write-class tools route through the
``PreToolUse`` hook in STRICT mode; read-class tools auto-approve.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from scieasy.ai.agent.mcp import (
    tools_authoring,
    tools_inspection,
    tools_qa,
    tools_workflow,
)


@dataclass(frozen=True)
class ToolEntry:
    """One registered MCP tool.

    Attributes
    ----------
    name
        The MCP method name (matches the tool function name).
    category
        ADR-033 §3 D2.2 category — ``"workflow"``, ``"authoring"``,
        ``"inspection"``, or ``"qa"``.
    mutation
        ``"read"`` or ``"write"``. Write tools route through the
        permission policy.
    description
        One-sentence description for the ``tools/list`` response and the
        system prompt's Section C enumeration.
    handler
        The bound Python callable that implements the tool.
    """

    name: str
    category: str
    mutation: str
    description: str
    handler: Callable[..., Any]


# Order matters for the system prompt enumeration but not for dispatch.
# Keep grouped by category to keep the prompt readable.
TOOL_REGISTRY: tuple[ToolEntry, ...] = (
    # (a) workflow
    ToolEntry(
        "list_blocks",
        "workflow",
        "read",
        "List every block type registered in the active block registry.",
        tools_workflow.list_blocks,
    ),
    ToolEntry(
        "get_block_schema",
        "workflow",
        "read",
        "Return ports and config_schema for one block type.",
        tools_workflow.get_block_schema,
    ),
    ToolEntry(
        "list_types",
        "workflow",
        "read",
        "Return the data-type registry hierarchy.",
        tools_workflow.list_types,
    ),
    ToolEntry(
        "get_workflow",
        "workflow",
        "read",
        "Load a workflow YAML and return its decoded representation.",
        tools_workflow.get_workflow,
    ),
    ToolEntry(
        "validate_workflow",
        "workflow",
        "read",
        "Validate a workflow (inline YAML or path) against runtime rules.",
        tools_workflow.validate_workflow,
    ),
    ToolEntry(
        "write_workflow",
        "workflow",
        "write",
        "Persist a workflow YAML to disk with a file lock.",
        tools_workflow.write_workflow,
    ),
    ToolEntry(
        "run_workflow",
        "workflow",
        "write",
        "Submit a workflow for execution and return its run_id.",
        tools_workflow.run_workflow,
    ),
    ToolEntry(
        "cancel_run",
        "workflow",
        "write",
        "Request cancellation of an in-flight workflow run.",
        tools_workflow.cancel_run,
    ),
    ToolEntry(
        "get_run_status",
        "workflow",
        "read",
        "Return current status of a workflow run.",
        tools_workflow.get_run_status,
    ),
    # (b) authoring
    ToolEntry(
        "read_block_source",
        "authoring",
        "read",
        "Return the Python source file backing a block type.",
        tools_authoring.read_block_source,
    ),
    ToolEntry(
        "list_block_examples",
        "authoring",
        "read",
        "List curated example blocks for a category.",
        tools_authoring.list_block_examples,
    ),
    ToolEntry(
        "scaffold_block",
        "authoring",
        "write",
        "Render a new block module from project templates.",
        tools_authoring.scaffold_block,
    ),
    ToolEntry(
        "reload_blocks",
        "authoring",
        "write",
        "Hot-reload the block registry.",
        tools_authoring.reload_blocks,
    ),
    ToolEntry(
        "run_block_tests",
        "authoring",
        "write",
        "Run pytest against the test module for a block.",
        tools_authoring.run_block_tests,
    ),
    # (c) inspection
    ToolEntry(
        "get_block_output",
        "inspection",
        "read",
        "Resolve recorded output of one block port from a run.",
        tools_inspection.get_block_output,
    ),
    ToolEntry(
        "inspect_data",
        "inspection",
        "read",
        "Return metadata about a stored data reference.",
        tools_inspection.inspect_data,
    ),
    ToolEntry(
        "preview_data",
        "inspection",
        "read",
        "Compute a bounded preview (thumbnail / first-N rows / first chars).",
        tools_inspection.preview_data,
    ),
    ToolEntry(
        "get_lineage",
        "inspection",
        "read",
        "Return transitive lineage ancestors of a data reference.",
        tools_inspection.get_lineage,
    ),
    ToolEntry(
        "get_block_config",
        "inspection",
        "read",
        "Return the static configuration of one block in a workflow file.",
        tools_inspection.get_block_config,
    ),
    ToolEntry(
        "update_block_config",
        "inspection",
        "write",
        "Patch one block's configuration in a workflow YAML (preserves comments).",
        tools_inspection.update_block_config,
    ),
    ToolEntry(
        "get_block_logs",
        "inspection",
        "read",
        "Return captured stdout/stderr from a block's execution.",
        tools_inspection.get_block_logs,
    ),
    # (d) Q&A
    ToolEntry(
        "search_docs",
        "qa",
        "read",
        "Search the on-disk docs/ tree for a free-text query.",
        tools_qa.search_docs,
    ),
    ToolEntry(
        "get_doc",
        "qa",
        "read",
        "Return the full text of one documentation file.",
        tools_qa.get_doc,
    ),
    ToolEntry(
        "list_data",
        "qa",
        "read",
        "Enumerate data assets in the project workspace.",
        tools_qa.list_data,
    ),
    ToolEntry(
        "get_project_info",
        "qa",
        "read",
        "Return high-level information about the active project.",
        tools_qa.get_project_info,
    ),
)


def lookup(name: str) -> ToolEntry | None:
    """Return the :class:`ToolEntry` with the given name, or ``None``."""
    for entry in TOOL_REGISTRY:
        if entry.name == name:
            return entry
    return None


def all_names() -> list[str]:
    """Return the list of all 25 registered tool names in declaration order."""
    return [entry.name for entry in TOOL_REGISTRY]


def by_category() -> dict[str, list[ToolEntry]]:
    """Return tools grouped by category, in declaration order."""
    grouped: dict[str, list[ToolEntry]] = {}
    for entry in TOOL_REGISTRY:
        grouped.setdefault(entry.category, []).append(entry)
    return grouped
