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


def _validate_production(fixture: str) -> dict[str, Any]:
    validate_package, profile = _validation_api()
    return _as_dict(validate_package(FIXTURES / fixture, profile=_profile(profile, "production")))


def _block_registry_snapshot(registry: Any) -> tuple[tuple[str, str | None], ...]:
    specs = getattr(registry, "specs", None)
    values = specs() if callable(specs) else getattr(registry, "_specs", {}).values()
    return tuple(sorted((str(getattr(spec, "type_name", "")), getattr(spec, "package_name", None)) for spec in values))


def _previewer_registry_snapshot(registry: Any) -> tuple[str, ...]:
    specs = getattr(registry, "specs", None)
    values = specs() if callable(specs) else getattr(registry, "_specs", {}).values()
    return tuple(sorted(str(getattr(spec, "previewer_id", "")) for spec in values))


def test_production_validation_rejects_invalid_package_without_live_registry_mutation() -> None:
    _validation_api()
    from scistudio.blocks.registry import BlockRegistry
    from scistudio.packages.validation.registration import validate_for_registration
    from scistudio.previewers.registry import PreviewerRegistry

    block_registry = BlockRegistry()
    previewer_registry = PreviewerRegistry()
    before_blocks = _block_registry_snapshot(block_registry)
    before_previewers = _previewer_registry_snapshot(previewer_registry)

    report = _validate_production("invalid_previewer_manifest_package")
    plan = validate_for_registration(FIXTURES / "invalid_previewer_manifest_package")

    assert report["status"] == "fail"
    assert report["registration_decision"] == "reject"
    assert not plan.accepted
    assert not plan.commit_to(block_registry=block_registry, previewer_registry=previewer_registry)
    assert _block_registry_snapshot(block_registry) == before_blocks
    assert _previewer_registry_snapshot(previewer_registry) == before_previewers


def test_production_validation_valid_package_commits_dry_run_rows_atomically() -> None:
    from scistudio.blocks.registry import BlockRegistry
    from scistudio.core.types.registry import TypeRegistry
    from scistudio.packages.validation.registration import validate_for_registration
    from scistudio.previewers.registry import PreviewerRegistry

    report = _validate_production("valid_package")
    plan = validate_for_registration(FIXTURES / "valid_package")
    block_registry = BlockRegistry()
    type_registry = TypeRegistry()
    previewer_registry = PreviewerRegistry()
    runners: dict[str, Any] = {}

    assert report["registration_decision"] in {"accept", "register", "allow"}
    assert report["dry_run_registries"]["blocks"] >= 1
    assert report["dry_run_registries"]["types"] >= 1
    assert report["dry_run_registries"]["previewers"] >= 1
    assert report["dry_run_registries"]["format_capabilities"] >= 1
    assert plan.accepted
    assert plan.commit_to(
        block_registry=block_registry,
        type_registry=type_registry,
        previewer_registry=previewer_registry,
        runners=runners,
    )
    assert block_registry.get_spec("PV Valid Transform") is not None
    assert block_registry.get_spec("PV Valid Sample Loader") is not None
    assert "ValidSample" in type_registry.all_types()
    assert previewer_registry.get("pv.valid.sample") is not None


def test_production_registration_commit_rolls_back_on_live_registry_failure() -> None:
    from scistudio.blocks.registry import BlockRegistry
    from scistudio.core.types.registry import TypeRegistry
    from scistudio.packages.validation.registration import validate_for_registration
    from scistudio.previewers.registry import PreviewerRegistry

    plan = validate_for_registration(FIXTURES / "valid_package")
    block_registry = BlockRegistry()
    type_registry = TypeRegistry()
    previewer_registry = PreviewerRegistry()
    previewer_registry.register(plan.dry_run.previewer_registry.all_specs()[0])
    before_blocks = _block_registry_snapshot(block_registry)
    before_types = tuple(sorted(type_registry.all_types()))
    before_previewers = _previewer_registry_snapshot(previewer_registry)

    with pytest.raises(ValueError, match="Previewer registry rejected"):
        plan.commit_to(
            block_registry=block_registry,
            type_registry=type_registry,
            previewer_registry=previewer_registry,
        )

    assert _block_registry_snapshot(block_registry) == before_blocks
    assert tuple(sorted(type_registry.all_types())) == before_types
    assert _previewer_registry_snapshot(previewer_registry) == before_previewers
