"""Workflow validation -- type compatibility, cycles, missing connections."""

from __future__ import annotations

from typing import Any

from scieasy.blocks.base.ports import InputPort, OutputPort, validate_connection
from scieasy.blocks.registry import BlockRegistry, BlockSpec
from scieasy.engine.dag import CycleError, build_dag, topological_sort
from scieasy.workflow.definition import NodeDef, WorkflowDefinition


def _parse_port_ref(ref: str) -> tuple[str, str] | None:
    """Split a ``"node_id:port_name"`` reference into its two parts.

    Returns ``None`` when the format is invalid (not exactly two non-empty
    parts separated by a single colon).
    """
    parts = ref.split(":")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def _find_port(
    ports: list[object],
    name: str,
) -> InputPort | OutputPort | None:
    """Return the port whose ``name`` attribute matches, or ``None``."""
    for port in ports:
        if isinstance(port, (InputPort, OutputPort)) and port.name == name:
            return port
    return None


def _effective_ports_for_node(
    registry: BlockRegistry,
    node: NodeDef,
    spec: BlockSpec,
) -> tuple[list[Any], list[Any]]:
    """Return ``(effective_input_ports, effective_output_ports)`` for *node*.

    ADR-028 Addendum 1 D6: when the registry can construct a real block
    instance from the node's config, the validator must use that instance's
    :meth:`Block.get_effective_input_ports` /
    :meth:`Block.get_effective_output_ports` so dynamic blocks (e.g.
    ``LoadData``) get their config-driven ports instead of the static
    ClassVar declaration.

    Spec-only registry entries (e.g. tests that inject a bare
    :class:`BlockSpec` without registering an importable class) cannot be
    instantiated; for those we fall back to the spec's static ports. This
    fallback is **explicit and load-bearing**: it preserves backward
    compatibility for both production registry entries that point at real
    classes (where instantiation succeeds and effective ports drive the
    check) and test fixtures that bypass the import path entirely.
    """
    try:
        instance = registry.instantiate(node.block_type, config=dict(node.config))
    except Exception:
        # Spec-only registry entry, missing module, broken construction —
        # fall back to the static spec ports so the rest of the validator
        # checks (Check 5 & 6) still run.
        return list(spec.input_ports), list(spec.output_ports)

    return list(instance.get_effective_input_ports()), list(instance.get_effective_output_ports())


