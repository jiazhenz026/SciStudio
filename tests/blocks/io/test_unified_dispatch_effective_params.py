"""Regression tests for package IO delegation effective-params resolution.

Pins the fix for the production hotfix where core ``Load`` of a
package-registered type (e.g. ``Spectrum``) failed in the engine worker with
``Load: no load capability is registered for type 'Spectrum'``.

Root cause: the engine worker constructs ``BlockConfig(**config)``
(``engine/runners/worker.py`` ``main``), so the user/runtime config (``path``,
``core_type``, …) lands in Pydantic *extra* fields, leaving ``config.params``
empty. ``delegate_load`` / ``delegate_save`` read ``config.params`` directly, so
they saw no ``path`` → no extension → :func:`selected_capability` matched no
format capability → "no load/save capability" even though the package loader was
registered. The fix routes both delegates through :func:`_effective_params`,
which merges the Pydantic extras (mirroring :meth:`BlockConfig.get`, #565).
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import Mock

import scistudio.desktop.paths as desktop_paths
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.io import _unified_dispatch as ud


class _FakeCapability:
    """Minimal stand-in for a package ``FormatCapability``."""

    id = "pkg.spectrum.txt.load"
    block_type = "LoadSpectrum"  # not "LoadData" → resolves to a package block
    format_id = "txt"
    extensions = (".txt",)


def test_effective_params_recovers_config_from_pydantic_extras() -> None:
    # Worker-style construction: fields land in extras, params stays empty.
    cfg = BlockConfig(**{"path": "/d/*.txt", "core_type": "Spectrum", "block_id": "u_load"})
    assert dict(cfg.params) == {}

    eff = ud._effective_params(cfg)
    assert eff["path"] == "/d/*.txt"
    assert eff["core_type"] == "Spectrum"
    assert eff["block_id"] == "u_load"


def test_effective_params_explicit_params_win_over_extras() -> None:
    cfg = BlockConfig(path="/from-extra.txt", params={"path": "/from-params.txt"})
    assert ud._effective_params(cfg)["path"] == "/from-params.txt"


def test_delegate_load_selects_capability_from_extras_path(monkeypatch: Any) -> None:
    """``delegate_load`` must pass the effective ``path`` (from extras) into
    :func:`selected_capability`; before the fix it passed empty params and the
    capability was never matched."""
    captured: dict[str, Any] = {}

    def fake_resolve(name: str) -> Any:
        return object  # any non-None type sentinel

    def fake_selected(*, direction: str, params: dict[str, Any], data_type: Any) -> tuple[str, _FakeCapability]:
        captured["direction"] = direction
        captured["params"] = dict(params)
        return ("registry", _FakeCapability())

    def fake_owner(registry: Any, capability: Any) -> type:
        class _Loader:
            def __init__(self, config: Any) -> None: ...

            def load(self, config: BlockConfig, output_dir: str) -> str:
                return "LOADED"

        return _Loader

    monkeypatch.setattr(ud, "resolve_type_class", fake_resolve)
    monkeypatch.setattr(ud, "selected_capability", fake_selected)
    monkeypatch.setattr(ud, "capability_owner_class", fake_owner)

    cfg = BlockConfig(**{"path": "/d/*.txt", "core_type": "Spectrum"})
    result = ud.delegate_load(config=cfg, output_dir="/tmp/out", core_type="Spectrum")

    assert result == "LOADED"
    assert captured["direction"] == "load"
    # Regression assertion: empty params (pre-fix) would have lost this path.
    assert captured["params"].get("path") == "/d/*.txt"


def test_delegate_save_selects_capability_from_extras_path(monkeypatch: Any) -> None:
    """Symmetric guard for ``delegate_save``."""
    captured: dict[str, Any] = {}

    class _SaveCap(_FakeCapability):
        id = "pkg.spectrum.txt.save"
        block_type = "SaveSpectrum"

    def fake_resolve(name: str) -> Any:
        return object

    def fake_selected(*, direction: str, params: dict[str, Any], data_type: Any) -> tuple[str, _SaveCap]:
        captured["direction"] = direction
        captured["params"] = dict(params)
        return ("registry", _SaveCap())

    saved: dict[str, Any] = {}

    def fake_owner(registry: Any, capability: Any) -> type:
        class _Saver:
            def __init__(self, config: Any) -> None: ...

            def save(self, obj: Any, config: BlockConfig) -> None:
                saved["done"] = True

        return _Saver

    monkeypatch.setattr(ud, "resolve_type_class", fake_resolve)
    monkeypatch.setattr(ud, "selected_capability", fake_selected)
    monkeypatch.setattr(ud, "capability_owner_class", fake_owner)

    # Path already carries a concrete filename+suffix so save-path resolution is a no-op.
    cfg = BlockConfig(**{"path": "/tmp/does-not-exist-xyz.txt", "core_type": "Spectrum"})
    ud.delegate_save(obj=Mock(), config=cfg, core_type="Spectrum")

    assert captured["direction"] == "save"
    assert captured["params"].get("path") == "/tmp/does-not-exist-xyz.txt"
    assert saved.get("done") is True


class _StubCap:
    """Minimal capability stub exposing the fields the error helper reads."""

    def __init__(self, format_id: str, extensions: tuple[str, ...]) -> None:
        self.format_id = format_id
        self.extensions = extensions


def test_path_extension_falls_back_to_filename_field() -> None:
    """#1760 Fix #2: the Save block's ``path`` is a *directory* browser, so the
    extension that selects the save format lives in the ``filename`` field. The
    folder-path + filename pattern must still infer the extension."""
    # Folder path (no suffix) + filename with extension -> filename wins.
    assert ud._path_extension({"path": "/out/dir", "filename": "foo.tiff"}) == ".tiff"
    # A concrete file path takes priority over filename.
    assert ud._path_extension({"path": "/out/foo.tiff", "filename": "bar.png"}) == ".tiff"
    # Neither carries a suffix -> no inference (caller renders an actionable error).
    assert ud._path_extension({"path": "/out/dir", "filename": "foo"}) is None
    assert ud._path_extension({"path": "/out/dir"}) is None


def test_ambiguous_capability_message_is_actionable() -> None:
    """#1760 Fix #1: the message must name the supported extensions and tell the
    user how to disambiguate, not claim the type has no save capability."""
    from scistudio.blocks.registry import AmbiguousCapabilityError

    exc = AmbiguousCapabilityError(
        "ambiguous",
        direction="save",
        data_type=object,
        candidates=(_StubCap("tiff", (".tif", ".tiff")), _StubCap("png", (".png",))),
    )
    msg = ud._ambiguous_capability_message(direction="save", core_type="Image", exc=exc)
    assert "Image" in msg
    assert ".tiff" in msg and ".png" in msg
    assert "no save capability" not in msg
    assert "path or filename" in msg


def test_selected_capability_propagates_ambiguous(monkeypatch: Any) -> None:
    """#1760 Fix #1: ``selected_capability`` must NOT swallow an ambiguous lookup
    into ``None`` (which produced the misleading 'no save capability' message)."""
    from scistudio.blocks.registry import AmbiguousCapabilityError

    class _Reg:
        def find_saver_capability(self, data_type: Any, extension: Any) -> Any:
            raise AmbiguousCapabilityError("ambiguous", direction="save", data_type=object, candidates=())

    monkeypatch.setattr(ud, "runtime_block_registry", lambda: _Reg())
    try:
        ud.selected_capability(direction="save", params={"path": "/out/dir"}, data_type=object)
    except AmbiguousCapabilityError:
        return
    raise AssertionError("AmbiguousCapabilityError should propagate, not be swallowed into None")


def test_delegate_save_renders_actionable_error_on_ambiguity(monkeypatch: Any) -> None:
    """#1760: the worker-facing failure must be the actionable message, not the
    misleading 'no save capability is registered for type ...'."""
    import pytest

    from scistudio.blocks.registry import AmbiguousCapabilityError

    def fake_selected(*, direction: str, params: dict[str, Any], data_type: Any) -> Any:
        raise AmbiguousCapabilityError(
            "ambiguous",
            direction="save",
            data_type=object,
            candidates=(_StubCap("tiff", (".tif", ".tiff")),),
        )

    monkeypatch.setattr(ud, "resolve_type_class", lambda name: object)
    monkeypatch.setattr(ud, "selected_capability", fake_selected)

    with pytest.raises(ValueError) as excinfo:
        ud.delegate_save(obj=Mock(), config=BlockConfig(**{"core_type": "Image"}), core_type="Image")
    message = str(excinfo.value)
    assert "no save capability is registered" not in message
    assert ".tiff" in message
    assert "save format" in message


def test_delegate_load_activates_package_import_roots_for_lazy_deps(monkeypatch: Any, tmp_path: Any) -> None:
    """Regression: a package loader's *lazy* third-party import (e.g. ``tifffile``
    in the imaging ``LoadImage`` loader) must resolve because ``delegate_load``
    re-activates the installed package import roots around the call. The engine
    worker for a core ``Load`` block does not carry plugin roots on ``sys.path``,
    so without the activation the deferred import raises ``ModuleNotFoundError``.
    """
    # A dependency module that only resolves when the plugin "site-packages" is
    # on sys.path — stands in for ``tifffile`` shipped in the plugin env.
    dep_root = tmp_path / "site-packages"
    dep_root.mkdir()
    (dep_root / "fake_plugin_dep.py").write_text("VALUE = 42\n", encoding="utf-8")

    # The worker condition: the dep is NOT importable before activation.
    sys.modules.pop("fake_plugin_dep", None)
    monkeypatch.setattr(desktop_paths, "installed_package_import_roots", lambda: [dep_root])

    class _Cap:
        id = "pkg.image.tiff.load"
        block_type = "LoadImage"
        format_id = "tiff"
        extensions = (".tiff",)

    def fake_owner(registry: Any, capability: Any) -> type:
        class _Loader:
            def __init__(self, config: Any) -> None: ...

            def load(self, config: BlockConfig, output_dir: str) -> str:
                import fake_plugin_dep  # deferred dep import, mirrors real loaders

                return f"LOADED:{fake_plugin_dep.VALUE}"

        return _Loader

    monkeypatch.setattr(ud, "resolve_type_class", lambda name: object)
    monkeypatch.setattr(ud, "selected_capability", lambda *, direction, params, data_type: ("registry", _Cap()))
    monkeypatch.setattr(ud, "capability_owner_class", fake_owner)

    try:
        result = ud.delegate_load(
            config=BlockConfig(**{"path": "/d/a.tiff", "core_type": "Image"}),
            output_dir="/tmp/out",
            core_type="Image",
        )
        assert result == "LOADED:42"
        # Scope guard: the activation is reverted after the delegated call.
        assert str(dep_root) not in sys.path
    finally:
        sys.modules.pop("fake_plugin_dep", None)
