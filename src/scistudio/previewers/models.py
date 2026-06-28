"""Typed models for the extensible preview subsystem.

A *previewer* turns a stored data object, collection, or artifact into a
bounded, JSON-safe view the frontend can display. This module is one of the
canonical roots you import from when you write a package-owned previewer; the
others are :mod:`scistudio.previewers.data_access` (the bounded reader injected
on each request) and :mod:`scistudio.previewers.helpers` (``sanitize_svg``).
Import the public types from here, not from the package top level.

The whole preview subsystem is **provisional**: usable today, but the surface
may still settle within a minor release. Each public symbol carries a
``scistudio.stability`` marker so the generated reference can show its tier.

Author-facing types:

* :class:`PreviewTarget` — what is being previewed (a data ref, a collection,
  an artifact, or a plot artifact) plus its recorded type chain.
* :class:`PreviewerSpec` — a provider declaration: its id, provenance tier,
  target type, priority, capabilities, backend provider, and frontend manifest.
* :class:`FrontendManifest` — the same-origin descriptor a previewer ships for
  its dynamically-loaded UI module and CSS assets.
* :class:`PreviewRequest` — the input a provider receives: the target, the
  selected spec, the query, the injected
  :class:`~scistudio.previewers.data_access.PreviewDataAccess`, the budgets, and
  the resolved storage reference.
* :class:`PreviewEnvelope` — the backend response: kind, payload, resources,
  metadata, diagnostics, and an optional error.
* :class:`PreviewMetadata` — the display flags every envelope carries (sampled,
  truncated, cached, derived, complete, failed).
* The :data:`PreviewProvider` callable type and the :class:`PreviewerEntryPoint`
  entry-point protocol a package wires up.
* The error types :class:`PreviewError` (the base you catch) and
  :class:`ProviderError` (what you raise for a hard failure).

Backend/runtime-only types (the session record and the routing/registration
error classes) are marked internal and excluded from the generated reference.
They stay importable for the runtime, but a provider signals a routine failure
by returning an envelope whose ``error`` carries a :class:`PreviewErrorCode`,
not by raising one of them.

The models are plain frozen dataclasses (not Pydantic) so this layer stays
import-light and independent of the API layer; the API layer mirrors the same
wire shapes as Pydantic models for serialization.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from scistudio.stability import internal, provisional

if TYPE_CHECKING:
    from scistudio.core.storage.ref import StorageReference
    from scistudio.previewers.data_access import PreviewDataAccess


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


@provisional(since="0.3.1")
class OwnerKind(StrEnum):
    """Where a previewer came from; sets how strongly it wins when routing.

    When more than one previewer could handle a target, provenance decides
    precedence: a project-local previewer beats a package previewer, which beats
    a built-in core fallback. The string values appear verbatim in the REST and
    session API payloads.
    """

    CORE = "core"
    """A built-in fallback that ships with SciStudio."""
    PACKAGE = "package"
    """A previewer registered by an installed package."""
    PROJECT = "project"
    """A previewer registered locally by the active project."""


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
    """The display kind a :class:`PreviewEnvelope` declares for its payload.

    These are the previewer-domain kinds. They are deliberately distinct from
    the older REST ``preview.kind`` strings (``table`` / ``image`` / ``chart`` /
    ``text`` / ``composite`` / ``artifact``); the API runtime maps between the
    two so existing callers and tests keep working.
    """

    DATAFRAME = "dataframe"
    """A tabular payload (rows and columns)."""
    ARRAY = "array"
    """A numeric N-D array plane."""
    SERIES = "series"
    """A 1-D series of values for a line/point chart."""
    TEXT = "text"
    """A bounded chunk of text."""
    ARTIFACT = "artifact"
    """Metadata (and optionally an inline data URI) for an opaque file."""
    COMPOSITE = "composite"
    """A multi-slot composite payload."""
    COLLECTION = "collection"
    """A bounded sample of a collection's items."""
    PLOT = "plot"
    """A rendered plot (image or SVG)."""
    ERROR = "error"
    """A failed preview; the envelope's ``error`` field explains why."""


