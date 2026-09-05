"""One path-confinement check and one suffix allowlist, for every panel asset.

ADR-054 spec 1 FR-021 and D-008: **one** asset route serves all four tiers,
using one confinement check and one allowlist, differing only in the root
directory each tier resolves to. This module owns that check.
:func:`resolve_confined_asset` is the single implementation; every route that
serves a panel file goes through it:

* ``GET /api/panels/assets/{panel_id}/{asset_path}`` — the merged route
  (:mod:`scistudio.api.routes.panels`), whose root is the discovered panel's
  own directory, whichever of the four tiers it was found in;
* ``GET /api/previews/assets/{previewer_id}/{asset_path}`` and
  ``GET /api/blocks/panels/{panel_id}/{asset_path}`` — the two routes FR-022
  keeps serving their existing clients for the duration of the migration. They
  resolve their root from a :class:`FrontendManifest`'s ``asset_root`` and then
  call the same function.

Three copies of a confinement check is the failure mode the spec exists to
remove: that single check is the only thing standing between a panel id and an
arbitrary filesystem read, so there is one of it and it is tested against every
tier root (SC-008).

This module also validates a :class:`FrontendManifest` — required fields,
api_version, version, remote-URL rejection — for the retired ADR-048 module
form. No remote (http/https/protocol-relative) URL is ever served: a manifest's
``module_url`` and css entries must be backend-relative and resolve to a real
file under the asset root.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from scistudio.panels.models import (
    PANEL_API_VERSION,
    FrontendManifest,
    MissingBundleError,
)

logger = logging.getLogger(__name__)

_REMOTE_PREFIXES = ("http://", "https://", "//", "data:", "file:")

#: The one suffix allowlist (FR-021, D-008): the ADR-048 previewer set plus
#: ``.html``, because a panel is now a self-contained document rather than an
#: ES module, plus the raster types a document embeds directly. Anything not
#: named here is refused whichever tier asked for it.
_ALLOWED_ASSET_SUFFIXES = {
    ".html",
    ".js",
    ".mjs",
    ".css",
    ".map",
    ".json",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".woff",
    ".woff2",
}
_ASSET_MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".map": "application/json",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}

#: The bound the route applies to any served asset. The Edge Cases entry: "a
#: panel document exceeds a reasonable size" is a *load failure with a readable
#: diagnostic", not a truncated document the host then fails to parse for a
#: reason nobody can see. 16 MiB is far above any self-contained document and
#: far below anything that would hurt to read.
MAX_PANEL_ASSET_BYTES = 16 * 1024 * 1024


class PanelAssetTooLargeError(MissingBundleError):
    """A panel asset is larger than :data:`MAX_PANEL_ASSET_BYTES` (Edge Cases).

    A subclass rather than a plain refusal because the route answers it with a
    different status than "no such file": a person whose edited document grew
    past the bound has to be told *that*, not told the panel disappeared.
    """


@dataclass(frozen=True)
class ManifestValidation:
    """Outcome of validating a :class:`FrontendManifest`."""

    valid: bool
    diagnostics: tuple[str, ...] = ()
    api_version_ok: bool = True


@dataclass(frozen=True)
class ServedAsset:
    """A validated, path-confined asset ready to stream to the client."""

    path: Path
    media_type: str


def is_remote_url(url: str) -> bool:
    """Return True if *url* points off-origin and must be rejected (FR-022)."""
    lowered = url.strip().lower()
    return any(lowered.startswith(prefix) for prefix in _REMOTE_PREFIXES)


def validate_manifest(manifest: FrontendManifest | None) -> ManifestValidation:
    """Validate a panel frontend manifest (FR-024).

    Checks required fields, rejects remote URLs, and flags an api_version
    mismatch as a non-fatal diagnostic (the host may still refuse to mount).
    """
    if manifest is None:
        return ManifestValidation(valid=False, diagnostics=("no frontend manifest declared",))

    diagnostics: list[str] = []
    valid = True

    if not manifest.previewer_id:
        diagnostics.append("manifest missing previewer_id")
        valid = False
    if not manifest.module_url:
        diagnostics.append("manifest missing module_url")
        valid = False
    elif is_remote_url(manifest.module_url):
        diagnostics.append(f"manifest module_url is remote and rejected: {manifest.module_url}")
        valid = False
    if not manifest.export_name:
        diagnostics.append("manifest missing export_name")
        valid = False

    for css_url in manifest.css:
        if is_remote_url(css_url):
            diagnostics.append(f"manifest css url is remote and rejected: {css_url}")
            valid = False

    api_version_ok = manifest.api_version == PANEL_API_VERSION
    if not api_version_ok:
        diagnostics.append(f"manifest api_version {manifest.api_version!r} != expected {PANEL_API_VERSION!r}")

    if not manifest.version:
        diagnostics.append("manifest missing version/fingerprint")

    return ManifestValidation(valid=valid, diagnostics=tuple(diagnostics), api_version_ok=api_version_ok)


def is_allowed_asset_suffix(name: str | Path) -> bool:
    """Return whether *name*'s suffix is in the one allowlist (FR-021, D-008).

    Exposed so the editing endpoints refuse to *write* what this module would
    refuse to *serve*. A panel directory that could hold a file the asset route
    will not serve is a panel a person can save and then not load.
    """
    return Path(name).suffix.lower() in _ALLOWED_ASSET_SUFFIXES


def is_safe_panel_id(panel_id: str) -> bool:
    """Return whether *panel_id* may be joined to a tier root as one segment.

    A panel id reaches the merged route as a path segment and is then used to
    find a directory, so an id that is itself a traversal — ``..``, an absolute
    path, anything carrying a separator or a NUL — is refused before it is
    joined to anything. Discovery would not produce such an id, but the route
    reads what the client sent, not what discovery produced.
    """
    if not panel_id or panel_id in {".", ".."}:
        return False
    if "\x00" in panel_id:
        return False
    if "/" in panel_id or "\\" in panel_id:
        return False
    # A Windows drive-qualified or UNC-ish id ("C:foo") would join as an
    # absolute path on that platform; refuse it on every platform so the check
    # does not change meaning between the developer's machine and the user's.
    return not Path(panel_id).is_absolute() and ":" not in panel_id


def resolve_confined_asset(
    root: Path | str,
    relative_path: str,
    *,
    panel_id: str = "",
    max_bytes: int = MAX_PANEL_ASSET_BYTES,
) -> ServedAsset:
    """Confine *relative_path* under *root* and return it (FR-021, SC-008).

    The one check, shared by the merged route and by the two routes FR-022
    keeps. Only *root* differs by tier; everything below is identical whichever
    tier asked, which is the property SC-008 measures.

    The confinement is a resolve-then-contain: both the root and the candidate
    are fully resolved first, so a symlink inside the panel directory pointing
    out of it lands outside the root and is refused by the same comparison that
    refuses ``..``. Percent-encoded traversal never reaches here as an escape
    either — the ASGI layer has already decoded it, so ``%2e%2e`` is ``..`` by
    the time it is joined.

    Args:
        root: The tier root, or the panel directory, the request is confined to.
        relative_path: The path the client asked for, relative to *root*.
        panel_id: The panel the request names, carried into the diagnostics.
        max_bytes: The size bound; an asset above it is a load failure with a
            readable diagnostic rather than a truncated read.

    Raises:
        MissingBundleError: The path escapes the root, the suffix is not
            allowed, or the file is absent.
        PanelAssetTooLargeError: The file is larger than *max_bytes*.
    """
    detail = {"panel_id": panel_id, "previewer_id": panel_id, "url": relative_path}
    if is_remote_url(relative_path):
        raise MissingBundleError(f"refusing to serve remote asset url: {relative_path}", detail=detail)

    resolved_root = Path(root).resolve()
    # Strip any leading slash so the request path joins relative to the root.
    cleaned = relative_path.lstrip("/\\")
    if not cleaned:
        raise MissingBundleError("asset path is empty", detail=detail)
    candidate = (resolved_root / cleaned).resolve()

    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise MissingBundleError(f"asset path escapes confinement root: {relative_path}", detail=detail) from exc

    suffix = candidate.suffix.lower()
    if suffix not in _ALLOWED_ASSET_SUFFIXES:
        raise MissingBundleError(f"asset suffix {suffix!r} is not an allowed panel asset type", detail=detail)
    if not candidate.is_file():
        raise MissingBundleError(f"asset not found on disk: {relative_path}", detail=detail)

    size = candidate.stat().st_size
    if size > max_bytes:
        raise PanelAssetTooLargeError(
            f"panel asset {relative_path} is {size} bytes, above the {max_bytes}-byte limit this route serves",
            detail={**detail, "size_bytes": size, "max_bytes": max_bytes},
        )

    return ServedAsset(path=candidate, media_type=_ASSET_MEDIA_TYPES.get(suffix, "application/octet-stream"))


def resolve_asset(manifest: FrontendManifest, relative_path: str) -> ServedAsset:
    """Confine *relative_path* under the manifest asset root and return it (FR-024).

    The manifest-addressed entry point, used by the two routes FR-022 keeps
    serving for the duration of the migration. It reads the root off the
    manifest and then defers to :func:`resolve_confined_asset`, so the two old
    routes and the merged one share one confinement check rather than three.

    Raises :class:`MissingBundleError` when no asset root is declared, the
    resolved path escapes the root, the suffix is disallowed, or the file is
    absent.
    """
    if not manifest.asset_root:
        raise MissingBundleError(
            f"panel {manifest.previewer_id!r} declares a manifest but no asset_root",
            detail={"previewer_id": manifest.previewer_id},
        )
    return resolve_confined_asset(
        manifest.asset_root,
        relative_path,
        panel_id=manifest.previewer_id,
    )


# ---------------------------------------------------------------------------
# The boundary the response carries (#2229)
# ---------------------------------------------------------------------------

#: The frame boundary, restated by the server that serves the document.
#:
#: FR-008's boundary is real, and it rests on **one attribute on one code
#: path**: ``element.setAttribute("sandbox", PANEL_FRAME_SANDBOX)`` in
#: ``frontend/src/panels/panelFrame.ts``. But the document is served as
#: ``text/html`` from the application's own origin, so a package panel — or a
#: project panel that arrived with a shared project — is an HTML document a
#: browser will execute *at the application origin* if it is ever reached
#: outside that frame: by direct navigation, by a link, by ``window.open``.
#:
#: Defence in depth, not a replacement. The CSP carries the same
#: ``allow-scripts`` token the frame applies and no other, so it removes
#: nothing a mounted panel can do today and makes the boundary a property of
#: the document rather than of one call site. ``Referrer-Policy`` likewise
#: mirrors the frame's own ``referrerpolicy="no-referrer"``.
#:
#: ``X-Frame-Options`` is deliberately absent. The mechanism *is* a document in
#: a frame, and ``DENY`` would break every panel.
PANEL_DOCUMENT_SECURITY_HEADERS = {
    "Content-Security-Policy": "sandbox allow-scripts",
    "Referrer-Policy": "no-referrer",
}

#: Carried by every served asset, not only the document. A ``.json`` or a
#: ``.map`` that a browser sniffed as HTML would be the same problem the CSP
#: above exists to close, arriving *through* the suffix allowlist rather than
#: past it.
PANEL_ASSET_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
}

#: The media type the document headers key off, compared on the type alone so a
#: charset parameter cannot make the check miss.
_DOCUMENT_MEDIA_TYPE = "text/html"


def panel_asset_security_headers(media_type: str) -> dict[str, str]:
    """Return the boundary headers one served panel asset answers with.

    Here rather than in a route for the same reason the confinement check is:
    three routes serve panel files, and a boundary that held on one of them
    would be a boundary a panel document reaches around by being requested
    through another. The cross-origin *grant* is not here — it belongs to the
    merged route alone (FR-021, A-008) and the two FR-022 routes must not gain
    it.
    """
    headers = dict(PANEL_ASSET_SECURITY_HEADERS)
    if media_type.split(";", 1)[0].strip().lower() == _DOCUMENT_MEDIA_TYPE:
        headers |= PANEL_DOCUMENT_SECURITY_HEADERS
    return headers


__all__ = [
    "MAX_PANEL_ASSET_BYTES",
    "PANEL_ASSET_SECURITY_HEADERS",
    "PANEL_DOCUMENT_SECURITY_HEADERS",
    "ManifestValidation",
    "PanelAssetTooLargeError",
    "ServedAsset",
    "is_allowed_asset_suffix",
    "is_remote_url",
    "is_safe_panel_id",
    "panel_asset_security_headers",
    "resolve_asset",
    "resolve_confined_asset",
    "validate_manifest",
]
