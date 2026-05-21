"""Sprint C imaging continuation B — skeleton stub tests (T-IMG-021..037).

Each test asserts the skeleton class exists and inherits from the
expected base. Behavioural tests are deferred to the impl agent and
marked via ``pytest.skip``.
"""

from __future__ import annotations

import sys

import numpy as np
import pyarrow as pa
import pytest

from scistudio.blocks.app.app_block import AppBlock
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.state import BlockState
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection


# ── T-IMG-021 ──────────────────────────────────────────────────────────
def test_t_img_021_connected_components_class() -> None:
    from scistudio_blocks_imaging.segmentation.connected_components import (
        ConnectedComponents,
    )

    assert issubclass(ConnectedComponents, ProcessBlock)
    assert ConnectedComponents.type_name == "imaging.connected_components"


def test_t_img_021_4_conn_label() -> None:
    from scistudio_blocks_imaging.segmentation.connected_components import (
        ConnectedComponents,
    )
    from scistudio_blocks_imaging.types import Mask

    arr = np.zeros((5, 5), dtype=bool)
    arr[1, 1] = True
    arr[2, 2] = True

    mask = Mask(axes=["y", "x"], shape=arr.shape, dtype=bool)
    mask._data = arr  # type: ignore[attr-defined]
    label = ConnectedComponents().process_item(mask, BlockConfig(params={"connectivity": 1}))

    assert label.meta is not None
    assert label.meta.n_objects == 2


def test_t_img_021_8_conn_label() -> None:
    from scistudio_blocks_imaging.segmentation.connected_components import (
        ConnectedComponents,
    )
    from scistudio_blocks_imaging.types import Mask

    arr = np.zeros((5, 5), dtype=bool)
    arr[1, 1] = True
    arr[2, 2] = True

    mask = Mask(axes=["y", "x"], shape=arr.shape, dtype=bool)
    mask._data = arr  # type: ignore[attr-defined]
    label = ConnectedComponents().process_item(mask, BlockConfig(params={"connectivity": 2}))

    assert label.meta is not None
    assert label.meta.n_objects == 1


def test_t_img_021_invalid_connectivity_raises() -> None:
    from scistudio_blocks_imaging.segmentation.connected_components import (
        ConnectedComponents,
    )
    from scistudio_blocks_imaging.types import Mask

    arr = np.ones((4, 4), dtype=bool)
    mask = Mask(axes=["y", "x"], shape=arr.shape, dtype=bool)
    mask._data = arr  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="connectivity"):
        ConnectedComponents().process_item(mask, BlockConfig(params={"connectivity": 3}))


# ── T-IMG-022 ──────────────────────────────────────────────────────────
def test_t_img_022_cleanup_classes() -> None:
    from scistudio_blocks_imaging.segmentation.cleanup import (
        ExpandLabels,
        FillHoles,
        RemoveBorderObjects,
        RemoveSmallObjects,
        ShrinkLabels,
    )

    for cls in (
        RemoveSmallObjects,
        RemoveBorderObjects,
        FillHoles,
        ExpandLabels,
        ShrinkLabels,
    ):
        assert issubclass(cls, ProcessBlock), cls


def test_t_img_022_remove_small_objects_min_size() -> None:
    pytest.importorskip("skimage")
    from scistudio_blocks_imaging.segmentation.cleanup import RemoveSmallObjects
    from scistudio_blocks_imaging.types import Mask

    arr = np.zeros((8, 8), dtype=bool)
    arr[1, 1] = True
    arr[3:7, 3:7] = True
    mask = Mask(axes=["y", "x"], shape=arr.shape, dtype=bool)
    mask._data = arr  # type: ignore[attr-defined]

    result = RemoveSmallObjects().process_item(mask, BlockConfig(params={"min_size": 4}))

    assert np.count_nonzero(np.asarray(result._data)) == 16


def test_t_img_022_fill_holes_basic() -> None:
    pytest.importorskip("scipy")
    from scistudio_blocks_imaging.segmentation.cleanup import FillHoles
    from scistudio_blocks_imaging.types import Mask

    arr = np.ones((7, 7), dtype=bool)
    arr[3, 3] = False
    mask = Mask(axes=["y", "x"], shape=arr.shape, dtype=bool)
    mask._data = arr  # type: ignore[attr-defined]

    result = FillHoles().process_item(mask, BlockConfig(params={}))

    assert bool(np.asarray(result._data)[3, 3]) is True


