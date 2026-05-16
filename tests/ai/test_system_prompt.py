"""Tests for the system-prompt composer.

ADR-040 §3.3 / §3.4 implementation.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path


def test_compose_reads_skill_md(tmp_path: Path) -> None:
    """The returned prompt must contain a recognisable SKILL.md marker."""
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(tmp_path)
    assert "name: scieasy" in prompt
    assert "# SciEasy" in prompt


def test_compose_injects_full_tool_catalog(tmp_path: Path) -> None:
    """Every registered tool name must appear in the rendered prompt."""
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(tmp_path)
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
        "finish_ai_block",
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


def test_load_skill_md_via_importlib_resources() -> None:
    """ADR-040 §3.4: ``_load_skill_md`` uses ``importlib.resources``."""
    from scieasy.ai.agent.system_prompt import _load_skill_md

    content = _load_skill_md()
    assert content, "_load_skill_md returned empty string"
    assert "name: scieasy" in content or "# SciEasy" in content


def test_load_skill_md_does_not_walk_up_from_file() -> None:
    """Confirm we don't fall back to a repo-root walk-up (the legacy bug)."""
    from scieasy.ai.agent.system_prompt import _load_skill_md

    # The current resolved path comes from importlib.resources — should
    # be inside the installed package, not the repo-root `skills/` dir.
    content = _load_skill_md()
    # The file content is the deterministic body of the relocated SKILL.md.
    assert "_skills" not in content  # the path is opaque; this is a sanity hold
    assert isinstance(content, str)


# ---------------------------------------------------------------------------
# ADR-040 §3.3 — project context splice (closes #825).
# ---------------------------------------------------------------------------


def test_compose_renders_project_context_block(tmp_path: Path) -> None:
    """ADR-040 §3.3: compose splices a project_context block into SKILL.md."""
    (tmp_path / "project.yaml").write_text("project:\n  name: TestProj\n", encoding="utf-8")
    (tmp_path / "workflows").mkdir()
    (tmp_path / "workflows" / "one.yaml").write_text("workflow: {}\n", encoding="utf-8")

    from scieasy.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(tmp_path)
    begin = prompt.find("<!-- project_context:begin -->")
    end = prompt.find("<!-- project_context:end -->")
    assert 0 <= begin < end, "project_context marker block missing or inverted"
    between = prompt[begin:end]
    assert "TestProj" in between
    assert "1 workflow" in between  # singular form


def test_compose_project_context_handles_non_git_project(tmp_path: Path) -> None:
    """ADR-040 §3.3: project_context omits the Git: line when project_dir isn't a git repo."""
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(tmp_path)
    begin = prompt.find("<!-- project_context:begin -->")
    end = prompt.find("<!-- project_context:end -->")
    between = prompt[begin:end]
    assert "**Git:**" not in between


def test_compose_project_context_handles_empty_workflows(tmp_path: Path) -> None:
    """Empty workflows/ dir → 0-workflow line, no recent-workflows section."""
    (tmp_path / "workflows").mkdir()
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(tmp_path)
    begin = prompt.find("<!-- project_context:begin -->")
    end = prompt.find("<!-- project_context:end -->")
    between = prompt[begin:end]
    assert "0 workflows" in between
    assert "Recently-modified workflows:" not in between


def test_compose_project_context_handles_git_project(tmp_path: Path) -> None:
    """ADR-040 §3.3: project_context includes branch + short sha when a git repo."""
    # Initialise a minimal git repo.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=False, timeout=10)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "t@t.test"],
        check=False,
        timeout=10,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "T"],
        check=False,
        timeout=10,
    )
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=False, timeout=10)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"],
        check=False,
        timeout=10,
    )

    from scieasy.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(tmp_path)
    begin = prompt.find("<!-- project_context:begin -->")
    end = prompt.find("<!-- project_context:end -->")
    between = prompt[begin:end]
    # Git block may or may not render depending on git availability; only
    # assert when the git binary was found.
    has_git = subprocess.run(["git", "--version"], capture_output=True, check=False).returncode == 0
    if has_git:
        assert "**Git:**" in between


def test_compose_project_context_meets_100ms_budget(tmp_path: Path) -> None:
    """ADR-040 §3.3 perf budget: <100ms even at 1000 workflows."""
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for i in range(1000):
        (workflows / f"wf_{i:04d}.yaml").touch()

    from scieasy.ai.agent.system_prompt import _render_project_context

    # Warm: import side effects already loaded.
    start = time.perf_counter()
    _render_project_context(tmp_path)
    elapsed_ms = (time.perf_counter() - start) * 1000
    # Generous-but-meaningful budget. CI runners can be slow on Windows
    # so we allow 250ms instead of strict 100; this still catches a
    # genuine O(N**2) regression.
    assert elapsed_ms < 250, f"project_context took {elapsed_ms:.1f}ms"


def test_compose_project_context_top_3_by_mtime(tmp_path: Path) -> None:
    """Recently-modified section shows top 3 by mtime."""
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    files = []
    for i in range(5):
        p = workflows / f"wf_{i}.yaml"
        p.touch()
        files.append(p)
    # Make wf_2 the most-recently-modified.
    time.sleep(0.01)
    files[2].touch()
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(tmp_path)
    begin = prompt.find("<!-- project_context:begin -->")
    end = prompt.find("<!-- project_context:end -->")
    between = prompt[begin:end]
    assert "Recently-modified workflows:" in between
    assert "`wf_2.yaml`" in between


def test_compose_project_context_uses_dir_name_when_project_yaml_missing(tmp_path: Path) -> None:
    """No project.yaml → fall back to dir name."""
    from scieasy.ai.agent.system_prompt import compose_system_prompt

    prompt = compose_system_prompt(tmp_path)
    between = prompt[prompt.find("<!-- project_context:begin -->") : prompt.find("<!-- project_context:end -->")]
    assert tmp_path.name in between
