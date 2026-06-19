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

import json
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


def _resolve_ledger_path(
    repo_root: Path,
    record: str | None,
    *,
    include_finalized: bool = False,
    include_finalized_paths: list[Path] | None = None,
) -> tuple[Path | None, CommandOutcome | None]:
    if record is not None:
        path = Path(record)
        path = path if path.is_absolute() else repo_root / path
        if not path.exists():
            return None, CommandOutcome(EXIT_USAGE, [f"ledger not found: {record}"])
        return path, None
    discovery = io.discover_ledger(
        repo_root,
        include_finalized=include_finalized,
        include_finalized_paths=include_finalized_paths,
    )
    if discovery.found:
        return discovery.path, None
    if discovery.ambiguous:
        candidates = "\n".join(f"  {p}" for p in discovery.candidates)
        return None, CommandOutcome(
            EXIT_USAGE,
            ["multiple active ledgers match this branch; pass --record:", candidates],
        )
    if discovery.has_unreadable:
        candidates = "\n".join(f"  {p}" for p in discovery.unreadable)
        return None, CommandOutcome(
            EXIT_SCHEMA,
            ["gate ledger exists but is temporarily unreadable; retry the command:", candidates],
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


def _unrun_mandatory_checks(
    result: evaluator.ReconcileResult,
    *,
    only: list[str] | None,
    args: Any,
) -> list[str]:
    """Return required tier-selected checks that were NOT actually run/validated.

    Used by the recovery-mode banner (§7.5): ``--only`` runs a subset and
    ``--skip-execution`` executes none, so any required check without current
    evidence is a mandatory check this invocation did not establish. Checks with
    an accepted N/A are not counted as unrun. The result is the gap between the
    inferred required check set and what this call actually executed/validated.
    """

    required = set(result.required_obligations.checks)
    if not required:
        return []
    if getattr(args, "skip_execution", False):
        ran: set[str] = set()
    elif only:
        ran = set(only) & required
    else:
        ran = set(required)
    # Checks that produced an event this run count as run.
    ran |= {event.name for event in result.check_events}
    return sorted(required - ran)


def _recovery_banner(mode: str, unrun: list[str]) -> list[str]:
    """Build the "not final PR readiness" recovery banner (§7.5)."""

    return [
        "",
        "RECOVERY MODE (--only / missing evidence): NOT final PR readiness.",
        f"  Mandatory tier-selected checks not run/validated this invocation: {', '.join(unrun)}",
        "  Run `gate_record check --mode pre-pr` to execute only missing/stale checks,",
        "  or add `--force-checks` to intentionally rerun the full selected set.",
    ]


def _resolve_base(repo_root: Path, base: str | None, head: str) -> str:
    """Resolve the diff base (Fix D / §7.5).

    An explicit ``--base`` is honored verbatim. When omitted, default to
    ``git merge-base origin/main HEAD`` so a branch's delta is its own commits
    (correct for normal branches; better for stacked branches). Falls back to
    raw ``origin/main`` when the merge-base cannot be computed.
    """

    if base:
        return base
    return io.resolve_default_base(repo_root, head=head)


def _changed_record_paths(repo_root: Path, *, base: str, head: str, mode: str) -> list[Path]:
    """Return changed gate-record paths that may be finalized provenance commits."""

    if mode not in {"pre-commit", "pre-push"}:
        return []
    changed = io.changed_files(repo_root, base, head, staged=mode == "pre-commit")
    paths: list[Path] = []
    for rel in changed:
        normalized = rel.replace("\\", "/")
        if normalized.startswith(".workflow/records/") and normalized.endswith(".json"):
            paths.append((repo_root / normalized).resolve())
    return paths


def _read_pr_body(repo_root: Path, pr_body_file: str | None) -> str | None:
    if not pr_body_file:
        return None
    path = Path(pr_body_file)
    path = path if path.is_absolute() else repo_root / path
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _read_pr_context(repo_root: Path, pr_context_file: str | None) -> dict[str, Any] | None:
    """Parse the CI PR-context JSON file, or return None when absent/unusable.

    The workflow assembles this file from the real GitHub event (labels with
    actor/permission provenance, reviews, merge intent). A missing, empty, or
    malformed file yields ``None`` so a PR with no context (like a labelless PR)
    behaves exactly as before: no PR context reaches the guards. Parse failures
    are non-fatal by design — provenance enrichment is best-effort and the
    guards fail closed without it.
    """

    if not pr_context_file:
        return None
    path = Path(pr_context_file)
    path = path if path.is_absolute() else repo_root / path
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def run_check(repo_root: Path, args: Any, *, mode: str | None = None) -> int:
    effective_mode = mode or getattr(args, "mode", "local") or "local"
    head = getattr(args, "head", "HEAD") or "HEAD"
    base = _resolve_base(repo_root, getattr(args, "base", None), head)
    changed_record_paths = _changed_record_paths(repo_root, base=base, head=head, mode=effective_mode)
    path, err = _resolve_ledger_path(
        repo_root,
        args.record,
        # A finalized ledger (PR created, not yet merged) is still the active
        # ledger for its branch until merge, so every git-hook mode that may run
        # on a post-finalize follow-up commit must still discover it. Without
        # commit-msg here, the commit-msg hook fails "no gate ledger found" on the
        # very commit that records the PR provenance, right after post-PR finalize
        # marks the ledger finalized (#1609).
        include_finalized=effective_mode in ("ci", "pre-commit", "pre-push", "commit-msg"),
        include_finalized_paths=changed_record_paths,
    )
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
    pr_context = _read_pr_context(repo_root, getattr(args, "pr_context_file", None))
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=repo_root,
        base=base,
        head=head,
        mode=effective_mode,  # type: ignore[arg-type]
        pr_body=pr_body,
        pr_context=pr_context,
        run_checks=not getattr(args, "skip_execution", False),
        force_checks=bool(getattr(args, "force_checks", False)),
        only=getattr(args, "only", None) or None,
    )

    # --no-record (git-hook use): run checks/guards and report pass/fail, but do
    # NOT persist the ledger. Under the pre-commit framework a hook that modifies
    # a tracked file (the ledger) fails the commit, and the gate's always-append
    # evidence never converges (issue #1609). Recording stays with explicit
    # ``check`` runs and CI.
    if not getattr(args, "no_record", False):
        save_err = _save(repo_root, path, ledger)
        if save_err:
            return _print_outcome(save_err)

    lines = [
        f"mode={effective_mode} tier={result.strictness_tier} checks={result.required_obligations.checks}",
    ]
    # Loud non-blocking warnings (e.g. --check-na with no force for ci.yml-owned
    # checks, §7.5/Fix B).
    if result.warnings:
        lines.append("")
        lines.append("WARNING:")
        lines.extend(f"- {w}" for w in result.warnings)
    # Recovery-mode banner (§7.5): --only / --skip-execution cannot create final
    # PR readiness when mandatory tier checks were not actually run/validated.
    recovery = bool(getattr(args, "only", None)) or bool(getattr(args, "skip_execution", False))
    unrun = _unrun_mandatory_checks(result, only=getattr(args, "only", None) or None, args=args)
    if recovery and unrun:
        lines.extend(_recovery_banner(effective_mode, unrun))

    # Environment-parity gaps (§7.10): the local env is not CI-equivalent, so we
    # could not validate the affected checks. Report distinctly and fail closed
    # for PR readiness (EXIT_TOOL) rather than as a misleading code failure.
    if result.parity_gaps:
        lines.append("")
        lines.append("Environment parity gaps (local env is not CI-equivalent):")
        lines.extend(f"- {gap}" for gap in result.parity_gaps)

    non_parity_unsatisfied = [item for item in result.unsatisfied if not item.startswith("parity.")]
    if result.unsatisfied:
        lines.append("")
        lines.append("Unsatisfied obligations:")
        lines.extend(result.repair_hints or [f"- {item}" for item in non_parity_unsatisfied])
        if non_parity_unsatisfied:
            return _print_outcome(CommandOutcome(EXIT_FAIL, lines))
        # Only parity gaps remain -> tool/environment failure, fail closed.
        return _print_outcome(CommandOutcome(EXIT_TOOL, lines))

    if result.parity_gaps and effective_mode in ("pre-pr", "ci"):
        return _print_outcome(CommandOutcome(EXIT_TOOL, lines))

    if recovery and unrun and effective_mode in ("pre-pr", "ci"):
        # Recovery cannot create final readiness in strict modes.
        return _print_outcome(CommandOutcome(EXIT_FAIL, lines))

    lines.append(
        "recovery reconciliation passed; NOT final PR readiness" if (recovery and unrun) else "reconciliation passed"
    )
    return _print_outcome(CommandOutcome(EXIT_OK, lines))


