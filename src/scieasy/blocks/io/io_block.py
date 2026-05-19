"""IOBlock — abstract base for plugin-owned data ingress and egress.

Per ADR-028 §D1, ``IOBlock`` is an abstract base class. Subclasses
override :meth:`load` (for ``direction="input"``) or :meth:`save` (for
``direction="output"``); the default :meth:`run` dispatches based on
the ``direction`` ClassVar.

ADR-031 D4: ``load()`` now accepts an ``output_dir`` parameter so
loader implementations can persist data to storage and return
reference-only :class:`DataObject` instances. The base class provides
:meth:`persist_array` and :meth:`persist_table` helper methods for
streaming writes. The ``run()`` method enforces a safety net: any
DataObject returned without ``storage_ref`` is auto-flushed before
crossing the block boundary.

The legacy ``adapter_registry`` / ``adapters/`` dispatch layer was
removed in T-TRK-004. Concrete core loaders (``LoadData``, ``SaveData``)
arrive in T-TRK-007 and T-TRK-008. Plugin-owned IO blocks (e.g.
``LoadImage`` in ``scieasy-blocks-imaging``) subclass ``IOBlock``
directly and register via the ``scieasy.blocks`` entry-point group.
"""

from __future__ import annotations

import logging
import tempfile
from abc import abstractmethod
from typing import Any, ClassVar

from scieasy.blocks.base.block import Block
from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy.core.types.text import Text

_logger = logging.getLogger(__name__)


class IOBlock(Block):
    """Abstract base for blocks that load or save data.

    Subclasses must override :meth:`load` (for ``direction='input'``)
    or :meth:`save` (for ``direction='output'``). The default
    :meth:`run` dispatches based on the ``direction`` ClassVar.
    """

    # ``name`` and ``description`` are preserved from the pre-T-TRK-004
    # concrete IOBlock so that the existing ``BlockRegistry`` builtin
    # registration (``registry._scan_builtins``) keeps surfacing the
    # ``"IO Block"`` / ``"io_block"`` identity that integration tests,
    # workflow YAMLs, and the API connection-validator depend on. The
    # spec body at standards doc lines 914-976 omits these but does not
    # forbid them; ADR-028 §D1 only mandates ``load`` / ``save``
    # abstractness and the ``run()`` dispatch contract.
    name: ClassVar[str] = "IO Block"
    description: ClassVar[str] = "Abstract base for blocks that load or save data."

    direction: ClassVar[str] = "input"
    subcategory: ClassVar[str] = "io"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[DataObject], required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[DataObject]),
    ]
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

    @abstractmethod
    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """Load and return a single :class:`DataObject` or :class:`Collection`.

        ADR-031 D4: ``output_dir`` is the directory where loaders should
        persist data to storage. Implementations may EITHER:

        (a) Return an in-memory DataObject (simple path):
            The base class auto-persists it to storage via ``_auto_flush``.
            Works for small/medium files. Will OOM on very large files.

        (b) Write to storage directly using :meth:`persist_array` or
            :meth:`persist_table` and return a reference-only object
            (streaming path). Required for large files.

        Artifact subclasses are exempt — return with ``file_path``, no
        storage write needed.
        """
        ...

    @abstractmethod
    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Persist *obj* to the configured path."""
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

    # persist_array and persist_table are inherited from Block base class.
    # See Block.persist_array / Block.persist_table (ADR-031 Addendum 1).

    def run(
        self,
        inputs: dict[str, Collection],
        config: BlockConfig,
    ) -> dict[str, Collection]:
        """Dispatch to :meth:`load` or :meth:`save` based on ``direction``.

        For ``direction='input'`` the result of :meth:`load` is wrapped
        in a single-item :class:`Collection` if it is not already a
        Collection, and returned under the declared output port name.

        For ``direction='output'`` the declared input port is required
        and forwarded to :meth:`save`; the configured ``path`` is
        returned under a receipt key that defaults to ``"path"`` for
        backward compatibility.
        """
        if self.direction == "input":
            # ADR-031 D4: resolve output_dir for loader persistence.
            from scieasy.core.storage.flush_context import get_output_dir

            output_dir = get_output_dir() or tempfile.mkdtemp(prefix="scieasy-io-")
            result = self.load(config, output_dir=output_dir)
            if not isinstance(result, Collection):
                result = Collection(items=[result], item_type=type(result))
            # ADR-031 D4 safety net: auto-flush any DataObject without
            # storage_ref before it crosses the block boundary. Artifact
            # instances with file_path are exempt (D5 path-only transport).
            from scieasy.core.types.artifact import Artifact

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
