"""Content hashing for lineage (xxhash on data chunks)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import xxhash

if TYPE_CHECKING:
    from scistudio.core.types.collection import Collection


def content_hash(data: Any) -> str:
    """Compute a content hash for lineage tracking using xxhash.

    Supports bytes, str, numpy arrays, pyarrow tables, and falls back
    to hashing ``repr()`` for other types.
    """
    hasher = xxhash.xxh64()

    if isinstance(data, bytes):
        hasher.update(data)
    elif isinstance(data, str):
        hasher.update(data.encode("utf-8"))
    else:
        # Try numpy ndarray
        try:
            import numpy as np

            if isinstance(data, np.ndarray):
                hasher.update(np.array(data.shape, dtype=np.int64).tobytes())
                hasher.update(data.dtype.str.encode("utf-8"))
                hasher.update(data.tobytes())
                return hasher.hexdigest()
        except ImportError:
            pass

        # Try pyarrow Table
        try:
            import pyarrow as pa

            if isinstance(data, pa.Table):
                for batch in data.to_batches():
                    for column in batch.columns:
                        for buf in column.buffers():
                            if buf is not None:
                                hasher.update(buf)
                return hasher.hexdigest()
        except ImportError:
            pass

        # Fallback: repr-based hash
        hasher.update(repr(data).encode("utf-8"))

    return hasher.hexdigest()


def collection_hashes(collection: Collection) -> list[str]:
    """Compute per-item content hashes for a Collection.

    Returns a list of content hashes, one per item in the Collection,
    preserving the Collection's item order.

    Issue #55: Enables item-level lineage tracking for Collection ports.
    """
    return [content_hash(item) for item in collection]
