"""Tests for package installation API endpoints."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scistudio.api.routes import packages as package_routes
from scistudio.desktop.package_installer import LocalPackageInstallResult


class _Registry:
    def all_specs(self) -> dict[str, object]:
        return {
            "probe": SimpleNamespace(source="entry_point", module_path="scistudio_blocks_probe.blocks"),
            "near_prefix": SimpleNamespace(source="entry_point", module_path="scistudio_blocks_probe_extra.blocks"),
            "builtin": SimpleNamespace(source="builtin", module_path="scistudio_blocks_probe.blocks"),
        }


class _Runtime:
    def __init__(self) -> None:
        self.block_registry = _Registry()
        self.refreshed = False

    def refresh_block_registry(self) -> None:
        self.refreshed = True


def test_install_local_package_route_refreshes_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SCISTUDIO_BUNDLED", "1")
    install_path = tmp_path / "installed" / "scistudio-blocks-probe-0.1.0"

    install_kwargs: dict[str, object] = {}

    def fake_install(path: str, **kwargs: object) -> LocalPackageInstallResult:
        install_kwargs.update(kwargs)
        return LocalPackageInstallResult(
            package_name="scistudio-blocks-probe",
            version="0.1.0",
            install_path=install_path,
            source_path=Path(path),
            modules=("scistudio_blocks_probe",),
            manifest_path=install_path / "scistudio-local-package.json",
            replaced=False,
        )

    monkeypatch.setattr(package_routes, "install_local_package", fake_install)
    runtime = _Runtime()
    app = FastAPI()
    app.state.runtime = runtime
    app.include_router(package_routes.router)

    response = TestClient(app).post("/api/packages/local", json={"path": str(tmp_path / "probe.whl")})

    assert response.status_code == 200
    assert runtime.refreshed is True
    assert install_kwargs == {"install_dependencies": True}
    assert response.json() == {
        "package_name": "scistudio-blocks-probe",
        "version": "0.1.0",
        "install_path": str(install_path),
        "modules": ["scistudio_blocks_probe"],
        "blocks_count": 1,
        "replaced": False,
    }


def test_install_local_package_route_rejects_non_bundled_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("SCISTUDIO_BUNDLED", raising=False)

    def fail_install(path: str) -> LocalPackageInstallResult:
        raise AssertionError(f"installer must not run outside bundled desktop mode: {path}")

    monkeypatch.setattr(package_routes, "install_local_package", fail_install)
    runtime = _Runtime()
    app = FastAPI()
    app.state.runtime = runtime
    app.include_router(package_routes.router)

    response = TestClient(app).post("/api/packages/local", json={"path": str(tmp_path / "probe.whl")})

    assert response.status_code == 403
    assert runtime.refreshed is False
    assert response.json()["detail"] == "Local package installation is only available in bundled desktop runs."
