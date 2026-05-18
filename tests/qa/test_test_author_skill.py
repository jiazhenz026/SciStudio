"""Tests for the TC-1F.5 ``test-author`` skill body (ADR-043 §4.4).

The skill body is mirrored to TWO locations during Phase 1:

* ``src/scieasy/_skills/qa/test-author/SKILL.md`` — canonical source for
  the future ``agent_provisioning.qa_skills`` cross-runtime installer
  (shipped by 1H sub-PR 3 per the cascade dispatch prompt).
* ``.claude/skills/test-author/SKILL.md`` — the in-repo Claude Code
  mirror so the skill is discoverable immediately by the current
  Claude Code session.

Both mirrors MUST stay in sync (byte-for-byte) until 1H sub-PR 3 lands
a generator. The tests below pin that invariant.

Per ADR-043 §4.4 the body is a 7-step protocol verbatim from the ADR;
the tests assert each canonical step heading is present so a future
ADR edit triggers a CI-visible diff before the skill body drifts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Use the project root via three parents (tests/qa/<this>.py).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_SKILL = _REPO_ROOT / "src" / "scieasy" / "_skills" / "qa" / "test-author" / "SKILL.md"
_MIRROR_SKILL = _REPO_ROOT / ".claude" / "skills" / "test-author" / "SKILL.md"


# --------------------------------------------------------------------------- #
# Existence + parity                                                          #
# --------------------------------------------------------------------------- #


class TestSkillFilesExist:
    """Both the canonical source and the .claude mirror must be present."""

    def test_source_skill_exists(self) -> None:
        # Behavior: the canonical source body lives under
        # src/scieasy/_skills/qa/ per ADR-043 §4.4 (will be the input
        # for agent_provisioning.qa_skills in 1H sub-PR 3).
        assert _SOURCE_SKILL.is_file(), f"missing skill source at {_SOURCE_SKILL}"

    def test_claude_mirror_exists(self) -> None:
        # Behavior: .claude/skills/test-author/SKILL.md must exist so
        # Claude Code's skill discovery finds it without waiting on
        # the cross-runtime installer (PR target tracking branch).
        assert _MIRROR_SKILL.is_file(), f"missing skill mirror at {_MIRROR_SKILL}"

    def test_source_and_mirror_byte_identical(self) -> None:
        # Behavior: until 1H sub-PR 3 generates the mirror from the
        # source, the two files MUST stay byte-for-byte identical so
        # the in-repo Claude Code mirror does not drift from the
        # canonical body.
        src = _SOURCE_SKILL.read_text(encoding="utf-8")
        mir = _MIRROR_SKILL.read_text(encoding="utf-8")
        assert src == mir, (
            "src/scieasy/_skills/qa/test-author/SKILL.md and "
            ".claude/skills/test-author/SKILL.md must match byte-for-byte "
            "until 1H sub-PR 3 (qa_skills installer) generates the mirror."
        )


# --------------------------------------------------------------------------- #
# Frontmatter                                                                 #
# --------------------------------------------------------------------------- #


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return ``(frontmatter_yaml, body_md)`` for a SKILL.md style file.

    Helper rather than importing pyyaml here — frontmatter parsing is
    well-defined for our minimal shape and we'd rather not add a
    dependency for these test-only assertions.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise AssertionError("file does not start with a `---` frontmatter delimiter")
    end = next((i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if end is None:
        raise AssertionError("frontmatter block has no closing `---`")
    return "\n".join(lines[1:end]), "\n".join(lines[end + 1 :])


@pytest.fixture(params=[_SOURCE_SKILL, _MIRROR_SKILL], ids=["source", "mirror"])
def skill_text(request: pytest.FixtureRequest) -> str:
    """Parametrise every frontmatter / body test over BOTH locations."""
    return request.param.read_text(encoding="utf-8")


class TestSkillFrontmatter:
    """Frontmatter must match the ADR-043 §4.4 contract."""

    def test_frontmatter_block_present(self, skill_text: str) -> None:
        # Behavior: the file is parseable as `---`-delimited frontmatter.
        fm, body = _split_frontmatter(skill_text)
        assert fm.strip(), "frontmatter block is empty"
        assert body.strip(), "body is empty"

    def test_name_field_is_test_author(self, skill_text: str) -> None:
        # Behavior: skill name MUST be `test-author` (matches §4.4 exactly).
        fm, _ = _split_frontmatter(skill_text)
        assert "name: test-author" in fm

    def test_description_field_present(self, skill_text: str) -> None:
        # Behavior: skill MUST carry a `description:` line so Claude
        # Code's auto-trigger heuristic can match user prompts.
        fm, _ = _split_frontmatter(skill_text)
        assert "description:" in fm

    def test_allowed_tools_list_present(self, skill_text: str) -> None:
        # Behavior: §4.4 names exactly Read, Write, Edit, Bash. The skill
        # MUST declare those tools — the agent runtime denies anything
        # outside the allowlist.
        fm, _ = _split_frontmatter(skill_text)
        assert "allowed-tools:" in fm
        for tool in ("Read", "Write", "Edit", "Bash"):
            assert tool in fm, f"allowed-tools missing {tool!r}"

    def test_priority_is_p0(self, skill_text: str) -> None:
        # Behavior: §4.4 adds the skill to the P0 list. CI ratchets
        # P0 skills as mandatory; a drift to P1 here would silently
        # demote it.
        fm, _ = _split_frontmatter(skill_text)
        assert "priority: P0" in fm

    def test_source_adr_recorded(self, skill_text: str) -> None:
        # Behavior: each generated/manually-mirrored ADR-sourced skill
        # records which ADR + section it derives from. Lets the doc
        # drift auditor pair the skill body against §4.4 going forward.
        fm, _ = _split_frontmatter(skill_text)
        assert "source_adr: ADR-043" in fm
        assert "source_section" in fm


# --------------------------------------------------------------------------- #
# Body — required protocol steps                                              #
# --------------------------------------------------------------------------- #


class TestSkillBodyContents:
    """The 7-step protocol from ADR-043 §4.4 must be present verbatim."""

    @pytest.mark.parametrize(
        "step_heading",
        [
            "1. **Identify the contract.**",
            "2. **Write the assertion first.**",
            "3. **Run pytest.**",
            "4. **Write the minimum implementation**",
            "5. **Run pytest again.**",
            "6. **Add edge cases**",
            "7. **Add a property test**",
        ],
    )
    def test_each_step_heading_present(self, skill_text: str, step_heading: str) -> None:
        # Behavior: the 7-step protocol is the heart of the skill.
        # Any silent edit that drops a step would degrade the agent's
        # test-authoring discipline without anybody noticing — pin it.
        _fm, body = _split_frontmatter(skill_text)
        assert step_heading in body, f"missing protocol step heading: {step_heading!r}"

    def test_forbidden_patterns_section_present(self, skill_text: str) -> None:
        # Behavior: §4.4 includes a "Forbidden patterns" section listing
        # the AST-flagged anti-patterns. Pin its heading so a future
        # author can't drop the section silently.
        _fm, body = _split_frontmatter(skill_text)
        assert "## Forbidden patterns" in body

    def test_mutation_score_table_present(self, skill_text: str) -> None:
        # Behavior: the skill body cites §4.5 mutation-score targets so
        # the agent knows the bar after authoring a test. Pin the
        # presence of all four path rows.
        _fm, body = _split_frontmatter(skill_text)
        for path in (
            "src/scieasy/qa/**",
            "src/scieasy/core/**",
            "src/scieasy/{blocks,engine,api,workflow}/**",
            "src/scieasy/ai/**",
        ):
            assert path in body, f"§4.5 path row missing: {path!r}"

    def test_uncertainty_carve_out_present(self, skill_text: str) -> None:
        # Behavior: §4.4 closes with "When uncertain, prefer no edit" —
        # this is the agent's guard against placeholder test theater.
        _fm, body = _split_frontmatter(skill_text)
        assert "## When uncertain" in body

    def test_followup_todo_references_1h_subpr_3(self, skill_text: str) -> None:
        # Behavior: the in-repo mirror MUST point at the 1H sub-PR 3
        # tracking issue so a maintainer sweeping `grep -rn "TODO(#"`
        # finds the cross-runtime installation followup.
        _fm, body = _split_frontmatter(skill_text)
        assert "TODO(#1145)" in body
        assert "qa_skills" in body
