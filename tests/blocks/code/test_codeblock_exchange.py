from __future__ import annotations

from pathlib import Path

import pytest

from scieasy.blocks.code.exchange import (
    CodeBlockExchangeError,
    CodeBlockExchangePort,
    allocate_port_folder,
    collect_codeblock_outputs,
    create_codeblock_exchange_layout,
    discover_declared_outputs,
    initialise_exchange_manifest,
    plan_input_filenames,
    prepare_codeblock_exchange,
)
from scieasy.core.storage.ref import StorageReference
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy.core.types.text import Text


def test_create_exchange_layout_creates_per_run_paths(tmp_path: Path) -> None:
    layout = create_codeblock_exchange_layout(
        tmp_path / "exchange",
        block_slug="Code Block",
        block_id="abc/123",
        run_id="run 001",
    )

    assert layout.exchange_dir == tmp_path / "exchange" / "Code_Block-abc_123" / "run_001"
    assert layout.inputs_dir.is_dir()
    assert layout.outputs_dir.is_dir()
    assert layout.logs_dir.is_dir()
    assert layout.temp_dir.is_dir()
    assert layout.manifest_path == layout.exchange_dir / "manifest.json"


def test_allocate_port_folder_suffixes_existing_and_duplicate_names(tmp_path: Path) -> None:
    parent = tmp_path / "inputs"
    (parent / "image").mkdir(parents=True)
    used: set[str] = set()

    first = allocate_port_folder(parent, "image", used)
    second = allocate_port_folder(parent, "image", used)

    assert first.name == "image__scieasy"
    assert second.name == "image__scieasy_2"
    assert first.is_dir()
    assert second.is_dir()


def test_plan_input_filenames_uses_source_basenames_and_collision_suffixes() -> None:
    first = DataObject(storage_ref=StorageReference(backend="filesystem", path="raw/sample.tif"))
    second = DataObject(storage_ref=StorageReference(backend="filesystem", path="other/sample.tif"))
    generated = DataObject()

    assert plan_input_filenames([first, second, generated], extension="tif") == [
        "sample.tif",
        "sample__2.tif",
        "item_0003.tif",
    ]


def test_prepare_exchange_materialises_inputs_and_records_manifest(tmp_path: Path) -> None:
    calls: list[tuple[str, Path, str, str, str | None]] = []

    def materialise(
        obj: DataObject,
        dest_dir: Path,
        extension: str,
        *,
        filename_stem: str,
        capability_id: str | None = None,
    ) -> Path:
        calls.append((type(obj).__name__, dest_dir, extension, filename_stem, capability_id))
        path = dest_dir / f"{filename_stem}{extension}"
        path.write_text("payload", encoding="utf-8")
        return path

    input_obj = DataObject(storage_ref=StorageReference(backend="filesystem", path="raw/sample.ome.tif"))
    ports = [
        CodeBlockExchangePort(
            name="image",
            direction="input",
            data_type=DataObject,
            extension=".ome.tif",
            capability_id="image.save.ome-tiff",
        ),
        CodeBlockExchangePort(name="table", direction="output", data_type=Text, extension=".csv"),
    ]

    manifest = prepare_codeblock_exchange(
        {"image": input_obj},
        ports,
        exchange_root=tmp_path / "exchange",
        block_id="block-1",
        run_id="run-1",
        materialise_adapter=materialise,
    )

    assert calls == [
        (
            "DataObject",
            manifest.input_folders["image"],
            ".ome.tif",
            "sample",
            "image.save.ome-tiff",
        )
    ]
    image_record = manifest.ports["image"]
    assert image_record.status == "materialised"
    assert image_record.files[0].path == manifest.input_folders["image"] / "sample.ome.tif"
    assert image_record.files[0].format_hint == ".ome.tif"
    assert image_record.files[0].capability_id == "image.save.ome-tiff"
    assert manifest.output_folders["table"].is_dir()
    assert manifest.to_dict()["ports"]["image"]["files"][0]["status"] == "materialised"


def test_discover_declared_outputs_routes_by_folder_and_reports_diagnostics(tmp_path: Path) -> None:
    ports = [
        CodeBlockExchangePort(name="image", direction="output", data_type=DataObject, extension=".tif"),
        CodeBlockExchangePort(name="mask", direction="output", data_type=DataObject, extension=".tif"),
        CodeBlockExchangePort(name="table", direction="output", data_type=Text, extension=".csv"),
    ]
    layout = create_codeblock_exchange_layout(tmp_path / "exchange", block_id="b1", run_id="r1")
    manifest = initialise_exchange_manifest(ports, layout=layout)

    (manifest.output_folders["image"] / "cell_001.tif").write_text("image", encoding="utf-8")
    (manifest.output_folders["mask"] / "cell_001.tif").write_text("mask", encoding="utf-8")
    (manifest.output_folders["mask"] / "notes.txt").write_text("wrong", encoding="utf-8")
    (layout.outputs_dir / "loose.tif").write_text("loose", encoding="utf-8")
    unknown = layout.outputs_dir / "unknown"
    unknown.mkdir()
    (unknown / "surprise.csv").write_text("extra", encoding="utf-8")

    result = discover_declared_outputs(ports, manifest=manifest)

    assert result.files_by_port == {
        "image": [manifest.output_folders["image"] / "cell_001.tif"],
        "mask": [manifest.output_folders["mask"] / "cell_001.tif"],
        "table": [],
    }
    assert {diagnostic.code for diagnostic in result.diagnostics} == {
        "output_extension_mismatch",
        "missing_required_output",
        "extra_output_file",
        "unknown_output_folder",
    }
    assert result.has_errors
    assert manifest.ports["mask"].files[-1].status == "collected"


def test_collect_outputs_uses_reconstruct_adapter_and_allows_empty_optional(tmp_path: Path) -> None:
    ports = [
        CodeBlockExchangePort(name="summary", direction="output", data_type=Text, extension=".txt"),
        CodeBlockExchangePort(name="optional", direction="output", data_type=Text, extension=".txt", required=False),
    ]
    layout = create_codeblock_exchange_layout(tmp_path / "exchange", block_id="b1", run_id="r1")
    manifest = initialise_exchange_manifest(ports, layout=layout)
    (manifest.output_folders["summary"] / "result.txt").write_text("done", encoding="utf-8")

    def reconstruct(
        path: Path,
        target_type: type[DataObject] | str,
        extension: str,
        *,
        capability_id: str | None = None,
    ) -> DataObject:
        assert target_type is Text
        assert extension == ".txt"
        assert capability_id is None
        return Text(content=path.read_text(encoding="utf-8"))

    outputs = collect_codeblock_outputs(ports, manifest=manifest, reconstruct_adapter=reconstruct)

    assert isinstance(outputs["summary"], Collection)
    assert outputs["summary"][0].content == "done"
    assert len(outputs["optional"]) == 0
    assert outputs["optional"].item_type is Text


def test_collect_outputs_raises_for_missing_required_output(tmp_path: Path) -> None:
    ports = [CodeBlockExchangePort(name="summary", direction="output", data_type=Text, extension=".txt")]
    layout = create_codeblock_exchange_layout(tmp_path / "exchange", block_id="b1", run_id="r1")
    manifest = initialise_exchange_manifest(ports, layout=layout)

    with pytest.raises(CodeBlockExchangeError) as exc_info:
        collect_codeblock_outputs(
            ports,
            manifest=manifest,
            reconstruct_adapter=lambda path, target_type, extension, capability_id=None: Text(content=""),
        )

    assert [diagnostic.code for diagnostic in exc_info.value.diagnostics] == ["missing_required_output"]
