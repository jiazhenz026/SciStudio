"""ADR-049 contract table loading and applicability helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scistudio.packages.validation.models import ContractApplicability

CONTRACT_TABLE_SCHEMA_VERSION = "adr049.package_contract_table.v1"


@dataclass(frozen=True)
class PackageContract:
    """One machine-verifiable ADR-049 contract row."""

    contract_id: str
    section: str
    title: str
    severity: str
    validator_profile: dict[str, str]
    applicability: ContractApplicability

    @property
    def primary_surface(self) -> str:
        return self.applicability.candidate_surfaces[0] if self.applicability.candidate_surfaces else "candidate"


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_contract_dir() -> Path:
    return repository_root() / "docs" / "planning" / "adr-049-package-validator" / "contracts"


def load_contract_tables(contract_dir: Path | None = None) -> list[PackageContract]:
    """Load and normalize all ADR-049 package-validator contract rows."""

    root = contract_dir or default_contract_dir()
    contracts: list[PackageContract] = []
    seen_ids: set[str] = set()
    for path in sorted(root.glob("pv-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        schema_version = payload.get("schema_version")
        if schema_version != CONTRACT_TABLE_SCHEMA_VERSION:
            raise ValueError(f"{path}: unsupported schema_version {schema_version!r}")
        for row in payload.get("contracts", []):
            applicability = _applicability_from_row(path, row)
            contract_id = str(row.get("id", ""))
            if not contract_id:
                raise ValueError(f"{path}: contract row is missing id")
            if contract_id in seen_ids:
                raise ValueError(f"{path}: duplicate contract id {contract_id}")
            seen_ids.add(contract_id)
            profile = row.get("validator_profile")
            if not isinstance(profile, dict) or "development" not in profile or "production" not in profile:
                raise ValueError(f"{path}: {contract_id} missing validator_profile entries")
            contracts.append(
                PackageContract(
                    contract_id=contract_id,
                    section=str(row.get("section", "")),
                    title=str(row.get("title", "")),
                    severity=str(row.get("severity", "error")),
                    validator_profile={str(key): str(value) for key, value in profile.items()},
                    applicability=applicability,
                )
            )
    return contracts


def contract_applies(contract: PackageContract, surfaces: set[str]) -> bool:
    """Return whether *contract* applies to a candidate exposing *surfaces*."""

    return bool(set(contract.applicability.candidate_surfaces) & surfaces)


def _applicability_from_row(path: Path, row: dict[str, Any]) -> ContractApplicability:
    applicability = row.get("applicability")
    contract_id = row.get("id", "<unknown>")
    if not isinstance(applicability, dict):
        raise ValueError(f"{path}: {contract_id} missing applicability")
    surfaces = applicability.get("candidate_surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise ValueError(f"{path}: {contract_id} missing applicability.candidate_surfaces")
    trigger = applicability.get("trigger")
    if not isinstance(trigger, str) or not trigger:
        raise ValueError(f"{path}: {contract_id} missing applicability.trigger")
    not_applicable = applicability.get("not_applicable_result")
    if not_applicable != "not_applicable":
        raise ValueError(f"{path}: {contract_id} must use not_applicable_result='not_applicable'")
    return ContractApplicability(candidate_surfaces=tuple(str(surface) for surface in surfaces), trigger=trigger)
