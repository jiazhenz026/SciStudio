"""Registry discovery tests (ADR-048 FR-002 / FR-006 / FR-030)."""

from __future__ import annotations

import importlib.metadata
import sys
import types

import pytest

from scistudio.previewers.fallbacks import dataframe_previewer
from scistudio.previewers.models import OwnerKind, PreviewerSpec
from scistudio.previewers.registry import PreviewerRegistry


def _spec(previewer_id: str, owner: OwnerKind = OwnerKind.PACKAGE, target: str = "Image") -> PreviewerSpec:
    return PreviewerSpec(
        previewer_id=previewer_id,
        owner_kind=owner,
        owner_name="pkg",
        target_type=target,
        backend_provider=dataframe_previewer,
    )


def test_core_specs_load_unconditionally() -> None:
    reg = PreviewerRegistry()
    reg.load_core()
    ids = {s.previewer_id for s in reg.all_specs()}
    # All eight typed core fallbacks plus the universal base fallback (FR-012).
    assert {
        "core.dataframe.basic",
        "core.array.basic",
        "core.series.basic",
        "core.text.basic",
        "core.artifact.basic",
        "core.composite.basic",
        "core.collection.basic",
        "core.plot.basic",
        "core.base.fallback",
    } <= ids
    assert reg.diagnostics == []


def test_duplicate_previewer_id_is_rejected_with_diagnostic() -> None:
    reg = PreviewerRegistry()
    assert reg.register(_spec("dup")) is True
    assert reg.register(_spec("dup")) is False
    assert any("duplicate previewer_id 'dup'" in d for d in reg.diagnostics)
    # The first registration is kept.
    assert reg.get("dup") is not None


def test_empty_previewer_id_rejected() -> None:
    reg = PreviewerRegistry()
    assert reg.register(_spec("")) is False
    assert any("empty previewer_id" in d for d in reg.diagnostics)


def test_specs_for_owner_filters_tier() -> None:
    reg = PreviewerRegistry()
    reg.register(_spec("a", OwnerKind.PACKAGE))
    reg.register(_spec("b", OwnerKind.PROJECT))
    assert {s.previewer_id for s in reg.specs_for_owner(OwnerKind.PROJECT)} == {"b"}
    assert {s.previewer_id for s in reg.specs_for_owner(OwnerKind.PACKAGE)} == {"a"}


def test_factory_returning_non_list_is_diagnosed() -> None:
    reg = PreviewerRegistry()
    reg._register_from_factory("bad", lambda: 42)
    assert any("expected list[PreviewerSpec]" in d for d in reg.diagnostics)


def test_factory_returning_non_spec_item_is_skipped() -> None:
    reg = PreviewerRegistry()
    reg._register_from_factory("mixed", lambda: [_spec("good"), object()])
    assert reg.get("good") is not None
    assert any("non-PreviewerSpec" in d for d in reg.diagnostics)


def test_raising_factory_is_diagnosed_not_fatal() -> None:
    reg = PreviewerRegistry()

    def boom() -> list[PreviewerSpec]:
        raise RuntimeError("kaboom")

    reg._register_from_factory("explode", boom)
    assert any("raised" in d for d in reg.diagnostics)


def test_monorepo_fallback_discovers_get_previewers(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-030: a monorepo package exposing get_previewers() is discovered."""
    import sys
    import types

    reg = PreviewerRegistry()

    fake_module = types.ModuleType("scistudio_blocks_fake")
    fake_module.get_previewers = lambda: [_spec("pkg.fake.viewer")]  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scistudio_blocks_fake", fake_module)

    # Drive the factory path directly (filesystem glob is exercised by the
    # imaging package's own monorepo test); this proves the contract shape.
    reg._register_from_factory("scistudio_blocks_fake", fake_module.get_previewers)
    assert reg.get("pkg.fake.viewer") is not None
    assert reg.diagnostics == []


def test_companion_package_entry_point_discovers_get_previewers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Block/type packages can provide previewers even when previewer metadata is stale."""
    fake_module = types.ModuleType("scistudio_blocks_fake")
    fake_module.get_previewers = lambda: [_spec("pkg.fake.viewer")]  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scistudio_blocks_fake", fake_module)

    block_ep = importlib.metadata.EntryPoint(
        name="fake",
        value="scistudio_blocks_fake:get_block_package",
        group="scistudio.blocks",
    )
    real_entry_points = importlib.metadata.entry_points

    def _entry_points(*args: object, **kwargs: object) -> object:
        group = kwargs.get("group")
        if group == "scistudio.previewers":
            return ()
        if group == "scistudio.blocks":
            return (block_ep,)
        if group == "scistudio.types":
            return ()
        return real_entry_points(*args, **kwargs)

    monkeypatch.setattr(importlib.metadata, "entry_points", _entry_points)

    reg = PreviewerRegistry()
    reg.load_packages(include_monorepo=False)

    assert reg.get("pkg.fake.viewer") is not None
    assert reg.diagnostics == []


def test_project_default_declaration_roundtrips() -> None:
    reg = PreviewerRegistry()
    reg.set_project_default("MyType", "project.mytype.viewer")
    assert reg.project_default_for("MyType") == "project.mytype.viewer"
    assert reg.project_default_for("Other") is None
