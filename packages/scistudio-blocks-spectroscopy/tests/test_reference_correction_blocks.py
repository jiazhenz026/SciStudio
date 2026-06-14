"""Reference correction block contract tests (SC-029..SC-032).

- SC-029: exactly SubtractReferenceSpectrum + DivideByReferenceSpectrum.
- SC-030: both accept ``Collection[Spectrum]`` plus one ``Spectrum`` reference
  and reject ``SpectralDataset`` directly.
- SC-031: subtraction (sample - reference) and division (sample / reference)
  apply the specified formulas while preserving count, order, spectrum_id,
  metadata, and the sample lambda grid.
- SC-032: mismatched grids fail by default and division by zero requires
  explicit non-default handling.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks import reference_correction
from scistudio_blocks_spectroscopy.blocks.reference_correction import (
    DivideByReferenceSpectrum,
    SubtractReferenceSpectrum,
)
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.testing import BlockTestHarness

_REFERENCE_BLOCKS = (SubtractReferenceSpectrum, DivideByReferenceSpectrum)


def _config(**params: Any) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _spectrum(sid: str, *, lam: Any, inten: Any) -> Spectrum:
    meta = Spectrum.Meta(
        lambda_unit="nm", intensity_unit="au", lambda_kind="wavelength", modality="uvvis", spectrum_id=sid
    )
    return _support.build_spectrum(np.asarray(lam, dtype=float), np.asarray(inten, dtype=float), meta=meta)


# ---------------------------------------------------------------------------
# SC-029: roster
# ---------------------------------------------------------------------------


def test_exactly_two_reference_blocks() -> None:
    names = {b.__name__ for b in reference_correction.BLOCKS}
    assert names == {"SubtractReferenceSpectrum", "DivideByReferenceSpectrum"}
    assert len(reference_correction.BLOCKS) == 2


def test_reference_blocks_pass_harness() -> None:
    for cls in _REFERENCE_BLOCKS:
        assert not BlockTestHarness(cls).validate_block(), cls.__name__


# ---------------------------------------------------------------------------
# SC-030: ports — Collection[Spectrum] + single Spectrum reference; no dataset
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("block_cls", _REFERENCE_BLOCKS)
def test_ports_accept_spectrum_collection_and_single_reference(block_cls: type[ProcessBlock]) -> None:
    spectra = next(p for p in block_cls.input_ports if p.name == "spectra")
    reference = next(p for p in block_cls.input_ports if p.name == "reference")
    assert spectra.accepted_types == [Spectrum] and spectra.is_collection is True
    assert reference.accepted_types == [Spectrum] and reference.is_collection is False
    assert SpectralDataset not in spectra.accepted_types
    assert SpectralDataset not in reference.accepted_types


@pytest.mark.parametrize("block_cls", _REFERENCE_BLOCKS)
def test_dataset_input_is_rejected(block_cls: type[ProcessBlock]) -> None:
    dataset = _support.build_spectral_dataset(
        _support.dataframe_from_rows([{"spectrum_id": "a"}]),
        _support.dataframe_from_rows([{"spectrum_id": "a", "lambda": 1.0, "intensity": 2.0}]),
    )
    ref = _spectrum("ref", lam=(1.0, 2.0, 3.0), inten=(1.0, 1.0, 1.0))
    with pytest.raises((ValueError, TypeError)):
        block_cls().run({"spectra": Collection([dataset], item_type=SpectralDataset), "reference": ref}, _config())


# ---------------------------------------------------------------------------
# SC-031: formulas + identity preservation
# ---------------------------------------------------------------------------


def test_subtraction_formula_and_identity_preservation() -> None:
    s = _spectrum("s1", lam=(1.0, 2.0, 3.0), inten=(4.0, 6.0, 8.0))
    ref = _spectrum("ref", lam=(1.0, 2.0, 3.0), inten=(1.0, 2.0, 3.0))
    out = SubtractReferenceSpectrum().run({"spectra": _support.spectra_collection([s]), "reference": ref}, _config())
    corrected = list(out["corrected"])
    assert len(corrected) == 1
    assert corrected[0].spectrum_id == "s1"
    lam, inten = _support.spectrum_arrays(corrected[0])
    assert np.allclose(lam, [1.0, 2.0, 3.0])  # grid preserved
    assert np.allclose(inten, [3.0, 4.0, 5.0])  # sample - reference


def test_division_formula_and_identity_preservation() -> None:
    s = _spectrum("s1", lam=(1.0, 2.0, 3.0), inten=(4.0, 6.0, 8.0))
    ref = _spectrum("ref", lam=(1.0, 2.0, 3.0), inten=(2.0, 3.0, 4.0))
    out = DivideByReferenceSpectrum().run({"spectra": _support.spectra_collection([s]), "reference": ref}, _config())
    corrected = next(iter(out["corrected"]))
    assert corrected.spectrum_id == "s1"
    lam, inten = _support.spectrum_arrays(corrected)
    assert np.allclose(lam, [1.0, 2.0, 3.0])
    assert np.allclose(inten, [2.0, 2.0, 2.0])  # sample / reference


def test_count_and_order_preserved_across_collection() -> None:
    spectra = [
        _spectrum("a", lam=(1.0, 2.0), inten=(2.0, 4.0)),
        _spectrum("b", lam=(1.0, 2.0), inten=(6.0, 8.0)),
    ]
    ref = _spectrum("ref", lam=(1.0, 2.0), inten=(1.0, 1.0))
    out = SubtractReferenceSpectrum().run(
        {"spectra": _support.spectra_collection(spectra), "reference": ref}, _config()
    )
    produced = list(out["corrected"])
    assert [s.spectrum_id for s in produced] == ["a", "b"]


# ---------------------------------------------------------------------------
# SC-032: grid mismatch + division-by-zero
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("block_cls", _REFERENCE_BLOCKS)
def test_grid_mismatch_fails_by_default(block_cls: type[ProcessBlock]) -> None:
    s = _spectrum("s1", lam=(1.0, 2.0, 3.0), inten=(4.0, 6.0, 8.0))
    ref = _spectrum("ref", lam=(1.0, 2.0, 3.0, 4.0), inten=(1.0, 1.0, 1.0, 1.0))
    with pytest.raises(ValueError):
        block_cls().run({"spectra": _support.spectra_collection([s]), "reference": ref}, _config())


def test_division_by_zero_requires_explicit_handling() -> None:
    s = _spectrum("s1", lam=(1.0, 2.0, 3.0), inten=(4.0, 6.0, 8.0))
    ref = _spectrum("ref", lam=(1.0, 2.0, 3.0), inten=(2.0, 0.0, 4.0))
    # Default: a zero in the reference fails.
    with pytest.raises(ValueError):
        DivideByReferenceSpectrum().run({"spectra": _support.spectra_collection([s]), "reference": ref}, _config())
    # Explicit non-default handling emits NaN at the zero location.
    out = DivideByReferenceSpectrum().run(
        {"spectra": _support.spectra_collection([s]), "reference": ref}, _config(zero_policy="nan")
    )
    _, inten = _support.spectrum_arrays(next(iter(out["corrected"])))
    assert np.isnan(inten[1])
    assert np.allclose(inten[[0, 2]], [2.0, 2.0])
