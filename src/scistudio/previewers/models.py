"""Typed models for the ADR-048 extensible preview subsystem.

This module defines the public contract every other half of SPEC 1 depends
on (the API runtime, the frontend PreviewHost, and package-owned previewers
such as ``scistudio-blocks-imaging``):

* :class:`PreviewTarget` — what is being previewed (data ref / collection /
  artifact / plot artifact) plus its recorded type chain.
* :class:`PreviewerSpec` — a provider declaration (id, owner tier, target
  type, priority, capabilities, backend provider, frontend manifest).
* :class:`FrontendManifest` — the same-origin descriptor a previewer ships
  for its dynamically-loaded ESM module + CSS assets.
* :class:`PreviewEnvelope` — the canonical backend response (kind, payload,
  resources, metadata, diagnostics, error).
* :class:`PreviewMetadata` — the sampled/truncated/cached/derived/complete/
  failed display flags every envelope must carry (FR-011).
* :class:`PreviewSession` — the backend-owned session record.
* The :data:`PreviewProvider` callable protocol and the
  :data:`PreviewerEntryPoint` package entry-point protocol.
* The typed error hierarchy (:class:`RoutingAmbiguityError`,
  :class:`UnknownPreviewerError`, :class:`MissingBundleError`,
  :class:`ProviderError`, :class:`UnknownTargetError`).

The models are plain frozen dataclasses (not Pydantic) so the core
previewer layer stays import-light and free of the API layer; the
``scistudio.api.schemas`` module mirrors the wire shapes as Pydantic
models for FastAPI serialization.

ADR-048 §3 governs the resolution order and entity definitions; this spec
is ``docs/specs/adr-048-preview-system.md`` (FR-001..FR-030, Key Entities).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from scistudio.previewers.data_access import PreviewDataAccess


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class OwnerKind(StrEnum):
    """Provenance tier of a previewer; drives routing precedence (FR-003).

    Project previewers win over package previewers, which win over core
    fallbacks. The string values are stable and surface verbatim in the
    REST/session API payloads.
    """

    CORE = "core"
    PACKAGE = "package"
    PROJECT = "project"


class TargetKind(StrEnum):
    """What a :class:`PreviewTarget` points at."""

    DATA_REF = "data_ref"
    COLLECTION_REF = "collection_ref"
    ARTIFACT = "artifact"
    PLOT_ARTIFACT = "plot_artifact"


class EnvelopeKind(StrEnum):
    """Canonical fallback kinds for a :class:`PreviewEnvelope` (spec Key Entities).

    These are previewer-domain kinds. They are intentionally distinct from
    the *legacy* REST ``preview.kind`` strings (``table``/``image``/
    ``chart``/``text``/``composite``/``artifact``); the compatibility
    adapter in the API runtime maps between the two so existing callers and
    tests keep working.
    """

    DATAFRAME = "dataframe"
    ARRAY = "array"
    SERIES = "series"
    TEXT = "text"
    ARTIFACT = "artifact"
    COMPOSITE = "composite"
    COLLECTION = "collection"
    PLOT = "plot"
    ERROR = "error"


class PreviewErrorCode(StrEnum):
    """Deterministic diagnostic codes for preview failures (FR-029)."""

    ROUTING_AMBIGUITY = "routing_ambiguity"
    UNKNOWN_PREVIEWER = "unknown_previewer"
    UNKNOWN_TARGET = "unknown_target"
    MISSING_BUNDLE = "missing_bundle"
    PROVIDER_EXCEPTION = "provider_exception"
    INVALID_SPEC = "invalid_spec"
    DUPLICATE_PREVIEWER_ID = "duplicate_previewer_id"
    BUDGET_EXCEEDED = "budget_exceeded"


# The current previewer API compatibility version. Specs declaring a
# different ``api_version`` are still loaded but flagged via diagnostics so
# the frontend can refuse to mount an incompatible manifest (FR-006).
PREVIEWER_API_VERSION = "1"


# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreviewSource:
    """Optional workflow/node/output identity for UI display (spec Key Entities).

    Carries no runtime truth — it is display metadata only so the preview
    panel can label "node X, output port Y" without the previewer becoming
    a workflow producer (FR-028).
    """

    workflow_id: str | None = None
    node_id: str | None = None
    output_port: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreviewTarget:
    """Identifies what is being previewed (spec Key Entities / ADR-048 §3).

    Attributes:
        kind: ``data_ref`` / ``collection_ref`` / ``artifact`` /
            ``plot_artifact``.
        ref: Data, collection, or artifact reference (a catalog id or path).
        recorded_type: The most-specific recorded type name from storage
            metadata, e.g. ``"Image"``. Empty when unknown.
        type_chain: Ordered general -> specific type chain, e.g.
            ``["DataObject", "Array", "Image"]``. The router walks this for
            parent fallback (FR-003).
        collection_item_type: Known item type when ``kind`` is
            ``collection_ref``.
        source: Optional workflow/node/output identity for UI display.
    """

    kind: TargetKind
    ref: str
    recorded_type: str = ""
    type_chain: tuple[str, ...] = ()
    collection_item_type: str | None = None
    source: PreviewSource | None = None

    @property
    def is_collection(self) -> bool:
        return self.kind is TargetKind.COLLECTION_REF

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "ref": self.ref,
            "recorded_type": self.recorded_type,
            "type_chain": list(self.type_chain),
            "collection_item_type": self.collection_item_type,
            "source": self.source.to_dict() if self.source is not None else None,
        }


# ---------------------------------------------------------------------------
# Frontend manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrontendManifest:
    """Same-origin descriptor for a previewer's dynamically loaded UI (FR-022/FR-024).

    A package or project ships a JavaScript ESM module that the frontend
    PreviewHost imports at runtime. The backend validates this descriptor
    (:mod:`scistudio.previewers.assets`) before serving any asset:

    Attributes:
        previewer_id: The owning previewer's stable id.
        module_url: Backend-relative URL the host imports the ESM module
            from, e.g. ``/api/previews/assets/<asset_id>``. Remote (http/https)
            URLs are rejected by the asset validator.
        export_name: Named export inside the module to mount.
        css: Optional list of backend-relative CSS asset URLs.
        version: Previewer bundle version (fingerprint or semver).
        api_version: Previewer API compatibility version; must match
            :data:`PREVIEWER_API_VERSION` to mount without a diagnostic.
        asset_root: Filesystem directory the package/project confines its
            assets under. Never serialized to the frontend; used only by the
            backend asset validator to path-confine reads (FR-024).
    """

    previewer_id: str
    module_url: str
    export_name: str = "default"
    css: tuple[str, ...] = ()
    version: str = "0"
    api_version: str = PREVIEWER_API_VERSION
    asset_root: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Wire shape sent to the frontend. ``asset_root`` is intentionally omitted."""
        return {
            "previewer_id": self.previewer_id,
            "module_url": self.module_url,
            "export_name": self.export_name,
            "css": list(self.css),
            "version": self.version,
            "api_version": self.api_version,
        }


