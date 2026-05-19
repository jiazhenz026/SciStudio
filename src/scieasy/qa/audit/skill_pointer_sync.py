"""Validate runtime skill files point to canonical workflow documentation."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa._shared import AuditReport

WORKFLOW_ROOT = "docs/contributing/workflows"


@dataclass(frozen=True)
class SkillPointer:
    runtime: str
    skill_path: str
    persona: str
    workflow_doc: str
    root_policy_ref: str


def discover_skill_pointers(
    repo_root: Path,
    *,
    runtime_roots: Sequence[Path] = (
        Path(".agents"),
        Path(".claude"),
        Path(".codex"),
        Path(".gemini"),
    ),
) -> list[SkillPointer]:
    pointers: list[SkillPointer] = []
    for root in runtime_roots:
        base = repo_root / root
        if not base.exists():
            continue
        for file in sorted(base.rglob("SKILL.md")):
            pointer = _parse_skill_file(file)
            pointers.append(
                SkillPointer(
                    runtime=base.name,
                    skill_path=file.relative_to(repo_root).as_posix(),
                    persona=file.parent.name or "unknown",
                    workflow_doc=pointer.get("workflow_doc", ""),
                    root_policy_ref=pointer.get("root_policy_ref", ""),
                )
            )
    return pointers


def _parse_skill_file(file: Path) -> dict[str, str]:
    text = file.read_text(encoding="utf-8")
    result: dict[str, str] = {}

    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            fm = yaml.safe_load(text[3:end]) or {}
            if isinstance(fm, dict):
                if isinstance(fm.get("workflow_doc"), str):
                    result["workflow_doc"] = fm["workflow_doc"].strip()
                elif isinstance(fm.get("workflow"), str):
                    result["workflow_doc"] = fm["workflow"].strip()
                if isinstance(fm.get("root_policy_ref"), str):
                    result["root_policy_ref"] = fm["root_policy_ref"].strip()

    for line in text.splitlines():
        if line.startswith("workflow_doc:"):
            value = line.split(":", 1)[1].strip()
            if value:
                result["workflow_doc"] = value
        if line.startswith("root_policy_ref:"):
            value = line.split(":", 1)[1].strip()
            if value:
                result["root_policy_ref"] = value
        if line.startswith("workflow:"):
            value = line.split(":", 1)[1].strip()
            if value:
                result["workflow_doc"] = value

    return result


def _is_canonical_workflow(path: Path, repo_root: Path) -> bool:
    target = path if path.is_absolute() else (repo_root / path).resolve()
    expected_root = (repo_root / WORKFLOW_ROOT).resolve()
    return target.exists() and expected_root in target.parents


def check(
    *,
    repo_root: Path,
    runtime_roots: Sequence[Path] | None = None,
) -> AuditReport:
    pointers = discover_skill_pointers(repo_root=repo_root, runtime_roots=runtime_roots or ())
    findings = []

    for pointer in pointers:
        if not pointer.workflow_doc:
            findings.append(
                build_finding(
                    finding_id="skill-pointer-missing",
                    tool="skill_pointer_sync",
                    finding_class="skill-pointer",
                    severity="error",
                    message=f"Skill {pointer.skill_path} missing workflow_doc pointer",
                    path=repo_root / pointer.skill_path,
                )
            )
            continue

        workflow_path = Path(pointer.workflow_doc)
        if workflow_path.suffix == "":
            workflow_path = workflow_path.with_suffix(".md")

        if not workflow_path.is_absolute():
            workflow_path = repo_root / workflow_path

        if not workflow_path.exists():
            findings.append(
                build_finding(
                    finding_id="skill-pointer-stale",
                    tool="skill_pointer_sync",
                    finding_class="skill-pointer",
                    severity="error",
                    message=(f"Skill {pointer.skill_path} points to missing workflow doc {pointer.workflow_doc}"),
                    path=repo_root / pointer.skill_path,
                    subject="pointer",
                )
            )
            continue

        if not _is_canonical_workflow(workflow_path, repo_root):
            findings.append(
                build_finding(
                    finding_id="skill-pointer-noncanonical",
                    tool="skill_pointer_sync",
                    finding_class="skill-pointer",
                    severity="error",
                    message=(f"Skill {pointer.skill_path} points to non-canonical workflow doc {pointer.workflow_doc}"),
                    path=repo_root / pointer.skill_path,
                )
            )

    return build_report(tool="skill_pointer_sync", repo_root=repo_root, findings=findings)


def _serialize(report: AuditReport, as_json: bool) -> None:
    if as_json:
        print(report.model_dump_json())
        return
    for finding in report.findings:
        print(f"[{finding.severity}] {finding.path}:{finding.line or 0} {finding.id} {finding.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check agent skill workflow pointers.")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    report = check(repo_root=Path.cwd())
    _serialize(report, args.format == "json")
    return 1 if report.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
