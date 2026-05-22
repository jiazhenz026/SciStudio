from __future__ import annotations

from pathlib import Path

from scistudio.qa.governance.test_engineer_scope_guard import ALLOWED_PATTERNS, check
from scistudio.qa.schemas.report import AuditStatus


def _rule_ids(report) -> set[str]:
    return {finding.rule_id for finding in report.findings}


def test_scope_guard_does_not_apply_to_other_personas() -> None:
    report = check(
        persona="implementer",
        changed_files=["src/scistudio/engine/scheduler.py"],
    )

    assert report.status == AuditStatus.PASS
    assert report.summary["applies"] is False


def test_scope_guard_allows_backend_tests_and_validation_evidence() -> None:
    report = check(
        persona="test_engineer",
        changed_files=[
            "tests/engine/test_scheduler.py",
            "docs/ai-developer/e2e/issue-1467-runtime.md",
            "docs/audit/issue-1467-runtime-validation.md",
        ],
    )

    assert report.status == AuditStatus.PASS


def test_scope_guard_allows_only_explicit_frontend_test_patterns() -> None:
    report = check(
        persona="test_engineer",
        changed_files=[
            "frontend/src/components/RunButton.test.tsx",
            "frontend/src/components/__tests__/RunButton.test.tsx",
            "frontend/src/components/__fixtures__/run-button.json",
            "frontend/src/components/__mocks__/api.ts",
            "frontend/e2e/run-flow.spec.ts",
            "frontend/tests/rendering.spec.ts",
            "frontend/test/setup.spec.ts",
            "frontend/playwright.config.ts",
            "frontend/vitest.config.ts",
            "frontend/vitest.setup.ts",
        ],
    )

    assert "frontend/**" not in ALLOWED_PATTERNS
    assert report.status == AuditStatus.PASS


def test_scope_guard_blocks_frontend_product_code_despite_frontend_prefix() -> None:
    report = check(
        persona="test_engineer",
        changed_files=["frontend/src/components/RunButton.tsx"],
    )

    assert report.status == AuditStatus.FAIL
    assert "test_engineer_scope_guard.blocked-path" in _rule_ids(report)
    finding = report.findings[0]
    assert finding.file == "frontend/src/components/RunButton.tsx"
    assert finding.evidence["classification"] == "blocked_production_surface"


def test_scope_guard_blocks_product_runtime_and_build_surfaces() -> None:
    report = check(
        persona="test_engineer",
        changed_files=[
            "src/scistudio/engine/scheduler.py",
            "src/scistudio/api/routes.py",
            "frontend/package.json",
            "pyproject.toml",
        ],
    )

    assert report.status == AuditStatus.FAIL
    blocked_paths = {finding.file for finding in report.findings}
    assert blocked_paths == {
        "src/scistudio/engine/scheduler.py",
        "src/scistudio/api/routes.py",
        "frontend/package.json",
        "pyproject.toml",
    }


def test_scope_guard_blocks_governance_paths_without_losing_dot_prefix() -> None:
    report = check(
        persona="test_engineer",
        changed_files=[".github/workflows/ci.yml", ".workflow/records/1467.json"],
    )

    assert report.status == AuditStatus.FAIL
    assert {finding.evidence["classification"] for finding in report.findings} == {"blocked_governance_surface"}


def test_scope_guard_allows_explicitly_scoped_qa_tooling() -> None:
    report = check(
        persona="test_engineer",
        changed_files=["src/scistudio/qa/governance/test_engineer_scope_guard.py"],
        scope_includes=["src/scistudio/qa/governance/test_engineer_scope_guard.py"],
    )

    assert report.status == AuditStatus.PASS


def test_scope_guard_reports_attempted_amendment_for_non_qa_production_path() -> None:
    report = check(
        persona="test_engineer",
        changed_files=["src/scistudio/engine/scheduler.py"],
        scope_includes=["src/scistudio/engine/scheduler.py"],
    )

    assert report.status == AuditStatus.FAIL
    finding = report.findings[0]
    assert finding.evidence["amendment_state"] == "attempted"
    assert finding.evidence["recommended_handoff"] == "assign implementer or remove the blocked path"


def test_scope_guard_normalizes_absolute_paths(tmp_path: Path) -> None:
    changed = tmp_path / "tests" / "qa" / "test_runtime_validation.py"

    report = check(
        repo_root=tmp_path,
        persona="test_engineer",
        changed_files=[changed],
    )

    assert report.status == AuditStatus.PASS
    assert report.summary["changed_files"] == ["tests/qa/test_runtime_validation.py"]
