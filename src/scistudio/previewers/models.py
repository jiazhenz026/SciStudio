"""Deprecated alias for :mod:`scistudio.panels.models` (ADR-054 spec 1, FR-038).

``scistudio.previewers.models`` was the canonical author root a package-owned
or drop-in previewer imported its declaration types from. The subsystem is now
:mod:`scistudio.panels`; this module keeps the retired path resolving so an
unmigrated package or an on-disk drop-in still loads (FR-045, FR-020, FR-042).

It contains no logic of its own — only imports and aliases. Removed under the
condition stated in the ADR-048 addendum (FR-044).
"""

from __future__ import annotations

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
    PanelEntryPoint as PreviewerEntryPoint,
)
from scistudio.panels.models import (
    PanelSpec as PreviewerSpec,
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
