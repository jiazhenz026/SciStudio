"""Typed models for routing a preview target to a panel and holding its session.

A preview names *what* is shown (a :class:`PreviewTarget`), the panel the
routing ladder picked for it (a :class:`PreviewerSpec` routing candidate), and
the session handle the host mounts (a :class:`PreviewEnvelope` of kind
``panel``, or of kind ``error`` when routing or reading failed).

:class:`OwnerKind` is public through :mod:`scistudio.panels`, because
:class:`~scistudio.panels.PanelDescriptor` records the tier a panel was
discovered under. The other types here are the panel runtime's own models.

The models are plain frozen dataclasses (not Pydantic) so this layer stays
import-light and independent of the API layer; the API layer mirrors the same
wire shapes as Pydantic models for serialization.
"""
# Maintainer context (kept outside generated API documentation):
# Relocated from the removed ``scistudio.previewers.models`` root (#2493,
# ADR-054 §8). Only the pieces the panel runtime uses were kept: the
# provider/entry-point contract, the frontend manifest, the follow-up resource
# descriptors and the registration errors went with the legacy previewers.
# Development references: ADR-048, ADR-052, ADR-054, #2493.

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from scistudio.stability import internal, provisional

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


@provisional(since="0.3.5")
class OwnerKind(StrEnum):
    """Where a panel came from; sets how strongly it wins when routing.

    When more than one panel could handle a target, provenance decides
    precedence: a project panel beats a user-library panel, which beats a
    package panel, which beats a built-in core panel. The string values appear
    verbatim in the REST and session API payloads.
    """

    CORE = "core"
    """A built-in panel that ships with SciStudio."""
    PACKAGE = "package"
    """A panel registered by an installed package."""
    USER = "user"
    """A panel in the user library (``~/.scistudio/panels``)."""
    PROJECT = "project"
    """A panel in the active project's ``panels/`` folder."""


@provisional(since="0.3.1")
class TargetKind(StrEnum):
    """The kind of thing a :class:`PreviewTarget` points at."""

    DATA_REF = "data_ref"
    """A single stored data object (e.g. a table, array, or series)."""
    COLLECTION_REF = "collection_ref"
    """A collection of items of one item type."""
    ARTIFACT = "artifact"
    """An opaque file artifact (image, document, ...)."""
    PLOT_ARTIFACT = "plot_artifact"
    """A rendered plot artifact (PNG/JPEG/SVG/PDF)."""


@provisional(since="0.3.1")
class EnvelopeKind(StrEnum):
    """The kind of a :class:`PreviewEnvelope`."""

    PANEL = "panel"
    """A sandboxed HTML panel selected by the routing ladder."""
    ERROR = "error"
    """A failed preview; the envelope's ``error`` field explains why."""


@provisional(since="0.3.1")
class PreviewErrorCode(StrEnum):
    """Stable, machine-readable codes describing why a preview failed.

    A failed envelope carries one of these on its ``error`` field so the
    frontend can react consistently instead of parsing a free-text message.
    """

    ROUTING_AMBIGUITY = "routing_ambiguity"
    """Two panels tied for the target and no choice of the person broke the tie."""
    UNKNOWN_PREVIEWER = "unknown_previewer"
    """The requested panel id is not registered, or does not serve the target."""
    UNKNOWN_TARGET = "unknown_target"
    """No panel (not even a core panel) matched the target."""
    PROVIDER_EXCEPTION = "provider_exception"
    """Reading the preview's data failed."""
    BUDGET_EXCEEDED = "budget_exceeded"
    """A read would exceed a bounded preview budget (rows/bytes/items/...)."""


# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PreviewSource:
    """Optional workflow/node/output identity shown alongside a preview.

    This is display metadata only — it lets the preview panel label a preview as
    "node X, output port Y" without making the panel part of the workflow. It
    carries no runtime truth and never drives data reads.

    Example:
        >>> source = PreviewSource(workflow_id="wf1", node_id="n3", output_port="out")
        >>> source.to_dict()["node_id"]
        'n3'
    """

    workflow_id: str | None = None
    """Id of the workflow the previewed output belongs to, if known."""
    node_id: str | None = None
    """Id of the node that produced the output, if known."""
    output_port: str | None = None
    """Name of the node output port the value came from, if known."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict of all three identity fields."""
        return asdict(self)


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PreviewTarget:
    """Identifies the thing a preview is asked to show.

    A target names *what* to preview (a data object, a collection, an artifact,
    or a plot) and records its type information so the router can pick the best
    panel.

    Example:
        >>> target = PreviewTarget(
        ...     kind=TargetKind.DATA_REF,
        ...     ref="catalog://run1/image0",
        ...     recorded_type="Image",
        ...     type_chain=("DataObject", "Array", "Image"),
        ... )
        >>> target.is_collection
        False
    """

    kind: TargetKind
    """Which category of thing ``ref`` points at."""
    ref: str
    """The data, collection, or artifact reference (a catalog id or path)."""
    recorded_type: str = ""
    """Most specific recorded type name from storage metadata (e.g. ``"Image"``);
    empty when unknown."""
    type_chain: tuple[str, ...] = ()
    """Recorded type names ordered general -> specific, e.g.
    ``("DataObject", "Array", "Image")``. The router walks this to fall back to a
    parent type's panel."""
    collection_item_type: str | None = None
    """Item type name when ``kind`` is ``collection_ref``; ``None`` otherwise."""
    source: PreviewSource | None = None
    """Optional workflow/node/output identity, for display only."""

    @property
    def is_collection(self) -> bool:
        """Whether this target points at a collection (``kind`` is ``collection_ref``)."""
        return self.kind is TargetKind.COLLECTION_REF

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict of the target for the API/wire payload."""
        return {
            "kind": self.kind.value,
            "ref": self.ref,
            "recorded_type": self.recorded_type,
            "type_chain": list(self.type_chain),
            "collection_item_type": self.collection_item_type,
            "source": self.source.to_dict() if self.source is not None else None,
        }


# ---------------------------------------------------------------------------
# Routing candidate
# ---------------------------------------------------------------------------


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PreviewerSpec:
    """One routing candidate: a panel's claim on one preview type.

    A panel that opens in the ``preview`` context contributes one candidate per
    type it claims (``PanelDescriptor.candidates``). The routing ladder reads the
    tier, the claimed type, whether the claim is a collection claim, and the
    priority.

    Example:
        >>> spec = PreviewerSpec(
        ...     previewer_id="acme.image.viewer",
        ...     owner_kind=OwnerKind.PACKAGE,
        ...     owner_name="acme",
        ...     target_type="Image",
        ... )
        >>> spec.target_type
        'Image'
    """

    previewer_id: str
    """Stable, unique panel id, e.g. ``"core.array.basic"``."""
    owner_kind: OwnerKind
    """Provenance tier (core / package / user / project) that sets routing precedence."""
    owner_name: str
    """Owning package name, project identifier, or ``"scistudio"``."""
    target_type: str
    """Type name this candidate claims, e.g. ``"Array"`` or ``"Image"``."""
    supports_collection: bool = False
    """Whether the candidate claims ``Collection[target_type]``."""
    priority: int = 0
    """Tie-break weight within one tier and type specificity; higher wins. An
    equal-priority tie the person has not resolved with a choice is a routing
    error."""
    capabilities: tuple[str, ...] = ()
    """Feature strings the candidate advertises."""
    api_version: str = "1.0"
    """The panel descriptor ``api_version`` of the candidate."""
    panel: dict[str, Any] | None = None
    """The public descriptor of the panel this candidate routes to."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict of the candidate."""
        return {
            "previewer_id": self.previewer_id,
            "owner_kind": self.owner_kind.value,
            "owner_name": self.owner_name,
            "target_type": self.target_type,
            "supports_collection": self.supports_collection,
            "priority": self.priority,
            "capabilities": list(self.capabilities),
            "panel": self.panel,
            "api_version": self.api_version,
        }