def test_t_img_022_expand_shrink_labels() -> None:
    pytest.importorskip("skimage")
    from scistudio_blocks_imaging.segmentation.cleanup import ExpandLabels, ShrinkLabels
    from scistudio_blocks_imaging.types import Label

    arr = np.zeros((11, 11), dtype=np.int32)
    arr[4:7, 4:7] = 1
    raster = Array(axes=["y", "x"], shape=arr.shape, dtype=arr.dtype)
    raster._data = arr  # type: ignore[attr-defined]
    label = Label(slots={"raster": raster}, meta=Label.Meta(source_file="label.tif", n_objects=1))

    expanded = ExpandLabels().process_item(label, BlockConfig(params={"distance_px": 2}))
    shrunk = ShrinkLabels().process_item(expanded, BlockConfig(params={"distance_px": 1}))

    assert np.count_nonzero(np.asarray(expanded.slots["raster"]._data)) > np.count_nonzero(arr)
    assert np.count_nonzero(np.asarray(shrunk.slots["raster"]._data)) < np.count_nonzero(
        np.asarray(expanded.slots["raster"]._data)
    )
    assert shrunk.meta is not None
    assert shrunk.meta.source_file == "label.tif"


# ── T-IMG-023 ──────────────────────────────────────────────────────────
def test_t_img_023_track_objects_class() -> None:
    from scistudio_blocks_imaging.tracking.track_objects import TrackObjects

    assert issubclass(TrackObjects, ProcessBlock)


def test_t_img_023_process_item_raises_not_implemented() -> None:
    pytest.skip("T-IMG-023 placeholder; Phase 12 impl pending")


# ── T-IMG-024 ──────────────────────────────────────────────────────────
def test_t_img_024_region_props_class() -> None:
    from scistudio_blocks_imaging.measurement.region_props import RegionProps

    assert issubclass(RegionProps, ProcessBlock)


def test_t_img_024_area_basic() -> None:
    pytest.importorskip("skimage")
    from scistudio_blocks_imaging.measurement.region_props import RegionProps
    from scistudio_blocks_imaging.types import Label

    arr = np.zeros((6, 6), dtype=np.int32)
    arr[1:3, 1:4] = 1
    arr[3:5, 4:6] = 2

    raster = Array(axes=["y", "x"], shape=arr.shape, dtype=arr.dtype)
    raster._data = arr  # type: ignore[attr-defined]
    label = Label(slots={"raster": raster}, meta=Label.Meta(source_file="cells.tif", n_objects=2))

    result = RegionProps().process_item(label, BlockConfig(params={"properties": ["area", "centroid"]}))
    table = result._arrow_table  # type: ignore[attr-defined]
    assert isinstance(table, pa.Table)

    rows = table.to_pylist()
    assert [row["label_id"] for row in rows] == [1, 2]
    assert [row["area"] for row in rows] == [6.0, 4.0]
    assert result.columns == ["label_id", "area", "centroid-0", "centroid-1"]


def test_t_img_024_intensity_image() -> None:
    pytest.importorskip("skimage")
    from scistudio_blocks_imaging.measurement.region_props import RegionProps
    from scistudio_blocks_imaging.types import Image, Label

    label_a_arr = np.zeros((4, 4), dtype=np.int32)
    label_a_arr[1:3, 1:3] = 1
    label_b_arr = np.zeros((4, 4), dtype=np.int32)
    label_b_arr[0:2, 0:2] = 2
    intensity_a_arr = np.zeros((4, 4), dtype=np.float32)
    intensity_a_arr[1:3, 1:3] = 5.0
    intensity_b_arr = np.zeros((4, 4), dtype=np.float32)
    intensity_b_arr[0:2, 0:2] = 9.0

    def _label(data: np.ndarray, source: str, n_objects: int) -> Label:
        raster = Array(axes=["y", "x"], shape=data.shape, dtype=data.dtype)
        raster._data = data  # type: ignore[attr-defined]
        return Label(slots={"raster": raster}, meta=Label.Meta(source_file=source, n_objects=n_objects))

    def _image(data: np.ndarray) -> Image:
        image = Image(axes=["y", "x"], shape=data.shape, dtype=data.dtype)
        image._data = data  # type: ignore[attr-defined]
        return image

    labels = Collection([_label(label_a_arr, "a.tif", 1), _label(label_b_arr, "b.tif", 1)], item_type=Label)
    intensities = Collection([_image(intensity_a_arr), _image(intensity_b_arr)], item_type=Image)

    result = RegionProps().run(
        {"label": labels, "intensity_image": intensities},
        BlockConfig(params={"properties": ["area", "mean_intensity"]}),
    )["properties"]
    rows = result._arrow_table.to_pylist()  # type: ignore[attr-defined]

    assert rows == [
        {"image_index": 0, "label_id": 1, "area": 4.0, "mean_intensity": 5.0},
        {"image_index": 1, "label_id": 2, "area": 4.0, "mean_intensity": 9.0},
    ]


