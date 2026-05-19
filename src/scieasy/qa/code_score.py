"""ADR-042 deterministic changed-code scoring and module health reporting."""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from ._shared import (
    AuditFinding,
    AuditReport,
    GradeAlias,
    as_finding,
    better_grade,
    git_sha,
    now_utc,
    schema_dependency_note,
)

ScoreMode = Literal["fast", "full", "module-health"]
AIAdvisoryStatus = Literal[
    "completed",
    "skipped-missing-cli",
    "skipped-timeout",
    "skipped-nonzero",
    "skipped-invalid-json",
    "disabled",
]
ToolStatus = Literal["passed", "failed", "skipped", "missing"]
ToolSeverity = Literal["info", "warning", "error"]


class ToolSignal(BaseModel):
    tool: str
    status: ToolStatus
    severity: ToolSeverity
    path: str | None = None
    subject: str | None = None
    message: str
    raw: dict[str, Any] = Field(default_factory=dict)


class CodeScoreFinding(BaseModel):
    id: str
    grade_impact: GradeAlias
    reason: str
    path: str | None = None
    symbol: str | None = None
    source_tool: str
    introduced_by_change: bool
    blocks_merge: bool = False


class AIAdvisoryScore(BaseModel):
    provider: str | None = None
    score: GradeAlias | None = None
    confidence: Literal["low", "medium", "high"] | None = None
    status: AIAdvisoryStatus
    summary: str | None = None
    findings: list[CodeScoreFinding] = Field(default_factory=list)
    raw_path: str | None = None


class ModuleScore(BaseModel):
    module: str
    grade: GradeAlias
    findings: list[CodeScoreFinding] = Field(default_factory=list)
    historical_health_grade: GradeAlias | None = None
    worsens_historical_findings: bool = False


class CodeScoreReport(BaseModel):
    schema_version: str = "1"
    mode: ScoreMode
    generated_at: datetime
    source_sha: str
    base_ref: str | None = None
    head_ref: str | None = None
    modules: list[ModuleScore]
    deterministic_final_grade: GradeAlias
    ai_advisory: AIAdvisoryScore | None = None
    blocks_merge: bool
    reason: str
    audit_report: AuditReport


class ToolReportBundle(BaseModel):
    signals: list[ToolSignal] = Field(default_factory=list)
    report_paths: list[str] = Field(default_factory=list)


class AIAdvisoryInput(BaseModel):
    diff: str
    touched_files: dict[str, str]
    deterministic_report: CodeScoreReport
    max_chars: int = 120_000


_FATAL_TOOLS = {"syntax", "pytest", "mypy", "pyright", "import-linter", "pip-audit", "ruff", "ruff-s", "security"}


def _to_tool_status(value: Any) -> ToolStatus:
    if value in {"passed", "failed", "skipped", "missing"}:
        return value
    return "passed"


def _normalize_path(path: str | Path, repo_root: Path | None = None) -> str:
    candidate = Path(path)
    if repo_root is not None:
        with contextlib.suppress(OSError):
            candidate = candidate.resolve().relative_to(repo_root.resolve())
    return str(candidate).replace("\\", "/")


def _normalize_module_path(path: str, repo_root: Path) -> str:
    normalized = _normalize_path(path, repo_root)
    if normalized.endswith("/__init__.py"):
        return normalized[:-12]
    return normalized


def _is_in_module(module: str, signal: ToolSignal, repo_root: Path) -> bool:
    if not signal.path:
        return False
    normalized_module = _normalize_module_path(module, repo_root)
    normalized_signal = _normalize_path(signal.path, repo_root)
    if normalized_signal == normalized_module:
        return True
    return normalized_signal.startswith(normalized_module + "/") or normalized_signal.startswith(normalized_module + ":")


