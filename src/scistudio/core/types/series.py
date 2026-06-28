"""Series — 1D indexed data DataObject (time series, chromatograms, spectra).

ADR-027 D2: this module is core-only. The legacy domain subclasses
(``Spectrum``, ``RamanSpectrum``, ``MassSpectrum``) have been removed as
of T-007 and now belong in the ``scistudio-blocks-spectral`` plugin
package. Code that previously imported them should either switch to
``Series(index_name=..., value_name=...)`` directly or depend on the
spectral plugin.
"""

from __future__ import annotations

from typing import Any, Self

from scistudio.core.types.base import DataObject
from scistudio.stability import provisional, stable


@stable(since="0.3.1")
class Series(DataObject):
    """One-dimensional indexed data (time series, chromatogram, spectrum).

    Persisted Series payloads use the Arrow/Parquet backend. In-memory
    payloads are normalised to a ``pyarrow.Table`` at the persistence boundary
    so ``to_memory()`` remains table-shaped after worker reconstruction.

    Attributes:
        index_name: Label for the index axis (e.g. ``"wavenumber"``,
            ``"mz"``, ``"time"``).
        value_name: Label for the value axis (e.g. ``"intensity"``).
        length: Number of data points, if known.
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
        """Construct a Series with optional axis labels and length.

        Standard :class:`DataObject` slots (``framework``, ``meta``,
        ``user``, ``storage_ref``) are passed through ``**kwargs`` to
        :meth:`DataObject.__init__`.

        Args:
            data: Optional in-memory series data (e.g. Arrow table).
                Stored in ``_transient_data``; never serialised.
                ADR-031 Addendum 2.
        """
        super().__init__(**kwargs)
        self.index_name = index_name
        self.value_name = value_name
        self.length = length
        if data is not None:
            self._transient_data = data

    def get_in_memory_data(self) -> Any:
        if self._storage_ref is not None:
            return self.to_memory()
        return _series_table_payload(self._transient_data, self.value_name, type(self).__name__)

    # -- with_meta override (T-005's base only handles standard slots) ----

    @stable(since="0.3.1")
    def with_meta(self, **changes: Any) -> Self:
        """Return a new Series with the ``meta`` slot updated.

        Overrides :meth:`DataObject.with_meta` to propagate the
        Series-specific constructor arguments (``index_name``,
        ``value_name``, ``length``). The base implementation only
        propagates the four standard DataObject slots (``framework``,
        ``meta``, ``user``, ``storage_ref``); without this override the
        call would lose the Series-specific attributes on the returned
        instance.

        Raises:
            ValueError: if ``self.meta is None`` (no typed Meta to
                update). Only Series subclasses that declare a ``Meta``
                ClassVar can use :meth:`with_meta`.
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

        Ergonomic accessor (ADR-052 §10): a read-only, additive wrapper
        over the inherited :meth:`to_memory` reader (which returns the
        canonical single-column ``pyarrow.Table``). It never replaces
        ``to_memory``. Packages inherit this accessor and must not
        redefine it (ADR-052 §4.2), and it is kept out of the core
        data-flow path (ADR-052 §8) — for inspection / export only.

        Returns:
            A :class:`pandas.Series` materialised from storage.
        """
        return self.to_memory().column(0).to_pandas()

    @stable(since="0.3.1")
    def to_numpy(self) -> Any:
        """Return the series values as a NumPy ``ndarray``.

        Ergonomic accessor (ADR-052 §10): a read-only, additive wrapper
        over :meth:`to_pandas` (and hence the inherited :meth:`to_memory`
        reader). It never replaces ``to_memory`` and is kept out of the
        core data-flow path (ADR-052 §8) — for inspection / export only.

        Returns:
            A :class:`numpy.ndarray` of the series values.
        """
        return self.to_pandas().to_numpy()

    # -- worker subprocess reconstruction hooks (ADR-027 Addendum 1 §2) -----

    @classmethod
    @provisional(since="0.3.1")
    def reconstruct_extra_kwargs(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        """Return ``Series``-specific kwargs for worker reconstruction.

        Extracts ``index_name`` / ``value_name`` / ``length`` from the
        wire-format metadata sidecar. All three are optional on the
        constructor; a missing key round-trips as ``None``.

        See ADR-027 Addendum 1 §2 ("D11' companion") for the full
        contract.
        """
        return {
            "index_name": metadata.get("index_name"),
            "value_name": metadata.get("value_name"),
            "length": metadata.get("length"),
        }

    @classmethod
    @provisional(since="0.3.1")
    def serialise_extra_metadata(cls, obj: DataObject) -> dict[str, Any]:
        """Return ``Series``-specific fields for the metadata sidecar.

        Symmetric counterpart of :meth:`reconstruct_extra_kwargs`.
        All three fields are already JSON-primitive (``str | None`` /
        ``int | None``) and need no conversion.

        The parameter is typed as :class:`DataObject` to respect the
        Liskov substitution principle with the base classmethod; at
        runtime the caller only ever passes an instance of ``cls``.
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
