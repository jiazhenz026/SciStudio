"""Change contract schemas for ADR-042 gate checks."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IssueReference: TypeAlias = int | str


class ChangeKind(StrEnum):
    """Top-level intent for a change contract."""

    ADDITIVE = "additive"
    MIGRATION = "migration"
    REFACTOR = "refactor"
    REMOVAL = "removal"
    COMPATIBILITY = "compatibility"
    DOCS_ONLY = "docs_only"


class ChangeSurfaceKind(StrEnum):
    """Addressable surface kinds declared by a change contract."""

    MODULE = "module"
    SYMBOL = "symbol"
    FILE = "file"
    GLOB = "glob"
    ROUTE = "route"
    ENTRY_POINT = "entry_point"
    FRONTEND_COMPONENT = "frontend_component"
    CLI = "cli"
    TOOL = "tool"


class ChangeSurfaceScope(StrEnum):
    """Repository scope for a declared change surface."""

    PRODUCTION = "production"
    TEST = "test"
    DOCS = "docs"
    GENERATED = "generated"
    ANY = "any"


class ForbiddenReferenceKind(StrEnum):
    """Forbidden production reference kinds."""

    MODULE = "module"
    SYMBOL = "symbol"
    IMPORT = "import"
    FILE = "file"
    GLOB = "glob"
    ROUTE = "route"
    ENTRY_POINT = "entry_point"
    FRONTEND_COMPONENT = "frontend_component"
    CLI = "cli"
    TOOL = "tool"
    PATTERN = "pattern"


class RequiredCanaryKind(StrEnum):
    """Kinds of public or live behavior that require canary evidence."""

    PUBLIC_API = "public_api"
    UI = "ui"
    CLI = "cli"
    PLUGIN = "plugin"
    WORKFLOW_RUNTIME = "workflow_runtime"
    EXTERNAL_INTEGRATION = "external_integration"


class BaselinePolicyMode(StrEnum):
    """Supported baseline reconciliation modes."""

    NO_NEW_VIOLATIONS = "no_new_violations"


def _validate_issue_reference(value: IssueReference) -> IssueReference:
    if isinstance(value, int):
        if value <= 0:
            raise ValueError("issue references must be positive")
        return value
    if not value.strip():
        raise ValueError("issue references must be non-empty strings")
    return value.strip()


def _dedupe_non_empty_strings(values: list[str], *, field_name: str) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip()
        if not value:
            raise ValueError(f"{field_name} entries must be non-empty strings")
        if value in seen:
            raise ValueError(f"duplicate {field_name} entry: {value}")
        seen.add(value)
        cleaned.append(value)
    return cleaned


class _ChangeContractSchema(BaseModel):
    """Shared validators for optional fields used by contract schemas."""

    @field_validator("issue", check_fields=False)
    @classmethod
    def _issue_reference(cls, value: IssueReference | None) -> IssueReference | None:
        if value is None:
            return None
        return _validate_issue_reference(value)

    @field_validator("allowed_scopes", check_fields=False)
    @classmethod
    def _allowed_scopes_unique(cls, values: list[ChangeSurfaceScope]) -> list[ChangeSurfaceScope]:
        seen: set[ChangeSurfaceScope] = set()
        for value in values:
            if value in seen:
                raise ValueError(f"duplicate allowed scope: {value}")
            seen.add(value)
        return values


class ChangeSurface(_ChangeContractSchema):
    """One target surface declared by a change contract."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: ChangeSurfaceKind
    target: str = Field(min_length=1)
    scope: ChangeSurfaceScope = ChangeSurfaceScope.PRODUCTION
    reason: str | None = Field(default=None, min_length=8)
    owner: str | None = Field(default=None, min_length=1)
    issue: IssueReference | None = None
    expires: date | None = None


