"""Two-input image calculator with AST-restricted expressions."""

from __future__ import annotations

import ast
from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio_blocks_imaging.types import Image

_ALLOWED_NODES = frozenset(
    {
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Name,
        ast.Constant,
        ast.Load,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.UAdd,
        ast.USub,
    }
)
_ALLOWED_VARIABLES = frozenset({"a", "b"})


class ImageCalculator(ProcessBlock):
    """Two-input image calculator: ``out = expr(a, b)``."""

    type_name: ClassVar[str] = "imaging.image_calculator"
    name: ClassVar[str] = "Image Calculator"
    description: ClassVar[str] = "Two-input image calculator. Evaluate an AST-restricted expression in 'a' and 'b'."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "math"
    algorithm: ClassVar[str] = "image_calculator"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="a", accepted_types=[Image], description="Left operand."),
        InputPort(name="b", accepted_types=[Image], description="Right operand."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="result", accepted_types=[Image], description="Result image."),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "default": "a + b",
                "description": "AST-restricted expression in names 'a' and 'b'.",
            },
        },
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        expression = _expression(config)
        return _calculate_image(item, item, expression=expression)

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        expression = _expression(config)
        left = inputs["a"]
        right = inputs["b"]

        if isinstance(left, Collection) or isinstance(right, Collection):
            left_items = _require_collection(left, "a")
            right_items = _require_collection(right, "b")
            results = [
                _calculate_image(a_item, b_item, expression=expression)
                for a_item, b_item in _broadcast_pairs(left_items, right_items)
            ]
            return {"result": Collection(items=_to_data_objects(results), item_type=Image)}

        return {"result": _calculate_image(cast(Image, left), cast(Image, right), expression=expression)}


def _calculate_image(a: Image, b: Image, *, expression: str) -> Image:
    if a.axes != b.axes:
        raise ValueError(f"ImageCalculator: axes must match exactly (got {a.axes} vs {b.axes})")

    a_data = _image_data(a)
    b_data = _image_data(b)
    if a_data.shape != b_data.shape:
        raise ValueError(f"ImageCalculator: shape mismatch {a_data.shape} vs {b_data.shape}")

    result = np.asarray(_evaluate_expression(expression, a_data, b_data))
    if result.shape != a_data.shape:
        raise ValueError(
            f"ImageCalculator: expression must preserve image shape (got {result.shape} vs {a_data.shape})"
        )
    return _make_derived_image(a, result)


def _evaluate_expression(expression: str, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    tree = _parse_expression(expression)
    compiled = compile(tree, "<image-calculator>", "eval")
    result = eval(compiled, {"__builtins__": {}}, {"a": a, "b": b})
    return np.asarray(result)


def _parse_expression(expression: str) -> ast.Expression:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"ImageCalculator: expression is not valid Python syntax: {exc.msg}") from exc
    _validate_expression_ast(tree)
    return tree


def _validate_expression_ast(tree: ast.Expression) -> None:
    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODES:
            raise ValueError(f"ImageCalculator: forbidden expression node {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_VARIABLES:
            raise ValueError(
                f"ImageCalculator: unknown variable {node.id!r}; allowed variables are {sorted(_ALLOWED_VARIABLES)}"
            )


def _expression(config: BlockConfig) -> str:
    expression = config.get("expression", "a + b")
    if not isinstance(expression, str):
        raise ValueError(f"ImageCalculator: expression must be a string, got {type(expression).__name__}")
    return expression


def _require_collection(raw: Any, port_name: str) -> list[Image]:
    if not isinstance(raw, Collection):
        raise ValueError(f"ImageCalculator: input {port_name!r} must be a Collection when any input is a Collection")

    items: list[Image] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Image):
            raise ValueError(
                f"ImageCalculator: input {port_name!r} item[{index}] must be Image, got {type(item).__name__}"
            )
        items.append(item)
    return items


def _broadcast_pairs(left: list[Image], right: list[Image]) -> list[tuple[Image, Image]]:
    if len(left) == len(right):
        return list(zip(left, right, strict=True))
    if len(left) == 1:
        return [(left[0], item) for item in right]
    if len(right) == 1:
        return [(item, right[0]) for item in left]
    raise ValueError(
        "ImageCalculator: Collection inputs must have the same length or one side must have length 1 "
        f"(got {len(left)} vs {len(right)})"
    )


def _image_data(image: Image) -> np.ndarray:
    if image.storage_ref is None and hasattr(image, "_data") and getattr(image, "_data", None) is not None:
        return np.asarray(image._data)  # type: ignore[attr-defined]
    return np.asarray(image.to_memory())


def _make_derived_image(source: Image, data: np.ndarray) -> Image:
    result = Image(
        axes=list(source.axes),
        shape=tuple(data.shape),
        dtype=data.dtype,
        framework=source.framework.derive(),
        meta=source.meta,
        user=dict(source.user),
        storage_ref=None,
    )
    result._data = data  # type: ignore[attr-defined]
    return result


def _to_data_objects(images: list[Image]) -> list[DataObject]:
    return list(images)


__all__ = ["ImageCalculator"]
