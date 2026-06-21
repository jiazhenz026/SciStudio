"""Alpha IO load+save coverage matrix for spectroscopy types.

Covers the full ``load_ext x save_ext`` matrix for ``Spectrum`` and
``SpectralDataset`` over the in-scope formats (legacy ``.xls`` is out of
scope for alpha) plus a 10-item ``Spectrum`` collection round-trip via
``LoadSpectrum`` multi-path loading.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.utilities import (
    LoadSpectralDataset,
    LoadSpectrum,
    SaveSpectralDataset,
    SaveSpectrum,
)
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.blocks.base.config import BlockConfig

SPECTRUM_EXTS = [".csv", ".tsv", ".txt", ".xlsx", ".dx", ".jcamp", ".jdx", ".spectrum.json"]
DATASET_EXTS = [".json", ".xlsx"]


def _spectrum(i: int = 0) -> Spectrum:
    lam = np.linspace(400.0, 800.0, 32)
    inten = (np.cos(lam / 50.0) + 2.0) * (1.0 + 0.1 * i)
    meta = Spectrum.Meta(
        lambda_unit="nm",
        intensity_unit="a.u.",
        lambda_kind="wavelength",
        modality="uvvis",
        sample_label=f"sample{i}",
    )
    return _support.build_spectrum(lam, inten, meta=meta)


def _dataset(i: int = 0) -> SpectralDataset:
    ids = [f"spec_{i}_{k}" for k in range(3)]
    index_rows, spectra_rows = [], []
    for k, sid in enumerate(ids):
        lam = np.linspace(400.0 + k, 410.0 + k, 5)
        inten = np.arange(5, dtype=float) + k * 10.0 + i
        index_rows.append({"spectrum_id": sid, "material": f"mat{k}", "replicate": k})
        for x, y in zip(lam, inten, strict=True):
            spectra_rows.append({"spectrum_id": sid, "lambda": float(x), "intensity": float(y)})
    meta = SpectralDataset.Meta(
        dataset_name=f"DS{i}",
        dataset_role="experiment",
        lambda_unit="nm",
        intensity_unit="counts",
        modality="raman",
        schema_version="1",
    )
    return _support.build_spectral_dataset(
        _support.dataframe_from_rows(index_rows),
        _support.dataframe_from_rows(spectra_rows),
        meta=meta,
    )


def _save_spectrum(spec: Spectrum, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    SaveSpectrum().save(_support.spectra_collection([spec]), BlockConfig(params={"path": str(path)}))


def _load_spectrum_one(path: Path) -> Spectrum:
    return next(iter(LoadSpectrum().load(BlockConfig(params={"path": str(path)}))))


def _assert_table_values(loaded_tbl, src_tbl) -> None:
    """Compare two Arrow tables by column names AND values (numeric-tolerant)."""
    assert sorted(loaded_tbl.column_names) == sorted(src_tbl.column_names), (
        f"columns {loaded_tbl.column_names} != {src_tbl.column_names}"
    )
    for col in src_tbl.column_names:
        got = loaded_tbl.column(col).to_pylist()
        want = src_tbl.column(col).to_pylist()
        assert len(got) == len(want), f"column {col}: length {len(got)} != {len(want)}"
        non_null = [x for x in want if x is not None]
        if non_null and all(isinstance(x, (int, float)) for x in non_null):
            np.testing.assert_allclose(
                [float(x) for x in got],
                [float(x) for x in want],
                rtol=1e-6,
                atol=1e-9,
                err_msg=f"column {col!r} values differ",
            )
        else:
            assert got == want, f"column {col!r} values differ: {got} != {want}"


def _assert_dataset_equiv(src: SpectralDataset, reloaded: SpectralDataset) -> None:
    """Index + spectra tables AND typed Meta must survive the round-trip."""
    src_idx, src_spectra = _support.dataset_frames(src)
    got_idx, got_spectra = _support.dataset_frames(reloaded)
    _assert_table_values(got_idx, src_idx)
    _assert_table_values(got_spectra, src_spectra)
    for field in ("dataset_name", "dataset_role", "lambda_unit", "intensity_unit", "modality", "schema_version"):
        assert getattr(reloaded.meta, field) == getattr(src.meta, field), f"meta.{field} differs"


@pytest.mark.parametrize("save_ext", SPECTRUM_EXTS)
@pytest.mark.parametrize("load_ext", SPECTRUM_EXTS)
def test_spectrum_load_save_matrix(tmp_path: Path, load_ext: str, save_ext: str) -> None:
    src = _spectrum()
    _, src_inten = _support.spectrum_arrays(src)

    in_path = tmp_path / f"in{load_ext}"
    _save_spectrum(src, in_path)
    loaded = _load_spectrum_one(in_path)

    out_path = tmp_path / f"out{save_ext}"
    _save_spectrum(loaded, out_path)
    assert out_path.exists() and out_path.stat().st_size > 0

    reloaded = _load_spectrum_one(out_path)
    _, out_inten = _support.spectrum_arrays(reloaded)
    assert out_inten.shape == src_inten.shape
    np.testing.assert_allclose(out_inten, src_inten, rtol=1e-4, atol=1e-4)


@pytest.mark.parametrize("save_ext", DATASET_EXTS)
@pytest.mark.parametrize("load_ext", DATASET_EXTS)
def test_spectral_dataset_load_save_matrix(tmp_path: Path, load_ext: str, save_ext: str) -> None:
    src = _dataset()

    in_path = tmp_path / f"in{load_ext}"
    SaveSpectralDataset().save(src, BlockConfig(params={"path": str(in_path)}))
    loaded = LoadSpectralDataset().load(BlockConfig(params={"path": str(in_path)}))
    if hasattr(loaded, "items") and not isinstance(loaded, SpectralDataset):
        loaded = next(iter(loaded))

    out_path = tmp_path / f"out{save_ext}"
    SaveSpectralDataset().save(loaded, BlockConfig(params={"path": str(out_path)}))
    assert out_path.exists() and out_path.stat().st_size > 0

    reloaded = LoadSpectralDataset().load(BlockConfig(params={"path": str(out_path)}))
    if hasattr(reloaded, "items") and not isinstance(reloaded, SpectralDataset):
        reloaded = next(iter(reloaded))
    assert isinstance(reloaded, SpectralDataset)
    _assert_dataset_equiv(src, reloaded)


def test_spectrum_collection_roundtrip_10(tmp_path: Path) -> None:
    paths: list[str] = []
    for i in range(10):
        p = tmp_path / f"spec_{i:02d}.csv"
        _save_spectrum(_spectrum(i), p)
        paths.append(str(p))
    result = LoadSpectrum().load(BlockConfig(params={"path": paths}))
    items = list(result)
    assert len(items) == 10
    for item in items:
        assert isinstance(item, Spectrum)
