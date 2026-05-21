"""Tests for SRS component-analysis blocks (T-SRS-006..010).

All tests use synthetic cubes with deterministic seeds and skip cleanly
when ``sklearn``/``scipy`` are not available via ``pytest.importorskip``.
"""

from __future__ import annotations

from typing import cast

import numpy as np
import pytest

pytest.importorskip("sklearn")
pytest.importorskip("scipy")

from scistudio_blocks_imaging.types import Image, Label
from scistudio_blocks_srs.component_analysis.srs_ica import SRSICA
from scistudio_blocks_srs.component_analysis.srs_kmeans import SRSKMeansCluster
from scistudio_blocks_srs.component_analysis.srs_pca import SRSPCA
from scistudio_blocks_srs.component_analysis.srs_unmix import SRSUnmix
from scistudio_blocks_srs.component_analysis.srs_vca import SRSVCA, _extract_endmembers
from scistudio_blocks_srs.types import SRSImage

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_srs_image(
    cube: np.ndarray,
    *,
    axes: list[str] | None = None,
    wavenumbers: list[float] | None = None,
) -> SRSImage:
    axes = axes if axes is not None else ["y", "x", "lambda"]
    meta: SRSImage.Meta | None = None
    if wavenumbers is not None:
        meta = SRSImage.Meta(wavenumbers_cm1=list(wavenumbers))
    img = SRSImage(axes=list(axes), shape=cube.shape, dtype=cube.dtype, meta=meta)
    img._data = cube  # type: ignore[attr-defined]
    return img