# ---------------------------------------------------------------------------
# finalize (pre-PR / post-PR)
# ---------------------------------------------------------------------------


def run_finalize(repo_root: Path, args: Any) -> int:
    is_post_pr = bool(getattr(args, "pr", None))
    path, err = _resolve_ledger_path(repo_root, args.record, include_finalized=is_post_pr)
    if err:
        return _print_outcome(err)
    assert path is not None
    ledger, load_err = _load(path)
    if load_err:
        return _print_outcome(load_err)
    assert ledger is not None

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

    pr_context = _read_pr_context(repo_root, getattr(args, "pr_context_file", None))
    # Local post-PR finalize records PR provenance but cannot prove CI-only
    # label actor/permission facts. Keep it in pre-PR reconciliation unless a
    # CI workflow explicitly supplies PR context; CI's workflow-gate owns the
    # authoritative provenance check.
    mode = "ci" if is_post_pr and pr_context is not None else "pre-pr"
    pr_body = _read_pr_body(repo_root, getattr(args, "pr_body_file", None))
    head = getattr(args, "head", "HEAD") or "HEAD"
    base = _resolve_base(repo_root, getattr(args, "base", None), head)
    force_checks = bool(getattr(args, "force_checks", False))
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=repo_root,
        base=base,
        head=head,
        mode=mode,  # type: ignore[arg-type]
        pr_body=pr_body,
        pr_context=pr_context,
        run_checks=force_checks,
        force_checks=force_checks,
    )
    save_err = _save(repo_root, path, ledger)
    if save_err:
        return _print_outcome(save_err)

    lines = [f"finalize mode={'post-PR' if is_post_pr else 'pre-PR'} tier={result.strictness_tier}"]
    if result.warnings:
        lines.append("WARNING:")
        lines.extend(f"- {w}" for w in result.warnings)
    if result.parity_gaps:
        lines.append("Environment parity gaps (local env is not CI-equivalent):")
        lines.extend(f"- {gap}" for gap in result.parity_gaps)
    non_parity_unsatisfied = [item for item in result.unsatisfied if not item.startswith("parity.")]
    if result.unsatisfied:
        lines.append("Unsatisfied obligations:")
        lines.extend(result.repair_hints or [f"- {item}" for item in non_parity_unsatisfied])
        if non_parity_unsatisfied:
            return _print_outcome(CommandOutcome(EXIT_FAIL, lines))
        return _print_outcome(CommandOutcome(EXIT_TOOL, lines))
    lines.append("ledger is PR-ready" if not is_post_pr else "post-PR reconciliation passed")
    return _print_outcome(CommandOutcome(EXIT_OK, lines))
