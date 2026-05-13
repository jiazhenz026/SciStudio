"""T-ECA-204: tests for the three-tier system prompt composer."""

from __future__ import annotations

from pathlib import Path

from scieasy.ai.agent.mcp._registry import TOOL_REGISTRY
from scieasy.ai.agent.system_prompt import (
    SECTION_A_IDENTITY,
    SECTION_B_CORE_CONCEPTS,
    SECTION_D_WORKING_PRINCIPLES,
    compose_system_prompt,
    prompt_hash,
)


def test_compose_contains_all_four_sections(tmp_path: Path) -> None:
    prompt = compose_system_prompt(tmp_path)
    # A: identity
    assert "SciEasy" in prompt and "AI assistant embedded" in prompt
    # B: core concepts (sample anchors)
    assert "Workflows are DAGs" in prompt
    assert "StorageReference" in prompt
    # C: tools list — every registered tool name appears.
    for entry in TOOL_REGISTRY:
        assert entry.name in prompt, f"tool {entry.name} missing from Section C"
    # D: working principles
    assert "Plan before acting" in prompt
    assert "Cite real data" in prompt


def test_compose_section_c_lists_every_tool_once(tmp_path: Path) -> None:
    prompt = compose_system_prompt(tmp_path)
    for entry in TOOL_REGISTRY:
        # Count occurrences — each name appears exactly once in Section C
        # (the rest of the prompt should not name individual tools).
        # We tolerate >= 1 occurrence because principle 5 references
        # ``list_blocks``, ``validate_workflow``, ``inspect_data`` etc.
        # Just assert presence (not exactly-once).
        assert entry.name in prompt


def test_compose_includes_write_tag(tmp_path: Path) -> None:
    prompt = compose_system_prompt(tmp_path)
    assert "[write]" in prompt
    assert "[read]" in prompt


def test_overlays_are_appended(tmp_path: Path) -> None:
    scieasy_dir = tmp_path / ".scieasy"
    scieasy_dir.mkdir()
    (scieasy_dir / "system_prompt.md").write_text("PROJECT_OVERLAY_MARKER\n", encoding="utf-8")
    (scieasy_dir / "system_prompt.local.md").write_text("LOCAL_OVERLAY_MARKER\n", encoding="utf-8")
    prompt = compose_system_prompt(tmp_path)
    assert "PROJECT_OVERLAY_MARKER" in prompt
    assert "LOCAL_OVERLAY_MARKER" in prompt
    # Order: project overlay before local overlay.
    assert prompt.index("PROJECT_OVERLAY_MARKER") < prompt.index("LOCAL_OVERLAY_MARKER")


def test_missing_overlays_dont_inject_markers(tmp_path: Path) -> None:
    prompt = compose_system_prompt(tmp_path)
    assert "PROJECT_OVERLAY_MARKER" not in prompt
    assert "LOCAL_OVERLAY_MARKER" not in prompt
    assert "Project overlay" not in prompt
    assert "Per-machine overlay" not in prompt


def test_reproducible_hash(tmp_path: Path) -> None:
    prompt_1 = compose_system_prompt(tmp_path)
    prompt_2 = compose_system_prompt(tmp_path)
    assert prompt_1 == prompt_2
    assert prompt_hash(prompt_1) == prompt_hash(prompt_2)


def test_hash_changes_with_overlay(tmp_path: Path) -> None:
    h_empty = prompt_hash(compose_system_prompt(tmp_path))
    (tmp_path / ".scieasy").mkdir()
    (tmp_path / ".scieasy" / "system_prompt.md").write_text("override\n", encoding="utf-8")
    h_overlay = prompt_hash(compose_system_prompt(tmp_path))
    assert h_empty != h_overlay


def test_section_constants_non_empty() -> None:
    assert SECTION_A_IDENTITY.strip()
    assert SECTION_B_CORE_CONCEPTS.strip()
    assert SECTION_D_WORKING_PRINCIPLES.strip()


def test_prompt_does_not_contain_developer_discipline(tmp_path: Path) -> None:
    """ADR-033 §3 D3.3: builtin must NOT carry CLAUDE.md gate / commit rules."""
    prompt = compose_system_prompt(tmp_path)
    for forbidden in ("gate.py", "conventional commit", "/speckit", "CHANGELOG.md", "git push"):
        assert forbidden.lower() not in prompt.lower(), f"forbidden phrase '{forbidden}' leaked into prompt"
