"""Argparse CLI for ``python -m scistudio.qa.governance.gate_record``.

ADR-042 Addendum 6 workflow surface: ``init`` / ``plan`` / ``amend`` /
``check`` / ``finalize``, with ``check --mode local|pre-commit|commit-msg|
pre-push|pre-pr|ci``. Compatibility aliases (§5.8) delegate to the new code; no
alias owns a validation decision.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scistudio.qa.governance.gate_record import workflow
from scistudio.qa.governance.gate_record.labels import ADMIN_LABELS
from scistudio.qa.governance.gate_record.ledger import SUPPORTED_PERSONAS, SUPPORTED_TASK_KINDS

_MODES = ("local", "pre-commit", "commit-msg", "pre-push", "pre-pr", "ci")


def _add_field_flags(parser: argparse.ArgumentParser) -> None:
    """Add the common additive field flags shared by plan/amend/check/finalize."""

    parser.add_argument("--owner-directive", action="append", default=[])
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--issue", action="append", default=[])
    parser.add_argument("--docs-updated", action="append", default=[])
    parser.add_argument("--docs-na", action="append", default=[])
    parser.add_argument("--test-path", action="append", default=[])
    parser.add_argument("--test-na", action="append", default=[])
    parser.add_argument("--check", action="append", default=[])
    parser.add_argument("--check-na", action="append", default=[])
    parser.add_argument("--admin-label", action="append", default=[], choices=sorted(ADMIN_LABELS))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gate_record",
        description="ADR-042 Addendum 6 gate ledger workflow CLI.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)

    # init -----------------------------------------------------------------
    init = sub.add_parser("init", help="Create or update the ledger; print task instructions.")
    init.add_argument("--record")
    init.add_argument("--task-kind", required=True, choices=SUPPORTED_TASK_KINDS)
    init.add_argument("--persona", required=True, choices=SUPPORTED_PERSONAS)
    init.add_argument("--runtime", required=True)
    init.add_argument("--branch", required=True)
    init.add_argument("--owner-directive", action="append", required=True, default=[])
    init.add_argument("--slug")
    init.add_argument("--session-id")
    init.add_argument("--issue", action="append", default=[])
    init.add_argument("--include", action="append", default=[])
    init.add_argument("--exclude", action="append", default=[])
    init.add_argument("--governance-touch", type=_bool, default=None)
    init.add_argument("--print-instructions", type=_bool, default=True)
    init.add_argument("--instructions-output")

    # plan -----------------------------------------------------------------
    plan = sub.add_parser("plan", help="Append planning fields without running checks.")
    plan.add_argument("--record")
    _add_field_flags(plan)

    # amend ----------------------------------------------------------------
    amend = sub.add_parser("amend", help="Append a correction event.")
    amend.add_argument("--record")
    amend.add_argument("--reason", required=True)
    amend.add_argument("--task-kind", choices=SUPPORTED_TASK_KINDS, default=None)
    amend.add_argument("--persona", choices=SUPPORTED_PERSONAS, default=None)
    amend.add_argument("--branch", default=None)
    amend.add_argument("--remove-issue", action="append", default=[])
    amend.add_argument("--remove-include", action="append", default=[])
    amend.add_argument("--remove-exclude", action="append", default=[])
    amend.add_argument("--governance-touch", type=_bool, default=None)
    _add_field_flags(amend)

    # check ----------------------------------------------------------------
    check = sub.add_parser("check", help="Run tier-selected checks and reconcile.")
    check.add_argument("--record")
    check.add_argument("--base", default="origin/main")
    check.add_argument("--head", default="HEAD")
    check.add_argument("--mode", choices=_MODES, default="local")
    check.add_argument("--pr-body-file")
    check.add_argument("--only", action="append", default=[])
    check.add_argument("--skip-execution", action="store_true")
    _add_field_flags(check)

    # finalize -------------------------------------------------------------
    finalize = sub.add_parser("finalize", help="Record commit/PR provenance and reconcile.")
    finalize.add_argument("--record")
    finalize.add_argument("--base", default="origin/main")
    finalize.add_argument("--head", default="HEAD")
    finalize.add_argument("--commit", action="append", default=[])
    finalize.add_argument("--pr")
    finalize.add_argument("--pr-body-file")
    finalize.add_argument("--closes", action="append", default=[])
    _add_field_flags(finalize)

    # Compatibility aliases (§5.8): delegate to the new code -----------------
    _add_alias(sub, "start", "init", init)
    _add_mode_alias(sub, "pre-commit", "pre-commit")
    _add_mode_alias(sub, "pre-push", "pre-push")
    _add_mode_alias(sub, "pr-ready", "pre-pr")
    _add_mode_alias(sub, "ci", "ci")
    _add_commit_msg_alias(sub)

    return parser


def _bool(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _add_alias(sub: argparse._SubParsersAction, name: str, target: str, template: argparse.ArgumentParser) -> None:
    # ``start`` is the only init-shaped alias; reuse identical args.
    alias = sub.add_parser(name, help=f"Alias for {target}.")
    alias.add_argument("--record")
    alias.add_argument("--task-kind", required=True, choices=SUPPORTED_TASK_KINDS)
    alias.add_argument("--persona", required=True, choices=SUPPORTED_PERSONAS)
    alias.add_argument("--runtime", required=True)
    alias.add_argument("--branch", required=True)
    alias.add_argument("--owner-directive", action="append", required=True, default=[])
    alias.add_argument("--slug")
    alias.add_argument("--session-id")
    alias.add_argument("--issue", action="append", default=[])
    alias.add_argument("--include", action="append", default=[])
    alias.add_argument("--exclude", action="append", default=[])
    alias.add_argument("--governance-touch", type=_bool, default=None)
    alias.add_argument("--print-instructions", type=_bool, default=True)
    alias.add_argument("--instructions-output")
    alias.set_defaults(_alias_to="init")


def _add_mode_alias(sub: argparse._SubParsersAction, name: str, mode: str) -> None:
    alias = sub.add_parser(name, help=f"Alias for `check --mode {mode}`.")
    alias.add_argument("--record")
    alias.add_argument("--base", default="origin/main")
    alias.add_argument("--head", default="HEAD")
    alias.add_argument("--pr-body-file")
    alias.add_argument("--only", action="append", default=[])
    alias.add_argument("--skip-execution", action="store_true")
    _add_field_flags(alias)
    alias.set_defaults(_alias_to="check", _alias_mode=mode)


def _add_commit_msg_alias(sub: argparse._SubParsersAction) -> None:
    alias = sub.add_parser("commit-msg", help="Alias for `check --mode commit-msg <message-file>`.")
    alias.add_argument("message_file", nargs="?")
    alias.add_argument("--record")
    alias.add_argument("--base", default="origin/main")
    alias.add_argument("--head", default="HEAD")
    _add_field_flags(alias)
    alias.set_defaults(_alias_to="check", _alias_mode="commit-msg")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root

    alias_to = getattr(args, "_alias_to", None)
    command = alias_to or args.command

    if command == "init":
        return workflow.run_init(repo_root, args)
    if command == "plan":
        return workflow.run_plan(repo_root, args)
    if command == "amend":
        return workflow.run_amend(repo_root, args)
    if command == "check":
        alias_mode = getattr(args, "_alias_mode", None)
        return workflow.run_check(repo_root, args, mode=alias_mode)
    if command == "finalize":
        return workflow.run_finalize(repo_root, args)

    parser.error(f"unknown command: {command}")
    return workflow.EXIT_USAGE
