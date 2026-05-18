"""Minimal ADR-043 section 2.5 phase gate validator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from scieasy.qa.schemas.frontmatter import Phase
from scieasy.qa.schemas.report import Finding, Severity
from scieasy.qa.schemas.tracker import SectionStatus
from scieasy.qa.tracker.adr_implementation_check import TRACKER_PATH, load_tracker, make_finding, resolve_repo_root
from scieasy.qa.tracker.tool_self_test_runner import run_self_test

PHASE_ORDER: tuple[Phase, ...] = (
    Phase.PHASE_0,
    Phase.PHASE_1,
    Phase.PHASE_1_5,
    Phase.PHASE_2,
    Phase.PHASE_3,
    Phase.PHASE_4,
    Phase.PHASE_5,
    Phase.COMPLETE,
)


def check_phase_transition(from_phase: Phase, to_phase: Phase) -> Literal["ok", "blocked"]:
    """Verify Phase N to N+1 readiness for the current repository."""
    findings = collect_phase_gate_findings(from_phase, to_phase)
    return "blocked" if any(finding.severity == Severity.ERROR for finding in findings) else "ok"


def collect_phase_gate_findings(from_phase: Phase, to_phase: Phase, repo_root: Path | None = None) -> list[Finding]:
    """Collect blocking findings for a phase transition."""
    root = resolve_repo_root(repo_root)
    findings: list[Finding] = []

    findings.extend(_validate_transition_shape(from_phase, to_phase))
    tracker, tracker_findings = load_tracker(root)
    findings.extend(tracker_findings)

    if tracker is not None:
        for entry in tracker.sections:
            # TODO(#1113): Add explicit tracker phase assignment once the full tracker schema lands.
            #   Out of scope per ADR-043 §2 skeleton; every current tracker entry is treated as in-scope.
            #   Followup: #1113.
            if entry.status != SectionStatus.VERIFIED:
                findings.append(
                    make_finding(
                        "phase-gate.tracker-entry-not-verified",
                        f"{entry.section} blocks {from_phase}->{to_phase}: status is {entry.status}.",
                        file=TRACKER_PATH,
                    )
                )

            # TODO(#1113): Check implemented_in_pr references are merged before allowing phase transitions.
            #   Out of scope per ADR-043 §2 skeleton; requires GitHub PR state.
            #   Followup: #1113.

    findings.extend(run_self_test("all", root))

    return findings


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for phase-transition validation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", required=True, help="Transition in the form phase-1->phase-2.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        from_phase, to_phase = _parse_transition(args.check)
    except ValueError as exc:
        print(f"Invalid phase transition: {exc}")
        return 2

    findings = collect_phase_gate_findings(from_phase, to_phase, args.repo_root)
    if args.json:
        print(json.dumps([finding.model_dump(mode="json") for finding in findings], indent=2))
    elif findings:
        print(f"PHASE {from_phase} -> {to_phase} BLOCKED.")
        for finding in findings:
            print(f"  [{finding.severity}] {finding.rule_id}: {finding.message}")
    else:
        print(f"PHASE {from_phase} -> {to_phase} readiness check passed.")

    return 1 if any(finding.severity == Severity.ERROR for finding in findings) else 0


def _validate_transition_shape(from_phase: Phase, to_phase: Phase) -> list[Finding]:
    try:
        from_index = PHASE_ORDER.index(from_phase)
        to_index = PHASE_ORDER.index(to_phase)
    except ValueError:
        return [
            make_finding(
                "phase-gate.unknown-phase",
                f"Phase transition uses a phase outside the ADR-042 rollout order: {from_phase}->{to_phase}.",
                file=TRACKER_PATH,
            )
        ]

    if to_index != from_index + 1:
        return [
            make_finding(
                "phase-gate.non-sequential-transition",
                f"Phase transition must advance exactly one phase, got {from_phase}->{to_phase}.",
                file=TRACKER_PATH,
            )
        ]
    return []


def _parse_transition(value: str) -> tuple[Phase, Phase]:
    if "->" not in value:
        raise ValueError("expected '<from-phase>-><to-phase>'")
    raw_from, raw_to = (part.strip() for part in value.split("->", 1))
    return Phase(raw_from), Phase(raw_to)


if __name__ == "__main__":
    raise SystemExit(main())
