"""#2384 / #2037 — ``scaffold_block`` writes a real starter per category.

Each accepted category renders the shared starter template for its base class
(``scistudio.blocks._templates``), imports every declared port type from its
public root, labels ports and parameters, and produces a file that imports and
registers unchanged. ``code`` / ``ai`` / ``subworkflow`` are refused with what
to do instead, and ``name`` is validated before it becomes a path (#2037).
"""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Coroutine, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import pytest

from scistudio.ai.agent.mcp import _context, tools_authoring
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.types import Array
from scistudio.core.types.registry import TypeRegistry, TypeSpec
from scistudio.testing import BlockTestHarness

_T = TypeVar("_T")


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(coro)


@dataclass
class _StubRuntime:
    block_registry: BlockRegistry = field(default_factory=BlockRegistry)
    type_registry: TypeRegistry = field(default_factory=TypeRegistry)
    _project_dir: Path | None = None
    active_workflow_id: str | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[_StubRuntime]:
    project = tmp_path / "project"
    project.mkdir()
    runtime = _StubRuntime(_project_dir=project)
    runtime.type_registry.scan_builtins()
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


def _scaffold(**kwargs: Any) -> tools_authoring.ScaffoldBlockResult:
    kwargs.setdefault("input_ports", None)
    kwargs.setdefault("output_ports", None)
    kwargs.setdefault("description", None)
    return _run(tools_authoring.scaffold_block(**kwargs))


def _load_class(path: str, class_name: str) -> type:
    namespace: dict[str, object] = {"__name__": f"scaffolded_{class_name.lower()}"}
    exec(compile(Path(path).read_text(encoding="utf-8"), path, "exec"), namespace)
    block = namespace[class_name]
    assert isinstance(block, type)
    return block


_CATEGORY_CASES = [
    # (name, category, input_ports, output_ports, expected base)
    ("plain_start", "block", None, None, "Block"),
    (
        "segment_cells",
        "block",
        {"raw": {"type": "Array", "description": "raw image"}},
        {"mask": {"type": "Array", "description": "binary mask"}, "table": {"type": "DataFrame"}},
        "Block",
    ),
    ("smooth_signal", "process", {"signal": {"type": "Array"}}, {"smoothed": {"type": "Array"}}, "ProcessBlock"),
    ("read_trace", "io", None, {"trace": {"type": "DataFrame", "description": "the trace"}}, "SimpleLoader"),
    ("write_report", "io", {"report": {"type": "Text"}}, None, "SimpleSaver"),
    ("run_fiji", "app", {"image": {"type": "Artifact"}}, {"result": {"type": "Artifact"}}, "AppBlock"),
]


@pytest.mark.parametrize(("name", "category", "inputs", "outputs", "base"), _CATEGORY_CASES)
def test_category_renders_matching_base_class(
    ctx: _StubRuntime,
    name: str,
    category: str,
    inputs: dict[str, Any] | None,
    outputs: dict[str, Any] | None,
    base: str,
) -> None:
    result = _scaffold(name=name, category=category, input_ports=inputs, output_ports=outputs)
    assert result.status == "ok"
    # An io scaffold may carry the #2376 core Load/Save steering advisory; nothing else is expected.
    unexpected = [w for w in result.warnings if not (category == "io" and "core '" in w)]
    assert not unexpected, unexpected
    source = Path(result.path).read_text(encoding="utf-8")
    class_name = "".join(part.capitalize() for part in name.split("_"))
    assert f"class {class_name}({base}):" in source
    # Canonical roots only (issue #2384 item 2).
    for deep in ("scistudio.blocks.base.block", "scistudio.blocks.base.ports", "scistudio.core.types.base"):
        assert deep not in source

    block = _load_class(result.path, class_name)
    assert not BlockTestHarness(block).validate_block()
    assert block.name == " ".join(part.capitalize() for part in name.split("_"))
    for port in [*block.input_ports, *block.output_ports]:
        assert port.description
    for key, prop in block.__dict__.get("config_schema", {}).get("properties", {}).items():
        assert prop.get("title") and prop.get("description"), key
    declared = {**(inputs or {}), **(outputs or {})}
    for port in [*block.input_ports, *block.output_ports]:
        if port.name in declared:
            assert [t.__name__ for t in port.accepted_types] == [declared[port.name]["type"]]
            if declared[port.name].get("description"):
                assert port.description == declared[port.name]["description"]


