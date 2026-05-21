"""Smoke-test ``NoopIOBlock`` — concrete IOBlock subclass for cascade tests.

T-TRK-004 / ADR-028 §D1: ``IOBlock`` is now an abstract base class.
However, ~6 existing test files (api/test_workflows, api/test_data,
integration/test_cancel_scenario, integration/test_multimodal_workflow,
api/test_blocks) reference the legacy ``block_type="io_block"`` string
via the BlockRegistry to construct workflows that the scheduler then
instantiates. Concrete core loaders (``LoadData`` / ``SaveData``) only
arrive in T-TRK-007 / T-TRK-008, so until then there is no instantiable
``io_block`` shipped by core.

This module follows the precedent set by ``tests/fixtures/noop_block.py``
(T-TRK-003): it is a TEST-ONLY concrete subclass that is registered
into every fresh ``BlockRegistry`` via the ``tests/conftest.py``
``_scan_builtins`` patch, aliased to the legacy ``"io_block"``
type_name. Production registries built outside the pytest session do
not see this fixture.

The semantics mirror the *old* concrete ``IOBlock``:

* ``direction='input'`` reads the file at ``config.params.path`` and
  builds a single-item ``Collection`` of one ``DataObject`` carrying a
  ``StorageReference``. No payload data is loaded — references only.
* ``direction='output'`` writes a one-line marker file at
  ``config.params.path`` so the legacy "did it run?" assertions hold.

Identity preservation is the load-bearing invariant for the workflow
smoke tests; do **not** add transformation logic here.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.io.io_block import IOBlock
from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


class NoopIOBlock(IOBlock):
    """Test-only concrete :class:`IOBlock` for the workflow smoke suite."""

    type_name: ClassVar[str] = "noop_io"
    name: ClassVar[str] = "IO Block"
    description: ClassVar[str] = "Test-only concrete IOBlock that creates lazy StorageReferences."

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """Build a single-item :class:`Collection` of one
        :class:`DataObject` referencing the configured path."""
        path_str = config.get("path") or config.params.get("path")
        if not path_str:
            raise ValueError("NoopIOBlock requires 'path' in config.params")
        path = Path(path_str)
        ref = StorageReference(
            backend="filesystem",
            path=str(path),
            format=path.suffix.lower().lstrip(".") or "bin",
        )
        return Collection(items=[DataObject(storage_ref=ref)], item_type=DataObject)

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Write a one-line marker file at the configured path so the
        smoke tests' "did it run?" assertions hold."""
        path_str = config.get("path") or config.params.get("path")
        if not path_str:
            raise ValueError("NoopIOBlock requires 'path' in config.params")
        path = Path(path_str)
        path.parent.mkdir(parents=True, exist_ok=True)
        # ``obj`` may be a Collection of items or a single DataObject;
        # we don't materialise either — just record that save was called.
        item_count = len(obj) if isinstance(obj, Collection) else 1
        path.write_text(f"NoopIOBlock saved {item_count} item(s)\n", encoding="utf-8")
