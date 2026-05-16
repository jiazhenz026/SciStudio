"""Tests for the system-prompt composer.

ADR-040 §3.3 / §3.4 — I40a Phase 2a:

* Wheel-layout regression: ``_load_skill_md`` uses ``importlib.resources``
  (closes #824). Falls back to legacy walk-up while the Skills track
  ships the relocated SKILL.md.
* Project context splice: ``compose_system_prompt(project_dir)`` renders
  a project-specific block between ``<!-- project_context:begin/end -->``
  markers (closes #825).
"""

from __future__ import annotations

import time
from pathlib import Path


def test_compose_reads_skill_md(tmp_path: Path) -> None:
    """The returned prompt must contain a recognisable SKILL.md marker."""
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(tmp_path)
    # SKILL.md opens with YAML frontmatter `name: scieasy` and an H1
    # ``# SciEasy`` heading — both are stable identity markers; at least
    # one should be present.
    assert "name: scieasy" in prompt or "# SciEasy" in prompt


def test_compose_injects_full_tool_catalog(tmp_path: Path) -> None:
    """Every registered tool name must appear in the rendered prompt."""
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(tmp_path)
    # Spot-check tools across all four categories.
    for name in (
        "list_blocks",
        "get_block_schema",
        "validate_workflow",
        "write_workflow",
        "run_workflow",
        "finish_ai_block",
        "scaffold_block",
        "inspect_data",
        "preview_data",
        "search_docs",
        "get_project_info",
    ):
        assert f"`{name}`" in prompt, f"tool {name!r} missing from rendered prompt"


def test_compose_is_idempotent(tmp_path: Path) -> None:
    """Same input project_dir must yield byte-identical output."""
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    a = compose_system_prompt(tmp_path)
    b = compose_system_prompt(tmp_path)
    assert a == b


def test_compose_uses_marker_block(tmp_path: Path) -> None:
    """The tool_catalog markers must wrap the rendered catalog."""
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(tmp_path)
    begin = prompt.find("<!-- tool_catalog:begin -->")
    end = prompt.find("<!-- tool_catalog:end -->")
    assert 0 <= begin < end, "marker block missing or inverted"
    between = prompt[begin:end]
    for name in ("list_blocks", "get_workflow", "search_docs", "get_project_info"):
        assert f"`{name}`" in between


# ---------------------------------------------------------------------------
# ADR-040 §3.4 — wheel-layout regression (closes #824).
# ---------------------------------------------------------------------------


def test_load_skill_md_returns_content() -> None:
    """ADR-040 §3.4: ``_load_skill_md`` returns the SKILL.md content.

    Resolution prefers ``importlib.resources.files("scieasy") /
    _skills/scieasy/SKILL.md`` and falls back to the legacy walk-up
    while the Skills track ships the relocated file.
    """
    from scieasy.ai.agent.system_prompt import _load_skill_md

    content = _load_skill_md()
    assert content, "_load_skill_md returned empty string"
    assert "name: scieasy" in content or "# SciEasy" in content


# ---------------------------------------------------------------------------
# ADR-040 §3.3 — project context splice (closes #825).
# ---------------------------------------------------------------------------


def test_compose_renders_project_context_block(tmp_path: Path) -> None:
    """ADR-040 §3.3: compose splices a ``<!-- project_context -->`` block into SKILL.md.

    Project setup: tmp_path/project.yaml with project.name = "TestProj" and
    tmp_path/workflows/ with one .yaml file.
    """
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    (tmp_path / "project.yaml").write_text("project:\n  name: TestProj\n", encoding="utf-8")
    (tmp_path / "workflows").mkdir()
    (tmp_path / "workflows" / "wf.yaml").write_text("workflow:\n  id: x\n", encoding="utf-8")

    prompt = compose_system_prompt(tmp_path)
    begin = prompt.find("<!-- project_context:begin -->")
    end = prompt.find("<!-- project_context:end -->")
    assert 0 <= begin < end, "project_context marker block missing or inverted"
    between = prompt[begin:end]
    assert "TestProj" in between, "project_name not rendered in project_context block"
    assert "1 workflow" in between, "workflow count not rendered"


def test_compose_project_context_handles_non_git_project(tmp_path: Path) -> None:
    """ADR-040 §3.3: project_context omits the Git: line when project_dir isn't a git repo."""
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    (tmp_path / "project.yaml").write_text("project:\n  name: NoGit\n", encoding="utf-8")
    prompt = compose_system_prompt(tmp_path)
    begin = prompt.find("<!-- project_context:begin -->")
    end = prompt.find("<!-- project_context:end -->")
    assert 0 <= begin < end
    between = prompt[begin:end]
    # No git data means no Git: line.
    assert "**Git:**" not in between


def test_compose_project_context_empty_workflows(tmp_path: Path) -> None:
    """ADR-040 §3.3: project_context renders even with zero workflows."""
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    (tmp_path / "project.yaml").write_text("project:\n  name: Empty\n", encoding="utf-8")
    prompt = compose_system_prompt(tmp_path)
    between = prompt[prompt.find("<!-- project_context:begin -->") : prompt.find("<!-- project_context:end -->")]
    assert "0 workflows" in between
    # No "Recently-modified workflows" section when there are no workflows.
    assert "Recently-modified workflows" not in between


def test_compose_project_context_meets_100ms_budget(tmp_path: Path) -> None:
    """ADR-040 §3.3 perf budget: <100ms even at 1000 workflows.

    Creates 1000 empty *.yaml files in tmp_path/workflows/ and times the
    full compose call.
    """
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    (tmp_path / "project.yaml").write_text("project:\n  name: PerfTest\n", encoding="utf-8")
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    for i in range(1000):
        (workflows_dir / f"wf-{i:04d}.yaml").write_text("workflow:\n  id: x\n", encoding="utf-8")

    # Warm-up call so SKILL.md / tool_catalog enumeration costs don't
    # dominate the measurement (the §3.3 budget is for project_context
    # rendering specifically).
    compose_system_prompt(tmp_path)
    start = time.perf_counter()
    compose_system_prompt(tmp_path)
    duration = time.perf_counter() - start
    # Headroom: 100ms is the budget; allow up to 500ms on CI runners
    # that may be under load.
    # TODO(#1012): tighten to <100ms once Phase 2a.5 audit confirms the
    # CI baseline measurement is stable. Out of scope per ADR-040 §3.3
    # / phase: 2a I40a. Followup: https://github.com/zjzcpj/SciEasy/issues/1012.
    assert duration < 0.5, f"compose_system_prompt took {duration:.3f}s, expected <0.5s"
