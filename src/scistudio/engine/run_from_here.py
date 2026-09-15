"""Decide whether "Run from here" may reuse the upstream outputs it needs.

"Run from here" on a target block re-runs the target and every block downstream
of it. Every input of those blocks that comes from a block *outside* that set
must be fed by an output reused from the workflow's checkpoint. This module
names those required outputs and checks each one:

* the checkpoint holds an output for the block (it ran and finished);
* the checkpoint records the block's definition fingerprint (checkpoints
  written before fingerprints existed cannot be trusted);
* the block, and every block upstream of it, still has the definition it had
  when the output was produced;
* every stored data file the output references still exists.

When any requirement fails the run is refused with one entry per upstream block
and its reason. Upstream blocks are never re-run automatically. A target whose
run set needs no upstream output runs without a checkpoint.

Definition fingerprint
    A SHA-256 over the block type, the block version when a registry is
    available, the node's configuration, and the node's input wiring (which
    upstream node and port feeds each input port). Configuration keys that do
    not change what a block computes are left out: the user-facing
    ``config.label``, the remembered interactive decision
    (``interactive_memory``) and the ``overwrite`` save flag.

Lineage fingerprint
    A SHA-256 over a node's definition fingerprint and the lineage fingerprints
    of the outputs it consumed. It changes when anything upstream of the node
    changes, so one comparison proves the whole upstream chain is unchanged.
"""

# Maintainer context (kept outside generated API documentation):
# Owner decisions on #2448 (2026-09-15): remove the blanket "run the full
# workflow first" refusal, check the target AND its descendants' other-branch
# inputs, refuse with per-node reasons, never re-run upstream automatically.
# Development references: #2448, ADR-012, ADR-038.

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scistudio.engine.dag import DAG, build_dag, get_downstream_blocks, topological_sort

if TYPE_CHECKING:
    from scistudio.engine.checkpoint import WorkflowCheckpoint
    from scistudio.workflow.definition import WorkflowDefinition

__all__ = [
    "REASON_DEFINITION_CHANGED",
    "REASON_DEFINITION_UNKNOWN",
    "REASON_NEVER_RAN",
    "REASON_OUTPUT_MISSING",
    "RunFromHerePlan",
    "RunFromHereRefusedError",
    "UnmetUpstream",
    "definition_fingerprints",
    "lineage_fingerprints",
    "plan_run_from_here",
]

#: The upstream block has no finished output in the checkpoint.
REASON_NEVER_RAN = "never_ran"
#: A data file the stored output references no longer exists.
REASON_OUTPUT_MISSING = "output_missing"
#: The block, or a block upstream of it, changed since the output was produced.
REASON_DEFINITION_CHANGED = "definition_changed"
#: The checkpoint does not record the definition the output was produced with.
REASON_DEFINITION_UNKNOWN = "definition_unknown"

_EXCLUDED_CONFIG_KEYS = frozenset({"label", "interactive_memory"})
_EXCLUDED_PARAM_KEYS = frozenset({"interactive_memory", "overwrite"})


@dataclass(frozen=True)
class UnmetUpstream:
    """One upstream block whose output "Run from here" cannot reuse."""

    node_id: str
    block_type: str
    reason: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        """Return the JSON shape sent to API clients."""
        return {
            "node_id": self.node_id,
            "block_type": self.block_type,
            "reason": self.reason,
            "detail": self.detail,
        }


class RunFromHereRefusedError(ValueError):
    """Raised when an upstream output needed by "Run from here" cannot be reused."""

    def __init__(self, block_id: str, unmet: list[UnmetUpstream]) -> None:
        self.block_id = block_id
        self.unmet = list(unmet)
        lines = "; ".join(f"{item.node_id}: {item.detail}" for item in self.unmet)
        super().__init__(
            f"Cannot run from {block_id!r}: {len(self.unmet)} upstream output(s) cannot be reused. "
            f"Run the upstream blocks first. {lines}"
        )


