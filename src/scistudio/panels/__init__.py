"""Sandboxed HTML panels: discover, validate, and check the panels a project sees.

A panel is a folder holding a ``panel.json`` descriptor and an HTML page, with
an optional ``panel.py`` beside it. The descriptor names the contexts the panel
opens in (``preview``, ``interactive``, ``miniapp``) and the data types it
claims. A panel needs no Python import to exist: a project or the user library
holds panel folders directly, and a package lists its panel folders from a
callable registered under the ``scistudio.panels`` entry-point group.

The Python surface below is for checking panels from code, for example in a
package's own tests:

* :func:`discover_panels` runs the same discovery the application runs and
  returns a :class:`PanelRegistry` holding the winning panels, the shadowed ones,
  and every diagnostic.
* :func:`parse_descriptor` validates one panel folder and returns its
  :class:`PanelDescriptor` with any non-fatal notes.
* :func:`validate_external_references` checks a panel's HTML, CSS, and scripts
  against the CDN allowlist and reports unpinned CDN versions.
* :func:`validate_interactive_panel` checks that an interactive block's panel
  declaration resolves to a panel that opens in the interactive context.
* :data:`PANEL_API_VERSION` is the descriptor ``api_version`` the host serves.

Every symbol here is **provisional**: usable, and it may change in a minor
release with a changelog note. Import from ``scistudio.panels``; the modules
inside this package carry no promise.
"""
# Maintainer context (kept outside generated API documentation):
# Canonical public root for the ADR-054 panels Python surface (ADR-052 §3, #2426).
#
# The exported names are the author-facing contract rows of the ADR-049 contract
# table (docs/planning/adr-054-contract-notes.md PV-09-007, PV-09-008, PV-09-010,
# PV-12-006): descriptor validation, discovery, the interactive compatibility
# check, and the CDN reference check. Everything else in this package -- the
# context store, token routes, file serving, the resident process host, the
# bootstrap, the watcher, MiniApp creation, and the GUI debug broker -- is runtime
# machinery and stays internal.
#
# Re-exports resolve lazily (PEP 562). ``python -m scistudio.panels.bootstrap``
# runs in the user's interpreter for every MiniApp and imports this package
# first; an eager import of discovery would pull the type registry and the entry
# point machinery into every resident panel process.
#
# TODO(#2288): PanelDescriptor.owner_kind and parse_descriptor(owner_kind=...)
#   still use OwnerKind from the deprecated scistudio.previewers.models root.
#   Out of scope per #2426 (marking only); the tier enum needs a non-deprecated
#   home before the previewer surface is removed in 0.6.
#   Followup: https://github.com/jiazhenz026/SciStudio/issues/2288
# Development references: ADR-052, ADR-054, #2426.

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scistudio.panels.descriptor import PANEL_API_VERSION, PanelDescriptor, parse_descriptor
    from scistudio.panels.files import validate_external_references
    from scistudio.panels.registry import PanelRegistry, discover_panels
    from scistudio.panels.validation import validate_interactive_panel

_EXPORTS: dict[str, str] = {
    "PANEL_API_VERSION": "scistudio.panels.descriptor",
    "PanelDescriptor": "scistudio.panels.descriptor",
    "PanelRegistry": "scistudio.panels.registry",
    "discover_panels": "scistudio.panels.registry",
    "parse_descriptor": "scistudio.panels.descriptor",
    "validate_external_references": "scistudio.panels.files",
    "validate_interactive_panel": "scistudio.panels.validation",
}

__all__ = [
    "PANEL_API_VERSION",
    "PanelDescriptor",
    "PanelRegistry",
    "discover_panels",
    "parse_descriptor",
    "validate_external_references",
    "validate_interactive_panel",
]


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
