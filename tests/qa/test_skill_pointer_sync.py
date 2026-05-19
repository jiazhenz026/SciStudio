from pathlib import Path

from scieasy.qa.audit import skill_pointer_sync


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_skill_pointer_sync_valid_pointer(tmp_path: Path) -> None:
    skill = tmp_path / ".agents" / "team" / "SKILL.md"
    workflow = tmp_path / "docs/contributing/workflows/agent.md"
    _write(skill, "workflow_doc: docs/contributing/workflows/agent.md\n")
    _write(workflow, "# Workflow\n")

    report = skill_pointer_sync.check(repo_root=tmp_path, runtime_roots=(Path(".agents"),))
    assert report.status == "passed"
    assert report.findings == []


def test_skill_pointer_sync_missing_pointer(tmp_path: Path) -> None:
    skill = tmp_path / ".agents" / "team" / "SKILL.md"
    _write(skill, "# just a heading\n")
    report = skill_pointer_sync.check(repo_root=tmp_path, runtime_roots=(Path(".agents"),))
    assert report.status == "failed"
    assert any(finding.id == "skill-pointer-missing" for finding in report.findings)


def test_skill_pointer_sync_stale_pointer(tmp_path: Path) -> None:
    skill = tmp_path / ".agents" / "team" / "SKILL.md"
    _write(skill, "workflow_doc: docs/contributing/workflows/missing.md\n")
    report = skill_pointer_sync.check(repo_root=tmp_path, runtime_roots=(Path(".agents"),))
    assert report.status == "failed"
    assert any(finding.id == "skill-pointer-stale" for finding in report.findings)
