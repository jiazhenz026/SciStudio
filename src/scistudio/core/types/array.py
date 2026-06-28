"""N-dimensional arrays with named axes (:class:`Array`).

This is the data type for image stacks, volumes, and any other gridded
numeric data. Each axis carries a name (such as ``"y"``, ``"x"``, or ``"c"``
for channel), so selections read clearly — ``img.sel(c=0)`` instead of
guessing positions. Large arrays are stored on disk (Zarr) and read lazily,
so working with one does not pull the whole thing into memory.

Domain-specific image kinds (fluorescence, mass-spec imaging, and so on)
live in the imaging plugin packages and subclass :class:`Array`. For data
that needs no specialised container, use :class:`Array` directly, e.g.
``Array(axes=["y", "x"])``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar, Self

from scistudio.core.types.base import DataObject
from scistudio.stability import internal, provisional, stable


@stable(since="0.3.1")
class Array(DataObject):
    """N-dimensional array with named axes, optionally chunked on disk.

    Use this for any gridded numeric data — a 2D image, a 3D volume, a
    time-lapse, a multi-channel stack. Naming the axes makes selections
    self-documenting: ``stack.sel(z=10, c=0)`` reads one z-plane of one
    channel without you tracking which position each axis is in.

    A subclass can restrict which axes it accepts through three class
    attributes that act as a schema: :attr:`required_axes`,
    :attr:`allowed_axes`, and :attr:`canonical_order`. Plain :class:`Array`
    leaves all three permissive, so it accepts any axes you give it.

    The axis names used for scientific imaging are ``t`` (time), ``z``
    (depth), ``c`` (discrete channel), ``lambda`` (continuous spectral), and
    ``y`` / ``x`` (the two spatial axes). ``c`` and ``lambda`` are different
    axes and may both appear on one array.

    Example:
        >>> from scistudio.core.types import Array
        >>> stack = Array(axes=["z", "y", "x"], shape=(20, 512, 512))
        >>> stack.ndim
        3
        >>> stack.axes
        ['z', 'y', 'x']
    """

    required_axes: ClassVar[frozenset[str]] = frozenset()
    """Axis names every instance of this class must carry.

    Empty on plain :class:`Array` (no requirement). A subclass tightens it to
    demand, say, ``{"y", "x"}``; constructing an instance without those axes
    then raises :class:`ValueError`.
    """
    allowed_axes: ClassVar[frozenset[str] | None] = None
    """The set of axis names this class permits, or ``None`` for no limit.

    ``None`` means any axis name is allowed. A frozenset means an instance's
    axes must all be drawn from it.
    """
    canonical_order: ClassVar[tuple[str, ...]] = ()
    """Preferred axis ordering, used when reordering or displaying axes.

    Empty on plain :class:`Array` (no preferred order).
    """

    @stable(since="0.3.1")
    def __init__(
        self,
        *,
        axes: list[str],
        shape: tuple[int, ...] | None = None,
        dtype: Any = None,
        chunk_shape: tuple[int, ...] | None = None,
        data: Any = None,
        **kwargs: Any,
    ) -> None:
        """Construct an array with explicit named axes.

        Args:
            axes: Required list of axis names, one per dimension, e.g.
                ``["z", "y", "x"]``.
            shape: Size along each axis, or ``None`` for a metadata-only
                placeholder.
            dtype: Element data type (for example a NumPy dtype).
            chunk_shape: Chunk sizes for chunked/lazy storage, or ``None``.
            data: Optional in-memory array (for example a NumPy ndarray).
                Held only until the framework writes it to storage; never
                serialised directly.
            **kwargs: The shared :class:`DataObject` slots (``framework``,
                ``meta``, ``user``, ``storage_ref``).

        Raises:
            ValueError: if *axes* contain duplicates, omit a required axis,
                or include an axis the class does not allow.
        """
        super().__init__(**kwargs)
        self.axes: list[str] = list(axes)
        """The per-instance axis names, one per dimension."""
        self.shape: tuple[int, ...] | None = tuple(shape) if shape is not None else None
        """Size along each axis, or ``None`` when unknown (metadata-only)."""
        self.dtype: Any = dtype
        """Element data type, or ``None`` when unknown."""
        self.chunk_shape: tuple[int, ...] | None = tuple(chunk_shape) if chunk_shape is not None else None
        """Chunk sizes for chunked/lazy storage, or ``None``."""
        if data is not None:
            self._transient_data = data
        self._validate_axes()

    def _validate_axes(self) -> None:
        """Validate the instance's axes against the class's schema.

        Raises:
            ValueError: if axes contain duplicates, are missing any
                required axis, or contain any axis not in
                ``allowed_axes`` (when the latter is non-None).
        """
        axes_set = set(self.axes)
        if len(axes_set) != len(self.axes):
            raise ValueError(f"Duplicate axes in {self.axes}")
        if not self.required_axes.issubset(axes_set):
            missing = sorted(self.required_axes - axes_set)
            raise ValueError(f"{type(self).__name__} requires axes {sorted(self.required_axes)}, missing: {missing}")
        if self.allowed_axes is not None and not axes_set.issubset(self.allowed_axes):
            extra = sorted(axes_set - self.allowed_axes)
            raise ValueError(f"{type(self).__name__} accepts only {sorted(self.allowed_axes)}, unexpected: {extra}")

    @property
    @stable(since="0.3.1")
    def ndim(self) -> int:
        """Number of dimensions (the length of :attr:`axes`).

        Returns:
            The count of axes.
        """
        return len(self.axes)

    @stable(since="0.3.1")
    def __array__(self, dtype: Any = None, copy: Any = None) -> Any:
        """Support ``numpy.asarray(array_obj)`` via the NumPy array protocol.

        Lets an :class:`Array` be passed anywhere NumPy expects an
        array-like; it materialises the full data with :meth:`to_memory`.

        Args:
            dtype: Optional dtype to cast the result to.
            copy: If truthy, return a copy rather than a view.

        Returns:
            A :class:`numpy.ndarray` of the data.
        """
        import numpy as np

        data = self.to_memory()
        arr = np.asarray(data)
        if dtype is not None:
            arr = arr.astype(dtype)
        if copy:
            arr = arr.copy()
        return arr

    # -- ADR-027 D4: sel and iter_over ------------------------------------

    @stable(since="0.3.1")
    def sel(self, **kwargs: int | slice) -> Array:
        """Select a sub-array by naming positions along one or more axes.

        Pass each axis you want to narrow as a keyword:

        - an integer picks one position and **drops** that axis from the
          result (``sel(z=15)`` turns a ``z, y, x`` array into ``y, x``);
        - a ``slice`` keeps a range and **keeps** the axis
          (``sel(z=slice(10, 20))`` keeps ``z, y, x``).

        Lists of indices and boolean masks are not supported.

        The result is always a plain :class:`Array` (not the original
        subclass), because a reduced selection may no longer satisfy a
        subclass's required axes — for example selecting one channel from an
        array that requires a channel axis. The new array carries derived
        lineage, shares the typed ``meta`` by reference, and copies the
        ``user`` dict.

        When the data is stored as Zarr, only the requested region is read
        from disk; other backends read the full array and then index it.

        Args:
            **kwargs: Axis name to selection, where each value is an ``int``
                (drops the axis) or a ``slice`` (keeps it).

        Returns:
            A new :class:`Array` for the selected region.

        Raises:
            ValueError: if a keyword names an axis the array does not have, a
                value is not an ``int`` or ``slice``, or the array has no
                backing storage to read from.

        Example:
            Select sub-regions by axis name (here ``stack`` is an Array with
            axes including ``z`` and ``c``)::

                plane = stack.sel(z=10, c=0)     # one z-plane, one channel
                band = stack.sel(z=slice(0, 5))  # the first five z-planes
        """
        # Validate kwargs refer to existing axes before doing anything.
        unknown = set(kwargs.keys()) - set(self.axes)
        if unknown:
            raise ValueError(f"sel() received unknown axes: {sorted(unknown)}")

        # Build numpy index tuple in axis order, tracking resulting axes
        # and shape simultaneously.
        indexer: list[Any] = []
        new_axes: list[str] = []
        new_shape_list: list[int] = []
        for i, axis_name in enumerate(self.axes):
            if axis_name in kwargs:
                idx = kwargs[axis_name]
                if isinstance(idx, bool) or not isinstance(idx, (int, slice)):
                    raise ValueError(
                        f"sel() index for axis {axis_name!r} must be int or slice, got {type(idx).__name__}"
                    )
                indexer.append(idx)
                if isinstance(idx, slice):
                    new_axes.append(axis_name)
                    if self.shape is not None:
                        start, stop, step = idx.indices(self.shape[i])
                        size = max(0, (stop - start + (step - (1 if step > 0 else -1))) // step)
                        new_shape_list.append(size)
                # Integer index drops the axis — no append to new_axes.
            else:
                indexer.append(slice(None))
                new_axes.append(axis_name)
                if self.shape is not None:
                    new_shape_list.append(self.shape[i])

        # ADR-031 D3: always read from storage. No _data backdoor.
        if self._storage_ref is None:
            raise ValueError(
                f"{type(self).__name__}.sel() requires backing data. This instance has no storage_ref set."
            )
        # ADR-031 Phase 3 (Task 17): for zarr-backed Arrays, use the
        # backend's native partial-read to avoid full materialisation.
        # ZarrBackend.slice() reads only the requested chunks from disk.
        if self._storage_ref.backend == "zarr":
            from scistudio.core.storage.zarr_backend import ZarrBackend

            backend = ZarrBackend()
            sliced_data = backend.slice(self._storage_ref, *indexer)
        else:
            # Non-zarr backends: full materialisation + numpy indexing.
            full_data = self.to_memory()
            sliced_data = full_data[tuple(indexer)]

        # Metadata propagation per ADR-027 D5.
        new_framework = self._framework.derive()

        # Compute the new shape. If we had a known shape, new_shape_list
        # was populated alongside indexer; otherwise fall back to the
        # sliced array's shape (may be None if sliced_data has no shape).
        if self.shape is not None:
            new_shape: tuple[int, ...] | None = tuple(new_shape_list) if new_shape_list else ()
        else:
            new_shape = tuple(getattr(sliced_data, "shape", ())) or None

        # Always construct a plain Array instance (not type(self)) so
        # that required_axes violations do not trip _validate_axes on
        # reduced slices. See docstring for the rationale.
        new_instance = Array(
            axes=new_axes,
            shape=new_shape,
            dtype=self.dtype,
            chunk_shape=None,  # derived slice drops the chunk hint
            framework=new_framework,
            meta=self._meta,
            user=dict(self._user),
            storage_ref=None,
        )
        # ADR-031 D3: persist slice result to zarr and set storage_ref
        # instead of stashing in _data.
        from scistudio.core.storage.flush_context import get_output_dir

        output_dir = get_output_dir()
        if output_dir:
            import uuid

            import zarr

            from scistudio.core.storage.ref import StorageReference

            zarr_path = str(Path(output_dir) / f"{uuid.uuid4()}.zarr")
            zarr.save(zarr_path, sliced_data)  # type: ignore[arg-type]
            new_instance._storage_ref = StorageReference(
                backend="zarr",
                path=zarr_path,
                metadata={
                    "shape": list(sliced_data.shape),
                    "dtype": str(sliced_data.dtype),
                },
            )
        else:
            # Fallback: no output_dir configured, use _auto_flush pattern
            # by saving to a temp location via the DataObject.save() method.
            import tempfile
            import uuid

            import zarr

            from scistudio.core.storage.ref import StorageReference

            tmpdir = tempfile.mkdtemp(prefix="scistudio_sel_")
            zarr_path = str(Path(tmpdir) / f"{uuid.uuid4()}.zarr")
            zarr.save(zarr_path, sliced_data)  # type: ignore[arg-type]
            new_instance._storage_ref = StorageReference(
                backend="zarr",
                path=zarr_path,
                metadata={
                    "shape": list(sliced_data.shape),
                    "dtype": str(sliced_data.dtype),
                },
            )
        return new_instance

    @internal()
    def iter_over(self, axis: str) -> Iterator[Array]:
        """Yield sub-arrays along one named axis (ADR-027 D4).

        Example::

            for z_slice in img.iter_over("z"):
                ...

        Memory: ``O(one slice per iteration step)`` — each yielded
        :class:`Array` has ``axis`` removed from its axes list, carries
        metadata propagated per :meth:`sel`'s rules, and has its
        ``storage_ref`` set to a persisted zarr store.

        Raises:
            ValueError: if ``axis`` is not in :attr:`axes` or if
                :attr:`shape` is ``None`` (cannot determine iteration
                length).
        """
        if axis not in self.axes:
            raise ValueError(f"Axis {axis!r} not in {self.axes}")
        if self.shape is None:
            raise ValueError(f"{type(self).__name__}.iter_over() requires a known shape. This instance has shape=None.")
        axis_pos = self.axes.index(axis)
        axis_size = self.shape[axis_pos]
        for i in range(axis_size):
            yield self.sel(**{axis: i})

    # -- with_meta override (T-005's base only handles standard slots) ----

    @stable(since="0.3.1")
    def with_meta(self, **changes: Any) -> Self:
        """Return a copy with some typed ``meta`` fields changed.

        Like :meth:`DataObject.with_meta`, but also carries the
        array-specific fields (:attr:`axes`, :attr:`shape`, :attr:`dtype`,
        :attr:`chunk_shape`) onto the copy, which the base version cannot do
        because it does not know about them.

        Args:
            **changes: Field name / value pairs to update on the ``meta``
                model.

        Returns:
            A new array of the same type with the updated metadata.

        Raises:
            ValueError: if this array has no typed ``meta`` (only subclasses
                that declare a :attr:`Meta` model can use this).
        """
        if self._meta is None:
            raise ValueError(
                f"{type(self).__name__}.with_meta() requires a typed `meta` slot. "
                f"This instance has meta=None. Subclass with a class-level `Meta` "
                f"Pydantic model and pass an instance via the constructor to use "
                f"with_meta()."
            )

        from scistudio.core.meta import with_meta_changes

        new_meta = with_meta_changes(self._meta, **changes)
        new_framework = self._framework.derive()

        return type(self)(
            axes=list(self.axes),
            shape=self.shape,
            dtype=self.dtype,
            chunk_shape=self.chunk_shape,
            framework=new_framework,
            meta=new_meta,
            user=dict(self._user),
            storage_ref=self._storage_ref,
        )

    # -- to_memory transition override (ADR-031 backward compat) -----------

    @stable(since="0.3.1")
    def to_memory(self) -> Any:
        """Load the full array into memory and return it.

        Reads from storage when the array is persisted. If a loader has set
        in-memory data on this array but it has not been written to storage
        yet, that data is returned directly.

        Returns:
            The array data in its in-memory form (typically a NumPy array).

        Raises:
            ValueError: if there is neither a storage reference nor in-memory
                data to return.
        """
        if self._storage_ref is not None:
            return super().to_memory()
        # ADR-031 Addendum 2: use the declared _transient_data slot.
        if self._transient_data is not None:
            return self._transient_data
        raise ValueError("Cannot load data: no storage reference set.")

    # -- ergonomic accessor (ADR-052 §10) ----------------------------------

    @stable(since="0.3.1")
    def to_numpy(self) -> Any:
        """Return the array data as a NumPy ``ndarray``.

        A convenience reader for inspecting or exporting data. It wraps the
        materialised contents of :meth:`to_memory` in :func:`numpy.asarray`
        and does not replace ``to_memory``. Use it for a quick look or to
        hand data to other tools — not inside a block's main compute path,
        which should stay storage-aware.

        Returns:
            A :class:`numpy.ndarray` loaded from storage.
        """
        import numpy as np

        return np.asarray(self.to_memory())

    # -- worker subprocess reconstruction hooks (ADR-027 Addendum 1 §2) -----

    @classmethod
    @provisional(since="0.3.1")
    def reconstruct_extra_kwargs(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        """Rebuild an array's constructor arguments from saved metadata.

        Reads ``axes`` / ``shape`` / ``dtype`` / ``chunk_shape`` back out of
        the metadata produced by :meth:`serialise_extra_metadata`. Shape
        fields, which travel through JSON as lists, are turned back into
        tuples; ``shape`` and ``chunk_shape`` may be absent or ``None`` for a
        metadata-only array.

        Args:
            metadata: The saved metadata dict for one array.

        Returns:
            Keyword arguments to pass to ``cls(**kwargs)``.
        """
        shape_raw = metadata.get("shape")
        chunk_shape_raw = metadata.get("chunk_shape")
        return {
            "axes": list(metadata.get("axes", [])),
            "shape": tuple(shape_raw) if shape_raw is not None else None,
            "dtype": metadata.get("dtype"),
            "chunk_shape": tuple(chunk_shape_raw) if chunk_shape_raw is not None else None,
        }

    @classmethod
    @provisional(since="0.3.1")
    def serialise_extra_metadata(cls, obj: DataObject) -> dict[str, Any]:
        """Return an array's own fields for the saved metadata.

        The counterpart of :meth:`reconstruct_extra_kwargs`. Tuples become
        lists and the dtype becomes its canonical short name (for example
        ``"uint8"``) so the result is plain JSON.

        Args:
            obj: The array to serialise. Typed as :class:`DataObject` so it
                matches the base method's signature; the caller always passes
                an :class:`Array`.

        Returns:
            A JSON-serialisable dict of the array's fields.
        """
        assert isinstance(obj, Array), f"Expected Array, got {type(obj).__name__}"
        # ``obj.dtype`` may be a numpy dtype, a python type (``bool``,
        # ``int``), or a string.  ``str(bool)`` returns ``"<class 'bool'>"``
        # which round-trips into ``np.dtype("<class 'bool'>")`` and fails
        # with ``data type ... not understood``.  Normalise via
        # ``np.dtype()`` first so the persisted string is always the
        # canonical short form (``"bool"``, ``"uint8"``, ...).
        import numpy as np

        if obj.dtype is None:
            dtype_str: str | None = None
        else:
            try:
                dtype_str = str(np.dtype(obj.dtype))
            except TypeError:
                # Fall back to stringification if ``obj.dtype`` is something
                # numpy cannot interpret (shouldn't happen for well-formed
                # arrays; preserve old behaviour rather than crash here).
                dtype_str = str(obj.dtype)
        return {
            "axes": list(obj.axes),
            "shape": list(obj.shape) if obj.shape is not None else None,
            "dtype": dtype_str,
            "chunk_shape": list(obj.chunk_shape) if obj.chunk_shape is not None else None,
        }
