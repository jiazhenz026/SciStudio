"""Type-name inference for API preview payloads.

Issue #1430 / umbrella #1427 originally extracted the raster preview helpers
here from the ``api/runtime.py`` god-file. ADR-048 / issue #1598 moved the
raster load/downsample/encode pipeline (``_image_data_uri_from_matrix``,
``_load_preview_matrix``, ``_downsample_matrix``) down into
``scistudio.previewers._raster`` so the previewer subsystem no longer imports
up into the API layer. The API-specific ``_infer_type_name_from_ref`` stays
here — it infers only core type names from API storage metadata and has no
previewer consumer.
"""

from __future__ import annotations

from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.text import Text


def _infer_type_name_from_ref(ref: StorageReference) -> str:
    # ADR-027 D2 / #407: prefer the type_chain written by the worker subprocess
    # via _serialise_one().  The rightmost (most specific) entry is the
    # canonical type name.  Fall through to the extension heuristic only when
    # metadata is absent (e.g. file uploads that have no type_chain yet).
    if ref.metadata:
        type_chain = ref.metadata.get("type_chain")
        if type_chain and isinstance(type_chain, list) and type_chain:
            return str(type_chain[-1])

    fmt = (ref.format or "").lower()
    if fmt in {"csv", "parquet"}:
        return DataFrame.__name__
    if fmt in {"txt", "json", "yaml", "yml", "md"}:
        return Text.__name__
    if fmt == "zarr":
        return Array.__name__
    return Artifact.__name__


__all__ = ["_infer_type_name_from_ref"]