def _provider_repr(provider: object) -> str | None:
    if isinstance(provider, str):
        return provider
    if provider is None:
        return None
    return getattr(provider, "__name__", repr(provider))


# ---------------------------------------------------------------------------
# Previewer spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreviewerSpec:
    """Declares a preview provider (spec Key Entities / FR-006).

    Attributes:
        previewer_id: Stable id, e.g. ``"core.array.basic"``.
        owner_kind: ``core`` / ``package`` / ``project``.
        owner_name: Package name, project identifier, or ``"scistudio"``.
        target_type: Fully qualified target type name this previewer claims,
            e.g. ``"Array"`` or ``"Image"``.
        supports_collection: Whether the previewer can inspect collections
            (i.e. claims ``Collection[target_type]``).
        priority: Integer priority within one tier and type specificity;
            higher wins. Equal priority within a tier+specificity is an
            ambiguity error (FR-004).
        capabilities: Feature strings such as ``slice``, ``table``, ``lut``,
            ``export``.
        backend_provider: Either a :data:`PreviewProvider` callable or a
            dotted ``module:callable`` import path resolved lazily.
        resource_provider: Optional package/project-owned follow-up resource
            reader for custom resource ids declared by the envelope.
        frontend_manifest: Optional same-origin manifest descriptor.
        api_version: Previewer API compatibility version.
    """

    previewer_id: str
    owner_kind: OwnerKind
    owner_name: str
    target_type: str
    supports_collection: bool = False
    priority: int = 0
    capabilities: tuple[str, ...] = ()
    backend_provider: PreviewProvider | str | None = None
    resource_provider: PreviewResourceProvider | str | None = None
    frontend_manifest: FrontendManifest | None = None
    api_version: str = PREVIEWER_API_VERSION

    def to_dict(self) -> dict[str, Any]:
        provider_repr = _provider_repr(self.backend_provider)
        resource_provider_repr = _provider_repr(self.resource_provider)
        return {
            "previewer_id": self.previewer_id,
            "owner_kind": self.owner_kind.value,
            "owner_name": self.owner_name,
            "target_type": self.target_type,
            "supports_collection": self.supports_collection,
            "priority": self.priority,
            "capabilities": list(self.capabilities),
            "backend_provider": provider_repr,
            "resource_provider": resource_provider_repr,
            "frontend_manifest": (self.frontend_manifest.to_dict() if self.frontend_manifest is not None else None),
            "api_version": self.api_version,
        }


