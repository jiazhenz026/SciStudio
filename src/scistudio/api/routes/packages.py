"""Desktop package installation endpoints."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from scistudio.api.deps import get_runtime
from scistudio.api.runtime import ApiRuntime
from scistudio.desktop.package_installer import PackageInstallError, install_local_package

router = APIRouter(prefix="/api/packages", tags=["packages"])
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]


class LocalPackageInstallRequest(BaseModel):
    path: str = Field(..., min_length=1)


class LocalPackageInstallResponse(BaseModel):
    package_name: str
    version: str
    install_path: str
    modules: list[str]
    blocks_count: int
    replaced: bool


def _is_bundled_desktop_run() -> bool:
    return os.environ.get("SCISTUDIO_BUNDLED", "").strip().lower() in {"1", "true", "yes"}


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
        result = install_local_package(body.path)
    except PackageInstallError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to install package: {exc}") from exc

    runtime.refresh_block_registry()
    module_names = set(result.modules)
    blocks_count = sum(
        1
        for spec in runtime.block_registry.all_specs().values()
        if getattr(spec, "source", "") == "package_src" and getattr(spec, "module_path", "") in module_names
    )
    return LocalPackageInstallResponse(
        package_name=result.package_name,
        version=result.version,
        install_path=str(result.install_path),
        modules=list(result.modules),
        blocks_count=blocks_count,
        replaced=result.replaced,
    )
