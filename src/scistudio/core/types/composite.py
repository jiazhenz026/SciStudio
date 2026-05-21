"""CompositeData — named collection of heterogeneous DataObject slots.

ADR-027 D2: this module is core-only. The legacy domain subclasses
(``AnnData``, ``SpatialData``) have been removed as of T-007 and now
belong in dedicated plugin packages (``scistudio-blocks-singlecell``,
``scistudio-blocks-spatial-omics``). Code that previously imported them
should either define a local subclass with the appropriate
``expected_slots`` or depend on the respective plugin.
"""

from __future__ import annotations

from typing import Any, ClassVar, Self

from scistudio.core.types.base import DataObject


class CompositeData(DataObject):
    """A named collection of heterogeneous :class:`DataObject` slots.

    Subclasses declare :attr:`expected_slots` as a class variable mapping
    slot names to their expected types.

    Attributes:
        expected_slots: Class-level mapping of slot name to expected type.
    """

    expected_slots: ClassVar[dict[str, type]] = {}

    def __init__(
        self,
        *,
        slots: dict[str, DataObject] | None = None,
        **kwargs: Any,
    ) -> None:
        """Construct a CompositeData with optional initial slot mapping.

        Standard :class:`DataObject` slots (``framework``, ``meta``,
        ``user``, ``storage_ref``) are passed through ``**kwargs`` to
        :meth:`DataObject.__init__`. Note that the :class:`CompositeData`
        ``slots`` attribute is distinct from the DataObject metadata
        slots — it holds child :class:`DataObject` instances keyed by
        slot name.
        """
        super().__init__(**kwargs)
        self._slots: dict[str, DataObject] = {}
        if slots:
            for name, obj in slots.items():
                self.set(name, obj)

    def get(self, slot_name: str) -> DataObject:
        """Retrieve the :class:`DataObject` stored in *slot_name*."""
        if slot_name not in self._slots:
            raise KeyError(f"Slot '{slot_name}' is not populated.")
        return self._slots[slot_name]

    def set(self, slot_name: str, data: DataObject) -> None:
        """Store *data* in *slot_name*, validating against expected_slots if defined."""
        expected = self.slot_types()
        if expected and slot_name in expected:
            expected_type = expected[slot_name]
            if not isinstance(data, expected_type):
                raise TypeError(f"Slot '{slot_name}' expects {expected_type.__name__}, got {type(data).__name__}.")
        self._slots[slot_name] = data

    def slot_types(self) -> dict[str, type]:
        """Return the expected slot-type mapping declared on this class."""
        return dict(self.expected_slots)

    @property
    def slot_names(self) -> list[str]:
        """Return the names of all currently populated slots."""
        return list(self._slots.keys())

    def get_in_memory_data(self) -> Any:
        """Return dict of slot data for composite persistence.

        Each slot value is packaged as ``(backend_name, raw_data)`` for
        :class:`CompositeStore.write`.
        """
        from scistudio.core.storage.backend_router import get_router

        if not self._slots:
            return super().get_in_memory_data()

        router = get_router()
        result: dict[str, tuple[str, Any]] = {}
        for slot_name, slot_obj in self._slots.items():
            backend_name = router.backend_name_for(type(slot_obj))
            slot_data = slot_obj.get_in_memory_data()
            result[slot_name] = (backend_name, slot_data)
        return result

    # -- with_meta override (T-005's base only handles standard slots) ----

    def with_meta(self, **changes: Any) -> Self:
        """Return a new CompositeData with the ``meta`` slot updated.

        Overrides :meth:`DataObject.with_meta` to propagate the
        CompositeData-specific constructor argument (the ``slots``
        mapping). Slots themselves are shared by reference on the new
        instance — composite slot sharing is intentional because the
        child :class:`DataObject` instances are independently immutable
        via their own ``with_meta`` methods; T-013 will revisit deep
        slot copying during worker-subprocess reconstruction.

        The base implementation only propagates the four standard
        DataObject slots (``framework``, ``meta``, ``user``,
        ``storage_ref``); without this override the call would drop
        the populated slot children on the returned instance.

        Raises:
            ValueError: if ``self.meta is None`` (no typed Meta to
                update). Only CompositeData subclasses that declare a
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
            slots=dict(self._slots) if self._slots else None,
            framework=new_framework,
            meta=new_meta,
            user=dict(self._user),
            storage_ref=self._storage_ref,
        )

    # -- worker subprocess reconstruction hooks (ADR-027 Addendum 1 §2) -----

    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        """Return ``CompositeData``-specific kwargs for worker reconstruction.

        Each composite slot is itself a typed :class:`DataObject`, so
        reconstruction is recursive: every entry in
        ``metadata["slots"]`` is a full wire-format payload item that
        we hand to
        :func:`scistudio.core.types.serialization._reconstruct_one`.

        The import of ``_reconstruct_one`` lives **inside the method
        body** (not at module top) to break an otherwise-circular
        load-time chain: ``composite`` would import ``serialization``,
        and the real T-014 ``serialization`` imports every base class
        — including ``composite``. The inside-the-method import delays
        the edge until the classmethod is actually called, by which
        time both modules are fully loaded. See Open Question 1 of the
        Phase 10 implementation standards doc and ADR-027 Addendum 1
        §2 ("D11' companion") for the full rationale.

        Note that in T-013, ``_reconstruct_one`` is a stub that raises
        :class:`NotImplementedError`. T-014 replaces the stub body
        with the real implementation. Code that needs to round-trip
        composite data **must wait for T-014**; T-013 only establishes
        the hook contract.

        Args:
            metadata: The ``metadata`` dict from the wire-format payload
                item. Expected to contain a ``"slots"`` key whose value
                is a ``{slot_name: payload_item_dict}`` mapping.

        Returns:
            A dict with a single ``"slots"`` key whose value is a
            ``{slot_name: DataObject}`` mapping suitable for
            :meth:`CompositeData.__init__`.
        """
        # Lazy import to break the load-time cycle. See docstring for
        # rationale. T-013 ships this as a NotImplementedError stub;
        # T-014 replaces the body with the real reconstruction logic.
        from scistudio.core.types.serialization import _reconstruct_one

        slot_payloads = metadata.get("slots", {}) or {}
        slots = {slot_name: _reconstruct_one(slot_payload) for slot_name, slot_payload in slot_payloads.items()}
        return {"slots": slots}

    @classmethod
    def _serialise_extra_metadata(cls, obj: DataObject) -> dict[str, Any]:
        """Return ``CompositeData``-specific fields for the metadata sidecar.

        Symmetric counterpart of :meth:`_reconstruct_extra_kwargs`.
        Each slot is itself a typed :class:`DataObject`; we delegate to
        :func:`scistudio.core.types.serialization._serialise_one` (full
        implementation in T-014) to produce a full wire-format payload
        item per slot, then assemble into a ``{slot_name: payload_item}``
        mapping.

        The import of ``_serialise_one`` is inside the method body for
        the same cycle-breaking reason as
        :meth:`_reconstruct_extra_kwargs`; see that method's docstring.

        The parameter is typed as :class:`DataObject` to respect the
        Liskov substitution principle with the base classmethod; at
        runtime the caller only ever passes a ``CompositeData``.
        """
        assert isinstance(obj, CompositeData), f"Expected CompositeData, got {type(obj).__name__}"
        # Lazy import to break the load-time cycle. See
        # _reconstruct_extra_kwargs docstring for rationale.
        from scistudio.core.types.serialization import _serialise_one

        return {"slots": {slot_name: _serialise_one(slot_obj) for slot_name, slot_obj in obj._slots.items()}}