# ── T-IMG-025 ──────────────────────────────────────────────────────────
def test_t_img_025_pairwise_distance_class() -> None:
    from scistudio_blocks_imaging.measurement.pairwise_distance import (
        PairwiseDistance,
    )

    assert issubclass(PairwiseDistance, ProcessBlock)


def test_t_img_025_centroid_metric() -> None:
    pytest.importorskip("skimage")
    from scistudio_blocks_imaging.measurement.pairwise_distance import PairwiseDistance
    from scistudio_blocks_imaging.types import Label

    arr = np.zeros((6, 6), dtype=np.int32)
    arr[0, 0] = 1
    arr[3, 4] = 2

    raster = Array(axes=["y", "x"], shape=arr.shape, dtype=arr.dtype)
    raster._data = arr  # type: ignore[attr-defined]
    label = Label(slots={"raster": raster}, meta=Label.Meta(source_file="dist.tif", n_objects=2))

    result = PairwiseDistance().process_item(label, BlockConfig(params={"metric": "centroid"}))
    rows = result._arrow_table.to_pylist()  # type: ignore[attr-defined]

    assert rows == [{"label_id_a": 1, "label_id_b": 2, "distance": 5.0}]


# ── T-IMG-026 ──────────────────────────────────────────────────────────
def test_t_img_026_colocalization_class() -> None:
    from scistudio_blocks_imaging.measurement.colocalization import Colocalization

    assert issubclass(Colocalization, ProcessBlock)


def test_t_img_026_pearson_basic() -> None:
    from scistudio_blocks_imaging.measurement.colocalization import Colocalization
    from scistudio_blocks_imaging.types import Image, Mask

    a_arr = np.array([[0.0, 1.0], [2.0, 3.0]], dtype=np.float32)
    b_arr = np.array([[0.0, 2.0], [4.0, 6.0]], dtype=np.float32)
    mask_arr = np.array([[False, True], [True, True]], dtype=bool)

    def _image(data: np.ndarray) -> Image:
        image = Image(axes=["y", "x"], shape=data.shape, dtype=data.dtype)
        image._data = data  # type: ignore[attr-defined]
        return image

    mask = Mask(axes=["y", "x"], shape=mask_arr.shape, dtype=bool)
    mask._data = mask_arr  # type: ignore[attr-defined]

    result = Colocalization().run(
        {"channel_a": _image(a_arr), "channel_b": _image(b_arr), "mask": mask},
        BlockConfig(params={"metrics": ["pearson", "manders"]}),
    )["metrics"]
    rows = result._arrow_table.to_pylist()  # type: ignore[attr-defined]

    assert len(rows) == 1
    assert rows[0]["pearson_r"] == pytest.approx(1.0)
    assert rows[0]["manders_m1"] == pytest.approx(1.0)
    assert rows[0]["manders_m2"] == pytest.approx(1.0)


# ── T-IMG-027 ──────────────────────────────────────────────────────────
def test_t_img_027_compute_registration_class() -> None:
    from scistudio_blocks_imaging.registration.compute_registration import (
        ComputeRegistration,
    )

    assert issubclass(ComputeRegistration, ProcessBlock)


def test_t_img_027_phase_correlation() -> None:
    pytest.importorskip("skimage")
    from scistudio_blocks_imaging.registration.compute_registration import (
        ComputeRegistration,
    )
    from scistudio_blocks_imaging.types import Image

    arr = np.zeros((16, 16), dtype=np.float32)
    arr[4:8, 4:8] = 1.0
    moving = np.roll(arr, shift=(2, -1), axis=(0, 1))
    moving_image = Image(axes=["y", "x"], shape=moving.shape, dtype=moving.dtype)
    moving_image._data = moving  # type: ignore[attr-defined]
    fixed_image = Image(axes=["y", "x"], shape=arr.shape, dtype=arr.dtype)
    fixed_image._data = arr  # type: ignore[attr-defined]
    result = ComputeRegistration().run(
        {
            "moving": Collection(items=[moving_image], item_type=Image),
            "fixed": Collection(items=[fixed_image], item_type=Image),
        },
        BlockConfig(params={"method": "phase_correlation"}),
    )
    assert result["transform"][0].shape == (2, 3)


