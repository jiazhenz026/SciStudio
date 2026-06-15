"""Shared data-model plumbing for the spectroscopy package (internal).

Every block builds, reads, and derives :class:`Spectrum` /
:class:`SpectralDataset` / core ``DataFrame`` values through these helpers so the
storage model stays consistent across the package. Implementers MUST NOT touch
``_transient_data`` / ``storage_ref`` directly.

Storage model:

- A :class:`Spectrum` payload is a two-column ``pyarrow.Table`` whose columns are
  named by its ``index_name`` (``"lambda"``) and ``value_name``
  (``"intensity"``). In-memory spectra carry it on the transient slot; persisted
  spectra read it back through ``to_memory()``.
- A core ``DataFrame`` payload (feature tables, diagnostics, dataset slots) is a
  ``pyarrow.Table`` carried the same way.

This module depends only on ``numpy`` + ``pyarrow`` (both core dependencies);
heavy scientific libraries (``scipy``) must be lazy-imported inside the blocks
that need them, never here and never at any module top level.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any, cast

import numpy as np
import pyarrow as pa

from scistudio.core.types.base import DataObject, FrameworkMeta
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy.types import (
    INTENSITY_COLUMN,
    LAMBDA_COLUMN,
    SpectralDataset,
    Spectrum,
)

# ---------------------------------------------------------------------------
# IDs
# ---------------------------------------------------------------------------


def new_spectrum_id(prefix: str = "spec") -> str:
    """Return a fresh, collision-free internal spectrum id (FR-035).

    Never derived from a filename (FR-036); loaders keep ``source_file`` as
    separate metadata.
    """
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Arrow / DataFrame plumbing
# ---------------------------------------------------------------------------


def arrow_table(columns: Mapping[str, Sequence[Any] | np.ndarray]) -> pa.Table:
    """Build a ``pyarrow.Table`` from an ordered column mapping."""
    return pa.table({name: pa.array(np.asarray(values)) for name, values in columns.items()})


def dataframe_from_arrow(table: pa.Table) -> DataFrame:
    """Wrap a ``pyarrow.Table`` in a core ``DataFrame`` (transient payload)."""
    frame = DataFrame(columns=list(table.column_names), row_count=table.num_rows)
    frame._arrow_table = table
    return frame


def dataframe_from_rows(rows: Sequence[Mapping[str, Any]], columns: Sequence[str] | None = None) -> DataFrame:
    """Build a flat core ``DataFrame`` from a list of row dicts.

    ``columns`` fixes the column order (and set); when omitted it is the union
    of keys in first-seen order. Missing cells become ``None``.
    """
    if columns is None:
        ordered: list[str] = []
        for row in rows:
            for key in row:
                if key not in ordered:
                    ordered.append(key)
        columns = ordered
    data = {name: pa.array([row.get(name) for row in rows]) for name in columns}
    return dataframe_from_arrow(pa.table(data))


def dataframe_from_pandas(pdf: Any) -> DataFrame:
    """Build a core ``DataFrame`` from a pandas ``DataFrame``."""
    return dataframe_from_arrow(pa.Table.from_pandas(pdf, preserve_index=False))


def dataframe_arrow(frame: DataFrame) -> pa.Table:
    """Return the backing ``pyarrow.Table`` of a core ``DataFrame``."""
    payload = frame.to_memory() if frame.storage_ref is not None else frame._transient_data
    if payload is None:
        raise ValueError("DataFrame has no in-memory or persisted payload.")
    if isinstance(payload, pa.Table):
        return payload
    # pandas / dict fall-backs
    return pa.Table.from_pandas(payload, preserve_index=False) if hasattr(payload, "columns") else pa.table(payload)


def dataframe_pandas(frame: DataFrame) -> Any:
    """Return the backing payload of a core ``DataFrame`` as a pandas frame."""
    return dataframe_arrow(frame).to_pandas()


# ---------------------------------------------------------------------------
# Spectrum build / read / derive
# ---------------------------------------------------------------------------


def build_spectrum(
    lambda_values: Sequence[float] | np.ndarray,
    intensity_values: Sequence[float] | np.ndarray,
    *,
    meta: Spectrum.Meta | None = None,
    user: dict[str, Any] | None = None,
    framework: FrameworkMeta | None = None,
    source: str | None = None,
    spectrum_id: str | None = None,
) -> Spectrum:
    """Construct a fresh :class:`Spectrum` from lambda + intensity arrays.

    When ``meta`` carries no ``spectrum_id`` and ``spectrum_id`` is not given, a
    fresh id is generated (FR-035). ``lambda``/``intensity`` are stored as a
    two-column Arrow table.
    """
    lam = np.asarray(lambda_values, dtype=np.float64)
    inten = np.asarray(intensity_values, dtype=np.float64)
    if lam.shape != inten.shape:
        raise ValueError(f"lambda and intensity must have equal shape, got {lam.shape} vs {inten.shape}")
    if lam.ndim != 1:
        raise ValueError(f"Spectrum data must be 1-D, got shape {lam.shape}")

    resolved_meta = meta or Spectrum.Meta()
    if resolved_meta.spectrum_id is None:
        from scistudio.core.meta import with_meta_changes

        resolved_meta = cast(
            Spectrum.Meta, with_meta_changes(resolved_meta, spectrum_id=spectrum_id or new_spectrum_id())
        )

    table = arrow_table({LAMBDA_COLUMN: lam, INTENSITY_COLUMN: inten})
    return Spectrum(
        index_name=LAMBDA_COLUMN,
        value_name=INTENSITY_COLUMN,
        length=int(lam.shape[0]),
        data=table,
        meta=resolved_meta,
        user=dict(user) if user else None,
        framework=framework or FrameworkMeta(source=source or "scistudio-blocks-spectroscopy"),
    )


def spectrum_table(spectrum: Spectrum) -> pa.Table:
    """Return the backing two-column ``pyarrow.Table`` of a spectrum."""
    payload = spectrum.to_memory() if spectrum.storage_ref is not None else spectrum._transient_data
    if payload is None:
        raise ValueError("Spectrum has no in-memory or persisted payload.")
    if isinstance(payload, pa.Table):
        return payload
    raise TypeError(f"Spectrum payload must be a pyarrow.Table, got {type(payload).__name__}")


def spectrum_arrays(spectrum: Spectrum) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(lambda_values, intensity_values)`` as float64 numpy arrays."""
    table = spectrum_table(spectrum)
    index_name = spectrum.index_name or LAMBDA_COLUMN
    value_name = spectrum.value_name or INTENSITY_COLUMN
    lam = np.asarray(table.column(index_name).to_numpy(zero_copy_only=False), dtype=np.float64)
    inten = np.asarray(table.column(value_name).to_numpy(zero_copy_only=False), dtype=np.float64)
    return lam, inten


