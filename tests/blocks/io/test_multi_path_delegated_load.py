"""Multi-file Load for a package-registered or project-defined type (#2146).

Pointing the core Load block at several files worked for the six core types and
failed for every other one. ``LoadData.load`` returns early for a type outside
``_CORE_TYPE_MAP``, and the multi-path fan-out lives below that early return, so
a delegated type's loader received the whole ``path`` list. A loader written for
one file — anything deriving :class:`SimpleLoader` — rejected it:

    ValueError: LoadTiffImage requires a single path string or PathLike in
    config.params.

The block had already declared otherwise: ``get_output_ports`` marks the port
``is_collection=True`` whenever ``path`` is a list, for *any* ``core_type``.

The fix fans out in :func:`delegate_load`, which is where the loader class is
known — and knowing it matters, because the two kinds of loader want opposite
treatment. A :class:`SimpleLoader` reads one file and expects its caller to
loop; a block that implements ``load`` by hand may want the whole batch to order
a z-stack or align across files, so it still receives the list as written.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.io import _unified_dispatch as ud
from scistudio.blocks.io.io_block import IOBlock
from scistudio.blocks.io.simple_io import SimpleLoader
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


class _Slide(DataObject):
    """Stand-in for a package or project type — not one of the six core types."""


class _OneFileLoader(SimpleLoader):
    """A loader written the ordinary way: three attributes and ``load_file``."""

    output_type: ClassVar[type[DataObject]] = _Slide
    extensions: ClassVar[tuple[str, ...]] = (".slide",)
    format_id: ClassVar[str] = "slide"

    def load_file(self, path: Path, config: dict[str, Any]) -> DataObject:
        return _Slide(user={"path": str(path), "format": config.get("format_id")})


class _WholeBatchLoader(IOBlock):
    """A loader that implements ``load`` by hand and wants the batch intact."""

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "test.whole_batch_loader"
    seen: ClassVar[list[Any]] = []

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raw = config.get("path")
        type(self).seen.append(raw)
        paths = raw if isinstance(raw, list) else [raw]
        return Collection(items=[_Slide(user={"path": str(p)}) for p in paths], item_type=_Slide)

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:  # pragma: no cover
        raise NotImplementedError


class _SlideCapability:
    """Minimal stand-in for the package ``FormatCapability`` being dispatched to."""

    id = "pkg.slide.slide.load"
    block_type = "LoadSlide"  # anything but "LoadData" → resolves to a package block
    format_id = "slide"
    extensions = (".slide",)
    data_type = _Slide


def _route_to(monkeypatch: Any, loader_cls: type[Any]) -> None:
    """Point ``delegate_load`` at *loader_cls* for the ``Slide`` type."""
    monkeypatch.setattr(ud, "resolve_type_class", lambda name: _Slide)
    monkeypatch.setattr(
        ud,
        "selected_capability",
        lambda *, direction, params, data_type: ("registry", _SlideCapability()),
    )
    monkeypatch.setattr(ud, "capability_owner_class", lambda registry, capability: loader_cls)


def test_a_single_file_loader_is_called_once_per_path(monkeypatch: Any, tmp_path: Any) -> None:
    """The list is fanned out and the results arrive as one Collection."""
    _route_to(monkeypatch, _OneFileLoader)
    first, second = tmp_path / "a.slide", tmp_path / "b.slide"

    result = ud.delegate_load(
        config=BlockConfig(params={"path": [str(first), str(second)], "core_type": "Slide"}),
        output_dir="",
        core_type="Slide",
    )

    assert isinstance(result, Collection)
    assert result.item_type is _Slide
    assert [item.user["path"] for item in result] == [str(first), str(second)]


def test_each_fanned_out_call_keeps_the_rest_of_the_config(monkeypatch: Any, tmp_path: Any) -> None:
    """Only ``path`` differs per call; the selected format still reaches the loader."""
    _route_to(monkeypatch, _OneFileLoader)

    result = ud.delegate_load(
        config=BlockConfig(params={"path": [str(tmp_path / "a.slide"), str(tmp_path / "b.slide")]}),
        output_dir="",
        core_type="Slide",
    )

    assert isinstance(result, Collection)
    assert {item.user["format"] for item in result} == {"slide"}


def test_a_drop_in_type_imported_by_path_is_not_rejected(monkeypatch: Any, tmp_path: Any) -> None:
    """The registry's class and the loader's class can be different objects (#1950).

    A project-defined type is imported by path under a synthetic module name, so
    ``resolve_type_class`` hands back a class with the same ``__name__`` as the
    one the loader actually constructs and a different identity. ``Collection``
    compares item types by identity, so declaring the registry's class for the
    batch failed with ``item[0] is Slide, expected Slide`` — the real symptom on
    a project's own ``Image``. The item type is inferred from the items instead.
    """
    registry_side_class = type("_Slide", (DataObject,), {})
    assert registry_side_class is not _Slide and registry_side_class.__name__ == _Slide.__name__

    _route_to(monkeypatch, _OneFileLoader)
    monkeypatch.setattr(ud, "resolve_type_class", lambda name: registry_side_class)

    result = ud.delegate_load(
        config=BlockConfig(params={"path": [str(tmp_path / "a.slide"), str(tmp_path / "b.slide")]}),
        output_dir="",
        core_type="Slide",
    )

    assert isinstance(result, Collection)
    assert result.item_type is _Slide, "the type the loader produced, not the one the registry resolved"
    assert len(result) == 2


def test_a_single_path_still_returns_one_object(monkeypatch: Any, tmp_path: Any) -> None:
    """A lone path is untouched by the fan-out — no Collection appears around it."""
    _route_to(monkeypatch, _OneFileLoader)

    result = ud.delegate_load(
        config=BlockConfig(params={"path": str(tmp_path / "only.slide")}),
        output_dir="",
        core_type="Slide",
    )

    assert isinstance(result, _Slide)


def test_a_hand_written_loader_still_receives_the_whole_list(monkeypatch: Any, tmp_path: Any) -> None:
    """A block that implements ``load`` itself keeps its batch (#2146).

    Fanning this one out would take the batch away from a loader that asked for
    it — the fixture package's own image loader is written this way.
    """
    _WholeBatchLoader.seen.clear()
    _route_to(monkeypatch, _WholeBatchLoader)
    paths = [str(tmp_path / "a.slide"), str(tmp_path / "b.slide")]

    result = ud.delegate_load(
        config=BlockConfig(params={"path": paths}),
        output_dir="",
        core_type="Slide",
    )

    assert _WholeBatchLoader.seen == [paths], "the loader was called once, with the list intact"
    assert isinstance(result, Collection)
    assert len(result) == 2


def test_a_simple_loader_on_its_own_still_refuses_a_list(tmp_path: Any) -> None:
    """The fan-out sits above ``SimpleLoader``, not inside it.

    ``SimpleLoader`` stays a single-file base class — the guard in
    ``tests/blocks/io/test_simple_io.py`` still holds — because the caller is
    what loops, exactly as ``LoadData`` loops over ``_load_array`` for the core
    types.
    """
    import pytest

    block = _OneFileLoader(config={"params": {"path": [str(tmp_path / "a.slide")]}})

    with pytest.raises(ValueError, match="single path"):
        block.load(block.config)


def test_the_load_block_returns_the_collection_its_port_declared(monkeypatch: Any, tmp_path: Any) -> None:
    """End to end through the core Load block, the case the tutorial hit.

    ``get_effective_output_ports`` promises ``is_collection=True`` for a
    multi-path config of any ``core_type``; before the fix the delegated path
    could not deliver it.
    """
    from scistudio.blocks.io.loaders.load_data import LoadData

    _route_to(monkeypatch, _OneFileLoader)
    paths = [str(tmp_path / "a.slide"), str(tmp_path / "b.slide")]
    block = LoadData(config={"params": {"core_type": "Slide", "path": paths}})

    (port,) = block.get_effective_output_ports()
    assert port.is_collection is True

    result = block.load(block.config)

    assert isinstance(result, Collection)
    assert len(result) == 2
