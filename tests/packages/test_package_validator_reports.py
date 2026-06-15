from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, cast

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "package_validator"


def _validation_api() -> tuple[Any, Any]:
    try:
        module = importlib.import_module("scistudio.packages.validation")
    except ModuleNotFoundError as exc:
        if exc.name in {"scistudio.packages", "scistudio.packages.validation"}:
            pytest.xfail("ADR-049 package validator implementation is not present in this worktree yet.")
        raise
    validate_package = getattr(module, "validate_package", None)
    profile = getattr(module, "PackageValidationProfile", None)
    if validate_package is None or profile is None:
        pytest.xfail("ADR-049 public validation API is not complete yet.")
    return validate_package, profile


def _profile(profile: Any, name: str) -> Any:
    return (
        getattr(profile, name.upper(), None)
        or getattr(profile, name.lower(), None)
        or getattr(profile, name, None)
        or name
    )


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return cast(dict[str, Any], value.model_dump(mode="json"))
    if hasattr(value, "to_dict"):
        return cast(dict[str, Any], value.to_dict())
    if isinstance(value, dict):
        return value
    return dict(value)


def _items(report: Any, key: str) -> list[dict[str, Any]]:
    data = _as_dict(report)
    values = data.get(key, [])
    return [_as_dict(value) for value in values]


def _validate(fixture: str, profile_name: str = "production") -> Any:
    validate_package, profile = _validation_api()
    return validate_package(FIXTURES / fixture, profile=_profile(profile, profile_name))


def test_report_envelope_contains_adr049_required_fields() -> None:
    report = _as_dict(_validate("valid_package", "production"))

    assert report["schema_version"] == "adr049.package_validation_report.v1"
    assert report["package"]["name"] == "pv-valid-package"
    assert report["package"]["version"] == "0.1.0"
    assert str(report["profile"]) == "production"
    assert report["status"] in {"pass", "pass_with_warnings"}
    assert report["registration_decision"] in {"accept", "register", "allow"}
    assert report["inventory"]["entry_points"]
    assert report["inventory"]["surfaces"]
    assert isinstance(report["contract_results"], list)
    assert isinstance(report["findings"], list)
    assert report["dry_run_registries"]["blocks"] >= 1
    assert report["dry_run_registries"]["types"] >= 1
    assert report["dry_run_registries"]["previewers"] >= 1
    assert report["dry_run_registries"]["format_capabilities"] >= 1


def test_failing_report_includes_repairable_finding_shape() -> None:
    report = _validate("invalid_previewer_manifest_package", "production")
    findings = _items(report, "findings")

    assert findings
    for finding in findings:
        assert finding["contract_id"].startswith("PV-")
        assert finding["severity"] in {"blocker", "error", "warning", "info"}
        assert finding["surface"]
        assert finding["message"]
        assert finding["repair_hint"]


def test_contract_results_include_pass_fail_and_not_applicable_classifications() -> None:
    valid = _validate("valid_package", "development")
    no_entry = _validate("no_entry_point_package", "development")
    invalid = _validate("invalid_block_package", "development")

    valid_results = {item["result"] for item in _items(valid, "contract_results")}
    no_entry_results = {item["result"] for item in _items(no_entry, "contract_results")}
    invalid_results = {item["result"] for item in _items(invalid, "contract_results")}

    assert "pass" in valid_results
    assert "not_applicable" in no_entry_results
    assert "fail" in invalid_results


def test_applicable_unexecuted_contract_rows_are_not_reported_as_pass() -> None:
    report = _validate("valid_package", "production")
    results = {
        item["contract_id"]: item
        for item in _items(report, "contract_results")
        if item["contract_id"] in {"PV-10-001", "PV-12-003"}
    }

    assert results
    assert {item["result"] for item in results.values()} == {"skipped"}
    assert {item.get("evidence") for item in results.values()} == {"validator_not_executed_for_candidate_trigger"}
