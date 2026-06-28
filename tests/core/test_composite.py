"""Tests for CompositeData slot access and nested composites (Phase 3.1).

T-006 (ADR-027 D2) removed ``Image`` from core. T-007 additionally
removed ``AnnData`` and ``SpatialData``. Tests that need those names
define local shim subclasses below. Full migration is T-008.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame


class Image(Array):
    """T-006 shim — plugin migration tracked by T-008."""

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})

    def __init__(
        self,
        *,
        shape: tuple[int, ...] | None = None,
        ndim: int | None = None,
        dtype: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(axes=["y", "x"], shape=shape, dtype=dtype, **kwargs)


class AnnData(CompositeData):
    """T-007 shim for the removed core ``AnnData`` class."""

    expected_slots: ClassVar[dict[str, type]] = {
        "X": Array,
        "obs": DataFrame,
        "var": DataFrame,
        "uns": Artifact,
    }


class SpatialData(CompositeData):
    """T-007 shim for the removed core ``SpatialData`` class."""

    expected_slots: ClassVar[dict[str, type]] = {
        "images": Array,
        "points": DataFrame,
        "shapes": DataFrame,
        "table": AnnData,
    }


class TestCompositeDataSlotAccess:
    """Verify get, set, slot_types, and slot_names."""

    def test_set_and_get(self) -> None:
        comp = CompositeData()
        # The deprecated ``metadata=`` constructor kwarg was removed in the
        # ADR-052 §16 cleanup; construct a plain DataObject (slot identity is
        # what this test pins, not provenance).
        obj = DataObject()
        comp.set("my_slot", obj)
        assert comp.get("my_slot") is obj

    def test_get_missing_raises(self) -> None:
        comp = CompositeData()
        with pytest.raises(KeyError, match="not populated"):
            comp.get("nonexistent")

    def test_slot_names_empty(self) -> None:
        comp = CompositeData()
        assert comp.slot_names == []

    def test_slot_names_populated(self) -> None:
        comp = CompositeData()
        comp.set("a", DataObject())
        comp.set("b", DataObject())
        assert sorted(comp.slot_names) == ["a", "b"]

    def test_slot_types_base_empty(self) -> None:
        comp = CompositeData()
        assert comp.slot_types() == {}

    def test_init_with_slots(self) -> None:
        obj_a = DataObject()
        obj_b = DataObject()
        comp = CompositeData(slots={"a": obj_a, "b": obj_b})
        assert comp.get("a") is obj_a
        assert comp.get("b") is obj_b


class TestAnnDataSlots:
    """Verify AnnData expected_slots and type validation."""

    def test_slot_types(self) -> None:
        ad = AnnData()
        types = ad.slot_types()
        assert "X" in types
        assert types["X"] is Array
        assert types["obs"] is DataFrame
        assert types["var"] is DataFrame

    def test_set_valid_slot(self) -> None:
        ad = AnnData()
        x = Array(axes=["y", "x"], shape=(100, 50), dtype="float64")
        obs = DataFrame(columns=["cell_type"], row_count=100)
        ad.set("X", x)
        ad.set("obs", obs)
        assert ad.get("X") is x
        assert ad.get("obs") is obs

    def test_set_invalid_type_raises(self) -> None:
        ad = AnnData()
        wrong = DataFrame(columns=["a"])  # Not an Array
        with pytest.raises(TypeError, match="expects Array"):
            ad.set("X", wrong)

    def test_set_subtype_accepted(self) -> None:
        """Image is a subtype of Array, so it should be accepted for X."""
        ad = AnnData()
        img = Image(shape=(100, 100))
        ad.set("X", img)
        assert ad.get("X") is img

    def test_dtype_info_slot_schema(self) -> None:
        ad = AnnData()
        sig = ad.dtype_info
        assert sig.slot_schema is not None
        assert "X" in sig.slot_schema
        assert sig.slot_schema["X"] == "Array"


class TestSpatialDataSlots:
    """Verify SpatialData expected_slots."""

    def test_slot_types(self) -> None:
        sd = SpatialData()
        types = sd.slot_types()
        assert "images" in types
        assert "points" in types
        assert "table" in types
        assert types["table"] is AnnData

    def test_set_anndata_in_table_slot(self) -> None:
        sd = SpatialData()
        ad = AnnData()
        sd.set("table", ad)
        assert sd.get("table") is ad


class TestNestedComposites:
    """Verify nested composites: SpatialData containing AnnData."""

    def test_nested_access(self) -> None:
        ad = AnnData()
        x = Array(axes=["y", "x"], shape=(100, 50), dtype="float64")
        obs = DataFrame(columns=["cell_type"], row_count=100)
        ad.set("X", x)
        ad.set("obs", obs)

        sd = SpatialData()
        images = Array(axes=["y", "x", "c"], shape=(1024, 1024, 3))
        points = DataFrame(columns=["x", "y", "z"])
        sd.set("images", images)
        sd.set("points", points)
        sd.set("table", ad)

        # Accessing nested: SpatialData -> table -> X
        inner_ad = sd.get("table")
        assert isinstance(inner_ad, AnnData)
        inner_x = inner_ad.get("X")
        assert inner_x is x
        assert inner_x.shape == (100, 50)

    def test_nested_dtype_info(self) -> None:
        sd = SpatialData()
        sig = sd.dtype_info
        assert sig.type_chain == ["DataObject", "CompositeData", "SpatialData"]
        assert sig.slot_schema is not None
        assert sig.slot_schema["table"] == "AnnData"


class TestCompositeInitValidation:
    """Verify constructor validates slots against expected_slots."""

    def test_init_with_invalid_slot_type_raises(self) -> None:
        wrong = DataFrame(columns=["a"])
        with pytest.raises(TypeError, match="expects Array"):
            AnnData(slots={"X": wrong})

    def test_init_with_valid_slots_succeeds(self) -> None:
        x = Array(axes=["y", "x"], shape=(10, 5), dtype="float64")
        obs = DataFrame(columns=["cell"], row_count=10)
        ad = AnnData(slots={"X": x, "obs": obs})
        assert ad.get("X") is x
        assert ad.get("obs") is obs


class TestAnnDataUnsType:
    """Verify AnnData uns slot expects Artifact."""

    def test_uns_expected_type_is_artifact(self) -> None:
        ad = AnnData()
        assert ad.slot_types()["uns"] is Artifact

    def test_uns_rejects_dataframe(self) -> None:
        ad = AnnData()
        df = DataFrame(columns=["a"])
        with pytest.raises(TypeError):
            ad.set("uns", df)
