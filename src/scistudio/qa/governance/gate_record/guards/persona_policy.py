"""persona_policy calculator (ADR-042 Addendum 6 spec §4 / §4.2).

Produces: unsupported persona; persona skill/guide pointer missing; unsupported
runtime root.

Ported from the legacy ``persona_policy`` (deleted on this branch). Per spec
§4.2 this calculator:

- adds ``live_implementer`` to the allowed personas, with skill mapping
  ``live-implementer``;
- fixes the stale ``implementer`` skill mapping (was ``implementation-worker``)
  to the actual ``implementer`` skill;
- treats ``guided`` as a valid task kind (the ledger ``TaskKind`` literal already
  includes it; this calculator does not reject it).

The persona and runtime are supplied by the evaluator from the ledger (no
free-form declaration dict). On-disk pointer validity is checked against the
runtime config root and the canonical persona guide under
``docs/ai-developer/personas/``.
"""

from __future__ import annotations

from scistudio.qa.governance.gate_record.guards import GuardInputs
from scistudio.qa.governance.gate_record.guards._stub import source_sha
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

# Allowed personas (Addendum 6 §7.3 adds ``live_implementer``).
ALLOWED_PERSONAS: frozenset[str] = frozenset(
    {"manager", "implementer", "adr_author", "audit_reviewer", "test_engineer", "live_implementer"}
)

# Persona -> runtime skill name (fixed ``implementer`` mapping; added
# ``live_implementer``).
REQUIRED_PERSONA_SKILLS: dict[str, str] = {
    "manager": "manager",
    "implementer": "implementer",
    "adr_author": "adr-author",
    "audit_reviewer": "audit-reviewer",
    "test_engineer": "test-engineer",
    "live_implementer": "live-implementer",
}

# Persona -> canonical persona guide under docs/ai-developer/personas/.
_PERSONA_GUIDES: dict[str, str] = {
    "manager": "docs/ai-developer/personas/manager.md",
    "implementer": "docs/ai-developer/personas/implementer.md",
    "adr_author": "docs/ai-developer/personas/adr-author.md",
    "audit_reviewer": "docs/ai-developer/personas/audit-reviewer.md",
    "test_engineer": "docs/ai-developer/personas/test-engineer.md",
    "live_implementer": "docs/ai-developer/personas/live-implementer.md",
}

# Supported AI runtime config roots (Addendum 6 §7.8).
SUPPORTED_RUNTIME_ROOTS: tuple[str, ...] = (".agents", ".claude", ".codex", ".gemini")

# Runtime token -> config root directory.
_RUNTIME_ROOTS: dict[str, str] = {
    "claude": ".claude",
    "codex": ".codex",
    "gemini": ".gemini",
    "agents": ".agents",
    "agent": ".agents",
}

# Root policy pointer that must exist for any runtime.
_ROOT_POLICY = "AGENTS.md"


def _runtime_root(runtime: str) -> str | None:
    normalized = runtime.strip().lower()
    for token, root in _RUNTIME_ROOTS.items():
        if normalized.startswith(token):
            return root
    return None


def check(inputs: GuardInputs) -> AuditReport:
    """Validate persona, persona skill/guide pointer, and runtime root."""

    repo_root = inputs.repo_root
    persona = inputs.persona
    findings: list[Finding] = []

    if persona not in ALLOWED_PERSONAS:
        findings.append(
            Finding(
                rule_id="persona_policy.unsupported-persona",
                severity=Severity.ERROR,
                message="persona must be one of the ADR-042 personas",
                evidence={"persona": persona, "allowed": sorted(ALLOWED_PERSONAS)},
            )
        )

    # Runtime config root validity.
    root = _runtime_root(inputs.runtime)
    if root is None or root not in SUPPORTED_RUNTIME_ROOTS:
        findings.append(
            Finding(
                rule_id="persona_policy.unsupported-runtime-root",
                severity=Severity.ERROR,
                message="runtime must map to one of the ADR-042 AI runtime config roots",
                evidence={"runtime": inputs.runtime, "allowed_roots": list(SUPPORTED_RUNTIME_ROOTS)},
            )
        )

    # Persona skill pointer under the runtime config root.
    skill = REQUIRED_PERSONA_SKILLS.get(persona)
    if skill and root is not None:
        skill_pointer = repo_root / root / "skills" / skill / "SKILL.md"
        if not skill_pointer.exists():
            findings.append(
                Finding(
                    rule_id="persona_policy.missing-skill-pointer",
                    severity=Severity.ERROR,
                    message=f"persona skill pointer is missing for {persona}",
                    evidence={"persona": persona, "expected_skill": skill, "root": root},
                )
            )

    # Canonical persona guide.
    guide = _PERSONA_GUIDES.get(persona)
    if guide and not (repo_root / guide).exists():
        findings.append(
            Finding(
                rule_id="persona_policy.missing-persona-guide",
                severity=Severity.ERROR,
                message=f"persona guide doc is missing for {persona}",
                evidence={"persona": persona, "guide": guide},
            )
        )

    # Root policy pointer.
    if not (repo_root / _ROOT_POLICY).exists():
        findings.append(
            Finding(
                rule_id="persona_policy.missing-root-policy",
                severity=Severity.ERROR,
                message="root policy pointer (AGENTS.md) is missing",
                evidence={"root_policy": _ROOT_POLICY},
            )
        )

    return AuditReport(
        tool="persona_policy",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=source_sha(repo_root),
        findings=findings,
        summary={"persona": persona, "runtime": inputs.runtime, "runtime_root": root, "task_kind": inputs.task_kind},
    )
