"""ADR-043 / FR-009, FR-010 — imaging ProcessBlock OME propagation tests.

Per spec ``docs/specs/adr-043-package-migration.md``:

- **FR-009** codifies three propagation modes for ``Image.Meta.ome``:

  - **Mode A** — shape-preserving same-type derivation; the block passes
    ``meta=source.meta`` through verbatim (or uses ``iterate_over_axes``
    which propagates ``meta`` by reference per ADR-027 D5).
  - **Mode B** — shape-changing same-type derivation; the block uses a
    transform helper (``_resize_meta``, ``_projected_meta``,
    ``_split_meta``) that MUST rewrite the OME spatial fields to match
    the new shape.
  - **Mode C** — cross-type derivation; the block rebuilds an
    ``OutputClass.Meta(...)``. When the output preserves the source's
    spatial coordinate system (e.g. ``Image -> Label`` from
    segmentation), ``ome`` MUST be among the propagated fields.

- **FR-010** requires every Image-domain ProcessBlock in
  ``scistudio-blocks-imaging`` to comply, with the audit recorded at
  ``docs/audit/adr-043-imaging-propagation-audit.md``.

Each test below pins one (block, mode, ome_decision) cell from the audit
table so future refactors that drop ``ome`` are caught in CI.
"""

from __future__ import annotations

import numpy as np
import pytest
from ome_types.model import OME, Pixels, PixelType
from ome_types.model import Image as OMEImage
from scistudio_blocks_imaging.types import Image, Label, Mask

from scistudio.blocks.base.config import BlockConfig

pytest.importorskip("skimage")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ome(
    *,
    physical_size_x: float = 0.5,
    physical_size_y: float = 0.5,
    size_x: int = 10,
    size_y: int = 20,
    size_c: int = 1,
    size_z: int = 1,
    size_t: int = 1,
) -> OME:
    """Build a minimal OME structure for propagation testing."""
    return OME(
        images=[
            OMEImage(
                pixels=Pixels(
                    size_x=size_x,
                    size_y=size_y,
                    size_c=size_c,
                    size_z=size_z,
                    size_t=size_t,
                    dimension_order="XYCZT",
                    type=PixelType.UINT8,
                    physical_size_x=physical_size_x,
                    physical_size_y=physical_size_y,
                )
            )
        ]
    )


def _make_image(
    arr: np.ndarray,
    *,
    axes: list[str] | None = None,
    ome: OME | None = None,
) -> Image:
    """Build an in-memory Image whose Meta carries the given OME."""
    image = Image(
        axes=axes or ["y", "x"],
        shape=arr.shape,
        dtype=arr.dtype,
        meta=Image.Meta(ome=ome),
    )
    image._data = arr  # type: ignore[attr-defined]
    return image


# ---------------------------------------------------------------------------
# Mode A — shape-preserving same-type derivation (transparent propagation)
# ---------------------------------------------------------------------------


def test_mode_a_image_calculator_propagates_ome() -> None:
    """ImageCalculator (math/) uses ``meta=source.meta`` — ome passes through."""
    from scistudio_blocks_imaging.math.image_calculator import ImageCalculator

    ome = _make_ome(physical_size_x=0.5)
    left = _make_image(np.array([[1.0, 2.0]], dtype=np.float32), ome=ome)
    right = _make_image(np.array([[3.0, 4.0]], dtype=np.float32), ome=ome)

    out = ImageCalculator().run({"a": left, "b": right}, BlockConfig(params={}))
    result = out["result"]

    assert result.meta is not None
    assert result.meta.ome is not None
    # Mode A: the same OME object (or one with the same physical_size_x)
    # propagates verbatim.
    assert result.meta.ome.images[0].pixels.physical_size_x == 0.5


def test_mode_a_add_scalar_propagates_ome() -> None:
    """AddScalar (math/scalar_ops) uses ``meta=source.meta`` — Mode A."""
    from scistudio_blocks_imaging.math.scalar_ops import AddScalar

    ome = _make_ome(physical_size_x=0.7)
    img = _make_image(np.array([[1.0, 2.0]], dtype=np.float32), ome=ome)
    out = AddScalar().process_item(img, BlockConfig(params={"value": 1.0}))

    assert out.meta is not None
    assert out.meta.ome is not None
    assert out.meta.ome.images[0].pixels.physical_size_x == 0.7


