"""Spectroscopy plugin public data types.

This module defines the two package-owned ``DataObject`` subclasses that form
the stable type contract for ``scistudio-blocks-spectroscopy``:

- :class:`Spectrum` — one 1-D spectrum, a subclass of core ``Series`` (FR-003,
  FR-004, FR-005, FR-006). It has NO ``axes``/``shape``/``dtype`` (that is the
  ``Array`` surface, which Spectrum deliberately does NOT use). Build and read
  it through the helpers in :mod:`scistudio_blocks_spectroscopy._support`.
- :class:`SpectralDataset` — many spectra, a subclass of core ``CompositeData``
  (FR-007) with exactly two semantic slots ``index`` and ``spectra`` (FR-008).

Per the spec (Edge Cases) the canonical coordinate column name is ``lambda``
even though ``lambda`` cannot be used as a Python identifier; we therefore use
``"lambda"`` only as a string column / semantic name, never as a variable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

import pyarrow as pa
import pyarrow.types as pat
from pydantic import BaseModel, ConfigDict

from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series

#: Canonical semantic names for a :class:`Spectrum` (FR-004).
LAMBDA_COLUMN = "lambda"
INTENSITY_COLUMN = "intensity"
SPECTRUM_ID_COLUMN = "spectrum_id"


class Spectrum(Series):
    """A single 1-D spectrum: intensity versus a spectral coordinate.

    ``Spectrum`` subclasses core :class:`~scistudio.core.types.series.Series`
    (NOT ``Array``). Core ``Series`` has no class-level axis schema, so the
    semantic names are pinned through ``__init__`` defaults: ``index_name``
    defaults to ``"lambda"`` and ``value_name`` to ``"intensity"`` (FR-004).

    Use :func:`scistudio_blocks_spectroscopy._support.build_spectrum` /
    :func:`~scistudio_blocks_spectroscopy._support.spectrum_arrays` /
    :func:`~scistudio_blocks_spectroscopy._support.derive_spectrum` to
    construct and read spectra; do not touch ``_transient_data`` or
    ``storage_ref`` directly.
    """

    def __init__(
        self,
        *,
        index_name: str | None = LAMBDA_COLUMN,
        value_name: str | None = INTENSITY_COLUMN,
        length: int | None = None,
        data: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            index_name=index_name,
            value_name=value_name,
            length=length,
            data=data,
            **kwargs,
        )

    class Meta(BaseModel):
        """Per-spectrum typed metadata (FR-005, FR-006).

        Frozen so :meth:`Series.with_meta` immutable updates are sound.

        Required-to-exist fields (values may be ``None`` when unknown):
        ``lambda_unit``, ``intensity_unit`` (FR-005); ``lambda_kind`` and
        ``modality`` (FR-006). Remaining fields are optional descriptive
        metadata; arbitrary user metadata belongs in the ``user`` dict, not
        here.
        """

        model_config = ConfigDict(frozen=True)

        # FR-005 / FR-006 — fields that MUST exist (nullable when unknown).
        lambda_unit: str | None = None
        intensity_unit: str | None = None
        lambda_kind: str | None = None
        modality: str | None = None

        # Optional descriptive metadata.
        spectrum_id: str | None = None
        source_file: str | None = None
        instrument: str | None = None
        sample_label: str | None = None
        acquisition_date: datetime | None = None
        processing_history: str | None = None

    @property
    def spectrum_id(self) -> str | None:
        """Convenience accessor for the internal spectrum id (FR-035).

        Reads ``meta.spectrum_id`` when a typed ``Meta`` is present; returns
        ``None`` otherwise. The id is an internal unique key, never a filename.
        """
        meta = self._meta
        return getattr(meta, "spectrum_id", None) if meta is not None else None


class SpectralDataset(CompositeData):
    """A many-spectrum composite: an ``index`` table plus a ``spectra`` table.

    Subclasses core :class:`~scistudio.core.types.composite.CompositeData`
    (FR-007) and declares exactly two semantic slots (FR-008):

    - ``index`` (:class:`DataFrame`): one row per spectrum, required column
      ``spectrum_id`` plus arbitrary metadata columns (FR-009, FR-010).
    - ``spectra`` (:class:`DataFrame`): long-form points with columns
      ``spectrum_id``, ``lambda``, ``intensity`` (FR-011).

    A spectral library is represented as a ``SpectralDataset`` with the
    appropriate ``dataset_role`` (FR-014); there is no separate library type.
    """

    expected_slots: ClassVar[dict[str, type]] = {
        "index": DataFrame,
        "spectra": DataFrame,
    }

    def __init__(self, *, slots: dict[str, Any] | None = None, **kwargs: Any) -> None:
        """Construct and validate the canonical two-slot dataset layout.

        Core ``CompositeData`` validates only slot object types. The spectroscopy
        package contract also requires table schemas and the
        ``index.spectrum_id`` <-> ``spectra.spectrum_id`` join invariant.
        """
        slot_names = set(slots or {})
        expected = set(self.expected_slots)
        if slot_names != expected:
            missing = sorted(expected - slot_names)
            extra = sorted(slot_names - expected)
            details: list[str] = []
            if missing:
                details.append(f"missing required slot(s) {missing!r}")
            if extra:
                details.append(f"unexpected slot(s) {extra!r}")
            raise ValueError(f"SpectralDataset requires exactly slots {sorted(expected)!r}; " + "; ".join(details))
        super().__init__(slots=slots, **kwargs)
        self.validate_slots()

    def validate_slots(self) -> None:
        """Validate required columns, ids, numeric payload columns, and joins."""
        index = self.get("index")
        spectra = self.get("spectra")
        if not isinstance(index, DataFrame) or not isinstance(spectra, DataFrame):
            return
        validate_spectral_dataset_tables(_dataframe_arrow(index), _dataframe_arrow(spectra))

    class Meta(BaseModel):
        """Dataset-level typed metadata (FR-013).

        Frozen so :meth:`CompositeData.with_meta` immutable updates are sound.
        ``dataset_role`` lets experiment, reference, calibration, and library
        datasets share one type (FR-013, FR-014).
        """

        model_config = ConfigDict(frozen=True)

        dataset_name: str | None = None
        dataset_role: str | None = None
        lambda_unit: str | None = None
        intensity_unit: str | None = None
        modality: str | None = None
        schema_version: str | None = None

    @property
    def slots(self) -> dict[str, Any]:
        """Expose populated composite slots for downstream blocks and tests.

        Core :class:`CompositeData` keeps the slot store private; mirror the
        imaging ``Label.slots`` accessor so blocks and previewers can read
        populated slots without reaching into ``_slots`` directly.
        """
        return self._slots


def get_types() -> list[type]:
    """Return the package's exported ``DataObject`` types for ``scistudio.types``."""
    return [Spectrum, SpectralDataset]


