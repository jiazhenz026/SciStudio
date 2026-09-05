"""Deprecated alias for :mod:`scistudio.panels.assets` (ADR-054 spec 1, FR-038).

Core-internal machinery that resolved under ``scistudio.previewers`` before the
rename. It carries no author stability promise, but it imported, and a path that
silently stops importing is the break the alias package exists to prevent
(FR-020).

The names ADR-054 added after the rename are re-exported too, so a package that
finds this module still finds one asset surface rather than a truncated copy of
an older one.

It contains no logic of its own — only imports and aliases. Removed under the
condition stated in the ADR-048 addendum (FR-044).
"""

from __future__ import annotations

from scistudio.panels.assets import (
    MAX_PANEL_ASSET_BYTES as MAX_PANEL_ASSET_BYTES,
)
from scistudio.panels.assets import (
    ManifestValidation as ManifestValidation,
)
from scistudio.panels.assets import (
    PanelAssetTooLargeError as PanelAssetTooLargeError,
)
from scistudio.panels.assets import (
    ServedAsset as ServedAsset,
)
from scistudio.panels.assets import (
    is_allowed_asset_suffix as is_allowed_asset_suffix,
)
from scistudio.panels.assets import (
    is_remote_url as is_remote_url,
)
from scistudio.panels.assets import (
    is_safe_panel_id as is_safe_panel_id,
)
from scistudio.panels.assets import (
    resolve_asset as resolve_asset,
)
from scistudio.panels.assets import (
    resolve_confined_asset as resolve_confined_asset,
)
from scistudio.panels.assets import (
    validate_manifest as validate_manifest,
)

__all__ = [
    "ManifestValidation",
    "ServedAsset",
    "is_remote_url",
    "resolve_asset",
    "validate_manifest",
]
