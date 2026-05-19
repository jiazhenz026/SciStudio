from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit.signature_drift import check_expected_signatures
from scieasy.qa.schemas.facts import Fact, FactsRegistry
from scieasy.qa.schemas.signatures import ExpectedParameter, ExpectedSignature


def _expected_fact(signature: ExpectedSignature) -> Fact:
    return Fact(
        id=f"expected-signature:{signature.subject}",
        kind="expected-signature",
        source=signature.source_path,
        subject=signature.subject,
        value=signature.model_dump(mode="json"),
        source_sha="abc123",
        confidence="normative",
    )


def test_signature_drift_reports_missing_symbol() -> None:
    signature = ExpectedSignature(
        subject="sample.func",
        kind="function",
        source_path="docs/specs/example.md",
        line=10,
    )
    facts = FactsRegistry(source_sha="abc123", facts=[_expected_fact(signature)])

    report = check_expected_signatures(Path("."), facts)

    assert report.findings[0].rule_id == "signature-drift.missing-symbol"


def test_signature_drift_reports_parameter_mismatch() -> None:
    signature = ExpectedSignature(
        subject="sample.func",
        kind="function",
        parameters=[ExpectedParameter(name="value", kind="positional or keyword", annotation="str")],
        return_annotation="bool",
        source_path="docs/specs/example.md",
        line=10,
    )
    actual = Fact(
        id="symbol:sample.func",
        kind="symbol",
        source="griffe",
        subject="sample.func",
        value={
            "kind": "function",
            "parameters": [{"name": "count", "annotation": "int", "required": True}],
            "return_annotation": "bool",
        },
        source_sha="abc123",
        confidence="generated",
    )
    facts = FactsRegistry(source_sha="abc123", facts=[_expected_fact(signature), actual])

    report = check_expected_signatures(Path("."), facts)

    assert [finding.rule_id for finding in report.findings] == ["signature-drift.parameters-mismatch"]
