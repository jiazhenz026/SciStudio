"""Plot target discovery + deterministic target IDs (ADR-048 SPEC 2 FR-005, FR-006).

A *plot target* is one output port of one workflow node. Discovery walks the
project's ``workflows/*.yaml`` files for the static graph (node id, block type,
output port) and overlays the latest live run output (``ctx.workflow_runs``) for
availability + run id.

The ``target_id`` is a short stable hash of ``workflow_path | node_id |
output_port`` so two repeated blocks with identical labels still get distinct
selectors (SC-002). Binding is ALWAYS by node id + output port, never by human
label (anti-pattern called out in FR-011 and the skill).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from scistudio.ai.agent.mcp._context import _resolve_project_root, get_context
from scistudio.ai.agent.mcp.tools_plot.models import PlotTarget

logger = logging.getLogger(__name__)

_TARGET_ID_PREFIX = "tgt_"
_TARGET_ID_LEN = 16


def make_target_id(workflow_path: str, node_id: str, output_port: str) -> str:
    """Deterministic opaque target id from stable identity (FR-006).

    Uses forward-slash-normalised workflow path so the id is stable across
    platforms.
    """
    norm_path = workflow_path.replace("\\", "/")
    raw = f"{norm_path}|{node_id}|{output_port}".encode()
    digest = hashlib.sha256(raw).hexdigest()[:_TARGET_ID_LEN]
    return f"{_TARGET_ID_PREFIX}{digest}"


def _workflow_files(root: Path, workflow_path: str | None) -> list[Path]:
    if workflow_path:
        candidate = (root / workflow_path).resolve()
        return [candidate] if candidate.is_file() else []
    wf_dir = root / "workflows"
    if not wf_dir.is_dir():
        return []
    return sorted(p for p in wf_dir.glob("*.yaml") if p.is_file()) + sorted(
        p for p in wf_dir.glob("*.yml") if p.is_file()
    )


def _output_ports_for_block(ctx: Any, block_type: str) -> list[tuple[str, str]]:
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
    ports: list[tuple[str, str]] = []
    raw_ports = getattr(spec, "output_ports", None) or []
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


def _latest_output_for(ctx: Any, node_id: str, output_port: str) -> tuple[str | None, bool, bool]:
    """Find the latest recorded output for ``node_id:output_port``.

    Returns ``(latest_run_id, output_available, is_collection)``. Reads the
    in-memory scheduler outputs exactly like ``tools_inspection.get_block_output``
    — never the lineage store, never mutating anything.
    """
    runs = getattr(ctx, "workflow_runs", None)
    if not isinstance(runs, dict) or not runs:
        return None, False, False
    # Iterate in insertion order; later runs override. dict preserves order.
    latest_run_id: str | None = None
    available = False
    is_collection = False
    for run_id, run in runs.items():
        scheduler = getattr(run, "scheduler", None)
        outputs = getattr(scheduler, "_block_outputs", {}) if scheduler is not None else {}
        block_payload = outputs.get(node_id)
        if not isinstance(block_payload, dict) or output_port not in block_payload:
            continue
        latest_run_id = run_id
        available = True
        value = block_payload[output_port]
        is_collection = _looks_like_collection(value)
    return latest_run_id, available, is_collection


def _looks_like_collection(value: Any) -> bool:
    if isinstance(value, dict):
        meta = value.get("metadata")
        if isinstance(meta, dict):
            chain = meta.get("type_chain")
            if isinstance(chain, list) and any("Collection" in str(x) for x in chain):
                return True
        if value.get("_collection") or value.get("collection_item_type"):
            return True
    return isinstance(value, (list, tuple))


def discover_targets(workflow_path: str | None = None, include_unavailable: bool = True) -> list[PlotTarget]:
    """Enumerate plot targets across the project's workflows (FR-005)."""
    ctx = get_context()
    root = _resolve_project_root(ctx)

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
        workflow_id = definition.id or None
        for node in definition.nodes:
            ports = _output_ports_for_block(ctx, node.block_type)
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
                latest_run_id, available, is_collection = _latest_output_for(ctx, node.id, port_name)
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


def resolve_target_by_id(target_id: str, workflow_path: str | None = None) -> PlotTarget | None:
    """Return the :class:`PlotTarget` for ``target_id`` or ``None`` (FR-006)."""
    for target in discover_targets(workflow_path=workflow_path, include_unavailable=True):
        if target.target_id == target_id:
            return target
    return None


__all__ = [
    "discover_targets",
    "make_target_id",
    "resolve_target_by_id",
]
