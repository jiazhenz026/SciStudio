"""ADR-049 validation engine."""

from __future__ import annotations

import contextlib
import importlib
import inspect
import os
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from scistudio.packages.validation.contracts import PackageContract, contract_applies, load_contract_tables
from scistudio.packages.validation.inventory import CandidateEntryPoint, build_inventory, candidate_import_context
from scistudio.packages.validation.models import (
    ContractResult,
    ContractResultState,
    DryRunRegistrySet,
    FindingSeverity,
    PackageValidationFinding,
    PackageValidationProfile,
    PackageValidationReport,
)


# fmt: off
def validate_package(path_or_distribution: str | Path, profile: PackageValidationProfile | str = PackageValidationProfile.DEVELOPMENT) -> PackageValidationReport:
    try:
        report, _dry_run = _validate_package_with_dry_run(path_or_distribution, profile=profile)
        return report
    except Exception as exc:
        return _failure_report(path_or_distribution, _normalize_profile(profile), exc)
# fmt: on


def validate_installed_package(
    distribution: str,
    profile: PackageValidationProfile | str = PackageValidationProfile.PRODUCTION,
) -> PackageValidationReport:
    validation_profile = _normalize_profile(profile)
    if (
        validation_profile is PackageValidationProfile.PRODUCTION
        and os.environ.get("SCISTUDIO_PACKAGE_VALIDATOR_SUBPROCESS") != "1"
    ):
        registration = importlib.import_module("scistudio.packages.validation.registration")
        return cast(PackageValidationReport, registration.validate_for_registration(distribution).report)
    return validate_package(distribution, profile=validation_profile)


def _validate_package_with_dry_run(
    path_or_distribution: str | Path,
    profile: PackageValidationProfile | str = PackageValidationProfile.DEVELOPMENT,
) -> tuple[PackageValidationReport, DryRunBuilder]:
    """Validate a package and retain the dry-run registry set for registration."""

    validation_profile = _normalize_profile(profile)
    candidate = build_inventory(path_or_distribution)
    contracts = load_contract_tables()
    findings: list[PackageValidationFinding] = []
    dry_run = DryRunBuilder()
    executed_contracts: set[str] = {"PV-01-001", "PV-01-002"}
    if candidate.candidate.source_kind == "unsupported-archive":
        findings.append(
            _finding(
                "PV-01-001",
                "blocker",
                "distribution_metadata",
                candidate.candidate.value,
                "Archive input type is not supported by the package validator.",
                "Provide a source tree, wheel, source distribution, or installed distribution name.",
            )
        )

    with candidate_import_context(candidate):
        for entry_point in candidate.entry_points:
            _validate_entry_point(entry_point, candidate.inventory, dry_run, findings, executed_contracts)
        _validate_cross_surface(candidate.inventory, dry_run, findings, executed_contracts)

    findings = _apply_profile_behaviors(findings, contracts, validation_profile)
    contract_results = _contract_results(
        contracts,
        candidate.inventory.surfaces,
        findings,
        validation_profile,
        executed_contracts,
    )
    report = PackageValidationReport(
        package=candidate.inventory.package,
        profile=validation_profile,
        inventory=candidate.inventory,
        contract_results=contract_results,
        findings=findings,
        dry_run_registries=dry_run.summary(),
    )
    return report, dry_run


