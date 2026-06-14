"""Public spectroscopy data types."""

from __future__ import annotations

from typing import Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict

from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio_blocks_spectroscopy._tables import table_columns, to_pandas_frame


class Spectrum(Series):
    """One ordinary 1-D spectrum with canonical lambda/intensity semantics."""

    class Meta(BaseModel):
        """Typed per-spectrum metadata shared across spectroscopy modalities."""

        model_config = ConfigDict(frozen=True)

        spectrum_id: str | None = None
        sample_label: str | None = None
        lambda_unit: str | None = None
        intensity_unit: str | None = None
        lambda_kind: str | None = None
        modality: str | None = None
        source_file: str | None = None

    def __init__(
        self,
        *,
        index_name: str | None = "lambda",
        value_name: str | None = "intensity",
        length: int | None = None,
        meta: BaseModel | None = None,
        **kwargs: Any,
    ) -> None:
        if index_name not in (None, "lambda"):
            raise ValueError("Spectrum uses canonical index_name='lambda'")
        if value_name not in (None, "intensity"):
            raise ValueError("Spectrum uses canonical value_name='intensity'")
        super().__init__(
            index_name="lambda",
            value_name="intensity",
            length=length,
            meta=meta if meta is not None else Spectrum.Meta(),
            **kwargs,
        )


class SpectralDataset(CompositeData):
    """Many spectra plus per-spectrum metadata in two table slots."""

    expected_slots: ClassVar[dict[str, type]] = {
        "index": DataFrame,
        "spectra": DataFrame,
    }

    class Meta(BaseModel):
        """Dataset-level defaults and role metadata."""

        model_config = ConfigDict(frozen=True)

        dataset_name: str | None = None
        dataset_role: str = "experiment"
        lambda_unit: str | None = None
        intensity_unit: str | None = None
        modality: str | None = None
        schema_version: str = "1"

    def __init__(self, *, slots: dict[str, Any] | None = None, meta: BaseModel | None = None, **kwargs: Any) -> None:
        if slots is None:
            raise ValueError("SpectralDataset requires 'index' and 'spectra' slots")
        unknown = set(slots) - set(self.expected_slots)
        if unknown:
            raise ValueError(f"SpectralDataset does not accept slots: {sorted(unknown)}")
        missing = set(self.expected_slots) - set(slots)
        if missing:
            raise ValueError(f"SpectralDataset requires slots: {sorted(missing)}")
        super().__init__(slots=slots, meta=meta if meta is not None else SpectralDataset.Meta(), **kwargs)
        self._validate_required_tables()

    @property
    def index(self) -> DataFrame:
        """Return the per-spectrum index table slot."""

        return self.get("index")  # type: ignore[return-value]

    @property
    def spectra(self) -> DataFrame:
        """Return the long-form spectra table slot."""

        return self.get("spectra")  # type: ignore[return-value]

    @property
    def slots(self) -> dict[str, DataFrame]:
        """Expose populated composite slots for package tests and utilities."""

        return cast(dict[str, DataFrame], dict(self._slots))

    def _validate_required_tables(self) -> None:
        index_columns = set(table_columns(self.index))
        spectra_columns = set(table_columns(self.spectra))
        if "spectrum_id" not in index_columns:
            raise ValueError("SpectralDataset.index requires a 'spectrum_id' column")
        required_spectra = {"spectrum_id", "lambda", "intensity"}
        missing_spectra = required_spectra - spectra_columns
        if missing_spectra:
            raise ValueError(f"SpectralDataset.spectra missing required columns: {sorted(missing_spectra)}")

        try:
            index_frame = to_pandas_frame(self.index)
        except ValueError:
            return
        if "spectrum_id" in index_frame.columns and index_frame["spectrum_id"].duplicated().any():
            raise ValueError("SpectralDataset.index spectrum_id values must be unique")


__all__ = ["SpectralDataset", "Spectrum"]
