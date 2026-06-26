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


# --------------------------------------------------------------------------- #
# Package Manager endpoints (#1784)
# --------------------------------------------------------------------------- #
from scistudio.blocks.base.package_info import PackageInfo, PackageOtaSource  # noqa: E402
from scistudio.desktop import package_manager  # noqa: E402


class _RegistryWithPackages(_Registry):
    def packages(self) -> dict[str, PackageInfo]:
        return {
            "scistudio-blocks-demo": PackageInfo(
                name="scistudio-blocks-demo",
                version="1.0.0",
                ota=PackageOtaSource(manifest_url="https://example.com/demo/manifest.json", channel="alpha"),
            )
        }


def _bundled_app(runtime: object) -> FastAPI:
    app = FastAPI()
    app.state.runtime = runtime
    app.include_router(package_routes.router)
    return app


def test_list_installed_route(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SCISTUDIO_BUNDLED", "1")
    monkeypatch.setattr(
        package_manager,
        "list_installed_packages",
        lambda: [
            package_manager.InstalledPackage(
                package_name="scistudio-blocks-demo",
                version="1.0.0",
                install_path=tmp_path / "demo",
                modules=("scistudio_blocks_demo",),
                has_backup=True,
                backup_version="0.9.0",
            )
        ],
    )
    response = TestClient(_bundled_app(_Runtime())).get("/api/packages/installed")
    assert response.status_code == 200
    body = response.json()
    assert body["packages"][0]["package_name"] == "scistudio-blocks-demo"
    assert body["packages"][0]["has_backup"] is True


def test_updates_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCISTUDIO_BUNDLED", "1")
    captured: dict[str, object] = {}

    def fake_check(packages, *, core_base):
        captured["packages"] = packages
        captured["core_base"] = core_base
        return [
            package_manager.PackageUpdateStatus(
                package_name="scistudio-blocks-demo",
                current_version="1.0.0",
                channel="alpha",
                manifest_url="https://example.com/demo/manifest.json",
                status="update",
                available_version="1.2.0",
                notes="fix",
            )
        ]

    monkeypatch.setattr(package_manager, "check_package_updates", fake_check)
    runtime = _Runtime()
    runtime.block_registry = _RegistryWithPackages()
    response = TestClient(_bundled_app(runtime)).get("/api/packages/updates")
    assert response.status_code == 200
    body = response.json()
    assert body["statuses"][0]["update_available"] is True
    assert body["statuses"][0]["available_version"] == "1.2.0"
    assert "scistudio-blocks-demo" in captured["packages"]


def test_update_route_refreshes_and_returns_relaunch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCISTUDIO_BUNDLED", "1")

    def fake_update(name, *, packages, core_base):
        return package_manager.PackageActionResult(
            package_name=name, version="1.2.0", action="update", previous_version="1.0.0"
        )

    monkeypatch.setattr(package_manager, "update_package", fake_update)
    runtime = _Runtime()
    runtime.block_registry = _RegistryWithPackages()
    response = TestClient(_bundled_app(runtime)).post("/api/packages/scistudio-blocks-demo/update")
    assert response.status_code == 200
    assert response.json()["needs_relaunch"] is True
    assert runtime.refreshed is True


def test_update_route_maps_known_error_to_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCISTUDIO_BUNDLED", "1")

    def boom(name, *, packages, core_base):
        raise package_manager.PackageUpdateError("Checksum mismatch")

    monkeypatch.setattr(package_manager, "update_package", boom)
    runtime = _Runtime()
    runtime.block_registry = _RegistryWithPackages()
    response = TestClient(_bundled_app(runtime)).post("/api/packages/scistudio-blocks-demo/update")
    assert response.status_code == 400
    assert "Checksum mismatch" in response.json()["detail"]


def test_rollback_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCISTUDIO_BUNDLED", "1")
    monkeypatch.setattr(
        package_manager,
        "rollback_package",
        lambda name: package_manager.PackageActionResult(
            package_name=name, version="1.0.0", action="rollback", previous_version="1.2.0"
        ),
    )
    runtime = _Runtime()
    response = TestClient(_bundled_app(runtime)).post("/api/packages/scistudio-blocks-demo/rollback")
    assert response.status_code == 200
    assert response.json()["action"] == "rollback"
    assert runtime.refreshed is True


def test_delete_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCISTUDIO_BUNDLED", "1")
    monkeypatch.setattr(
        package_manager,
        "delete_package",
        lambda name: package_manager.PackageActionResult(package_name=name, version="1.0.0", action="delete"),
    )
    runtime = _Runtime()
    response = TestClient(_bundled_app(runtime)).delete("/api/packages/scistudio-blocks-demo")
    assert response.status_code == 200
    assert response.json()["action"] == "delete"
    assert runtime.refreshed is True


def test_delete_route_missing_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCISTUDIO_BUNDLED", "1")

    def missing(name):
        raise package_manager.PackageUpdateError("Package 'x' is not installed.")

    monkeypatch.setattr(package_manager, "delete_package", missing)
    response = TestClient(_bundled_app(_Runtime())).delete("/api/packages/x")
    assert response.status_code == 404


def test_package_manager_routes_reject_non_bundled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCISTUDIO_BUNDLED", raising=False)
    client = TestClient(_bundled_app(_Runtime()))
    assert client.get("/api/packages/installed").status_code == 403
    assert client.get("/api/packages/updates").status_code == 403
    assert client.post("/api/packages/x/update").status_code == 403
    assert client.delete("/api/packages/x").status_code == 403
