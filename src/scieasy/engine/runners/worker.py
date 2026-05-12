"""Subprocess entry point — invoked by spawn_block_process().

ADR-017: All block execution happens in isolated subprocesses. This module
is the entry point for those subprocesses.

ADR-027 D11 + Addendum 1 §1 (T-014): per-item reconstruction delegates
to :func:`scieasy.core.types.serialization._reconstruct_one` which
returns typed :class:`~scieasy.core.types.base.DataObject` instances
(e.g. a :class:`~scieasy.core.types.array.Array`). Lazy loading is
preserved at the method level: returned instances have ``storage_ref``
set but do not read payload data until ``to_memory()`` / ``sel()`` /
``iter_over()`` is called (ADR-031 D2: ViewProxy eliminated).
Serialisation delegates symmetrically to
:func:`~scieasy.core.types.serialization._serialise_one`, which writes
the full metadata sidecar (``type_chain`` + ``framework`` + ``meta`` +
``user`` + base-class extras).

Protocol:
    1. Scan the TypeRegistry for plugin-provided types (ADR-027 D11).
    2. Receive serialized payload via stdin:
       - block_class: str (dotted module path + class name)
       - inputs: dict[str, Any] (wire-format typed payload items)
       - config: dict[str, Any]
       - output_dir: str (optional, for persisting outputs)
    3. Reconstruct inputs into typed DataObject instances.
    4. Import block class, instantiate, call block.run(inputs, config).
    5. Serialize outputs to wire format and write JSON result to stdout.
    6. On error: serialize traceback, return error payload, exit with code 1.
"""

from __future__ import annotations

import importlib
import json
import logging
import sys
import traceback
from typing import Any

logger = logging.getLogger(__name__)


