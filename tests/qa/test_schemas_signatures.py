from __future__ import annotations

import pytest
from pydantic import ValidationError

from scieasy.qa.schemas.signatures import ExpectedParameter, ExpectedSignature


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


def test_expected_signature_rejects_empty_subject() -> None:
    with pytest.raises(ValidationError):
        ExpectedSignature(subject="", kind="class", source_path="docs/specs/example.md", line=1)
