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


def _field(report: Any, key: str) -> Any:
    return _as_dict(report).get(key)


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _validate(fixture: str, profile_name: str = "development") -> Any:
    validate_package, profile = _validation_api()
    return validate_package(FIXTURES / fixture, profile=_profile(profile, profile_name))


def _finding_contract_ids(report: Any) -> set[str]:
    return {str(item.get("contract_id")) for item in _items(report, "findings") if item.get("contract_id")}


def _finding_symbols(report: Any) -> set[str]:
    symbols: set[str] = set()
    for item in _items(report, "findings"):
        for key in ("symbol", "source_symbol"):
            value = item.get(key)
            if value:
                symbols.add(str(value))
    return symbols


def _status_is_passing(status: Any) -> bool:
    return _text(status) in {"pass", "passed", "ok", "pass_with_warnings"}


def _status_is_failing(status: Any) -> bool:
    return _text(status) in {"fail", "failed", "error"}


@pytest.mark.parametrize("profile_name", ["development", "production"])
def test_valid_fixture_package_passes_without_blocking_findings(profile_name: str) -> None:
    report = _validate("valid_package", profile_name)

    assert _status_is_passing(_field(report, "status"))
    assert _text(_field(report, "registration_decision")) in {"accept", "register", "allow", "none"}
    assert not _items(report, "findings")
    dry_run = _field(report, "dry_run_registries")
    assert dry_run


@pytest.mark.parametrize(
    ("fixture", "expected_contract_id", "expected_symbol"),
    [
        ("invalid_block_package", "PV-04-001", "NotABlock"),
        ("invalid_type_meta_package", "PV-03-002", "InvalidMetaType"),
        ("invalid_previewer_manifest_package", "PV-09-003", "pv.invalid.remote.manifest"),
        ("invalid_io_capability_package", "PV-06-001", "InvalidCapabilityLoader"),
        ("conflicting_capability_id_package", "PV-06-002", "pv-conflicting-capability-id-package.duplicate.load"),
        ("unknown_cross_surface_target_package", "PV-13-004", "MissingFixtureType"),
    ],
)
@pytest.mark.parametrize("profile_name", ["development", "production"])
def test_invalid_fixture_packages_report_expected_contracts(
    fixture: str,
    expected_contract_id: str,
    expected_symbol: str,
    profile_name: str,
) -> None:
    report = _validate(fixture, profile_name)

    assert _status_is_failing(_field(report, "status"))
    assert expected_contract_id in _finding_contract_ids(report)
    assert expected_symbol in _finding_symbols(report)
    if profile_name == "production":
        assert _text(_field(report, "registration_decision")) == "reject"


def test_block_type_only_package_marks_previewer_contracts_not_applicable() -> None:
    report = _validate("block_type_only_package", "development")
    previewer_results = [
        item for item in _items(report, "contract_results") if str(item.get("contract_id", "")).startswith("PV-09-")
    ]

    assert previewer_results
    assert {str(item.get("result")) for item in previewer_results} == {"not_applicable"}


def test_no_entry_point_package_reports_surface_contracts_not_applicable() -> None:
    report = _validate("no_entry_point_package", "development")
    extension_results = [
        item
        for item in _items(report, "contract_results")
        if str(item.get("contract_id", "")).startswith(("PV-02-", "PV-03-", "PV-04-", "PV-09-"))
    ]

    assert _text(_field(report, "registration_decision")) in {"accept", "register", "allow", "none"}
    assert extension_results
    assert {str(item.get("result")) for item in extension_results} == {"not_applicable"}
