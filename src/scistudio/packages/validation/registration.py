"""Production registration handoff helpers for ADR-049."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scistudio.packages.validation.engine import DryRunBuilder, _validate_package_with_dry_run
from scistudio.packages.validation.models import (
    FindingSeverity,
    PackageIdentity,
    PackageInventory,
    PackageValidationFinding,
    PackageValidationProfile,
    PackageValidationReport,
    RegistrationDecision,
    package_validation_report_from_dict,
)


@dataclass(frozen=True)
class PackageRegistrationPlan:
    """Atomic production registration decision.

    The first ADR-049 implementation returns a plan/report boundary instead of
    mutating live registries unless ``commit_to`` is called by installer code
    after the plan is accepted.
    """

    report: PackageValidationReport
    dry_run: DryRunBuilder
    candidate: str | Path | None = None

    @property
    def accepted(self) -> bool:
        return self.report.registration_decision == RegistrationDecision.ACCEPT

    def commit_to(
        self,
        *,
        block_registry: Any | None = None,
        type_registry: Any | None = None,
        previewer_registry: Any | None = None,
        runners: dict[str, Any] | None = None,
    ) -> bool:
        """Atomically commit accepted dry-run rows into caller-owned registries.

        Returns ``False`` without mutation when validation rejected the package.
        If any live registry rejects a row, all registries passed to this call
        are restored to their pre-commit state before the exception is raised.
        """

        if not self.accepted:
            return False

        dry_run = self._materialized_dry_run()
        snapshots = _RegistrySnapshots.capture(
            block_registry=block_registry,
            type_registry=type_registry,
            previewer_registry=previewer_registry,
            runners=runners,
        )
        try:
            if block_registry is not None:
                for block_spec in dry_run.candidate_block_specs():
                    block_registry._register_spec(block_spec)
            if type_registry is not None:
                for type_name, type_spec in dry_run.candidate_type_specs().items():
                    type_registry.register(type_name, type_spec)
            if previewer_registry is not None:
                for previewer_spec in dry_run.candidate_previewer_specs():
                    if not previewer_registry.register(previewer_spec):
                        raise ValueError(f"Previewer registry rejected {previewer_spec.previewer_id!r}.")
            if runners is not None:
                runners.update({name: dry_run.runners[name] for name in dry_run.candidate_runner_names})
        except Exception:
            snapshots.restore(
                block_registry=block_registry,
                type_registry=type_registry,
                previewer_registry=previewer_registry,
                runners=runners,
            )
            raise
        return True

    def _materialized_dry_run(self) -> DryRunBuilder:
        if (
            self.dry_run.candidate_block_names
            or self.dry_run.candidate_type_names
            or self.dry_run.candidate_previewer_ids
            or self.dry_run.candidate_runner_names
            or self.candidate is None
        ):
            return self.dry_run
        report, dry_run = _validate_package_with_dry_run(self.candidate, profile=PackageValidationProfile.PRODUCTION)
        if report.registration_decision == RegistrationDecision.REJECT:
            raise ValueError("Accepted registration plan no longer validates when materializing dry-run rows.")
        return dry_run


def validate_for_registration(
    candidate: str | Path,
    *,
    block_registry: Any | None = None,
    type_registry: Any | None = None,
    previewer_registry: Any | None = None,
    runners: dict[str, Any] | None = None,
) -> PackageRegistrationPlan:
    """Validate *candidate* with the production profile and return a commit plan."""

    isolated_report = _validate_in_subprocess(candidate)
    if isolated_report.registration_decision == RegistrationDecision.REJECT:
        return PackageRegistrationPlan(report=isolated_report, dry_run=DryRunBuilder())
    conflict_report = _existing_registry_conflict_report(
        isolated_report,
        block_registry=block_registry,
        type_registry=type_registry,
        previewer_registry=previewer_registry,
        runners=runners,
    )
    if conflict_report is not None:
        return PackageRegistrationPlan(report=conflict_report, dry_run=DryRunBuilder())

    return PackageRegistrationPlan(report=isolated_report, dry_run=DryRunBuilder(), candidate=candidate)


def _validate_in_subprocess(candidate: str | Path) -> PackageValidationReport:
    command = [
        sys.executable,
        "-m",
        "scistudio.cli.package_validator",
        str(candidate),
        "--profile",
        PackageValidationProfile.PRODUCTION.value,
        "--json",
    ]
    try:
        env = dict(os.environ)
        env["SCISTUDIO_PACKAGE_VALIDATOR_SUBPROCESS"] = "1"
        result = subprocess.run(command, check=False, capture_output=True, text=True, env=env)
    except OSError as exc:
        return _subprocess_failure_report(candidate, f"Production validation subprocess failed to start: {exc}")

    if result.stdout.strip():
        try:
            return package_validation_report_from_dict(json.loads(result.stdout))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            return _subprocess_failure_report(
                candidate,
                f"Production validation subprocess did not emit a valid report: {exc}",
            )
    return _subprocess_failure_report(
        candidate,
        f"Production validation subprocess emitted no report and exited {result.returncode}: {result.stderr.strip()}",
    )


def _subprocess_failure_report(candidate: str | Path, message: str) -> PackageValidationReport:
    package = _candidate_identity(candidate)
    return PackageValidationReport(
        package=package,
        profile=PackageValidationProfile.PRODUCTION,
        inventory=PackageInventory(package=package, surfaces={"distribution_metadata"}),
        findings=[_isolation_failure(candidate, message)],
    )


def _candidate_identity(candidate: str | Path) -> PackageIdentity:
    value = str(candidate)
    return PackageIdentity(name=Path(value).name or value, version="unknown", source=value)


def _isolation_failure(candidate: str | Path, message: str) -> PackageValidationFinding:
    return PackageValidationFinding(
        contract_id="PV-12-004",
        severity=FindingSeverity.BLOCKER,
        surface="security_isolation",
        symbol=str(candidate),
        message=message,
        repair_hint="Run production validation in a working isolated Python environment before registration.",
    )


def _existing_registry_conflict_report(
    report: PackageValidationReport,
    *,
    block_registry: Any | None,
    type_registry: Any | None,
    previewer_registry: Any | None,
    runners: dict[str, Any] | None,
) -> PackageValidationReport | None:
    findings: list[PackageValidationFinding] = []
    if block_registry is not None:
        existing_capability_ids = {capability.id for capability in block_registry.list_format_capabilities()}
        for capability_id in report.inventory.format_capability_ids:
            if capability_id in existing_capability_ids:
                findings.append(
                    PackageValidationFinding(
                        contract_id="PV-13-004",
                        severity=FindingSeverity.BLOCKER,
                        surface="cross_surface_registry_consistency",
                        symbol=capability_id,
                        message=f"Candidate capability id {capability_id!r} already exists in the target registry.",
                        repair_hint="Use a package-qualified capability id that does not conflict with installed packages.",
                        profile_behavior="block",
                    )
                )
    if type_registry is not None:
        existing_types = set(type_registry.all_types())
        for type_name in report.inventory.type_symbols:
            if type_name in existing_types:
                findings.append(
                    PackageValidationFinding(
                        contract_id="PV-13-003",
                        severity=FindingSeverity.BLOCKER,
                        surface="cross_surface_registry_consistency",
                        symbol=type_name,
                        message=f"Candidate type {type_name!r} already exists in the target registry.",
                        repair_hint="Rename the candidate type or upgrade the existing package through an explicit replacement path.",
                        profile_behavior="block",
                    )
                )
    if previewer_registry is not None:
        for previewer_id in report.inventory.previewer_ids:
            if previewer_registry.get(previewer_id) is not None:
                findings.append(
                    PackageValidationFinding(
                        contract_id="PV-13-004",
                        severity=FindingSeverity.BLOCKER,
                        surface="cross_surface_registry_consistency",
                        symbol=previewer_id,
                        message=f"Candidate previewer_id {previewer_id!r} already exists in the target registry.",
                        repair_hint="Use a unique package-qualified previewer_id or perform an explicit package upgrade.",
                        profile_behavior="block",
                    )
                )
    if runners is not None:
        for runner_name in report.inventory.runner_symbols:
            if runner_name in runners:
                findings.append(
                    PackageValidationFinding(
                        contract_id="PV-99-001",
                        severity=FindingSeverity.ERROR,
                        surface="runners",
                        symbol=runner_name,
                        message=f"Candidate runner {runner_name!r} already exists in the target registry.",
                        repair_hint="Use a unique runner entry-point name or perform an explicit package upgrade.",
                        profile_behavior="error",
                    )
                )
    if not findings:
        return None
    return PackageValidationReport(
        package=report.package,
        profile=report.profile,
        inventory=report.inventory,
        contract_results=report.contract_results,
        findings=[*report.findings, *findings],
        dry_run_registries=report.dry_run_registries,
    )


@dataclass(frozen=True)
class _RegistrySnapshots:
    block_registry_state: tuple[dict[str, Any], dict[str, str], dict[str, Any]] | None
    type_registry_state: dict[str, Any] | None
    previewer_registry_state: tuple[dict[str, Any], list[str], dict[str, str]] | None
    runners_state: dict[str, Any] | None

    @classmethod
    def capture(
        cls,
        *,
        block_registry: Any | None,
        type_registry: Any | None,
        previewer_registry: Any | None,
        runners: dict[str, Any] | None,
    ) -> _RegistrySnapshots:
        return cls(
            block_registry_state=(
                dict(block_registry._registry),
                dict(block_registry._aliases),
                dict(block_registry._packages),
            )
            if block_registry is not None
            else None,
            type_registry_state=dict(type_registry._registry) if type_registry is not None else None,
            previewer_registry_state=(
                dict(previewer_registry._by_id),
                list(previewer_registry._diagnostics),
                dict(previewer_registry._project_default_previewers),
            )
            if previewer_registry is not None
            else None,
            runners_state=dict(runners) if runners is not None else None,
        )

    def restore(
        self,
        *,
        block_registry: Any | None,
        type_registry: Any | None,
        previewer_registry: Any | None,
        runners: dict[str, Any] | None,
    ) -> None:
        if block_registry is not None and self.block_registry_state is not None:
            registry, aliases, packages = self.block_registry_state
            block_registry._registry = dict(registry)
            block_registry._aliases = dict(aliases)
            block_registry._packages = dict(packages)
        if type_registry is not None and self.type_registry_state is not None:
            type_registry._registry = dict(self.type_registry_state)
        if previewer_registry is not None and self.previewer_registry_state is not None:
            by_id, diagnostics, project_defaults = self.previewer_registry_state
            previewer_registry._by_id = dict(by_id)
            previewer_registry._diagnostics = list(diagnostics)
            previewer_registry._project_default_previewers = dict(project_defaults)
        if runners is not None and self.runners_state is not None:
            runners.clear()
            runners.update(self.runners_state)
