"""The single shared evaluator for ADR-042 Addendum 6 (spec §3).

``reconcile()`` is the one reconciliation code path that every command, hook,
PR wrapper, and CI step calls. The ``mode`` only changes which facts are
required-now versus recorded as a pre-PR gap; it never forks the logic.

Pipeline (§3.3): observe git diff -> classify surfaces -> reconcile declared
scope -> reconcile declared docs/test claims -> infer obligations -> derive
strictness tier (escalate, never lower, §7.6) -> infer + run tier-selected
checks (with parity) -> run guard calculators -> write a reconcile event ->
sanitize committed events.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import scistudio.qa.governance.gate_record.checks as checks
import scistudio.qa.governance.gate_record.io as io
import scistudio.qa.governance.gate_record.parity as parity
import scistudio.qa.governance.gate_record.surfaces as surfaces
from scistudio.qa.governance.gate_record.guards import GUARD_REGISTRY, GuardInputs
from scistudio.qa.governance.gate_record.ledger import (
    AdminLabel,
    CheckEvent,
    GateLedger,
    GuardEvent,
    ObservedDiff,
    ReconcileEvent,
    RequiredObligations,
    StrictnessTier,
    TaskKind,
)
from scistudio.qa.schemas.report import AuditFinding, AuditReport, AuditStatus, Severity

EvaluatorMode = Literal["local", "pre-commit", "commit-msg", "pre-push", "pre-pr", "ci"]

# Baseline tier from task kind (§7.6). Escalation only raises (never lowers).
_BASELINE_TIER: dict[str, StrictnessTier] = {
    "feature": 1,
    "refactor": 1,
    "bugfix": 2,
    "hotfix": 2,
    "maintenance": 2,
    "guided": 2,
    "docs": 3,
    "manager": 3,
}

# Quality checks owned by the separate ``ci.yml`` jobs (ADR-042 Addendum 6
# §7.5 CI command-source table). The ``workflow-gate.yml`` / "Verify Workflow
# Compliance" job validates GOVERNANCE + guards, NOT this quality matrix: those
# jobs are authoritative for lint/format/type/test/audit/architecture/import-
# contracts/frontend/wheel/semantic-dup and run independently. So in ``ci`` mode
# the shared evaluator must NOT re-require ledger ``check_events`` for these --
# doing so both duplicates ``ci.yml`` and blocks on evidence the workflow-gate
# job was never meant to demand. ``local``/``pre-pr`` modes still run them as the
# CI-equivalent preflight. This is the §7.5 role split, not a weakening: the
# matrix remains enforced by ``ci.yml`` on the same PR.
_CI_OWNED_QUALITY_CHECKS: frozenset[str] = frozenset(
    {
        "lint_format",
        "format_check",
        "type_check",
        "architecture_tests",
        "full_audit",
        "python_tests",
        "import_contracts",
        "frontend",
        "wheel_release_smoke",
        "semantic_dup",
        "deferral_discipline",
    }
)

# The two slowest checks (~3min combined: full pytest + src-wide embeddings).
# pre-commit is a fast local gate, so it skips these — they still run in
# pre-pr / CI, and the governance guards + fast checks still run at commit time
# (#1628).
_PRE_COMMIT_SKIP_CHECKS: frozenset[str] = frozenset({"python_tests", "semantic_dup"})
_CHECK_EVIDENCE_IGNORED_PREFIXES: tuple[str, ...] = (".workflow/records/",)
_CHECK_FINGERPRINT_VERSION = "gate-check-input-v2"

# Surface classes the evaluator records on the observed diff.
_SURFACE_CLASSIFIERS = {
    "implementation": surfaces.is_implementation_path,
    "test": surfaces.is_test_path,
    "governance": surfaces.is_governance_path,
    "protected_core": surfaces.is_protected_core_path,
    "frontend": surfaces.is_frontend_path,
    "packaging": surfaces.is_packaging_path,
    "workflow_ci": surfaces.is_workflow_ci_path,
    "docs": surfaces.is_docs_path,
    "governed_docs": surfaces.is_governed_doc_path,
    "sentrux": surfaces.sentrux_applies,
}


@dataclass
class ReconcileResult:
    """The consolidated outcome of one ``reconcile()`` call (spec §3.1)."""

    report: AuditReport
    strictness_tier: StrictnessTier
    required_obligations: RequiredObligations
    unsatisfied: list[str] = field(default_factory=list)
    repair_hints: list[str] = field(default_factory=list)
    check_events: list[CheckEvent] = field(default_factory=list)
    guard_events: list[GuardEvent] = field(default_factory=list)
    reconcile_event: ReconcileEvent | None = None
    parity_gaps: list[str] = field(default_factory=list)
    # Non-blocking, loud warnings (e.g. a --check-na that has no force for a
    # ci.yml-owned check, §7.5/Fix B). Surfaced by callers; never flips status.
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.unsatisfied and not self.report.blocks_merge


def classify_surfaces(changed_files: Sequence[str]) -> dict[str, list[str]]:
    """Group changed files by surface class (§3.3.2)."""

    grouped: dict[str, list[str]] = {name: [] for name in _SURFACE_CLASSIFIERS}
    for path in changed_files:
        for name, predicate in _SURFACE_CLASSIFIERS.items():
            if predicate(path):
                grouped[name].append(path)
    return grouped


def derive_tier(task_kind: TaskKind, grouped: dict[str, list[str]]) -> StrictnessTier:
    """Derive the strictness tier: baseline + escalation only (§7.6)."""

    tier: StrictnessTier = _BASELINE_TIER.get(task_kind, 2)
    escalate = bool(grouped["protected_core"] or grouped["governance"] or grouped["workflow_ci"])
    # Broad cross-module change: many distinct top-level surfaces touched.
    distinct_surfaces = sum(1 for name in ("implementation", "frontend", "packaging") if grouped[name])
    if distinct_surfaces >= 3:
        escalate = True
    if escalate:
        return 1
    return tier


# Task kinds whose gate record represents an INTEGRATION / umbrella PR rather
# than a single worker task (issue #1283). An integration record legitimately
# spans the union of every merged worker scope, so applying a narrow declared
# worker-scope to the whole integration PR produces false ``scope.out-of-scope``
# failures. For these records the declared include is advisory (it still records
# intent), and out-of-scope files are reported as a NON-blocking WARNING instead
# of a blocking ERROR. This does NOT weaken enforcement: the worker sub-PRs were
# each gate-validated on their own narrow scope before merging into the
# integration branch, and the integration PR still runs every guard + tier check.
_INTEGRATION_TASK_KINDS: frozenset[str] = frozenset({"manager"})


def _scope_findings(
    ledger: GateLedger,
    changed_files: Sequence[str],
    *,
    repo_root: Path | None = None,
    base: str | None = None,
    head: str | None = None,
) -> list[AuditFinding]:
    """Reconcile declared scope against the PR-authored diff (§3.3.3).

    ``changed_files`` here is the PR-AUTHORED scope set (first-parent, non-merge
    commits) so merge-imported main-side changes are never flagged as
    out-of-scope (#1463 Bug A). Integration/umbrella records (manager task kind)
    treat declared scope as advisory and downgrade out-of-scope to a warning
    (#1283). Main-side renames of a scoped path are tolerated: when a scoped
    include glob matches zero current files but the path was renamed/split on the
    base, the out-of-scope finding for the new location is downgraded to a
    warning with a remap hint rather than blocking (#1463 Bug B).
    """

    include = ledger.effective_include()
    exclude = ledger.effective_exclude()
    findings: list[AuditFinding] = []
    if not include:
        # No declared include: scope reconciliation defers to tier obligations.
        return findings

    is_integration = ledger.task_kind in _INTEGRATION_TASK_KINDS
    # Includes that no longer match ANY current file are candidates for a
    # main-side rename/split (#1463 Bug B): a scoped path the umbrella refactored
    # away. We tolerate continuation work on the renamed location instead of hard
    # blocking, but only as a warning so the drift stays visible.
    stale_includes = (
        _stale_include_globs(repo_root, include, base=base, head=head)
        if repo_root is not None and base is not None and head is not None
        else set()
    )
    rename_tolerant = bool(stale_includes)

    for path in changed_files:
        if surfaces.is_gate_record_path(path):
            continue
        in_scope = surfaces.matches_any(path, include)
        excluded = surfaces.matches_any(path, exclude)
        if in_scope and not excluded:
            continue
        # Downgrade to a non-blocking warning for integration records or when a
        # main-side rename plausibly relocated in-scope work (#1283 / #1463 B).
        downgrade = is_integration or (rename_tolerant and not excluded)
        findings.append(
            AuditFinding(
                rule_id="scope.out-of-scope",
                severity=Severity.WARNING if downgrade else Severity.ERROR,
                file=path,
                message=(
                    "changed file is outside the effective declared scope "
                    + (
                        "(integration/umbrella record: advisory only)"
                        if is_integration
                        else (
                            "(a scoped path was renamed/split on the base; amend --include the new "
                            "location and cite the upstream rename)"
                            if downgrade
                            else ""
                        )
                    )
                ).strip(),
                evidence={"include": include, "exclude": exclude, "stale_includes": sorted(stale_includes)},
            )
        )
    return findings


def _stale_include_globs(repo_root: Path, include: Sequence[str], *, base: str, head: str) -> set[str]:
    """Return declared include globs that match zero files in the working tree.

    Used for #1463 Bug B rename tolerance: an include like
    ``src/scistudio/api/runtime.py`` that no longer exists (it was split into a
    ``runtime/`` package on the base while the PR was in review) matches nothing
    on the PR branch. Such a stale glob signals a main-side rename/split, so the
    evaluator tolerates the continuation work on the new location with a warning
    instead of a hard block. Literal globs (no wildcard) that resolve to a
    missing path are the clearest signal; wildcard globs are checked against the
    union of base+head trees.
    """

    tracked = set(io.tracked_files(repo_root, head)) | set(io.tracked_files(repo_root, base))
    stale: set[str] = set()
    for glob in include:
        if not any(surfaces.match_path(path, glob) for path in tracked):
            stale.add(glob)
    return stale


def _verify_claims(declared: Sequence[str], changed_files: Sequence[str]) -> tuple[list[str], list[str]]:
    """Split declared paths into verified-in-diff and claimed-but-unverified."""

    changed = {surfaces.normalize_path(p) for p in changed_files}
    verified = [p for p in declared if surfaces.normalize_path(p) in changed]
    unverified = [p for p in declared if surfaces.normalize_path(p) not in changed]
    return verified, unverified


def _observed_docs_evidence(grouped: dict[str, list[str]]) -> list[str]:
    """Return docs/governed-doc files present in the observed diff (§7.5).

    The workflow-gate job validates that documentation LANDED; a docs or
    governed-doc file in the git diff is objective git-observed landing
    evidence, independent of whether the agent declared it as a ``docs_event``.
    Used in ``ci`` mode so docs-landing is satisfiable from the observed diff.
    """

    return sorted({*grouped.get("docs", []), *grouped.get("governed_docs", [])})


def _observed_test_evidence(grouped: dict[str, list[str]]) -> list[str]:
    """Return test files present in the observed diff (§7.5).

    A changed test file in the git diff satisfies ``changed_test_required``
    directly: the diff is the evidence, so ``ci`` mode does not require a
    separately recorded ``test_event`` when tests visibly changed.
    """

    return sorted(set(grouped.get("test", [])))


def _docs_na_rationales(ledger: GateLedger) -> list[str]:
    """Return docs N/A rationales recorded on the ledger (for ``extras['docs_na']``)."""

    return [
        f"{event.doc_class or 'docs'}: {event.rationale}"
        for event in ledger.docs_events
        if event.kind == "na" and event.rationale
    ]


def _recorded_sentrux_evidence(ledger: GateLedger) -> Any | None:
    """Return the latest recorded Sentrux evidence payload, or None (§4).

    Sentrux evidence rides in on a ``check_event`` (or ``guard_event``) the agent
    recorded; the evaluator surfaces the latest such payload to the
    ``sentrux_gate`` calculator via ``extras['sentrux_evidence']``. Absent
    evidence means the guard records an advisory (opt-in), never a hard block.
    """

    for event in reversed(ledger.check_events):
        name = (event.name or "").lower()
        if ("sentrux" in name or event.covered_surface == "sentrux") and event.summary.strip().startswith("{"):
            return event.summary
    return None


def _observed_labels_from_context(pr_context: Mapping[str, Any] | None) -> list[AdminLabel]:
    """Convert CI PR-context ``labels`` into provenance-carrying AdminLabels (§4).

    The CI workflow assembles ``pr_context['labels']`` from the real GitHub event
    as ``[{name, actor, permission}, ...]`` where ``actor``/``permission`` are the
    labeling actor and that actor's repository permission (resolved in CI via the
    GitHub API). Each entry becomes an observed :class:`AdminLabel` whose
    ``actor_permission`` is the verified provenance the core/human/merge guards
    require — they authorize an admin label ONLY when its labeling actor has an
    admin/maintainer permission, so a label with no/insufficient provenance never
    authorizes. Entries without a name are dropped; malformed entries are skipped.
    """

    if not pr_context:
        return []
    raw = pr_context.get("labels")
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        return []
    labels: list[AdminLabel] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        actor = entry.get("actor")
        permission = entry.get("permission", entry.get("actor_permission"))
        labels.append(
            AdminLabel(
                name=name,
                applied_by=actor if isinstance(actor, str) else None,
                actor_permission=permission if isinstance(permission, str) else None,
            )
        )
    return labels


def _merge_observed_labels(
    ledger_labels: Sequence[AdminLabel],
    context_labels: Sequence[AdminLabel],
) -> list[AdminLabel]:
    """Merge ledger + CI-context observed labels, latest provenance wins per name.

    A given label name may appear in both the committed ledger and the live CI
    context; the CI context carries the authoritative actor/permission provenance,
    so context entries override ledger entries of the same name. Names unique to
    either source are kept. The result is the single observed-label set the guards
    read.
    """

    merged: dict[str, AdminLabel] = {label.name: label for label in ledger_labels}
    for label in context_labels:
        merged[label.name] = label
    return list(merged.values())


def _build_pr_context(
    ledger: GateLedger,
    mode: EvaluatorMode,
    pr_context: Mapping[str, Any] | None,
    observed_admin_labels: Sequence[AdminLabel],
) -> dict[str, Any] | None:
    """Assemble the PR context the merge/core/human guards read (§3.2).

    The caller may pass a partial ``pr_context`` (real GitHub event in CI mode)
    carrying ``reviews`` and ``merge_intent``. The evaluator passes those through
    and also surfaces the merged observed-label names (which carry CI-verified
    actor/permission provenance) as ``observed_labels`` so the guards see the same
    label set as ``GuardInputs.observed_admin_labels``. In local modes there is no
    real PR yet, so labels are recorded intent only and no context is built unless
    the caller supplies one.
    """

    if mode not in ("pre-pr", "ci") and pr_context is None:
        return None
    context: dict[str, Any] = dict(pr_context or {})
    if observed_admin_labels:
        context.setdefault("observed_labels", [label.name for label in observed_admin_labels])
    return context or (dict(pr_context) if pr_context is not None else None)


def _infer_obligations(
    *,
    task_kind: TaskKind,
    tier: StrictnessTier,
    grouped: dict[str, list[str]],
    required_checks: Sequence[str],
) -> RequiredObligations:
    """Infer required obligations from task kind, tier, and surfaces (§3.3.5)."""

    docs: list[str] = []
    tests: list[str] = []
    guards = sorted(GUARD_REGISTRY.keys())
    admin_labels: list[str] = []

    # Docs obligation when governed/contract surfaces change.
    if grouped["implementation"] or grouped["governance"] or grouped["governed_docs"]:
        docs.append("docs_required_or_na")
    # Test obligation when implementation/runtime/tooling surfaces change.
    if grouped["implementation"] and task_kind not in ("docs", "manager"):
        tests.append("changed_test_required")
    # Protected-core authorization.
    if grouped["protected_core"]:
        admin_labels.append("admin-approved:core-change")

    return RequiredObligations(
        checks=list(required_checks),
        docs=docs,
        tests=tests,
        guards=guards,
        admin_labels=admin_labels,
    )


# Per-guard fallback repair actions (§5.2 one-pass guidance). Used only when a
# blocking guard finding carries no remediation/suggested_fix of its own. These
# are intentionally guard-class actions, not check waivers: NEVER suggest
# ``--check-na`` here (that waiver is over-broad for merge-blocking standalone CI
# jobs like python_tests/lint_format and has no force there).
_GUARD_REPAIR_ACTIONS: dict[str, str] = {
    "core_change_guard": (
        "Request the admin-approved:core-change label (owner applies it; the "
        "actor-permission provenance is verified in CI), or move the change out "
        "of the protected-core surface."
    ),
    "human_bypass_guard": (
        "Use a valid ADR-042 override label applied by an authorized maintainer; "
        "AI-authored evidence needs admin-approved:bypass provenance."
    ),
    "pr_merge_guard": (
        "AI merge automation needs admin-approved:merge applied by an authorized maintainer (verified in CI)."
    ),
    "mod_guard": (
        "Declare the governance touch and obtain owner review for the governed "
        "surface change, or revert the unauthorized governed-file edit."
    ),
    "weakened_ci_check": (
        "Restore the removed/altered required CI or pre-commit check token, or "
        "get owner sign-off recorded for the governance change."
    ),
    "sentrux_gate": (
        "Record passing Sentrux evidence for the changed surface "
        "(scan + check_rules), or attach an owner-approved waiver rationale."
    ),
    "test_engineer_scope_guard": (
        "Keep test-engineer edits inside the allowed test/fixture surface; amend "
        "scope or move non-test changes to an implementer task."
    ),
    "docs_landing": (
        "Record a docs/changelog/checklist path or an explicit N/A:\n"
        "  gate_record amend --reason '<why>' --docs-na 'implementation:<rationale>'"
    ),
    "issue_link": ("Link an issue and close it in the PR body:\n  gate_record amend --reason '<why>' --issue <n>"),
    "persona_policy": (
        "Add the missing persona skill/constitution/root-policy pointer at the "
        "path named in the finding evidence (match an existing persona's pointer; "
        "git add -f gitignored runtime roots)."
    ),
}


def _guard_repair_hint(guard_name: str, report: AuditReport) -> str:
    """Build an actionable repair hint for a blocking guard (§5.2).

    Prefers the guard's own remediation/suggested_fix, falls back to the
    finding message, and always appends a concrete per-guard action plus the
    relevant finding evidence (e.g. the missing pointer path) so guard findings
    carry the same one-pass guidance as docs/test/issue/check obligations.
    """

    lines = [f"- guard.{guard_name}"]
    errors = report.error_findings()
    # Surface what the guard reported (its own remediation wins; else the
    # descriptive message). Dedupe so repeated per-file findings don't repeat.
    seen: set[str] = set()
    for finding in errors:
        detail = finding.remediation or finding.suggested_fix or finding.message
        if detail and detail not in seen:
            seen.add(detail)
            lines.append(f"  {detail}")
    action = _GUARD_REPAIR_ACTIONS.get(guard_name)
    if action:
        lines.append(f"  Fix: {action}")
    # Append the load-bearing evidence (paths/labels) so the hint is concrete.
    evidence_bits: list[str] = []
    for finding in errors:
        if finding.file and finding.file not in evidence_bits:
            evidence_bits.append(finding.file)
    if evidence_bits:
        lines.append(f"  Affected: {', '.join(evidence_bits[:5])}")
    return "\n".join(lines)


def _failed_check_excerpt(repo_root: Path, event: CheckEvent, *, max_lines: int = 50, max_chars: int = 6000) -> str:
    """Return an indented tail excerpt of a failed check's raw log, or "".

    The committed ledger keeps only a one-line ``summary`` + ``raw_log_ref``; this
    surfaces the actual findings inline in the repair hint so a failing check is
    actionable without opening the log file (#1628). Tail-biased because most
    tools (pytest/ruff/mypy) put their error summary last, and full_audit's
    per-child status table also lands at the tail.
    """

    ref = event.raw_log_ref
    if not ref:
        return ""
    try:
        text = (repo_root / ref).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    tail = text.splitlines()[-max_lines:]
    excerpt = "\n".join(f"  | {line}" for line in tail).rstrip()
    if len(excerpt) > max_chars:
        excerpt = "  | ...(truncated)\n" + excerpt[-max_chars:]
    # Keep it printable on ANY console: a Windows GBK/cp1252 stdout cannot encode
    # the U+FFFD replacement char that ``errors="replace"`` emits for non-UTF-8
    # log bytes, which would crash ``_print_outcome``'s ``print``. ASCII-clean it.
    return excerpt.encode("ascii", "replace").decode("ascii")


def _is_global_check_config_path(path: str) -> bool:
    """Return True for files that can change the meaning of check execution."""

    return path in {
        ".pre-commit-config.yaml",
        "pyproject.toml",
        "setup.cfg",
        "tox.ini",
    } or path.startswith(".github/workflows/")


def _is_python_check_input(path: str) -> bool:
    return (
        path.endswith((".py", ".pyi"))
        or path.startswith(("src/", "tests/", "packages/", "scripts/"))
        or path in {".codespellrc", "mypy.ini", "pyrightconfig.json", "setup.py"}
        or _is_global_check_config_path(path)
    )


def _is_frontend_check_input(path: str) -> bool:
    return (
        path.startswith("frontend/")
        or path in {"package.json", "package-lock.json", "pnpm-lock.yaml"}
        or _is_global_check_config_path(path)
    )


def _is_architecture_check_input(path: str) -> bool:
    return path.startswith(
        ("src/", "tests/architecture/", "docs/architecture/", "docs/adr/", "docs/specs/")
    ) or _is_global_check_config_path(path)


def _is_packaging_check_input(path: str) -> bool:
    return (
        path.startswith(("src/", "packages/", "frontend/dist/"))
        or surfaces.is_packaging_path(path)
        or _is_global_check_config_path(path)
    )


def _check_input_paths(name: str, changed_files: Sequence[str]) -> list[str]:
    """Return changed files that can affect ``name``'s reusable evidence."""

    normalized = sorted(
        {
            p
            for p in (surfaces.normalize_path(path) for path in changed_files)
            if p and not p.startswith(_CHECK_EVIDENCE_IGNORED_PREFIXES)
        }
    )
    spec = checks.CHECK_CATALOG.get(name)
    if spec is None:
        return normalized
    if name in {"full_audit", "deferral_discipline"}:
        return normalized
    if name == "semantic_dup":
        return [
            p
            for p in normalized
            if surfaces.sentrux_applies_to_changes([p])
            or p.startswith("docs/audit/baselines/semantic-dup")
            or _is_global_check_config_path(p)
        ]
    if spec.covered_surface == "python":
        return [p for p in normalized if _is_python_check_input(p)]
    if spec.covered_surface == "frontend":
        return [p for p in normalized if _is_frontend_check_input(p)]
    if spec.covered_surface == "architecture":
        return [p for p in normalized if _is_architecture_check_input(p)]
    if spec.covered_surface == "packaging":
        return [p for p in normalized if _is_packaging_check_input(p)]
    return normalized


def _check_input_fingerprint(
    repo_root: Path,
    name: str,
    *,
    base: str,
    head: str,
    staged: bool,
    changed_files: Sequence[str],
    diff_fingerprint: str | None,
) -> str | None:
    """Return the content fingerprint used to validate reusable check evidence.

    Gate ledger events are evidence ABOUT checks, not inputs TO source quality
    checks. Excluding committed ledger files prevents the finalize/evidence
    append loop from making every previously passing check stale. The remaining
    input set is per-check, so unrelated source surfaces do not invalidate
    evidence for a check they cannot affect.
    """

    covered_paths = _check_input_paths(name, changed_files)
    diff_text = io.diff_text(repo_root, base, head, staged=staged, paths=covered_paths) if covered_paths else ""
    input_text = diff_text if diff_text or not covered_paths else diff_fingerprint or ""
    fingerprint_body = "\n".join(
        [
            _CHECK_FINGERPRINT_VERSION,
            name,
            *covered_paths,
            "",
            input_text,
        ]
    )
    return "sha256:" + hashlib.sha256(fingerprint_body.encode("utf-8")).hexdigest()


def _valid_prior_check_event(
    ledger: GateLedger,
    *,
    name: str,
    input_fingerprint: str | None,
) -> CheckEvent | None:
    """Return the newest passing event for ``name`` that still covers this diff."""

    for event in reversed(ledger.check_events):
        if event.name == name and checks.event_is_valid_for(event, input_fingerprint=input_fingerprint):
            return event
    return None


def _validate_prior_check_events(
    ledger: GateLedger,
    *,
    required_names: Sequence[str],
    na_names: set[str],
    only: Sequence[str] | None,
    pr_readiness_mode: bool,
    input_fingerprints: Mapping[str, str | None],
) -> tuple[list[CheckEvent], list[str], list[str]]:
    """Validate reusable check evidence for the current candidate."""

    validated: list[CheckEvent] = []
    unsatisfied: list[str] = []
    repair_hints: list[str] = []
    to_validate = [name for name in required_names if name not in na_names]
    if only is not None:
        to_validate = [name for name in to_validate if name in set(only)]
    for name in to_validate:
        prior = _valid_prior_check_event(ledger, name=name, input_fingerprint=input_fingerprints.get(name))
        if prior is not None:
            validated.append(prior)
            continue
        if not pr_readiness_mode:
            continue
        unsatisfied.append(f"checks.{name}")
        repair_hints.append(
            f"- checks.{name}\n"
            "  Required check evidence is missing or stale for the current diff.\n"
            "  Run the incremental pre-PR check once, then retry this command:\n"
            "  gate_record check --mode pre-pr --base origin/main --head HEAD "
            "--pr-body-file .workflow/local/pr-body.md"
        )
    return validated, unsatisfied, repair_hints


def _select_checks_to_execute(
    ledger: GateLedger,
    *,
    required_names: Sequence[str],
    na_names: set[str],
    only: Sequence[str] | None,
    force_checks: bool,
    input_fingerprints: Mapping[str, str | None],
) -> tuple[list[str], list[CheckEvent]]:
    """Split required checks into current evidence vs checks to execute."""

    selected = [name for name in required_names if name not in na_names]
    if only is not None:
        selected = [name for name in selected if name in set(only)]
    to_run: list[str] = []
    current: list[CheckEvent] = []
    for name in selected:
        prior = (
            None
            if force_checks
            else _valid_prior_check_event(
                ledger,
                name=name,
                input_fingerprint=input_fingerprints.get(name),
            )
        )
        if prior is None:
            to_run.append(name)
        else:
            current.append(prior)
    return to_run, current


def reconcile(
    *,
    ledger: GateLedger,
    repo_root: Path,
    base: str,
    head: str,
    mode: EvaluatorMode,
    pr_body: str | None = None,
    pr_context: dict[str, Any] | None = None,
    run_checks: bool = True,
    force_checks: bool = False,
    only: Sequence[str] | None = None,
) -> ReconcileResult:
    """The single shared reconciliation entry point (spec §3.1)."""

    staged = mode == "pre-commit"

    # Modes that gate full PR readiness (docs/test/issue obligations are
    # required-now). pre-push validates scope/diff coherence + recorded-check
    # freshness only; it must NOT block a WIP push on PR-readiness obligations
    # (those belong to pre-pr / ci, §3.4).
    pr_readiness_mode = mode in ("pre-pr", "ci")

    # 1. Observe the git diff (objective evidence, never agent claims).
    observed_files = io.changed_files(repo_root, base, head, staged=staged)
    fingerprint = io.diff_fingerprint(repo_root, base, head, staged=staged)

    # 2. Classify surfaces.
    grouped = classify_surfaces(observed_files)

    # Record the authoritative branch/PR observation on the ledger. pre-commit
    # mode observes the transient staged index for hook decisions, so it must
    # not clobber the durable pre-pr/ci observation with an empty index diff.
    if mode != "pre-commit":
        ledger.observed_diff = ObservedDiff(
            base=base,
            head=head,
            base_sha=io.resolve_sha(repo_root, base),
            head_sha=io.resolve_sha(repo_root, head),
            diff_fingerprint=fingerprint,
            changed_files=list(observed_files),
            surfaces={name: len(paths) for name, paths in grouped.items()},
        )

    # 6. Derive tier (escalate, never lower). Done before check inference.
    tier = derive_tier(ledger.task_kind, grouped)
    ledger.strictness_tier = tier

    findings: list[AuditFinding] = []
    unsatisfied: list[str] = []
    repair_hints: list[str] = []
    parity_gaps: list[str] = []

    # 3. Reconcile declared scope against the PR-AUTHORED diff (first-parent,
    #    non-merge commits), NOT the full merge-base diff: merge-imported
    #    main-side changes must not be flagged as out-of-scope (#1463 Bug A).
    #    Integration/umbrella (manager) records and main-side renames downgrade
    #    out-of-scope to a non-blocking warning (#1283 / #1463 Bug B).
    scope_files = io.scope_changed_files(repo_root, base, head, staged=staged)
    scope_findings = _scope_findings(ledger, scope_files, repo_root=repo_root, base=base, head=head)
    findings.extend(scope_findings)
    # Surface BLOCKING scope violations as unsatisfied obligations so the CLI
    # actually fails on them (previously scope findings only flipped the report
    # status, which run_check/run_finalize never inspected -> scope violations
    # silently passed at the CLI). Warning-severity scope findings (integration
    # records / rename tolerance) stay non-blocking.
    blocking_scope = [f for f in scope_findings if f.severity == Severity.ERROR]
    if blocking_scope:
        unsatisfied.append("scope.out-of-scope")
        offenders = ", ".join(sorted({f.file for f in blocking_scope if f.file})[:5])
        repair_hints.append(
            "- scope.out-of-scope\n"
            f"  Changed files outside the declared scope: {offenders}\n"
            "  Amend the scope to include them (cite the reason) or move them out of this PR:\n"
            "  gate_record amend --reason '<why>' --include '<glob>'"
        )

    # 4. Reconcile declared docs/test claims (claimed-but-unverified, §3.3.4).
    verified_docs, unverified_docs = _verify_claims(ledger.declared_docs_paths(), observed_files)
    verified_tests, unverified_tests = _verify_claims(ledger.declared_test_paths(), observed_files)

    # ci mode aligns docs/test satisfaction to the workflow-gate role (§7.5):
    # documentation that LANDED and tests that CHANGED are visible in the git
    # diff, so the workflow-gate validates them from the observed diff without
    # requiring separately declared docs_events/test_events. Git-observed facts
    # are trusted over declarations, so observed docs/test surfaces augment the
    # verified sets used by the obligations and the docs_landing guard. local /
    # pre-pr keep their declared-evidence behavior unchanged.
    if mode == "ci":
        observed_docs = _observed_docs_evidence(grouped)
        observed_tests = _observed_test_evidence(grouped)
        verified_docs = sorted({*verified_docs, *observed_docs})
        verified_tests = sorted({*verified_tests, *observed_tests})
    for path in unverified_docs:
        findings.append(
            AuditFinding(
                rule_id="docs.claimed-but-unverified",
                severity=Severity.WARNING,
                file=path,
                message="declared docs path is not in the observed diff; does not satisfy a docs obligation",
            )
        )
    for path in unverified_tests:
        findings.append(
            AuditFinding(
                rule_id="tests.claimed-but-unverified",
                severity=Severity.WARNING,
                file=path,
                message="declared test path is not in the observed diff; does not satisfy a test obligation",
            )
        )

    # 7. Infer tier-selected required check set from the CI graph.
    selection = checks.select_checks(tier=tier, changed_files=observed_files)
    parity_gaps.extend(selection.parity_gaps)

    # In ci mode the workflow-gate job does NOT own the ci.yml quality matrix
    # (§7.5): those checks run as separate authoritative ci.yml jobs on the same
    # PR. Drop them from the required obligations so the shared evaluator does
    # not re-require ledger check_events for them (which would duplicate ci.yml
    # and block on evidence the workflow-gate job was never meant to demand).
    # local / pre-pr keep the full CI-equivalent preflight selection.
    if mode == "ci":
        selection.required = [name for name in selection.required if name not in _CI_OWNED_QUALITY_CHECKS]

    # pre-commit is a fast local gate: drop the two slowest checks (#1628). This
    # removes them from BOTH the required obligations and the executed set below,
    # so a commit is neither required to prove nor runs them; pre-pr / CI keep the
    # full selection. Governance guards and the fast checks still run at commit.
    if mode == "pre-commit":
        selection.required = [name for name in selection.required if name not in _PRE_COMMIT_SKIP_CHECKS]

    # 5. Infer obligations.
    obligations = _infer_obligations(
        task_kind=ledger.task_kind,
        tier=tier,
        grouped=grouped,
        required_checks=selection.required,
    )
    ledger.required_obligations = obligations

    # 8. Execute / validate checks with parity (§7.10), unless skipping.
    check_events: list[CheckEvent] = []
    # A --check-na for a ci.yml-OWNED check has NO force (ci.yml is authoritative
    # and runs it regardless, §7.5/Fix B): such an N/A may not waive the check for
    # PR readiness. Only N/A for task-specific / non-ci-owned checks waives. We do
    # NOT add an ERROR finding (that would block); we emit a loud non-blocking
    # warning and simply ignore the N/A for the ci-owned check.
    warnings: list[str] = []
    ci_owned_na = sorted({na.name for na in ledger.check_na} & _CI_OWNED_QUALITY_CHECKS)
    na_names = {na.name for na in ledger.check_na} - _CI_OWNED_QUALITY_CHECKS
    for name in ci_owned_na:
        warnings.append(
            f"--check-na '{name}:...' has NO force: '{name}' is owned by ci.yml and the "
            "standalone CI job runs it regardless. It does not waive that obligation for PR "
            "readiness; the N/A is recorded but ignored for this check. Fix the check or rely on CI."
        )
    if run_checks and mode not in ("commit-msg",):
        input_fps = {
            name: _check_input_fingerprint(
                repo_root,
                name,
                base=base,
                head=head,
                staged=staged,
                changed_files=observed_files,
                diff_fingerprint=fingerprint,
            )
            for name in selection.required
        }
        to_run, current_events = _select_checks_to_execute(
            ledger,
            required_names=selection.required,
            na_names=na_names,
            only=only,
            force_checks=force_checks,
            input_fingerprints=input_fps,
        )
        check_events.extend(current_events)
        # §7.10: for LOCAL preflight modes this AUTO-PROVISIONS the isolated
        # per-worktree venv with CI-equivalent deps and validates importability
        # inside it, so the checks below run at CI tool versions in an equivalent
        # environment. CRITICAL: ``ci`` mode never provisions — ci.yml owns its
        # own quality matrix and environment — so we pass ``mode`` through and
        # only validate the PYTHONPATH=src fallback in CI mode.
        if to_run:
            parity_report = parity.assess_parity(repo_root, mode=mode)
            if mode in ("pre-pr", "ci") and not parity_report.importable:
                # Fail closed for PR readiness (exit 4 surfaced by the CLI).
                parity_gaps.extend(parity_report.gaps)
            elif parity_report.gaps:
                # Non-PR-readiness local modes still surface provisioning failures so
                # the agent sees them, but do not hard-fail a WIP invocation.
                parity_gaps.extend(parity_report.gaps)
        for name in to_run:
            event = checks.run_check(
                repo_root,
                name,
                changed_files=observed_files,
                diff_fingerprint=fingerprint,
                input_fingerprint=input_fps.get(name),
            )
            check_events.append(event)
            ledger.check_events.append(event)
            if event.status == "skipped":
                # FAIL CLOSED (§7.5): a REQUIRED check that comes back "skipped"
                # (e.g. its tool is genuinely unavailable and the skip is NOT a
                # recorded parity gap, NOT an explicit --check-na — those are
                # already removed from ``to_run`` above) is unproven, not proven
                # passing. Silently passing it would let a required obligation
                # slip. For PR-readiness modes treat it as unsatisfied with a
                # clear repair hint; non-PR-readiness local modes still record
                # the event but do not block a WIP invocation.
                if pr_readiness_mode:
                    unsatisfied.append(f"checks.{name}")
                    repair_hints.append(
                        f"- checks.{name}\n  Required check was SKIPPED (tool unavailable): {event.summary}\n"
                        f"  Make the tool available and re-run, record an explicit N/A "
                        f"(gate_record amend --reason '<why>' --check-na '{name}:<rationale>'), or rely on CI.\n"
                        f"  {event.command}"
                    )
                continue
            if event.status != "fail":
                continue
            if event.parity_gap:
                # ENVIRONMENT-PARITY cause, not a code failure (§7.10): the local
                # environment is not CI-equivalent (a dep/plugin/tool CI has is
                # missing locally). Report it distinctly and fail closed for PR
                # readiness rather than surfacing a misleading code failure. Do
                # NOT auto-install anything.
                detail = event.parity_detail or "local environment is not CI-equivalent"
                gap = (
                    f"{name}: local environment is not CI-equivalent: {detail}; "
                    "reproduce the CI env (e.g. install the dev/test extras into an "
                    "isolated per-worktree env) and re-run check, or rely on CI"
                )
                parity_gaps.append(gap)
            else:
                unsatisfied.append(f"checks.{name}")
                hint = f"- checks.{name}\n  Re-run the check after fixing:\n  {event.command}"
                excerpt = _failed_check_excerpt(repo_root, event)
                if excerpt:
                    hint += f"\n  --- {name} output (tail) ---\n{excerpt}"
                repair_hints.append(hint)
    elif mode not in ("commit-msg",):
        # Reuse previously recorded passing check evidence instead of executing
        # local commands. This is the fast path used by finalize and PR
        # creation: it is only PR-ready when every required check has current
        # evidence for the observed diff fingerprint.
        input_fps = {
            name: _check_input_fingerprint(
                repo_root,
                name,
                base=base,
                head=head,
                staged=staged,
                changed_files=observed_files,
                diff_fingerprint=fingerprint,
            )
            for name in selection.required
        }
        validated, evidence_gaps, evidence_hints = _validate_prior_check_events(
            ledger,
            required_names=selection.required,
            na_names=na_names,
            only=only,
            pr_readiness_mode=pr_readiness_mode,
            input_fingerprints=input_fps,
        )
        check_events.extend(validated)
        unsatisfied.extend(evidence_gaps)
        repair_hints.extend(evidence_hints)

    # Docs/test obligations unsatisfied when no verified evidence and no N/A.
    # These are PR-readiness obligations: local and pre-pr/ci enforce them, but
    # pre-push (a WIP push) does NOT block on them (§3.4).
    docs_na = any(event.kind == "na" for event in ledger.docs_events)
    tests_na = any(event.kind == "na" for event in ledger.test_events)
    if mode != "pre-push":
        if obligations.docs and not verified_docs and not docs_na:
            unsatisfied.append("docs.docs_required_or_na")
            repair_hints.append(
                "- docs.docs_required_or_na\n  Record a docs path or N/A:\n"
                "  gate_record amend --reason '<why>' --docs-na 'implementation:<rationale>'"
            )
        if obligations.tests and not verified_tests and not tests_na:
            unsatisfied.append("tests.changed_test_required")
            repair_hints.append(
                "- tests.changed_test_required\n  Add a changed test path:\n"
                "  gate_record amend --reason '<why>' --test-path tests/<area>/test_<x>.py"
            )

    # Issue obligation (required before PR readiness, §7.7.3). Not enforced on a
    # WIP pre-push: an in-scope push must not be blocked as if opening a PR.
    if pr_readiness_mode and not ledger.issues:
        unsatisfied.append("issue.required")
        repair_hints.append("- issue.required\n  Link an issue:\n  gate_record amend --reason '<why>' --issue <n>")

    # 9. Run guard calculators (each exactly once, §3.3.9). Build the evaluator-
    #    supplied inputs the calculators expect (the integration wiring §4 needs):
    #    - extras['governed_diff_text'] / ['governed_diff_lines']: the governed-
    #      surface diff hunks for weakened_ci_check + mod_guard;
    #    - extras['sentrux_evidence']: recorded Sentrux evidence for sentrux_gate;
    #    - extras['docs_na']: recorded docs N/A rationales for docs_landing;
    #    - pr_context: merge_intent / reviews / observed-label provenance for
    #      core_change_guard / human_bypass_guard / pr_merge_guard (pre-pr/ci).
    governed_surfaces = sorted(set(grouped["governance"]) | set(grouped["workflow_ci"]) | set(grouped["packaging"]))
    governed_diff = io.diff_text(repo_root, base, head, staged=staged, paths=governed_surfaces)
    extras: dict[str, Any] = {
        "governed_diff_text": governed_diff,
        "docs_na": _docs_na_rationales(ledger),
    }
    sentrux_evidence = _recorded_sentrux_evidence(ledger)
    if sentrux_evidence is not None:
        extras["sentrux_evidence"] = sentrux_evidence
    # Observed labels the guards read = committed ledger labels merged with the
    # CI PR-context labels (which carry the authoritative actor/permission
    # provenance the GitHub workflow resolved). In CI the ledger's set is empty,
    # so this is how a maintainer-applied admin label reaches the guards;
    # provenance from the live context wins per name.
    context_labels = _observed_labels_from_context(pr_context)
    effective_observed_labels = _merge_observed_labels(ledger.observed_admin_labels, context_labels)
    effective_pr_context = _build_pr_context(ledger, mode, pr_context, effective_observed_labels)

    guard_inputs = GuardInputs(
        repo_root=repo_root,
        mode=mode,
        task_kind=ledger.task_kind,
        persona=ledger.persona,
        runtime=ledger.runtime,
        tier=tier,
        governance_touch=ledger.governance_touch,
        changed_files=list(observed_files),
        diff_fingerprint=fingerprint,
        surfaces={name: list(paths) for name, paths in grouped.items()},
        effective_include=ledger.effective_include(),
        effective_exclude=ledger.effective_exclude(),
        declared_docs_paths=ledger.declared_docs_paths(),
        declared_test_paths=ledger.declared_test_paths(),
        verified_docs_paths=verified_docs,
        verified_test_paths=verified_tests,
        issues=list(ledger.issues),
        pr_body=pr_body,
        pr_context=effective_pr_context,
        requested_admin_labels=list(ledger.requested_admin_labels),
        observed_admin_labels=effective_observed_labels,
        extras=extras,
    )
    # Guards whose findings are PR-readiness obligations (docs landing, linked
    # issue). On a WIP pre-push they still RUN and record, but they do not block
    # the push (§3.4); the diff-coherence guards below still block on pre-push.
    _pr_readiness_guards = {"docs_landing", "issue_link"}
    guard_reports: list[AuditReport] = []
    guard_events: list[GuardEvent] = []
    for name in sorted(GUARD_REGISTRY):
        guard = GUARD_REGISTRY[name]
        report = guard(guard_inputs)
        guard_reports.append(report)
        guard_status: Literal["pass", "fail"] = "fail" if report.blocks_merge else "pass"
        guard_event = GuardEvent(
            guard=name,
            status=guard_status,
            findings=[f.model_dump(mode="json") for f in report.findings],
        )
        guard_events.append(guard_event)
        ledger.guard_events.append(guard_event)
        if report.blocks_merge:
            if mode == "pre-push" and name in _pr_readiness_guards:
                continue
            unsatisfied.append(f"guard.{name}")
            findings.extend(report.error_findings())
            repair_hints.append(_guard_repair_hint(name, report))

    # Parity gaps fail closed for PR readiness. The detailed gap text (which can
    # carry tool/venv error tails) is surfaced to the CONSOLE via
    # ``ReconcileResult.parity_gaps``; the COMMITTED ledger records only a
    # generic, sanitized token per gap so no local-machine detail (absolute
    # paths, venv paths) ever lands in ``reconcile_event.unsatisfied`` (§8).
    if mode in ("pre-pr", "ci") and parity_gaps:
        for _gap in parity_gaps:
            unsatisfied.append("parity.environment-not-ci-equivalent")

    has_error_finding = any(finding.severity == Severity.ERROR for finding in findings)
    result_status = AuditStatus.FAIL if (has_error_finding or unsatisfied) else AuditStatus.PASS
    source_sha = ledger.observed_diff.head_sha if ledger.observed_diff is not None else io.resolve_sha(repo_root, head)
    report = AuditReport(
        tool="gate_record.evaluator",
        status=result_status,
        source_sha=source_sha or "unknown",
        findings=findings,
        summary={
            "mode": mode,
            "tier": tier,
            "task_kind": ledger.task_kind,
            "required_checks": selection.required,
            "pr_only_checks": selection.pr_only,
        },
        child_reports=guard_reports,
    )

    # 10. Write a reconcile event.
    reconcile_event = ReconcileEvent(
        mode=mode,
        tier=tier,
        diff_fingerprint=fingerprint,
        result="pass" if not unsatisfied and not report.blocks_merge else "fail",
        unsatisfied=sorted(set(unsatisfied)),
    )
    ledger.reconcile_events.append(reconcile_event)

    return ReconcileResult(
        report=report,
        strictness_tier=tier,
        required_obligations=obligations,
        unsatisfied=sorted(set(unsatisfied)),
        repair_hints=repair_hints,
        check_events=check_events,
        guard_events=guard_events,
        reconcile_event=reconcile_event,
        parity_gaps=parity_gaps,
        warnings=warnings,
    )
