"""Block source resolution and the shared block/type origin resolver.

Two jobs, kept in one module because the second grew out of the first.

**Source resolution** backs ``GET /api/blocks/{block_type}/source`` (#1758).
The block's source file is resolved from its registry spec — the concrete
file path for drop-in (tier-1) blocks, otherwise the import module's file for
core and package blocks — so the homepage "View source" action can show a
selected block's code regardless of origin. Resolution is read-only and
limited to registered block types; no arbitrary filesystem path is ever
exposed.

**Origin resolution** is ADR-053 FR-001 to FR-005
(``docs/specs/adr-053-personal-tool-library.md`` §3). ``map_block_origin``
used to collapse both drop-in tiers into one ``custom`` label::

    if raw == "tier1":
        return "custom"

so ``~/.scistudio/blocks/`` and ``{project}/blocks/`` arrived at the palette
indistinguishable and the user tier was invisible. :func:`resolve_origin`
splits them by comparing the spec's file path against the tier roots
:mod:`scistudio.core.dropins` defines, and falls back to ``custom`` for a path
that resolves under neither (FR-002) — an absent file path, a symlink escaping
both, a differing Windows drive. Behaviour degrades; it does not break.

FR-003 requires *one* implementation for both the block surface and the type
surface, not two path comparisons that can diverge. The only things that
actually differ between the two surfaces are the tier child directory
(``blocks`` vs ``types``), the label for an item that ships with SciStudio
(``builtin`` vs ``core``), and the import root that identifies it. Those three
facts are the whole of :class:`OriginSurface`; everything else — the
realpath-before-comparing, the project-tier-before-user-tier order (FR-014),
the ``custom`` fallback — is shared. :data:`BLOCK_SURFACE` and
:data:`TYPE_SURFACE` are the two instances, and a caller resolving a type spec
needs nothing from the block layer to use the second one.

Containment is decided on **resolved real paths**, never on string prefixes: a
symlink inside a tier root that points outside it is not in that tier, and on
Windows a path on a different drive is not relative to anything on this one.
"""

from __future__ import annotations

import importlib
import inspect
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scistudio.core.dropins import (
    project_blocks_dir,
    project_types_dir,
    user_blocks_dir,
    user_types_dir,
)

#: FR-002 fallback: a drop-in whose file path resolves under neither tier root.
CUSTOM_ORIGIN = "custom"

#: An item supplied by an installed plugin distribution.
PACKAGE_ORIGIN = "package"

#: The user-wide library tier, ``~/.scistudio/<child>``.
USER_ORIGIN = "user"

#: The active project's tier, ``{project}/<child>``.
PROJECT_ORIGIN = "project"


class BlockSourceUnavailableError(Exception):
    """A block type is registered but its source file cannot be located/read."""


@dataclass(frozen=True)
class OriginSurface:
    """Everything that differs between the block and type origin surfaces.

    Three facts, and no behaviour: :func:`resolve_origin` owns the rules and
    reads them from here, so adding a surface can never add a second path
    comparison (FR-003).
    """

    installed_origin: str
    """Label for an item that ships with SciStudio: ``builtin`` / ``core``."""

    installed_module_root: str
    """Import root identifying such an item (``scistudio.blocks``)."""

    user_dir: Callable[[], Path]
    """The user-tier drop-in directory accessor from ``core.dropins``."""

    project_dir: Callable[[str | Path], Path]
    """The project-tier drop-in directory accessor from ``core.dropins``."""


#: FR-001/FR-002/FR-004 — ``builtin`` | ``user`` | ``project`` | ``package`` |
#: ``custom``. ``builtin`` is unchanged from before ADR-053 so existing
#: consumers keep working.
BLOCK_SURFACE = OriginSurface(
    installed_origin="builtin",
    installed_module_root="scistudio.blocks",
    user_dir=user_blocks_dir,
    project_dir=project_blocks_dir,
)

