"""Array — N-dimensional array DataObject with named axes.

Implements ADR-027 D1 (instance-level axes with class-level schema) and
ADR-027 D4 (``sel`` / ``iter_over`` with Level 1 laziness).

ADR-027 D2: this module is core-only. The four legacy domain subclasses
(``Image``, ``MSImage``, ``SRSImage``, ``FluorImage``) have been removed
as of T-006 and now live in the ``scistudio-blocks-imaging`` plugin
package. Code that previously imported them should either switch to
``Array(axes=[...])`` directly or depend on the imaging plugin.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar, Self

from scistudio.core.types.base import DataObject


class Array(DataObject):
    """N-dimensional array, optionally chunked and backed by Zarr.

    ADR-027 D1: ``axes`` is an instance-level attribute passed via the
    constructor. Subclasses declare what axes they accept via three
    class-level ClassVars that form a small schema:

    - ``required_axes``: minimum set of axis names any instance must
      carry. Subclasses tighten this to enforce "must have ``y, x``" or
      "must have ``c``".
    - ``allowed_axes``: superset of axis names the class accepts.
      ``None`` means "no restriction"; a frozenset means "instance axes
      must be a subset of this set".
    - ``canonical_order``: preferred ordering of axes used by reorder
      operations and pretty-printing.

    The 6D axis alphabet for scientific imaging is::

        {"t", "z", "c", "lambda", "y", "x"}

    where ``t`` is time, ``z`` is depth, ``c`` is discrete channel,
    ``lambda`` is continuous spectral, ``y`` and ``x`` are the spatial
    axes. ``c`` (discrete channel) and ``lambda`` (continuous spectral)
    are distinct axes and may coexist in a single instance (ADR-027
    discussion #3).

    Plugin subclasses (e.g. ``FluorImage`` in ``scistudio-blocks-imaging``)
    tighten the schema::

        class FluorImage(Image):
            required_axes = frozenset({"y", "x", "c"})

    Attributes:
        axes: Per-instance axis labels, e.g. ``["t", "z", "c", "y", "x"]``.
        shape: Shape of the array (may be ``None`` for metadata-only).
        dtype: Element data type.
        chunk_shape: Chunk dimensions for lazy/chunked storage.
    """

    # Class-level schema (subclasses override). Defaults are maximally
    # permissive: no required axes, no allowed restriction, no canonical
    # order. Plugin subclasses (Image / FluorImage / ...) override.
    required_axes: ClassVar[frozenset[str]] = frozenset()
    allowed_axes: ClassVar[frozenset[str] | None] = None
    canonical_order: ClassVar[tuple[str, ...]] = ()

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
        """Construct an Array with explicit axes and shape.

        ``axes`` is required per ADR-027 D1. The other :class:`DataObject`
        slots (``framework``, ``meta``, ``user``, ``storage_ref``) are
        passed through ``**kwargs`` to
        :meth:`DataObject.__init__`.

        Args:
            data: Optional in-memory array data (e.g. numpy ndarray).
                Stored in ``_transient_data``; never serialised.
                ADR-031 Addendum 2.

        Raises:
            ValueError: if ``axes`` fails :meth:`_validate_axes` (missing
                required / disallowed / duplicate).
        """
        super().__init__(**kwargs)
        self.axes: list[str] = list(axes)
        self.shape: tuple[int, ...] | None = tuple(shape) if shape is not None else None
        self.dtype: Any = dtype
        self.chunk_shape: tuple[int, ...] | None = tuple(chunk_shape) if chunk_shape is not None else None
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
    def ndim(self) -> int:
        """Return the number of dimensions (length of ``axes``)."""
        return len(self.axes)

    def __array__(self, dtype: Any = None, copy: Any = None) -> Any:
        """Support ``np.asarray(array_obj)`` via the NumPy array protocol.

        Materialises the full data from storage via :meth:`to_memory`.
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

    def sel(self, **kwargs: int | slice) -> Array:
        """Select a sub-array along named axes (ADR-027 D4).

        Examples::

            img.sel(z=15, c=0)        # single z, single channel
            img.sel(z=slice(10, 20))  # z range

        Integer indices REMOVE the corresponding axis from the result.
        Slice objects KEEP the axis. Lists of indices and boolean masks
        are NOT supported in Phase 10.

        The result is always a plain :class:`Array` instance (not
        ``type(self)``). This deliberate choice sidesteps the problem
        that a reduced slice may no longer satisfy the source class's
        ``required_axes`` invariant (e.g. a ``FluorImage`` requiring
        ``{y, x, c}`` and a call to ``sel(c=0)`` produces axes
        ``[y, x]``). The returned :class:`Array` has
        ``required_axes = frozenset()``, so any axis subset is valid.

        Metadata inheritance follows ADR-027 D5:

        - ``framework``: derived (lineage hint ``derived_from = self.object_id``).
        - ``meta``: shared by reference (immutable Pydantic model).
        - ``user``: shallow copy.
        - ``axes``: reduced per the selection.

        ADR-031 Phase 3 (Task 17): when the backing storage is zarr,
        ``sel()`` delegates to ``ZarrBackend.slice()`` for partial reads
        instead of materialising the full array. For non-zarr backends,
        falls back to ``to_memory()`` + numpy indexing.

        Raises:
            ValueError: if any kwarg key is not in ``self.axes``, if any
                kwarg value is not ``int`` or ``slice``, or if the
                instance has no ``storage_ref``.
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

    def with_meta(self, **changes: Any) -> Self:
        """Return a new Array with the ``meta`` slot updated.

        Overrides :meth:`DataObject.with_meta` to propagate the
        Array-specific constructor arguments (``axes``, ``shape``,
        ``dtype``, ``chunk_shape``). The base implementation only
        propagates the four standard DataObject slots (``framework``,
        ``meta``, ``user``, ``storage_ref``); without this override the
        call would raise ``TypeError`` because ``Array.__init__``
        requires ``axes``.

        Raises:
            ValueError: if ``self.meta is None`` (no typed Meta to
                update). Only Array subclasses that declare a
                ``Meta`` ClassVar can use :meth:`with_meta`.
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

    def to_memory(self) -> Any:
        """Materialise the full data into an in-memory representation.

        ADR-031 D3 transition: if ``storage_ref`` is set, delegates to
        the base class (storage backend read). If ``_data`` was set
        transiently by a loader before ``_auto_flush`` persists it,
        returns that data directly. This backward-compat path will be
        removed once all loaders write to storage directly.
        """
        if self._storage_ref is not None:
            return super().to_memory()
        # ADR-031 Addendum 2: use the declared _transient_data slot.
        if self._transient_data is not None:
            return self._transient_data
        raise ValueError("Cannot load data: no storage reference set.")

    # -- worker subprocess reconstruction hooks (ADR-027 Addendum 1 §2) -----

    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        """Return ``Array``-specific kwargs for worker reconstruction.

        Extracts ``axes`` / ``shape`` / ``dtype`` / ``chunk_shape`` from
        the wire-format metadata sidecar. Shape-like fields are
        converted back into tuples (they round-trip through JSON as
        lists). ``shape`` and ``chunk_shape`` may be absent or ``None``
        for metadata-only instances.

        See ADR-027 Addendum 1 §2 ("D11' companion") for the full
        contract.
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
    def _serialise_extra_metadata(cls, obj: DataObject) -> dict[str, Any]:
        """Return ``Array``-specific fields for the metadata sidecar.

        Symmetric counterpart of :meth:`_reconstruct_extra_kwargs`.
        Tuples are converted to lists so the payload is JSON-clean;
        ``dtype`` is stringified because numpy dtypes are not natively
        JSON-serialisable.

        The parameter is typed as :class:`DataObject` (not :class:`Array`)
        to respect the Liskov substitution principle with the base
        classmethod. T-014's worker calls
        ``type(obj)._serialise_extra_metadata(obj)`` polymorphically, so
        the override must accept any ``DataObject`` the worker hands in;
        at runtime the caller will only ever pass an instance of
        ``cls`` (or a subclass).
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
