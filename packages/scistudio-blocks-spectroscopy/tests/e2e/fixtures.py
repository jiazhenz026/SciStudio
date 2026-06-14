"""Deterministic pseudo-spectra generators with analytic ground truth (#1661).

Every generator here is *seeded* (callers pass a fixed seed; no unseeded
randomness is ever used) so the e2e asserts can compare block outputs against
known analytic values within an explicit tolerance.

What this module provides
-------------------------

- :class:`PeakSpec` / :class:`Ground` — analytic descriptors carrying the true
  peak center, amplitude, sigma/gamma, FWHM, and integrated area so tests can
  assert recovered fit parameters against the values that generated the data.
- :func:`gaussian` / :func:`lorentzian` / :func:`voigt` — pure peak profiles.
- :func:`polynomial_baseline` / :func:`asls_like_baseline` — additive baseline
  drift (smooth polynomial and an asymmetric, asls-shaped rising baseline).
- :func:`gaussian_noise` — seeded additive noise.
- :func:`make_peak_spectrum` — a single :class:`Spectrum` = peak(s) + baseline
  + noise, returning ``(Spectrum, Ground)``.
- :func:`make_two_peak_spectrum` — a two-peak spectrum for ratio / FWHM tests.
- :func:`make_collection` — a multi-sample ``Collection[Spectrum]`` with
  ``material`` / ``method`` / ``replicate`` index metadata.
- :func:`make_library_dataset` — a library-shaped :class:`SpectralDataset`
  (``dataset_role="library"``).
- :func:`make_reference_spectra` / :func:`make_mixture` — endmember references
  and a known linear mixture for unmixing tests.
- on-disk writers (:func:`write_delimited`, :func:`write_xlsx`,
  :func:`write_spectrum_json`, :func:`write_dataset_json`,
  :func:`write_dataset_xlsx`) that round-trip through the real IO blocks.

The shared canonical grid is ``DEFAULT_GRID`` (a regular ascending nm grid).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.types import (
    INTENSITY_COLUMN,
    LAMBDA_COLUMN,
    SPECTRUM_ID_COLUMN,
    SpectralDataset,
    Spectrum,
)

# Canonical regular grid used across the e2e suite (nm, ascending).
DEFAULT_GRID = np.linspace(400.0, 600.0, 401)
GAUSS_FWHM_FACTOR = 2.0 * np.sqrt(2.0 * np.log(2.0))


# ---------------------------------------------------------------------------
# Analytic descriptors
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PeakSpec:
    """Analytic description of one synthetic peak (the ground truth)."""

    model: str  # "gaussian" | "lorentzian" | "voigt"
    amplitude: float
    center: float
    sigma: float = 0.0  # gaussian / voigt
    gamma: float = 0.0  # lorentzian / voigt

    @property
    def fwhm(self) -> float:
        """Analytic full width at half maximum."""
        if self.model == "gaussian":
            return float(GAUSS_FWHM_FACTOR * abs(self.sigma))
        if self.model == "lorentzian":
            return float(2.0 * abs(self.gamma))
        # Voigt (Olivero & Longbothum pseudo-Voigt approximation).
        fwhm_g = GAUSS_FWHM_FACTOR * abs(self.sigma)
        fwhm_l = 2.0 * abs(self.gamma)
        return float(0.5346 * fwhm_l + np.sqrt(0.2166 * fwhm_l**2 + fwhm_g**2))

    @property
    def area(self) -> float:
        """Analytic integrated area of the pure peak."""
        if self.model == "gaussian":
            return float(self.amplitude * abs(self.sigma) * np.sqrt(2.0 * np.pi))
        if self.model == "lorentzian":
            return float(self.amplitude * np.pi * abs(self.gamma))
        # Voigt area is computed numerically by the caller from the curve.
        return float("nan")

    def evaluate(self, lam: np.ndarray) -> np.ndarray:
        """Evaluate the pure peak profile on ``lam``."""
        if self.model == "gaussian":
            return gaussian(lam, self.amplitude, self.center, self.sigma)
        if self.model == "lorentzian":
            return lorentzian(lam, self.amplitude, self.center, self.gamma)
        return voigt(lam, self.amplitude, self.center, self.sigma, self.gamma)


@dataclass(frozen=True)
class Ground:
    """Analytic ground truth carried alongside a generated spectrum."""

    spectrum_id: str
    grid: np.ndarray
    peaks: tuple[PeakSpec, ...]
    baseline: np.ndarray
    noise_sigma: float
    pure_peak: np.ndarray  # sum of peak profiles, no baseline / noise
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def primary(self) -> PeakSpec:
        return self.peaks[0]

    @property
    def total_area(self) -> float:
        """Trapezoidal area of the pure (baseline-free) peak signal."""
        return float(np.trapezoid(self.pure_peak, self.grid))


# ---------------------------------------------------------------------------
# Pure profiles
# ---------------------------------------------------------------------------


def gaussian(lam: np.ndarray, amplitude: float, center: float, sigma: float) -> np.ndarray:
    """Gaussian peak: ``amplitude * exp(-0.5 ((lam-center)/sigma)^2)``."""
    sigma = sigma if abs(sigma) > 1e-12 else 1e-12
    return np.asarray(amplitude * np.exp(-0.5 * ((lam - center) / sigma) ** 2), dtype=np.float64)


def lorentzian(lam: np.ndarray, amplitude: float, center: float, gamma: float) -> np.ndarray:
    """Lorentzian peak with HWHM ``gamma`` and peak height ``amplitude``."""
    gamma = gamma if abs(gamma) > 1e-12 else 1e-12
    return np.asarray(amplitude * (gamma**2) / ((lam - center) ** 2 + gamma**2), dtype=np.float64)


def voigt(lam: np.ndarray, amplitude: float, center: float, sigma: float, gamma: float) -> np.ndarray:
    """Voigt peak (gaussian-lorentzian convolution) normalised to ``amplitude``.

    Uses ``scipy.special.voigt_profile``; callers that exercise this must guard
    with ``pytest.importorskip("scipy")``.
    """
    from scipy.special import voigt_profile

    sigma = abs(sigma) if abs(sigma) > 1e-12 else 1e-12
    gamma = abs(gamma) if abs(gamma) > 1e-12 else 1e-12
    profile = voigt_profile(lam - center, sigma, gamma)
    peak = float(voigt_profile(np.array([0.0]), sigma, gamma)[0]) or 1e-12
    return np.asarray(amplitude * profile / peak, dtype=np.float64)


# ---------------------------------------------------------------------------
# Baselines + noise
# ---------------------------------------------------------------------------


def polynomial_baseline(lam: np.ndarray, coeffs: tuple[float, ...]) -> np.ndarray:
    """Smooth polynomial baseline ``sum(coeffs[i] * t^i)`` over normalised t.

    ``t`` is ``lam`` rescaled to ``[0, 1]`` so the coefficients stay O(1)
    regardless of the absolute lambda range.
    """
    span = float(lam[-1] - lam[0]) or 1.0
    t = (lam - lam[0]) / span
    out = np.zeros_like(lam, dtype=np.float64)
    for power, coeff in enumerate(coeffs):
        out = out + coeff * t**power
    return out


def asls_like_baseline(lam: np.ndarray, *, low: float = 0.0, high: float = 4.0, curvature: float = 2.5) -> np.ndarray:
    """Asymmetric, monotonically rising baseline shaped like an asls drift.

    Convex rising background (``t**curvature`` between ``low`` and ``high``)
    that sits *below* the peaks, the regime asymmetric-least-squares estimators
    target.
    """
    span = float(lam[-1] - lam[0]) or 1.0
    t = (lam - lam[0]) / span
    return np.asarray(low + (high - low) * t**curvature, dtype=np.float64)


def gaussian_noise(size: int, sigma: float, seed: int) -> np.ndarray:
    """Seeded additive gaussian noise of length ``size`` (deterministic)."""
    if sigma <= 0.0:
        return np.zeros(size, dtype=np.float64)
    rng = np.random.default_rng(seed)
    return np.asarray(rng.normal(0.0, sigma, size=size), dtype=np.float64)


# ---------------------------------------------------------------------------
# Spectrum builders
# ---------------------------------------------------------------------------


def _meta(metadata: dict[str, Any]) -> Spectrum.Meta:
    fields = set(Spectrum.Meta.model_fields)
    kwargs = {k: v for k, v in metadata.items() if k in fields}
    kwargs.setdefault("lambda_unit", "nm")
    kwargs.setdefault("intensity_unit", "au")
    kwargs.setdefault("lambda_kind", "wavelength")
    kwargs.setdefault("modality", "uvvis")
    return Spectrum.Meta(**kwargs)


def make_peak_spectrum(
    *,
    spectrum_id: str = "spec_0",
    grid: np.ndarray | None = None,
    peaks: tuple[PeakSpec, ...] | PeakSpec | None = None,
    baseline_coeffs: tuple[float, ...] = (0.0,),
    baseline: np.ndarray | None = None,
    noise_sigma: float = 0.0,
    seed: int = 0,
    metadata: dict[str, Any] | None = None,
) -> tuple[Spectrum, Ground]:
    """Build one ``Spectrum`` = peak(s) + baseline + seeded noise + its ground truth."""
    lam = np.asarray(DEFAULT_GRID if grid is None else grid, dtype=np.float64)
    if peaks is None:
        peaks = (PeakSpec("gaussian", amplitude=5.0, center=500.0, sigma=8.0),)
    elif isinstance(peaks, PeakSpec):
        peaks = (peaks,)

    pure = np.zeros_like(lam, dtype=np.float64)
    for peak in peaks:
        pure = pure + peak.evaluate(lam)

    base = polynomial_baseline(lam, baseline_coeffs) if baseline is None else np.asarray(baseline, dtype=np.float64)
    noise = gaussian_noise(lam.shape[0], noise_sigma, seed)
    intensity = pure + base + noise

    meta_dict = dict(metadata or {})
    spectrum = _support.build_spectrum(lam, intensity, meta=_meta(meta_dict), spectrum_id=spectrum_id)
    ground = Ground(
        spectrum_id=spectrum_id,
        grid=lam,
        peaks=tuple(peaks),
        baseline=base,
        noise_sigma=noise_sigma,
        pure_peak=pure,
        metadata=meta_dict,
    )
    return spectrum, ground


def make_two_peak_spectrum(
    *,
    spectrum_id: str = "two_peak",
    grid: np.ndarray | None = None,
    amp_a: float = 6.0,
    center_a: float = 470.0,
    sigma_a: float = 6.0,
    amp_b: float = 3.0,
    center_b: float = 540.0,
    sigma_b: float = 9.0,
    noise_sigma: float = 0.0,
    seed: int = 1,
) -> tuple[Spectrum, Ground]:
    """Two well-separated gaussian peaks (for ratio / multi-peak feature tests)."""
    peaks = (
        PeakSpec("gaussian", amplitude=amp_a, center=center_a, sigma=sigma_a),
        PeakSpec("gaussian", amplitude=amp_b, center=center_b, sigma=sigma_b),
    )
    return make_peak_spectrum(spectrum_id=spectrum_id, grid=grid, peaks=peaks, noise_sigma=noise_sigma, seed=seed)


def make_collection(
    *,
    n: int = 4,
    grid: np.ndarray | None = None,
    noise_sigma: float = 0.0,
    seed: int = 100,
) -> tuple[list[Spectrum], list[Ground]]:
    """Build a multi-sample list of spectra with material/method/replicate metadata.

    Each sample carries a single gaussian whose amplitude and center vary
    deterministically with the sample index so downstream features differ.
    """
    lam = np.asarray(DEFAULT_GRID if grid is None else grid, dtype=np.float64)
    materials = ("polymerA", "polymerB")
    methods = ("spin_coat", "drop_cast")
    spectra: list[Spectrum] = []
    grounds: list[Ground] = []
    for i in range(n):
        amplitude = 4.0 + i
        center = 480.0 + 10.0 * i
        peak = PeakSpec("gaussian", amplitude=amplitude, center=center, sigma=7.0)
        metadata = {
            "material": materials[i % len(materials)],
            "method": methods[i % len(methods)],
            "replicate": i // 2,
            "sample_label": f"sample_{i}",
        }
        spectrum, ground = make_peak_spectrum(
            spectrum_id=f"spec_{i}",
            grid=lam,
            peaks=(peak,),
            baseline_coeffs=(0.2, 0.5),
            noise_sigma=noise_sigma,
            seed=seed + i,
            metadata=metadata,
        )
        # Carry the non-typed columns (material/method/replicate) as user metadata.
        spectra.append(
            _support.build_spectrum(
                ground.grid,
                ground.pure_peak + ground.baseline + gaussian_noise(lam.shape[0], noise_sigma, seed + i),
                meta=spectrum.meta if isinstance(spectrum.meta, Spectrum.Meta) else None,
                user={k: metadata[k] for k in ("material", "method", "replicate")},
                spectrum_id=f"spec_{i}",
            )
        )
        grounds.append(ground)
    return spectra, grounds


def make_library_dataset(
    *,
    entries: list[tuple[str, PeakSpec]] | None = None,
    grid: np.ndarray | None = None,
    dataset_role: str = "library",
) -> tuple[SpectralDataset, dict[str, np.ndarray]]:
    """Build a library-shaped ``SpectralDataset`` plus a {id: intensity} truth map."""
    lam = np.asarray(DEFAULT_GRID if grid is None else grid, dtype=np.float64)
    if entries is None:
        entries = [
            ("ref_500", PeakSpec("gaussian", amplitude=5.0, center=500.0, sigma=8.0)),
            ("ref_520", PeakSpec("gaussian", amplitude=5.0, center=520.0, sigma=8.0)),
            ("ref_480", PeakSpec("gaussian", amplitude=5.0, center=480.0, sigma=8.0)),
        ]
    truth: dict[str, np.ndarray] = {}
    spectrum_ids: list[str] = []
    lambdas: list[float] = []
    intensities: list[float] = []
    index_rows: list[dict[str, Any]] = []
    for sid, peak in entries:
        inten = peak.evaluate(lam)
        truth[sid] = inten
        spectrum_ids.extend([sid] * lam.shape[0])
        lambdas.extend(lam.tolist())
        intensities.extend(inten.tolist())
        index_rows.append({SPECTRUM_ID_COLUMN: sid, "material": sid, "citation": f"doi:{sid}"})

    spectra_table = _support.dataframe_from_rows(
        [
            {SPECTRUM_ID_COLUMN: s, LAMBDA_COLUMN: x, INTENSITY_COLUMN: y}
            for s, x, y in zip(spectrum_ids, lambdas, intensities, strict=True)
        ],
        columns=[SPECTRUM_ID_COLUMN, LAMBDA_COLUMN, INTENSITY_COLUMN],
    )
    index_table = _support.dataframe_from_rows(index_rows)
    dataset = _support.build_spectral_dataset(
        index_table,
        spectra_table,
        meta=SpectralDataset.Meta(
            dataset_name="lib",
            dataset_role=dataset_role,
            lambda_unit="nm",
            intensity_unit="au",
            modality="uvvis",
        ),
    )
    return dataset, truth


def make_reference_spectra(
    *,
    grid: np.ndarray | None = None,
    labels: tuple[str, ...] = ("compA", "compB", "compC"),
) -> list[Spectrum]:
    """Build distinct endmember reference spectra for unmixing (no noise)."""
    lam = np.asarray(DEFAULT_GRID if grid is None else grid, dtype=np.float64)
    peaks = [
        PeakSpec("gaussian", amplitude=5.0, center=460.0, sigma=9.0),
        PeakSpec("gaussian", amplitude=5.0, center=510.0, sigma=9.0),
        PeakSpec("gaussian", amplitude=5.0, center=560.0, sigma=9.0),
    ]
    return [
        _support.build_spectrum(
            lam,
            peaks[i].evaluate(lam),
            meta=_meta({"sample_label": labels[i]}),
            spectrum_id=labels[i],
        )
        for i in range(len(labels))
    ]


def make_mixture(
    references: list[Spectrum],
    coefficients: list[float],
    *,
    spectrum_id: str = "mixture",
    noise_sigma: float = 0.0,
    seed: int = 7,
) -> Spectrum:
    """Build a known linear mixture ``sum(coeff_i * reference_i)`` (+ seeded noise)."""
    lam, _ = _support.spectrum_arrays(references[0])
    mixed = np.zeros_like(lam, dtype=np.float64)
    for coeff, ref in zip(coefficients, references, strict=True):
        _, inten = _support.spectrum_arrays(ref)
        mixed = mixed + coeff * inten
    mixed = mixed + gaussian_noise(lam.shape[0], noise_sigma, seed)
    return _support.build_spectrum(lam, mixed, meta=_meta({}), spectrum_id=spectrum_id)


# ---------------------------------------------------------------------------
# On-disk writers (round-trip through the real IO handlers / blocks)
# ---------------------------------------------------------------------------


def write_delimited(spectrum: Spectrum, path: Path) -> Path:
    """Write a spectrum as a 2-column delimited file (.txt/.csv/.tsv)."""
    from scistudio_blocks_spectroscopy.blocks.io_handlers import spectrum_formats

    spectrum_formats.save_delimited_text(spectrum, Path(path))
    return Path(path)


def write_spectrum_json(spectrum: Spectrum, path: Path) -> Path:
    """Write a spectrum to the lossless native ``.spectrum.json`` format."""
    from scistudio_blocks_spectroscopy.blocks.io_handlers import spectrum_formats

    spectrum_formats.save_spectrum_json(spectrum, Path(path))
    return Path(path)


def write_xlsx(spectrum: Spectrum, path: Path) -> Path:
    """Write a spectrum to an ``.xlsx`` workbook (requires openpyxl)."""
    from scistudio_blocks_spectroscopy.blocks.io_handlers import spectrum_formats

    spectrum_formats.save_spectrum_xlsx(spectrum, Path(path))
    return Path(path)


def write_dataset_json(dataset: SpectralDataset, path: Path) -> Path:
    """Write a dataset to the lossless JSON manifest (+ sidecar parquet slots)."""
    from scistudio_blocks_spectroscopy.blocks.io_handlers import dataset_formats

    dataset_formats.save_manifest_json(dataset, Path(path))
    return Path(path)


def write_dataset_xlsx(dataset: SpectralDataset, path: Path) -> Path:
    """Write a dataset to an ``.xlsx`` workbook (requires openpyxl)."""
    from scistudio_blocks_spectroscopy.blocks.io_handlers import dataset_formats

    dataset_formats.save_dataset_xlsx(dataset, Path(path))
    return Path(path)
