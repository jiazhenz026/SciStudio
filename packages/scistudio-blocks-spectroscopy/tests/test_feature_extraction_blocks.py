"""Feature extraction block contract tests (SC-025..SC-028).

Covers the five measurement blocks:

- SC-025: exactly ExtractIntensity / CalculateAUC / CalculateCentroid /
  CalculateRatio / FindPeaks.
- SC-026: each accepts ``Collection[Spectrum]``, rejects ``SpectralDataset``,
  and emits a flat ``DataFrame`` keyed by ``spectrum_id`` (no object cells) that
  can merge into ``SpectralDataset.index``.
- SC-027: ExtractIntensity / CalculateAUC / CalculateCentroid report explicit
  status for missing coordinates, empty ranges, and unusable denominators.
- SC-028: CalculateRatio is peak-to-peak only, FindPeaks supports range bounds,
  and no standalone CalculateFWHM / MeasurePeakInRange block exists.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks import feature_extraction
from scistudio_blocks_spectroscopy.blocks.feature_extraction import (
    CalculateAUC,
    CalculateCentroid,
    CalculateRatio,
    ExtractIntensity,
    FindPeaks,
)
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.testing import BlockTestHarness

_SCALAR_TYPES = (type(None), bool, int, float, str)

_FEATURE_BLOCK_NAMES = {
    "ExtractIntensity",
    "CalculateAUC",
    "CalculateCentroid",
    "CalculateRatio",
    "FindPeaks",
}


def _config(**params: Any) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _spectrum(sid: str, *, lam: Any = None, inten: Any = None) -> Spectrum:
    if lam is None:
        lam = np.linspace(0.0, 100.0, 51)
    if inten is None:
        inten = np.exp(-((np.asarray(lam) - 50.0) ** 2) / (2 * 6.0**2)) + 0.1
    meta = Spectrum.Meta(
        lambda_unit="cm-1", intensity_unit="au", lambda_kind="raman_shift", modality="raman", spectrum_id=sid
    )
    return _support.build_spectrum(np.asarray(lam, dtype=float), np.asarray(inten, dtype=float), meta=meta)


def _features_table(block: Any, spectra: list[Spectrum], **params: Any) -> Any:
    out = block.run({"spectra": _support.spectra_collection(spectra)}, _config(**params))
    df = next(iter(out["features"]))
    return _support.dataframe_arrow(df)


# ---------------------------------------------------------------------------
# SC-025 / SC-028: roster
# ---------------------------------------------------------------------------


def test_exactly_five_feature_blocks() -> None:
    names = {b.__name__ for b in feature_extraction.BLOCKS}
    assert names == _FEATURE_BLOCK_NAMES
    assert len(feature_extraction.BLOCKS) == 5
    # SC-028: no standalone CalculateFWHM / MeasurePeakInRange block.
    assert "CalculateFWHM" not in names
    assert "MeasurePeakInRange" not in names


def test_feature_blocks_pass_harness() -> None:
    for cls in feature_extraction.BLOCKS:
        assert not BlockTestHarness(cls).validate_block(), cls.__name__


# ---------------------------------------------------------------------------
# SC-026: input/output contract — accept Collection[Spectrum], reject dataset,
# flat DataFrame keyed by spectrum_id, no object cells, mergeable into index.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("block_cls", feature_extraction.BLOCKS)
def test_spectra_port_accepts_only_spectrum(block_cls: type[ProcessBlock]) -> None:
    spectra_port = next(p for p in block_cls.input_ports if p.name == "spectra")
    assert spectra_port.accepted_types == [Spectrum]
    assert spectra_port.is_collection is True
    assert SpectralDataset not in spectra_port.accepted_types


def test_passing_dataset_directly_is_rejected() -> None:
    """SC-026: a SpectralDataset on the spectra port is not silently processed.

    The block raises rather than treating the composite as a spectrum (the exact
    exception type is an implementation detail; the contract is non-acceptance).
    """
    dataset = _support.build_spectral_dataset(
        _support.dataframe_from_rows([{"spectrum_id": "a"}]),
        _support.dataframe_from_rows([{"spectrum_id": "a", "lambda": 1.0, "intensity": 2.0}]),
    )
    with pytest.raises((ValueError, TypeError, AttributeError)):
        CalculateAUC().run({"spectra": Collection([dataset], item_type=SpectralDataset)}, _config())


@pytest.mark.parametrize(
    ("block_cls", "params"),
    [
        (ExtractIntensity, {"target_coordinate": 50.0}),
        (CalculateAUC, {"lambda_min": 0.0, "lambda_max": 100.0}),
        (CalculateCentroid, {"lambda_min": 0.0, "lambda_max": 100.0}),
        (FindPeaks, {}),
        (
            CalculateRatio,
            {"numerator_peak": {"coordinate": 50.0}, "denominator_peak": {"coordinate": 10.0}},
        ),
    ],
)
def test_features_table_is_flat_and_keyed_by_spectrum_id(block_cls: type[ProcessBlock], params: dict) -> None:
    pytest.importorskip("scipy")
    spectra = [_spectrum("s1"), _spectrum("s2")]
    table = _features_table(block_cls(), spectra, **params)
    # spectrum_id + status columns present.
    assert "spectrum_id" in table.column_names
    assert "status" in table.column_names
    # No object cells: every column value is a scalar (mergeable into index).
    pdf = table.to_pylist()
    for row in pdf:
        for value in row.values():
            assert isinstance(value, _SCALAR_TYPES), f"non-scalar cell: {value!r}"
    # FindPeaks may emit multiple rows per spectrum; others are one row each.
    ids = set(table.column("spectrum_id").to_pylist())
    assert ids <= {"s1", "s2"}


def test_features_merge_into_dataset_index() -> None:
    """SC-026: a feature table merges into SpectralDataset.index by spectrum_id."""
    from scistudio_blocks_spectroscopy.blocks.utilities import (
        AttachFeaturesToSpectralDataset,
        SpectrumToSpectralDataset,
    )

    from scistudio.core.types.dataframe import DataFrame

    spectra = [_spectrum("s1"), _spectrum("s2")]
    ds_out = SpectrumToSpectralDataset().run({"spectra": _support.spectra_collection(spectra)}, _config())
    dataset = next(iter(ds_out["dataset"]))
    feat_out = CalculateAUC().run(
        {"spectra": _support.spectra_collection(spectra)}, _config(lambda_min=0.0, lambda_max=100.0)
    )
    features = next(iter(feat_out["features"]))
    merged = AttachFeaturesToSpectralDataset().run(
        {
            "dataset": Collection([dataset], item_type=SpectralDataset),
            "features": Collection([features], item_type=DataFrame),
        },
        _config(),
    )
    index, _ = _support.dataset_frames(next(iter(merged["dataset"])))
    assert "auc" in index.column_names


# ---------------------------------------------------------------------------
# SC-027: explicit status for missing/empty/unusable cases
# ---------------------------------------------------------------------------


def test_extract_intensity_reports_status() -> None:
    ok = _features_table(ExtractIntensity(), [_spectrum("s1")], target_coordinate=50.0)
    assert ok.column("status").to_pylist() == ["ok"]
    empty = _support.build_spectrum(
        np.array([], dtype=float), np.array([], dtype=float), meta=Spectrum.Meta(spectrum_id="empty")
    )
    empty_table = _features_table(ExtractIntensity(), [empty], target_coordinate=50.0)
    assert empty_table.column("status").to_pylist() == ["empty_spectrum"]
    # No coordinate or range configured -> explicit status, not a crash.
    no_target = _features_table(ExtractIntensity(), [_spectrum("s1")])
    assert no_target.column("status").to_pylist() == ["no_target_coordinate_or_range"]


def test_calculate_auc_reports_insufficient_points() -> None:
    ok = _features_table(CalculateAUC(), [_spectrum("s1")], lambda_min=0.0, lambda_max=100.0)
    assert ok.column("status").to_pylist() == ["ok"]
    # Range narrower than the grid spacing -> fewer than two points.
    narrow = _features_table(CalculateAUC(), [_spectrum("s1")], lambda_min=49.9, lambda_max=50.1)
    assert narrow.column("status").to_pylist() == ["range_has_fewer_than_two_points"]


def test_calculate_centroid_reports_zero_denominator() -> None:
    ok = _features_table(CalculateCentroid(), [_spectrum("s1")], lambda_min=0.0, lambda_max=100.0)
    assert ok.column("status").to_pylist() == ["ok"]
    flat_zero = _spectrum("zero", inten=np.zeros(51))
    zero_table = _features_table(CalculateCentroid(), [flat_zero], lambda_min=0.0, lambda_max=100.0)
    assert zero_table.column("status").to_pylist() == ["zero_intensity_denominator"]


# ---------------------------------------------------------------------------
# SC-028: CalculateRatio peak-to-peak only; FindPeaks range bounds
# ---------------------------------------------------------------------------


def test_calculate_ratio_is_peak_to_peak() -> None:
    """SC-028: CalculateRatio requires numerator_peak + denominator_peak."""
    props = CalculateRatio.config_schema["properties"]
    assert "numerator_peak" in props
    assert "denominator_peak" in props
    spectra = [_spectrum("s1")]
    table = _features_table(
        CalculateRatio(),
        spectra,
        numerator_peak={"coordinate": 50.0},
        denominator_peak={"coordinate": 50.0},
    )
    assert "ratio" in table.column_names
    # Peak at center over itself -> ratio 1.0 with ok status.
    assert table.column("status").to_pylist() == ["ok"]
    assert table.column("ratio").to_pylist()[0] == pytest.approx(1.0)


def test_find_peaks_supports_range_bounds() -> None:
    """SC-028: FindPeaks exposes lambda_min / lambda_max range bounds."""
    props = FindPeaks.config_schema["properties"]
    assert "lambda_min" in props
    assert "lambda_max" in props
    pytest.importorskip("scipy")
    # Two peaks; restrict the search window to only the first.
    lam = np.linspace(0.0, 100.0, 201)
    inten = np.exp(-((lam - 25.0) ** 2) / 8.0) + np.exp(-((lam - 75.0) ** 2) / 8.0)
    spectrum = _spectrum("two_peaks", lam=lam, inten=inten)
    bounded = _features_table(FindPeaks(), [spectrum], lambda_min=0.0, lambda_max=50.0, prominence=0.2)
    coords = [
        c
        for c, status in zip(
            bounded.column("peak_coordinate").to_pylist(), bounded.column("status").to_pylist(), strict=True
        )
        if status == "ok" and c is not None
    ]
    assert coords  # a peak was found
    assert all(c <= 50.0 for c in coords)