def derive_spectrum(
    source: Spectrum,
    *,
    lambda_values: Sequence[float] | np.ndarray | None = None,
    intensity_values: Sequence[float] | np.ndarray | None = None,
    meta: Spectrum.Meta | None = None,
    meta_changes: Mapping[str, Any] | None = None,
) -> Spectrum:
    """Derive a new :class:`Spectrum` from ``source``, preserving identity.

    Preserves ``spectrum_id`` and user metadata, derives a fresh framework
    (lineage), and lets callers replace lambda and/or intensity. When neither
    array is provided the source payload is reused.
    """
    src_lam, src_inten = spectrum_arrays(source)
    lam = np.asarray(lambda_values, dtype=np.float64) if lambda_values is not None else src_lam
    inten = np.asarray(intensity_values, dtype=np.float64) if intensity_values is not None else src_inten
    if lam.shape != inten.shape:
        raise ValueError(f"lambda and intensity must have equal shape, got {lam.shape} vs {inten.shape}")

    resolved_meta = meta if meta is not None else source.meta
    if resolved_meta is not None and meta_changes:
        from scistudio.core.meta import with_meta_changes

        resolved_meta = cast(Spectrum.Meta, with_meta_changes(resolved_meta, **dict(meta_changes)))

    table = arrow_table({LAMBDA_COLUMN: lam, INTENSITY_COLUMN: inten})
    return Spectrum(
        index_name=source.index_name or LAMBDA_COLUMN,
        value_name=source.value_name or INTENSITY_COLUMN,
        length=int(lam.shape[0]),
        data=table,
        meta=resolved_meta,
        user=dict(source.user) if source.user else None,
        framework=source.framework.derive(),
    )


# ---------------------------------------------------------------------------
# Collection helpers
# ---------------------------------------------------------------------------


def spectra_collection(spectra: Sequence[Spectrum]) -> Collection:
    """Wrap spectra in a ``Collection[Spectrum]`` (empty allowed via item_type)."""
    return Collection(items=cast(list[DataObject], list(spectra)), item_type=Spectrum)


def dataframe_collection(frame: DataFrame) -> Collection:
    """Wrap one ``DataFrame`` in a ``Collection[DataFrame]`` for an output port."""
    return Collection(items=cast(list[DataObject], [frame]), item_type=DataFrame)


