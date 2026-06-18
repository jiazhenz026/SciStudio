"""Block palette listing and connection validation endpoints."""

from __future__ import annotations

import importlib.resources as importlib_resources
import logging
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from scistudio.api.deps import get_block_registry, get_type_registry
from scistudio.api.schemas import (
    BlockConnectionValidation,
    BlockListResponse,
    BlockPortResponse,
    BlockSchemaResponse,
    BlockSummary,
    ConnectionValidationResponse,
    FormatCapabilityResponse,
    MetadataFidelityResponse,
    TypeHierarchyEntry,
)
from scistudio.blocks.base.ports import InputPort, OutputPort, validate_connection

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


def _type_names_for_io_direction(
    registry: Any,
    type_registry: Any,
    *,
    direction: str,
) -> list[str]:
    """Return all registered type names, with IO-capable types first."""
    registered = set(type_registry.all_types().keys())
    capable = {capability.data_type.__name__ for capability in registry.list_format_capabilities(direction=direction)}
    core_order = ["Array", "DataFrame", "Series", "Text", "Artifact", "CompositeData"]
    ordered = [name for name in core_order if name in registered]
    ordered.extend(sorted(capable - set(ordered)))
    ordered.extend(sorted(registered - set(ordered)))
    return ordered


def _config_schema_for_block(spec: Any, registry: Any = None, type_registry: Any = None) -> dict[str, Any]:
    schema = spec.config_schema or {"type": "object", "properties": {}}
    if registry is None or type_registry is None:
        return schema
    if spec.type_name not in {"load_data", "save_data"}:
        return schema

    import copy

    direction = "load" if spec.type_name == "load_data" else "save"
    merged = copy.deepcopy(schema)
    properties = merged.setdefault("properties", {})
    properties.pop("allow_pickle", None)
    type_names = _type_names_for_io_direction(registry, type_registry, direction=direction)
    properties["core_type"] = {
        **properties.get("core_type", {}),
        "title": "Type",
        "enum": type_names,
        "default": "DataFrame" if "DataFrame" in type_names else (type_names[0] if type_names else ""),
        "ui_priority": 1,
    }
    if "path" in properties:
        properties["path"]["title"] = "Path"
        properties["path"]["ui_priority"] = 0
        properties["path"]["ui_widget"] = "file_browser" if spec.type_name == "load_data" else "directory_browser"
    merged["required"] = ["path", "core_type"]
    return merged


def _map_source(raw: str) -> str:
    """Map internal source labels to palette-friendly values.

    tier1 -> "custom" (project-local hot-loaded blocks)
    entry_point / monorepo / package_src -> "package" (installed plugin blocks)
    builtin -> "builtin" (core blocks)
    """
    if raw == "tier1":
        return "custom"
    if raw in ("entry_point", "monorepo", "package_src"):
        return "package"
    if raw == "builtin":
        return "builtin"
    return raw


def _format_capability_response(capability: Any) -> FormatCapabilityResponse:
    fidelity = capability.metadata_fidelity
    return FormatCapabilityResponse(
        id=capability.id,
        direction=capability.direction,
        data_type=capability.data_type.__name__,
        format_id=capability.format_id,
        extensions=list(capability.extensions),
        label=capability.label,
        block_type=capability.block_type,
        handler=capability.handler,
        is_default=capability.is_default,
        priority=capability.priority,
        roundtrip_group=capability.roundtrip_group,
        metadata_fidelity=MetadataFidelityResponse(
            level=fidelity.level,
            typed_meta_reads=list(fidelity.typed_meta_reads),
            typed_meta_writes=list(fidelity.typed_meta_writes),
            format_metadata_reads=list(fidelity.format_metadata_reads),
            format_metadata_writes=list(fidelity.format_metadata_writes),
            notes=fidelity.notes,
        ),
        is_synthesized=capability.is_synthesized,
        migration_scaffold=capability.migration_scaffold,
    )


def _artifact_any_response(direction: str, template: FormatCapabilityResponse) -> FormatCapabilityResponse:
    fidelity = template.metadata_fidelity
    return FormatCapabilityResponse(
        id=f"core.artifact.any.{direction}",
        direction=direction,
        data_type="Artifact",
        format_id="any",
        extensions=[],
        label="Any",
        block_type=template.block_type,
        handler=template.handler,
        is_default=True,
        priority=template.priority,
        roundtrip_group=None,
        metadata_fidelity=MetadataFidelityResponse(
            level=fidelity.level,
            typed_meta_reads=list(fidelity.typed_meta_reads),
            typed_meta_writes=list(fidelity.typed_meta_writes),
            format_metadata_reads=list(fidelity.format_metadata_reads),
            format_metadata_writes=list(fidelity.format_metadata_writes),
            notes=fidelity.notes,
        ),
        is_synthesized=False,
        migration_scaffold=False,
    )


