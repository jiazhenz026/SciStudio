"""Desktop package installation and Package Manager endpoints (#1784)."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from scistudio.api.deps import get_runtime
from scistudio.api.runtime import ApiRuntime
from scistudio.desktop import package_manager
from scistudio.desktop.package_installer import PackageInstallError, install_local_package
from scistudio.version import get_version

router = APIRouter(prefix="/api/packages", tags=["packages"])
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]
_PACKAGE_BLOCK_SOURCES = {"entry_point", "package_src"}


class LocalPackageInstallRequest(BaseModel):
    path: str = Field(..., min_length=1)


class LocalPackageInstallResponse(BaseModel):
    package_name: str
    version: str
    install_path: str
    modules: list[str]
    blocks_count: int
    replaced: bool


class InstalledPackageModel(BaseModel):
    package_name: str
    version: str
    install_path: str
    modules: list[str]
    has_backup: bool
    backup_version: str
    bundled: bool


class InstalledPackagesResponse(BaseModel):
    packages: list[InstalledPackageModel]


class PackageUpdateStatusModel(BaseModel):
    package_name: str
    current_version: str
    channel: str
    manifest_url: str
    status: str
    available_version: str
    min_core_base: str
    notes: str
    reason: str
    update_available: bool


class PackageUpdatesResponse(BaseModel):
    core_base: str
    statuses: list[PackageUpdateStatusModel]


class PackageActionResponse(BaseModel):
    package_name: str
    version: str
    action: str
    previous_version: str
    needs_relaunch: bool


def _is_bundled_desktop_run() -> bool:
    return os.environ.get("SCISTUDIO_BUNDLED", "").strip().lower() in {"1", "true", "yes"}


def _require_bundled() -> None:
    if not _is_bundled_desktop_run():
        raise HTTPException(
            status_code=403,
            detail="Package management is only available in bundled desktop runs.",
        )


def _registry_packages(runtime: ApiRuntime) -> dict:
    registry = runtime.block_registry
    getter = getattr(registry, "packages", None)
    return getter() if callable(getter) else {}


@router.post("/local", response_model=LocalPackageInstallResponse)
async def install_local_package_route(
    body: LocalPackageInstallRequest,
    runtime: RuntimeDep,
) -> LocalPackageInstallResponse:
    """Install a local package and refresh the block registry."""

    if not _is_bundled_desktop_run():
        raise HTTPException(
            status_code=403,
            detail="Local package installation is only available in bundled desktop runs.",
        )

    try:
        result = install_local_package(body.path, install_dependencies=True)
    except PackageInstallError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to install package: {exc}") from exc

    runtime.refresh_block_registry()
    module_names = set(result.modules)
    blocks_count = 0
    for spec in runtime.block_registry.all_specs().values():
        source = getattr(spec, "source", "")
        module_path = getattr(spec, "module_path", "")
        if source in _PACKAGE_BLOCK_SOURCES and any(
            module_path == module_name or module_path.startswith(f"{module_name}.") for module_name in module_names
        ):
            blocks_count += 1
    return LocalPackageInstallResponse(
        package_name=result.package_name,
        version=result.version,
        install_path=str(result.install_path),
        modules=list(result.modules),
        blocks_count=blocks_count,
        replaced=result.replaced,
    )


@router.get("/installed", response_model=InstalledPackagesResponse)
async def list_installed_packages_route(runtime: RuntimeDep) -> InstalledPackagesResponse:
    """List packages: on-disk user installs plus loaded bundled packages."""
    _require_bundled()
    installed = package_manager.list_installed_packages(registry_packages=_registry_packages(runtime))
    return InstalledPackagesResponse(
        packages=[
            InstalledPackageModel(
                package_name=pkg.package_name,
                version=pkg.version,
                install_path=str(pkg.install_path),
                modules=list(pkg.modules),
                has_backup=pkg.has_backup,
                backup_version=pkg.backup_version,
                bundled=pkg.bundled,
            )
            for pkg in installed
        ]
    )


@router.get("/updates", response_model=PackageUpdatesResponse)
async def check_package_updates_route(runtime: RuntimeDep) -> PackageUpdatesResponse:
    """Check each package's self-declared OTA source for newer releases."""
    _require_bundled()
    core_base = str(get_version().base)
    statuses = package_manager.check_package_updates(_registry_packages(runtime), core_base=core_base)
    return PackageUpdatesResponse(
        core_base=core_base,
        statuses=[
            PackageUpdateStatusModel(
                package_name=s.package_name,
                current_version=s.current_version,
                channel=s.channel,
                manifest_url=s.manifest_url,
                status=s.status,
                available_version=s.available_version,
                min_core_base=s.min_core_base,
                notes=s.notes,
                reason=s.reason,
                update_available=s.update_available,
            )
            for s in statuses
        ],
    )


@router.post("/{package_name}/update", response_model=PackageActionResponse)
async def update_package_route(package_name: str, runtime: RuntimeDep) -> PackageActionResponse:
    """Download, verify, and stage the latest release for one package."""
    _require_bundled()
    core_base = str(get_version().base)
    try:
        result = package_manager.update_package(
            package_name,
            packages=_registry_packages(runtime),
            core_base=core_base,
        )
    except package_manager.PackageUpdateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (PackageInstallError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update package: {exc}") from exc
    runtime.refresh_block_registry()
    return _action_response(result)


@router.post("/{package_name}/rollback", response_model=PackageActionResponse)
async def rollback_package_route(package_name: str, runtime: RuntimeDep) -> PackageActionResponse:
    """Restore the backed-up previous version of a package."""
    _require_bundled()
    try:
        result = package_manager.rollback_package(package_name)
    except package_manager.PackageUpdateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to roll back package: {exc}") from exc
    runtime.refresh_block_registry()
    return _action_response(result)


@router.delete("/{package_name}", response_model=PackageActionResponse)
async def delete_package_route(package_name: str, runtime: RuntimeDep) -> PackageActionResponse:
    """Uninstall a package and remove any rollback backup."""
    _require_bundled()
    try:
        result = package_manager.delete_package(package_name)
    except package_manager.PackageUpdateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete package: {exc}") from exc
    runtime.refresh_block_registry()
    return _action_response(result)


def _action_response(result: package_manager.PackageActionResult) -> PackageActionResponse:
    return PackageActionResponse(
        package_name=result.package_name,
        version=result.version,
        action=result.action,
        previous_version=result.previous_version,
        needs_relaunch=result.needs_relaunch,
    )