def _normalize_tool_payload(payload: Any, source: str) -> list[ToolSignal]:
    signals: list[ToolSignal] = []
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            signals.append(
                ToolSignal(
                    tool=str(item.get("tool", source)),
                    status=_to_tool_status(item.get("status", "passed")),
                    severity=str(item.get("severity", "info"))
                    if str(item.get("severity", "info")) in {"info", "warning", "error"}
                    else "info",
                    path=str(item.get("path")) if item.get("path") else None,
                    subject=str(item.get("rule")) or str(item.get("source")) or None,
                    message=str(item.get("message", "tool finding")),
                    raw=item,
                )
            )
        return signals

    if not isinstance(payload, dict):
        return signals

    # Common ruff-like object: {"results":[{...}],"summary":...}
    if "results" in payload and isinstance(payload["results"], list):
        for item in payload["results"]:
            if not isinstance(item, dict):
                continue
            loc = item.get("location", {})
            path = loc.get("path") if isinstance(loc, dict) else item.get("path")
            status = "passed" if item.get("kind") in {None, "fixed", "no-issues"} else "failed"
            message = str(item.get("message", item.get("description", "")))
            signals.append(
                ToolSignal(
                    tool=source,
                    status=_to_tool_status(status),
                    severity="error" if item.get("kind") in {"error", "F"} else "warning",
                    path=str(path) if path else None,
                    subject=str(item.get("code", "")) or None,
                    message=message,
                    raw=item,
                )
            )
        return signals

    # Generic envelope: {"status":"failed","findings":[...]}
    if "findings" in payload and isinstance(payload["findings"], list):
        for item in payload["findings"]:
            if not isinstance(item, dict):
                continue
            signals.append(
                ToolSignal(
                    tool=str(payload.get("tool", source)),
                    status=_to_tool_status(item.get("status", payload.get("status", "passed"))),
                    severity=str(item.get("severity", "info"))
                    if str(item.get("severity", "info")) in {"info", "warning", "error"}
                    else "info",
                    path=str(item.get("path")) if item.get("path") else None,
                    subject=str(item.get("subject", "")) or None,
                    message=str(item.get("message", "")),
                    raw=item,
                )
            )
        return signals

    # Tool envelope fallback.
    signals.append(
        ToolSignal(
            tool=source,
            status=_to_tool_status(payload.get("status", "passed")),
            severity="error" if payload.get("status") == "failed" else "info",
            message=str(payload.get("message", payload.get("summary", "")) or f"{source} report produced findings"),
            raw=payload if isinstance(payload, dict) else {},
        )
    )
    return signals


def collect_tool_reports(
    repo_root: Path,
    *,
    report_paths: Sequence[Path] | None = None,
    include_missing: bool = True,
) -> ToolReportBundle:
    repo_root = repo_root.resolve()
    if report_paths is None:
        candidate_paths = [
            repo_root / ".qa-tool-report.json",
            repo_root / ".ruff.json",
            repo_root / "reports" / "ruff.json",
            repo_root / "reports" / "mypy.json",
            repo_root / "reports" / "pytest.json",
            repo_root / "reports" / "import-linter.json",
            repo_root / "reports" / "pip-audit.json",
            repo_root / "reports" / "pyright.json",
        ]
    else:
        candidate_paths = [Path(path) for path in report_paths]

    normalized_paths: list[str] = []
    all_signals: list[ToolSignal] = []
    for path in candidate_paths:
        normalized_paths.append(_normalize_path(path, repo_root))
        if not path.exists():
            if include_missing:
                all_signals.append(
                    ToolSignal(
                        tool=path.stem or "unknown",
                        status="missing",
                        severity="info",
                        message=f"Missing report file: {path}",
                        raw={"path": str(path)},
                    )
                )
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            all_signals.append(
                ToolSignal(
                    tool=path.stem or "unknown",
                    status="failed",
                    severity="error",
                    message=f"Invalid JSON report file: {path}",
                    raw={"path": str(path)},
                )
            )
            continue
        all_signals.extend(_normalize_tool_payload(payload, source=path.stem))

    return ToolReportBundle(signals=all_signals, report_paths=normalized_paths)


