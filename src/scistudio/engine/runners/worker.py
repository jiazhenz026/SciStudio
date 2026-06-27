"""Subprocess entry point — invoked by spawn_block_process().

ADR-017: All block execution happens in isolated subprocesses. This module
is the entry point for those subprocesses.

ADR-027 D11 + Addendum 1 §1 (T-014): per-item reconstruction delegates
to :func:`scistudio.core.types.serialization._reconstruct_one` which
returns typed :class:`~scistudio.core.types.base.DataObject` instances
(e.g. a :class:`~scistudio.core.types.array.Array`). Lazy loading is
preserved at the method level: returned instances have ``storage_ref``
set but do not read payload data until ``to_memory()`` / ``sel()`` /
``iter_over()`` is called (ADR-031 D2: ViewProxy eliminated).
Serialisation delegates symmetrically to
:func:`~scistudio.core.types.serialization._serialise_one`, which writes
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
import importlib.util
import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Any

from scistudio.blocks.base.exceptions import BlockCancelledByAppError
from scistudio.core.storage.errors import StorageReferenceInvalidError
from scistudio.core.storage.ref import StorageReference

logger = logging.getLogger(__name__)

# #1530: persisted/wire-format version stamp for the worker stdout envelope.
# Bump on a non-backward-compatible change to the engine<->worker JSON contract
# and pair it with a migration/compat step; stamping is the cheap half done now.
WIRE_FORMAT_VERSION = 1


def _prepend_runtime_import_roots(raw_roots: Any) -> tuple[str, ...]:
    """Prepend block-local import roots after worker core startup."""
    if not isinstance(raw_roots, list):
        return ()

    resolved: list[str] = []
    seen: set[str] = set()
    for raw_root in raw_roots:
        if not isinstance(raw_root, str) or not raw_root:
            continue
        root = Path(raw_root).expanduser()
        if not root.is_dir():
            continue
        key = str(root.resolve())
        if key in seen:
            continue
        seen.add(key)
        resolved.append(key)

    for path in reversed(resolved):
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)
    if resolved:
        importlib.invalidate_caches()
    return tuple(resolved)


def _same_storage_ref(left: StorageReference | None, right: StorageReference) -> bool:
    return left is not None and left.backend == right.backend and left.path == right.path


def _contains_storage_ref(value: Any, ref: StorageReference) -> bool:
    storage_ref = getattr(value, "storage_ref", None)
    if _same_storage_ref(storage_ref, ref):
        return True
    if isinstance(value, dict):
        return any(_contains_storage_ref(item, ref) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_storage_ref(item, ref) for item in value)
    if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
        try:
            return any(_contains_storage_ref(item, ref) for item in value)
        except TypeError:
            return False
    return False


def _storage_error_context(
    inputs: dict[str, Any],
    ref: StorageReference,
) -> tuple[str | None, str | None]:
    """Return ``(port_name, upstream_block)`` for a failed storage ref."""
    for port_name, value in inputs.items():
        if _contains_storage_ref(value, ref):
            metadata = ref.metadata or {}
            upstream_block = (
                metadata.get("upstream_block") or metadata.get("producer_block") or metadata.get("block_id")
            )
            return port_name, str(upstream_block) if upstream_block is not None else None
    return None, None


def _emit_storage_error(
    exc: StorageReferenceInvalidError,
    *,
    inputs: dict[str, Any] | None,
    block_id: str | None,
) -> None:
    port_name, upstream_block = _storage_error_context(inputs or {}, exc.ref)
    print(
        json.dumps(
            exc.to_payload(
                block_id=block_id,
                port_name=port_name,
                upstream_block=upstream_block,
            )
        )
    )


def reconstruct_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct typed DataObject inputs from the JSON wire payload.

    ADR-027 D11 + Addendum 1 §1: returns typed :class:`DataObject`
    instances (e.g. a :class:`~scistudio.core.types.array.Array` or a
    plugin subclass like ``FluorImage``). Lazy loading is preserved
    at the method level: returned instances have ``storage_ref`` set
    but do not read payload data until ``to_memory()`` / ``sel()`` /
    ``iter_over()`` is called (ADR-031 D2: ViewProxy eliminated).

    Three dispatch cases (per the ADR pseudocode):

    1. ``{"_collection": True, "items": [...], "item_type": "..."}``
       — reconstruct each item via :func:`_reconstruct_one`, then wrap
       in a :class:`~scistudio.core.types.collection.Collection` whose
       ``item_type`` is resolved via :class:`TypeRegistry`.
    2. ``{"backend": ..., "path": ..., "metadata": {...}}`` — single
       typed DataObject reconstructed via :func:`_reconstruct_one`.
    3. Anything else — scalar / list / dict pass-through for
       config-derived inputs that are not DataObjects.
    """
    from scistudio.core.types.base import DataObject
    from scistudio.core.types.collection import Collection
    from scistudio.core.types.serialization import _get_type_registry, _reconstruct_one

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
            # #1811: in the live flow this branch is not reached for block
            # outputs — every port output is wrapped into a Collection at the
            # engine boundary (_normalize_outputs) and serialised as a
            # ``_collection`` envelope, which the branch above decodes. This
            # bare branch faithfully decodes any legacy bare-wire payload
            # (e.g. an old checkpoint); such a value is delivered as a bare
            # DataObject and handled by the consuming block's existing
            # bare-input fallback.
            result[key] = _reconstruct_one(value)
        else:
            # Scalar / list / dict / None — pass through for non-DataObject
            # inputs threaded in from config or upstream non-typed outputs.
            result[key] = value

    return result


