"""Tests for ``Array`` instance-level axes and ``sel`` / ``iter_over`` (T-006).

Implements the acceptance criteria from
``docs/specs/phase10-implementation-standards.md`` §T-006 and exercises
ADR-027 D1 (instance-level axes with class-level schema) and ADR-027 D4
(``sel`` and ``iter_over`` with Level 1 laziness).

The shim subclass ``_TestArray`` below declares a typed ``Meta`` model so
the ``with_meta`` override can be covered end-to-end; the base
``Array`` class has ``meta=None`` and therefore rejects ``with_meta``.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pytest
from pydantic import BaseModel

from scistudio.core.types.array import Array
from scistudio.core.types.base import TypeSignature

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class _TestArrayMeta(BaseModel):
    """Minimal typed Meta for exercising ``Array.with_meta``."""

    sample_id: str = ""
    exposure_ms: float = 0.0


class _TestArray(Array):
    """Subclass with a class-level ``Meta`` model and tightened axes schema.

    Used to exercise ``required_axes`` enforcement and the
    ``with_meta`` override.
    """

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
    Meta: ClassVar[type[BaseModel] | None] = _TestArrayMeta


class _ChannelRequired(Array):
    """Subclass whose ``required_axes`` demands a ``c`` (channel) axis."""

    required_axes: ClassVar[frozenset[str]] = frozenset({"c"})


class _RestrictedAxes(Array):
    """Subclass whose ``allowed_axes`` is a strict subset of the alphabet."""

    allowed_axes: ClassVar[frozenset[str] | None] = frozenset({"y", "x"})


def _backed_array(axes: list[str], data: np.ndarray) -> Array:
    """Return a plain :class:`Array` backed by zarr storage.

    ADR-031 D3: uses zarr storage instead of the former ``_data`` backdoor.
    """
    import tempfile
    import uuid

    import zarr

    from scistudio.core.storage.ref import StorageReference

    tmpdir = tempfile.mkdtemp(prefix="scistudio_test_")
    zarr_path = f"{tmpdir}/{uuid.uuid4()}.zarr"
    zarr.save(zarr_path, data)
    ref = StorageReference(
        backend="zarr",
        path=zarr_path,
        metadata={"shape": list(data.shape), "dtype": str(data.dtype)},
    )
    return Array(axes=axes, shape=data.shape, dtype=str(data.dtype), storage_ref=ref)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestArrayConstruction:
    """ADR-027 D1: instance-level axes are required and validated."""

    def test_array_construction_with_2d_axes(self) -> None:
        arr = Array(axes=["y", "x"], shape=(10, 10))
        assert arr.axes == ["y", "x"]
        assert arr.shape == (10, 10)
        assert arr.ndim == 2

    def test_array_construction_with_5d_axes(self) -> None:
        arr = Array(axes=["t", "z", "c", "y", "x"], shape=(2, 3, 4, 10, 10))
        assert arr.axes == ["t", "z", "c", "y", "x"]
        assert arr.ndim == 5
        assert arr.shape == (2, 3, 4, 10, 10)

    def test_array_construction_with_6d_axes(self) -> None:
        """ADR-027 discussion #3: ``lambda`` and ``c`` coexist in 6D."""
        arr = Array(
            axes=["t", "z", "c", "lambda", "y", "x"],
            shape=(2, 3, 4, 5, 10, 10),
        )
        assert arr.ndim == 6
        assert "c" in arr.axes
        assert "lambda" in arr.axes

    def test_array_construction_missing_axes_kwarg_raises(self) -> None:
        with pytest.raises(TypeError):
            Array(shape=(10, 10))  # type: ignore[call-arg]

    def test_array_duplicate_axes_raises(self) -> None:
        with pytest.raises(ValueError, match="Duplicate axes"):
            Array(axes=["y", "y"], shape=(10, 10))

    def test_array_subclass_required_axes_enforced(self) -> None:
        with pytest.raises(ValueError, match="requires axes"):
            _ChannelRequired(axes=["y", "x"], shape=(10, 10))

    def test_array_subclass_required_axes_satisfied(self) -> None:
        arr = _ChannelRequired(axes=["y", "x", "c"], shape=(10, 10, 3))
        assert "c" in arr.axes

    def test_array_subclass_allowed_axes_enforced(self) -> None:
        with pytest.raises(ValueError, match="accepts only"):
            _RestrictedAxes(axes=["y", "x", "z"], shape=(10, 10, 3))

    def test_array_no_allowed_axes_means_unrestricted(self) -> None:
        """The base ``Array`` accepts any axis labels."""
        arr = Array(axes=["alpha", "beta", "gamma"], shape=(1, 1, 1))
        assert arr.axes == ["alpha", "beta", "gamma"]

    def test_array_ndim_property_returns_axes_length(self) -> None:
        arr = Array(axes=["t", "z", "c", "y", "x"], shape=(1, 2, 3, 4, 5))
        assert arr.ndim == len(arr.axes)


# ---------------------------------------------------------------------------
# sel()
# ---------------------------------------------------------------------------


