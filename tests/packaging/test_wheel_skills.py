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
    assert "Body content deferred" not in content, (
        "Base SKILL.md body must be authored in Phase 2c (I40b)."
    )
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
        assert content.startswith("---\n"), (
            f"{task_skill}/SKILL.md must start with YAML frontmatter."
        )
        assert f"name: {task_skill}" in content, (
            f"{task_skill}/SKILL.md frontmatter must declare name: {task_skill}."
        )
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
        assert task_skill in content, (
            f"Base SKILL.md must reference {task_skill} in its skill index."
        )
