"""ADR-049 validation engine."""

from __future__ import annotations

import inspect
from collections import Counter
from pathlib import Path
from typing import Any

from scistudio.packages.validation.contracts import contract_applies, load_contract_tables
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


def validate_package(
    path_or_distribution: str | Path,
    profile: PackageValidationProfile | str = PackageValidationProfile.DEVELOPMENT,
) -> PackageValidationReport:
    """Validate a source tree, archive path, or installed distribution."""

    report, _dry_run = _validate_package_with_dry_run(path_or_distribution, profile=profile)
    return report


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

    with candidate_import_context(candidate):
        for entry_point in candidate.entry_points:
            _validate_entry_point(entry_point, candidate.inventory, dry_run, findings)
        _validate_cross_surface(candidate.inventory, dry_run, findings)

    contract_results = _contract_results(contracts, candidate.inventory.surfaces, findings, validation_profile)
    report = PackageValidationReport(
        package=candidate.inventory.package,
        profile=validation_profile,
        inventory=candidate.inventory,
        contract_results=contract_results,
        findings=findings,
        dry_run_registries=dry_run.summary(),
    )
    return report, dry_run


def validate_installed_package(
    distribution: str,
    profile: PackageValidationProfile | str = PackageValidationProfile.PRODUCTION,
) -> PackageValidationReport:
    """Validate an installed distribution before production registration."""

    return validate_package(distribution, profile=profile)


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

    def summary(self) -> DryRunRegistrySet:
        return DryRunRegistrySet(
            blocks=len(self.block_registry.all_specs()),
            types=len(self.type_registry.all_types()),
            previewers=len(self.previewer_registry.all_specs()),
            format_capabilities=len(self.block_registry.list_format_capabilities()),
            runners=len(self.runners),
            api_payloads=self.api_payloads,
        )


def _validate_entry_point(
    entry_point: CandidateEntryPoint,
    inventory: Any,
    dry_run: DryRunBuilder,
    findings: list[PackageValidationFinding],
) -> None:
    try:
        loaded = entry_point.load()
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
        return

    if entry_point.group == "scistudio.blocks":
        _validate_blocks_entry_point(entry_point, loaded, inventory, dry_run, findings)
    elif entry_point.group == "scistudio.types":
        _validate_types_entry_point(entry_point, loaded, inventory, dry_run, findings)
    elif entry_point.group == "scistudio.previewers":
        _validate_previewers_entry_point(entry_point, loaded, inventory, dry_run, findings)
    elif entry_point.group == "scistudio.runners":
        _validate_runner_entry_point(entry_point, loaded, inventory, dry_run, findings)


def _validate_blocks_entry_point(
    entry_point: CandidateEntryPoint,
    loaded: Any,
    inventory: Any,
    dry_run: DryRunBuilder,
    findings: list[PackageValidationFinding],
) -> None:
    from scistudio.blocks.base.block import Block
    from scistudio.blocks.base.package_info import PackageInfo

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
        if inspect.isabstract(cls):
            continue
        try:
            spec = _block_spec_for_class(cls, package_name, inventory.package.version)
            dry_run.block_registry._register_spec(spec)
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
    from scistudio.blocks.base.package_info import PackageInfo

    if not isinstance(package_info, PackageInfo):
        findings.append(
            _finding(
                "PV-01-001",
                "error",
                "package_info",
                type(package_info).__name__,
                "Package metadata is not a PackageInfo instance.",
                "Return scistudio.blocks.base.package_info.PackageInfo from get_block_package().",
            )
        )
        return
    inventory.package_info = {
        "name": package_info.name,
        "description": package_info.description,
        "author": package_info.author,
        "version": package_info.version,
    }
    for field_name in ("name", "version"):
        value = getattr(package_info, field_name)
        if not isinstance(value, str) or not value.strip():
            findings.append(
                _finding(
                    "PV-01-002",
                    "error",
                    "package_info",
                    field_name,
                    f"PackageInfo.{field_name} must be a non-empty string.",
                    "Populate PackageInfo with stable non-empty name and version fields.",
                )
            )