def validate_spectral_dataset_tables(index_table: pa.Table, spectra_table: pa.Table) -> None:
    """Validate the canonical ``SpectralDataset`` table contract.

    Enforces SC-003 / FR-009..FR-012 at the type boundary:
    ``index.spectrum_id`` must be present, unique, non-null, and covered by the
    long-form spectra slot; ``spectra`` must carry non-null ``spectrum_id`` plus
    numeric ``lambda`` and ``intensity`` columns whose ids join back to index.
    """
    if SPECTRUM_ID_COLUMN not in index_table.column_names:
        raise ValueError(
            f"SpectralDataset index table must contain {SPECTRUM_ID_COLUMN!r}; got {list(index_table.column_names)}"
        )

    required_spectra = {SPECTRUM_ID_COLUMN, LAMBDA_COLUMN, INTENSITY_COLUMN}
    missing = required_spectra.difference(spectra_table.column_names)
    if missing:
        raise ValueError(
            f"SpectralDataset spectra table must contain {sorted(required_spectra)}; missing {sorted(missing)}"
        )

    for column in (LAMBDA_COLUMN, INTENSITY_COLUMN):
        field = spectra_table.schema.field(column)
        if not (pat.is_integer(field.type) or pat.is_floating(field.type)):
            raise ValueError(f"SpectralDataset spectra.{column} must be numeric, got {field.type}")

    index_ids = index_table.column(SPECTRUM_ID_COLUMN).to_pylist()
    spectra_ids = spectra_table.column(SPECTRUM_ID_COLUMN).to_pylist()
    if any(sid in (None, "") for sid in index_ids):
        raise ValueError("SpectralDataset index.spectrum_id must not contain null/empty values")
    if any(sid in (None, "") for sid in spectra_ids):
        raise ValueError("SpectralDataset spectra.spectrum_id must not contain null/empty values")

    duplicates = _duplicates(index_ids)
    if duplicates:
        raise ValueError(f"SpectralDataset index.spectrum_id must be unique; duplicates {duplicates!r}")

    index_id_set = set(index_ids)
    spectra_id_set = set(spectra_ids)
    orphans = sorted(str(sid) for sid in (spectra_id_set - index_id_set))
    if orphans:
        raise ValueError(f"SpectralDataset spectra rows reference unknown spectrum_id(s) {orphans!r}")
    missing_coverage = sorted(str(sid) for sid in (index_id_set - spectra_id_set))
    if missing_coverage:
        raise ValueError(f"SpectralDataset index row(s) have no spectra coverage {missing_coverage!r}")


def _dataframe_arrow(frame: DataFrame) -> pa.Table:
    payload = frame.to_memory() if frame.storage_ref is not None else frame._transient_data
    if payload is None:
        raise ValueError("SpectralDataset DataFrame slot has no in-memory or persisted payload")
    if isinstance(payload, pa.Table):
        return payload
    if hasattr(payload, "columns"):
        return pa.Table.from_pandas(payload, preserve_index=False)
    return pa.table(payload)


def _duplicates(values: list[Any]) -> list[str]:
    seen: set[Any] = set()
    out: list[str] = []
    for value in values:
        if value in seen and str(value) not in out:
            out.append(str(value))
        seen.add(value)
    return out


__all__ = [
    "INTENSITY_COLUMN",
    "LAMBDA_COLUMN",
    "SPECTRUM_ID_COLUMN",
    "SpectralDataset",
    "Spectrum",
    "get_types",
    "validate_spectral_dataset_tables",
]
