"""Ratchet wrapper for the ADR-042/043/044 QA cascade (TC-1G.1).

Implements the *zero-tolerance + monotonic ratchet* enforcement model
described in ADR-042 §4.3 (verbatim, lines 481-526).

Why this exists
---------------

ADR-042 §4.3 states zero-tolerance: there is no ``baseline.json`` of
tolerated violations and CI is red from Phase 2 until Phase 3 cleanup
completes.  Mechanically, GitHub branch protection only accepts a required
status check whose ``conclusion`` is one of ``success``, ``skipped``, or
``neutral``.

The GitHub *branch protection* documentation states (verbatim, retrieved
2026-05-17 via the URL below):

    "Required status checks must have a `successful`, `skipped`, or
    `neutral` status before collaborators can make changes to a
    protected branch."

    -- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/defining-the-mergeability-of-pull-requests/about-protected-branches

The GitHub *Checks API* documentation states (verbatim, retrieved
2026-05-17 via the URL below):

    "Required. The final conclusion of the check.  Can be one of
    ``action_required``, ``cancelled``, ``failure``, ``neutral``,
    ``success``, ``skipped``, ``stale``, or ``timed_out``."

    -- https://docs.github.com/en/rest/checks/runs#update-a-check-run

By having the per-tool wrapper report ``conclusion=neutral`` on monotonic
decrease (current ≤ previous AND no new file regressed), cleanup PRs are
mergeable even while a tool still shows a non-zero finding count — without
the wrapper ever lying about the absolute number to the developer.

When the count increases or a previously-clean file regresses, the wrapper
reports ``conclusion=failure``, which blocks merge.

This is the same ratchet pattern used by FastAPI + mypy and by GitHub
Code Scanning's ``partialFingerprints`` feature.

Scope of this module
--------------------

This module exposes:

* :func:`compute_ratchet_decision` — pure function over (previous baseline,
  current findings) that returns a :class:`RatchetDecision`.  Pure, easily
  unit-tested, has no GitHub API dependency.

* :func:`emit_checks_api_payload` — turn a :class:`RatchetDecision` into
  the JSON payload to POST to the Checks API.  Pure dict construction; the
  HTTP transport is intentionally not in this module (Phase 2 deliverable).

* ``__main__`` CLI — ``python -m workflow_ci.ratchet --tool=ruff
  --current=findings.json [--baselines-dir=...]`` for local invocation and
  CI smoke tests.  Exit code 0 = neutral or success, 1 = failure.

Out of scope (intentional)
--------------------------

* HTTP calls to the Checks API.  Phase 2 (CI flip) wires that.
  See TODO below.
* SARIF emission.  See :mod:`.sarif` for that.
* Per-file diff-based regression detection beyond *new-file regression*
  (a file that was absent or zero in the baseline and is non-zero now).
  Richer diff semantics are Phase 3 territory.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

if __package__ in (None, ""):
    # Direct script invocation: ``python .workflow/ci/ratchet.py``.
    # Insert the parent directory on sys.path and import absolutely.  This
    # keeps the CLI usable without requiring ``-m`` or any sys.path
    # configuration on the caller's part.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ci.baselines import read_baseline
else:
    from .baselines import read_baseline

# TODO(#1138-followup): wire HTTP transport for Checks API once Phase 2 begins.
#   Out of scope per ADR-042 §4.3 (Phase 1 ships infrastructure; Phase 2 flips CI).
#   Followup: open as part of ADR-042 Phase 2 wiring sub-issue.


CheckConclusion = Literal["success", "neutral", "failure"]


@dataclasses.dataclass(frozen=True, slots=True)
class RatchetDecision:
    """Result of comparing a current run against the previous baseline.

    Attributes:
        tool: Tool identifier (e.g. ``"ruff"``).
        conclusion: One of ``"success"`` (zero findings), ``"neutral"``
            (count strictly decreased OR equal with no new-file regression),
            or ``"failure"`` (count increased OR new-file regression).
        previous_total: Previous total finding count read from the baseline.
        current_total: Current total finding count from the run under
            evaluation.
        delta: ``current_total - previous_total``.
        new_file_regressions: Sorted list of file paths absent or zero in
            baseline but non-zero in the current run.  Always empty when
            ``conclusion`` is ``"success"`` and may be empty when
            ``conclusion`` is ``"neutral"``.
        message: Human-readable one-line summary suitable for the Checks
            API ``output.title`` field.
    """

    tool: str
    conclusion: CheckConclusion
    previous_total: int
    current_total: int
    delta: int
    new_file_regressions: tuple[str, ...]
    message: str


def compute_ratchet_decision(
    *,
    tool: str,
    current_total: int,
    current_per_file: Mapping[str, int] | None,
    previous_baseline: Mapping[str, Any],
) -> RatchetDecision:
    """Decide ``neutral`` / ``success`` / ``failure`` for a single tool run.

    This is the **core** ratchet logic.  It is a pure function: same inputs
    always produce the same :class:`RatchetDecision`.

    Args:
        tool: Tool identifier.
        current_total: Current run's total finding count.
        current_per_file: Optional per-file finding counts for the current
            run.  When ``None``, new-file regression detection is skipped
            (only count-monotonic enforcement applies).
        previous_baseline: Parsed baseline dict (as returned by
            :func:`.baselines.read_baseline`).

    Returns:
        :class:`RatchetDecision`.

    Raises:
        ValueError: When ``current_total`` is negative.
    """
    if current_total < 0:
        raise ValueError(f"current_total must be >= 0, got {current_total}")

    previous_total = int(previous_baseline.get("total_findings", 0))
    previous_per_file: dict[str, int] = dict(previous_baseline.get("per_file", {}))

    delta = current_total - previous_total

    new_file_regressions: list[str] = []
    if current_per_file is not None:
        for path, count in current_per_file.items():
            if count <= 0:
                continue
            if previous_per_file.get(path, 0) == 0:
                new_file_regressions.append(path)
        new_file_regressions.sort()

    conclusion: CheckConclusion
    if current_total == 0 and not new_file_regressions:
        conclusion = "success"
        message = f"{tool}: 0 findings (clean)."
    elif new_file_regressions:
        conclusion = "failure"
        message = (
            f"{tool}: {len(new_file_regressions)} previously-clean file(s) regressed "
            f"(current_total={current_total}, previous_total={previous_total})."
        )
    elif delta > 0:
        conclusion = "failure"
        message = f"{tool}: finding count increased {previous_total} -> {current_total} (+{delta})."
    else:
        # delta <= 0 AND no new-file regression.  This is the ratchet's
        # raison d'etre per ADR-042 §4.3: report neutral so the PR can
        # merge under branch protection while the count is still non-zero.
        conclusion = "neutral"
        message = f"{tool}: finding count {previous_total} -> {current_total} (delta={delta})."

    return RatchetDecision(
        tool=tool,
        conclusion=conclusion,
        previous_total=previous_total,
        current_total=current_total,
        delta=delta,
        new_file_regressions=tuple(new_file_regressions),
        message=message,
    )


def emit_checks_api_payload(decision: RatchetDecision) -> dict[str, Any]:
    """Build the JSON body for ``PATCH /repos/{owner}/{repo}/check-runs/{id}``.

    Per the Checks API docs, the required fields for a terminal update are
    ``status: "completed"``, ``conclusion``, and an ``output`` object.
    We populate ``output.title`` with the decision's ``message`` and
    ``output.summary`` with a verbatim dump of the decision so a reviewer
    inspecting the Checks UI can see the full diff at a glance.
    """
    return {
        "status": "completed",
        "conclusion": decision.conclusion,
        "output": {
            "title": decision.message,
            "summary": _format_summary(decision),
        },
    }


def _format_summary(decision: RatchetDecision) -> str:
    lines = [
        f"Tool: `{decision.tool}`",
        "",
        f"- previous_total: **{decision.previous_total}**",
        f"- current_total:  **{decision.current_total}**",
        f"- delta:          **{decision.delta:+d}**",
        f"- conclusion:     **{decision.conclusion}**",
    ]
    if decision.new_file_regressions:
        lines.extend(
            [
                "",
                "### New-file regressions",
                "",
                *[f"- `{p}`" for p in decision.new_file_regressions],
            ],
        )
    return "\n".join(lines)


# --- CLI ---------------------------------------------------------------


def _load_current_findings(path: Path) -> tuple[int, dict[str, int] | None]:
    """Load a current-run findings file.

    Supports two shapes:

    1. ``{"total": int, "per_file": {path: int, ...}}`` — preferred.
    2. ``{"total": int}`` — count-only (per-file regression detection
       disabled).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if "total" not in data:
        raise SystemExit(f"current findings file {path}: missing 'total' key")
    total = int(data["total"])
    per_file_raw = data.get("per_file")
    per_file: dict[str, int] | None = (
        None if per_file_raw is None else {str(k): int(v) for k, v in per_file_raw.items()}
    )
    return total, per_file


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ratchet",
        description=(
            "Ratchet wrapper for ADR-042 §4.3.  Reads previous baseline "
            "for --tool, compares to --current, prints decision JSON, and "
            "exits 0 on success/neutral or 1 on failure."
        ),
    )
    p.add_argument("--tool", required=True, help="Tool identifier (e.g. ruff).")
    p.add_argument(
        "--current",
        type=Path,
        required=True,
        help="Path to JSON file with current-run totals.",
    )
    p.add_argument(
        "--baselines-dir",
        type=Path,
        default=None,
        help="Directory containing per-tool baseline JSON files.",
    )
    p.add_argument(
        "--emit-payload",
        action="store_true",
        help="Print the Checks API payload (JSON) instead of the decision.",
    )
    return p.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    """CLI entry point.  Returns the intended process exit code."""
    args = _parse_args(argv)
    previous_baseline = read_baseline(args.tool, args.baselines_dir)
    current_total, current_per_file = _load_current_findings(args.current)
    decision = compute_ratchet_decision(
        tool=args.tool,
        current_total=current_total,
        current_per_file=current_per_file,
        previous_baseline=previous_baseline,
    )
    if args.emit_payload:
        print(json.dumps(emit_checks_api_payload(decision), indent=2))
    else:
        print(json.dumps(dataclasses.asdict(decision), indent=2))
    return 0 if decision.conclusion != "failure" else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