def test_mode_a_morphology_propagates_ome_via_iterate_over_axes() -> None:
    """MorphologyOp (morphology/) uses ``iterate_over_axes`` which propagates
    meta by reference per ADR-027 D5. Mode A."""
    from scistudio_blocks_imaging.morphology.morphology_op import MorphologyOp

    ome = _make_ome(physical_size_x=0.3)
    arr = np.zeros((8, 8), dtype=np.float32)
    arr[3:5, 3:5] = 1.0
    img = _make_image(arr, ome=ome)

    out = MorphologyOp().process_item(img, BlockConfig(params={"op": "dilate", "selem_shape": "disk", "selem_size": 1}))

    assert out.meta is not None
    assert out.meta.ome is not None
    assert out.meta.ome.images[0].pixels.physical_size_x == 0.3


def test_mode_a_register_series_propagates_ome() -> None:
    """RegisterSeries uses ``meta=item.meta`` — Mode A propagation."""
    from scistudio_blocks_imaging.registration.register_series import RegisterSeries

    ome = _make_ome(physical_size_x=0.4)
    arr = np.zeros((3, 8, 8), dtype=np.float32)
    arr[:, 3:5, 3:5] = 1.0
    img = _make_image(arr, axes=["t", "y", "x"], ome=ome)

    out = RegisterSeries().run({"series": img}, BlockConfig(params={"axis": "t"}))
    registered = out["registered"][0]

    assert registered.meta is not None
    assert registered.meta.ome is not None
    assert registered.meta.ome.images[0].pixels.physical_size_x == 0.4


# ---------------------------------------------------------------------------
# Mode B — shape-changing same-type derivation (transform helper updates OME)
# ---------------------------------------------------------------------------


def test_mode_b_resize_factor_half_doubles_physical_pixel_size() -> None:
    """Resize(factor=0.5) halves spatial extents -> physical pixel size doubles."""
    from scistudio_blocks_imaging.preprocess.geometry import Resize

    ome = _make_ome(physical_size_x=0.5, physical_size_y=0.5, size_x=10, size_y=20)
    arr = np.arange(20 * 10, dtype=np.float32).reshape(20, 10)
    img = _make_image(arr, ome=ome)

    out = Resize().process_item(img, BlockConfig(params={"factor": 0.5}))

    assert out.meta is not None
    assert out.meta.ome is not None
    pixels = out.meta.ome.images[0].pixels
    assert pixels.size_x == 5
    assert pixels.size_y == 10
    # Halving spatial extent -> doubling physical pixel size (each output
    # pixel covers twice the physical area).
    assert pixels.physical_size_x == pytest.approx(1.0)
    assert pixels.physical_size_y == pytest.approx(1.0)


def test_mode_b_resize_target_shape_updates_ome_size() -> None:
    """Resize(target_shape=...) rewrites OME size_x/size_y to the new shape."""
    from scistudio_blocks_imaging.preprocess.geometry import Resize

    ome = _make_ome(physical_size_x=0.5, physical_size_y=0.5, size_x=10, size_y=20)
    arr = np.arange(20 * 10, dtype=np.float32).reshape(20, 10)
    img = _make_image(arr, ome=ome)

    out = Resize().process_item(img, BlockConfig(params={"target_shape": [10, 5]}))
    pixels = out.meta.ome.images[0].pixels
    assert pixels.size_y == 10
    assert pixels.size_x == 5
    # physical extent preserved -> pixel size scaled by old/new factor.
    assert pixels.physical_size_x == pytest.approx(1.0)
    assert pixels.physical_size_y == pytest.approx(1.0)


