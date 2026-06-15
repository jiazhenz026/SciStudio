"""Spectrum IO contract tests (SC-049, SC-050, SC-052).

These tests bind the spec IO contract for ``LoadSpectrum`` / ``SaveSpectrum`` to
executable assertions, complementing the implementer smoke tests:

- the native formats (txt/csv/tsv/xlsx/spectrum_json/jcamp_dx) load and save
  according to their declared metadata fidelity (SC-050);
- ``spectrum_json`` is lossless: spectrum_id + every typed ``Meta`` field + the
  ``user`` dict survive a build -> save -> load round-trip (FR-141);
- delimited text is ``pixel_only`` (numeric payload survives, typed meta does
  not), and the LoadSpectrum block regenerates a fresh package-managed
  ``spectrum_id`` while keeping ``source_file`` separate (FR-035/FR-036);
- ``capability_id`` selects a handler by ``FormatCapability.id`` (SC-049);
- vendor/SPC handlers remain tracked deferrals, but are not advertised through
  block capability dispatch until implemented (SC-051/SC-052).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.io_handlers import spectrum_formats
from scistudio_blocks_spectroscopy.blocks.utilities import LoadSpectrum, SaveSpectrum
from scistudio_blocks_spectroscopy.types import Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection

_TYPED_META_FIELDS = ("lambda_unit", "intensity_unit", "lambda_kind", "modality")


def _meta(spectrum: Spectrum) -> Spectrum.Meta:
    meta = spectrum.meta
    assert isinstance(meta, Spectrum.Meta)
    return meta


def _make_spectrum(scale: float = 1.0) -> Spectrum:
    lam = np.linspace(400.0, 800.0, 32)
    inten = (np.cos(lam / 50.0) + 2.0) * scale
    meta = Spectrum.Meta(
        lambda_unit="nm",
        intensity_unit="a.u.",
        lambda_kind="wavelength",
        modality="uvvis",
        sample_label="sampleA",
    )
    return _support.build_spectrum(lam, inten, meta=meta, user={"note": "hi", "n": 3})


# ---------------------------------------------------------------------------
# SC-050: native formats load + save per declared fidelity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "saver", "loader"),
    [
        ("s.txt", spectrum_formats.save_delimited_text, spectrum_formats.load_delimited_text),
        ("s.csv", spectrum_formats.save_delimited_text, spectrum_formats.load_delimited_text),
        ("s.tsv", spectrum_formats.save_delimited_text, spectrum_formats.load_delimited_text),
        ("s.spectrum.json", spectrum_formats.save_spectrum_json, spectrum_formats.load_spectrum_json),
        ("s.jdx", spectrum_formats.save_jcamp_dx, spectrum_formats.load_jcamp_dx),
    ],
)
def test_native_format_numeric_roundtrip(tmp_path: Path, filename: str, saver: Any, loader: Any) -> None:
    spec = _make_spectrum()
    lam, inten = _support.spectrum_arrays(spec)
    path = tmp_path / filename
    saver(spec, path)
    assert path.exists()
    glam, ginten = _support.spectrum_arrays(loader(path))
    assert np.allclose(glam, lam, rtol=1e-6, atol=1e-6)
    assert np.allclose(ginten, inten, rtol=1e-6, atol=1e-6)


def test_spectrum_json_is_lossless(tmp_path: Path) -> None:
    """FR-141 / SC-050: spectrum_json round-trips id + all Meta + user."""
    spec = _make_spectrum()
    path = tmp_path / "s.spectrum.json"
    spectrum_formats.save_spectrum_json(spec, path)
    loaded = spectrum_formats.load_spectrum_json(path)
    assert loaded.spectrum_id == spec.spectrum_id
    meta = _meta(loaded)
    assert meta.lambda_unit == "nm"
    assert meta.intensity_unit == "a.u."
    assert meta.lambda_kind == "wavelength"
    assert meta.modality == "uvvis"
    assert meta.sample_label == "sampleA"
    assert loaded.user == {"note": "hi", "n": 3}


def test_xlsx_typed_meta_roundtrip(tmp_path: Path) -> None:
    """SC-050: xlsx carries typed_meta (units/kind/modality survive)."""
    pytest.importorskip("openpyxl")
    spec = _make_spectrum()
    lam, inten = _support.spectrum_arrays(spec)
    path = tmp_path / "s.xlsx"
    spectrum_formats.save_spectrum_xlsx(spec, path)
    loaded = spectrum_formats.load_spectrum_xlsx(path)
    glam, ginten = _support.spectrum_arrays(loaded)
    assert np.allclose(glam, lam, rtol=1e-6, atol=1e-6)
    assert np.allclose(ginten, inten, rtol=1e-6, atol=1e-6)
    meta = _meta(loaded)
    for field in _TYPED_META_FIELDS:
        assert getattr(meta, field) == getattr(_meta(spec), field)


def test_jcamp_typed_meta_maps_units(tmp_path: Path) -> None:
    """SC-050: JCAMP-DX maps XUNITS/YUNITS -> lambda_unit/intensity_unit."""
    spec = _make_spectrum()
    path = tmp_path / "s.dx"
    spectrum_formats.save_jcamp_dx(spec, path)
    meta = _meta(spectrum_formats.load_jcamp_dx(path))
    assert meta.lambda_unit == "nm"
    assert meta.intensity_unit == "a.u."


def test_delimited_text_is_pixel_only(tmp_path: Path) -> None:
    """SC-050: pixel_only formats preserve numbers but not typed meta."""
    spec = _make_spectrum()
    path = tmp_path / "s.csv"
    spectrum_formats.save_delimited_text(spec, path)
    loaded = spectrum_formats.load_delimited_text(path)
    # Numeric payload preserved.
    _, inten = _support.spectrum_arrays(spec)
    _, ginten = _support.spectrum_arrays(loaded)
    assert np.allclose(ginten, inten, rtol=1e-6, atol=1e-6)
    # Typed units are NOT carried by a pixel_only format.
    assert _meta(loaded).lambda_unit is None
    assert _meta(loaded).intensity_unit is None


# ---------------------------------------------------------------------------
# Block-level identity + capability selection (FR-035/036, SC-049)
# ---------------------------------------------------------------------------


def test_load_block_generates_fresh_id_keeps_source_file(tmp_path: Path) -> None:
    """FR-035 / FR-036: a pixel_only load mints a fresh id, never from filename."""
    spec = _make_spectrum()
    out = tmp_path / "named_after_file.csv"
    SaveSpectrum().save(Collection([spec], item_type=Spectrum), BlockConfig(params={"path": str(out)}))
    result = LoadSpectrum().load(BlockConfig(params={"path": str(out)}))
    assert isinstance(result, Collection)
    got = result[0]
    assert got.spectrum_id is not None
    assert got.spectrum_id != spec.spectrum_id
    assert "named_after_file" not in (got.spectrum_id or "")
    assert _meta(got).source_file == str(out)


def test_capability_id_selects_handler_by_id(tmp_path: Path) -> None:
    """SC-049: capability_id (a FormatCapability.id) selects the writer."""
    spec = _make_spectrum()
    out = tmp_path / "forced.dat"  # extension does not imply jcamp
    SaveSpectrum().save(
        Collection([spec], item_type=Spectrum),
        BlockConfig(
            params={
                "path": str(out),
                "capability_id": "scistudio-blocks-spectroscopy.spectrum.jcamp_dx.save",
            }
        ),
    )
    assert out.read_text(encoding="utf-8").startswith("##TITLE=")


def test_unknown_capability_id_is_rejected(tmp_path: Path) -> None:
    """SC-049: a capability_id that is not a declared id fails loudly."""
    spec = _make_spectrum()
    with pytest.raises(ValueError):
        SaveSpectrum().save(
            Collection([spec], item_type=Spectrum),
            BlockConfig(params={"path": str(tmp_path / "x.csv"), "capability_id": "not.a.real.capability"}),
        )


# ---------------------------------------------------------------------------
# SC-052: vendor load-only formats
# ---------------------------------------------------------------------------


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
def test_vendor_loaders_are_tracked_not_implemented(tmp_path: Path, loader: Any) -> None:
    with pytest.raises(NotImplementedError):
        loader(tmp_path / "vendor.bin")


def test_save_block_rejects_vendor_load_only_extension(tmp_path: Path) -> None:
    """SC-052: vendor formats have no saver, so a .spa save target fails."""
    spec = _make_spectrum()
    with pytest.raises(ValueError):
        SaveSpectrum().save(
            Collection([spec], item_type=Spectrum),
            BlockConfig(params={"path": str(tmp_path / "out.spa")}),
        )


def test_spc_spectrum_is_deferred_not_advertised(tmp_path: Path) -> None:
    """SC-051: SPC handlers are tracked TODOs, not block capabilities."""
    spec = _make_spectrum()
    with pytest.raises(NotImplementedError):
        spectrum_formats.save_spc(spec, tmp_path / "x.spc")
    with pytest.raises(NotImplementedError):
        spectrum_formats.load_spc(tmp_path / "x.spc")
    with pytest.raises(ValueError):
        SaveSpectrum().save(
            Collection([spec], item_type=Spectrum), BlockConfig(params={"path": str(tmp_path / "x.spc")})
        )
    spc = tmp_path / "x.spc"
    spc.write_bytes(b"")
    with pytest.raises(ValueError):
        LoadSpectrum().load(BlockConfig(params={"path": str(spc)}))
