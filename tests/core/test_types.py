"""Tests for DataObject types, TypeSignature, and TypeRegistry (Phase 3.1).

T-006 (ADR-027 D2) removed ``Image``, ``MSImage``, ``SRSImage``, and
``FluorImage`` from ``scistudio.core.types.array``.

T-007 (ADR-027 D2) additionally removed ``Spectrum``, ``RamanSpectrum``,
``MassSpectrum``, ``PeakTable``, ``MetabPeakTable``, ``AnnData``, and
``SpatialData`` — they now belong in the spectral / single-cell /
spatial-omics plugin packages.

This test module keeps its historical coverage by defining local shim
subclasses that mimic the pre-removal constructor surface. The fully
migrated versions of these tests will land in T-008.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pytest

from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject, TypeSignature
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.registry import TypeRegistry, TypeSpec
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

# ---------------------------------------------------------------------------
# T-006 shim: local Image/MSImage/SRSImage/FluorImage subclasses.
# These mirror the pre-T-006 constructor surface to keep existing tests
# running without a full migration sweep (that is T-008's job).
# ---------------------------------------------------------------------------


class Image(Array):
    """T-006 shim for the removed core ``Image`` class.

    Accepts the legacy ``shape=/ndim=/dtype=`` kwargs. Uses
    ``axes=["y", "x"]`` for 2D payloads. TODO(T-008): drop shim and
    migrate tests to ``Array(axes=["y","x"], ...)`` or to the plugin
    ``Image`` once ``scistudio-blocks-imaging`` is available.
    """

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
    allowed_axes: ClassVar[frozenset[str] | None] = frozenset({"t", "z", "c", "lambda", "y", "x"})
    canonical_order: ClassVar[tuple[str, ...]] = ("t", "z", "c", "lambda", "y", "x")

    def __init__(
        self,
        *,
        shape: tuple[int, ...] | None = None,
        ndim: int | None = None,
        dtype: Any = None,
        axes: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(axes=axes if axes is not None else ["y", "x"], shape=shape, dtype=dtype, **kwargs)


class MSImage(Array):
    """T-006 shim for the removed core ``MSImage`` class."""

    def __init__(
        self,
        *,
        shape: tuple[int, ...] | None = None,
        ndim: int | None = None,
        dtype: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(axes=["y", "x", "mz"], shape=shape, dtype=dtype, **kwargs)


class SRSImage(Image):
    """T-006 shim for the removed core ``SRSImage`` class."""

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
    # Permit the legacy ``wavenumber`` axis alongside the 6D alphabet.
    allowed_axes: ClassVar[frozenset[str] | None] = frozenset({"t", "z", "c", "lambda", "y", "x", "wavenumber"})

    def __init__(
        self,
        *,
        shape: tuple[int, ...] | None = None,
        ndim: int | None = None,
        dtype: Any = None,
        **kwargs: Any,
    ) -> None:
        Array.__init__(self, axes=["y", "x", "wavenumber"], shape=shape, dtype=dtype, **kwargs)


class FluorImage(Image):
    """T-006 shim for the removed core ``FluorImage`` class."""

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
    # Permit the legacy discrete ``channel`` axis alongside the 6D alphabet.
    allowed_axes: ClassVar[frozenset[str] | None] = frozenset({"t", "z", "c", "lambda", "y", "x", "channel"})

    def __init__(
        self,
        *,
        shape: tuple[int, ...] | None = None,
        ndim: int | None = None,
        dtype: Any = None,
        **kwargs: Any,
    ) -> None:
        Array.__init__(self, axes=["y", "x", "channel"], shape=shape, dtype=dtype, **kwargs)


# ---------------------------------------------------------------------------
# T-007 shims: local Spectrum / PeakTable / AnnData / SpatialData
# subclasses. These mirror the pre-T-007 behaviour to keep existing
# test coverage running without a full migration sweep (T-008).
# ---------------------------------------------------------------------------


class Spectrum(Series):
    """T-007 shim for the removed core ``Spectrum`` class."""


class RamanSpectrum(Spectrum):
    """T-007 shim for the removed core ``RamanSpectrum`` class."""


class MassSpectrum(Spectrum):
    """T-007 shim for the removed core ``MassSpectrum`` class."""


class PeakTable(DataFrame):
    """T-007 shim for the removed core ``PeakTable`` class."""


class MetabPeakTable(PeakTable):
    """T-007 shim for the removed core ``MetabPeakTable`` class."""


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


# ---------------------------------------------------------------------------
# TypeSignature.from_type
# ---------------------------------------------------------------------------


class TestTypeSignatureFromType:
    """Verify auto-generation of TypeSignature from class MRO."""

    def test_data_object(self) -> None:
        sig = TypeSignature.from_type(DataObject)
        assert sig.type_chain == ["DataObject"]

    def test_array(self) -> None:
        sig = TypeSignature.from_type(Array)
        assert sig.type_chain == ["DataObject", "Array"]

    def test_image(self) -> None:
        sig = TypeSignature.from_type(Image)
        assert sig.type_chain == ["DataObject", "Array", "Image"]

    def test_ms_image(self) -> None:
        sig = TypeSignature.from_type(MSImage)
        assert sig.type_chain == ["DataObject", "Array", "MSImage"]

    def test_srs_image(self) -> None:
        sig = TypeSignature.from_type(SRSImage)
        assert sig.type_chain == ["DataObject", "Array", "Image", "SRSImage"]

    def test_fluor_image(self) -> None:
        sig = TypeSignature.from_type(FluorImage)
        assert sig.type_chain == ["DataObject", "Array", "Image", "FluorImage"]

    def test_series(self) -> None:
        sig = TypeSignature.from_type(Series)
        assert sig.type_chain == ["DataObject", "Series"]

    def test_spectrum(self) -> None:
        sig = TypeSignature.from_type(Spectrum)
        assert sig.type_chain == ["DataObject", "Series", "Spectrum"]

    def test_raman_spectrum(self) -> None:
        sig = TypeSignature.from_type(RamanSpectrum)
        assert sig.type_chain == ["DataObject", "Series", "Spectrum", "RamanSpectrum"]

    def test_mass_spectrum(self) -> None:
        sig = TypeSignature.from_type(MassSpectrum)
        assert sig.type_chain == ["DataObject", "Series", "Spectrum", "MassSpectrum"]

    def test_dataframe(self) -> None:
        sig = TypeSignature.from_type(DataFrame)
        assert sig.type_chain == ["DataObject", "DataFrame"]

    def test_peak_table(self) -> None:
        sig = TypeSignature.from_type(PeakTable)
        assert sig.type_chain == ["DataObject", "DataFrame", "PeakTable"]

    def test_metab_peak_table(self) -> None:
        sig = TypeSignature.from_type(MetabPeakTable)
        assert sig.type_chain == ["DataObject", "DataFrame", "PeakTable", "MetabPeakTable"]

    def test_text(self) -> None:
        sig = TypeSignature.from_type(Text)
        assert sig.type_chain == ["DataObject", "Text"]

    def test_artifact(self) -> None:
        sig = TypeSignature.from_type(Artifact)
        assert sig.type_chain == ["DataObject", "Artifact"]

    def test_composite(self) -> None:
        sig = TypeSignature.from_type(CompositeData)
        assert sig.type_chain == ["DataObject", "CompositeData"]

    def test_anndata(self) -> None:
        sig = TypeSignature.from_type(AnnData)
        assert sig.type_chain == ["DataObject", "CompositeData", "AnnData"]
        assert sig.slot_schema is not None
        assert "X" in sig.slot_schema

    def test_spatial_data(self) -> None:
        sig = TypeSignature.from_type(SpatialData)
        assert sig.type_chain == ["DataObject", "CompositeData", "SpatialData"]
        assert sig.slot_schema is not None
        assert "table" in sig.slot_schema


# ---------------------------------------------------------------------------
# TypeSignature.matches
# ---------------------------------------------------------------------------


class TestTypeSignatureMatches:
    """Verify inheritance-aware type matching."""

    def test_exact_match(self) -> None:
        sig_image = TypeSignature.from_type(Image)
        sig_image2 = TypeSignature.from_type(Image)
        assert sig_image.matches(sig_image2)

    def test_subtype_matches_parent(self) -> None:
        sig_image = TypeSignature.from_type(Image)
        sig_array = TypeSignature.from_type(Array)
        # Image matches a port accepting Array
        assert sig_image.matches(sig_array)

    def test_parent_does_not_match_subtype(self) -> None:
        sig_array = TypeSignature.from_type(Array)
        sig_image = TypeSignature.from_type(Image)
        # Array does NOT match a port requiring Image
        assert not sig_array.matches(sig_image)

    def test_unrelated_types_no_match(self) -> None:
        sig_image = TypeSignature.from_type(Image)
        sig_series = TypeSignature.from_type(Series)
        assert not sig_image.matches(sig_series)

    def test_deep_subtype_matches_root(self) -> None:
        sig_raman = TypeSignature.from_type(RamanSpectrum)
        sig_data = TypeSignature.from_type(DataObject)
        assert sig_raman.matches(sig_data)

    def test_matches_self(self) -> None:
        sig = TypeSignature.from_type(PeakTable)
        assert sig.matches(sig)


# ---------------------------------------------------------------------------
# DataObject.dtype_info property
# ---------------------------------------------------------------------------


class TestDataObjectDtypeInfo:
    """Verify dtype_info auto-generation on instances."""

    def test_array_dtype_info(self) -> None:
        arr = Array(axes=["y", "x"], shape=(10, 10), dtype="float64")
        assert arr.dtype_info.type_chain == ["DataObject", "Array"]

    def test_image_dtype_info(self) -> None:
        img = Image(shape=(1024, 1024), dtype="uint8")
        assert img.dtype_info.type_chain == ["DataObject", "Array", "Image"]

    def test_text_dtype_info(self) -> None:
        txt = Text(content="hello")
        assert txt.dtype_info.type_chain == ["DataObject", "Text"]

    def test_artifact_dtype_info(self) -> None:
        art = Artifact(mime_type="application/pdf")
        assert art.dtype_info.type_chain == ["DataObject", "Artifact"]


# ---------------------------------------------------------------------------
# DataObject metadata
# ---------------------------------------------------------------------------


class TestDataObjectMetadata:
    """Verify the three-slot metadata API (T-005, ADR-027 D5).

    The legacy ``metadata`` dict was migrated to the ``user`` slot.
    The pre-T-005 single-dict tests are now expressed against
    ``obj.user``; the deprecation shim is regression-tested in
    ``tests/core/test_stratified_metadata.py`` and
    ``tests/core/test_dataobject_extended.py``.
    """

    def test_default_user_empty(self) -> None:
        obj = DataObject()
        assert obj.user == {}

    def test_custom_user(self) -> None:
        obj = DataObject(user={"source": "test", "units": "nm"})
        assert obj.user["source"] == "test"
        assert obj.user["units"] == "nm"


# ---------------------------------------------------------------------------
# DataObject.view raises without storage_ref
# ---------------------------------------------------------------------------


class TestDataObjectToMemory:
    """ADR-031 D2: Verify to_memory() requires a storage reference (view() deleted)."""

    def test_to_memory_without_ref_raises(self) -> None:
        obj = DataObject()
        with pytest.raises(ValueError, match="no storage reference"):
            obj.to_memory()


# ---------------------------------------------------------------------------
# TypeRegistry
# ---------------------------------------------------------------------------


class TestTypeRegistry:
    """Verify TypeRegistry registration, lookup, and scanning."""

    def test_register_and_resolve(self) -> None:
        registry = TypeRegistry()
        spec = TypeSpec(name="Image", module_path="scistudio.core.types.array", class_name="Image")
        registry.register("Image", spec)
        resolved = registry.resolve("Image")
        assert resolved.name == "Image"

    def test_resolve_missing_raises(self) -> None:
        registry = TypeRegistry()
        with pytest.raises(KeyError, match="not registered"):
            registry.resolve("Nonexistent")

    def test_all_types(self) -> None:
        registry = TypeRegistry()
        spec = TypeSpec(name="A", module_path="m", class_name="A")
        registry.register("A", spec)
        all_t = registry.all_types()
        assert "A" in all_t
        # Returns a copy
        all_t["B"] = spec
        assert "B" not in registry.all_types()

    def test_scan_builtins(self) -> None:
        registry = TypeRegistry()
        registry.scan_builtins()
        all_t = registry.all_types()
        # T-006 / T-007 / ADR-027 D2: all domain subtypes moved to
        # plugins; scan_builtins only registers the seven core base
        # types (plus DataObject itself).
        assert "DataObject" in all_t
        assert "Array" in all_t
        assert "Series" in all_t
        assert "DataFrame" in all_t
        assert "Text" in all_t
        assert "Artifact" in all_t
        assert "CompositeData" in all_t
        # Domain subtypes are NOT present — they will be re-registered
        # via the ``scistudio.types`` entry-point when the relevant plugin
        # is installed.
        assert "Spectrum" not in all_t
        assert "PeakTable" not in all_t
        assert "AnnData" not in all_t
        assert "SpatialData" not in all_t
        # Exactly the seven core base types plus DataObject.
        assert len(all_t) == 7

    def test_load_class(self) -> None:
        registry = TypeRegistry()
        registry.scan_builtins()
        cls = registry.load_class("Array")
        assert cls is Array

    def test_is_instance(self) -> None:
        registry = TypeRegistry()
        registry.scan_builtins()
        arr = Array(axes=["y", "x"], shape=(10, 10))
        assert registry.is_instance(arr, "Array")
        assert registry.is_instance(arr, "DataObject")
        assert not registry.is_instance(arr, "Series")


# ---------------------------------------------------------------------------
# TypeRegistry entry-point scanning (ADR-025 Phase 2.3)
# ---------------------------------------------------------------------------


class TestTypeRegistryEntryPoints:
    """Verify _scan_entrypoint_types discovers and registers external types."""

    def test_scan_registers_valid_subclass(self) -> None:
        """A well-formed entry-point returning [CustomType] registers the type."""
        from unittest.mock import MagicMock, patch

        class CustomImage(Image):
            """A custom image type from an external package."""

        mock_ep = MagicMock()
        mock_ep.name = "my_plugin"
        mock_ep.load.return_value = lambda: [CustomImage]

        registry = TypeRegistry()
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            registry._scan_entrypoint_types()

        assert "CustomImage" in registry.all_types()
        spec = registry.resolve("CustomImage")
        assert spec.base_type == "Image"

    def test_scan_registers_multiple_types(self) -> None:
        """A single entry-point returning multiple types registers all of them."""
        from unittest.mock import MagicMock, patch

        class TypeA(DataObject):
            """Type A."""

        class TypeB(DataObject):
            """Type B."""

        mock_ep = MagicMock()
        mock_ep.name = "multi"
        mock_ep.load.return_value = lambda: [TypeA, TypeB]

        registry = TypeRegistry()
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            registry._scan_entrypoint_types()

        assert "TypeA" in registry.all_types()
        assert "TypeB" in registry.all_types()

    def test_scan_load_failure_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """An entry-point that fails to load logs a warning and does not crash."""
        from unittest.mock import MagicMock, patch

        mock_ep = MagicMock()
        mock_ep.name = "broken_load"
        mock_ep.load.side_effect = ImportError("no such module")

        registry = TypeRegistry()
        with (
            patch("importlib.metadata.entry_points", return_value=[mock_ep]),
            caplog.at_level("WARNING", logger="scistudio.core.types.registry"),
        ):
            registry._scan_entrypoint_types()

        assert "Failed to load entry-point 'broken_load'" in caplog.text
        assert len(registry.all_types()) == 0

    def test_scan_callable_exception_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """An entry-point whose callable raises logs a warning and does not crash."""
        from unittest.mock import MagicMock, patch

        def bad_factory() -> list[type]:
            raise RuntimeError("boom")

        mock_ep = MagicMock()
        mock_ep.name = "broken_factory"
        mock_ep.load.return_value = bad_factory

        registry = TypeRegistry()
        with (
            patch("importlib.metadata.entry_points", return_value=[mock_ep]),
            caplog.at_level("WARNING", logger="scistudio.core.types.registry"),
        ):
            registry._scan_entrypoint_types()

        assert "Entry-point 'broken_factory' callable raised an exception" in caplog.text
        assert len(registry.all_types()) == 0

    def test_scan_non_list_return_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """An entry-point returning a non-list value logs a warning."""
        from unittest.mock import MagicMock, patch

        mock_ep = MagicMock()
        mock_ep.name = "bad_return"
        mock_ep.load.return_value = lambda: "not a list"

        registry = TypeRegistry()
        with (
            patch("importlib.metadata.entry_points", return_value=[mock_ep]),
            caplog.at_level("WARNING", logger="scistudio.core.types.registry"),
        ):
            registry._scan_entrypoint_types()

        assert "returned str instead of a list" in caplog.text
        assert len(registry.all_types()) == 0

    def test_scan_non_dataobject_subclass_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """An entry-point returning a class not subclassing DataObject logs a warning."""
        from unittest.mock import MagicMock, patch

        class NotADataObject:
            """Just a regular class."""

        mock_ep = MagicMock()
        mock_ep.name = "bad_class"
        mock_ep.load.return_value = lambda: [NotADataObject]

        registry = TypeRegistry()
        with (
            patch("importlib.metadata.entry_points", return_value=[mock_ep]),
            caplog.at_level("WARNING", logger="scistudio.core.types.registry"),
        ):
            registry._scan_entrypoint_types()

        assert "not a DataObject subclass" in caplog.text
        assert len(registry.all_types()) == 0

    def test_scan_non_class_item_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """An entry-point returning a non-class item (e.g. a string) logs a warning."""
        from unittest.mock import MagicMock, patch

        mock_ep = MagicMock()
        mock_ep.name = "bad_item"
        mock_ep.load.return_value = lambda: ["not_a_class"]

        registry = TypeRegistry()
        with (
            patch("importlib.metadata.entry_points", return_value=[mock_ep]),
            caplog.at_level("WARNING", logger="scistudio.core.types.registry"),
        ):
            registry._scan_entrypoint_types()

        assert "not a DataObject subclass" in caplog.text
        assert len(registry.all_types()) == 0

    def test_scan_all_includes_builtins_and_entrypoints(self) -> None:
        """scan_all() registers both builtins and entry-point types."""
        from unittest.mock import MagicMock, patch

        class ExternalType(DataObject):
            """An external type."""

        mock_ep = MagicMock()
        mock_ep.name = "ext"
        mock_ep.load.return_value = lambda: [ExternalType]

        registry = TypeRegistry()
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            registry.scan_all()

        all_t = registry.all_types()
        # Builtins are present. T-006 / ADR-027 D2: Image moved to
        # scistudio-blocks-imaging; Array stays in core.
        assert "Array" in all_t
        assert "DataFrame" in all_t
        # External type is also present
        assert "ExternalType" in all_t

    def test_scan_all_works_with_no_entrypoints(self) -> None:
        """scan_all() works fine when no entry-points exist."""
        from unittest.mock import patch

        registry = TypeRegistry()
        with patch("importlib.metadata.entry_points", return_value=[]):
            registry.scan_all()

        all_t = registry.all_types()
        # T-006 / T-007: core only registers the seven base types plus
        # DataObject; domain subtypes live in plugins.
        assert "Array" in all_t
        assert len(all_t) == 7

    def test_scan_skips_bad_entries_registers_good_ones(self) -> None:
        """Mixed valid/invalid items: good ones register, bad ones are skipped."""
        from unittest.mock import MagicMock, patch

        class GoodType(DataObject):
            """A valid type."""

        class NotAType:
            """Not a DataObject."""

        mock_ep = MagicMock()
        mock_ep.name = "mixed"
        mock_ep.load.return_value = lambda: [GoodType, NotAType, "junk"]

        registry = TypeRegistry()
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            registry._scan_entrypoint_types()

        assert "GoodType" in registry.all_types()
        assert len(registry.all_types()) == 1

    def test_scan_tuple_return_accepted(self) -> None:
        """Entry-point returning a tuple (instead of list) is also accepted."""
        from unittest.mock import MagicMock, patch

        class TupleType(DataObject):
            """Returned as tuple."""

        mock_ep = MagicMock()
        mock_ep.name = "tuple_ep"
        mock_ep.load.return_value = lambda: (TupleType,)

        registry = TypeRegistry()
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            registry._scan_entrypoint_types()

        assert "TupleType" in registry.all_types()


# ---------------------------------------------------------------------------
# TypeSignature slot_schema comparison
# ---------------------------------------------------------------------------


class TestTypeSignatureSlotSchema:
    """Verify slot_schema comparison in TypeSignature.matches()."""

    def test_matching_slot_schema(self) -> None:
        sig_a = TypeSignature(
            type_chain=["DataObject", "CompositeData", "AnnData"],
            slot_schema={"X": "Array", "obs": "DataFrame", "var": "DataFrame", "uns": "Artifact"},
        )
        sig_b = TypeSignature(
            type_chain=["DataObject", "CompositeData"],
            slot_schema={"X": "Array", "obs": "DataFrame"},
        )
        assert sig_a.matches(sig_b)

    def test_mismatched_slot_type_rejects(self) -> None:
        sig_a = TypeSignature(
            type_chain=["DataObject", "CompositeData", "AnnData"],
            slot_schema={"X": "Array", "obs": "DataFrame", "var": "DataFrame", "uns": "Artifact"},
        )
        sig_b = TypeSignature(
            type_chain=["DataObject", "CompositeData"],
            slot_schema={"X": "DataFrame"},
        )
        assert not sig_a.matches(sig_b)

    def test_missing_slot_rejects(self) -> None:
        sig_a = TypeSignature(
            type_chain=["DataObject", "CompositeData"],
            slot_schema={"X": "Array"},
        )
        sig_b = TypeSignature(
            type_chain=["DataObject", "CompositeData"],
            slot_schema={"X": "Array", "Y": "DataFrame"},
        )
        assert not sig_a.matches(sig_b)

    def test_no_slot_schema_on_other_passes(self) -> None:
        sig_a = TypeSignature(
            type_chain=["DataObject", "CompositeData", "AnnData"],
            slot_schema={"X": "Array"},
        )
        sig_b = TypeSignature(type_chain=["DataObject", "CompositeData"])
        assert sig_a.matches(sig_b)

    def test_slot_schema_on_other_but_not_self_rejects(self) -> None:
        sig_a = TypeSignature(type_chain=["DataObject", "CompositeData"])
        sig_b = TypeSignature(
            type_chain=["DataObject", "CompositeData"],
            slot_schema={"X": "Array"},
        )
        assert not sig_a.matches(sig_b)


# ---------------------------------------------------------------------------
# Array.__array__() protocol
# ---------------------------------------------------------------------------


class TestArrayProtocol:
    """Verify Array.__array__() supports np.asarray()."""

    def test_array_protocol_with_storage(self, tmp_path: Path) -> None:
        """Array.__array__() materialises data via storage reference."""
        from scistudio.core.storage.ref import StorageReference
        from scistudio.core.storage.zarr_backend import ZarrBackend

        backend = ZarrBackend()
        data = np.array([[1, 2], [3, 4]], dtype=np.float32)
        ref = StorageReference(backend="zarr", path=str(tmp_path / "test.zarr"))
        backend.write(data, ref)

        arr = Array(axes=["y", "x"], shape=(2, 2), dtype="float32", storage_ref=ref)

        result = np.asarray(arr)
        np.testing.assert_array_equal(result, data)

    def test_array_protocol_dtype_conversion(self, tmp_path: Path) -> None:
        """Array.__array__() respects dtype parameter."""
        from scistudio.core.storage.ref import StorageReference
        from scistudio.core.storage.zarr_backend import ZarrBackend

        backend = ZarrBackend()
        data = np.array([[1, 2], [3, 4]], dtype=np.float32)
        ref = StorageReference(backend="zarr", path=str(tmp_path / "test.zarr"))
        backend.write(data, ref)

        arr = Array(axes=["y", "x"], shape=(2, 2), dtype="float32", storage_ref=ref)

        result = np.asarray(arr, dtype=np.float64)
        assert result.dtype == np.float64
        np.testing.assert_array_equal(result, data.astype(np.float64))

    def test_array_protocol_without_storage_raises(self) -> None:
        """Array.__array__() raises when no storage reference is set."""
        arr = Array(axes=["y", "x"], shape=(2, 2), dtype="float32")
        with pytest.raises(ValueError, match="storage reference"):
            np.asarray(arr)
