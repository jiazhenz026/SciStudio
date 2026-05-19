"""Validate human-authored bypass provenance."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa.audit._cli import exit_code, print_report
from scieasy.qa.governance._auth import has_authorized_signal, has_label, review_authorized
from scieasy.qa.governance.local_gate import ActorPermission, AuthorizationSignal, PullRequestMetadata


def check_human_bypass(
    pr: PullRequestMetadata,
    *,
    required_label: str = "human-authored",
):
    findings = []
    if not has_label(pr, required_label):
        return build_report(tool="human_bypass_guard", repo_root=Path.cwd(), findings=[])
    if not (
        has_authorized_signal(
            pr,
            operation="human-authored",
            name=required_label,
            signal_type="label",
        )
        or review_authorized(pr.reviews)
    ):
        findings.append(
            build_finding(
                finding_id="human-bypass-unauthorized-label",
                tool="human_bypass_guard",
                finding_class="human-bypass",
                severity="error",
                message="human-authored label requires maintainer/admin provenance.",
                subject=required_label,
            )
        )
    ai_evidence = [
        commit
        for commit in pr.commits
        if "Assisted-by:" in str(commit.get("message", "")) or "Gate-Session:" in str(commit.get("message", ""))
    ]
    if ai_evidence and "admin-approved:ai-override" not in pr.labels:
        findings.append(
            build_finding(
                finding_id="human-bypass-conflicting-ai-evidence",
                tool="human_bypass_guard",
                finding_class="human-bypass",
                severity="error",
                message="human-authored label does not bypass explicit AI-authored commit evidence.",
                subject=required_label,
                evidence={"ai_commit_count": len(ai_evidence)},
            )
        )
    return build_report(tool="human_bypass_guard", repo_root=Path.cwd(), findings=findings)


def check(pr: PullRequestMetadata, *, required_label: str = "human-authored"):
    return check_human_bypass(pr, required_label=required_label)


def _permission_from_association(association: str | None) -> str:
    normalized = (association or "").upper()
    if normalized == "OWNER":
        return "admin"
    if normalized == "MEMBER":
        return "maintain"
    if normalized == "COLLABORATOR":
        return "write"
    return "read" if normalized else "none"


def _permission_from_gh(repo: str, login: str) -> ActorPermission:
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/collaborators/{login}/permission"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ActorPermission(login=login, permission="none")
    try:
        permission = str(json.loads(proc.stdout).get("permission") or "none")
    except json.JSONDecodeError:
        permission = "none"
    if permission not in {"none", "read", "triage", "write", "maintain", "admin"}:
        permission = "none"
    return ActorPermission(login=login, permission=permission)


def _gh_json(args: list[str]) -> Any:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "gh command failed")
    return json.loads(proc.stdout or "null")


def _current_repo() -> str:
    payload = _gh_json(["repo", "view", "--json", "nameWithOwner"])
    repo = str(payload.get("nameWithOwner") or "")
    if not repo:
        raise RuntimeError("unable to determine GitHub repository")
    return repo


def _label_operation(label: str) -> str | None:
    return {
        "human-authored": "human-authored",
        "admin-approved:core-change": "core-change",
        "admin-approved:merge": "merge",
        "admin-approved:ai-override": "ai-override",
    }.get(label)


def _metadata_from_gh(pr_number: int, *, repo: str | None = None) -> PullRequestMetadata:
    repo_name = repo or _current_repo()
    pr = _gh_json(
        [
            "pr",
            "view",
            str(pr_number),
            "--repo",
            repo_name,
            "--json",
            "number,headRefName,baseRefName,headRefOid,labels,reviews,commits,files",
        ]
    )
    labels = [str(label.get("name")) for label in pr.get("labels", []) if label.get("name")]
    commits = [
        {
            "oid": commit.get("oid") or commit.get("sha"),
            "message": commit.get("messageHeadline") or commit.get("message") or "",
        }
        for commit in pr.get("commits", [])
    ]
    reviews = []
    actors: dict[str, ActorPermission] = {}
    for review in pr.get("reviews", []):
        author = review.get("author") or {}
        login = str(author.get("login") or "")
        permission = _permission_from_association(review.get("authorAssociation"))
        if login:
            actor = ActorPermission(login=login, permission=permission)
            actors[login] = actor
        reviews.append(
            {
                "state": review.get("state"),
                "actor": login,
                "actor_permission": permission,
            }
        )
    signals = []
    try:
        timeline = _gh_json(
            [
                "api",
                f"repos/{repo_name}/issues/{pr_number}/timeline",
                "--paginate",
                "-H",
                "Accept: application/vnd.github+json",
            ]
        )
    except RuntimeError:
        timeline = []
    for event in timeline if isinstance(timeline, list) else []:
        if event.get("event") != "labeled":
            continue
        label = str((event.get("label") or {}).get("name") or "")
        operation = _label_operation(label)
        actor_login = str((event.get("actor") or {}).get("login") or "")
        if not operation or not actor_login:
            continue
        actor = actors.get(actor_login) or _permission_from_gh(repo_name, actor_login)
        actors[actor_login] = actor
        created = event.get("created_at") or datetime.utcnow().isoformat()
        created_at = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        signals.append(
            AuthorizationSignal(
                operation=operation,
                signal_type="label",
                name=label,
                actor=actor.login,
                actor_permission=actor,
                created_at=created_at,
                valid=True,
            )
        )
    return PullRequestMetadata(
        repo=repo_name,
        number=int(pr.get("number") or pr_number),
        head_sha=str(pr.get("headRefOid") or ""),
        base_ref=str(pr.get("baseRefName") or ""),
        head_ref=str(pr.get("headRefName") or ""),
        labels=labels,
        reviews=reviews,
        commits=commits,
        changed_files=[str(file.get("path")) for file in pr.get("files", []) if file.get("path")],
        actors=list(actors.values()),
        authorization_signals=signals,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate ADR-042 human bypass metadata.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--metadata", help="JSON file with PullRequestMetadata")
    source.add_argument("--pr", type=int, help="GitHub pull request number to inspect with gh")
    parser.add_argument("--repo", help="GitHub repository in owner/name form for --pr")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    try:
        if args.metadata:
            pr = PullRequestMetadata.model_validate(json.loads(Path(args.metadata).read_text(encoding="utf-8")))
        else:
            pr = _metadata_from_gh(args.pr, repo=args.repo)
        report = check(pr)
    except Exception as exc:
        print(f"human_bypass_guard: {exc}", file=sys.stderr)
        return 2
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
