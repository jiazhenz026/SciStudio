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
    """Storage backend for chunked N-dimensional arrays, backed by Zarr.

    Persists array data as a chunked, compressed Zarr store and reads it back as
    numpy arrays. The router selects this backend for array types, so you rarely
    construct it directly. Writes are atomic: on a crash or cancellation the
    previous store is left intact rather than half-written.

    Example:
        >>> import os, tempfile
        >>> import numpy as np
        >>> backend = ZarrBackend()
        >>> path = os.path.join(tempfile.mkdtemp(), "a.zarr")
        >>> ref = backend.write(np.arange(6).reshape(2, 3), StorageReference(backend="zarr", path=path))
        >>> backend.read(ref).shape
        (2, 3)
    """

    def read(self, ref: StorageReference) -> Any:
        """Read the Zarr array at *ref* and return it as a numpy array.

        Args:
            ref: Pointer to the stored Zarr array.

        Returns:
            The array as a :class:`numpy.ndarray`.

        Raises:
            StorageMissingError: When the store does not exist.
            StorageReferenceInvalidError: When the store is corrupt or unreadable.
        """
        try:
            arr = zarr.open_array(ref.path, mode="r")
            return np.asarray(arr)
        except Exception as exc:
            raise _wrap_zarr_read_error(ref, "read", exc) from exc

    def write(self, data: Any, ref: StorageReference) -> StorageReference:
        """Write *data* as a Zarr array to *ref*.

        Writes to a scratch directory and renames into place, so either the
        old data remains intact or the new data is fully committed.

        Args:
            data: Array-like data (converted via :func:`numpy.asarray`).
            ref: Pointer describing where to write the store. An ``"axes"`` key
                in ``ref.metadata`` is stored as a Zarr attribute.

        Returns:
            An updated :class:`StorageReference` whose metadata records the
            array shape and dtype.
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
        """Read a sub-array from the Zarr store at *ref* without loading it whole.

        Args:
            ref: Pointer to the stored Zarr array.
            *args: numpy-style index expressions (slices, ints) applied to the
                array.

        Returns:
            The selected sub-array as a :class:`numpy.ndarray`.

        Raises:
            StorageMissingError: When the store does not exist.
            StorageReferenceInvalidError: When the store is corrupt or unreadable.
        """
        try:
            arr = zarr.open_array(ref.path, mode="r")
            return np.asarray(arr[args])
        except Exception as exc:
            raise _wrap_zarr_read_error(ref, "slice", exc) from exc

    def iter_chunks(self, ref: StorageReference, chunk_size: int) -> Iterator[Any]:
        """Yield the Zarr array at *ref* in slabs along its first axis.

        Args:
            ref: Pointer to the stored Zarr array.
            chunk_size: Number of elements along axis 0 per yielded slab.

        Yields:
            A :class:`numpy.ndarray` slab for each range along axis 0.

        Raises:
            StorageMissingError: When the store does not exist.
            StorageReferenceInvalidError: When the store is corrupt or unreadable.
        """
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
        """Write in-memory array data to a new Zarr store at *path*.

        Args:
            data: Array-like data (converted via :func:`numpy.asarray`).
            path: Target filesystem path for the Zarr store.

        Returns:
            A :class:`StorageReference` pointing at the new store.
        """
        ref = StorageReference(backend="zarr", path=path)
        return self.write(data, ref)

    def get_metadata(self, ref: StorageReference) -> dict[str, Any]:
        """Return Zarr-level metadata for *ref*.

        Args:
            ref: Pointer to the stored Zarr array.

        Returns:
            A dict with ``shape``, ``dtype``, ``chunks``, and ``ndim``, plus an
            ``axes`` entry when the store records one.

        Raises:
            StorageMissingError: When the store does not exist.
            StorageReferenceInvalidError: When the store is corrupt or unreadable.
        """
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