#: FR-005 — ``core`` | ``user`` | ``project`` | ``package`` | ``custom``. The
#: same vocabulary as :data:`BLOCK_SURFACE` with ``core`` in place of
#: ``builtin``; core ``DataObject`` subclasses live under
#: ``scistudio.core.types``.
TYPE_SURFACE = OriginSurface(
    installed_origin="core",
    installed_module_root="scistudio.core.types",
    user_dir=user_types_dir,
    project_dir=project_types_dir,
)


def _real(path: str | Path) -> Path | None:
    """Return *path* with symlinks resolved, or ``None`` if unresolvable."""
    try:
        return Path(os.path.realpath(str(path)))
    except (OSError, ValueError):
        return None


def _is_within(candidate: Path, root: Path) -> bool:
    """Return whether *candidate* sits at or under *root*, both already real.

    ``is_relative_to`` answers ``False`` rather than raising for a path on a
    different Windows drive, which is exactly the FR-002 degradation.
    """
    try:
        return candidate.is_relative_to(root)
    except (OSError, ValueError):  # pragma: no cover - defensive
        return False


def resolve_origin(
    surface: OriginSurface,
    *,
    file_path: str | Path | None = None,
    module_path: str = "",
    is_dropin: bool = False,
    project_dir: str | Path | None = None,
) -> str:
    """Return the origin tier of one registered block or data type (FR-003).

    The single implementation both the block palette and the types listing
    resolve through. ``surface`` selects the vocabulary and the tier
    directories; everything else is the same question asked of a different
    registry spec.

    Args:
        surface: :data:`BLOCK_SURFACE` or :data:`TYPE_SURFACE`.
        file_path: The spec's concrete source file, set only for drop-ins.
        module_path: The spec's import module path, used when there is no
            file path to classify installed items.
        is_dropin: Whether the registry classified this as a drop-in even
            though no usable file path came with it. Such an item is ``custom``
            rather than ``package``: a drop-in type registers under a synthetic
            ``_scistudio_type_dropin_*`` module name, and a block registers
            under ``tier1``, neither of which is a distribution.
        project_dir: Active project root, or ``None`` when no project is open —
            in which case nothing can resolve to :data:`PROJECT_ORIGIN`.

    Returns:
        One of ``surface.installed_origin``, :data:`USER_ORIGIN`,
        :data:`PROJECT_ORIGIN`, :data:`PACKAGE_ORIGIN`, :data:`CUSTOM_ORIGIN`.
    """
    if file_path:
        resolved = _real(file_path)
        if resolved is not None:
            # Project tier first, matching the FR-014 shadowing order, so a
            # project nested inside the user library still reads as project.
            if project_dir is not None:
                project_root = _real(surface.project_dir(project_dir))
                if project_root is not None and _is_within(resolved, project_root):
                    return PROJECT_ORIGIN
            user_root = _real(surface.user_dir())
            if user_root is not None and _is_within(resolved, user_root):
                return USER_ORIGIN
        return CUSTOM_ORIGIN
    if is_dropin:
        return CUSTOM_ORIGIN
    root = surface.installed_module_root
    if module_path == root or module_path.startswith(f"{root}."):
        return surface.installed_origin
    return PACKAGE_ORIGIN if module_path else CUSTOM_ORIGIN


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


def map_block_origin(spec: Any, *, project_dir: str | Path | None = None) -> str:
    """Return the FR-001/FR-002 origin tier of a block registry spec.

    The block-side adapter over :func:`resolve_origin`: it reads the three
    fields a :class:`~scistudio.blocks.registry.BlockSpec` carries and asks the
    shared resolver. It holds no rule of its own.
    """
    return resolve_origin(
        BLOCK_SURFACE,
        file_path=getattr(spec, "file_path", None),
        module_path=getattr(spec, "module_path", "") or "",
        is_dropin=(getattr(spec, "source", "") or "").strip() == "tier1",
        project_dir=project_dir,
    )


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