class DryRunBuilder:
    """In-process dry-run registries that never mutate live application registries."""

    def __init__(self) -> None:
        from scistudio.blocks.registry import BlockRegistry
        from scistudio.core.types.registry import TypeRegistry
        from scistudio.previewers.registry import PreviewerRegistry

        self.block_registry = BlockRegistry()
        self.type_registry = TypeRegistry()
        self.type_registry.scan_builtins()
        self.previewer_registry = PreviewerRegistry()
        self.runners: dict[str, Any] = {}
        self.api_payloads = 0
        self.candidate_block_names: set[str] = set()
        self.candidate_type_names: set[str] = set()
        self.candidate_previewer_ids: set[str] = set()
        self.candidate_runner_names: set[str] = set()

    def summary(self) -> DryRunRegistrySet:
        return DryRunRegistrySet(
            blocks=len(self.candidate_block_names),
            types=len(self.candidate_type_names),
            previewers=len(self.candidate_previewer_ids),
            format_capabilities=len(self.candidate_format_capability_ids()),
            runners=len(self.candidate_runner_names),
            api_payloads=self.api_payloads,
        )

    def add_block_spec(self, spec: Any) -> None:
        self.block_registry._register_spec(spec)
        self.candidate_block_names.add(spec.name)

    def add_type_class(self, cls: type) -> None:
        self.type_registry.register_class(cls)
        self.candidate_type_names.add(cls.__name__)

    def add_previewer_spec(self, spec: Any) -> bool:
        registered = self.previewer_registry.register(spec)
        if registered:
            self.candidate_previewer_ids.add(spec.previewer_id)
        return registered

    def add_runner(self, name: str, runner: Any) -> None:
        self.runners[name] = runner
        self.candidate_runner_names.add(name)

    def candidate_block_specs(self) -> list[Any]:
        specs = self.block_registry.all_specs()
        return [specs[name] for name in self.candidate_block_names if name in specs]

    def candidate_type_specs(self) -> dict[str, Any]:
        specs = self.type_registry.all_types()
        return {name: specs[name] for name in self.candidate_type_names if name in specs}

    def candidate_previewer_specs(self) -> list[Any]:
        return [
            spec for spec in self.previewer_registry.all_specs() if spec.previewer_id in self.candidate_previewer_ids
        ]

    def candidate_format_capability_ids(self) -> set[str]:
        return {
            capability.id
            for spec in self.candidate_block_specs()
            for capability in getattr(spec, "format_capabilities", ())
        }


def _validate_entry_point(
    entry_point: CandidateEntryPoint,
    inventory: Any,
    dry_run: DryRunBuilder,
    findings: list[PackageValidationFinding],
    executed_contracts: set[str],
) -> None:
    executed_contracts.update({"PV-02-001", "PV-02-002"})
    validator = _ENTRY_POINT_VALIDATORS.get(entry_point.group)
    if validator is None:
        findings.append(_unknown_entry_point_group_finding(entry_point))
        return
    loaded = _load_entry_point(entry_point, findings)
    if loaded is not None:
        validator(entry_point, loaded, inventory, dry_run, findings, executed_contracts)


def _unknown_entry_point_group_finding(entry_point: CandidateEntryPoint) -> PackageValidationFinding:
    return _finding(
        "PV-02-002",
        "error",
        "entry_points",
        f"{entry_point.group}:{entry_point.name}",
        f"Unknown SciStudio entry-point group {entry_point.group!r}.",
        "Use one of scistudio.blocks, scistudio.types, scistudio.previewers, or scistudio.runners.",
    )


def _load_entry_point(
    entry_point: CandidateEntryPoint,
    findings: list[PackageValidationFinding],
) -> Any | None:
    try:
        return entry_point.load()
    except Exception as exc:
        findings.append(
            _finding(
                "PV-02-002",
                "blocker",
                "entry_points",
                entry_point.value,
                f"Entry point {entry_point.group}:{entry_point.name} failed to import: {exc}",
                "Ensure the module path and attribute exist and import without required missing dependencies.",
            )
        )
        return None


