"""#2384 — per-kind block starter templates and the renderer that fills them in.

The templates in ``scistudio.blocks._templates`` back both the GUI "New custom
block" endpoint (served verbatim) and the agent's ``scaffold_block`` tool
(rendered). These tests pin that every kind, verbatim and rendered, is a block
that imports, passes the contract harness, and registers from a drop-in
directory without edits.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scistudio.blocks._templates import TEMPLATE_KINDS, read_template
from scistudio.blocks._templates.render import PortStub, StarterSpec, render_starter
from scistudio.blocks.registry import BlockRegistry
from scistudio.core import types as core_types
from scistudio.testing import BlockTestHarness

_EXPECTED_BASES = {
    "basic": "Block",
    "process": "ProcessBlock",
    "io_load": "SimpleLoader",
    "io_save": "SimpleSaver",
    "app": "AppBlock",
}

# The deep-module import roots the public API forbids (public-api.md).
_DEEP_IMPORTS = (
    "scistudio.blocks.base.block",
    "scistudio.blocks.base.ports",
    "scistudio.blocks.base.config",
    "scistudio.core.types.base",
    "scistudio.blocks.process.process_block",
    "scistudio.blocks.io.simple_io",
    "scistudio.blocks.app.app_block",
)


def _exec_block(source: str, class_name: str) -> type:
    namespace: dict[str, object] = {"__name__": f"starter_{class_name.lower()}"}
    exec(compile(source, f"{class_name}.py", "exec"), namespace)
    block = namespace[class_name]
    assert isinstance(block, type)
    return block


def _class_name(source: str) -> str:
    classes = [node for node in ast.parse(source).body if isinstance(node, ast.ClassDef)]
    assert len(classes) == 1
    return classes[0].name


def _assert_canonical_imports(source: str) -> None:
    imported = [
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("scistudio")
    ]
    assert imported, "a starter must import from the scistudio public roots"
    for module in imported:
        assert module not in _DEEP_IMPORTS, f"deep import {module!r} in starter"
        assert not any(part.startswith("_") for part in module.split(".")), f"private import {module!r}"


def test_registry_covers_every_scaffold_base() -> None:
    assert {kind: template.base_class for kind, template in TEMPLATE_KINDS.items()} == _EXPECTED_BASES
    basic = TEMPLATE_KINDS["basic"]
    assert (basic.resource, basic.suggested_filename) == ("block_base_template.py", "my_block.py")


@pytest.mark.parametrize("kind", sorted(TEMPLATE_KINDS))
def test_verbatim_template_is_a_valid_block(kind: str) -> None:
    source = read_template(kind)
    _assert_canonical_imports(source)
    assert "# >>> EDIT THIS <<<" in source
    block = _exec_block(source, _class_name(source))
    assert [base.__name__ for base in block.__mro__][1] == _EXPECTED_BASES[kind]
    assert not BlockTestHarness(block).validate_block()


@pytest.mark.parametrize("kind", sorted(TEMPLATE_KINDS))
def test_verbatim_template_labels_every_port_and_parameter(kind: str) -> None:
    block = _exec_block(read_template(kind), _class_name(read_template(kind)))
    for port in [*block.input_ports, *block.output_ports]:
        assert port.description, f"{kind}: port {port.name!r} has no description"
    own_schema = block.__dict__.get("config_schema", {})
    if kind == "basic":
        # The GUI basic template is served unchanged (#2384); the renderer adds labels.
        return
    for key, prop in own_schema.get("properties", {}).items():
        assert prop.get("title") and prop.get("description"), f"{kind}: parameter {key!r} is unlabelled"


def test_render_without_ports_keeps_template_shape_and_renames() -> None:
    spec = StarterSpec(class_name="GaussianSmooth", label="Gaussian Smooth", description="Smooth each image.")
    source = render_starter("basic", spec)
    block = _exec_block(source, "GaussianSmooth")
    assert block.name == "Gaussian Smooth"
    assert block.description == "Smooth each image."
    assert "class MyBlock" not in source
    # The worked body of the GUI template is kept when no ports are declared.
    assert "self.map_items(scale" in source
    gain = block.config_schema["properties"]["gain"]
    assert gain["title"] == "Gain" and gain["description"] and gain["default"] == 1.0


def test_render_rewrites_header_only_below_the_class() -> None:
    """The teaching header mentions ``def run`` and port lists; only class code is rewritten."""
    template = read_template("basic")
    header = template[: template.index("class MyBlock")]
    spec = StarterSpec(
        class_name="Router",
        label="Router",
        description="Route items.",
        input_ports=(PortStub("raw", "Array", "raw image"),),
        output_ports=(PortStub("kept", "Array", "items kept"),),
    )
    source = render_starter("basic", spec)
    assert source.startswith(header.split("from scistudio.core.types import")[0])


def test_render_ports_imports_and_passthrough_body(tmp_path: Path) -> None:
    spec = StarterSpec(
        class_name="SegmentCells",
        label="Segment Cells",
        description="Segment cells in each image.",
        input_ports=(PortStub("raw", "Array", "raw image"),),
        output_ports=(
            PortStub("mask", "Array", "binary mask"),
            PortStub("table", "DataFrame", "per-cell measurements"),
            PortStub("overlay", "DataObject", "overlay image", note="fill in: Image"),
        ),
        extra_import_lines=("# from <package> import Image  # fill in",),
    )
    source = render_starter("basic", spec)
    _assert_canonical_imports(source)
    assert "# fill in: Image" in source
    assert "# from <package> import Image" in source
    assert "raise NotImplementedError" not in source
    block = _exec_block(source, "SegmentCells")
    assert [p.name for p in block.output_ports] == ["mask", "table", "overlay"]
    assert [p.description for p in block.input_ports] == ["raw image"]
    assert block.output_ports[1].accepted_types == [core_types.DataFrame]
    assert not BlockTestHarness(block).validate_block()

    run_source = source[source.index("    def run(") :]
    assert 'self.map_items(transform, inputs["raw"])' in run_source
    assert "Collection([], item_type=DataFrame)" in run_source


def test_render_process_item_body_matches_port_types() -> None:
    same = render_starter(
        "process",
        StarterSpec(
            class_name="Clean",
            label="Clean",
            description="d",
            input_ports=(PortStub("table", "DataFrame", "in"),),
            output_ports=(PortStub("cleaned", "DataFrame", "out"),),
        ),
    )
    assert "def process_item(self, item: DataFrame, config: BlockConfig, state: Any = None) -> DataFrame:" in same
    assert "return item" in same
    different = render_starter(
        "process",
        StarterSpec(
            class_name="Summarise",
            label="Summarise",
            description="d",
            input_ports=(PortStub("table", "DataFrame", "in"),),
            output_ports=(PortStub("report", "Text", "out"),),
        ),
    )
    assert "raise NotImplementedError" in different
    for source, name in ((same, "Clean"), (different, "Summarise")):
        assert not BlockTestHarness(_exec_block(source, name)).validate_block()


@pytest.mark.parametrize(
    ("kind", "port_type", "snippet"),
    [
        ("io_load", "Array", "np.load(path)"),
        ("io_load", "DataFrame", "pa_csv.read_csv(path)"),
        ("io_save", "Text", "path.write_text("),
        ("io_save", "DataObject", "raise NotImplementedError"),
    ],
)
def test_render_io_starters(kind: str, port_type: str, snippet: str) -> None:
    port = PortStub("data", port_type, "the data")
    spec = StarterSpec(
        class_name="MyFormat",
        label="My Format",
        description="d",
        input_ports=(port,) if kind == "io_save" else None,
        output_ports=(port,) if kind == "io_load" else None,
        extension=".my_format",
        format_id="my_format",
        known_types=frozenset(core_types.__all__),
    )
    source = render_starter(kind, spec)
    assert snippet in source
    block = _exec_block(source, "MyFormat")
    attr = "output_type" if kind == "io_load" else "input_type"
    assert getattr(block, attr).__name__ == port_type
    assert tuple(block.extensions) == (".my_format",)
    assert not BlockTestHarness(block).validate_block()


def test_every_kind_registers_from_a_dropin_directory(tmp_path: Path) -> None:
    """Verbatim and rendered starters register without edits (the reload_blocks path)."""
    blocks_dir = tmp_path / "blocks"
    blocks_dir.mkdir()
    expected: set[str] = set()
    for kind in TEMPLATE_KINDS:
        stem = f"verbatim_{kind}"
        # Two copies of one class name cannot share a registry; rename the verbatim copy.
        verbatim = read_template(kind)
        renamed = f"Verbatim{kind.title().replace('_', '')}"
        source = verbatim.replace(f"class {_class_name(verbatim)}(", f"class {renamed}(")
        if kind in {"io_load", "io_save"}:
            source = source.replace('(".mytext",)', f'(".{stem}",)').replace('"my_text"', f'"{stem}"')
        (blocks_dir / f"{stem}.py").write_text(source, encoding="utf-8")
        expected.add(_class_name(source))

        port = (PortStub("item", "Text", "an item"),)
        rendered = render_starter(
            kind,
            StarterSpec(
                class_name=f"Rendered{kind.title().replace('_', '')}",
                label=f"Rendered {kind}",
                description="Rendered starter.",
                input_ports=None if kind == "io_load" else port,
                output_ports=None if kind == "io_save" else port,
                extension=f".rendered_{kind}" if kind.startswith("io_") else None,
                format_id=f"rendered_{kind}" if kind.startswith("io_") else None,
                known_types=frozenset(core_types.__all__),
            ),
        )
        (blocks_dir / f"rendered_{kind}.py").write_text(rendered, encoding="utf-8")
        expected.add(_class_name(rendered))

    registry = BlockRegistry()
    registry.add_scan_dir(blocks_dir)
    registry.scan()
    assert not registry.dropin_failures(), registry.dropin_failures()
    registered = {spec.class_name for spec in registry.all_specs().values()}
    assert expected <= registered, expected - registered


def test_render_rejects_a_template_without_the_expected_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    import scistudio.blocks._templates.render as render

    monkeypatch.setattr(render, "read_template", lambda kind: "class A(Block):\n    x = 1\n")
    with pytest.raises(ValueError, match="docstring"):
        render.render_starter("basic", StarterSpec(class_name="B", label="B", description="d"))


def test_render_with_ports_clears_the_template_example_parameters() -> None:
    """Codex review on #2387: replaced bodies must not leave inert template parameters in the GUI."""
    port = (PortStub("signal", "Array", "the signal"),)
    source = render_starter(
        "process",
        StarterSpec(
            class_name="Passthrough", label="Passthrough", description="d", input_ports=port, output_ports=port
        ),
    )
    block = _exec_block(source, "Passthrough")
    assert block.__dict__["config_schema"]["properties"] == {}
    assert "Gain" not in source.split("class Passthrough", 1)[1]
    assert "config.get()" in source  # the empty schema still shows how to add a labelled parameter
    # Without declared ports the worked body and its parameter stay together.
    kept = render_starter("process", StarterSpec(class_name="Kept", label="Kept", description="d"))
    assert "gain" in _exec_block(kept, "Kept").__dict__["config_schema"]["properties"]


def test_rendered_array_saver_writes_the_requested_path(tmp_path: Path) -> None:
    """Codex review on #2387: ``np.save(path)`` would append ``.npy`` to the claimed extension."""
    import numpy as np

    spec = StarterSpec(
        class_name="SaveArr",
        label="Save Arr",
        description="d",
        input_ports=(PortStub("data", "Array", "the array"),),
        extension=".save_arr",
        format_id="save_arr",
        known_types=frozenset(core_types.__all__),
    )
    block = _exec_block(render_starter("io_save", spec), "SaveArr")
    target = tmp_path / "result.save_arr"
    block().save_file(core_types.Array(axes=["x"], data=np.arange(3)), target, {})
    assert target.is_file()
    assert not (tmp_path / "result.save_arr.npy").exists()
    assert np.load(target).tolist() == [0, 1, 2]
