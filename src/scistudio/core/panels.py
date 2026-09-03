"""The shared panel contract: one manifest, two capabilities, four tiers.

ADR-054 §3.3 and §9.2; ``docs/specs/adr-054-panel-contract.md`` FR-001 to
FR-006, FR-018, FR-019 and FR-047 to FR-050. Manager decision D-007 fixes the
on-disk form and D-009 fixes this module's membership.

**Why the contract lives in ``core``.** Its consumers span three layers and no
layer above ``core`` may be imported by the others (FR-001). The block layer
declares a manifest on a block class
(:mod:`scistudio.blocks.base.interactive`), the panel subsystem validates and
serves manifests from above it (:mod:`scistudio.panels`), and the API layer
routes them from above that. SciStudio has answered this question once already:
:mod:`scistudio.core.origins` records that it sits in ``core`` because its
consumers span layers, and it is why the drop-in tier roots live in
:mod:`scistudio.core.dropins` rather than inside the block or type registries.
Leaving the shared type inside the panel subsystem would force the block layer
to import upward, and the pressure to relieve that produces a second manifest
type in the block layer — the duplication ADR-054 exists to remove.

**One API version constant.** :data:`PANEL_API_VERSION` is defined here and
nowhere else (FR-004, SC-001, D-010). ``scistudio.panels.models`` and
``scistudio.blocks.base.interactive`` re-export this object; the frontend host
defines none of its own and reads the accepted version off the descriptor the
backend sends it.

**What a panel is on disk.** A directory holding a ``panel.json`` declaration
and a single self-contained entry document, ``index.html`` by default (FR-002,
D-007). :func:`manifest_from_declaration` is the one parser, and it refuses a
declaration missing a required field with a diagnostic naming the directory and
the field (FR-003). The reading of the directory itself, and the four-tier
discovery that shadows one declaration with another, belong to
:mod:`scistudio.panels.discovery` — this module owns the shape, not the search.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from scistudio.stability import provisional

# A bare ``str`` cannot carry a ``scistudio.stability`` marker (it is an
# immutable builtin), so the provisional tier is recorded in the ADR-052
# expected surface and this constant renders in the reference without a tier
# badge — the same treatment ``scistudio.panels.models`` already gives it.
PANEL_API_VERSION = "1"
"""The one panel API compatibility version (FR-004, SC-001, D-010).

