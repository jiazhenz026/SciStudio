"""ADR-055 Spec 2 (#2279) — ``get_agent_context`` over really provisioned assets.

The fixture project is provisioned through the normal provisioning entry point
(:func:`scistudio.agent_provisioning.install_project_agent_assets`), so the
index is checked against what SciStudio actually writes — not a hand-made
tree. Spec §2 User Story 1 / acceptance scenarios 1-3 and the no-project edge
case.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from scistudio.agent_provisioning import install_project_agent_assets
from scistudio.ai.agent.mcp import _context, tools_qa, tools_workspace
from scistudio.ai.agent.mcp.server import AUDIENCE_EXTERNAL_TAG, mcp


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@dataclass
class _StubContext:
    _project_dir: Path | None = None
    block_registry: object = field(default_factory=object)
    type_registry: object = field(default_factory=object)
    active_workflow_id: str | None = "main"

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture
def provisioned(tmp_path: Path) -> Path:
    root = tmp_path / "context project"
    root.mkdir()
    (root / "project.yaml").write_text(
        "project:\n  id: ctx-project\n  name: Context Project\n  description: fixture\n", encoding="utf-8"
    )
    (root / "workflows").mkdir()
    (root / "workflows" / "main.yaml").write_text("workflow: {}\n", encoding="utf-8")
    (root / "docs" / "guides").mkdir(parents=True)
    (root / "docs" / "overview.md").write_text("# Project overview\n\nWhat this project does.\n", encoding="utf-8")
    (root / "docs" / "guides" / "analysis.md").write_text("# Analysis guide\n\nSteps.\n", encoding="utf-8")
    install_project_agent_assets(root, force=False)
    return root


@pytest.fixture
def ctx(provisioned: Path) -> Iterator[_StubContext]:
    context = _StubContext(_project_dir=provisioned)
    _context.set_context(context)
    yield context
    _context.set_context(None)


def _classes(result: tools_qa.AgentContextResult) -> dict[str, tools_qa.AssetClassStatus]:
    return {status.asset_class: status for status in result.asset_classes}


def test_index_names_real_paths_with_working_retrievals(ctx: _StubContext, provisioned: Path) -> None:
    """AS1: identity, guidance, and an index whose every entry exists and is retrievable."""
    result = _run(tools_qa.get_agent_context())

    assert result.status == "ok"
    assert result.project is not None
    assert result.project["id"] == "ctx-project"
    assert result.project["name"] == "Context Project"
    assert result.project["active_workflow_id"] == "main"
    assert result.project["workflows"] == ["main"]

    classes = _classes(result)
    for name in ("guidance", "project_docs", "agent_reference", "skills_claude", "skills_agents", "hooks"):
        assert classes[name].available, f"{name}: {classes[name].diagnostic}"

    assert result.index, "a provisioned project must produce a non-empty index"
    for entry in result.index:
        assert (provisioned / entry.path).is_file(), entry.path
        expected_tool = "get_doc" if entry.asset_class == "project_docs" else "read_file"
        assert entry.retrieval.tool == expected_tool
        assert entry.retrieval.arguments == {"path": entry.path}

    # The docs index is the real docs/ tree, not a copy of other assets (FR-002).
    docs_entries = {entry.path for entry in result.index if entry.asset_class == "project_docs"}
    assert docs_entries == {"docs/overview.md", "docs/guides/analysis.md"}

    # Every retrieval instruction actually works with the tool it names.
    for entry in result.index:
        if entry.retrieval.tool == "get_doc":
            doc = _run(tools_qa.get_doc(**entry.retrieval.arguments))
            assert doc.content
        else:
            read = _run(tools_workspace.read_file(**entry.retrieval.arguments))
            assert read.status == "ok", entry.path
            assert read.content


def test_agent_reference_and_skills_titles_come_from_the_files(ctx: _StubContext) -> None:
    result = _run(tools_qa.get_agent_context())
    skills = [entry for entry in result.index if entry.asset_class == "skills_claude"]
    assert skills
    assert all(entry.path.startswith(".claude/skills/") and entry.path.endswith("/SKILL.md") for entry in skills)
    assert any(entry.title and entry.title.startswith("scistudio") for entry in skills)
    reference = [entry for entry in result.index if entry.asset_class == "agent_reference"]
    assert any(entry.path == ".scistudio/agent-reference/README.md" for entry in reference)


def test_guidance_summary_is_a_bounded_agents_md_excerpt(ctx: _StubContext, provisioned: Path) -> None:
    result = _run(tools_qa.get_agent_context())
    assert result.guidance_source == "AGENTS.md"
    assert result.guidance_summary
    agents = (provisioned / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith(result.guidance_summary[:200])
    assert len(result.guidance_summary) <= tools_qa._GUIDANCE_EXCERPT_CHARS


def test_missing_agent_reference_is_reported_not_fabricated(ctx: _StubContext, provisioned: Path) -> None:
    """AS2: a removed asset class is reported unavailable; the rest is unaffected."""
    before = _run(tools_qa.get_agent_context())
    shutil.rmtree(provisioned / ".scistudio" / "agent-reference")
    after = _run(tools_qa.get_agent_context())

    classes = _classes(after)
    assert classes["agent_reference"].available is False
    assert classes["agent_reference"].entry_count == 0
    assert ".scistudio/agent-reference" in (classes["agent_reference"].diagnostic or "")
    assert not [entry for entry in after.index if entry.asset_class == "agent_reference"]

    for name in ("guidance", "project_docs", "skills_claude", "skills_agents", "hooks"):
        assert classes[name].available
        assert classes[name].entry_count == _classes(before)[name].entry_count


def test_missing_docs_and_guidance_are_diagnosed(ctx: _StubContext, provisioned: Path) -> None:
    shutil.rmtree(provisioned / "docs")
    (provisioned / "AGENTS.md").unlink()
    (provisioned / "CLAUDE.md").unlink()
    result = _run(tools_qa.get_agent_context())
    classes = _classes(result)
    assert classes["project_docs"].available is False
    assert "docs/" in (classes["project_docs"].diagnostic or "")
    assert classes["guidance"].available is False
    assert result.guidance_summary is None
    assert result.guidance_source is None


def test_hook_guidance_states_where_hooks_run_and_never_claims_they_ran(ctx: _StubContext, provisioned: Path) -> None:
    """AS3: execution location explicit; no claim of host execution; server equivalents named."""
    (provisioned / ".claude" / "hooks" / "remind_poll_status.py").unlink()
    result = _run(tools_qa.get_agent_context())
    hooks = result.hooks
    assert hooks is not None
    assert hooks.host_execution_observed is False
    assert "does not execute them" in hooks.execution_location
    assert "not evidence" in hooks.execution_location
    by_name = {entry.hook: entry for entry in hooks.entries}
    assert set(by_name) == {
        "deny_scistudio_cli",
        "protect_workflow_yaml",
        "protect_data_dir",
        "enforce_list_blocks_before_block_write",
        "mark_list_blocks_called",
        "enforce_concrete_port_types",
        "remind_poll_status",
    }
    for entry in hooks.entries:
        assert entry.server_side_equivalent
        assert entry.script_present == (provisioned / entry.script_path).is_file()
    assert by_name["remind_poll_status"].script_present is False
    assert by_name["deny_scistudio_cli"].script_present is True


def test_absent_project_gets_an_explicit_response(tmp_path: Path) -> None:
    """Edge case: no project open -> explicit absent-context response, never a default index."""
    _context.set_context(_StubContext(_project_dir=None))
    try:
        result = _run(tools_qa.get_agent_context())
    finally:
        _context.set_context(None)
    assert result.status == "no_active_project"
    assert result.message and "open or create a project" in result.message
    assert result.project is None
    assert result.index == []
    assert result.asset_classes == []
    assert result.hooks is None
    assert result.guidance_summary is None
    # Instance-level facts are still reported.
    assert result.execution_environment["python_executable"] == sys.executable
    assert result.execution_environment["working_directory"] is None


def test_execution_environment_describes_run_command_without_side_effects(
    ctx: _StubContext, provisioned: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugins = tmp_path / "plugins-root"
    monkeypatch.setattr("scistudio.desktop.paths.plugins_dir", lambda: plugins)
    result = _run(tools_qa.get_agent_context())
    env = result.execution_environment
    assert env["python_executable"] == sys.executable
    assert env["working_directory"] == os.path.realpath(provisioned)
    assert env["environment_set"]["SCISTUDIO_PROJECT_DIR"] == os.path.realpath(provisioned)
    assert env["user_site_packages"].startswith(str(plugins))
    assert env["user_site_packages_exists"] is False
    # Describing the environment must not create the user dependency tree.
    assert not plugins.exists()
    assert "run_command" in result.capabilities["tools"]["execution"]


def test_get_agent_context_is_an_external_audience_read_tool() -> None:
    tools = {tool.name: tool for tool in _run(mcp.list_tools())}
    tags = set(tools["get_agent_context"].tags or ())
    assert AUDIENCE_EXTERNAL_TAG in tags
    assert "read" in tags and "write" not in tags
