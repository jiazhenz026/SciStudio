"""Tests for ``scieasy.qa.audit.frontmatter_lint`` (ADR-042 §5, ADR-044 §5.6).

Covers:

* :func:`select_schema` dispatch on every documented path category.
* :func:`lint_file` valid-frontmatter → empty Finding list.
* :func:`lint_file` malformed YAML → ``yaml-parse`` finding.
* :func:`lint_file` schema violation → per-error finding with structured
  ``rule_id``.
* :func:`lint_file` non-mapping frontmatter → ``non-mapping`` finding.
* :func:`lint_file` missing-frontmatter on a required path.
* :func:`lint_file` permissive fall-through (no schema selected).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scieasy.qa.audit.frontmatter_lint import lint_file, select_schema
from scieasy.qa.docs.schemas import (
    DocGuideFrontmatter,
    ProdAgentDocFrontmatter,
    UserDocFrontmatter,
    WorkflowDocFrontmatter,
)
from scieasy.qa.schemas.frontmatter import ADRFrontmatter, SpecFrontmatter
from scieasy.qa.schemas.report import Severity

# ---------------------------------------------------------------------------
# select_schema dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, expected",
    [
        ("docs/adr/ADR-042.md", ADRFrontmatter),
        ("docs/spec/SPEC-foo.md", SpecFrontmatter),
        ("docs/contributing/workflows/agent-onboarding.md", WorkflowDocFrontmatter),
        ("docs/user/getting-started.md", UserDocFrontmatter),
        ("docs/prod/agent/registry.md", ProdAgentDocFrontmatter),
        ("docs/guides/install.md", DocGuideFrontmatter),
        ("docs/contributing/onboarding.md", None),  # permissive fall-through (Q1B.2.2)
        ("docs/random.md", None),
        ("README.md", None),
    ],
)
def test_select_schema_dispatches(path: str, expected: type | None) -> None:
    result = select_schema(Path(path))
    assert result is expected


def test_select_schema_skips_template_directory() -> None:
    """Template files contain pseudo-frontmatter that should not validate."""
    assert select_schema(Path("docs/adr/_template/ADR-template.md")) is None


# ---------------------------------------------------------------------------
# lint_file — happy path
# ---------------------------------------------------------------------------


VALID_ADR = """---
adr: 99
title: "Valid Test ADR"
status: Draft
date_created: 2026-05-18
is_code_implementation: false
governs:
  modules: []
  files: []
tests: []
agent_editable: "false"
owner: "@you"
---

