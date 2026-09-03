"""Deprecated alias for :mod:`scistudio.panels` (ADR-054 spec 1, FR-038).

The subsystem was renamed from *previewer* to *panel*. This package exists only
so the retired import path keeps resolving while published packages and
on-disk drop-ins migrate:

* the ``scistudio.previewers`` entry-point group and its ``get_previewers()``
  factory must continue to be discovered (FR-045, FR-020), and a package that
  supplies that factory imports its spec type from this path;
* the user-library and project tiers still read ``~/.scistudio/previewers`` and
  ``<project>/previewers``, whose drop-in modules import from here.

**The alias modules translate; they do not merely re-export** (ADR-054 spec 1
D-001). Keeping a name importable is not the promise the ADR-048 addendum makes.
The promise is that code already written against the pre-rename API keeps
producing a registered panel, so where the rename moved a keyword or a field
position, :mod:`scistudio.previewers.models` carries a translating
:class:`~scistudio.previewers.models.PreviewerSpec` rather than the renamed
class itself, and it is that spec type this package re-exports.

Every module that resolved under ``scistudio.previewers`` before the rename
still resolves — ``registry``, ``router``, ``session``, ``fallbacks``,
``assets``, ``choices``, ``project``, ``open_as``, ``_raster`` and
``_table_cache`` alongside the three canonical author roots. Most of those were
core-internal and carry no author promise, but a path that used to import and
now raises ``ModuleNotFoundError`` is exactly the silent break this package
exists to prevent, and :mod:`scistudio.previewers.fallbacks` in particular was
kept by #1823 as a deliberate back-compat door for ``sanitize_svg``.

Apart from that translation the package holds no logic of its own. The renamed
symbols are re-exported under their old names; import from
:mod:`scistudio.panels` in new code. This module is removed under the condition
stated in the ADR-048 addendum (FR-044).
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

# ``load_choices`` was imported into this namespace before the rename, so
# ``from scistudio.previewers import load_choices`` resolved. It was never in
# ``__all__`` and was never advertised author surface, but it imported, and a
# path that silently stops importing is the break this package exists to
# prevent — so it is re-exported here and left out of ``__all__`` exactly as it
# was.
from scistudio.panels.choices import (
    load_choices as load_choices,
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

# The pre-rename spec type, translated rather than re-exported (D-001). This is
# the one symbol the alias package does not take straight from
# :mod:`scistudio.panels`: see :mod:`scistudio.previewers.models`.
from scistudio.previewers.models import (
    PreviewerSpec as PreviewerSpec,
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
