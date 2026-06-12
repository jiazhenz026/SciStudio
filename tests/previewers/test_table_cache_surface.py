"""Contract tests for the previewer-owned DataFrame table cache.

ADR-048 / issue #1598 moved the table-paging LRU cache down out of
``scistudio.api.runtime._preview_cache`` into
``scistudio.previewers._table_cache`` so the previewer subsystem no longer
imports up into the API layer. These tests pin the two behaviours the previous
``tests/api/test_runtime_import_surface.py`` guarded, now at the new location:

1. ``_table_cache`` / ``_table_cache_lock`` are shared module-level objects (a
   ``clear()`` from a test must mutate the same object the getter reads).
2. ``_get_preview_table`` resolves ``_read_preview_table_from_disk`` from this
   module's own namespace, so ``monkeypatch.setattr(_table_cache,
   "_read_preview_table_from_disk", ...)`` is observed by the getter — the
   contract the LRU-cache route test in ``tests/api/test_data.py`` depends on.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from _pytest.monkeypatch import MonkeyPatch

from scistudio.previewers import _table_cache


def test_table_cache_objects_are_module_level_singletons() -> None:
    assert isinstance(_table_cache._table_cache, OrderedDict)
    assert isinstance(_table_cache._table_cache_lock, type(threading.Lock()))


def test_get_preview_table_observes_monkeypatched_disk_reader(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Patching the disk reader on this module is seen by ``_get_preview_table``.

    Without the same-module name resolution this would silently bypass the
    mock and the cache-read-count assertions in ``test_data.py`` would be
    meaningless.
    """
    csv_path = tmp_path / "cached.csv"
    csv_path.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")

    # Own the cache lifecycle for this test.
    with _table_cache._table_cache_lock:
        _table_cache._table_cache.clear()

    calls: list[Path] = []
    real_read = _table_cache._read_preview_table_from_disk

    def counting_read(path: Path) -> Any:
        calls.append(path)
        return real_read(path)

    monkeypatch.setattr(_table_cache, "_read_preview_table_from_disk", counting_read)

    # First call hits disk through the patched reader; second is a cache hit.
    _table_cache._get_preview_table(csv_path, sort_by=None, sort_dir="asc")
    _table_cache._get_preview_table(csv_path, sort_by=None, sort_dir="asc")

    assert calls == [csv_path]
