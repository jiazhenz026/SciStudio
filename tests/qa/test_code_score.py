"""Tests for ADR-042 code scoring APIs."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from scieasy.qa import code_score
from scieasy.qa.code_score import AIAdvisoryInput, AIAdvisoryScore


def _init_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=str(repo_root), check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "qa@example.com"], cwd=str(repo_root), check=True)
    subprocess.run(["git", "config", "user.name", "qa"], cwd=str(repo_root), check=True)


def _commit_all(repo_root: Path, message: str) -> str:
    subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=str(repo_root), check=True, capture_output=True, text=True)
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_root), capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_changed_modules_excludes_tests(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_text(tmp_path / "pkg" / "core.py", "VALUE = 1\n")
    base = _commit_all(tmp_path, "base")

    _write_text(tmp_path / "pkg" / "core.py", "VALUE = 2\n")
    _write_text(tmp_path / "tests" / "test_core.py", "def test_ok():\n    assert True\n")
    _commit_all(tmp_path, "change")

    changed = code_score.changed_modules(tmp_path, base_ref=base, head_ref="HEAD")
    assert changed == ["pkg/core.py"]


def test_score_changed_modules_flags_syntax_error(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_text(tmp_path / "pkg" / "bad.py", "VALUE = 1\n")
    base = _commit_all(tmp_path, "base")

    _write_text(tmp_path / "pkg" / "bad.py", "def x(:\n    pass\n")
    _commit_all(tmp_path, "broken")

    report = code_score.score_changed_modules(tmp_path, base_ref=base, head_ref="HEAD")
    assert report.deterministic_final_grade == "F"
    assert report.blocks_merge is True
    assert report.modules[0].module == "pkg/bad.py"
    assert report.modules[0].grade == "F"
    assert report.modules[0].findings[0].source_tool == "syntax"


def test_score_changed_modules_historical_debt_non_blocking(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_text(tmp_path / "pkg" / "core.py", "VALUE = 1\n")
    base = _commit_all(tmp_path, "base")

    _write_text(tmp_path / "pkg" / "core.py", "VALUE = 2\n")
    _commit_all(tmp_path, "change")

    module_health = {
        "tool": "code_score",
        "status": "failed",
        "generated_at": "2000-01-01T00:00:00+00:00",
        "source_sha": "abc",
        "modules": [
            {
                "module": "pkg/core.py",
                "grade": "F",
                "findings": [],
            }
        ],
        "schema_version": "1",
    }
    health_path = tmp_path / "module-health.json"
    health_path.write_text(json.dumps(module_health), encoding="utf-8")

    report = code_score.score_changed_modules(
        tmp_path,
        base_ref=base,
        head_ref="HEAD",
        module_health_path=health_path,
    )
    assert report.modules[0].historical_health_grade == "F"
    assert report.deterministic_final_grade != "F"
    assert report.blocks_merge is False


def test_run_ai_advisory_missing_cli_returns_skipped(monkeypatch) -> None:
    monkeypatch.setattr(code_score.shutil, "which", lambda name: None)
    deterministic_report = code_score.CodeScoreReport(
        mode="fast",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_sha="abc",
        modules=[],
        deterministic_final_grade="A",
        ai_advisory=AIAdvisoryScore(status="disabled"),
        blocks_merge=False,
        reason="",
        audit_report=code_score.AuditReport(
            tool="code_score",
            status="passed",
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            source_sha="abc",
            findings=[],
        ),
    )
    score = code_score.run_ai_advisory(
        AIAdvisoryInput(
            diff="",
            touched_files={},
            deterministic_report=deterministic_report,
        ),
        provider="codex",
    )
    assert score.status == "skipped-missing-cli"


def test_run_ai_advisory_nonzero_is_skipped(monkeypatch) -> None:
    fake_result = subprocess.CompletedProcess(args=["codex"], returncode=2, stdout="", stderr="")

    class _FakeProc:
        @staticmethod
        def run(*_args, **_kwargs) -> subprocess.CompletedProcess:
            return fake_result

    monkeypatch.setattr(code_score, "_advisor_command", lambda provider: ["codex"])
    monkeypatch.setattr(code_score.subprocess, "run", _FakeProc.run)
    deterministic_report = code_score.CodeScoreReport(
        mode="fast",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_sha="abc",
        modules=[],
        deterministic_final_grade="A",
        ai_advisory=AIAdvisoryScore(status="disabled"),
        blocks_merge=False,
        reason="",
        audit_report=code_score.AuditReport(
            tool="code_score",
            status="passed",
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            source_sha="abc",
            findings=[],
        ),
    )
    score = code_score.run_ai_advisory(
        AIAdvisoryInput(diff="", touched_files={}, deterministic_report=deterministic_report),
        provider="codex",
    )
    assert score.status == "skipped-nonzero"
