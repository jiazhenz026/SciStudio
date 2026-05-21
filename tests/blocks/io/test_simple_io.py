from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from scistudio.blocks.io.capabilities import MetadataFidelity, SimpleIODeclarationError
from scistudio.blocks.io.simple_io import SimpleLoader, SimpleSaver
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


class _SimpleObject(DataObject):
    pass


class _LocalLoader(SimpleLoader):
    output_type: ClassVar[type[DataObject]] = _SimpleObject
    extensions: ClassVar[list[str]] = ["TIF", ".TIFF"]
    format_id: ClassVar[str] = "TIFF"

    def load_file(self, path: Path, config: dict[str, Any]) -> DataObject:
        return _SimpleObject(user={"path": str(path), "seen": config.get("marker")})


class _LocalSaver(SimpleSaver):
    input_type: ClassVar[type[DataObject]] = _SimpleObject
    extensions: ClassVar[list[str]] = [".TIF"]
    format_id: ClassVar[str] = "TIFF"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config=config)
        self.saved: tuple[DataObject, Path, dict[str, Any]] | None = None

    def save_file(self, obj: DataObject, path: Path, config: dict[str, Any]) -> None:
        self.saved = (obj, path, config)


def test_simple_loader_synthesizes_pixel_only_capability() -> None:
    (capability,) = _LocalLoader.get_format_capabilities()

    assert capability.id.endswith("._localloader.load.tiff")
    assert capability.direction == "load"
    assert capability.data_type is _SimpleObject
    assert capability.format_id == "tiff"
    assert capability.extensions == (".tif", ".tiff")
    assert capability.label == "TIFF"
    assert capability.block_type == "_LocalLoader"
    assert capability.handler == "load_file"
    assert capability.metadata_fidelity == MetadataFidelity(level="pixel_only")
    assert capability.is_synthesized is True


def test_simple_loader_run_delegates_to_load_file(tmp_path: Path) -> None:
    path = tmp_path / "input.tif"
    block = _LocalLoader(config={"params": {"path": str(path), "marker": "ok"}})

    result = block.run({}, block.config)

    collection = result["data"]
    assert isinstance(collection, Collection)
    loaded = collection[0]
    assert isinstance(loaded, _SimpleObject)
    assert loaded.user == {"path": str(path), "seen": "ok"}


def test_simple_loader_rejects_multi_path_config(tmp_path: Path) -> None:
    block = _LocalLoader(config={"params": {"path": [str(tmp_path / "a.tif"), str(tmp_path / "b.tif")]}})

    with pytest.raises(ValueError, match="single path"):
        block.run({}, block.config)


def test_simple_saver_synthesizes_pixel_only_capability() -> None:
    (capability,) = _LocalSaver.get_format_capabilities()

    assert capability.id.endswith("._localsaver.save.tiff")
    assert capability.direction == "save"
    assert capability.data_type is _SimpleObject
    assert capability.extensions == (".tif",)
    assert capability.handler == "save_file"
    assert capability.metadata_fidelity.level == "pixel_only"
    assert capability.migration_scaffold is True


def test_simple_saver_run_delegates_to_save_file(tmp_path: Path) -> None:
    path = tmp_path / "output.tif"
    obj = _SimpleObject()
    block = _LocalSaver(config={"params": {"path": str(path), "marker": "save"}})

    result = block.run({"data": Collection(items=[obj], item_type=_SimpleObject)}, block.config)

    assert block.saved == (obj, path, {"path": str(path), "marker": "save"})
    assert result["path"][0].content == str(path)


def test_simple_saver_rejects_multi_path_config(tmp_path: Path) -> None:
    obj = _SimpleObject()
    block = _LocalSaver(config={"params": {"path": [str(tmp_path / "a.tif"), str(tmp_path / "b.tif")]}})

    with pytest.raises(ValueError, match="single path"):
        block.run({"data": Collection(items=[obj], item_type=_SimpleObject)}, block.config)


def test_simple_saver_rejects_multi_object_collection(tmp_path: Path) -> None:
    path = tmp_path / "output.tif"
    block = _LocalSaver(config={"params": {"path": str(path)}})
    collection = Collection(items=[_SimpleObject(), _SimpleObject()], item_type=_SimpleObject)

    with pytest.raises(ValueError, match="exactly one object"):
        block.run({"data": collection}, block.config)


def test_simple_loader_missing_output_type_is_invalid() -> None:
    class MissingOutputType(SimpleLoader):
        extensions: ClassVar[list[str]] = [".tif"]
        format_id: ClassVar[str] = "tiff"

        def load_file(self, path: Path, config: dict[str, Any]) -> DataObject:
            return _SimpleObject()

    with pytest.raises(SimpleIODeclarationError, match="output_type"):
        MissingOutputType.get_format_capabilities()


def test_simple_saver_missing_format_id_is_invalid() -> None:
    class MissingFormatId(SimpleSaver):
        input_type: ClassVar[type[DataObject]] = _SimpleObject
        extensions: ClassVar[list[str]] = [".tif"]

        def save_file(self, obj: DataObject, path: Path, config: dict[str, Any]) -> None:
            return None

    with pytest.raises(SimpleIODeclarationError, match="format_id"):
        MissingFormatId.get_format_capabilities()
