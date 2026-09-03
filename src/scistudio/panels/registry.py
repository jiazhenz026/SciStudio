"""PanelRegistry — core / package / project / user discovery (FR-002).

Loads :class:`PanelSpec` declarations from four tiers, in registration
order:

1. **core** — always loaded, unconditionally, from
   :func:`scistudio.panels.fallbacks.core_panel_specs`.
2. **package** — installed packages that ship a ``scistudio.previewers``
   entry point (``importlib.metadata.entry_points(group="scistudio.previewers")``),
   plus companion ``get_previewers()`` factories re-exported by installed
   block/type packages, plus bundled desktop source packages (FR-030).
3. **project** — project-local specs registered via
   :mod:`scistudio.panels.project`.
4. **user** — user-library specs from ``~/.scistudio/previewers`` (#2017),
   registered via :func:`scistudio.panels.project.load_user_panels`.

Registration is first-wins in this order, so a project spec shadows a
same-id user spec — the mirror of routing precedence, which the router
orders project > user > package > core.

Duplicate ``previewer_id`` across the loaded set is recorded as a diagnostic
and the subsequent registration is rejected (FR-006); a broken entry point is
logged and skipped, never crashing the registry (mirrors the block/type
registries).
"""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
from typing import Any

from scistudio.core.entry_points import (
    EntryPointDiagnostic,
    entry_point_module,
    entry_point_name,
    enumerate_group,
    load_entry_point,
    prepared_plugin_import_roots,
)
from scistudio.desktop.paths import (
    candidate_package_dirs,
    iter_source_package_module_candidates,
    prepended_sys_paths,
)
from scistudio.panels.models import (
    OwnerKind,
    PanelSpec,
)
from scistudio.stability import internal

logger = logging.getLogger(__name__)

PREVIEWER_ENTRY_POINT_GROUP = "scistudio.previewers"
COMPANION_ENTRY_POINT_GROUPS = ("scistudio.blocks", "scistudio.types")


