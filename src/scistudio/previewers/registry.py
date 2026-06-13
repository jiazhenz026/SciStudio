"""PreviewerRegistry — core / package / monorepo / project discovery (FR-002).

Loads :class:`PreviewerSpec` declarations from three tiers:

1. **core** — always loaded, unconditionally, from
   :func:`scistudio.previewers.fallbacks.core_previewer_specs`.
2. **package** — installed packages that ship a ``scistudio.previewers``
   entry point (``importlib.metadata.entry_points(group="scistudio.previewers")``)
   plus a monorepo dev fallback that scans ``packages/scistudio-blocks-*`` for a
   module-level ``get_previewers()`` callable, gated by ``SCISTUDIO_DEV=1`` in
   the same spirit as :meth:`TypeRegistry._scan_monorepo_types` (FR-030).
3. **project** — project-local specs registered via
   :mod:`scistudio.previewers.project`.

Duplicate ``previewer_id`` across the loaded set is recorded as a diagnostic
and the subsequent registration is rejected (FR-006); a broken entry point is
logged and skipped, never crashing the registry (mirrors the block/type
registries).
"""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
import sys
from pathlib import Path
from typing import Any

from scistudio.previewers.models import (
    OwnerKind,
    PreviewerSpec,
)

logger = logging.getLogger(__name__)

PREVIEWER_ENTRY_POINT_GROUP = "scistudio.previewers"


class PreviewerRegistry:
    """In-memory registry of :class:`PreviewerSpec` objects keyed by id.

    The registry holds specs only (no provider instances). Routing reads the
    full set via :meth:`all_specs`; the session manager resolves a single spec
    by id via :meth:`get`.
    """

    def __init__(self) -> None:
        self._by_id: dict[str, PreviewerSpec] = {}
        self._diagnostics: list[str] = []
        self._project_default_previewers: dict[str, str] = {}

    # -- registration -------------------------------------------------------

    def register(self, spec: PreviewerSpec) -> bool:
        """Register *spec*; reject duplicates with a diagnostic (FR-006).

        Returns ``True`` when the spec was added, ``False`` when a spec with
        the same ``previewer_id`` was already present.
        """
        if not spec.previewer_id:
            self._diagnostics.append("previewer spec rejected: empty previewer_id")
            return False
        if spec.previewer_id in self._by_id:
            self._diagnostics.append(
                f"duplicate previewer_id '{spec.previewer_id}' "
                f"(owner={spec.owner_kind.value}/{spec.owner_name}); keeping first"
            )
            logger.warning("Duplicate previewer_id '%s' ignored", spec.previewer_id)
            return False
        self._by_id[spec.previewer_id] = spec
        return True

    def set_project_default(self, target_type: str, previewer_id: str) -> None:
        """Declare a project default previewer for *target_type* (FR-005)."""
        self._project_default_previewers[target_type] = previewer_id

    # -- accessors ----------------------------------------------------------

    def get(self, previewer_id: str) -> PreviewerSpec | None:
        return self._by_id.get(previewer_id)

    def all_specs(self) -> list[PreviewerSpec]:
        return list(self._by_id.values())

    def specs_for_owner(self, owner_kind: OwnerKind) -> list[PreviewerSpec]:
        return [s for s in self._by_id.values() if s.owner_kind is owner_kind]

    def project_default_for(self, target_type: str) -> str | None:
        return self._project_default_previewers.get(target_type)

    @property
    def diagnostics(self) -> list[str]:
        return list(self._diagnostics)

    def clear(self) -> None:
        self._by_id.clear()
        self._diagnostics.clear()
        self._project_default_previewers.clear()

    # -- discovery ----------------------------------------------------------

    def load_core(self) -> None:
        """Load the core fallback previewer specs unconditionally (FR-002)."""
        from scistudio.previewers.fallbacks import core_previewer_specs

        for spec in core_previewer_specs():
            self.register(spec)

    def load_packages(self, *, include_monorepo: bool = False) -> None:
        """Load package previewers from entry points + monorepo fallback (FR-002/FR-030)."""
        self._scan_entry_points()
        if include_monorepo:
            self._scan_monorepo_packages()

    def _scan_entry_points(self) -> None:
        try:
            eps = importlib.metadata.entry_points(group=PREVIEWER_ENTRY_POINT_GROUP)
        except Exception:
            logger.warning("Failed to enumerate '%s' entry points", PREVIEWER_ENTRY_POINT_GROUP, exc_info=True)
            return
        for ep in eps:
            try:
                factory = ep.load()
            except Exception:
                logger.warning("Failed to load previewer entry point '%s'", ep.name, exc_info=True)
                self._diagnostics.append(f"entry point '{ep.name}' failed to load")
                continue
            self._register_from_factory(ep.name, factory)

    def _scan_monorepo_packages(self) -> None:
        """Dev fallback: import ``packages/scistudio-blocks-*`` and call get_previewers().

        Mirrors :meth:`TypeRegistry._scan_monorepo_types` and
        :func:`blocks.registry._scan._scan_monorepo_packages`. ``__file__``
        sits at ``src/scistudio/previewers/registry.py`` so the repo root is
        ``parents[3]`` (previewers -> scistudio -> src -> root).
        """
        repo_root = Path(__file__).resolve().parents[3]
        packages_dir = repo_root / "packages"
        if not packages_dir.is_dir():
            return
        for pkg_dir in sorted(packages_dir.glob("scistudio-blocks-*")):
            src_dir = pkg_dir / "src"
            if not src_dir.is_dir():
                continue
            src_dir_str = str(src_dir)
            if src_dir_str not in sys.path:
                sys.path.insert(0, src_dir_str)
            module_name = pkg_dir.name.replace("-", "_")
            try:
                module = importlib.import_module(module_name)
            except Exception:
                logger.warning("Failed to import monorepo package '%s' for previewers", module_name, exc_info=True)
                continue
            factory = getattr(module, "get_previewers", None)
            if not callable(factory):
                continue
            self._register_from_factory(module_name, factory)

    def _register_from_factory(self, source: str, factory: Any) -> None:
        """Invoke a previewer entry-point/monorepo factory and register results."""
        try:
            specs = factory()
        except Exception:
            logger.warning("Previewer factory '%s' raised", source, exc_info=True)
            self._diagnostics.append(f"previewer factory '{source}' raised")
            return
        if not isinstance(specs, (list, tuple)):
            self._diagnostics.append(
                f"previewer factory '{source}' returned {type(specs).__name__}, expected list[PreviewerSpec]"
            )
            return
        for spec in specs:
            if not isinstance(spec, PreviewerSpec):
                self._diagnostics.append(f"previewer factory '{source}' returned non-PreviewerSpec item; skipping")
                continue
            self.register(spec)


__all__ = ["PREVIEWER_ENTRY_POINT_GROUP", "PreviewerRegistry"]
