"""Tests for DataObject three-slot stratified metadata (ADR-027 D5, T-005).

Covers:
    - Construction defaults for the framework / meta / user slots.
    - JSON-serialisability validation on the user dict.
    - Removal of the legacy ``metadata=`` kwarg and the
      ``DataObject.metadata`` property — the Phase-11 deprecation shim is
      deleted in #1817 (ADR-052 §3.1 / §16); the three-slot ``user`` API is
      the replacement.
    - The :meth:`DataObject.with_meta` immutable update path: requires a
      typed Meta on the instance, returns a new instance, derives a
      fresh FrameworkMeta with ``derived_from`` set, preserves user and
      storage_ref, and does not mutate the original.
    - The :attr:`DataObject.Meta` ClassVar declaration that plugin
      subclasses (T-013) override.
    - Sanity checks that ``view()`` and ``save()`` are unchanged by
      T-005 (no contract change to non-metadata methods).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest
from pydantic import BaseModel

from scistudio.core.meta import FrameworkMeta
from scistudio.core.storage.ref import StorageReference
from scistudio.core.storage.zarr_backend import ZarrBackend
from scistudio.core.types.base import DataObject

# ---------------------------------------------------------------------------
# Test fixtures: a tiny typed Meta + a subclass that uses it.
# ---------------------------------------------------------------------------


class _SampleMeta(BaseModel):
    """Minimal frozen Pydantic model used to exercise with_meta()."""

    field: int = 0
    label: str = ""


class _SampleObject(DataObject):
    """DataObject subclass that declares its own typed Meta.

    The base ``DataObject`` has ``Meta = None``; this test subclass
    overrides the ClassVar so we can construct instances with a real
    Pydantic model in the meta slot and exercise ``with_meta``.
    """

    Meta = _SampleMeta


# ---------------------------------------------------------------------------
# Default construction
# ---------------------------------------------------------------------------


class TestDefaultConstruction:
    """Verify the three-slot defaults on a bare ``DataObject()``."""

    def test_default_construction_creates_framework_meta(self) -> None:
        obj = DataObject()
        assert isinstance(obj.framework, FrameworkMeta)
        # FrameworkMeta default factories populate object_id and created_at.
        assert obj.framework.object_id != ""
        assert obj.framework.created_at is not None

    def test_default_construction_meta_is_none(self) -> None:
        obj = DataObject()
        assert obj.meta is None

    def test_default_construction_user_is_empty_dict(self) -> None:
        obj = DataObject()
        assert obj.user == {}
        assert isinstance(obj.user, dict)

    def test_default_construction_storage_ref_is_none(self) -> None:
        obj = DataObject()
        assert obj.storage_ref is None


# ---------------------------------------------------------------------------
# user dict validation
# ---------------------------------------------------------------------------


class TestUserDictValidation:
    """ADR-017: user dict must be JSON-serialisable."""

    def test_user_accepts_json_primitives(self) -> None:
        obj = DataObject(user={"s": "x", "n": 1, "f": 2.5, "b": True, "z": None})
        assert obj.user["s"] == "x"
        assert obj.user["n"] == 1

    def test_user_accepts_nested_structures(self) -> None:
        obj = DataObject(user={"list": [1, 2, 3], "nested": {"a": {"b": [1]}}})
        assert obj.user["list"] == [1, 2, 3]

    def test_user_dict_must_be_json_serialisable(self) -> None:
        with pytest.raises(TypeError, match="JSON-serialisable"):
            DataObject(user={"key": object()})

    def test_user_dict_validates_at_construction(self) -> None:
        # Same case as above but explicit about timing: validation runs
        # during __init__, not lazily on access.
        with pytest.raises(TypeError, match="JSON-serialisable"):
            DataObject(user={"bad": {1, 2, 3}})

    def test_user_lambda_raises(self) -> None:
        with pytest.raises(TypeError, match="JSON-serialisable"):
            DataObject(user={"fn": lambda x: x})

    def test_user_bytes_raises(self) -> None:
        with pytest.raises(TypeError, match="JSON-serialisable"):
            DataObject(user={"data": b"\x00\x01"})

    def test_user_dict_is_copied(self) -> None:
        # Mutating the original after construction must not change obj.user.
        original = {"k": "v"}
        obj = DataObject(user=original)
        original["k"] = "mutated"
        assert obj.user["k"] == "v"


# ---------------------------------------------------------------------------
# Removal of the legacy metadata property and metadata= kwarg (ADR-052 §3.1/§16)
# ---------------------------------------------------------------------------

_ABSENT = object()


class TestMetadataShimRemoved:
    """The Phase-11 ``metadata`` deprecation shim is deleted (ADR-052 §3.1 / §16).

    The legacy single-dict ``metadata`` property and ``metadata=`` constructor
    kwarg are removed in #1817. Authors use the three-slot ``user`` API instead.
    """

    def test_metadata_property_is_gone(self) -> None:
        # No ``metadata`` property survives on the class (not even deprecated).
        assert inspect.getattr_static(DataObject, "metadata", _ABSENT) is _ABSENT

    def test_metadata_kwarg_removed_from_signature(self) -> None:
        params = inspect.signature(DataObject.__init__).parameters
        assert "metadata" not in params, f"DataObject.__init__ must not accept metadata=; got {list(params)}"

    def test_user_slot_is_the_replacement(self) -> None:
        # The three-slot API is the supported path the shim used to route into.
        obj = DataObject(user={"key": "value"})
        assert obj.user == {"key": "value"}


# ---------------------------------------------------------------------------
# framework slot
# ---------------------------------------------------------------------------


class TestFrameworkSlot:
    """The framework slot is a FrameworkMeta and is unique per instance."""

    def test_framework_property_returns_framework_meta(self) -> None:
        obj = DataObject()
        assert isinstance(obj.framework, FrameworkMeta)

    def test_framework_is_unique_per_instance(self) -> None:
        a = DataObject()
        b = DataObject()
        # Default factories produce a fresh object_id per call.
        assert a.framework.object_id != b.framework.object_id

    def test_explicit_framework_passed_through(self) -> None:
        fw = FrameworkMeta(source="test_source")
        obj = DataObject(framework=fw)
        assert obj.framework is fw
        assert obj.framework.source == "test_source"

    def test_framework_object_id_is_non_empty_string(self) -> None:
        obj = DataObject()
        assert isinstance(obj.framework.object_id, str)
        assert len(obj.framework.object_id) > 0


# ---------------------------------------------------------------------------
# with_meta() — immutable update
# ---------------------------------------------------------------------------


class TestWithMeta:
    """:meth:`DataObject.with_meta` returns a new typed instance."""

    def test_with_meta_raises_when_meta_is_none(self) -> None:
        obj = DataObject()
        with pytest.raises(ValueError, match="requires a typed `meta` slot"):
            obj.with_meta(field=1)

    def test_with_meta_returns_new_instance_with_updated_meta(self) -> None:
        obj = _SampleObject(meta=_SampleMeta(field=0, label="x"))
        new = obj.with_meta(field=42)
        assert isinstance(new, _SampleObject)
        assert new.meta is not None
        assert new.meta.field == 42
        # Unchanged fields are preserved by Pydantic model_copy.
        assert new.meta.label == "x"

    def test_with_meta_preserves_user(self) -> None:
        obj = _SampleObject(meta=_SampleMeta(field=1), user={"k": "v"})
        new = obj.with_meta(field=2)
        assert new.user == {"k": "v"}
        # User dict is shallow-copied so the new instance does not share
        # the dict object with the original.
        assert new.user is not obj.user

    def test_with_meta_preserves_storage_ref(self) -> None:
        ref = StorageReference(backend="zarr", path="/tmp/test.zarr")
        obj = _SampleObject(meta=_SampleMeta(field=1), storage_ref=ref)
        new = obj.with_meta(field=2)
        assert new.storage_ref is ref

    def test_with_meta_creates_derived_framework(self) -> None:
        obj = _SampleObject(meta=_SampleMeta(field=1))
        new = obj.with_meta(field=2)
        # ADR-027 D5 propagation: derived framework's derived_from points
        # at the parent's object_id.
        assert new.framework.derived_from == obj.framework.object_id

    def test_with_meta_new_framework_has_different_object_id(self) -> None:
        obj = _SampleObject(meta=_SampleMeta(field=1))
        new = obj.with_meta(field=2)
        assert new.framework.object_id != obj.framework.object_id

    def test_with_meta_inherits_source(self) -> None:
        # FrameworkMeta.derive() inherits source unless overridden.
        obj = _SampleObject(
            meta=_SampleMeta(field=1),
            framework=FrameworkMeta(source="parent_source"),
        )
        new = obj.with_meta(field=2)
        assert new.framework.source == "parent_source"

    def test_with_meta_does_not_mutate_original(self) -> None:
        obj = _SampleObject(meta=_SampleMeta(field=0, label="orig"))
        _ = obj.with_meta(field=99, label="changed")
        assert obj.meta is not None
        assert obj.meta.field == 0
        assert obj.meta.label == "orig"

    def test_with_meta_partial_update(self) -> None:
        # Updating one field leaves the others alone.
        obj = _SampleObject(meta=_SampleMeta(field=5, label="x"))
        new = obj.with_meta(label="y")
        assert new.meta is not None
        assert new.meta.field == 5
        assert new.meta.label == "y"


# ---------------------------------------------------------------------------
# Class-level Meta declaration
# ---------------------------------------------------------------------------


class TestClassLevelMeta:
    """The :attr:`DataObject.Meta` ClassVar is the per-subtype Meta hook."""

    def test_class_level_meta_attribute_default_is_none(self) -> None:
        assert DataObject.Meta is None

    def test_subclass_can_set_class_level_meta(self) -> None:
        # _SampleObject sets Meta = _SampleMeta at class scope.
        assert _SampleObject.Meta is _SampleMeta

    def test_subclass_meta_is_inherited_by_default(self) -> None:
        class _SubSample(_SampleObject):
            pass

        assert _SubSample.Meta is _SampleMeta


# ---------------------------------------------------------------------------
# Sanity: pre-existing methods unchanged by T-005
# ---------------------------------------------------------------------------


class TestExistingMethodsUnchanged:
    """T-005 only changes the metadata story; other methods are unchanged."""

    def test_to_memory_without_storage_ref_still_raises(self) -> None:
        """ADR-031 D2: view() removed; to_memory() requires storage_ref."""
        obj = DataObject()
        with pytest.raises(ValueError, match="no storage reference"):
            obj.to_memory()

    def test_view_with_storage_ref_round_trip(self, tmp_path: Path) -> None:
        backend = ZarrBackend()
        data = np.array([1.0, 2.0, 3.0])
        ref = StorageReference(backend="zarr", path=str(tmp_path / "data.zarr"))
        ref = backend.write(data, ref)

        obj = DataObject(storage_ref=ref)
        assert obj.storage_ref is ref
        result = obj.to_memory()
        np.testing.assert_array_equal(result, data)

    def test_save_idempotent_when_storage_ref_already_set(self) -> None:
        ref = StorageReference(backend="zarr", path="/tmp/already.zarr")
        obj = DataObject(storage_ref=ref)
        # Save returns the existing ref without writing.
        assert obj.save("/some/other/path") is ref

    def test_dtype_info_returns_type_signature(self) -> None:
        obj = DataObject()
        sig = obj.dtype_info
        assert sig.type_chain == ["DataObject"]
