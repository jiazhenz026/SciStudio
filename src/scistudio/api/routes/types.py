"""Registered data type listing and the data-type template (ADR-053 §7).

The Data types tab and the canvas both read type colour from here, and
:func:`list_types` is the only endpoint that reports it (FR-050). Before this
router, type information reached the frontend only as ``type_hierarchy`` riding
on the block *schema* response — with no origin tier, no file path, and a
``ui_ring_color`` field nothing ever populated. FR-027 makes the two
independent: the Data types tab must not have to fetch blocks to draw types,
and refreshing types must not mean refreshing the palette.

``type_hierarchy`` is deliberately left exactly as it was. FR-066 moves canvas
port colour onto this endpoint rather than adding a colour field to
``TypeHierarchyEntry``, because two supply points for one fact are what this
work exists to remove; the dead ``ui_ring_color`` field stays dead.

Everything here is derived, never stored. Origin comes from the shared resolver
(:func:`scistudio.api._block_source.resolve_origin`, FR-003), colour from the
type registry's validated collection (FR-050/FR-052), extensions from the IO
format capability table (FR-054), and the owning package name from the block
registry's own record of it (FR-040) so the two tabs cannot title one
distribution two ways. This module owns no rule of its own — it asks four
existing sources one question each and assembles the answer.
"""

from __future__ import annotations

import importlib.resources as importlib_resources
import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from scistudio.api._block_source import PACKAGE_ORIGIN, TYPE_SURFACE, resolve_origin
from scistudio.api.deps import get_block_registry, get_type_registry
from scistudio.api.routes.blocks import (
    _active_project_dir,
    _is_plugin_package,
    get_optional_runtime,
)
from scistudio.api.schemas import (
    TypeListResponse,
    TypeSummary,
    TypeTemplateResponse,
)
from scistudio.blocks.io._config_enrichment import format_extensions_by_type

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/types", tags=["types"])
BlockRegistryDep = Annotated[Any, Depends(get_block_registry)]
TypeRegistryDep = Annotated[Any, Depends(get_type_registry)]
OptionalRuntimeDep = Annotated[Any, Depends(get_optional_runtime)]

# ADR-053 FR-028 — only ``basic`` is recognised today. A future kind adds a
# template file and stays schema-compatible, exactly as the block template
# endpoint does.
_KNOWN_TEMPLATES: dict[str, tuple[str, str]] = {
    # kind -> (resource filename, suggested user-facing filename)
    "basic": ("type_base_template.py", "my_data_type.py"),
}

_TEMPLATE_PACKAGE = "scistudio.core.types._templates"


def _type_origin(spec: Any, project_dir: Path | None) -> str:
    """Return the FR-005 origin tier of one type registry spec.

    The type-side adapter over :func:`resolve_origin`, the counterpart of
    ``map_block_origin`` and holding no rule of its own: FR-003 requires one
    implementation for both surfaces, so a second path comparison here is
    precisely what must not exist.

    Two spec fields need translating. A file path is passed only for a drop-in,
    because the resolver reads a path as "this is a file in a tier, decide
    which" — and every type has a file, including the core ones, which live in
    no tier at all. ``is_dropin`` then carries the case the path cannot: a
    drop-in registers under a synthetic module name that is not an import path,
    so without the flag it would read as a plugin distribution instead of
    falling back to ``custom``.
    """
    is_dropin = bool(getattr(spec, "is_dropin", False))
    return resolve_origin(
        TYPE_SURFACE,
        file_path=(getattr(spec, "file_path", "") or None) if is_dropin else None,
        module_path=getattr(spec, "module_path", "") or "",
        is_dropin=is_dropin,
        project_dir=project_dir,
    )


#: Sentinel for an import root two differently-named distributions both claim.
#: Naming such a package would mean picking one of two right answers, so the
#: listing declines and the type falls back to the lumped section.
_AMBIGUOUS = ""


def package_names_by_import_root(block_registry: Any) -> dict[str, str]:
    """Map each import root to the package name the Blocks tab shows for it.

    ADR-053 FR-040. The Data types tab must title a package exactly as the
    Blocks tab does, and the only way to guarantee that is to report the same
    string rather than a second string derived to look like it — an inferred
    name that disagreed with the block side for one distribution would be worse
    than the single lumped section it replaced.

    ``BlockSpec`` carries both the resolved package name and the module its
    class came from, so the block registry already records import root ->
    package name for every installed distribution that ships blocks. Types join
    on the import root (:attr:`~scistudio.core.types.registry.TypeSpec.package_root`)
    because that is the one handle the two registries share.

    Only names the block *listing* keeps are included, via the same
    :func:`~scistudio.api.routes.blocks._is_plugin_package` predicate: a name
    that route blanks is one the Blocks tab never shows, so honouring it here
    would invent a section the other tab does not have.
    """
    names: dict[str, str] = {}
    for spec in block_registry.all_specs().values():
        name = getattr(spec, "package_name", "") or ""
        root = (getattr(spec, "module_path", "") or "").split(".")[0]
        if not root or not _is_plugin_package(name):
            continue
        known = names.setdefault(root, name)
        if known != name:
            names[root] = _AMBIGUOUS
    return names


