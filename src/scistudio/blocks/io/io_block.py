"""The abstract base class for blocks that read files in or write files out.

:class:`IOBlock` is what every data-ingress or data-egress block inherits from.
A subclass picks one direction and overrides one method:

- a *loader* sets ``direction = "input"`` and overrides :meth:`load`;
- a *saver* sets ``direction = "output"`` and overrides :meth:`save`.

The inherited :meth:`run` looks at the ``direction`` and calls the right one, so
subclasses never implement ``run`` themselves.

Loaders can stream large files straight to storage instead of holding them in
memory: :meth:`load` receives an ``output_dir`` and the base class offers
``persist_array`` / ``persist_table`` helpers for that. As a safety net,
:meth:`run` automatically writes any returned object that is still in memory out
to storage before it leaves the block.

Plugin-owned IO blocks (for example, an image loader shipped in a separate
package) subclass :class:`IOBlock` directly and register through the
``scistudio.blocks`` entry-point group.
"""

from __future__ import annotations

import logging
import tempfile
from abc import abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.io.capabilities import CapabilityDirection, FormatCapability, MetadataFidelity
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.text import Text
from scistudio.stability import stable

_logger = logging.getLogger(__name__)


def _collect_load_batch(
    path_list: list[Any],
    load_one: Callable[[str], DataObject | Collection],
    *,
    empty_item_type: type[DataObject],
) -> Collection:
    """Read each path with its own single-path call and collect the results.

    The single loop behind :attr:`IOBlock.accepts_path_list`'s default. Both
    execution routes share it so the declaration means the same thing
    everywhere: the core ``Load`` block's delegation
    (:func:`~scistudio.blocks.io._unified_dispatch.delegate_load`) and a
    user-facing loader's own :meth:`IOBlock.run`.

    A loader is free to answer one path with a :class:`Collection` — a loader
    that already packs its own result, or a format where one file holds several
    objects. Those are flattened into the batch in the order they were
    returned, so the caller receives the flat ``Collection`` of data objects
    the port's ``is_collection=True`` promises, never a Collection of
    Collections.

    The item type is inferred from what the loader returned rather than
    declared up front: a drop-in type imported by path is a distinct class
    object with the same ``__name__`` as the registry's, and ``Collection``
    compares item types by identity. Only an empty list needs a type
    stated, supplied by the caller (the delegated route passes the capability's
    declared data type; the direct route passes the loader's own declared
    output type).
    """
    # Development references: #1950, #2355, #2357.
    items: list[DataObject] = []
    for one_path in path_list:
        loaded = load_one(str(one_path))
        if isinstance(loaded, Collection):
            items.extend(loaded)
        else:
            items.append(loaded)
    if not items:
        return Collection(items=[], item_type=empty_item_type)
    return Collection(items=items)


