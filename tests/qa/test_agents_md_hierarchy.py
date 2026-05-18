"""Tests for AGENTS.md hierarchy (Phase 1H sub-PR 2, TC-1H.3/1H.4).

References
----------
ADR-042 §12.1 — root AGENTS.md canonical; pointer files for other runtimes.
ADR-042 §12.2 — per-subtree AGENTS.md hierarchy.
ADR-042 §12.4 — validation rules (lint enforced in Phase 1F; here we test
the source-of-truth invariants directly).
ADR-043 §5.6 — required sections per AGENTS.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Repo-root walk-up — tests run from anywhere in the tree.
_HERE = Path(__file__).resolve()


def _repo_root() -> Path:
    for parent in _HERE.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise FileNotFoundError("could not locate repo root from test_agents_md_hierarchy.py")


REPO = _repo_root()

ROOT_AGENTS = REPO / "AGENTS.md"

# Per ADR-042 §12.2 + ADR-043 §5.3.
SUBTREE_AGENTS = (
    REPO / "src" / "scieasy" / "AGENTS.md",
    REPO / "src" / "scieasy" / "core" / "AGENTS.md",
    REPO / "src" / "scieasy" / "blocks" / "AGENTS.md",
    REPO / "src" / "scieasy" / "qa" / "AGENTS.md",
    REPO / "frontend" / "AGENTS.md",
    REPO / "docs" / "AGENTS.md",
    REPO / ".github" / "AGENTS.md",
    REPO / ".workflow" / "AGENTS.md",
)

# Pointer files per ADR-042 §12.1 (Windows fallback: `@include AGENTS.md`).
POINTER_FILES = {
    REPO / "CLAUDE.md": "@include AGENTS.md",
    REPO / "CURSOR.md": "@include AGENTS.md",
    REPO / "GEMINI.md": "@include AGENTS.md",
    REPO / ".aiderrc": "system: AGENTS.md",
}

# Required sections per ADR-043 §5.6.
REQUIRED_SECTIONS_SUBTREE = (
    "Scope",
    "Policy",
    "Routing",
    "Data classification",
    "Assessment rubric",
    "Paths",
    "Out-of-scope",
)
REQUIRED_SECTIONS_ROOT = (
    "Identity",
    "Policy",
    "Routing",
    "Data classification",
    "Assessment rubric",
    "Paths",
    "Out-of-scope",
)


# ---------------------------------------------------------------------------
# Root AGENTS.md
# ---------------------------------------------------------------------------


def test_root_agents_md_exists() -> None:
    """ADR-042 §12.1 — root AGENTS.md is canonical."""
    assert ROOT_AGENTS.is_file(), f"missing root AGENTS.md at {ROOT_AGENTS}"


def test_root_agents_md_has_required_sections() -> None:
    """ADR-043 §5.6 — root AGENTS.md MUST contain the 7 universal sections."""
    body = ROOT_AGENTS.read_text(encoding="utf-8")
    for header in REQUIRED_SECTIONS_ROOT:
        # Match `## Header` or `## Header (qualifier)` or similar.
        pattern = re.compile(rf"^##\s+{re.escape(header)}\b", re.MULTILINE)
        assert pattern.search(body), f"root AGENTS.md missing `## {header}` section"


def test_root_agents_md_under_size_target() -> None:
    """ADR-043 §5.3 — root target ≤200 lines (with §11.5 Hotfix Mode carve-out)."""
    lines = ROOT_AGENTS.read_text(encoding="utf-8").splitlines()
    # Soft ceiling: 230 lines accommodates verbatim Hotfix Mode preservation
    # per ADR-042 §27.3. Tighter limit becomes a CI gate in Phase 1G.
    assert len(lines) <= 230, f"root AGENTS.md is {len(lines)} lines (target ≤230 with hotfix carve-out)"


def test_root_agents_md_lists_all_subtrees() -> None:
    """Root AGENTS.md `## Per-subtree AGENTS.md` should reference all subtrees."""
    body = ROOT_AGENTS.read_text(encoding="utf-8")
    for path in SUBTREE_AGENTS:
        rel = path.relative_to(REPO).as_posix()
        assert rel in body, f"root AGENTS.md does not reference `{rel}`"


def test_root_agents_md_preserves_hotfix_mode() -> None:
    """ADR-042 §27.3 — §11.5 Hotfix mode protocol preserved verbatim."""
    body = ROOT_AGENTS.read_text(encoding="utf-8")
    assert "Hotfix mode" in body, "root AGENTS.md missing Hotfix Mode section"
    # Spot-check verbatim trigger phrases per §27.3.
    assert "hotfix this" in body
    assert "进入 hotfix 模式" in body
    assert "gate workflow is" in body  # the suspended-during-round clause


# ---------------------------------------------------------------------------
# Pointer files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected_substr",
    sorted((str(p), v) for p, v in POINTER_FILES.items()),
)
def test_pointer_file_exists_and_points_to_agents_md(path: str, expected_substr: str) -> None:
    """ADR-042 §12.1 — pointer files exist and forward to AGENTS.md."""
    p = Path(path)
    assert p.is_file(), f"missing pointer file {p}"
    body = p.read_text(encoding="utf-8").strip()
    assert expected_substr in body, f"{p} does not contain `{expected_substr}` (got `{body}`)"


def test_pointer_files_are_one_line() -> None:
    """Pointer files are 1-line forwarders (ADR-042 §12.1 Windows fallback)."""
    for p in POINTER_FILES:
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 1, f"{p} should be a 1-line pointer (got {len(lines)} non-blank lines)"


# ---------------------------------------------------------------------------
# Per-subtree AGENTS.md
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", sorted(str(p) for p in SUBTREE_AGENTS))
def test_subtree_agents_md_exists(path: str) -> None:
    """ADR-042 §12.2 + ADR-043 §5.3 — every governed subtree has an AGENTS.md."""
    p = Path(path)
    assert p.is_file(), f"missing per-subtree AGENTS.md at {p}"


@pytest.mark.parametrize("path", sorted(str(p) for p in SUBTREE_AGENTS))
def test_subtree_agents_md_has_frontmatter(path: str) -> None:
    """ADR-042 §12.2 — per-subtree AGENTS.md MUST declare frontmatter."""
    p = Path(path)
    body = p.read_text(encoding="utf-8")
    assert body.startswith("---\n"), f"{p} missing YAML frontmatter opener"
    end = body.find("\n---\n", 4)
    assert end > 0, f"{p} missing YAML frontmatter terminator"
    frontmatter = body[4:end]
    for key in ("scope:", "parent_agents_md:", "applies_to_agents:", "governing_adrs:"):
        assert key in frontmatter, f"{p} frontmatter missing `{key}`"


@pytest.mark.parametrize("path", sorted(str(p) for p in SUBTREE_AGENTS))
def test_subtree_agents_md_has_required_sections(path: str) -> None:
    """ADR-043 §5.6 — per-subtree AGENTS.md MUST contain the 7 required sections."""
    p = Path(path)
    body = p.read_text(encoding="utf-8")
    for header in REQUIRED_SECTIONS_SUBTREE:
        pattern = re.compile(rf"^##\s+{re.escape(header)}\b", re.MULTILINE)
        assert pattern.search(body), f"{p} missing `## {header}` section"


@pytest.mark.parametrize("path", sorted(str(p) for p in SUBTREE_AGENTS))
def test_subtree_agents_md_does_not_duplicate_root(path: str) -> None:
    """ADR-042 §12.4 — sub-AGENTS.md MUST NOT duplicate root content.

    Heuristic: no paragraph of ≥10 lines from root AGENTS.md appears verbatim
    in the sub-file. (The Phase 1F `agents-md-lint` hook will do a more
    rigorous text-diff; this test catches whole-section copies.)
    """
    root_body = ROOT_AGENTS.read_text(encoding="utf-8")
    sub_body = Path(path).read_text(encoding="utf-8")

    # Extract paragraphs ≥10 lines from the root body, ignoring the
    # `## Per-subtree AGENTS.md` enumeration block (subtrees may legitimately
    # mention their own path back to the root list).
    paragraphs = [
        block for block in root_body.split("\n\n") if block.count("\n") >= 9 and "Active sub-files" not in block
    ]
    for para in paragraphs:
        stripped = para.strip()
        if not stripped:
            continue
        assert stripped not in sub_body, (
            f"{Path(path).relative_to(REPO)} duplicates a ≥10-line paragraph "
            f"from root AGENTS.md verbatim (ADR-042 §12.4 forbids duplication)."
        )


@pytest.mark.parametrize("path", sorted(str(p) for p in SUBTREE_AGENTS))
def test_subtree_paths_section_uses_tier_markers(path: str) -> None:
    """ADR-043 §6.3 — `## Paths` section uses ✅ / ⚠️ / 🚫 tier markers."""
    body = Path(path).read_text(encoding="utf-8")
    paths_match = re.search(r"^##\s+Paths\b(.*?)(?=^##\s|\Z)", body, re.MULTILINE | re.DOTALL)
    assert paths_match is not None, f"{path} missing `## Paths` section body"
    section_body = paths_match.group(1)
    # At least one tier marker must appear; each sub-file is free to use
    # whichever subset of the three is relevant to its scope.
    has_marker = any(marker in section_body for marker in ("✅", "⚠️", "🚫"))
    assert has_marker, f"{path} `## Paths` section uses none of ✅/⚠️/🚫"
