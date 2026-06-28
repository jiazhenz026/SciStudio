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
from scistudio.blocks.base.state import ExecutionMode
from scistudio.stability import provisional, stable


@stable(since="0.3.1")
class Block(ABC):
    """Abstract base class every processing block inherits from.

    A block is one node in a workflow: it declares typed input and output ports,
    reads its parameters from a :class:`BlockConfig`, and turns input data
    objects into output data objects. This base class defines the contract the
    runtime relies on and supplies working defaults for everything except the
    main work.

    To write a block, subclass this (or a more specific category such as
    ``ProcessBlock``), describe it, and implement the work:

    - Declare named inputs and outputs by setting the :attr:`input_ports` and
      :attr:`output_ports` class attributes (lists of :class:`InputPort` /
      :class:`OutputPort`), and describe the parameters the block accepts in
      :attr:`config_schema`.
    - Implement :meth:`run`, which receives the inputs keyed by input-port name
      and the resolved config, and returns the outputs keyed by output-port
      name. Each output value is a
      :class:`~scistudio.core.types.collection.Collection`.
    - Optionally override :meth:`validate` (input checks before the run) and
      :meth:`postprocess` (adjust outputs before delivery); both have working
      defaults.

    The display metadata (:attr:`name`, :attr:`description`, :attr:`ui_icon`,
    :attr:`ui_color`, …) is how a block describes itself to the workflow editor
    and registry.

    Example:
        >>> from scistudio.blocks.base import Block, OutputPort
        >>> class Greeter(Block):  # doctest: +SKIP
        ...     name = "Greeter"
        ...     output_ports = [OutputPort(name="message", accepted_types=[])]
        ...     def run(self, inputs, config):
        ...         greeting = config.get("greeting", "hello")
        ...         return {"message": self.pack([greeting])}
    """

    # -- class-level metadata --------------------------------------------------

    name: ClassVar[str] = "Unnamed Block"
    """Human-readable block name shown in the palette and on the canvas node."""

    description: ClassVar[str] = ""
    """One-line description of what the block does, shown in the editor."""

    version: ClassVar[str] = "0.1.0"
    """Block version string; bump it when the block's behavior changes."""

    # The base category (io, process, code, app, ai, subworkflow) is always
    # inferred from the class hierarchy and cannot be overridden here (#588).
    subcategory: ClassVar[str] = ""
    """Optional finer palette grouping within the block's category (e.g. ``"segmentation"``).

    Leave empty to group the block by its inferred category only.
    """

    # Optional canvas-node display hints (#1839). The frontend resolves each as
    # block-declared, then category default, then a generic fallback. Provisional:
    # the icon set and color derivation are still settling.
    ui_color: ClassVar[str | None] = None
    """CSS hex color for this block's canvas node (e.g. ``"#ff5733"``).

    The frontend derives the border and foreground shades from it. ``None`` uses
    the block category's default color.
    """

    ui_icon: ClassVar[str | None] = None
    """Lucide icon *name* shown on this block's node (e.g. ``"Microscope"``).

    Resolved against the bundled Lucide icon set; an unknown name falls back to
    the category icon (never an error or a missing glyph). ``None`` uses the
    default.
    """

    input_ports: ClassVar[list[InputPort]] = []
    """The block's declared input ports (named, typed inputs it reads).

    Override with a list of :class:`InputPort`. For variadic blocks the
    effective ports come from config instead — see
    :meth:`get_effective_input_ports`.
    """

    output_ports: ClassVar[list[OutputPort]] = []
    """The block's declared output ports (named, typed outputs it emits).

    Override with a list of :class:`OutputPort`. The keys of the mapping returned
    by :meth:`run` must match these port names.
    """

    # When variadic, the effective ports come from the per-instance config
    # (self.config["input_ports"] / ["output_ports"]) rather than the ClassVar.
    variadic_inputs: ClassVar[bool] = False
    """Whether users may add a variable number of input ports to this block.

    When ``True``, the effective input ports are read per instance from the
    block's config rather than from :attr:`input_ports`.
    """

    variadic_outputs: ClassVar[bool] = False
    """Whether users may add a variable number of output ports to this block.

    When ``True``, the effective output ports are read per instance from the
    block's config rather than from :attr:`output_ports`.
    """

    allowed_input_types: ClassVar[list[type]] = []
    """Data types a user may pick for a variadic input port, limiting the editor dropdown.

    An empty list accepts any data object. Only meaningful when
    :attr:`variadic_inputs` is ``True``.
    """

    allowed_output_types: ClassVar[list[type]] = []
    """Data types a user may pick for a variadic output port, limiting the editor dropdown.

    An empty list accepts any data object. Only meaningful when
    :attr:`variadic_outputs` is ``True``.
    """

    # Only meaningful when the matching variadic_* flag is True.
    min_input_ports: ClassVar[int | None] = None
    """Minimum number of variadic input ports allowed; ``None`` means no limit."""

    max_input_ports: ClassVar[int | None] = None
    """Maximum number of variadic input ports allowed; ``None`` means no limit."""

    min_output_ports: ClassVar[int | None] = None
    """Minimum number of variadic output ports allowed; ``None`` means no limit."""

    max_output_ports: ClassVar[int | None] = None
    """Maximum number of variadic output ports allowed; ``None`` means no limit."""

    # The shape is validated when the registry scans blocks, so a malformed
    # declaration fails loudly at import time. Provisional: this descriptor is
    # still settling; the other authoring ClassVars are stable.
    dynamic_ports: ClassVar[dict[str, Any] | None] = None
    """Optional descriptor making a port's accepted types depend on a config value.

    When set, it is a dict of the shape::

        {
            "source_config_key": str,    # config field whose value drives the override
            "output_port_mapping": {     # port name -> config value -> accepted type names
                "<port_name>": {"<value>": ["<TypeName>", ...], ...},
                ...
            },
        }

    Blocks that use it (e.g. data load/save blocks) also override
    :meth:`get_effective_input_ports` / :meth:`get_effective_output_ports` to
    compute their per-instance ports. ``None`` means the block has no dynamic
    ports.
    """

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.AUTO
    """How the runtime runs this block; see :class:`ExecutionMode`. Defaults to automatic."""

    # Grace period before a running block is force-killed on cancellation.
    terminate_grace_sec: ClassVar[float] = 5.0
    """Seconds to wait after asking the block to stop before forcibly killing it.

    On cancellation the runtime sends a graceful stop signal first, then
    force-kills the block once this grace period elapses.
    """

    key_dependencies: ClassVar[list[str]] = []
    """Names of packages this block depends on, recorded with the run's lineage.

    Listing the packages whose versions matter (alongside the always-recorded
    core and array libraries) makes a run easier to reproduce. Empty by default.
    """

    config_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}
    """JSON Schema describing the block's configuration parameters.

    The workflow editor renders the parameter form from this schema. Defaults to
    an empty object schema (no parameters).
    """

    # -- instance lifecycle ----------------------------------------------------

    @stable(since="0.3.1")
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Create a block instance, wrapping *config* in a :class:`BlockConfig`.

        Args:
            config: Optional parameter mapping; an empty config is used when
                omitted.
        """
        self.config: BlockConfig = BlockConfig(**(config or {}))
        """The block's resolved configuration (a :class:`BlockConfig`)."""

    # -- interactive-block panel metadata --------------------------------------

    @provisional(since="0.3.1")
    def get_panel_manifest(self) -> Any | None:
        """Return this block's interactive panel manifest, or ``None``.

        Interactive blocks declare an ``interactive_panel`` (via
        :class:`InteractiveMixin`); this exposes it as block metadata for the API
        and registry. When the block pauses for interaction, the engine sends the
        manifest to the frontend so it knows which window to open.

        Returns:
            The block's :class:`PanelManifest`, or ``None`` for a non-interactive
            block.
        """
        return getattr(self, "interactive_panel", None)

    # -- effective-ports hooks -------------------------------------------------

    @stable(since="0.3.1")
    def get_effective_input_ports(self) -> list[InputPort]:
        """Return the input ports that actually apply to this block instance.

        For a variadic block (:attr:`variadic_inputs` is ``True``), reads the
        port list from this instance's config and builds :class:`InputPort`
        objects from it, falling back to the class-level :attr:`input_ports` when
        the config has none. For a non-variadic block, returns a copy of
        :attr:`input_ports`.

        Framework code that needs a block's ports should call this rather than
        read :attr:`input_ports` directly, so dynamic and variadic blocks resolve
        correctly.

        Returns:
            The effective input ports for this instance.
        """
        if type(self).variadic_inputs:
            config_ports = self.config.get("input_ports")
            if config_ports and isinstance(config_ports, list):
                return ports_from_config_dicts(config_ports, "input")  # type: ignore[return-value]
        return list(type(self).input_ports)

    @stable(since="0.3.1")
    def get_effective_output_ports(self) -> list[OutputPort]:
        """Return the output ports that actually apply to this block instance.

        The output-side counterpart of :meth:`get_effective_input_ports`: for a
        variadic block (:attr:`variadic_outputs` is ``True``) the ports come from
        this instance's config; otherwise it returns a copy of
        :attr:`output_ports`.

        Returns:
            The effective output ports for this instance.
        """
        if type(self).variadic_outputs:
            config_ports = self.config.get("output_ports")
            if config_ports and isinstance(config_ports, list):
                return ports_from_config_dicts(config_ports, "output")  # type: ignore[return-value]
        return list(type(self).output_ports)

    # -- hooks -----------------------------------------------------------------

    @stable(since="0.3.1")
    def validate(self, inputs: dict[str, Any]) -> bool:
        """Check that *inputs* satisfy the block's input-port contract.

        Verifies that every required port has a value, that each supplied value's
        type is accepted by its port, and that each port's optional constraint
        passes. For variadic blocks it also checks the port-count limits. The
        default implementation is usually enough; override it only for extra
        cross-input checks.

        Args:
            inputs: Incoming values keyed by input-port name.

        Returns:
            ``True`` when every input satisfies its port's contract.

        Raises:
            ValueError: On the first failed check (a missing required input, an
                unaccepted type, a failed constraint, or an out-of-range variadic
                port count), with a message naming the port.
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
    @stable(since="0.3.1")
    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Execute the block's work and return its outputs. **Must be overridden.**

        This is the one method every block must implement. It receives the
        block's inputs and resolved config and returns the data the block
        produces.

        Args:
            inputs: Input collections keyed by input-port name.
            config: The block's resolved :class:`BlockConfig`.

        Returns:
            A mapping from output-port name to the
            :class:`~scistudio.core.types.collection.Collection` emitted on that
            port. The keys must match the block's :attr:`output_ports`.
        """
        ...

    @stable(since="0.3.1")
    def postprocess(self, outputs: dict[str, Collection]) -> dict[str, Collection]:
        """Adjust the block's outputs before they are handed downstream.

        Optional hook called after :meth:`run`. The default returns *outputs*
        unchanged; override it to tweak the outputs (for example to attach
        metadata) without touching the main run logic.

        Args:
            outputs: Output collections keyed by output-port name, as returned by
                :meth:`run`.

        Returns:
            The (possibly modified) output mapping to deliver downstream.
        """
        return outputs

    # -- Collection utilities for block authoring ------------------------------

    @stable(since="0.3.1")
    def process_item(self, item: Any, config: BlockConfig) -> Any:
        """Process a single item of the input collection. **Override for per-item work.**

        The simplest way to write a block: implement just this method and the
        standard per-item ``run()`` (provided by ``ProcessBlock``) calls it once
        for each item in the primary input collection, saving each result for
        you. Most blocks only need this. The base implementation raises, because
        a per-item block must supply it.

        Args:
            item: One data object from the primary input collection.
            config: The block's resolved :class:`BlockConfig`.

        Returns:
            The processed data object for this item.

        Raises:
            NotImplementedError: If the block does not override this method.
        """
        raise NotImplementedError("Subclass must implement process_item()")

    @staticmethod
    @stable(since="0.3.1")
    def pack(items: list[Any], item_type: type | None = None) -> Any:
        """Bundle data objects into a Collection, saving any not yet saved.

        Use this in a custom :meth:`run` to turn a list of result data objects
        into a Collection to return on an output port. Any item not already
        written to storage is saved first, so downstream blocks can read it.

        Args:
            items: The data objects to bundle.
            item_type: Optional element type for the Collection; inferred when
                omitted.

        Returns:
            A Collection wrapping *items*.
        """
        from scistudio.core.types.collection import Collection

        flushed = [Block._auto_flush(item) for item in items]
        return Collection(flushed, item_type=item_type)

    @staticmethod
    @stable(since="0.3.1")
    def unpack(collection: Any) -> list[Any]:
        """Return a Collection's items as a plain list of data objects.

        Args:
            collection: The Collection to read.

        Returns:
            The Collection's items as a list. Call ``.to_memory()`` on an item
            when you are ready to read its data.
        """
        return list(collection)

    @staticmethod
    @stable(since="0.3.1")
    def unpack_single(collection: Any) -> Any:
        """Return the single data object from a length-one Collection.

        Args:
            collection: A Collection expected to hold exactly one item.

        Returns:
            The Collection's only item.

        Raises:
            ValueError: If the Collection does not hold exactly one item.
        """
        if len(collection) != 1:
            raise ValueError(f"Expected single-item Collection, got length {len(collection)}")
        return collection[0]

    @staticmethod
    @stable(since="0.3.1")
    def map_items(func: Any, collection: Any) -> Any:
        """Apply *func* to each item in turn, saving each result, into a new Collection.

        Processes one item at a time, so peak memory stays at about one input
        plus one output — the memory-safe choice for large items.

        Args:
            func: A function taking one item and returning the processed item.
            collection: The Collection to process.

        Returns:
            A new Collection of the results, in the same order.
        """
        from scistudio.core.types.collection import Collection

        results = []
        for item in collection:
            result = func(item)
            result = Block._auto_flush(result)
            results.append(result)
        return Collection(results, item_type=collection.item_type)

    @staticmethod
    @stable(since="0.3.1")
    def parallel_map(func: Any, collection: Any, max_workers: int = 4) -> Any:
        """Apply *func* to each item across worker processes, saving each result.

        Faster than :meth:`map_items` for CPU-heavy work, but it holds up to
        *max_workers* items in memory at once. For large items (images, MSI
        datasets) set ``max_workers=1`` or use :meth:`map_items`, which processes
        one item at a time.

        Args:
            func: A function taking one item and returning the processed item. It
                must be picklable, since it runs in a separate process.
            collection: The Collection to process.
            max_workers: Number of worker processes to run in parallel.

        Returns:
            A new Collection of the results.
        """
        from concurrent.futures import ProcessPoolExecutor

        from scistudio.core.types.collection import Collection

        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(func, collection))
        flushed = [Block._auto_flush(r) for r in results]
        return Collection(flushed, item_type=collection.item_type)

    @stable(since="0.3.1")
    def persist_array(
        self,
        data_or_iterator: Any,
        shape: tuple[int, ...],
        dtype: Any,
        output_dir: str | None = None,
        chunks: tuple[int, ...] | None = None,
    ) -> StorageReference:
        """Write array data to zarr storage and return a reference to it.

        Use this to save a large numpy array (or stream one in chunks) to the
        workflow's managed storage, getting back a :class:`StorageReference` you
        can attach to a data object instead of keeping the array in memory.

        Args:
            data_or_iterator: Either a numpy ndarray written in one shot, or an
                iterator/generator yielding ``(index, chunk_array)`` tuples for a
                streaming, constant-memory write. For a 3-D array of shape
                ``(N, H, W)``, yield ``(i, page)`` where ``page`` has shape
                ``(H, W)`` for each ``i`` in ``range(N)``.
            shape: Full shape of the array being written.
            dtype: Element data type (anything ``numpy.dtype`` accepts).
            output_dir: Directory to write into; defaults to the run's configured
                output directory.
            chunks: Optional zarr chunk shape; zarr auto-chunks when omitted.

        Returns:
            A :class:`StorageReference` pointing at the created zarr store.

        Raises:
            RuntimeError: If no output directory is given and none is configured.
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

    @stable(since="0.3.1")
    def persist_table(self, table: Any, output_dir: str | None = None) -> StorageReference:
        """Write an Arrow table to parquet storage and return a reference to it.

        Saves a ``pyarrow.Table`` to the workflow's managed storage and returns a
        :class:`StorageReference` pointing at the parquet file, so you can attach
        it to a data object instead of holding the table in memory.

        Args:
            table: The ``pyarrow.Table`` to write.
            output_dir: Directory to write into; defaults to the run's configured
                output directory.

        Returns:
            A :class:`StorageReference` pointing at the written parquet file.

        Raises:
            RuntimeError: If no output directory is given and none is configured.
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
