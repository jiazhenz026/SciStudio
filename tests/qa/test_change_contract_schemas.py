from __future__ import annotations

import pytest
from pydantic import ValidationError

from scistudio.qa.schemas import ChangeContract as ExportedChangeContract
from scistudio.qa.schemas.change_contracts import (
    BaselinePolicyMode,
    ChangeContract,
    ChangeContractBaseline,
    ChangeContractBaselineFinding,
    ChangeContractNotApplicable,
    ChangeContractSurfaces,
    ChangeKind,
    ChangeSurface,
    ChangeSurfaceKind,
    ChangeSurfaceScope,
    ChangeWaiver,
)


def _module_surface(target: str = "scistudio.qa.schemas.change_contracts") -> dict[str, str]:
    return {"kind": "module", "target": target, "scope": "production"}


def _contract_payload() -> dict[str, object]:
    added_surface = _module_surface()
    retained_surface = {
        "kind": "module",
        "target": "scistudio.qa.schemas.legacy_change_contracts",
        "scope": "production",
        "reason": "Compatibility adapter remains during migration.",
        "owner": "@jiazhenz026",
        "issue": "#1618",
    }
    return {
        "id": "adr-042-change-contract-gate",
        "parent": "docs/specs/adr-042-change-contract-gate.md",
        "change_kind": "additive",
        "surfaces": {"added": [added_surface], "retained": [retained_surface]},
        "forbidden_prod_references": [
            {
                "kind": "import",
                "target": "scistudio.qa.schemas.legacy_change_contracts",
                "allowed_scopes": ["test", "docs"],
                "reason": "Legacy import should not be used by production code.",
            }
        ],
        "required_reachability": [
            {
                "surface": added_surface,
                "production_roots": ["src/scistudio/qa/schemas/__init__.py"],
            }
        ],
        "required_canaries": [
            {
                "kind": "public_api",
                "surface": added_surface,
                "test_path": "tests/qa/test_change_contract_schemas.py",
            }
        ],
        "waivers": [
            {
                "rule_id": "change-contract.fixture",
                "owner": "@jiazhenz026",
                "issue": 1618,
                "reason": "Fixture waiver validates schema requirements.",
                "allowed_scopes": ["test"],
            }
        ],
        "baseline_policy": {
            "mode": "no_new_violations",
            "baseline": "docs/audit/baselines/change-contract-baseline.json",
        },
    }


def test_change_contract_schema_accepts_valid_contract() -> None:
    contract = ChangeContract.model_validate(_contract_payload())

    assert contract.change_kind == ChangeKind.ADDITIVE
    assert contract.surfaces.added[0].target == "scistudio.qa.schemas.change_contracts"
    assert contract.surfaces.retained[0].issue == "#1618"
    assert contract.baseline_policy.mode == BaselinePolicyMode.NO_NEW_VIOLATIONS
    assert ExportedChangeContract is ChangeContract


def test_change_contract_schema_rejects_invalid_enum_values() -> None:
    payload = _contract_payload()
    payload["change_kind"] = "rewrite"

    with pytest.raises(ValidationError):
        ChangeContract.model_validate(payload)

    with pytest.raises(ValidationError):
        ChangeSurface.model_validate({"kind": "package", "target": "scistudio.qa.schemas.change_contracts"})


def test_retained_surfaces_require_reason_owner_and_issue() -> None:
    with pytest.raises(ValidationError, match="retained surfaces require reason, owner, and issue"):
        ChangeContractSurfaces(retained=[ChangeSurface(kind=ChangeSurfaceKind.MODULE, target="scistudio.legacy")])


def test_waivers_require_owner_issue_and_reason() -> None:
    with pytest.raises(ValidationError):
        ChangeWaiver.model_validate(
            {"rule_id": "change-contract.fixture", "owner": "@jiazhenz026", "reason": "Missing issue."}
        )

    with pytest.raises(ValidationError):
        ChangeWaiver(rule_id="change-contract.fixture", owner="@jiazhenz026", issue="#1618", reason="short")


def test_structured_not_applicable_declaration_requires_rationale() -> None:
    declaration = ChangeContractNotApplicable(
        rationale="Documentation-only change with no implementation surface.",
        owner="@jiazhenz026",
        issue="#1618",
    )

    assert declaration.kind == "not_applicable"
    assert declaration.issue == "#1618"

    with pytest.raises(ValidationError):
        ChangeContractNotApplicable(rationale="   ")


def test_baseline_schema_requires_stable_unique_finding_ids() -> None:
    finding = ChangeContractBaselineFinding(
        id="change-contract.fixture:legacy",
        rule_id="change-contract.fixture",
        fingerprint="legacy-import",
        reason="Existing fixture debt is intentionally grandfathered.",
    )
    baseline = ChangeContractBaseline(generated_from="abc123", findings=[finding])

    assert baseline.version == "1"
    assert baseline.findings[0].id == "change-contract.fixture:legacy"

    with pytest.raises(ValidationError, match="duplicate baseline finding id"):
        ChangeContractBaseline(generated_from="abc123", findings=[finding, finding])


def test_surface_scope_enum_accepts_specified_values() -> None:
    surface = ChangeSurface(
        kind=ChangeSurfaceKind.FILE,
        target="docs/example.md",
        scope=ChangeSurfaceScope.DOCS,
    )

    assert surface.scope == ChangeSurfaceScope.DOCS