def reconstruct_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct typed DataObject inputs from the JSON wire payload.

    ADR-027 D11 + Addendum 1 §1: returns typed :class:`DataObject`
    instances (e.g. a :class:`~scieasy.core.types.array.Array` or a
    plugin subclass like ``FluorImage``). Lazy loading is preserved
    at the method level: returned instances have ``storage_ref`` set
    but do not read payload data until ``to_memory()`` / ``sel()`` /
    ``iter_over()`` is called (ADR-031 D2: ViewProxy eliminated).

    Three dispatch cases (per the ADR pseudocode):

    1. ``{"_collection": True, "items": [...], "item_type": "..."}``
       — reconstruct each item via :func:`_reconstruct_one`, then wrap
       in a :class:`~scieasy.core.types.collection.Collection` whose
       ``item_type`` is resolved via :class:`TypeRegistry`.
    2. ``{"backend": ..., "path": ..., "metadata": {...}}`` — single
       typed DataObject reconstructed via :func:`_reconstruct_one`.
    3. Anything else — scalar / list / dict pass-through for
       config-derived inputs that are not DataObjects.
    """
    from scieasy.core.types.base import DataObject
    from scieasy.core.types.collection import Collection
    from scieasy.core.types.serialization import _get_type_registry, _reconstruct_one

    raw_inputs = payload.get("inputs", {})
    result: dict[str, Any] = {}

    for key, value in raw_inputs.items():
        if isinstance(value, dict) and value.get("_collection"):
            # Collection of typed items — reconstruct each one and
            # rewrap into a Collection with the resolved item_type.
            raw_items = value.get("items", [])
            items = [_reconstruct_one(item) for item in raw_items]
            item_type_name = value.get("item_type", "DataObject")
            registry = _get_type_registry()
            resolved = registry.resolve([item_type_name])
            item_type: type = resolved if resolved is not None else DataObject
            result[key] = Collection(items, item_type=item_type)
        elif isinstance(value, dict) and "backend" in value and "path" in value:
            # Single typed DataObject — delegate to _reconstruct_one.
            result[key] = _reconstruct_one(value)
        else:
            # Scalar / list / dict / None — pass through for non-DataObject
            # inputs threaded in from config or upstream non-typed outputs.
            result[key] = value

    return result


def serialise_outputs(outputs: dict[str, Any], output_dir: str) -> dict[str, Any]:
    """Serialize block outputs to JSON-compatible wire format.

    ADR-027 D11 + Addendum 1 §1: each output value (or each item in an
    output :class:`Collection`) is serialised via
    :func:`_serialise_one`, which writes the typed-instance metadata
    sidecar (``type_chain`` + ``framework`` + ``meta`` + ``user`` +
    base-class extras). The top-level wire-format keys
    (``backend``/``path``/``format``/``metadata``/``_collection``/
    ``items``/``item_type``) are unchanged.

    Auto-flush behaviour from ADR-020-Add5 is preserved: in-memory
    :class:`DataObject` instances without a :class:`StorageReference`
    are written to ``output_dir`` (via :meth:`Block._auto_flush`)
    before being handed to :func:`_serialise_one`. When no flush
    context is configured, ``_auto_flush`` returns the object unchanged
    and :func:`_serialise_one` tolerates the missing ``storage_ref``
    by emitting ``backend=None`` / ``path=None``.

    Parameters
    ----------
    outputs:
        Mapping of port names to output data objects.
    output_dir:
        Directory for writing output artifacts when auto-flushing.
    """
    from scieasy.blocks.base.block import Block
    from scieasy.core.storage.flush_context import clear, get_output_dir, set_output_dir
    from scieasy.core.types.base import DataObject
    from scieasy.core.types.collection import Collection
    from scieasy.core.types.serialization import _serialise_one

    previous_output_dir = get_output_dir()
    if output_dir:
        set_output_dir(output_dir)
    try:
        result: dict[str, Any] = {}
        for key, value in outputs.items():
            # Handle Collection: serialise each item via _serialise_one.
            if isinstance(value, Collection):
                item_payloads: list[Any] = []
                for item in value:
                    flushed = Block._auto_flush(item)
                    if isinstance(flushed, DataObject):
                        if flushed.storage_ref is None:
                            from scieasy.core.types.artifact import Artifact

                            if not (isinstance(flushed, Artifact) and getattr(flushed, "file_path", None) is not None):
                                raise RuntimeError(
                                    f"{type(flushed).__name__} on port '{key}' has no storage_ref after auto_flush. "
                                    f"Block output must be persisted before leaving the worker subprocess."
                                )
                        item_payloads.append(_serialise_one(flushed))
                    else:
                        item_payloads.append({"_value": str(flushed)})
                if value.item_type is None:
                    logger.warning(
                        "Collection output on port '%s' has item_type=None; defaulting to 'DataObject'",
                        key,
                    )
                result[key] = {
                    "_collection": True,
                    "items": item_payloads,
                    "item_type": value.item_type.__name__ if value.item_type is not None else "DataObject",
                }
                continue

            # Typed DataObject: auto-flush then delegate to _serialise_one.
            if isinstance(value, DataObject):
                flushed_obj = Block._auto_flush(value)
                if isinstance(flushed_obj, DataObject):
                    if flushed_obj.storage_ref is None:
                        from scieasy.core.types.artifact import Artifact

                        if not (
                            isinstance(flushed_obj, Artifact) and getattr(flushed_obj, "file_path", None) is not None
                        ):
                            raise RuntimeError(
                                f"{type(flushed_obj).__name__} on port '{key}' has no storage_ref after auto_flush. "
                                f"Block output must be persisted before leaving the worker subprocess."
                            )
                    result[key] = _serialise_one(flushed_obj)
                else:
                    # _auto_flush only ever returns the same obj or a
                    # passed-through non-DataObject; this branch is
                    # defensive only.
                    result[key] = str(flushed_obj)
                continue

            # Scalar / list / dict / None: native JSON pass-through.
            if isinstance(value, (str, int, float, bool, type(None), list, dict)):
                result[key] = value
            else:
                result[key] = str(value)

        return result
    finally:
        if previous_output_dir is None:
            clear()
        else:
            set_output_dir(previous_output_dir)


def main() -> None:
    """Subprocess entry point.

    ADR-027 D11 + Addendum 1: warms up the :class:`TypeRegistry`
    singleton at startup (so plugin types can be resolved during
    :func:`reconstruct_inputs`), then reconstructs typed inputs,
    runs the block, and serialises typed outputs.

    Steps:
        1. Warm up the TypeRegistry singleton (scans builtins + plugins).
        2. Read JSON payload from stdin.
        3. Parse block_class path, inputs, config, output_dir.
        4. Import the block class via importlib.
        5. Reconstruct inputs as typed DataObject instances.
        6. Instantiate block, call block.run(inputs, config).
        7. Serialize outputs via the typed wire format.
        8. On exception: write {"error": traceback_str} to stdout, exit 1.
    """
    try:
        # ADR-027 D11: warm the TypeRegistry singleton so plugin-provided
        # DataObject subtypes can be resolved during reconstruct_inputs.
        # The singleton lives in scieasy.core.types.serialization; the
        # first call scans builtins + entry-points.
        from scieasy.core.types.serialization import _get_type_registry

        _get_type_registry()

        raw = sys.stdin.read()
        payload = json.loads(raw)

        block_class_path: str = payload["block_class"]
        config: dict[str, Any] = payload.get("config", {})
        output_dir: str = payload.get("output_dir", "")

        # Import block class.
        module_path, class_name = block_class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        block_cls = getattr(module, class_name)

        # Set output_dir BEFORE block.run() so IOBlock.run() can resolve it
        # via get_output_dir() for loader persistence (ADR-031 D4).
        # serialise_outputs() also uses this context, so it stays set.
        if output_dir:
            from scieasy.core.storage.flush_context import set_output_dir

            set_output_dir(output_dir)

        # Reconstruct inputs as typed DataObject instances (ADR-027 Addendum 1).
        inputs = reconstruct_inputs(payload)

        # Instantiate block.
        block = block_cls()

        if hasattr(block, "transition"):
            from scieasy.blocks.base.state import BlockState

            block.transition(BlockState.READY)

        # Build config object.
        from scieasy.blocks.base.config import BlockConfig

        block_config = BlockConfig(**config)

        # Execute.
        outputs = block.run(inputs, block_config)

        # #681: capture the block's terminal state if it transitioned to a
        # non-DONE terminal state (CANCELLED / ERROR / SKIPPED) from inside
        # ``run()``. ``Block.transition()`` only mutates ``self.state`` in
        # the worker process; without this readback the orchestrator never
        # observes the change. The envelope's ``final_state`` field is
        # absent for the common case where the block ends in RUNNING/DONE,
        # so existing blocks that do not call ``transition()`` from inside
        # ``run()`` keep the previous "no field == DONE" semantics.
        final_state: str | None = None
        if hasattr(block, "state"):
            from scieasy.blocks.base.state import BlockState

            block_state = getattr(block, "state", None)
            if isinstance(block_state, BlockState) and block_state in (
                BlockState.CANCELLED,
                BlockState.ERROR,
                BlockState.SKIPPED,
            ):
                final_state = block_state.value

        # Capture environment inside subprocess for accurate lineage (issue #54).
        from scieasy.core.lineage.environment import EnvironmentSnapshot

        env_snapshot = EnvironmentSnapshot.capture()

        # Serialize outputs via the typed wire format.
        result = serialise_outputs(outputs, output_dir) if isinstance(outputs, dict) else {"_result": str(outputs)}

        envelope: dict[str, Any] = {"outputs": result, "environment": env_snapshot.to_dict()}
        if final_state is not None:
            envelope["final_state"] = final_state
        print(json.dumps(envelope))
    except Exception:
        print(json.dumps({"error": traceback.format_exc()}))
        sys.exit(1)


if __name__ == "__main__":
    main()
