"""Wheel-install regression for ADR-040 §3.4 / #824 — relocated skill tree.

These tests assert that the multi-skill source tree under
``src/scieasy/_skills/scieasy/`` is findable via ``importlib.resources``
in **both** editable installs and wheel installs (per the
``[tool.setuptools.package-data]`` entry in ``pyproject.toml``).

Skill bodies authored by I40b in Phase 2c (ADR-040). The base SKILL.md
carries the agent identity + skill index + the ``<!-- project_context -->``
and ``<!-- tool_catalog -->`` splice markers; the 5 task skills carry
the task-scoped teaching surfaces.
"""

from __future__ import annotations

from importlib.resources import files

# Per ADR-040 §3.4, these 5 task skills MUST exist alongside the base.
_TASK_SKILLS: tuple[str, ...] = (
    "scieasy-build-workflow",
    "scieasy-write-block",
    "scieasy-debug-run",
    "scieasy-inspect-data",
    "scieasy-project-qa",
)


def test_base_skill_loadable_via_importlib_resources() -> None:
    """The base ``scieasy/SKILL.md`` is shipped and contains real content.

    Closes #824 (skills lost on wheel install): the package-data glob
    ``_skills/scieasy/**/*.md`` in pyproject.toml MUST keep the file
    accessible via importlib.resources after ``pip install dist/*.whl``.
    """
    base = files("scieasy") / "_skills" / "scieasy" / "SKILL.md"
    content = base.read_text(encoding="utf-8")
    # Frontmatter present.
    assert content.startswith("---\n"), "SKILL.md must start with YAML frontmatter."
    assert "name: scieasy" in content, "Base skill frontmatter must declare name: scieasy."
    # Body authored (not a skeleton stub).
    assert "Body content deferred" not in content, "Base SKILL.md body must be authored in Phase 2c (I40b)."
    # Splice markers preserved (target of _render_project_context + _render_tool_catalog).
    assert "<!-- project_context:begin -->" in content
    assert "<!-- project_context:end -->" in content
    assert "<!-- tool_catalog:begin -->" in content
    assert "<!-- tool_catalog:end -->" in content


def test_all_task_skills_loadable_via_importlib_resources() -> None:
    """All 5 task skill ``SKILL.md`` files are shipped with real bodies."""
    base_dir = files("scieasy") / "_skills" / "scieasy"
    for task_skill in _TASK_SKILLS:
        skill_md = base_dir / task_skill / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        assert content.startswith("---\n"), f"{task_skill}/SKILL.md must start with YAML frontmatter."
        assert f"name: {task_skill}" in content, f"{task_skill}/SKILL.md frontmatter must declare name: {task_skill}."
        assert "Body content deferred" not in content, (
            f"{task_skill}/SKILL.md body must be authored in Phase 2c (I40b)."
        )


def test_base_skill_indexes_all_task_skills() -> None:
    """The base ``SKILL.md`` must reference all 5 task skills by name.

    Discoverability check: the agent reads the base first and uses its
    skill index to find the relevant task skill. If a task skill is
    not indexed, the agent will never load it.
    """
    base = files("scieasy") / "_skills" / "scieasy" / "SKILL.md"
    content = base.read_text(encoding="utf-8")
    for task_skill in _TASK_SKILLS:
        assert task_skill in content, f"Base SKILL.md must reference {task_skill} in its skill index."


# --- Codex P1/P2 reconcile regression pins ---------------------------------
# These tests pin the specific tool-shape facts surfaced by the post-#1059
# Codex auto-review. Each one corresponds to a finding on PR #1059; the
# assertions guard against the body regressing to the pre-reconcile wording.


def test_write_block_skill_uses_type_name_not_block_path() -> None:
    """run_block_tests takes type_name, not block_path (Codex P1, #1059).

    Pins the fix at scieasy-write-block/SKILL.md — the tool signature in
    src/scieasy/ai/agent/mcp/tools_authoring.py:430 is
    run_block_tests(type_name: str), and the worked-example tool-call
    sequence MUST teach that — not the obsolete block_path parameter.
    """
    skill = files("scieasy") / "_skills" / "scieasy" / "scieasy-write-block" / "SKILL.md"
    content = skill.read_text(encoding="utf-8")
    assert "type_name=" in content, (
        "scieasy-write-block must teach run_block_tests with type_name=, "
        "not the obsolete block_path= parameter (Codex P1 on PR #1059)."
    )
    assert "block_path=" not in content, (
        "scieasy-write-block must NOT mention block_path= for run_block_tests "
        "(parameter does not exist on the live tool — Codex P1 on PR #1059)."
    )


def test_build_workflow_skill_documents_validate_result_correctly() -> None:
    """validate_workflow returns ValidateWorkflowResult(valid, errors) (Codex P2, #1059).

    Pins the fix at scieasy-build-workflow/SKILL.md — the read-class tool
    has no `ok` field and no `next_step`; envelope shape is
    (valid: bool, errors: list[str]) per tools_workflow.py:251.
    """
    skill = files("scieasy") / "_skills" / "scieasy" / "scieasy-build-workflow" / "SKILL.md"
    content = skill.read_text(encoding="utf-8")
    assert "ValidateWorkflowResult" in content, (
        "scieasy-build-workflow must document the real envelope name ValidateWorkflowResult (Codex P2 on PR #1059)."
    )
    assert "valid=False" in content or "valid: bool" in content, (
        "scieasy-build-workflow must teach the `valid` field "
        "(Codex P2 on PR #1059 — was incorrectly documented as `ok`)."
    )


def test_debug_run_skill_documents_get_run_status_envelope_correctly() -> None:
    """GetRunStatusResult has progress.block_states + errors (Codex P2, #1059).

    Pins the fix at scieasy-debug-run/SKILL.md — per tools_workflow.py:300
    the per-block state map lives at progress.block_states (NOT top-level
    block_states), errors is a list of BlockErrorEntry (NOT a top-level
    error: str | None), and there is no 'pending' state.
    """
    skill = files("scieasy") / "_skills" / "scieasy" / "scieasy-debug-run" / "SKILL.md"
    content = skill.read_text(encoding="utf-8")
    assert "progress.block_states" in content or 'progress: {"block_states"' in content, (
        "scieasy-debug-run must document progress.block_states "
        "(Codex P2 on PR #1059 — block_states is nested, not top-level)."
    )
    assert "BlockErrorEntry" in content, (
        "scieasy-debug-run must mention BlockErrorEntry "
        "(Codex P2 on PR #1059 — errors is list[BlockErrorEntry], not a str)."
    )
