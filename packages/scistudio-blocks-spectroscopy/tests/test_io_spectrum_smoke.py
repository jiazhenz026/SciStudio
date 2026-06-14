"""Smoke tests for LoadSpectrum / SaveSpectrum and the spectrum format handlers.

Covers (track io-spectrum, FR-034..FR-037, FR-132..FR-134, FR-141..FR-143):

- per-format round-trips (txt/csv/tsv/spectrum_json/jcamp_dx, and xlsx when
  ``openpyxl`` is installed): build via ``_support`` -> save to tmp -> load back
  -> assert lambda/intensity equal and typed Meta preserved where the format
  claims ``typed_meta``/``lossless``;
- ``spectrum_json`` losslessness: spectrum_id + every typed Meta field + the
  ``user`` dict survive the round-trip (FR-141);
- LoadSpectrum generates a fresh package-managed ``spectrum_id`` and keeps
  ``source_file`` as metadata only (FR-035/FR-036);
- SaveSpectrum single vs. multi-item (batch numbered files) and explicit
  ``capability_id`` selection (FR-143);
- SaveSpectrum refuses a vendor load-only extension as a save target (FR-134);
- LoadSpectrum surfaces vendor load-only formats as informative
  ``NotImplementedError`` (FR-133); SPC is deferred with a tracked TODO.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.io_handlers import spectrum_formats
from scistudio_blocks_spectroscopy.blocks.utilities import LoadSpectrum, SaveSpectrum
from scistudio_blocks_spectroscopy.types import Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.testing import BlockTestHarness

_Saver = Callable[[Spectrum, Path], None]
_Loader = Callable[[Path], Spectrum]


def _load_collection(block: LoadSpectrum, config: BlockConfig) -> Collection:
    """Run ``LoadSpectrum.load`` and narrow the result to a ``Collection``."""
    result = block.load(config)
    assert isinstance(result, Collection)
    return result


def _meta(spectrum: Spectrum) -> Spectrum.Meta:
    """Return ``spectrum.meta`` narrowed to the typed ``Spectrum.Meta``."""
    meta = spectrum.meta
    assert isinstance(meta, Spectrum.Meta)
    return meta


def _make_spectrum(scale: float = 1.0) -> Spectrum:
    lam = np.linspace(400.0, 800.0, 48)
    inten = (np.sin(lam / 40.0) + 2.0) * scale
    meta = Spectrum.Meta(
        lambda_unit="nm",
        intensity_unit="a.u.",
        lambda_kind="wavelength",
        modality="uvvis",
        sample_label="sampleA",
    )
    return _support.build_spectrum(lam, inten, meta=meta, user={"note": "hi", "n": 3})


# --------------------------------------------------------------------------
# Block contract validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("block_cls", [LoadSpectrum, SaveSpectrum])
def test_block_validates(block_cls: type) -> None:
    assert not BlockTestHarness(block_cls).validate_block()


# --------------------------------------------------------------------------
# Per-format handler round-trips
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "saver", "loader"),
    [
        ("spec.txt", spectrum_formats.save_delimited_text, spectrum_formats.load_delimited_text),
        ("spec.csv", spectrum_formats.save_delimited_text, spectrum_formats.load_delimited_text),
        ("spec.tsv", spectrum_formats.save_delimited_text, spectrum_formats.load_delimited_text),
        ("spec.spectrum.json", spectrum_formats.save_spectrum_json, spectrum_formats.load_spectrum_json),
        ("spec.jdx", spectrum_formats.save_jcamp_dx, spectrum_formats.load_jcamp_dx),
    ],
)
def test_format_roundtrip_numeric(tmp_path: Path, filename: str, saver: _Saver, loader: _Loader) -> None:
    spec = _make_spectrum()
    lam, inten = _support.spectrum_arrays(spec)
    path = tmp_path / filename
    saver(spec, path)
    assert path.exists()
    loaded = loader(path)
    glam, ginten = _support.spectrum_arrays(loaded)
    assert np.allclose(glam, lam, rtol=1e-6, atol=1e-6)
    assert np.allclose(ginten, inten, rtol=1e-6, atol=1e-6)


def test_xlsx_roundtrip_typed_meta(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    spec = _make_spectrum()
    lam, inten = _support.spectrum_arrays(spec)
    path = tmp_path / "spec.xlsx"
    spectrum_formats.save_spectrum_xlsx(spec, path)
    loaded = spectrum_formats.load_spectrum_xlsx(path)
    glam, ginten = _support.spectrum_arrays(loaded)
    assert np.allclose(glam, lam, rtol=1e-6, atol=1e-6)
    assert np.allclose(ginten, inten, rtol=1e-6, atol=1e-6)
    # typed_meta: declared units/kind/modality survive.
    assert _meta(loaded).lambda_unit == "nm"
    assert _meta(loaded).intensity_unit == "a.u."
    assert _meta(loaded).lambda_kind == "wavelength"
    assert _meta(loaded).modality == "uvvis"


def test_jcamp_preserves_units(tmp_path: Path) -> None:
    spec = _make_spectrum()
    path = tmp_path / "spec.dx"
    spectrum_formats.save_jcamp_dx(spec, path)
    loaded = spectrum_formats.load_jcamp_dx(path)
    # JCAMP typed_meta maps XUNITS/YUNITS -> lambda_unit/intensity_unit.
    assert _meta(loaded).lambda_unit == "nm"
    assert _meta(loaded).intensity_unit == "a.u."


def test_spectrum_json_lossless(tmp_path: Path) -> None:
    spec = _make_spectrum()
    path = tmp_path / "spec.spectrum.json"
    spectrum_formats.save_spectrum_json(spec, path)
    loaded = spectrum_formats.load_spectrum_json(path)
    # FR-141: spectrum_id, every typed Meta field, and the user dict survive.
    assert loaded.spectrum_id == spec.spectrum_id
    assert _meta(loaded).lambda_unit == "nm"
    assert _meta(loaded).intensity_unit == "a.u."
    assert _meta(loaded).lambda_kind == "wavelength"
    assert _meta(loaded).modality == "uvvis"
    assert _meta(loaded).sample_label == "sampleA"
    assert loaded.user == {"note": "hi", "n": 3}


# --------------------------------------------------------------------------
# Deferred formats
# --------------------------------------------------------------------------


def test_spc_is_deferred(tmp_path: Path) -> None:
    spec = _make_spectrum()
    with pytest.raises(NotImplementedError):
        spectrum_formats.save_spc(spec, tmp_path / "spec.spc")
    with pytest.raises(NotImplementedError):
        spectrum_formats.load_spc(tmp_path / "spec.spc")


@pytest.mark.parametrize(
    "loader",
    [
        spectrum_formats.load_thermo_omnic_spa,
        spectrum_formats.load_bruker_opus,
        spectrum_formats.load_horiba_labspec,
        spectrum_formats.load_renishaw_wdf,
        spectrum_formats.load_andor_solis,
        spectrum_formats.load_princeton_spe,
    ],
)
def test_vendor_loaders_deferred(tmp_path: Path, loader: _Loader) -> None:
    with pytest.raises(NotImplementedError):
        loader(tmp_path / "vendor.bin")


# --------------------------------------------------------------------------
# Block-level load -> save -> load
# --------------------------------------------------------------------------


def test_load_generates_fresh_id_and_keeps_source_file(tmp_path: Path) -> None:
    spec = _make_spectrum()
    out = tmp_path / "single.csv"
    SaveSpectrum().save(Collection([spec], item_type=Spectrum), BlockConfig(params={"path": str(out)}))
    loaded = _load_collection(LoadSpectrum(), BlockConfig(params={"path": str(out)}))
    assert len(loaded) == 1
    got = loaded[0]
    lam, inten = _support.spectrum_arrays(spec)
    glam, ginten = _support.spectrum_arrays(got)
    assert np.allclose(glam, lam) and np.allclose(ginten, inten)
    # FR-035 / FR-036: a fresh id is generated (pixel_only csv carries none),
    # never derived from the filename; source_file is metadata only.
    assert got.spectrum_id is not None
    assert got.spectrum_id != spec.spectrum_id
    assert "single" not in (got.spectrum_id or "")
    assert _meta(got).source_file == str(out)


def test_save_batch_writes_numbered_files(tmp_path: Path) -> None:
    s1, s2 = _make_spectrum(), _make_spectrum(scale=2.0)
    out = tmp_path / "batch.spectrum.json"
    SaveSpectrum().save(Collection([s1, s2], item_type=Spectrum), BlockConfig(params={"path": str(out)}))
    files = sorted(tmp_path.glob("batch_*.spectrum.json"))
    assert len(files) == 2
    # Lossless json round-trip preserves both ids in order (FR-037/FR-141).
    loaded = _load_collection(LoadSpectrum(), BlockConfig(params={"path": [str(f) for f in files]}))
    assert [s.spectrum_id for s in loaded] == [s1.spectrum_id, s2.spectrum_id]


def test_save_capability_id_override(tmp_path: Path) -> None:
    spec = _make_spectrum()
    # Unknown extension; capability_id forces the jcamp_dx writer (FR-143).
    out = tmp_path / "forced.dat"
    SaveSpectrum().save(
        Collection([spec], item_type=Spectrum),
        BlockConfig(params={"path": str(out), "capability_id": "scistudio-blocks-spectroscopy.spectrum.jcamp_dx.save"}),
    )
    assert out.read_text(encoding="utf-8").startswith("##TITLE=")


def test_save_rejects_vendor_load_only_extension(tmp_path: Path) -> None:
    spec = _make_spectrum()
    with pytest.raises(ValueError):
        SaveSpectrum().save(
            Collection([spec], item_type=Spectrum),
            BlockConfig(params={"path": str(tmp_path / "out.spa")}),
        )


def test_load_vendor_format_is_not_implemented(tmp_path: Path) -> None:
    vendor = tmp_path / "v.spa"
    vendor.write_bytes(b"\x00\x01")
    with pytest.raises(NotImplementedError):
        LoadSpectrum().load(BlockConfig(params={"path": str(vendor)}))


def test_load_resolves_folder_and_glob(tmp_path: Path) -> None:
    folder = tmp_path / "spectra"
    folder.mkdir()
    SaveSpectrum().save(
        Collection([_make_spectrum()], item_type=Spectrum), BlockConfig(params={"path": str(folder / "a.txt")})
    )
    SaveSpectrum().save(
        Collection([_make_spectrum(scale=3.0)], item_type=Spectrum), BlockConfig(params={"path": str(folder / "b.txt")})
    )
    by_folder = _load_collection(LoadSpectrum(), BlockConfig(params={"path": str(folder)}))
    by_glob = _load_collection(LoadSpectrum(), BlockConfig(params={"path": str(folder / "*.txt")}))
    assert len(by_folder) == 2
    assert len(by_glob) == 2