def validate_workflow(
    workflow: WorkflowDefinition,
    registry: BlockRegistry | None = None,
) -> list[str]:
    """Validate a workflow definition and return a list of diagnostic messages.

    Checks include:

    1. **Structural** -- duplicate node IDs, empty workflow.
    2. **Edge format** -- ``node_id:port_name`` colon-separated format.
    3. **Edge node references** -- source / target nodes exist.
    4. **Cycle detection** -- delegates to :func:`~scieasy.engine.dag.build_dag`
       and :func:`~scieasy.engine.dag.topological_sort`.
    5. **Type compatibility** -- port type matching via
       :func:`~scieasy.blocks.base.ports.validate_connection` (only when
       *registry* is provided).
    6. **Dangling required input ports** -- required ``InputPort`` instances
       without an incoming edge (only when *registry* is provided).
    7. **Variadic port cardinality** -- effective port count within
       ``min_input_ports`` / ``max_input_ports`` / ``min_output_ports`` /
       ``max_output_ports`` limits declared on the ``BlockSpec`` (only when
       *registry* is provided).
    8. **AppBlock duplicate output-port extensions** -- two output ports on
       a single variadic-output block declaring the same file extension
       (case-insensitive) would make extension-based binning ambiguous, so
       such configurations are rejected at workflow save time
       (issue #680).

    Parameters
    ----------
    workflow:
        A ``WorkflowDefinition`` instance to validate.
    registry:
        An optional ``BlockRegistry`` used for type-compatibility and
        dangling-port checks.  When ``None``, those checks are skipped.

    Returns
    -------
    list[str]
        A (possibly empty) list of human-readable validation error or warning
        messages.  An empty list indicates a valid workflow.
    """
    errors: list[str] = []

    # ------------------------------------------------------------------
    # Check 1: Structural validation
    # ------------------------------------------------------------------
    seen_ids: set[str] = set()
    for node in workflow.nodes:
        if node.id in seen_ids:
            errors.append(f"Duplicate node id: '{node.id}'")
        seen_ids.add(node.id)

    if not workflow.nodes:
        return errors  # empty workflow is valid

    # ------------------------------------------------------------------
    # Check 2 & 3: Edge format and node reference validation
    # ------------------------------------------------------------------
    has_edge_errors = False
    for edge in workflow.edges:
        src_parsed = _parse_port_ref(edge.source)
        tgt_parsed = _parse_port_ref(edge.target)
        if src_parsed is None or tgt_parsed is None:
            errors.append(
                f"Edge '{edge.source}' -> '{edge.target}': invalid port reference format (expected 'node_id:port_name')"
            )
            has_edge_errors = True
            continue  # skip further checks on this malformed edge

        # --------------------------------------------------------------
        # Check 3: Edge node reference validation
        # --------------------------------------------------------------
        src_node_id, _ = src_parsed
        tgt_node_id, _ = tgt_parsed
        if src_node_id not in seen_ids:
            errors.append(f"Edge references unknown node '{src_node_id}'")
            has_edge_errors = True
        if tgt_node_id not in seen_ids:
            errors.append(f"Edge references unknown node '{tgt_node_id}'")
            has_edge_errors = True

    # ------------------------------------------------------------------
    # Check 4: Cycle detection (skipped when edges are malformed)
    # ------------------------------------------------------------------
    if not has_edge_errors:
        try:
            dag = build_dag(workflow)
            topological_sort(dag)
        except CycleError:
            errors.append("Workflow contains a cycle")

    # ------------------------------------------------------------------
    # Registry-dependent checks (5 & 6)
    # ------------------------------------------------------------------
    if registry is None:
        return errors

    node_map = {node.id: node for node in workflow.nodes}

    # ADR-028 Addendum 1 D6: cache effective ports per node so we only
    # instantiate each block once across both Check 5 and Check 6.
    effective_ports_cache: dict[str, tuple[list[Any], list[Any]]] = {}

    def _ports_for(node: NodeDef, spec: BlockSpec) -> tuple[list[Any], list[Any]]:
        cached = effective_ports_cache.get(node.id)
        if cached is not None:
            return cached
        result = _effective_ports_for_node(registry, node, spec)
        effective_ports_cache[node.id] = result
        return result

    # ------------------------------------------------------------------
    # Check 5: Type compatibility on edges
    # ------------------------------------------------------------------
    for edge in workflow.edges:
        src_parsed = _parse_port_ref(edge.source)
        tgt_parsed = _parse_port_ref(edge.target)
        if src_parsed is None or tgt_parsed is None:
            continue  # already reported in Check 2

        src_node_id, src_port_name = src_parsed
        tgt_node_id, tgt_port_name = tgt_parsed

        src_node = node_map.get(src_node_id)
        tgt_node = node_map.get(tgt_node_id)
        if src_node is None or tgt_node is None:
            continue  # already reported in Check 3

        src_spec = registry.get_spec(src_node.block_type)
        if src_spec is None:
            errors.append(
                f"Warning: block type '{src_node.block_type}' not in registry, "
                f"skipping type check for node '{src_node_id}'"
            )
            continue

        tgt_spec = registry.get_spec(tgt_node.block_type)
        if tgt_spec is None:
            errors.append(
                f"Warning: block type '{tgt_node.block_type}' not in registry, "
                f"skipping type check for node '{tgt_node_id}'"
            )
            continue

        # ADR-028 Addendum 1 D6: use effective ports from a per-node block
        # instance when available; fall back to the static spec ports for
        # spec-only registry entries (see ``_effective_ports_for_node``).
        _, src_output_ports = _ports_for(src_node, src_spec)
        tgt_input_ports, _ = _ports_for(tgt_node, tgt_spec)

        src_port = _find_port(src_output_ports, src_port_name)
        if src_port is None:
            errors.append(f"Warning: port '{src_port_name}' not found on block '{src_node.block_type}'")
            continue

        tgt_port = _find_port(tgt_input_ports, tgt_port_name)
        if tgt_port is None:
            errors.append(f"Warning: port '{tgt_port_name}' not found on block '{tgt_node.block_type}'")
            continue

        if isinstance(src_port, OutputPort) and isinstance(tgt_port, InputPort):
            ok, reason = validate_connection(src_port, tgt_port)
            if not ok:
                errors.append(f"Edge '{edge.source}' -> '{edge.target}': {reason}")

    # ------------------------------------------------------------------
    # Check 6: Dangling required input ports
    # ------------------------------------------------------------------
    # Build a map of which input ports are connected per node.
    connected_inputs: dict[str, set[str]] = {node.id: set() for node in workflow.nodes}
    for edge in workflow.edges:
        tgt_parsed = _parse_port_ref(edge.target)
        if tgt_parsed is not None:
            tgt_node_id, tgt_port_name = tgt_parsed
            if tgt_node_id in connected_inputs:
                connected_inputs[tgt_node_id].add(tgt_port_name)

    for node in workflow.nodes:
        spec: BlockSpec | None = registry.get_spec(node.block_type)
        if spec is None:
            continue  # unknown block type — already warned in Check 5

        # ADR-028 Addendum 1 D6: dangling-port check uses effective ports
        # so dynamic blocks aren't flagged for static-but-unused declarations.
        node_input_ports, _ = _ports_for(node, spec)

        for port in node_input_ports:
            if isinstance(port, InputPort) and port.required and port.name not in connected_inputs[node.id]:
                errors.append(f"Node '{node.id}': required input port '{port.name}' has no incoming connection")

    # ------------------------------------------------------------------
    # Check 7: Variadic port cardinality limits (ADR-029 Addendum 1)
    # ------------------------------------------------------------------
    # For blocks with variadic_inputs or variadic_outputs, verify that
    # the number of effective ports respects min/max ClassVar limits
    # exposed on BlockSpec.
    for node in workflow.nodes:
        spec = registry.get_spec(node.block_type)
        if spec is None:
            continue

        if spec.variadic_inputs:
            input_ports, _ = _ports_for(node, spec)
            n_in = len(input_ports)
            if spec.min_input_ports is not None and n_in < spec.min_input_ports:
                errors.append(
                    f"Node '{node.id}': variadic input port count {n_in} is below minimum {spec.min_input_ports}"
                )
            if spec.max_input_ports is not None and n_in > spec.max_input_ports:
                errors.append(
                    f"Node '{node.id}': variadic input port count {n_in} exceeds maximum {spec.max_input_ports}"
                )

        if spec.variadic_outputs:
            _, output_ports = _ports_for(node, spec)
            n_out = len(output_ports)
            if spec.min_output_ports is not None and n_out < spec.min_output_ports:
                errors.append(
                    f"Node '{node.id}': variadic output port count {n_out} is below minimum {spec.min_output_ports}"
                )
            if spec.max_output_ports is not None and n_out > spec.max_output_ports:
                errors.append(
                    f"Node '{node.id}': variadic output port count {n_out} exceeds maximum {spec.max_output_ports}"
                )

    # ------------------------------------------------------------------
    # Check 8: AppBlock duplicate output-port extensions (issue #680)
    # ------------------------------------------------------------------
    # AppBlock subclasses route output files into ports by file extension.
    # Two ports declaring the same extension would be ambiguous, so reject
    # such configurations at save time. Case-insensitive comparison; ports
    # that omit the ``extension`` field are skipped (the runtime binner
    # will leave them empty / raise on its own if required).
    #
    # #690 audit fix: the frontend port editor writes ``output_ports`` under
    # ``node.config["params"]["output_ports"]`` (mirroring the
    # :class:`BlockConfig` two-tier layout used at runtime), so the original
    # root-level read here never matched real configs and Check 8 silently
    # passed every workflow. Read ``params.output_ports`` first; fall back
    # to the root-level key so direct API callers and existing tests that
    # construct configs without a ``params`` envelope still work.
    for node in workflow.nodes:
        spec = registry.get_spec(node.block_type)
        if spec is None or not spec.variadic_outputs:
            continue
        params = node.config.get("params")
        configured: Any = None
        if isinstance(params, dict):
            configured = params.get("output_ports")
        if configured is None:
            configured = node.config.get("output_ports")
        if not isinstance(configured, list):
            continue
        ext_to_ports: dict[str, list[str]] = {}
        for entry in configured:
            if not isinstance(entry, dict):
                continue
            port_name = str(entry.get("name", "")).strip()
            ext_raw = entry.get("extension")
            if not port_name or ext_raw in (None, ""):
                continue
            ext = str(ext_raw).strip().lstrip(".").lower()
            if not ext:
                continue
            ext_to_ports.setdefault(ext, []).append(port_name)
        for ext, names in ext_to_ports.items():
            if len(names) > 1:
                joined = ", ".join(sorted(set(names)))
                errors.append(f"Node '{node.id}': Duplicate extension {ext!r} across output ports {{{joined}}}")

    return errors