@dataclass(frozen=True)
class RunFromHerePlan:
    """What a permitted "Run from here" runs and reuses."""

    target: str
    #: The target and every block downstream of it; these run.
    run_set: frozenset[str]
    #: Blocks outside ``run_set`` whose outputs feed a block in ``run_set``.
    required: frozenset[str] = field(default_factory=frozenset)
    #: ``required`` plus every block upstream of them.
    reused: frozenset[str] = field(default_factory=frozenset)


# ---------------------------------------------------------------------------
# Fingerprints
# ---------------------------------------------------------------------------


def _hash(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fingerprinted_config(config: Mapping[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in config.items() if key not in _EXCLUDED_CONFIG_KEYS}
    params = result.get("params")
    if isinstance(params, Mapping):
        result["params"] = {key: value for key, value in params.items() if key not in _EXCLUDED_PARAM_KEYS}
    return result


def _block_version(registry: Any, block_type: str) -> str | None:
    if registry is None:
        return None
    try:
        spec = registry.get_spec(block_type)
    except Exception:
        return None
    version = getattr(spec, "version", None) if spec is not None else None
    return str(version) if version else None


def _input_wiring(dag: DAG) -> dict[str, list[list[str]]]:
    wiring: dict[str, list[list[str]]] = {node_id: [] for node_id in dag.nodes}
    for edge in dag.edges:
        source_node, _, source_port = edge.source.partition(":")
        target_node, _, target_port = edge.target.partition(":")
        wiring[target_node].append([target_port, source_node, source_port])
    for entries in wiring.values():
        entries.sort()
    return wiring


def definition_fingerprints(
    workflow: WorkflowDefinition,
    *,
    registry: Any = None,
    dag: DAG | None = None,
) -> dict[str, str]:
    """Return the definition fingerprint of every executing node in *workflow*."""
    dag = dag if dag is not None else build_dag(workflow)
    wiring = _input_wiring(dag)
    fingerprints: dict[str, str] = {}
    for node_id, node in dag.nodes.items():
        config = node.config if isinstance(node.config, Mapping) else {}
        fingerprints[node_id] = _hash(
            {
                "block_type": node.block_type,
                "block_version": _block_version(registry, node.block_type),
                "config": _fingerprinted_config(config),
                "inputs": wiring[node_id],
            }
        )
    return fingerprints


def lineage_fingerprints(
    dag: DAG,
    definitions: Mapping[str, str],
    *,
    recorded: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return the lineage fingerprint of every node in *dag*.

    A node listed in *recorded* keeps that value: its output was produced
    earlier and is reused as-is. Every other node's value is derived from its
    current definition and the lineage fingerprints of its upstream nodes.
    """
    recorded = recorded or {}
    lineage: dict[str, str] = {}
    for node_id in topological_sort(dag):
        if node_id in recorded:
            lineage[node_id] = recorded[node_id]
            continue
        upstream = sorted((source, lineage[source]) for source in dag.reverse_adjacency.get(node_id, []))
        lineage[node_id] = _hash({"definition": definitions[node_id], "upstream": upstream})
    return lineage


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


def _ancestors(dag: DAG, node_id: str) -> set[str]:
    visited: set[str] = set()
    queue = list(dag.reverse_adjacency.get(node_id, []))
    while queue:
        current = queue.pop()
        if current in visited:
            continue
        visited.add(current)
        queue.extend(dag.reverse_adjacency.get(current, []))
    return visited


def _storage_paths(value: Any) -> Iterator[str]:
    """Yield every stored data path referenced by a checkpointed output value."""
    if isinstance(value, Mapping):
        path = value.get("path")
        if "backend" in value and isinstance(path, str):
            yield path
            return
        for item in value.values():
            yield from _storage_paths(item)
    elif isinstance(value, list):
        for item in value:
            yield from _storage_paths(item)


def _missing_path(output: Any, project_dir: str | None) -> str | None:
    for raw in _storage_paths(output):
        path = Path(raw)
        if not path.is_absolute() and project_dir:
            path = Path(project_dir) / path
        if not path.exists():
            return raw
    return None


def _definition_changes(
    dag: DAG,
    node_id: str,
    current: Mapping[str, str],
    recorded: Mapping[str, Any],
) -> list[str]:
    changed: list[str] = []
    for candidate in sorted(_ancestors(dag, node_id) | {node_id}):
        entry = recorded.get(candidate)
        if not isinstance(entry, Mapping) or entry.get("definition") != current[candidate]:
            changed.append(candidate)
    return changed


def _check_required(
    dag: DAG,
    node_id: str,
    checkpoint: WorkflowCheckpoint | None,
    definitions: Mapping[str, str],
    lineage: Mapping[str, str],
    project_dir: str | None,
) -> UnmetUpstream | None:
    block_type = dag.nodes[node_id].block_type

    def unmet(reason: str, detail: str) -> UnmetUpstream:
        return UnmetUpstream(node_id=node_id, block_type=block_type, reason=reason, detail=detail)

    if checkpoint is None:
        return unmet(REASON_NEVER_RAN, "has not run in this workflow yet")
    state = checkpoint.block_states.get(node_id)
    if node_id not in checkpoint.intermediate_refs or state != "done":
        suffix = f" (last state: {state})" if state and state != "done" else ""
        return unmet(REASON_NEVER_RAN, f"has no finished output from an earlier run{suffix}")

    recorded = checkpoint.node_fingerprints
    entry = recorded.get(node_id)
    if not isinstance(entry, Mapping) or not entry.get("lineage"):
        return unmet(
            REASON_DEFINITION_UNKNOWN,
            "its output was saved without a definition record, so it cannot be checked against the current workflow",
        )
    if entry["lineage"] != lineage[node_id]:
        changed = _definition_changes(dag, node_id, definitions, recorded)
        if node_id in changed:
            detail = "its definition changed since its output was produced"
        elif changed:
            detail = "upstream block(s) changed since its output was produced: " + ", ".join(changed)
        else:
            detail = "an upstream output changed since its output was produced"
        return unmet(REASON_DEFINITION_CHANGED, detail)

    missing = _missing_path(checkpoint.intermediate_refs[node_id], project_dir)
    if missing is not None:
        return unmet(REASON_OUTPUT_MISSING, f"its stored output no longer exists: {missing}")
    return None


def plan_run_from_here(
    workflow: WorkflowDefinition,
    block_id: str,
    checkpoint: WorkflowCheckpoint | None,
    *,
    registry: Any = None,
    project_dir: str | None = None,
    dag: DAG | None = None,
) -> RunFromHerePlan:
    """Check the upstream outputs "Run from here" on *block_id* needs.

    Returns the plan when every required output can be reused. Raises
    :class:`RunFromHereRefusedError` listing each upstream block that cannot,
    and ``ValueError`` when *block_id* is not an executing block.
    """
    dag = dag if dag is not None else build_dag(workflow)
    if block_id not in dag.nodes:
        raise ValueError(f"Unknown block: {block_id}")

    run_set = frozenset(get_downstream_blocks(dag, block_id)) | {block_id}
    required = frozenset(
        source for node_id in run_set for source in dag.reverse_adjacency.get(node_id, []) if source not in run_set
    )
    reused = set(required)
    for node_id in required:
        reused |= _ancestors(dag, node_id)

    if required:
        definitions = definition_fingerprints(workflow, registry=registry, dag=dag)
        lineage = lineage_fingerprints(dag, definitions)
        unmet = [
            item
            for node_id in sorted(required)
            if (item := _check_required(dag, node_id, checkpoint, definitions, lineage, project_dir)) is not None
        ]
        if unmet:
            raise RunFromHereRefusedError(block_id, unmet)

    return RunFromHerePlan(target=block_id, run_set=run_set, required=required, reused=frozenset(reused))
