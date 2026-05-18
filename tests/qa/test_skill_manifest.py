"""Tests for ``docs/skills/required.yaml`` + the 11 SKILL.md pointer files (Phase 1H sub-PR 3, TC-1H.7/1H.8).

References
----------
ADR-042 §17.1 — required-skill list (canonical names + priorities).
ADR-042 §17.3 — manifest format.
ADR-044 §11 — pointer-pattern (≤ 30 body lines, real pointer target).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# Repo-root walk-up — tests run from anywhere in the tree.
_HERE = Path(__file__).resolve()


def _repo_root() -> Path:
    for parent in _HERE.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise FileNotFoundError("could not locate repo root from test_skill_manifest.py")


REQUIRED_NAMES = (
    "scieasy-skill-creator",
    "doc-drift-guard",
    "provenance-tagger",
    "adr-router",
    "pr-maintainer",
    "mantis-proof",
    "session-logs",
    "release-maintainer",
    "codemod-with-adr",
    "hallucination-guard",
    "maintainers-reverse",
)

# Allowed `kind` values per ADR-044 §11.3.
ALLOWED_KINDS = {"procedural", "tool-wrapping", "bootstrap-meta"}

# Allowed `priority` values per ADR-042 §17.1.
ALLOWED_PRIORITIES = {"P0", "P1", "P2"}


# ---------------------------------------------------------------------------
# docs/skills/required.yaml
# ---------------------------------------------------------------------------


def test_required_yaml_exists() -> None:
    p = _repo_root() / "docs" / "skills" / "required.yaml"
    assert p.is_file(), "ADR-042 §17.3 requires docs/skills/required.yaml"


def test_required_yaml_lists_all_11_skills() -> None:
    p = _repo_root() / "docs" / "skills" / "required.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    names = [entry["name"] for entry in data["skills"]]
    assert sorted(names) == sorted(REQUIRED_NAMES)


def test_required_yaml_entry_shape() -> None:
    p = _repo_root() / "docs" / "skills" / "required.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    for entry in data["skills"]:
        assert set(entry.keys()) >= {"name", "priority", "kind", "purpose", "pointer"}, entry
        assert entry["priority"] in ALLOWED_PRIORITIES
        assert entry["kind"] in ALLOWED_KINDS
        assert isinstance(entry["pointer"], str) and entry["pointer"]


def test_required_yaml_priority_distribution() -> None:
    """Per ADR-042 §17.1 — exactly 4 P0 + 4 P1 + 3 P2 = 11."""
    p = _repo_root() / "docs" / "skills" / "required.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    counts = {"P0": 0, "P1": 0, "P2": 0}
    for entry in data["skills"]:
        counts[entry["priority"]] += 1
    assert counts == {"P0": 4, "P1": 4, "P2": 3}


# ---------------------------------------------------------------------------
# Source-of-truth tree under src/scieasy/_skills/qa/
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", REQUIRED_NAMES)
def test_source_skill_md_exists(name: str) -> None:
    p = _repo_root() / "src" / "scieasy" / "_skills" / "qa" / name / "SKILL.md"
    assert p.is_file(), f"source SKILL.md missing: {p}"


@pytest.mark.parametrize("name", REQUIRED_NAMES)
def test_source_skill_md_pointer_pattern(name: str) -> None:
    """ADR-044 §11: pointer-pattern files have a frontmatter + ≤ 30 body lines."""
    p = _repo_root() / "src" / "scieasy" / "_skills" / "qa" / name / "SKILL.md"
    text = p.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{name} missing frontmatter"
    # Frontmatter block + body.
    closing = text.find("\n---\n", 4)
    assert closing > 0, f"{name} frontmatter not closed"
    body = text[closing + 5 :]
    body_lines = [line for line in body.splitlines() if line.strip()]
    assert len(body_lines) <= 30, f"{name} body exceeds 30 non-blank lines ({len(body_lines)})"


@pytest.mark.parametrize("name", REQUIRED_NAMES)
def test_source_skill_md_frontmatter_shape(name: str) -> None:
    p = _repo_root() / "src" / "scieasy" / "_skills" / "qa" / name / "SKILL.md"
    text = p.read_text(encoding="utf-8")
    fm_end = text.find("\n---\n", 4)
    fm_block = text[4:fm_end]
    fm = yaml.safe_load(fm_block)
    assert fm["name"] == name
    assert fm["kind"] in ALLOWED_KINDS
    assert fm["priority"] in ALLOWED_PRIORITIES
    assert fm["adr"] == 42
    assert "pointer" in fm
    assert isinstance(fm["description"], str)


@pytest.mark.parametrize("name", REQUIRED_NAMES)
def test_source_skill_md_includes_uncertainty_phrase(name: str) -> None:
    """ADR-042 §17.5: every skill must include the no-edit-with-explanation phrase."""
    p = _repo_root() / "src" / "scieasy" / "_skills" / "qa" / name / "SKILL.md"
    text = p.read_text(encoding="utf-8")
    assert "When uncertain, prefer no edit with explanation." in text, name


# ---------------------------------------------------------------------------
# Installed copies under .claude/skills/<name>/ (optional — .claude/ is gitignored)
# ---------------------------------------------------------------------------
#
# `.claude/` is gitignored (see `.gitignore`). Installed copies materialise
# via `agent_provisioning.qa_skills.install_qa_skills` at project-init time
# and are NOT committed. The byte-identity invariant (installed equals
# source) is enforced inside the installer itself by `_read_skill_body`
# (which only ever returns the source body); the dedicated
# `tests/qa/test_qa_skills_installer.py` suite exercises that path.
#
# Here we only do a soft-skip drift check: when an installed copy happens to
# exist locally, assert it matches source. On a fresh checkout the test
# skips.


@pytest.mark.parametrize("name", REQUIRED_NAMES)
def test_installed_matches_source_when_present(name: str) -> None:
    source = _repo_root() / "src" / "scieasy" / "_skills" / "qa" / name / "SKILL.md"
    installed = _repo_root() / ".claude" / "skills" / name / "SKILL.md"
    if not installed.is_file():
        pytest.skip(f"{installed} not present (expected; .claude/ is gitignored)")
    assert source.read_text(encoding="utf-8") == installed.read_text(encoding="utf-8")
