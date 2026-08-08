"""Project-local and user-library previewer discovery + default declaration (ADR-048 FR-002/FR-005).

A project may register project-local previewers (backend Python providers plus
same-origin packaged assets) and declare an explicit default previewer for a
target type to resolve otherwise-ambiguous matches. The user library
(``~/.scistudio/previewers``) registers previewers the same way, in every
project, with no project open required (#2017) — the same tier rule blocks and
types already follow (ADR-053 FR-058/FR-060, :mod:`scistudio.core.dropins`).

Discovery surface (kept deliberately small per spec §4.5 risk mitigation):

* ``<project>/.scistudio/previewers.json`` — a declarative manifest listing
  project previewer specs and default-previewer declarations. Backend provider
  code is referenced by a ``module:callable`` import path resolved lazily, with
  the project-local ``previewers/`` directory re-activated on ``sys.path`` for
  the duration of the lazy import
  (:meth:`scistudio.previewers.session.PreviewSessionManager._resolve_provider`).
  The manifest-defaults path is project-only: FR-005 declares a *project*
  default, and the user tier deliberately has no manifest.
* A drop-in ``<project>/previewers/*.py`` or ``~/.scistudio/previewers/*.py``
  module exposing a module-level ``get_previewers() -> list[PreviewerSpec]``
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
    project_previewers_dir,
    user_previewers_dir,
)
from scistudio.desktop.paths import prepended_sys_paths
from scistudio.previewers.models import (
    OwnerKind,
    PreviewerSpec,
)
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.stability import internal

logger = logging.getLogger(__name__)

PROJECT_PREVIEWERS_DIR = "previewers"
PROJECT_PREVIEWERS_MANIFEST = ".scistudio/previewers.json"


@internal()
def load_project_previewers(registry: PreviewerRegistry, project_dir: Path | None) -> None:
    """Load project-local previewers + default declarations into *registry* (FR-002/FR-005).

    Best-effort: a missing project dir, missing manifest, or a broken drop-in
    is logged, recorded on the registry diagnostics, and skipped. Never raises.
    """
    if project_dir is None:
        return
    _load_manifest_defaults(registry, project_dir)
    _scan_previewer_dropins(registry, project_previewers_dir(project_dir), expected_owner=OwnerKind.PROJECT)


@internal()
def load_user_previewers(registry: PreviewerRegistry) -> None:
    """Load user-library previewers into *registry* (#2017).

    Unconditional, matching the user type/block tiers (ADR-053 FR-060): the
    user library is defined by the user's home directory and has no
    relationship to which project happens to be open. Best-effort like
    :func:`load_project_previewers`; never raises.
    """
    _scan_previewer_dropins(registry, user_previewers_dir(), expected_owner=OwnerKind.USER)


def _load_manifest_defaults(registry: PreviewerRegistry, project_dir: Path) -> None:
    manifest_path = project_dir / PROJECT_PREVIEWERS_MANIFEST
    if not manifest_path.is_file():
        return
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to read project previewers manifest at %s", manifest_path, exc_info=True)
        return
    defaults = data.get("default_previewers") if isinstance(data, dict) else None
    if isinstance(defaults, dict):
        for target_type, previewer_id in defaults.items():
            if isinstance(target_type, str) and isinstance(previewer_id, str):
                registry.set_project_default(target_type, previewer_id)


def _scan_previewer_dropins(
    registry: PreviewerRegistry,
    previewers_dir: Path,
    *,
    expected_owner: OwnerKind,
) -> None:
    """Scan one drop-in previewer directory into *registry* (shared project/user pass).

    The one implementation of the drop-in scan for both tiers (#2017); the
    guards come from :mod:`scistudio.core.dropins` so previewers enforce the
    same rules as blocks and types (#2044). See the module docstring for the
    guard list.
    """
    if not previewers_dir.is_dir():
        return

    # FR-016: refuse drop-in files whose stem an installed module owns, before
    # the directory joins sys.path for any exec below. The guard also binds (or
    # refuses outright) the shadowed name so the installed module keeps winning.
    collisions = guard_dropin_roots((previewers_dir,), dir_name=PREVIEWERS_DIR_NAME)
    refused = {collision.path for collision in collisions}
    for collision in collisions:
        logger.warning("Refusing previewer drop-in %s: %s", collision.path, collision.message)
        registry.record_diagnostic(collision.message)

    for py_file in sorted(previewers_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        if py_file in refused:
            continue
        mod_name = f"_scistudio_{expected_owner.value}_previewer_{py_file.stem}"
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
            with prepended_sys_paths((previewers_dir,)):
                spec.loader.exec_module(module)
        except KeyboardInterrupt:
            # The operator's own signal, not the drop-in's failure.
            raise
        except BaseException:
            # Skip-don't-crash on a failing/hostile drop-in. ``BaseException``
            # rather than ``Exception`` so a ``sys.exit()`` carried over from a
            # script is recorded and skipped instead of killing the scan.
            message = f"previewer drop-in '{py_file.name}' failed to import; skipping"
            logger.warning("Failed to import %s previewer drop-in %s", expected_owner.value, py_file, exc_info=True)
            registry.record_diagnostic(message)
            continue

        factory = getattr(module, "get_previewers", None)
        if not callable(factory):
            continue
        try:
            specs = factory()
        except KeyboardInterrupt:
            raise
        except BaseException:
            message = f"previewer drop-in '{py_file.name}' get_previewers() raised; skipping"
            logger.warning("Previewer drop-in %s get_previewers() raised", py_file, exc_info=True)
            registry.record_diagnostic(message)
            continue
        if not isinstance(specs, (list, tuple)):
            continue
        for ps in specs:
            if isinstance(ps, PreviewerSpec) and ps.owner_kind is expected_owner:
                registry.register(ps)
            elif isinstance(ps, PreviewerSpec):
                logger.warning(
                    "%s previewer %r declared owner_kind=%s, expected %s; skipping",
                    expected_owner.value.capitalize(),
                    ps.previewer_id,
                    ps.owner_kind.value,
                    expected_owner.value,
                )


__all__ = [
    "PROJECT_PREVIEWERS_DIR",
    "PROJECT_PREVIEWERS_MANIFEST",
    "load_project_previewers",
    "load_user_previewers",
]
