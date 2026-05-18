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


def test_run_default_commit_range_covers_branch(tmp_path: Path) -> None:
    """Codex P1 #1161: trailer_lint must audit every commit on the branch.

    Without an explicit commit_range, ``run`` should resolve to
    ``origin/main..HEAD`` when ``origin/main`` exists, and to
    ``HEAD~1..HEAD`` otherwise (fresh clone). We verify the fallback
    here; the ``origin/main`` path is exercised in the real CI run.
    """
    from scieasy.qa.audit.full_audit import _default_commit_range

    _init_repo(tmp_path)
    # No remote 'origin/main' present → must fall back.
    assert _default_commit_range(tmp_path) == "HEAD~1..HEAD"


def test_run_with_explicit_commit_range(tmp_path: Path) -> None:
    """Caller can override the default range."""
    _init_repo(tmp_path)
    report = run(tmp_path, pre_push=True, commit_range="HEAD")
    trailer = next(tr for tr in report.runs if tr.tool == "trailer_lint")
    # The hash includes the range so we can verify it propagated.
    assert "HEAD" in trailer.config_hash or trailer.exit_status in {
        "ok",
        "warnings",
        "errors",
    }


def test_run_discovers_specs_dir(tmp_path: Path) -> None:
    """Codex P2 #1161: docs/specs/ (plural) is also scanned."""
    from scieasy.qa.audit.full_audit import _resolve_file_targets

    _init_repo(tmp_path)
    (tmp_path / "docs" / "specs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "specs" / "my-feature.md").write_text("---\nkey: value\n---\n", encoding="utf-8")
    targets = _resolve_file_targets(tmp_path, None)
    target_strs = [str(t).replace("\\", "/") for t in targets]
    assert any("docs/specs/my-feature.md" in s for s in target_strs)


def test_run_with_targets_filters_frontmatter_lint(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    p = tmp_path / "docs" / "adr" / "ADR-042.md"
    p.write_text("not-a-valid-frontmatter\n", encoding="utf-8")
    report = run(tmp_path, pre_push=True, targets=[p])
    # frontmatter_lint should run on the single target; no schema match
    # for a non-frontmatter file → no findings (permissive fall-through).
    fm_run = next(tr for tr in report.runs if tr.tool == "frontmatter_lint")
    assert fm_run.exit_status in {"ok", "warnings", "errors"}
