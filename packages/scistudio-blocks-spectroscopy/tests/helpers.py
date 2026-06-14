from __future__ import annotations

from typing import Any

import pandas as pd
import pyarrow as pa
from scistudio_blocks_spectroscopy._tables import dataframe_from_pandas
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame


def make_spectrum(
    spectrum_id: str = "s1",
    *,
    lambda_unit: str | None = "cm^-1",
    intensity_unit: str | None = "counts",
    material: str | None = None,
) -> Spectrum:
    frame = pd.DataFrame({"lambda": [100.0, 101.0, 102.0], "intensity": [10.0, 12.0, 11.0]})
    user = {"spectrum_id": spectrum_id}
    if material is not None:
        user["material"] = material
    return Spectrum(
        length=len(frame),
        meta=Spectrum.Meta(lambda_unit=lambda_unit, intensity_unit=intensity_unit, modality="raman"),
        user=user,
        data=pa.Table.from_pandas(frame, preserve_index=False),
    )


def make_dataset(
    *,
    ids: tuple[str, ...] = ("s1", "s2"),
    materials: tuple[str, ...] = ("cell", "buffer"),
    dataset_name: str = "dataset",
) -> SpectralDataset:
    index = pd.DataFrame(
        {
            "spectrum_id": list(ids),
            "material": list(materials),
            "lambda_unit": ["cm^-1"] * len(ids),
            "intensity_unit": ["counts"] * len(ids),
            "modality": ["raman"] * len(ids),
        }
    )
    spectra_rows = []
    for ordinal, spectrum_id in enumerate(ids):
        for value in (100.0, 101.0):
            spectra_rows.append({"spectrum_id": spectrum_id, "lambda": value, "intensity": value + ordinal})
    spectra = pd.DataFrame(spectra_rows)
    return SpectralDataset(
        slots={
            "index": dataframe_from_pandas(index),
            "spectra": dataframe_from_pandas(spectra),
        },
        meta=SpectralDataset.Meta(
            dataset_name=dataset_name,
            lambda_unit="cm^-1",
            intensity_unit="counts",
            modality="raman",
        ),
    )


def dataframe_collection(frame: pd.DataFrame) -> Collection:
    table: DataFrame = dataframe_from_pandas(frame)
    return Collection(items=[table], item_type=DataFrame)


def spectrum_frame(spectrum: Spectrum) -> pd.DataFrame:
    data: Any = spectrum.get_in_memory_data()
    if isinstance(data, pa.Table):
        return data.to_pandas()
    if isinstance(data, pd.DataFrame):
        return data.copy()
    return pd.DataFrame(data)


def spectrum_meta(spectrum: Spectrum) -> Spectrum.Meta:
    assert isinstance(spectrum.meta, Spectrum.Meta)
    return spectrum.meta


def dataset_meta(dataset: SpectralDataset) -> SpectralDataset.Meta:
    assert isinstance(dataset.meta, SpectralDataset.Meta)
    return dataset.meta
