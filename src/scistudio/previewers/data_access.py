"""Deprecated alias for :mod:`scistudio.panels.data_access` (ADR-054 spec 1, FR-038).

``scistudio.previewers.data_access`` was the canonical author root for the
bounded reader injected on each request. The subsystem is now
:mod:`scistudio.panels`; this module keeps the retired path resolving for
unmigrated packages and on-disk drop-ins (FR-045, FR-020, FR-042).

The seven ``DEFAULT_*`` budget constants are re-exported alongside the types.
They were never in this module's ``__all__``, on either tree, but they resolved
here before the rename and their names did not change — so leaving them out
would be one more path that stops importing without saying so.

It contains no logic of its own — only imports and aliases. Removed under the
condition stated in the ADR-048 addendum (FR-044).
"""

from __future__ import annotations

from scistudio.panels.data_access import (
    DEFAULT_MAX_BYTES as DEFAULT_MAX_BYTES,
)
from scistudio.panels.data_access import (
    DEFAULT_MAX_DIM as DEFAULT_MAX_DIM,
)
from scistudio.panels.data_access import (
    DEFAULT_MAX_ITEMS as DEFAULT_MAX_ITEMS,
)
from scistudio.panels.data_access import (
    DEFAULT_MAX_ROWS as DEFAULT_MAX_ROWS,
)
from scistudio.panels.data_access import (
    DEFAULT_MAX_TILE as DEFAULT_MAX_TILE,
)
from scistudio.panels.data_access import (
    DEFAULT_SERIES_POINTS as DEFAULT_SERIES_POINTS,
)
from scistudio.panels.data_access import (
    DEFAULT_TEXT_CHARS as DEFAULT_TEXT_CHARS,
)
from scistudio.panels.data_access import (
    ArrayPlane as ArrayPlane,
)
from scistudio.panels.data_access import (
    ArrayTile as ArrayTile,
)
from scistudio.panels.data_access import (
    ArtifactInfo as ArtifactInfo,
)
from scistudio.panels.data_access import (
    CollectionSample as CollectionSample,
)
from scistudio.panels.data_access import (
    CompositeSlots as CompositeSlots,
)
from scistudio.panels.data_access import (
    DataFramePage as DataFramePage,
)
from scistudio.panels.data_access import (
    PreviewDataAccess as PreviewDataAccess,
)
from scistudio.panels.data_access import (
    SeriesPoints as SeriesPoints,
)
from scistudio.panels.data_access import (
    SliceAxis as SliceAxis,
)
from scistudio.panels.data_access import (
    TableXYPoints as TableXYPoints,
)
from scistudio.panels.data_access import (
    TextChunk as TextChunk,
)

__all__ = [
    "ArrayPlane",
    "ArrayTile",
    "ArtifactInfo",
    "CollectionSample",
    "CompositeSlots",
    "DataFramePage",
    "PreviewDataAccess",
    "SeriesPoints",
    "SliceAxis",
    "TableXYPoints",
    "TextChunk",
]
