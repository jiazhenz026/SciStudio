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

from scistudio.workflow.definition import ExposedPort, ExposedPorts, NodeDef, WorkflowDefinition
from scistudio.workflow.flatten import _split_internal, subworkflow_ref_path
from scistudio.workflow.serializer import load_yaml

__all__ = [
    "PortEntry",
    "PortSurface",
    "derive_exposed_ports",
    "resolve_port_surface",
    "subworkflow_ref_path",
]


class PortEntry(TypedDict):
    name: str
    accepted_types: list[str]
    # ADR-044 — provenance so the editor can show which inner block each exposed
    # port belongs to (the exposed name is the opaque dot form "<block>.<port>").
    block_id: str  # inner node id, e.g. "d_bl" ("" when the ref is malformed)
    block_type: str  # inner block registry type, e.g. "spectroscopy.baseline_correction"
    block_label: str  # human display name (falls back to block_type, then block_id)
    port: str  # the inner port name, e.g. "spectra"


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
    for entries, target, direction in (
        (exposed.inputs, surface["inputs"], "input"),
        (exposed.outputs, surface["outputs"], "output"),
    ):
        for entry in entries:
            accepted = _accepted_types(node_by_id, entry.internal, direction, registry)
            block_id, port, block_type, block_label = _block_provenance(
                node_by_id, entry.internal, registry
            )
            target.append(
                {
                    "name": entry.name,
                    "accepted_types": accepted,
                    "block_id": block_id,
                    "block_type": block_type,
                    "block_label": block_label,
                    "port": port,
                }
            )
    return surface


def _block_provenance(
    node_by_id: dict[str, Any],
    internal: str,
    registry: Any | None,
) -> tuple[str, str, str, str]:
    """Resolve ``(block_id, port, block_type, block_label)`` for an exposed port.

    Best-effort: a malformed ``internal`` yields all-empty; an unknown inner node
    yields the parsed id/port with empty type/label; a known node falls back to
    ``block_type`` (then ``block_id``) for the label when no registry display name
    is available. The label lets the editor name the owning inner block instead
    of the opaque ``"<block>.<port>"`` exposed name.
    """
    try:
        block_id, port = _split_internal(internal)
    except ValueError:
        return "", "", "", ""
    node = node_by_id.get(block_id)
    if node is None:
        return block_id, port, "", block_id
    block_type = node.block_type
    label = block_type
    if registry is not None:
        try:
            spec = registry.get_spec(block_type)
            spec_name = spec.name if spec is not None else None
            if isinstance(spec_name, str) and spec_name:
                label = spec_name
        except Exception:
            pass
    return block_id, port, block_type, label or block_id


def _node_effective_ports(node: NodeDef, registry: Any | None) -> tuple[list[Any], list[Any]]:
    """Return ``(input_ports, output_ports)`` for *node* via the registry.

    Best-effort: returns ``([], [])`` when no registry is supplied or the block
    cannot be instantiated (e.g. an unregistered plugin block). A node whose
    ports cannot be determined contributes no exposed ports rather than failing
    the whole derivation.
    """
    if registry is None:
        return [], []
    try:
        instance = registry.instantiate(node.block_type, config=dict(node.config or {}))
        return (
            list(instance.get_effective_input_ports()),
            list(instance.get_effective_output_ports()),
        )
    except Exception:
        return [], []


def derive_exposed_ports(
    definition: WorkflowDefinition,
    *,
    registry: Any | None = None,
) -> ExposedPorts:
    """Derive an exposed-port surface from a workflow's open (unconnected) ports.

    ADR-044 Addendum 1 — when a workflow file is imported as a subworkflow and
    declares no ``exposed_ports`` section, every input port with no incoming
    edge and every output port with no outgoing edge is an *open* boundary port
    and is exposed so the referenced pipeline surfaces usable handles on the
    parent canvas (FR-004) without the user hand-editing YAML. Both the exposed
    ``name`` and ``internal`` ref use the dot form ``"<node_id>.<port>"``; the
    node id is unique within the file so the generated names never collide even
    when several inner nodes share a port name (e.g. two unconnected ``spectra``
    inputs).

    A *registry* is required to read each node's effective ports; without it (or
    for a node whose block cannot be instantiated) that node contributes nothing.
    """
    connected_inputs = {edge.target for edge in definition.edges}
    connected_outputs = {edge.source for edge in definition.edges}
    inputs: list[ExposedPort] = []
    outputs: list[ExposedPort] = []
    for node in definition.nodes:
        in_ports, out_ports = _node_effective_ports(node, registry)
        for port in in_ports:
            if f"{node.id}:{port.name}" not in connected_inputs:
                ref = f"{node.id}.{port.name}"
                inputs.append(ExposedPort(name=ref, internal=ref))
        for port in out_ports:
            if f"{node.id}:{port.name}" not in connected_outputs:
                ref = f"{node.id}.{port.name}"
                outputs.append(ExposedPort(name=ref, internal=ref))
    return ExposedPorts(inputs=inputs, outputs=outputs)


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
