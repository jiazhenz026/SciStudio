"""Streaming export helpers used by the ``SaveData`` dispatch functions.

ADR-031 Phase 3 (Task 18) introduced row-group / zero-materialisation
write paths for the storage-backed DataFrame and zarr-backed Array cases
so very large tables and chunked arrays can be written without
allocating the entire payload in memory. The functions live here so the
:class:`SaveData` class file stays under the 750-LOC god-file threshold
per issue #1459 (Phase 2 of #1427).

Per ADR-028 Addendum 1 §C9 ("private functions, not helper classes")
every symbol is underscore-prefixed; the module itself starts with an
underscore and is package-private.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from scistudio.blocks.io.savers._helpers import _dataframe_to_arrow_table
from scistudio.core.types.base import DataObject


def _zarr_store_copy(src_path: str, dst_path: str) -> None:
    """Copy a zarr store from *src_path* to *dst_path* without materialisation.

    Uses ``shutil.copytree`` for a file-level copy of the zarr directory
    store. This copies the compressed chunks directly, avoiding any
    decompression/recompression round-trip.
    """
    dst = Path(dst_path)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src_path, dst_path)


def _streaming_save_dataframe_csv(obj: DataObject, path: Path, delimiter: str = ",") -> None:
    """Stream a storage-backed DataFrame to CSV/TSV via row-group batches.

    Reads from the arrow backend in chunks and writes each batch to the
    output file, avoiding full materialisation of the entire table.
    """
    import pyarrow.csv as pcsv

    ref = getattr(obj, "_storage_ref", None)
    if ref is None or ref.backend != "arrow":
        # Fallback: full materialisation
        table = _dataframe_to_arrow_table(obj)  # type: ignore[arg-type]
        pcsv.write_csv(
            table,
            str(path),
            write_options=pcsv.WriteOptions(delimiter=delimiter),
        )
        return

    from scistudio.core.storage.arrow_backend import ArrowBackend

    backend = ArrowBackend()
    # Write header from first chunk, then append remaining chunks
    first_chunk = True
    with open(str(path), "wb") as fh:
        for chunk_table in backend.iter_chunks(ref, chunk_size=65536):
            pcsv.write_csv(
                chunk_table,
                fh,
                write_options=pcsv.WriteOptions(
                    delimiter=delimiter,
                    include_header=first_chunk,
                ),
            )
            first_chunk = False


def _streaming_save_dataframe_parquet(obj: DataObject, path: Path) -> None:
    """Stream a storage-backed DataFrame to Parquet via row-group batches.

    Reads from the arrow backend in chunks and writes each batch as a
    separate row group, avoiding full materialisation.
    """
    import pyarrow.parquet as pq

    ref = getattr(obj, "_storage_ref", None)
    if ref is None or ref.backend != "arrow":
        # Fallback: full materialisation
        table = _dataframe_to_arrow_table(obj)  # type: ignore[arg-type]
        pq.write_table(table, str(path))
        return

    from scistudio.core.storage.arrow_backend import ArrowBackend

    backend = ArrowBackend()
    writer = None
    try:
        for chunk_table in backend.iter_chunks(ref, chunk_size=65536):
            if writer is None:
                writer = pq.ParquetWriter(str(path), chunk_table.schema)
            writer.write_table(chunk_table)
    finally:
        if writer is not None:
            writer.close()


__all__ = [
    "_streaming_save_dataframe_csv",
    "_streaming_save_dataframe_parquet",
    "_zarr_store_copy",
]
