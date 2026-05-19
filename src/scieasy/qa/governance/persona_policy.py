"""Persona, constitution, and runtime skill parity checks."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa._shared import AuditReport
from scieasy.qa.audit._cli import exit_code, print_report
from scieasy.qa.governance.local_gate import GateSession, load_session

SUPPORTED_PERSONAS = {
    "manager": "agent-manager",
    "implementer": "implementation-worker",
    "adr_author": "adr-author",
    "audit_reviewer": "audit-reviewer",
}


class SkillPointer(BaseModel):
    runtime: str
    skill_path: str
    persona: str
    workflow_doc: str
    root_policy_ref: str


def _runtime_name(root: Path) -> str:
    return root.name.lstrip(".")


def discover_skill_pointers(
    repo_root: Path,
    *,
    runtime_roots: Sequence[Path] = (Path(".agents"), Path(".claude"), Path(".codex"), Path(".gemini")),
) -> list[SkillPointer]:
    pointers: list[SkillPointer] = []
    for root in runtime_roots:
        absolute_root = root if root.is_absolute() else repo_root / root
        if not absolute_root.exists():
            continue
        for persona, skill_name in SUPPORTED_PERSONAS.items():
            skill_path = absolute_root / "skills" / skill_name / "SKILL.md"
            if not skill_path.exists():
                continue
            text = skill_path.read_text(encoding="utf-8")
            workflow_doc = ""
            root_policy_ref = ""
            for line in text.splitlines():
                if "docs/contributing/workflows/" in line:
                    workflow_doc = line.strip()
                if "AGENTS.md" in line or "root policy" in line.lower():
                    root_policy_ref = line.strip()
            pointers.append(
                SkillPointer(
                    runtime=_runtime_name(root),
                    skill_path=skill_path.relative_to(repo_root).as_posix(),
                    persona=persona,
                    workflow_doc=workflow_doc,
                    root_policy_ref=root_policy_ref,
                )
            )
    return pointers


def check_persona_policy(
    *,
    repo_root: Path,
    session: GateSession,
    runtime_roots: Sequence[Path] | None = None,
) -> AuditReport:
    repo_root = repo_root.resolve()
    findings = []
    if session.persona not in SUPPORTED_PERSONAS:
        findings.append(
            build_finding(
                finding_id="persona-policy-unsupported",
                tool="persona_policy",
                finding_class="persona",
                severity="error",
                message=f"Unsupported ADR-042 persona: {session.persona}",
                subject=session.persona,
            )
        )
    roots = runtime_roots or (Path(".agents"), Path(".claude"), Path(".codex"), Path(".gemini"))
    pointers = discover_skill_pointers(repo_root, runtime_roots=roots)
    expected_skill = SUPPORTED_PERSONAS.get(session.persona)
    matching = [p for p in pointers if p.runtime == session.runtime and p.persona == session.persona]
    if expected_skill and not matching:
        findings.append(
            build_finding(
                finding_id="persona-policy-missing-skill",
                tool="persona_policy",
                finding_class="skill-pointer",
                severity="error",
                message=f"Runtime {session.runtime} missing skill for persona {session.persona}",
                subject=session.persona,
            )
        )
    for root in roots:
        absolute_root = root if root.is_absolute() else repo_root / root
        if not absolute_root.exists():
            continue
        constitution = absolute_root / "memory" / "constitution.md"
        if not constitution.exists():
            findings.append(
                build_finding(
                    finding_id="persona-policy-missing-constitution",
                    tool="persona_policy",
                    finding_class="constitution",
                    severity="error",
                    message=f"Runtime root missing memory/constitution.md: {root}",
                    path=root.as_posix(),
                )
            )
    runtimes = {p.runtime for p in pointers}
    if {"claude", "codex"}.issubset(runtimes):
        for persona in SUPPORTED_PERSONAS:
            per_runtime = {p.runtime for p in pointers if p.persona == persona}
            if "claude" in per_runtime and "codex" not in per_runtime:
                findings.append(
                    build_finding(
                        finding_id="persona-policy-runtime-parity",
                        tool="persona_policy",
                        finding_class="runtime-parity",
                        severity="error",
                        message=f"Persona {persona} exists for Claude but not Codex.",
                        subject=persona,
                    )
                )
    return build_report(tool="persona_policy", repo_root=repo_root, findings=findings)


def check(
    *,
    repo_root: Path,
    session: GateSession | None = None,
    runtime_roots: Sequence[Path] | None = None,
) -> AuditReport:
    session = session or load_session(repo_root)
    if session is None:
        return build_report(
            tool="persona_policy",
            repo_root=repo_root,
            findings=[
                build_finding(
                    finding_id="persona-policy-missing-session",
                    tool="persona_policy",
                    finding_class="missing-session",
                    severity="error",
                    message="No gate session found for persona policy check.",
                )
            ],
        )
    return check_persona_policy(repo_root=repo_root, session=session, runtime_roots=runtime_roots)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check ADR-042 persona policy.")
    parser.add_argument("--session")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    report = check(repo_root=Path.cwd(), session=load_session(Path.cwd(), session_id=args.session))
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