def _collapse_artifact_capabilities_for_core_io(
    capabilities: list[FormatCapabilityResponse],
    *,
    direction: str,
) -> list[FormatCapabilityResponse]:
    """Expose Artifact IO as one opaque Any choice in core Load/Save."""
    collapsed: list[FormatCapabilityResponse] = []
    artifact_template: FormatCapabilityResponse | None = None
    artifact_inserted = False
    for capability in capabilities:
        if capability.data_type != "Artifact":
            collapsed.append(capability)
            continue
        if artifact_template is None:
            artifact_template = capability
        if not artifact_inserted:
            collapsed.append(_artifact_any_response(direction, capability))
            artifact_inserted = True
    return collapsed


def _format_capability_responses_for_spec(spec: Any, registry: Any = None) -> list[FormatCapabilityResponse]:
    if registry is not None:
        capabilities = _all_format_capabilities_for_core_io(registry, spec)
    else:
        capabilities = list(getattr(spec, "format_capabilities", []))
    responses = [_format_capability_response(capability) for capability in capabilities]
    if spec.type_name == "load_data":
        return _collapse_artifact_capabilities_for_core_io(responses, direction="load")
    if spec.type_name == "save_data":
        return _collapse_artifact_capabilities_for_core_io(responses, direction="save")
    return responses


def _is_plugin_package(name: str) -> bool:
    """Return True if *name* looks like an external plugin package.

    Convention: plugin packages are named ``scistudio-blocks-<domain>``
    (e.g. ``scistudio-blocks-imaging``).  Everything else (individual
    entry-point names like ``ai_block``, ``code_block``, or empty
    strings) is a core block and should be grouped under the default
    "SciStudio Core" header in the palette.
    """
    return name.startswith("scistudio-blocks-")


def _all_format_capabilities_for_core_io(registry: Any, spec: Any) -> list[Any]:
    if spec.type_name == "load_data":
        return cast(list[Any], registry.list_format_capabilities(direction="load"))
    if spec.type_name == "save_data":
        return cast(list[Any], registry.list_format_capabilities(direction="save"))
    return list(getattr(spec, "format_capabilities", []))


def _summary(spec: Any, registry: Any = None) -> BlockSummary:
    raw_pkg = getattr(spec, "package_name", "") or ""
    # Only keep the package_name for genuine plugin packages so the
    # frontend groups core blocks together under "SciStudio Core".
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
        format_capabilities=_format_capability_responses_for_spec(spec, registry),
    )


def _is_replaced_io_palette_block(spec: Any) -> bool:
    """Hide package-specific IO blocks now represented by core Load/Save."""
    if spec.type_name in {"load_data", "save_data"}:
        return False
    if getattr(spec, "direction", "") not in {"input", "output"}:
        return False
    return bool(getattr(spec, "format_capabilities", []))


def _dynamic_ports_for_core_io(spec: Any, registry: Any, type_registry: Any) -> dict[str, Any] | None:
    if spec.type_name not in {"load_data", "save_data"}:
        return cast(dict[str, Any] | None, spec.dynamic_ports)
    direction = "load" if spec.type_name == "load_data" else "save"
    type_names = _type_names_for_io_direction(registry, type_registry, direction=direction)
    enum_map = {name: [name] for name in type_names}
    if spec.type_name == "load_data":
        return {"source_config_key": "core_type", "output_port_mapping": {"data": enum_map}}
    return {"source_config_key": "core_type", "input_port_mapping": {"data": enum_map}}


@router.get("/", response_model=BlockListResponse)
async def list_blocks(registry: BlockRegistryDep) -> BlockListResponse:
    """Return the full block palette available in the current registry."""
    blocks = [
        _summary(spec, registry) for spec in registry.all_specs().values() if not _is_replaced_io_palette_block(spec)
    ]
    blocks.sort(key=lambda item: (item.base_category, item.subcategory, item.name))
    return BlockListResponse(blocks=blocks)


