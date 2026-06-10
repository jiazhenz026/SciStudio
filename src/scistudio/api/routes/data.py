"""Data upload, metadata, and preview endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from scistudio.api.deps import get_runtime
from scistudio.api.runtime import ApiRuntime
from scistudio.api.schemas import DataMetadataResponse, DataPreviewResponse, DataUploadResponse

router = APIRouter(prefix="/api/data", tags=["data"])
UploadFileParam = Annotated[UploadFile, File(...)]
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]


MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB read granularity


@router.post("/upload", response_model=DataUploadResponse)
async def upload_data(
    file: UploadFileParam,
    runtime: RuntimeDep,
) -> DataUploadResponse:
    """Upload a data file and register it in the active project.

    #1526: stream the request body in fixed-size chunks while tracking a
    running byte counter and abort with 413 as soon as the cap is exceeded.
    Previously the whole body was buffered via ``await file.read()`` *before*
    the size check, so an oversized upload (accidental or hostile) could
    exhaust process memory before the 413 ever fired.
    """
    destination, staged_path = runtime.stage_upload_file(file.filename or "upload.bin")
    total = 0
    try:
        with staged_path.open("wb") as staged:
            while True:
                chunk = await file.read(_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail="File too large (max 2 GB)")
                staged.write(chunk)
        payload = runtime.finish_staged_upload(destination, staged_path)
    except Exception:
        runtime.discard_staged_upload(staged_path)
        raise
    return DataUploadResponse(**payload)


@router.get("/{data_ref}", response_model=DataMetadataResponse)
@router.get("/{data_ref}/metadata", response_model=DataMetadataResponse, include_in_schema=False)
async def get_data_metadata(data_ref: str, runtime: RuntimeDep) -> DataMetadataResponse:
    """Return metadata for a stored data object."""
    try:
        record = runtime.get_data_record(data_ref)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DataMetadataResponse(ref=record.id, type_name=record.type_name, metadata=record.metadata)


@router.get("/{data_ref}/preview", response_model=DataPreviewResponse)
async def preview_data(
    data_ref: str,
    runtime: RuntimeDep,
    slice: int = 0,
    page: int = 1,
    page_size: int = 50,
    sort_by: str | None = None,
    sort_dir: str = "asc",
) -> DataPreviewResponse:
    """Return a lightweight preview of a stored data object.

    #899 — ``slice`` query param selects an index along the
    auto-detected slider axis (the first non-(y, x) dim) for 3-D
    images. Out-of-range values are clamped server-side.

    DataFrame paging: ``page`` (1-based), ``page_size`` (capped at 200),
    ``sort_by`` (column name), ``sort_dir`` (``asc``/``desc``). Page is
    clamped to [1, ceil(total_rows / page_size)] server-side. Sort is
    ignored when the column is missing. Non-table previews ignore these.
    """
    try:
        record = runtime.get_data_record(data_ref)
        preview = runtime.preview_data(
            data_ref,
            slice_index=slice,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DataPreviewResponse(ref=record.id, type_name=record.type_name, preview=preview)