@provisional(since="0.3.1")
class PreviewErrorCode(StrEnum):
    """Stable, machine-readable codes describing why a preview failed.

    A failed envelope carries one of these on its ``error`` field so the
    frontend can react consistently instead of parsing a free-text message.
    """

    ROUTING_AMBIGUITY = "routing_ambiguity"
    """Two previewers tied for the target and neither could be preferred."""
    UNKNOWN_PREVIEWER = "unknown_previewer"
    """The requested previewer id is not registered."""
    UNKNOWN_TARGET = "unknown_target"
    """No previewer (not even a core fallback) matched the target."""
    MISSING_BUNDLE = "missing_bundle"
    """A previewer declares a frontend manifest but no servable bundle."""
    PROVIDER_EXCEPTION = "provider_exception"
    """A backend provider raised while rendering the preview."""
    INVALID_SPEC = "invalid_spec"
    """A previewer spec failed validation when it was registered."""
    DUPLICATE_PREVIEWER_ID = "duplicate_previewer_id"
    """Two specs declared the same previewer id."""
    BUDGET_EXCEEDED = "budget_exceeded"
    """A read would exceed a bounded preview budget (rows/bytes/items/...)."""


# A bare ``str`` cannot carry a ``scistudio.stability`` marker (it is an
# immutable builtin), so the provisional tier is recorded in the spec and this
# constant renders in the reference without a tier badge.
PREVIEWER_API_VERSION = "1"
"""Current previewer API compatibility version.

A :class:`PreviewerSpec` or :class:`FrontendManifest` that declares a different
``api_version`` is still loaded, but the mismatch is flagged through diagnostics
so the frontend can refuse to mount an incompatible manifest.
"""


# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PreviewSource:
    """Optional workflow/node/output identity shown alongside a preview.

    This is display metadata only — it lets the preview panel label a preview as
    "node X, output port Y" without making the previewer part of the workflow.
    It carries no runtime truth and never drives data reads.

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
    """Identifies the thing a previewer is asked to render.

    A target names *what* to preview (a data object, a collection, an artifact,
    or a plot) and records its type information so the router can pick the best
    previewer. You build a target to ask the preview system for a preview, and a
    provider receives the normalized target on its request.

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
    parent type's previewer."""
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
# Frontend manifest
# ---------------------------------------------------------------------------


