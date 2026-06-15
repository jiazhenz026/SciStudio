from __future__ import annotations

import importlib
import zipfile
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


def test_unknown_scistudio_entry_point_group_is_a_structured_failure(tmp_path: Path) -> None:
    package_root = tmp_path / "unknown_group"
    package_dir = package_root / "src" / "pv_unknown_group"
    package_dir.mkdir(parents=True)
    package_dir.joinpath("__init__.py").write_text("def get_bad():\n    return []\n", encoding="utf-8")
    package_root.joinpath("pyproject.toml").write_text(
        """[project]
name = "pv-unknown-group"
version = "0.1.0"

[project.entry-points."scistudio.unknown"]
bad = "pv_unknown_group:get_bad"

[tool.setuptools.packages.find]
where = ["src"]
""",
        encoding="utf-8",
    )

    report = _validation_api()[0](package_root)

    assert _status_is_failing(_field(report, "status"))
    assert "PV-02-002" in _finding_contract_ids(report)


def test_declared_dependency_port_types_do_not_need_candidate_registration(tmp_path: Path) -> None:
    packages_root = tmp_path / "packages"
    dependency_root = packages_root / "pv-dependency"
    dependency_package_dir = dependency_root / "src" / "pv_dependency"
    dependency_package_dir.mkdir(parents=True)
    dependency_package_dir.joinpath("__init__.py").write_text(
        """
from scistudio.core.types.base import DataObject


class DependencySample(DataObject):
    pass


def get_types():
    return [DependencySample]
""",
        encoding="utf-8",
    )
    dependency_root.joinpath("pyproject.toml").write_text(
        """[project]
name = "pv-dependency"
version = "0.1.0"

[project.entry-points."scistudio.types"]
types = "pv_dependency:get_types"

[tool.setuptools.packages.find]
where = ["src"]
""",
        encoding="utf-8",
    )

    candidate_root = packages_root / "pv-candidate"
    candidate_package_dir = candidate_root / "src" / "pv_candidate"
    candidate_package_dir.mkdir(parents=True)
    candidate_package_dir.joinpath("__init__.py").write_text(
        """
from typing import ClassVar

from pv_dependency import DependencySample
from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.core.types.collection import Collection


class DependencyBlock(Block):
    name: ClassVar[str] = "Dependency Block"
    type_name: ClassVar[str] = "pv.dependency"
    input_ports: ClassVar[list[InputPort]] = [InputPort(name="sample", accepted_types=[DependencySample])]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="sample", accepted_types=[DependencySample])]

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        return {"sample": inputs["sample"]}


def get_blocks():
    return [DependencyBlock]
""",
        encoding="utf-8",
    )
    candidate_root.joinpath("pyproject.toml").write_text(
        """[project]
name = "pv-candidate"
version = "0.1.0"
dependencies = ["pv-dependency>=0.1.0"]

[project.entry-points."scistudio.blocks"]
blocks = "pv_candidate:get_blocks"

[tool.setuptools.packages.find]
where = ["src"]
""",
        encoding="utf-8",
    )

    report = _validation_api()[0](candidate_root, profile="production")

    assert _status_is_passing(_field(report, "status"))
    assert "PV-13-003" not in _finding_contract_ids(report)


def test_candidate_local_port_types_must_be_registered(tmp_path: Path) -> None:
    package_root = tmp_path / "local_type_not_registered"
    package_dir = package_root / "src" / "pv_local_type_not_registered"
    package_dir.mkdir(parents=True)
    package_dir.joinpath("__init__.py").write_text(
        """
from typing import ClassVar

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


class LocalSample(DataObject):
    pass


class LocalTypeBlock(Block):
    name: ClassVar[str] = "Local Type Block"
    type_name: ClassVar[str] = "pv.local_type"
    input_ports: ClassVar[list[InputPort]] = [InputPort(name="sample", accepted_types=[LocalSample])]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="sample", accepted_types=[LocalSample])]

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        return {"sample": inputs["sample"]}


def get_blocks():
    return [LocalTypeBlock]
""",
        encoding="utf-8",
    )
    package_root.joinpath("pyproject.toml").write_text(
        """[project]
name = "pv-local-type-not-registered"
version = "0.1.0"

[project.entry-points."scistudio.blocks"]
blocks = "pv_local_type_not_registered:get_blocks"

[tool.setuptools.packages.find]
where = ["src"]
""",
        encoding="utf-8",
    )

    report = _validation_api()[0](package_root, profile="production")

    assert _status_is_failing(_field(report, "status"))
    assert "PV-13-003" in _finding_contract_ids(report)
    assert "LocalSample" in _finding_symbols(report)


def test_wheel_entry_points_are_validated_instead_of_treated_as_metadata_only(tmp_path: Path) -> None:
    wheel_path = tmp_path / "pv_bad_wheel-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as wheel:
        wheel.writestr(
            "pv_bad_wheel/__init__.py",
            "def get_blocks():\n    return ['not a block class']\n",
        )
        wheel.writestr("pv_bad_wheel-0.1.0.dist-info/METADATA", "Name: pv-bad-wheel\nVersion: 0.1.0\n")
        wheel.writestr(
            "pv_bad_wheel-0.1.0.dist-info/entry_points.txt",
            "[scistudio.blocks]\nmain = pv_bad_wheel:get_blocks\n",
        )

    report = _validation_api()[0](wheel_path)

    assert _status_is_failing(_field(report, "status"))
    assert "PV-04-001" in _finding_contract_ids(report)


def test_bad_source_metadata_returns_structured_report(tmp_path: Path) -> None:
    package_root = tmp_path / "bad_toml"
    package_root.mkdir()
    package_root.joinpath("pyproject.toml").write_text("[project\n", encoding="utf-8")

    report = _validation_api()[0](package_root)

    assert _status_is_failing(_field(report, "status"))
    assert "PV-01-001" in _finding_contract_ids(report)