The host accepts a panel whose declaration states this version and refuses one
that states any other, before the panel is mounted. It is defined here and
re-exported by :mod:`scistudio.panels.models` and
:mod:`scistudio.blocks.base.interactive`; a second definition anywhere in the
tree — the frontend included — is a defect against SC-001.
"""

#: The declaration file a panel directory must contain (FR-002, D-007).
PANEL_DECLARATION_FILENAME = "panel.json"

#: The entry document a declaration names when it names none of its own.
DEFAULT_PANEL_ENTRY = "index.html"


@provisional(since="0.3.4")
class PanelCapability(StrEnum):
    """What a panel may do, declared statically before it loads (FR-005/FR-006).

    Exactly two members, and the set is closed. Which outbound message types the
    host grants a mounted panel follows from this and from nothing the panel
    says at runtime: there is no negotiation by which a mounted panel acquires a
    capability it did not declare.

    The string values appear verbatim in the panel descriptor and in the
    ``init`` message the frontend host reads.
    """

    DISPLAYING = "displaying"
    """Renders what it is given and has no outbound path.

    What SciStudio calls a previewer today is exactly this: a panel resolved by
    the type of the data, declaring only the displaying capability.
    """

    PRODUCING = "producing"
    """Renders what it is given and can hand a value back (FR-012)."""

    def satisfies(self, required: PanelCapability) -> bool:
        """Return whether a panel with this capability can serve *required*.

        FR-006: a producing panel is also mountable for display, so producing
        satisfies a displaying request. The converse does not hold — a
        displaying panel mounted in a producing position would need an outbound
        path it never claimed — which is what makes the filter in FR-048
        asymmetric rather than an equality test.
        """
        if self is PanelCapability.PRODUCING:
            return True
        return required is PanelCapability.DISPLAYING


@provisional(since="0.3.1")
class PanelTier(StrEnum):
    """Where a panel was discovered, and how strongly it shadows (FR-018/FR-019).

    Four tiers, and the string values appear verbatim in the REST and session
    payloads. A panel in a lower tier shadows a panel of the same id in a higher
    one, in the order project, user library, package, core — which is the
    mechanism the editing story depends on: copying a read-only core panel into
    the project is what makes the copy take effect (FR-026, FR-027).

    This is the same four-valued provenance the ADR-048 preview subsystem calls
    ``OwnerKind``; that name is an alias of this enum rather than a second
    definition of it (``scistudio.panels.models``).
    """

    CORE = "core"
    """A built-in panel shipped with the application, on disk under the panel
    subsystem (A-003, D-015)."""
    PACKAGE = "package"
    """A panel an installed package registers through the ``scistudio.panels``
    entry-point group (FR-045)."""
    USER = "user"
    """A panel the user library contains as a directory (FR-046)."""
    PROJECT = "project"
    """A panel the open project contains as a directory (FR-046)."""

    @property
    def shadow_rank(self) -> int:
        """Position in the FR-019 shadowing order; lower shadows higher."""
        return PANEL_TIER_ORDER.index(self)


#: The FR-019 shadowing order, most-shadowing first. Written once here so that
#: discovery, the API listing, and any future consumer order tiers identically.
PANEL_TIER_ORDER: tuple[PanelTier, ...] = (
    PanelTier.PROJECT,
    PanelTier.USER,
    PanelTier.PACKAGE,
    PanelTier.CORE,
)


# ---------------------------------------------------------------------------
# Declaration validation errors (D-009)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class PanelDeclarationError(ValueError):
    """A panel declaration cannot be admitted (FR-003).

    Carries the directory the declaration was read from so every refusal can
    name the thing an author has to go and fix. Discovery turns one of these
    into a diagnostic rather than letting it escape: one broken declaration must
    never cost the rest of a tier.

    Args:
        message: The human-readable refusal, already naming the directory.
        directory: The panel directory the declaration was read from.
        field: The declaration field at fault, when one field is at fault.
        panel_id: The declared panel id, when the declaration got far enough to
            carry one.
    """

    def __init__(
        self,
        message: str,
        *,
        directory: Path | str | None = None,
        field: str | None = None,
        panel_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.directory = Path(directory) if directory is not None else None
        self.field = field
        self.panel_id = panel_id


@provisional(since="0.3.4")
class MissingDeclarationFieldError(PanelDeclarationError):
    """A required declaration field is absent or empty (FR-003)."""


@provisional(since="0.3.4")
class InvalidDeclarationFieldError(PanelDeclarationError):
    """A declaration field is present but not of the declared shape (FR-003)."""


@provisional(since="0.3.4")
class UnreadableDeclarationError(PanelDeclarationError):
    """A ``panel.json`` is missing, unreadable, or not a JSON object."""


@provisional(since="0.3.4")
class DuplicatePanelDeclarationError(PanelDeclarationError):
    """Two declarations in one tier claim the same panel id.

    A collision *between* tiers is shadowing and is the mechanism FR-019
    describes. A collision *within* one tier is a discovery error, because
    nothing in the tier decides which of the two wins.
    """


# ---------------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------------

#: The fields D-007 makes required. Order is the order they are checked in, so
#: an author fixing one declaration field at a time is told about them in the
#: order they appear in the form.
REQUIRED_DECLARATION_FIELDS: tuple[str, ...] = (
    "panel_id",
    "display_name",
    "target_types",
    "capability",
    "entry",
    "api_version",
)


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PanelManifest:
    """The declaration a panel carries (FR-001, D-007, D-009).

    One type for both places a declaration comes from: a ``panel.json`` inside a
    panel directory, and a block class naming the window it opens (FR-017). It
    moved out of the block layer into ``core`` so that both readings are the
    same reading; see the module docstring for why that is a layering constraint
    rather than a preference.

    Example:
        >>> manifest = PanelManifest(
        ...     panel_id="core.plot.basic",
        ...     display_name="Plot",
        ...     target_types=("PlotArtifact",),
        ...     capability=PanelCapability.DISPLAYING,
        ... )
        >>> manifest.entry
        'index.html'
    """

    panel_id: str
    """Stable, unique id, e.g. ``"core.plot.basic"``. Kept when a panel is
    copied into a project, which is what makes the FR-019 ordering shadow the
    original (FR-027)."""

    display_name: str = ""
    """The name a person sees in the panel palette."""

    target_types: tuple[str, ...] = ()
    """The recorded data type names this panel claims, e.g.
    ``("PlotArtifact",)``. Empty only for a panel addressed by a block rather
    than by a data type (FR-017)."""

    capability: PanelCapability = PanelCapability.PRODUCING
    """What this panel may do (FR-005).

    The default is :attr:`PanelCapability.PRODUCING` because the only caller
    that constructs a manifest in Python is a block class declaring the window
    it opens, and such a panel is producing by definition — it exists to take a
    decision back (FR-017, FR-050). An on-disk declaration never reaches this
    default: ``capability`` is one of the required fields
    (:data:`REQUIRED_DECLARATION_FIELDS`), so a ``panel.json`` that omits it is
    refused rather than silently granted an outbound path.
    """

    entry: str = DEFAULT_PANEL_ENTRY
    """The self-contained entry document inside the panel directory (FR-002)."""

    api_version: str = PANEL_API_VERSION
    """The panel API version this panel targets. A panel declaring a version the
    host does not accept is refused before it is mounted (FR-004)."""

    features: tuple[str, ...] = ()
    """Free-form feature tags such as ``table``, ``sort`` or ``export``
    (FR-051). Advertising only; the word *capability* names
    :class:`PanelCapability` and nothing else."""

    priority: int = 0
    """Tie-break weight within one tier and type specificity; higher wins."""

    supports_collection: bool = False
    """Whether the panel can render a collection of its target types."""

    provider: str | None = None
    """Optional ``module:attribute`` reference to a Python provider that windows
    data of the target types (FR-047). ``None`` means the panel's windowed reads
    are served by the shared bounded data-access layer, which is the default
    because that layer windows every core type (A-010)."""

    # ------------------------------------------------------------------
    # ADR-051 block-declared fields.
    #
    # These belong to the block-addressed reading of a manifest and predate the
    # on-disk form. They are kept on the one type rather than split into a
    # second one, because a second manifest type in the block layer is exactly
    # what FR-001 exists to prevent, and because the wire shape :meth:`to_dict`
    # produces is read by clients this spec does not change (D-004).
    # ------------------------------------------------------------------

    module_url: str = ""
    """Backend-relative URL a package panel's module was imported from, in the
    retired ADR-048/ADR-051 module form. Empty for every panel in the on-disk
    form; kept for the compatibility shim."""

    export_name: str = "default"
    """Named export inside a module-form panel to mount."""

    css: tuple[str, ...] = ()
    """Backend-relative CSS asset URLs a module-form panel needs."""

    version: str = "0"
    """Bundle version (a fingerprint or semantic version)."""

    response_schema: dict[str, Any] | None = None
    """Optional advisory declaration of the response shape a producing panel
    returns. Metadata for the host; not enforced by the runtime."""

    asset_root: str | None = None
    """Filesystem directory the panel's assets are confined under. Backend-only;
    never sent to the frontend."""

    def satisfies(self, required: PanelCapability) -> bool:
        """Return whether this panel can serve a request for *required* (FR-048)."""
        return self.capability.satisfies(required)

    @provisional(since="0.3.1")
    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-safe wire form the ADR-051 clients already read.

        :attr:`asset_root` is intentionally omitted (it is a backend-only path),
        and :attr:`response_schema` is included only when it is set. The fields
        the on-disk form adds are deliberately **not** here: bringing the
        endpoints under the panel naming is FR-023 behaviour work, and the panel
        descriptor the frame host reads is built separately
        (:func:`scistudio.panels.descriptor.panel_descriptor`).

        Returns:
            A dict with the manifest's frontend-facing fields.
        """
        data: dict[str, Any] = {
            "panel_id": self.panel_id,
            "module_url": self.module_url,
            "export_name": self.export_name,
            "css": list(self.css),
            "version": self.version,
            "api_version": self.api_version,
        }
        if self.response_schema is not None:
            data["response_schema"] = self.response_schema
        return data

    def to_declaration_dict(self) -> dict[str, Any]:
        """Return the D-007 ``panel.json`` form of this manifest.

        The inverse of :func:`manifest_from_declaration` for the fields that
        form carries, so a panel copied into a project (FR-026) can be written
        back out without the caller re-deriving the shape.
        """
        data: dict[str, Any] = {
            "panel_id": self.panel_id,
            "display_name": self.display_name,
            "target_types": list(self.target_types),
            "capability": self.capability.value,
            "entry": self.entry,
            "api_version": self.api_version,
            "features": list(self.features),
            "priority": self.priority,
            "supports_collection": self.supports_collection,
        }
        if self.provider is not None:
            data["provider"] = self.provider
        return data


