from __future__ import annotations

import subprocess
from pathlib import Path

from scieasy.qa.governance import weakened_ci_check
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
    _write(
        repo,
        ".github/workflows/ci.yml",
        "\n".join(
            [
                "name: CI",
                "jobs:",
                "  lint:",
                "    steps:",
                "      - run: ruff check .",
                "      - run: ruff format --check .",
                "  test:",
                "    steps:",
                "      - run: timeout 600 pytest -n auto --timeout=60 --timeout-method=thread",
                "  import-lint:",
                "    steps:",
                "      - run: lint-imports",
                "",
            ]
        ),
    )
    _write(
        repo,
        ".pre-commit-config.yaml",
        "\n".join(
            [
                "repos:",
                "  - repo: https://github.com/pre-commit/pre-commit-hooks",
                "    hooks:",
                "      - id: check-yaml",
                "      - id: check-json",
                "      - id: check-merge-conflict",
                "      - id: detect-private-key",
                "",
            ]
        ),
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_weakened_ci_detects_removed_required_check(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    workflow = repo / ".github/workflows/ci.yml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace("      - run: ruff check .\n", ""), encoding="utf-8"
    )
    _git(repo, "add", ".")

    report = weakened_ci_check.verify_no_weakening(repo, staged=True)

    assert report.status == AuditStatus.FAIL
    assert "weakened-ci.removed-ruff-check" in {finding.rule_id for finding in report.findings}


def test_weakened_ci_detects_added_continue_on_error(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    workflow = repo / ".github/workflows/ci.yml"
    workflow.write_text(workflow.read_text(encoding="utf-8") + "    continue-on-error: true\n", encoding="utf-8")
    _git(repo, "add", ".")

    report = weakened_ci_check.verify_no_weakening(repo, staged=True)

    assert report.status == AuditStatus.FAIL
    assert "weakened-ci.added-continue-on-error" in {finding.rule_id for finding in report.findings}


def test_weakened_ci_passes_unrelated_diff(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write(repo, "README.md", "not governed\n")
    _git(repo, "add", ".")

    report = weakened_ci_check.verify_no_weakening(repo, staged=True)

    assert report.status == AuditStatus.PASS
    assert report.summary["diff_lines_checked"] == 0


def test_weakened_ci_detects_removed_pre_commit_hook(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    config = repo / ".pre-commit-config.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace("      - id: detect-private-key\n", ""), encoding="utf-8"
    )
    _git(repo, "add", ".")

    report = weakened_ci_check.verify_no_weakening(repo, staged=True)

    assert report.status == AuditStatus.FAIL
    assert "weakened-ci.removed-detect-private-key" in {finding.rule_id for finding in report.findings}


def test_weakened_ci_accepts_adr042_local_bypass_label(tmp_path: Path, monkeypatch) -> None:
    repo = _init_repo(tmp_path)
    workflow = repo / ".github/workflows/ci.yml"
    workflow.write_text(workflow.read_text(encoding="utf-8") + "    continue-on-error: true\n", encoding="utf-8")
    _git(repo, "add", ".")
    monkeypatch.setenv("SCIEASY_GATE_BYPASS_LABELS", "admin-approved:ai-override")

    report = weakened_ci_check.verify_no_weakening(repo, staged=True)

    assert report.status == AuditStatus.PASS
    assert report.summary["bypassed"] is True


def test_weakened_ci_rejects_invalid_adr042_local_bypass_label(tmp_path: Path, monkeypatch) -> None:
    repo = _init_repo(tmp_path)
    workflow = repo / ".github/workflows/ci.yml"
    workflow.write_text(workflow.read_text(encoding="utf-8") + "    continue-on-error: true\n", encoding="utf-8")
    _git(repo, "add", ".")
    monkeypatch.setenv("SCIEASY_GATE_BYPASS_LABELS", "admin-approved-core-change")

    report = weakened_ci_check.verify_no_weakening(repo, staged=True)

    assert report.status == AuditStatus.FAIL
    assert "weakened-ci.invalid-override-label" in {finding.rule_id for finding in report.findings}
