"""End-to-end IO tests for the 4 IO blocks (US5, FR-034..FR-039, FR-132..FR-143).

Drives full save -> load round-trips on disk through the real LoadSpectrum /
SaveSpectrum / LoadSpectralDataset / SaveSpectralDataset blocks (writing to
tmp_path) and asserts numeric + metadata fidelity, id generation/preservation,
batch numbering, capability_id selection, and vendor/SPC deferrals.
"""

from __future__ import annotations

from pathlib import Path

import fixtures as fx
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
from scistudio.core.types.collection import Collection
from scistudio.testing import BlockTestHarness


def _cfg(**params: object) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _load_collection(block: LoadSpectrum, config: BlockConfig) -> Collection:
    result = block.load(config)
    assert isinstance(result, Collection)
    return result


@pytest.mark.parametrize("block_cls", [LoadSpectrum, SaveSpectrum, LoadSpectralDataset, SaveSpectralDataset])
def test_block_validates(block_cls: type) -> None:
    assert not BlockTestHarness(block_cls).validate_block()


# ---------------------------------------------------------------------------
# Spectrum IO round-trips (LOAD -> assert -> SAVE -> LOAD)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ext", [".txt", ".csv", ".tsv", ".spectrum.json"])
def test_spectrum_save_load_numeric_roundtrip(tmp_path: Path, ext: str) -> None:
    spec, _ = fx.make_peak_spectrum(spectrum_id="io1", peaks=(fx.PeakSpec("gaussian", 5.0, 500.0, 8.0),))
    lam, inten = _support.spectrum_arrays(spec)
    out = tmp_path / f"spec{ext}"
    SaveSpectrum().save(Collection([spec], item_type=Spectrum), _cfg(path=str(out)))
    assert out.exists()
    loaded = _load_collection(LoadSpectrum(), _cfg(path=str(out)))
    assert len(loaded) == 1
    glam, ginten = _support.spectrum_arrays(loaded[0])
    assert np.allclose(glam, lam, rtol=1e-6, atol=1e-6)
    assert np.allclose(ginten, inten, rtol=1e-6, atol=1e-6)


def test_spectrum_json_lossless_id_and_meta(tmp_path: Path) -> None:
    spec, _ = fx.make_peak_spectrum(spectrum_id="lossless1")
    out = tmp_path / "spec.spectrum.json"
    SaveSpectrum().save(Collection([spec], item_type=Spectrum), _cfg(path=str(out)))
    loaded = _load_collection(LoadSpectrum(), _cfg(path=str(out)))[0]
    # Native JSON is lossless: spectrum_id + typed meta survive (FR-141).
    assert loaded.spectrum_id == "lossless1"
    assert isinstance(loaded.meta, Spectrum.Meta)
    assert loaded.meta.lambda_unit == "nm"


def test_spectrum_xlsx_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    spec, _ = fx.make_peak_spectrum(spectrum_id="xl1")
    lam, inten = _support.spectrum_arrays(spec)
    out = tmp_path / "spec.xlsx"
    SaveSpectrum().save(Collection([spec], item_type=Spectrum), _cfg(path=str(out)))
    loaded = _load_collection(LoadSpectrum(), _cfg(path=str(out)))[0]
    glam, ginten = _support.spectrum_arrays(loaded)
    assert np.allclose(glam, lam, rtol=1e-6, atol=1e-6)
    assert np.allclose(ginten, inten, rtol=1e-6, atol=1e-6)
    assert isinstance(loaded.meta, Spectrum.Meta) and loaded.meta.lambda_unit == "nm"


def test_load_generates_fresh_id_keeps_source_file(tmp_path: Path) -> None:
    spec, _ = fx.make_peak_spectrum(spectrum_id="src_id")
    out = tmp_path / "single.csv"  # pixel_only -> no id carried
    SaveSpectrum().save(Collection([spec], item_type=Spectrum), _cfg(path=str(out)))
    loaded = _load_collection(LoadSpectrum(), _cfg(path=str(out)))[0]
    assert loaded.spectrum_id is not None
    assert loaded.spectrum_id != "src_id"  # fresh id, not the source id
    assert "single" not in (loaded.spectrum_id or "")  # never from filename (FR-036)
    assert isinstance(loaded.meta, Spectrum.Meta)
    assert loaded.meta.source_file == str(out)  # source_file kept as metadata