# ---------------------------------------------------------------------------
# Declaration parsing (FR-003)
# ---------------------------------------------------------------------------


def _string_field(raw: dict[str, Any], name: str, directory: Path) -> str:
    value = raw.get(name)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise MissingDeclarationFieldError(
            f"panel declaration at {directory} is missing the required field {name!r}",
            directory=directory,
            field=name,
        )
    if not isinstance(value, str):
        raise InvalidDeclarationFieldError(
            f"panel declaration at {directory} declares {name!r} as {type(value).__name__}, expected a string",
            directory=directory,
            field=name,
        )
    return value.strip()


def _string_tuple_field(raw: dict[str, Any], name: str, directory: Path, *, required: bool) -> tuple[str, ...]:
    value = raw.get(name)
    if value is None:
        if required:
            raise MissingDeclarationFieldError(
                f"panel declaration at {directory} is missing the required field {name!r}",
                directory=directory,
                field=name,
            )
        return ()
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise InvalidDeclarationFieldError(
            f"panel declaration at {directory} declares {name!r} as {type(value).__name__}, expected a list of strings",
            directory=directory,
            field=name,
        )
    return tuple(item.strip() for item in value if item.strip())


@provisional(since="0.3.4")
def manifest_from_declaration(raw: object, directory: Path | str) -> PanelManifest:
    """Return the :class:`PanelManifest` a ``panel.json`` body declares (FR-003).

    *raw* is the parsed JSON body and *directory* the panel directory it was
    read from, which is what every refusal names. The six fields in
    :data:`REQUIRED_DECLARATION_FIELDS` must be present and non-empty; the rest
    take the D-007 defaults. Anything else in the body is ignored, so a
    declaration written against a newer version of the form still loads rather
    than being refused for a field this build has never heard of.

    Raises:
        PanelDeclarationError: When the body is not an object, a required field
            is absent, or a field is present with the wrong shape. The message
            names the directory and, where one field is at fault, the field.
    """
    directory = Path(directory)
    if not isinstance(raw, dict):
        raise UnreadableDeclarationError(
            f"panel declaration at {directory} is a {type(raw).__name__}, expected a JSON object",
            directory=directory,
        )

    panel_id = _string_field(raw, "panel_id", directory)
    display_name = _string_field(raw, "display_name", directory)
    target_types = _string_tuple_field(raw, "target_types", directory, required=True)
    capability_name = _string_field(raw, "capability", directory)
    entry = _string_field(raw, "entry", directory)
    api_version = _string_field(raw, "api_version", directory)

    try:
        capability = PanelCapability(capability_name)
    except ValueError as exc:
        raise InvalidDeclarationFieldError(
            f"panel declaration at {directory} declares capability {capability_name!r}; "
            f"the capability set is exactly "
            f"{', '.join(repr(member.value) for member in PanelCapability)}",
            directory=directory,
            field="capability",
            panel_id=panel_id,
        ) from exc

    priority = raw.get("priority", 0)
    if not isinstance(priority, int) or isinstance(priority, bool):
        raise InvalidDeclarationFieldError(
            f"panel declaration at {directory} declares 'priority' as {type(priority).__name__}, expected an integer",
            directory=directory,
            field="priority",
            panel_id=panel_id,
        )

    supports_collection = raw.get("supports_collection", False)
    if not isinstance(supports_collection, bool):
        raise InvalidDeclarationFieldError(
            f"panel declaration at {directory} declares 'supports_collection' as "
            f"{type(supports_collection).__name__}, expected a boolean",
            directory=directory,
            field="supports_collection",
            panel_id=panel_id,
        )

    provider = raw.get("provider")
    if provider is not None and (not isinstance(provider, str) or not provider.strip()):
        raise InvalidDeclarationFieldError(
            f"panel declaration at {directory} declares 'provider' as "
            f"{type(provider).__name__}, expected a 'module:attribute' string",
            directory=directory,
            field="provider",
            panel_id=panel_id,
        )

    return PanelManifest(
        panel_id=panel_id,
        display_name=display_name,
        target_types=target_types,
        capability=capability,
        entry=entry,
        api_version=api_version,
        features=_string_tuple_field(raw, "features", directory, required=False),
        priority=priority,
        supports_collection=supports_collection,
        provider=provider.strip() if isinstance(provider, str) else None,
    )


