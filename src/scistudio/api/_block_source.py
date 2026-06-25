"""Resolve a registered block type to its on-disk Python source (read-only).

Backs ``GET /api/blocks/{block_type}/source`` (#1758). The block's source
file is resolved from its registry spec — the project-local file path for
custom (tier-1) blocks, otherwise the import module's file for core and
package blocks — so the homepage "View source" action can show a selected
block's code regardless of origin. Resolution is read-only and limited to
registered block types; no arbitrary filesystem path is ever exposed.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any


class BlockSourceUnavailableError(Exception):
    """A block type is registered but its source file cannot be located/read."""


def map_block_origin(raw: str) -> str:
    """Map an internal registry source label to a palette-friendly origin.

    ``tier1`` -> ``custom`` (project-local hot-loaded blocks); ``entry_point``
    / ``package_src`` -> ``package`` (installed plugin blocks);
    ``builtin`` -> ``builtin`` (core blocks). Unknown labels pass through.
    """
    if raw == "tier1":
        return "custom"
    if raw in ("entry_point", "package_src"):
        return "package"
    if raw == "builtin":
        return "builtin"
    return raw


def resolve_block_source(registry: Any, block_type: str) -> dict[str, str]:
    """Return ``{path, source, language, origin}`` for a registered block type.

    Raises:
        KeyError: the block type is not registered.
        BlockSourceUnavailableError: the type is registered but its source file
            cannot be located or read.
    """
    spec = registry.get_spec(block_type)
    if spec is None:
        raise KeyError(block_type)

    path = _source_path(spec)
    if path is None or not path.exists():
        raise BlockSourceUnavailableError(f"no source file for block type '{block_type}'")
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BlockSourceUnavailableError(f"could not read source for '{block_type}': {exc}") from exc

    return {
        "path": str(path),
        "source": source,
        "language": "python",
        "origin": _origin(spec),
    }


def _source_path(spec: Any) -> Path | None:
    """Locate the ``.py`` file backing *spec*, or ``None`` if unresolvable."""
    # Tier-1 custom blocks carry the concrete project-local file path.
    file_path = getattr(spec, "file_path", None)
    if file_path:
        return Path(str(file_path))
    # Core and package blocks resolve through their import module.
    module_path = getattr(spec, "module_path", "") or ""
    if module_path:
        try:
            module = importlib.import_module(module_path)
            return Path(inspect.getfile(module))
        except (ImportError, TypeError, OSError):
            return None
    return None


def _origin(spec: Any) -> str:
    """Best-effort block origin for display ("builtin" / "package" / "custom").

    The import root is the authoritative core-vs-package signal: core blocks
    live under ``scistudio.blocks.*`` while plugin packages import from their
    own roots (e.g. ``scistudio_blocks_*``). The registry tier label is not
    used for that split because core blocks are themselves registered through
    entry points (source ``entry_point``), which would mislabel them as
    ``package``. A project-local file path always means a custom block.
    """
    if getattr(spec, "file_path", None) or map_block_origin((getattr(spec, "source", "") or "").strip()) == "custom":
        return "custom"
    module_path = getattr(spec, "module_path", "") or ""
    if module_path.startswith("scistudio.blocks.") or module_path == "scistudio.blocks":
        return "builtin"
    return "package"
