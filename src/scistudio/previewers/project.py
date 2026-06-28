"""Project-local previewer discovery + default declaration (ADR-048 FR-002/FR-005).

A project may register project-local previewers (backend Python providers plus
same-origin packaged assets) and declare an explicit default previewer for a
target type to resolve otherwise-ambiguous matches.

Discovery surface (kept deliberately small per spec §4.5 risk mitigation):

* ``<project>/.scistudio/previewers.json`` — a declarative manifest listing
  project previewer specs and default-previewer declarations. Backend provider
  code is referenced by a ``module:callable`` import path resolved lazily, and
  the file path is loaded from a project-local ``previewers/`` directory placed
  on ``sys.path`` so a project can ship Python providers without installing a
  package.
* A drop-in ``<project>/previewers/*.py`` module exposing a module-level
  ``get_previewers() -> list[PreviewerSpec]`` callable (same protocol as the
  package entry point), mirroring the type/block drop-in scan dirs (#1332).

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
    is logged and skipped. Never raises.
    """
    if project_dir is None:
        return
    _load_manifest_defaults(registry, project_dir)
    _scan_project_dropins(registry, project_dir)


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


def _scan_project_dropins(registry: PreviewerRegistry, project_dir: Path) -> None:
    previewers_dir = project_dir / PROJECT_PREVIEWERS_DIR
    if not previewers_dir.is_dir():
        return
    # Make the dir importable so providers referenced by module path resolve.
    if str(previewers_dir) not in sys.path:
        sys.path.insert(0, str(previewers_dir))

    for py_file in sorted(previewers_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            mod_name = f"_scistudio_project_previewer_{py_file.stem}"
            spec = importlib.util.spec_from_file_location(mod_name, py_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        except Exception:
            logger.warning("Failed to import project previewer drop-in %s", py_file, exc_info=True)
            continue

        factory = getattr(module, "get_previewers", None)
        if not callable(factory):
            continue
        try:
            specs = factory()
        except Exception:
            logger.warning("Project previewer drop-in %s get_previewers() raised", py_file, exc_info=True)
            continue
        if not isinstance(specs, (list, tuple)):
            continue
        for ps in specs:
            if isinstance(ps, PreviewerSpec) and ps.owner_kind is OwnerKind.PROJECT:
                registry.register(ps)
            elif isinstance(ps, PreviewerSpec):
                logger.warning(
                    "Project previewer %r declared owner_kind=%s, expected project; skipping",
                    ps.previewer_id,
                    ps.owner_kind.value,
                )


__all__ = [
    "PROJECT_PREVIEWERS_DIR",
    "PROJECT_PREVIEWERS_MANIFEST",
    "load_project_previewers",
]
