"""ADR-044 §4 & §7 — inline flattening of ``SubWorkflowBlock`` references.

A ``SubWorkflowBlock`` is an authoring-time container that references an
external workflow file. Before scheduler dispatch
(``ApiRuntime.start_workflow``), :func:`flatten_subworkflows` rewrites every
reference into a prefixed copy of the referenced workflow's nodes and edges, so
the scheduler always receives a flat DAG that never contains a
``SubWorkflowBlock`` (ADR-044 §1, §4; FR-001, FR-003, FR-005, FR-006).

Representation note (ADR/spec prose vs. real code): the ADR text says "blocks"
and dot-form port refs; the real graph uses :attr:`WorkflowDefinition.nodes`
and colon-form edge refs ``"node_id:port_name"``. Only ``exposed_ports.internal``
keeps the dot form ``"block_id.port"``; this module translates it to the colon
wire form when rewriting parent edges (ADR-044 §4 step 6; FR-006).

This module is pure with respect to its on-disk inputs (ADR-044 §4.1): the same
referenced YAML files always produce the same flat DAG. It depends only on the
``workflow`` layer (``definition`` + ``serializer``); it never imports
``blocks``/``engine``/``api``, so it can be invoked from any layer without an
import cycle.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition
from scistudio.workflow.serializer import load_yaml

# Registry ``type_name`` of the authoring container and the broken-ref
# placeholder (see ``blocks.registry._spec._type_name_for_class``).
SUBWORKFLOW_TYPE = "subworkflow_block"
SUBWORKFLOW_BROKEN_TYPE = "subworkflow_broken"

# Config key (set by the flattener on a broken placeholder) carrying the
# unresolved reference string for the editor / validator to surface.
BROKEN_REF_CONFIG_KEY = "_broken_ref"


class CyclicSubworkflowError(Exception):
    """Raised when inline flattening detects a reference cycle (ADR-044 §7).

    Carries the full reference chain as a list of :class:`~pathlib.Path`
    objects, e.g. ``a.wf.yaml -> b.swf.yaml -> a.wf.yaml`` (FR-007, SC-003).
    """

    def __init__(self, chain: list[Path]) -> None:
        self.chain: list[Path] = [Path(p) for p in chain]
        rendered = " -> ".join(str(p) for p in self.chain)
        super().__init__(f"Cyclic subworkflow reference: {rendered}")


def is_subworkflow_node(node: NodeDef) -> bool:
    """Return whether *node* is a ``SubWorkflowBlock`` authoring container."""
    return node.block_type == SUBWORKFLOW_TYPE


def is_broken_subworkflow_node(node: NodeDef) -> bool:
    """Return whether *node* is a broken-ref placeholder."""
    return node.block_type == SUBWORKFLOW_BROKEN_TYPE


def subworkflow_ref_path(node: NodeDef) -> str | None:
    """Extract ``config.ref.path`` (ADR-044) from a subworkflow node.

    Tolerates the ``config.params.ref.path`` envelope as well. Returns
    ``None`` when no usable reference string is present.
    """
    config = node.config or {}
    for container in (config, config.get("params") if isinstance(config.get("params"), dict) else None):
        if not isinstance(container, dict):
            continue
        ref = container.get("ref")
        if isinstance(ref, dict):
            path = ref.get("path")
            if isinstance(path, str) and path.strip():
                return path
    return None


def _split_colon(ref: str) -> tuple[str, str]:
    """Split a ``"node_id:port_name"`` wire ref. Raises on malformed input."""
    node_id, sep, port = ref.partition(":")
    if not sep or not node_id or not port:
        raise ValueError(f"Malformed port reference '{ref}' (expected 'node_id:port_name')")
    return node_id, port


def _prefix_colon(ref: str, prefix: str) -> str:
    """Prefix the node-id half of a ``"node_id:port_name"`` wire ref."""
    node_id, port = _split_colon(ref)
    return f"{prefix}{node_id}:{port}"


def _split_internal(internal: str) -> tuple[str, str]:
    """Split an ``exposed_ports.internal`` dot ref ``"block_id.port"``."""
    block_id, sep, port = internal.partition(".")
    if not sep or not block_id or not port:
        raise ValueError(f"Malformed exposed_ports.internal '{internal}' (expected 'block_id.port')")
    return block_id, port


def _broken_node(node: NodeDef, ref_path: str) -> NodeDef:
    """Return a ``subworkflow_broken`` placeholder mirroring *node*'s identity."""
    config = dict(node.config or {})
    config[BROKEN_REF_CONFIG_KEY] = ref_path
    return NodeDef(
        id=node.id,
        block_type=SUBWORKFLOW_BROKEN_TYPE,
        config=config,
        execution_mode=node.execution_mode,
        layout=node.layout,
    )


