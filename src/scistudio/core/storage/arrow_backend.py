"""Apache Arrow / Parquet storage backend for tabular DataFrame and Series types."""

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
    """Storage backend for tabular data, backed by Apache Arrow / Parquet.

    Persists DataFrame- and Series-like data as Parquet files and reads them
    back as PyArrow tables. The router selects this backend for columnar
    tabular types, so you rarely construct it directly.

    Example:
        >>> import os, tempfile
        >>> backend = ArrowBackend()
        >>> path = os.path.join(tempfile.mkdtemp(), "t.parquet")
        >>> ref = backend.write({"x": [1, 2, 3]}, StorageReference(backend="arrow", path=path))
        >>> backend.read(ref).num_rows
        3
    """

    def read(self, ref: StorageReference) -> Any:
        """Read the Parquet file at *ref* and return it as a PyArrow table.

        Args:
            ref: Pointer to the stored Parquet file.

        Returns:
            The table as a :class:`pyarrow.Table`.

        Raises:
            StorageMissingError: When the file does not exist.
            StorageReferenceInvalidError: When the file is corrupt or unreadable.
        """
        try:
            return pq.read_table(ref.path)
        except (FileNotFoundError, pa.ArrowInvalid) as exc:
            raise _wrap_arrow_read_error(ref, "read", exc) from exc

    def write(self, data: Any, ref: StorageReference) -> StorageReference:
        """Write *data* as Parquet to *ref*.

        Args:
            data: A :class:`pyarrow.Table`, or a dict of column name to values.
            ref: Pointer describing where to write the file.

        Returns:
            An updated :class:`StorageReference` whose metadata records the
            column names and row count.

        Raises:
            TypeError: When *data* is neither a dict nor a :class:`pyarrow.Table`.
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
        """Write in-memory table/dict data to a new Parquet file at *path*.

        Args:
            data: A :class:`pyarrow.Table` or a dict of column name to values.
            path: Target filesystem path for the Parquet file.

        Returns:
            A :class:`StorageReference` pointing at the new file.
        """
        ref = StorageReference(backend="arrow", path=path)
        return self.write(data, ref)

    def slice(self, ref: StorageReference, *args: Any) -> Any:
        """Read only selected columns from the table at *ref*.

        Args:
            ref: Pointer to the stored Parquet file.
            *args: Column names to select, given either as separate arguments or
                as a single list. Empty selects all columns.

        Returns:
            A :class:`pyarrow.Table` containing only the requested columns.

        Raises:
            StorageMissingError: When the file does not exist.
            StorageReferenceInvalidError: When the file is corrupt or unreadable.
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
        """Yield the Parquet file at *ref* as successive row batches.

        Args:
            ref: Pointer to the stored Parquet file.
            chunk_size: Maximum number of rows per yielded batch.

        Yields:
            A :class:`pyarrow.Table` for each row batch.

        Raises:
            StorageMissingError: When the file does not exist.
            StorageReferenceInvalidError: When the file is corrupt or unreadable.
        """
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
        """Return Parquet-level metadata for *ref*.

        Args:
            ref: Pointer to the stored Parquet file.

        Returns:
            A dict with ``columns``, ``num_rows``, ``num_row_groups``, and a
            ``schema`` mapping each column name to its type.

        Raises:
            StorageMissingError: When the file does not exist.
            StorageReferenceInvalidError: When the file is corrupt or unreadable.
        """
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
