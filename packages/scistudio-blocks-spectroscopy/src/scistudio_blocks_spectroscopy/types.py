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


__all__ = [
    "INTENSITY_COLUMN",
    "LAMBDA_COLUMN",
    "SPECTRUM_ID_COLUMN",
    "SpectralDataset",
    "Spectrum",
    "get_types",
]
