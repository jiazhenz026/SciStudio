from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.qa.audit._util import load_spec_frontmatter
from scistudio.qa.audit.frontmatter_lint import lint_file
from scistudio.qa.audit.spec_standard import check_spec

_FRONTMATTER = """---
spec_id: sample-standard-two
title: "A sample revision-2 spec"
status: Draft
spec_standard: 2
created: 2026-09-17
input: "Sample"
owners:
  - "@sample"
related_adrs: []
related_specs: []
scope:
  in: []
  out: []
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - src/scistudio/sample/changed.py
    - src/scistudio/sample/gone.py
    - docs/sample.md
  excludes: []
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - src/scistudio/sample/added.py
  excludes: []
tests: []
language_source: en
---
"""

_BODY = """
# Spec: A sample revision-2 spec

## 1. Change Summary

One sentence.

## 2. User Stories

### User Story 1 - Something (Priority: P1)

**Why this priority**: it is first.

**Independent Test**: run it.

**Acceptance Scenarios**:

- **Given** a thing, **When** it happens, **Then** it works.

### Edge Cases

None identified.

## 3. Functional Requirements

| FR | Name | Behavior | ADR decision |
|---|---|---|---|
| FR-001 | First | It does the first thing. | Section 4.1 |
| FR-002 | Second | It does the second thing. | Section 4.2 |

## 4. New Modules

| ID | FR | Module |
|---|---|---|
| NEW-001 | FR-001 | src/scistudio/sample/added.py |

### NEW-001 src/scistudio/sample/added.py

Adds the thing.

## 5. Changed Modules

| ID | FR | Action | Module |
|---|---|---|---|
| CHANGE-001 | FR-002 | modify | src/scistudio/sample/changed.py |

### CHANGE-001 src/scistudio/sample/changed.py

Changes the thing.

## 6. Removed Modules

| ID | FR | Replaced by | Module |
|---|---|---|---|
| DEL-001 | FR-001 | NEW-001 | src/scistudio/sample/gone.py |

### DEL-001 src/scistudio/sample/gone.py

Removes the thing.

## 7. Migration

| ID | FR | From | To | Carrier |
|---|---|---|---|---|
| MIG-001 | FR-001 | The old way | The new way | NEW-001 |

## 8. Public API Changes

| ID | FR | Surface | Change | Compatibility |
|---|---|---|---|---|
| API-000 | FR-001 | None | changed | None |

## 9. Documentation Changes

| ID | FR | Document | Change |
|---|---|---|---|
| DOC-001 | FR-002 | docs/sample.md | Says the new thing. |

## 10. Impact Surface

| Path | IDs | Action |
|---|---|---|
| src/scistudio/sample/added.py | NEW-001 | create |
| docs/sample.md | DOC-001 | modify |
| src/scistudio/sample/changed.py | CHANGE-001 | modify |
| src/scistudio/sample/gone.py | DEL-001 | delete |
"""


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    specs = tmp_path / "docs" / "specs"
    specs.mkdir(parents=True)
    path = specs / "sample.md"
    path.write_text(_FRONTMATTER + _BODY, encoding="utf-8")
    return path


def _check(path: Path, body: str | None = None):
    frontmatter, parsed, findings = load_spec_frontmatter(path)
    assert frontmatter is not None, findings
    return check_spec(path, frontmatter, body if body is not None else parsed, repo_root=path.parents[2])


def test_a_conforming_spec_passes(sample: Path) -> None:
    assert _check(sample) == []


def test_lint_file_runs_the_standard_for_a_declared_spec(sample: Path) -> None:
    assert lint_file(sample) == []


def test_a_spec_without_the_field_is_not_checked(tmp_path: Path) -> None:
    specs = tmp_path / "docs" / "specs"
    specs.mkdir(parents=True)
    path = specs / "legacy.md"
    legacy = _FRONTMATTER.replace("spec_standard: 2\n", "feature_branch: 001-legacy\n")
    legacy = legacy.replace("tests: []\n", "tests: []\nacceptance_source: manual\n")
    # A body that breaks every revision-2 rule, and must still pass.
    path.write_text(legacy + "\n# Legacy\n\n## 1. Change Summary\n\nNo tables at all.\n", encoding="utf-8")
    assert [f for f in lint_file(path) if f.rule_id.startswith("spec-standard.")] == []


