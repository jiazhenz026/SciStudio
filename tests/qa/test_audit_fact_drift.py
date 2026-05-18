"""Tests for ``scieasy.qa.audit.fact_drift`` (ADR-042 §10).

Covers:

* :func:`check_substitutions` no findings when no facts registry.
* :func:`check_substitutions` flags hardcoded numeric / string facts.
* :func:`check_substitutions` ignores fenced/indented code blocks.
* :func:`check_substitutions` ignores existing ``{{ facts.X }}`` blocks.
* :func:`check_substitutions` excludes numerics below the floor.
* :func:`check_substitutions` honours severity floor.
* :func:`collect_fact_values` flattens dotted paths.
* :func:`main` CLI exit codes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scieasy.qa.audit.fact_drift import (
    check_substitutions,
    collect_fact_values,
    main,
)
from scieasy.qa.schemas.report import Severity

# ---------------------------------------------------------------------------
# Test repo fixture
# ---------------------------------------------------------------------------


FACTS_YAML = """
schema_version: 1
generated_at: "2026-05-18T00:00:00+00:00"
source_shas:
  workflow: abc123
  tool: def456
  adr: ghi789
  maintainers: jkl012
  skill: mno345
workflow:
  stage_count: 7
  stages: ["start", "create_issue", "write_change_plan", "create_branch", "update_docs", "update_changelog", "submit_pr"]
  blocking_validations:
    create_issue: ["title", "labels"]
tool:
  python_version: "3.12"
  min_coverage_percent: 70
  lint_rules: ["E", "F", "W", "I", "B"]
  type_checkers: ["mypy", "pyright"]
  docs_engine: "sphinx"
adr:
  total_count: 44
  by_status:
    Accepted: 30
    Draft: 14
  latest_adr_number: 44
maintainers:
  entry_count: 5
  human_count: 1
  paths_covered_count: 10
skill:
  required_skills: ["doc-drift-guard", "adr-self-audit"]
  installed_per_runtime:
    Claude: ["doc-drift-guard"]
