"""Fixture image loader — a trivial ``IOBlock`` mirroring ``LoadImage``.

Loads a TIFF file into a fixture :class:`Image`. The implementation is
deliberately minimal: it declares one TIFF ``FormatCapability`` (so the
capability-dispatch machinery in core has something to route to) and reads
the file eagerly via ``tifffile``. No streaming, OME parsing, axis
inference, or vendor-format support — just enough to satisfy a load
round-trip through the entry-point/capability path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import OutputPort
from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scistudio.blocks.io.io_block import IOBlock
from scistudio.core.meta.framework import FrameworkMeta
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio_blocks_fixture.types import Image


def _load_tiff(path: Path, axes_override: list[str] | None, block: Any = None, output_dir: str = "") -> Image:
    """Load a TIFF file into a fixture :class:`Image` (eager, full read)."""
    import tifffile

    data_arr: np.ndarray = np.asarray(tifffile.imread(str(path)))
    ndim = data_arr.ndim
    axes = axes_override if axes_override is not None else Image._default_axes(ndim)
    img = Image(
        axes=axes,
        shape=tuple(data_arr.shape),
        dtype=str(data_arr.dtype),
        framework=FrameworkMeta(source=str(path)),
        meta=Image.Meta(source_file=str(path)),
    )
    img._data = data_arr  # type: ignore[attr-defined]
    return img


class LoadImageFixture(IOBlock):
    """Trivial TIFF image loader returning a ``Collection[Image]``."""

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "fixture.load_image"
    name: ClassVar[str] = "Load Image (fixture)"
    description: ClassVar[str] = "Fixture-only TIFF loader for core IO machinery tests."
    subcategory: ClassVar[str] = "io"

    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id="scistudio-blocks-fixture.image.tiff.load",
            direction="load",
            data_type=Image,
            format_id="tiff",
            extensions=(".tif", ".tiff"),
            label="Fixture TIFF image",
            block_type="LoadImageFixture",
            handler="_load_tiff",
            is_default=True,
            roundtrip_group="scistudio-blocks-fixture.image.tiff",
            metadata_fidelity=MetadataFidelity(
                level="typed_meta",
                typed_meta_reads=("source_file",),
                notes="Fixture loader: eager TIFF read; records source_file only.",
            ),
        ),
    )

    supported_extensions: ClassVar[dict[str, str]] = {
        ".tif": "tiff",
        ".tiff": "tiff",
    }

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="images", accepted_types=[Image], is_collection=True),
    ]
    _load_tiff = staticmethod(_load_tiff)

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"axes": {"type": "string", "ui_priority": 1}},
        "required": [],
    }

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raw_path = config.get("path")
        axes_cfg = config.get("axes")
        axes_override: list[str] | None
        if axes_cfg is None:
            axes_override = None
        elif isinstance(axes_cfg, str):
            axes_override = [a.strip() for a in axes_cfg.split(",")] if "," in axes_cfg else list(axes_cfg)
        else:
            raise ValueError("LoadImageFixture: config['axes'] must be a string or omitted")

        if isinstance(raw_path, list):
            images: list[DataObject] = []
            for single_raw in raw_path:
                if not isinstance(single_raw, str) or not single_raw:
                    raise ValueError("LoadImageFixture: each entry in path list must be a non-empty string")
                images.append(self._load_single(Path(single_raw), axes_override))
            return Collection(items=images, item_type=Image)

        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError("LoadImageFixture: config['path'] must be a non-empty string or list of strings")
        image = self._load_single(Path(raw_path), axes_override)
        return Collection(items=[image], item_type=Image)

    def _load_single(self, path: Path, axes_override: list[str] | None) -> Image:
        if not path.exists():
            raise FileNotFoundError(f"LoadImageFixture: no file at {path}")
        return _load_tiff(path, axes_override, block=self)

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:  # pragma: no cover - input block
        raise NotImplementedError("LoadImageFixture is an input block; use load()")
