"""Tests for the SKILL.md-based system prompt body (#787).

Verifies:

* ``compose_system_prompt`` reads ``skills/scieasy/SKILL.md`` when
  available and includes its content.
* Tool catalog is re-synthesised from the live registry (not the
  static text inside SKILL.md) so prompt and dispatcher cannot drift.
* When the skill file is missing, the legacy inline body is used and
  a warning is logged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from scieasy.ai.agent import system_prompt
from scieasy.ai.agent.mcp._registry import TOOL_REGISTRY
from scieasy.ai.agent.system_prompt import (
    _find_skill_file,
    _splice_live_tool_catalog,
    compose_system_prompt,
)


def test_skill_file_is_locatable() -> None:
    """Editable install path: SKILL.md is reachable from this module."""
    skill = _find_skill_file()
    assert skill is not None, "skills/scieasy/SKILL.md should be present in the source tree"
    assert skill.is_file()


def test_prompt_includes_content_from_skill_file(tmp_path: Path) -> None:
    """A unique marker string in SKILL.md must show up in the composed prompt."""
    skill = _find_skill_file()
    assert skill is not None
    body = skill.read_text(encoding="utf-8")
    # Pick a distinctive phrase from the skill body that doesn't appear
    # in the fallback constants.
    marker = "## Project layout"
    assert marker in body, "test invariant: SKILL.md should contain '## Project layout'"

    prompt = compose_system_prompt(tmp_path)
    assert marker in prompt


def test_prompt_section_c_uses_live_registry(tmp_path: Path) -> None:
    """The live tool catalog must contain every TOOL_REGISTRY entry."""
    prompt = compose_system_prompt(tmp_path)
    for entry in TOOL_REGISTRY:
        assert entry.name in prompt, f"tool {entry.name} missing from composed prompt"


def test_splice_live_tool_catalog_replaces_static_section() -> None:
    """When markers are present, splice should replace inner text."""
    body = (
        "# Title\n\nintro\n\n<!-- tool_catalog:begin -->\nOLD STATIC CONTENT\n<!-- tool_catalog:end -->\n\ntrailing\n"
    )
    out = _splice_live_tool_catalog(body)
    assert "OLD STATIC CONTENT" not in out
    assert "Available tools:" in out
    assert "<!-- tool_catalog:begin -->" in out
    assert "<!-- tool_catalog:end -->" in out
    assert "trailing" in out


def test_splice_live_tool_catalog_no_markers_appends() -> None:
    """When markers are absent the live catalog is appended at the end."""
    body = "# Title\n\nNo markers here.\n"
    out = _splice_live_tool_catalog(body)
    assert "Available tools:" in out
    # Original content preserved verbatim before the appended catalog.
    assert out.index("No markers here.") < out.index("Available tools:")


def test_fallback_when_skill_file_missing(tmp_path: Path, caplog: object) -> None:
    """When SKILL.md cannot be located, compose_system_prompt logs and falls back."""
    # Patch the locator so it pretends the file is gone.
    with (
        patch.object(system_prompt, "_find_skill_file", return_value=None),
        caplog.at_level(logging.WARNING, logger=system_prompt.__name__),  # type: ignore[attr-defined]
    ):
        prompt = compose_system_prompt(tmp_path)
    # Fallback body still contains the canonical anchors.
    assert "AI assistant embedded" in prompt
    assert "Workflows are DAGs" in prompt
    assert "Plan before acting" in prompt
    # Warning emitted.
    messages = [rec.getMessage() for rec in caplog.records]  # type: ignore[attr-defined]
    assert any("SKILL.md not found" in m for m in messages)


def test_fallback_when_skill_file_unreadable(tmp_path: Path) -> None:
    """A read error on SKILL.md should drop back to the inline body."""
    fake_path = tmp_path / "nonexistent" / "SKILL.md"
    with patch.object(system_prompt, "_find_skill_file", return_value=fake_path):
        prompt = compose_system_prompt(tmp_path)
    # We don't fail loudly — the legacy body is good enough.
    assert "Plan before acting" in prompt
    for entry in TOOL_REGISTRY:
        assert entry.name in prompt