def test_mode_b_resize_does_not_mutate_source_ome() -> None:
    """``_resize_meta`` MUST deep-copy the OME so the frozen source Meta is
    not mutated in place."""
    from scistudio_blocks_imaging.preprocess.geometry import Resize

    ome = _make_ome(physical_size_x=0.5, size_x=10, size_y=20)
    arr = np.arange(20 * 10, dtype=np.float32).reshape(20, 10)
    img = _make_image(arr, ome=ome)

    _ = Resize().process_item(img, BlockConfig(params={"factor": 0.5}))

    # Source OME unchanged after resize.
    assert img.meta.ome.images[0].pixels.physical_size_x == 0.5
    assert img.meta.ome.images[0].pixels.size_x == 10
    assert img.meta.ome.images[0].pixels.size_y == 20


def test_mode_b_resize_preserves_ome_none_when_source_has_none() -> None:
    """When source has ``ome=None``, output has ``ome=None`` too."""
    from scistudio_blocks_imaging.preprocess.geometry import Resize

    arr = np.arange(20 * 10, dtype=np.float32).reshape(20, 10)
    img = _make_image(arr, ome=None)
    out = Resize().process_item(img, BlockConfig(params={"factor": 0.5}))
    assert out.meta is not None
    assert out.meta.ome is None


def test_mode_b_axis_projection_along_channel_collapses_size_c() -> None:
    """AxisProjection('c') collapses OME size_c to 1 while preserving other
    pixel-size and dimensional metadata."""
    from scistudio_blocks_imaging.projection.projection import AxisProjection

    ome = _make_ome(physical_size_x=0.5, physical_size_y=0.5, size_c=3, size_x=4, size_y=4)
    arr = np.zeros((3, 4, 4), dtype=np.float32)
    img = _make_image(arr, axes=["c", "y", "x"], ome=ome)

    out = AxisProjection().process_item(img, BlockConfig(params={"axis": "c", "method": "max"}))

    assert out.meta is not None
    assert out.meta.ome is not None
    pixels = out.meta.ome.images[0].pixels
    # Channel axis collapsed.
    assert pixels.size_c == 1
    # In-plane sampling preserved.
    assert pixels.physical_size_x == 0.5
    assert pixels.physical_size_y == 0.5
    assert pixels.size_x == 4
    assert pixels.size_y == 4


def test_mode_b_axis_projection_along_z_collapses_size_z() -> None:
    """AxisProjection('z') collapses OME size_z to 1."""
    from scistudio_blocks_imaging.projection.projection import AxisProjection

    ome = _make_ome(size_z=5, size_x=4, size_y=4)
    arr = np.zeros((5, 4, 4), dtype=np.float32)
    img = _make_image(arr, axes=["z", "y", "x"], ome=ome)

    out = AxisProjection().process_item(img, BlockConfig(params={"axis": "z", "method": "mean"}))
    assert out.meta.ome.images[0].pixels.size_z == 1


def test_mode_b_axis_split_preserves_in_plane_sampling() -> None:
    """AxisSplit propagates OME to every split output with size_<axis> collapsed."""
    from scistudio_blocks_imaging.preprocess.axis_ops import AxisSplit

    ome = _make_ome(physical_size_x=0.5, physical_size_y=0.5, size_c=3)
    arr = np.zeros((3, 4, 4), dtype=np.float32)
    img = _make_image(arr, axes=["c", "y", "x"], ome=ome)

    out = AxisSplit().run({"image": img}, BlockConfig(params={"axis": "c"}))
    items = list(out["images"])
    assert len(items) == 3
    for item in items:
        assert item.meta is not None
        assert item.meta.ome is not None
        pixels = item.meta.ome.images[0].pixels
        assert pixels.size_c == 1
        assert pixels.physical_size_x == 0.5
        assert pixels.physical_size_y == 0.5


# ---------------------------------------------------------------------------
# Mode C — cross-type derivation (per-block ome decision)
# ---------------------------------------------------------------------------


def test_mode_c_threshold_image_to_mask_propagates_ome() -> None:
    """Threshold uses ``meta=result.meta`` (Mask inherits Image, so Image.Meta
    propagates verbatim from the source). The output Mask carries source ome."""
    from scistudio_blocks_imaging.segmentation.threshold import Threshold

    ome = _make_ome(physical_size_x=0.5)
    arr = np.zeros((8, 8), dtype=np.float32)
    arr[3:5, 3:5] = 1.0
    img = _make_image(arr, ome=ome)

    mask = Threshold().process_item(img, BlockConfig(params={"method": "otsu"}))
    assert isinstance(mask, Mask)
    assert mask.meta is not None
    assert mask.meta.ome is not None
    assert mask.meta.ome.images[0].pixels.physical_size_x == 0.5


