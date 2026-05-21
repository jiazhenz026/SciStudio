"""Smoke tests for the relocated :class:`tests.fixtures.noop_block.NoopBlock`.

Per ``docs/specs/phase11-implementation-standards.md`` T-TRK-003 (f), this
file verifies that the relocated fixture instantiates and that the
identity-in == identity-out invariant still holds. The latter is
load-bearing for every existing test that uses NoopBlock as a generic
side-effect-free Process block in a workflow.
"""

from __future__ import annotations

import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.storage.flush_context import clear, set_output_dir
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from tests.fixtures.noop_block import NoopBlock


@pytest.fixture(autouse=True)
def _flush_context(tmp_path):
    """ADR-031 Addendum 1: auto_flush now hard-gates on output_dir."""
    set_output_dir(str(tmp_path))
    yield
    clear()


def test_noop_instantiates() -> None:
    """NoopBlock constructs without arguments."""
    block = NoopBlock()
    assert block is not None
    assert block.type_name == "noop"
    assert block.algorithm == "transform"


def test_noop_process_item_is_identity() -> None:
    """``process_item`` returns the input object unchanged (no copy)."""
    block = NoopBlock()
    config = BlockConfig()
    obj = DataObject()
    result = block.process_item(obj, config)
    assert result is obj


def test_noop_run_passes_collection_through_unchanged() -> None:
    """``run`` returns a Collection whose items match the input items by identity."""
    block = NoopBlock()
    config = BlockConfig()
    inputs = [DataObject(), DataObject(), DataObject()]
    collection = Collection(inputs, item_type=DataObject)

    outputs = block.run({"input": collection}, config)

    assert "output" in outputs
    out_collection = outputs["output"]
    assert isinstance(out_collection, Collection)
    out_items = list(out_collection)
    assert len(out_items) == len(inputs)
    for original, returned in zip(inputs, out_items, strict=True):
        assert returned is original
