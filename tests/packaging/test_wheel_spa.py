"""Regression coverage for wheel SPA bundling (#891)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest
from setuptools import Distribution


def _load_setup_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setattr("setuptools.setup", Mock())
    module_path = Path(__file__).resolve().parents[2] / "setup.py"
    spec = importlib.util.spec_from_file_location("scistudio_test_setup", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_spa(root: Path, *, with_assets: bool = True, with_js: bool = True) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text("<!doctype html><html><body>SciStudio</body></html>", encoding="utf-8")
    if with_assets:
        assets = root / "assets"
        assets.mkdir()
        if with_js:
            (assets / "index.js").write_text("console.log('scistudio')", encoding="utf-8")


def test_has_prebuilt_spa_requires_index_assets_and_js(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_module = _load_setup_module(monkeypatch)
    static_dir = tmp_path / "static"
    monkeypatch.setattr(setup_module, "_PACKAGED_STATIC", static_dir)

    assert setup_module._has_prebuilt_spa() is False

    (static_dir / "index.html").parent.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    assert setup_module._has_prebuilt_spa() is False

    (static_dir / "assets").mkdir()
    assert setup_module._has_prebuilt_spa() is False

    (static_dir / "assets" / "style.css").write_text("body{}", encoding="utf-8")
    assert setup_module._has_prebuilt_spa() is False

    (static_dir / "assets" / "main.js").write_text("console.log('ok')", encoding="utf-8")
    assert setup_module._has_prebuilt_spa() is True


def test_required_frontend_build_fails_when_npm_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_module = _load_setup_module(monkeypatch)
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    monkeypatch.setattr(setup_module, "_FRONTEND_DIR", frontend_dir)
    monkeypatch.setattr(setup_module, "_npm_available", lambda: False)

    with pytest.raises(RuntimeError, match="npm not found"):
        setup_module._run_frontend_build(required=True)


def test_optional_frontend_build_allows_missing_npm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_module = _load_setup_module(monkeypatch)
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    monkeypatch.setattr(setup_module, "_FRONTEND_DIR", frontend_dir)
    monkeypatch.setattr(setup_module, "_npm_available", lambda: False)

    setup_module._run_frontend_build(required=False)


def test_required_frontend_build_rejects_partial_dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_module = _load_setup_module(monkeypatch)
    frontend_dir = tmp_path / "frontend"
    dist_dir = frontend_dir / "dist"
    frontend_dir.mkdir()
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(setup_module, "_FRONTEND_DIR", frontend_dir)
    monkeypatch.setattr(setup_module, "_FRONTEND_DIST", dist_dir)
    monkeypatch.setattr(setup_module, "_npm_available", lambda: True)
    monkeypatch.setattr(setup_module.subprocess, "check_call", Mock())

    with pytest.raises(RuntimeError, match="complete SPA bundle"):
        setup_module._run_frontend_build(required=True)


def test_required_frontend_build_copies_complete_dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_module = _load_setup_module(monkeypatch)
    frontend_dir = tmp_path / "frontend"
    dist_dir = frontend_dir / "dist"
    packaged_static = tmp_path / "package" / "static"
    frontend_dir.mkdir()
    _write_spa(dist_dir)
    monkeypatch.setattr(setup_module, "_FRONTEND_DIR", frontend_dir)
    monkeypatch.setattr(setup_module, "_FRONTEND_DIST", dist_dir)
    monkeypatch.setattr(setup_module, "_PACKAGED_STATIC", packaged_static)
    monkeypatch.setattr(setup_module, "_npm_available", lambda: True)
    check_call = Mock()
    monkeypatch.setattr(setup_module.subprocess, "check_call", check_call)

    setup_module._run_frontend_build(required=True)

    assert (packaged_static / "index.html").is_file()
    assert (packaged_static / "assets" / "index.js").is_file()
    assert check_call.call_args_list[0].args[0] == ["npm", "ci"]
    assert check_call.call_args_list[1].args[0] == ["npm", "run", "build"]


def test_required_frontend_build_raises_on_npm_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_module = _load_setup_module(monkeypatch)
    command = setup_module.build_py(Distribution())
    monkeypatch.setattr(setup_module, "_has_prebuilt_spa", lambda: False)
    monkeypatch.setattr(setup_module, "_run_frontend_build", Mock(side_effect=subprocess.CalledProcessError(1, "npm")))
    monkeypatch.setattr(setup_module._build_py, "run", Mock())
    monkeypatch.setenv("SCISTUDIO_REQUIRE_FRONTEND_BUILD", "1")

    with pytest.raises(RuntimeError, match="frontend build failed with exit 1"):
        command.run()


def test_skip_frontend_build_overrides_required_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    setup_module = _load_setup_module(monkeypatch)
    command = setup_module.build_py(Distribution())
    run_frontend_build = Mock()
    base_run = Mock()
    monkeypatch.setattr(setup_module, "_has_prebuilt_spa", lambda: False)
    monkeypatch.setattr(setup_module, "_run_frontend_build", run_frontend_build)
    monkeypatch.setattr(setup_module._build_py, "run", base_run)
    monkeypatch.setenv("SCISTUDIO_REQUIRE_FRONTEND_BUILD", "1")
    monkeypatch.setenv("SCISTUDIO_SKIP_FRONTEND_BUILD", "1")

    command.run()

    run_frontend_build.assert_not_called()
    base_run.assert_called_once_with()
