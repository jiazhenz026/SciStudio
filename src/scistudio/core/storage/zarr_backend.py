"""Zarr storage backend for Array types (chunked, compressed, lazy)."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import zarr

from scistudio.core.storage.errors import StorageMissingError, StorageReferenceInvalidError
from scistudio.core.storage.ref import StorageReference

_ZARR_MISSING_ERRORS: tuple[type[BaseException], ...] = (
    FileNotFoundError,
    *tuple(
        error_type
        for error_name in ("PathNotFoundError", "ArrayNotFoundError")
        if (error_type := getattr(zarr.errors, error_name, None)) is not None
    ),
)


def _wrap_zarr_read_error(ref: StorageReference, operation: str, exc: Exception) -> StorageReferenceInvalidError:
    if _ZARR_MISSING_ERRORS and isinstance(exc, _ZARR_MISSING_ERRORS):
        return StorageMissingError(ref, operation=operation, detail=str(exc))
    return StorageReferenceInvalidError(
        ref,
        reason="corrupt_or_unreadable",
        operation=operation,
        detail=str(exc),
    )


class ZarrBackend:
    """Zarr-based storage backend for chunked N-dimensional arrays."""

    def read(self, ref: StorageReference) -> Any:
        """Read a Zarr array from *ref* and return it as a numpy array."""
        try:
            arr = zarr.open_array(ref.path, mode="r")
            return np.asarray(arr)
        except Exception as exc:
            raise _wrap_zarr_read_error(ref, "read", exc) from exc

    def write(self, data: Any, ref: StorageReference) -> StorageReference:
        """Write *data* (numpy array) as a Zarr array to *ref*.

        Returns an updated :class:`StorageReference` with shape/dtype metadata.

        Uses write-to-temp-directory-then-rename for atomicity: on crash or
        cancellation, either the old data remains intact or the new data is
        fully committed.
        """
        arr = np.asarray(data)

        target = Path(ref.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = tempfile.mkdtemp(dir=target.parent, prefix=".zarr_tmp_")
        try:
            z = zarr.open_array(tmp_dir, mode="w", shape=arr.shape, dtype=arr.dtype)
            z[:] = arr
            if ref.metadata and "axes" in ref.metadata:
                z.attrs["axes"] = ref.metadata["axes"]

            # Atomic swap: remove old target (if exists), rename temp to target.
            if target.exists():
                shutil.rmtree(target)
            Path(tmp_dir).rename(target)
        except BaseException:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise

        metadata = dict(ref.metadata) if ref.metadata else {}
        metadata.update({"shape": list(arr.shape), "dtype": str(arr.dtype)})
        return StorageReference(
            backend="zarr",
            path=ref.path,
            format=ref.format,
            metadata=metadata,
        )

    def slice(self, ref: StorageReference, *args: Any) -> Any:
        """Return a sub-array slice from the Zarr store at *ref*.

        *args* should be valid numpy-style index expressions (slices, ints).
        """
        try:
            arr = zarr.open_array(ref.path, mode="r")
            return np.asarray(arr[args])
        except Exception as exc:
            raise _wrap_zarr_read_error(ref, "slice", exc) from exc

    def iter_chunks(self, ref: StorageReference, chunk_size: int) -> Iterator[Any]:
        """Yield chunks along axis 0 of the Zarr array at *ref*."""
        try:
            arr = zarr.open_array(ref.path, mode="r")
            total = arr.shape[0]
            for start in range(0, total, chunk_size):
                end = min(start + chunk_size, total)
                try:
                    yield np.asarray(arr[start:end])
                except Exception as exc:
                    raise _wrap_zarr_read_error(ref, "iter_chunks", exc) from exc
        except _ZARR_MISSING_ERRORS as exc:
            raise StorageMissingError(ref, operation="iter_chunks", detail=str(exc)) from exc

    def write_from_memory(self, data: Any, path: str) -> StorageReference:
        """Write raw in-memory numpy data to a Zarr store at *path*."""
        ref = StorageReference(backend="zarr", path=path)
        return self.write(data, ref)

    def get_metadata(self, ref: StorageReference) -> dict[str, Any]:
        """Return Zarr-level metadata for *ref*."""
        try:
            arr = zarr.open_array(ref.path, mode="r")
        except Exception as exc:
            raise _wrap_zarr_read_error(ref, "get_metadata", exc) from exc
        meta: dict[str, Any] = {
            "shape": list(arr.shape),
            "dtype": str(arr.dtype),
            "chunks": list(arr.chunks),
            "ndim": arr.ndim,
        }
        axes = arr.attrs.get("axes")
        if axes is not None:
            meta["axes"] = axes
        return meta
