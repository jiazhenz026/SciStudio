"""Data models for ADR-049 package validation reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

REPORT_SCHEMA_VERSION = "adr049.package_validation_report.v1"


class PackageValidationProfile(StrEnum):
    """Validation strictness profile."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


class PackageValidationStatus(StrEnum):
    """Overall report status."""

    PASS = "pass"
    PASS_WITH_WARNINGS = "pass_with_warnings"
    FAIL = "fail"


class RegistrationDecision(StrEnum):
    """Install/registration decision derived from findings and profile."""

    ACCEPT = "accept"
    REJECT = "reject"


class ContractResultState(StrEnum):
    """Per-contract validation state."""

    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not_applicable"


class FindingSeverity(StrEnum):
    """Finding severity understood by ADR-049."""

    BLOCKER = "blocker"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class PackageIdentity:
    """Candidate package identity carried in the report envelope."""

    name: str
    version: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "version": self.version, "source": self.source}


@dataclass(frozen=True)
class CandidatePackage:
    """Caller-supplied candidate package descriptor."""

    source_kind: str
    value: str
    root_path: Path | None = None
    name: str = ""
    version: str = ""


@dataclass(frozen=True)
class ContractApplicability:
    """Runtime applicability metadata loaded from an ADR-049 contract row."""

    candidate_surfaces: tuple[str, ...]
    trigger: str
    not_applicable_result: str = ContractResultState.NOT_APPLICABLE.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_surfaces": list(self.candidate_surfaces),
            "trigger": self.trigger,
            "not_applicable_result": self.not_applicable_result,
        }


@dataclass
class PackageInventory:
    """Mechanical inventory of surfaces declared by a candidate package."""

    package: PackageIdentity
    root_path: Path | None = None
    entry_points: list[dict[str, str]] = field(default_factory=list)
    surfaces: set[str] = field(default_factory=set)
    package_info: dict[str, Any] | None = None
    block_symbols: list[str] = field(default_factory=list)
    type_symbols: list[str] = field(default_factory=list)
    previewer_ids: list[str] = field(default_factory=list)
    runner_symbols: list[str] = field(default_factory=list)
    format_capability_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_points": [f"{item['group']}:{item['name']}" for item in self.entry_points],
            "entry_point_details": list(self.entry_points),
            "surfaces": sorted(self.surfaces),
            "package_info": self.package_info,
            "blocks": list(self.block_symbols),
            "types": list(self.type_symbols),
            "previewers": list(self.previewer_ids),
            "runners": list(self.runner_symbols),
            "format_capabilities": list(self.format_capability_ids),
        }


@dataclass(frozen=True)
class ContractResult:
    """Per-contract result emitted for every loaded ADR-049 row."""

    contract_id: str
    result: ContractResultState | str
    surface: str
    symbol: str | None = None
    severity: FindingSeverity | str | None = None
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "contract_id": self.contract_id,
            "result": str(self.result),
            "surface": self.surface,
        }
        if self.symbol:
            data["symbol"] = self.symbol
        if self.severity:
            data["severity"] = str(self.severity)
        if self.evidence:
            data["evidence"] = self.evidence
        return data


@dataclass(frozen=True)
class PackageValidationFinding:
    """Structured problem found during package validation."""

    contract_id: str
    severity: FindingSeverity | str
    surface: str
    message: str
    repair_hint: str
    symbol: str | None = None
    source_path: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    profile_behavior: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "contract_id": self.contract_id,
            "severity": str(self.severity),
            "surface": self.surface,
            "message": self.message,
            "repair_hint": self.repair_hint,
        }
        if self.symbol:
            data["symbol"] = self.symbol
            data["source_symbol"] = self.symbol
        if self.source_path:
            data["source_path"] = self.source_path
        if self.evidence:
            data["evidence"] = dict(self.evidence)
        if self.profile_behavior:
            data["profile_behavior"] = self.profile_behavior
        return data


@dataclass(frozen=True)
class DryRunRegistrySet:
    """Summary of non-live registry rows produced by validation."""

    blocks: int = 0
    types: int = 0
    previewers: int = 0
    format_capabilities: int = 0
    runners: int = 0
    api_payloads: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "blocks": self.blocks,
            "types": self.types,
            "previewers": self.previewers,
            "format_capabilities": self.format_capabilities,
            "runners": self.runners,
            "api_payloads": self.api_payloads,
        }