class TestArraySel:
    """ADR-027 D4: ``Array.sel`` with Level 1 laziness."""

    def test_sel_single_axis_integer_drops_axis(self) -> None:
        data = np.arange(3 * 5 * 5, dtype="float32").reshape(3, 5, 5)
        arr = _backed_array(["z", "y", "x"], data)
        result = arr.sel(z=0)
        assert result.axes == ["y", "x"]
        assert result.shape == (5, 5)
        np.testing.assert_array_equal(np.asarray(result), data[0])

    def test_sel_slice_keeps_axis(self) -> None:
        data = np.arange(10 * 5 * 5, dtype="float32").reshape(10, 5, 5)
        arr = _backed_array(["z", "y", "x"], data)
        result = arr.sel(z=slice(0, 5))
        assert result.axes == ["z", "y", "x"]
        assert result.shape == (5, 5, 5)

    def test_sel_multiple_axes(self) -> None:
        data = np.arange(2 * 3 * 4 * 5 * 6, dtype="float32").reshape(2, 3, 4, 5, 6)
        arr = _backed_array(["t", "z", "c", "y", "x"], data)
        result = arr.sel(t=0, z=1)
        assert result.axes == ["c", "y", "x"]
        assert result.shape == (4, 5, 6)
        np.testing.assert_array_equal(np.asarray(result), data[0, 1])

    def test_sel_unknown_axis_raises(self) -> None:
        arr = _backed_array(["y", "x"], np.zeros((3, 3)))
        with pytest.raises(ValueError, match="unknown axes"):
            arr.sel(foo=0)

    def test_sel_invalid_index_type_raises(self) -> None:
        arr = _backed_array(["z", "y", "x"], np.zeros((3, 3, 3)))
        with pytest.raises(ValueError, match="must be int or slice"):
            arr.sel(z=[1, 2])  # type: ignore[arg-type]

    def test_sel_preserves_meta(self) -> None:
        import tempfile
        import uuid

        import zarr

        from scistudio.core.storage.ref import StorageReference

        meta = _TestArrayMeta(sample_id="s1", exposure_ms=12.5)
        data = np.zeros((5, 5), dtype="float32")
        tmpdir = tempfile.mkdtemp(prefix="scistudio_test_")
        zarr_path = f"{tmpdir}/{uuid.uuid4()}.zarr"
        zarr.save(zarr_path, data)
        ref = StorageReference(backend="zarr", path=zarr_path, metadata={"shape": [5, 5], "dtype": "float32"})
        arr = _TestArray(axes=["y", "x"], shape=(5, 5), meta=meta, storage_ref=ref)
        result = arr.sel(y=0)
        assert result.meta is meta

    def test_sel_preserves_user_dict(self) -> None:
        arr = _backed_array(["z", "y", "x"], np.zeros((3, 5, 5)))
        arr._user = {"project": "demo", "note": "phase10"}
        result = arr.sel(z=0)
        assert result.user == {"project": "demo", "note": "phase10"}
        # Shallow copy — must not share the reference
        assert result.user is not arr.user

    def test_sel_creates_derived_framework(self) -> None:
        arr = _backed_array(["z", "y", "x"], np.zeros((3, 5, 5)))
        parent_id = arr.framework.object_id
        result = arr.sel(z=0)
        assert result.framework.derived_from == parent_id
        assert result.framework.object_id != parent_id

    def test_sel_without_data_raises(self) -> None:
        """Metadata-only instances cannot be sliced."""
        arr = Array(axes=["y", "x"], shape=(10, 10))
        with pytest.raises(ValueError, match="requires backing data"):
            arr.sel(y=0)

    def test_sel_returns_plain_array(self) -> None:
        """``sel`` deliberately returns a plain ``Array`` (not ``type(self)``)."""
        import tempfile
        import uuid

        import zarr

        from scistudio.core.storage.ref import StorageReference

        data = np.zeros((5, 5), dtype="float32")
        tmpdir = tempfile.mkdtemp(prefix="scistudio_test_")
        zarr_path = f"{tmpdir}/{uuid.uuid4()}.zarr"
        zarr.save(zarr_path, data)
        ref = StorageReference(backend="zarr", path=zarr_path, metadata={"shape": [5, 5], "dtype": "float32"})
        arr = _TestArray(axes=["y", "x"], shape=(5, 5), storage_ref=ref)
        result = arr.sel(y=0)
        assert type(result) is Array

    def test_sel_zarr_partial_read(self) -> None:
        """ADR-031 Phase 3 (Task 17): sel() uses zarr partial-read for
        zarr-backed Arrays, avoiding full materialisation."""
        data = np.arange(4 * 5 * 6, dtype="float32").reshape(4, 5, 6)
        arr = _backed_array(["z", "y", "x"], data)
        # Verify the source is zarr-backed
        assert arr.storage_ref is not None
        assert arr.storage_ref.backend == "zarr"
        # Select a single z-plane — should use ZarrBackend.slice()
        result = arr.sel(z=2)
        assert result.axes == ["y", "x"]
        assert result.shape == (5, 6)
        np.testing.assert_array_equal(np.asarray(result), data[2])

    def test_sel_zarr_partial_read_slice_range(self) -> None:
        """ADR-031 Phase 3: sel() with slice range on zarr-backed Array."""
        data = np.arange(10 * 5 * 5, dtype="float32").reshape(10, 5, 5)
        arr = _backed_array(["z", "y", "x"], data)
        result = arr.sel(z=slice(2, 7))
        assert result.axes == ["z", "y", "x"]
        assert result.shape == (5, 5, 5)
        np.testing.assert_array_equal(np.asarray(result), data[2:7])

    def test_sel_zarr_partial_read_multiple_axes(self) -> None:
        """ADR-031 Phase 3: sel() with multiple axes on zarr-backed Array."""
        data = np.arange(2 * 3 * 4 * 5 * 6, dtype="float32").reshape(2, 3, 4, 5, 6)
        arr = _backed_array(["t", "z", "c", "y", "x"], data)
        result = arr.sel(t=1, c=2)
        assert result.axes == ["z", "y", "x"]
        assert result.shape == (3, 5, 6)
        np.testing.assert_array_equal(np.asarray(result), data[1, :, 2])


