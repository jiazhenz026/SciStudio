"""test_engineer_scope_guard calculator (ADR-042 Addendum 6 spec §4).

Produces: ``test_engineer`` persona touched production/build/governance code
without authorization.

Ported from the legacy ``test_engineer_scope_guard`` (deleted on this branch).
Path classification now uses the evaluator's single ``surfaces`` classifier
(implementation / protected-core / frontend / packaging / governance / test /
docs) instead of the guard's own overlapping pattern sets. The one
test-engineer-specific exception preserved is the explicitly-scoped QA-tooling
allowance (``src/scistudio/qa/**`` declared in the effective include set), which
lets a test engineer touch QA tooling when scope authorizes it.
"""

from __future__ import annotations

from scistudio.qa.governance.gate_record import surfaces
from scistudio.qa.governance.gate_record.guards import GuardInputs
from scistudio.qa.governance.gate_record.guards._stub import source_sha
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

TEST_ENGINEER_PERSONA = "test_engineer"

# Test artifact / validation surfaces a test engineer may always touch beyond
# the generic ``surfaces.is_test_path`` set (docs-side e2e + audit scratch).
_ALLOWED_NON_TEST_PATTERNS: tuple[str, ...] = (
    "docs/ai-developer/e2e/**",
    "docs/audit/**",
    "frontend/playwright.config.*",
    "frontend/vitest.config.*",
    "frontend/vitest.setup.*",
)

_QA_TOOLING_PATTERN = "src/scistudio/qa/**"


def _classify(path: str, *, effective_include: list[str]) -> tuple[str, bool]:
    """Return ``(classification, allowed)`` for one changed path."""

    if surfaces.is_gate_record_path(path):
        return "allowed_gate_record", True
    if surfaces.is_test_path(path) or surfaces.matches_any(path, _ALLOWED_NON_TEST_PATTERNS):
        return "allowed_test_artifact", True
    # Explicitly-scoped QA tooling: allowed only when scope authorizes it.
    if surfaces.match_path(path, _QA_TOOLING_PATTERN) and surfaces.matches_any(path, effective_include):
        return "allowed_explicit_qa_tooling", True
    if surfaces.is_governance_path(path):
        return "blocked_governance_surface", False
    if surfaces.is_protected_core_path(path):
        return "blocked_production_surface", False
    if surfaces.is_packaging_path(path):
        return "blocked_product_build_surface", False
    if surfaces.is_frontend_path(path):
        return "blocked_production_surface", False
    if surfaces.is_implementation_path(path):
        return "blocked_production_surface", False
    if surfaces.is_docs_path(path):
        return "allowed_docs", True
    return "blocked_unknown_surface", False


def check(inputs: GuardInputs) -> AuditReport:
    """Validate the test_engineer no-production-code boundary."""

    if inputs.persona != TEST_ENGINEER_PERSONA:
        return AuditReport(
            tool="test_engineer_scope_guard",
            status=AuditStatus.PASS,
            source_sha=source_sha(inputs.repo_root),
            findings=[],
            summary={"persona": inputs.persona, "applies": False},
        )

    effective_include = list(inputs.effective_include)
    classifications: dict[str, str] = {}
    findings: list[Finding] = []
    for path in inputs.changed_files:
        classification, allowed = _classify(path, effective_include=effective_include)
        classifications[path] = classification
        if not allowed:
            findings.append(
                Finding(
                    rule_id="test_engineer_scope_guard.blocked-path",
                    severity=Severity.ERROR,
                    file=path,
                    message=(
                        "test_engineer changes must stay in test, validation, e2e, or explicitly "
                        "scoped QA tooling paths"
                    ),
                    evidence={
                        "persona": inputs.persona,
                        "path": path,
                        "classification": classification,
                        "recommended_handoff": "assign implementer or remove the blocked path",
                    },
                )
            )

    return AuditReport(
        tool="test_engineer_scope_guard",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=source_sha(inputs.repo_root),
        findings=findings,
        summary={
            "persona": inputs.persona,
            "applies": True,
            "classifications": classifications,
        },
    )
