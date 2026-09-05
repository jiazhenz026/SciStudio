"""The one declaration of what the MCP tool registry is expected to hold.

ADR-054 §8.4 names the cost this module removes: "every change to the agent's
MCP tool set moves a set of count assertions in the test suite and a set of live
catalog documents; a tool added without updating them fails the suite in places
that do not mention the tool." Five test files across four suites asserted the
tool total, and two of them carried their own full copy of the expected names.
Adding a group meant finding all five, and the spec's own affected-files table
listed three of them.

So the expectation lives here once and the five sites import it. The name set is
the assertion with teeth — it says *which* tools, and a rename fails it as
loudly as a removal. :data:`EXPECTED_TOOL_COUNT` is derived from that set rather
than written down beside it, so the two can never disagree.

:data:`EXPECTED_TOOL_GROUPS` is the same statement per ``category:`` tag, which
is the grouping the server reports on ``tools/list`` and the one the catalog
documents are organised by. A module-level assertion below checks that its
counts sum to :data:`EXPECTED_TOOL_COUNT`, which catches the one way these
three can drift apart: a name claimed by two groups.
``tests/ai/test_tool_catalogs.py`` checks the declaration against the live
registry, both counts and membership.

**Adding a tool group**: add its names below, add its row to
``EXPECTED_TOOL_GROUPS``, and add it to the catalogs
(``src/scistudio/_skills/scistudio/SKILL.md`` and
``docs/specs/embedded-coding-agent-spec.md``). Nothing else moves.

Both tool groups ADR-054 spec 5 adds are here: the panel group (S5-B2) and the
Explore session group (S5-B3). The registry holds 47 tools in eight groups.
"""

from __future__ import annotations

#: Workflow inspection and execution (ADR-040 §3.1; ``edit_workflow`` #1912;
#: ``finish_ai_block`` ADR-035 §3.5; ``get_active_workflow_context`` ADR-040
#: Addendum 5, widened into the workspace focus by ADR-054 spec 5 FR-003).
WORKFLOW_TOOLS: frozenset[str] = frozenset(
    {
        "list_blocks",
        "get_block_schema",
        "list_types",
        "get_workflow",
        "validate_workflow",
        "write_workflow",
        "edit_workflow",
        "run_workflow",
        "cancel_run",
        "get_run_status",
        "finish_ai_block",
        "get_active_workflow_context",
    }
)

#: Block authoring helpers (ADR-040 §3.1).
AUTHORING_TOOLS: frozenset[str] = frozenset(
    {
        "read_block_source",
        "list_block_examples",
        "scaffold_block",
        "reload_blocks",
        "run_block_tests",
    }
)

#: Run and data inspection (ADR-040 §3.1).
INSPECTION_TOOLS: frozenset[str] = frozenset(
    {
        "get_block_output",
        "inspect_data",
        "preview_data",
        "get_lineage",
        "get_block_config",
        "update_block_config",
        "get_block_logs",
    }
)

#: Documentation and project Q&A (ADR-040 §3.1; ``open_gui`` #1947).
QA_TOOLS: frozenset[str] = frozenset(
    {
        "search_docs",
        "get_doc",
        "list_data",
        "get_project_info",
        "open_gui",
    }
)

#: Preview-only plot authoring (ADR-048 SPEC 2).
PLOT_TOOLS: frozenset[str] = frozenset(
    {
        "list_plot_targets",
        "scaffold_plot",
        "list_plot_examples",
        "read_plot_source",
        "validate_plot",
        "run_plot_job",
    }
)

#: Promotion into the personal tool library (ADR-053 FR-011).
LIBRARY_TOOLS: frozenset[str] = frozenset({"promote_to_user_library"})

#: Panel authoring (ADR-054 spec 5 FR-014 to FR-018).
PANEL_TOOLS: frozenset[str] = frozenset(
    {
        "scaffold_panel",
        "read_panel_source",
        "list_panel_examples",
        "reload_panels",
    }
)

#: The Explore session tools (ADR-054 spec 5 FR-019 to FR-024). Note the tag is
#: ``category:session`` while the module is ``tools_explore`` -- the group is
#: named for what the agent acts on, the module for the subsystem it calls.
SESSION_TOOLS: frozenset[str] = frozenset(
    {
        "open_explore_session",
        "read_notebook",
        "append_cell",
        "run_cell",
        "get_bindings",
        "check_packaging",
        "package_notebook",
    }
)

#: Expected registry contents per ``category:`` tag.
EXPECTED_TOOL_GROUPS: dict[str, frozenset[str]] = {
    "workflow": WORKFLOW_TOOLS,
    "authoring": AUTHORING_TOOLS,
    "inspection": INSPECTION_TOOLS,
    "qa": QA_TOOLS,
    "plot": PLOT_TOOLS,
    "library": LIBRARY_TOOLS,
    "panel": PANEL_TOOLS,
    "session": SESSION_TOOLS,
}

#: Every tool the MCP server is expected to register.
EXPECTED_TOOL_NAMES: frozenset[str] = frozenset().union(*EXPECTED_TOOL_GROUPS.values())

#: How many. Derived, never written down: a total that can disagree with the
#: names it counts is the defect this module exists to remove.
EXPECTED_TOOL_COUNT: int = len(EXPECTED_TOOL_NAMES)

#: Expected count per group, for the per-group assertions (ADR-054 spec 5 FR-025).
EXPECTED_GROUP_COUNTS: dict[str, int] = {group: len(names) for group, names in EXPECTED_TOOL_GROUPS.items()}

# A name in two groups would make the group counts sum past the total while the
# name set stayed right, which is the one way these three can drift apart.
assert sum(EXPECTED_GROUP_COUNTS.values()) == EXPECTED_TOOL_COUNT, (
    "a tool name appears in more than one group in EXPECTED_TOOL_GROUPS"
)

__all__ = [
    "AUTHORING_TOOLS",
    "EXPECTED_GROUP_COUNTS",
    "EXPECTED_TOOL_COUNT",
    "EXPECTED_TOOL_GROUPS",
    "EXPECTED_TOOL_NAMES",
    "INSPECTION_TOOLS",
    "LIBRARY_TOOLS",
    "PANEL_TOOLS",
    "PLOT_TOOLS",
    "QA_TOOLS",
    "SESSION_TOOLS",
    "WORKFLOW_TOOLS",
]
