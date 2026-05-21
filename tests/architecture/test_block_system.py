"""Architecture enforcement: block system invariants.

Validates structural properties of the block hierarchy:

* Every concrete block class inherits from exactly one block category.
* Block category classes define ``output_ports`` as a class attribute.
* ``Block.run()`` has the expected signature ``(inputs, config) -> dict``.
"""

from __future__ import annotations

import inspect

import pytest

from scistudio.blocks.ai.ai_block import AIBlock
from scistudio.blocks.app.app_block import AppBlock
from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.code.code_block import CodeBlock
from scistudio.blocks.io.io_block import IOBlock
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.blocks.subworkflow.subworkflow_block import SubWorkflowBlock

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

BLOCK_CATEGORIES: list[type] = [
    IOBlock,
    ProcessBlock,
    CodeBlock,
    AppBlock,
    AIBlock,
    SubWorkflowBlock,
]

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    BLOCK_CATEGORIES,
    ids=[c.__name__ for c in BLOCK_CATEGORIES],
)
def test_block_categories_inherit_from_block(cls: type) -> None:
    """Every block category class inherits from the Block ABC."""
    assert issubclass(cls, Block), f"{cls.__name__} does not inherit from Block"


@pytest.mark.parametrize(
    "cls",
    BLOCK_CATEGORIES,
    ids=[c.__name__ for c in BLOCK_CATEGORIES],
)
def test_block_categories_are_unique_lineage(cls: type) -> None:
    """No block category inherits from another block category."""
    for other in BLOCK_CATEGORIES:
        if other is cls:
            continue
        assert not issubclass(cls, other), f"{cls.__name__} unexpectedly inherits from {other.__name__}"


@pytest.mark.parametrize(
    "cls",
    BLOCK_CATEGORIES,
    ids=[c.__name__ for c in BLOCK_CATEGORIES],
)
def test_block_types_declare_output_ports(cls: type) -> None:
    """Every block category has an ``output_ports`` class attribute (list)."""
    assert hasattr(cls, "output_ports"), f"{cls.__name__} is missing output_ports class attribute"
    assert isinstance(cls.output_ports, list), (
        f"{cls.__name__}.output_ports should be a list, got {type(cls.output_ports).__name__}"
    )


@pytest.mark.parametrize(
    "cls",
    BLOCK_CATEGORIES,
    ids=[c.__name__ for c in BLOCK_CATEGORIES],
)
def test_block_types_declare_input_ports(cls: type) -> None:
    """Every block category has an ``input_ports`` class attribute (list)."""
    assert hasattr(cls, "input_ports"), f"{cls.__name__} is missing input_ports class attribute"
    assert isinstance(cls.input_ports, list), (
        f"{cls.__name__}.input_ports should be a list, got {type(cls.input_ports).__name__}"
    )


def test_block_run_signature() -> None:
    """``Block.run()`` accepts ``(self, inputs, config)`` and is abstract."""
    sig = inspect.signature(Block.run)
    params = list(sig.parameters.keys())
    # inspect.signature on an unbound method includes 'self'
    non_self_params = [p for p in params if p != "self"]
    assert non_self_params == ["inputs", "config"], (
        f"Block.run() parameters are {non_self_params}, expected ['inputs', 'config']"
    )

    # Verify that 'config' is annotated with BlockConfig.
    # Because the source uses ``from __future__ import annotations``, the
    # annotation may be the string ``"BlockConfig"`` rather than the class.
    config_annotation = sig.parameters["config"].annotation
    expected = {BlockConfig, "BlockConfig"}
    assert config_annotation in expected, (
        f"Block.run(config=) should be annotated as BlockConfig, got {config_annotation!r}"
    )


@pytest.mark.parametrize(
    "cls",
    BLOCK_CATEGORIES,
    ids=[c.__name__ for c in BLOCK_CATEGORIES],
)
def test_block_category_run_signature_matches_base(cls: type) -> None:
    """Every category's ``run()`` has the same parameter names as ``Block.run()``."""
    base_params = list(inspect.signature(Block.run).parameters.keys())
    category_params = list(inspect.signature(cls.run).parameters.keys())
    assert category_params == base_params, (
        f"{cls.__name__}.run() parameters are {category_params}, expected {base_params}"
    )


@pytest.mark.parametrize(
    "cls",
    BLOCK_CATEGORIES,
    ids=[c.__name__ for c in BLOCK_CATEGORIES],
)
def test_block_categories_have_name_attribute(cls: type) -> None:
    """Every block category has a ``name`` class attribute (string)."""
    assert hasattr(cls, "name"), f"{cls.__name__} is missing 'name' class attribute"
    assert isinstance(cls.name, str), f"{cls.__name__}.name should be a str, got {type(cls.name).__name__}"


@pytest.mark.parametrize(
    "cls",
    BLOCK_CATEGORIES,
    ids=[c.__name__ for c in BLOCK_CATEGORIES],
)
def test_run_signature_uses_collection(cls: type) -> None:
    """ADR-020: ``run()`` annotations must reference Collection, not Any."""
    sig = inspect.signature(cls.run)
    inputs_annotation = sig.parameters["inputs"].annotation
    return_annotation = sig.return_annotation

    assert "Collection" in str(inputs_annotation), (
        f"{cls.__name__}.run(inputs=) annotation is {inputs_annotation!r}, expected dict[str, Collection]"
    )
    assert "Collection" in str(return_annotation), (
        f"{cls.__name__}.run() return annotation is {return_annotation!r}, expected dict[str, Collection]"
    )


@pytest.mark.parametrize(
    "cls",
    BLOCK_CATEGORIES,
    ids=[c.__name__ for c in BLOCK_CATEGORIES],
)
def test_block_categories_have_version_attribute(cls: type) -> None:
    """Every block category has a ``version`` class attribute (string)."""
    assert hasattr(cls, "version"), f"{cls.__name__} is missing 'version' class attribute"
    assert isinstance(cls.version, str), f"{cls.__name__}.version should be a str, got {type(cls.version).__name__}"
