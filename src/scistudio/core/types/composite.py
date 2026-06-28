"""Named bundles of several data objects (:class:`CompositeData`).

Use :class:`CompositeData` when one logical result is really several data
objects that belong together — for example a table of measurements plus the
image they came from, kept in named slots. Domain-specific bundles
(single-cell and spatial-omics containers) live in their own plugin packages
and subclass this with a fixed slot layout.
"""

from __future__ import annotations

from typing import Any, ClassVar, Self

from scistudio.core.types.base import DataObject
from scistudio.stability import internal, stable


@stable(since="0.3.1")
class CompositeData(DataObject):
    """A bundle of named :class:`DataObject` slots.

    Holds several data objects together under string keys — think "the image
    goes in the ``image`` slot, the measurements in the ``table`` slot". A
    subclass can fix which slots exist and what type each must be by setting
    :attr:`expected_slots`; a plain :class:`CompositeData` accepts any slots.

    Example:
        >>> from scistudio.core.types import CompositeData, Text
        >>> bundle = CompositeData()
        >>> bundle.set("notes", Text(content="ok"))
        >>> bundle.slot_names
        ['notes']
        >>> bundle.get("notes").content
        'ok'
    """

    expected_slots: ClassVar[dict[str, type]] = {}
    """Required slot layout for a subclass: slot name to expected type.

    Empty on plain :class:`CompositeData` (any slot is accepted). When a
    subclass fills this in, :meth:`set` rejects a value whose type does not
    match the entry for that slot.
    """

    @stable(since="0.3.1")
    def __init__(
        self,
        *,
        slots: dict[str, DataObject] | None = None,
        **kwargs: Any,
    ) -> None:
        """Construct a bundle, optionally pre-filled with slots.

        Args:
            slots: Optional initial mapping of slot name to
                :class:`DataObject`. Each entry is validated the same way
                :meth:`set` validates it.
            **kwargs: The shared :class:`DataObject` slots (``framework``,
                ``meta``, ``user``, ``storage_ref``). These metadata slots
                are separate from the named data slots this class holds.

        Raises:
            TypeError: if an initial slot value does not match the type
                declared for it in :attr:`expected_slots`.
        """
        super().__init__(**kwargs)
        self._slots: dict[str, DataObject] = {}
        if slots:
            for name, obj in slots.items():
                self.set(name, obj)

    @stable(since="0.3.1")
    def get(self, slot_name: str) -> DataObject:
        """Return the data object stored under *slot_name*.

        Args:
            slot_name: The slot to read.

        Returns:
            The :class:`DataObject` in that slot.

        Raises:
            KeyError: if the slot has not been populated.
        """
        if slot_name not in self._slots:
            raise KeyError(f"Slot '{slot_name}' is not populated.")
        return self._slots[slot_name]

    @stable(since="0.3.1")
    def set(self, slot_name: str, data: DataObject) -> None:
        """Store *data* under *slot_name*.

        If the class declares an expected type for that slot (via
        :attr:`expected_slots`), *data* must be an instance of it.

        Args:
            slot_name: The slot to write.
            data: The data object to store.

        Raises:
            TypeError: if *data* does not match the slot's expected type.
        """
        expected = self.slot_types()
        if expected and slot_name in expected:
            expected_type = expected[slot_name]
            if not isinstance(data, expected_type):
                raise TypeError(f"Slot '{slot_name}' expects {expected_type.__name__}, got {type(data).__name__}.")
        self._slots[slot_name] = data

    @stable(since="0.3.1")
    def slot_types(self) -> dict[str, type]:
        """Return this class's expected slot-type mapping.

        Returns:
            A copy of :attr:`expected_slots` (slot name to expected type).
        """
        return dict(self.expected_slots)

    @property
    @stable(since="0.3.1")
    def slot_names(self) -> list[str]:
        """The names of the currently populated slots.

        Returns:
            A list of slot names that have a value set.
        """
        return list(self._slots.keys())

    @internal()
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

    @stable(since="0.3.1")
    def with_meta(self, **changes: Any) -> Self:
        """Return a copy with some typed ``meta`` fields changed.

        Like :meth:`DataObject.with_meta`, but also carries the populated
        slots onto the copy. The slot children are shared by reference, which
        is safe because each child is independently immutable through its own
        :meth:`with_meta`.

        Args:
            **changes: Field name / value pairs to update on the ``meta``
                model.

        Returns:
            A new bundle of the same type with the updated metadata.

        Raises:
            ValueError: if this bundle has no typed ``meta`` (only subclasses
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
            slots=dict(self._slots) if self._slots else None,
            framework=new_framework,
            meta=new_meta,
            user=dict(self._user),
            storage_ref=self._storage_ref,
        )

    # -- worker subprocess reconstruction hooks (ADR-027 Addendum 1 §2) -----
    #
    # ``CompositeData`` does NOT override ``serialise_extra_metadata`` /
    # ``reconstruct_extra_kwargs`` (the ADR-052 §3.7 hook exception). Its
    # slots are nested ``DataObject``s, and
    # the recursion that (de)serialises them is owned by the serialiser itself
    # (``scistudio.core.types.serialization._serialise_one`` /
    # ``_reconstruct_one`` handle the ``CompositeData`` case directly).
    #
    # Round-4 no-cycles (#1342): the previous override imported the serialiser
    # from inside the method body, i.e. the *type* reached back to the
    # serialiser. That ``composite -> serialisation`` edge — together with
    # ``serialisation -> registry`` and ``registry -> composite`` — closed a
    # core.types-internal import cycle. Hosting the recursion on the serialiser
    # (which is the authority on (de)serialising any ``DataObject``) keeps this
    # module a leaf, so the wire format is unchanged but the cycle is gone.
