"""Confined static assets and the SciStudio-owned panel content policy."""

from __future__ import annotations

import mimetypes
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

CDN_HOSTS = ("cdn.jsdelivr.net", "cdnjs.cloudflare.com", "unpkg.com")
ASSET_SUFFIXES = frozenset(
    {
        ".html",
        ".js",
        ".mjs",
        ".css",
        ".map",
        ".json",
        ".svg",
        ".woff",
        ".woff2",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ttf",
        ".otf",
        ".wasm",
    }
)


def resolve_panel_file(root: Path, relative: str) -> Path:
    """Reject traversal, absolute paths, symlink escapes and executable source."""
    if not relative or "\\" in relative or "\x00" in relative or urlsplit(relative).scheme:
        raise ValueError("FR-026: invalid panel asset path")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts:
        raise ValueError("FR-026: asset path escapes confinement root")
    root = Path(root).resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("FR-026: asset symlink escapes confinement root")
    if candidate.suffix.lower() not in ASSET_SUFFIXES:
        raise ValueError("FR-026: file type is not a panel asset")
    if not candidate.is_file():
        raise ValueError("FR-026: panel asset does not exist")
    return candidate


def media_type(path: Path) -> str:
    """Use JavaScript module MIME types on every platform."""
    return (
        {".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm"}.get(path.suffix.lower())
        or mimetypes.guess_type(path.name)[0]
        or "application/octet-stream"
    )


def content_policy(token_base_url: str) -> str:
    """Restrict loads to this mount's token path and versioned CDN allowlist."""
    cdns = " ".join(f"https://{host}" for host in CDN_HOSTS)
    return (
        f"default-src 'none'; script-src {token_base_url} 'unsafe-inline' {cdns}; "
        f"style-src {token_base_url} 'unsafe-inline' {cdns}; font-src {token_base_url} {cdns}; "
        f"img-src {token_base_url} data: blob:; connect-src 'none'; object-src 'none'; "
        "base-uri 'none'; form-action 'none'; frame-src 'none'"
    )