# ---------------------------------------------------------------------------
# Envelope metadata + error
# ---------------------------------------------------------------------------


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PreviewMetadata:
    """Display and state flags carried by every preview envelope.

    Example:
        >>> meta = PreviewMetadata(truncated=True, extra={"shape": [1000, 3]})
        >>> meta.to_dict()["truncated"]
        True
    """

    sampled: bool = False
    """True when only a sample of the data was read, not all of it."""
    truncated: bool = False
    """True when the payload was cut to fit a row/byte/item budget."""
    cached: bool = False
    """True when the payload was served from a preview cache."""
    derived: bool = False
    """True when the shown values were computed/transformed, not raw."""
    complete: bool = True
    """True when the payload represents the whole target."""
    failed: bool = False
    """True when the preview failed; pair with an ``error`` on the envelope."""
    extra: dict[str, Any] = field(default_factory=dict)
    """Extra metadata merged into the wire payload."""

    def to_dict(self) -> dict[str, Any]:
        """Return the flags plus ``extra`` flattened into one JSON-safe dict."""
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


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PreviewErrorInfo:
    """The typed error payload embedded in a failed envelope.

    When a preview fails, the envelope's ``kind`` is ``error`` and this object
    explains why: a stable :class:`PreviewErrorCode`, a human message, and
    optional structured detail.
    """

    code: PreviewErrorCode
    """The machine-readable failure code."""
    message: str
    """Human-readable explanation of the failure."""
    detail: dict[str, Any] = field(default_factory=dict)
    """Optional structured context (ids, types, sizes, ...)."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict of the error payload."""
        return {
            "code": self.code.value,
            "message": self.message,
            "detail": dict(self.detail),
        }


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PreviewEnvelope:
    """The backend's response describing one preview session.

    A ``panel`` envelope names the panel to mount (``panel``) and the session it
    reads through; an ``error`` envelope carries a typed :class:`PreviewErrorInfo`.

    Example:
        >>> env = PreviewEnvelope(
        ...     previewer_id="core.text.basic",
        ...     target=PreviewTarget(kind=TargetKind.DATA_REF, ref="r1"),
        ...     kind=EnvelopeKind.PANEL,
        ... )
        >>> env.kind.value
        'panel'
    """

    previewer_id: str
    """Id of the panel the envelope routes to."""
    target: PreviewTarget
    """The normalized target that was previewed."""
    kind: EnvelopeKind
    """``panel``, or ``error`` when the preview failed."""
    payload: dict[str, Any] = field(default_factory=dict)
    """Bounded, JSON-safe payload for the host."""
    session_id: str | None = None
    """Owning session id, or ``None`` when no session was opened."""
    metadata: PreviewMetadata = field(default_factory=PreviewMetadata)
    """Display and state flags for ``payload``."""
    diagnostics: tuple[str, ...] = ()
    """Non-fatal warnings or repair hints."""
    error: PreviewErrorInfo | None = None
    """Set when the preview failed (``kind`` is ``error``); ``None`` otherwise."""
    panel: dict[str, Any] | None = None
    """Resolved panel identity for the sandbox host."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict of the whole envelope for the API/wire."""
        return {
            "panel": self.panel,
            "session_id": self.session_id,
            "previewer_id": self.previewer_id,
            "target": self.target.to_dict(),
            "kind": self.kind.value,
            "payload": self.payload,
            "metadata": self.metadata.to_dict(),
            "diagnostics": list(self.diagnostics),
            "error": self.error.to_dict() if self.error is not None else None,
        }


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PreviewLimits:
    """The bounded-read budgets applied to a preview session.

    Example:
        >>> limits = PreviewLimits()
        >>> limits.max_rows
        200
    """

    max_rows: int = 200
    """Maximum table rows returned in one page."""
    max_bytes: int = 20 * 1024 * 1024
    """Maximum payload size in bytes (default 20 MiB)."""
    max_items: int = 100
    """Maximum collection items sampled at once."""
    max_tile: int = 256
    """Maximum width/height in pixels of an array tile read."""
    max_dim: int = 256
    """Maximum width/height a displayed array plane is downsampled to."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict of the budgets."""
        return asdict(self)


@internal()
@dataclass
class PreviewSession:
    """Backend-owned preview session.

    Attributes:
        session_id: Opaque session identifier.
        previewer_id: Mounted panel id.
        target: Target reference and type.
        created_at: ISO creation timestamp.
        query: Normalized query state (slice, page, sort, slot, item, ...).
        cache_key: Preview cache key where applicable.
        limits: Applied bounded-read budgets.
    """

    # Development references: FR-007.

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
# Typed error hierarchy
# ---------------------------------------------------------------------------


@provisional(since="0.3.1")
class PreviewError(Exception):
    """Base class for typed preview errors.

    Each subclass carries a :class:`PreviewErrorCode` so the session/API layer
    can render a deterministic error envelope instead of an opaque 500.

    Args:
        message: Human-readable description of the failure.
        detail: Optional structured context attached to the error envelope.
    """

    code: PreviewErrorCode = PreviewErrorCode.PROVIDER_EXCEPTION
    """The failure code reported on the error envelope for this error type."""

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}

    def to_error_info(self) -> PreviewErrorInfo:
        """Convert this error into a :class:`PreviewErrorInfo` for an envelope."""
        return PreviewErrorInfo(code=self.code, message=self.message, detail=self.detail)


@internal()
class RoutingAmbiguityError(PreviewError):
    """Two panels tie on tier, specificity, and priority, and no choice breaks the tie."""

    # Development references: ADR-052, FR-004.

    code = PreviewErrorCode.ROUTING_AMBIGUITY


@internal()
class UnknownPreviewerError(PreviewError):
    """The requested panel id is not registered or does not serve the target."""

    # Development references: ADR-052.

    code = PreviewErrorCode.UNKNOWN_PREVIEWER


@internal()
class UnknownTargetError(PreviewError):
    """No panel (not even a core panel) matched the target."""

    # Development references: ADR-052.

    code = PreviewErrorCode.UNKNOWN_TARGET


@provisional(since="0.3.1")
class ProviderError(PreviewError):
    """A preview read failed and cannot be turned into a result."""

    code = PreviewErrorCode.PROVIDER_EXCEPTION
    """Failure code reported for a read failure."""


__all__ = [
    "EnvelopeKind",
    "OwnerKind",
    "PreviewEnvelope",
    "PreviewError",
    "PreviewErrorCode",
    "PreviewErrorInfo",
    "PreviewLimits",
    "PreviewMetadata",
    "PreviewSession",
    "PreviewSource",
    "PreviewTarget",
    "PreviewerSpec",
    "ProviderError",
    "RoutingAmbiguityError",
    "TargetKind",
    "UnknownPreviewerError",
    "UnknownTargetError",
]