def test_every_category_registers_through_the_reload_path(ctx: _StubRuntime) -> None:
    """The scaffolded files register as written — what ``reload_blocks`` re-scans."""
    for name, category, inputs, outputs, _base in _CATEGORY_CASES:
        _scaffold(name=name, category=category, input_ports=inputs, output_ports=outputs)
    assert ctx.project_dir is not None
    registry = BlockRegistry()
    registry.add_scan_dir(ctx.project_dir / "blocks")
    registry.scan()
    assert not registry.dropin_failures(), registry.dropin_failures()
    registered = {spec.class_name for spec in registry.all_specs().values()}
    for name, *_rest in _CATEGORY_CASES:
        assert "".join(part.capitalize() for part in name.split("_")) in registered


def test_description_argument_labels_the_block(ctx: _StubRuntime) -> None:
    result = _scaffold(name="count_nuclei", category="block", description="Count nuclei in each image.")
    block = _load_class(result.path, "CountNuclei")
    assert block.description == "Count nuclei in each image."
    assert block.__doc__ == "Count nuclei in each image."


def test_code_category_scaffolds_a_process_block_with_a_warning(ctx: _StubRuntime) -> None:
    """Owner decision on #2384: ``code`` is not a subclassable base; steer to ProcessBlock."""
    result = _scaffold(
        name="script_step", category="code", input_ports={"a": {"type": "Array"}}, output_ports={"b": {"type": "Array"}}
    )
    assert result.status == "ok"
    assert any("ProcessBlock starter was generated" in w and "category='process'" in w for w in result.warnings)
    source = Path(result.path).read_text(encoding="utf-8")
    assert "class ScriptStep(ProcessBlock):" in source
    assert "code_block" not in source and "CodeBlock" not in source
    assert not BlockTestHarness(_load_class(result.path, "ScriptStep")).validate_block()


@pytest.mark.parametrize("category", ["ai", "subworkflow"])
def test_non_author_categories_are_refused_without_writing(ctx: _StubRuntime, category: str) -> None:
    result = _scaffold(name="not_written", category=category)
    assert result.status == "refused"
    assert result.refusal is not None and result.refusal.message
    assert result.path == ""
    assert ctx.project_dir is not None
    assert not (ctx.project_dir / "blocks" / "not_written.py").exists()


def test_unknown_category_lists_valid_ones(ctx: _StubRuntime) -> None:
    with pytest.raises(ValueError, match="process"):
        _scaffold(name="whatever", category="frobnicate")


@pytest.mark.parametrize(
    "bad_name",
    ["../escaped", "/tmp/absolute_block", "..\\escaped", "sub/dir", "CamelName", "class", "has-dash", "", "a" * 65],
)
def test_invalid_name_is_rejected_before_any_write(ctx: _StubRuntime, tmp_path: Path, bad_name: str) -> None:
    """#2037: the name never reaches a path join unvalidated."""
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    with pytest.raises(ValueError, match="Invalid block name"):
        _scaffold(name=bad_name, category="block")
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before


def test_existing_file_is_not_overwritten(ctx: _StubRuntime) -> None:
    _scaffold(name="dup_block", category="block")
    with pytest.raises(FileExistsError):
        _scaffold(name="dup_block", category="block")