def flatten_subworkflows(
    definition: WorkflowDefinition,
    base_dir: str | Path,
    *,
    registry: object | None = None,  # accepted for API symmetry; not required here
    self_path: str | Path | None = None,
) -> WorkflowDefinition:
    """Return a copy of *definition* with every subworkflow reference inlined.

    Parameters
    ----------
    definition:
        The authored workflow (may contain ``SubWorkflowBlock`` nodes).
    base_dir:
        Project root against which ``config.ref.path`` values resolve
        (ADR-044 / FR-011 stores project-relative refs). Absolute refs also
        resolve correctly (``Path(base) / abs == abs``).
    self_path:
        Optional on-disk path of *definition* itself, seeded into the cycle
        DFS so a reference loop that returns to the root is detected and the
        error chain reads root-first (FR-007).

    Returns a new :class:`WorkflowDefinition` whose ``nodes`` contain no
    ``SubWorkflowBlock`` (only inlined inner nodes and, for unresolved refs,
    ``subworkflow_broken`` placeholders that the validator rejects at run
    start — FR-010).
    """
    base = Path(base_dir).resolve()
    visiting: tuple[Path, ...] = ()
    if self_path is not None:
        try:
            visiting = (Path(self_path).resolve(strict=True),)
        except OSError:
            visiting = (Path(self_path).resolve(),)
    flat, _exp_in, _exp_out = _flatten(definition, base, visiting, registry)
    return flat


# A resolved exposed-port map: exposed port name -> a real leaf wire ref
# ``"present_node_id:port"`` inside the flattened definition.
_ExposedMap = dict[str, str]


def _flatten(
    definition: WorkflowDefinition,
    base: Path,
    visiting: tuple[Path, ...],
    registry: Any | None = None,
) -> tuple[WorkflowDefinition, _ExposedMap, _ExposedMap]:
    """Flatten *definition* and return ``(flat_def, exposed_in, exposed_out)``.

    ``exposed_in`` / ``exposed_out`` resolve each of *definition*'s own
    ``exposed_ports`` to a real leaf wire ref present in ``flat_def`` (handling
    the nested case where an exposed port forwards a *child* subworkflow's
    exposed port). The top-level caller discards these maps. When *registry* is
    supplied, ``exposed_ports.internal`` is additionally validated to reference a
    port that actually exists on the inner block (ADR §9.1 item 3).
    """
    new_nodes: list[NodeDef] = []
    new_edges: list[EdgeDef] = []
    direct_nodes: dict[str, NodeDef] = {}  # non-subworkflow nodes (raw ports)
    # sw_node_id -> resolved exposed maps of that inlined child (prefixed leaf refs)
    sw_in: dict[str, _ExposedMap] = {}
    sw_out: dict[str, _ExposedMap] = {}

    for node in definition.nodes:
        if not is_subworkflow_node(node):
            new_nodes.append(node)
            if not is_broken_subworkflow_node(node):
                direct_nodes[node.id] = node
            continue

        ref = subworkflow_ref_path(node)
        if not ref:
            new_nodes.append(_broken_node(node, ""))
            continue
        try:
            resolved = (base / ref).resolve(strict=True)
        except (OSError, RuntimeError):
            # FR-010 / US6: unresolved ref -> placeholder; validator rejects at run start.
            new_nodes.append(_broken_node(node, ref))
            continue

        if resolved in visiting:
            raise CyclicSubworkflowError([*visiting, resolved])

        child = load_yaml(resolved)
        child_flat, child_in, child_out = _flatten(child, base, (*visiting, resolved), registry)

        prefix = f"{node.id}__"
        for inner in child_flat.nodes:
            new_nodes.append(dataclasses.replace(inner, id=prefix + inner.id))
        for edge in child_flat.edges:
            new_edges.append(
                EdgeDef(
                    source=_prefix_colon(edge.source, prefix),
                    target=_prefix_colon(edge.target, prefix),
                )
            )
        # The child's resolved exposed maps point at leaf refs inside the child;
        # prefix them so they address the inlined copy in this definition.
        sw_in[node.id] = {name: _prefix_colon(leaf, prefix) for name, leaf in child_in.items()}
        sw_out[node.id] = {name: _prefix_colon(leaf, prefix) for name, leaf in child_out.items()}

    for edge in definition.edges:
        new_edges.append(_rewrite_parent_edge(edge, sw_in, sw_out))

    exposed_in, exposed_out = _resolve_own_exposed(definition.exposed_ports, direct_nodes, sw_in, sw_out, registry)

    flat = WorkflowDefinition(
        id=definition.id,
        version=definition.version,
        description=definition.description,
        nodes=new_nodes,
        edges=new_edges,
        metadata=dict(definition.metadata),
        exposed_ports=definition.exposed_ports,
    )
    return flat, exposed_in, exposed_out