def _validate_blocks_entry_point(
    entry_point: CandidateEntryPoint,
    loaded: Any,
    inventory: Any,
    dry_run: DryRunBuilder,
    findings: list[PackageValidationFinding],
    executed_contracts: set[str],
) -> None:
    from scistudio.blocks.app.app_block import AppBlock
    from scistudio.blocks.base.block import Block
    from scistudio.blocks.base.package_info import PackageInfo
    from scistudio.blocks.code.code_block import CodeBlock
    from scistudio.blocks.io.io_block import IOBlock

    executed_contracts.add("PV-02-003")

    try:
        result = loaded if isinstance(loaded, type) and issubclass(loaded, Block) else loaded()
    except Exception as exc:
        findings.append(
            _finding(
                "PV-02-003",
                "error",
                "blocks",
                entry_point.value,
                f"Block entry-point callable raised: {exc}",
                "Make the scistudio.blocks entry point return a Block class list or (PackageInfo, list[type[Block]]).",
            )
        )
        return

    package_info: PackageInfo | None = None
    block_classes: list[Any] = []
    if isinstance(result, tuple) and len(result) == 2:
        first, second = result
        if isinstance(first, PackageInfo) and isinstance(second, list):
            package_info = first
            block_classes = list(second)
        else:
            findings.append(
                _finding(
                    "PV-02-003",
                    "error",
                    "blocks",
                    entry_point.value,
                    "Block entry point returned an unsupported tuple shape.",
                    "Return (PackageInfo, list[type[Block]]) or list[type[Block]].",
                )
            )
            return
    elif isinstance(result, list):
        block_classes = list(result)
    elif isinstance(result, type):
        block_classes = [result]
    else:
        findings.append(
            _finding(
                "PV-02-003",
                "error",
                "blocks",
                entry_point.value,
                f"Block entry point returned {type(result).__name__}, not a supported payload.",
                "Return a Block class, list[type[Block]], or (PackageInfo, list[type[Block]]).",
            )
        )
        return

    if package_info is not None:
        _validate_package_info(package_info, inventory, findings)

    package_name = package_info.name if package_info is not None else inventory.package.name
    for cls in block_classes:
        if not isinstance(cls, type) or not issubclass(cls, Block):
            findings.append(
                _finding(
                    "PV-04-001",
                    "error",
                    "blocks",
                    getattr(cls, "__name__", repr(cls)),
                    "Block payload item is not a Block subclass.",
                    "Return only concrete subclasses of scistudio.blocks.base.block.Block.",
                )
            )
            continue
        inventory.block_symbols.append(cls.__name__)
        inventory.surfaces.update({"blocks", "block_config", "block_ports"})
        executed_contracts.update({"PV-04-001", "PV-05-001", "PV-05-002"})
        if issubclass(cls, IOBlock):
            inventory.surfaces.update({"io_blocks", "format_capabilities"})
            executed_contracts.update({"PV-06-001", "PV-06-002", "PV-06-003", "PV-06-004"})
        if issubclass(cls, AppBlock):
            inventory.surfaces.add("app_blocks")
            executed_contracts.update({"PV-08-001", "PV-08-002", "PV-08-003"})
        if issubclass(cls, CodeBlock):
            inventory.surfaces.add("code_blocks")
            executed_contracts.update({"PV-08-001", "PV-08-002", "PV-08-003"})
        if inspect.isabstract(cls):
            continue
        try:
            spec = _block_spec_for_class(cls, package_name, inventory.package.version)
            dry_run.add_block_spec(spec)
            inventory.format_capability_ids.extend(capability.id for capability in spec.format_capabilities)
        except Exception as exc:
            contract_id = "PV-06-002" if "Duplicate capability id" in str(exc) else "PV-06-001"
            if "capability" not in str(exc).lower():
                contract_id = "PV-04-001"
            symbol = _capability_symbol(cls, exc) or cls.__name__
            findings.append(
                _finding(
                    contract_id,
                    "error",
                    "format_capabilities" if contract_id.startswith("PV-06") else "blocks",
                    symbol,
                    f"Block dry-run registration failed: {exc}",
                    "Fix the block class, ports, config, or IO format capability declarations.",
                )
            )


def _validate_package_info(package_info: Any, inventory: Any, findings: list[PackageValidationFinding]) -> None:
    if not _package_info_is_instance(package_info, findings):
        return
    inventory.surfaces.add("package_info")
    inventory.package_info = _package_info_payload(package_info)
    findings.extend(_package_info_field_findings(package_info))
    findings.extend(_package_info_identity_findings(package_info, inventory))


def _package_info_is_instance(package_info: Any, findings: list[PackageValidationFinding]) -> bool:
    from scistudio.blocks.base.package_info import PackageInfo

    if isinstance(package_info, PackageInfo):
        return True
    findings.append(_package_info_type_finding(package_info))
    return False


def _package_info_type_finding(package_info: Any) -> PackageValidationFinding:
    return _finding(
        "PV-01-001",
        "error",
        "package_info",
        type(package_info).__name__,
        "Package metadata is not a PackageInfo instance.",
        "Return scistudio.blocks.base.package_info.PackageInfo from get_block_package().",
    )


def _package_info_payload(package_info: Any) -> dict[str, Any]:
    return {
        "name": package_info.name,
        "description": package_info.description,
        "author": package_info.author,
        "version": package_info.version,
    }


def _blank_package_info_fields(package_info: Any) -> list[str]:
    return [
        field_name
        for field_name in ("name", "version")
        if not isinstance(getattr(package_info, field_name), str) or not getattr(package_info, field_name).strip()
    ]


