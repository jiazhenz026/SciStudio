"""Block palette listing and connection validation endpoints."""

from __future__ import annotations

import importlib.resources as importlib_resources
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from scieasy.api.deps import get_block_registry, get_type_registry
from scieasy.api.schemas import (
    BlockConnectionValidation,
    BlockListResponse,
    BlockPortResponse,
    BlockSchemaResponse,
    BlockSummary,
    ConnectionValidationResponse,
    TypeHierarchyEntry,
)
from scieasy.blocks.base.ports import InputPort, OutputPort, validate_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/blocks", tags=["blocks"])
BlockRegistryDep = Annotated[Any, Depends(get_block_registry)]
TypeRegistryDep = Annotated[Any, Depends(get_type_registry)]


def _port_response(port: Any, *, direction: str) -> BlockPortResponse:
    return BlockPortResponse(
        name=port.name,
        direction=direction,
        accepted_types=[accepted.__name__ for accepted in getattr(port, "accepted_types", [])],
        required=getattr(port, "required", True),
        description=getattr(port, "description", ""),
        constraint_description=getattr(port, "constraint_description", ""),
        is_collection=getattr(port, "is_collection", False),
    )


def _config_schema_for_block(spec: Any) -> dict[str, Any]:
    return spec.config_schema or {"type": "object", "properties": {}}


def _map_source(raw: str) -> str:
    """Map internal source labels to palette-friendly values.

    tier1 -> "custom" (project-local hot-loaded blocks)
    entry_point / monorepo -> "package" (installed plugin blocks)
    builtin -> "builtin" (core blocks)
    """
    if raw == "tier1":
        return "custom"
    if raw in ("entry_point", "monorepo"):
        return "package"
    if raw == "builtin":
        return "builtin"
    return raw


def _is_plugin_package(name: str) -> bool:
    """Return True if *name* looks like an external plugin package.

    Convention: plugin packages are named ``scieasy-blocks-<domain>``
    (e.g. ``scieasy-blocks-imaging``).  Everything else (individual
    entry-point names like ``ai_block``, ``code_block``, or empty
    strings) is a core block and should be grouped under the default
    "SciEasy Core" header in the palette.
    """
    return name.startswith("scieasy-blocks-")


def _summary(spec: Any) -> BlockSummary:
    raw_pkg = getattr(spec, "package_name", "") or ""
    # Only keep the package_name for genuine plugin packages so the
    # frontend groups core blocks together under "SciEasy Core".
    package_name = raw_pkg if _is_plugin_package(raw_pkg) else ""
    return BlockSummary(
        name=spec.name,
        type_name=spec.type_name,
        base_category=spec.base_category,
        subcategory=spec.subcategory,
        description=spec.description,
        version=spec.version,
        input_ports=[_port_response(port, direction="input") for port in spec.input_ports],
        output_ports=[_port_response(port, direction="output") for port in spec.output_ports],
        direction=spec.direction or None,
        source=_map_source(getattr(spec, "source", "") or ""),
        package_name=package_name,
        variadic_inputs=bool(getattr(spec, "variadic_inputs", False)),
        variadic_outputs=bool(getattr(spec, "variadic_outputs", False)),
    )


@router.get("/", response_model=BlockListResponse)
async def list_blocks(registry: BlockRegistryDep) -> BlockListResponse:
    """Return the full block palette available in the current registry."""
    blocks = [_summary(spec) for spec in registry.all_specs().values()]
    blocks.sort(key=lambda item: (item.base_category, item.subcategory, item.name))
    return BlockListResponse(blocks=blocks)


# ---------------------------------------------------------------------------
# ADR-036 §3.12 — block template endpoint (skeleton, returns 501)
#
# The "New custom block" toolbar action (see ADR-036 §3.7) needs a starter
# template that already wires up imports, ports, and a placeholder ``run()``
# body. Rather than ship the template content in the frontend, we ship it
# next to the package (``src/scieasy/blocks/_templates/``) and serve it via
# this endpoint so the template stays in lockstep with whatever
# ``scieasy.blocks.base`` actually exports.
#
# IMPORTANT — route ordering:
# ``/template`` MUST be declared BEFORE the greedy ``/{block_type}``
# (and ``/{block_type}/schema``) routes below. FastAPI matches in
# declaration order; otherwise ``/api/blocks/template`` is swallowed by
# ``get_block_schema`` with ``block_type="template"`` and never reaches
# this handler. See ADR-036 audit
# (docs/audit/2026-05-14-adr-036-skeleton.md, finding P1-2) for details.
# ---------------------------------------------------------------------------


class BlockTemplateResponse(BaseModel):
    """Skeleton — response shape for GET /api/blocks/template (per ADR-036 §3.12)."""

    kind: str
    content: str
    suggested_filename: str


# ADR-036 §3.12 — only "basic" is recognised in v1. Future kinds
# (e.g. "io", "ai") add new template files but stay schema-compatible.
# Kept module-level so tests + future template kinds can extend it
# without re-defining inside the handler.
_KNOWN_TEMPLATES: dict[str, tuple[str, str]] = {
    # kind -> (resource filename, suggested user-facing filename)
    "basic": ("block_base_template.py", "my_block.py"),
}


