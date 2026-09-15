"""Confined static assets and the SciStudio-owned panel content policy."""

from __future__ import annotations

import json
import mimetypes
import os
import re
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

CDN_HOSTS = ("cdn.jsdelivr.net", "cdnjs.cloudflare.com", "unpkg.com")
MAX_SOURCE_BYTES = 16 * 1024 * 1024
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


def bootstrap_entry(document: bytes, proof: str) -> bytes:
    """Bind the initialization channel to this document before author scripts run."""
    encoded = (
        json.dumps(proof, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )
    # A leading doctype preserves standards mode while putting trusted code before
    # every original tag, including refresh metadata and executable author code.
    script = (
        "<!doctype html><script>(()=>{"
        "const host=parent,dispatch=window.dispatchEvent.bind(window),Event=MessageEvent;"
        "const channel=new MessageChannel(),port=channel.port1;"
        "port.onmessage=(event)=>{port.onmessage=null;"
        "dispatch(new Event('message',{source:host,data:event.data,ports:event.ports}));port.close();};"
        "port.start();host.postMessage({v:1,id:'bootstrap',type:'bootstrap',proof:"
        + encoded
        + "},'*',[channel.port2]);})();</script>"
    )
    return script.encode("utf-8") + document.removeprefix(b"\xef\xbb\xbf")


def resolve_panel_file(root: Path, relative: str) -> Path:
    """Reject traversal, absolute paths, symlink escapes and executable source."""
    if not relative or "\\" in relative or "\x00" in relative or urlsplit(relative).scheme:
        raise ValueError("FR-026: invalid panel asset path")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts:
        raise ValueError("FR-026: asset path escapes confinement root")
    # Normalise both sides and confine the join with commonpath. This resolves
    # symlinks and rejects any escape before the path reaches the filesystem;
    # it is also a containment barrier static path-injection analysis models.
    root_real = os.path.realpath(root)
    resolved = os.path.realpath(os.path.join(root_real, relative))
    if os.path.commonpath((root_real, resolved)) != root_real:
        raise ValueError("FR-026: asset symlink escapes confinement root")
    candidate = Path(resolved)
    if candidate.suffix.lower() not in ASSET_SUFFIXES:
        raise ValueError("FR-026: file type is not a panel asset")
    if not candidate.is_file():
        raise ValueError("FR-026: panel asset does not exist")
    python_source = Path(root_real) / "panel.py"
    if python_source.is_file() and candidate.samefile(python_source):
        raise ValueError("FR-026: executable source is not a panel asset")
    return candidate


def media_type(path: Path) -> str:
    """Use JavaScript module MIME types on every platform."""
    return (
        {".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm"}.get(path.suffix.lower())
        or mimetypes.guess_type(path.name)[0]
        or "application/octet-stream"
    )


def content_policy(token_base_url: str) -> str:
    """Restrict loads to this mount's own origin, its token path, and the CDN allowlist.

    The panel document and its subresources (SDK, ``panel.js``, assets) are always
    served from the same origin the browser used to load the iframe, so ``'self'``
    is the correct, deployment-agnostic source for them. ``token_base_url`` (an
    absolute URL the backend derives from its own view of the request) is kept as
    a path-pinned source for direct deployments, but under a reverse proxy or the
    dev vite proxy the browser's origin differs from the backend's
    ``request.url.netloc``; ``'self'`` is what makes those deployments work.
    """
    cdns = " ".join(f"https://{host}" for host in CDN_HOSTS)
    return (
        f"default-src 'none'; script-src 'self' {token_base_url} 'unsafe-inline' {cdns}; "
        f"style-src 'self' {token_base_url} 'unsafe-inline' {cdns}; font-src 'self' {token_base_url} {cdns}; "
        f"img-src 'self' {token_base_url} data: blob:; connect-src 'none'; object-src 'none'; "
        "base-uri 'none'; form-action 'none'; frame-src 'none'"
    )


_URL = re.compile(r"""(?:https?:)?//[^\s"'<>`)]+""")
_PINNED = re.compile(r"(?:@|/)(?:v)?\d+\.\d+\.\d+(?:[/.-]|$)")


def validate_external_references(root: Path) -> list[str]:
    """Refuse off-allowlist references and report unpinned CDN versions."""
    notes = []
    for file in root.rglob("*"):
        if not file.is_file() or file.suffix.lower() not in {".html", ".css", ".js", ".mjs"}:
            continue
        if not file.resolve().is_relative_to(root.resolve()):
            raise ValueError("FR-038: panel contains an escaping asset symlink")
        if file.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError("FR-038: panel source exceeds 16 MiB validation budget")
        for url in _URL.findall(file.read_text(encoding="utf-8", errors="replace")):
            parsed = urlsplit(url if not url.startswith("//") else "https:" + url)
            # XML namespace identifiers are names, not loads.
            if url in ("http://www.w3.org/2000/svg", "http://www.w3.org/1999/xhtml"):
                continue
            if parsed.hostname not in CDN_HOSTS or parsed.scheme != "https" or parsed.username or parsed.port:
                raise ValueError(f"FR-038: external reference outside CDN allowlist: {url}")
            if not _PINNED.search(parsed.path):
                notes.append(f"FR-038: unpinned CDN reference {url}")
    return notes