def _non_string_package_info_fields(package_info: Any) -> list[str]:
    return [
        field_name for field_name in ("description", "author") if not isinstance(getattr(package_info, field_name), str)
    ]


def _package_info_field_findings(package_info: Any) -> list[PackageValidationFinding]:
    return [
        _finding(
            "PV-01-002",
            "error",
            "package_info",
            field_name,
            f"PackageInfo.{field_name} must be a non-empty string.",
            "Populate PackageInfo with stable non-empty name and version fields.",
        )
        for field_name in _blank_package_info_fields(package_info)
    ] + [
        _finding(
            "PV-01-002",
            "error",
            "package_info",
            field_name,
            f"PackageInfo.{field_name} must be a string.",
            "Populate PackageInfo description and author with strings, or leave them as empty strings.",
        )
        for field_name in _non_string_package_info_fields(package_info)
    ]


def _package_info_identity_findings(package_info: Any, inventory: Any) -> list[PackageValidationFinding]:
    if not isinstance(package_info.name, str) or not package_info.name.strip():
        return []
    if package_info.name == inventory.package.name:
        return []
    return [
        _finding(
            "PV-01-002",
            "warning",
            "package_info",
            package_info.name,
            f"PackageInfo.name {package_info.name!r} differs from distribution name {inventory.package.name!r}.",
            "Keep PackageInfo.name aligned with the package distribution name where possible.",
        )
    ]


def _validate_types_entry_point(
    entry_point: CandidateEntryPoint,
    loaded: Any,
    inventory: Any,
    dry_run: DryRunBuilder,
    findings: list[PackageValidationFinding],
    executed_contracts: set[str],
) -> None:
    from scistudio.core.types.base import DataObject

    executed_contracts.update({"PV-03-001", "PV-03-002", "PV-03-003"})

    try:
        result = loaded()
    except Exception as exc:
        findings.append(
            _finding(
                "PV-03-001",
                "error",
                "types",
                entry_point.value,
                f"Type entry-point callable raised: {exc}",
                "Make the scistudio.types callable return a list of DataObject subclasses.",
            )
        )
        return
    if not isinstance(result, (list, tuple)):
        findings.append(
            _finding(
                "PV-03-001",
                "error",
                "types",
                entry_point.value,
                f"Type entry point returned {type(result).__name__}, not list/tuple.",
                "Return list[type[DataObject]] from scistudio.types entry points.",
            )
        )
        return
    for cls in result:
        symbol = getattr(cls, "__name__", repr(cls))
        if not isinstance(cls, type) or not issubclass(cls, DataObject):
            findings.append(
                _finding(
                    "PV-03-001",
                    "error",
                    "types",
                    symbol,
                    "Type payload item is not a DataObject subclass.",
                    "Return only subclasses of scistudio.core.types.base.DataObject.",
                )
            )
            continue
        inventory.type_symbols.append(cls.__name__)
        try:
            dry_run.add_type_class(cls)
        except Exception as exc:
            findings.append(
                _finding(
                    "PV-03-002",
                    "error",
                    "types",
                    cls.__name__,
                    f"Type dry-run registration failed: {exc}",
                    "Fix the DataObject Meta model so it is a Pydantic model without PrivateAttr and JSON round-trips.",
                )
            )


