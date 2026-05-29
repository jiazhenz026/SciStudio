"""Task-specific instruction generator for ``init`` (ADR-042 Addendum 6 §7.5).

Renders, from task kind + persona + tier + scope + issues + governance-touch,
the guidance the agent needs at each workflow concern, plus the §7.7.4 task-kind
and §7.7.5 persona CLI argument profiles. Instructions are guidance; ``check``
remains authoritative (§5.2).
"""

from __future__ import annotations

from collections.abc import Sequence

from scistudio.qa.governance.gate_record.ledger import Persona, StrictnessTier, TaskKind

# §7.7.4 task-kind CLI argument profiles (condensed to the load-bearing args).
_TASK_PROFILE: dict[str, dict[str, str]] = {
    "hotfix": {
        "plan": "plan --owner-directive '<bug list>' --include <path> [--issue <n>] (--test-path <p> | --test-na '<class>:<why>') (--docs-updated <p> | --docs-na '<class>:<why>')",
        "check": "check --base <base> --head HEAD [--test-path <p>] [--admin-label <label>]",
    },
    "bugfix": {
        "plan": "plan --include <path> (--test-path <regression-test> | --test-na '<class>:<why>') (--docs-updated <p> | --docs-na '<class>:<why>')",
        "check": "check --base <base> --head HEAD [--test-path <p>]",
    },
    "feature": {
        "plan": "plan --include <impl-path> --test-path <test-path> --docs-updated <doc-or-spec-path> [--admin-label <label>]",
        "check": "check --base <base> --head HEAD [--include <p>] [--test-path <p>] [--docs-updated <p>]",
    },
    "refactor": {
        "plan": "plan --include <path> (--test-path <behavior-preservation-test> | --test-na '<class>:<why>') (--docs-updated <p> | --docs-na '<class>:<why>')",
        "check": "check --base <base> --head HEAD [--test-path <p>]",
    },
    "docs": {
        "plan": "plan --docs-updated <path> --test-na 'implementation:<docs-only rationale>' [--check full_audit]",
        "check": "check --base <base> --head HEAD [--docs-updated <p>] [--test-na 'implementation:<why>']",
    },
    "maintenance": {
        "plan": "plan --include <path> (--test-path <tooling-test> | --test-na '<class>:<why>') (--docs-updated <p> | --docs-na '<class>:<why>') [--admin-label <label>]",
        "check": "check --base <base> --head HEAD [--test-path <p>] [--admin-label <label>]",
    },
    "manager": {
        "plan": "plan --docs-updated <checklist-or-report-path> --test-na 'implementation:<manager-only rationale>'",
        "check": "check --base <base> --head HEAD [--docs-updated <p>] [--test-na 'implementation:<why>']",
    },
    "guided": {
        "plan": "plan --owner-directive '<current instruction>' [--include <p>] [--issue <n>] [--test-path <p>] [--docs-updated <p>]",
        "check": "check --base <base> --head HEAD [--owner-directive '<late instruction>'] [--include <p>] [--test-path <p>]",
    },
}

_TIER_NOTE: dict[int, str] = {
    1: "Tier 1 (strict): plan before implementation; check runs the full merge-blocking CI mirror.",
    2: "Tier 2 (standard): scope may emerge during work; check runs governance/lint/audit baseline plus changed-surface jobs.",
    3: "Tier 3 (lightweight): minimal up-front ceremony; check runs only mandatory checks for the observed diff.",
}


def generate_instructions(
    *,
    task_kind: TaskKind,
    persona: Persona,
    tier: StrictnessTier,
    branch: str,
    issues: Sequence[int],
    include: Sequence[str],
    governance_touch: bool,
    record_path: str,
) -> str:
    """Render the task-specific init instructions (§7.5)."""

    lines: list[str] = []
    lines.append(f"Gate ledger created: {record_path}")
    lines.append(f"Task identity: task_kind={task_kind}, persona={persona}, branch={branch}")
    lines.append(_TIER_NOTE.get(int(tier), ""))
    lines.append("")

    # Issue closure expectations.
    if issues:
        lines.append(f"Issues: {', '.join(f'#{n}' for n in issues)} (close in PR body).")
    else:
        lines.append(
            "Issue: none linked yet. Add one before PR readiness via "
            "`gate_record amend --reason '<why>' --issue <n>` "
            "(unless this is an owner-approved exploratory task)."
        )

    # Scope / directive rules.
    if task_kind in ("guided", "hotfix"):
        lines.append(
            "Scope: live owner-guided work. Record each meaningful owner instruction as a "
            "directive (`amend --owner-directive ...`); the observed diff must be explainable by "
            "directive events or amended scope before PR readiness."
        )
    elif include:
        lines.append(f"Scope: declared include = {list(include)}. Stay inside it; amend to expand.")
    else:
        lines.append("Scope: declare include paths via `plan --include <path>` before broad edits.")

    if governance_touch:
        lines.append(
            "Governance touch declared: edits to governance surfaces require owner review and "
            "the governance docs/closure checks (§7.8)."
        )

    # Likely docs/tests/checks.
    lines.append("")
    lines.append("Likely obligations (check infers the final set from the real diff):")
    if task_kind in ("docs", "manager"):
        lines.append("- Implementation tests N/A by default; docs/checklist landing required.")
    else:
        lines.append("- Implementation changes require test evidence (or an explicit, reviewable N/A).")
        lines.append("- Docs/spec/ADR/changelog landing required when contracts or behavior change.")
    lines.append("- Protected-core paths require an admin-approved:core-change label (verified in CI).")

    # CLI argument profiles for this task kind.
    profile = _TASK_PROFILE.get(task_kind, {})
    lines.append("")
    lines.append("Likely commands:")
    if profile.get("plan"):
        lines.append(f"  gate_record {profile['plan']}")
    if profile.get("check"):
        lines.append(f"  gate_record {profile['check']}")
    lines.append(
        "  gate_record finalize --base <base> --head HEAD --commit <sha> "
        "--pr-body-file <path> --closes '#<issue>'   # pre-PR"
    )
    lines.append("  gate_record finalize --commit <sha> --pr <url> --pr-body-file <path>   # post-PR")

    lines.append("")
    lines.append("`check` is authoritative: follow its 'Unsatisfied obligations' repair hints.")
    return "\n".join(line for line in lines if line is not None)