def test_mode_c_connected_components_label_carries_ome() -> None:
    """ConnectedComponents rebuilds Label.Meta from a Mask source; ome MUST
    propagate because the output Label raster is shape-aligned with the
    source Mask (same axes / spatial coordinate system)."""
    from scistudio_blocks_imaging.segmentation.connected_components import ConnectedComponents

    ome = _make_ome(physical_size_x=0.5)
    arr = np.zeros((8, 8), dtype=bool)
    arr[2:4, 2:4] = True
    arr[5:7, 5:7] = True
    mask = Mask(axes=["y", "x"], shape=arr.shape, dtype=bool, meta=Image.Meta(ome=ome))
    mask._data = arr  # type: ignore[attr-defined]

    label = ConnectedComponents().process_item(mask, BlockConfig(params={"connectivity": 1}))
    assert isinstance(label, Label)
    assert label.meta is not None
    assert label.meta.ome is not None
    assert label.meta.ome.images[0].pixels.physical_size_x == 0.5


def test_mode_c_blob_detect_label_carries_ome() -> None:
    """BlobDetect rebuilds Label.Meta from an Image source; ome MUST propagate."""
    from scistudio_blocks_imaging.segmentation.blob_detect import BlobDetect

    ome = _make_ome(physical_size_x=0.5)
    arr = np.zeros((16, 16), dtype=np.float32)
    arr[7:9, 7:9] = 1.0
    img = _make_image(arr, ome=ome)

    label = BlobDetect().process_item(
        img,
        BlockConfig(params={"method": "LoG", "min_sigma": 1.0, "max_sigma": 5.0, "num_sigma": 3, "threshold": 0.05}),
    )
    assert isinstance(label, Label)
    assert label.meta is not None
    assert label.meta.ome is not None
    assert label.meta.ome.images[0].pixels.physical_size_x == 0.5


def test_mode_c_watershed_label_carries_ome() -> None:
    """Watershed Label output is shape-aligned with the source Image."""
    from scistudio_blocks_imaging.segmentation.watershed import Watershed

    ome = _make_ome(physical_size_x=0.5)
    arr = np.zeros((16, 16), dtype=np.float32)
    arr[4:8, 4:8] = 1.0
    arr[10:14, 10:14] = 1.0
    img = _make_image(arr, ome=ome)

    out = Watershed().run({"image": img}, BlockConfig(params={"method": "distance", "min_distance": 2}))
    label = out["label"][0]
    assert label.meta is not None
    assert label.meta.ome is not None
    assert label.meta.ome.images[0].pixels.physical_size_x == 0.5


def test_mode_c_cleanup_remove_small_objects_propagates_ome_via_model_dump() -> None:
    """RemoveSmallObjects rebuilds Label.Meta via ``model_dump+override``,
    which preserves ``ome`` because the dumped dict round-trips through
    Pydantic validation back to an OME object."""
    from scistudio_blocks_imaging.segmentation.cleanup import RemoveSmallObjects

    from scistudio.core.types.array import Array

    ome = _make_ome(physical_size_x=0.5)
    raster = np.zeros((16, 16), dtype=np.int32)
    raster[2:4, 2:4] = 1
    raster[5:9, 5:9] = 2
    raster_array = Array(axes=["y", "x"], shape=raster.shape, dtype=raster.dtype)
    raster_array._data = raster  # type: ignore[attr-defined]
    label = Label(slots={"raster": raster_array}, meta=Label.Meta(ome=ome, n_objects=2))

    out = RemoveSmallObjects().process_item(label, BlockConfig(params={"min_size": 8}))
    assert isinstance(out, Label)
    assert out.meta is not None
    assert out.meta.ome is not None
    assert out.meta.ome.images[0].pixels.physical_size_x == 0.5


