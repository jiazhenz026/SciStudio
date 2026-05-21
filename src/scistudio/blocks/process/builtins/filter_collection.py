"""FilterCollection — keep items matching a metadata predicate.

ADR-021: Built-in utility block for Collection operations.

Phase 11 / T-TRK-012: in addition to the legacy
``predicate_key`` / ``predicate_value`` equality match, the block now
accepts an ``expression: str`` config field. The expression is parsed
through an AST whitelist (see
:mod:`scistudio.blocks.process.builtins.expression_evaluator`) and is
evaluated once per item with ``item``, ``index``, ``meta``,
``framework``, and ``user`` in scope. There is no ``eval()`` path and
no "trusted mode" bypass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.builtins.expression_evaluator import (
    ExpressionEvaluator,
    build_scope,
)
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject

if TYPE_CHECKING:
    from scistudio.core.types.collection import Collection


class FilterCollection(ProcessBlock):
    """Keep items whose metadata matches a predicate.

    Two mutually exclusive predicate modes are supported:

    * ``expression`` — a Python-syntax boolean expression evaluated
      through the AST-whitelisted
      :class:`ExpressionEvaluator`. Available names: ``item``,
      ``index``, ``meta``, ``framework``, ``user``, and the whitelisted
      call ``len``.
    * ``predicate_key`` / ``predicate_value`` — legacy equality match
      against ``item.user`` (the free-form metadata slot). Kept for
      backward compatibility with ADR-021.

    The output Collection preserves the original ``item_type`` and may
    be empty.
    """

    name: ClassVar[str] = "Filter Collection"
    algorithm: ClassVar[str] = "filter_collection"
    description: ClassVar[str] = "Filter Collection items by metadata predicate"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[DataObject], description="Collection to filter"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[DataObject], description="Filtered Collection"),
    ]

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Filter items by predicate.

        Config params:
            expression (str, optional): AST-whitelisted boolean
                expression evaluated per item. Takes precedence over
                ``predicate_key`` / ``predicate_value`` when set.
            predicate_key (str, optional): Legacy ``item.user`` key to
                match on. Required when ``expression`` is not set.
            predicate_value (Any, optional): Legacy value to compare
                against the key.

        Raises:
            TypeError: If input is not a Collection.
            ValueError: If neither ``expression`` nor ``predicate_key``
                is provided, if both are provided, or if the expression
                contains a forbidden construct.
        """
        from scistudio.core.types.collection import Collection

        collection = inputs["input"]
        if not isinstance(collection, Collection):
            raise TypeError("FilterCollection requires a Collection input")

        expression = config.params.get("expression")
        predicate_key = config.params.get("predicate_key")

        if expression is not None and predicate_key is not None:
            raise ValueError("FilterCollection accepts either 'expression' or 'predicate_key', not both")

        if expression is not None:
            if not isinstance(expression, str):
                raise ValueError(f"FilterCollection 'expression' must be a str, got {type(expression).__name__}")
            evaluator = ExpressionEvaluator(expression)
            filtered: list[DataObject] = [
                item for index, item in enumerate(collection) if evaluator.evaluate(build_scope(item, index))
            ]
        else:
            if predicate_key is None:
                raise ValueError("FilterCollection requires either 'expression' or 'predicate_key' in config.params")
            predicate_value = config.params.get("predicate_value")
            filtered = [item for item in collection if item.user.get(predicate_key) == predicate_value]

        result = Collection(filtered, item_type=collection.item_type)
        return {"output": result}
