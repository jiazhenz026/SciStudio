"""Author-facing panel package checks, shared with runtime discovery."""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlsplit

from scistudio.panels.files import CDN_HOSTS

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
        if file.stat().st_size > 16 * 1024 * 1024:
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


def validate_interactive_panel(manifest: object, registry: object = None) -> None:
    """Apply block-to-panel context compatibility, including 0.5 legacy modules."""
    import warnings

    from scistudio.panels.contexts import LEGACY_CORE_PANELS
    from scistudio.panels.registry import discover_panels

    panel_id = getattr(manifest, "panel_id", "")
    if getattr(manifest, "module_url", ""):
        warnings.warn(
            f"Panel {panel_id!r} module_url is deprecated; replace with an HTML panel", DeprecationWarning, stacklevel=2
        )
        return
    panels = registry or _SCAN_PANELS.get() or discover_panels()
    panel = panels.get(panel_id)
    if panel is None and panel_id in LEGACY_CORE_PANELS:
        return
    if panel is None or "interactive" not in panel.contexts:
        resolved = f"{panel.owner_kind.value} panel {panel.id!r}" if panel else "no registered panel"
        raise ValueError(f"FR-023: block panel {panel_id!r} resolves to {resolved}; interactive context required")


_SCAN_PANELS: ContextVar[object] = ContextVar("scistudio_panel_scan", default=None)


@contextmanager
def panel_scan_scope(scan_dirs: object):
    """Reuse one panel discovery pass throughout a block registry scan."""
    from scistudio.core.dropins import library_root_for_project
    from scistudio.panels.registry import discover_panels

    project = next((Path(p).parent for p in scan_dirs if Path(p).parent != library_root_for_project(None)), None)
    token = _SCAN_PANELS.set(discover_panels(project))
    try:
        yield _SCAN_PANELS.get()
    finally:
        _SCAN_PANELS.reset(token)