def test_mode_c_legitimate_drop_region_props_returns_dataframe() -> None:
    """RegionProps deliberately drops Image.Meta.ome because its output is a
    DataFrame (per-label measurements have no image coordinate system).

    This test pins the legitimate-drop decision so future refactors don't
    silently add an ome carrier to DataFrame outputs.
    """
    from scistudio_blocks_imaging.measurement.region_props import RegionProps

    from scistudio.core.types.array import Array
    from scistudio.core.types.dataframe import DataFrame

    ome = _make_ome(physical_size_x=0.5)
    raster = np.zeros((8, 8), dtype=np.int32)
    raster[2:4, 2:4] = 1
    raster[5:7, 5:7] = 2
    raster_array = Array(axes=["y", "x"], shape=raster.shape, dtype=raster.dtype)
    raster_array._data = raster  # type: ignore[attr-defined]
    label = Label(slots={"raster": raster_array}, meta=Label.Meta(ome=ome, n_objects=2))

    out = RegionProps().process_item(label, BlockConfig(params={"properties": ["area"]}))
    assert isinstance(out, DataFrame)
    # DataFrame schema has no ``ome`` carrier — Mode C legitimate drop.
    assert not hasattr(out, "ome")


# ---------------------------------------------------------------------------
# Mode C — cross-type derivation with NEW type (deliberate drop is correct)
# ---------------------------------------------------------------------------


def test_mode_c_cellpose_collapses_non_spatial_ome_to_2d() -> None:
    """CellposeSegment reduces non-2D input to a 2D ``(y, x)`` plane via
    ``_center_spatial_slice``. The OME propagated into the output's
    ``Label.Meta`` / ``Image.Meta`` MUST have ``size_t`` / ``size_z`` /
    ``size_c`` collapsed to 1 so the carried metadata is consistent with
    the 2D output raster. Reconciles Codex P1 on PR #1302 (2026-05-20).

    Tests the propagation helper directly because CellposeSegment's
    ``process_item`` requires the ``[cellpose]`` extra at runtime; the
    helper is the load-bearing piece of the P1 fix.
    """
    from scistudio_blocks_imaging.segmentation.cellpose_segment import _collapse_non_spatial_ome_to_2d

    ome = _make_ome(
        physical_size_x=0.5,
        physical_size_y=0.5,
        size_x=128,
        size_y=64,
        size_c=3,
        size_z=10,
        size_t=4,
    )
    collapsed = _collapse_non_spatial_ome_to_2d(ome)
    assert collapsed is not None
    pixels = collapsed.images[0].pixels
    # Non-spatial axes collapsed.
    assert pixels.size_t == 1
    assert pixels.size_z == 1
    assert pixels.size_c == 1
    # In-plane sampling preserved verbatim.
    assert pixels.size_x == 128
    assert pixels.size_y == 64
    assert pixels.physical_size_x == 0.5
    assert pixels.physical_size_y == 0.5
    # Source OME untouched (deep-copy contract).
    assert ome.images[0].pixels.size_t == 4
    assert ome.images[0].pixels.size_z == 10
    assert ome.images[0].pixels.size_c == 3
    # None passes through unchanged.
    assert _collapse_non_spatial_ome_to_2d(None) is None


def test_mode_c_compute_registration_transform_has_no_ome_carrier() -> None:
    """ComputeRegistration outputs a ``Transform`` whose Meta schema has no
    ``ome`` field. The output represents an alignment between two images,
    not an image itself, so dropping ome is correct (FR-009 Mode C
    legitimate drop)."""
    from scistudio_blocks_imaging.registration.compute_registration import ComputeRegistration
    from scistudio_blocks_imaging.types import Transform

    ome = _make_ome(physical_size_x=0.5)
    arr = np.zeros((16, 16), dtype=np.float32)
    arr[3:5, 3:5] = 1.0
    moving = _make_image(arr, ome=ome)
    fixed = _make_image(arr.copy(), ome=ome)

    out = ComputeRegistration().run(
        {"moving": moving, "fixed": fixed},
        BlockConfig(params={"method": "phase_correlation"}),
    )
    transform = out["transform"][0]
    assert isinstance(transform, Transform)
    # Transform.Meta is a sibling schema with no ome field.
    assert "ome" not in Transform.Meta.model_fields
