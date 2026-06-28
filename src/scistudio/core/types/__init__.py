"""DataObject type hierarchy — re-exports all base types.

Per ADR-027 D2, ``scistudio.core.types`` contains ONLY the base types.
Domain subtypes (``Image``, ``FluorImage``, ``MSImage``, ``SRSImage``,
``Spectrum``, ``RamanSpectrum``, ``MassSpectrum``, ``PeakTable``,
``MetabPeakTable``, ``AnnData``, ``SpatialData``) live in plugin
packages (``scistudio-blocks-imaging``, ``scistudio-blocks-spectral``,
``scistudio-blocks-msi``, ``scistudio-blocks-singlecell``,
``scistudio-blocks-spatial-omics``).

T-006 deleted the Array-family subclasses; T-007 deletes the remaining
Series/DataFrame/Composite domain subclasses.
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