@provisional(since="0.3.1")
@dataclass(frozen=True)
class FrontendManifest:
    """Describes the same-origin UI bundle a previewer ships for the frontend.

    A package or project previewer can include a small JavaScript module (and
    optional CSS) that the frontend loads at runtime to render a custom view.
    This descriptor tells the frontend what to import; the backend validates it
    and confines every asset read under ``asset_root`` before serving anything,
    and it refuses remote (http/https) URLs.

    Example:
        >>> manifest = FrontendManifest(
        ...     previewer_id="acme.image.viewer",
        ...     module_url="/api/previews/assets/abc123",
        ...     export_name="ImageViewer",
        ... )
        >>> "asset_root" in manifest.to_dict()
        False
    """

    previewer_id: str
    """Stable id of the previewer that owns this bundle."""
    module_url: str
    """Backend-relative URL the frontend imports the module from, e.g.
    ``/api/previews/assets/<asset_id>``. Remote URLs are rejected."""
    export_name: str = "default"
    """Name of the export inside the module to mount."""
    css: tuple[str, ...] = ()
    """Optional backend-relative CSS asset URLs to load with the module."""
    version: str = "0"
    """Bundle version (a fingerprint or semantic version)."""
    api_version: str = PREVIEWER_API_VERSION
    """Previewer API version the bundle targets; must equal
    :data:`PREVIEWER_API_VERSION` to mount without a diagnostic."""
    asset_root: str | None = None
    """Filesystem directory the assets are confined under. Used only by the
    backend asset validator and never sent to the frontend."""

    def to_dict(self) -> dict[str, Any]:
        """Return the wire-shape dict sent to the frontend (``asset_root`` is omitted)."""
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


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PreviewerSpec:
    """Declares one preview provider and how the router should choose it.

    A package's entry-point callable returns a list of these. Each spec says
    which target type the previewer handles, how strongly it should win, what
    features it offers, and which backend callable renders the envelope. You
    construct specs to register a previewer; the router and session manager read
    them.

    Example:
        >>> spec = PreviewerSpec(
        ...     previewer_id="acme.image.viewer",
        ...     owner_kind=OwnerKind.PACKAGE,
        ...     owner_name="acme",
        ...     target_type="Image",
        ...     capabilities=("slice", "lut"),
        ...     backend_provider="acme.previewers:render_image",
        ... )
        >>> spec.target_type
        'Image'
    """

    previewer_id: str
    """Stable, unique id, e.g. ``"core.array.basic"``."""
    owner_kind: OwnerKind
    """Provenance tier (core / package / project) that sets routing precedence."""
    owner_name: str
    """Owning package name, project identifier, or ``"scistudio"``."""
    target_type: str
    """Fully qualified type name this previewer claims, e.g. ``"Array"`` or
    ``"Image"``."""
    supports_collection: bool = False
    """Whether the previewer can inspect collections (claims
    ``Collection[target_type]``)."""
    priority: int = 0
    """Tie-break weight within one tier and type specificity; higher wins. An
    unresolved equal-priority tie is a routing error."""
    capabilities: tuple[str, ...] = ()
    """Feature strings the previewer advertises, e.g. ``slice``, ``table``,
    ``lut``, ``export``."""
    backend_provider: PreviewProvider | str | None = None
    """The render callable, or a dotted ``module:callable`` import path resolved
    lazily."""
    resource_provider: PreviewResourceProvider | str | None = None
    """Optional follow-up resource reader for custom resource ids the envelope
    declares."""
    frontend_manifest: FrontendManifest | None = None
    """Optional same-origin UI bundle descriptor."""
    api_version: str = PREVIEWER_API_VERSION
    """Previewer API version this spec targets."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict of the spec (providers shown by name)."""
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


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PreviewMetadata:
    """Display and state flags carried by every preview envelope.

    These six booleans tell the frontend exactly how trustworthy and complete
    the shown data is — for example whether it was sampled or truncated to stay
    within budget. Every envelope sets them so the UI can be honest about what
    the user is looking at. ``extra`` carries previewer-owned shape/type details.

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
    """Previewer-owned extra metadata merged into the wire payload, e.g.
    ``{"shape": [...], "dtype": "..."}``."""

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
class PreviewResource:
    """Describes a bounded follow-up read a preview offers (a session resource).

    An envelope can advertise extra reads the frontend may request on demand — an
    array tile, an image plane, a document page, or a child preview — without
    sending all of that data up front. Each one is described by a resource and
    fetched on demand through the session's resources route.

    Example:
        >>> res = PreviewResource(resource_id="tile", kind="tile",
        ...                       params={"y0": 0, "x0": 0})
        >>> res.kind
        'tile'
    """

    resource_id: str
    """Id unique within the session, used to request this resource."""
    kind: str
    """Coarse shape of the resource, e.g. ``tile`` / ``plane`` / ``page`` /
    ``asset`` / ``child``."""
    media_type: str | None = None
    """MIME type of the resource body when it is binary; ``None`` otherwise."""
    description: str = ""
    """Human-readable label for the resource."""
    params: dict[str, Any] = field(default_factory=dict)
    """Provider-defined query parameters needed to fetch the resource."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict of the resource descriptor."""
        return {
            "resource_id": self.resource_id,
            "kind": self.kind,
            "media_type": self.media_type,
            "description": self.description,
            "params": dict(self.params),
        }


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
    """The backend's complete response describing one preview.

    A provider returns an envelope; the session layer and REST API serialize it
    to the frontend. It carries the bounded payload, the metadata flags, any
    follow-up resources, non-fatal diagnostics, and — when the preview failed —
    a typed error. Build it with the previewer id, the target, an
    :class:`EnvelopeKind`, and a JSON-safe ``payload``.

    Example:
        >>> env = PreviewEnvelope(
        ...     previewer_id="core.text.basic",
        ...     target=PreviewTarget(kind=TargetKind.DATA_REF, ref="r1"),
        ...     kind=EnvelopeKind.TEXT,
        ...     payload={"content": "hello"},
        ... )
        >>> env.kind.value
        'text'
    """

    previewer_id: str
    """Id of the previewer that produced this envelope."""
    target: PreviewTarget
    """The normalized target that was previewed."""
    kind: EnvelopeKind
    """The display kind of ``payload``."""
    payload: dict[str, Any] = field(default_factory=dict)
    """Previewer-owned, bounded, JSON-safe payload for the frontend."""
    session_id: str | None = None
    """Owning session id, or ``None`` for a one-shot preview."""
    resources: tuple[PreviewResource, ...] = ()
    """Follow-up resources the frontend may fetch on demand."""
    metadata: PreviewMetadata = field(default_factory=PreviewMetadata)
    """Display and state flags for ``payload``."""
    diagnostics: tuple[str, ...] = ()
    """Non-fatal warnings or repair hints."""
    error: PreviewErrorInfo | None = None
    """Set when the preview failed (``kind`` is ``error``); ``None`` otherwise."""
    frontend_manifest: FrontendManifest | None = None
    """Optional UI bundle to mount for this envelope. If the provider does not
    set one, the session manager stamps the resolved spec's manifest; ``None``
    for core fallbacks. The wire shape omits the backend-only ``asset_root``."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict of the whole envelope for the API/wire."""
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
        """Return a copy bound to *session_id*.

        Envelopes are frozen, so this builds a new envelope with every field
        copied and ``session_id`` replaced.

        Args:
            session_id: Session id to stamp, or ``None`` for a one-shot preview.

        Returns:
            A new :class:`PreviewEnvelope` identical except for ``session_id``.
        """
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


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PreviewLimits:
    """The bounded-read budgets applied to a preview session.

    These mirror the limits the bounded reader enforces, and they are surfaced
    on the session so the UI can be honest about bounds — e.g. show
    "showing 200 of N rows". Read them from ``request.limits`` inside a provider.

    Example:
        >>> limits = PreviewLimits()
        >>> limits.max_rows
        200
    """

    max_rows: int = 200
    """Maximum table rows returned in one page."""
    max_bytes: int = 8 * 1024 * 1024
    """Maximum payload size in bytes (default 8 MiB)."""
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


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PreviewRequest:
    """Everything a provider receives when it is asked to render a preview.

    The session manager builds this and passes it to your provider callable.
    Read the target, query, and budgets; do all reads through ``data_access``
    using the supplied ``storage`` reference; and return a
    :class:`PreviewEnvelope`.

    Example:
        >>> def render(request: PreviewRequest) -> PreviewEnvelope:
        ...     page = request.data_access.dataframe_page(request.storage)
        ...     return PreviewEnvelope(
        ...         previewer_id=request.spec.previewer_id,
        ...         target=request.target,
        ...         kind=EnvelopeKind.DATAFRAME,
        ...         payload={"rows": page.rows},
        ...     )
    """

    target: PreviewTarget
    """The normalized target being previewed."""
    spec: PreviewerSpec
    """The previewer spec the router selected."""
    query: dict[str, Any]
    """Normalized query state (slice index, page, page_size, sort_by, sort_dir,
    selected slot, selected item, ...)."""
    data_access: PreviewDataAccess
    """The bounded reader to use for all payload reads — never read storage
    directly."""
    limits: PreviewLimits
    """The session's applied read budgets."""
    session_id: str | None = None
    """Owning session id, or ``None`` for a one-shot preview."""
    storage: StorageReference | None = None
    """The resolved storage reference for the target's payload. This is the
    sanctioned way to get a storage ref: read ``request.storage`` and pass it to
    ``request.data_access`` methods — never import or rebuild a storage reference
    yourself. ``None`` only when a request is built outside the session manager
    without one."""
    record_metadata: dict[str, Any] = field(default_factory=dict)
    """The recorded data-record metadata, populated by the session manager."""

    # The ``query["_storage"]`` / ``query["_record_metadata"]`` keys remain a
    # runtime serialization detail (session cache-key versioning and resource
    # reads); they are not part of the author contract — use ``storage`` and
    # ``record_metadata`` above instead.