# ---------------------------------------------------------------------------
# ADR-036 §3.12 — block template endpoint (skeleton, returns 501)
#
# The "New custom block" toolbar action (see ADR-036 §3.7) needs a starter
# template that already wires up imports, ports, and a placeholder ``run()``
# body. Rather than ship the template content in the frontend, we ship it
# next to the package (``src/scistudio/blocks/_templates/``) and serve it via
# this endpoint so the template stays in lockstep with whatever
# ``scistudio.blocks.base`` actually exports.
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
         ``importlib.resources.files("scistudio.blocks._templates") /
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
        ``"from scistudio.blocks.base import Block, BlockSpec, PortSpec"``.
      - test_template_basic_has_run_marker: response content contains
        ``"# >>> EDIT THIS <<<"``.
      - test_template_unknown_kind_400.

    References: ADR-036 §3.12; template file at
    ``src/scistudio/blocks/_templates/block_base_template.py``.
    """
    if kind not in _KNOWN_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown template kind: {kind!r}. Known: {sorted(_KNOWN_TEMPLATES)}",
        )

    resource_name, suggested = _KNOWN_TEMPLATES[kind]
    try:
        template_dir = importlib_resources.files("scistudio.blocks._templates")
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
        **_summary(spec, registry).model_dump(),
        config_schema=_config_schema_for_block(spec, registry, type_registry),
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
        dynamic_ports=_dynamic_ports_for_core_io(spec, registry, type_registry),
        # ADR-029 D11: variadic port type constraints for frontend port editor.
        allowed_input_types=list(getattr(spec, "allowed_input_types", []) or []),
        allowed_output_types=list(getattr(spec, "allowed_output_types", []) or []),
        # ADR-029 Addendum 1: port count limits for variadic blocks.
        min_input_ports=getattr(spec, "min_input_ports", None),
        max_input_ports=getattr(spec, "max_input_ports", None),
        min_output_ports=getattr(spec, "min_output_ports", None),
        max_output_ports=getattr(spec, "max_output_ports", None),
    )


def _resolve_effective_port(
    spec: Any,
    registry: Any,
    block_type: str,
    port_name: str,
    node_config: dict[str, Any] | None,
    *,
    direction: str,
) -> InputPort | OutputPort | None:
    """Return the effective port for ``(block_type, port_name)`` (#889).

    Direction-agnostic resolver shared by the input and output paths:

    * When ``node_config`` is provided, instantiate the block via the
      registry and read its :meth:`Block.get_effective_input_ports`
      or :meth:`Block.get_effective_output_ports` (per *direction*) so
      the validator sees the same contract the renderer uses —
      LoadData's ``core_type`` drives the port type and variadic
      blocks define their ports in config.
    * Falls back to the class-level ``spec.input_ports`` /
      ``spec.output_ports`` when no config is supplied or the
      registry cannot instantiate the block (e.g. malformed config).
    * Preserves the ADR-029 legacy synthetic ``DataObject`` port for
      variadic blocks when no other lookup matches, so older clients
      that have not started passing ``node_config`` still get a
      sensible answer.
    """
    expected_cls: type[InputPort] | type[OutputPort] = InputPort if direction == "input" else OutputPort
    static_ports = getattr(spec, f"{direction}_ports", []) or []
    variadic_flag = f"variadic_{direction}s"
    effective_attr = f"get_effective_{direction}_ports"

    if node_config is not None:
        try:
            block = registry.instantiate(block_type, node_config)
            for port in getattr(block, effective_attr)():
                if port.name == port_name and isinstance(port, expected_cls):
                    return port
        except Exception:
            logger.debug(
                "validate_connection: failed to resolve effective %s ports for %s; falling back to static spec",
                direction,
                block_type,
                exc_info=True,
            )

    static_port = next((port for port in static_ports if port.name == port_name), None)
    if isinstance(static_port, expected_cls):
        return static_port

    # ADR-029 legacy fallback: variadic blocks define ports in
    # config, not in static spec. If lookup fails on a variadic
    # block, synthesize a permissive port.
    from scistudio.core.types.base import DataObject

    if getattr(spec, variadic_flag, False):
        return expected_cls(name=port_name, accepted_types=[DataObject])
    return None


@router.post("/validate-connection", response_model=ConnectionValidationResponse)
async def validate_connection_route(
    body: BlockConnectionValidation,
    registry: BlockRegistryDep,
) -> ConnectionValidationResponse:
    """Validate whether two ports can be connected.

    #889: when the client supplies ``source_node_config`` /
    ``target_node_config`` the route resolves the endpoints' effective
    ports per ADR-028 / ADR-029 (LoadData ``core_type`` drives the
    output type; variadic blocks read their ports from config). The
    legacy payload — block types and port names alone — still works
    against the class-level static spec.
    """
    source = registry.get_spec(body.source_block)
    target = registry.get_spec(body.target_block)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="Unknown block in connection validation.")

    source_port = _resolve_effective_port(
        source, registry, body.source_block, body.source_port, body.source_node_config, direction="output"
    )
    target_port = _resolve_effective_port(
        target, registry, body.target_block, body.target_port, body.target_node_config, direction="input"
    )
    if not isinstance(source_port, OutputPort) or not isinstance(target_port, InputPort):
        raise HTTPException(status_code=404, detail="Unknown source or target port.")

    compatible, reason = validate_connection(source_port, target_port)
    return ConnectionValidationResponse(compatible=compatible, reason=reason)
