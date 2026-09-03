"""Deprecated alias for :mod:`scistudio.panels._raster` (ADR-054 spec 1, FR-038).

Private core machinery that resolved under ``scistudio.previewers`` before the
rename. It carries no promise at all — the leading underscore says so — but it
imported, and the alias package's job is that no path that used to import
silently stops (FR-020). Recorded here so the retired module list is complete
rather than judged one module at a time.

It contains no logic of its own — only imports and aliases. Removed under the
condition stated in the ADR-048 addendum (FR-044).
"""

from __future__ import annotations

from scistudio.panels._raster import (
    _downsample_matrix as _downsample_matrix,
)
from scistudio.panels._raster import (
    _image_data_uri_from_matrix as _image_data_uri_from_matrix,
)
from scistudio.panels._raster import (
    _load_preview_matrix as _load_preview_matrix,
)

__all__ = [
    "_downsample_matrix",
    "_image_data_uri_from_matrix",
    "_load_preview_matrix",
]
