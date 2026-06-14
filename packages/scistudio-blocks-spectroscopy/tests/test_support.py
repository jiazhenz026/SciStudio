"""Tests for the shared data-model helpers in ``_support``.

These cover the spectroscopy storage model (Spectrum as a two-column Arrow
table, identity-preserving derivation, DataFrame plumbing, dataset frames,
coercion, and grid comparison) that every block relies on.
"""

from __future__ import annotations

import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support as support
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame


def _gaussian(lam: np.ndarray, center: float, width: float) -> np.ndarray:
    return np.exp(-((lam - center) ** 2) / (2.0 * width**2))


def test_build_and_read_spectrum_roundtrip() -> None:
    lam = np.linspace(400.0, 1800.0, 64)
    inten = _gaussian(lam, 1000.0, 30.0)
    spec = support.build_spectrum(
        lam, inten, meta=Spectrum.Meta(lambda_unit="cm-1", intensity_unit="a.u.", lambda_kind="raman_shift")
    )
    assert isinstance(spec, Spectrum)
    assert spec.index_name == "lambda"
    assert spec.value_name == "intensity"
    assert spec.length == 64
    assert spec.spectrum_id  # generated when absent (FR-035)
    out_lam, out_inten = support.spectrum_arrays(spec)
    np.testing.assert_allclose(out_lam, lam)
    np.testing.assert_allclose(out_inten, inten)


def test_build_spectrum_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="equal shape"):
        support.build_spectrum([1.0, 2.0, 3.0], [1.0, 2.0])


def test_derive_spectrum_preserves_identity_and_lineage() -> None:
    lam = np.linspace(0.0, 10.0, 11)
    src = support.build_spectrum(lam, lam, spectrum_id="abc")
    derived = support.derive_spectrum(src, intensity_values=lam * 2.0)
    _, dy = support.spectrum_arrays(derived)
    np.testing.assert_allclose(dy, lam * 2.0)
    assert derived.spectrum_id == "abc"  # identity preserved
    assert derived.framework.derived_from == src.framework.object_id  # lineage


def test_dataframe_from_rows_is_flat_and_columnar() -> None:
    rows = [{"spectrum_id": "a", "auc": 1.5, "status": "ok"}, {"spectrum_id": "b", "auc": 2.0, "status": "ok"}]
    df = support.dataframe_from_rows(rows)
    assert isinstance(df, DataFrame)
    table = support.dataframe_arrow(df)
    assert table.column_names == ["spectrum_id", "auc", "status"]
    assert table.column("auc").to_pylist() == [1.5, 2.0]


def test_build_spectral_dataset_and_frames() -> None:
    import pandas as pd

    index = pd.DataFrame({"spectrum_id": ["a", "b"], "material": ["x", "y"]})
    spectra = pd.DataFrame({"spectrum_id": ["a", "a", "b"], "lambda": [1.0, 2.0, 1.0], "intensity": [10.0, 11.0, 12.0]})
    dataset = support.build_spectral_dataset(index, spectra, meta=SpectralDataset.Meta(dataset_role="library"))
    assert isinstance(dataset, SpectralDataset)
    assert set(dataset.slot_names) == {"index", "spectra"}
    index_tbl, spectra_tbl = support.dataset_frames(dataset)
    assert index_tbl.num_rows == 2
    assert spectra_tbl.num_rows == 3
    meta = dataset.meta
    assert isinstance(meta, SpectralDataset.Meta)
    assert meta.dataset_role == "library"


def test_coerce_spectra_accepts_single_and_collection() -> None:
    spec = support.build_spectrum([1.0, 2.0], [3.0, 4.0])
    assert support.coerce_spectra(spec, block="b") == [spec]
    coll = Collection(items=[spec], item_type=Spectrum)
    assert support.coerce_spectra(coll, block="b") == [spec]
    with pytest.raises(ValueError, match="missing required"):
        support.coerce_spectra(None, block="b")
    with pytest.raises(ValueError, match="empty"):
        support.coerce_spectra(Collection(items=[], item_type=Spectrum), block="b")


def test_grids_close() -> None:
    a = np.linspace(0.0, 1.0, 10)
    assert support.grids_close(a, a.copy())
    assert not support.grids_close(a, a + 1.0)
    assert not support.grids_close(a, a[:-1])


def test_new_spectrum_id_unique() -> None:
    ids = {support.new_spectrum_id() for _ in range(100)}
    assert len(ids) == 100