def _synthetic_mixture(
    seed: int = 0,
    y: int = 8,
    x: int = 8,
    n_w: int = 20,
    n_endmembers: int = 3,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (cube, endmembers, abundances) with each pixel being a
    non-negative mixture of ``n_endmembers`` known spectra + small noise.
    """
    rng = np.random.default_rng(seed)
    # Smooth random endmember spectra.
    t = np.linspace(0.0, 1.0, n_w)
    endmembers = np.stack(
        [np.exp(-((t - (i + 1) / (n_endmembers + 1)) ** 2) * 30.0) for i in range(n_endmembers)],
        axis=0,
    ).astype(np.float64)
    # Random per-pixel abundances summing to 1 via Dirichlet.
    abundances = rng.dirichlet(np.ones(n_endmembers), size=y * x)
    cube_flat = abundances @ endmembers
    cube_flat += rng.normal(scale=0.005, size=cube_flat.shape)
    cube = cube_flat.reshape(y, x, n_w).astype(np.float64)
    return cube, endmembers, abundances.reshape(y, x, n_endmembers)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _best_cosine(recovered: np.ndarray, truth: np.ndarray) -> float:
    """Max over truth rows of cosine similarity with any recovered row."""
    best = 0.0
    for r in recovered:
        for t in truth:
            best = max(best, abs(_cosine(r, t)))
    return best


# ---------------------------------------------------------------------------
# T-SRS-006 — SRSVCA
# ---------------------------------------------------------------------------


def test_vca_smoke_recovers_endmembers() -> None:
    cube, endmembers, _ = _synthetic_mixture(seed=1, n_endmembers=2)
    item = _make_srs_image(cube)
    block = SRSVCA()
    result = block.process_item(item, BlockConfig(params={"n_components": 2}))
    assert isinstance(result, DataFrame)
    table = result._arrow_table  # type: ignore[attr-defined]
    assert table.num_rows == 2
    # First column is endmember_id, remaining are wavenumber columns.
    data = np.asarray([table.column(c).to_pylist() for c in table.column_names if c != "endmember_id"]).T
    # At least one truth row has a very high cosine match.
    for truth_row in endmembers:
        assert _best_cosine(data, truth_row[None, :]) > 0.95


def test_vca_n_components_param() -> None:
    cube, _, _ = _synthetic_mixture(seed=2, n_endmembers=3)
    item = _make_srs_image(cube)
    result = SRSVCA().process_item(item, BlockConfig(params={"n_components": 3}))
    assert result.row_count == 3


def test_vca_columns_default_to_index_when_no_wavenumbers() -> None:
    cube, _, _ = _synthetic_mixture(seed=3, n_w=6)
    item = _make_srs_image(cube)
    result = SRSVCA().process_item(item, BlockConfig(params={"n_components": 2}))
    feature_cols = [c for c in result.columns if c != "endmember_id"]
    assert feature_cols == [str(float(i)) for i in range(6)]


def test_vca_columns_match_wavenumbers() -> None:
    cube, _, _ = _synthetic_mixture(seed=4, n_w=5)
    wns = [100.0, 200.0, 300.0, 400.0, 500.0]
    item = _make_srs_image(cube, wavenumbers=wns)
    result = SRSVCA().process_item(item, BlockConfig(params={"n_components": 2}))
    feature_cols = [c for c in result.columns if c != "endmember_id"]
    assert feature_cols == [str(w) for w in wns]


def test_vca_endmember_id_is_first_column() -> None:
    cube, _, _ = _synthetic_mixture(seed=5, n_endmembers=2)
    result = SRSVCA().process_item(_make_srs_image(cube), BlockConfig(params={"n_components": 2}))
    assert result.columns is not None and result.columns[0] == "endmember_id"


def test_vca_internal_helper_callable_from_unmix() -> None:
    cube, _, _ = _synthetic_mixture(seed=6, n_endmembers=2)
    item = _make_srs_image(cube)
    endmembers, wavenumbers = _extract_endmembers(item, n_components=2)
    assert endmembers.shape == (2, cube.shape[-1])
    assert len(wavenumbers) == cube.shape[-1]


def test_vca_invalid_n_components_raises() -> None:
    cube, _, _ = _synthetic_mixture(seed=7)
    with pytest.raises(ValueError, match="n_components must be"):
        _extract_endmembers(_make_srs_image(cube), n_components=1)


# ---------------------------------------------------------------------------
# T-SRS-007 — SRSUnmix
# ---------------------------------------------------------------------------


def _references_dataframe(endmembers: np.ndarray) -> DataFrame:
    import pyarrow as pa

    n_em, n_w = endmembers.shape
    column_data: dict = {
        "endmember_id": pa.array(list(range(n_em)), type=pa.int64()),
    }
    for k in range(n_w):
        column_data[str(float(k))] = pa.array(endmembers[:, k].tolist())
    table = pa.table(column_data)
    df = DataFrame(columns=list(table.column_names), row_count=n_em)
    df._arrow_table = table  # type: ignore[attr-defined]
    return df


def test_unmix_with_explicit_references() -> None:
    cube, endmembers, abundances = _synthetic_mixture(seed=10, n_endmembers=2)
    item = _make_srs_image(cube)
    ref_df = _references_dataframe(endmembers)
    block = SRSUnmix()
    out = block.run({"image": item, "references": ref_df}, BlockConfig(params={}))
    maps_coll = cast(Collection, out["abundance_maps"])
    maps = list(maps_coll)
    assert len(maps) == 2
    # Cosine of recovered abundances with truth should be high.
    for k, img in enumerate(maps):
        recovered = img._data.reshape(-1)  # type: ignore[attr-defined]
        truth = abundances[..., k].reshape(-1)
        assert _cosine(recovered, truth) > 0.9
        # NNLS non-negativity.
        assert float(recovered.min()) >= -1e-6


def test_unmix_vca_nnls_mode() -> None:
    cube, _, _ = _synthetic_mixture(seed=11, n_endmembers=3)
    item = _make_srs_image(cube)
    out = SRSUnmix().run({"image": item}, BlockConfig(params={"mode": "vca_nnls", "auto_vca_n_components": 3}))
    maps = list(cast(Collection, out["abundance_maps"]))
    assert len(maps) == 3
    assert isinstance(out["endmembers"], DataFrame)


def test_unmix_nnls_mode_requires_references() -> None:
    cube, _, _ = _synthetic_mixture(seed=11, n_endmembers=3)
    item = _make_srs_image(cube)
    with pytest.raises(ValueError, match="mode='nnls' requires"):
        SRSUnmix().run({"image": item}, BlockConfig(params={"mode": "nnls"}))


def test_unmix_collection_item_type_is_image() -> None:
    cube, endmembers, _ = _synthetic_mixture(seed=12, n_endmembers=2)
    item = _make_srs_image(cube)
    ref_df = _references_dataframe(endmembers)
    out = SRSUnmix().run({"image": item, "references": ref_df}, BlockConfig(params={}))
    coll = cast(Collection, out["abundance_maps"])
    assert coll._item_type is Image


def test_unmix_abundance_axes_are_yx() -> None:
    cube, endmembers, _ = _synthetic_mixture(seed=13, n_endmembers=2)
    item = _make_srs_image(cube)
    ref_df = _references_dataframe(endmembers)
    out = SRSUnmix().run({"image": item, "references": ref_df}, BlockConfig(params={}))
    for img in cast(Collection, out["abundance_maps"]):
        assert img.axes == ["y", "x"]


def test_unmix_vca_nnls_mode_logs(caplog: pytest.LogCaptureFixture) -> None:
    cube, _, _ = _synthetic_mixture(seed=14, n_endmembers=2)
    item = _make_srs_image(cube)
    caplog.set_level("INFO", logger="scistudio_blocks_srs.component_analysis.srs_unmix")
    SRSUnmix().run({"image": item}, BlockConfig(params={"mode": "vca_nnls", "auto_vca_n_components": 2}))
    assert any("vca_nnls" in rec.message for rec in caplog.records)


def test_unmix_missing_image_raises() -> None:
    with pytest.raises(ValueError, match="missing required 'image'"):
        SRSUnmix().run({}, BlockConfig(params={}))


# ---------------------------------------------------------------------------
# T-SRS-008 — SRSPCA
# ---------------------------------------------------------------------------


def test_pca_smoke_3components() -> None:
    cube, _, _ = _synthetic_mixture(seed=20, n_endmembers=3, y=6, x=6, n_w=12)
    item = _make_srs_image(cube)
    out = SRSPCA().run({"image": item}, BlockConfig(params={"n_components": 3, "scale": False}))
    coll = cast(Collection, out["pc_maps"])
    maps = list(coll)
    assert len(maps) == 3
    for img in maps:
        assert img.axes == ["y", "x"]
    assert cast(DataFrame, out["loadings"]).row_count == 3


def test_pca_scale_toggle_changes_result() -> None:
    cube, _, _ = _synthetic_mixture(seed=21, n_w=10)
    item = _make_srs_image(cube)
    scaled = SRSPCA().run({"image": item}, BlockConfig(params={"n_components": 2, "scale": True}))
    unscaled = SRSPCA().run({"image": item}, BlockConfig(params={"n_components": 2, "scale": False}))
    s = next(iter(cast(Collection, scaled["pc_maps"])))._data  # type: ignore[attr-defined]
    u = next(iter(cast(Collection, unscaled["pc_maps"])))._data  # type: ignore[attr-defined]
    assert not np.allclose(s, u)


def test_pca_loadings_index_is_pc_id() -> None:
    cube, _, _ = _synthetic_mixture(seed=22)
    item = _make_srs_image(cube)
    out = SRSPCA().run({"image": item}, BlockConfig(params={"n_components": 2}))
    loadings = cast(DataFrame, out["loadings"])
    assert loadings.columns is not None and loadings.columns[0] == "pc_id"


def test_pca_n_components_too_large_raises() -> None:
    cube, _, _ = _synthetic_mixture(seed=23, n_w=4)
    item = _make_srs_image(cube)
    with pytest.raises(ValueError, match="exceeds n_wavenumbers"):
        SRSPCA().run({"image": item}, BlockConfig(params={"n_components": 99}))


# ---------------------------------------------------------------------------
# T-SRS-009 — SRSICA
# ---------------------------------------------------------------------------


def test_ica_smoke_3components() -> None:
    cube, _, _ = _synthetic_mixture(seed=30, n_endmembers=3, y=6, x=6, n_w=12)
    item = _make_srs_image(cube)
    out = SRSICA().run({"image": item}, BlockConfig(params={"n_components": 3}))
    maps = list(cast(Collection, out["ic_maps"]))
    assert len(maps) == 3
    for img in maps:
        assert img.axes == ["y", "x"]
    assert cast(DataFrame, out["components"]).row_count == 3


def test_ica_components_index_is_ic_id() -> None:
    cube, _, _ = _synthetic_mixture(seed=31)
    item = _make_srs_image(cube)
    out = SRSICA().run({"image": item}, BlockConfig(params={"n_components": 2}))
    comps = cast(DataFrame, out["components"])
    assert comps.columns is not None and comps.columns[0] == "ic_id"


def test_ica_rejects_unknown_method() -> None:
    cube, _, _ = _synthetic_mixture(seed=32)
    item = _make_srs_image(cube)
    with pytest.raises(ValueError, match="method must be"):
        SRSICA().run({"image": item}, BlockConfig(params={"n_components": 2, "method": "infomax"}))


# ---------------------------------------------------------------------------
# T-SRS-010 — SRSKMeansCluster
# ---------------------------------------------------------------------------


def test_kmeans_smoke_3clusters() -> None:
    cube, _, _ = _synthetic_mixture(seed=40, n_endmembers=3, y=6, x=6, n_w=10)
    item = _make_srs_image(cube)
    out = SRSKMeansCluster().run({"image": item}, BlockConfig(params={"n_clusters": 3, "n_init": 3}))
    label_obj = out["labels"]
    assert isinstance(label_obj, Label)
    raster = label_obj.slots["raster"]
    data = raster._data  # type: ignore[attr-defined]
    assert data.dtype == np.int32
    assert set(np.unique(data).tolist()).issubset({0, 1, 2})
    centroids = cast(DataFrame, out["centroids"])
    assert centroids.row_count == 3
    assert centroids.columns is not None and centroids.columns[0] == "cluster_id"


def test_kmeans_init_random_accepted() -> None:
    cube, _, _ = _synthetic_mixture(seed=41, y=5, x=5, n_w=8, n_endmembers=2)
    item = _make_srs_image(cube)
    out = SRSKMeansCluster().run(
        {"image": item},
        BlockConfig(params={"n_clusters": 2, "init": "random", "n_init": 3}),
    )
    assert isinstance(out["labels"], Label)


def test_kmeans_rejects_bad_init() -> None:
    cube, _, _ = _synthetic_mixture(seed=42, y=5, x=5, n_w=6, n_endmembers=2)
    item = _make_srs_image(cube)
    with pytest.raises(ValueError, match="init must be"):
        SRSKMeansCluster().run(
            {"image": item},
            BlockConfig(params={"n_clusters": 2, "init": "bogus"}),
        )
