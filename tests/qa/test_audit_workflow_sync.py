"""Tests for ``scieasy.qa.audit.workflow_sync`` (ADR-044 §11.5 + §12.3)."""

from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit.workflow_sync import run
from scieasy.qa.schemas.report import Severity


def _write_skill(
    repo: Path,
    skill_name: str,
    *,
    kind: str = "procedural",
    target: str = "docs/contributing/workflows/new-feature.md",
) -> Path:
    path = repo / ".claude/skills" / skill_name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {skill_name}\ndescription: x\nkind: {kind}\n---\n\nFor canonical procedure, read: `{target}`\n",
        encoding="utf-8",
    )
    return path


def _write_skill_no_pointer(repo: Path, skill_name: str) -> Path:
    path = repo / ".claude/skills" / skill_name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {skill_name}\ndescription: x\nkind: procedural\n---\n\nNo pointer in body.\n",
        encoding="utf-8",
    )
    return path


def _write_workflow_doc(repo: Path, slug: str, *, related_skills: list[str] | None = None) -> Path:
    path = repo / "docs/contributing/workflows" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = f"---\nworkflow_id: {slug}\n"
    if related_skills:
        fm += "related_skills:\n"
        for s in related_skills:
            fm += f"  - {s}\n"
    fm += "---\n"
    path.write_text(fm + f"# {slug}\n", encoding="utf-8")
    return path


class TestRun:
    def test_dormant_when_workflows_dir_absent(self, tmp_path: Path) -> None:
        findings = run(tmp_path)
        assert len(findings) == 1
        assert findings[0].rule_id == "workflow-sync.dormant"
        assert findings[0].severity == Severity.INFO

    def test_clean_closure_no_findings(self, tmp_path: Path) -> None:
        _write_workflow_doc(tmp_path, "new-feature", related_skills=["new-feature"])
        _write_skill(
            tmp_path,
            "new-feature",
            target="docs/contributing/workflows/new-feature.md",
        )
        findings = run(tmp_path)
        assert findings == []

    def test_workflow_unreferenced_error(self, tmp_path: Path) -> None:
        _write_workflow_doc(tmp_path, "orphan")
        # We need to anchor workflows/ directory existence with one valid skill.
        _write_workflow_doc(tmp_path, "other", related_skills=["other"])
        _write_skill(
            tmp_path,
            "other",
            target="docs/contributing/workflows/other.md",
        )
        findings = run(tmp_path)
        assert any(
            f.rule_id == "workflow-sync.workflow-unreferenced"
            and f.file == "docs/contributing/workflows/orphan.md"
            and f.severity == Severity.ERROR
            for f in findings
        )

    def test_related_skills_mismatch_warning(self, tmp_path: Path) -> None:
        # Workflow doc exists with NO related_skills, but a skill points
        # at it.
        _write_workflow_doc(tmp_path, "implicit")
        _write_skill(
            tmp_path,
            "implicit",
            target="docs/contributing/workflows/implicit.md",
        )
        findings = run(tmp_path)
        assert any(
            f.rule_id == "workflow-sync.related-skills-mismatch" and f.severity == Severity.WARNING for f in findings
        )

    def test_target_missing_error(self, tmp_path: Path) -> None:
        # Workflows dir exists (from another doc) but the skill's target
        # is non-existent.
        _write_workflow_doc(tmp_path, "real", related_skills=["real"])
        _write_skill(
            tmp_path,
            "real",
            target="docs/contributing/workflows/real.md",
        )
        _write_skill(
            tmp_path,
            "ghost",
            target="docs/contributing/workflows/ghost.md",
        )
        findings = run(tmp_path)
        assert any(f.rule_id == "workflow-sync.target-missing" and f.severity == Severity.ERROR for f in findings)

    def test_skill_no_target_warning(self, tmp_path: Path) -> None:
        _write_workflow_doc(tmp_path, "x", related_skills=["x"])
        _write_skill(tmp_path, "x", target="docs/contributing/workflows/x.md")
        _write_skill_no_pointer(tmp_path, "y")
        findings = run(tmp_path)
        assert any(f.rule_id == "workflow-sync.no-target" and f.severity == Severity.WARNING for f in findings)

    def test_non_procedural_skills_ignored(self, tmp_path: Path) -> None:
        _write_workflow_doc(tmp_path, "x", related_skills=["x"])
        _write_skill(
            tmp_path,
            "x",
            target="docs/contributing/workflows/x.md",
        )
        # bootstrap-meta skill — not part of workflow-sync.
        _write_skill(
            tmp_path,
            "speckit",
            kind="bootstrap-meta",
            target="docs/doc-guide/foo.md",
        )
        findings = run(tmp_path)
        # No findings from the bootstrap-meta skill.
        assert all("speckit" not in str(f.file) for f in findings)

    def test_multiple_related_skills_ok(self, tmp_path: Path) -> None:
        _write_workflow_doc(tmp_path, "shared", related_skills=["a", "b"])
        _write_skill(
            tmp_path,
            "a",
            target="docs/contributing/workflows/shared.md",
        )
        _write_skill(
            tmp_path,
            "b",
            target="docs/contributing/workflows/shared.md",
        )
        findings = run(tmp_path)
        assert findings == []