def test_save_batch_numbered_files(tmp_path: Path) -> None:
    s1, _ = fx.make_peak_spectrum(spectrum_id="b1")
    s2, _ = fx.make_peak_spectrum(spectrum_id="b2", peaks=(fx.PeakSpec("gaussian", 7.0, 520.0, 6.0),))
    out = tmp_path / "batch.spectrum.json"
    SaveSpectrum().save(Collection([s1, s2], item_type=Spectrum), _cfg(path=str(out)))
    files = sorted(tmp_path.glob("batch_*.spectrum.json"))
    assert len(files) == 2
    loaded = _load_collection(LoadSpectrum(), _cfg(path=[str(f) for f in files]))
    assert [s.spectrum_id for s in loaded] == ["b1", "b2"]  # order + ids preserved


def test_save_capability_id_override(tmp_path: Path) -> None:
    spec, _ = fx.make_peak_spectrum()
    out = tmp_path / "forced.dat"  # unknown ext; capability_id forces jcamp
    SaveSpectrum().save(
        Collection([spec], item_type=Spectrum),
        _cfg(path=str(out), capability_id="scistudio-blocks-spectroscopy.spectrum.jcamp_dx.save"),
    )
    assert out.read_text(encoding="utf-8").startswith("##TITLE=")


def test_save_rejects_vendor_load_only_extension(tmp_path: Path) -> None:
    spec, _ = fx.make_peak_spectrum()
    with pytest.raises(ValueError):
        SaveSpectrum().save(Collection([spec], item_type=Spectrum), _cfg(path=str(tmp_path / "out.spa")))


def test_load_vendor_format_not_implemented(tmp_path: Path) -> None:
    vendor = tmp_path / "v.spa"
    vendor.write_bytes(b"\x00\x01")
    with pytest.raises(NotImplementedError):
        LoadSpectrum().load(_cfg(path=str(vendor)))


def test_load_folder_and_glob(tmp_path: Path) -> None:
    folder = tmp_path / "spectra"
    folder.mkdir()
    s1, _ = fx.make_peak_spectrum(spectrum_id="a")
    s2, _ = fx.make_peak_spectrum(spectrum_id="b")
    SaveSpectrum().save(Collection([s1], item_type=Spectrum), _cfg(path=str(folder / "a.txt")))
    SaveSpectrum().save(Collection([s2], item_type=Spectrum), _cfg(path=str(folder / "b.txt")))
    assert len(_load_collection(LoadSpectrum(), _cfg(path=str(folder)))) == 2
    assert len(_load_collection(LoadSpectrum(), _cfg(path=str(folder / "*.txt")))) == 2


# ---------------------------------------------------------------------------
# SpectralDataset IO round-trips
# ---------------------------------------------------------------------------


def _load_dataset(config: BlockConfig) -> SpectralDataset:
    result = LoadSpectralDataset().load(config)
    assert isinstance(result, SpectralDataset)
    return result


def test_dataset_json_lossless_roundtrip(tmp_path: Path) -> None:
    dataset, truth = fx.make_library_dataset()
    out = tmp_path / "lib.json"
    SaveSpectralDataset().save(dataset, _cfg(path=str(out)))
    assert out.exists()
    loaded = _load_dataset(_cfg(path=str(out)))
    index_tbl, spectra_tbl = _support.dataset_frames(loaded)
    assert "spectrum_id" in index_tbl.column_names
    assert {"spectrum_id", "lambda", "intensity"}.issubset(spectra_tbl.column_names)
    assert set(index_tbl.column("spectrum_id").to_pylist()) == set(truth)
    meta = loaded.meta
    assert isinstance(meta, SpectralDataset.Meta)
    assert meta.dataset_role == "library"  # role preserved (US3)
    assert meta.lambda_unit == "nm"


def test_dataset_xlsx_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    dataset, truth = fx.make_library_dataset()
    out = tmp_path / "lib.xlsx"
    SaveSpectralDataset().save(dataset, _cfg(path=str(out)))
    loaded = _load_dataset(_cfg(path=str(out)))
    index_tbl, spectra_tbl = _support.dataset_frames(loaded)
    assert index_tbl.num_rows == len(truth)
    assert set(spectra_tbl.column("spectrum_id").to_pylist()) == set(truth)


def test_dataset_save_rejects_zip(tmp_path: Path) -> None:
    dataset, _ = fx.make_library_dataset()
    with pytest.raises(ValueError, match="unsupported extension"):
        SaveSpectralDataset().save(dataset, _cfg(path=str(tmp_path / "out.zip")))


def test_dataset_load_rejects_unsupported_extension(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported extension"):
        LoadSpectralDataset().load(_cfg(path=str(tmp_path / "x.foo")))
