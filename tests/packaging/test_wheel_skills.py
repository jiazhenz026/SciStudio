"""Wheel-install regression for ADR-040 §3.4 / #824 — relocated skill tree.

These tests assert that the multi-skill source tree under
``src/scistudio/_skills/scistudio/`` is findable via ``importlib.resources``
in **both** editable installs and wheel installs (per the
``[tool.setuptools.package-data]`` entry in ``pyproject.toml``).

Skill bodies authored by I40b in Phase 2c (ADR-040). The base SKILL.md
carries the agent identity + skill index + the ``<!-- project_context -->``
and ``<!-- tool_catalog -->`` splice markers; the 5 task skills carry
the task-scoped teaching surfaces.
"""

from __future__ import annotations

from importlib.resources import files

# Per ADR-040 §3.4 + ADR-048 SPEC 2, these 6 task skills MUST exist alongside
# the base ``scistudio`` skill.
_TASK_SKILLS: tuple[str, ...] = (
    "scistudio-build-workflow",
    "scistudio-write-block",
    "scistudio-debug-run",
    "scistudio-inspect-data",
    "scistudio-project-qa",
    "scistudio-write-plot",
)


def test_base_skill_loadable_via_importlib_resources() -> None:
    """The base ``scistudio/SKILL.md`` is shipped and contains real content.

    Closes #824 (skills lost on wheel install): the package-data glob
    ``_skills/scistudio/**/*.md`` in pyproject.toml MUST keep the file
    accessible via importlib.resources after ``pip install dist/*.whl``.
    """
    base = files("scistudio") / "_skills" / "scistudio" / "SKILL.md"
    content = base.read_text(encoding="utf-8")
    # Frontmatter present.
    assert content.startswith("---\n"), "SKILL.md must start with YAML frontmatter."
    assert "name: scistudio" in content, "Base skill frontmatter must declare name: scistudio."
    # Body authored (not a skeleton stub).
    assert "Body content deferred" not in content, "Base SKILL.md body must be authored in Phase 2c (I40b)."
    # Splice markers preserved (target of _render_project_context + _render_tool_catalog).
    assert "<!-- project_context:begin -->" in content
    assert "<!-- project_context:end -->" in content
    assert "<!-- tool_catalog:begin -->" in content
    assert "<!-- tool_catalog:end -->" in content


def test_all_task_skills_loadable_via_importlib_resources() -> None:
    """All 5 task skill ``SKILL.md`` files are shipped with real bodies."""
    base_dir = files("scistudio") / "_skills" / "scistudio"
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
    base = files("scistudio") / "_skills" / "scistudio" / "SKILL.md"
    content = base.read_text(encoding="utf-8")
    for task_skill in _TASK_SKILLS:
        assert task_skill in content, f"Base SKILL.md must reference {task_skill} in its skill index."


# --- Codex P1/P2 reconcile regression pins ---------------------------------
# These tests pin the specific tool-shape facts surfaced by the post-#1059
# Codex auto-review. Each one corresponds to a finding on PR #1059; the
# assertions guard against the body regressing to the pre-reconcile wording.


def test_write_block_skill_uses_type_name_not_block_path() -> None:
    """run_block_tests takes type_name, not block_path (Codex P1, #1059).

    Pins the fix at scistudio-write-block/SKILL.md — the tool signature in
    src/scistudio/ai/agent/mcp/tools_authoring.py:430 is
    run_block_tests(type_name: str), and the worked-example tool-call
    sequence MUST teach that — not the obsolete block_path parameter.
    """
    skill = files("scistudio") / "_skills" / "scistudio" / "scistudio-write-block" / "SKILL.md"
    content = skill.read_text(encoding="utf-8")
    assert "type_name=" in content, (
        "scistudio-write-block must teach run_block_tests with type_name=, "
        "not the obsolete block_path= parameter (Codex P1 on PR #1059)."
    )
    assert "block_path=" not in content, (
        "scistudio-write-block must NOT mention block_path= for run_block_tests "
        "(parameter does not exist on the live tool — Codex P1 on PR #1059)."
    )


def test_build_workflow_skill_documents_validate_result_correctly() -> None:
    """validate_workflow returns ValidateWorkflowResult(valid, errors) (Codex P2, #1059).

    Pins the fix at scistudio-build-workflow/SKILL.md — the read-class tool
    has no `ok` field and no `next_step`; envelope shape is
    (valid: bool, errors: list[str]) per tools_workflow.py:251.
    """
    skill = files("scistudio") / "_skills" / "scistudio" / "scistudio-build-workflow" / "SKILL.md"
    content = skill.read_text(encoding="utf-8")
    assert "ValidateWorkflowResult" in content, (
        "scistudio-build-workflow must document the real envelope name ValidateWorkflowResult (Codex P2 on PR #1059)."
    )
    assert "valid=False" in content or "valid: bool" in content, (
        "scistudio-build-workflow must teach the `valid` field "
        "(Codex P2 on PR #1059 — was incorrectly documented as `ok`)."
    )


