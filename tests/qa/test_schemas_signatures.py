from __future__ import annotations

import pytest
from pydantic import ValidationError

from scieasy.qa.schemas.signatures import (
    ExpectedCliCommand,
    ExpectedModelField,
    ExpectedParameter,
    ExpectedSignature,
    ParameterSpec,
)


def test_expected_signature_schema_accepts_function_contract() -> None:
    signature = ExpectedSignature(
        subject="sample.func",
        kind="function",
        parameters=[ExpectedParameter(name="value", kind="positional or keyword", annotation="str")],
        return_annotation="bool",
        source_path="docs/specs/example.md",
        line=12,
    )

    assert signature.parameters[0].name == "value"
    assert isinstance(signature.parameters[0], ParameterSpec)
    assert signature.symbol == "sample.func"
    assert signature.source_spec == "docs/specs/example.md"
    assert signature.source_line == 12


def test_expected_signature_accepts_adr042_aliases() -> None:
    signature = ExpectedSignature(
        symbol="sample.func",
        kind="method",
        source_spec="docs/specs/example.md",
        source_line=12,
    )

    assert signature.subject == "sample.func"
    assert signature.source_path == "docs/specs/example.md"
    assert signature.line == 12


def test_expected_signature_rejects_empty_subject() -> None:
    with pytest.raises(ValidationError):
        ExpectedSignature(subject="", kind="class", source_path="docs/specs/example.md", line=1)


def test_expected_model_field_and_cli_command_schemas() -> None:
    field = ExpectedModelField(
        model_symbol="sample.Model",
        field_name="name",
        annotation="str",
        source_spec="docs/specs/example.md",
        source_line=20,
    )
    command = ExpectedCliCommand(
        command=["scieasy", "audit"],
        expected_exit_codes={0: "ok"},
        source_spec="docs/specs/example.md",
        source_line=30,
    )

    assert field.required
    assert command.command == ["scieasy", "audit"]
