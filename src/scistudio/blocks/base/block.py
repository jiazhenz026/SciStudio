"""Block ABC — validate(), run(), postprocess() contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from scistudio.core.storage.ref import StorageReference
    from scistudio.core.types.collection import Collection

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import (
    InputPort,
    OutputPort,
    port_accepts_type,
    ports_from_config_dicts,
    validate_port_constraint,
)
from scistudio.blocks.base.state import BlockState, ExecutionMode

_VALID_TRANSITIONS: dict[BlockState, set[BlockState]] = {
    BlockState.IDLE: {BlockState.READY, BlockState.SKIPPED, BlockState.ERROR},
    BlockState.READY: {BlockState.RUNNING, BlockState.SKIPPED, BlockState.ERROR},
    BlockState.RUNNING: {BlockState.DONE, BlockState.PAUSED, BlockState.ERROR, BlockState.CANCELLED},
    BlockState.PAUSED: {BlockState.RUNNING, BlockState.ERROR, BlockState.CANCELLED},
    BlockState.DONE: {BlockState.IDLE},
    BlockState.ERROR: {BlockState.IDLE},
    BlockState.CANCELLED: {BlockState.IDLE},  # ADR-018: user explicitly terminated
    BlockState.SKIPPED: {BlockState.IDLE},  # ADR-018: upstream input unavailable
}


class Block(ABC):
    """Abstract base class for all processing blocks.

    Subclasses must override :meth:`run`.  The optional :meth:`validate` and
    :meth:`postprocess` hooks have working default implementations.
    """

    # -- class-level metadata --------------------------------------------------

    name: ClassVar[str] = "Unnamed Block"
    description: ClassVar[str] = ""
    version: ClassVar[str] = "0.1.0"

    # #588: Palette display subcategory. Leave empty to use base_category for grouping.
    # Subclasses may set e.g. ``subcategory = "segmentation"`` for fine-grained
    # palette grouping. The base_category (io, process, code, app, ai,
    # subworkflow) is always inferred from the class hierarchy and cannot be
    # overridden by a ClassVar. See issue #588.
    subcategory: ClassVar[str] = ""

    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = []

    # ADR-029 D8 / D11: variadic port flags and type constraints.
    # When ``variadic_inputs`` / ``variadic_outputs`` is True the block's port
    # list is determined per-instance from ``self.config["input_ports"]`` /
    # ``self.config["output_ports"]`` (list of ``{"name": str, "types": [str]}``)
    # rather than from the class-level ClassVar.  ``allowed_input_types`` /
    # ``allowed_output_types`` constrain the type dropdown in the port editor UI.
    variadic_inputs: ClassVar[bool] = False
    variadic_outputs: ClassVar[bool] = False

    # Block authors override these on variadic subclasses to restrict which
    # types users may choose in the port editor dropdown (e.g.
    # ``allowed_input_types = [Image, DataFrame]``).  An empty list means
    # "accept any DataObject subclass" — consistent with the port system's
    # own semantics (``accepted_types = []`` accepts anything).
    allowed_input_types: ClassVar[list[type]] = []
    allowed_output_types: ClassVar[list[type]] = []

    # ADR-029 Addendum 1: optional min/max constraints on variadic port count.
    # ``None`` means "no limit". Only meaningful when the corresponding
    # ``variadic_inputs`` / ``variadic_outputs`` flag is ``True``.
    min_input_ports: ClassVar[int | None] = None
    max_input_ports: ClassVar[int | None] = None
    min_output_ports: ClassVar[int | None] = None
    max_output_ports: ClassVar[int | None] = None

    # ADR-028 Addendum 1 D1: declarative dynamic-port override mechanism.
    # When non-None, must be a dict of the shape::
    #
    #     {
    #         "source_config_key": str,                          # config field whose value drives the override
    #         "output_port_mapping": {                          # port name -> enum value -> list of accepted type names
    #             "<port_name>": {
    #                 "<enum_value>": ["<TypeName>", ...],
    #                 ...
    #             },
    #             ...
    #         },
    #     }
    #
    # The shape is validated at registry scan time by
    # ``BlockRegistry._validate_dynamic_ports`` so malformed declarations fail
    # loudly at import time. Dynamic blocks (e.g. ``LoadData`` / ``SaveData``)
    # additionally override :meth:`get_effective_input_ports` /
    # :meth:`get_effective_output_ports` to compute their per-instance ports
    # from ``self.config``. The ClassVar itself is the static descriptor that
    # the API and frontend consume to render the dynamic-port UI.
    dynamic_ports: ClassVar[dict[str, Any] | None] = None

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.AUTO
    # ADR-020: batch_mode and on_batch_error REMOVED — Collection iteration is block-internal.
    # ADR-019: grace period for SIGTERM before SIGKILL on cancellation.
    terminate_grace_sec: ClassVar[float] = 5.0

    key_dependencies: ClassVar[list[str]] = []
    config_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    # -- instance lifecycle ----------------------------------------------------

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: BlockConfig = BlockConfig(**(config or {}))
        self.state: BlockState = BlockState.IDLE

    def transition(self, target: BlockState) -> None:
        """Transition to *target* state, raising if the transition is invalid."""
        allowed = _VALID_TRANSITIONS.get(self.state, set())
        if target not in allowed:
            raise RuntimeError(f"Invalid state transition: {self.state.value} -> {target.value}")
        self.state = target

    # -- ADR-028 Addendum 1 D2: effective-ports hooks --------------------------

    def get_effective_input_ports(self) -> list[InputPort]:
        """Return effective input ports for this instance.

        For variadic blocks (``variadic_inputs = True``), reads the port list
        from ``self.config["input_ports"]`` and converts it to
        :class:`InputPort` instances via :func:`ports_from_config_dicts`.
        Falls back to the class-level ``input_ports`` ClassVar when no
        per-instance config is present.

        For non-variadic blocks, returns a copy of the class-level
        ``input_ports`` ClassVar unchanged (ADR-028 Addendum 1 D2 behaviour).

        Framework callsites that need per-instance port information (e.g.
        :meth:`Block.validate`, ``ProcessBlock.run``,
        ``workflow/validator.py``) MUST go through this method instead of
        reading the ClassVar directly.
        """
        if type(self).variadic_inputs:
            config_ports = self.config.get("input_ports")
            if config_ports and isinstance(config_ports, list):
                return ports_from_config_dicts(config_ports, "input")  # type: ignore[return-value]
        return list(type(self).input_ports)

    def get_effective_output_ports(self) -> list[OutputPort]:
        """Return effective output ports for this instance.

        For variadic blocks (``variadic_outputs = True``), reads the port list
        from ``self.config["output_ports"]`` and converts it to
        :class:`OutputPort` instances via :func:`ports_from_config_dicts`.
        Falls back to the class-level ``output_ports`` ClassVar when no
        per-instance config is present.

        See :meth:`get_effective_input_ports` for the framework rationale.
        """
        if type(self).variadic_outputs:
            config_ports = self.config.get("output_ports")
            if config_ports and isinstance(config_ports, list):
                return ports_from_config_dicts(config_ports, "output")  # type: ignore[return-value]
        return list(type(self).output_ports)

    # -- hooks -----------------------------------------------------------------

    def validate(self, inputs: dict[str, Any]) -> bool:
        """Validate *inputs* against the block's port contract.

        Checks:
        1. All required ports have a value in *inputs*.
        2. Each supplied value's type is accepted by the port.
        3. Each port's constraint function (if any) passes.

        Returns ``True`` when all inputs satisfy their constraints.
        Raises ``ValueError`` on the first failed check.
        """
        # ADR-028 Addendum 1 D5: read effective ports so dynamic blocks
        # validate against their per-instance port set.
        effective_input_ports = self.get_effective_input_ports()
        port_map = {p.name: p for p in effective_input_ports}

        # Check required ports are present.
        for port in effective_input_ports:
            if port.required and port.name not in inputs and port.default is None:
                raise ValueError(f"Required input port '{port.name}' is missing.")

        # Check types and constraints for supplied inputs.
        for key, value in inputs.items():
            if key not in port_map:
                continue
            port = port_map[key]

            # Type check: handle Collection and plain types.
            # ADR-031 D2: ViewProxy eliminated — no ViewProxy branch needed.
            from scistudio.core.types.collection import Collection

            if isinstance(value, Collection):
                # ADR-020-Add6: Collection transparency — pass instance directly
                # so port_accepts_type() can inspect item_type.
                if port.accepted_types and not port_accepts_type(port, value):
                    accepted = [t.__name__ for t in port.accepted_types]
                    item_type_name = value.item_type.__name__ if value.item_type else "unknown"
                    raise ValueError(
                        f"Port '{port.name}': Collection item type {item_type_name} not compatible with {accepted}"
                    )
            else:
                actual_type = type(value)
                if port.accepted_types and not port_accepts_type(port, actual_type):
                    accepted = [t.__name__ for t in port.accepted_types]
                    raise ValueError(f"Port '{port.name}': got {actual_type.__name__}, expected one of {accepted}")

            # Constraint check.
            ok, desc = validate_port_constraint(port, value)
            if not ok:
                raise ValueError(f"Port '{port.name}' constraint failed: {desc}")

        # ADR-029 Addendum 1: validate variadic port count limits.
        if type(self).variadic_inputs:
            n_in = len(effective_input_ports)
            min_in = type(self).min_input_ports
            max_in = type(self).max_input_ports
            if min_in is not None and n_in < min_in:
                raise ValueError(f"Variadic input port count {n_in} is below minimum {min_in}.")
            if max_in is not None and n_in > max_in:
                raise ValueError(f"Variadic input port count {n_in} exceeds maximum {max_in}.")

        if type(self).variadic_outputs:
            effective_output_ports = self.get_effective_output_ports()
            n_out = len(effective_output_ports)
            min_out = type(self).min_output_ports
            max_out = type(self).max_output_ports
            if min_out is not None and n_out < min_out:
                raise ValueError(f"Variadic output port count {n_out} is below minimum {min_out}.")
            if max_out is not None and n_out > max_out:
                raise ValueError(f"Variadic output port count {n_out} exceeds maximum {max_out}.")

        return True

    @abstractmethod
    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Execute the block's main logic and return output mapping."""
        ...

    def postprocess(self, outputs: dict[str, Collection]) -> dict[str, Collection]:
        """Optional post-processing of *outputs* before downstream delivery.

        ADR-020: Outputs are ``dict[str, Collection]`` — each value is a
        Collection wrapping the block's output DataObjects for that port.
        Default implementation passes outputs through unchanged.
        """
        return outputs

    # -- ADR-020: Collection utilities (Tier 1/2/3 block authoring) ----------

    def process_item(self, item: Any, config: BlockConfig) -> Any:
        """Tier 1 entry point: override for per-item processing.

        The default ``run()`` in :class:`ProcessBlock` iterates the primary
        input Collection and calls this method for each item, auto-flushing
        each result. 80% of blocks only need to override this method.
        """
        raise NotImplementedError("Subclass must implement process_item()")

    @staticmethod
    def pack(items: list[Any], item_type: type | None = None) -> Any:
        """Pack a list of DataObjects into a Collection, auto-flushing each.

        Any item without a ``StorageReference`` is flushed to storage as a
        safety net (Tier 3).
        """
        from scistudio.core.types.collection import Collection

        flushed = [Block._auto_flush(item) for item in items]
        return Collection(flushed, item_type=item_type)

    @staticmethod
    def unpack(collection: Any) -> list[Any]:
        """Unpack a Collection into a list of DataObject instances.

        Returns DataObject instances (ADR-020-Add1). Block authors call
        ``.to_memory()`` when ready to access data.
        """
        return list(collection)

    @staticmethod
    def unpack_single(collection: Any) -> Any:
        """Unpack a length-1 Collection into a single DataObject.

        Raises ``ValueError`` if the Collection does not have exactly one item.
        """
        if len(collection) != 1:
            raise ValueError(f"Expected single-item Collection, got length {len(collection)}")
        return collection[0]

    @staticmethod
    def map_items(func: Any, collection: Any) -> Any:
        """Apply *func* to each item sequentially, auto-flushing each result.

        Returns a new Collection. Peak memory: 1 input + 1 output per iteration.
        """
        from scistudio.core.types.collection import Collection

        results = []
        for item in collection:
            result = func(item)
            result = Block._auto_flush(result)
            results.append(result)
        return Collection(results, item_type=collection.item_type)

    @staticmethod
    def parallel_map(func: Any, collection: Any, max_workers: int = 4) -> Any:
        """Apply *func* to each item in parallel, auto-flushing each result.

        Returns a new Collection.

        Warning: ``parallel_map`` loads ``max_workers`` items into memory
        concurrently. For large items (images, MSI datasets), set
        ``max_workers=1`` or use ``map_items()`` which processes one item
        at a time.
        """
        from concurrent.futures import ProcessPoolExecutor

        from scistudio.core.types.collection import Collection

        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(func, collection))
        flushed = [Block._auto_flush(r) for r in results]
        return Collection(flushed, item_type=collection.item_type)

    def persist_array(
        self,
        data_or_iterator: Any,
        shape: tuple[int, ...],
        dtype: Any,
        output_dir: str | None = None,
        chunks: tuple[int, ...] | None = None,
    ) -> StorageReference:
        """Write array data to zarr storage and return a :class:`StorageReference`.

        ADR-031 D4: persistence helper promoted from IOBlock to Block base class.

        ``data_or_iterator`` may be:

        - A numpy ndarray (written in one shot).
        - An iterator/generator yielding ``(index, chunk_array)`` tuples
          for streaming, constant-memory writes. For a 3-D array of shape
          ``(N, H, W)``, yield ``(i, page_2d)`` where ``page_2d`` has
          shape ``(H, W)`` for each ``i`` in ``range(N)``.

        Returns a :class:`StorageReference` pointing at the created zarr
        store.
        """
        import uuid
        from pathlib import Path

        import numpy as np
        import zarr

        from scistudio.core.storage.flush_context import get_output_dir
        from scistudio.core.storage.ref import StorageReference

        if output_dir is None:
            output_dir = get_output_dir()
        if not output_dir:
            raise RuntimeError("persist_array requires output_dir but none is configured.")

        import sys
        import tempfile as _tempfile

        store_name = f"{uuid.uuid4().hex[:12]}.zarr"
        store_path = str(Path(output_dir) / store_name)
        # Windows MAX_PATH: zarr internal subfiles add ~60 chars.
        # If total exceeds limit, redirect to a short temp dir.
        if sys.platform == "win32" and len(store_path) > 200:
            short_dir = _tempfile.mkdtemp(prefix="scistudio-zarr-")
            store_path = str(Path(short_dir) / store_name)
        Path(store_path).parent.mkdir(parents=True, exist_ok=True)

        np_dtype = np.dtype(dtype)
        if chunks is None:
            zarr_chunks: tuple[int, ...] | bool = True  # let zarr auto-chunk
        else:
            zarr_chunks = chunks

        z = zarr.open_array(store_path, mode="w", shape=shape, dtype=np_dtype, chunks=zarr_chunks)

        if isinstance(data_or_iterator, np.ndarray):
            z[:] = data_or_iterator
        else:
            # Iterator of (index, chunk_array) tuples — streaming write.
            for idx, chunk in data_or_iterator:
                z[idx] = chunk

        metadata = {"shape": list(shape), "dtype": str(np_dtype)}
        return StorageReference(
            backend="zarr",
            path=store_path,
            format="zarr",
            metadata=metadata,
        )

    def persist_table(self, table: Any, output_dir: str | None = None) -> StorageReference:
        """Write an Arrow table to parquet storage and return a :class:`StorageReference`.

        ADR-031 D4: persistence helper promoted from IOBlock to Block base class.

        ``table`` should be a ``pyarrow.Table``. The table is written to
        a parquet file in ``output_dir`` and the returned
        :class:`StorageReference` points at the persisted file.
        """
        import uuid
        from pathlib import Path

        from scistudio.core.storage.arrow_backend import ArrowBackend
        from scistudio.core.storage.flush_context import get_output_dir
        from scistudio.core.storage.ref import StorageReference

        if output_dir is None:
            output_dir = get_output_dir()
        if not output_dir:
            raise RuntimeError("persist_table requires output_dir but none is configured.")

        file_name = f"{uuid.uuid4().hex[:12]}.parquet"
        file_path = str(Path(output_dir) / file_name)
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        backend = ArrowBackend()
        ref = StorageReference(backend="arrow", path=file_path, format="parquet")
        result_ref = backend.write(table, ref)
        return result_ref

    @staticmethod
    def _auto_flush(obj: Any) -> Any:
        """Write in-memory DataObject to storage, return with StorageReference set.

        If the object already has a ``StorageReference``, return as-is (no-op).
        If no flush context output directory is configured, return as-is
        (the object stays in-memory — valid for in-process execution paths
        like SmokeHarness, interactive blocks, and unit tests).
        Called internally by ``map_items``, ``parallel_map``, ``pack``, and
        the ``process_item`` default ``run()``.

        ADR-031 D5: Artifact instances with ``file_path`` set use
        path-only transport and are exempt from auto-flush. They should
        NOT be read into memory and copied to managed storage.
        """
        from scistudio.core.types.base import DataObject

        if not isinstance(obj, DataObject):
            return obj

        # ADR-031 D5: Artifact with file_path uses path-only transport.
        from scistudio.core.types.artifact import Artifact

        if isinstance(obj, Artifact) and getattr(obj, "file_path", None) is not None:
            return obj

        # #436: Recursively flush CompositeData internal slots so that
        # child DataObjects (e.g. Label's raster Array) persist across
        # the subprocess boundary.
        from scistudio.core.types.composite import CompositeData

        if isinstance(obj, CompositeData):
            for _slot_name, slot_obj in obj._slots.items():
                if isinstance(slot_obj, DataObject) and slot_obj.storage_ref is None:
                    Block._auto_flush(slot_obj)

        if obj.storage_ref is not None:
            return obj

        from scistudio.core.storage.flush_context import get_output_dir

        output_dir = get_output_dir()
        if output_dir is None:
            return obj

        import uuid
        from pathlib import Path

        from scistudio.core.storage.backend_router import get_router

        router = get_router()
        try:
            ext = router.extension_for(type(obj))
        except KeyError:
            # No storage backend registered for this type (e.g. bare
            # DataObject used in tests).  Return as-is — the object stays
            # in-memory.
            return obj
        import sys
        import tempfile as _tempfile

        filename = f"{uuid.uuid4().hex[:12]}{ext}"
        target_path = str(Path(output_dir) / filename)
        # Windows MAX_PATH workaround (same as persist_array)
        if sys.platform == "win32" and len(target_path) > 200:
            short_dir = _tempfile.mkdtemp(prefix="scistudio-flush-")
            target_path = str(Path(short_dir) / filename)

        try:
            obj.save(target_path)
        except ValueError:
            # No in-memory data to persist (metadata-only object).
            # Return as-is — the object stays in-memory.
            return obj
        except Exception as exc:
            raise RuntimeError(f"auto_flush failed for {type(obj).__name__} at {target_path}: {exc}") from exc
        return obj