# ── T-IMG-028 ──────────────────────────────────────────────────────────
def test_t_img_028_apply_transform_class() -> None:
    from scistudio_blocks_imaging.registration.apply_transform import ApplyTransform

    assert issubclass(ApplyTransform, ProcessBlock)


def test_t_img_028_warp_basic() -> None:
    pytest.importorskip("skimage")
    from scistudio_blocks_imaging.registration.apply_transform import ApplyTransform
    from scistudio_blocks_imaging.types import Image, Transform

    arr = np.zeros((10, 10), dtype=np.float32)
    arr[3:5, 3:5] = 1.0
    image = Image(axes=["y", "x"], shape=arr.shape, dtype=arr.dtype)
    image._data = arr  # type: ignore[attr-defined]
    transform = Transform(
        axes=["row", "col"],
        shape=(2, 3),
        dtype=np.float64,
        meta=Transform.Meta(transform_type="affine"),
    )
    transform._data = np.asarray([[1.0, 0.0, 1.0], [0.0, 1.0, 0.0]], dtype=np.float64)  # type: ignore[attr-defined]

    result = ApplyTransform().run(
        {
            "image": Collection(items=[image], item_type=Image),
            "transform": Collection(items=[transform], item_type=Transform),
        },
        BlockConfig(params={"interpolation": "nearest"}),
    )
    assert result["warped"][0].shape == (10, 10)


# ── T-IMG-029 ──────────────────────────────────────────────────────────
def test_t_img_029_register_series_class() -> None:
    from scistudio_blocks_imaging.registration.register_series import RegisterSeries

    assert issubclass(RegisterSeries, ProcessBlock)


def test_t_img_029_align_to_reference() -> None:
    pytest.importorskip("skimage")
    from scistudio_blocks_imaging.registration.register_series import RegisterSeries
    from scistudio_blocks_imaging.types import Image

    base = np.zeros((12, 12), dtype=np.float32)
    base[4:8, 4:8] = 1.0
    shifted = np.roll(base, shift=(1, 2), axis=(0, 1))
    series = Image(axes=["t", "y", "x"], shape=(2, 12, 12), dtype=np.float32)
    series._data = np.stack([base, shifted], axis=0)  # type: ignore[attr-defined]

    result = RegisterSeries().run(
        {"series": Collection(items=[series], item_type=Image)},
        BlockConfig(params={"axis": "t", "reference_frame": 0}),
    )
    assert result["registered"][0].shape == (2, 12, 12)


# ── T-IMG-030 ──────────────────────────────────────────────────────────
def test_t_img_030_projection_classes() -> None:
    from scistudio_blocks_imaging.projection.projection import (
        AxisProjection,
        SelectSlice,
    )

    for cls in (AxisProjection, SelectSlice):
        assert issubclass(cls, ProcessBlock), cls


def test_t_img_030_axis_projection_max() -> None:
    from scistudio_blocks_imaging.projection.projection import AxisProjection
    from scistudio_blocks_imaging.types import Image

    image = Image(axes=["z", "y", "x"], shape=(2, 4, 4), dtype=np.float32)
    image._data = np.arange(2 * 4 * 4, dtype=np.float32).reshape(2, 4, 4)  # type: ignore[attr-defined]

    projected = AxisProjection().process_item(image, BlockConfig(params={"axis": "z", "method": "max"}))

    assert projected.axes == ["y", "x"]
    assert projected.shape == (4, 4)


def test_t_img_030_select_slice_index() -> None:
    from scistudio_blocks_imaging.projection.projection import SelectSlice
    from scistudio_blocks_imaging.types import Image

    image = Image(axes=["c", "y", "x"], shape=(2, 4, 4), dtype=np.float32)
    image._data = np.arange(2 * 4 * 4, dtype=np.float32).reshape(2, 4, 4)  # type: ignore[attr-defined]

    selected = SelectSlice().process_item(image, BlockConfig(params={"axis": "c", "index": 1}))

    assert selected.axes == ["y", "x"]
    assert selected.shape == (4, 4)


