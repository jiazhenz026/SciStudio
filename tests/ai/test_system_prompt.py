"""Tests for the system-prompt composer.

ADR-034 Phase 1.2 baseline + ADR-040 §3.3 / §3.4 evolution (S40a skeleton).

All four existing behavior tests are marked skip in this skeleton phase —
they rely on the live ``_load_skill_md`` / ``_render_tool_catalog`` / etc.
bodies which now raise ``NotImplementedError`` until I40a Phase 2a wires
the FastMCP-backed implementations.

The skeleton additionally pre-declares two new test stubs reflecting
the §3.3 / §3.4 additions:

* Wheel-layout regression: ``_load_skill_md`` uses ``importlib.resources``
  instead of walking up from ``__file__``. Closes #824.
* Project context splice: ``compose_system_prompt(project_dir)`` renders
  a project-specific block between ``<!-- project_context:begin/end -->``
  markers. Closes #825.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): wire FastMCP-backed compose.")
def test_compose_reads_skill_md(tmp_path: Path) -> None:
    """The returned prompt must contain a recognisable SKILL.md marker."""
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(tmp_path)
    # SKILL.md opens with YAML frontmatter `name: scieasy` and the H1
    # `# SciEasy` heading — both are stable identity markers.
    assert "name: scieasy" in prompt
    assert "# SciEasy" in prompt


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): wire FastMCP list_tools() catalog.")
def test_compose_injects_full_tool_catalog(tmp_path: Path) -> None:
    """Every registered tool name must appear in the rendered prompt.

    Pre-FastMCP this iterated ``TOOL_REGISTRY``; post-FastMCP it
    iterates ``mcp.list_tools()``. The deleted ``_registry.py`` no
    longer exists; I40a wires the equivalent enumeration via FastMCP.
    """
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(tmp_path)
    # Spot-check tools across all four categories.
    for name in (
        "list_blocks",
        "get_block_schema",
        "list_types",
        "get_workflow",
        "validate_workflow",
        "write_workflow",
        "run_workflow",
        "cancel_run",
        "get_run_status",
        "finish_ai_block",  # ADR-035 §3.5 — 10th workflow-category tool.
        "read_block_source",
        "list_block_examples",
        "scaffold_block",
        "reload_blocks",
        "run_block_tests",
        "get_block_output",
        "inspect_data",
        "preview_data",
        "get_lineage",
        "get_block_config",
        "update_block_config",
        "get_block_logs",
        "search_docs",
        "get_doc",
        "list_data",
        "get_project_info",
    ):
        assert f"`{name}`" in prompt, f"tool {name!r} missing from rendered prompt"


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): deterministic output verification.")
def test_compose_is_idempotent(tmp_path: Path) -> None:
    """Same input project_dir must yield byte-identical output.

    Post-ADR-040 §3.3, this is per-project-dynamic but still
    deterministic for a given project_dir (no global state, no timestamps
    in the rendered context).
    """
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    a = compose_system_prompt(tmp_path)
    b = compose_system_prompt(tmp_path)
    assert a == b


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): tool_catalog marker splice.")
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


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): #824 importlib.resources skill load.")
def test_load_skill_md_via_importlib_resources() -> None:
    """ADR-040 §3.4: ``_load_skill_md`` uses ``importlib.resources`` so wheel installs work.

    The legacy walk-up resolver broke for ``pip install scieasy`` because
    ``skills/`` lived at repo-root, not inside the package. I40a switches
    to ``files('scieasy') / '_skills' / 'scieasy' / 'SKILL.md'``.

    Test plan:
      1. Verify ``_load_skill_md()`` returns a non-empty string.
      2. Verify the string starts with a YAML frontmatter / H1 marker
         (``# SciEasy`` or ``name: scieasy``).
      3. (Optional regression) ensure the function does NOT walk up from
         ``__file__`` looking for ``skills/`` at repo-root — that path
         is unreliable in wheel installs.
    """
    from scieasy.ai.agent.system_prompt import _load_skill_md

    content = _load_skill_md()
    assert content, "_load_skill_md returned empty string"
    assert "name: scieasy" in content or "# SciEasy" in content


# ---------------------------------------------------------------------------
# ADR-040 §3.3 — project context splice (closes #825).
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): #825 project_context splice.")
def test_compose_renders_project_context_block(tmp_path: Path) -> None:
    """ADR-040 §3.3: compose splices a ``<!-- project_context -->`` block into SKILL.md.

    Test plan:
      1. Set up tmp_path/project.yaml with project.name = "TestProj".
      2. Set up tmp_path/workflows/ with one .yaml file.
      3. Call compose_system_prompt(tmp_path).
      4. Assert prompt contains both
         ``<!-- project_context:begin -->`` and
         ``<!-- project_context:end -->``.
      5. Assert prompt mentions "TestProj" between the markers.
      6. Assert prompt mentions "1 workflow" (or similar count rendering).
    """
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(tmp_path)
    begin = prompt.find("<!-- project_context:begin -->")
    end = prompt.find("<!-- project_context:end -->")
    assert 0 <= begin < end, "project_context marker block missing or inverted"


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): #825 git/non-git handling.")
def test_compose_project_context_handles_non_git_project(tmp_path: Path) -> None:
    """ADR-040 §3.3: project_context omits the Git: line when project_dir isn't a git repo."""
    raise NotImplementedError("skeleton")


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): #825 perf budget assertion.")
def test_compose_project_context_meets_100ms_budget(tmp_path: Path) -> None:
    """ADR-040 §3.3 perf budget: <100ms even at 1000 workflows.

    Test plan:
      1. Create 1000 empty *.yaml files in tmp_path/workflows/.
      2. Time compose_system_prompt(tmp_path).
      3. Assert duration < 100ms.
    """
    raise NotImplementedError("skeleton")
