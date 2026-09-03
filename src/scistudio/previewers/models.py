"""Deprecated alias for :mod:`scistudio.panels.models` (ADR-054 spec 1, FR-038).

``scistudio.previewers.models`` was the canonical author root a package-owned
or drop-in previewer imported its declaration types from. The subsystem is now
:mod:`scistudio.panels`; this module keeps the retired path resolving so an
unmigrated package or an on-disk drop-in still loads (FR-045, FR-020, FR-042).

**It translates; it does not merely re-export** (ADR-054 spec 1 D-001). A
re-export keeps a *name* importable, which is not the promise the ADR-048
addendum makes: the promise is that code already written against the pre-rename
API keeps producing a registered panel. FR-051 renamed
``PreviewerSpec.capabilities`` to :attr:`~scistudio.panels.models.PanelSpec.features`
and D-007 inserted ``target_types`` ahead of ``supports_collection``, so a
re-export of the renamed class refuses the keyword an author copied out of the
pre-rename docstring and silently mis-binds a positional call. :class:`PreviewerSpec`
below is therefore a translating subclass carrying the *pre-rename* constructor
signature — same parameter order, same spelling — that normalises onto the
renamed fields. FR-051 is untouched: ``capabilities`` is not a field on
:class:`~scistudio.panels.models.PanelSpec`, does not appear in ``to_dict()``,
and is not on the wire. It exists only here, at the compatibility boundary, and
using it raises a :class:`DeprecationWarning` naming both spellings.

Everything else in this module is an import or an alias. Removed under the
condition stated in the ADR-048 addendum (FR-044).
"""

from __future__ import annotations

import warnings
from dataclasses import fields
from typing import Any

from scistudio.panels.models import (
    PANEL_API_VERSION as PREVIEWER_API_VERSION,
)
from scistudio.panels.models import (
    DuplicatePanelIdError as DuplicatePreviewerIdError,  # noqa: F401  (retired-name re-export)
)
from scistudio.panels.models import (
    EnvelopeKind as EnvelopeKind,
)
from scistudio.panels.models import (
    FrontendManifest as FrontendManifest,
)
from scistudio.panels.models import (
    InvalidSpecError as InvalidSpecError,
)
from scistudio.panels.models import (
    MissingBundleError as MissingBundleError,
)
from scistudio.panels.models import (
    OwnerKind as OwnerKind,
)
from scistudio.panels.models import (
    PanelCapability as PanelCapability,
)
from scistudio.panels.models import (
    PanelEntryPoint as PreviewerEntryPoint,
)
from scistudio.panels.models import (
    PanelSpec as PanelSpec,
)
from scistudio.panels.models import (
    PanelSpecList as PreviewerSpecList,
)
from scistudio.panels.models import (
    PreviewEnvelope as PreviewEnvelope,
)
from scistudio.panels.models import (
    PreviewError as PreviewError,
)
from scistudio.panels.models import (
    PreviewErrorCode as PreviewErrorCode,
)
from scistudio.panels.models import (
    PreviewErrorInfo as PreviewErrorInfo,
)
from scistudio.panels.models import (
    PreviewLimits as PreviewLimits,
)
from scistudio.panels.models import (
    PreviewMetadata as PreviewMetadata,
)
from scistudio.panels.models import (
    PreviewProvider as PreviewProvider,
)
from scistudio.panels.models import (
    PreviewRequest as PreviewRequest,
)
from scistudio.panels.models import (
    PreviewResource as PreviewResource,
)
from scistudio.panels.models import (
    PreviewResourceProvider as PreviewResourceProvider,
)
from scistudio.panels.models import (
    PreviewSession as PreviewSession,
)
from scistudio.panels.models import (
    PreviewSource as PreviewSource,
)
from scistudio.panels.models import (
    PreviewTarget as PreviewTarget,
)
from scistudio.panels.models import (
    ProviderError as ProviderError,
)
from scistudio.panels.models import (
    RoutingAmbiguityError as RoutingAmbiguityError,
)
from scistudio.panels.models import (
    TargetKind as TargetKind,
)
from scistudio.panels.models import (
    UnknownPanelError as UnknownPreviewerError,  # noqa: F401  (retired-name re-export)
)
from scistudio.panels.models import (
    UnknownTargetError as UnknownTargetError,
)

#: Sentinel for "the caller did not pass this at all", so ``capabilities`` and
#: ``features`` can be told apart from each other *and* from an explicit empty
#: tuple. ``None`` would not do: ``capabilities=None`` is something a pre-rename
#: author could plausibly have written.
_UNSET: Any = object()

#: The one field FR-051 renamed, in the direction this module translates.
_RETIRED_SPEC_KEYWORD = "capabilities"
_CURRENT_SPEC_KEYWORD = "features"


