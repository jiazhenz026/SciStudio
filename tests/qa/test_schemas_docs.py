"""Tests for ``scieasy.qa.docs.schemas`` (ADR-044 §5)."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from scieasy.qa.docs.schemas import (
    AutoGenSource,
    DocAudience,
    DocCategory,
    DocGuideFrontmatter,
    Generation,
    ProdAgentDocFrontmatter,
    UserDocFrontmatter,
    WorkflowDocFrontmatter,
)

# --------------------------------------------------------------------------- #
# Enums                                                                       #
# --------------------------------------------------------------------------- #


def test_generation_values_match_adr() -> None:
    assert {g.value for g in Generation} == {"auto", "hand", "hybrid"}


def test_doc_audience_values_match_adr() -> None:
    assert {a.value for a in DocAudience} == {
        "human",
        "agent",
        "both",
        "end-user",
        "operator",
        "maintainer",
    }


def test_doc_category_values_match_adr() -> None:
    assert {c.value for c in DocCategory} == {
        "contributing",
        "user",
        "prod-agent",
        "doc-guide",
    }


# --------------------------------------------------------------------------- #
# AutoGenSource                                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "kind",
    [
        "entry-points",
        "pydantic-model",
        "typer-cli",
        "openapi",
        "sphinx-autoapi",
        "facts-registry",
        "custom",
    ],
)
def test_auto_gen_source_kind_literal(kind: str) -> None:
    obj = AutoGenSource(
        kind=kind,  # type: ignore[arg-type]
        targets=["scieasy.qa.foo"],
        generator="scieasy.qa.docs.generators.gen_foo",
    )
    assert obj.kind == kind
    assert obj.last_generated_sha is None


def test_auto_gen_source_round_trip_with_sha() -> None:
    obj = AutoGenSource(
        kind="entry-points",
        targets=["scieasy.cli"],
        generator="scieasy.cli._gen",
        last_generated_sha="abc1234",
    )
    restored = AutoGenSource.model_validate_json(obj.model_dump_json())
    assert restored == obj


def test_auto_gen_source_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        AutoGenSource(
            kind="unsupported",  # type: ignore[arg-type]
            targets=[],
            generator="g",
        )


def test_auto_gen_source_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        AutoGenSource.model_validate(
            {
                "kind": "custom",
                "targets": [],
                "generator": "g",
                "extra": "boom",
            }
        )


# --------------------------------------------------------------------------- #
# WorkflowDocFrontmatter                                                      #
# --------------------------------------------------------------------------- #


def _valid_workflow_fm(**overrides: object) -> WorkflowDocFrontmatter:
    base: dict[str, object] = {
        "workflow_id": "ship-a-feature",
        "title": "Ship a feature",
        "audience": [DocAudience.HUMAN, DocAudience.AGENT],
        "maintenance_owner": "@jiazhenz026",
        "last_reviewed": date(2026, 5, 18),
    }
    base.update(overrides)
    return WorkflowDocFrontmatter(**base)  # type: ignore[arg-type]


def test_workflow_fm_round_trip() -> None:
    fm = _valid_workflow_fm()
    restored = WorkflowDocFrontmatter.model_validate_json(fm.model_dump_json())
    assert restored == fm
    assert restored.category == DocCategory.CONTRIBUTING
    assert restored.generation == Generation.HAND


def test_workflow_fm_id_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        _valid_workflow_fm(workflow_id="UPPER-CASE")
    with pytest.raises(ValidationError):
        _valid_workflow_fm(workflow_id="1-leading-digit")


def test_workflow_fm_title_length_bounds() -> None:
    with pytest.raises(ValidationError):
        _valid_workflow_fm(title="abc")  # too short
    with pytest.raises(ValidationError):
        _valid_workflow_fm(title="x" * 121)  # too long


def test_workflow_fm_exception_validator_requires_pair() -> None:
    """length_exception_reason without length_exception_issue must fail."""
    with pytest.raises(ValidationError) as exc:
        _valid_workflow_fm(length_exception_reason="needs split, see #999")
    assert "length_exception_issue" in str(exc.value)


def test_workflow_fm_exception_validator_passes_with_pair() -> None:
    fm = _valid_workflow_fm(
        length_exception_reason="see #999",
        length_exception_issue=999,
    )
    assert fm.length_exception_issue == 999


def test_workflow_fm_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        WorkflowDocFrontmatter.model_validate(
            {
                "workflow_id": "ok",
                "title": "valid",
                "audience": ["human"],
                "maintenance_owner": "@x",
                "last_reviewed": "2026-05-18",
                "extra": "boom",
            }
        )


# --------------------------------------------------------------------------- #
# UserDocFrontmatter                                                          #
# --------------------------------------------------------------------------- #


def _valid_user_fm(**overrides: object) -> UserDocFrontmatter:
    base: dict[str, object] = {
        "doc_id": "getting/started",
        "title": "Getting started",
        "audience": [DocAudience.END_USER],
        "generation": Generation.HAND,
        "maintenance_owner": "@jiazhenz026",
        "last_reviewed": date(2026, 5, 18),
    }
    base.update(overrides)
    return UserDocFrontmatter(**base)  # type: ignore[arg-type]


def test_user_fm_hand_does_not_require_source() -> None:
    fm = _valid_user_fm()
    assert fm.source is None


def test_user_fm_auto_requires_source() -> None:
    with pytest.raises(ValidationError) as exc:
        _valid_user_fm(generation=Generation.AUTO)
    assert "source" in str(exc.value)


def test_user_fm_hybrid_requires_source() -> None:
    with pytest.raises(ValidationError):
        _valid_user_fm(generation=Generation.HYBRID)


def test_user_fm_auto_with_source_ok() -> None:
    fm = _valid_user_fm(
        generation=Generation.AUTO,
        source=AutoGenSource(
            kind="entry-points",
            targets=["scieasy.cli"],
            generator="scieasy.cli._gen",
        ),
    )
    assert fm.generation == Generation.AUTO
    assert fm.source is not None


def test_user_fm_doc_id_pattern_allows_slashes() -> None:
    """Per §5.3 user doc_id regex includes `/`."""
    fm = _valid_user_fm(doc_id="getting/started/install")
    assert fm.doc_id == "getting/started/install"


def test_user_fm_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        UserDocFrontmatter.model_validate(
            {
                "doc_id": "ok",
                "title": "valid",
                "audience": ["end-user"],
                "generation": "hand",
                "maintenance_owner": "@x",
                "last_reviewed": "2026-05-18",
                "extra": "boom",
            }
        )


# --------------------------------------------------------------------------- #
# ProdAgentDocFrontmatter                                                     #
# --------------------------------------------------------------------------- #


def _valid_prod_fm(**overrides: object) -> ProdAgentDocFrontmatter:
    base: dict[str, object] = {
        "doc_id": "adr-040-overview",
        "title": "ADR-040 overview",
        "audience": [DocAudience.OPERATOR],
        "maintenance_owner": "@jiazhenz026",
        "last_reviewed": date(2026, 5, 18),
    }
    base.update(overrides)
    return ProdAgentDocFrontmatter(**base)  # type: ignore[arg-type]


def test_prod_fm_defaults() -> None:
    fm = _valid_prod_fm()
    assert fm.category == DocCategory.PROD_AGENT
    assert fm.generation == Generation.HAND
    assert fm.governs_adr == 40
    assert fm.related_addenda == []


@pytest.mark.parametrize("a", ["A1", "A2", "A3", "A4"])
def test_prod_fm_addenda_literal(a: str) -> None:
    fm = _valid_prod_fm(related_addenda=[a])  # type: ignore[list-item]
    assert fm.related_addenda == [a]


def test_prod_fm_rejects_unknown_addendum() -> None:
    with pytest.raises(ValidationError):
        _valid_prod_fm(related_addenda=["A99"])  # type: ignore[list-item]


def test_prod_fm_rejects_non_40_governs_adr() -> None:
    with pytest.raises(ValidationError):
        _valid_prod_fm(governs_adr=41)  # type: ignore[arg-type]


def test_prod_fm_round_trip() -> None:
    fm = _valid_prod_fm(related_addenda=["A1", "A2"])  # type: ignore[list-item]
    restored = ProdAgentDocFrontmatter.model_validate_json(fm.model_dump_json())
    assert restored == fm


def test_prod_fm_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        ProdAgentDocFrontmatter.model_validate(
            {
                "doc_id": "ok",
                "title": "valid",
                "audience": ["operator"],
                "maintenance_owner": "@x",
                "last_reviewed": "2026-05-18",
                "extra": "boom",
            }
        )


# --------------------------------------------------------------------------- #
# DocGuideFrontmatter                                                         #
# --------------------------------------------------------------------------- #


def _valid_guide_fm(**overrides: object) -> DocGuideFrontmatter:
    base: dict[str, object] = {
        "doc_id": "style-guide",
        "title": "Documentation style guide",
        "applies_to_categories": [DocCategory.USER, DocCategory.CONTRIBUTING],
        "maintenance_owner": "@jiazhenz026",
        "last_reviewed": date(2026, 5, 18),
    }
    base.update(overrides)
    return DocGuideFrontmatter(**base)  # type: ignore[arg-type]


def test_guide_fm_defaults() -> None:
    fm = _valid_guide_fm()
    assert fm.category == DocCategory.DOC_GUIDE
    assert fm.generation == Generation.HAND
    assert fm.related_adrs == []


def test_guide_fm_applies_to_categories_required() -> None:
    """``applies_to_categories`` is required (no default) per §5.5."""
    with pytest.raises(ValidationError):
        DocGuideFrontmatter(  # type: ignore[call-arg]
            doc_id="x",
            title="valid",
            maintenance_owner="@x",
            last_reviewed=date(2026, 5, 18),
        )


def test_guide_fm_round_trip() -> None:
    fm = _valid_guide_fm()
    restored = DocGuideFrontmatter.model_validate_json(fm.model_dump_json())
    assert restored == fm


def test_guide_fm_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        DocGuideFrontmatter.model_validate(
            {
                "doc_id": "ok",
                "title": "valid",
                "applies_to_categories": ["user"],
                "maintenance_owner": "@x",
                "last_reviewed": "2026-05-18",
                "extra": "boom",
            }
        )


# --------------------------------------------------------------------------- #
# Cross-schema: ``Translation`` import path                                   #
# --------------------------------------------------------------------------- #


def test_translation_imported_from_frontmatter_works() -> None:
    """SUMMARY Q1A.10 Q7: verify the ``Translation`` re-export path
    from ``scieasy.qa.schemas.frontmatter`` used by ADR-044 §5.1."""
    from scieasy.qa.schemas.frontmatter import Translation

    fm = _valid_workflow_fm(
        translations=[
            Translation(
                locale="zh-CN",
                path="docs/zh-CN/contributing/workflows/ship-a-feature.md",
            )
        ]
    )
    assert len(fm.translations) == 1
    assert fm.translations[0].locale == "zh-CN"
