"""Apache Arrow / Parquet storage backend for DataFrame types."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from scistudio.core.storage.errors import StorageMissingError, StorageReferenceInvalidError
from scistudio.core.storage.ref import StorageReference


def _wrap_arrow_read_error(ref: StorageReference, operation: str, exc: Exception) -> StorageReferenceInvalidError:
    if isinstance(exc, FileNotFoundError):
        return StorageMissingError(ref, operation=operation, detail=str(exc))
    if isinstance(exc, pa.ArrowInvalid):
        return StorageReferenceInvalidError(
            ref,
            reason="corrupt_or_unreadable",
            operation=operation,
            detail=str(exc),
        )
    raise exc


class ArrowBackend:
    """Arrow/Parquet-based storage backend for columnar tabular data."""

    def read(self, ref: StorageReference) -> Any:
        """Read a Parquet file from *ref* and return a PyArrow Table."""
        try:
            return pq.read_table(ref.path)
        except (FileNotFoundError, pa.ArrowInvalid) as exc:
            raise _wrap_arrow_read_error(ref, "read", exc) from exc

    def write(self, data: Any, ref: StorageReference) -> StorageReference:
        """Write *data* (PyArrow Table or dict) as Parquet to *ref*.

        Returns an updated :class:`StorageReference` with column metadata.
        """
        if isinstance(data, dict):
            table = pa.table(data)
        elif isinstance(data, pa.Table):
            table = data
        else:
            raise TypeError(f"ArrowBackend.write expects dict or pa.Table, got {type(data).__name__}")
        pq.write_table(table, ref.path)
        metadata = dict(ref.metadata) if ref.metadata else {}
        metadata.update(
            {
                "columns": table.column_names,
                "num_rows": table.num_rows,
            }
        )
        return StorageReference(
            backend="arrow",
            path=ref.path,
            format="parquet",
            metadata=metadata,
        )

    def write_from_memory(self, data: Any, path: str) -> StorageReference:
        """Write raw in-memory Arrow/dict data to Parquet at *path*."""
        ref = StorageReference(backend="arrow", path=path)
        return self.write(data, ref)

    def slice(self, ref: StorageReference, *args: Any) -> Any:
        """Return a column-selected subset from the table at *ref*.

        *args* should be a list of column names to select, or a single
        list argument.
        """
        columns: list[str] | None = None
        if args:
            first = args[0]
            columns = first if isinstance(first, list) else list(args)
        try:
            return pq.read_table(ref.path, columns=columns)
        except (FileNotFoundError, pa.ArrowInvalid) as exc:
            raise _wrap_arrow_read_error(ref, "slice", exc) from exc

    def iter_chunks(self, ref: StorageReference, chunk_size: int) -> Iterator[Any]:
        """Yield row-batched chunks from the Parquet file at *ref*."""
        try:
            pf = pq.ParquetFile(ref.path)
        except (FileNotFoundError, pa.ArrowInvalid) as exc:
            raise _wrap_arrow_read_error(ref, "iter_chunks", exc) from exc
        for batch in pf.iter_batches(batch_size=chunk_size):
            try:
                yield pa.Table.from_batches([batch])
            except pa.ArrowInvalid as exc:
                raise _wrap_arrow_read_error(ref, "iter_chunks", exc) from exc

    def get_metadata(self, ref: StorageReference) -> dict[str, Any]:
        """Return Parquet-level metadata for *ref*."""
        try:
            pf = pq.ParquetFile(ref.path)
        except (FileNotFoundError, pa.ArrowInvalid) as exc:
            raise _wrap_arrow_read_error(ref, "get_metadata", exc) from exc
        schema = pf.schema_arrow
        return {
            "columns": schema.names,
            "num_rows": pf.metadata.num_rows,
            "num_row_groups": pf.metadata.num_row_groups,
            "schema": {f.name: str(f.type) for f in schema},
        }
