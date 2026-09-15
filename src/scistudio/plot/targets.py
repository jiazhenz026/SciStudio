"""Discover plot targets and mint their deterministic target IDs.

A *plot target* is one output port of one workflow node. Discovery walks the
project's ``workflows/*.yaml`` files for the static graph (node id, block type,
output port) and overlays the latest live run output (from the context's recorded
runs) so each target also reports whether data is available and which run
produced it.

Each ``target_id`` is a short stable hash of the workflow path, node id, and
output port, so two repeated blocks with identical labels still get distinct
selectors. Binding is ALWAYS by node id + output port, never by the human label.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from scistudio.plot._context import PlotRuntimeContext, resolve_project_root, safe_under
from scistudio.plot.models import PlotTarget

logger = logging.getLogger(__name__)

_TARGET_ID_PREFIX = "tgt_"
_TARGET_ID_LEN = 16


def make_target_id(workflow_path: str, node_id: str, output_port: str) -> str:
    """Build the stable, opaque id for one workflow output.

    The id is a short hash of the workflow path, node id, and output port, so the
    same output always maps to the same id and two outputs never collide. The
    workflow path is forward-slash-normalised first so the id is identical across
    Windows and POSIX.

    Args:
        workflow_path: Project-relative path of the workflow file.
        node_id: Stable id of the node that produces the output.
        output_port: Name of the node's output port.

    Returns:
        An opaque ``"tgt_"``-prefixed identifier.

    Example:
        >>> tid = make_target_id("workflows/main.yaml", "node-7", "table")
        >>> tid.startswith("tgt_")
        True
        >>> tid == make_target_id("workflows/main.yaml", "node-7", "table")
        True
    """
    norm_path = workflow_path.replace("\\", "/")
    raw = f"{norm_path}|{node_id}|{output_port}".encode()
    digest = hashlib.sha256(raw).hexdigest()[:_TARGET_ID_LEN]
    return f"{_TARGET_ID_PREFIX}{digest}"


def _workflow_files(root: Path, workflow_path: str | None) -> list[Path]:
    if workflow_path:
        candidate = safe_under(root, Path(workflow_path))
        return [candidate] if candidate.is_file() else []
    wf_dir = root / "workflows"
    if not wf_dir.is_dir():
        return []
    return sorted(p for p in wf_dir.glob("*.yaml") if p.is_file()) + sorted(
        p for p in wf_dir.glob("*.yml") if p.is_file()
    )


def _output_ports_for_block(ctx: Any, block_type: str, node_config: dict[str, Any]) -> list[tuple[str, str]]:
    """Return ``[(port_name, accepted_type_name)]`` for a registered block type.

    Best-effort: returns ``[]`` when the block type is not registered (e.g. a
    plugin not installed in this environment) so discovery degrades to a
    diagnostic rather than raising.
    """
    registry = getattr(ctx, "block_registry", None)
    if registry is None:
        return []
    try:
        spec = registry.get_spec(block_type)
    except Exception:
        spec = None
    if spec is None:
        return []
    raw_ports: list[Any] | None = None
    instantiate = getattr(registry, "instantiate", None)
    if callable(instantiate):
        try:
            instance = instantiate(block_type, config=dict(node_config))
            getter = getattr(instance, "get_effective_output_ports", None)
            if callable(getter):
                raw_ports = list(getter())
        except Exception:
            raw_ports = None
    if raw_ports is None:
        raw_ports = list(getattr(spec, "output_ports", None) or [])
    ports: list[tuple[str, str]] = []
    for port in raw_ports:
        name = getattr(port, "name", None)
        if not name:
            continue
        accepted = getattr(port, "accepted_types", None) or []
        type_name = ""
        if accepted:
            first = accepted[0]
            type_name = getattr(first, "__name__", str(first))
        ports.append((str(name), type_name))
    return ports


def workflow_run_keys(workflow_path: str, workflow_id: str | None) -> tuple[str, ...]:
    """Return the keys under which *this* workflow's run may be registered.

    ``ctx.workflow_runs`` is a registry of runs keyed by the workflow's run
    identity, which is derived from its file: ``workflows/main.yaml`` is
    ``main`` and ``subworkflows/qc.yaml`` is ``@subworkflows@qc.yaml``. A node
    id alone is NOT a key into that registry: two workflows may legitimately
    contain a node with the same name, so a lookup that omits the workflow
    resolves to whichever workflow happens to come last in iteration order.

    The declared ``workflow_id`` is not a key: a copied file still declaring the
    original's id would otherwise read the original's run.

    Args:
        workflow_path: Project-relative path of the workflow file.
        workflow_id: The workflow's declared id; kept for callers, not used.

    Returns:
        The run-registry keys for this file.

    Example:
        >>> workflow_run_keys("workflows/main.yaml", "main")
        ('main',)
        >>> workflow_run_keys("workflows/main.yaml", "renamed")
        ('main',)
        >>> workflow_run_keys("subworkflows/qc.yaml", "main")
        ('@subworkflows@qc.yaml',)
    """
    # Development references: #2362, #2394.
    from scistudio.workflow.identity import workflow_identity_for_relative_path

    del workflow_id
    normalised = workflow_path.replace("\\", "/")
    try:
        return (workflow_identity_for_relative_path(normalised),)
    except ValueError:
        return (Path(normalised).stem,)


def target_workflow_identity(workflow_path: str) -> str:
    """Return the run identity of the workflow a plot target is bound to.

    Derived from the target's ``workflow_path``, so a manifest saved with a
    declared id still files its previews under the workflow file's identity.
    """
    return workflow_run_keys(workflow_path, None)[0]


def _latest_output_for(
    ctx: Any, workflow_keys: tuple[str, ...], node_id: str, output_port: str
) -> tuple[str | None, bool, bool]:
    """Find the latest recorded output for ``node_id:output_port`` in ONE workflow.

    Returns ``(latest_run_id, output_available, is_collection)``. Reads the
    in-memory scheduler outputs exactly like ``tools_inspection.get_block_output``
    — never the lineage store, never mutating anything.

    *workflow_keys* comes from :func:`workflow_run_keys` and confines the lookup
    to the run of the workflow the node actually belongs to. Scanning every run
    and matching on ``(node_id, output_port)`` alone reported another workflow's
    output for any node name two workflows share.
    """
    runs = getattr(ctx, "workflow_runs", None)
    if not isinstance(runs, dict) or not runs:
        return None, False, False
    for run_id in workflow_keys:
        run = runs.get(run_id)
        if run is None:
            continue
        scheduler = getattr(run, "scheduler", None)
        outputs = getattr(scheduler, "_block_outputs", {}) if scheduler is not None else {}
        block_payload = outputs.get(node_id)
        if not isinstance(block_payload, dict) or output_port not in block_payload:
            continue
        return run_id, True, _looks_like_collection(block_payload[output_port])
    return None, False, False


def _looks_like_collection(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("_collection"):
            # #1811 Option 2: a length-one Collection represents a single
            # value (ADR-020 §3); only >1 items is a real collection target.
            items = value.get("items")
            return not (isinstance(items, list) and len(items) == 1)
        meta = value.get("metadata")
        if isinstance(meta, dict):
            chain = meta.get("type_chain")
            if isinstance(chain, list) and any("Collection" in str(x) for x in chain):
                return True
        if value.get("collection_item_type"):
            return True
    return isinstance(value, (list, tuple))


def discover_targets(
    ctx: PlotRuntimeContext, workflow_path: str | None = None, include_unavailable: bool = True
) -> list[PlotTarget]:
    """List every plottable output across the project's workflows.

    Walks the project's workflows, resolves each node's output ports, and overlays
    the latest recorded run so each target reports whether data is ready to plot.
    This is what backs ``list_plot_targets``: call it, then bind a plot to one of
    the returned ``target_id`` values.

    Args:
        ctx: The injected runtime context (the REST API runtime or the agent
            context); the engine never reaches a global context.
        workflow_path: Restrict discovery to this one workflow file when given;
            otherwise scan every workflow in ``workflows/``.
        include_unavailable: When ``True``, also return targets that have no
            recorded output yet (and nodes whose block type is not installed),
            each annotated with a diagnostic. When ``False``, return only targets
            that can be plotted right now.

    Returns:
        The discovered :class:`~scistudio.plot.models.PlotTarget` objects.

    Raises:
        RuntimeError: When no project is currently open.

    Example:
        >>> targets = discover_targets(ctx)  # doctest: +SKIP
        >>> ready = [t.target_id for t in targets if t.latest_output_available]  # doctest: +SKIP
    """
    root = resolve_project_root(ctx)

    # Local import: keep the module import cheap and avoid a hard dependency on
    # workflow serialization at decorator-registration time.
    from scistudio.workflow.serializer import load_yaml

    targets: list[PlotTarget] = []
    for wf_file in _workflow_files(root, workflow_path):
        try:
            rel = wf_file.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = wf_file.name
        try:
            definition = load_yaml(wf_file)
        except Exception as exc:
            logger.debug("discover_targets: failed to load %s: %s", wf_file, exc)
            continue
        # #2362: confine the recorded-output overlay to THIS workflow's run.
        # #2394: the target carries the file's run identity (not the declared
        # ``id:``), so its manifest, preview cache and source metadata are filed
        # under the same key the run registry and the editor use.
        run_keys = workflow_run_keys(rel, definition.id or None)
        workflow_id = run_keys[0]
        for node in definition.nodes:
            ports = _output_ports_for_block(ctx, node.block_type, node.config)
            node_label = str(node.config.get("label", "")) if isinstance(node.config, dict) else ""
            if not ports:
                # Block type not registered here — emit a single diagnostic
                # target keyed on a synthetic 'output' port so the agent at
                # least sees the node exists.
                diag_target = PlotTarget(
                    target_id=make_target_id(rel, node.id, "output"),
                    workflow_path=rel,
                    workflow_id=workflow_id,
                    node_id=node.id,
                    node_label=node_label,
                    block_type=node.block_type,
                    output_port="output",
                    output_type="",
                    is_collection=False,
                    latest_run_id=None,
                    latest_output_available=False,
                    diagnostics=[
                        f"block type {node.block_type!r} is not registered in this environment; "
                        "output ports could not be resolved.",
                    ],
                )
                if include_unavailable:
                    targets.append(diag_target)
                continue
            for port_name, type_name in ports:
                latest_run_id, available, is_collection = _latest_output_for(ctx, run_keys, node.id, port_name)
                diagnostics: list[str] = []
                if not available:
                    diagnostics.append("no recorded output for this port yet; run the workflow before run_plot_job.")
                target = PlotTarget(
                    target_id=make_target_id(rel, node.id, port_name),
                    workflow_path=rel,
                    workflow_id=workflow_id,
                    node_id=node.id,
                    node_label=node_label,
                    block_type=node.block_type,
                    output_port=port_name,
                    output_type=type_name,
                    is_collection=is_collection,
                    latest_run_id=latest_run_id,
                    latest_output_available=available,
                    diagnostics=diagnostics,
                )
                if available or include_unavailable:
                    targets.append(target)
    return targets


def resolve_target_by_id(
    ctx: PlotRuntimeContext, target_id: str, workflow_path: str | None = None
) -> PlotTarget | None:
    """Look up the discovered target with a given ``target_id``.

    Runs discovery and returns the single matching target, or ``None`` when no
    target has that id (for example after the bound node was deleted).

    Args:
        ctx: The injected runtime context.
        target_id: The opaque id to look up.
        workflow_path: Restrict the search to this one workflow file when given.

    Returns:
        The matching :class:`~scistudio.plot.models.PlotTarget`, or ``None``.

    Raises:
        RuntimeError: When no project is currently open.
    """
    for target in discover_targets(ctx, workflow_path=workflow_path, include_unavailable=True):
        if target.target_id == target_id:
            return target
    return None


__all__ = [
    "discover_targets",
    "make_target_id",
    "resolve_target_by_id",
    "target_workflow_identity",
    "workflow_run_keys",
]
