"""Preprocessing block contract tests (SC-016..SC-023).

Covers the seven preprocessing blocks of FR-053:

- SC-016: exactly the seven preprocessing blocks are registered.
- SC-017: each accepts ``Collection[Spectrum]`` and does NOT accept
  ``SpectralDataset`` directly.
- SC-018: item count, order, and ``spectrum_id`` values are preserved across
  every accepted preprocessing block.
- SC-019..SC-023: the method/model enums exposed per block are exactly the
  accepted closed sets.

Fit-output port shape (SC-024) lives in ``test_preprocessing_fit_outputs.py``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks import preprocessing
from scistudio_blocks_spectroscopy.blocks.preprocessing import (
    AlignAndResampleSpectra,
    BaselineCorrection,
    CropSpectrumRange,
    NormalizeSpectrum,
    ShiftSpectralAxis,
    SmoothSpectrum,
    SubtractPeakComponent,
)
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.testing import BlockTestHarness

_PREPROCESSING_BLOCK_NAMES = {
    "CropSpectrumRange",
    "ShiftSpectralAxis",
    "BaselineCorrection",
    "SmoothSpectrum",
    "AlignAndResampleSpectra",
    "NormalizeSpectrum",
    "SubtractPeakComponent",
}

# The single output collection port that carries the transformed spectra,
# plus a config that keeps every spectrum in the output (count/order/id preserved).
_PRIMARY_OUTPUT: dict[type[ProcessBlock], tuple[str, dict[str, Any]]] = {
    CropSpectrumRange: ("cropped", {"lambda_min": 0.0, "lambda_max": 1000.0}),
    ShiftSpectralAxis: ("shifted", {"shift": 1.0}),
    BaselineCorrection: ("corrected", {"method": "polynomial"}),
    SmoothSpectrum: ("smoothed", {"method": "moving_average"}),
    NormalizeSpectrum: ("normalized", {"method": "max"}),
    SubtractPeakComponent: ("corrected", {"model": "gaussian"}),
    AlignAndResampleSpectra: ("aligned", {"alignment_method": "none", "target_grid_mode": "first"}),
}


def _config(**params: Any) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _spectrum(sid: str, *, scale: float = 1.0) -> Spectrum:
    lam = np.linspace(0.0, 100.0, 40)
    inten = np.exp(-((lam - 50.0) ** 2) / (2 * 8.0**2)) * 10.0 * scale + 0.5
    meta = Spectrum.Meta(
        lambda_unit="cm-1", intensity_unit="au", lambda_kind="raman_shift", modality="raman", spectrum_id=sid
    )
    return _support.build_spectrum(lam, inten, meta=meta)


def _enum_values(block_cls: type[ProcessBlock], key: str) -> set[str]:
    schema = block_cls.config_schema
    return set(schema["properties"][key]["enum"])


# ---------------------------------------------------------------------------
# SC-016: roster
# ---------------------------------------------------------------------------


def test_exactly_seven_preprocessing_blocks() -> None:
    names = {b.__name__ for b in preprocessing.BLOCKS}
    assert names == _PREPROCESSING_BLOCK_NAMES
    assert len(preprocessing.BLOCKS) == 7


def test_preprocessing_blocks_pass_harness() -> None:
    for cls in preprocessing.BLOCKS:
        assert not BlockTestHarness(cls).validate_block(), cls.__name__


# ---------------------------------------------------------------------------
# SC-017: accept Collection[Spectrum], reject SpectralDataset
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("block_cls", preprocessing.BLOCKS)
def test_spectra_port_accepts_only_spectrum(block_cls: type[ProcessBlock]) -> None:
    spectra_port = next(p for p in block_cls.input_ports if p.name == "spectra")
    assert spectra_port.accepted_types == [Spectrum]
    assert spectra_port.is_collection is True
    # SpectralDataset is not an accepted type on the spectra port.
    assert SpectralDataset not in spectra_port.accepted_types


@pytest.mark.parametrize("block_cls", preprocessing.BLOCKS)
def test_passing_dataset_directly_is_rejected(block_cls: type[ProcessBlock]) -> None:
    """SC-017: a SpectralDataset on the spectra port is refused at runtime."""
    pytest.importorskip("scipy")
    dataset = _support.build_spectral_dataset(
        _support.dataframe_from_rows([{"spectrum_id": "a"}]),
        _support.dataframe_from_rows([{"spectrum_id": "a", "lambda": 1.0, "intensity": 2.0}]),
    )
    _, params = _PRIMARY_OUTPUT[block_cls]
    with pytest.raises((ValueError, TypeError)):
        block_cls().run({"spectra": Collection([dataset], item_type=SpectralDataset)}, _config(**params))


# ---------------------------------------------------------------------------
# SC-018: count / order / spectrum_id preserved
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("block_cls", preprocessing.BLOCKS)
def test_count_order_and_id_preserved(block_cls: type[ProcessBlock]) -> None:
    pytest.importorskip("scipy")
    port, params = _PRIMARY_OUTPUT[block_cls]
    spectra = [_spectrum("first"), _spectrum("second", scale=2.0), _spectrum("third", scale=0.5)]
    out = block_cls().run({"spectra": _support.spectra_collection(spectra)}, _config(**params))
    produced = list(out[port])
    assert len(produced) == 3
    assert [s.spectrum_id for s in produced] == ["first", "second", "third"]


# ---------------------------------------------------------------------------
# SC-019..SC-023: closed method/model enums per block
# ---------------------------------------------------------------------------


def test_baseline_methods_closed_set() -> None:
    """SC-019: only polynomial / asls / arpls / airpls."""
    assert _enum_values(BaselineCorrection, "method") == {"polynomial", "asls", "arpls", "airpls"}


def test_smooth_methods_closed_set() -> None:
    """SC-020: only savitzky_golay / moving_average / gaussian / median."""
    assert _enum_values(SmoothSpectrum, "method") == {
        "savitzky_golay",
        "moving_average",
        "gaussian",
        "median",
    }


def test_align_methods_and_target_grid_modes_closed() -> None:
    """SC-021: alignment modes + accepted target-grid modes."""
    assert _enum_values(AlignAndResampleSpectra, "alignment_method") == {
        "none",
        "peak_fit",
        "cross_correlation",
    }
    assert _enum_values(AlignAndResampleSpectra, "target_grid_mode") == {
        "explicit",
        "first",
        "reference",
        "range_step",
    }


def test_normalize_methods_closed_set() -> None:
    """SC-022: only max / minmax in this draft."""
    assert _enum_values(NormalizeSpectrum, "method") == {"max", "minmax"}


def test_subtract_peak_component_models_closed_set() -> None:
    """SC-023: gaussian / lorentzian / voigt component models."""
    assert _enum_values(SubtractPeakComponent, "model") == {"gaussian", "lorentzian", "voigt"}


def test_invalid_method_is_rejected() -> None:
    """Closed enums are enforced at runtime, not just declared in the schema."""
    spectra = _support.spectra_collection([_spectrum("a")])
    with pytest.raises(ValueError):
        NormalizeSpectrum().run({"spectra": spectra}, _config(method="zscore"))