def changed_modules(
    repo_root: Path,
    *,
    base_ref: str | None = None,
    head_ref: str = "HEAD",
) -> list[str]:
    repo_root = repo_root.resolve()
    if base_ref is None:
        command = ["git", "diff", "--name-only", head_ref]
    else:
        command = ["git", "diff", "--name-only", base_ref, head_ref]
    proc = subprocess.run(command, cwd=str(repo_root), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return []

    changed: list[str] = []
    for line in proc.stdout.splitlines():
        entry = line.strip().replace("\\", "/")
        if not entry.endswith(".py"):
            continue
        if "/test" in ("/" + entry) or entry.startswith("tests/") or "/tests/" in ("/" + entry):
            continue
        if entry.startswith(".git/") or "site-packages/" in entry:
            continue
        changed.append(entry)
    return sorted(set(changed))


def _should_fail_for_signal(signal: ToolSignal) -> bool:
    if signal.status != "failed":
        return False
    if signal.severity not in {"error", "warning"}:
        return False
    return signal.tool in _FATAL_TOOLS or signal.severity == "error"


def score_module(
    module: str,
    *,
    repo_root: Path,
    tool_reports: ToolReportBundle,
    base_ref: str | None = None,
    head_ref: str = "HEAD",
    module_health: ModuleScore | None = None,
) -> ModuleScore:
    del base_ref, head_ref
    repo_root = repo_root.resolve()
    module_path = repo_root / module
    findings: list[CodeScoreFinding] = []
    grade: GradeAlias = "A"

    try:
        source = module_path.read_text(encoding="utf-8")
        compile(source, str(module_path), "exec")
    except OSError:
        findings.append(
            CodeScoreFinding(
                id=f"missing-file:{module}",
                grade_impact="A",
                reason="Module was removed or is not present in this ref; no deterministic score applied.",
                path=module,
                source_tool="module-presence",
                introduced_by_change=True,
                blocks_merge=False,
            )
        )
        return ModuleScore(
            module=module,
            grade="A",
            findings=findings,
            historical_health_grade=module_health.grade if module_health is not None else None,
            worsens_historical_findings=False,
        )
    except SyntaxError as exc:
        findings.append(
            CodeScoreFinding(
                id=f"syntax:{module}:{exc.lineno or 1}",
                grade_impact="F",
                reason="SyntaxError while compiling module.",
                path=module,
                source_tool="syntax",
                introduced_by_change=True,
                blocks_merge=True,
            )
        )
        grade = "F"

    for signal in tool_reports.signals:
        if not _is_in_module(module, signal, repo_root):
            continue
        if not _should_fail_for_signal(signal):
            continue
        impact: GradeAlias = "F" if signal.tool in _FATAL_TOOLS or signal.severity == "error" else "D"
        findings.append(
            CodeScoreFinding(
                id=f"{signal.tool}:{signal.subject or signal.path or module}",
                grade_impact=impact,
                reason=signal.message,
                path=signal.path,
                symbol=signal.subject,
                source_tool=signal.tool,
                introduced_by_change=True,
                blocks_merge=impact == "F",
            )
        )
        grade = better_grade(grade, impact)

    historical: GradeAlias | None = module_health.grade if module_health is not None else None
    worsens = False
    if module_health is not None and findings:
        # If historical findings exist and we find at least one corresponding
        # module-level blocking finding, treat it as a worsening signal.
        worsens = any(item.blocks_merge for item in findings)

    return ModuleScore(
        module=module,
        grade=grade,
        findings=findings,
        historical_health_grade=historical,
        worsens_historical_findings=worsens,
    )


def _load_module_health_report(path: Path, repo_root: Path) -> dict[str, ModuleScore]:
    del repo_root
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    modules = payload.get("modules", []) if isinstance(payload, dict) else []
    out: dict[str, ModuleScore] = {}
    for item in modules:
        if not isinstance(item, dict):
            continue
        try:
            score = ModuleScore.model_validate(item)
        except Exception:
            continue
        out[score.module] = score
    return out


def _build_audit_report(modules: list[ModuleScore], source_sha: str) -> AuditReport:
    findings: list[AuditFinding] = []
    for module_score in modules:
        for item in module_score.findings:
            findings.append(
                as_finding(
                    tool="code_score",
                    severity="error" if item.blocks_merge else "warning",
                    finding_class="code-score",
                    message=item.reason,
                    path=item.path,
                    line=None,
                    subject=item.source_tool,
                )
            )
    status: Literal["passed", "failed", "skipped", "error"] = "failed" if any(finding.severity == "error" for finding in findings) else "passed"
    return AuditReport(
        tool="code_score",
        status=status,
        generated_at=now_utc(),
        source_sha=source_sha,
        findings=findings,
        summary={
            "module_count": len(modules),
            "modules": [item.module for item in modules],
            "schema_dependency": schema_dependency_note(),
        },
    )


def _load_diff(repo_root: Path, base_ref: str | None, head_ref: str) -> str:
    command = ["git", "diff", head_ref] if base_ref is None else ["git", "diff", base_ref, head_ref]
    proc = subprocess.run(command, cwd=str(repo_root), capture_output=True, text=True, check=False)
    return proc.stdout if proc.returncode == 0 else ""


def _score_to_grade(score: float, failed_signals: int) -> GradeAlias:
    if failed_signals > 0:
        return "F"
    return "A" if score >= 0.95 else "B" if score >= 0.85 else "C" if score >= 0.70 else "D"


def score_changed_modules(
    repo_root: Path,
    *,
    base_ref: str | None = None,
    head_ref: str = "HEAD",
    mode: Literal["fast", "full"] = "fast",
    tool_reports: ToolReportBundle | None = None,
    module_health_path: Path | None = None,
    ai_advisory: bool = False,
    ai_provider: Literal["codex", "claude"] | None = None,
    output_path: Path | None = None,
) -> CodeScoreReport:
    repo_root = repo_root.resolve()
    modules = changed_modules(repo_root, base_ref=base_ref, head_ref=head_ref)
    reports = tool_reports if tool_reports is not None else collect_tool_reports(repo_root=repo_root)

    health = _load_module_health_report(module_health_path, repo_root) if module_health_path else {}
    module_scores = [
        score_module(
            module=module,
            repo_root=repo_root,
            tool_reports=reports,
            module_health=health.get(module),
        )
        for module in modules
    ]

    final_grade: GradeAlias = "A"
    for module_score in module_scores:
        final_grade = better_grade(final_grade, module_score.grade)

    # Historical module F should not solely block safe changes that do not worsen
    # known findings.
    has_historical = any(item.historical_health_grade is not None for item in module_scores)
    if (
        final_grade == "F"
        and has_historical
        and module_scores
        and all(not item.worsens_historical_findings for item in module_scores)
    ):
        final_grade = "C"

    audit_report = _build_audit_report(module_scores, source_sha=git_sha(repo_root))
    blocks_merge = audit_report.blocks_merge

    if mode == "full" and audit_report.findings:
        final_grade = better_grade(final_grade, _score_to_grade(1.0, len(audit_report.findings)))

    report = CodeScoreReport(
        schema_version="1",
        mode=mode,
        generated_at=now_utc(),
        source_sha=git_sha(repo_root),
        base_ref=base_ref,
        head_ref=head_ref,
        modules=module_scores,
        deterministic_final_grade=final_grade,
        ai_advisory=AIAdvisoryScore(status="disabled", provider=ai_provider, findings=[]),
        blocks_merge=blocks_merge,
        reason=f"scored ({schema_dependency_note()})",
        audit_report=audit_report,
    )

    if ai_advisory:
        report.ai_advisory = run_ai_advisory(
            AIAdvisoryInput(
                diff="\n".join(_split_diff_hunks(_load_diff(repo_root=repo_root, base_ref=base_ref, head_ref=head_ref))),
                touched_files={module: "changed" for module in modules},
                deterministic_report=report,
            ),
            provider=ai_provider,
        )
    else:
        report.ai_advisory = AIAdvisoryScore(status="disabled", provider=ai_provider, findings=[])

    if output_path is not None:
        write_report(report, output_path)
    return report


def _split_diff_hunks(diff_text: str) -> list[str]:
    return [
        line.strip()
        for line in diff_text.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]


def _advisor_command(provider: Literal["codex", "claude"]) -> list[str] | None:
    if provider == "codex":
        path = shutil.which("codex")
        if not path:
            return None
        return [path, "run", "--json", "scieasy-code-score-review"]
    if provider == "claude":
        path = shutil.which("claude")
        if not path:
            return None
        return [path, "--output-format", "json"]
    return None


def run_ai_advisory(
    advisory_input: AIAdvisoryInput,
    *,
    provider: Literal["codex", "claude"] | None,
    timeout_seconds: int = 60,
) -> AIAdvisoryScore:
    if provider is None:
        return AIAdvisoryScore(status="disabled", findings=[])
    command = _advisor_command(provider)
    if command is None:
        return AIAdvisoryScore(status="skipped-missing-cli", provider=provider, findings=[])

    try:
        payload = advisory_input.model_dump_json()
        proc = subprocess.run(
            command,
            input=payload if len(payload) <= advisory_input.max_chars else payload[: advisory_input.max_chars],
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return AIAdvisoryScore(status="skipped-timeout", provider=provider, findings=[])
    except FileNotFoundError:
        return AIAdvisoryScore(status="skipped-missing-cli", provider=provider, findings=[])

    if proc.returncode != 0:
        return AIAdvisoryScore(status="skipped-nonzero", provider=provider, findings=[])

    if not proc.stdout:
        return AIAdvisoryScore(status="skipped-invalid-json", provider=provider, findings=[])

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return AIAdvisoryScore(status="skipped-invalid-json", provider=provider, findings=[])

    return AIAdvisoryScore(
        status="completed",
        provider=provider,
        score=payload.get("score"),
        confidence=payload.get("confidence"),
        summary=str(payload.get("summary", "")) or None,
        findings=[],
        raw_path=payload.get("raw_path"),
    )


def score_module_health(
    repo_root: Path,
    *,
    modules: Sequence[str] | None = None,
    output_path: Path = Path("docs/audit/code-score/module-health/latest.json"),
) -> CodeScoreReport:
    repo_root = repo_root.resolve()
    if modules is None:
        modules = [
            str(path.relative_to(repo_root)).replace("\\", "/")
            for path in repo_root.rglob("*.py")
            if "test" not in path.name.lower()
            and not path.name.startswith("__")
            and ".git/" not in str(path)
        ]
    reports = collect_tool_reports(repo_root=repo_root)
    scores = [
        score_module(
            module=module,
            repo_root=repo_root,
            tool_reports=reports,
            module_health=None,
        )
        for module in modules
    ]
    final_grade: GradeAlias = "A"
    for score in scores:
        final_grade = better_grade(final_grade, score.grade)

    report = CodeScoreReport(
        schema_version="1",
        mode="module-health",
        generated_at=now_utc(),
        source_sha=git_sha(repo_root),
        modules=scores,
        deterministic_final_grade=final_grade,
        ai_advisory=AIAdvisoryScore(status="disabled", provider=None, findings=[]),
        blocks_merge=False,
        reason=f"module health snapshot ({schema_dependency_note()})",
        audit_report=_build_audit_report(scores, source_sha=git_sha(repo_root)),
    )
    write_report(report, output_path)
    return report


def write_report(report: CodeScoreReport, path: Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ADR-042 code score CLI.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--changed", action="store_true", help="Run changed-module scoring.")
    action.add_argument("--module-health", action="store_true", help="Run module-health scoring.")
    parser.add_argument("--fast", action="store_true", help="Run changed mode='fast' (default).")
    parser.add_argument("--full", action="store_true", help="Run changed mode='full'.")
    parser.add_argument("--base", default=None)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--module-health-modules", nargs="*", default=None)
    parser.add_argument("--module-health-report", default=None)
    parser.add_argument("--write", default=None)
    parser.add_argument("--ai-advisory", action="store_true")
    parser.add_argument("--ai-provider", choices=["codex", "claude"], default=None)
    parser.add_argument("--format", default="text", choices=["json", "text"])
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args()


def _run_changed_cli(args: argparse.Namespace) -> CodeScoreReport:
    mode: Literal["fast", "full"] = "full" if args.full else "fast"
    output = Path(args.write or ".git/scieasy/code-score/changed.json")
    return score_changed_modules(
        repo_root=Path(args.repo_root),
        base_ref=args.base,
        head_ref=args.head,
        mode=mode,
        module_health_path=Path(args.module_health_report) if args.module_health_report else None,
        ai_advisory=args.ai_advisory,
        ai_provider=args.ai_provider,
        output_path=output,
    )


def _run_module_health_cli(args: argparse.Namespace) -> CodeScoreReport:
    output = Path(args.write or "docs/audit/code-score/module-health/latest.json")
    return score_module_health(
        repo_root=Path(args.repo_root),
        modules=args.module_health_modules,
        output_path=output,
    )


def _run_cli(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.changed:
        report = _run_changed_cli(args)
        if args.format == "json":
            print(report.model_dump_json(indent=2))
        else:
            print(f"grade={report.deterministic_final_grade} blocks_merge={report.blocks_merge}")
        return 1 if report.blocks_merge else 0
    report = _run_module_health_cli(args)
    if args.format == "json":
        print(report.model_dump_json(indent=2))
    else:
        print(f"grade={report.deterministic_final_grade} modules={len(report.modules)} mode={report.mode}")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _run_cli(argv)
    except Exception:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
