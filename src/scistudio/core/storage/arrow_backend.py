"""Apache Arrow / Parquet storage backend for DataFrame types."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from scistudio.core.storage.ref import StorageReference


class ArrowBackend:
    """Arrow/Parquet-based storage backend for columnar tabular data."""

    def read(self, ref: StorageReference) -> Any:
        """Read a Parquet file from *ref* and return a PyArrow Table."""
        return pq.read_table(ref.path)

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
        return pq.read_table(ref.path, columns=columns)

    def iter_chunks(self, ref: StorageReference, chunk_size: int) -> Iterator[Any]:
        """Yield row-batched chunks from the Parquet file at *ref*."""
        pf = pq.ParquetFile(ref.path)
        for batch in pf.iter_batches(batch_size=chunk_size):
            yield pa.Table.from_batches([batch])

    def get_metadata(self, ref: StorageReference) -> dict[str, Any]:
        """Return Parquet-level metadata for *ref*."""
        pf = pq.ParquetFile(ref.path)
        schema = pf.schema_arrow
        return {
            "columns": schema.names,
            "num_rows": pf.metadata.num_rows,
            "num_row_groups": pf.metadata.num_row_groups,
            "schema": {f.name: str(f.type) for f in schema},
        }
