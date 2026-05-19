from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from scieasy.qa.schemas.facts import Fact, FactsRegistry
from scieasy.qa.schemas.frontmatter import ADRFrontmatter
from scieasy.qa.schemas.maintainers import MaintainerRule, Maintainers
from scieasy.qa.schemas.report import AuditFinding, AuditReport
from scieasy.qa.schemas.signatures import ExpectedSignature


def test_audit_report_blocks_merge_on_error() -> None:
    report = AuditReport(
        tool="tool",
        status="failed",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_sha="abc",
        findings=[
            AuditFinding(
                id="f1",
                tool="tool",
                severity="error",
                finding_class="class",
                message="message",
            )
        ],
    )
    assert report.blocks_merge is True
    assert report.error_findings()[0].id == "f1"


def test_facts_registry_lookup() -> None:
    fact = Fact(
        id="fact-1",
        kind="file",
        source="docs/spec.md",
        subject="src/example.py",
        value={"exists": True},
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_sha="abc",
        confidence="normative",
        stability="stable",
    )
    registry = FactsRegistry(generated_at=datetime(2026, 1, 1, tzinfo=UTC), source_sha="abc", facts=[fact])
    assert registry.by_id()["fact-1"] == fact
    assert registry.find(kind="file", subject="src/example.py") == [fact]


def test_adr_frontmatter_requires_accepted_date() -> None:
    payload = {
        "adr": 1,
        "title": "Accepted decision",
        "status": "Accepted",
        "date_created": date(2026, 1, 1),
        "date_accepted": None,
        "date_superseded": None,
        "supersedes": [],
        "superseded_by": None,
        "related": [],
        "closes_issues": [],
        "tracking_issue": None,
        "is_code_implementation": False,
        "governs": {"modules": [], "contracts": [], "entry_points": [], "files": [], "excludes": []},
        "tests": [],
        "agent_editable": False,
        "assisted_by": [],
        "phase": "planning",
        "tags": [],
        "owner": "@owner",
        "co_authors": [],
        "translations": [],
    }
    with pytest.raises(ValidationError):
        ADRFrontmatter.model_validate(payload)


def test_maintainers_and_signature_models_validate() -> None:
    maintainers = Maintainers(rules=[MaintainerRule(pattern="src/**", owners=["@owner"])])
    signature = ExpectedSignature(symbol="scieasy.example.fn", kind="function", source_spec="spec.md", source_line=1)
    assert maintainers.rules[0].required_reviewers == 1
    assert signature.parameters == []
