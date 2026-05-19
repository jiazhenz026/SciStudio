"""Tests for `test_quality.ast_lint` anti-pattern detection."""

from __future__ import annotations

from pathlib import Path

from scieasy.qa.test_quality.ast_lint import check_test_file


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _findings_by_class(report, rule: str):
    return [item for item in report.findings if item.finding_class == rule]


def test_ast_lint_detects_empty_assertion(tmp_path: Path) -> None:
    path = tmp_path / "tests" / "test_empty.py"
    _write(path, "def test_noop():\n    assert True\n")
    report = check_test_file(path)
    assert "empty-assertion" in [item.finding_class for item in report.findings]
    assert report.status == "failed"


def test_ast_lint_detects_snapshot_only_warning(tmp_path: Path) -> None:
    path = tmp_path / "tests" / "test_snapshot.py"
    _write(
        path,
        (
            "from unittest.mock import Mock\n\n"
            "def test_snapshot():\n"
            "    result = Mock()\n"
            "    assert result.match_snapshot()\n"
        ),
    )
    report = check_test_file(path)
    assert "snapshot-only" in {item.finding_class for item in report.findings}


def test_ast_lint_detects_mocked_away_behavior(tmp_path: Path) -> None:
    path = tmp_path / "tests" / "test_mocked.py"
    _write(
        path,
        (
            "from unittest.mock import patch\n\n"
            "def test_mocked_away():\n"
            "    with patch('pkg.fn') as mock_fn:\n"
            "        mock_fn()\n"
            "    assert mock_fn\n"
        ),
    )
    report = check_test_file(path)
    assert "mocked-away-behavior" in {item.finding_class for item in report.findings}
    assert report.status == "failed"


def test_ast_lint_detects_broad_exception_and_untracked_skip(tmp_path: Path) -> None:
    path = tmp_path / "tests" / "test_broad_and_skip.py"
    _write(
        path,
        (
            "import pytest\n\n"
            "def test_broad():\n"
            "    try:\n"
            "        1 / 0\n"
            "    except:\n"
            "        pass\n\n"
            "@pytest.mark.skip\n"
            "def test_skipped():\n"
            "    assert True\n"
        ),
    )
    report = check_test_file(path)
    assert _findings_by_class(report, "broad-exception")
    assert _findings_by_class(report, "untracked-skip")

    tracked_path = tmp_path / "tests" / "test_tracked_skip.py"
    _write(
        tracked_path,
        ("import pytest\n\n@pytest.mark.skip(reason='tracked in GH-123')\ndef test_tracked_skip():\n    assert True\n"),
    )
    tracked_report = check_test_file(tracked_path)
    assert "untracked-skip" not in {item.finding_class for item in tracked_report.findings}