def _validate_previewers_entry_point(
    entry_point: CandidateEntryPoint,
    loaded: Any,
    inventory: Any,
    dry_run: DryRunBuilder,
    findings: list[PackageValidationFinding],
    executed_contracts: set[str],
) -> None:
    from scistudio.previewers.assets import validate_manifest
    from scistudio.previewers.models import PreviewerSpec

    executed_contracts.update({"PV-09-001", "PV-09-002", "PV-09-004", "PV-09-005"})

    try:
        result = loaded()
    except Exception as exc:
        findings.append(
            _finding(
                "PV-09-001",
                "error",
                "previewers",
                entry_point.value,
                f"Previewer entry-point callable raised: {exc}",
                "Make the scistudio.previewers callable return list[PreviewerSpec].",
            )
        )
        return
    if not isinstance(result, (list, tuple)):
        findings.append(
            _finding(
                "PV-09-001",
                "error",
                "previewers",
                entry_point.value,
                f"Previewer entry point returned {type(result).__name__}, not list/tuple.",
                "Return list[PreviewerSpec] from scistudio.previewers entry points.",
            )
        )
        return
    for spec in result:
        if not isinstance(spec, PreviewerSpec):
            findings.append(
                _finding(
                    "PV-09-002",
                    "error",
                    "previewers",
                    type(spec).__name__,
                    "Previewer payload item is not a PreviewerSpec.",
                    "Return only scistudio.previewers.models.PreviewerSpec objects.",
                )
            )
            continue
        inventory.previewer_ids.append(spec.previewer_id)
        inventory.surfaces.add("previewers")
        if spec.backend_provider is not None:
            inventory.surfaces.add("preview_provider")
            executed_contracts.update({"PV-10-001", "PV-10-002", "PV-10-003", "PV-09-006"})
        if spec.frontend_manifest is not None:
            inventory.surfaces.update({"preview_frontend_manifest", "security_isolation"})
            executed_contracts.update({"PV-09-003", "PV-12-001", "PV-12-002", "PV-12-004"})
        manifest_result = validate_manifest(spec.frontend_manifest)
        if spec.frontend_manifest is not None and not manifest_result.valid:
            findings.append(
                _finding(
                    "PV-09-003",
                    "error",
                    "preview_frontend_manifest",
                    spec.previewer_id,
                    "; ".join(manifest_result.diagnostics),
                    "Use same-origin backend-relative module/css URLs and a valid manifest descriptor.",
                )
            )
        if not dry_run.add_previewer_spec(spec):
            findings.append(
                _finding(
                    "PV-09-004",
                    "error",
                    "previewers",
                    spec.previewer_id,
                    "Duplicate previewer_id detected in dry-run registry.",
                    "Use a unique package-qualified previewer_id.",
                )
            )


# fmt: off
def _validate_runner_entry_point(
    entry_point: CandidateEntryPoint,
    loaded: Any,
    inventory: Any,
    dry_run: DryRunBuilder,
    findings: list[PackageValidationFinding],
    executed_contracts: set[str],
) -> None:
    executed_contracts.add("PV-99-001")
    if not isinstance(loaded, type):
        findings.append(_runner_class_finding(entry_point))
        return
    inventory.runner_symbols.append(loaded.__name__)
    dry_run.add_runner(entry_point.name, loaded)
# fmt: on


def _runner_class_finding(entry_point: CandidateEntryPoint) -> PackageValidationFinding:
    return _finding(
        "PV-99-001",
        "error",
        "runners",
        entry_point.value,
        "Runner entry point did not resolve to a class.",
        "Point scistudio.runners entry points at importable runner classes.",
    )


_ENTRY_POINT_VALIDATORS = {
    "scistudio.blocks": _validate_blocks_entry_point,
    "scistudio.types": _validate_types_entry_point,
    "scistudio.previewers": _validate_previewers_entry_point,
    "scistudio.runners": _validate_runner_entry_point,
}


def _validate_cross_surface(
    inventory: Any,
    dry_run: DryRunBuilder,
    findings: list[PackageValidationFinding],
    executed_contracts: set[str],
) -> None:
    if inventory.surfaces & {"blocks", "types", "previewers", "format_capabilities", "runners"}:
        inventory.surfaces.update({"cross_surface_registry_consistency", "registry_derived_api_serialization"})
        executed_contracts.update({"PV-13-001", "PV-13-002", "PV-13-003", "PV-13-004", "PV-99-004"})
    known_types = set(dry_run.type_registry.all_types())
    for block_spec in dry_run.candidate_block_specs():
        for port in [*getattr(block_spec, "input_ports", ()), *getattr(block_spec, "output_ports", ())]:
            for accepted_type in getattr(port, "accepted_types", ()):
                if not _accepted_type_is_known(accepted_type, inventory, known_types):
                    findings.append(
                        _finding(
                            "PV-13-003",
                            "error",
                            "cross_surface_registry_consistency",
                            getattr(accepted_type, "__name__", repr(accepted_type)),
                            f"Block {block_spec.name!r} port {getattr(port, 'name', '<unknown>')!r} references an unregistered type.",
                            "Declare referenced DataObject types through scistudio.types or use a registered core type.",
                        )
                    )
    for spec in dry_run.previewer_registry.all_specs():
        if spec.target_type and spec.target_type not in known_types:
            findings.append(
                _finding(
                    "PV-13-004",
                    "error",
                    "cross_surface_registry_consistency",
                    spec.target_type,
                    f"Previewer {spec.previewer_id!r} targets unknown type {spec.target_type!r}.",
                    "Declare the target DataObject type through scistudio.types or target a registered core/base type.",
                )
            )
    _validate_registry_api_serialization(dry_run, findings)