# Body
"""


def test_lint_file_valid_adr_no_findings(tmp_path: Path) -> None:
    f = tmp_path / "docs" / "adr" / "ADR-099.md"
    f.parent.mkdir(parents=True)
    f.write_text(VALID_ADR)
    assert lint_file(f, repo_root=tmp_path) == []


def test_lint_file_permissive_path_no_findings(tmp_path: Path) -> None:
    """A frontmatter-less file in a permissive directory should not error."""
    f = tmp_path / "docs" / "contributing" / "onboarding.md"
    f.parent.mkdir(parents=True)
    f.write_text("# Onboarding\n\nNo frontmatter here.\n")
    assert lint_file(f, repo_root=tmp_path) == []


# ---------------------------------------------------------------------------
# lint_file — error paths
# ---------------------------------------------------------------------------


def test_lint_file_missing_file(tmp_path: Path) -> None:
    findings = lint_file(tmp_path / "docs" / "adr" / "ADR-999.md", repo_root=tmp_path)
    assert any(f.rule_id == "frontmatter-lint.missing-file" for f in findings)


def test_lint_file_required_path_missing_frontmatter(tmp_path: Path) -> None:
    f = tmp_path / "docs" / "adr" / "ADR-099.md"
    f.parent.mkdir(parents=True)
    f.write_text("# ADR-99 with no frontmatter\n")
    findings = lint_file(f, repo_root=tmp_path)
    assert any(f.rule_id == "frontmatter-lint.missing-frontmatter" for f in findings)


def test_lint_file_malformed_yaml(tmp_path: Path) -> None:
    f = tmp_path / "docs" / "adr" / "ADR-099.md"
    f.parent.mkdir(parents=True)
    f.write_text("---\nadr: [unclosed\n---\n# Body\n")
    findings = lint_file(f, repo_root=tmp_path)
    assert any(f.rule_id == "frontmatter-lint.yaml-parse" for f in findings)


def test_lint_file_non_mapping_frontmatter(tmp_path: Path) -> None:
    f = tmp_path / "docs" / "adr" / "ADR-099.md"
    f.parent.mkdir(parents=True)
    f.write_text("---\n- list_item\n- another_item\n---\n# Body\n")
    findings = lint_file(f, repo_root=tmp_path)
    assert any(f.rule_id == "frontmatter-lint.non-mapping" for f in findings)


def test_lint_file_validation_error(tmp_path: Path) -> None:
    """Missing required field → one ValidationError finding per missing field."""
    f = tmp_path / "docs" / "adr" / "ADR-099.md"
    f.parent.mkdir(parents=True)
    f.write_text('---\nadr: 99\ntitle: "Missing many fields"\n---\n# Body\n')
    findings = lint_file(f, repo_root=tmp_path)
    assert findings
    assert all(f.severity == Severity.ERROR for f in findings)
    # At least one finding should reference status or governs (required fields).
    assert any("status" in f.message or "governs" in f.message for f in findings)


def test_lint_file_extra_field_rejected(tmp_path: Path) -> None:
    """extra='forbid' on the schema must surface as findings."""
    body = VALID_ADR.replace("---\n\n# Body", "rogue_extra: yes\n---\n\n# Body")
    f = tmp_path / "docs" / "adr" / "ADR-099.md"
    f.parent.mkdir(parents=True)
    f.write_text(body)
    findings = lint_file(f, repo_root=tmp_path)
    assert any("rogue_extra" in f.message for f in findings)


def test_lint_file_no_closing_delimiter(tmp_path: Path) -> None:
    """A file starting with --- but never closing is treated as no-frontmatter."""
    f = tmp_path / "docs" / "contributing" / "onboarding.md"
    f.parent.mkdir(parents=True)
    f.write_text("---\nadr: 99\n# no closing fence\n")
    # No closing → not a frontmatter block; permissive location → empty list.
    assert lint_file(f, repo_root=tmp_path) == []


def test_lint_file_permissive_docs_with_frontmatter(tmp_path: Path) -> None:
    """A permissive doc with frontmatter still parses but no schema check."""
    f = tmp_path / "docs" / "contributing" / "onboarding.md"
    f.parent.mkdir(parents=True)
    f.write_text("---\nany: yaml\nshape: ok\n---\n# Body\n")
    assert lint_file(f, repo_root=tmp_path) == []


def test_select_schema_relative_to_root() -> None:
    """select_schema works with a Path that is already relative."""
    assert select_schema(Path("docs") / "adr" / "ADR-042.md") is ADRFrontmatter


def test_select_schema_path_outside_repo_root(tmp_path: Path) -> None:
    """A path outside repo_root falls back to its absolute form (line 203-204)."""
    other = tmp_path.parent / "outside_repo.md"
    other.touch()
    # Should not raise even though path is outside repo_root.
    assert select_schema(other, repo_root=tmp_path) is None
    other.unlink()


def test_format_validation_error_no_location() -> None:
    """Validation errors without a `loc` render the message verbatim."""
    from scieasy.qa.audit.frontmatter_lint import _format_validation_error

    out = _format_validation_error({"loc": (), "msg": "bare error"})
    assert out == "bare error"


def test_lint_file_docs_root_no_schema(tmp_path: Path) -> None:
    """A bare ``docs/foo.md`` (no subdir) falls through to permissive."""
    f = tmp_path / "docs" / "foo.md"
    f.parent.mkdir(parents=True)
    f.write_text("# bare\n")
    assert lint_file(f, repo_root=tmp_path) == []
