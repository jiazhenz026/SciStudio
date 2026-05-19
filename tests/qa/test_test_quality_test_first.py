"""Tests for `test_quality.test_first_check` ordering proof."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scieasy.qa.test_quality.test_first_check import verify_ordering


def _init_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=str(repo_root), check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "qa@example.com"], cwd=str(repo_root), check=True)
    subprocess.run(["git", "config", "user.name", "qa"], cwd=str(repo_root), check=True)


def _commit_all(repo_root: Path, message: str) -> str:
    subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=str(repo_root), check=True, capture_output=True, text=True)
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_root), capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_required_false_is_not_required_even_for_code_changes(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write(tmp_path / "pkg" / "core.py", "VALUE = 1\n")
    base = _commit_all(tmp_path, "base")

    _write(tmp_path / "pkg" / "core.py", "VALUE = 2\n")
    _commit_all(tmp_path, "change")

    report = verify_ordering(tmp_path, base_ref=base, head_ref="HEAD", required=False)
    assert report.status == "passed"
    assert report.summary["required"] is False
    assert report.summary["not_required"] is True


def test_required_fails_when_code_has_no_test_changes(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write(tmp_path / "pkg" / "core.py", "VALUE = 1\n")
    base = _commit_all(tmp_path, "base")

    _write(tmp_path / "pkg" / "core.py", "VALUE = 2\n")
    _commit_all(tmp_path, "change")

    report = verify_ordering(tmp_path, base_ref=base, head_ref="HEAD", required=True)
    assert report.status == "failed"
    assert report.findings
    assert report.findings[0].finding_class == "test-first-missing"


def test_required_passes_when_code_and_test_both_change(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write(tmp_path / "pkg" / "core.py", "VALUE = 1\n")
    base = _commit_all(tmp_path, "base")

    _write(tmp_path / "pkg" / "core.py", "VALUE = 2\n")
    _write(tmp_path / "tests" / "test_core.py", "def test_core():\n    assert True\n")
    _commit_all(tmp_path, "change")

    report = verify_ordering(tmp_path, base_ref=base, head_ref="HEAD", required=True)
    assert report.status == "passed"
    assert report.summary["changed_test_count"] == 1
