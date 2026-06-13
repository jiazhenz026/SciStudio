"""Same-origin frontend asset serving + manifest validation (ADR-048 FR-022/FR-024).

Package- and project-owned previewers ship a JavaScript ESM module plus
optional CSS. The frontend PreviewHost imports those at runtime, but ONLY from
backend-validated, same-origin URLs (FR-022). This module:

* validates a :class:`FrontendManifest` (required fields, api_version,
  version, remote-URL rejection);
* path-confines an asset request under the previewer's declared
  ``asset_root`` so a manifest cannot read arbitrary files (FR-024);
* returns a typed result the API route can serve.

No remote (http/https/protocol-relative) URLs are ever served — the manifest
``module_url`` and css entries must be backend-relative
(``/api/previews/assets/...``) and resolve to a real file under the asset root.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from scistudio.previewers.models import (
    PREVIEWER_API_VERSION,
    FrontendManifest,
    MissingBundleError,
)

logger = logging.getLogger(__name__)

_REMOTE_PREFIXES = ("http://", "https://", "//", "data:", "file:")
_ALLOWED_ASSET_SUFFIXES = {".js", ".mjs", ".css", ".map", ".json", ".svg", ".woff", ".woff2"}
_ASSET_MEDIA_TYPES = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".map": "application/json",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


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
    """Validate a previewer frontend manifest (FR-024).

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

    api_version_ok = manifest.api_version == PREVIEWER_API_VERSION
    if not api_version_ok:
        diagnostics.append(f"manifest api_version {manifest.api_version!r} != expected {PREVIEWER_API_VERSION!r}")

    if not manifest.version:
        diagnostics.append("manifest missing version/fingerprint")

    return ManifestValidation(valid=valid, diagnostics=tuple(diagnostics), api_version_ok=api_version_ok)


def resolve_asset(manifest: FrontendManifest, relative_path: str) -> ServedAsset:
    """Confine *relative_path* under the manifest asset root and return it (FR-024).

    Raises :class:`MissingBundleError` when no asset root is declared, the
    resolved path escapes the root, the suffix is disallowed, or the file is
    absent.
    """
    if not manifest.asset_root:
        raise MissingBundleError(
            f"previewer {manifest.previewer_id!r} declares a manifest but no asset_root",
            detail={"previewer_id": manifest.previewer_id},
        )
    if is_remote_url(relative_path):
        raise MissingBundleError(
            f"refusing to serve remote asset url: {relative_path}",
            detail={"previewer_id": manifest.previewer_id, "url": relative_path},
        )

    root = Path(manifest.asset_root).resolve()
    # Strip any leading slash so the request path joins relative to the root.
    cleaned = relative_path.lstrip("/\\")
    candidate = (root / cleaned).resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise MissingBundleError(
            f"asset path escapes confinement root: {relative_path}",
            detail={"previewer_id": manifest.previewer_id, "url": relative_path},
        ) from exc

    suffix = candidate.suffix.lower()
    if suffix not in _ALLOWED_ASSET_SUFFIXES:
        raise MissingBundleError(
            f"asset suffix {suffix!r} is not an allowed frontend asset type",
            detail={"previewer_id": manifest.previewer_id, "url": relative_path},
        )
    if not candidate.is_file():
        raise MissingBundleError(
            f"asset bundle not found on disk: {relative_path}",
            detail={"previewer_id": manifest.previewer_id, "url": relative_path},
        )

    return ServedAsset(path=candidate, media_type=_ASSET_MEDIA_TYPES.get(suffix, "application/octet-stream"))


__all__ = [
    "ManifestValidation",
    "ServedAsset",
    "is_remote_url",
    "resolve_asset",
    "validate_manifest",
]
