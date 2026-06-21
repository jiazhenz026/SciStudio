"""ADR-044 FR-004 — resolve a ``SubWorkflowBlock``'s effective port surface.

Given a reference to a subworkflow file, read its ``exposed_ports`` section and
produce the parent-facing port surface. When a block registry is supplied, each
exposed port's ``accepted_types`` is inherited from the inner block's effective
port (FR-004); without a registry the types default to accept-any (``[]``).

This lives in the ``workflow`` layer and depends only on ``serializer`` plus the
*caller-supplied* registry object — it never imports ``scistudio.blocks`` — so
both the API route (which delivers ``resolved_ports`` to the editor, D4) and
``SubWorkflowBlock.get_effective_*_ports`` can reuse it with no import cycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from scistudio.workflow.flatten import _split_internal, subworkflow_ref_path
from scistudio.workflow.serializer import load_yaml

__all__ = ["PortEntry", "PortSurface", "resolve_port_surface", "subworkflow_ref_path"]


class PortEntry(TypedDict):
    name: str
    accepted_types: list[str]


class PortSurface(TypedDict):
    inputs: list[PortEntry]
    outputs: list[PortEntry]
    broken: bool
    ref_path: str | None


def _empty_surface(ref_path: str | None, *, broken: bool) -> PortSurface:
    return {"inputs": [], "outputs": [], "broken": broken, "ref_path": ref_path}


def resolve_port_surface(
    ref_path: str | None,
    base_dir: str | Path,
    *,
    registry: Any | None = None,
) -> PortSurface:
    """Resolve the exposed-port surface for a subworkflow reference (FR-004).

    Returns a :class:`PortSurface` dict. ``broken`` is ``True`` when *ref_path*
    is missing or does not resolve to a readable workflow file (FR-010). A file
    with no ``exposed_ports`` section resolves to an empty, non-broken surface
    (FR-008).
    """
    if not ref_path:
        return _empty_surface(ref_path, broken=True)
    try:
        resolved = (Path(base_dir) / ref_path).resolve(strict=True)
        child = load_yaml(resolved)
    except Exception:
        return _empty_surface(ref_path, broken=True)

    surface = _empty_surface(ref_path, broken=False)
    exposed = child.exposed_ports
    if exposed is None:
        return surface

    node_by_id = {node.id: node for node in child.nodes}
    for entries, key, direction in (
        (exposed.inputs, "inputs", "input"),
        (exposed.outputs, "outputs", "output"),
    ):
        for entry in entries:
            accepted = _accepted_types(node_by_id, entry.internal, direction, registry)
            surface[key].append({"name": entry.name, "accepted_types": accepted})
    return surface


def _accepted_types(
    node_by_id: dict[str, Any],
    internal: str,
    direction: str,
    registry: Any | None,
) -> list[str]:
    """Return inner-port ``accepted_types`` as type-name strings (FR-004).

    Best-effort: returns ``[]`` (accept-any) when no registry is supplied, the
    internal ref is malformed, the inner block cannot be instantiated, or the
    named port is absent. The authoritative typed surface is produced for the
    editor by the API route, which always passes the runtime registry.
    """
    if registry is None:
        return []
    try:
        block_id, port_name = _split_internal(internal)
    except ValueError:
        return []
    node = node_by_id.get(block_id)
    if node is None:
        return []
    try:
        instance = registry.instantiate(node.block_type, config=dict(node.config or {}))
        ports = instance.get_effective_input_ports() if direction == "input" else instance.get_effective_output_ports()
    except Exception:
        return []
    port = next((p for p in ports if p.name == port_name), None)
    if port is None:
        return []
    return [t.__name__ for t in (getattr(port, "accepted_types", None) or [])]
