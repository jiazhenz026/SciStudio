"""Production registration handoff helpers for ADR-049."""

from __future__ import annotations

import json
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

        snapshots = _RegistrySnapshots.capture(
            block_registry=block_registry,
            type_registry=type_registry,
            previewer_registry=previewer_registry,
            runners=runners,
        )
        try:
            if block_registry is not None:
                for block_spec in self.dry_run.block_registry.all_specs().values():
                    block_registry._register_spec(block_spec)
            if type_registry is not None:
                for type_name, type_spec in self.dry_run.type_registry.all_types().items():
                    type_registry.register(type_name, type_spec)
            if previewer_registry is not None:
                for previewer_spec in self.dry_run.previewer_registry.all_specs():
                    if not previewer_registry.register(previewer_spec):
                        raise ValueError(f"Previewer registry rejected {previewer_spec.previewer_id!r}.")
            if runners is not None:
                runners.update(self.dry_run.runners)
        except Exception:
            snapshots.restore(
                block_registry=block_registry,
                type_registry=type_registry,
                previewer_registry=previewer_registry,
                runners=runners,
            )
            raise
        return True


def validate_for_registration(candidate: str | Path) -> PackageRegistrationPlan:
    """Validate *candidate* with the production profile and return a commit plan."""

    isolated_report = _validate_in_subprocess(candidate)
    if isolated_report.registration_decision == RegistrationDecision.REJECT:
        return PackageRegistrationPlan(report=isolated_report, dry_run=DryRunBuilder())

    report, dry_run = _validate_package_with_dry_run(candidate, profile=PackageValidationProfile.PRODUCTION)
    return PackageRegistrationPlan(report=report, dry_run=dry_run)


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
        result = subprocess.run(command, check=False, capture_output=True, text=True)
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
    package = PackageIdentity(
        name=Path(str(candidate)).name or str(candidate), version="unknown", source=str(candidate)
    )
    return PackageValidationReport(
        package=package,
        profile=PackageValidationProfile.PRODUCTION,
        inventory=PackageInventory(package=package, surfaces={"distribution_metadata"}),
        findings=[
            PackageValidationFinding(
                contract_id="PV-12-004",
                severity=FindingSeverity.BLOCKER,
                surface="security_isolation",
                symbol=str(candidate),
                message=message,
                repair_hint="Run production validation in a working isolated Python environment before registration.",
            )
        ],
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