@stable(since="0.3.1")
class IOBlock(Block):
    """Abstract base for a block that loads data from a file or saves it to one.

    Inherit from this to build a custom IO block. Choose a direction with the
    ``direction`` class attribute and override the matching method:

    - ``direction = "input"`` (a loader): override :meth:`load` to read the
      configured ``path`` and return a :class:`DataObject` or a
      :class:`Collection`. A loader has no data input port — it is a pure source.
      Write it for one file: when the user selects several, the runtime calls it
      once per path and collects the results. Set
      :attr:`accepts_path_list` to ``True`` to take the whole list in one call
      instead.
    - ``direction = "output"`` (a saver): override :meth:`save` to write the
      object arriving on the ``data`` input port to the configured ``path``.

    You do not override :meth:`run`; the base class reads ``direction`` and calls
    :meth:`load` or :meth:`save` for you. Declare the file formats the block
    handles in :attr:`format_capabilities` so the runtime can route files by
    extension and the UI can list the format. The base ``config_schema``
    contributes a required ``path`` field; subclasses add their own fields.

    Example:
        >>> from pathlib import Path
        >>> class LoadPlainText(IOBlock):
        ...     direction = "input"
        ...     def load(self, config, output_dir=""):
        ...         text = Path(config.get("path")).read_text(encoding="utf-8")
        ...         return Text(content=text, format="plain")
    """

    # ``name``/``description`` are kept so the builtin BlockRegistry scan keeps
    # surfacing the historical "IO Block"/"io_block" identity that integration
    # tests, workflow YAMLs, and the connection validator rely on.
    name: ClassVar[str] = "IO Block"
    """Display name of the block, shown in the UI block library."""
    description: ClassVar[str] = "Abstract base for blocks that load or save data."
    """One-line description of the block, shown in the UI."""

    direction: ClassVar[str] = "input"
    """``"input"`` for a loader (overrides :meth:`load`) or ``"output"`` for a
    saver (overrides :meth:`save`). Selects which method :meth:`run` calls."""
    subcategory: ClassVar[str] = "io"
    """Block-library subcategory this block is grouped under in the UI."""

    # Legacy extension->format scaffolding kept importable for the migration
    # window; the registry's extension dispatch still consults it at runtime.
    # New blocks should declare ``format_capabilities`` instead.
    supported_extensions: ClassVar[dict[str, str]] = {}
    """Legacy map from file suffix to a stable format id (e.g. ``".ome.tif"`` ->
    ``"ome_tiff"``); suffixes are lowercase with a leading dot and may be
    compound. Empty by default.

    .. deprecated:: 0.3.1
        Declare :attr:`format_capabilities` instead. This mapping is kept only so
        blocks written before the capability model still import, and it will be
        removed.
    """
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = ()
    """The file formats this block can read or write, as :class:`FormatCapability`
    records. This is the supported way to declare format support; the runtime and
    UI read it for extension-based routing. Empty on the base class."""
    accepts_path_list: ClassVar[bool] = False
    """Whether :meth:`load` wants a multi-file ``path`` list handed to it whole.

    ``False`` (the default) means the loader reads one file per call. Whenever
    a multi-path config reaches this loader — whether the core ``Load`` block
    dispatches to it or the loader runs as its own user-facing block — the
    runtime calls :meth:`load` once per path with a single-path config and
    collects the results into the :class:`Collection` the port declares.

    Set it to ``True`` only when the loader needs the whole batch in one call —
    to order a z-stack, or to align across files, say. :meth:`load` then
    receives ``path`` as the list it was configured with and owns the looping,
    the item ordering, and the returned :class:`Collection`.
    """

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[DataObject], required=False),
    ]
    """Declared input ports. Loaders (``direction="input"``) drop this to an empty
    list automatically, since a loader reads from its ``path`` rather than an
    incoming edge."""
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[DataObject]),
    ]
    """Declared output ports. The default single ``data`` port carries the loaded
    object; savers override this with an empty list."""
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": ["string", "array"],
                "items": {"type": "string"},
                "ui_priority": 0,
                "ui_widget": "file_browser",
            },
        },
        "required": ["path"],
    }
    """JSON-schema for the block's configuration. The base schema contributes a
    required ``path`` field (rendered as a file browser); subclasses merge in
    their own fields."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # #10: a loader (``direction="input"``) is a pure source — it reads from
        # its configured ``path``, never from an inbound edge — so it must not
        # expose an input port, otherwise the canvas renders a dangling left
        # handle. ``run()`` for the input direction only ever uses the output
        # port (``_resolved_load_output_port_name``); the inherited base input
        # port is dead weight. Enforce an empty input-port list for every IO
        # subclass (core ``load_data`` + package loaders) that did not declare
        # its own ``input_ports``.
        if getattr(cls, "direction", None) == "input" and "input_ports" not in cls.__dict__:
            cls.input_ports = []

    @classmethod
    @stable(since="0.3.1")
    def get_format_capabilities(cls) -> tuple[FormatCapability, ...]:
        """Return the file formats this block supports as capability records.

        Prefers the explicit :attr:`format_capabilities`. If those are empty but
        the legacy :attr:`supported_extensions` map is set, one capability is
        synthesized per format from that map (each marked ``is_synthesized=True``
        so tooling can tell synthesized records from hand-authored ones).

        Returns:
            A tuple of :class:`FormatCapability` records, or an empty tuple when
            the block declares neither source.
        """

        if cls.format_capabilities:
            return tuple(cls.format_capabilities)
        if not cls.supported_extensions:
            return ()

        capability_direction: CapabilityDirection = "load" if cls.direction == "input" else "save"
        data_type = cls._legacy_capability_data_type(capability_direction)
        handler = "load" if capability_direction == "load" else "save"
        by_format: dict[str, list[str]] = {}
        for extension, format_id in cls.supported_extensions.items():
            by_format.setdefault(str(format_id), []).append(extension)

        capabilities: list[FormatCapability] = []
        module = cls.__module__
        for format_id, extensions in sorted(by_format.items()):
            normalized_format = format_id.strip().lower()
            capabilities.append(
                FormatCapability(
                    id=f"{module}.{cls.__name__}.{capability_direction}.{normalized_format}".lower(),
                    direction=capability_direction,
                    data_type=data_type,
                    format_id=normalized_format,
                    extensions=tuple(extensions),
                    label=normalized_format.replace("_", " ").replace("-", " ").upper(),
                    block_type=cls.__name__,
                    handler=handler,
                    metadata_fidelity=MetadataFidelity(level="pixel_only"),
                    is_synthesized=True,
                )
            )
        return tuple(capabilities)

    @classmethod
    def _legacy_capability_data_type(cls, capability_direction: str) -> type[DataObject]:
        ports = cls.output_ports if capability_direction == "load" else cls.input_ports
        if ports:
            accepted_types = getattr(ports[0], "accepted_types", None)
            if accepted_types:
                candidate = accepted_types[0]
                if isinstance(candidate, type) and issubclass(candidate, DataObject):
                    return candidate
        return DataObject

    @abstractmethod
    @stable(since="0.3.1")
    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """Read the configured file and return its contents as a data object.

        Override this in a loader (``direction="input"``). Read the path from
        ``config`` and return either a single :class:`DataObject` or a
        :class:`Collection` of them. There are two ways to hand back the data:

        - **Simple** — return an in-memory object; the base class writes it out
          to storage for you. Fine for small or medium files, but a very large
          file can exhaust memory.
        - **Streaming** — write to storage yourself with :meth:`persist_array`
          or :meth:`persist_table` and return a reference-only object. Use this
          for large files.

        :class:`~scistudio.core.types.artifact.Artifact` results are exempt:
        return one carrying a ``file_path`` and no storage write is needed.

        Args:
            config: The block's configuration; read ``config.get("path")`` and
                any block-specific fields from here.
            output_dir: Directory to stream large outputs into when taking the
                streaming path.

        Returns:
            The loaded :class:`DataObject`, or a :class:`Collection` of them.
        """
        ...

    @abstractmethod
    @stable(since="0.3.1")
    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Write *obj* to the configured file path.

        Override this in a saver (``direction="output"``). The object arrives on
        the block's ``data`` input port; read the destination from
        ``config.get("path")``.

        Args:
            obj: The :class:`DataObject` (or :class:`Collection`) to write out.
            config: The block's configuration, including the target ``path``.
        """
        ...

    def _resolved_input_port_name(self) -> str:
        """Return the active input-port name for this IO block."""
        getter = getattr(self, "get_effective_input_ports", None)
        ports = getter() if callable(getter) else self.input_ports
        return ports[0].name if ports else "data"

    def _resolved_load_output_port_name(self) -> str:
        """Return the active output-port name for input-direction dispatch."""
        getter = getattr(self, "get_effective_output_ports", None)
        ports = getter() if callable(getter) else self.output_ports
        return ports[0].name if ports else "data"

    def _resolved_save_receipt_port_name(self) -> str:
        """Return the receipt port name for output-direction dispatch.

        Legacy compatibility: subclasses that inherit the base
        ``output_ports=[OutputPort(name="data", ...)]`` still receive the
        historical ``"path"`` receipt key unless they explicitly override
        ``output_ports`` with a concrete receipt port.
        """
        getter = getattr(self, "get_effective_output_ports", None)
        ports = getter() if callable(getter) else self.output_ports
        if not ports or self.__class__.output_ports is IOBlock.output_ports:
            return "path"
        return ports[0].name

    def _detect_format(self, path: Path) -> str | None:
        """Look up the format identifier for *path* in :attr:`supported_extensions`.

        matching is case-insensitive and prefers compound
        suffixes over single suffixes. For example, given a mapping that
        contains both ``".ome.tif"`` and ``".tif"``, a path ending in
        ``".ome.tif"`` resolves to the compound entry; a path ending in
        ``".tif"`` alone resolves to the single entry; a path ending in
        ``".TIF"`` resolves to either via case-insensitive comparison.

        Returns the mapped format identifier, or ``None`` if the suffix
        is not declared (including the base-class default of an empty
        :attr:`supported_extensions` mapping).
        """
        # Development references: ADR-028.
        if not self.supported_extensions:
            return None
        # Case-insensitive: normalize both the path suffixes and the keys.
        # ``Path.suffixes`` returns ``[".ome", ".tif"]`` for ``foo.ome.tif``.
        # We probe the longest compound suffix first, then fall back to the
        # single trailing suffix. This avoids accidentally short-circuiting
        # on a single suffix when a compound entry is registered.
        normalized = {k.lower(): v for k, v in self.supported_extensions.items()}
        suffixes = [s.lower() for s in path.suffixes]
        # Try suffix combinations from longest to shortest (compound-first).
        for start in range(len(suffixes)):
            candidate = "".join(suffixes[start:])
            if candidate in normalized:
                return normalized[candidate]
        return None

    def _load_with_path_fanout(self, config: BlockConfig, *, output_dir: str) -> DataObject | Collection:
        """Call :meth:`load` once — or once per path when ``path`` is a list.

        The fan-out used to live only in
        :func:`~scistudio.blocks.io._unified_dispatch.delegate_load`, so a
        loader executed as its own user-facing block still received the whole
        list despite the default ``accepts_path_list = False`` — the public
        contract had semantics on the delegated route only. Both routes now
        share :func:`_collect_load_batch`, so the declaration is honoured
        wherever the loader runs. A loader that declared
        ``accepts_path_list = True`` keeps receiving the list intact.
        """
        # Development references: #2355, #2357.
        raw_path = config.get("path")
        if isinstance(raw_path, list) and not type(self).accepts_path_list:
            return _collect_load_batch(
                raw_path,
                lambda one_path: self.load(
                    self._config_with_single_path(config, one_path),
                    output_dir=output_dir,
                ),
                empty_item_type=type(self)._legacy_capability_data_type("load"),
            )
        return self.load(config, output_dir=output_dir)

    @staticmethod
    def _config_with_single_path(config: BlockConfig, one_path: str) -> BlockConfig:
        """Return *config* unchanged except ``path`` carries exactly *one_path*.

        Only ``path`` differs per fanned-out call; every other field — explicit
        ``params`` and runtime-injected Pydantic extras alike — must still reach
        the loader. ``path`` sits in ``params`` for a hand-built config and in
        the extras for an engine-constructed one
        (:meth:`~scistudio.blocks.base.config.BlockConfig.get` reads both), so
        replace it where it actually lives.
        """
        if "path" in (config.params or {}):
            return config.model_copy(update={"params": {**config.params, "path": one_path}})
        return config.model_copy(update={"path": one_path})

    # persist_array and persist_table are inherited from Block base class.
    # See Block.persist_array / Block.persist_table (ADR-031 Addendum 1).

    @stable(since="0.3.1")
    def run(
        self,
        inputs: dict[str, Collection],
        config: BlockConfig,
    ) -> dict[str, Collection]:
        """Run the block: call :meth:`load` or :meth:`save` based on ``direction``.

        You normally do not override this. For a loader (``direction="input"``)
        it calls :meth:`load`, wraps a bare result in a single-item
        :class:`Collection`, writes any still-in-memory object out to storage,
        and returns it under the output port name. For a saver
        (``direction="output"``) it takes the object from the required input
        port, calls :meth:`save`, and returns the written path as a receipt.

        Args:
            inputs: Objects arriving on the block's input ports, keyed by port
                name. A saver requires its ``data`` port to be present.
            config: The block's configuration (including ``path``).

        Returns:
            A mapping from output port name to a :class:`Collection`: the loaded
            data for a loader, or a single-item ``Text`` Collection holding the
            written path for a saver.

        Raises:
            ValueError: if a saver is run without its required input present.
        """
        if self.direction == "input":
            # ADR-031 D4: resolve output_dir for loader persistence.
            from scistudio.core.storage.flush_context import get_output_dir

            output_dir = get_output_dir() or tempfile.mkdtemp(prefix="scistudio-io-")
            result = self._load_with_path_fanout(config, output_dir=output_dir)
            if not isinstance(result, Collection):
                result = Collection(items=[result], item_type=type(result))
            # ADR-031 D4 safety net: auto-flush any DataObject without
            # storage_ref before it crosses the block boundary. Artifact
            # instances with file_path are exempt (D5 path-only transport).
            from scistudio.core.types.artifact import Artifact

            for item in result:
                if (
                    isinstance(item, DataObject)
                    and item.storage_ref is None
                    and not (isinstance(item, Artifact) and item.file_path is not None)
                ):
                    self._auto_flush(item)
            return {self._resolved_load_output_port_name(): result}
        else:
            input_port_name = self._resolved_input_port_name()
            data = inputs.get(input_port_name)
            if data is None:
                raise ValueError(f"IOBlock(output) requires {input_port_name!r} input")
            self.save(data, config)
            # T-TRK-008: wrap the path receipt in a single-item Collection
            # of Text so the return type matches the public
            # ``dict[str, Collection]`` signature without a type-ignore
            # suppression. The pre-T-TRK-004 IOBlock returned a bare
            # string here; the spec body for the post-T-TRK-004 ABC made
            # the same shape literal which forced a targeted
            # ``# type: ignore[dict-item]``. Wrapping in a typed
            # ``Text`` Collection preserves the "configured path" receipt
            # semantics for downstream consumers (they call
            # ``coll[0].content`` instead of ``result["path"]``) and
            # restores strict typing across the IO surface. See
            # ``project_phase11_ttrk007_008_bookkeeping.md`` Item 1.
            path_receipt = Text(content=str(config.get("path")), format="plain")
            return {self._resolved_save_receipt_port_name(): Collection(items=[path_receipt], item_type=Text)}
