"""Smoke tests for the SpectralDataset IO track (io-dataset).

Covers the two package-owned, round-trippable ``SpectralDataset`` formats wired
through :class:`LoadSpectralDataset` / :class:`SaveSpectralDataset` and the
handlers in :mod:`scistudio_blocks_spectroscopy.blocks.io_handlers.dataset_formats`:

- ``manifest_json`` (``.json``) — lossless (FR-135, FR-141): index rows, the
  long-form spectra table, the spectrum_id join, and all dataset ``Meta`` fields
  survive a save -> load cycle.
- ``xlsx`` (``.xlsx``) — typed-meta three-sheet workbook round-trip (FR-137).

Plus the canonical two-table layout (FR-038/FR-039), the FR-136 archive (.zip)
rejection, and the load-only vendor / SPC deferrals (FR-139/FR-140, FR-138).
"""

from __future__ import annotations

from collections.abc import Callable
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
from scistudio.testing import BlockTestHarness

_IDS = ("spec_a", "spec_b", "spec_c")


def _config(**params: Any) -> BlockConfig:
    """Build a ``BlockConfig`` carrying the given params (``config.get`` reads them)."""
    return BlockConfig(params=dict(params))


def _synthetic_dataset() -> tuple[SpectralDataset, int, int]:
    """Build a 3-spectrum dataset with index metadata + long-form spectra."""
    index_rows = []
    spectra_rows = []
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

    # Canonical two-table layout: required columns present (FR-038/FR-039).
    assert "spectrum_id" in index_table.column_names
    assert {"spectrum_id", "lambda", "intensity"}.issubset(spectra_table.column_names)

    # Row counts preserved.
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


def test_blocks_validate() -> None:
    """Both IO blocks pass the harness contract validation."""
    assert not BlockTestHarness(LoadSpectralDataset).validate_block()
    assert not BlockTestHarness(SaveSpectralDataset).validate_block()


def test_manifest_json_lossless_roundtrip(tmp_path: Path) -> None:
    """manifest_json: save -> load preserves tables, join, and all Meta (FR-141)."""
    dataset, n_index, n_spectra = _synthetic_dataset()
    out = tmp_path / "sample.json"

    SaveSpectralDataset().save(dataset, _config(path=str(out)))
    assert out.exists()
    # Sidecar Parquet slot files are written next to the manifest.
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
    """xlsx three-sheet workbook: save -> load round-trip (FR-137)."""
    pytest.importorskip("openpyxl")
    dataset, n_index, n_spectra = _synthetic_dataset()
    out = tmp_path / "sample.xlsx"

    SaveSpectralDataset().save(dataset, _config(path=str(out)))
    assert out.exists()

    loaded = LoadSpectralDataset().load(_config(path=str(out)))
    assert isinstance(loaded, SpectralDataset)
    _assert_roundtrip(loaded, n_index, n_spectra)


def test_explicit_capability_id_selection(tmp_path: Path) -> None:
    """ADR-043: an explicit capability_id selects the saver (FR-143)."""
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
    """FR-136: no archive (.zip) save capability is declared."""
    dataset, _, _ = _synthetic_dataset()
    with pytest.raises(ValueError, match="unsupported extension"):
        SaveSpectralDataset().save(dataset, _config(path=str(tmp_path / "out.zip")))


def test_load_rejects_unsupported_extension(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported extension"):
        LoadSpectralDataset().load(_config(path=str(tmp_path / "x.foo")))


def test_manifest_json_rejects_orphan_spectra(tmp_path: Path) -> None:
    """FR-012: spectra rows must join to index.spectrum_id."""
    index = _support.dataframe_from_rows([{"spectrum_id": "a"}])
    orphan = _support.dataframe_from_rows([{"spectrum_id": "ghost", "lambda": 1.0, "intensity": 2.0}])
    bad = _support.build_spectral_dataset(index, orphan, meta=SpectralDataset.Meta())
    with pytest.raises(ValueError, match="unknown spectrum_id"):
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
def test_load_only_handlers_are_deferred(handler: Callable[[Path], Any]) -> None:
    """SPC + vendor multi-spectrum loaders are tracked NotImplementedError (FR-138/FR-139)."""
    with pytest.raises(NotImplementedError):
        handler(Path("nonexistent.bin"))


def test_spc_dataset_save_is_deferred(tmp_path: Path) -> None:
    dataset, _, _ = _synthetic_dataset()
    with pytest.raises(NotImplementedError):
        dataset_formats.save_spc_dataset(dataset, tmp_path / "out.spc")