def _validate_direct_port(
    node: NodeDef,
    port: str,
    direction: str,
    exposed_name: str,
    registry: Any | None,
) -> None:
    """Raise if *port* does not exist on *node*'s effective ports (ADR §9.1).

    No-op when *registry* is absent or the block cannot be instantiated (e.g. a
    spec-only test registry) — port existence is then left to the normal
    post-flatten edge validation.
    """
    if registry is None:
        return
    try:
        instance = registry.instantiate(node.block_type, config=dict(node.config or {}))
        ports = instance.get_effective_input_ports() if direction == "input" else instance.get_effective_output_ports()
    except Exception:
        return
    if not any(p.name == port for p in ports):
        raise ValueError(
            f"Exposed {direction} '{exposed_name}' references port '{port}' "
            f"that does not exist on block '{node.id}' ({node.block_type})"
        )


def _resolve_own_exposed(
    exposed: Any,
    direct_nodes: dict[str, NodeDef],
    sw_in: dict[str, _ExposedMap],
    sw_out: dict[str, _ExposedMap],
    registry: Any | None = None,
) -> tuple[_ExposedMap, _ExposedMap]:
    """Resolve a definition's own ``exposed_ports`` to leaf wire refs (ADR §9.1).

    ``exposed_ports.internal`` (dot form ``block.port``) may point at either a
    direct block (``-> "block:port"``) or a child subworkflow node whose own
    exposed port forwards to a deeper leaf (``-> sw_<dir>[block][port]``). An
    ``internal`` that resolves to neither is a hard error. When *registry* is
    supplied, a direct block's named port must also exist on the block's
    effective ports (ADR §9.1 item 3).
    """
    exposed_in: _ExposedMap = {}
    exposed_out: _ExposedMap = {}
    if exposed is None:
        return exposed_in, exposed_out
    for entries, sw_map, target, direction in (
        (exposed.inputs, sw_in, exposed_in, "input"),
        (exposed.outputs, sw_out, exposed_out, "output"),
    ):
        for entry in entries:
            block_id, port = _split_internal(entry.internal)
            if block_id in direct_nodes:
                _validate_direct_port(direct_nodes[block_id], port, direction, entry.name, registry)
                target[entry.name] = f"{block_id}:{port}"
            elif block_id in sw_map:
                leaf = sw_map[block_id].get(port)
                if leaf is None:
                    raise ValueError(
                        f"Exposed {direction} '{entry.name}' references unknown exposed "
                        f"port '{port}' of subworkflow node '{block_id}'"
                    )
                target[entry.name] = leaf
            else:
                raise ValueError(f"Exposed {direction} '{entry.name}' references unknown block '{block_id}'")
    return exposed_in, exposed_out


def _rewrite_parent_edge(
    edge: EdgeDef,
    in_maps: dict[str, dict[str, str]],
    out_maps: dict[str, dict[str, str]],
) -> EdgeDef:
    """Rewrite a parent edge touching an inlined subworkflow node (FR-006).

    An edge endpoint ``sw:exposed`` is translated to the prefixed inner wire
    ref via the subworkflow's exposed-port map. An endpoint referencing an
    exposed port that no longer exists is left untouched; because the ``sw``
    node has been removed, the downstream validator rejects it as an edge to
    an unknown node (a dangling edge — ADR-044 §10.1 negative consequence /
    US3.1).
    """
    new_source = edge.source
    new_target = edge.target
    src_node, src_port = _split_colon(edge.source)
    tgt_node, tgt_port = _split_colon(edge.target)
    if src_node in out_maps:
        mapped = out_maps[src_node].get(src_port)
        if mapped is not None:
            new_source = mapped
    if tgt_node in in_maps:
        mapped = in_maps[tgt_node].get(tgt_port)
        if mapped is not None:
            new_target = mapped
    return EdgeDef(source=new_source, target=new_target)
