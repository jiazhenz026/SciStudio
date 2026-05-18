from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
for module_name in list(sys.modules):
    if module_name == "scieasy" or module_name.startswith("scieasy."):
        del sys.modules[module_name]

from scieasy.qa.schemas.frontmatter import Phase  # noqa: E402
from scieasy.qa.schemas.report import AuditReport, Severity  # noqa: E402
from scieasy.qa.schemas.tracker import ImplementationTracker, SectionStatus  # noqa: E402
from scieasy.qa.tracker.adr_implementation_check import run  # noqa: E402


def test_schema_imports_are_available() -> None:
    assert Phase.PHASE_1.value == "phase-1"
    assert AuditReport.model_fields["runs"].is_required()
    assert ImplementationTracker.model_fields["sections"].is_required()


def test_checked_in_tracker_yaml_validates_without_claiming_implemented() -> None:
    payload = yaml.safe_load((REPO_ROOT / "docs/audit/adr-042-implementation-tracker.yaml").read_text())
    tracker = ImplementationTracker.model_validate(payload)

    assert tracker.adr == 42
    assert tracker.sections
    assert all(entry.status != SectionStatus.IMPLEMENTED for entry in tracker.sections)
    assert all(entry.status != SectionStatus.VERIFIED for entry in tracker.sections)


def test_implementation_check_reports_missing_tracker_without_traceback(tmp_path: Path) -> None:
    report = run(tmp_path)
    findings = report.runs[0].findings

    assert report.total_findings == 1
    assert findings[0].severity == Severity.ERROR
    assert findings[0].rule_id == "implementation-tracker.missing"
