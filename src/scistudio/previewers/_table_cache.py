"""Deprecated alias for :mod:`scistudio.panels._table_cache` (ADR-054 spec 1, FR-038).

Private core machinery that resolved under ``scistudio.previewers`` before the
rename. It carries no promise at all — the leading underscore says so — but it
imported, and the alias package's job is that no path that used to import
silently stops (FR-020). Recorded here so the retired module list is complete
rather than judged one module at a time.

The cache dict and its lock are re-exported by reference, not copied, so there
is one cache in the process however it is reached.

It contains no logic of its own — only imports and aliases. Removed under the
condition stated in the ADR-048 addendum (FR-044).
"""

from __future__ import annotations

from scistudio.panels._table_cache import (
    _TABLE_CACHE_MAX as _TABLE_CACHE_MAX,
)
from scistudio.panels._table_cache import (
    MAX_TABLE_PAGE_SIZE as MAX_TABLE_PAGE_SIZE,
)
from scistudio.panels._table_cache import (
    _get_preview_table as _get_preview_table,
)
from scistudio.panels._table_cache import (
    _read_preview_table_from_disk as _read_preview_table_from_disk,
)
from scistudio.panels._table_cache import (
    _table_cache as _table_cache,
)
from scistudio.panels._table_cache import (
    _table_cache_lock as _table_cache_lock,
)
from scistudio.panels._table_cache import (
    _trim_table_cache_locked as _trim_table_cache_locked,
)

__all__ = [
    "MAX_TABLE_PAGE_SIZE",
    "_TABLE_CACHE_MAX",
    "_get_preview_table",
    "_read_preview_table_from_disk",
    "_table_cache",
    "_table_cache_lock",
    "_trim_table_cache_locked",
]
