"""ADR-034 Phase 1.2: tests for the system-prompt composer."""

from __future__ import annotations

from pathlib import Path

from scieasy.ai.agent.mcp._registry import TOOL_REGISTRY, all_names
from scieasy.ai.agent.system_prompt import compose_system_prompt


def test_compose_reads_skill_md(tmp_path: Path) -> None:
    """The returned prompt must contain a recognisable SKILL.md marker."""
    prompt = compose_system_prompt(tmp_path)
    # SKILL.md opens with a YAML frontmatter `name: scieasy` and the H1
    # `# SciEasy` heading — both are stable identity markers.
    assert "name: scieasy" in prompt
    assert "# SciEasy" in prompt


def test_compose_injects_full_tool_catalog(tmp_path: Path) -> None:
    """Every registered tool name must appear in the rendered prompt."""
    prompt = compose_system_prompt(tmp_path)
    for name in all_names():
        # Match the rendered ``- `name` [mode] — description`` shape so
        # we know the splice happened (not just an unrelated mention).
        assert f"`{name}`" in prompt, f"tool {name!r} missing from rendered prompt"
    assert len(TOOL_REGISTRY) == 25, "registry should expose 25 tools"


def test_compose_is_idempotent(tmp_path: Path) -> None:
    """Same input project_dir must yield byte-identical output."""
    a = compose_system_prompt(tmp_path)
    b = compose_system_prompt(tmp_path)
    assert a == b


def test_compose_uses_marker_block(tmp_path: Path) -> None:
    """The tool_catalog markers must wrap the rendered catalog."""
    prompt = compose_system_prompt(tmp_path)
    begin = prompt.find("<!-- tool_catalog:begin -->")
    end = prompt.find("<!-- tool_catalog:end -->")
    assert 0 <= begin < end, "marker block missing or inverted"
    between = prompt[begin:end]
    # Catalogue body should be ~25 bullet points; assert a representative
    # subset to avoid brittle length-based assertions.
    for name in ("list_blocks", "get_workflow", "search_docs", "get_project_info"):
        assert f"`{name}`" in between
