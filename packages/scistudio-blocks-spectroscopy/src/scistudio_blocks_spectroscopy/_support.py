"""Internal support helpers for the spectroscopy package.

This module is the single approved seam for constructing and reading
:class:`~scistudio_blocks_spectroscopy.types.Spectrum` and for wrapping
``DataFrame``/``Spectrum`` payloads into ``Collection`` outputs. Block code
MUST go through these helpers instead of touching ``_transient_data`` /
``storage_ref`` / Arrow tables directly, so that the in-memory payload
convention stays in exactly one place.

``Spectrum`` is a ``Series`` subtype, so its numeric payload is a 2-column
Arrow table (``lambda``, ``intensity``) carried via the ``data=`` constructor
parameter (ADR-031 Addendum 2). The reader prefers the in-memory transient
payload and otherwise materialises from storage.

numpy and pyarrow are safe to import at module top level (they are package
dependencies). scipy and other heavy libraries are NOT imported here; block
bodies lazy-import them inside methods.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pyarrow as pa

from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy.types import (
    INTENSITY_COLUMN,
    LAMBDA_COLUMN,
    Spectrum,
)

if TYPE_CHECKING:
    from pydantic import BaseModel


def _as_arrow_table(obj: Any) -> pa.Table | None:
    """Return the in-memory Arrow table for *obj*, or ``None`` if absent."""
    payload = getattr(obj, "_transient_data", None)
    if isinstance(payload, pa.Table):
        return payload
    return None


def build_spectrum(
    lam: Any,
    inten: Any,
    *,
    meta: BaseModel | None = None,
    user: dict[str, Any] | None = None,
    framework: Any | None = None,
) -> Spectrum:
    """Build a :class:`Spectrum` from coordinate and intensity arrays.

    The two arrays are stored as a 2-column in-memory Arrow table named
    ``("lambda", "intensity")`` via the ``Series`` ``data=`` parameter. The
    returned spectrum is reference-free (``storage_ref is None``); the block
    runtime auto-flushes it to storage when it crosses a port boundary.

    Args:
        lam: 1-D array-like of spectral coordinates (the ``lambda`` axis).
        inten: 1-D array-like of intensities, same length as *lam*.
        meta: Optional :class:`Spectrum.Meta` instance.
        user: Optional free-form user-metadata dict (JSON-serialisable).
        framework: Optional ``FrameworkMeta`` (e.g. ``source.framework.derive()``);
            when ``None`` a fresh one is generated.

    Returns:
        A new :class:`Spectrum`.

    Raises:
        ValueError: if *lam* and *inten* have mismatched lengths.
    """
    lam_arr = np.asarray(lam, dtype=np.float64).reshape(-1)
    inten_arr = np.asarray(inten, dtype=np.float64).reshape(-1)
    if lam_arr.shape[0] != inten_arr.shape[0]:
        raise ValueError(
            f"build_spectrum: lambda/intensity length mismatch ({lam_arr.shape[0]} != {inten_arr.shape[0]})"
        )
    table = pa.table(
        {
            LAMBDA_COLUMN: pa.array(lam_arr),
            INTENSITY_COLUMN: pa.array(inten_arr),
        }
    )
    kwargs: dict[str, Any] = {
        "index_name": LAMBDA_COLUMN,
        "value_name": INTENSITY_COLUMN,
        "length": int(lam_arr.shape[0]),
        "data": table,
    }
    if meta is not None:
        kwargs["meta"] = meta
    if user is not None:
        kwargs["user"] = user
    if framework is not None:
        kwargs["framework"] = framework
    return Spectrum(**kwargs)


def spectrum_arrays(spec: Spectrum) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(lambda, intensity)`` numpy arrays for *spec*.

    Prefers the in-memory transient Arrow payload; otherwise materialises the
    backing table from storage via ``to_memory()``. The first two columns are
    interpreted as ``lambda`` and ``intensity`` respectively (by name when
    present, else by position).

    Args:
        spec: The spectrum to read.

    Returns:
        A ``(lambda_values, intensity_values)`` tuple of float64 arrays.

    Raises:
        ValueError: if no payload is available (neither transient nor stored).
    """
    table = _as_arrow_table(spec)
    if table is None:
        materialised = spec.to_memory()
        table = materialised if isinstance(materialised, pa.Table) else pa.table(materialised)
    if table is None:  # pragma: no cover - defensive
        raise ValueError("spectrum_arrays: spectrum has no readable payload")

    names = list(table.column_names)
    lam_name = LAMBDA_COLUMN if LAMBDA_COLUMN in names else names[0]
    inten_name = INTENSITY_COLUMN if INTENSITY_COLUMN in names else names[1]
    lam = np.asarray(table.column(lam_name).to_numpy(zero_copy_only=False), dtype=np.float64)
    inten = np.asarray(table.column(inten_name).to_numpy(zero_copy_only=False), dtype=np.float64)
    return lam, inten