# ── T-IMG-031 ──────────────────────────────────────────────────────────
def test_t_img_031_scalar_op_classes() -> None:
    from scistudio_blocks_imaging.math.scalar_ops import (
        AddScalar,
        DivideScalar,
        MultiplyScalar,
        SubtractScalar,
    )

    for cls in (AddScalar, SubtractScalar, MultiplyScalar, DivideScalar):
        assert issubclass(cls, ProcessBlock), cls


def test_t_img_031_add_subtract_basic() -> None:
    from scistudio_blocks_imaging.math.scalar_ops import AddScalar, SubtractScalar
    from scistudio_blocks_imaging.types import Image

    image = Image(axes=["y", "x"], shape=(2, 2), dtype=np.float32)
    image._data = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)  # type: ignore[attr-defined]

    added = AddScalar().process_item(image, BlockConfig(params={"value": 1.0}))
    subtracted = SubtractScalar().process_item(image, BlockConfig(params={"value": 1.0}))

    assert np.array_equal(added._data, np.array([[2.0, 3.0], [4.0, 5.0]], dtype=np.float32))
    assert np.array_equal(subtracted._data, np.array([[0.0, 1.0], [2.0, 3.0]], dtype=np.float32))


def test_t_img_031_divide_by_zero_raises() -> None:
    from scistudio_blocks_imaging.math.scalar_ops import DivideScalar
    from scistudio_blocks_imaging.types import Image

    image = Image(axes=["y", "x"], shape=(1, 1), dtype=np.float32)
    image._data = np.array([[1.0]], dtype=np.float32)  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="non-zero"):
        DivideScalar().process_item(image, BlockConfig(params={"value": 0.0, "epsilon": 0.0}))


# ── T-IMG-032 ──────────────────────────────────────────────────────────
def test_t_img_032_image_calculator_class() -> None:
    from scistudio_blocks_imaging.math.image_calculator import ImageCalculator

    assert issubclass(ImageCalculator, ProcessBlock)
    assert len(ImageCalculator.input_ports) == 2  # 2-port FIXED


def test_t_img_032_simple_expression() -> None:
    from scistudio_blocks_imaging.math.image_calculator import ImageCalculator
    from scistudio_blocks_imaging.types import Image

    left = Image(axes=["y", "x"], shape=(2, 2), dtype=np.float32)
    left._data = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)  # type: ignore[attr-defined]
    right = Image(axes=["y", "x"], shape=(2, 2), dtype=np.float32)
    right._data = np.array([[4.0, 3.0], [2.0, 1.0]], dtype=np.float32)  # type: ignore[attr-defined]

    result = ImageCalculator().run({"a": left, "b": right}, BlockConfig(params={"expression": "a - b"}))

    assert np.array_equal(result["result"]._data, np.array([[-3.0, -1.0], [1.0, 3.0]], dtype=np.float32))


def test_t_img_032_invalid_expression_raises() -> None:
    from scistudio_blocks_imaging.math.image_calculator import ImageCalculator
    from scistudio_blocks_imaging.types import Image

    left = Image(axes=["y", "x"], shape=(1, 1), dtype=np.float32)
    left._data = np.array([[1.0]], dtype=np.float32)  # type: ignore[attr-defined]
    right = Image(axes=["y", "x"], shape=(1, 1), dtype=np.float32)
    right._data = np.array([[1.0]], dtype=np.float32)  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="forbidden"):
        ImageCalculator().run({"a": left, "b": right}, BlockConfig(params={"expression": "abs(a)"}))


# ── T-IMG-033 ──────────────────────────────────────────────────────────
def test_t_img_033_render_classes() -> None:
    from scistudio_blocks_imaging.visualization.render import (
        RenderHistogram,
        RenderMontage,
        RenderMovie,
        RenderOverlay,
        RenderPseudoColor,
    )

    for cls in (
        RenderPseudoColor,
        RenderOverlay,
        RenderMontage,
        RenderMovie,
        RenderHistogram,
    ):
        assert issubclass(cls, ProcessBlock), cls


def test_t_img_033_pseudo_color_lut() -> None:
    pytest.importorskip("matplotlib")
    from scistudio_blocks_imaging.types import Image
    from scistudio_blocks_imaging.visualization.render import RenderPseudoColor

    image = Image(axes=["y", "x"], shape=(4, 4), dtype=np.float32)
    image._data = np.arange(16, dtype=np.float32).reshape(4, 4)  # type: ignore[attr-defined]

    artifact = RenderPseudoColor().process_item(image, BlockConfig(params={"lut": "viridis"}))

    assert artifact.mime_type == "image/png"
    assert artifact.file_path is not None
    assert artifact.file_path.exists()