def test_io_with_both_sides_scaffolds_a_loader_and_warns(ctx: _StubRuntime) -> None:
    result = _scaffold(
        name="load_both", category="io", input_ports={"x": {"type": "Text"}}, output_ports={"y": {"type": "Text"}}
    )
    assert "class LoadBoth(SimpleLoader):" in Path(result.path).read_text(encoding="utf-8")
    assert any("input_ports were ignored" in warning for warning in result.warnings)


def test_process_with_several_ports_warns(ctx: _StubRuntime) -> None:
    result = _scaffold(
        name="multi_out",
        category="process",
        input_ports={"a": {"type": "Array"}},
        output_ports={"b": {"type": "Array"}, "c": {"type": "Array"}},
    )
    assert any("first output port" in warning for warning in result.warnings)


def test_generic_and_unregistered_type_warnings_are_kept(ctx: _StubRuntime) -> None:
    result = _scaffold(
        name="warned_block",
        category="block",
        input_ports={"any": {"type": "DataObject"}},
        output_ports={"img": {"type": "NoSuchType_XYZ"}},
    )
    joined = " ".join(result.warnings)
    assert "generic DataObject" in joined
    assert "unregistered type 'NoSuchType_XYZ'" in joined
    source = Path(result.path).read_text(encoding="utf-8")
    assert "# fill in: NoSuchType_XYZ" in source
    assert "# from <package> import NoSuchType_XYZ" in source
    assert not BlockTestHarness(_load_class(result.path, "WarnedBlock")).validate_block()


def test_package_type_is_imported_from_its_public_root(ctx: _StubRuntime, monkeypatch: pytest.MonkeyPatch) -> None:
    package = types.ModuleType("scaffold_fake_pkg")
    submodule = types.ModuleType("scaffold_fake_pkg.types")

    class Spectrum(Array):
        pass

    Spectrum.__module__ = submodule.__name__
    submodule.Spectrum = Spectrum  # type: ignore[attr-defined]
    package.Spectrum = Spectrum  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    monkeypatch.setitem(sys.modules, submodule.__name__, submodule)
    ctx.type_registry.register_class(Spectrum, package_root="scaffold_fake_pkg")

    result = _scaffold(name="peak_pick", category="process", input_ports={"spectrum": {"type": "Spectrum"}})
    assert not result.warnings, result.warnings
    source = Path(result.path).read_text(encoding="utf-8")
    assert "from scaffold_fake_pkg import Spectrum" in source
    block = _load_class(result.path, "PeakPick")
    assert block.input_ports[0].accepted_types == [Spectrum]


def test_dropin_type_is_imported_by_file_stem(ctx: _StubRuntime) -> None:
    ctx.type_registry.register(
        "SpectrumData",
        TypeSpec(
            name="SpectrumData",
            module_path="_scistudio_type_dropin_spectrum_1_abc",
            class_name="SpectrumData",
            file_path="/project/types/spectrum.py",
            is_dropin=True,
        ),
    )
    result = _scaffold(name="use_spectrum", category="block", input_ports={"s": {"type": "SpectrumData"}})
    assert "from spectrum import SpectrumData" in Path(result.path).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("name", "inputs", "outputs"),
    [("sink_only", {"a": {"type": "Array"}}, None), ("source_only", None, {"b": {"type": "Array"}})],
)
def test_one_sided_contract_does_not_keep_template_ports(
    ctx: _StubRuntime, name: str, inputs: dict[str, Any] | None, outputs: dict[str, Any] | None
) -> None:
    """Codex review on #2387: an omitted side renders as no ports, not the template's example ports."""
    result = _scaffold(name=name, category="block", input_ports=inputs, output_ports=outputs)
    class_name = "".join(part.capitalize() for part in name.split("_"))
    block = _load_class(result.path, class_name)
    assert [p.name for p in block.input_ports] == list(inputs or {})
    assert [p.name for p in block.output_ports] == list(outputs or {})
    assert not BlockTestHarness(block).validate_block()
    if outputs is None:
        assert block().run({"a": None}, None) == {}
