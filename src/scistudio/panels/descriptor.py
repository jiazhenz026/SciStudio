"""The panel descriptor the frame host mounts from (FR-004, FR-005, D-016).

The host invents nothing. It is handed the version it accepts, the capability
this mount is granted, the URL of the entry document, the base it fetches its
own assets from, and the bounds on one windowed read; a descriptor missing the
accepted version or the read limits is refused as a backend defect rather than
filled in with a guess (D-016.3). This module is where the backend's half of
that contract is built, so there is one answer rather than one per route.

The URLs are the merged asset route's (D-008,
``GET /api/panels/assets/{panel_id}/{asset_path}``). One route, four tier roots,
one path-confinement check and one suffix allowlist — the shape is identical
whichever tier the panel came from, which is what makes copying a built-in panel
into a project a directory copy and nothing more.

The counterpart is ``frontend/src/panels/panelDescriptor.ts``; the field names
here are the wire's, so a caller can hand a response object straight to
``validatePanelDescriptor``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from scistudio.core.panels import PANEL_API_VERSION, PanelCapability
from scistudio.panels.models import PreviewLimits
from scistudio.stability import internal

if TYPE_CHECKING:
    from scistudio.core.panels import PanelManifest
    from scistudio.panels.discovery import DiscoveredPanel

__all__ = [
    "PANEL_ASSET_ROUTE_PREFIX",
    "PanelDescriptor",
    "panel_asset_base_url",
    "panel_descriptor",
    "read_limits_payload",
]

#: The merged asset route's prefix (D-008, FR-021). Written here rather than in
#: the route module so the descriptor builder and the route cannot disagree
#: about the URL a panel is served from; the route imports it.
PANEL_ASSET_ROUTE_PREFIX = "/api/panels/assets"


def panel_asset_base_url(panel_id: str) -> str:
    """Return the same-origin base a panel fetches its own assets from.

    A panel runs at an opaque origin, so this is the only thing it can reach
    without going through the host (FR-021). The id is percent-encoded because
    it reaches the route as a path segment.
    """
    return f"{PANEL_ASSET_ROUTE_PREFIX}/{quote(panel_id, safe='')}/"


def read_limits_payload(limits: PreviewLimits | None = None) -> dict[str, Any]:
    """Return the ``read_limits`` object the descriptor and ``init`` carry.

    The two fields the message contract names, plus the remaining budgets the
    bounded reader already enforces, so a panel that wants to size a tile
    request need not guess. The host requires ``max_rows`` and ``max_bytes`` and
    ignores the rest.
    """
    limits = limits or PreviewLimits()
    return {
        "max_rows": limits.max_rows,
        "max_bytes": limits.max_bytes,
        "max_items": limits.max_items,
        "max_tile": limits.max_tile,
        "max_dim": limits.max_dim,
    }


@internal()
@dataclass(frozen=True)
class PanelDescriptor:
    """Everything the frame host needs to mount one panel.

    ``capability`` is the capability *this mount* is granted, which is not
    always the one the panel declares: a producing panel opened from the preview
    surface is granted display only, and a producing request that found no
    producing panel mounts the displaying result with no outbound path (FR-049).
    Whoever builds the descriptor decides that; the panel never negotiates it.
    """

    panel_id: str
    display_name: str
    api_version: str
    accepted_api_version: str
    capability: PanelCapability
    document_url: str
    asset_base_url: str
    read_limits: dict[str, Any]
    tier: str = ""
    features: tuple[str, ...] = ()
    supports_collection: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-safe wire form ``validatePanelDescriptor`` reads."""
        return {
            "panel_id": self.panel_id,
            "display_name": self.display_name,
            "api_version": self.api_version,
            "accepted_api_version": self.accepted_api_version,
            "capability": self.capability.value,
            "document_url": self.document_url,
            "asset_base_url": self.asset_base_url,
            "read_limits": dict(self.read_limits),
            "tier": self.tier,
            "features": list(self.features),
            "supports_collection": self.supports_collection,
        }


def panel_descriptor(
    panel: DiscoveredPanel | PanelManifest,
    *,
    granted_capability: PanelCapability | None = None,
    limits: PreviewLimits | None = None,
    tier: str = "",
) -> PanelDescriptor:
    """Build the descriptor for *panel* (FR-004, FR-005, D-016).

    Args:
        panel: A discovered panel, or a bare manifest when the caller has no
            discovery record (a block-declared panel, for instance).
        granted_capability: The capability this mount is granted. Defaults to
            the capability the panel declares, which is the right answer only
            when the request asked for exactly that; a caller resolving a
            request passes the granted one explicitly (FR-049).
        limits: The read budgets in force, defaulting to the standard ones.
        tier: The tier the panel resolved from, when the caller is not passing a
            discovered panel that already knows.

    Returns:
        The :class:`PanelDescriptor`. It always carries ``accepted_api_version``
        and ``read_limits``, because the host refuses to mount without either.
    """
    manifest = panel.manifest if hasattr(panel, "manifest") else panel
    resolved_tier = tier or (panel.tier.value if hasattr(panel, "tier") else "")
    return PanelDescriptor(
        panel_id=manifest.panel_id,
        display_name=manifest.display_name or manifest.panel_id,
        api_version=manifest.api_version,
        accepted_api_version=PANEL_API_VERSION,
        capability=granted_capability or manifest.capability,
        document_url=f"{panel_asset_base_url(manifest.panel_id)}{quote(manifest.entry)}",
        asset_base_url=panel_asset_base_url(manifest.panel_id),
        read_limits=read_limits_payload(limits),
        tier=resolved_tier,
        features=tuple(manifest.features),
        supports_collection=manifest.supports_collection,
    )