@dataclass
class PackageValidationReport:
    """ADR-049 report envelope for CLI, logs, desktop, and tests."""

    package: PackageIdentity
    profile: PackageValidationProfile
    inventory: PackageInventory
    contract_results: list[ContractResult] = field(default_factory=list)
    findings: list[PackageValidationFinding] = field(default_factory=list)
    dry_run_registries: DryRunRegistrySet = field(default_factory=DryRunRegistrySet)

    @property
    def status(self) -> PackageValidationStatus:
        severities = {str(finding.severity) for finding in self.findings}
        if FindingSeverity.BLOCKER.value in severities or FindingSeverity.ERROR.value in severities:
            return PackageValidationStatus.FAIL
        if FindingSeverity.WARNING.value in severities:
            return PackageValidationStatus.PASS_WITH_WARNINGS
        return PackageValidationStatus.PASS

    @property
    def registration_decision(self) -> RegistrationDecision:
        return (
            RegistrationDecision.REJECT if self.status == PackageValidationStatus.FAIL else RegistrationDecision.ACCEPT
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "package": self.package.to_dict(),
            "profile": self.profile.value,
            "status": self.status.value,
            "registration_decision": self.registration_decision.value,
            "inventory": self.inventory.to_dict(),
            "contract_results": [result.to_dict() for result in self.contract_results],
            "findings": [finding.to_dict() for finding in self.findings],
            "dry_run_registries": self.dry_run_registries.to_dict(),
        }

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        """Pydantic-compatible adapter used by tests and callers."""

        return self.to_dict()


def package_validation_report_from_dict(data: dict[str, Any]) -> PackageValidationReport:
    """Rehydrate a report emitted by the validator CLI JSON path."""

    package_data = data.get("package", {})
    package = PackageIdentity(
        name=str(package_data.get("name", "")),
        version=str(package_data.get("version", "unknown")),
        source=str(package_data.get("source", "")),
    )
    inventory_data = data.get("inventory", {})
    inventory = PackageInventory(
        package=package,
        entry_points=list(inventory_data.get("entry_point_details", [])),
        surfaces=set(inventory_data.get("surfaces", [])),
        package_info=inventory_data.get("package_info"),
        block_symbols=list(inventory_data.get("blocks", [])),
        type_symbols=list(inventory_data.get("types", [])),
        previewer_ids=list(inventory_data.get("previewers", [])),
        runner_symbols=list(inventory_data.get("runners", [])),
        format_capability_ids=list(inventory_data.get("format_capabilities", [])),
    )
    dry_run_data = data.get("dry_run_registries", {})
    return PackageValidationReport(
        package=package,
        profile=PackageValidationProfile(str(data.get("profile", PackageValidationProfile.DEVELOPMENT.value))),
        inventory=inventory,
        contract_results=[
            ContractResult(
                contract_id=str(item.get("contract_id", "")),
                result=ContractResultState(str(item.get("result", ContractResultState.NOT_APPLICABLE.value))),
                surface=str(item.get("surface", "")),
                symbol=item.get("symbol"),
                severity=item.get("severity"),
                evidence=item.get("evidence"),
            )
            for item in data.get("contract_results", [])
            if isinstance(item, dict)
        ],
        findings=[
            PackageValidationFinding(
                contract_id=str(item.get("contract_id", "")),
                severity=FindingSeverity(str(item.get("severity", FindingSeverity.ERROR.value))),
                surface=str(item.get("surface", "")),
                message=str(item.get("message", "")),
                repair_hint=str(item.get("repair_hint", "")),
                symbol=item.get("symbol") or item.get("source_symbol"),
                source_path=item.get("source_path"),
                evidence=dict(item.get("evidence", {})),
                profile_behavior=item.get("profile_behavior"),
            )
            for item in data.get("findings", [])
            if isinstance(item, dict)
        ],
        dry_run_registries=DryRunRegistrySet(
            blocks=int(dry_run_data.get("blocks", 0)),
            types=int(dry_run_data.get("types", 0)),
            previewers=int(dry_run_data.get("previewers", 0)),
            format_capabilities=int(dry_run_data.get("format_capabilities", 0)),
            runners=int(dry_run_data.get("runners", 0)),
            api_payloads=int(dry_run_data.get("api_payloads", 0)),
        ),
    )