# ---------------------------------------------------------------------------
# Envelope metadata + resources + error
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreviewMetadata:
    """Display + state metadata carried by every envelope (FR-011).

    The six boolean flags are mandatory per the spec: every envelope must
    state whether the displayed data is sampled, truncated, cached, derived,
    complete, or failed. ``extra`` carries previewer-owned shape/type/axis
    metadata (e.g. ``{"shape": [...], "dtype": "..."}``).
    """

    sampled: bool = False
    truncated: bool = False
    cached: bool = False
    derived: bool = False
    complete: bool = True
    failed: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "sampled": self.sampled,
            "truncated": self.truncated,
            "cached": self.cached,
            "derived": self.derived,
            "complete": self.complete,
            "failed": self.failed,
        }
        data.update(self.extra)
        return data


@dataclass(frozen=True)
class PreviewResource:
    """Descriptor for a bounded follow-up resource read (session resources route).

    Attributes:
        resource_id: Opaque id unique within the session.
        kind: Coarse resource shape, e.g. ``tile`` / ``plane`` / ``page`` /
            ``asset`` / ``child``.
        media_type: MIME type of the resource body when it is binary.
        description: Human-readable label.
        params: Provider-defined query parameters needed to fetch it.
    """

    resource_id: str
    kind: str
    media_type: str | None = None
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "kind": self.kind,
            "media_type": self.media_type,
            "description": self.description,
            "params": dict(self.params),
        }


@dataclass(frozen=True)
class PreviewErrorInfo:
    """Typed error payload embedded in a failed envelope (FR-029)."""

    code: PreviewErrorCode
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "detail": dict(self.detail),
        }


