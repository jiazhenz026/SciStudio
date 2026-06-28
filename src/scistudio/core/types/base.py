"""The shared base class for all data objects, plus its type descriptor.

Defines :class:`DataObject` (the base every concrete data type inherits
from) and :class:`TypeSignature` (a small record of an object's type
chain, used to check that two blocks' ports are compatible).

Every :class:`DataObject` carries three separate metadata slots, each with
a clear owner:

- ``framework`` — managed by SciStudio (identity, lineage, provenance).
  Block authors read it but do not edit it.
- ``meta`` — typed, validated metadata for a specific data kind (a Pydantic
  ``BaseModel``), or ``None`` on the plain base class.
- ``user`` — a free-form ``dict`` for anything you want to attach. The
  framework never interprets it, so it must be JSON-serialisable (it is
  sent between processes).

These three slots are the only metadata API.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Self

from pydantic import BaseModel

from scistudio.core.meta import FrameworkMeta
from scistudio.core.storage.ref import StorageReference
from scistudio.stability import internal, provisional, stable

# Warn when to_memory() would load more than this many bytes (2 GB).
_SIZE_WARNING_THRESHOLD = 2 * 1024 * 1024 * 1024


def _get_backend(ref: StorageReference) -> Any:
    """Return the appropriate backend instance for *ref*.

    ADR-031 D2: moved from proxy.py to be shared by DataObject methods.
    """
    from scistudio.core.storage.arrow_backend import ArrowBackend
    from scistudio.core.storage.composite_store import CompositeStore
    from scistudio.core.storage.filesystem import FilesystemBackend
    from scistudio.core.storage.zarr_backend import ZarrBackend

    backends: dict[str, Any] = {
        "zarr": ZarrBackend(),
        "arrow": ArrowBackend(),
        "filesystem": FilesystemBackend(),
        "composite": CompositeStore(),
    }
    if ref.backend not in backends:
        raise ValueError(f"Unknown backend: {ref.backend}")
    return backends[ref.backend]


@stable(since="0.3.1")
@dataclass
class TypeSignature:
    """The semantic type of a :class:`DataObject`, used for port matching.

    A signature records the chain of type names from most general to most
    specific (for example ``["DataObject", "Array"]``). SciStudio compares
    these signatures to decide whether the output of one block may be fed
    into the input port of the next.

    You rarely build one by hand: :meth:`from_type` derives it from a class,
    and :attr:`DataObject.dtype_info` returns the signature of a live object.

    Example:
        >>> from scistudio.core.types import Array, TypeSignature
        >>> sig = TypeSignature.from_type(Array)
        >>> sig.type_chain
        ['DataObject', 'Array']
        >>> sig.matches(TypeSignature(type_chain=["DataObject"]))
        True
    """

    type_chain: list[str]
    """Type names from most general to most specific.

    For example ``["DataObject", "Array"]``. A signature matches another
    when this chain starts with the other's chain.
    """
    slot_schema: dict[str, str] | None = field(default=None)
    """Mapping of slot name to type name for composite types, else ``None``.

    Used to compare the named slots of a :class:`CompositeData`.
    """
    required_axes: frozenset[str] | None = field(default=None)
    """Axis names an :class:`Array` subclass requires, or ``None``.

    Populated by :meth:`from_type` from the class's ``required_axes`` when
    that set is non-empty, so a port check can require that an incoming
    array carries at least those axes. ``None`` for non-array types and for
    plain :class:`Array` (which requires no specific axes).
    """

    @stable(since="0.3.1")
    def matches(self, other: TypeSignature) -> bool:
        """Return whether this type can stand in for *other*.

        This is the check a port uses to accept incoming data. It returns
        ``True`` when this signature is *other* or a more specific subtype of
        it — concretely, when *other*'s type chain is a prefix of this one.
        For composite types, every slot *other* names must also be present
        here with a matching type.

        Args:
            other: The signature the receiving port expects.

        Returns:
            ``True`` if an object of this type is acceptable where *other* is
            expected, ``False`` otherwise.

        Example:
            >>> from scistudio.core.types import Array, DataObject, TypeSignature
            >>> array_sig = TypeSignature.from_type(Array)
            >>> object_sig = TypeSignature.from_type(DataObject)
            >>> array_sig.matches(object_sig)
            True
            >>> object_sig.matches(array_sig)
            False
        """
        if len(other.type_chain) > len(self.type_chain):
            return False
        if self.type_chain[: len(other.type_chain)] != other.type_chain:
            return False
        # Slot schema comparison for composites
        if other.slot_schema is not None:
            if self.slot_schema is None:
                return False
            for slot_name, expected_type in other.slot_schema.items():
                if slot_name not in self.slot_schema:
                    return False
                if self.slot_schema[slot_name] != expected_type:
                    return False
        return True

    @classmethod
    @stable(since="0.3.1")
    def from_type(cls, data_type: type) -> TypeSignature:
        """Build a :class:`TypeSignature` from a :class:`DataObject` subclass.

        Walks the class's inheritance chain (skipping ``object``) and keeps
        only :class:`DataObject` and its subclasses, ordered from most
        general to most specific. If *data_type* is an :class:`Array`
        subclass that requires specific axes, those axis names are captured
        on the result so port checks can enforce them.

        Args:
            data_type: The class to describe. Normally a :class:`DataObject`
                subclass.

        Returns:
            A :class:`TypeSignature` for *data_type*. Plain :class:`Array`
            (which requires no specific axes) yields ``required_axes=None``.

        Example:
            >>> from scistudio.core.types import Array, TypeSignature
            >>> TypeSignature.from_type(Array).type_chain
            ['DataObject', 'Array']
        """
        chain: list[str] = []
        for klass in reversed(data_type.__mro__):
            if klass is object:
                continue
            # Only include DataObject and its subclasses in the chain.
            if klass.__name__ == "DataObject" or (isinstance(klass, type) and issubclass(klass, DataObject)):
                chain.append(klass.__name__)

        slot_schema: dict[str, str] | None = None
        if hasattr(data_type, "expected_slots") and data_type.expected_slots:
            slot_schema = {name: t.__name__ for name, t in data_type.expected_slots.items()}

        # ADR-027 D1: capture required_axes for Array subclasses so port
        # checks can enforce "incoming instance must have at least
        # required_axes of target port type". Only populated when the
        # ClassVar is non-empty; Array itself has an empty frozenset and
        # so maps to None here.
        required_axes: frozenset[str] | None = None
        raw_required = getattr(data_type, "required_axes", None)
        if isinstance(raw_required, frozenset) and len(raw_required) > 0:
            required_axes = raw_required

        return cls(type_chain=chain, slot_schema=slot_schema, required_axes=required_axes)


@stable(since="0.3.1")
class DataObject:
    """Base class for every first-class data object in SciStudio.

    Concrete subclasses represent the kinds of data that blocks exchange:
    :class:`Array`, :class:`Series`, :class:`DataFrame`, :class:`Text`,
    :class:`Artifact`, and :class:`CompositeData`. You normally work with
    those subclasses; this base class defines what they all share —
    metadata, lazy access to stored data, and persistence.

    Every instance carries three metadata slots:

    - :attr:`framework` — managed by SciStudio (identity, lineage). Read it,
      but treat it as read-only.
    - :attr:`meta` — typed, validated metadata for a specific data kind, or
      ``None`` on a plain :class:`DataObject`. A subclass opts in by
      declaring its own model in the :attr:`Meta` class attribute.
    - :attr:`user` — a free-form ``dict`` for your own values. It must be
      JSON-serialisable because it travels between processes.

    Example:
        >>> from scistudio.core.types import Text
        >>> doc = Text(content="hello", user={"sample_id": "S1"})
        >>> doc.user["sample_id"]
        'S1'
    """

    # The worker subprocess reconstruction path reads this class attribute to
    # know which Pydantic model to rebuild when a data object crosses a
    # process boundary.
    Meta: ClassVar[type[BaseModel] | None] = None
    """The typed metadata model this class uses, or ``None`` for none.

    A plain :class:`DataObject` has no typed metadata, so its :attr:`meta`
    slot is ``None``. A subclass that wants validated, domain-specific
    metadata sets this to its own Pydantic model class and passes an
    instance of that model to the constructor.
    """

    @stable(since="0.3.1")
    def __init__(
        self,
        *,
        framework: FrameworkMeta | None = None,
        meta: BaseModel | None = None,
        user: dict[str, Any] | None = None,
        storage_ref: StorageReference | None = None,
    ) -> None:
        """Create a data object and populate its three metadata slots.

        Args:
            framework: Framework-managed metadata. When omitted, a fresh
                :class:`~scistudio.core.meta.FrameworkMeta` is created with a
                new identity and creation timestamp.
            meta: Typed domain metadata, or ``None``. A subclass with a
                :attr:`Meta` model passes an instance of that model here.
            user: Free-form metadata. Copied on input so the caller's dict
                cannot be mutated later. Must be JSON-serialisable.
            storage_ref: Where the object's data is persisted, if it has
                already been written to storage.

        Raises:
            TypeError: if *user* is not JSON-serialisable.
        """
        # ADR-027 D5: framework slot is always populated. ``FrameworkMeta``
        # default factories produce a fresh ``object_id`` and
        # ``created_at`` per instance.
        self._framework: FrameworkMeta = framework if framework is not None else FrameworkMeta()
        # ADR-027 D5: meta slot is None on the base class. Plugin
        # subclasses set their own typed Pydantic model and pass it
        # explicitly via the constructor (or via ``with_meta``).
        self._meta: BaseModel | None = meta
        # ADR-027 D5 + ADR-017: user slot is a JSON-serialisable dict.
        # We copy on input so callers cannot mutate the original dict
        # out from under us.
        self._user: dict[str, Any] = dict(user) if user is not None else {}
        self._validate_user(self._user)
        self._storage_ref: StorageReference | None = storage_ref
        # ADR-031 Addendum 2: declared transient in-memory data slot.
        # Never serialised; used by loaders during the _auto_flush
        # transition and by the typed ``data=`` constructor parameter on
        # concrete subclasses (Array, DataFrame, Series).
        self._transient_data: Any = None

    @staticmethod
    def _validate_user(user: dict[str, Any]) -> None:
        """Validate that the *user* metadata dict is JSON-serialisable.

        ADR-017: cross-process worker transport requires JSON. The
        framework and meta slots are Pydantic models, which handle their
        own serialisation; only the free-form ``user`` dict needs this
        explicit check.
        """
        import json

        try:
            json.dumps(user)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"DataObject user metadata must be JSON-serialisable: {exc}") from exc

    # -- new three-slot properties ------------------------------------------

    @property
    @stable(since="0.3.1")
    def framework(self) -> FrameworkMeta:
        """Framework-managed metadata (identity, lineage, provenance).

        Treat this as read-only: SciStudio sets and updates it for you.

        Returns:
            The :class:`~scistudio.core.meta.FrameworkMeta` for this object.
        """
        return self._framework

    @property
    @stable(since="0.3.1")
    def meta(self) -> BaseModel | None:
        """Typed domain metadata (a Pydantic ``BaseModel``), or ``None``.

        ``None`` for a plain :class:`DataObject` and for any subclass that
        has not declared its own :attr:`Meta` model. A subclass that does
        declare one returns an instance of that model here.

        Returns:
            The typed metadata model, or ``None``.
        """
        return self._meta

    @property
    @stable(since="0.3.1")
    def user(self) -> dict[str, Any]:
        """Free-form user metadata.

        SciStudio never interprets these values; attach whatever you like.
        Must stay JSON-serialisable because it is sent between processes.

        Returns:
            The user metadata dict.
        """
        return self._user

    # -- with_meta immutable update -----------------------------------------

    @stable(since="0.3.1")
    def with_meta(self, **changes: Any) -> Self:
        """Return a copy with some of the typed ``meta`` fields changed.

        Data objects are treated as immutable, so instead of editing
        :attr:`meta` in place you make an updated copy. The copy gets a
        freshly derived :attr:`framework` whose lineage points back to this
        object, the requested ``meta`` field changes, and the same
        :attr:`user` data and storage reference.

        Subclasses that take extra constructor arguments (for example
        :class:`Array`, which needs ``axes``) override this method so those
        extra fields carry over too; the base version only copies the shared
        slots.

        Args:
            **changes: Field name / value pairs to update on the ``meta``
                model.

        Returns:
            A new instance of the same type with the updated metadata.

        Raises:
            ValueError: if this object has no typed ``meta`` (only subclasses
                that declare a :attr:`Meta` model can use this).
        """
        if self._meta is None:
            raise ValueError(
                f"{type(self).__name__}.with_meta() requires a typed `meta` slot. "
                f"This instance has meta=None. Subclass with a class-level `Meta` "
                f"Pydantic model and pass an instance via the constructor to use "
                f"with_meta()."
            )

        # Lazy import to avoid any chance of an import cycle at module
        # load time. ``scistudio.core.meta`` deliberately does not export
        # ``DataObject``; importing the helper here keeps the direction
        # clean.
        from scistudio.core.meta import with_meta_changes

        new_meta = with_meta_changes(self._meta, **changes)
        new_framework = self._framework.derive(derived_from=self._framework.object_id)

        # TODO(T-006): Array overrides this method to also pass
        # ``axes``/``shape``/``dtype``/``chunk_shape``. The base
        # implementation only propagates the four standard slots; if
        # ``type(self).__init__`` requires additional positional or
        # required keyword arguments, this call will raise TypeError
        # at construction. The fix is the per-subclass override, not
        # generic introspection here (per ADR-027 Addendum 1 §2:
        # plugin-specific reconstruction knowledge belongs on the
        # subclass, not in the framework).
        return type(self)(
            framework=new_framework,
            meta=new_meta,
            user=dict(self._user),
            storage_ref=self._storage_ref,
        )

    # -- properties (unchanged from pre-T-005 contract) ---------------------

    @property
    @stable(since="0.3.1")
    def dtype_info(self) -> TypeSignature:
        """The :class:`TypeSignature` describing this object's type.

        Returns:
            A :class:`TypeSignature` derived from this object's class, used
            for port-compatibility checks.
        """
        return TypeSignature.from_type(type(self))

    @property
    @stable(since="0.3.1")
    def storage_ref(self) -> StorageReference | None:
        """Where this object's data is persisted, or ``None``.

        Returns:
            The :class:`StorageReference` if the object has been written to
            storage, otherwise ``None``.
        """
        return self._storage_ref

    @storage_ref.setter
    def storage_ref(self, ref: StorageReference | None) -> None:
        """Set the storage reference."""
        self._storage_ref = ref

    # -- ADR-031 Addendum 2: backward-compat property bridges ----------------
    # These properties let legacy code that writes ``obj._data = arr`` or
    # ``obj._arrow_table = table`` transparently use the declared
    # ``_transient_data`` slot. Internal (excluded from ``__all__`` and the
    # ADR-052 public surface).
    # TODO(#1817): retire the _data/_arrow_table transient-data bridges once
    #   all callers migrate to the data= constructor parameter (ADR-031
    #   Addendum 2). Internal-only; no public-surface impact.

    @property
    def _data(self) -> Any:
        """Backward-compat bridge: reads ``_transient_data``."""
        return self._transient_data

    @_data.setter
    def _data(self, value: Any) -> None:
        """Backward-compat bridge: writes ``_transient_data``."""
        self._transient_data = value

    @_data.deleter
    def _data(self) -> None:
        """Backward-compat bridge: clears ``_transient_data``."""
        self._transient_data = None

    @property
    def _arrow_table(self) -> Any:
        """Backward-compat bridge for DataFrame/Series: reads ``_transient_data``."""
        return self._transient_data

    @_arrow_table.setter
    def _arrow_table(self, value: Any) -> None:
        """Backward-compat bridge for DataFrame/Series: writes ``_transient_data``."""
        self._transient_data = value

    @_arrow_table.deleter
    def _arrow_table(self) -> None:
        """Backward-compat bridge for DataFrame/Series: clears ``_transient_data``."""
        self._transient_data = None

    # -- data access (ADR-031 D1/D2/D6: methods moved from ViewProxy) --------

    @stable(since="0.3.1")
    def to_memory(self) -> Any:
        """Load the full data from storage into memory and return it.

        Reads through this object's :attr:`storage_ref` using the matching
        storage backend. Emits a :class:`ResourceWarning` when the data is
        estimated to exceed 2 GB, since loading it all at once may exhaust
        memory — prefer :meth:`slice` or :meth:`iter_chunks` for large data.

        Returns:
            The data in its in-memory form (for example a NumPy array or a
            ``pyarrow.Table``, depending on the type).

        Raises:
            ValueError: if no storage reference is set.
        """
        if self._storage_ref is None:
            raise ValueError("Cannot load data: no storage reference set.")
        backend = _get_backend(self._storage_ref)
        # Size warning (from former ViewProxy)
        meta = backend.get_metadata(self._storage_ref)
        size = meta.get("size")
        if size is None:
            shape = meta.get("shape")
            if shape is not None:
                import math

                size = math.prod(shape) * 8
        if size is not None and size > _SIZE_WARNING_THRESHOLD:
            warnings.warn(
                f"Loading {size / (1024**3):.1f} GB into memory. Consider using .slice() or .iter_chunks() instead.",
                ResourceWarning,
                stacklevel=2,
            )
        return backend.read(self._storage_ref)

    @stable(since="0.3.1")
    def slice(self, *args: Any) -> Any:
        """Read a sub-selection of the data without loading all of it.

        Passes the index arguments straight to the storage backend so only
        the requested region is read from disk.

        Args:
            *args: Index arguments (integers and ``slice`` objects) the
                backend applies, in axis order.

        Returns:
            The selected sub-region in its in-memory form.

        Raises:
            ValueError: if no storage reference is set.
        """
        if self._storage_ref is None:
            raise ValueError("Cannot slice: no storage reference set.")
        return _get_backend(self._storage_ref).slice(self._storage_ref, *args)

    @stable(since="0.3.1")
    def iter_chunks(self, chunk_size: int) -> Iterator[Any]:
        """Yield the data in successive chunks, keeping memory bounded.

        Useful for streaming through data that is too large to hold in memory
        all at once.

        Args:
            chunk_size: Number of elements (along the leading axis) per chunk.

        Yields:
            Each chunk in its in-memory form, in order.

        Raises:
            ValueError: if no storage reference is set.
        """
        if self._storage_ref is None:
            raise ValueError("Cannot iterate chunks: no storage reference set.")
        yield from _get_backend(self._storage_ref).iter_chunks(self._storage_ref, chunk_size)

    @internal()
    def get_in_memory_data(self) -> Any:
        """Materialise data from storage for persistence/export.

        ADR-031 D6: primary path routes through :meth:`to_memory` ->
        storage backend read. For backward compatibility with the
        ``_auto_flush()`` transition (loaders that still set ``_data``
        or ``_arrow_table`` transiently before the framework persists
        them), falls back to those attributes if ``storage_ref`` is not
        set. Subclasses override for non-storage-backed types (Text
        returns ``self.content``; Artifact returns file bytes).
        """
        if self._storage_ref is not None:
            return self.to_memory()
        # ADR-031 Addendum 2: use the declared _transient_data slot
        # instead of hasattr probing for _data / _arrow_table.
        if self._transient_data is not None:
            return self._transient_data
        raise ValueError(f"{type(self).__name__} has no in-memory data to persist.")

    @provisional(since="0.3.1")
    def save(self, path: str | Path) -> StorageReference:
        """Persist this object's data to *path* and remember where it went.

        Chooses the storage backend that matches this object's type, writes
        the in-memory data, and records the resulting location on
        :attr:`storage_ref`. If the object is already persisted, returns the
        existing reference without rewriting.

        Args:
            path: Destination path for the persisted data.

        Returns:
            A :class:`StorageReference` pointing to the written data.
        """
        if self._storage_ref is not None:
            return self._storage_ref

        from scistudio.core.storage.backend_router import get_router

        path_str = str(path)
        backend_name, backend = get_router().resolve(type(self))
        data = self.get_in_memory_data()
        ref = StorageReference(backend=backend_name, path=path_str)
        result_ref = backend.write(data, ref)
        self._storage_ref = result_ref
        return result_ref

    # -- worker subprocess reconstruction hooks (ADR-027 Addendum 1 §2) -----

    @classmethod
    @provisional(since="0.3.1")
    def reconstruct_extra_kwargs(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        """Return the extra constructor arguments needed to rebuild an object.

        Extension point for subclass authors. When a data object is sent to a
        worker subprocess it is taken apart into plain metadata and later
        rebuilt; this hook supplies any constructor arguments **beyond** the
        four shared slots (``storage_ref``, ``framework``, ``meta``,
        ``user``).

        The plain base class needs no extras and returns an empty dict.
        Concrete subclasses (:class:`Array`, :class:`Series`,
        :class:`DataFrame`, :class:`Text`, :class:`Artifact`) override this to
        read their own fields back out of *metadata*.
        (:class:`CompositeData` is the exception — its slots are nested data
        objects rebuilt by the serializer itself.) This hook and
        :meth:`serialise_extra_metadata` are a matched pair: override both or
        neither, and have each exactly undo the other. When overriding, call
        ``super().reconstruct_extra_kwargs(metadata)`` first and extend the
        result.

        Args:
            metadata: The metadata dict produced by
                :meth:`serialise_extra_metadata`.

        Returns:
            Keyword arguments to splat into ``cls(**kwargs)``.
        """
        return {}

    @classmethod
    @provisional(since="0.3.1")
    def serialise_extra_metadata(cls, obj: DataObject) -> dict[str, Any]:
        """Return the subclass-specific fields to store alongside an object.

        The matching counterpart of :meth:`reconstruct_extra_kwargs` and the
        other half of the subclass extension point. When a data object is
        prepared for transport to a worker subprocess, this hook returns the
        fields that must be saved **beyond** the four shared slots
        (``type_chain``, ``framework``, ``meta``, ``user``).

        The plain base class has no extras and returns an empty dict.
        Concrete subclasses override this to emit their own fields in a
        JSON-friendly form (tuples become lists, a :class:`pathlib.Path`
        becomes a string, a dtype becomes its canonical name). Override this
        and :meth:`reconstruct_extra_kwargs` together or not at all.

        Args:
            obj: The data object being serialised.

        Returns:
            A JSON-serialisable dict merged into the saved metadata.
        """
        return {}