def test_t_img_033_overlay_alpha() -> None:
    pytest.importorskip("matplotlib")
    from scistudio_blocks_imaging.types import Image, Label
    from scistudio_blocks_imaging.visualization.render import RenderOverlay

    from scistudio.core.types.array import Array

    image = Image(axes=["y", "x"], shape=(4, 4), dtype=np.float32)
    image._data = np.arange(16, dtype=np.float32).reshape(4, 4)  # type: ignore[attr-defined]
    raster = Array(axes=["y", "x"], shape=(4, 4), dtype=np.int32)
    raster._data = np.array([[0, 0, 1, 1], [0, 0, 1, 1], [0, 0, 0, 0], [0, 0, 0, 0]], dtype=np.int32)  # type: ignore[attr-defined]
    label = Label(slots={"raster": raster})

    result = RenderOverlay().run(
        {"image": image, "overlay": label},
        BlockConfig(params={"alpha": 0.8, "outline_only": True}),
    )

    artifact = result["artifact"]
    assert artifact.mime_type == "image/png"
    assert artifact.file_path is not None
    assert artifact.file_path.exists()


# ── T-IMG-034 ──────────────────────────────────────────────────────────
def test_t_img_034_fiji_block_class() -> None:
    from scistudio_blocks_imaging.interactive.fiji_block import FijiBlock

    assert issubclass(FijiBlock, AppBlock)
    assert FijiBlock.app_command == r"C:\Program Files\Fiji\fiji-windows-x64.exe"


def test_t_img_034_run_routes_outputs(tmp_path) -> None:
    from scistudio_blocks_imaging.interactive.fiji_block import FijiBlock
    from scistudio_blocks_imaging.types import Image

    script = tmp_path / "fake_fiji.py"
    script.write_text(
        """
from pathlib import Path
import shutil
import sys

exchange = Path(sys.argv[-1])
source = next((exchange / "inputs").glob("*.tif"))
target = exchange / "outputs" / "image_reviewed.tif"
target.parent.mkdir(exist_ok=True)
shutil.copyfile(source, target)
""".strip(),
        encoding="utf-8",
    )

    block = FijiBlock()
    block.transition(BlockState.READY)
    block.transition(BlockState.RUNNING)
    image = Image(axes=["y", "x"], shape=(3, 3), dtype=np.uint8)
    image._data = np.arange(9, dtype=np.uint8).reshape(3, 3)  # type: ignore[attr-defined]

    result = block.run(
        {"image": Collection(items=[image], item_type=Image)},
        BlockConfig(params={"app_command": [sys.executable, str(script)], "watch_timeout": 5}),
    )

    assert "image" in result


# ── T-IMG-035 ──────────────────────────────────────────────────────────
def test_t_img_035_napari_block_class() -> None:
    from scistudio_blocks_imaging.interactive.napari_block import NapariBlock

    assert issubclass(NapariBlock, AppBlock)
    assert NapariBlock.app_command == "napari"


def test_t_img_035_run_routes_outputs(tmp_path) -> None:
    from scistudio_blocks_imaging.interactive.napari_block import NapariBlock
    from scistudio_blocks_imaging.types import Image

    script = tmp_path / "fake_napari.py"
    script.write_text(
        """
from pathlib import Path
import shutil
import sys

exchange = Path(sys.argv[-1])
source = next((exchange / "inputs").glob("*.tif"))
target = exchange / "outputs" / "image_layer.tif"
target.parent.mkdir(exist_ok=True)
shutil.copyfile(source, target)
""".strip(),
        encoding="utf-8",
    )

    block = NapariBlock()
    block.transition(BlockState.READY)
    block.transition(BlockState.RUNNING)
    image = Image(axes=["y", "x"], shape=(3, 3), dtype=np.uint8)
    image._data = np.arange(9, dtype=np.uint8).reshape(3, 3)  # type: ignore[attr-defined]

    result = block.run(
        {"image": Collection(items=[image], item_type=Image)},
        BlockConfig(params={"app_command": [sys.executable, str(script)], "watch_timeout": 5}),
    )

    assert "image" in result
