"""Validate ADR-042 AI persona and runtime policy declarations."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

ALLOWED_PERSONAS = frozenset({"manager", "implementer", "adr_author", "audit_reviewer"})
REQUIRED_PERSONA_SKILLS = {
    "manager": "agent-manager",
    "implementer": "implementation-worker",
    "adr_author": "adr-author",
    "audit_reviewer": "audit-reviewer",
}
SUPPORTED_RUNTIME_ROOTS = (".agents", ".claude", ".codex", ".gemini")


def _source_sha(repo_root: Path | None) -> str:
    if repo_root is None:
        return "unknown"
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _as_path(repo_root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def _missing_path_finding(field: str, value: object) -> Finding:
    return Finding(
        rule_id=f"persona_policy.missing-{field}",
        severity=Severity.ERROR,
        message=f"persona declaration must reference an existing {field.replace('_', ' ')}",
        evidence={field: value},
    )


def check(
    *,
    repo_root: Path,
    declaration: Mapping[str, Any],
    runtime_roots: Sequence[str | Path] | None = None,
) -> AuditReport:
    """Validate a fixture-friendly persona declaration."""

    findings: list[Finding] = []
    persona = str(declaration.get("persona", ""))
    if persona not in ALLOWED_PERSONAS:
        findings.append(
            Finding(
                rule_id="persona_policy.unsupported-persona",
                severity=Severity.ERROR,
                message="persona must be one of the four ADR-042 personas",
                evidence={"persona": persona, "allowed": sorted(ALLOWED_PERSONAS)},
            )
        )

    expected_skill = REQUIRED_PERSONA_SKILLS.get(persona)
    skill_name = str(declaration.get("skill", declaration.get("required_skill", "")))
    if expected_skill and skill_name and skill_name != expected_skill:
        findings.append(
            Finding(
                rule_id="persona_policy.skill-mismatch",
                severity=Severity.ERROR,
                message="persona skill does not match ADR-042 persona table",
                evidence={"persona": persona, "expected": expected_skill, "actual": skill_name},
            )
        )

    roots = [str(path).replace("\\", "/").rstrip("/") for path in (runtime_roots or SUPPORTED_RUNTIME_ROOTS)]
    runtime_root = str(declaration.get("runtime_root", "")).replace("\\", "/").rstrip("/")
    if runtime_root and not any(runtime_root == root or runtime_root.startswith(f"{root}/") for root in roots):
        findings.append(
            Finding(
                rule_id="persona_policy.unsupported-runtime-root",
                severity=Severity.ERROR,
                message="runtime root must be one of the ADR-042 AI runtime config roots",
                evidence={"runtime_root": runtime_root, "allowed_roots": roots},
            )
        )

    for field in ("skill_path", "constitution_path", "root_policy_path"):
        path = _as_path(repo_root, declaration.get(field))
        if path is None or not path.exists():
            findings.append(_missing_path_finding(field, declaration.get(field)))

    workflow_docs = declaration.get("workflow_docs", [])
    if not isinstance(workflow_docs, Sequence) or isinstance(workflow_docs, str) or not workflow_docs:
        findings.append(
            Finding(
                rule_id="persona_policy.missing-workflow-docs",
                severity=Severity.ERROR,
                message="persona declaration must reference at least one workflow doc",
                evidence={"workflow_docs": workflow_docs},
            )
        )
    else:
        for doc in workflow_docs:
            path = _as_path(repo_root, doc)
            if path is None or not path.exists():
                findings.append(_missing_path_finding("workflow_docs", doc))

    return AuditReport(
        tool="persona_policy",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=_source_sha(repo_root),
        findings=findings,
        summary={"persona": persona, "runtime_root": runtime_root},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--declaration-json", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = check(repo_root=args.repo_root, declaration=json.loads(args.declaration_json))
    if args.format == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print("persona_policy: pass" if not report.findings else "persona_policy: fail")
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    sys.exit(main())