@pytest.mark.parametrize(
    ("rule", "old", "new"),
    [
        ("spec-standard.sections", "## 7. Migration", "## 7. Migrations"),
        ("spec-standard.tables", "| ID | FR | Action | Module |", "| ID | FR | Module |"),
        ("spec-standard.numbering", "| FR-002 | Second", "| FR-003 | Second"),
        ("spec-standard.requirement-links", "| NEW-001 | FR-001 |", "| NEW-001 | FR-404 |"),
        ("spec-standard.carrier-links", "| DEL-001 | FR-001 | NEW-001 |", "| DEL-001 | FR-001 | NEW-404 |"),
        ("spec-standard.action-values", "| CHANGE-001 | FR-002 | modify |", "| CHANGE-001 | FR-002 | rewrite |"),
        ("spec-standard.paths", "| DOC-001 | FR-002 | docs/sample.md |", "| DOC-001 | FR-002 | /docs/sample.md |"),
    ],
)
def test_each_structural_break_is_reported(sample: Path, rule: str, old: str, new: str) -> None:
    body = _BODY.replace(old, new, 1)
    assert body != _BODY
    assert rule in {finding.rule_id for finding in _check(sample, body)}


def test_a_detail_subsection_must_follow_its_table_row(sample: Path) -> None:
    body = _BODY.replace(
        "### NEW-001 src/scistudio/sample/added.py", "### NEW-001 src/scistudio/sample/elsewhere.py", 1
    )
    assert "spec-standard.detail-subsections" in {finding.rule_id for finding in _check(sample, body)}


def test_impact_surface_must_match_the_earlier_sections(sample: Path) -> None:
    body = _BODY.replace("| src/scistudio/sample/changed.py | CHANGE-001 | modify |\n", "", 1)
    assert "spec-standard.impact-surface" in {finding.rule_id for finding in _check(sample, body)}


def test_impact_surface_action_must_agree(sample: Path) -> None:
    body = _BODY.replace(
        "| src/scistudio/sample/gone.py | DEL-001 | delete |", "| src/scistudio/sample/gone.py | DEL-001 | modify |", 1
    )
    assert "spec-standard.impact-surface" in {finding.rule_id for finding in _check(sample, body)}


def test_every_impact_path_must_be_governed(sample: Path) -> None:
    body = (
        _BODY.replace(
            "| src/scistudio/sample/changed.py | CHANGE-001 | modify |",
            "| src/scistudio/sample/ungoverned.py | CHANGE-001 | modify |",
            1,
        )
        .replace(
            "| CHANGE-001 | FR-002 | modify | src/scistudio/sample/changed.py |",
            "| CHANGE-001 | FR-002 | modify | src/scistudio/sample/ungoverned.py |",
            1,
        )
        .replace(
            "### CHANGE-001 src/scistudio/sample/changed.py", "### CHANGE-001 src/scistudio/sample/ungoverned.py", 1
        )
    )
    assert "spec-standard.governed-scope" in {finding.rule_id for finding in _check(sample, body)}


def test_the_checks_never_read_the_source_tree(sample: Path) -> None:
    # Every module path in the fixture is invented; structure alone must pass.
    assert not any(Path(part).exists() for part in ("src/scistudio/sample/added.py", "src/scistudio/sample/changed.py"))
    assert _check(sample) == []


def test_the_repository_spec_conforms() -> None:
    path = Path("docs/specs/adr-056-user-code-import.md")
    if not path.is_file():  # pragma: no cover - only when run outside the repo
        pytest.skip("repository spec not present")
    assert [f for f in lint_file(path) if f.rule_id.startswith("spec-standard.")] == []