def derive_spectrum(
    src: Spectrum,
    *,
    intensity_values: Any | None = None,
    lambda_values: Any | None = None,
    meta: BaseModel | None = None,
) -> Spectrum:
    """Derive a new :class:`Spectrum` from *src*, preserving identity metadata.

    Copies the source ``lambda`` grid and intensities by default, overriding
    either when ``lambda_values`` / ``intensity_values`` are supplied. The
    derived spectrum carries a lineage-derived framework, the source ``user``
    dict (shallow-copied), and either the supplied ``meta`` or the source
    ``meta``. This is the canonical way preprocessing/fitting blocks emit a
    transformed spectrum that keeps the same ``spectrum_id`` and metadata.

    Args:
        src: The source spectrum.
        intensity_values: Optional replacement intensity array (same length as
            the lambda grid in use).
        lambda_values: Optional replacement coordinate array.
        meta: Optional replacement :class:`Spectrum.Meta`; defaults to
            ``src.meta``.

    Returns:
        A new :class:`Spectrum`.
    """
    src_lam, src_inten = spectrum_arrays(src)
    lam = np.asarray(lambda_values, dtype=np.float64).reshape(-1) if lambda_values is not None else src_lam
    inten = np.asarray(intensity_values, dtype=np.float64).reshape(-1) if intensity_values is not None else src_inten
    derived_framework = src.framework.derive(derived_from=src.framework.object_id)
    return build_spectrum(
        lam,
        inten,
        meta=meta if meta is not None else src.meta,
        user=dict(src.user),
        framework=derived_framework,
    )


def spectra_collection(spectra: list[Spectrum]) -> Collection:
    """Wrap a list of spectra into a ``Collection[Spectrum]`` output.

    Empty lists are allowed and produce an explicitly typed empty collection
    (required by ``Collection`` for the empty case).

    Args:
        spectra: The spectra to wrap (may be empty).

    Returns:
        A ``Collection`` whose ``item_type`` is :class:`Spectrum`.
    """
    if not spectra:
        return Collection([], item_type=Spectrum)
    return Collection(items=list(spectra), item_type=Spectrum)


def dataframe_from_rows(rows: list[dict[str, Any]], *, columns: list[str] | None = None) -> DataFrame:
    """Build a core :class:`DataFrame` from a list of row dicts.

    Stores the rows as an in-memory Arrow table (carried via ``data=``); the
    block runtime persists it on the way out. Column order follows *columns*
    when given, else the union of keys in first-seen order.

    Args:
        rows: List of ``column -> value`` row dicts (may be empty).
        columns: Optional explicit column ordering.

    Returns:
        A core :class:`DataFrame` wrapping the rows.
    """
    if columns is None:
        ordered: list[str] = []
        for row in rows:
            for key in row:
                if key not in ordered:
                    ordered.append(key)
        columns = ordered
    table = pa.table({name: pa.array([row.get(name) for row in rows]) for name in columns}) if columns else pa.table({})
    return DataFrame(
        columns=list(table.column_names),
        row_count=table.num_rows,
        data=table,
    )


def dataframe_collection(df: DataFrame) -> Collection:
    """Wrap a single :class:`DataFrame` into a ``Collection[DataFrame]`` output.

    Multi-output blocks declare ``DataFrame`` output ports and must return a
    ``Collection`` for every port; this is the canonical single-table wrapper.

    Args:
        df: The table to wrap.

    Returns:
        A ``Collection`` whose ``item_type`` is :class:`DataFrame`.
    """
    return Collection(items=[df], item_type=DataFrame)


__all__ = [
    "build_spectrum",
    "dataframe_collection",
    "dataframe_from_rows",
    "derive_spectrum",
    "spectra_collection",
    "spectrum_arrays",
]
