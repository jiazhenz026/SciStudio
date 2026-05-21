"""Tests for T-IMG-001 imaging type classes."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError
from scistudio_blocks_imaging import get_types
from scistudio_blocks_imaging.types import Image, Label, Mask, Transform

from scistudio.core.meta import ChannelInfo
from scistudio.core.types.array import Array
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.registry import TypeRegistry
from scistudio.core.types.serialization import _reconstruct_one, _serialise_one
from scistudio.core.units import PhysicalQuantity


def _image_meta() -> Image.Meta:
    return Image.Meta(
        pixel_size=PhysicalQuantity(0.108, "um"),
        z_spacing=PhysicalQuantity(0.5, "um"),
        time_interval=PhysicalQuantity(1.0, "s"),
        channels=[ChannelInfo(name="DAPI"), ChannelInfo(name="GFP", excitation_nm=488.0)],
        wavelengths_nm=[405.0, 488.0],
        objective="20x",
        source_file="sample.tif",
        instrument="scope-1",
    )


class TestImage:
    def test_image_required_axes_yx(self) -> None:
        assert Image.required_axes == frozenset({"y", "x"})

    def test_image_allowed_axes_full_alphabet(self) -> None:
        assert Image.allowed_axes == frozenset({"t", "z", "c", "lambda", "y", "x"})

    def test_image_2d_construction(self) -> None:
        image = Image(axes=["y", "x"], shape=(8, 8), dtype=np.float32)
        assert image.axes == ["y", "x"]
        assert image.shape == (8, 8)

    def test_image_3d_zyx_construction(self) -> None:
        image = Image(axes=["z", "y", "x"], shape=(3, 8, 8), dtype=np.uint16)
        assert image.axes == ["z", "y", "x"]
        assert image.shape == (3, 8, 8)

    def test_image_5d_tzcyx_construction(self) -> None:
        image = Image(axes=["t", "z", "c", "y", "x"], shape=(2, 3, 4, 8, 8), dtype=np.float32)
        assert image.ndim == 5

    def test_image_6d_tzclambdayx_construction(self) -> None:
        image = Image(axes=["t", "z", "c", "lambda", "y", "x"], shape=(1, 2, 3, 4, 8, 8), dtype=np.float32)
        assert image.ndim == 6

    def test_image_invalid_axis_raises(self) -> None:
        with pytest.raises(ValueError, match="accepts only"):
            Image(axes=["q", "y", "x"], shape=(1, 8, 8), dtype=np.float32)

    def test_image_missing_required_axis_raises(self) -> None:
        with pytest.raises(ValueError, match="requires axes"):
            Image(axes=["y"], shape=(8,), dtype=np.float32)

    def test_image_meta_pixel_size_pq_round_trip(self) -> None:
        meta = Image.Meta(pixel_size=PhysicalQuantity(0.108, "um"))
        dumped = meta.model_dump_json()
        restored = Image.Meta.model_validate_json(dumped)
        assert restored.pixel_size == PhysicalQuantity(0.108, "um")

    def test_image_meta_channels_list_channel_info(self) -> None:
        meta = Image.Meta(channels=[ChannelInfo(name="DAPI"), ChannelInfo(name="GFP")])
        assert meta.channels is not None
        assert meta.channels[0].name == "DAPI"

    def test_image_meta_channels_string_names_coerce_to_channel_info(self) -> None:
        meta = Image.Meta(channels=["c0", "c1"])
        assert meta.channels is not None
        assert [channel.name for channel in meta.channels] == ["c0", "c1"]

    def test_image_meta_json_round_trip(self) -> None:
        meta = _image_meta()
        restored = Image.Meta.model_validate_json(meta.model_dump_json())
        assert restored == meta

    def test_image_serialise_reconstruct_round_trip(self) -> None:
        import scistudio.core.types.serialization as serialization_module

        registry = TypeRegistry()
        registry.scan_builtins()
        registry.register_class(Image)
        previous_registry = serialization_module._registry_instance
        serialization_module._registry_instance = registry
        try:
            image = Image(axes=["t", "z", "y", "x"], shape=(2, 3, 8, 8), dtype=np.float32, meta=_image_meta())
            payload = _serialise_one(image)
            restored = _reconstruct_one(payload)
        finally:
            serialization_module._registry_instance = previous_registry

        assert type(restored) is Image
        assert restored.axes == image.axes
        assert restored.meta == image.meta


class TestMask:
    def test_mask_dtype_bool_required(self) -> None:
        mask = Mask(axes=["y", "x"], shape=(4, 4), dtype=bool)
        assert mask.axes == ["y", "x"]
        assert mask.dtype == bool

    def test_mask_dtype_float_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="dtype=bool"):
            Mask(axes=["y", "x"], shape=(4, 4), dtype="float32")

    def test_mask_inherits_image_axes(self) -> None:
        assert issubclass(Mask, Image)
        assert Mask.required_axes == Image.required_axes


class TestLabel:
    def test_label_expected_slots(self) -> None:
        assert Label.expected_slots == {"raster": Array, "polygons": DataFrame}

    def test_label_with_raster_only(self) -> None:
        raster = Array(axes=["y", "x"], shape=(4, 4), dtype=np.int32)
        label = Label(slots={"raster": raster})
        assert label.slots["raster"] is raster

    def test_label_with_polygons_only(self) -> None:
        polygons = DataFrame(columns=["x", "y"], row_count=2)
        label = Label(slots={"polygons": polygons})
        assert label.slots["polygons"] is polygons

    def test_label_with_both_slots(self) -> None:
        raster = Array(axes=["y", "x"], shape=(4, 4), dtype=np.int32)
        polygons = DataFrame(columns=["x", "y"], row_count=2)
        label = Label(slots={"raster": raster, "polygons": polygons})
        assert set(label.slots) == {"raster", "polygons"}

    def test_label_neither_slot_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            Label(slots={})

    def test_label_meta_round_trip(self) -> None:
        meta = Label.Meta(source_file="labels.tif", n_objects=5)
        restored = Label.Meta.model_validate_json(meta.model_dump_json())
        assert restored == meta


class TestTransform:
    def test_transform_2d_affine_shape(self) -> None:
        transform = Transform(
            axes=["row", "col"],
            shape=(2, 3),
            dtype=np.float32,
            meta=Transform.Meta(transform_type="affine"),
        )
        assert transform.shape == (2, 3)

    def test_transform_3d_affine_shape(self) -> None:
        transform = Transform(
            axes=["row", "col"],
            shape=(3, 3),
            dtype=np.float32,
            meta=Transform.Meta(transform_type="rigid"),
        )
        assert transform.shape == (3, 3)

    def test_transform_meta_transform_type_required(self) -> None:
        with pytest.raises(ValidationError):
            Transform.Meta()


class TestPluginEntryPoint:
    def test_get_types_returns_four_classes(self) -> None:
        assert get_types() == [Image, Mask, Label, Transform]
