"""ADR-043 FR-009/FR-011 — SRS ProcessBlock OME-metadata propagation tests.

Per spec ``docs/specs/adr-043-package-migration.md`` Phase B2:

- **Mode A (shape-preserving same-type derivation)** — block constructs output
  via ``OutputClass(..., meta=item.meta, ...)``; ``ome`` propagates
  transparently. Verified for ``SRSBaseline`` and ``SRSSpectralDenoise``.

- **Mode C with ``model_dump`` override** — block constructs output via
  ``SRSImage.Meta(**old_meta.model_dump(), ...overrides)``;
  ``model_dump()`` carries the ``ome`` field automatically. Verified for
  ``SRSCalibrate``.

- **Mode C fix** — shape-preserving cross-type derivation (``Image`` →
  ``Label``) MUST carry ``ome``. Verified for ``SRSKMeansCluster`` (T-042).

- **Mode C legitimate drop** — output drops spectral alignment with the
  source (``SRSImage`` → ``Image`` PC score maps / endmember abundance
  maps), so ``meta=None`` is the documented behavior. Verified for
  ``SRSPCA`` (T-044).

See ``docs/audit/adr-043-srs-propagation-audit.md`` for the full Mode A/B/C
classification table and per-block rationale.
"""

from __future__ import annotations

import numpy as np
import pytest

# Cross-plugin imports per imaging-plugin spec §Q5 / phase11-implementation-standards.
# The SRS test environment in CI installs ``scistudio-blocks-imaging`` as a dep
# (declared in ``packages/scistudio-blocks-srs/pyproject.toml``); local
# developers without it set up get the same skip behavior as
# ``test_component_analysis.py`` uses for ``sklearn``.
pytest.importorskip("scistudio_blocks_imaging")
pytest.importorskip("sklearn")  # SRSKMeansCluster + SRSPCA require sklearn
pytest.importorskip("scipy")  # SRSBaseline rubber_band / rolling_ball
pytest.importorskip("ome_types")

from ome_types.model import OME, Pixels, PixelType
from ome_types.model import Image as OMEImage
from scistudio_blocks_imaging.types import Image as ImagingImage
from scistudio_blocks_imaging.types import Label
from scistudio_blocks_srs import (
    SRSPCA,
    SRSBaseline,
    SRSCalibrate,
    SRSImage,
    SRSKMeansCluster,
    SRSSpectralDenoise,
)

from scistudio.blocks.base.block import BlockConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ome() -> OME:
    """Build a minimal OME structure pretending to describe a 4x4x8 SRS cube."""
    return OME(
        images=[
            OMEImage(
                pixels=Pixels(
                    size_x=4,
                    size_y=4,
                    size_c=1,
                    size_z=1,
                    size_t=1,
                    dimension_order="XYCZT",
                    type=PixelType.FLOAT,
                    physical_size_x=0.5,
                    physical_size_y=0.5,
                )
            )
        ]
    )


def _config(**params: object) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _srs_cube_with_ome(
    *,
    shape: tuple[int, ...] = (4, 4, 8),
    ome: OME | None = None,
) -> SRSImage:
    """Build an :class:`SRSImage` with a representative spectral signal and OME meta."""
    if ome is None:
        ome = _make_ome()
    axes = ["y", "x", "lambda"]
    lambda_axis = axes.index("lambda")
    wavelengths = np.linspace(2850.0, 2930.0, shape[lambda_axis], dtype=np.float32)
    line = np.linspace(0.0, 1.0, shape[lambda_axis], dtype=np.float32)
    baseline = 0.3 * (0.4 + 0.8 * line + 0.6 * line**2)
    peak = np.exp(-((wavelengths - 2890.0) ** 2) / (2.0 * 8.0**2)).astype(np.float32)
    spectrum = baseline + peak
    reshape = [1] * len(shape)
    reshape[lambda_axis] = shape[lambda_axis]
    cube = np.broadcast_to(spectrum.reshape(reshape), shape).astype(np.float32).copy()
    cube += 0.02 * np.arange(cube.size, dtype=np.float32).reshape(shape)

    meta = SRSImage.Meta(
        wavenumbers_cm1=list(wavelengths),
        laser_power=5.0,
        source_file="srs_meta_propagation_test.tif",
        ome=ome,
    )
    img = SRSImage(axes=axes, shape=shape, dtype=cube.dtype, meta=meta)
    img._data = cube  # type: ignore[attr-defined]
    return img


# ---------------------------------------------------------------------------
# Mode A — shape-preserving same-type derivations: ``meta=item.meta``
# ---------------------------------------------------------------------------


def test_srs_baseline_mode_a_preserves_ome() -> None:
    """``SRSBaseline`` constructs the output with ``meta=item.meta`` (Mode A)."""
    ome = _make_ome()
    src = _srs_cube_with_ome(ome=ome)

    out = SRSBaseline().process_item(src, _config())

    assert isinstance(out, SRSImage)
    assert out.meta is not None
    assert out.meta.ome is ome  # transparent pass-through preserves identity


def test_srs_spectral_denoise_mode_a_preserves_ome() -> None:
    """``SRSSpectralDenoise`` constructs the output with ``meta=item.meta`` (Mode A)."""
    ome = _make_ome()
    src = _srs_cube_with_ome(ome=ome)

    out = SRSSpectralDenoise().process_item(src, _config(window_length=3, polyorder=1))

    assert isinstance(out, SRSImage)
    assert out.meta is not None
    assert out.meta.ome is ome


# ---------------------------------------------------------------------------
# Mode C via ``model_dump`` + override: SRSCalibrate
# ---------------------------------------------------------------------------