# ---------------------------------------------------------------------------
# iter_over()
# ---------------------------------------------------------------------------


class TestArrayIterOver:
    """ADR-027 D4: ``Array.iter_over`` as generator over one axis."""

    def test_iter_over_yields_correct_count(self) -> None:
        data = np.arange(3 * 5 * 5, dtype="float32").reshape(3, 5, 5)
        arr = _backed_array(["z", "y", "x"], data)
        slices = list(arr.iter_over("z"))
        assert len(slices) == 3

    def test_iter_over_each_item_has_correct_shape(self) -> None:
        data = np.arange(3 * 5 * 5, dtype="float32").reshape(3, 5, 5)
        arr = _backed_array(["z", "y", "x"], data)
        for i, sub in enumerate(arr.iter_over("z")):
            assert sub.axes == ["y", "x"]
            assert sub.shape == (5, 5)
            np.testing.assert_array_equal(np.asarray(sub), data[i])

    def test_iter_over_unknown_axis_raises(self) -> None:
        arr = _backed_array(["y", "x"], np.zeros((5, 5)))
        with pytest.raises(ValueError, match="not in"):
            list(arr.iter_over("z"))

    def test_iter_over_no_shape_raises(self) -> None:
        arr = Array(axes=["z", "y", "x"], shape=None)
        with pytest.raises(ValueError, match="requires a known shape"):
            list(arr.iter_over("z"))


# ---------------------------------------------------------------------------
# with_meta override
# ---------------------------------------------------------------------------


class TestArrayWithMeta:
    """T-006: the ``with_meta`` override propagates Array-specific kwargs."""

    def test_with_meta_propagates_axes(self) -> None:
        meta = _TestArrayMeta(sample_id="s1")
        arr = _TestArray(
            axes=["y", "x"],
            shape=(10, 10),
            dtype="float32",
            meta=meta,
        )
        result = arr.with_meta(sample_id="s2")
        assert result.axes == ["y", "x"]
        assert result.shape == (10, 10)
        assert result.dtype == "float32"
        assert isinstance(result.meta, _TestArrayMeta)
        assert result.meta.sample_id == "s2"

    def test_with_meta_preserves_chunk_shape(self) -> None:
        meta = _TestArrayMeta()
        arr = _TestArray(
            axes=["y", "x"],
            shape=(10, 10),
            chunk_shape=(2, 2),
            meta=meta,
        )
        result = arr.with_meta(sample_id="abc")
        assert result.chunk_shape == (2, 2)

    def test_with_meta_creates_derived_framework(self) -> None:
        meta = _TestArrayMeta()
        arr = _TestArray(axes=["y", "x"], shape=(5, 5), meta=meta)
        parent_id = arr.framework.object_id
        result = arr.with_meta(sample_id="derived")
        assert result.framework.derived_from == parent_id
        assert result.framework.object_id != parent_id

    def test_with_meta_without_meta_raises(self) -> None:
        arr = Array(axes=["y", "x"], shape=(5, 5))
        with pytest.raises(ValueError, match="requires a typed"):
            arr.with_meta(anything=True)


# ---------------------------------------------------------------------------
# TypeSignature.from_type captures required_axes
# ---------------------------------------------------------------------------


class TestTypeSignatureRequiredAxes:
    """ADR-027 D1: port-level ``required_axes`` is captured in the signature."""

    def test_array_signature_required_axes_none(self) -> None:
        """Base ``Array`` has empty ``required_axes`` → ``None`` on the signature."""
        sig = TypeSignature.from_type(Array)
        assert sig.required_axes is None

    def test_subclass_signature_required_axes_populated(self) -> None:
        sig = TypeSignature.from_type(_TestArray)
        assert sig.required_axes == frozenset({"y", "x"})

    def test_channel_required_signature(self) -> None:
        sig = TypeSignature.from_type(_ChannelRequired)
        assert sig.required_axes == frozenset({"c"})

    def test_non_array_signature_has_no_required_axes(self) -> None:
        from scistudio.core.types.series import Series

        sig = TypeSignature.from_type(Series)
        assert sig.required_axes is None
