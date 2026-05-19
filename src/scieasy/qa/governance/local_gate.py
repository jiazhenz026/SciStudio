"""Local ADR-042 gate sessions for AI-authored commits."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa.audit._cli import exit_code, print_report

TaskKind = Literal["hotfix", "bugfix", "feature", "docs", "maintenance", "manager"]
Persona = Literal["manager", "implementer", "adr_author", "audit_reviewer"]
GateStage = Literal["scope", "issue", "implement", "test_and_checks", "documentation_landing", "commit"]

GOVERNANCE_GLOBS = (
    "AGENTS.md",
    "docs/adr/ADR-042.md",
    "docs/specs/adr-042-*.md",
    ".pre-commit-config.yaml",
    ".github/workflows/**",
    ".claude/**",
    ".codex/**",
    ".agents/**",
    ".gemini/**",
)


class GateScope(BaseModel):
    include: list[str]
    exclude: list[str] = Field(default_factory=list)


class CheckResult(BaseModel):
    command: str
    exit_code: int
    timestamp: datetime
    output_path: str | None = None
    summary: str | None = None


class DocsLandingRecord(BaseModel):
    docs_updated: list[str] = Field(default_factory=list)
    changelog_updated: bool | None = None
    checklist_updated: bool | None = None
    not_applicable_rationale: str | None = None


class IssueRecord(BaseModel):
    number: int
    url: str
    source: Literal["existing", "created"]
    closes: bool = False


class GateSession(BaseModel):
    session_id: str
    task_kind: TaskKind
    branch: str
    owner_directive: str
    scope: GateScope
    governance_touch: bool = False
    issues: list[IssueRecord] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    check_results: list[CheckResult] = Field(default_factory=list)
    docs_landing: DocsLandingRecord | None = None
    persona: Persona
    runtime: str
    admin_labels: list[str] = Field(default_factory=list)
    amendments: list[Mapping[str, Any]] = Field(default_factory=list)


class ActorPermission(BaseModel):
    login: str
    permission: Literal["none", "read", "triage", "write", "maintain", "admin"]


class AuthorizationSignal(BaseModel):
    operation: Literal["human-authored", "core-change", "merge", "ai-override"]
    signal_type: Literal["label", "review"]
    name: str
    actor: str
    actor_permission: ActorPermission
    created_at: datetime
    valid: bool


class PullRequestMetadata(BaseModel):
    repo: str
    number: int
    head_sha: str
    base_ref: str
    head_ref: str
    labels: list[str]
    reviews: list[Mapping[str, Any]] = Field(default_factory=list)
    commits: list[Mapping[str, Any]] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    actors: list[ActorPermission] = Field(default_factory=list)
    authorization_signals: list[AuthorizationSignal] = Field(default_factory=list)


def _git(repo_root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(repo_root), capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _current_branch(repo_root: Path) -> str:
    return _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD") or "HEAD"


def _gate_dir(repo_root: Path) -> Path:
    git_dir = _git(repo_root, "rev-parse", "--git-dir")
    base = Path(git_dir) if git_dir else repo_root / ".git"
    if not base.is_absolute():
        base = repo_root / base
    return base / "scieasy" / "gates"


def save_session(repo_root: Path, session: GateSession) -> Path:
    directory = _gate_dir(repo_root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session.session_id}.json"
    path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_session(repo_root: Path, *, session_id: str | None = None, branch: str | None = None) -> GateSession | None:
    directory = _gate_dir(repo_root)
    if not directory.exists():
        return None
    candidates = [directory / f"{session_id}.json"] if session_id else sorted(directory.glob("*.json"))
    target_branch = branch or _current_branch(repo_root)
    for path in candidates:
        if not path.exists():
            continue
        try:
            session = GateSession.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if session_id or session.branch == target_branch:
            return session
    return None


def start_session(
    repo_root: Path,
    *,
    task_kind: TaskKind,
    owner_directive: str,
    scope: GateScope,
    persona: Persona,
    runtime: str,
    branch: str | None = None,
    governance_touch: bool = False,
) -> GateSession:
    session = GateSession(
        session_id=datetime.utcnow().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8],
        task_kind=task_kind,
        branch=branch or _current_branch(repo_root),
        owner_directive=owner_directive,
        scope=scope,
        governance_touch=governance_touch,
        persona=persona,
        runtime=runtime,
    )
    save_session(repo_root, session)
    return session


def record_stage(
    repo_root: Path,
    session_id: str,
    stage: GateStage,
    data: Mapping[str, Any],
) -> GateSession:
    session = load_session(repo_root, session_id=session_id)
    if session is None:
        raise ValueError(f"unknown gate session: {session_id}")
    payload = dict(data)
    if stage == "issue":
        issue = IssueRecord.model_validate(payload)
        session.issues = [*session.issues, issue]
    elif stage == "test_and_checks":
        result = CheckResult.model_validate(payload)
        session.check_results = [*session.check_results, result]
    elif stage == "documentation_landing":
        session.docs_landing = DocsLandingRecord.model_validate(payload)
    else:
        session.amendments = [*session.amendments, {"stage": stage, "data": payload}]
    save_session(repo_root, session)
    return session


def staged_files(repo_root: Path) -> list[Path]:
    output = _git(repo_root, "diff", "--cached", "--name-only")
    return [Path(line.strip()) for line in output.splitlines() if line.strip()]


def _matches_any(path: str, patterns: Sequence[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def _docs_landing_ok(session: GateSession) -> bool:
    landing = session.docs_landing
    if landing is None:
        return False
    return bool(
        landing.not_applicable_rationale
        or landing.docs_updated
        or landing.changelog_updated
        or landing.checklist_updated
    )


def _check_evidence(session: GateSession) -> list[str]:
    missing = []
    for command in session.required_checks:
        if not any(result.command == command and result.exit_code == 0 for result in session.check_results):
            missing.append(command)
    return missing


def check_pre_commit(
    repo_root: Path,
    *,
    session_id: str | None = None,
    staged: Sequence[Path] | None = None,
):
    repo_root = repo_root.resolve()
    session = load_session(repo_root, session_id=session_id)
    findings = []
    staged_paths = [Path(item) for item in (staged if staged is not None else staged_files(repo_root))]
    if session is None:
        findings.append(
            build_finding(
                finding_id="local-gate-missing-session",
                tool="local_gate",
                finding_class="missing-session",
                severity="error",
                message="AI-authored commit has no active ADR-042 gate session.",
                remediation="Start a local gate session before committing.",
            )
        )
        return build_report(tool="local_gate", repo_root=repo_root, findings=findings)

    branch = _current_branch(repo_root)
    if session.branch != branch:
        findings.append(
            build_finding(
                finding_id="local-gate-branch-mismatch",
                tool="local_gate",
                finding_class="branch-mismatch",
                severity="error",
                message="Gate session branch does not match current branch.",
                expected=session.branch,
                actual=branch,
            )
        )
    if not session.issues:
        findings.append(
            build_finding(
                finding_id="local-gate-missing-issue",
                tool="local_gate",
                finding_class="missing-issue",
                severity="error",
                message=f"{session.task_kind} task has no linked issue.",
            )
        )
    for path in staged_paths:
        normalized = path.as_posix()
        if not _matches_any(normalized, session.scope.include) or _matches_any(normalized, session.scope.exclude):
            findings.append(
                build_finding(
                    finding_id="local-gate-scope-violation",
                    tool="local_gate",
                    finding_class="scope",
                    severity="error",
                    message=f"Staged file outside declared scope: {normalized}",
                    path=normalized,
                )
            )
        if _matches_any(normalized, GOVERNANCE_GLOBS) and "admin-approved:governance" not in session.admin_labels:
            findings.append(
                build_finding(
                    finding_id="local-gate-governance-touch",
                    tool="local_gate",
                    finding_class="governance",
                    severity="error",
                    message=f"Governance file requires admin-approved:governance: {normalized}",
                    path=normalized,
                )
            )
        try:
            staged_text = (repo_root / path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            staged_text = ""
        if "TODO(" in staged_text and "TODO(#" not in staged_text:
            findings.append(
                build_finding(
                    finding_id="local-gate-untracked-deferral",
                    tool="local_gate",
                    finding_class="untracked-deferral",
                    severity="error",
                    message=f"Deferred work must use tracked TODO(#...): {normalized}",
                    path=normalized,
                )
            )
    for command in _check_evidence(session):
        findings.append(
            build_finding(
                finding_id="local-gate-missing-check-evidence",
                tool="local_gate",
                finding_class="missing-check",
                severity="error",
                message=f"Missing passing check evidence: {command}",
                subject=command,
            )
        )
    for result in session.check_results:
        if "code-score" in result.command and result.exit_code != 0:
            findings.append(
                build_finding(
                    finding_id="local-gate-code-score-f",
                    tool="local_gate",
                    finding_class="code-score",
                    severity="error",
                    message="Deterministic code score failed.",
                    subject=result.command,
                )
            )
    if not _docs_landing_ok(session):
        findings.append(
            build_finding(
                finding_id="local-gate-missing-docs-landing",
                tool="local_gate",
                finding_class="docs-landing",
                severity="error",
                message="Gate session lacks docs/changelog/checklist landing or N/A rationale.",
            )
        )
    return build_report(tool="local_gate", repo_root=repo_root, findings=findings)


def check_commit_msg(message: str, *, require_ai_trailers: bool = True):
    findings = []
    required = ["Gate-Session", "Task-Kind", "Issue", "Assisted-by"] if require_ai_trailers else []
    for trailer in required:
        if not re_search_trailer(message, trailer):
            findings.append(
                build_finding(
                    finding_id=f"local-gate-missing-trailer-{trailer.lower()}",
                    tool="local_gate.commit_msg",
                    finding_class="missing-trailer",
                    severity="error",
                    message=f"Missing required AI trailer: {trailer}",
                    subject=trailer,
                )
            )
    return build_report(tool="local_gate.commit_msg", repo_root=Path.cwd(), findings=findings)


def re_search_trailer(message: str, trailer: str) -> bool:
    prefix = trailer.lower() + ":"
    return any(line.lower().startswith(prefix) and line.split(":", 1)[1].strip() for line in message.splitlines())


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ADR-042 local gate.")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument(
        "--kind", required=True, choices=["hotfix", "bugfix", "feature", "docs", "maintenance", "manager"]
    )
    start.add_argument("--persona", required=True, choices=["manager", "implementer", "adr_author", "audit_reviewer"])
    start.add_argument("--runtime", default="codex")
    start.add_argument("--scope", action="append", required=True)
    start.add_argument("--directive", default="ADR-042 governed task")
    record = sub.add_parser("record")
    record.add_argument("--session", required=True)
    record.add_argument("--stage", required=True)
    record.add_argument("--data", required=True)
    pre = sub.add_parser("pre-commit")
    pre.add_argument("--session")
    msg = sub.add_parser("commit-msg")
    msg.add_argument("path")
    msg.add_argument("--no-ai-trailers", action="store_true")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)

    try:
        if args.command == "start":
            session = start_session(
                Path.cwd(),
                task_kind=args.kind,
                owner_directive=args.directive,
                scope=GateScope(include=args.scope),
                persona=args.persona,
                runtime=args.runtime,
            )
            print(session.model_dump_json(indent=2))
            return 0
        if args.command == "record":
            session = record_stage(Path.cwd(), args.session, args.stage, json.loads(args.data))
            print(session.model_dump_json(indent=2))
            return 0
        if args.command == "pre-commit":
            report = check_pre_commit(Path.cwd(), session_id=args.session)
        else:
            report = check_commit_msg(
                Path(args.path).read_text(encoding="utf-8"), require_ai_trailers=not args.no_ai_trailers
            )
    except Exception as exc:
        print(f"local_gate: {exc}", file=sys.stderr)
        return 2
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(_main())