def test_srs_calibrate_mode_c_model_dump_carries_ome() -> None:
    """``SRSCalibrate`` rebuilds SRSImage.Meta from ``item.meta.model_dump()`` plus
    digitizer overrides. ``model_dump()`` includes every Meta field by default —
    including the new ``ome`` field — so the override path carries it through
    without any explicit code change. This test proves that contract.
    """
    ome = _make_ome()
    # Raw imaging-plugin Image input (not SRSImage), with ome populated.
    raw_data = np.arange(2 * 2 * 3, dtype=np.uint16).reshape(2, 2, 3)
    raw = ImagingImage(
        axes=["y", "x", "lambda"],
        shape=raw_data.shape,
        dtype=raw_data.dtype,
        meta=ImagingImage.Meta(source_file="raw.tif", ome=ome),
    )
    raw._data = raw_data  # type: ignore[attr-defined]

    out = SRSCalibrate().process_item(
        raw,
        _config(bit_depth=4096, voltage_range=10.0, offset=0.0, scale=1.0),
    )

    assert isinstance(out, SRSImage)
    assert out.meta is not None
    # ``model_dump`` round-trip rebuilds the OME object, so identity is not
    # preserved — but the dumped/reconstructed object must compare equal.
    assert out.meta.ome is not None
    assert out.meta.ome.model_dump() == ome.model_dump()
    # Digitizer overrides must also be present (sanity check that the override
    # path didn't silently nuke unrelated fields).
    assert out.meta.digitizer_bit_depth == 4096
    assert out.meta.source_file == "raw.tif"


# ---------------------------------------------------------------------------
# Mode C fix — SRSImage → Label is shape-preserving; ome MUST propagate.
# ---------------------------------------------------------------------------


def test_srs_kmeans_mode_c_label_carries_ome() -> None:
    """``SRSKMeansCluster`` emits ``Label`` whose ``Label.Meta.ome`` must equal
    the source SRSImage's OME object (cluster assignments share the
    source's y/x spatial layout — FR-009 Mode C shape-preserving rule).
    """
    ome = _make_ome()
    src = _srs_cube_with_ome(ome=ome)

    outputs = SRSKMeansCluster().run({"image": src}, _config(n_clusters=3, n_init=1))

    label = outputs["labels"]
    assert isinstance(label, Label)
    assert label.meta is not None
    assert label.meta.ome is ome  # same object — Mode C explicit propagation
    assert label.meta.source_file == "srs_meta_propagation_test.tif"
    assert label.meta.n_objects == 3


# ---------------------------------------------------------------------------
# Mode C legitimate drop — SRS_PCA score maps and SRSUnmix abundance maps
# replace lambda with a derived axis, so meta=None is documented behavior.
# ---------------------------------------------------------------------------


def test_srs_pca_mode_c_legitimate_meta_drop() -> None:
    """``SRSPCA`` emits ``Collection[Image]`` of PC score maps with
    ``meta=None`` because the spectral (lambda) axis is replaced by a
    derived ``pc_id`` index — OME channel/spectral descriptions no longer
    apply. This is a documented Mode C legitimate-drop case per
    ``docs/audit/adr-043-srs-propagation-audit.md``.
    """
    ome = _make_ome()
    src = _srs_cube_with_ome(ome=ome)

    outputs = SRSPCA().run({"image": src}, _config(n_components=2, scale=False))

    maps = outputs["pc_maps"]
    items = list(maps)
    assert len(items) == 2
    for img in items:
        assert isinstance(img, ImagingImage)
        # Mode C legitimate drop: meta=None is the documented behavior.
        assert img.meta is None


# ---------------------------------------------------------------------------
# Sanity guards on the propagation contract for None-meta sources
# ---------------------------------------------------------------------------


def test_srs_kmeans_handles_none_meta_source() -> None:
    """When the source SRSImage has ``meta=None``, ``SRSKMeansCluster`` must
    still build a valid Label without raising and without inventing an
    ome field out of thin air.
    """
    axes = ["y", "x", "lambda"]
    shape = (3, 3, 4)
    cube = np.random.default_rng(0).standard_normal(shape).astype(np.float32)
    src = SRSImage(axes=axes, shape=shape, dtype=cube.dtype, meta=None)
    src._data = cube  # type: ignore[attr-defined]

    outputs = SRSKMeansCluster().run({"image": src}, _config(n_clusters=2, n_init=1))

    label = outputs["labels"]
    assert isinstance(label, Label)
    assert label.meta is not None
    assert label.meta.ome is None
    assert label.meta.source_file is None


def test_srs_kmeans_handles_meta_without_ome() -> None:
    """When the source SRSImage has a populated Meta but ``ome=None``, the
    Label output's ``ome`` must also be ``None`` (no synthesis).
    """
    axes = ["y", "x", "lambda"]
    shape = (3, 3, 4)
    cube = np.random.default_rng(0).standard_normal(shape).astype(np.float32)
    src = SRSImage(
        axes=axes,
        shape=shape,
        dtype=cube.dtype,
        meta=SRSImage.Meta(source_file="no_ome.tif", ome=None),
    )
    src._data = cube  # type: ignore[attr-defined]

    outputs = SRSKMeansCluster().run({"image": src}, _config(n_clusters=2, n_init=1))

    label = outputs["labels"]
    assert isinstance(label, Label)
    assert label.meta is not None
    assert label.meta.ome is None
    assert label.meta.source_file == "no_ome.tif"


if __name__ == "__main__":  # pragma: no cover - manual debugging
    pytest.main([__file__, "-v"])
