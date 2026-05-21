"""SplitCollection — split a Collection by index or condition.

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


class SplitCollection(ProcessBlock):
    """Split Collection by index into 2 Collections.

    ADR-021: Splits at ``config.params["split_index"]`` (defaults to midpoint).
    Both output Collections preserve the original item_type.
    """

    name: ClassVar[str] = "Split Collection"
    algorithm: ClassVar[str] = "split_collection"
    description: ClassVar[str] = "Split a Collection by index"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[DataObject], description="Collection to split"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output_a", accepted_types=[DataObject], description="First split"),
        OutputPort(name="output_b", accepted_types=[DataObject], description="Second split"),
    ]

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Split a Collection at ``split_index``.

        Config params:
            split_index (int): Index to split at. Defaults to ``len(collection) // 2``.

        Raises:
            TypeError: If input is not a Collection.
        """
        from scistudio.core.types.collection import Collection

        collection = inputs["input"]
        if not isinstance(collection, Collection):
            raise TypeError("SplitCollection requires a Collection input")
        items = list(collection)
        split_index = config.params.get("split_index", len(items) // 2)
        part_a = items[:split_index]
        part_b = items[split_index:]
        output_a = Collection(part_a, item_type=collection.item_type)
        output_b = Collection(part_b, item_type=collection.item_type)
        return {"output_a": output_a, "output_b": output_b}