class ChangeContractSurfaces(BaseModel):
    """Grouped added, changed, removed, and retained surface declarations."""

    model_config = ConfigDict(extra="forbid")

    added: list[ChangeSurface] = Field(default_factory=list)
    changed: list[ChangeSurface] = Field(default_factory=list)
    removed: list[ChangeSurface] = Field(default_factory=list)
    retained: list[ChangeSurface] = Field(default_factory=list)

    @field_validator("added", "changed", "removed", "retained")
    @classmethod
    def _surface_entries_unique(cls, surfaces: list[ChangeSurface]) -> list[ChangeSurface]:
        seen: set[tuple[ChangeSurfaceKind, str, ChangeSurfaceScope]] = set()
        for surface in surfaces:
            key = (surface.kind, surface.target, surface.scope)
            if key in seen:
                raise ValueError(f"duplicate surface declaration: {surface.kind}:{surface.target}:{surface.scope}")
            seen.add(key)
        return surfaces

    @model_validator(mode="after")
    def _retained_surfaces_are_justified(self) -> ChangeContractSurfaces:
        for surface in self.retained:
            missing = [
                name
                for name, value in (
                    ("reason", surface.reason),
                    ("owner", surface.owner),
                    ("issue", surface.issue),
                )
                if value is None
            ]
            if missing:
                missing_text = ", ".join(missing)
                raise ValueError(f"retained surfaces require reason, owner, and issue: missing {missing_text}")
        return self

    @property
    def has_declared_surface(self) -> bool:
        """Return true when any surface bucket is non-empty."""

        return bool(self.added or self.changed or self.removed or self.retained)


class ForbiddenProdReference(_ChangeContractSchema):
    """A reference that must not appear in production code."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: ForbiddenReferenceKind
    target: str = Field(min_length=1)
    allowed_scopes: list[ChangeSurfaceScope] = Field(
        default_factory=lambda: [ChangeSurfaceScope.TEST, ChangeSurfaceScope.DOCS, ChangeSurfaceScope.GENERATED]
    )
    reason: str | None = Field(default=None, min_length=8)


class RequiredReachability(BaseModel):
    """Required production reachability evidence for a declared surface."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    surface: ChangeSurface
    production_roots: list[str] = Field(default_factory=list)
    registrations: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    canaries: list[str] = Field(default_factory=list)
    reason: str | None = Field(default=None, min_length=8)

    @field_validator("production_roots", "registrations", "entry_points", "canaries")
    @classmethod
    def _evidence_entries_unique(cls, values: list[str], info: object) -> list[str]:
        field_name = getattr(info, "field_name", "evidence")
        return _dedupe_non_empty_strings(values, field_name=field_name)

    @model_validator(mode="after")
    def _has_reachability_path(self) -> RequiredReachability:
        if not (self.production_roots or self.registrations or self.entry_points or self.canaries):
            raise ValueError("required reachability must name a production root, registration, entry point, or canary")
        return self


class RequiredCanary(BaseModel):
    """Test or smoke evidence required for public and live behavior."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: RequiredCanaryKind
    surface: ChangeSurface
    test_path: str | None = Field(default=None, min_length=1)
    command: list[str] = Field(default_factory=list)
    entry_point: str | None = Field(default=None, min_length=1)
    rationale: str | None = Field(default=None, min_length=8)

    @field_validator("command")
    @classmethod
    def _command_entries_unique(cls, values: list[str]) -> list[str]:
        return _dedupe_non_empty_strings(values, field_name="command")

    @model_validator(mode="after")
    def _has_canary_evidence(self) -> RequiredCanary:
        if not (self.test_path or self.command or self.entry_point):
            raise ValueError("required canaries must declare test_path, command, or entry_point evidence")
        return self


class ChangeWaiver(_ChangeContractSchema):
    """Narrow exception to a change contract rule."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rule_id: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    issue: IssueReference
    reason: str = Field(min_length=8)
    surface: ChangeSurface | None = None
    allowed_scopes: list[ChangeSurfaceScope] = Field(default_factory=list)
    expires: date | None = None


