"""Tests for ``scieasy.qa.workflow.gate`` (ADR-042 §19.5).

Covers:

- ``StageContext`` field shapes (especially ``pr_number: int | None``
  and ``declared_data: dict[str, object]`` accepting arbitrary inner
  values).
- ``ValidationResult`` ``status: Literal["pass", "fail", "skip"]``
  rejects unknown values and accepts each documented one.
- ``ValidationResult.blocking`` defaults to True.
- ``Validator`` Protocol ``isinstance`` check (the
  ``@runtime_checkable`` decorator — Phase 1 investigation SUMMARY X2
  manager default — must classify a class with the right shape as a
  ``Validator``, and reject one missing fields / call signature).
- ``StageDefinition`` dataclass:
  - all required fields wire up,
  - ``sub_checklist`` defaults to ``[]`` via ``field(default_factory=list)``,
  - each instance has its own ``sub_checklist`` (no shared mutable default),
  - ``validations`` accepts Validator-shaped objects.
"""

from __future__ import annotations

import dataclasses

import pytest
from pydantic import ValidationError

from scieasy.qa.workflow.gate import (
    StageContext,
    StageDefinition,
    ValidationResult,
    Validator,
)

# --------------------------------------------------------------------------- #
# StageContext                                                                #
# --------------------------------------------------------------------------- #


def _ctx(**overrides: object) -> StageContext:
    base: dict[str, object] = {
        "task_id": "20260518-052816-feat-1130",
        "stage_name": "implement_validate",
        "repo_root": "/repo",
        "pr_number": None,
        "branch": "feat/issue-1130/phase-1a-b",
        "declared_data": {},
    }
    base.update(overrides)
    return StageContext(**base)  # type: ignore[arg-type]


def test_stage_context_basic() -> None:
    ctx = _ctx()
    assert ctx.pr_number is None
    assert ctx.declared_data == {}


def test_stage_context_pr_number_can_be_int() -> None:
    ctx = _ctx(pr_number=42)
    assert ctx.pr_number == 42


def test_stage_context_declared_data_accepts_arbitrary_inner_shape() -> None:
    payload: dict[str, object] = {
        "issue_number": 1130,
        "files": ["a.py", "b.py"],
        "nested": {"key": [1, 2, 3]},
        "flag": True,
        "absent": None,
    }
    ctx = _ctx(declared_data=payload)
    assert ctx.declared_data == payload


def test_stage_context_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        _ctx(unknown="boom")


def test_stage_context_round_trip() -> None:
    src = _ctx(pr_number=7, declared_data={"k": "v"})
    rebuilt = StageContext.model_validate_json(src.model_dump_json())
    assert rebuilt == src


# --------------------------------------------------------------------------- #
# ValidationResult                                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("status", ["pass", "fail", "skip"])
def test_validation_result_accepts_documented_status(status: str) -> None:
    r = ValidationResult(validator_id="v1", status=status, message="ok")  # type: ignore[arg-type]
    assert r.status == status
    assert r.blocking is True


@pytest.mark.parametrize("status", ["ok", "PASS", "warning", ""])
def test_validation_result_rejects_unknown_status(status: str) -> None:
    with pytest.raises(ValidationError):
        ValidationResult(validator_id="v1", status=status, message="x")  # type: ignore[arg-type]


def test_validation_result_blocking_override() -> None:
    r = ValidationResult(validator_id="v", status="pass", message="ok", blocking=False)
    assert r.blocking is False


def test_validation_result_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        ValidationResult(
            validator_id="v",
            status="pass",
            message="x",
            rogue=True,  # type: ignore[call-arg]
        )


# --------------------------------------------------------------------------- #
# Validator Protocol (@runtime_checkable)                                     #
# --------------------------------------------------------------------------- #


class _GoodValidator:
    """A class whose shape satisfies the Validator protocol."""

    validator_id = "good"
    blocking = True

    def __call__(self, ctx: StageContext) -> ValidationResult:
        return ValidationResult(validator_id=self.validator_id, status="pass", message="ok")


class _MissingAttrValidator:
    """Lacks ``blocking`` — should not satisfy the protocol."""

    validator_id = "incomplete"

    def __call__(self, ctx: StageContext) -> ValidationResult:
        return ValidationResult(validator_id="incomplete", status="pass", message="x")


class _NotCallable:
    validator_id = "noncallable"
    blocking = True


def test_validator_protocol_accepts_matching_class() -> None:
    # @runtime_checkable lets isinstance see the shape — SUMMARY X2.
    assert isinstance(_GoodValidator(), Validator)


def test_validator_protocol_rejects_missing_attribute() -> None:
    # Protocol membership is structural: a class missing ``blocking``
    # must not be classified as a Validator.
    assert not isinstance(_MissingAttrValidator(), Validator)


def test_validator_protocol_rejects_non_callable() -> None:
    assert not isinstance(_NotCallable(), Validator)


def test_validator_protocol_callable_actually_runs() -> None:
    v = _GoodValidator()
    ctx = _ctx()
    result = v(ctx)
    assert isinstance(result, ValidationResult)
    assert result.status == "pass"


# --------------------------------------------------------------------------- #
# StageDefinition dataclass                                                   #
# --------------------------------------------------------------------------- #


def test_stage_definition_minimal_fields() -> None:
    stage = StageDefinition(
        name="implement_validate",
        requires=["branch"],
        validations=[],
        guidance_template="Run local CI and report.",
        auto_advance=True,
    )
    assert stage.name == "implement_validate"
    assert stage.requires == ["branch"]
    assert stage.validations == []
    assert stage.auto_advance is True
    # sub_checklist default is an EMPTY list via field(default_factory=list).
    assert stage.sub_checklist == []


def test_stage_definition_sub_checklist_default_is_per_instance() -> None:
    s1 = StageDefinition(
        name="a",
        requires=[],
        validations=[],
        guidance_template="",
        auto_advance=False,
    )
    s2 = StageDefinition(
        name="b",
        requires=[],
        validations=[],
        guidance_template="",
        auto_advance=False,
    )
    s1.sub_checklist.append("item")
    # If sub_checklist were a shared mutable default (the common Python
    # bug), s2.sub_checklist would also contain "item". Verify the
    # default_factory wired things up correctly.
    assert s2.sub_checklist == []


def test_stage_definition_accepts_validator_in_validations() -> None:
    v = _GoodValidator()
    stage = StageDefinition(
        name="x",
        requires=[],
        validations=[v],
        guidance_template="",
        auto_advance=False,
    )
    # Pull the validator back out and exercise it.
    [registered] = stage.validations
    assert isinstance(registered, Validator)
    result = registered(_ctx())
    assert result.status == "pass"


def test_stage_definition_is_a_dataclass() -> None:
    assert dataclasses.is_dataclass(StageDefinition)


def test_stage_definition_sub_checklist_explicit() -> None:
    stage = StageDefinition(
        name="x",
        requires=[],
        validations=[],
        guidance_template="",
        auto_advance=False,
        sub_checklist=["a", "b", "c"],
    )
    assert stage.sub_checklist == ["a", "b", "c"]
