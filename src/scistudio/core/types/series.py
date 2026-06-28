"""One-dimensional indexed data (:class:`Series`).

The data type for a single sequence of values against an index — a time
series, a chromatogram, a spectrum. It is stored as a one-column
Arrow/Parquet table. Domain-specific series (such as spectra) live in plugin
packages and subclass this.
"""

from __future__ import annotations

from typing import Any, Self

from scistudio.core.types.base import DataObject
from scistudio.stability import internal, provisional, stable


@stable(since="0.3.1")
class Series(DataObject):
    """One-dimensional indexed data: a time series, chromatogram, or spectrum.

    A single run of values paired with an index axis (for example intensity
    vs. wavenumber). It is persisted as a one-column Arrow/Parquet table, so
    :meth:`to_memory` returns a ``pyarrow.Table`` even after the series has
    crossed a worker subprocess.

    Example:
        >>> from scistudio.core.types import Series
        >>> spec = Series(index_name="wavenumber", value_name="intensity", length=1024)
        >>> spec.index_name
        'wavenumber'
    """

    @stable(since="0.3.1")
    def __init__(
        self,
        *,
        index_name: str | None = None,
        value_name: str | None = None,
        length: int | None = None,
        data: Any = None,
        **kwargs: Any,
    ) -> None:
        """Construct a series, optionally with axis labels and length.

        Args:
            index_name: Label for the index axis, e.g. ``"time"``.
            value_name: Label for the value axis, e.g. ``"intensity"``.
            length: Number of data points, if known.
            data: Optional in-memory series data (for example a
                ``pyarrow.Table`` or a value array). Held only until the
                framework writes it to storage; never serialised directly.
            **kwargs: The shared :class:`DataObject` slots (``framework``,
                ``meta``, ``user``, ``storage_ref``).
        """
        super().__init__(**kwargs)
        self.index_name = index_name
        """Label for the index axis (e.g. ``"wavenumber"``, ``"mz"``, ``"time"``)."""
        self.value_name = value_name
        """Label for the value axis (e.g. ``"intensity"``)."""
        self.length = length
        """Number of data points, or ``None`` when not known."""
        if data is not None:
            self._transient_data = data

    @internal()
    def get_in_memory_data(self) -> Any:
        if self._storage_ref is not None:
            return self.to_memory()
        return _series_table_payload(self._transient_data, self.value_name, type(self).__name__)

    # -- with_meta override (T-005's base only handles standard slots) ----

    @stable(since="0.3.1")
    def with_meta(self, **changes: Any) -> Self:
        """Return a copy with some typed ``meta`` fields changed.

        Like :meth:`DataObject.with_meta`, but also carries the
        series-specific fields (:attr:`index_name`, :attr:`value_name`,
        :attr:`length`) onto the copy.

        Args:
            **changes: Field name / value pairs to update on the ``meta``
                model.

        Returns:
            A new series of the same type with the updated metadata.

        Raises:
            ValueError: if this series has no typed ``meta`` (only subclasses
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
            index_name=self.index_name,
            value_name=self.value_name,
            length=self.length,
            framework=new_framework,
            meta=new_meta,
            user=dict(self._user),
            storage_ref=self._storage_ref,
        )

    # -- ergonomic accessors (ADR-052 §10) ---------------------------------

    @stable(since="0.3.1")
    def to_pandas(self) -> Any:
        """Return the series as a :class:`pandas.Series`.

        A convenience reader for inspecting or exporting the series. It
        materialises the canonical single-column ``pyarrow.Table`` from
        storage and converts it; it does not replace :meth:`to_memory`. Use
        it for a quick look or with pandas-based tools — not inside a block's
        main compute path.

        Returns:
            A :class:`pandas.Series` loaded from storage.
        """
        return self.to_memory().column(0).to_pandas()

    @stable(since="0.3.1")
    def to_numpy(self) -> Any:
        """Return the series values as a NumPy ``ndarray``.

        A convenience reader, built on :meth:`to_pandas`, for inspection or
        export only; it does not replace :meth:`to_memory`.

        Returns:
            A :class:`numpy.ndarray` of the series values.
        """
        return self.to_pandas().to_numpy()

    # -- worker subprocess reconstruction hooks (ADR-027 Addendum 1 §2) -----

    @classmethod
    @provisional(since="0.3.1")
    def reconstruct_extra_kwargs(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        """Rebuild a series' constructor arguments from saved metadata.

        Reads ``index_name`` / ``value_name`` / ``length`` back out of the
        metadata produced by :meth:`serialise_extra_metadata`. All three are
        optional; a missing key round-trips as ``None``.

        Args:
            metadata: The saved metadata dict for one series.

        Returns:
            Keyword arguments to pass to ``cls(**kwargs)``.
        """
        return {
            "index_name": metadata.get("index_name"),
            "value_name": metadata.get("value_name"),
            "length": metadata.get("length"),
        }

    @classmethod
    @provisional(since="0.3.1")
    def serialise_extra_metadata(cls, obj: DataObject) -> dict[str, Any]:
        """Return a series' own fields for the saved metadata.

        The counterpart of :meth:`reconstruct_extra_kwargs`. All three fields
        are already JSON primitives and need no conversion.

        Args:
            obj: The series to serialise. Typed as :class:`DataObject` so it
                matches the base method's signature; the caller always passes
                a :class:`Series`.

        Returns:
            A JSON-serialisable dict of the series' fields.
        """
        assert isinstance(obj, Series), f"Expected Series, got {type(obj).__name__}"
        return {
            "index_name": obj.index_name,
            "value_name": obj.value_name,
            "length": obj.length,
        }


def _series_table_payload(data: Any, value_name: str | None, type_name: str) -> Any:
    if data is None:
        raise ValueError(f"{type_name} has no in-memory data to persist.")

    import pyarrow as pa

    if isinstance(data, pa.Table):
        return data
    return pa.table({value_name or "value": pa.array(data)})