@router.get("/template", response_model=BlockTemplateResponse)
async def get_block_template(kind: str = "basic") -> BlockTemplateResponse:
    """Serve a block-scaffolding template. (ADR-036 §3.12 — SKELETON)

    Implementation plan (per ADR-036 §3.12):
      1. Validate ``kind`` against a known set (initially just ``"basic"``).
         Unknown kind -> HTTP 400.
      2. Resolve the template file inside the package via
         ``importlib.resources.files("scieasy.blocks._templates") /
         "block_base_template.py"``.
      3. Read with ``encoding="utf-8"`` and return content + suggested
         filename (default ``"my_block.py"``).
      4. The frontend pipes ``content`` to PUT /api/projects/{id}/file with
         path ``"blocks/<user-supplied-name>.py"``, then opens an editor
         tab on the new file. None of that orchestration belongs here —
         this endpoint is content-only.

    Edge cases:
      - kind not in known set -> HTTP 400.
      - Template file missing from package (deployment bug) -> HTTP 500
        with a clear "template asset missing" message.

    Test plan (must be added by I36c):
      - test_template_basic_returns_python_with_correct_imports: response
        content contains the literal string
        ``"from scieasy.blocks.base import Block, BlockSpec, PortSpec"``.
      - test_template_basic_has_run_marker: response content contains
        ``"# >>> EDIT THIS <<<"``.
      - test_template_unknown_kind_400.

    References: ADR-036 §3.12; template file at
    ``src/scieasy/blocks/_templates/block_base_template.py``.
    """
    if kind not in _KNOWN_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown template kind: {kind!r}. Known: {sorted(_KNOWN_TEMPLATES)}",
        )

    resource_name, suggested = _KNOWN_TEMPLATES[kind]
    try:
        template_dir = importlib_resources.files("scieasy.blocks._templates")
        content = (template_dir / resource_name).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
        # Deployment bug: package was installed without the bundled
        # template asset. Log + 500 with a stable message so operators can
        # search for it.
        logger.exception("ADR-036 §3.12: template asset %s missing", resource_name)
        raise HTTPException(
            status_code=500,
            detail=f"Template asset {resource_name!r} missing from package",
        ) from exc

    return BlockTemplateResponse(kind=kind, content=content, suggested_filename=suggested)


@router.get("/{block_type}/schema", response_model=BlockSchemaResponse)
@router.get("/{block_type}", response_model=BlockSchemaResponse, include_in_schema=False)
async def get_block_schema(
    block_type: str,
    registry: BlockRegistryDep,
    type_registry: TypeRegistryDep,
) -> BlockSchemaResponse:
    """Return the JSON Schema for a block type's parameters and ports."""
    spec = registry.get_spec(block_type)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown block type: {block_type}")
    return BlockSchemaResponse(
        **_summary(spec).model_dump(),
        config_schema=_config_schema_for_block(spec),
        type_hierarchy=[
            TypeHierarchyEntry(
                name=entry.name,
                base_type=entry.base_type,
                description=entry.description,
            )
            for entry in type_registry.all_types().values()
        ],
        # ADR-028 Addendum 1 D4 / D7: surface dynamic-port descriptor and IO
        # direction to the frontend so BlockNode.tsx can render dynamic-port
        # UI and IO-specific controls without hardcoded type checks.
        dynamic_ports=spec.dynamic_ports,
        # ADR-029 D11: variadic port type constraints for frontend port editor.
        allowed_input_types=list(getattr(spec, "allowed_input_types", []) or []),
        allowed_output_types=list(getattr(spec, "allowed_output_types", []) or []),
        # ADR-029 Addendum 1: port count limits for variadic blocks.
        min_input_ports=getattr(spec, "min_input_ports", None),
        max_input_ports=getattr(spec, "max_input_ports", None),
        min_output_ports=getattr(spec, "min_output_ports", None),
        max_output_ports=getattr(spec, "max_output_ports", None),
    )


@router.post("/validate-connection", response_model=ConnectionValidationResponse)
async def validate_connection_route(
    body: BlockConnectionValidation,
    registry: BlockRegistryDep,
) -> ConnectionValidationResponse:
    """Validate whether two ports can be connected."""
    source = registry.get_spec(body.source_block)
    target = registry.get_spec(body.target_block)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="Unknown block in connection validation.")

    source_port = next((port for port in source.output_ports if port.name == body.source_port), None)
    target_port = next((port for port in target.input_ports if port.name == body.target_port), None)
    # ADR-029: variadic blocks define ports in config, not in static spec.
    # If lookup fails on a variadic block, synthesize a permissive port.
    from scieasy.core.types.base import DataObject

    if source_port is None and getattr(source, "variadic_outputs", False):
        source_port = OutputPort(name=body.source_port, accepted_types=[DataObject])
    if target_port is None and getattr(target, "variadic_inputs", False):
        target_port = InputPort(name=body.target_port, accepted_types=[DataObject])
    if not isinstance(source_port, OutputPort) or not isinstance(target_port, InputPort):
        raise HTTPException(status_code=404, detail="Unknown source or target port.")

    compatible, reason = validate_connection(source_port, target_port)
    return ConnectionValidationResponse(compatible=compatible, reason=reason)
