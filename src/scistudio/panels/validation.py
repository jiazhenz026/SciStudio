"""Author-facing panel package checks, shared with runtime discovery."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scistudio.panels.registry import PanelRegistry

from scistudio.panels.files import validate_external_references as validate_external_references
from scistudio.stability import provisional


@provisional(since="0.3.5")
def validate_interactive_panel(manifest: object, registry: PanelRegistry | None = None) -> None:
    """Check that an interactive block's panel declaration can open.

    ``manifest`` is the block's panel declaration (its ``panel_id`` and
    ``module_url``). The panel must resolve, in ``registry`` or in a fresh
    discovery, to a panel whose contexts include ``interactive``; otherwise
    ``ValueError`` is raised. A declaration that still names a legacy
    ``module_url`` emits a ``DeprecationWarning`` and is not checked further.
    """
    import warnings

    from scistudio.panels.registry import discover_panels

    panel_id = getattr(manifest, "panel_id", "")
    if getattr(manifest, "module_url", ""):
        warnings.warn(
            f"Panel {panel_id!r} module_url is deprecated; replace with an HTML panel", DeprecationWarning, stacklevel=2
        )
        return
    panels = registry or _SCAN_PANELS.get() or discover_panels()
    panel = panels.get(panel_id)
    if panel is None or "interactive" not in panel.contexts:
        resolved = f"{panel.owner_kind.value} panel {panel.id!r}" if panel else "no registered panel"
        raise ValueError(f"FR-023: block panel {panel_id!r} resolves to {resolved}; interactive context required")


_SCAN_PANELS: ContextVar[PanelRegistry | None] = ContextVar("scistudio_panel_scan", default=None)


@contextmanager
def panel_scan_scope(scan_dirs: Iterable[Path]) -> Iterator[PanelRegistry]:
    """Reuse one panel discovery pass throughout a block registry scan."""
    from scistudio.core.dropins import library_root_for_project
    from scistudio.panels.registry import discover_panels

    project = next((Path(p).parent for p in scan_dirs if Path(p).parent != library_root_for_project(None)), None)
    token = _SCAN_PANELS.set(discover_panels(project))
    try:
        panels = _SCAN_PANELS.get()
        assert panels is not None
        yield panels
    finally:
        _SCAN_PANELS.reset(token)
