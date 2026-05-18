"""Tests for ``scieasy.qa.audit.committer_enforce`` (ADR-042 §16).

Covers:

* No commit-log → INFO finding, no error.
* Empty commit-log → INFO finding, no error.
* Malformed JSON line → ERROR finding.
* Agent commit absent from log → ``missing-log-entry`` ERROR.
* Agent commit present in log → no findings.
* :func:`load_commit_log` validates :class:`CommitLogEntry` shape.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scieasy.qa.audit.committer_enforce import (
    LOG_PATH_REL,
    check,
    load_commit_log,
)
from scieasy.qa.schemas.report import Severity


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "claude@example.org"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Claude"], cwd=path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True)


def _commit(path: Path, message: str) -> str:
    (path / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=path, check=True)
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_check_returns_info_when_log_missing(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "feat: x\n\nAssisted-by: Claude:claude-opus-4-7")
    findings = check(tmp_path)
    assert len(findings) == 1
    assert findings[0].rule_id == "committer-enforce.no-log-file"
    assert findings[0].severity == Severity.INFO


def test_check_returns_info_when_log_empty(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "feat: x\n\nAssisted-by: Claude:claude-opus-4-7")
    (tmp_path / "docs" / "audit").mkdir(parents=True)
    (tmp_path / LOG_PATH_REL).write_text("", encoding="utf-8")
    findings = check(tmp_path)
    assert any(f.rule_id == "committer-enforce.empty-log" for f in findings)


def test_check_finds_missing_log_entry(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    sha = _commit(tmp_path, "feat: x\n\nAssisted-by: Claude:claude-opus-4-7")
    # Log file exists with an unrelated commit
    (tmp_path / "docs" / "audit").mkdir(parents=True)
    log = (
        json.dumps(
            {
                "sha": "0123456789abcdef0123456789abcdef01234567",
                "timestamp": "2026-05-17T12:34:56Z",
                "author": "@other",
                "runtime": "Claude",
                "model": "claude-opus-4-7",
                "files": ["docs/README.md"],
                "message_first_line": "feat: other",
            }
        )
        + "\n"
    )
    (tmp_path / LOG_PATH_REL).write_text(log, encoding="utf-8")
    findings = check(tmp_path)
    matching = [f for f in findings if f.rule_id == "committer-enforce.missing-log-entry"]
    assert matching
    assert sha[:7] in matching[0].message


def test_check_passes_when_log_includes_commit(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    sha = _commit(tmp_path, "feat: x\n\nAssisted-by: Claude:claude-opus-4-7")
    (tmp_path / "docs" / "audit").mkdir(parents=True)
    log = (
        json.dumps(
            {
                "sha": sha,
                "timestamp": "2026-05-17T12:34:56Z",
                "author": "@claude",
                "runtime": "Claude",
                "model": "claude-opus-4-7",
                "files": ["README.md"],
                "message_first_line": "feat: x",
            }
        )
        + "\n"
    )
    (tmp_path / LOG_PATH_REL).write_text(log, encoding="utf-8")
    findings = check(tmp_path)
    assert not [f for f in findings if f.rule_id == "committer-enforce.missing-log-entry"]


def test_check_reports_malformed_log(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "feat: x\n\nAssisted-by: Claude:claude-opus-4-7")
    (tmp_path / "docs" / "audit").mkdir(parents=True)
    (tmp_path / LOG_PATH_REL).write_text("not-json\n", encoding="utf-8")
    findings = check(tmp_path)
    assert any(f.rule_id == "committer-enforce.malformed-log" for f in findings)


def test_load_commit_log_validates_shape(tmp_path: Path) -> None:
    path = tmp_path / "commit-log.jsonl"
    entry = {
        "sha": "abc1234",
        "timestamp": "2026-05-17T12:34:56Z",
        "author": "@claude",
        "runtime": "Claude",
        "model": "claude-opus-4-7",
        "files": ["x.py"],
        "message_first_line": "feat: x",
    }
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    entries = load_commit_log(path)
    assert len(entries) == 1
    assert entries[0].sha == "abc1234"


def test_load_commit_log_rejects_invalid_field(tmp_path: Path) -> None:
    path = tmp_path / "commit-log.jsonl"
    # Bad sha pattern.
    bad = {
        "sha": "NOT-HEX",
        "timestamp": "2026-05-17T12:34:56Z",
        "author": "@claude",
        "runtime": "Claude",
        "model": "claude-opus-4-7",
        "files": [],
        "message_first_line": "x",
    }
    path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_commit_log(path)


def test_load_commit_log_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "commit-log.jsonl"
    path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_commit_log(path)
