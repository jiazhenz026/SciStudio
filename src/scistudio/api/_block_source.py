"""Block source resolution, and the API's view of the shared origin resolver.

**Source resolution** backs ``GET /api/blocks/{block_type}/source`` (#1758).
The block's source file is resolved from its registry spec — the concrete
file path for drop-in (tier-1) blocks, otherwise the import module's file for
core and package blocks — so the homepage "View source" action can show a
selected block's code regardless of origin. Resolution is read-only and
limited to registered block types; no arbitrary filesystem path is ever
exposed.

**Origin resolution** (ADR-053 FR-001 to FR-005) used to live here too, and
now lives in :mod:`scistudio.core.origins`. It moved because its consumers
span layers: the agent's promotion tool (§6.2 E3) has to apply the same rule
as the palette, and the ``AI must not depend on api`` import-linter contract
put an ``api`` module out of its reach — so E3 grew a second, narrower
comparison and diverged from the three frontend entry points on the FR-002
``custom`` case. FR-003 asks for one implementation, so the implementation
moved to a layer both sides can import rather than a second rule being
written. See ``docs/audit/2026-08-07-adr-053-spec1-track-b.md`` (P2-2).

Every origin name is re-exported below, so ``scistudio.api`` callers import it
from here exactly as before. :func:`map_source_label` stays here because it is
about the *legacy* ``BlockSummary.source`` vocabulary this router still emits,
not about the tier resolution.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

from scistudio.core.origins import (
    BLOCK_ORIGIN_VOCABULARY,
    BLOCK_SURFACE,
    CUSTOM_ORIGIN,
    PACKAGE_ORIGIN,
    PROJECT_ORIGIN,
    TYPE_ORIGIN_VOCABULARY,
    TYPE_SURFACE,
    USER_ORIGIN,
    OriginSurface,
    map_block_origin,
    resolve_origin,
)

__all__ = [
    "BLOCK_ORIGIN_VOCABULARY",
    "BLOCK_SURFACE",
    "CUSTOM_ORIGIN",
    "PACKAGE_ORIGIN",
    "PROJECT_ORIGIN",
    "TYPE_ORIGIN_VOCABULARY",
    "TYPE_SURFACE",
    "USER_ORIGIN",
    "BlockSourceUnavailableError",
    "OriginSurface",
    "map_block_origin",
    "map_source_label",
    "resolve_block_source",
    "resolve_origin",
]


class BlockSourceUnavailableError(Exception):
    """A block type is registered but its source file cannot be located/read."""


def map_source_label(raw: str) -> str:
    """Map an internal registry source label to the pre-ADR-053 vocabulary.

    ``tier1`` -> ``custom`` (drop-in blocks); ``entry_point`` / ``package_src``
    -> ``package``; ``builtin`` -> ``builtin``. Unknown labels pass through.

    This is the legacy ``BlockSummary.source`` value and is deliberately left
    unchanged by ADR-053: FR-002 requires existing consumers of ``custom`` to
    keep working, so the tier split is carried by the additive ``origin`` field
    (FR-004) rather than by redefining a shipped one.
    """
    if raw == "tier1":
        return CUSTOM_ORIGIN
    if raw in ("entry_point", "package_src"):
        return PACKAGE_ORIGIN
    if raw == "builtin":
        return "builtin"
    return raw


def resolve_block_source(
    registry: Any,
    block_type: str,
    *,
    project_dir: str | Path | None = None,
) -> dict[str, str]:
    """Return ``{path, source, language, origin}`` for a registered block type.

    ``origin`` is the FR-001 resolved tier, so the source viewer and the
    palette agree about which library a block came from — the source editor's
    promotion affordance (§6.2 E1) is gated on it.

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
        "origin": map_block_origin(spec, project_dir=project_dir),
    }


def _source_path(spec: Any) -> Path | None:
    """Locate the ``.py`` file backing *spec*, or ``None`` if unresolvable."""
    # Drop-in blocks carry the concrete file path.
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
