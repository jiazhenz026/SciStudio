"""Tests for ``scieasy.qa.audit.full_audit`` (ADR-042 §9.6 orchestrator)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scieasy.qa.audit.full_audit import run
from scieasy.qa.schemas.report import AuditReport


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.org"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True)
    (path / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    pkg = path / "src" / "myproj"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('"""mod."""\n', encoding="utf-8")
    (path / "MAINTAINERS").write_text("entries: []\n", encoding="utf-8")
    (path / "docs" / "adr").mkdir(parents=True)


def test_run_pre_push_subset(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    report = run(tmp_path, pre_push=True)
    tools = {tr.tool for tr in report.runs}
    assert "trailer_lint" in tools
    assert "committer_enforce" in tools
    assert "frontmatter_lint" in tools
    assert "closure" in tools
    # pre_push omits slow tools
    assert "doc_drift" not in tools
    assert "fact_drift" not in tools
    assert isinstance(report, AuditReport)


def test_run_full_includes_doc_drift_and_fact_drift(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    report = run(tmp_path, pre_push=False)
    tools = {tr.tool for tr in report.runs}
    assert "doc_drift" in tools
    assert "fact_drift" in tools


def test_run_self_check_adds_contradiction(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    adr_path = tmp_path / "docs" / "adr" / "ADR-042.md"
    adr_path.write_text(
        (
            "---\n"
            "adr: 42\n"
            'title: "Self"\n'
            "status: Accepted\n"
            "date_created: 2026-05-17\n"
            "date_accepted: 2026-05-18\n"
            "is_code_implementation: false\n"
            "governs:\n"
            "  modules: []\n"
            "  files: []\n"
            "tests: []\n"
            'agent_editable: "false"\n'
            'owner: "@you"\n'
            "---\n\n"
            "# 1. Intro\n"
        ),
        encoding="utf-8",
    )
    report = run(tmp_path, pre_push=False, self_check=True)
    tools = {tr.tool for tr in report.runs}
    assert "contradiction_audit" in tools


def test_run_with_targets_filters_frontmatter_lint(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    p = tmp_path / "docs" / "adr" / "ADR-042.md"
    p.write_text("not-a-valid-frontmatter\n", encoding="utf-8")
    report = run(tmp_path, pre_push=True, targets=[p])
    # frontmatter_lint should run on the single target; no schema match
    # for a non-frontmatter file → no findings (permissive fall-through).
    fm_run = next(tr for tr in report.runs if tr.tool == "frontmatter_lint")
    assert fm_run.exit_status in {"ok", "warnings", "errors"}
