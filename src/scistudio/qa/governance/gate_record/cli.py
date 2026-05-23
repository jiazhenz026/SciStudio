"""Argparse CLI for ``python -m scistudio.qa.governance.gate_record``.

Wires every subcommand to the matching mutator (``stages.*``) or validator
(``validation.*``). The dispatch logic is intentionally a thin shell so the
behavior surface stays identical to the pre-refactor single-file module
(ADR-042 hooks and CI scripts hard-code these subcommand names).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from scistudio.qa.governance.gate_record.io import (
    _load_record,
    _parse_issue_numbers,
    verify_provenance_hash,
)
from scistudio.qa.governance.gate_record.paths import _normalize_path
from scistudio.qa.governance.gate_record.stages import (
    admin_label_add_record,
    admin_label_remove_record,
    amend_record,
    check_record,
    docs_record,
    docs_remove_record,
    finalize_record,
    issue_add_record,
    issue_remove_record,
    issue_update_record,
    plan_record,
    plan_remove_record,
    provenance_rebuild_record,
    sentrux_record,
    start_record,
)
from scistudio.qa.governance.gate_record.validation import (
    _env_bypass_labels,
    check_commit_msg,
    check_pr_ready,
    check_pre_commit,
    check_pre_push,
)
from scistudio.qa.schemas.report import AuditReport

_CLI_DESCRIPTION = "Committed gate-record validation for ADR-042 Addendum 1."


def _render_text(report: AuditReport) -> str:
    if not report.findings:
        return "gate_record: pass"
    lines = ["gate_record: fail"]
    lines.extend(f"- {finding.rule_id}: {finding.message}" for finding in report.findings)
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    # ``prog="gate_record"`` keeps ``--help`` / error output stable after the
    # 2026-05-22 single-file -> sub-package refactor (#1433). Without an
    # explicit ``prog``, argparse derives the program name from
    # ``sys.argv[0]``, which is now ``__main__.py`` instead of the original
    # ``gate_record.py``; CI hooks parse human-readable error lines so
    # pinning the prog avoids a silently-changing surface.
    parser = argparse.ArgumentParser(prog="gate_record", description=_CLI_DESCRIPTION)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="create or replace a committed gate record")
    start.add_argument("--repo-root", type=Path, default=Path.cwd())
    start.add_argument("--issue", type=int, required=True)
    start.add_argument("--issue-url")
    start.add_argument("--slug", required=True)
    start.add_argument("--task-kind", required=True)
    start.add_argument("--persona", required=True)
    start.add_argument("--branch", required=True)
    start.add_argument("--owner-directive", required=True)
    start.add_argument("--include", action="append", default=[])
    start.add_argument("--exclude", action="append", default=[])
    start.add_argument("--governance-touch", action="store_true")
    start.add_argument("--record-path", "--record", dest="record_path", type=Path)

    plan = subparsers.add_parser("plan", help="record planned files, checks, and expected tests (additive by default)")
    plan.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    plan.add_argument("--planned-file", "--files", dest="planned_file", action="append", default=[])
    plan.add_argument("--required-check", "--checks", dest="required_check", action="append", default=[])
    plan.add_argument("--changed-test-path", "--tests", dest="changed_test_path", action="append", default=[])
    plan.add_argument("--docs", action="append", default=[], help="planned documentation path or N/A rationale")
    plan.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Replace planned_files/required_checks/changed_test_paths instead of merging. "
            "Use only when intentionally rewriting the plan from scratch (Issue #1498 default = additive merge)."
        ),
    )

    plan_remove = subparsers.add_parser("plan-remove", help="remove specific plan entries (Issue #1498)")
    plan_remove.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    plan_remove.add_argument("--planned-file", "--files", dest="planned_file", action="append", default=[])
    plan_remove.add_argument("--required-check", "--checks", dest="required_check", action="append", default=[])
    plan_remove.add_argument("--changed-test-path", "--tests", dest="changed_test_path", action="append", default=[])

    amend = subparsers.add_parser("amend", help="append a scope amendment")
    amend.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    amend.add_argument("--reason", required=True)
    amend.add_argument("--include", action="append", default=[])
    amend.add_argument("--exclude", action="append", default=[])
    amend.add_argument("--approved-by")
    amend.add_argument(
        "--governance-touch",
        action="store_true",
        help=(
            "flip the record's governance_touch flag to True. Use when the "
            "amendment brings real governance code under the gate scope and "
            "the original start did not set --governance-touch."
        ),
    )

    docs = subparsers.add_parser("docs", help="record documentation landing (additive by default)")
    docs.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    docs.add_argument("--updated", action="append", default=[])
    docs.add_argument("--na", action="append", default=[], help="N/A rationale as KEY=VALUE or KEY:VALUE")
    docs.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Replace docs_landing instead of merging. "
            "Use only when intentionally rewriting the docs landing (Issue #1498 default = additive merge)."
        ),
    )

    docs_remove = subparsers.add_parser("docs-remove", help="remove specific docs-landing entries (Issue #1498)")
    docs_remove.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    docs_remove.add_argument("--updated", action="append", default=[])
    docs_remove.add_argument("--na", action="append", default=[], help="N/A class key to remove")

    issue_add = subparsers.add_parser("issue-add", help="add a new issue reference (Issue #1498)")
    issue_add.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    issue_add.add_argument("--number", type=int, required=True)
    issue_add.add_argument("--url")
    issue_add.add_argument("--close-in-pr", dest="close_in_pr", action="store_true", default=True)
    issue_add.add_argument("--no-close-in-pr", dest="close_in_pr", action="store_false")
    issue_add.add_argument("--followup-rationale")

    issue_update = subparsers.add_parser("issue-update", help="update an existing issue reference (Issue #1498)")
    issue_update.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    issue_update.add_argument("--number", type=int, required=True)
    issue_update.add_argument("--url")
    issue_update.add_argument(
        "--close-in-pr",
        dest="close_in_pr",
        action="store_const",
        const=True,
        default=None,
    )
    issue_update.add_argument(
        "--no-close-in-pr",
        dest="close_in_pr",
        action="store_const",
        const=False,
    )
    issue_update.add_argument("--followup-rationale")

    issue_remove = subparsers.add_parser("issue-remove", help="remove an issue reference (Issue #1498)")
    issue_remove.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    issue_remove.add_argument("--number", type=int, required=True)
    issue_remove.add_argument("--reason", required=True)

    admin_label_add = subparsers.add_parser(
        "admin-label-add", help="record an expected admin override label (Issue #1498)"
    )
    admin_label_add.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    admin_label_add.add_argument("--label", required=True)
    admin_label_add.add_argument("--reason", required=True)
    admin_label_add.add_argument("--approved-by", dest="approved_by")

    admin_label_remove = subparsers.add_parser(
        "admin-label-remove", help="remove an admin override label entry (Issue #1498)"
    )
    admin_label_remove.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    admin_label_remove.add_argument("--label", required=True)
    admin_label_remove.add_argument("--reason", required=True)

    provenance_show = subparsers.add_parser("provenance-show", help="display the provenance audit log (Issue #1498)")
    provenance_show.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    provenance_show.add_argument("--format", choices=("text", "json"), default="text")

    provenance_verify = subparsers.add_parser(
        "provenance-verify",
        help="verify head_content_hash matches current content; detect direct JSON edits (Issue #1498)",
    )
    provenance_verify.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)

    provenance_rebuild = subparsers.add_parser(
        "provenance-rebuild",
        help="rebuild head_content_hash after a legitimate out-of-band edit (Issue #1498)",
    )
    provenance_rebuild.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    provenance_rebuild.add_argument("--reason", required=True)
    provenance_rebuild.add_argument("--approved-by", dest="approved_by")

    check = subparsers.add_parser("check", help="record a check result or full-audit evidence")
    check.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    check.add_argument("--name", default="full_audit")
    check.add_argument("--command-or-tool", "--command", dest="command_or_tool", required=True)
    check.add_argument("--status", choices=("pass", "fail", "skipped", "unknown"), required=True)
    check.add_argument("--exit-code", type=int)
    check.add_argument("--output-path", "--output", dest="output_path")
    check.add_argument("--full-audit", action="store_true")
    check.add_argument("--blocks-merge", action="store_true")
    check.add_argument("--known-debt", action="append", default=[])
    check.add_argument("--unclassified-failure", action="append", default=[])

    sentrux = subparsers.add_parser("sentrux", help="record Sentrux free-tier evidence")
    sentrux.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    sentrux.add_argument("--command-or-tool", "--command", dest="command_or_tool", default="sentrux check")
    sentrux.add_argument("--mode", choices=("free-tier",), default="free-tier")
    sentrux.add_argument("--status", choices=("pass", "fail", "skipped", "unknown"), required=True)
    sentrux.add_argument("--evidence", dest="output_path")
    sentrux.add_argument("--rules-checked", type=int)
    sentrux.add_argument("--total-rules-defined", type=int)
    sentrux.add_argument("--quality-signal", type=float)
    sentrux.add_argument("--threshold", action="append", default=[], help="threshold as KEY=VALUE")
    sentrux.add_argument("--output-path")

    finalize = subparsers.add_parser("finalize", help="record final commit and PR provenance")
    finalize.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    finalize.add_argument("--commit-sha", "--commit", dest="commit_sha", action="append", default=[])
    finalize.add_argument("--pr-number", type=int)
    finalize.add_argument("--pr-url", "--pr", dest="pr_url")
    finalize.add_argument("--body-closes-issue", "--closes", dest="body_closes_issue", action="append", default=[])

    pre_commit = subparsers.add_parser("pre-commit", help="validate staged files against a gate record")
    pre_commit.add_argument("--repo-root", type=Path, default=Path.cwd())
    pre_commit.add_argument("--gate-record", "--record", dest="gate_record", type=Path)
    pre_commit.add_argument("--staged", action="store_true", help="kept for hook compatibility")
    pre_commit.add_argument("--bypass-label", action="append", default=[])

    commit_msg = subparsers.add_parser("commit-msg", help="validate commit-message trailers")
    commit_msg.add_argument("message_file", type=Path)
    commit_msg.add_argument("--bypass-label", action="append", default=[])

    ci = subparsers.add_parser("ci", help="validate a committed gate record against PR metadata")
    ci.add_argument("--repo-root", type=Path, default=Path.cwd())
    ci.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    ci.add_argument("--base", default="origin/main")
    ci.add_argument("--head", default="HEAD")
    ci.add_argument("--pr-body", default="")
    ci.add_argument("--pr-label", action="append", default=[])
    ci.add_argument("--format", choices=("text", "json"), default="text")

    pre_push = subparsers.add_parser("pre-push", help="validate local branch diff before push")
    pre_push.add_argument("--repo-root", type=Path, default=Path.cwd())
    pre_push.add_argument("--gate-record", "--record", dest="gate_record", type=Path)
    pre_push.add_argument("--base", default="origin/main")
    pre_push.add_argument("--head", default="HEAD")
    pre_push.add_argument("--format", choices=("text", "json"), default="text")
    pre_push.add_argument("--bypass-label", action="append", default=[])

    pr_ready = subparsers.add_parser("pr-ready", help="validate local PR readiness before gh pr create")
    pr_ready.add_argument("--repo-root", type=Path, default=Path.cwd())
    pr_ready.add_argument("--gate-record", "--record", dest="gate_record", type=Path)
    pr_ready.add_argument("--base", default="origin/main")
    pr_ready.add_argument("--head", default="HEAD")
    pr_ready.add_argument("--pr-body", default="")
    pr_ready.add_argument("--pr-label", action="append", default=[])
    pr_ready.add_argument("--format", choices=("text", "json"), default="text")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            output_path = start_record(
                repo_root=args.repo_root,
                issue_number=args.issue,
                issue_url=args.issue_url,
                slug=args.slug,
                task_kind=args.task_kind,
                persona=args.persona,
                branch=args.branch,
                owner_directive=args.owner_directive,
                include=args.include,
                exclude=args.exclude,
                governance_touch=args.governance_touch,
                record_path=args.record_path,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "plan":
            output_path = plan_record(
                args.gate_record,
                planned_files=args.planned_file,
                required_checks=args.required_check,
                changed_test_paths=args.changed_test_path,
                replace=args.replace,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "plan-remove":
            output_path = plan_remove_record(
                args.gate_record,
                planned_files=args.planned_file,
                required_checks=args.required_check,
                changed_test_paths=args.changed_test_path,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "amend":
            output_path = amend_record(
                args.gate_record,
                reason=args.reason,
                include=args.include,
                exclude=args.exclude,
                approved_by=args.approved_by,
                governance_touch=True if args.governance_touch else None,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "docs":
            output_path = docs_record(
                args.gate_record,
                updated=args.updated,
                na=args.na,
                replace=args.replace,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "docs-remove":
            output_path = docs_remove_record(args.gate_record, updated=args.updated, na=args.na)
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "issue-add":
            output_path = issue_add_record(
                args.gate_record,
                number=args.number,
                url=args.url,
                close_in_pr=args.close_in_pr,
                followup_rationale=args.followup_rationale,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "issue-update":
            output_path = issue_update_record(
                args.gate_record,
                number=args.number,
                url=args.url,
                close_in_pr=args.close_in_pr,
                followup_rationale=args.followup_rationale,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "issue-remove":
            output_path = issue_remove_record(
                args.gate_record,
                number=args.number,
                reason=args.reason,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "admin-label-add":
            output_path = admin_label_add_record(
                args.gate_record,
                label=args.label,
                reason=args.reason,
                approved_by=args.approved_by,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "admin-label-remove":
            output_path = admin_label_remove_record(
                args.gate_record,
                label=args.label,
                reason=args.reason,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "provenance-rebuild":
            output_path = provenance_rebuild_record(
                args.gate_record,
                reason=args.reason,
                approved_by=args.approved_by,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "provenance-show":
            record = _load_record(args.gate_record)
            provenance = record.provenance
            if provenance is None:
                if args.format == "json":
                    print(json.dumps({"provenance": None}, indent=2))
                else:
                    print("provenance: not recorded (pre-Issue-#1498 record)")
                return 0
            if args.format == "json":
                print(json.dumps(provenance.model_dump(mode="json"), indent=2, sort_keys=True))
            else:
                print(f"head_content_hash: {provenance.head_content_hash}")
                print(f"mutations: {len(provenance.mutations)}")
                for index, mutation in enumerate(provenance.mutations, 1):
                    print(
                        f"  {index}. [{mutation.timestamp.isoformat()}] {mutation.subcommand} "
                        f"-> {mutation.content_hash_after[:14]}..."
                    )
                    if mutation.summary:
                        print(f"     summary: {dict(mutation.summary)}")
            return 0
        if args.command == "provenance-verify":
            record = _load_record(args.gate_record)
            is_valid, computed = verify_provenance_hash(record)
            if record.provenance is None:
                print("provenance-verify: skipped (no provenance field; pre-Issue-#1498 record)")
                return 0
            if is_valid:
                print(f"provenance-verify: pass (head_content_hash={record.provenance.head_content_hash})")
                return 0
            print("provenance-verify: fail (direct edit detected)", file=sys.stderr)
            print(f"  stored:   {record.provenance.head_content_hash}", file=sys.stderr)
            print(f"  computed: {computed}", file=sys.stderr)
            return 1
        if args.command == "check":
            output_path = check_record(
                args.gate_record,
                name=args.name,
                command_or_tool=args.command_or_tool,
                status=args.status,
                exit_code=args.exit_code,
                output_path=args.output_path,
                full_audit=args.full_audit,
                blocks_merge=args.blocks_merge if args.full_audit else None,
                known_debt=args.known_debt,
                unclassified_failure=args.unclassified_failure,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "sentrux":
            output_path = sentrux_record(
                args.gate_record,
                command_or_tool=args.command_or_tool,
                status=args.status,
                rules_checked=args.rules_checked,
                total_rules_defined=args.total_rules_defined,
                quality_signal=args.quality_signal,
                threshold=args.threshold,
                output_path=args.output_path,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "finalize":
            output_path = finalize_record(
                args.gate_record,
                commit_sha=args.commit_sha,
                pr_number=args.pr_number,
                pr_url=args.pr_url,
                body_closes_issue=_parse_issue_numbers(args.body_closes_issue),
            )
            print(_normalize_path(str(output_path)))
            return 0
    except (OSError, ValidationError, ValueError) as exc:
        print(f"gate_record {args.command} failed: {exc}", file=sys.stderr)
        return 1

    if args.command == "pre-commit":
        report = check_pre_commit(
            args.repo_root,
            gate_record=args.gate_record,
            bypass_labels=[*args.bypass_label, *_env_bypass_labels()],
        )
    elif args.command == "commit-msg":
        report = check_commit_msg(args.message_file, bypass_labels=[*args.bypass_label, *_env_bypass_labels()])
    elif args.command == "pre-push":
        report = check_pre_push(
            args.repo_root,
            gate_record=args.gate_record,
            base=args.base,
            head=args.head,
            bypass_labels=[*args.bypass_label, *_env_bypass_labels()],
        )
    elif args.command == "pr-ready":
        report = check_pr_ready(
            args.repo_root,
            gate_record=args.gate_record,
            base=args.base,
            head=args.head,
            pr_body=args.pr_body,
            pr_labels=[*args.pr_label, *_env_bypass_labels()],
        )
    else:
        # ADR-042 Addendum 5: the CI subcommand is the local/CI shared
        # orchestration surface. Keep pre-push/pr-ready structural, but make
        # `ci` include the same blocking guard classes the workflow uses.
        from scistudio.qa.governance.gate_record.workflow import run_ci

        report = run_ci(
            repo_root=args.repo_root,
            gate_record=args.gate_record,
            base=args.base,
            head=args.head,
            pr_body=args.pr_body,
            pr_labels=args.pr_label,
        )

    if getattr(args, "format", "text") == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print(_render_text(report))
    return 1 if report.blocks_merge else 0
