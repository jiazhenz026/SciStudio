"""One answer to "which library tier did this block or data type come from?".

ADR-053 / ``docs/specs/adr-053-personal-tool-library.md`` §3 (FR-001 to
FR-005). ``map_block_origin`` used to collapse both drop-in tiers into one
``custom`` label::

    if raw == "tier1":
        return "custom"

so ``~/.scistudio/blocks/`` and ``{project}/blocks/`` arrived at the palette
indistinguishable and the user tier was invisible. :func:`resolve_origin`
splits them by comparing the item's file path against the tier roots
:mod:`scistudio.core.dropins` defines, and falls back to ``custom`` for a path
that resolves under neither (FR-002) — an absent file path, a symlink escaping
both, a differing Windows drive. Behaviour degrades; it does not break.

**FR-003 requires one implementation**, not two path comparisons that can
diverge. The only things that actually differ between the block surface and the
type surface are the tier child directory (``blocks`` vs ``types``), the label
for an item that ships with SciStudio (``builtin`` vs ``core``), and the import
root that identifies it. Those three facts are the whole of
:class:`OriginSurface`; everything else — the realpath-before-comparing, the
project-tier-before-user-tier order (FR-014), the ``custom`` fallback — is
shared. :data:`BLOCK_SURFACE` and :data:`TYPE_SURFACE` are the two instances.

Containment is decided on **resolved real paths**, never on string prefixes: a
symlink inside a tier root that points outside it is not in that tier, and on
Windows a path on a different drive is not relative to anything on this one.

Layering: this module lives in ``scistudio.core`` for the same reason
:mod:`scistudio.core.dropins` does — its consumers span layers, and no layer
above ``core`` may be imported by the others. It began in
``scistudio.api._block_source``, where the ``AI must not depend on api``
import-linter contract put it out of reach of the agent's promotion tool
(§6.2 E3), which therefore grew a second, narrower rule: the tool asked whether
the source file's parent *equalled* the user library root, so a block whose
origin resolved to the FR-002 ``custom`` fallback was hidden by the three
frontend entry points and accepted by the agent. That is precisely the
divergence FR-003 was written to prevent, and the fix is layering rather than a
third comparison — recorded in
``docs/audit/2026-08-07-adr-053-spec1-track-b.md`` (P2-2).
``scistudio.api._block_source`` re-exports every name here, so the API-side
call sites are unchanged.

This module holds no rule about *directories*; it asks
:mod:`scistudio.core.dropins` for those, which keeps FR-058's single tier
definition single.
"""

from __future__ import annotations

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

__all__ = [
    "BLOCK_ORIGIN_VOCABULARY",
    "BLOCK_SURFACE",
    "CUSTOM_ORIGIN",
    "PACKAGE_ORIGIN",
    "PROJECT_ORIGIN",
    "TYPE_ORIGIN_VOCABULARY",
    "TYPE_SURFACE",
    "USER_ORIGIN",
    "OriginSurface",
    "map_block_origin",
    "resolve_origin",
]

#: FR-002 fallback: a drop-in whose file path resolves under neither tier root.
CUSTOM_ORIGIN = "custom"

#: An item supplied by an installed plugin distribution.
PACKAGE_ORIGIN = "package"

#: The user-wide library tier, ``~/.scistudio/<child>``.
USER_ORIGIN = "user"

#: The active project's tier, ``{project}/<child>``.
PROJECT_ORIGIN = "project"


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

    @property
    def vocabulary(self) -> tuple[str, ...]:
        """Every label :func:`resolve_origin` can return for this surface.

        The complete vocabulary, in one place, so a consumer that must behave
        differently per tier can enumerate it instead of hardcoding a list that
        silently stops being complete. ``promote_to_user_library`` and its
        parity test both read it.
        """
        return (
            self.installed_origin,
            USER_ORIGIN,
            PROJECT_ORIGIN,
            PACKAGE_ORIGIN,
            CUSTOM_ORIGIN,
        )


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

#: Convenience aliases for the two surfaces' complete vocabularies. They are
#: what ``frontend/src/types/api.ts`` declares as ``BlockOrigin`` /
#: ``TypeOrigin``, and the FR-025 parity test enumerates them so a case can
#: never be added on one side of the wire alone.
BLOCK_ORIGIN_VOCABULARY = BLOCK_SURFACE.vocabulary
TYPE_ORIGIN_VOCABULARY = TYPE_SURFACE.vocabulary


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

    The single implementation the block palette, the types listing, the source
    viewer and the agent's promotion tool all resolve through. ``surface``
    selects the vocabulary and the tier directories; everything else is the
    same question asked of a different registry spec.

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
        One of ``surface.vocabulary``.
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


def map_block_origin(spec: Any, *, project_dir: str | Path | None = None) -> str:
    """Return the FR-001/FR-002 origin tier of a block registry spec.

    The block-side adapter over :func:`resolve_origin`: it reads the three
    fields a :class:`~scistudio.blocks.registry.BlockSpec` carries and asks the
    shared resolver. It holds no rule of its own.

    ``spec`` is read structurally rather than imported, because ``core`` may
    not depend on ``scistudio.blocks``. That is also what lets the API's block
    listing and the agent's promotion tool call *this* function rather than two
    look-alikes (FR-025 / §6.2 E3).
    """
    return resolve_origin(
        BLOCK_SURFACE,
        file_path=getattr(spec, "file_path", None),
        module_path=getattr(spec, "module_path", "") or "",
        is_dropin=(getattr(spec, "source", "") or "").strip() == "tier1",
        project_dir=project_dir,
    )
