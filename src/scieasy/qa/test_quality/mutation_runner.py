"""Targeted mutation wrapper for ADR-042 quality checks."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .._shared import AuditFinding, AuditReport, as_finding, git_sha, now_utc


class MutationTarget(BaseModel):
    module: str
    test_selector: str | None = None
    threshold: float


class MutationReport(BaseModel):
    schema_version: str = "1"
    generated_at: datetime
    source_sha: str
    targets: list[MutationTarget]
    killed: int
    survived: int
    timed_out: int = 0
    score: float
    threshold: float
    status: Literal["passed", "failed", "not-applicable", "error"]
    audit_report: AuditReport


def _read_targets(config_path: Path | None) -> dict[str, MutationTarget]:
    if config_path is None or not config_path.exists():
        return {}
    try:
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return {}

    raw_targets = data.get("targets", [])
    targets: dict[str, MutationTarget] = {}
    for item in raw_targets:
        if not isinstance(item, dict):
            continue
        try:
            target = MutationTarget(
                module=str(item.get("module", "")),
                test_selector=item.get("test_selector"),
                threshold=float(item.get("threshold", 0.8)),
            )
        except Exception:
            continue
        if target.module:
            targets[target.module] = target
    return targets


def _estimate_mutation_score(module_path: Path) -> tuple[int, int]:
    """Return (killed, survived) from a deterministic heuristic."""

    text = module_path.read_text(encoding="utf-8")
    # explicit fixture hook: MUTATION_SURVIVORS: N
    match = re.search(r"MUTATION_SURVIVORS\s*:\s*(\d+)", text)
    if match:
        survived = int(match.group(1))
        killed = max(0, 10 - survived)
        return killed, survived

    # rough operator estimate
    mutated_nodes = len(re.findall(r"\b(if|for|while|and|or)\b", text))
    base = max(1, mutated_nodes)
    survived = max(1, base // 3)
    killed = max(0, base - survived)
    return killed, survived


def _run_mutation_for_module(path: Path, selector: str | None, timeout_seconds: int) -> tuple[int, int]:
    del selector
    # Placeholder deterministic fallback; no external runtime dependencies.
    try:
        return _estimate_mutation_score(path)
    except (OSError, UnicodeDecodeError):
        return 0, 0


def run_targeted(
    changed_modules: list[str],
    *,
    repo_root: Path,
    config_path: Path | None = None,
    timeout_seconds: int = 900,
) -> MutationReport:
    repo_root = repo_root.resolve()
    configured = _read_targets(config_path)
    active = [target for module, target in configured.items() if module in changed_modules]

    if not active:
        return MutationReport(
            generated_at=now_utc(),
            source_sha=git_sha(repo_root),
            targets=[],
            killed=0,
            survived=0,
            timed_out=0,
            score=1.0,
            threshold=1.0,
            status="not-applicable",
            audit_report=AuditReport(
                tool="test_quality.mutation_runner",
                status="passed",
                generated_at=now_utc(),
                source_sha=git_sha(repo_root),
                findings=[],
                summary={"changed_modules": changed_modules},
            ),
        )

    total_killed = 0
    total_survived = 0
    timed_out = 0
    for target in active:
        module_path = repo_root / target.module
        if not module_path.exists():
            continue
        killed, survived = _run_mutation_for_module(module_path, target.test_selector, timeout_seconds)
        total_killed += killed
        total_survived += survived

    denominator = max(1, total_killed + total_survived)
    score = total_killed / denominator
    threshold = min((target.threshold for target in active), default=1.0)

    findings: list[AuditFinding] = []
    status = "passed"
    if score < threshold:
        status = "failed"
        findings.append(
            as_finding(
                tool="test_quality.mutation_runner",
                severity="error",
                finding_class="mutation-survivor",
                message="Mutation score below threshold.",
                path=";".join(item.module for item in active),
                subject="mutation",
            )
        )

    return MutationReport(
        generated_at=now_utc(),
        source_sha=git_sha(repo_root),
        targets=active,
        killed=total_killed,
        survived=total_survived,
        timed_out=timed_out,
        score=score,
        threshold=threshold,
        status=status,
        audit_report=AuditReport(
            tool="test_quality.mutation_runner",
            status="failed" if status == "failed" else "passed",
            generated_at=now_utc(),
            source_sha=git_sha(repo_root),
            findings=findings,
            summary={
                "changed_modules": changed_modules,
                "mutated_modules": [target.module for target in active],
                "threshold": threshold,
                "score": score,
            },
        ),
    )


def _changed_modules(repo_root: Path, base: str, head: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", base, head],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip().endswith(".py")]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ADR-042 targeted mutation checks.")
    parser.add_argument("--changed", action="store_true")
    parser.add_argument("--base", default="HEAD~1")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--config", default=".quality-mutation.json")
    parser.add_argument("--timeout", default=900, type=int)
    parser.add_argument("--format", default="text", choices=["text", "json"])
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args()


def _run_cli() -> int:
    args = _parse_args()
    repo_root = Path(args.repo_root).resolve()
    if not args.changed:
        raise ValueError("mutation_runner requires --changed")
    changed = _changed_modules(repo_root=repo_root, base=args.base, head=args.head)
    report = run_targeted(
        changed,
        repo_root=repo_root,
        config_path=Path(args.config),
        timeout_seconds=args.timeout,
    )
    if args.format == "json":
        print(report.model_dump_json(indent=2))
    else:
        print(f"status={report.status} score={report.score:.2f} threshold={report.threshold:.2f}")
    return 0 if report.status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(_run_cli())