# A ``collections.abc.Callable`` subscription is a generic-alias with no writable
# ``__dict__`` (like the ``list[...]`` alias and the ``str`` constant), so it
# cannot carry a ``scistudio.stability`` marker and renders in the reference
# without a tier badge; the provisional tier is recorded in the spec.
PreviewProvider = Callable[[PreviewRequest], PreviewEnvelope]
"""A backend preview provider: a callable mapping a :class:`PreviewRequest` to a
:class:`PreviewEnvelope`.

Implement one of these to render a preview. It must not raise for routine
failures (a missing slot, a decode error); instead return an envelope whose
``error`` carries a :class:`PreviewErrorCode`, so the session API never crashes.
The session manager still guards against unexpected exceptions.
"""
PreviewResourceProvider = Callable[[PreviewRequest, str, dict[str, Any]], dict[str, Any]]
"""A follow-up resource reader: a callable taking ``(request, resource_id,
params)`` and returning a JSON-safe dict for one bounded resource read."""


@provisional(since="0.3.1")
@runtime_checkable
class PreviewerEntryPoint(Protocol):
    """The callable a package wires to the ``scistudio.previewers`` entry point.

    A package advertises its previewers by pointing a ``scistudio.previewers``
    entry point at a zero-argument callable that returns a list of
    :class:`PreviewerSpec`. Each returned spec declares
    ``owner_kind=OwnerKind.PACKAGE`` and a resolvable ``backend_provider``
    (a callable or a ``module:callable`` import path).

    Example:
        In ``pyproject.toml``::

            [project.entry-points."scistudio.previewers"]
            imaging = "scistudio_blocks_imaging.previewers:get_previewers"

        where ``get_previewers() -> list[PreviewerSpec]``. An installed
        block/type package may instead re-export a module-level
        ``get_previewers()`` that the registry discovers as a companion factory,
        in the same spirit as ``get_blocks`` / ``get_types``.
    """

    def __call__(self) -> list[PreviewerSpec]: ...