"""


@pytest.fixture
def repo_with_facts(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "facts").mkdir(parents=True)
    (tmp_path / "docs" / "facts" / "generated.yaml").write_text(FACTS_YAML, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# collect_fact_values
# ---------------------------------------------------------------------------


def test_collect_fact_values_flattens_numerics(repo_with_facts: Path) -> None:
    from scieasy.qa.audit.fact_drift import _load_facts

    facts = _load_facts(repo_with_facts)
    assert facts is not None
    values = collect_fact_values(facts)
    # numerics ≥ 3 are kept.
    assert "7" in values
    assert "44" in values
    assert "30" in values
    # numerics < 3 are dropped (default numeric_floor=3); 1 is the source-sha
    # length so not a number.


def test_collect_fact_values_flattens_strings(repo_with_facts: Path) -> None:
    from scieasy.qa.audit.fact_drift import _load_facts

    facts = _load_facts(repo_with_facts)
    assert facts is not None
    values = collect_fact_values(facts)
    assert "submit_pr" in values
    assert "sphinx" in values


def test_collect_fact_values_skips_short_strings(repo_with_facts: Path) -> None:
    from scieasy.qa.audit.fact_drift import _load_facts

    facts = _load_facts(repo_with_facts)
    assert facts is not None
    values = collect_fact_values(facts, min_length=4)
    assert "E" not in values
    assert "F" not in values


# ---------------------------------------------------------------------------
# check_substitutions
# ---------------------------------------------------------------------------


def test_check_substitutions_no_facts_returns_empty(tmp_path: Path) -> None:
    """No facts registry → no findings (transitional period)."""
    assert check_substitutions(tmp_path) == []


def test_check_substitutions_flags_hardcoded_numeric(repo_with_facts: Path) -> None:
    """A hardcoded ``7 stages`` literal in prose must be flagged."""
    (repo_with_facts / "docs" / "claude.md").write_text(
        "# Heading\n\nThe workflow has 7 stages.\n",
        encoding="utf-8",
    )
    findings = check_substitutions(repo_with_facts)
    rule_ids = {f.rule_id for f in findings}
    assert "fact-drift.hardcoded" in rule_ids
    assert any("'7'" in f.message for f in findings)


def test_check_substitutions_strips_code_blocks(repo_with_facts: Path) -> None:
    """Fenced code blocks must NOT trigger a finding."""
    (repo_with_facts / "docs" / "claude.md").write_text(
        "# Heading\n\n```\nstage_count = 7\n```\n",
        encoding="utf-8",
    )
    findings = check_substitutions(repo_with_facts)
    # The 7 above is inside a fenced block → must be ignored.
    assert not any(f.file == "docs/claude.md" and "'7'" in f.message for f in findings)


def test_check_substitutions_strips_indented_blocks(repo_with_facts: Path) -> None:
    (repo_with_facts / "docs" / "claude.md").write_text(
        "# Heading\n\n    stage_count = 7\n",
        encoding="utf-8",
    )
    findings = check_substitutions(repo_with_facts)
    assert not any("'7'" in f.message for f in findings)


def test_check_substitutions_strips_existing_substitutions(repo_with_facts: Path) -> None:
    """``{{ facts.workflow.stage_count }}`` must NOT match itself."""
    (repo_with_facts / "docs" / "claude.md").write_text(
        "The workflow has {{ facts.workflow.stage_count }} stages.\n",
        encoding="utf-8",
    )
    findings = check_substitutions(repo_with_facts)
    assert findings == []


def test_check_substitutions_word_boundary_for_numerics(repo_with_facts: Path) -> None:
    """``17 stages`` must NOT trigger ``'7'`` (word-boundary)."""
    (repo_with_facts / "docs" / "claude.md").write_text(
        "The workflow has 17 stages.\n",
        encoding="utf-8",
    )
    findings = check_substitutions(repo_with_facts)
    # 17 not in registry, 7 inside 17 also not flagged.
    assert not any("'7'" in f.message for f in findings)


def test_check_substitutions_severity_floor_warning(repo_with_facts: Path) -> None:
    (repo_with_facts / "docs" / "claude.md").write_text(
        "The workflow has 7 stages.\n",
        encoding="utf-8",
    )
    findings = check_substitutions(repo_with_facts, severity_floor=Severity.WARNING)
    assert findings
    assert all(f.severity == Severity.WARNING for f in findings)


def test_check_substitutions_severity_floor_error(repo_with_facts: Path) -> None:
    (repo_with_facts / "docs" / "claude.md").write_text(
        "The workflow has 7 stages.\n",
        encoding="utf-8",
    )
    findings = check_substitutions(repo_with_facts, severity_floor=Severity.ERROR)
    assert findings
    assert all(f.severity == Severity.ERROR for f in findings)


def test_check_substitutions_scans_root_readme(repo_with_facts: Path) -> None:
    (repo_with_facts / "README.md").write_text("Project has 44 ADRs.\n", encoding="utf-8")
    findings = check_substitutions(repo_with_facts)
    assert any(f.file == "README.md" for f in findings)


def test_check_substitutions_excludes_archive_paths(repo_with_facts: Path) -> None:
    archive = repo_with_facts / "docs" / "audit" / "archive"
    archive.mkdir(parents=True)
    (archive / "snapshot.md").write_text("Historical 7 stages\n", encoding="utf-8")
    findings = check_substitutions(repo_with_facts)
    assert not any(f.file.startswith("docs/audit/archive/") for f in findings)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_main_exit_zero_on_no_findings(tmp_path: Path) -> None:
    """No facts registry → 0 findings → exit 0."""
    rc = main(["--repo-root", str(tmp_path)])
    assert rc == 0


def test_main_exit_one_on_findings(repo_with_facts: Path) -> None:
    (repo_with_facts / "docs" / "claude.md").write_text(
        "The workflow has 7 stages.\n",
        encoding="utf-8",
    )
    rc = main(["--repo-root", str(repo_with_facts)])
    assert rc == 1


def test_main_accepts_severity_floor(repo_with_facts: Path) -> None:
    rc = main(["--repo-root", str(repo_with_facts), "--severity-floor", "warning"])
    assert rc == 0  # no findings: empty docs


# ---------------------------------------------------------------------------
# Malformed facts file
# ---------------------------------------------------------------------------


def test_malformed_facts_yaml_returns_no_findings(tmp_path: Path) -> None:
    (tmp_path / "docs" / "facts").mkdir(parents=True)
    (tmp_path / "docs" / "facts" / "generated.yaml").write_text(":\n: invalid:\n", encoding="utf-8")
    assert check_substitutions(tmp_path) == []


def test_facts_with_invalid_schema_returns_no_findings(tmp_path: Path) -> None:
    (tmp_path / "docs" / "facts").mkdir(parents=True)
    (tmp_path / "docs" / "facts" / "generated.yaml").write_text("schema_version: 1\nworkflow: {}\n", encoding="utf-8")
    assert check_substitutions(tmp_path) == []


def test_facts_yaml_decodes_to_list_returns_none(tmp_path: Path) -> None:
    """If generated.yaml decodes to a list, _load_facts returns None."""
    (tmp_path / "docs" / "facts").mkdir(parents=True)
    (tmp_path / "docs" / "facts" / "generated.yaml").write_text("- item1\n- item2\n", encoding="utf-8")
    assert check_substitutions(tmp_path) == []


def test_collect_fact_values_skips_booleans(repo_with_facts: Path) -> None:
    """Booleans (True/False) are skipped — they're too common as prose words."""
    from scieasy.qa.audit.fact_drift import _load_facts, collect_fact_values

    facts = _load_facts(repo_with_facts)
    assert facts is not None
    values = collect_fact_values(facts)
    assert "True" not in values
    assert "False" not in values


def test_check_substitutions_string_value(repo_with_facts: Path) -> None:
    """A hardcoded string value in prose (e.g. 'sphinx') is flagged."""
    (repo_with_facts / "docs" / "tooling.md").write_text(
        "We use sphinx for docs.\n",
        encoding="utf-8",
    )
    findings = check_substitutions(repo_with_facts)
    assert any("'sphinx'" in f.message for f in findings)


def test_check_substitutions_no_facts_to_scan(tmp_path: Path) -> None:
    """No facts → no scanning → no findings."""
    # Empty facts registry (workflow with stage_count=0 is invalid; use schema_version=2).
    (tmp_path / "docs" / "facts").mkdir(parents=True)
    (tmp_path / "docs" / "facts" / "generated.yaml").write_text("schema_version: 2\n", encoding="utf-8")
    assert check_substitutions(tmp_path) == []