class ChangeContractBaselinePolicy(BaseModel):
    """Baseline behavior declared by a contract."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mode: BaselinePolicyMode = BaselinePolicyMode.NO_NEW_VIOLATIONS
    baseline: str | None = Field(default=None, min_length=1)
    require_renewed_justification_on_touched: bool = True


class ChangeContract(BaseModel):
    """Per-change intent contract linked from an ADR or spec."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=3)
    parent: str = Field(min_length=1)
    change_kind: ChangeKind
    surfaces: ChangeContractSurfaces = Field(default_factory=ChangeContractSurfaces)
    forbidden_prod_references: list[ForbiddenProdReference] = Field(default_factory=list)
    required_reachability: list[RequiredReachability] = Field(default_factory=list)
    required_canaries: list[RequiredCanary] = Field(default_factory=list)
    waivers: list[ChangeWaiver] = Field(default_factory=list)
    baseline_policy: ChangeContractBaselinePolicy = Field(default_factory=ChangeContractBaselinePolicy)

    @model_validator(mode="after")
    def _declares_change_intent(self) -> ChangeContract:
        if self.change_kind == ChangeKind.DOCS_ONLY:
            return self
        if any(
            (
                self.surfaces.has_declared_surface,
                self.forbidden_prod_references,
                self.required_reachability,
                self.required_canaries,
                self.waivers,
            )
        ):
            return self
        raise ValueError("change contracts must declare at least one surface, rule, reachability, canary, or waiver")


class ChangeContractLink(BaseModel):
    """Frontmatter declaration that links to a physical change contract."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    path: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def _normalise_path(cls, value: str) -> str:
        return value.replace("\\", "/")


class ChangeContractNotApplicable(_ChangeContractSchema):
    """Structured frontmatter declaration for docs-only or irrelevant changes."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Literal["not_applicable"] = "not_applicable"
    rationale: str = Field(min_length=8)
    owner: str | None = Field(default=None, min_length=1)
    issue: IssueReference | None = None


ChangeContractFrontmatterDeclaration: TypeAlias = ChangeContractLink | ChangeContractNotApplicable


class ChangeContractBaselineFinding(_ChangeContractSchema):
    """One grandfathered finding identity in the committed baseline."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    fingerprint: str = Field(min_length=1)
    surface: ChangeSurface | None = None
    source: str | None = Field(default=None, min_length=1)
    owner: str | None = Field(default=None, min_length=1)
    issue: IssueReference | None = None
    reason: str | None = Field(default=None, min_length=8)
    expires: date | None = None


class ChangeContractBaseline(BaseModel):
    """Committed baseline for grandfathered change-contract findings."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    version: Literal["1"] = "1"
    generated_from: str = Field(min_length=1)
    findings: list[ChangeContractBaselineFinding] = Field(default_factory=list)
    expires: date | None = None

    @field_validator("findings")
    @classmethod
    def _finding_ids_unique(cls, values: list[ChangeContractBaselineFinding]) -> list[ChangeContractBaselineFinding]:
        seen: set[str] = set()
        for finding in values:
            if finding.id in seen:
                raise ValueError(f"duplicate baseline finding id: {finding.id}")
            seen.add(finding.id)
        return values


__all__ = [
    "BaselinePolicyMode",
    "ChangeContract",
    "ChangeContractBaseline",
    "ChangeContractBaselineFinding",
    "ChangeContractBaselinePolicy",
    "ChangeContractFrontmatterDeclaration",
    "ChangeContractLink",
    "ChangeContractNotApplicable",
    "ChangeContractSurfaces",
    "ChangeKind",
    "ChangeSurface",
    "ChangeSurfaceKind",
    "ChangeSurfaceScope",
    "ChangeWaiver",
    "ForbiddenProdReference",
    "ForbiddenReferenceKind",
    "IssueReference",
    "RequiredCanary",
    "RequiredCanaryKind",
    "RequiredReachability",
]