# A PEP 585 ``list[...]`` alias is a ``types.GenericAlias`` with no writable
# ``__dict__``, so it cannot carry a ``scistudio.stability`` marker and renders
# without a tier badge; the provisional tier is recorded in the spec.
PreviewerSpecList = list[PreviewerSpec]
"""The accepted return type of a previewer entry-point callable: a list of
:class:`PreviewerSpec`. Any other shape is rejected with a diagnostic."""


# ---------------------------------------------------------------------------
# Typed error hierarchy
# ---------------------------------------------------------------------------


@provisional(since="0.3.1")
class PreviewError(Exception):
    """Base class for typed preview errors — catch this in a provider.

    Each subclass carries a :class:`PreviewErrorCode` so the session/API layer
    can render a deterministic error envelope instead of an opaque 500. Catch
    :class:`PreviewError` to handle any preview-layer failure uniformly.

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
    """Two previewers tie on tier, specificity, and priority (FR-004).

    Runtime-raised by the router; an author signals routing problems through a
    :class:`PreviewErrorCode` on a returned envelope rather than importing this
    type (ADR-052 §8.1 — Internal).
    """

    code = PreviewErrorCode.ROUTING_AMBIGUITY


@internal()
class UnknownPreviewerError(PreviewError):
    """The requested previewer id is not registered (runtime-raised; ADR-052 §8.1 Internal)."""

    code = PreviewErrorCode.UNKNOWN_PREVIEWER


@internal()
class UnknownTargetError(PreviewError):
    """No previewer (not even a core fallback) matched the target (runtime-raised; ADR-052 §8.1 Internal)."""

    code = PreviewErrorCode.UNKNOWN_TARGET


@internal()
class MissingBundleError(PreviewError):
    """A previewer declares a frontend manifest but no servable bundle (runtime-raised; ADR-052 §8.1 Internal)."""

    code = PreviewErrorCode.MISSING_BUNDLE


@provisional(since="0.3.1")
class ProviderError(PreviewError):
    """Raise this from a provider for a hard failure it cannot recover from.

    Use it when a provider genuinely cannot produce a payload and cannot turn
    the situation into a typed error envelope itself; the session layer catches
    it and renders a ``provider_exception`` error envelope.
    """

    code = PreviewErrorCode.PROVIDER_EXCEPTION
    """Failure code reported for a provider hard failure."""


@internal()
class InvalidSpecError(PreviewError):
    """A previewer spec failed validation at registration time (runtime-raised; ADR-052 §8.1 Internal)."""

    code = PreviewErrorCode.INVALID_SPEC


@internal()
class DuplicatePreviewerIdError(PreviewError):
    """Two specs declare the same ``previewer_id`` (FR-006; runtime-raised; ADR-052 §8.1 Internal)."""

    code = PreviewErrorCode.DUPLICATE_PREVIEWER_ID


# Public author surface for ``scistudio.previewers.models`` (ADR-052 §8.1).
# The whole preview subsystem is provisional. The seven runtime-only / backend
# types — ``PreviewSession`` and the six runtime-raised error classes
# (``RoutingAmbiguityError``, ``UnknownPreviewerError``, ``UnknownTargetError``,
# ``MissingBundleError``, ``InvalidSpecError``, ``DuplicatePreviewerIdError``) —
# are Internal (decorated ``@internal``) and intentionally excluded; they stay
# importable for the runtime/API layer but carry no author stability promise.
__all__ = [
    "PREVIEWER_API_VERSION",
    "EnvelopeKind",
    "FrontendManifest",
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
    "PreviewSource",
    "PreviewTarget",
    "PreviewerEntryPoint",
    "PreviewerSpec",
    "PreviewerSpecList",
    "ProviderError",
    "TargetKind",
]
