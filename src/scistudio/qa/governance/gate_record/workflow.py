"""Workflow command implementations for ADR-042 Addendum 6 (spec §5).

Thin orchestration over the evaluator and append-only ledger I/O. Implements
``init`` / ``plan`` / ``amend`` / ``check`` / ``finalize`` and the ``--mode``
dispatch. Every command appends events; none rewrites or deletes prior events.

Exit codes (spec §5.7):
    0 reconciliation passed | 1 reconciliation failed | 2 invalid usage |
    3 ledger schema/migration error | 4 required tool unavailable, no N/A |
    5 sanitization violation in a would-be-committed event.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pydantic

import scistudio.qa.governance.gate_record.evaluator as evaluator
import scistudio.qa.governance.gate_record.io as io
from scistudio.qa.governance.gate_record.instructions import generate_instructions
from scistudio.qa.governance.gate_record.io import SanitizationError
from scistudio.qa.governance.gate_record.labels import ADMIN_LABELS
from scistudio.qa.governance.gate_record.ledger import (
    AdminLabel,
    CheckNa,
    CommitEvidence,
    DeclaredScope,
    DirectiveEvent,
    DocsEvent,
    GateLedger,
    IssueRef,
    PullRequestEvidence,
    ScopeEvent,
    TestEvent,
)

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_SCHEMA = 3
EXIT_TOOL = 4
EXIT_SANITIZE = 5


@dataclass
class CommandOutcome:
    """A command result: exit code plus lines to print."""

    exit_code: int
    lines: list[str]


def _print_outcome(outcome: CommandOutcome) -> int:
    for line in outcome.lines:
        print(line)
    return outcome.exit_code


# ---------------------------------------------------------------------------
# Discovery + load helpers.
# ---------------------------------------------------------------------------


def _resolve_ledger_path(repo_root: Path, record: str | None) -> tuple[Path | None, CommandOutcome | None]:
    if record is not None:
        path = Path(record)
        path = path if path.is_absolute() else repo_root / path
        if not path.exists():
            return None, CommandOutcome(EXIT_USAGE, [f"ledger not found: {record}"])
        return path, None
    discovery = io.discover_ledger(repo_root)
    if discovery.found:
        return discovery.path, None
    if discovery.ambiguous:
        candidates = "\n".join(f"  {p}" for p in discovery.candidates)
        return None, CommandOutcome(
            EXIT_USAGE,
            ["multiple active ledgers match this branch; pass --record:", candidates],
        )
    return None, CommandOutcome(EXIT_USAGE, ["no gate ledger found; run init first"])


def _load(path: Path) -> tuple[GateLedger | None, CommandOutcome | None]:
    try:
        ledger = io.load_ledger(path)
    except pydantic.ValidationError as exc:
        return None, CommandOutcome(EXIT_SCHEMA, [f"ledger schema/migration error: {exc.error_count()} errors"])
    except (OSError, ValueError) as exc:
        return None, CommandOutcome(EXIT_SCHEMA, [f"ledger load error: {exc}"])
    return ledger, None


def _save(repo_root: Path, path: Path, ledger: GateLedger) -> CommandOutcome | None:
    try:
        io.write_ledger(path, ledger, repo_root=repo_root)
    except SanitizationError as exc:
        return CommandOutcome(EXIT_SANITIZE, [f"sanitization violation: {exc}"])
    return None


# ---------------------------------------------------------------------------
# Shared field-application (additive, append-only).
# ---------------------------------------------------------------------------


def _apply_fields(ledger: GateLedger, args: Any, *, reason: str | None = None) -> None:
    """Append additive field events to the ledger (never overwrite)."""

    for directive in getattr(args, "owner_directive", None) or []:
        ledger.directive_events.append(DirectiveEvent(owner_directive=directive, reason=reason))
    for pattern in getattr(args, "include", None) or []:
        ledger.scope_events.append(ScopeEvent(action="add-include", pattern=pattern, reason=reason))
    for pattern in getattr(args, "exclude", None) or []:
        ledger.scope_events.append(ScopeEvent(action="add-exclude", pattern=pattern, reason=reason))
    for pattern in getattr(args, "remove_include", None) or []:
        ledger.scope_events.append(ScopeEvent(action="remove-include", pattern=pattern, reason=reason))
    for pattern in getattr(args, "remove_exclude", None) or []:
        ledger.scope_events.append(ScopeEvent(action="remove-exclude", pattern=pattern, reason=reason))
    for number in io.parse_issue_numbers(getattr(args, "issue", None) or []):
        if all(ref.number != number for ref in ledger.issues):
            ledger.issues.append(IssueRef(number=number))
    for number in io.parse_issue_numbers(getattr(args, "remove_issue", None) or []):
        ledger.issues = [ref for ref in ledger.issues if ref.number != number]
    for path in getattr(args, "docs_updated", None) or []:
        ledger.docs_events.append(DocsEvent(kind="path", path=path))
    for value in getattr(args, "docs_na", None) or []:
        cls, rationale = io.parse_class_rationale(value)
        ledger.docs_events.append(DocsEvent.model_validate({"kind": "na", "class": cls, "rationale": rationale}))
    for path in getattr(args, "test_path", None) or []:
        ledger.test_events.append(TestEvent(kind="path", path=path))
    for value in getattr(args, "test_na", None) or []:
        cls, rationale = io.parse_class_rationale(value)
        ledger.test_events.append(TestEvent.model_validate({"kind": "na", "class": cls, "rationale": rationale}))
    for value in getattr(args, "check_na", None) or []:
        name, rationale = io.parse_class_rationale(value)
        ledger.check_na.append(CheckNa(name=name, rationale=rationale))
    for label in getattr(args, "admin_label", None) or []:
        if label not in ADMIN_LABELS:
            raise ValueError(f"invalid --admin-label: {label}")
        if label not in ledger.requested_label_names():
            ledger.requested_admin_labels.append(AdminLabel(name=label))
    governance_touch = getattr(args, "governance_touch", None)
    if governance_touch is not None:
        ledger.governance_touch = governance_touch
    task_kind = getattr(args, "task_kind", None)
    if task_kind is not None:
        ledger.task_kind = task_kind
    persona = getattr(args, "persona", None)
    if persona is not None:
        ledger.persona = persona
    branch = getattr(args, "branch", None)
    if branch is not None:
        ledger.branch = branch


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def run_init(repo_root: Path, args: Any) -> int:
    issues = io.parse_issue_numbers(args.issue or [])
    explicit = Path(args.record) if args.record else None
    slug = args.slug or args.branch or (args.owner_directive[0] if args.owner_directive else "task")
    path = io.record_path(
        repo_root,
        issue_number=issues[0] if issues else None,
        branch=args.branch,
        slug=slug,
        explicit=explicit,
    )

    if path.exists():
        ledger, err = _load(path)
        if err:
            return _print_outcome(err)
        assert ledger is not None
    else:
        record_id = path.stem
        session_id = args.session_id or io.new_session_id()
        ledger = GateLedger(
            record_id=record_id,
            session_id=session_id,
            runtime=args.runtime,
            task_kind=args.task_kind,
            persona=args.persona,
            branch=args.branch,
            owner_directive=args.owner_directive[0] if args.owner_directive else "",
        )
        io.write_session_state(repo_root, session_id, {"record_id": record_id, "branch": args.branch})

    for directive in args.owner_directive[1:]:
        ledger.directive_events.append(DirectiveEvent(owner_directive=directive, reason="init"))
    for number in issues:
        if all(ref.number != number for ref in ledger.issues):
            ledger.issues.append(IssueRef(number=number))
    declared = DeclaredScope(include=list(args.include or []), exclude=list(args.exclude or []))
    if declared.include or declared.exclude:
        ledger.declared_scope = declared
    if args.governance_touch is not None:
        ledger.governance_touch = args.governance_touch

    save_err = _save(repo_root, path, ledger)
    if save_err:
        return _print_outcome(save_err)

    rel = path.relative_to(repo_root) if path.is_relative_to(repo_root) else path
    lines = [f"gate ledger: {rel}"]
    if args.print_instructions:
        empty_surfaces: dict[str, list[str]] = {name: [] for name in evaluator._SURFACE_CLASSIFIERS}
        tier = evaluator.derive_tier(ledger.task_kind, empty_surfaces)
        instructions = generate_instructions(
            task_kind=ledger.task_kind,
            persona=ledger.persona,
            tier=tier,
            branch=ledger.branch,
            issues=[ref.number for ref in ledger.issues],
            include=ledger.declared_scope.include,
            governance_touch=ledger.governance_touch,
            record_path=str(rel),
        )
        lines.append("")
        lines.append(instructions)
        if args.instructions_output:
            out = repo_root / args.instructions_output
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(instructions + "\n", encoding="utf-8")
    return _print_outcome(CommandOutcome(EXIT_OK, lines))


# ---------------------------------------------------------------------------
# plan / amend (no expensive checks)
# ---------------------------------------------------------------------------


def run_plan(repo_root: Path, args: Any) -> int:
    path, err = _resolve_ledger_path(repo_root, args.record)
    if err:
        return _print_outcome(err)
    assert path is not None
    ledger, load_err = _load(path)
    if load_err:
        return _print_outcome(load_err)
    assert ledger is not None
    try:
        _apply_fields(ledger, args, reason="plan")
    except ValueError as exc:
        return _print_outcome(CommandOutcome(EXIT_USAGE, [str(exc)]))
    save_err = _save(repo_root, path, ledger)
    if save_err:
        return _print_outcome(save_err)
    return _print_outcome(CommandOutcome(EXIT_OK, ["plan recorded"]))


def run_amend(repo_root: Path, args: Any) -> int:
    if not args.reason:
        return _print_outcome(CommandOutcome(EXIT_USAGE, ["amend requires --reason"]))
    path, err = _resolve_ledger_path(repo_root, args.record)
    if err:
        return _print_outcome(err)
    assert path is not None
    ledger, load_err = _load(path)
    if load_err:
        return _print_outcome(load_err)
    assert ledger is not None
    try:
        _apply_fields(ledger, args, reason=args.reason)
    except ValueError as exc:
        return _print_outcome(CommandOutcome(EXIT_USAGE, [str(exc)]))
    save_err = _save(repo_root, path, ledger)
    if save_err:
        return _print_outcome(save_err)
    return _print_outcome(CommandOutcome(EXIT_OK, [f"amendment recorded: {args.reason}"]))


# ---------------------------------------------------------------------------
# check (the main reconciliation)
# ---------------------------------------------------------------------------


def _read_pr_body(repo_root: Path, pr_body_file: str | None) -> str | None:
    if not pr_body_file:
        return None
    path = Path(pr_body_file)
    path = path if path.is_absolute() else repo_root / path
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def run_check(repo_root: Path, args: Any, *, mode: str | None = None) -> int:
    effective_mode = mode or getattr(args, "mode", "local") or "local"
    path, err = _resolve_ledger_path(repo_root, args.record)
    if err:
        return _print_outcome(err)
    assert path is not None
    ledger, load_err = _load(path)
    if load_err:
        return _print_outcome(load_err)
    assert ledger is not None
    try:
        _apply_fields(ledger, args, reason="check")
    except ValueError as exc:
        return _print_outcome(CommandOutcome(EXIT_USAGE, [str(exc)]))

    pr_body = _read_pr_body(repo_root, getattr(args, "pr_body_file", None))
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=repo_root,
        base=getattr(args, "base", "origin/main") or "origin/main",
        head=getattr(args, "head", "HEAD") or "HEAD",
        mode=effective_mode,  # type: ignore[arg-type]
        pr_body=pr_body,
        run_checks=not getattr(args, "skip_execution", False),
        only=getattr(args, "only", None) or None,
    )

    save_err = _save(repo_root, path, ledger)
    if save_err:
        return _print_outcome(save_err)

    lines = [
        f"mode={effective_mode} tier={result.strictness_tier} checks={result.required_obligations.checks}",
    ]
    if result.unsatisfied:
        lines.append("")
        lines.append("Unsatisfied obligations:")
        lines.extend(result.repair_hints or [f"- {item}" for item in result.unsatisfied])
        if any(item.startswith("parity.") for item in result.unsatisfied):
            return _print_outcome(CommandOutcome(EXIT_TOOL, lines))
        return _print_outcome(CommandOutcome(EXIT_FAIL, lines))
    lines.append("reconciliation passed")
    return _print_outcome(CommandOutcome(EXIT_OK, lines))


# ---------------------------------------------------------------------------
# finalize (pre-PR / post-PR)
# ---------------------------------------------------------------------------


def run_finalize(repo_root: Path, args: Any) -> int:
    path, err = _resolve_ledger_path(repo_root, args.record)
    if err:
        return _print_outcome(err)
    assert path is not None
    ledger, load_err = _load(path)
    if load_err:
        return _print_outcome(load_err)
    assert ledger is not None

    is_post_pr = bool(getattr(args, "pr", None))
    if not is_post_pr and not getattr(args, "pr_body_file", None):
        return _print_outcome(CommandOutcome(EXIT_USAGE, ["pre-PR finalize requires --pr-body-file"]))

    try:
        _apply_fields(ledger, args, reason="finalize")
    except ValueError as exc:
        return _print_outcome(CommandOutcome(EXIT_USAGE, [str(exc)]))

    commits = list(getattr(args, "commit", None) or [])
    closes = io.parse_issue_numbers([str(c) for c in (getattr(args, "closes", None) or [])])
    ledger.commit = CommitEvidence(sha=commits[0] if commits else None, shas=commits)
    pr_value = getattr(args, "pr", None)
    pr = ledger.pull_request or PullRequestEvidence()
    if closes:
        pr.closes = closes
    if pr_value:
        pr.url = pr_value if str(pr_value).startswith("http") else None
        try:
            pr.number = int(str(pr_value).lstrip("#").rsplit("/", 1)[-1])
        except ValueError:
            pr.number = None
    ledger.pull_request = pr

    mode = "ci" if is_post_pr else "pre-pr"
    pr_body = _read_pr_body(repo_root, getattr(args, "pr_body_file", None))
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=repo_root,
        base=getattr(args, "base", "origin/main") or "origin/main",
        head=getattr(args, "head", "HEAD") or "HEAD",
        mode=mode,  # type: ignore[arg-type]
        pr_body=pr_body,
        run_checks=True,
    )
    save_err = _save(repo_root, path, ledger)
    if save_err:
        return _print_outcome(save_err)

    lines = [f"finalize mode={'post-PR' if is_post_pr else 'pre-PR'} tier={result.strictness_tier}"]
    if result.unsatisfied:
        lines.append("Unsatisfied obligations:")
        lines.extend(result.repair_hints or [f"- {item}" for item in result.unsatisfied])
        if any(item.startswith("parity.") for item in result.unsatisfied):
            return _print_outcome(CommandOutcome(EXIT_TOOL, lines))
        return _print_outcome(CommandOutcome(EXIT_FAIL, lines))
    lines.append("ledger is PR-ready" if not is_post_pr else "post-PR reconciliation passed")
    return _print_outcome(CommandOutcome(EXIT_OK, lines))
