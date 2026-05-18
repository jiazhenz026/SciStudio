"""Tests for ``scieasy.qa.schemas.frontmatter`` (ADR-042 §5).

Covers:
- Every ``_common`` regex pattern (positive + negative).
- All four ``ADRFrontmatter`` model_validators.
- ``SpecFrontmatter._code_impl_requires_governs_and_tests``.
- ``extra="forbid"`` rejection on every model.
- JSON Schema export (Draft 2020-12).
- Round-trip via ``model_dump_json`` / ``model_validate_json``.
- ``model_rebuild`` resolved the ``AgentRuntime`` forward ref.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import TypeAdapter, ValidationError

from scieasy.qa.schemas._common import (
    ADRRef,
    AssistedByLine,
    DottedModulePath,
    FunctionOrClassPath,
    GitHandle,
    IssueRef,
    LocaleCode,
    PathGlob,
    RepoRelativePath,
)
from scieasy.qa.schemas.frontmatter import (
    ADRFrontmatter,
    AgentEditable,
    Amendment,
    AmendmentKind,
    Governs,
    Phase,
    SpecFrontmatter,
    Status,
    Translation,
)
from scieasy.qa.schemas.maintainers import AgentRuntime

# --------------------------------------------------------------------------- #
# _common regex / bound primitives                                            #
# --------------------------------------------------------------------------- #


def _validate(alias: object, value: object) -> None:
    """Helper: run ``TypeAdapter(alias).validate_python(value)``."""
    TypeAdapter(alias).validate_python(value)


@pytest.mark.parametrize(
    "value",
    ["a", "src/scieasy/qa/__init__.py", "docs/adr/ADR-042.md", "x.y"],
)
def test_repo_relative_path_accepts(value: str) -> None:
    _validate(RepoRelativePath, value)


@pytest.mark.parametrize(
    "value",
    ["/abs/path", "trailing/", "", "/", "x/"],
)
def test_repo_relative_path_rejects(value: str) -> None:
    with pytest.raises(ValidationError):
        _validate(RepoRelativePath, value)


@pytest.mark.parametrize(
    "value",
    ["src/scieasy/**", "**/*.py", "docs/adr/ADR-*.md", "a"],
)
def test_path_glob_accepts(value: str) -> None:
    _validate(PathGlob, value)


def test_path_glob_rejects_empty() -> None:
    with pytest.raises(ValidationError):
        _validate(PathGlob, "")


@pytest.mark.parametrize(
    "value",
    ["scieasy", "scieasy.qa", "scieasy.qa.schemas.frontmatter", "_private.mod"],
)
def test_dotted_module_path_accepts(value: str) -> None:
    _validate(DottedModulePath, value)


@pytest.mark.parametrize(
    "value",
    ["Scieasy", "scieasy.Qa", "scieasy..qa", "scieasy.", ".scieasy", "1bad"],
)
def test_dotted_module_path_rejects(value: str) -> None:
    with pytest.raises(ValidationError):
        _validate(DottedModulePath, value)


@pytest.mark.parametrize(
    "value",
    [
        "scieasy.qa.schemas.frontmatter.ADRFrontmatter",
        "scieasy.qa.schemas.report.AuditReport",
        "scieasy.qa.module.func_name",
    ],
)
def test_function_or_class_path_accepts(value: str) -> None:
    _validate(FunctionOrClassPath, value)


@pytest.mark.parametrize(
    "value",
    ["scieasy", "ADRFrontmatter", "scieasy.qa.", "1bad.X"],
)
def test_function_or_class_path_rejects(value: str) -> None:
    with pytest.raises(ValidationError):
        _validate(FunctionOrClassPath, value)


@pytest.mark.parametrize("value", ["@claude", "@codex", "@jiazhenz026", "@a"])
def test_git_handle_accepts(value: str) -> None:
    _validate(GitHandle, value)


@pytest.mark.parametrize("value", ["claude", "@", "@-bad", "@_x", ""])
def test_git_handle_rejects(value: str) -> None:
    with pytest.raises(ValidationError):
        _validate(GitHandle, value)


@pytest.mark.parametrize(
    "value",
    [
        "Claude:claude-opus-4-7",
        "Codex:gpt-5 [Bash,Read]",
        "Gemini:1.5-pro",
    ],
)
def test_assisted_by_line_accepts(value: str) -> None:
    _validate(AssistedByLine, value)


@pytest.mark.parametrize("value", ["Claude", "claude-opus-4-7", "Claude::dup", ""])
def test_assisted_by_line_rejects(value: str) -> None:
    with pytest.raises(ValidationError):
        _validate(AssistedByLine, value)


@pytest.mark.parametrize("value", ["en", "zh-CN", "fr", "pt-BR"])
def test_locale_code_accepts(value: str) -> None:
    _validate(LocaleCode, value)


@pytest.mark.parametrize("value", ["EN", "en-cn", "english", "zh_CN", ""])
def test_locale_code_rejects(value: str) -> None:
    with pytest.raises(ValidationError):
        _validate(LocaleCode, value)


@pytest.mark.parametrize("value", [1, 42, 9999])
def test_adr_ref_accepts(value: int) -> None:
    _validate(ADRRef, value)


@pytest.mark.parametrize("value", [0, -1, 10000])
def test_adr_ref_rejects(value: int) -> None:
    with pytest.raises(ValidationError):
        _validate(ADRRef, value)


@pytest.mark.parametrize("value", [1, 42, 100000])
def test_issue_ref_accepts(value: int) -> None:
    _validate(IssueRef, value)


@pytest.mark.parametrize("value", [0, -5])
def test_issue_ref_rejects(value: int) -> None:
    with pytest.raises(ValidationError):
        _validate(IssueRef, value)


# --------------------------------------------------------------------------- #
# Governs / Translation / Amendment                                           #
# --------------------------------------------------------------------------- #


def test_governs_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        Governs.model_validate({"modules": [], "unknown": "x"})


def test_governs_defaults() -> None:
    g = Governs()
    assert g.modules == [] and g.contracts == [] and g.files == []


def test_translation_round_trip() -> None:
    t = Translation(locale="zh-CN", path="docs/zh-CN/adr/ADR-042.md")
    dumped = t.model_dump_json()
    reloaded = Translation.model_validate_json(dumped)
    assert reloaded == t
    assert reloaded.auto_generated is True


def test_translation_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        Translation.model_validate({"locale": "en", "path": "docs/x.md", "extra_field": "no"})


def test_amendment_round_trip() -> None:
    a = Amendment(target="ADR-042 §17 Required Skills", kind=AmendmentKind.EXTEND, summary="add gemini")
    reloaded = Amendment.model_validate_json(a.model_dump_json())
    assert reloaded == a


def test_amendment_kind_values() -> None:
    assert {k.value for k in AmendmentKind} == {"extend", "replace", "constrain", "clarify"}


def test_amendment_summary_length_bounds() -> None:
    with pytest.raises(ValidationError):
        Amendment(target="ADR-042 §17", kind=AmendmentKind.CLARIFY, summary="x")
    with pytest.raises(ValidationError):
        Amendment(target="ADR-042 §17", kind=AmendmentKind.CLARIFY, summary="x" * 241)


# --------------------------------------------------------------------------- #
# Status / AgentEditable / Phase enums                                        #
# --------------------------------------------------------------------------- #


def test_status_values() -> None:
    assert {s.value for s in Status} == {
        "Draft",
        "Proposed",
        "Accepted",
        "Superseded",
        "Withdrawn",
        "Deprecated",
    }


def test_agent_editable_values() -> None:
    assert {v.value for v in AgentEditable} == {"true", "false", "allowlist"}


def test_phase_values() -> None:
    expected = {
        "planning",
        "phase-0",
        "phase-1",
        "phase-1-5",
        "phase-2",
        "phase-3",
        "phase-4",
        "phase-5",
        "complete",
    }
    assert {p.value for p in Phase} == expected


# --------------------------------------------------------------------------- #
# ADRFrontmatter — fixtures + happy path                                       #
# --------------------------------------------------------------------------- #


def _valid_adr_kwargs() -> dict[str, object]:
    """Return a kwargs dict that constructs a valid Accepted ADRFrontmatter."""
    return {
        "adr": 42,
        "title": "QA Infrastructure Overhaul",
        "status": Status.ACCEPTED,
        "date_created": date(2026, 5, 17),
        "date_accepted": date(2026, 5, 18),
        "is_code_implementation": True,
        "governs": Governs(modules=["scieasy.qa"]),
        "tests": ["tests/qa/test_schemas_frontmatter.py"],
        "owner": "@jiazhenz026",
    }


def test_adr_frontmatter_happy_path() -> None:
    fm = ADRFrontmatter(**_valid_adr_kwargs())
    assert fm.adr == 42
    assert fm.status == Status.ACCEPTED
    assert fm.agent_editable == AgentEditable.FALSE


def test_adr_frontmatter_extra_forbid() -> None:
    kwargs = _valid_adr_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        ADRFrontmatter.model_validate(kwargs)


def test_adr_frontmatter_round_trip() -> None:
    fm = ADRFrontmatter(**_valid_adr_kwargs())
    dumped = fm.model_dump_json()
    reloaded = ADRFrontmatter.model_validate_json(dumped)
    assert reloaded == fm


# --------------------------------------------------------------------------- #
# ADRFrontmatter validators — negative + positive                              #
# --------------------------------------------------------------------------- #


def test_agent_editable_allowlist_requires_list() -> None:
    kwargs = _valid_adr_kwargs()
    kwargs["agent_editable"] = AgentEditable.ALLOWLIST
    with pytest.raises(ValidationError, match="non-empty agent_editable_allowlist"):
        ADRFrontmatter.model_validate(kwargs)


def test_agent_editable_allowlist_paired_ok() -> None:
    kwargs = _valid_adr_kwargs()
    kwargs["agent_editable"] = AgentEditable.ALLOWLIST
    kwargs["agent_editable_allowlist"] = [AgentRuntime.CLAUDE]
    fm = ADRFrontmatter.model_validate(kwargs)
    assert fm.agent_editable_allowlist == [AgentRuntime.CLAUDE]


def test_agent_editable_allowlist_invalid_without_allowlist_flag() -> None:
    kwargs = _valid_adr_kwargs()
    kwargs["agent_editable_allowlist"] = [AgentRuntime.CLAUDE]
    with pytest.raises(ValidationError, match="only valid when agent_editable=allowlist"):
        ADRFrontmatter.model_validate(kwargs)


def test_status_accepted_requires_date_accepted() -> None:
    kwargs = _valid_adr_kwargs()
    kwargs["date_accepted"] = None
    with pytest.raises(ValidationError, match="status=Accepted requires date_accepted"):
        ADRFrontmatter.model_validate(kwargs)


def test_status_superseded_requires_dates_and_replacement() -> None:
    kwargs = _valid_adr_kwargs()
    kwargs["status"] = Status.SUPERSEDED
    with pytest.raises(ValidationError, match="status=Superseded requires"):
        ADRFrontmatter.model_validate(kwargs)


def test_status_superseded_requires_superseded_by() -> None:
    """SUPERSEDED + date but missing ``superseded_by`` is rejected (covers line 212)."""
    kwargs = _valid_adr_kwargs()
    kwargs["status"] = Status.SUPERSEDED
    kwargs["date_superseded"] = date(2026, 6, 1)
    with pytest.raises(ValidationError, match="superseded_by"):
        ADRFrontmatter.model_validate(kwargs)


def test_status_superseded_full() -> None:
    kwargs = _valid_adr_kwargs()
    kwargs["status"] = Status.SUPERSEDED
    kwargs["date_superseded"] = date(2026, 6, 1)
    kwargs["superseded_by"] = 100
    fm = ADRFrontmatter.model_validate(kwargs)
    assert fm.status == Status.SUPERSEDED
    assert fm.superseded_by == 100


def test_code_impl_requires_governs() -> None:
    kwargs = _valid_adr_kwargs()
    kwargs["governs"] = Governs()  # empty
    with pytest.raises(ValidationError, match=r"non-empty governs\.modules or governs\.contracts"):
        ADRFrontmatter.model_validate(kwargs)


def test_code_impl_requires_tests() -> None:
    kwargs = _valid_adr_kwargs()
    kwargs["tests"] = []
    with pytest.raises(ValidationError, match="is_code_implementation=true requires non-empty tests"):
        ADRFrontmatter.model_validate(kwargs)


def test_non_code_impl_skips_governs_check() -> None:
    kwargs = _valid_adr_kwargs()
    kwargs["is_code_implementation"] = False
    kwargs["governs"] = Governs()
    kwargs["tests"] = []
    fm = ADRFrontmatter.model_validate(kwargs)
    assert not fm.is_code_implementation


def test_no_self_supersede_via_supersedes() -> None:
    kwargs = _valid_adr_kwargs()
    kwargs["supersedes"] = [42]
    with pytest.raises(ValidationError, match="ADR cannot supersede itself"):
        ADRFrontmatter.model_validate(kwargs)


def test_no_self_supersede_via_superseded_by() -> None:
    kwargs = _valid_adr_kwargs()
    kwargs["status"] = Status.SUPERSEDED
    kwargs["date_superseded"] = date(2026, 6, 1)
    kwargs["superseded_by"] = 42
    with pytest.raises(ValidationError, match="ADR cannot be superseded by itself"):
        ADRFrontmatter.model_validate(kwargs)


# --------------------------------------------------------------------------- #
# SpecFrontmatter                                                              #
# --------------------------------------------------------------------------- #


def _valid_spec_kwargs() -> dict[str, object]:
    return {
        "spec_id": "qa-pipeline",
        "title": "QA Pipeline Spec",
        "status": "Active",
        "date_created": date(2026, 5, 17),
        "is_code_implementation": True,
        "governs": Governs(modules=["scieasy.qa"]),
        "tests": ["tests/qa/test_schemas_frontmatter.py"],
        "owner": "@jiazhenz026",
    }


def test_spec_frontmatter_happy_path() -> None:
    spec = SpecFrontmatter(**_valid_spec_kwargs())
    assert spec.spec_id == "qa-pipeline"
    assert spec.language_source == "en"


def test_spec_frontmatter_extra_forbid() -> None:
    kwargs = _valid_spec_kwargs()
    kwargs["unknown"] = "x"
    with pytest.raises(ValidationError):
        SpecFrontmatter.model_validate(kwargs)


def test_spec_code_impl_planned_governs_satisfies() -> None:
    """``is_code_implementation=true`` with only ``planned_governs`` is OK."""
    kwargs = _valid_spec_kwargs()
    kwargs["governs"] = Governs()
    kwargs["planned_governs"] = Governs(modules=["scieasy.qa.future"])
    spec = SpecFrontmatter.model_validate(kwargs)
    assert spec.planned_governs.modules == ["scieasy.qa.future"]


def test_spec_code_impl_requires_some_governs() -> None:
    kwargs = _valid_spec_kwargs()
    kwargs["governs"] = Governs()
    with pytest.raises(ValidationError, match="non-empty governs OR planned_governs"):
        SpecFrontmatter.model_validate(kwargs)


def test_spec_code_impl_requires_tests() -> None:
    kwargs = _valid_spec_kwargs()
    kwargs["tests"] = []
    with pytest.raises(ValidationError, match="requires non-empty tests"):
        SpecFrontmatter.model_validate(kwargs)


def test_spec_id_pattern_rejects_uppercase() -> None:
    kwargs = _valid_spec_kwargs()
    kwargs["spec_id"] = "QA-Pipeline"
    with pytest.raises(ValidationError):
        SpecFrontmatter.model_validate(kwargs)


def test_spec_status_literal_rejects_unknown() -> None:
    kwargs = _valid_spec_kwargs()
    kwargs["status"] = "Accepted"  # SpecFrontmatter uses a narrower literal
    with pytest.raises(ValidationError):
        SpecFrontmatter.model_validate(kwargs)


# --------------------------------------------------------------------------- #
# JSON Schema export (Draft 2020-12)                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "model",
    [
        Governs,
        Translation,
        Amendment,
        ADRFrontmatter,
        SpecFrontmatter,
    ],
)
def test_json_schema_export(model: type) -> None:
    schema = model.model_json_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema or schema.get("$ref")
    # Draft 2020-12 is pydantic v2 default; verify the dialect URI either
    # absent (delegated to bundle root) or matches the expected dialect.
    if "$schema" in schema:
        assert "2020-12" in schema["$schema"]


def test_model_rebuild_resolved_forward_ref() -> None:
    """Confirm ``AgentRuntime`` forward ref no longer raises on validation.

    Manager-default per Phase 1 investigation SUMMARY TC-1A.1: the
    ``model_rebuild()`` call at package init forces pydantic to resolve
    the ``agent_editable_allowlist: list[AgentRuntime]`` annotation.
    """
    kwargs = _valid_adr_kwargs()
    kwargs["agent_editable"] = AgentEditable.ALLOWLIST
    # Pass the value as a string — pydantic v2 must coerce to AgentRuntime
    # via the forward-resolved enum, which only works after model_rebuild.
    kwargs["agent_editable_allowlist"] = ["Claude"]
    fm = ADRFrontmatter.model_validate(kwargs)
    assert fm.agent_editable_allowlist == [AgentRuntime.CLAUDE]
