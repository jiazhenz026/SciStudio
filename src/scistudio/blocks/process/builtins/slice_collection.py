"""SliceCollection — extract a sub-range from a Collection.

ADR-021: Built-in utility block for Collection operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject

if TYPE_CHECKING:
    from scistudio.core.types.collection import Collection


class SliceCollection(ProcessBlock):
    """Extract sub-range [start:end] from a Collection.

    ADR-021: ``start`` defaults to 0, ``end`` defaults to ``len(collection)``.
    Result preserves the original item_type.
    """

    name: ClassVar[str] = "Slice Collection"
    algorithm: ClassVar[str] = "slice_collection"
    description: ClassVar[str] = "Extract a sub-range from a Collection"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[DataObject], description="Collection to slice"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[DataObject], description="Sliced Collection"),
    ]

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Slice a Collection from ``start`` to ``end``.

        Config params:
            start (int): Start index (inclusive). Defaults to 0.
            end (int): End index (exclusive). Defaults to ``len(collection)``.

        Raises:
            TypeError: If input is not a Collection.
        """
        from scistudio.core.types.collection import Collection

        collection = inputs["input"]
        if not isinstance(collection, Collection):
            raise TypeError("SliceCollection requires a Collection input")
        items = list(collection)
        start = config.params.get("start", 0)
        end = config.params.get("end", len(items))
        sliced = items[start:end]
        result = Collection(sliced, item_type=collection.item_type)
        return {"output": result}
