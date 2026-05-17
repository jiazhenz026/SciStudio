"""Regression tests for #1063 — scaffold template port-spec API drift.

`tools_authoring._render_port_block` was emitting `type=DataObject` /
`type=<T>` for `InputPort` / `OutputPort` constructor calls, but the
live `Port` dataclass (`src/scieasy/blocks/base/ports.py:17`) takes
`accepted_types: list[type]`. Blocks scaffolded via the broken template
would raise `TypeError` at registry-load time.

These tests exercise the private helper directly to bypass the
FastMCP-decorated public tool surface (which has a different call
shape and is covered by a separate skip in `test_mcp_tools_authoring.py`).
"""

from __future__ import annotations

from scieasy.ai.agent.mcp import tools_authoring


def test_render_port_block_non_empty_uses_accepted_types() -> None:
    """Non-empty spec_map → accepted_types=[T] (not type=T)."""
    rendered = tools_authoring._render_port_block(
        {"in1": {"type": "DataObject"}, "in2": {"type": "Image"}},
        "InputPort",
    )
    assert "accepted_types=[DataObject]" in rendered, (
        f"Expected accepted_types=[DataObject] in scaffold output, got:\n{rendered}"
    )
    assert "accepted_types=[Image]" in rendered
    # Old shape MUST be gone — this is the bug #1063 fixes
    assert "type=DataObject" not in rendered, f"Stale type=DataObject kwarg still in template:\n{rendered}"
    assert "type=Image" not in rendered


def test_render_port_block_empty_placeholder_uses_accepted_types() -> None:
    """Empty spec_map → placeholder comment also uses accepted_types=[DataObject]."""
    rendered = tools_authoring._render_port_block(None, "OutputPort")
    assert "accepted_types=[DataObject]" in rendered
    assert "type=DataObject" not in rendered


def test_render_port_block_preserves_description_comment() -> None:
    """Description-bearing specs still emit the trailing `# <desc>` comment."""
    rendered = tools_authoring._render_port_block(
        {"in1": {"type": "DataObject", "description": "primary input"}},
        "InputPort",
    )
    assert "accepted_types=[DataObject]" in rendered
    assert "# primary input" in rendered
