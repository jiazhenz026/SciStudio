"""Spectral unmixing block contract tests (SC-033..SC-038).

- SC-033: the unmixing group is exactly ``SpectralUnmixing``.
- SC-034: it exposes exactly two output ports: ``coefficients`` + ``fit_quality``.
- SC-035: ``coefficients`` is a wide table — one row per sample spectrum, with
  ``spectrum_id``, ``method``, and one deterministic numeric coefficient column
  per reference component (collision-free).
- SC-036: ``fit_quality`` carries spectrum_id / method / status / residual_norm
  / rmse / n_components.
- SC-037: only least_squares / non_negative_least_squares /
  sum_to_one_non_negative_least_squares are exposed.
- SC-038: the block does not define or emit a SpectralUnmixingResult, fitted
  spectra, residual spectra, or component spectra.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks import unmixing
from scistudio_blocks_spectroscopy.blocks.unmixing import SpectralUnmixing
from scistudio_blocks_spectroscopy.types import Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.testing import BlockTestHarness

_RESERVED_COEF_COLUMNS = {"spectrum_id", "method"}


def _config(**params: Any) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _spectrum(sid: str, *, lam: Any, inten: Any) -> Spectrum:
    meta = Spectrum.Meta(
        lambda_unit="nm", intensity_unit="au", lambda_kind="wavelength", modality="raman", spectrum_id=sid
    )
    return _support.build_spectrum(np.asarray(lam, dtype=float), np.asarray(inten, dtype=float), meta=meta)


def _run(samples: list[Spectrum], refs: list[Spectrum], **params: Any) -> Any:
    out = SpectralUnmixing().run(
        {
            "spectra": _support.spectra_collection(samples),
            "references": _support.spectra_collection(refs),
        },
        _config(**params),
    )
    coef = _support.dataframe_arrow(next(iter(out["coefficients"])))
    fq = _support.dataframe_arrow(next(iter(out["fit_quality"])))
    return out, coef, fq


# ---------------------------------------------------------------------------
# SC-033 / SC-034: roster + output ports
# ---------------------------------------------------------------------------


def test_unmixing_group_is_exactly_spectral_unmixing() -> None:
    assert [b.__name__ for b in unmixing.BLOCKS] == ["SpectralUnmixing"]


def test_unmixing_passes_harness() -> None:
    assert not BlockTestHarness(SpectralUnmixing).validate_block()


def test_exactly_two_output_ports() -> None:
    names = [p.name for p in SpectralUnmixing.output_ports]
    assert names == ["coefficients", "fit_quality"]


# ---------------------------------------------------------------------------
# SC-037: method enum
# ---------------------------------------------------------------------------


def test_unmixing_methods_closed_set() -> None:
    enum = set(SpectralUnmixing.config_schema["properties"]["method"]["enum"])
    assert enum == {
        "least_squares",
        "non_negative_least_squares",
        "sum_to_one_non_negative_least_squares",
    }


# ---------------------------------------------------------------------------
# SC-035: wide coefficients table, deterministic collision-free columns
# ---------------------------------------------------------------------------


def test_coefficients_is_wide_with_one_column_per_component() -> None:
    grid = np.linspace(0.0, 10.0, 11)
    ref_a = _spectrum("compA", lam=grid, inten=np.ones_like(grid))
    ref_b = _spectrum("compB", lam=grid, inten=grid)
    sample = _spectrum("s1", lam=grid, inten=2.0 * np.ones_like(grid) + 3.0 * grid)
    _, coef, _ = _run([sample], [ref_a, ref_b], method="least_squares")

    assert "spectrum_id" in coef.column_names
    assert "method" in coef.column_names
    component_cols = [c for c in coef.column_names if c not in _RESERVED_COEF_COLUMNS]
    # One coefficient column per reference component.
    assert len(component_cols) == 2
    assert coef.num_rows == 1  # one row per sample spectrum
    row = coef.to_pylist()[0]
    assert row["spectrum_id"] == "s1"
    # Recovered coefficients ~ [2, 3] (least squares on a clean linear mixture).
    values = sorted(round(float(row[c]), 3) for c in component_cols)
    assert values == pytest.approx([2.0, 3.0], abs=1e-3)


def test_coefficient_columns_are_collision_free() -> None:
    """SC-035: duplicate raw labels yield distinct deterministic columns."""
    grid = np.linspace(0.0, 10.0, 11)
    # Two references share the same id -> column names must still be unique.
    ref_a = _spectrum("dup", lam=grid, inten=np.ones_like(grid))
    ref_b = _spectrum("dup", lam=grid, inten=grid)
    sample = _spectrum("s1", lam=grid, inten=grid + 1.0)
    _, coef, _ = _run([sample], [ref_a, ref_b], method="least_squares")
    component_cols = [c for c in coef.column_names if c not in _RESERVED_COEF_COLUMNS]
    assert len(component_cols) == 2
    assert len(set(component_cols)) == 2  # no collision


# ---------------------------------------------------------------------------
# SC-036: fit_quality schema
# ---------------------------------------------------------------------------


def test_fit_quality_schema() -> None:
    grid = np.linspace(0.0, 10.0, 11)
    ref_a = _spectrum("compA", lam=grid, inten=np.ones_like(grid))
    ref_b = _spectrum("compB", lam=grid, inten=grid)
    sample = _spectrum("s1", lam=grid, inten=2.0 + 3.0 * grid)
    _, _, fq = _run([sample], [ref_a, ref_b], method="least_squares")
    assert {
        "spectrum_id",
        "method",
        "status",
        "residual_norm",
        "rmse",
        "n_components",
    }.issubset(fq.column_names)
    row = fq.to_pylist()[0]
    assert row["n_components"] == 2
    assert row["method"] == "least_squares"


# ---------------------------------------------------------------------------
# SC-038: no result type / fitted / residual / component spectra output
# ---------------------------------------------------------------------------


def test_no_result_type_or_spectra_outputs() -> None:
    # Only the two DataFrame ports exist; no fitted/residual/component spectra.
    from scistudio.core.types.dataframe import DataFrame

    port_names = {p.name for p in SpectralUnmixing.output_ports}
    assert port_names == {"coefficients", "fit_quality"}
    for port in SpectralUnmixing.output_ports:
        assert port.accepted_types == [DataFrame]
        assert Spectrum not in port.accepted_types
    # No SpectralUnmixingResult type is importable from the package.
    import scistudio_blocks_spectroscopy as pkg

    assert not hasattr(pkg, "SpectralUnmixingResult")


def test_run_emits_only_the_two_ports() -> None:
    grid = np.linspace(0.0, 10.0, 11)
    ref_a = _spectrum("compA", lam=grid, inten=np.ones_like(grid))
    sample = _spectrum("s1", lam=grid, inten=np.ones_like(grid))
    out, _, _ = _run([sample], [ref_a], method="least_squares")
    assert set(out.keys()) == {"coefficients", "fit_quality"}
