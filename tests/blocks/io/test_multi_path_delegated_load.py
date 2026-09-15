"""Multi-file Load for a package-registered or project-defined type (#2146, #2355).

Pointing the core Load block at several files worked for the six core types and
failed for every other one. ``LoadData.load`` returns early for a type outside
``_CORE_TYPE_MAP``, and the multi-path fan-out lives below that early return, so
a delegated type's loader received the whole ``path`` list. A loader written for
one file — anything deriving :class:`SimpleLoader` — rejected it:

    ValueError: LoadTiffImage requires a single path string or PathLike in
    config.params.

The block had already declared otherwise: ``get_output_ports`` marks the port
``is_collection=True`` whenever ``path`` is a list, for *any* ``core_type``.

#2146 fanned the list out in :func:`delegate_load` — but only for a loader whose
``load`` was *identically* ``SimpleLoader.load``. That made the documented
general pattern (subclass :class:`IOBlock`, implement ``load``) the broken one:
it still received the list, which was then stringified into a path and surfaced
as ``FileNotFoundError: ... "['a.jpg', 'b.jpg']"`` inside whatever library the
loader called.

#2355 inverts the default. Every loader is fanned out unless it declares
:attr:`IOBlock.accepts_path_list`, so wanting the whole batch — to order a
z-stack, or to align across files — is something a loader says rather than
something inferred from which base class it inherits.
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


class _HandWrittenLoader(IOBlock):
    """The general documented pattern: subclass ``IOBlock``, implement ``load``.

    It reads one file and declares nothing, which is what the #2355 reporter
    wrote. Before the fix it received the list.
    """

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "test.hand_written_loader"
    seen: ClassVar[list[Any]] = []

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raw = config.get("path")
        type(self).seen.append(raw)
        if not isinstance(raw, str):
            raise TypeError(f"expected one path, got {type(raw).__name__}")
        return _Slide(user={"path": raw})

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:  # pragma: no cover
        raise NotImplementedError


class _PerFileCollectionLoader(IOBlock):
    """A per-file loader that answers each path with its own ``Collection``.

    One file holding several objects, or a loader that packs its own result —
    either way the batch must come back flat, not nested.
    """

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "test.per_file_collection_loader"

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raw = config.get("path")
        return Collection(
            items=[_Slide(user={"path": str(raw), "part": part}) for part in ("a", "b")],
            item_type=_Slide,
        )

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:  # pragma: no cover
        raise NotImplementedError


class _WholeBatchLoader(IOBlock):
    """A loader that declares it wants the batch intact."""

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "test.whole_batch_loader"
    accepts_path_list: ClassVar[bool] = True
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


def test_a_hand_written_loader_is_fanned_out_too(monkeypatch: Any, tmp_path: Any) -> None:
    """The documented general pattern gets one path per call (#2355).

    ``IOBlock`` + ``load`` is what ADR-043 documents as the general base and what
    an agent writing a custom loader plausibly writes. It used to be handed the
    whole list purely because its ``load`` was not ``SimpleLoader.load``.
    """
    _HandWrittenLoader.seen.clear()
    _route_to(monkeypatch, _HandWrittenLoader)
    first, second = tmp_path / "a.slide", tmp_path / "b.slide"

    result = ud.delegate_load(
        config=BlockConfig(params={"path": [str(first), str(second)]}),
        output_dir="",
        core_type="Slide",
    )

    assert _HandWrittenLoader.seen == [str(first), str(second)], "one path per call, in order"
    assert isinstance(result, Collection)
    assert result.item_type is _Slide
    assert [item.user["path"] for item in result] == [str(first), str(second)]


def test_the_fanned_out_batch_comes_back_flat(monkeypatch: Any, tmp_path: Any) -> None:
    """A loader answering one path with a Collection is flattened into the batch.

    The Load port promises ``is_collection=True`` over data objects, so nesting
    a Collection per path inside the result would contradict it.
    """
    _route_to(monkeypatch, _PerFileCollectionLoader)
    first, second = tmp_path / "a.slide", tmp_path / "b.slide"

    result = ud.delegate_load(
        config=BlockConfig(params={"path": [str(first), str(second)]}),
        output_dir="",
        core_type="Slide",
    )

    assert isinstance(result, Collection)
    assert result.item_type is _Slide
    assert [(item.user["path"], item.user["part"]) for item in result] == [
        (str(first), "a"),
        (str(first), "b"),
        (str(second), "a"),
        (str(second), "b"),
    ]


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


def test_a_loader_that_declared_the_opt_out_still_receives_the_whole_list(monkeypatch: Any, tmp_path: Any) -> None:
    """``accepts_path_list = True`` keeps the batch in one call (#2355).

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


def test_the_opt_out_is_a_declaration_not_an_inherited_trait(monkeypatch: Any) -> None:
    """Nothing about the class hierarchy decides this — only the ClassVar.

    ``_HandWrittenLoader`` and ``_WholeBatchLoader`` are both plain ``IOBlock``
    subclasses that implement ``load``; only the declaration separates them.
    """
    assert IOBlock.accepts_path_list is False, "fanning out is the default"
    assert SimpleLoader.accepts_path_list is False
    assert _HandWrittenLoader.accepts_path_list is False
    assert _WholeBatchLoader.accepts_path_list is True


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


# ---------------------------------------------------------------------------
# Direct execution: a loader run as its own user-facing block (#2357, P2).
#
# The fan-out used to live only in delegate_load, so IOBlock.run() handed the
# whole list to self.load in one call and a default loader written for one
# file failed (below: _HandWrittenLoader's TypeError). Both routes now share
# _collect_load_batch, so accepts_path_list means the same thing either way.
# ---------------------------------------------------------------------------


def test_direct_run_fans_out_a_hand_written_loader(tmp_path: Any) -> None:
    """``IOBlock.run`` honours the default: one call per path, flat Collection."""
    _HandWrittenLoader.seen.clear()
    first, second = tmp_path / "a.slide", tmp_path / "b.slide"
    block = _HandWrittenLoader(config={"params": {"path": [str(first), str(second)]}})

    result = block.run({}, block.config)

    assert _HandWrittenLoader.seen == [str(first), str(second)], "one path per call, in order"
    coll = result["data"]
    assert isinstance(coll, Collection)
    assert coll.item_type is _Slide
    assert [item.user["path"] for item in coll] == [str(first), str(second)]


def test_direct_run_finds_path_in_engine_style_extras(tmp_path: Any) -> None:
    """The engine builds ``BlockConfig(**config)``, so ``path`` lands in extras.

    The per-call config must replace ``path`` where it actually sits — a
    params-only replacement would leave the list visible through
    ``config.get`` and the loader would still see the batch.
    """
    _HandWrittenLoader.seen.clear()
    first, second = tmp_path / "a.slide", tmp_path / "b.slide"
    config = BlockConfig(path=[str(first), str(second)])
    assert "path" not in config.params, "the path arrived as a Pydantic extra"
    block = _HandWrittenLoader(config={})
    block.config = config

    result = block.run({}, config)

    assert _HandWrittenLoader.seen == [str(first), str(second)]
    assert [item.user["path"] for item in result["data"]] == [str(first), str(second)]


def test_direct_run_keeps_the_rest_of_the_config(tmp_path: Any) -> None:
    """Only ``path`` differs per call; block-specific params survive."""

    class _NotingLoader(_HandWrittenLoader):
        seen_notes: ClassVar[list[Any]] = []

        def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
            type(self).seen_notes.append(config.get("note"))
            return super().load(config, output_dir)

    _NotingLoader.seen.clear()
    _NotingLoader.seen_notes.clear()
    block = _NotingLoader(
        config={"params": {"path": [str(tmp_path / "a.slide"), str(tmp_path / "b.slide")], "note": "keepme"}}
    )

    block.run({}, block.config)

    assert _NotingLoader.seen_notes == ["keepme", "keepme"]


def test_direct_run_respects_the_opt_out(tmp_path: Any) -> None:
    """``accepts_path_list = True`` receives the whole list in one call here too."""
    _WholeBatchLoader.seen.clear()
    paths = [str(tmp_path / "a.slide"), str(tmp_path / "b.slide")]
    block = _WholeBatchLoader(config={"params": {"path": paths}})

    result = block.run({}, block.config)

    assert _WholeBatchLoader.seen == [paths], "the loader was called once, with the list intact"
    assert isinstance(result["data"], Collection)
    assert len(result["data"]) == 2


def test_direct_run_flattens_per_file_collections(tmp_path: Any) -> None:
    """A loader answering one path with a Collection stays flat on this route too."""
    first, second = tmp_path / "a.slide", tmp_path / "b.slide"
    block = _PerFileCollectionLoader(config={"params": {"path": [str(first), str(second)]}})

    result = block.run({}, block.config)

    coll = result["data"]
    assert isinstance(coll, Collection)
    assert coll.item_type is _Slide
    assert [(item.user["path"], item.user["part"]) for item in coll] == [
        (str(first), "a"),
        (str(first), "b"),
        (str(second), "a"),
        (str(second), "b"),
    ]


def test_direct_run_single_path_is_untouched(tmp_path: Any) -> None:
    """A lone path still produces the historical single-item Collection wrap."""
    _HandWrittenLoader.seen.clear()
    only = tmp_path / "only.slide"
    block = _HandWrittenLoader(config={"params": {"path": str(only)}})

    result = block.run({}, block.config)

    assert _HandWrittenLoader.seen == [str(only)], "one call, no fan-out"
    coll = result["data"]
    assert isinstance(coll, Collection)
    assert coll.length == 1
    assert coll[0].user["path"] == str(only)