@dataclass(frozen=True)
class PreviewEnvelope:
    """Canonical backend preview response (spec Key Entities / FR-011).

    Attributes:
        previewer_id: Selected previewer id.
        target: Normalized :class:`PreviewTarget`.
        kind: Canonical :class:`EnvelopeKind`.
        payload: Previewer-owned bounded payload (JSON-safe).
        session_id: Owning session id, or ``None`` for one-shot compat previews.
        resources: Session resource descriptors for follow-up reads.
        metadata: :class:`PreviewMetadata`.
        diagnostics: Non-fatal warnings / repair hints.
        error: Typed error when the preview failed (kind == ``error``).
        frontend_manifest: Optional same-origin manifest descriptor the host
            mounts for this envelope. Framework-stamped by
            :class:`~scistudio.previewers.session.PreviewSessionManager` from the
            resolved :class:`PreviewerSpec` when a provider does not set its own
            (ADR-048 §4 / #1579); ``None`` for core fallbacks. The wire shape
            omits the backend-only ``asset_root``.
    """

    previewer_id: str
    target: PreviewTarget
    kind: EnvelopeKind
    payload: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    resources: tuple[PreviewResource, ...] = ()
    metadata: PreviewMetadata = field(default_factory=PreviewMetadata)
    diagnostics: tuple[str, ...] = ()
    error: PreviewErrorInfo | None = None
    frontend_manifest: FrontendManifest | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "previewer_id": self.previewer_id,
            "target": self.target.to_dict(),
            "kind": self.kind.value,
            "payload": self.payload,
            "resources": [r.to_dict() for r in self.resources],
            "metadata": self.metadata.to_dict(),
            "diagnostics": list(self.diagnostics),
            "error": self.error.to_dict() if self.error is not None else None,
            "frontend_manifest": (self.frontend_manifest.to_dict() if self.frontend_manifest is not None else None),
        }

    def with_session(self, session_id: str | None) -> PreviewEnvelope:
        """Return a copy bound to *session_id* (envelopes are frozen)."""
        return PreviewEnvelope(
            previewer_id=self.previewer_id,
            target=self.target,
            kind=self.kind,
            payload=self.payload,
            session_id=session_id,
            resources=self.resources,
            metadata=self.metadata,
            diagnostics=self.diagnostics,
            error=self.error,
            frontend_manifest=self.frontend_manifest,
        )


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreviewLimits:
    """Applied bounded-read budgets recorded on a session (spec Key Entities).

    Mirrors the budgets enforced by :class:`PreviewDataAccess`. Surfaced so
    the UI can show "showing 200 of N rows" and prove FR-010 bounds.
    """

    max_rows: int = 200
    max_bytes: int = 8 * 1024 * 1024
    max_items: int = 100
    max_tile: int = 256
    max_dim: int = 256

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PreviewSession:
    """Backend-owned preview session (spec Key Entities / FR-007).

    Attributes:
        session_id: Opaque session identifier.
        previewer_id: Mounted previewer id.
        target: Target reference and type.
        created_at: ISO creation timestamp.
        query: Normalized query state (slice, page, sort, slot, item, ...).
        cache_key: Preview cache key where applicable.
        limits: Applied bounded-read budgets.
    """

    session_id: str
    previewer_id: str
    target: PreviewTarget
    created_at: str
    query: dict[str, Any] = field(default_factory=dict)
    cache_key: str | None = None
    limits: PreviewLimits = field(default_factory=PreviewLimits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "previewer_id": self.previewer_id,
            "target": self.target.to_dict(),
            "created_at": self.created_at,
            "query": dict(self.query),
            "cache_key": self.cache_key,
            "limits": self.limits.to_dict(),
        }


# ---------------------------------------------------------------------------
# Provider request + protocols
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreviewRequest:
    """Input handed to a :data:`PreviewProvider` when it renders an envelope.

    Attributes:
        target: The normalized :class:`PreviewTarget`.
        spec: The selected :class:`PreviewerSpec`.
        query: Normalized query state (slice index, page, page_size, sort_by,
            sort_dir, selected slot, selected item, ...).
        data_access: The bounded :class:`PreviewDataAccess` helper the
            provider must use for all reads (FR-009/FR-010).
        limits: The session budgets.
        session_id: Owning session id, or ``None`` for one-shot previews.
    """

    target: PreviewTarget
    spec: PreviewerSpec
    query: dict[str, Any]
    data_access: PreviewDataAccess
    limits: PreviewLimits
    session_id: str | None = None


# A backend preview provider is any callable mapping a request to an
# envelope. Providers MUST NOT raise for routine failures (e.g. missing
# slot, decode error); they should embed a typed error envelope instead so
# the session API never crashes (FR-028). The session manager still wraps
# provider calls defensively for unexpected exceptions.
PreviewProvider = Callable[[PreviewRequest], PreviewEnvelope]
PreviewResourceProvider = Callable[[PreviewRequest, str, dict[str, Any]], dict[str, Any]]


