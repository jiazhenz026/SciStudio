"""Deprecated alias for :mod:`scistudio.panels` (ADR-054 spec 1, FR-038).

The subsystem was renamed from *previewer* to *panel*. This package exists only
so the retired import path keeps resolving while published packages and
on-disk drop-ins migrate:

* the ``scistudio.previewers`` entry-point group and its ``get_previewers()``
  factory must continue to be discovered (FR-045, FR-020), and a package that
  supplies that factory imports its spec type from this path;
* the user-library and project tiers still read ``~/.scistudio/previewers`` and
  ``<project>/previewers``, whose drop-in modules import from here.

It contains no logic of its own — only imports and aliases. The renamed symbols
are re-exported under their old names; import from :mod:`scistudio.panels` in
new code. This module is removed under the condition stated in the ADR-048
addendum (FR-044).
"""

from __future__ import annotations

from scistudio.panels import (
    PANEL_API_VERSION as PREVIEWER_API_VERSION,
)
from scistudio.panels import (
    PanelEntryPoint as PreviewerEntryPoint,
)
from scistudio.panels import (
    PanelRegistry as PreviewerRegistry,  # noqa: F401  (retired-name re-export)
)
from scistudio.panels import (
    PanelSpec as PreviewerSpec,
)
from scistudio.panels import (
    PreviewDataAccess as PreviewDataAccess,
)
from scistudio.panels import (
    PreviewEnvelope as PreviewEnvelope,
)
from scistudio.panels import (
    PreviewError as PreviewError,
)
from scistudio.panels import (
    PreviewErrorCode as PreviewErrorCode,
)
from scistudio.panels import (
    PreviewErrorInfo as PreviewErrorInfo,
)
from scistudio.panels import (
    PreviewLimits as PreviewLimits,
)
from scistudio.panels import (
    PreviewMetadata as PreviewMetadata,
)
from scistudio.panels import (
    PreviewProvider as PreviewProvider,
)
from scistudio.panels import (
    PreviewRequest as PreviewRequest,
)
from scistudio.panels import (
    PreviewResource as PreviewResource,
)
from scistudio.panels import (
    PreviewResourceProvider as PreviewResourceProvider,
)
from scistudio.panels import (
    PreviewRouter as PreviewRouter,
)
from scistudio.panels import (
    PreviewService as PreviewService,
)
from scistudio.panels import (
    PreviewSessionManager as PreviewSessionManager,
)
from scistudio.panels import (
    PreviewSource as PreviewSource,
)
from scistudio.panels import (
    PreviewTarget as PreviewTarget,
)
from scistudio.panels import (
    ProviderError as ProviderError,
)
from scistudio.panels import (
    UnknownPanelError as UnknownPreviewerError,  # noqa: F401  (retired-name re-export)
)
from scistudio.panels import (
    UnknownTargetError as UnknownTargetError,
)
from scistudio.panels import (
    build_preview_service as build_preview_service,
)
from scistudio.panels import (
    get_preview_service as get_preview_service,
)
from scistudio.panels import (
    load_project_panels as load_project_previewers,  # noqa: F401  (retired-name re-export)
)
from scistudio.panels import (
    load_user_panels as load_user_previewers,  # noqa: F401  (retired-name re-export)
)
from scistudio.panels.models import (
    EnvelopeKind as EnvelopeKind,
)
from scistudio.panels.models import (
    FrontendManifest as FrontendManifest,
)
from scistudio.panels.models import (
    OwnerKind as OwnerKind,
)
from scistudio.panels.models import (
    TargetKind as TargetKind,
)

__all__ = [
    "PREVIEWER_API_VERSION",
    "EnvelopeKind",
    "FrontendManifest",
    "OwnerKind",
    "PreviewDataAccess",
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
    "ProviderError",
    "TargetKind",
]
