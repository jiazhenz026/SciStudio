"""MergeCollection -- concatenate several same-typed Collections into one.

A built-in utility block for Collection operations. Its input side has a
configurable (variadic) set of ports, so a user can merge several Collections
in one block instead of chaining pairwise merges. Filed under the ``routing``
subcategory alongside DataRouter and PairEditor.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject


class MergeCollection(ProcessBlock):
    """Concatenate several same-typed Collections into one.

    Wire two to eight Collections into the input ports and get a single
    Collection back, with the items joined in input-port order. Every input
    must hold the same item type. Use it to gather results from parallel
    branches into one stream.

    Ports: a variadic input side (2-8 ports), each accepting a Collection, and
    one ``output`` port carrying the concatenated Collection. Config: none of
    its own; the active input ports come from the block's port configuration.

    Example:
        >>> block = MergeCollection()
    """

    name: ClassVar[str] = "Merge Collection"
    """Display name shown in the block palette and on the canvas node."""

    algorithm: ClassVar[str] = "merge_collection"
    """Stable identifier for this block's transform; recorded in metadata."""

    description: ClassVar[str] = "Concatenate multiple same-typed Collections into one"
    """One-line summary shown in the palette and node tooltip."""

    subcategory: ClassVar[str] = "routing"
    """Palette subgroup this block is filed under (here, ``"routing"``)."""

    # Variadic input side: the concrete ports live in ``config["input_ports"]``;
    # the class-level list below is the default 2-port seed.
    variadic_inputs: ClassVar[bool] = True
    """When ``True``, the user adds and removes input ports instead of using a fixed list."""

    allowed_input_types: ClassVar[list[type]] = []
    """Data types selectable for the variadic input ports; empty means any type."""

    min_input_ports: ClassVar[int | None] = 2
    """Fewest input ports the user may configure."""

    max_input_ports: ClassVar[int | None] = 8
    """Most input ports the user may configure."""

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input_1", accepted_types=[DataObject], description="Collection to merge"),
        InputPort(name="input_2", accepted_types=[DataObject], description="Collection to merge"),
    ]
    """Default seed of two input ports; the user adds more up to ``max_input_ports``."""

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[DataObject], description="Merged Collection"),
    ]
    """The single output port ``output``, carrying the concatenated Collection."""

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Concatenate every connected input Collection in input-port order.

        Args:
            inputs: Mapping of input port name to its Collection. All connected
                Collections must share the same ``item_type``.
            config: The block configuration for this run.

        Returns:
            Mapping of ``output`` to a single Collection holding the items of
            all inputs, joined in input-port order.

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
