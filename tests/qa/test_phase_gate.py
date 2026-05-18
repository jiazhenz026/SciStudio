from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
for module_name in list(sys.modules):
    if module_name == "scieasy" or module_name.startswith("scieasy."):
        del sys.modules[module_name]

from scieasy.qa.schemas.frontmatter import Phase  # noqa: E402
from scieasy.qa.tracker.phase_gate import check_phase_transition, collect_phase_gate_findings  # noqa: E402


def test_phase_gate_missing_tracker_blocks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert check_phase_transition(Phase.PHASE_1, Phase.PHASE_2) == "blocked"


def test_phase_gate_unverified_tracker_entry_blocks(tmp_path: Path) -> None:
    tracker_path = tmp_path / "docs/audit/adr-042-implementation-tracker.yaml"
    tracker_path.parent.mkdir(parents=True)
    tracker_path.write_text(
        """
adr: 42
schema_version: 1
sections:
  - section: "ADR-043 §2 Implementation Monitoring"
    requires_artifacts:
      files: []
      symbols: []
      tests: []
    verification_checks: []
    status: in_progress
    implemented_in_pr: null
    verified_at: null
    verifier_skill: null
    verifier_command: "pytest"
""".strip(),
        encoding="utf-8",
    )

    findings = collect_phase_gate_findings(Phase.PHASE_1, Phase.PHASE_2, tmp_path)

    assert any(finding.rule_id == "phase-gate.tracker-entry-not-verified" for finding in findings)


def test_phase_gate_non_sequential_transition_blocks(tmp_path: Path) -> None:
    findings = collect_phase_gate_findings(Phase.PHASE_1, Phase.PHASE_3, tmp_path)

    assert any(finding.rule_id == "phase-gate.non-sequential-transition" for finding in findings)
