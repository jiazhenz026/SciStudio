"""Columnar tables (:class:`DataFrame`).

The data type for tabular results — rows and named columns, like a
spreadsheet or a pandas DataFrame. It is backed by Arrow/Parquet, so large
tables live on disk and load lazily. Domain-specific tables (such as peak
tables) live in plugin packages and subclass this.
"""

from __future__ import annotations

from typing import Any, Self

from scistudio.core.types.base import DataObject
from scistudio.stability import provisional, stable


@stable(since="0.3.1")
class DataFrame(DataObject):
    """Columnar table of rows and named columns, backed by Arrow/Parquet.

    Use this for any tabular result. The canonical in-memory form is a
    ``pyarrow.Table``; :meth:`to_pandas` and :meth:`to_numpy` are convenience
    readers for inspection and export. Large tables stay on disk and are read
    lazily.

    Example:
        >>> from scistudio.core.types import DataFrame
        >>> table = DataFrame(columns=["mz", "intensity"], row_count=1024)
        >>> table.columns
        ['mz', 'intensity']
    """

    @stable(since="0.3.1")
    def __init__(
        self,
        *,
        columns: list[str] | None = None,
        row_count: int | None = None,
        schema: dict[str, Any] | None = None,
        data: Any = None,
        **kwargs: Any,
    ) -> None:
        """Construct a table, optionally with column and schema information.

        Args:
            columns: Column names, if known.
            row_count: Number of rows, if known.
            schema: Column-level type schema, if known.
            data: Optional in-memory table (for example a ``pyarrow.Table``).
                Held only until the framework writes it to storage; never
                serialised directly.
            **kwargs: The shared :class:`DataObject` slots (``framework``,
                ``meta``, ``user``, ``storage_ref``).
        """
        super().__init__(**kwargs)
        self.columns = columns
        """Column names, or ``None`` when not known."""
        self.row_count = row_count
        """Number of rows, or ``None`` when not known."""
        self.schema = schema
        """Column-level type schema, or ``None`` when not known."""
        if data is not None:
            self._transient_data = data

    # -- with_meta override (T-005's base only handles standard slots) ----

    @stable(since="0.3.1")
    def with_meta(self, **changes: Any) -> Self:
        """Return a copy with some typed ``meta`` fields changed.

        Like :meth:`DataObject.with_meta`, but also carries the table-specific
        fields (:attr:`columns`, :attr:`row_count`, :attr:`schema`) onto the
        copy.

        Args:
            **changes: Field name / value pairs to update on the ``meta``
                model.

        Returns:
            A new table of the same type with the updated metadata.

        Raises:
            ValueError: if this table has no typed ``meta`` (only subclasses
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
            columns=list(self.columns) if self.columns is not None else None,
            row_count=self.row_count,
            schema=dict(self.schema) if self.schema is not None else None,
            framework=new_framework,
            meta=new_meta,
            user=dict(self._user),
            storage_ref=self._storage_ref,
        )

    # -- ergonomic accessors (ADR-052 §10) ---------------------------------

    @stable(since="0.3.1")
    def to_pandas(self) -> Any:
        """Return the table as a :class:`pandas.DataFrame`.

        A convenience reader for inspecting or exporting the table. It
        materialises the canonical ``pyarrow.Table`` from storage and
        converts it; it does not replace :meth:`to_memory`. Use it for a
        quick look or to hand data to pandas-based tools — not inside a
        block's main compute path.

        Returns:
            A :class:`pandas.DataFrame` loaded from storage.
        """
        return self.to_memory().to_pandas()

    @stable(since="0.3.1")
    def to_numpy(self) -> Any:
        """Return the table values as a NumPy ``ndarray``.

        A convenience reader, built on :meth:`to_pandas`, for inspection or
        export only; it does not replace :meth:`to_memory`.

        Returns:
            A :class:`numpy.ndarray` of the table values.
        """
        return self.to_pandas().to_numpy()

    # -- worker subprocess reconstruction hooks (ADR-027 Addendum 1 §2) -----

    @classmethod
    @provisional(since="0.3.1")
    def reconstruct_extra_kwargs(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        """Rebuild a table's constructor arguments from saved metadata.

        Reads ``columns`` / ``row_count`` / ``schema`` back out of the
        metadata produced by :meth:`serialise_extra_metadata`. Missing
        ``columns`` becomes an empty list and missing ``schema`` an empty
        dict, both of which the constructor accepts.

        Args:
            metadata: The saved metadata dict for one table.

        Returns:
            Keyword arguments to pass to ``cls(**kwargs)``.
        """
        return {
            "columns": list(metadata.get("columns", [])),
            "row_count": metadata.get("row_count"),
            "schema": dict(metadata.get("schema", {}) or {}),
        }

    @classmethod
    @provisional(since="0.3.1")
    def serialise_extra_metadata(cls, obj: DataObject) -> dict[str, Any]:
        """Return a table's own fields for the saved metadata.

        The counterpart of :meth:`reconstruct_extra_kwargs`. ``columns`` and
        ``schema`` are copied into a fresh list and dict so the result is
        independent of the source table.

        Args:
            obj: The table to serialise. Typed as :class:`DataObject` so it
                matches the base method's signature; the caller always passes
                a :class:`DataFrame`.

        Returns:
            A JSON-serialisable dict of the table's fields.
        """
        assert isinstance(obj, DataFrame), f"Expected DataFrame, got {type(obj).__name__}"
        return {
            "columns": list(obj.columns) if obj.columns is not None else [],
            "row_count": obj.row_count,
            "schema": dict(obj.schema) if obj.schema is not None else {},
        }