def _package_name(spec: Any, origin: str, names: dict[str, str]) -> str | None:
    """Return the distribution a package-tier type belongs to, or ``None``.

    ``None`` covers core, the two drop-in tiers, the ``custom`` fallback, and a
    package whose distribution the block side does not name — the last of which
    keeps the type in the lumped section rather than dropping it (FR-040).
    """
    if origin != PACKAGE_ORIGIN:
        return None
    return names.get(getattr(spec, "package_root", "") or "") or None


def _summary(
    spec: Any,
    *,
    project_dir: Path | None,
    package_names: dict[str, str],
    load_extensions: dict[str, list[str]],
    save_extensions: dict[str, list[str]],
) -> TypeSummary:
    """Assemble one :class:`TypeSummary` from a type spec and the IO tables."""
    name = spec.name
    origin = _type_origin(spec, project_dir)
    return TypeSummary(
        name=name,
        base_type=getattr(spec, "base_type", "") or "",
        description=getattr(spec, "description", "") or "",
        origin=origin,
        package_name=_package_name(spec, origin, package_names),
        file_path=getattr(spec, "file_path", "") or None,
        ui_color=getattr(spec, "ui_color", None),
        ui_ring_color=getattr(spec, "ui_ring_color", None),
        # FR-056: a type with no capability reports an empty list rather than
        # omitting the field, so the popover can say "no file formats
        # registered" instead of leaving a silent gap.
        load_extensions=load_extensions.get(name, []),
        save_extensions=save_extensions.get(name, []),
    )


@router.get("/template", response_model=TypeTemplateResponse)
async def get_type_template(kind: str = "basic") -> TypeTemplateResponse:
    """Return the source of a starter template for a new data type.

    ADR-053 FR-028. The response shape matches ``GET /api/blocks/template``
    exactly so the new-block and new-data-type flows can share their
    fetch-write-open steps (FR-033); only the template kind and the target
    subdirectory differ.

    Declared as the first route on this router so it stays ahead of any future
    ``/{type_name}`` path, which would otherwise swallow it.

    Returns HTTP 400 for an unknown ``kind``, and HTTP 500 if the bundled
    template asset is missing from the installation.
    """
    if kind not in _KNOWN_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown template kind: {kind!r}. Known: {sorted(_KNOWN_TEMPLATES)}",
        )

    resource_name, suggested = _KNOWN_TEMPLATES[kind]
    try:
        template_dir = importlib_resources.files(_TEMPLATE_PACKAGE)
        content = (template_dir / resource_name).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
        logger.exception("ADR-053 FR-028: template asset %s missing", resource_name)
        raise HTTPException(
            status_code=500,
            detail=f"Template asset {resource_name!r} missing from package",
        ) from exc

    return TypeTemplateResponse(kind=kind, content=content, suggested_filename=suggested)


@router.get("/", response_model=TypeListResponse)
@router.get("", response_model=TypeListResponse, include_in_schema=False)
async def list_types(
    registry: BlockRegistryDep,
    type_registry: TypeRegistryDep,
    runtime: OptionalRuntimeDep,
) -> TypeListResponse:
    """Return every registered data type, with origin, colour, and extensions.

    ADR-053 FR-026. Answered entirely from the two registries this request
    already has, so it costs no scan and can be re-fetched on every reload
    event without the Data types tab needing a block request (FR-027).

    Both extension tables and the import-root -> package-name map are built
    once per request rather than per type: the capability list is walked twice
    and the block registry once, not once per registered type.

    The listing is sorted by name. The palette groups by origin tier itself
    (FR-038), and a name sort is the ordering that stays stable when a type's
    tier changes underneath it.
    """
    project_dir = _active_project_dir(runtime)
    load_extensions = format_extensions_by_type(registry, direction="load")
    save_extensions = format_extensions_by_type(registry, direction="save")
    package_names = package_names_by_import_root(registry)
    types = [
        _summary(
            spec,
            project_dir=project_dir,
            package_names=package_names,
            load_extensions=load_extensions,
            save_extensions=save_extensions,
        )
        for spec in type_registry.all_types().values()
    ]
    types.sort(key=lambda item: item.name)
    return TypeListResponse(types=types)