def _accepted_type_is_known(accepted_type: Any, inventory: Any, known_types: set[str]) -> bool:
    name = getattr(accepted_type, "__name__", "")
    if name in known_types:
        return True

    if _is_core_transport_type(accepted_type):
        return True

    if not _is_data_object_subclass(accepted_type):
        return False

    type_path = _module_file_for_type(accepted_type)
    candidate_root = getattr(inventory, "root_path", None)
    if type_path is None or candidate_root is None:
        return False
    return not _path_is_relative_to(type_path, candidate_root)


def _is_core_transport_type(value: Any) -> bool:
    return (
        isinstance(value, type)
        and value.__module__.startswith("scistudio.core.types.")
        and value.__name__ == "Collection"
    )


def _is_data_object_subclass(value: Any) -> bool:
    from scistudio.core.types.base import DataObject

    return isinstance(value, type) and issubclass(value, DataObject)


def _module_file_for_type(value: type) -> Path | None:
    module = inspect.getmodule(value)
    module_file = getattr(module, "__file__", None)
    if module_file is None:
        return None
    return Path(module_file).resolve()


def _path_is_relative_to(path: Path, root: Path) -> bool:
    with contextlib.suppress(ValueError):
        path.relative_to(root.resolve())
        return True
    return False


def _validate_registry_api_serialization(
    dry_run: DryRunBuilder,
    findings: list[PackageValidationFinding],
) -> None:
    try:
        for block_spec in dry_run.candidate_block_specs():
            {
                "name": block_spec.name,
                "type_name": block_spec.type_name,
                "package_name": block_spec.package_name,
                "inputs": [getattr(port, "name", "") for port in block_spec.input_ports],
                "outputs": [getattr(port, "name", "") for port in block_spec.output_ports],
                "format_capabilities": [capability.id for capability in block_spec.format_capabilities],
            }
        for previewer_spec in dry_run.candidate_previewer_specs():
            previewer_spec.to_dict()
        dry_run.api_payloads = len(dry_run.candidate_block_names) + len(dry_run.candidate_previewer_ids)
    except Exception as exc:
        findings.append(
            _finding(
                "PV-99-004",
                "error",
                "registry_derived_api_serialization",
                None,
                f"Dry-run registry rows could not be serialized for API/palette payloads: {exc}",
                "Keep registry descriptors JSON-safe and free of unserializable runtime objects in API payload fields.",
            )
        )


def _contract_results(
    contracts: Any,
    surfaces: set[str],
    findings: list[PackageValidationFinding],
    profile: PackageValidationProfile,
    executed_contracts: set[str],
) -> list[ContractResult]:
    findings_by_contract = {finding.contract_id: finding for finding in findings}
    results: list[ContractResult] = []
    for contract in contracts:
        applies = contract_applies(contract, surfaces)
        if not applies:
            result = ContractResultState.NOT_APPLICABLE
        elif contract.contract_id in findings_by_contract:
            result = _finding_result_state(findings_by_contract[contract.contract_id])
        elif contract.validator_profile.get(profile.value) == "skip" or contract.contract_id not in executed_contracts:
            result = ContractResultState.SKIPPED
        else:
            result = ContractResultState.PASS
        finding = findings_by_contract.get(contract.contract_id)
        results.append(
            ContractResult(
                contract_id=contract.contract_id,
                result=result,
                surface=contract.primary_surface,
                symbol=finding.symbol if finding else None,
                severity=finding.severity if finding else contract.severity,
                evidence=(
                    "validator_not_executed_for_candidate_trigger"
                    if applies and contract.contract_id not in executed_contracts and finding is None
                    else None
                ),
            )
        )
    return results


def _finding_result_state(finding: PackageValidationFinding) -> ContractResultState:
    severity = str(finding.severity)
    if severity in {FindingSeverity.WARNING.value, FindingSeverity.INFO.value}:
        return ContractResultState.WARNING
    return ContractResultState.FAIL


