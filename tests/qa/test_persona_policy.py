from __future__ import annotations

from pathlib import Path

from scistudio.qa.governance.persona_policy import check
from scistudio.qa.schemas.report import AuditStatus


def _write(repo: Path, path: str, content: str = "ok\n") -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return path


def _valid_declaration(repo: Path) -> dict[str, object]:
    return {
        "persona": "implementer",
        "skill": "implementation-worker",
        "runtime_root": ".codex",
        "skill_path": _write(repo, ".codex/skills/implementation-worker/SKILL.md"),
        "constitution_path": _write(repo, ".codex/constitution.md"),
        "root_policy_path": _write(repo, "AGENTS.md"),
        "workflow_docs": [_write(repo, "docs/contributing/workflows/human-bypass.md")],
    }


def test_persona_policy_accepts_supported_persona_fixture(tmp_path: Path) -> None:
    declaration = _valid_declaration(tmp_path)

    report = check(repo_root=tmp_path, declaration=declaration)

    assert report.status == AuditStatus.PASS


def test_persona_policy_accepts_test_engineer_with_required_skill(tmp_path: Path) -> None:
    declaration = _valid_declaration(tmp_path)
    declaration["persona"] = "test_engineer"
    declaration["skill"] = "test-engineer"
    declaration["skill_path"] = _write(tmp_path, ".codex/skills/test-engineer/SKILL.md")

    report = check(repo_root=tmp_path, declaration=declaration)

    assert report.status == AuditStatus.PASS


def test_persona_policy_rejects_test_engineer_skill_mismatch(tmp_path: Path) -> None:
    declaration = _valid_declaration(tmp_path)
    declaration["persona"] = "test_engineer"

    report = check(repo_root=tmp_path, declaration=declaration)

    assert report.status == AuditStatus.FAIL
    assert "persona_policy.skill-mismatch" in {finding.rule_id for finding in report.findings}


def test_persona_policy_rejects_unsupported_persona(tmp_path: Path) -> None:
    declaration = _valid_declaration(tmp_path)
    declaration["persona"] = "freeform_agent"

    report = check(repo_root=tmp_path, declaration=declaration)

    assert report.status == AuditStatus.FAIL
    assert "persona_policy.unsupported-persona" in {finding.rule_id for finding in report.findings}


def test_persona_policy_rejects_missing_skill_and_policy_pointers(tmp_path: Path) -> None:
    declaration = _valid_declaration(tmp_path)
    declaration["skill_path"] = ".codex/skills/missing/SKILL.md"
    declaration["root_policy_path"] = "MISSING_AGENTS.md"

    report = check(repo_root=tmp_path, declaration=declaration)

    assert report.status == AuditStatus.FAIL
    assert "persona_policy.missing-skill_path" in {finding.rule_id for finding in report.findings}
    assert "persona_policy.missing-root_policy_path" in {finding.rule_id for finding in report.findings}


def test_persona_policy_rejects_runtime_specific_root(tmp_path: Path) -> None:
    declaration = _valid_declaration(tmp_path)
    declaration["runtime_root"] = ".vendor-only"

    report = check(repo_root=tmp_path, declaration=declaration)

    assert report.status == AuditStatus.FAIL
    assert "persona_policy.unsupported-runtime-root" in {finding.rule_id for finding in report.findings}
