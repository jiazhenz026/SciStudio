"""ADR-049 package validator public API."""

from scistudio.packages.validation.engine import validate_installed_package, validate_package
from scistudio.packages.validation.models import (
    CandidatePackage,
    ContractApplicability,
    ContractResult,
    DryRunRegistrySet,
    PackageIdentity,
    PackageInventory,
    PackageValidationFinding,
    PackageValidationProfile,
    PackageValidationReport,
    PackageValidationStatus,
    RegistrationDecision,
)

__all__ = [
    "CandidatePackage",
    "ContractApplicability",
    "ContractResult",
    "DryRunRegistrySet",
    "PackageIdentity",
    "PackageInventory",
    "PackageValidationFinding",
    "PackageValidationProfile",
    "PackageValidationReport",
    "PackageValidationStatus",
    "RegistrationDecision",
    "validate_installed_package",
    "validate_package",
]
