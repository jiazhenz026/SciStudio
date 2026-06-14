"""SpectralDataset IO contract tests (SC-053, SC-054, FR-141).

Binds the dataset IO contract for ``LoadSpectralDataset`` / ``SaveSpectralDataset``:

- the native JSON format is a package-owned manifest plus sidecar ``index`` and
  ``spectra`` table slots, and the manifest round-trip is lossless: both tables,
  the spectrum_id join, and every dataset ``Meta`` field survive (SC-053/FR-141);
- xlsx is a typed-meta three-sheet workbook round-trip (FR-137);
- no ``.zip``/``.spectraldataset.zip`` save capability is declared (SC-054);
- SPC + vendor multi-spectrum loaders are tracked ``NotImplementedError``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.io_handlers import dataset_formats
from scistudio_blocks_spectroscopy.blocks.utilities import (
    LoadSpectralDataset,
    SaveSpectralDataset,
)
from scistudio_blocks_spectroscopy.types import SpectralDataset

from scistudio.blocks.base.config import BlockConfig

_IDS = ("spec_a", "spec_b", "spec_c")


def _config(**params: Any) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _synthetic_dataset() -> tuple[SpectralDataset, int, int]:
    index_rows: list[dict[str, Any]] = []
    spectra_rows: list[dict[str, Any]] = []
    for i, sid in enumerate(_IDS):
        lam = np.linspace(400.0 + i, 410.0 + i, 5)
        inten = np.arange(5, dtype=float) + i * 10.0
        index_rows.append({"spectrum_id": sid, "material": f"mat{i}", "replicate": i})
        for x, y in zip(lam, inten, strict=True):
            spectra_rows.append({"spectrum_id": sid, "lambda": float(x), "intensity": float(y)})
    meta = SpectralDataset.Meta(
        dataset_name="DS",
        dataset_role="experiment",
        lambda_unit="nm",
        intensity_unit="counts",
        modality="raman",
        schema_version="1",
    )
    dataset = _support.build_spectral_dataset(
        _support.dataframe_from_rows(index_rows),
        _support.dataframe_from_rows(spectra_rows),
        meta=meta,
    )
    return dataset, len(index_rows), len(spectra_rows)


def _assert_roundtrip(loaded: SpectralDataset, n_index: int, n_spectra: int) -> None:
    index_table, spectra_table = _support.dataset_frames(loaded)
    # Canonical two-table layout (FR-038/FR-039).
    assert "spectrum_id" in index_table.column_names
    assert {"spectrum_id", "lambda", "intensity"}.issubset(spectra_table.column_names)
    assert index_table.num_rows == n_index
    assert spectra_table.num_rows == n_spectra
    # spectrum_id join preserved across both slots.
    assert set(index_table.column("spectrum_id").to_pylist()) == set(_IDS)
    assert set(spectra_table.column("spectrum_id").to_pylist()) == set(_IDS)
    # Dataset Meta preserved.
    meta = loaded.meta
    assert isinstance(meta, SpectralDataset.Meta)
    assert meta.dataset_name == "DS"
    assert meta.dataset_role == "experiment"
    assert meta.lambda_unit == "nm"
    assert meta.intensity_unit == "counts"
    assert meta.modality == "raman"
    assert meta.schema_version == "1"


def test_manifest_json_lossless_roundtrip(tmp_path: Path) -> None:
    """SC-053 / FR-141: manifest + sidecar slots, lossless save -> load."""
    dataset, n_index, n_spectra = _synthetic_dataset()
    out = tmp_path / "sample.json"
    SaveSpectralDataset().save(dataset, _config(path=str(out)))
    assert out.exists()
    # SC-053: native JSON is a manifest + sidecar index/spectra slot tables.
    assert (tmp_path / "sample.index.parquet").exists()
    assert (tmp_path / "sample.spectra.parquet").exists()

    loaded = LoadSpectralDataset().load(_config(path=str(out)))
    assert isinstance(loaded, SpectralDataset)
    _assert_roundtrip(loaded, n_index, n_spectra)

    # Lossless numeric payload: intensities preserved exactly.
    _, spectra_table = _support.dataset_frames(loaded)
    _, orig_spectra = _support.dataset_frames(dataset)
    assert sorted(spectra_table.column("intensity").to_pylist()) == sorted(orig_spectra.column("intensity").to_pylist())


def test_dataset_xlsx_roundtrip(tmp_path: Path) -> None:
    """FR-137: xlsx three-sheet (index/spectra/meta) workbook round-trip."""
    pytest.importorskip("openpyxl")
    dataset, n_index, n_spectra = _synthetic_dataset()
    out = tmp_path / "sample.xlsx"
    SaveSpectralDataset().save(dataset, _config(path=str(out)))
    assert out.exists()
    loaded = LoadSpectralDataset().load(_config(path=str(out)))
    assert isinstance(loaded, SpectralDataset)
    _assert_roundtrip(loaded, n_index, n_spectra)


def test_explicit_capability_id_selects_saver(tmp_path: Path) -> None:
    """SC-049: an explicit manifest capability_id forces the manifest saver."""
    dataset, _, _ = _synthetic_dataset()
    out = tmp_path / "explicit.json"
    SaveSpectralDataset().save(
        dataset,
        _config(
            path=str(out),
            capability_id="scistudio-blocks-spectroscopy.spectral_dataset.manifest_json.save",
        ),
    )
    assert out.exists()


def test_save_rejects_zip_bundle(tmp_path: Path) -> None:
    """SC-054: no archive (.zip) save capability is declared."""
    dataset, _, _ = _synthetic_dataset()
    with pytest.raises(ValueError):
        SaveSpectralDataset().save(dataset, _config(path=str(tmp_path / "out.zip")))


def test_load_rejects_unsupported_extension(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        LoadSpectralDataset().load(_config(path=str(tmp_path / "x.foo")))


def test_manifest_rejects_orphan_spectra(tmp_path: Path) -> None:
    """FR-012: spectra rows must join to an index spectrum_id."""
    index = _support.dataframe_from_rows([{"spectrum_id": "a"}])
    orphan = _support.dataframe_from_rows([{"spectrum_id": "ghost", "lambda": 1.0, "intensity": 2.0}])
    bad = _support.build_spectral_dataset(index, orphan, meta=SpectralDataset.Meta())
    with pytest.raises(ValueError):
        dataset_formats.save_manifest_json(bad, tmp_path / "bad.json")


@pytest.mark.parametrize(
    "handler",
    [
        dataset_formats.load_spc_dataset,
        dataset_formats.load_thermo_omnic_spg,
        dataset_formats.load_renishaw_wdf_dataset,
        dataset_formats.load_bruker_opus_dataset,
        dataset_formats.load_horiba_labspec_dataset,
        dataset_formats.load_witec_project,
        dataset_formats.load_andor_solis_dataset,
        dataset_formats.load_princeton_spe_dataset,
    ],
)
def test_vendor_dataset_loaders_are_deferred(handler: Any) -> None:
    with pytest.raises(NotImplementedError):
        handler(Path("nonexistent.bin"))


def test_spc_dataset_save_is_deferred(tmp_path: Path) -> None:
    dataset, _, _ = _synthetic_dataset()
    with pytest.raises(NotImplementedError):
        dataset_formats.save_spc_dataset(dataset, tmp_path / "out.spc")
