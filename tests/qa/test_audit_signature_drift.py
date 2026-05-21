from __future__ import annotations

from pathlib import Path

from scistudio.qa.audit.signature_drift import check_expected_signatures
from scistudio.qa.schemas.facts import Fact, FactsRegistry
from scistudio.qa.schemas.signatures import ExpectedCliCommand, ExpectedModelField, ExpectedParameter, ExpectedSignature


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


def _expected_model_field_fact(field: ExpectedModelField) -> Fact:
    return Fact(
        id=f"expected-model-field:{field.model_symbol}.{field.field_name}",
        kind="expected-model-field",
        source=field.source_spec,
        subject=f"{field.model_symbol}.{field.field_name}",
        value=field.model_dump(mode="json"),
        source_sha="abc123",
        confidence="normative",
    )


def _expected_cli_command_fact(command: ExpectedCliCommand) -> Fact:
    subject = " ".join(command.command)
    return Fact(
        id=f"expected-cli-command:{subject}",
        kind="expected-cli-command",
        source=command.source_spec,
        subject=subject,
        value=command.model_dump(mode="json"),
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


def test_signature_drift_checks_pydantic_model_fields(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "sample_model.py").write_text(
        "from pydantic import BaseModel\n\nclass SampleModel(BaseModel):\n    name: str\n",
        encoding="utf-8",
    )
    field = ExpectedModelField(
        model_symbol="sample_model.SampleModel",
        field_name="name",
        annotation="str",
        source_spec="docs/specs/example.md",
        source_line=10,
    )
    facts = FactsRegistry(source_sha="abc123", facts=[_expected_model_field_fact(field)])

    report = check_expected_signatures(tmp_path, facts)

    assert report.status == "pass"
    assert report.summary["expected_model_fields_checked"] == 1


def test_signature_drift_reports_cli_exit_code_mismatch() -> None:
    command = ExpectedCliCommand(
        command=["scistudio", "audit"],
        expected_exit_codes={0: "success"},
        source_spec="docs/specs/example.md",
        source_line=20,
    )
    actual = Fact(
        id="cli:scistudio audit",
        kind="cli",
        source="fixture",
        subject="scistudio audit",
        value={"exit_codes": {1: "failure"}},
        source_sha="abc123",
        confidence="generated",
    )
    facts = FactsRegistry(source_sha="abc123", facts=[_expected_cli_command_fact(command), actual])

    report = check_expected_signatures(Path("."), facts)

    assert [finding.rule_id for finding in report.findings] == ["signature-drift.cli-exit-codes-mismatch"]
