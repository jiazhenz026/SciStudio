"""Test support for spectroscopy package slices before skeleton integration."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

import numpy as np
import pyarrow as pa

from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum  # noqa: E402


def install_type_shim() -> None:
    """Backward-compatible no-op after package skeleton integration."""

    return None


def make_spectrum(
    spectrum_id: str,
    lambdas: list[float] | np.ndarray,
    intensities: list[float] | np.ndarray,
    *,
    sample_label: str | None = None,
    user_extra: dict[str, Any] | None = None,
) -> Spectrum:
    lambda_values = np.asarray(lambdas, dtype=float)
    intensity_values = np.asarray(intensities, dtype=float)
    user = {"spectrum_id": spectrum_id}
    if user_extra:
        user.update(user_extra)
    return Spectrum(
        index_name="lambda",
        value_name="intensity",
        length=int(lambda_values.size),
        meta=Spectrum.Meta(spectrum_id=spectrum_id, sample_label=sample_label),
        user=user,
        data=pa.table({"lambda": lambda_values, "intensity": intensity_values}),
    )


def spectrum_collection(*spectra: Spectrum) -> Collection:
    return Collection(list(spectra), item_type=Spectrum)


def make_spectral_dataset() -> SpectralDataset:
    index = DataFrame(
        columns=["spectrum_id"],
        row_count=1,
        data=pa.table({"spectrum_id": ["s1"]}),
    )
    spectra = DataFrame(
        columns=["spectrum_id", "lambda", "intensity"],
        row_count=1,
        data=pa.table({"spectrum_id": ["s1"], "lambda": [1.0], "intensity": [2.0]}),
    )
    return SpectralDataset(slots={"index": index, "spectra": spectra})


def table_rows(collection: Collection) -> list[dict[str, Any]]:
    frame = collection[0]
    assert isinstance(frame, DataFrame)
    table = frame.get_in_memory_data()
    assert isinstance(table, pa.Table)
    return cast(list[dict[str, Any]], table.to_pylist())


def spectrum_xy(spectrum: Spectrum) -> tuple[np.ndarray, np.ndarray]:
    table = spectrum.get_in_memory_data()
    assert isinstance(table, pa.Table)
    return (
        np.asarray(table.column("lambda").to_pylist(), dtype=float),
        np.asarray(table.column("intensity").to_pylist(), dtype=float),
    )