def coerce_spectra(
    value: Any, *, block: str = "block", port: str = "spectra", allow_empty: bool = False
) -> list[Spectrum]:
    """Normalise a port value to a ``list[Spectrum]``.

    Accepts a bare :class:`Spectrum` or a ``Collection[Spectrum]``. Raises
    ``ValueError`` with a block-qualified message on a missing/empty/wrong input.
    """
    if value is None:
        raise ValueError(f"{block}: missing required '{port}' input")
    if isinstance(value, Spectrum):
        return [value]
    if isinstance(value, Collection):
        items = [cast(Spectrum, item) for item in value]
        if not items and not allow_empty:
            raise ValueError(f"{block}: '{port}' collection is empty")
        return items
    raise ValueError(f"{block}: '{port}' expected Spectrum or Collection[Spectrum], got {type(value).__name__}")


def coerce_single_spectrum(value: Any, *, block: str = "block", port: str = "reference") -> Spectrum:
    """Normalise a port value to exactly one :class:`Spectrum`."""
    items = coerce_spectra(value, block=block, port=port)
    if len(items) != 1:
        raise ValueError(f"{block}: '{port}' must be exactly one Spectrum, got {len(items)}")
    return items[0]


def coerce_dataset(value: Any, *, block: str = "block", port: str = "dataset") -> SpectralDataset:
    """Normalise a port value to one :class:`SpectralDataset`."""
    if value is None:
        raise ValueError(f"{block}: missing required '{port}' input")
    if isinstance(value, SpectralDataset):
        return value
    if isinstance(value, Collection):
        items = list(value)
        if len(items) == 1 and isinstance(items[0], SpectralDataset):
            return cast(SpectralDataset, items[0])
    raise ValueError(f"{block}: '{port}' expected SpectralDataset, got {type(value).__name__}")


def coerce_dataframe(value: Any, *, block: str = "block", port: str = "features") -> DataFrame:
    """Normalise a port value to one core ``DataFrame``."""
    if value is None:
        raise ValueError(f"{block}: missing required '{port}' input")
    if isinstance(value, DataFrame):
        return value
    if isinstance(value, Collection):
        items = list(value)
        if len(items) == 1 and isinstance(items[0], DataFrame):
            return cast(DataFrame, items[0])
    raise ValueError(f"{block}: '{port}' expected DataFrame, got {type(value).__name__}")


# ---------------------------------------------------------------------------
# SpectralDataset frames
# ---------------------------------------------------------------------------


def build_spectral_dataset(
    index: Any,
    spectra: Any,
    *,
    meta: SpectralDataset.Meta | None = None,
    framework: FrameworkMeta | None = None,
    source: str | None = None,
) -> SpectralDataset:
    """Construct a :class:`SpectralDataset` from ``index`` + ``spectra`` frames.

    Each of ``index`` / ``spectra`` may be a core ``DataFrame``, a pandas frame,
    or a ``pyarrow.Table``.
    """
    index_df = _as_dataframe(index)
    spectra_df = _as_dataframe(spectra)
    return SpectralDataset(
        slots={"index": index_df, "spectra": spectra_df},
        meta=meta or SpectralDataset.Meta(),
        framework=framework or FrameworkMeta(source=source or "scistudio-blocks-spectroscopy"),
    )


def dataset_frames(dataset: SpectralDataset) -> tuple[pa.Table, pa.Table]:
    """Return ``(index_table, spectra_table)`` as ``pyarrow.Table`` values."""
    dataset.validate_slots()
    return dataframe_arrow(cast(DataFrame, dataset.get("index"))), dataframe_arrow(
        cast(DataFrame, dataset.get("spectra"))
    )


def _as_dataframe(value: Any) -> DataFrame:
    if isinstance(value, DataFrame):
        return value
    if isinstance(value, pa.Table):
        return dataframe_from_arrow(value)
    if hasattr(value, "columns"):  # pandas
        return dataframe_from_pandas(value)
    raise TypeError(f"Cannot coerce {type(value).__name__} to a core DataFrame slot.")


# ---------------------------------------------------------------------------
# Grid utilities
# ---------------------------------------------------------------------------


def grids_close(a: np.ndarray, b: np.ndarray, *, rtol: float = 1e-5, atol: float = 1e-8) -> bool:
    """Return ``True`` when two lambda grids match within tolerance."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    return a.shape == b.shape and bool(np.allclose(a, b, rtol=rtol, atol=atol))


__all__ = [
    "arrow_table",
    "build_spectral_dataset",
    "build_spectrum",
    "coerce_dataframe",
    "coerce_dataset",
    "coerce_single_spectrum",
    "coerce_spectra",
    "dataframe_arrow",
    "dataframe_collection",
    "dataframe_from_arrow",
    "dataframe_from_pandas",
    "dataframe_from_rows",
    "dataframe_pandas",
    "dataset_frames",
    "derive_spectrum",
    "grids_close",
    "new_spectrum_id",
    "spectra_collection",
    "spectrum_arrays",
    "spectrum_table",
]
