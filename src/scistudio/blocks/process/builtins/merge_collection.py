"""MergeCollection — concatenate N same-typed Collections into one.

ADR-021: Built-in utility block for Collection operations. The input side is a
variadic port set (ADR-029) so a user can merge multiple Collections in a single
block instead of chaining pairwise merges. Lives in the ``routing`` subcategory
alongside DataRouter and PairEditor.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject


class MergeCollection(ProcessBlock):
    """Concatenate N same-typed Collections into one.

    ADR-021 / ADR-029: variadic input ports (2-8) let the user merge several
    Collections at once; the output is a single Collection. All inputs must
    share the same ``item_type``. Items are concatenated in input-port order.
    """

    name: ClassVar[str] = "Merge Collection"
    algorithm: ClassVar[str] = "merge_collection"
    description: ClassVar[str] = "Concatenate multiple same-typed Collections into one"
    subcategory: ClassVar[str] = "routing"

    # Variadic input side (ADR-029): the concrete ports live in
    # ``config["input_ports"]``; the class-level list is the default 2-port seed.
    variadic_inputs: ClassVar[bool] = True
    allowed_input_types: ClassVar[list[type]] = []
    min_input_ports: ClassVar[int | None] = 2
    max_input_ports: ClassVar[int | None] = 8

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input_1", accepted_types=[DataObject], description="Collection to merge"),
        InputPort(name="input_2", accepted_types=[DataObject], description="Collection to merge"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[DataObject], description="Merged Collection"),
    ]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Concatenate all connected input Collections in input-port order.

        Raises:
            TypeError: If any input is not a Collection, or the inputs do not
                all share the same ``item_type``.
            ValueError: If no input Collections are connected.
        """
        from scistudio.core.types.collection import Collection

        # Preserve the declared input-port order so the merge is deterministic
        # (``get_effective_input_ports`` reflects the variadic config order).
        ordered_ports = [p.name for p in self.get_effective_input_ports()]
        connected = [name for name in ordered_ports if name in inputs]
        # Defensive: append any inputs the engine passed that are not in the
        # declared port list, in stable order, so nothing is silently dropped.
        connected += [name for name in inputs if name not in connected]

        if not connected:
            raise ValueError("MergeCollection requires at least one connected input Collection")

        collections: list[Collection] = []
        for name in connected:
            value = inputs[name]
            if not isinstance(value, Collection):
                raise TypeError(f"MergeCollection requires Collection inputs; port '{name}' is not a Collection")
            collections.append(value)

        item_type = collections[0].item_type
        for name, col in zip(connected, collections, strict=True):
            if col.item_type != item_type:
                raise TypeError(
                    f"Cannot merge Collections with different item types: "
                    f"{item_type.__name__} vs {col.item_type.__name__} (port '{name}')"
                )

        merged_items: list[DataObject] = []
        for col in collections:
            merged_items.extend(list(col))

        return {"output": Collection(merged_items, item_type=item_type)}