@internal()
class PanelRegistry:
    """In-memory registry of :class:`PanelSpec` objects keyed by id.

    The registry holds specs only (no provider instances). Routing reads the
    full set via :meth:`all_specs`; the session manager resolves a single spec
    by id via :meth:`get`.
    """

    def __init__(self) -> None:
        self._by_id: dict[str, PanelSpec] = {}
        self._diagnostics: list[str] = []
        self._project_default_panels: dict[str, str] = {}
        # #2049: the person's own per-type choice, loaded from
        # :mod:`scistudio.panels.choices`. Distinct from the field above:
        # that one is the FR-005 project-author declaration and only breaks a
        # same-tier priority tie, while this one short-circuits the whole
        # FR-003 ladder. They are kept apart here for the same reason they are
        # kept in separate files.
        self._panel_choices: dict[str, str] = {}

    # -- registration -------------------------------------------------------

    def register(self, spec: PanelSpec) -> bool:
        """Register *spec*; reject duplicates with a diagnostic (FR-006).

        Returns ``True`` when the spec was added, ``False`` when a spec with
        the same ``previewer_id`` was already present.
        """
        if not spec.previewer_id:
            self._diagnostics.append("panel spec rejected: empty previewer_id")
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
        """Declare a project default panel for *target_type* (FR-005)."""
        self._project_default_panels[target_type] = previewer_id

    def set_panel_choices(self, choices: dict[str, str]) -> None:
        """Install the person's per-type panel choices (#2049).

        Replaces the set wholesale, because the caller loads both layers and
        resolves them together; a partial update here would let a cleared
        project-layer choice keep shadowing the user-layer one it overrode.
        """
        self._panel_choices = dict(choices)

    def record_diagnostic(self, message: str) -> None:
        """Record a discovery-scan diagnostic from an external scan pass.

        Used by the drop-in panel scan (#2044) so a refused or broken
        drop-in is surfaced through :attr:`diagnostics` rather than only
        logged — the same surfacing the block/type scans get.
        """
        self._diagnostics.append(message)

    # -- accessors ----------------------------------------------------------

    def get(self, previewer_id: str) -> PanelSpec | None:
        return self._by_id.get(previewer_id)

    def all_specs(self) -> list[PanelSpec]:
        return list(self._by_id.values())

    def specs_for_owner(self, owner_kind: OwnerKind) -> list[PanelSpec]:
        return [s for s in self._by_id.values() if s.owner_kind is owner_kind]

    def project_default_for(self, target_type: str) -> str | None:
        return self._project_default_panels.get(target_type)

    def choice_for(self, target_type: str) -> str | None:
        """Return the panel id chosen for *target_type*, if any (#2049)."""
        return self._panel_choices.get(target_type)

    def panel_choices(self) -> dict[str, str]:
        """Return a copy of the installed per-type choices (#2049)."""
        return dict(self._panel_choices)

    @property
    def diagnostics(self) -> list[str]:
        return list(self._diagnostics)

    def clear(self) -> None:
        self._by_id.clear()
        self._diagnostics.clear()
        self._project_default_panels.clear()
        self._panel_choices.clear()

    # -- discovery ----------------------------------------------------------

    def load_core(self) -> None:
        """Load the core fallback panel specs unconditionally (FR-002)."""
        from scistudio.panels.fallbacks import core_panel_specs

        for spec in core_panel_specs():
            self.register(spec)

    def load_packages(self) -> None:
        """Load package panels from entry points (FR-002/FR-030).

        The entry-point scans run with the user-installed plugin import roots
        activated on ``sys.path`` (their ``site-packages`` carry the dist-info),
        so ``importlib.metadata.entry_points()`` can actually see installed
        plugins' ``scistudio.previewers`` entry points. Without this the
        canonical entry-point path silently finds nothing in the packaged app —
        the plugin ``site-packages`` is off ``sys.path`` — and panel
        discovery falls entirely to the source-dir scan fallback (#1752).

        ADR-053 FR-030: that activation is no longer this registry's private
        arrangement. :func:`scistudio.core.entry_points.prepared_plugin_import_roots`
        is the one answer and the block and type scans now use it too, so the
        same installed package cannot resolve for panels and vanish for
        blocks.
        """
        with prepared_plugin_import_roots():
            self._scan_entry_points()
            self._scan_companion_entry_point_packages()
        self._scan_package_src_dirs()

    def _scan_entry_points(self) -> None:
        """Scan the canonical ``scistudio.previewers`` group (FR-002).

        ADR-053 FR-025: enumeration, load, and error containment come from
        :mod:`scistudio.core.entry_points`. What stays here is registration —
        which ids win, what a :class:`PanelSpec` must be — in
        :meth:`_register_from_factory`.
        """
        diagnostics: list[EntryPointDiagnostic] = []
        eps = enumerate_group(PREVIEWER_ENTRY_POINT_GROUP, diagnostics=diagnostics)
        for ep in eps:
            factory = load_entry_point(ep, PREVIEWER_ENTRY_POINT_GROUP, diagnostics=diagnostics)
            if factory is None:
                continue
            self._register_from_factory(entry_point_name(ep), factory)
        self._diagnostics.extend(str(diagnostic) for diagnostic in diagnostics)

    def _scan_companion_entry_point_packages(self) -> None:
        """Discover panels re-exported by installed block/type packages.

        Some package installs can expose ``scistudio.blocks`` / ``scistudio.types``
        entry points while their installed metadata is missing the newer
        ``scistudio.previewers`` group. Treat an already-declared SciStudio
        package as an authoritative companion source and call its conventional
        ``get_previewers()`` factory when present. Explicit panel entry
        points remain authoritative because existing ids are skipped silently.

        **This is the one permitted asymmetry (ADR-053 FR-032), and it is
        history rather than a pattern.** Reading one group's entry points to
        find another group's contribution exists only because installed
        metadata written before ``scistudio.previewers`` existed cannot declare
        it, and rewriting a user's installed ``dist-info`` is not something the
        product may do. That reason expires with those installs; it does not
        generalise. A subsequent group has no such history, so this fallback
        MUST NOT be extended to ``scistudio.tutorials`` or to any other new
        group — for tutorials it could not be, in any case, because it works by
        importing the companion module and FR-018 forbids importing a package
        module while listing the catalogue.

        Enumeration still goes through the shared helper: the exemption is
        about *what* is scanned, never about error containment.
        """
        diagnostics: list[EntryPointDiagnostic] = []
        seen_modules: set[str] = set()
        for group in COMPANION_ENTRY_POINT_GROUPS:
            eps = enumerate_group(group, diagnostics=diagnostics)

            for ep in eps:
                root_name = _entry_point_root_module(ep)
                if not root_name:
                    continue
                for module_name in (root_name, f"{root_name}.previewers"):
                    if module_name in seen_modules:
                        continue
                    seen_modules.add(module_name)
                    try:
                        module = importlib.import_module(module_name)
                    except ModuleNotFoundError as exc:
                        if exc.name != module_name:
                            logger.debug(
                                "Companion panel import failed for '%s'",
                                module_name,
                                exc_info=True,
                            )
                        continue
                    except Exception:
                        logger.debug(
                            "Companion panel import failed for '%s'",
                            module_name,
                            exc_info=True,
                        )
                        continue

                    factory = getattr(module, "get_previewers", None)
                    if not callable(factory):
                        continue
                    self._register_from_factory(
                        f"{group}:{entry_point_name(ep)}:{module_name}",
                        factory,
                        skip_existing=True,
                    )
                    break
        self._diagnostics.extend(str(diagnostic) for diagnostic in diagnostics)

    def _scan_package_src_dirs(self) -> None:
        """Discover desktop/installed source-package panels via ``get_previewers()``."""
        # Issue #1885: scan candidate_package_dirs() unconditionally — matching
        # block/type discovery — so a plugin's panels register from the same
        # module-glob pass as its blocks. This used to be gated behind
        # SCISTUDIO_BUNDLED, which dropped plugin panels in a non-bundled
        # desktop run. Explicit entry-point registrations still win because
        # registration below uses skip_existing=True.
        package_dirs = candidate_package_dirs()
        registered_roots: set[str] = set()
        candidates = iter_source_package_module_candidates(package_dirs, module_suffixes=("previewers",))
        for root_name, module_name, import_roots in candidates:
            if root_name in registered_roots:
                continue
            try:
                with prepended_sys_paths(import_roots):
                    module = importlib.import_module(module_name)
            except ModuleNotFoundError as exc:
                if exc.name != module_name:
                    logger.debug(
                        "Source package panel import failed for '%s'",
                        module_name,
                        exc_info=True,
                    )
                continue
            except Exception:
                logger.debug(
                    "Source package panel import failed for '%s'",
                    module_name,
                    exc_info=True,
                )
                continue

            factory = getattr(module, "get_previewers", None)
            if not callable(factory):
                continue
            self._register_from_factory(
                f"package_src:{module_name}",
                factory,
                skip_existing=True,
            )
            registered_roots.add(root_name)

    def _register_from_factory(self, source: str, factory: Any, *, skip_existing: bool = False) -> None:
        """Invoke a panel entry-point/monorepo factory and register results."""
        try:
            specs = factory()
        except Exception:
            logger.warning("Panel factory '%s' raised", source, exc_info=True)
            self._diagnostics.append(f"panel factory '{source}' raised")
            return
        if not isinstance(specs, (list, tuple)):
            self._diagnostics.append(
                f"panel factory '{source}' returned {type(specs).__name__}, expected list[PanelSpec]"
            )
            return
        for spec in specs:
            if not isinstance(spec, PanelSpec):
                self._diagnostics.append(f"panel factory '{source}' returned non-PanelSpec item; skipping")
                continue
            if skip_existing and spec.previewer_id in self._by_id:
                continue
            self.register(spec)


def _entry_point_root_module(ep: importlib.metadata.EntryPoint) -> str | None:
    """Return the top-level module named by an entry point value.

    The companion fallback wants the distribution's *root* package so it can
    try ``pkg`` and ``pkg.panels``, where the rest of the product wants the
    module the value actually names. ADR-053 FR-025 puts that shared parse in
    :func:`scistudio.core.entry_points.entry_point_module`; the extra step here
    is the truncation to the first segment, which is this fallback's own.
    """
    module_name = entry_point_module(ep)
    if not module_name:
        return None
    return module_name.split(".", 1)[0]


__all__ = ["COMPANION_ENTRY_POINT_GROUPS", "PREVIEWER_ENTRY_POINT_GROUP", "PanelRegistry"]
