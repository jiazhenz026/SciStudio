"""API-side helpers for image/type inference on catalog registration.

Historically this module also held previewer-facing image helpers; those moved
up into the API layer. The API-specific ``_infer_type_name_from_ref`` stays
here — it infers a recorded type name from API storage metadata and has no
previewer consumer.
"""

from __future__ import annotations

from typing import Any

from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.text import Text


def _specific_type_for_extension(registry: Any, extension: str) -> str | None:
    """Return the one installed non-``Artifact`` type that loads *extension*.

    #2112: a file registered straight off disk (the data-tree preview tab, an
    upload) carries no ``type_chain``, so the extension heuristic below is all
    the router has to go on. Hardcoding it to core types recorded ``.tif`` as
    :class:`Artifact` and routed the generic artifact previewer even with the
    imaging package installed and declaring ``Image`` for ``.tif``.

    The ADR-043 load capability table already states which type each extension
    can be read as, so ask it rather than duplicating the mapping. ``Artifact``
    is dropped from the candidates because it declares every opaque extension
    by design and would otherwise mask the specific answer. A tie is left
    unresolved on purpose: ``.csv`` is loadable as ``DataFrame``,
    ``LCMSFeatureTable``, ``Series`` and ``Spectrum`` depending on which
    packages are installed, and guessing between them would make the recorded
    type depend on install order. Only an unambiguous single candidate wins;
    everything else keeps today's answer.
    """
    if registry is None or not extension:
        return None
    try:
        capabilities = registry.list_format_capabilities(direction="load", extension=extension)
    except Exception:  # pragma: no cover - a registry that cannot answer is not authoritative
        return None
    candidates = {
        str(capability.data_type.__name__)
        for capability in capabilities
        if capability.data_type.__name__ != Artifact.__name__
    }
    if len(candidates) == 1:
        return candidates.pop()
    return None


def _infer_type_name_from_ref(ref: StorageReference, registry: Any | None = None) -> str:
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
    # #2112: before settling for the opaque fallback, let an installed package
    # claim the extension (``.tif``/``.nd2`` -> ``Image``). Core formats above
    # keep their fixed answer so a package cannot silently retype ``.csv``.
    installed = _specific_type_for_extension(registry, f".{fmt}" if fmt else "")
    if installed is not None:
        return installed
    return Artifact.__name__


__all__ = ["_infer_type_name_from_ref", "_specific_type_for_extension"]
