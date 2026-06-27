"""Fixture savers — trivial ``IOBlock`` mirroring a package's save side.

Declares two SAVE capabilities so core's unified Load/Save delegation
machinery (``scistudio.blocks.io._unified_dispatch``) has a real
package-owned saver to route to:

* ``scistudio-blocks-fixture.table.fix.save`` — writes a :class:`DataFrame`
  to a ``.fix`` file as JSON records. Used by the rewired
  ``SaveData`` package-capability-delegation test.
* ``scistudio-blocks-fixture.image.tiff.save`` — writes a fixture
  :class:`Image` to TIFF. Present so the Image type has a save capability
  to mirror the load side; not exercised by the round-trip-critical tests.

Neither writer carries real scientific behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort
from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scistudio.blocks.io.io_block import IOBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_fixture.types import Image


def _write_fix(obj: DataFrame, path: Path) -> None:
    """Write a DataFrame's in-memory arrow table to ``path`` as JSON records."""
    table = obj.get_in_memory_data()
    records = table.to_pylist() if table is not None else []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")


def _write_tiff(obj: Image, path: Path) -> None:
    """Write a fixture Image to TIFF (eager materialisation)."""
    import tifffile

    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(str(path), np.asarray(obj.to_memory()))


class SaveDataFixture(IOBlock):
    """Trivial saver owning fixture DataFrame and Image save capabilities."""

    direction: ClassVar[str] = "output"
    type_name: ClassVar[str] = "fixture.save_data"
    name: ClassVar[str] = "Save Data (fixture)"
    description: ClassVar[str] = "Fixture-only saver for core IO delegation tests."
    subcategory: ClassVar[str] = "io"

    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id="scistudio-blocks-fixture.table.fix.save",
            direction="save",
            data_type=DataFrame,
            format_id="fix",
            extensions=(".fix",),
            label="Fixture table",
            block_type="SaveDataFixture",
            handler="_write_fix",
            is_default=True,
            roundtrip_group="scistudio-blocks-fixture.table.fix",
            metadata_fidelity=MetadataFidelity(level="pixel_only"),
        ),
        FormatCapability(
            id="scistudio-blocks-fixture.image.tiff.save",
            direction="save",
            data_type=Image,
            format_id="tiff",
            extensions=(".tif", ".tiff"),
            label="Fixture TIFF image",
            block_type="SaveDataFixture",
            handler="_write_tiff",
            is_default=True,
            roundtrip_group="scistudio-blocks-fixture.image.tiff",
            metadata_fidelity=MetadataFidelity(level="pixel_only"),
        ),
    )

    supported_extensions: ClassVar[dict[str, str]] = {
        ".fix": "fix",
        ".tif": "tiff",
        ".tiff": "tiff",
    }

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[DataFrame, Image], required=True),
    ]
    _write_fix = staticmethod(_write_fix)
    _write_tiff = staticmethod(_write_tiff)

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"path": {"type": "string", "ui_priority": 0}},
        "required": ["path"],
    }

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:  # pragma: no cover
        raise NotImplementedError("SaveDataFixture is an output block; use save()")

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raw_path = config.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError("SaveDataFixture: config['path'] must be a non-empty string")
        path = Path(raw_path)
        item = obj[0] if isinstance(obj, Collection) and len(obj) == 1 else obj
        if isinstance(item, Image):
            _write_tiff(item, path)
        elif isinstance(item, DataFrame):
            _write_fix(item, path)
        else:
            raise ValueError(f"SaveDataFixture: unsupported object type {type(item).__name__}")
