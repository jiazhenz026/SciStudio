"""Tests for ``scieasy.qa.audit.complete_artifacts`` (ADR-042 §19.2 stage 6)."""

from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit.complete_artifacts import check
from scieasy.qa.schemas.report import Severity


def _minimal_repo(tmp_path: Path) -> Path:
    """A repo with the absolute minimum scaffolding: empty package, MAINTAINERS."""
    pkg = tmp_path / "src" / "myproj"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('"""Hello."""\n', encoding="utf-8")
    (tmp_path / "MAINTAINERS").write_text(
        "entries: []\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    return tmp_path


def test_check_emits_placeholders_without_pr_number(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    findings = check(tmp_path)
    rule_ids = {f.rule_id for f in findings}
    # All four placeholders surface.
    assert "complete-artifacts.translation-placeholder" in rule_ids
    assert "complete-artifacts.codemod-placeholder" in rule_ids
    assert "complete-artifacts.rbp-placeholder" in rule_ids
    assert "complete-artifacts.skills-placeholder" in rule_ids
    # Without pr_number the CHANGELOG check is INFO (skipped).
    skipped = [f for f in findings if f.rule_id == "complete-artifacts.changelog-skipped"]
    assert skipped and skipped[0].severity == Severity.INFO


def test_check_with_pr_number_requires_changelog_entry(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    # No CHANGELOG at all → 'changelog-missing'.
    findings = check(tmp_path, pr_number=42)
    rule_ids = {f.rule_id for f in findings}
    assert "complete-artifacts.changelog-missing" in rule_ids


def test_check_changelog_present_but_no_entry(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n", encoding="utf-8")
    findings = check(tmp_path, pr_number=42)
    assert any(f.rule_id == "complete-artifacts.changelog-no-entry" for f in findings)


def test_check_changelog_with_entry_passes(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n- [#42] something\n", encoding="utf-8")
    findings = check(tmp_path, pr_number=42)
    rule_ids = {f.rule_id for f in findings}
    assert "complete-artifacts.changelog-no-entry" not in rule_ids
    assert "complete-artifacts.changelog-missing" not in rule_ids


def test_filter_to_diff_keeps_placeholders_and_matched(tmp_path: Path) -> None:
    from scieasy.qa.audit.complete_artifacts import _filter_to_diff
    from scieasy.qa.schemas.report import Finding, Severity

    findings = [
        Finding(rule_id="x.pl", severity=Severity.INFO, file="<PR body>", message="m"),
        Finding(rule_id="x.kept", severity=Severity.INFO, file="src/a.py", message="m"),
        Finding(rule_id="x.parent", severity=Severity.INFO, file="src", message="m"),
        Finding(rule_id="x.dropped", severity=Severity.INFO, file="src/b.py", message="m"),
    ]
    kept = _filter_to_diff(findings, {"src/a.py"})
    ids = {f.rule_id for f in kept}
    assert "x.pl" in ids and "x.kept" in ids and "x.parent" in ids and "x.dropped" not in ids


def test_check_with_pr_number_invokes_diff_filter(tmp_path: Path) -> None:
    """End-to-end: pr_number + git diff produces a filtered findings list."""
    import subprocess

    _minimal_repo(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.org"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n- [#42] x\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    # No origin/main → diff returns empty; the filter falls back to no-op.
    findings = check(tmp_path, pr_number=42)
    assert isinstance(findings, list)


def test_check_accepts_issue_reference_as_proxy(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n- closes issue #99\n", encoding="utf-8")
    findings = check(tmp_path, pr_number=99)
    assert not any(f.rule_id == "complete-artifacts.changelog-no-entry" for f in findings)
