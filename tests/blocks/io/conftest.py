"""Shared fixtures for ``tests/blocks/io`` — IOBlock ABC test helpers.

T-TRK-004 / ADR-028 §D1: ``IOBlock`` is an abstract base class. Any
test that needs a runnable IOBlock instance must subclass it and
override ``load`` / ``save``. ``InMemoryIOBlock`` is a minimal
in-memory subclass that records the most recent ``save`` call and
returns a configurable payload from ``load``; downstream IO tests
reuse it via the ``in_memory_io_block_cls`` fixture so we keep one
canonical fake.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.io.io_block import IOBlock
from scistudio.core.storage.flush_context import clear, set_output_dir
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


@pytest.fixture(autouse=True)
def _flush_context(tmp_path):
    """ADR-031 Addendum 1: auto_flush now hard-gates on output_dir."""
    set_output_dir(str(tmp_path))
    yield
    clear()


class InMemoryIOBlock(IOBlock):
    """Minimal concrete ``IOBlock`` subclass for ABC contract tests.

    Attributes
    ----------
    last_saved:
        The most recent ``(obj, config)`` pair passed to :meth:`save`,
        or ``None`` if :meth:`save` has not been called.
    payload:
        The :class:`DataObject` returned by :meth:`load` (override on
        the instance after construction to control the loaded value).
    """

    name: ClassVar[str] = "InMemory IO Block"
    description: ClassVar[str] = "Test-only in-memory IOBlock subclass for ABC contract tests."

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config=config)
        self.payload: DataObject = DataObject()
        self.last_saved: tuple[object, BlockConfig] | None = None

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        return self.payload

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        self.last_saved = (obj, config)


@pytest.fixture
def in_memory_io_block_cls() -> type[InMemoryIOBlock]:
    """Expose :class:`InMemoryIOBlock` as a fixture for parametrised tests."""
    return InMemoryIOBlock
