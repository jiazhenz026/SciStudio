"""DataFrame — columnar tabular data DataObject.

ADR-027 D2: this module is core-only. The legacy domain subclasses
(``PeakTable``, ``MetabPeakTable``) have been removed as of T-007 and
now belong in the ``scistudio-blocks-spectral`` plugin package. Code that
previously imported them should either switch to ``DataFrame(columns=..., ...)``
directly or depend on the spectral plugin.
"""

from __future__ import annotations

from typing import Any, Self

from scistudio.core.types.base import DataObject
from scistudio.stability import provisional, stable


@stable(since="0.3.1")
class DataFrame(DataObject):
    """Columnar tabular data, backed by Arrow/Parquet for large datasets.

    Attributes:
        columns: Column names, if known.
        row_count: Number of rows, if known.
        schema: Column-level type schema, if known.
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
        """Construct a DataFrame with optional column/schema information.

        Standard :class:`DataObject` slots (``framework``, ``meta``,
        ``user``, ``storage_ref``) are passed through ``**kwargs`` to
        :meth:`DataObject.__init__`.

        Args:
            data: Optional in-memory tabular data (e.g. Arrow table).
                Stored in ``_transient_data``; never serialised.
                ADR-031 Addendum 2.
        """
        super().__init__(**kwargs)
        self.columns = columns
        self.row_count = row_count
        self.schema = schema
        if data is not None:
            self._transient_data = data

    # -- with_meta override (T-005's base only handles standard slots) ----

    @stable(since="0.3.1")
    def with_meta(self, **changes: Any) -> Self:
        """Return a new DataFrame with the ``meta`` slot updated.

        Overrides :meth:`DataObject.with_meta` to propagate the
        DataFrame-specific constructor arguments (``columns``,
        ``row_count``, ``schema``). The base implementation only
        propagates the four standard DataObject slots (``framework``,
        ``meta``, ``user``, ``storage_ref``); without this override the
        call would lose the DataFrame-specific attributes on the
        returned instance.

        Raises:
            ValueError: if ``self.meta is None`` (no typed Meta to
                update). Only DataFrame subclasses that declare a
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

        Ergonomic accessor (ADR-052 §10): a read-only, additive wrapper
        over the inherited :meth:`to_memory` reader (which returns the
        canonical ``pyarrow.Table``). It never replaces ``to_memory``.
        Packages inherit this accessor and must not redefine it
        (ADR-052 §4.2), and it is kept out of the core data-flow path
        (ADR-052 §8) — for inspection / export only.

        Returns:
            A :class:`pandas.DataFrame` materialised from storage.
        """
        return self.to_memory().to_pandas()

    @stable(since="0.3.1")
    def to_numpy(self) -> Any:
        """Return the table values as a NumPy ``ndarray``.

        Ergonomic accessor (ADR-052 §10): a read-only, additive wrapper
        over :meth:`to_pandas` (and hence the inherited :meth:`to_memory`
        reader). It never replaces ``to_memory`` and is kept out of the
        core data-flow path (ADR-052 §8) — for inspection / export only.

        Returns:
            A :class:`numpy.ndarray` of the table values.
        """
        return self.to_pandas().to_numpy()

    # -- worker subprocess reconstruction hooks (ADR-027 Addendum 1 §2) -----

    @classmethod
    @provisional(since="0.3.1")
    def reconstruct_extra_kwargs(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        """Return ``DataFrame``-specific kwargs for worker reconstruction.

        Extracts ``columns`` / ``row_count`` / ``schema`` from the
        wire-format metadata sidecar. ``columns`` defaults to an empty
        list and ``schema`` to an empty dict when absent, which
        :class:`DataFrame.__init__` accepts.

        See ADR-027 Addendum 1 §2 ("D11' companion") for the full
        contract.
        """
        return {
            "columns": list(metadata.get("columns", [])),
            "row_count": metadata.get("row_count"),
            "schema": dict(metadata.get("schema", {}) or {}),
        }

    @classmethod
    @provisional(since="0.3.1")
    def serialise_extra_metadata(cls, obj: DataObject) -> dict[str, Any]:
        """Return ``DataFrame``-specific fields for the metadata sidecar.

        Symmetric counterpart of :meth:`reconstruct_extra_kwargs`.
        ``columns`` is copied to a new list and ``schema`` to a new
        dict so the returned payload is independent of the source
        instance.

        The parameter is typed as :class:`DataObject` to respect the
        Liskov substitution principle with the base classmethod; at
        runtime the caller only ever passes an instance of ``cls``.
        """
        assert isinstance(obj, DataFrame), f"Expected DataFrame, got {type(obj).__name__}"
        return {
            "columns": list(obj.columns) if obj.columns is not None else [],
            "row_count": obj.row_count,
            "schema": dict(obj.schema) if obj.schema is not None else {},
        }
