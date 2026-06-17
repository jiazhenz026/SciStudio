"""Fit-output port contract tests for preprocessing blocks (SC-024).

SC-024 requires that:

- ``BaselineCorrection`` always emits ``corrected``, ``baseline``, and
  ``fit_diagnostics``;
- ``AlignAndResampleSpectra`` always emits ``aligned``, ``fit_curves``, and
  ``fit_diagnostics``;
- ``SubtractPeakComponent`` always emits ``corrected``, ``component``, and
  ``fit_diagnostics`` including FWHM where available.

Both the declared output-port set and the live ``run()`` output dict are
asserted, plus the per-spectrum diagnostics row schema.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.preprocessing import (
    AlignAndResampleSpectra,
    BaselineCorrection,
    SubtractPeakComponent,
)
from scistudio_blocks_spectroscopy.types import Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.dataframe import DataFrame


def _config(**params: Any) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _peak_spectrum(sid: str) -> Spectrum:
    lam = np.linspace(0.0, 100.0, 81)
    inten = 5.0 * np.exp(-((lam - 50.0) ** 2) / (2 * 6.0**2)) + 0.4
    meta = Spectrum.Meta(
        lambda_unit="cm-1", intensity_unit="au", lambda_kind="raman_shift", modality="raman", spectrum_id=sid
    )
    return _support.build_spectrum(lam, inten, meta=meta)


def _declared_port_names(block_cls: type[ProcessBlock]) -> list[str]:
    return [p.name for p in block_cls.output_ports]


def _diag_table(diagnostics: Any) -> Any:
    df = next(iter(diagnostics))
    assert isinstance(df, DataFrame)
    return _support.dataframe_arrow(df)


# ---------------------------------------------------------------------------
# Declared output ports
# ---------------------------------------------------------------------------


def test_baseline_declares_three_ports() -> None:
    assert _declared_port_names(BaselineCorrection) == ["corrected", "baseline", "fit_diagnostics"]


def test_align_declares_three_ports() -> None:
    assert _declared_port_names(AlignAndResampleSpectra) == ["aligned", "fit_curves", "fit_diagnostics"]


def test_subtract_peak_declares_three_ports() -> None:
    assert _declared_port_names(SubtractPeakComponent) == ["corrected", "component", "fit_diagnostics"]


# ---------------------------------------------------------------------------
# Live run() always emits the three named ports
# ---------------------------------------------------------------------------


def test_baseline_run_emits_all_three_ports() -> None:
    pytest.importorskip("scipy")
    spectra = _support.spectra_collection([_peak_spectrum("b1")])
    out = BaselineCorrection().run({"spectra": spectra}, _config(method="polynomial"))
    assert set(out.keys()) == {"corrected", "baseline", "fit_diagnostics"}
    assert len(list(out["corrected"])) == 1
    assert len(list(out["baseline"])) == 1
    diag = _diag_table(out["fit_diagnostics"])
    assert "spectrum_id" in diag.column_names
    assert "status" in diag.column_names
    assert diag.num_rows == 1


def test_align_run_emits_all_three_ports() -> None:
    pytest.importorskip("scipy")
    spectra = _support.spectra_collection([_peak_spectrum("a1"), _peak_spectrum("a2")])
    out = AlignAndResampleSpectra().run(
        {"spectra": spectra}, _config(alignment_method="none", target_grid_mode="first")
    )
    assert set(out.keys()) == {"aligned", "fit_curves", "fit_diagnostics"}
    assert len(list(out["aligned"])) == 2
    diag = _diag_table(out["fit_diagnostics"])
    assert {"spectrum_id", "status"}.issubset(diag.column_names)
    assert diag.num_rows == 2


def test_subtract_peak_run_emits_all_three_ports_with_fwhm() -> None:
    pytest.importorskip("scipy")
    spectra = _support.spectra_collection([_peak_spectrum("c1")])
    out = SubtractPeakComponent().run({"spectra": spectra}, _config(model="gaussian"))
    assert set(out.keys()) == {"corrected", "component", "fit_diagnostics"}
    assert len(list(out["corrected"])) == 1
    assert len(list(out["component"])) == 1
    diag = _diag_table(out["fit_diagnostics"])
    # SC-024: SubtractPeakComponent diagnostics carry FWHM (where available).
    assert "fwhm" in diag.column_names
    assert {"spectrum_id", "status", "center", "amplitude"}.issubset(diag.column_names)
    assert diag.num_rows == 1
    # On a clean Gaussian, the fit succeeds and FWHM is a finite positive number.
    status = diag.column("status").to_pylist()[0]
    fwhm = diag.column("fwhm").to_pylist()[0]
    if status == "ok":
        assert fwhm is not None and np.isfinite(fwhm) and fwhm > 0.0