@runtime_checkable
class PreviewerEntryPoint(Protocol):
    """``scistudio.previewers`` entry-point callable protocol (FR-002).

    A package wires a ``scistudio.previewers`` entry point to a zero-argument
    callable that returns a list of :class:`PreviewerSpec` objects. Each spec
    declares its ``owner_kind=OwnerKind.PACKAGE`` and a resolvable
    ``backend_provider`` (callable or ``module:callable`` import path).

    Example (``pyproject.toml``)::

        [project.entry-points."scistudio.previewers"]
        imaging = "scistudio_blocks_imaging.previewers:get_previewers"

    Where ``get_previewers() -> list[PreviewerSpec]``. The monorepo dev
    fallback (no installed entry point) calls a module-level
    ``get_previewers()`` on each ``packages/scistudio-blocks-*`` package, in
    the same spirit as ``get_blocks`` / ``get_types``.
    """

    def __call__(self) -> list[PreviewerSpec]: ...


# Accepted return shapes from the entry-point callable: a list/tuple of
# specs (canonical) — anything else is rejected with a diagnostic.
PreviewerSpecList = list[PreviewerSpec]


# ---------------------------------------------------------------------------
# Typed error hierarchy
# ---------------------------------------------------------------------------


class PreviewError(Exception):
    """Base class for typed preview errors.

    Each subclass carries a :class:`PreviewErrorCode` so the API/session
    layer can render a deterministic error envelope (FR-029) instead of an
    opaque 500.
    """

    code: PreviewErrorCode = PreviewErrorCode.PROVIDER_EXCEPTION

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}

    def to_error_info(self) -> PreviewErrorInfo:
        return PreviewErrorInfo(code=self.code, message=self.message, detail=self.detail)


class RoutingAmbiguityError(PreviewError):
    """Two previewers tie on tier, specificity, and priority (FR-004)."""

    code = PreviewErrorCode.ROUTING_AMBIGUITY


class UnknownPreviewerError(PreviewError):
    """The requested previewer id is not registered."""

    code = PreviewErrorCode.UNKNOWN_PREVIEWER


class UnknownTargetError(PreviewError):
    """No previewer (not even a core fallback) matched the target."""

    code = PreviewErrorCode.UNKNOWN_TARGET


class MissingBundleError(PreviewError):
    """A previewer declares a frontend manifest but no servable bundle."""

    code = PreviewErrorCode.MISSING_BUNDLE


class ProviderError(PreviewError):
    """A backend provider raised while rendering an envelope."""

    code = PreviewErrorCode.PROVIDER_EXCEPTION


class InvalidSpecError(PreviewError):
    """A previewer spec failed validation at registration time."""

    code = PreviewErrorCode.INVALID_SPEC


class DuplicatePreviewerIdError(PreviewError):
    """Two specs declare the same ``previewer_id`` (FR-006)."""

    code = PreviewErrorCode.DUPLICATE_PREVIEWER_ID


__all__ = [
    "PREVIEWER_API_VERSION",
    "DuplicatePreviewerIdError",
    "EnvelopeKind",
    "FrontendManifest",
    "InvalidSpecError",
    "MissingBundleError",
    "OwnerKind",
    "PreviewEnvelope",
    "PreviewError",
    "PreviewErrorCode",
    "PreviewErrorInfo",
    "PreviewLimits",
    "PreviewMetadata",
    "PreviewProvider",
    "PreviewRequest",
    "PreviewResource",
    "PreviewResourceProvider",
    "PreviewSession",
    "PreviewSource",
    "PreviewTarget",
    "PreviewerEntryPoint",
    "PreviewerSpec",
    "PreviewerSpecList",
    "ProviderError",
    "RoutingAmbiguityError",
    "TargetKind",
    "UnknownPreviewerError",
    "UnknownTargetError",
]