def _normalize_outputs(
    outputs: dict[str, Any],
    output_ports: list[Any],
) -> dict[str, Any]:
    """Normalize block outputs to satisfy the ADR-020 §3 transport contract.

    ADR-020 §3 makes a hard contract claim: every value crossing a block
    boundary is represented as a :class:`Collection`. A single item is a
    length-one Collection; a multi-file or multi-object input is a longer
    Collection. The engine, not the block, is responsible for honouring
    that contract.

    #1811: this wrap is **unconditional** — it applies to every declared
    output port, not just ``is_collection=True`` ports. ``is_collection``
    is a UI hint only and does not change runtime transport
    (collection-guide.md). The earlier ``is_collection=True``-gated wrap
    (#1330) left single-value ports transporting a bare DataObject, which
    violated the contract and produced wire-format drift at the downstream
    port; gating is removed so the wire format is uniform.

    For each ``(port_name, value)`` pair:

    1. Look up the matching :class:`OutputPort` by name. If the port name
       is not declared (e.g. sentinels like ``__scistudio_env__``), leave
       the value unchanged.
    2. If ``value`` is a bare :class:`DataObject` (not already a
       :class:`Collection`), wrap it as
       ``Collection([value], item_type=type(value))``. The ``type(value)``
       strategy matches the precedent in
       :mod:`scistudio.blocks.ai.ai_block` (``ai_block.py:532``) and is
       stable under Add6's ``port_accepts_type`` check.
    3. If ``value`` is a bare ``list`` of :class:`DataObject` items (every
       element is a DataObject and the list is non-empty), pack it as
       ``Collection(value, item_type=type(value[0]))``. Catches the
       ADR-020 §3 "multi-file → longer Collection" case where a block
       returned a native list without packing — without this, the bare
       list would either fall through unwrapped or be wrapped as a single
       1-item Collection containing the list (which violates Collection's
       homogeneity invariant).
    4. For all other shapes (already-wrapped Collection, scalar/dict/None,
       wire-format dict from a serialised payload, mixed-type lists, empty
       lists), leave the value untouched and let the existing
       serialisation / validation layer surface a clear error.

    The helper is idempotent: calling it twice on the same dict yields
    the same result. It is safe to invoke on both raw-Python outputs
    (subprocess pre-``serialise_outputs``) and wire-format dicts
    (in-process post-runner), because plain ``dict`` values never satisfy
    the ``isinstance(value, DataObject)`` guard.

    Parameters
    ----------
    outputs:
        Mapping of port names to output values. Mutated in-place.
    output_ports:
        Effective output ports for the block (typically obtained via
        :meth:`Block.get_effective_output_ports`).

    Returns
    -------
    dict[str, Any]
        The same ``outputs`` dict, mutated in-place and returned for
        chainability.
    """
    from scistudio.core.types.base import DataObject
    from scistudio.core.types.collection import Collection

    port_map = {port.name: port for port in output_ports}

    for port_name, value in list(outputs.items()):
        port = port_map.get(port_name)
        if port is None:
            # Unknown port name (e.g. ``__scistudio_env__`` sentinel) —
            # leave it alone.
            continue
        # #1811: ADR-020 §3 makes the Collection transport contract
        # unconditional — EVERY declared port carries a Collection, not just
        # ``is_collection=True`` ports. The ``is_collection`` flag is a UI
        # hint only (collection-guide.md) and must not gate the wrap. A bare
        # single value on any port is wrapped into a length-one Collection
        # here, so the wire format is uniform regardless of the flag.
        if isinstance(value, Collection):
            continue
        if isinstance(value, list) and value and all(isinstance(item, DataObject) for item in value):
            # Bare ``list[DataObject]`` on a Collection port — pack with
            # the first item's runtime type. ADR-020 §3 "multi-object
            # input is a longer Collection"; without this branch, the
            # list would either fall through unwrapped or hit the bare
            # DataObject branch below (which would wrap the list as a
            # single 1-item Collection containing the list itself and
            # then fail Collection's homogeneity check).
            outputs[port_name] = Collection(value, item_type=type(value[0]))
            continue
        if not isinstance(value, DataObject):
            # Bare scalar / dict / None / wire-format payload / mixed
            # or empty list — the contract only covers DataObject values
            # (and homogeneous lists of them, handled above).
            # ``serialise_outputs`` already handles non-DataObject
            # pass-through.
            continue
        outputs[port_name] = Collection([value], item_type=type(value))

    return outputs