@provisional(since="0.3.4")
def read_panel_declaration(directory: Path | str) -> PanelManifest:
    """Read and validate ``<directory>/panel.json`` (FR-002, FR-003).

    Raises:
        PanelDeclarationError: When the declaration file is absent, unreadable,
            not JSON, or fails :func:`manifest_from_declaration`. Every message
            names *directory*.
    """
    directory = Path(directory)
    path = directory / PANEL_DECLARATION_FILENAME
    if not path.is_file():
        raise UnreadableDeclarationError(
            f"panel directory at {directory} contains no {PANEL_DECLARATION_FILENAME}",
            directory=directory,
            field=PANEL_DECLARATION_FILENAME,
        )
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise UnreadableDeclarationError(
            f"panel declaration at {directory} could not be read as JSON ({exc})",
            directory=directory,
        ) from exc
    manifest = manifest_from_declaration(body, directory)
    if not (directory / manifest.entry).is_file():
        raise InvalidDeclarationFieldError(
            f"panel declaration at {directory} names entry document {manifest.entry!r}, "
            f"which the directory does not contain",
            directory=directory,
            field="entry",
            panel_id=manifest.panel_id,
        )
    return manifest


__all__ = [
    "DEFAULT_PANEL_ENTRY",
    "PANEL_API_VERSION",
    "PANEL_DECLARATION_FILENAME",
    "PANEL_TIER_ORDER",
    "REQUIRED_DECLARATION_FIELDS",
    "DuplicatePanelDeclarationError",
    "InvalidDeclarationFieldError",
    "MissingDeclarationFieldError",
    "PanelCapability",
    "PanelDeclarationError",
    "PanelManifest",
    "PanelTier",
    "UnreadableDeclarationError",
    "manifest_from_declaration",
    "read_panel_declaration",
]
