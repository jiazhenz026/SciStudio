"""DataFrame preview paging + caching.

Issue #1430 / umbrella #1427: extracted verbatim from the original
``api/runtime.py`` god-file. Behavior is unchanged. The module-level
symbols (``MAX_TABLE_PAGE_SIZE``, ``_TABLE_CACHE_MAX``, ``_table_cache``,
``_table_cache_lock``, ``_read_preview_table_from_disk``,
``_get_preview_table``, ``_trim_table_cache_locked``) are re-exported by
``runtime/__init__.py`` so existing tests that reach in via
``runtime_mod._table_cache_lock`` keep working.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

# DataFrame preview paging — cap the per-request payload to keep the response
# under a few hundred KB even with wide tables.
MAX_TABLE_PAGE_SIZE = 200

# DataFrame preview cache — keyed by (path, mtime_ns, sort_by, sort_dir).
# Empty sort_by means the unsorted base table; sorted variants reuse the
# cached base on miss to avoid re-parsing the source file.
#
# Wide-table sorts (e.g. 5200 rows x 40 cols) cost ~200 ms per request when
# we re-read + re-sort on every page click. The cache turns that into a
# one-time cost per (column, direction) pair; subsequent pagination of the
# same sort lands O(slice).
#
# Cap is intentionally small — large enough to cover typical
# unsorted+asc+desc trios per column but bounded by RAM.
_TABLE_CACHE_MAX = 16
_table_cache: OrderedDict[tuple[str, int, str, str], Any] = OrderedDict()
_table_cache_lock = threading.Lock()


def _trim_table_cache_locked() -> None:
    """Evict oldest entries until under the cap. Caller holds the lock."""
    while len(_table_cache) > _TABLE_CACHE_MAX:
        _table_cache.popitem(last=False)


def _read_preview_table_from_disk(path: Path) -> Any:
    """Read a csv/parquet file into a pyarrow Table — uncached."""
    if path.suffix.lower() == ".parquet":
        return pq.read_table(path)
    import pyarrow.csv as pcsv

    return pcsv.read_csv(str(path))


def _get_preview_table(path: Path, sort_by: str | None, sort_dir: str) -> Any:
    """Return a parsed (and optionally sorted) pyarrow Table for ``path``.

    Cached by (path, mtime, sort_by, sort_dir). On sort-variant cache miss
    we look up the unsorted base in the same cache to avoid re-reading the
    file, sort that, then cache the sorted variant.
    """
    # Resolve ``_read_preview_table_from_disk`` via the package module so the
    # public ``runtime._read_preview_table_from_disk`` symbol is the
    # single source of truth — the pre-split tests
    # (``test_data.test_preview_dataframe_paging_sort_lru_cache``) patch
    # the function on the public ``scistudio.api.runtime`` module via
    # ``monkeypatch.setattr``; this indirection keeps that patch live.
    from scistudio.api import runtime as _runtime_pkg

    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        mtime = 0
    sort_key = sort_by or ""
    dir_key = sort_dir if sort_key else ""
    key = (str(path), mtime, sort_key, dir_key)

    with _table_cache_lock:
        cached = _table_cache.get(key)
        if cached is not None:
            _table_cache.move_to_end(key)
            return cached

    # Cache miss — try to reuse an already-parsed unsorted base, otherwise read disk.
    base = None
    if sort_key:
        base_key = (str(path), mtime, "", "")
        with _table_cache_lock:
            base = _table_cache.get(base_key)
            if base is not None:
                _table_cache.move_to_end(base_key)
    if base is None:
        base = _runtime_pkg._read_preview_table_from_disk(path)
        if sort_key:
            # Persist the unsorted base too so the next sort change skips IO.
            base_key = (str(path), mtime, "", "")
            with _table_cache_lock:
                _table_cache[base_key] = base
                _trim_table_cache_locked()

    if sort_key:
        order = "descending" if dir_key == "desc" else "ascending"
        table = base.sort_by([(sort_key, order)])
    else:
        table = base

    with _table_cache_lock:
        _table_cache[key] = table
        _trim_table_cache_locked()
    return table