def _validate_types_entry_point(
    entry_point: CandidateEntryPoint,
    loaded: Any,
    inventory: Any,
    dry_run: DryRunBuilder,
    findings: list[PackageValidationFinding],
) -> None:
    from scistudio.core.types.base import DataObject

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
            dry_run.type_registry.register_class(cls)
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
) -> None:
    from scistudio.previewers.assets import validate_manifest
    from scistudio.previewers.models import PreviewerSpec

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
        if not dry_run.previewer_registry.register(spec):
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


def _validate_runner_entry_point(
    entry_point: CandidateEntryPoint,
    loaded: Any,
    inventory: Any,
    dry_run: DryRunBuilder,
    findings: list[PackageValidationFinding],
) -> None:
    if not isinstance(loaded, type):
        findings.append(
            _finding(
                "PV-99-001",
                "error",
                "runners",
                entry_point.value,
                "Runner entry point did not resolve to a class.",
                "Point scistudio.runners entry points at importable runner classes.",
            )
        )
        return
    inventory.runner_symbols.append(loaded.__name__)
    dry_run.runners[entry_point.name] = loaded


def _validate_cross_surface(inventory: Any, dry_run: DryRunBuilder, findings: list[PackageValidationFinding]) -> None:
    known_types = set(dry_run.type_registry.all_types())
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


def _contract_results(
    contracts: Any,
    surfaces: set[str],
    findings: list[PackageValidationFinding],
    profile: PackageValidationProfile,
) -> list[ContractResult]:
    findings_by_contract = {finding.contract_id: finding for finding in findings}
    results: list[ContractResult] = []
    for contract in contracts:
        applies = contract_applies(contract, surfaces)
        if not applies:
            result = ContractResultState.NOT_APPLICABLE
        elif contract.contract_id in findings_by_contract:
            result = ContractResultState.FAIL
        elif contract.validator_profile.get(profile.value) == "skip":
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
            )
        )
    return results


def _block_spec_for_class(cls: type, package_name: str, package_version: str) -> Any:
    from scistudio.blocks.registry import (
        BlockRegistrationError,
        BlockRegistry,
        BlockSpec,
        _format_capabilities_from_class,
        _infer_category,
        _merge_config_schema,
        _type_name_for_class,
    )
    from scistudio.blocks.registry._spec import _spec_from_class

    try:
        spec = _spec_from_class(cls, source="package_validator")
    except BlockRegistrationError:
        BlockRegistry._validate_dynamic_ports(cls)
        spec = BlockSpec(
            name=getattr(cls, "name", cls.__name__),
            description=getattr(cls, "description", "") or (cls.__doc__ or "").split("\n")[0],
            version=package_version,
            module_path=cls.__module__,
            class_name=cls.__name__,
            base_category=_infer_category(cls),
            subcategory=getattr(cls, "subcategory", "") or "",
            input_ports=list(getattr(cls, "input_ports", [])),
            output_ports=list(getattr(cls, "output_ports", [])),
            config_schema=_merge_config_schema(cls),
            source="package_validator",
            type_name=_type_name_for_class(cls),
            direction=getattr(cls, "direction", "") or "",
            dynamic_ports=getattr(cls, "dynamic_ports", None),
            variadic_inputs=bool(getattr(cls, "variadic_inputs", False)),
            variadic_outputs=bool(getattr(cls, "variadic_outputs", False)),
            allowed_input_types=[t.__name__ for t in (getattr(cls, "allowed_input_types", None) or [])],
            allowed_output_types=[t.__name__ for t in (getattr(cls, "allowed_output_types", None) or [])],
            min_input_ports=getattr(cls, "min_input_ports", None),
            max_input_ports=getattr(cls, "max_input_ports", None),
            min_output_ports=getattr(cls, "min_output_ports", None),
            max_output_ports=getattr(cls, "max_output_ports", None),
            supported_extensions=dict(getattr(cls, "supported_extensions", {}) or {}),
            format_capabilities=_format_capabilities_from_class(cls),
        )
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
