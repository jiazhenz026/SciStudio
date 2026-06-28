"""Core data types shared by every SciStudio block.

This package holds the small set of general-purpose data containers that
blocks pass to one another:

- :class:`Array` — N-dimensional arrays (images, volumes, stacks),
- :class:`Series` — 1D indexed data (time series, chromatograms, spectra),
- :class:`DataFrame` — columnar tables,
- :class:`Text` — plain text, Markdown, or JSON,
- :class:`Artifact` — opaque files (PDFs, reports, binary blobs),
- :class:`CompositeData` — named bundles of the above,
- :class:`Collection` — an ordered batch of items, all of one type.

:class:`DataObject` is the base class they all inherit from, and
:class:`TypeSignature` describes an object's type so blocks can check that
two ports are compatible.

Only these general-purpose types live here. Domain-specific kinds
(microscopy images, spectra, peak tables, single-cell and spatial-omics
containers, and so on) live in their own plugin packages and build on
these base types. Reach for a base type directly when your data needs no
specialised container — for example ``Array(axes=["y", "x"])`` for a plain
2D image.

Example:
    >>> from scistudio.core.types import Array, Collection
    >>> img = Array(axes=["y", "x"], shape=(512, 512))
    >>> batch = Collection([img], item_type=Array)
    >>> batch.length
    1
"""

from __future__ import annotations

from scistudio.core.storage.ref import StorageReference

# #1342 / round-4 no-cycles: importing this registers the default
# ``type -> backend`` builder callback with ``core.storage.backend_router``
# (the wiring lives on the types side so storage never imports concrete
# types). Importing any DataObject runs this package __init__, so the default
# router is always wired before the first ``save`` / ``get_router`` call.
from scistudio.core.types import _backend_defaults  # noqa: F401
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject, TypeSignature
from scistudio.core.types.collection import Collection
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

# ADR-052 §3.9: ``TypeRegistry`` / ``TypeSpec`` are Internal (owner
# 2026-06-27, "A confirmed"; 0 author-facing importers). They are NOT
# re-exported from this canonical root and are excluded from ``__all__``;
# internal callers import them from ``scistudio.core.types.registry``.

__all__ = [
    "Array",
    "Artifact",
    "Collection",
    "CompositeData",
    "DataFrame",
    "DataObject",
    "Series",
    "StorageReference",
    "Text",
    "TypeSignature",
]
