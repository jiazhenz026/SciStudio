"""Resolving a MiniApp source to a target and shaping the process setup payload."""
# Resolving a MiniApp source to a target and shaping the process setup payload.
#
# ADR-054 MiniApp FR-004/FR-005/FR-007. A ``miniapp`` context opens from
# ``{panel_id, source}`` where ``source`` is ``{workflow_id, block_id, port}``.
# The backend resolves the source to the output reference of that block's latest
# successful run — a preview target, exactly as ``adr-054-panels`` FR-009 does —
# refuses a source with no such output or a type that is neither the MiniApp's
# declared type nor a subtype of it, and builds the wire payload the subprocess
# reconstructs into the target data object.

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from scistudio.panels.descriptor import PanelDescriptor
from scistudio.panels.targets import FrozenTarget, PanelError, freeze_target


def declared_type(panel: PanelDescriptor) -> tuple[str, bool]:
    """Return the MiniApp's single declared type and whether it is a collection."""
    claim = panel.types[0]
    if claim.startswith("Collection[") and claim.endswith("]"):
        return claim[11:-1], True
    if claim == "Collection":
        return "", True
    return claim, False


def _output_ref(runtime: Any, value: Any) -> str:
    """The catalog/collection ref for a block output, registering a raw ref."""
    if isinstance(value, dict):
        for key in ("data_ref", "collection_ref"):
            ref = value.get(key)
            if isinstance(ref, str):
                return ref
    descriptor = runtime.register_output_payload(value)
    if isinstance(descriptor, dict):
        for key in ("data_ref", "collection_ref"):
            ref = descriptor.get(key)
            if isinstance(ref, str):
                return ref
    raise PanelError(409, "no_output", "The block output cannot be resolved to a data reference")


def run_belongs_to_project(runtime: Any, run: Any) -> bool:
    """Require the run's launch directory to match the active project."""
    project = getattr(runtime, "active_project", None)
    project_dir = getattr(project, "path", None)
    run_dir = getattr(getattr(run, "scheduler", None), "_project_dir", None)
    if not project_dir or not run_dir:
        return False
    return Path(project_dir).resolve() == Path(run_dir).resolve()


def resolve_source(runtime: Any, source: dict[str, Any], panel: PanelDescriptor) -> FrozenTarget:
    """Freeze the block-output target for *source*, refusing a mismatched type."""
    workflow_id = source.get("workflow_id")
    block_id = source.get("block_id")
    port = source.get("port")
    if not all(isinstance(v, str) and v for v in (workflow_id, block_id, port)):
        raise PanelError(422, "invalid_request", "source requires workflow_id, block_id and port")
    run = runtime.workflow_runs.get(workflow_id)
    if not run_belongs_to_project(runtime, run):
        raise PanelError(409, "no_output", "That workflow has no output in the current project")
    scheduler = getattr(run, "scheduler", None)
    if scheduler is None:
        raise PanelError(409, "no_output", "That workflow has no completed run in this session")
    state = getattr(scheduler, "_block_states", {}).get(block_id)
    if state is not None and getattr(state, "value", state) not in ("done", "DONE"):
        raise PanelError(409, "no_output", "The block has no successful run to open on")
    outputs = getattr(scheduler, "_block_outputs", {}).get(block_id)
    if not isinstance(outputs, dict) or port not in outputs:
        raise PanelError(409, "no_output", f"The block produced no output on port {port!r}")
    frozen = freeze_target(runtime, _output_ref(runtime, outputs[port]))
    frozen.validate(runtime)
    _check_type(panel, frozen)
    return frozen


def _check_type(panel: PanelDescriptor, frozen: FrozenTarget) -> None:
    name, is_collection = declared_type(panel)
    if is_collection:
        if frozen.collection is None:
            raise PanelError(409, "type_mismatch", "This MiniApp opens on a collection")
        item_type = str(frozen.collection.get("item_type") or "")
        chain = tuple(frozen.target.type_chain) or (item_type,)
        if name and name not in chain and item_type != name:
            raise PanelError(409, "type_mismatch", f"This MiniApp opens on Collection[{name}]")
        return
    if frozen.collection is not None:
        raise PanelError(409, "type_mismatch", f"This MiniApp opens on {name}, not a collection")
    if name not in tuple(frozen.target.type_chain) and name != frozen.target.recorded_type:
        raise PanelError(409, "type_mismatch", f"This MiniApp opens on {name} or a subtype")


def build_setup_payload(runtime: Any, frozen: FrozenTarget) -> Any:
    """The wire payload the subprocess turns into the target via _reconstruct_one.

    A storage-backed object becomes a single reconstruction dict; a collection
    becomes the reconstruction dicts of its storage-backed items. ``None`` means
    the target could not be materialised, and ``setup`` receives ``None``.
    """
    if frozen.storage is not None:
        return _wire(frozen)
    if frozen.collection is not None:
        items: list[dict[str, Any]] = []
        for raw in frozen.collection.get("items", []):
            ref = raw.get("data_ref") or raw.get("collection_ref")
            if not ref:
                continue
            try:
                child = freeze_target(runtime, ref)
            except PanelError:
                continue
            if child.storage is not None:
                items.append(_wire(child))
        return {"kind": "collection", "items": items}
    return None


def _wire(frozen: FrozenTarget) -> dict[str, Any]:
    """One reconstruction dict, as faithful as the catalog can make it."""
    # One reconstruction dict, as faithful as the catalog can make it (FR-007).
    #
    # ``setup`` must receive the target as the engine's own reconstruction builds
    # it, which resolves the concrete class from ``type_chain`` and fills the
    # ``framework``/``meta``/``user`` slots from the same sidecar the worker wrote.
    # The storage reference normally carries that sidecar verbatim, but a record
    # registered by another path can carry it only on the catalog record — so the
    # record's metadata is the floor, the storage reference's the override, and
    # the catalog's own type chain the last word on what the target *is*. Building
    # the dict from the storage metadata alone handed ``setup`` a bare
    # ``DataObject`` whenever those keys were only on the record.
    storage = frozen.storage
    assert storage is not None
    metadata: dict[str, Any] = {}
    if isinstance(frozen.metadata, dict):
        metadata.update(deepcopy(frozen.metadata))
    metadata.update(deepcopy(dict(storage.metadata or {})))
    chain = [str(name) for name in frozen.target.type_chain]
    if chain:
        metadata["type_chain"] = chain
    elif not metadata.get("type_chain") and frozen.target.recorded_type:
        metadata["type_chain"] = [frozen.target.recorded_type]
    return {"backend": storage.backend, "path": storage.path, "format": storage.format, "metadata": metadata}


def miniapp_input(frozen: FrozenTarget, panel: PanelDescriptor) -> dict[str, Any]:
    """The ``init`` payload for a MiniApp: target ref and type, and MiniApp id/name."""
    # The ``init`` payload for a MiniApp: target ref and type, and MiniApp id/name.
    #
    # FR-005: the init message carries the target reference, its type, and the
    # MiniApp's id and name.
    return {
        "ref": frozen.target.ref,
        "type": frozen.target.recorded_type,
        "type_chain": list(frozen.target.type_chain),
        "panel_id": panel.id,
        "panel_name": panel.name,
    }


__all__ = ["build_setup_payload", "declared_type", "miniapp_input", "resolve_source"]
