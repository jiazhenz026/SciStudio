from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.io.capabilities import FormatCapability
from scistudio.blocks.io.io_block import IOBlock
from scistudio.blocks.registry import AmbiguousCapabilityError, BlockRegistry, _spec_from_class
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.text import Text
from scistudio.engine.materialisation import materialise_to_file, reconstruct_from_file


def _capability(
    *,
    capability_id: str,
    direction: str,
    block_type: str,
    handler: str,
    extensions: tuple[str, ...] = (".txtcap",),
) -> FormatCapability:
    return FormatCapability(
        id=capability_id,
        direction=direction,  # type: ignore[arg-type]
        data_type=Text,
        format_id="txtcap",
        extensions=extensions,
        label="Text capability",
        block_type=block_type,
        handler=handler,
    )


class _TextCapLoader(IOBlock):
    name: ClassVar[str] = "_TextCapLoader"
    type_name: ClassVar[str] = "test.text_cap_loader"
    direction: ClassVar[str] = "input"
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="data", accepted_types=[Text])]
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        _capability(
            capability_id="tests.text.txtcap.primary.load",
            direction="load",
            block_type="_TextCapLoader",
            handler="_load_textcap",
        ),
    )

    def _load_textcap(self, path: Path, config: dict[str, object]) -> Text:
        return Text(content=path.read_text(encoding="utf-8"), format="txtcap")

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        assert config.get("capability_id") == "tests.text.txtcap.primary.load"
        return self._load_textcap(Path(str(config.get("path"))), dict(config.params))

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError


class _AltTextCapLoader(_TextCapLoader):
    name: ClassVar[str] = "_AltTextCapLoader"
    type_name: ClassVar[str] = "test.alt_text_cap_loader"
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        _capability(
            capability_id="tests.text.txtcap.alt.load",
            direction="load",
            block_type="_AltTextCapLoader",
            handler="_load_textcap",
        ),
    )

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        assert config.get("capability_id") == "tests.text.txtcap.alt.load"
        return Text(content=f"alt:{Path(str(config.get('path'))).read_text(encoding='utf-8')}", format="txtcap")


class _TextCapSaver(IOBlock):
    name: ClassVar[str] = "_TextCapSaver"
    type_name: ClassVar[str] = "test.text_cap_saver"
    direction: ClassVar[str] = "output"
    input_ports: ClassVar[list[InputPort]] = [InputPort(name="data", accepted_types=[Text])]
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        _capability(
            capability_id="tests.text.txtcap.primary.save",
            direction="save",
            block_type="_TextCapSaver",
            handler="_save_textcap",
        ),
    )

    def _save_textcap(self, obj: Text, path: Path, config: dict[str, object]) -> None:
        path.write_text(obj.content or "", encoding="utf-8")

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        assert isinstance(obj, Text)
        assert config.get("capability_id") == "tests.text.txtcap.primary.save"
        self._save_textcap(obj, Path(str(config.get("path"))), dict(config.params))


def _registry(*classes: type) -> BlockRegistry:
    registry = BlockRegistry()
    for cls in classes:
        registry._register_spec(_spec_from_class(cls, source="test"))
    return registry


def test_reconstruct_dispatches_via_explicit_capability_id(tmp_path: Path) -> None:
    source = tmp_path / "sample.txtcap"
    source.write_text("payload", encoding="utf-8")
    registry = _registry(_TextCapLoader, _AltTextCapLoader)

    result = reconstruct_from_file(
        source,
        Text,
        extension=".txtcap",
        capability_id="tests.text.txtcap.alt.load",
        registry=registry,
    )

    assert isinstance(result, Text)
    assert result.content == "alt:payload"


def test_reconstruct_raises_ambiguity_without_explicit_capability_id(tmp_path: Path) -> None:
    source = tmp_path / "sample.txtcap"
    source.write_text("payload", encoding="utf-8")
    registry = _registry(_TextCapLoader, _AltTextCapLoader)

    with pytest.raises(AmbiguousCapabilityError):
        reconstruct_from_file(source, Text, extension=".txtcap", registry=registry)


def test_materialise_dispatches_via_explicit_capability_id(tmp_path: Path) -> None:
    registry = _registry(_TextCapSaver)
    text = Text(content="payload", format="plain")

    output = materialise_to_file(
        text,
        tmp_path,
        extension=".txtcap",
        capability_id="tests.text.txtcap.primary.save",
        registry=registry,
    )

    assert output.read_text(encoding="utf-8") == "payload"


def test_materialise_missing_saver_raises_lookup(tmp_path: Path) -> None:
    registry = _registry(_TextCapLoader)

    with pytest.raises(LookupError, match="no saver matches"):
        materialise_to_file(Text(content="payload"), tmp_path, extension=".txtcap", registry=registry)


def test_reconstruct_artifact_fallback_only_for_artifact_compatible_type(tmp_path: Path) -> None:
    source = tmp_path / "opaque.unknown"
    source.write_bytes(b"x")
    registry = BlockRegistry()

    artifact = reconstruct_from_file(source, Artifact, registry=registry)
    assert isinstance(artifact, Artifact)

    with pytest.raises(LookupError, match="cannot fall back"):
        reconstruct_from_file(source, Text, registry=registry)