def _validate_outputs(outputs: dict[str, Any], output_ports: list[Any]) -> None:
    """Enforce the block's declared output-port contract (#1518 / DSN-2).

    Every required output port must be present in *outputs* with a
    non-``None`` value. A block that silently drops a required output
    previously surfaced only when a downstream block tried to consume the
    missing edge (or never, if the port was a leaf); enforce it at the
    producing boundary so the run fails with a clear contract error.

    Ports with ``required=False`` may be absent. ``ValueError`` is raised
    on the first violation, mirroring :meth:`Block.validate` for inputs.
    """
    for port in output_ports:
        if not getattr(port, "required", True):
            continue
        if port.name not in outputs or outputs[port.name] is None:
            raise ValueError(f"Required output port '{port.name}' was not produced by the block.")


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
    from scistudio.blocks.base.block import Block
    from scistudio.core.storage.flush_context import clear, get_output_dir, set_output_dir
    from scistudio.core.types.base import DataObject
    from scistudio.core.types.collection import Collection
    from scistudio.core.types.serialization import _serialise_one

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
                            from scistudio.core.types.artifact import Artifact

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
                        from scistudio.core.types.artifact import Artifact

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
    payload: dict[str, Any] = {}
    inputs: dict[str, Any] = {}
    block_id: str | None = None
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        _prepend_runtime_import_roots(payload.get("runtime_import_roots"))

        # ADR-027 D11: warm the TypeRegistry singleton so plugin-provided
        # DataObject subtypes can be resolved during reconstruct_inputs.
        # The singleton lives in scistudio.core.types.serialization; the
        # first call scans builtins + entry-points.
        from scistudio.core.types.serialization import _get_type_registry

        _get_type_registry()

        block_class_path: str = payload["block_class"]
        config: dict[str, Any] = payload.get("config", {})
        block_id = str(config.get("block_id") or block_class_path)
        output_dir: str = payload.get("output_dir", "")
        # ADR-051: two-phase marker. "prompt" runs prepare_prompt and exits;
        # absent / "compute" is the existing single-phase run path.
        phase: str = payload.get("phase", "compute")
        # #706: For Tier-1 drop-in blocks, the parent registry passes the
        # absolute path of the source ``.py`` file. The synthetic module
        # name (``_scistudio_dropin_<stem>_<mtime>``) only exists in the
        # parent's ``sys.modules`` and is not importable here via
        # ``importlib.import_module``. Reload it via spec_from_file_location
        # and register under the same name so the class resolves.
        block_file_path: str | None = payload.get("block_file_path")

        # Import block class.
        module_path, class_name = block_class_path.rsplit(".", 1)
        if block_file_path is not None:
            spec = importlib.util.spec_from_file_location(module_path, block_file_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create module spec for {module_path!r} from file {block_file_path!r}")
            module = importlib.util.module_from_spec(spec)
            # Register before exec so any intra-module imports of the same
            # name resolve to the in-flight module (matches importlib's
            # standard import protocol).
            sys.modules[module_path] = module
            spec.loader.exec_module(module)
        else:
            module = importlib.import_module(module_path)
        block_cls = getattr(module, class_name)

        # Set output_dir BEFORE block.run() so IOBlock.run() can resolve it
        # via get_output_dir() for loader persistence (ADR-031 D4).
        # serialise_outputs() also uses this context, so it stays set.
        if output_dir:
            from scistudio.core.storage.flush_context import set_output_dir

            set_output_dir(output_dir)

        # Reconstruct inputs as typed DataObject instances (ADR-027 Addendum 1).
        inputs = reconstruct_inputs(payload)

        # Instantiate block. Pass config to the constructor so ``self.config``
        # is populated — variadic-port blocks (ADR-029 D1) read
        # ``self.config["input_ports"]`` / ``self.config["output_ports"]``
        # from ``get_effective_input_ports()`` / ``get_effective_output_ports()``
        # to compute per-instance ports. Without this the AIBlock instance
        # always falls back to the static class-level "result" port and the
        # CompletionWatcher / validator look at the wrong file (#883).
        block = block_cls(config=config)

        # Build config object.
        from scistudio.blocks.base.config import BlockConfig

        block_config = BlockConfig(**config)

        # ADR-051 prompt phase: build the panel view in this isolated worker
        # (FR-003) and exit. The block stays as isolated as any other block
        # while a human is in the loop. prepare_prompt receives the full input
        # collections (one interaction spans the whole input, FR-005). Mirrors
        # the pre-ADR-051 in-process path, which did not call validate() before
        # prepare_prompt, so we skip it here too.
        if phase == "prompt":
            from scistudio.blocks.base.interactive import (
                coerce_prompt,
                interactive_input_signature,
                serialise_storage_ref,
            )
            from scistudio.core.lineage.environment import EnvironmentSnapshot

            prompt = coerce_prompt(block.prepare_prompt(inputs, block_config))
            # FR-004: the panel payload must be a JSON object (a dict) and
            # strictly JSON-safe; reject otherwise rather than pickling or
            # truncating. allow_nan=False also rejects NaN/Infinity (non-standard
            # JSON). Failures propagate to the generic handler as a block error.
            if not isinstance(prompt.panel_payload, dict):
                raise TypeError(
                    f"panel_payload must be a JSON object (dict), got {type(prompt.panel_payload).__name__}"
                )
            json.dumps(prompt.panel_payload, allow_nan=False)
            env_snapshot = EnvironmentSnapshot.capture()
            prompt_envelope: dict[str, Any] = {
                "wire_version": WIRE_FORMAT_VERSION,
                "phase": "prompt",
                "panel_payload": prompt.panel_payload,
                "intermediate": [serialise_storage_ref(ref) for ref in prompt.intermediate],
                "environment": env_snapshot.to_dict(),
                # ADR-051 interaction memory: a generic identity fingerprint of
                # the inputs, used to decide whether a remembered decision can be
                # replayed (skipping the dialog) on a subsequent run.
                "input_signature": interactive_input_signature(inputs),
            }
            print(json.dumps(prompt_envelope))
            return

        # #1518 (DSN-2): enforce the documented Block.validate() contract on
        # the execution path. Before #1518 ``validate()`` had zero call sites
        # in the worker, so port/required/constraint checks were dead code and
        # an ill-typed graph failed deep inside ``run`` instead of at the
        # contract boundary. ``validate()`` raises ``ValueError`` on the first
        # failed check; we let that propagate to the generic handler below so
        # the run fails with the contract error rather than warn-and-continue.
        # The ``callable`` guard mirrors the ``get_effective_output_ports``
        # fallback below: real blocks always subclass ``Block`` (which defines
        # ``validate``); duck-typed stubs without it simply skip the check.
        _validate_fn = getattr(block, "validate", None)
        if callable(_validate_fn):
            _validate_fn(inputs)

        # Execute. Block.state / Block.transition were removed per #1334:
        # the engine-owned DAGScheduler (ADR-018 §8.1) is the authoritative
        # state machine. Cancellation from inside a block surfaces as a
        # ``BlockCancelledByAppError`` exception (#681 / #560) — the engine path
        # below catches it and forwards ``final_state="cancelled"`` via the
        # stdout envelope.
        try:
            outputs = block.run(inputs, block_config)
        except BlockCancelledByAppError:
            from scistudio.core.lineage.environment import EnvironmentSnapshot

            env_snapshot = EnvironmentSnapshot.capture()
            envelope: dict[str, Any] = {
                "wire_version": WIRE_FORMAT_VERSION,  # #1530
                "outputs": {},
                "environment": env_snapshot.to_dict(),
                "final_state": "cancelled",
            }
            print(json.dumps(envelope))
            return

        # #1330/#1811: enforce ADR-020 §3 transport contract — wrap bare
        # DataObject values on EVERY declared output port into length-one
        # Collections at the engine boundary (unconditional as of #1811;
        # the ``is_collection`` flag no longer gates the wrap). Idempotent
        # and a no-op for blocks that already self-wrap. Skipped when
        # ``run`` returned a non-dict (handled below by the ``_result``
        # fallback).
        if isinstance(outputs, dict):
            try:
                effective_output_ports = block.get_effective_output_ports()
            except AttributeError:
                effective_output_ports = list(getattr(type(block), "output_ports", []))
            _normalize_outputs(outputs, effective_output_ports)
            # #1518 (DSN-2): validate the produced outputs against the
            # declared output-port contract. A block that fails to emit a
            # required output port previously produced a partial result that
            # failed only when a *downstream* block tried to consume the
            # missing edge; enforce it at the producing boundary instead.
            _validate_outputs(outputs, effective_output_ports)

        # Capture environment inside subprocess for accurate lineage (issue #54).
        from scistudio.core.lineage.environment import EnvironmentSnapshot

        env_snapshot = EnvironmentSnapshot.capture()

        # Serialize outputs via the typed wire format.
        result = serialise_outputs(outputs, output_dir) if isinstance(outputs, dict) else {"_result": str(outputs)}

        envelope = {"wire_version": WIRE_FORMAT_VERSION, "outputs": result, "environment": env_snapshot.to_dict()}
        print(json.dumps(envelope))
    except StorageReferenceInvalidError as exc:
        _emit_storage_error(exc, inputs=inputs, block_id=block_id)
        sys.exit(1)
    except Exception:
        print(json.dumps({"error": traceback.format_exc()}))
        sys.exit(1)


if __name__ == "__main__":
    main()
