"""Tests for T-SRS-001 — ``SRSImage`` type and ``Meta`` model."""

from __future__ import annotations

import importlib.metadata

import numpy as np
import pytest
from scistudio_blocks_srs import SRSImage, get_types

from scistudio.core.types.registry import TypeRegistry
from scistudio.core.units import _TIME, PhysicalQuantity


def test_srsimage_subclass_of_image(imaging_types: object) -> None:
    """SRSImage must inherit from imaging plugin's Image."""
    assert issubclass(SRSImage, imaging_types.Image)


def test_srsimage_required_axes() -> None:
    """SRSImage.required_axes == frozenset({'y','x','lambda'})."""
    assert SRSImage.required_axes == frozenset({"y", "x", "lambda"})


def test_srsimage_inherits_allowed_axes_from_image(imaging_types: object) -> None:
    """allowed_axes is inherited (not overridden)."""
    assert SRSImage.allowed_axes == imaging_types.Image.allowed_axes


def test_srsimage_canonical_order() -> None:
    """canonical_order == ('t','z','c','lambda','y','x')."""
    assert SRSImage.canonical_order == ("t", "z", "c", "lambda", "y", "x")


def test_srsimage_construct_minimal() -> None:
    """3D (lambda, y, x) construction succeeds."""
    out = SRSImage(axes=["lambda", "y", "x"], shape=(5, 16, 16), dtype=np.float32)
    assert out.axes == ["lambda", "y", "x"]
    assert out.shape == (5, 16, 16)
    assert out.dtype == np.float32


def test_srsimage_construct_5d() -> None:
    """5D (t, c, lambda, y, x) construction succeeds."""
    out = SRSImage(axes=["t", "c", "lambda", "y", "x"], shape=(2, 3, 4, 8, 8), dtype=np.float64)
    assert out.axes == ["t", "c", "lambda", "y", "x"]
    assert out.shape == (2, 3, 4, 8, 8)


def test_srsimage_missing_lambda_raises() -> None:
    """Constructing without a lambda axis raises via Array._validate_axes."""
    with pytest.raises(ValueError, match="missing"):
        SRSImage(axes=["y", "x"], shape=(16, 16), dtype=np.float32)


def test_srsimage_meta_default_none() -> None:
    """All nine SRS-specific meta fields default to None."""
    meta = SRSImage.Meta()
    assert meta.wavenumbers_cm1 is None
    assert meta.laser_power is None
    assert meta.integration_time is None
    assert meta.digitizer_bit_depth is None
    assert meta.digitizer_voltage_range is None
    assert meta.digitizer_offset is None
    assert meta.digitizer_scale is None
    assert meta.pump_wavelength_nm is None
    assert meta.stokes_wavelength_nm is None


def test_srsimage_meta_with_wavenumbers() -> None:
    """Meta round-trips wavenumbers_cm1 through model_dump_json."""
    meta = SRSImage.Meta(wavenumbers_cm1=[2850.0, 2880.0, 2930.0])
    restored = SRSImage.Meta.model_validate_json(meta.model_dump_json())
    assert restored.wavenumbers_cm1 == [2850.0, 2880.0, 2930.0]


def test_srsimage_meta_with_digitizer_fields() -> None:
    """Meta round-trips all four digitizer_* fields."""
    meta = SRSImage.Meta(
        digitizer_bit_depth=16,
        digitizer_voltage_range=10.0,
        digitizer_offset=0.25,
        digitizer_scale=0.5,
    )
    restored = SRSImage.Meta.model_validate_json(meta.model_dump_json())
    assert restored.digitizer_bit_depth == 16
    assert restored.digitizer_voltage_range == 10.0
    assert restored.digitizer_offset == 0.25
    assert restored.digitizer_scale == 0.5


def test_srsimage_meta_laser_power_float() -> None:
    """laser_power stored as float (mW); future PhysicalQuantity upgrade."""
    meta = SRSImage.Meta(laser_power=12.5)
    assert meta.laser_power == 12.5


def test_srsimage_meta_with_integration_time() -> None:
    """integration_time stored as PhysicalQuantity with time units."""
    assert "ms" in _TIME
    meta = SRSImage.Meta(integration_time=PhysicalQuantity(10.0, "ms"))
    restored = SRSImage.Meta.model_validate_json(meta.model_dump_json())
    assert restored.integration_time == PhysicalQuantity(10.0, "ms")


def test_srsimage_meta_pump_stokes_wavelengths() -> None:
    """pump_wavelength_nm and stokes_wavelength_nm round-trip."""
    meta = SRSImage.Meta(pump_wavelength_nm=800.0, stokes_wavelength_nm=1031.0)
    restored = SRSImage.Meta.model_validate_json(meta.model_dump_json())
    assert restored.pump_wavelength_nm == 800.0
    assert restored.stokes_wavelength_nm == 1031.0


def test_srsimage_with_meta_immutable_update() -> None:
    """Meta is frozen — updates produce new instances (ADR-027 D5)."""
    img = SRSImage(
        axes=["lambda", "y", "x"],
        shape=(3, 8, 8),
        dtype=np.float32,
        meta=SRSImage.Meta(laser_power=4.0),
    )
    updated = img.with_meta(laser_power=6.0)
    assert img.meta is not None
    assert updated.meta is not None
    assert img.meta.laser_power == 4.0
    assert updated.meta.laser_power == 6.0
    assert updated.framework.derived_from == img.framework.object_id


def test_srsimage_in_type_registry_after_scan(monkeypatch: pytest.MonkeyPatch, imaging_types: object) -> None:
    """TypeRegistry.scan() resolves the full type chain to SRSImage."""

    class _FakeEntryPoint:
        name = "phase11-srs-test"

        def load(self):
            return lambda: [imaging_types.Image, SRSImage]

    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda *, group=None: [_FakeEntryPoint()] if group == "scistudio.types" else [],
    )

    registry = TypeRegistry()
    registry.scan_all()

    resolved = registry.resolve(["DataObject", "Array", "Image", "SRSImage"])
    assert resolved is SRSImage


def test_srsimage_wavenumbers_length_matches_lambda_axis() -> None:
    """Metadata wavenumber vectors must match the lambda-axis size when shape is known."""
    with pytest.raises(ValueError, match="lambda axis size"):
        SRSImage(
            axes=["lambda", "y", "x"],
            shape=(2, 4, 4),
            dtype=np.float32,
            meta=SRSImage.Meta(wavenumbers_cm1=[2850.0, 2880.0, 2930.0]),
        )


def test_get_types_returns_srsimage() -> None:
    """Plugin type entry point exports exactly the SRSImage type."""
    assert get_types() == [SRSImage]
