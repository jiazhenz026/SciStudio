from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scieasy.qa.governance import mod_guard
from scieasy.qa.schemas.report import AuditStatus


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True)


def _write(repo: Path, path: str, content: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "agent@example.com")
    _git(repo, "config", "user.name", "Agent")
    _write(repo, "README.md", "hello\n")
    _write(repo, ".pre-commit-config.yaml", "repos: []\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_mod_guard_passes_for_unprotected_staged_change(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write(repo, "docs/user/guide.md", "safe\n")
    _git(repo, "add", ".")

    report = mod_guard.check(repo, staged=True)

    assert report.status == AuditStatus.PASS
    assert report.summary["changed_protected_files"] == []


def test_mod_guard_blocks_protected_staged_change_without_approval(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write(repo, ".pre-commit-config.yaml", "repos:\n  - repo: local\n")
    _git(repo, "add", ".")

    report = mod_guard.check(repo, staged=True)

    assert report.status == AuditStatus.FAIL
    assert [finding.file for finding in report.findings] == [".pre-commit-config.yaml"]


def test_mod_guard_allows_gate_record_without_approval(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write(repo, ".workflow/records/123-example.json", "{}\n")
    _git(repo, "add", ".")

    report = mod_guard.check(repo, staged=True)

    assert report.status == AuditStatus.PASS
    assert report.summary["changed_protected_files"] == []


def test_mod_guard_still_blocks_non_record_workflow_change_without_approval(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write(repo, ".workflow/gate-record.schema.json", "{}\n")
    _git(repo, "add", ".")

    report = mod_guard.check(repo, staged=True)

    assert report.status == AuditStatus.FAIL
    assert [finding.file for finding in report.findings] == [".workflow/gate-record.schema.json"]


def test_mod_guard_allows_protected_change_with_explicit_flag(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write(repo, "src/scieasy/qa/governance/mod_guard.py", "print('changed')\n")
    _git(repo, "add", ".")

    report = mod_guard.check(repo, staged=True, allow_governance_change=True)

    assert report.status == AuditStatus.PASS
    assert report.summary["changed_protected_files"] == ["src/scieasy/qa/governance/mod_guard.py"]


def test_mod_guard_allows_protected_change_with_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_repo(tmp_path)
    _write(repo, "tests/qa/test_example.py", "def test_example():\n    assert True\n")
    _git(repo, "add", ".")
    monkeypatch.setenv(mod_guard.APPROVAL_ENV, "1")

    report = mod_guard.check(repo, staged=True)

    assert report.status == AuditStatus.PASS
    assert os.environ[mod_guard.APPROVAL_ENV] == "1"


def test_mod_guard_accepts_adr042_local_bypass_labels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _init_repo(tmp_path)
    _write(repo, ".pre-commit-config.yaml", "repos:\n  - repo: local\n")
    _git(repo, "add", ".")
    monkeypatch.setenv("SCIEASY_GATE_BYPASS_LABELS", "admin-approved:ai-override")

    report = mod_guard.check(repo, staged=True)

    assert report.status == AuditStatus.PASS
    assert report.summary["bypassed"] is True


def test_mod_guard_rejects_invalid_adr042_local_bypass_label(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _init_repo(tmp_path)
    _write(repo, ".pre-commit-config.yaml", "repos:\n  - repo: local\n")
    _git(repo, "add", ".")
    monkeypatch.setenv("SCIEASY_GATE_BYPASS_LABELS", "admin-approved-core-change")

    report = mod_guard.check(repo, staged=True)

    assert report.status == AuditStatus.FAIL
    assert "governance.mod_guard.invalid-override-label" in {finding.rule_id for finding in report.findings}
