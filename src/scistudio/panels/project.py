"""Project-local and user-library panel discovery + default declaration (ADR-048 FR-002/FR-005).

A project may register project-local panels (backend Python providers plus
same-origin packaged assets) and declare an explicit default panel for a
target type to resolve otherwise-ambiguous matches. The user library
(``~/.scistudio/previewers``) registers panels the same way, in every
project, with no project open required (#2017) — the same tier rule blocks and
types already follow (ADR-053 FR-058/FR-060, :mod:`scistudio.core.dropins`).
For a tutorial project the user tier is the tutorial-scoped library's
``panels/`` directory rather than ``~/.scistudio/previewers`` (Learning
Center FR-070/FR-071, #2086) — the same one-root swap the block and type scans
make through :func:`scistudio.core.dropins.library_root_for_project`.

Discovery surface (kept deliberately small per spec §4.5 risk mitigation):

* ``<project>/.scistudio/panels.json`` — a declarative manifest declaring
  default-panel tie-breakers (FR-005); it does not register panel
  specs. ADR-054 spec 1 FR-046 carries this file over under the panel naming
  with its behaviour unchanged, and FR-020 keeps the file it used to be called,
  ``previewers.json``, working for projects that already exist on disk. **When
  both are present the panel-named one is used, entire, and the older one is
  ignored with a diagnostic saying so.** Not merged: two files declaring the
  same defaults produce a state neither of them describes, and "which file am I
  editing" then has no answer. The older file is never rewritten or deleted, so
  a project opened by an earlier build finds it exactly as it was. Drop-in provider code may also be referenced by a ``module:callable``
  import path resolved lazily at render time against the spec's **owning**
  tier directory — imported by file path under a synthetic name, so no
  bare-stem ``sys.modules`` entry crosses tier boundaries
  (:meth:`scistudio.panels.session.PreviewSessionManager._resolve_provider`).
  The manifest-defaults path is project-only: FR-005 declares a *project*
  default, and the user tier deliberately has no manifest.
* A drop-in ``<project>/previewers/*.py`` or ``~/.scistudio/previewers/*.py``
  module exposing a module-level ``get_previewers() -> list[PanelSpec]``
  callable (same protocol as the package entry point), mirroring the type/block
  drop-in scan dirs (#1332).

The drop-in scan is the third consumer of :mod:`scistudio.core.dropins`
(#2044), so it carries the same guards as the blocks/types scans rather than a
fourth copy of the rule: the FR-016 name-collision guard refuses a drop-in file
whose stem an installed module owns (underscore-prefixed names included in the
collision question, skipped only for registration), the ``sys.path``
activation is scoped to each module exec through
:func:`scistudio.desktop.paths.prepended_sys_paths` instead of a permanent
``sys.path.insert``, stale bytecode is evicted before every load (FR-062), a
``BaseException`` (e.g. a stray ``sys.exit()``) in one drop-in cannot kill the
scan, and every refusal/import failure is recorded on the registry diagnostics
instead of only being logged.

Project-local React build tooling is intentionally NOT auto-loaded; only
backend Python providers + path-confined same-origin assets are wired here
(spec §4.5).
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path

from scistudio.core.dropins import (
    PREVIEWERS_DIR_NAME,
    evict_cached_bytecode,
    guard_dropin_roots,
    panel_scan_dirs,
    project_panels_dir,
    transient_dropin_modules,
)
from scistudio.desktop.paths import prepended_sys_paths
from scistudio.panels.models import (
    OwnerKind,
    PanelSpec,
)
from scistudio.panels.registry import PanelRegistry
from scistudio.stability import internal

logger = logging.getLogger(__name__)

PROJECT_PANELS_DIR = "previewers"

#: The project's default-panel declaration, under the panel naming (FR-046).
PROJECT_PANELS_MANIFEST = ".scistudio/panels.json"

#: The name that file had before the rename. Read when the panel-named one is
#: absent, so a project written by an earlier build keeps its defaults (FR-020).
LEGACY_PROJECT_PANELS_MANIFEST = ".scistudio/previewers.json"


@internal()
def load_project_panels(registry: PanelRegistry, project_dir: Path | None) -> None:
    """Load project-local panels + default declarations into *registry* (FR-002/FR-005).

    Best-effort: a missing project dir, missing manifest, or a broken drop-in
    is logged, recorded on the registry diagnostics, and skipped. Never raises.
    """
    if project_dir is None:
        return
    _load_manifest_defaults(registry, project_dir)
    _scan_panel_dropins(registry, project_panels_dir(project_dir), expected_owner=OwnerKind.PROJECT)


@internal()
def load_user_panels(registry: PanelRegistry, project_dir: Path | None = None) -> None:
    """Load user-library panels into *registry* (#2017).

    Unconditional, matching the user type/block tiers (ADR-053 FR-060): the
    user tier does not require an open project. *Which* library answers as the
    user tier does follow the open project, though (Learning Center
    FR-070/FR-071, #2086): a tutorial project's user tier is the
    tutorial-scoped library, so the root is read off
    :func:`scistudio.core.dropins.panel_scan_dirs` — the same tuple the
    session manager reads its owning roots from — rather than recomputed as
    ``~/.scistudio/previewers``. Scoped-library panels therefore register
    as ``OwnerKind.USER``, riding the user-tier slot in the routing precedence
    (project > user > package > core) instead of adding a fifth tier.
    Best-effort like :func:`load_project_panels`; never raises.
    """
    _scan_panel_dropins(registry, panel_scan_dirs(project_dir)[-1], expected_owner=OwnerKind.USER)


def _load_manifest_defaults(registry: PanelRegistry, project_dir: Path) -> None:
    """Install the project's declared default panels (FR-005, FR-046, FR-020).

    Exactly one file is in effect. The panel-named one wins whenever it exists,
    and the older ``previewers.json`` is then ignored with a diagnostic naming
    both — a person who copied one to the other and edited the copy has to be
    able to tell which of them the product is reading.
    """
    manifest_path = project_dir / PROJECT_PANELS_MANIFEST
    legacy_path = project_dir / LEGACY_PROJECT_PANELS_MANIFEST
    if manifest_path.is_file():
        if legacy_path.is_file():
            message = (
                f"project declares default panels in both {PROJECT_PANELS_MANIFEST} and "
                f"{LEGACY_PROJECT_PANELS_MANIFEST}; reading {PROJECT_PANELS_MANIFEST} and "
                f"ignoring the other"
            )
            logger.warning("%s (%s)", message, project_dir)
            registry.record_diagnostic(message)
    elif legacy_path.is_file():
        manifest_path = legacy_path
    else:
        return

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to read project panels manifest at %s", manifest_path, exc_info=True)
        return
    defaults = data.get("default_panels") if isinstance(data, dict) else None
    if isinstance(defaults, dict):
        for target_type, previewer_id in defaults.items():
            if isinstance(target_type, str) and isinstance(previewer_id, str):
                registry.set_project_default(target_type, previewer_id)


def _scan_panel_dropins(
    registry: PanelRegistry,
    panels_dir: Path,
    *,
    expected_owner: OwnerKind,
) -> None:
    """Scan one drop-in panel directory into *registry* (shared project/user pass).

    The one implementation of the drop-in scan for both tiers (#2017); the
    guards come from :mod:`scistudio.core.dropins` so panels enforce the
    same rules as blocks and types (#2044). See the module docstring for the
    guard list.
    """
    if not panels_dir.is_dir():
        return

    # FR-016: refuse drop-in files whose stem an installed module owns, before
    # the directory joins sys.path for any exec below. The guard also binds (or
    # refuses outright) the shadowed name so the installed module keeps winning.
    collisions = guard_dropin_roots((panels_dir,), dir_name=PREVIEWERS_DIR_NAME)
    refused = {collision.path for collision in collisions}
    for collision in collisions:
        logger.warning("Refusing panel drop-in %s: %s", collision.path, collision.message)
        registry.record_diagnostic(collision.message)

    for py_file in sorted(panels_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        if py_file in refused:
            continue
        mod_name = f"_scistudio_{expected_owner.value}_panel_{py_file.stem}"
        spec = importlib.util.spec_from_file_location(mod_name, py_file)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        # FR-062: a drop-in edited within one second of its last load, to the
        # same length, would otherwise re-execute the previous bytecode.
        evict_cached_bytecode(py_file)
        try:
            # Scoped sys.path activation so the drop-in's sibling imports
            # resolve during exec — never a permanent sys.path.insert (#2044).
            # The sibling imports leave with the window too: a bare-stem
            # module cached from this tier's directory would otherwise answer
            # for the next tier's same-named file and turn the FR-016 guard's
            # verdicts into false refusals (#2017, PR #2072 audit).
            with prepended_sys_paths((panels_dir,)), transient_dropin_modules((panels_dir,)):
                spec.loader.exec_module(module)
        except KeyboardInterrupt:
            # The operator's own signal, not the drop-in's failure.
            raise
        except BaseException:
            # Skip-don't-crash on a failing/hostile drop-in. ``BaseException``
            # rather than ``Exception`` so a ``sys.exit()`` carried over from a
            # script is recorded and skipped instead of killing the scan. The
            # half-executed module leaves ``sys.modules`` with it, so its
            # residue cannot answer for anything afterwards.
            sys.modules.pop(spec.name, None)
            message = f"panel drop-in '{py_file.name}' failed to import; skipping"
            logger.warning("Failed to import %s panel drop-in %s", expected_owner.value, py_file, exc_info=True)
            registry.record_diagnostic(message)
            continue

        factory = getattr(module, "get_previewers", None)
        if not callable(factory):
            continue
        try:
            # The factory runs inside the same scoped window as the exec: a
            # drop-in may defer a sibling import into ``get_previewers()``
            # rather than the module top level, and that import must resolve
            # (and clean up) exactly as a top-level one does (#2072 review).
            with prepended_sys_paths((panels_dir,)), transient_dropin_modules((panels_dir,)):
                specs = factory()
        except KeyboardInterrupt:
            raise
        except BaseException:
            message = f"panel drop-in '{py_file.name}' get_previewers() raised; skipping"
            logger.warning("Panel drop-in %s get_previewers() raised", py_file, exc_info=True)
            registry.record_diagnostic(message)
            continue
        if not isinstance(specs, (list, tuple)):
            continue
        for ps in specs:
            if isinstance(ps, PanelSpec) and ps.owner_kind is expected_owner:
                registry.register(ps)
            elif isinstance(ps, PanelSpec):
                # Recorded like every other refusal in this pass: a silently
                # log-only skip would contradict the "every refusal is
                # surfaced on diagnostics" contract the scan documents.
                message = (
                    f"panel {ps.previewer_id!r} declared owner_kind={ps.owner_kind.value}, "
                    f"expected {expected_owner.value}; skipping"
                )
                logger.warning(
                    "%s panel %r declared owner_kind=%s, expected %s; skipping",
                    expected_owner.value.capitalize(),
                    ps.previewer_id,
                    ps.owner_kind.value,
                    expected_owner.value,
                )
                registry.record_diagnostic(message)


__all__ = [
    "LEGACY_PROJECT_PANELS_MANIFEST",
    "PROJECT_PANELS_DIR",
    "PROJECT_PANELS_MANIFEST",
    "load_project_panels",
    "load_user_panels",
]