def _apply_profile_behaviors(
    findings: list[PackageValidationFinding],
    contracts: list[PackageContract],
    profile: PackageValidationProfile,
) -> list[PackageValidationFinding]:
    contracts_by_id = {contract.contract_id: contract for contract in contracts}
    normalized: list[PackageValidationFinding] = []
    for finding in findings:
        contract = contracts_by_id.get(finding.contract_id)
        behavior = contract.validator_profile.get(profile.value) if contract is not None else None
        severity = _severity_for_profile_behavior(behavior, str(finding.severity))
        normalized.append(replace(finding, severity=severity, profile_behavior=behavior))
    return normalized


def _severity_for_profile_behavior(behavior: str | None, fallback: str) -> FindingSeverity:
    fallback_severity = FindingSeverity(fallback)
    if behavior is None:
        return fallback_severity
    profile_severity = {
        "block": FindingSeverity.BLOCKER,
        "error": FindingSeverity.ERROR,
        "warning": FindingSeverity.WARNING,
        "info": FindingSeverity.INFO,
    }.get(behavior)
    if profile_severity is None:
        return fallback_severity
    order = {
        FindingSeverity.INFO: 0,
        FindingSeverity.WARNING: 1,
        FindingSeverity.ERROR: 2,
        FindingSeverity.BLOCKER: 3,
    }
    return profile_severity if order[profile_severity] > order[fallback_severity] else fallback_severity


def _block_spec_for_class(cls: type, package_name: str, package_version: str) -> Any:
    import scistudio.blocks.registry._spec as spec_module
    from scistudio.blocks.registry import BlockRegistrationError

    try:
        spec = spec_module._spec_from_class(cls, source="package_validator")
    except BlockRegistrationError as exc:
        if "cannot resolve distribution version" not in str(exc):
            raise
        original_resolver = spec_module._resolve_distribution_version

        def resolve_candidate_package_version(cls: type) -> str:
            return package_version

        spec_module._resolve_distribution_version = resolve_candidate_package_version
        try:
            spec = spec_module._spec_from_class(cls, source="package_validator")
        finally:
            spec_module._resolve_distribution_version = original_resolver
    spec.package_name = package_name
    return spec


def _capability_symbol(cls: type, exc: Exception) -> str | None:
    text = str(exc)
    for quoted in ("'", '"'):
        parts = text.split(quoted)
        if len(parts) >= 3 and "." in parts[1]:
            return parts[1]
    capabilities = getattr(cls, "format_capabilities", ())
    counts: Counter[str] = Counter(
        capability.id for capability in capabilities if hasattr(capability, "id") and isinstance(capability.id, str)
    )
    for capability_id, count in counts.items():
        if count > 1:
            return capability_id
    return None


def _normalize_profile(profile: PackageValidationProfile | str) -> PackageValidationProfile:
    if isinstance(profile, PackageValidationProfile):
        return profile
    return PackageValidationProfile(str(profile).lower())


def _finding(
    contract_id: str,
    severity: str,
    surface: str,
    symbol: str | None,
    message: str,
    repair_hint: str,
) -> PackageValidationFinding:
    return PackageValidationFinding(
        contract_id=contract_id,
        severity=FindingSeverity(severity),
        surface=surface,
        symbol=symbol,
        message=message,
        repair_hint=repair_hint,
    )


def _failure_report(
    path_or_distribution: str | Path,
    profile: PackageValidationProfile,
    exc: Exception,
) -> PackageValidationReport:
    from scistudio.packages.validation.models import PackageIdentity, PackageInventory

    value = str(path_or_distribution)
    package = PackageIdentity(name=Path(value).name or value, version="unknown", source=value)
    inventory = PackageInventory(package=package, surfaces={"distribution_metadata"})
    return PackageValidationReport(
        package=package,
        profile=profile,
        inventory=inventory,
        findings=[
            PackageValidationFinding(
                contract_id="PV-01-001",
                severity=FindingSeverity.BLOCKER,
                surface="distribution_metadata",
                symbol=value,
                message=f"Package inventory could not be built: {exc}",
                repair_hint="Provide valid package metadata and importable SciStudio entry-point declarations.",
                profile_behavior="block" if profile is PackageValidationProfile.PRODUCTION else "error",
            )
        ],
    )
