"""Tests for the vulture dead-code child report (#1340)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scistudio.qa.audit import vulture_audit
from scistudio.qa.audit.vulture_audit import check, main
from scistudio.qa.schemas.report import AuditStatus, Severity


def test_check_reports_skipped_when_vulture_not_importable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vulture_audit, "_vulture_available", lambda: False)

    report = check(tmp_path)

    assert report.status == AuditStatus.SKIPPED
    assert not report.blocks_merge
    assert [finding.rule_id for finding in report.findings] == ["vulture.unavailable"]
    assert report.findings[0].severity == Severity.INFO
    assert report.summary["vulture_available"] is False


def test_check_returns_pass_with_zero_findings_when_no_targets_resolve(tmp_path: Path) -> None:
    report = check(tmp_path, paths=("nonexistent_subdir",), allowlist=None)

    assert report.status == AuditStatus.PASS
    assert not report.blocks_merge
    assert report.findings == []
    assert report.summary["targets_resolved"] == 0
    assert report.summary["vulture_available"] is True


def test_check_emits_warning_findings_for_dead_code(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "dead.py").write_text(
        textwrap.dedent(
            """
            def never_called():
                return 42

            UNUSED_CONSTANT = 7
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    report = check(tmp_path, paths=("pkg",), allowlist=None, min_confidence=60)

    assert report.status == AuditStatus.PASS
    assert not report.blocks_merge, "vulture child report must never block merge in v1 (#1340)"
    assert report.findings, "expected at least one dead-code finding for never_called or UNUSED_CONSTANT"
    for finding in report.findings:
        assert finding.severity == Severity.WARNING
        assert finding.rule_id == "vulture.dead-code"
        assert "confidence" in finding.evidence
    assert report.summary["total_findings"] == len(report.findings)
    assert report.summary["targets_resolved"] == 1


def test_check_uses_allowlist_to_suppress_known_intentional_names(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "lib.py").write_text(
        "def keep_me_callback():\n    return 1\n",
        encoding="utf-8",
    )
    allowlist = tmp_path / "vulture_allowlist.py"
    allowlist.write_text(
        textwrap.dedent(
            """
            _ = None
            _.keep_me_callback  # noqa: F821
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    report = check(tmp_path, paths=("pkg",), allowlist=allowlist, min_confidence=60)

    assert report.status == AuditStatus.PASS
    assert not any("keep_me_callback" in finding.message for finding in report.findings)
    assert report.summary["allowlist"] == "vulture_allowlist.py"


def test_main_returns_zero_when_only_warnings_are_emitted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "dead.py").write_text("def unused():\n    return 1\n", encoding="utf-8")

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--path",
            "pkg",
            "--min-confidence",
            "60",
            "--format",
            "text",
        ]
    )

    out = capsys.readouterr().out
    assert exit_code == 0, "vulture child report must not exit non-zero on WARNING-only findings"
    assert "vulture:" in out


def test_main_returns_zero_when_vulture_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(vulture_audit, "_vulture_available", lambda: False)

    exit_code = main(["--repo-root", str(tmp_path), "--format", "text"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "skipped" in out