def test_debug_run_skill_documents_get_run_status_envelope_correctly() -> None:
    """GetRunStatusResult has progress.block_states + errors (Codex P2, #1059).

    Pins the fix at scistudio-debug-run/SKILL.md — per tools_workflow.py:300
    the per-block state map lives at progress.block_states (NOT top-level
    block_states), errors is a list of BlockErrorEntry (NOT a top-level
    error: str | None), and there is no 'pending' state.
    """
    skill = files("scistudio") / "_skills" / "scistudio" / "scistudio-debug-run" / "SKILL.md"
    content = skill.read_text(encoding="utf-8")
    assert "progress.block_states" in content or 'progress: {"block_states"' in content, (
        "scistudio-debug-run must document progress.block_states "
        "(Codex P2 on PR #1059 — block_states is nested, not top-level)."
    )
    assert "BlockErrorEntry" in content, (
        "scistudio-debug-run must mention BlockErrorEntry "
        "(Codex P2 on PR #1059 — errors is list[BlockErrorEntry], not a str)."
    )


# --- F40-integration regression pins ---------------------------------------


def test_build_workflow_skill_run_failure_section_uses_live_envelope() -> None:
    """F40-integration F3: §6 "When a run fails" teaches the live envelope.

    Pre-F3 the section taught flat ``{state, block_states, error}`` —
    matching the legacy pre-FastMCP shape. Post-F3 it teaches the live
    ``progress.block_states`` + ``errors: list[BlockErrorEntry]`` shape.
    """
    skill = files("scistudio") / "_skills" / "scistudio" / "scistudio-build-workflow" / "SKILL.md"
    content = skill.read_text(encoding="utf-8")
    assert "GetRunStatusResult" in content, "scistudio-build-workflow §6 must reference the live envelope name."
    assert "progress" in content and "block_states" in content
    assert "BlockErrorEntry" in content, "scistudio-build-workflow §6 must document the BlockErrorEntry shape."


def test_write_block_skill_frontmatter_disambiguates_add_block_to_workflow() -> None:
    """F40-integration F5: frontmatter explicitly distinguishes file-authoring
    vs adding-an-existing-block-as-a-workflow-node.

    Pre-F5 the description triggered both ``scistudio-write-block`` AND
    ``scistudio-build-workflow`` for a query like "add a new block to my
    workflow" (block-authoring vs adding-a-node-to-yaml). Post-F5 the
    description names the actual file path target and rejects the
    YAML-add use case.
    """
    skill = files("scistudio") / "_skills" / "scistudio" / "scistudio-write-block" / "SKILL.md"
    content = skill.read_text(encoding="utf-8")
    # New disambiguator phrasing — capitalised so an agent skimming the
    # frontmatter cannot miss it.
    assert "NEW BLOCK FILE" in content or "blocks/<name>.py" in content, (
        "scistudio-write-block frontmatter must name the file-path target "
        "to disambiguate against scistudio-build-workflow (F40-integration F5)."
    )
    assert "EXISTING BLOCK TYPE" in content or "ADDING AN EXISTING" in content, (
        "scistudio-write-block frontmatter must reject the 'add an existing "
        "block as a workflow node' use case (F40-integration F5)."
    )


def test_base_skill_carries_static_tool_catalog_fallback_for_codex() -> None:
    """F40-integration F6: base SKILL.md has non-empty static content between
    ``<!-- tool_catalog:begin -->`` / ``<!-- tool_catalog:end -->`` markers.

    On Claude Code, ``compose_system_prompt`` splices the live FastMCP
    catalog over the static content (``_splice`` replaces ALL content
    between markers). On Codex, the splice does not run and the file is
    read verbatim; pre-F6 the markers wrapped empty space and Codex saw
    nothing. Post-F6 the static fallback enumerates all 4 categories.
    """
    base = files("scistudio") / "_skills" / "scistudio" / "SKILL.md"
    content = base.read_text(encoding="utf-8")
    begin = content.find("<!-- tool_catalog:begin -->")
    end = content.find("<!-- tool_catalog:end -->")
    assert begin >= 0 and end > begin, "tool_catalog markers missing"
    between = content[begin + len("<!-- tool_catalog:begin -->") : end].strip()
    assert between, (
        "Static tool catalog fallback must be non-empty so Codex agents "
        "(who read the file verbatim, no splice) see something (F40-integration F6)."
    )
    # The 4 category labels are pinned so a future refactor that drops a
    # category by accident gets flagged.
    for category in ("Workflow", "Authoring", "Inspection"):
        assert category in between, (
            f"Static tool catalog must list the {category} category for Codex (F40-integration F6)."
        )