def _panel_spec_key(spec: PanelSpec) -> tuple[Any, ...]:
    """Return *spec*'s field values in declaration order.

    The tuple :func:`dataclasses.dataclass` itself compares and hashes on. Used
    so a translated :class:`PreviewerSpec` and the
    :class:`~scistudio.panels.models.PanelSpec` it is equivalent to compare
    equal, which the generated ``__eq__`` would refuse on the class check alone.
    """
    return tuple(getattr(spec, spec_field.name) for spec_field in fields(PanelSpec))


class PreviewerSpec(PanelSpec):
    """The pre-rename spelling of :class:`~scistudio.panels.models.PanelSpec`.

    A drop-in already sitting in ``<project>/previewers`` or a package already
    published against the ``scistudio.previewers`` entry-point group constructs
    its specs through *this* name, and it does so with the pre-rename signature:

    * ``capabilities=`` — the keyword the pre-rename ``PreviewerSpec`` docstring
      used in its own worked example, and the one the shipped package-authoring
      guide still teaches. FR-051 renamed the field ``features``.
    * the pre-rename *positional* order, in which ``supports_collection`` is the
      fifth argument. D-007 inserted ``target_types`` there, so a positional
      caller reaching a re-exported :class:`~scistudio.panels.models.PanelSpec`
      binds a ``bool`` to a tuple field and a tuple to an ``int`` field without
      raising — a wrong object rather than a refusal.

    This subclass keeps both working by declaring the pre-rename signature and
    normalising onto the renamed fields, so the object handed back to the
    registry is an ordinary panel spec: ``isinstance(spec, PanelSpec)`` holds,
    ``to_dict()`` emits ``features`` like every other spec, and equality and
    hashing match the equivalent :class:`~scistudio.panels.models.PanelSpec`.

    The fields D-007 and FR-005 added are reachable here too, keyword-only, so a
    half-migrated author is not forced to choose between the old constructor and
    the new fields — and so :func:`dataclasses.replace` round-trips.

    Example:
        >>> spec = PreviewerSpec(
        ...     previewer_id="acme.image.viewer",
        ...     owner_kind=OwnerKind.PACKAGE,
        ...     owner_name="acme",
        ...     target_type="Image",
        ...     capabilities=("slice", "lut"),  # doctest: +SKIP
        ... )
    """

    def __init__(
        self,
        previewer_id: str,
        owner_kind: OwnerKind,
        owner_name: str,
        target_type: str,
        supports_collection: bool = False,
        priority: int = 0,
        capabilities: tuple[str, ...] = _UNSET,
        backend_provider: PreviewProvider | str | None = None,
        resource_provider: PreviewResourceProvider | str | None = None,
        frontend_manifest: FrontendManifest | None = None,
        api_version: str = PREVIEWER_API_VERSION,
        *,
        features: tuple[str, ...] = _UNSET,
        target_types: tuple[str, ...] = (),
        capability: PanelCapability = PanelCapability.DISPLAYING,
    ) -> None:
        if capabilities is not _UNSET and features is not _UNSET:
            raise TypeError(
                f"{type(self).__name__} was given both {_RETIRED_SPEC_KEYWORD}= and "
                f"{_CURRENT_SPEC_KEYWORD}=; they are the same field under two spellings "
                f"(ADR-054 spec 1 FR-051 renamed {_RETIRED_SPEC_KEYWORD} to "
                f"{_CURRENT_SPEC_KEYWORD}). Pass {_CURRENT_SPEC_KEYWORD}= only."
            )
        if capabilities is not _UNSET:
            warnings.warn(
                f"scistudio.previewers.models.PreviewerSpec({_RETIRED_SPEC_KEYWORD}=...) is the "
                f"retired spelling of scistudio.panels.models.PanelSpec("
                f"{_CURRENT_SPEC_KEYWORD}=...) for panel {previewer_id!r} owned by "
                f"{owner_name!r}. It is translated for now (ADR-054 spec 1 FR-051, D-001); "
                f"rename the keyword to {_CURRENT_SPEC_KEYWORD}= and import PanelSpec from "
                f"scistudio.panels.models.",
                DeprecationWarning,
                stacklevel=2,
            )
            advertised = capabilities
        elif features is not _UNSET:
            advertised = features
        else:
            advertised = ()
        super().__init__(
            previewer_id=previewer_id,
            owner_kind=owner_kind,
            owner_name=owner_name,
            target_type=target_type,
            target_types=target_types,
            supports_collection=supports_collection,
            priority=priority,
            features=advertised,
            capability=capability,
            backend_provider=backend_provider,
            resource_provider=resource_provider,
            frontend_manifest=frontend_manifest,
            api_version=api_version,
        )

    @property
    def capabilities(self) -> tuple[str, ...]:
        """The retired spelling of :attr:`~scistudio.panels.models.PanelSpec.features`.

        Read-only, and deliberately not a field: FR-051 reserves the word
        *capability* for :class:`~scistudio.core.panels.PanelCapability`. A
        pre-rename author who wrote the attribute as well as the keyword reads
        the same tuple back.
        """
        return self.features

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PanelSpec):
            return _panel_spec_key(self) == _panel_spec_key(other)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(_panel_spec_key(self))


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
