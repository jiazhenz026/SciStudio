"""Extended tests for DataObject — storage_ref, to_memory, type attributes.

T-005 (ADR-027 D5): The legacy single-dict ``metadata`` API has been
replaced with the three-slot ``framework`` / ``meta`` / ``user`` model.
The validation tests below now exercise the ``user`` slot directly.
A small ``TestMetadataDeprecationShim`` class remains to guard the
backward-compat path; the comprehensive shim tests live in
``tests/core/test_stratified_metadata.py``.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pytest

from scistudio.core.storage.ref import StorageReference
from scistudio.core.storage.zarr_backend import ZarrBackend
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text


class Image(Array):
    """T-006 shim for the removed core ``Image`` class (see T-008)."""

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


class TestUserSlotValidation:
    """ADR-017: the ``user`` slot must be JSON-serialisable.

    Migrated from the pre-T-005 ``TestMetadataValidation`` suite. The
    free-form metadata dict is now ``user``; ``framework`` and ``meta``
    are typed Pydantic models that handle their own serialisation.
    """

    def test_valid_json_primitives(self) -> None:
        obj = DataObject(user={"str": "hello", "int": 42, "float": 3.14, "bool": True, "none": None})
        assert obj.user["str"] == "hello"

    def test_valid_nested_structures(self) -> None:
        obj = DataObject(user={"list": [1, 2, 3], "nested": {"a": {"b": [1]}}})
        assert obj.user["list"] == [1, 2, 3]

    def test_empty_user_passes(self) -> None:
        obj = DataObject(user={})
        assert obj.user == {}

    def test_none_user_defaults_to_empty(self) -> None:
        obj = DataObject(user=None)
        assert obj.user == {}

    def test_no_user_arg(self) -> None:
        obj = DataObject()
        assert obj.user == {}

    def test_set_raises(self) -> None:
        with pytest.raises(TypeError, match="JSON-serialisable"):
            DataObject(user={"bad": {1, 2, 3}})

    def test_lambda_raises(self) -> None:
        with pytest.raises(TypeError, match="JSON-serialisable"):
            DataObject(user={"fn": lambda x: x})

    def test_custom_object_raises(self) -> None:
        class Custom:
            pass

        with pytest.raises(TypeError, match="JSON-serialisable"):
            DataObject(user={"obj": Custom()})

    def test_bytes_raises(self) -> None:
        with pytest.raises(TypeError, match="JSON-serialisable"):
            DataObject(user={"data": b"\x00\x01"})


class TestMetadataShimRemoved:
    """The Phase-11 ``metadata`` deprecation shim is deleted (ADR-052 §3.1 / §16).

    The legacy ``DataObject(metadata=...)`` constructor kwarg and the
    ``DataObject.metadata`` property are removed in #1817. Comprehensive
    removal coverage lives in ``tests/core/test_stratified_metadata.py``; this
    class exists so a regression that re-introduces the shim trips a test in
    this file as well.
    """

    def test_metadata_property_is_gone(self) -> None:
        _absent = object()
        assert inspect.getattr_static(DataObject, "metadata", _absent) is _absent

    def test_metadata_kwarg_removed_from_signature(self) -> None:
        params = inspect.signature(DataObject.__init__).parameters
        assert "metadata" not in params, f"DataObject.__init__ must not accept metadata=; got {list(params)}"

    def test_user_slot_still_validates_json(self) -> None:
        # The supported three-slot ``user`` API keeps the JSON validation the
        # shim used to route into.
        with pytest.raises(TypeError, match="JSON-serialisable"):
            DataObject(user={"bad": {1, 2, 3}})


class TestDataObjectStorageRef:
    """DataObject.storage_ref — getter and setter."""

    def test_default_none(self) -> None:
        obj = DataObject()
        assert obj.storage_ref is None

    def test_setter(self) -> None:
        obj = DataObject()
        ref = StorageReference(backend="zarr", path="/tmp/test.zarr")
        obj.storage_ref = ref
        assert obj.storage_ref is ref

    def test_clear_to_none(self) -> None:
        ref = StorageReference(backend="zarr", path="/tmp/test.zarr")
        obj = DataObject(storage_ref=ref)
        assert obj.storage_ref is ref
        obj.storage_ref = None
        assert obj.storage_ref is None


class TestDataObjectToMemory:
    """DataObject.to_memory — delegates to view().to_memory()."""

    def test_to_memory_delegates(self, tmp_path: Path) -> None:
        arr = np.array([1.0, 2.0, 3.0])
        backend = ZarrBackend()
        ref = StorageReference(backend="zarr", path=str(tmp_path / "data.zarr"))
        ref = backend.write(arr, ref)

        obj = DataObject(storage_ref=ref)
        result = obj.to_memory()
        np.testing.assert_array_equal(result, arr)

    def test_to_memory_without_ref_raises(self) -> None:
        obj = DataObject()
        with pytest.raises(ValueError, match="Cannot load data: no storage reference set"):
            obj.to_memory()


class TestTypeAttributes:
    """Type attribute storage on concrete DataObject subclasses."""

    def test_array_shape_dtype(self) -> None:
        arr = Array(axes=["y", "x"], shape=(10, 20), dtype="float32")
        assert arr.shape == (10, 20)
        assert arr.ndim == 2
        assert arr.dtype == "float32"

    def test_image_inherits_array(self) -> None:
        img = Image(shape=(256, 256), ndim=2, dtype="uint8")
        assert img.shape == (256, 256)
        assert isinstance(img, Array)

    def test_series_attributes(self) -> None:
        s = Series(index_name="wavelength", value_name="intensity", length=100)
        assert s.index_name == "wavelength"
        assert s.value_name == "intensity"
        assert s.length == 100

    def test_dataframe_columns(self) -> None:
        df = DataFrame(columns=["a", "b", "c"], row_count=50)
        assert df.columns == ["a", "b", "c"]
        assert df.row_count == 50

    def test_text_content(self) -> None:
        t = Text(content="hello world", format="plain")
        assert t.content == "hello world"
        assert t.format == "plain"

    def test_artifact_file_path_and_mime(self) -> None:
        a = Artifact(file_path=Path("/data/report.pdf"), mime_type="application/pdf")
        assert a.file_path == Path("/data/report.pdf")
        assert a.mime_type == "application/pdf"
