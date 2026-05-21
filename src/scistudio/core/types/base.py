"""DataObject ABC, TypeSignature, and metadata containers.

Implements the stratified three-slot metadata model from ADR-027 D5:

- ``framework``: :class:`scistudio.core.meta.FrameworkMeta` — framework-managed,
  immutable from block authors' perspective. Carries identity, lineage,
  and provenance hints.
- ``meta``: a typed Pydantic ``BaseModel`` (or ``None`` on the base class).
  Plugin subclasses declare their own ``Meta`` model via the class-level
  :attr:`DataObject.Meta` ClassVar; T-013 will use this hook for the
  worker subprocess reconstruction path.
- ``user``: a free-form ``dict[str, Any]`` escape hatch the framework
  does not interpret. Must be JSON-serialisable per ADR-017.

The legacy single-dict ``metadata`` API is preserved as a deprecation
shim for one phase: ``DataObject(metadata=...)`` and the
``DataObject.metadata`` property both still work and emit
``DeprecationWarning``. Both are removed in Phase 11.
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


@dataclass
class TypeSignature:
    """Describes the semantic type of a DataObject via a chain of type names.

    Attributes:
        type_chain: Ordered list of type names from most general to most specific,
            e.g. ``["DataObject", "Array", "FluorImage"]``.
        slot_schema: Optional mapping of slot names to type names (for composites).
        required_axes: Optional frozenset of axis names that Array subclasses
            require at the instance level. ``None`` for non-Array types or
            for Array itself (which has an empty ``required_axes`` ClassVar).
            Populated by :meth:`from_type` from the class's
            ``required_axes`` ClassVar when it is non-empty. Added per
            ADR-027 D1 so that port ``port_accepts_signature`` checks can
            enforce "incoming instance must have at least required_axes of
            target port type".
    """

    type_chain: list[str]
    slot_schema: dict[str, str] | None = field(default=None)
    required_axes: frozenset[str] | None = field(default=None)

    def matches(self, other: TypeSignature) -> bool:
        """Return ``True`` if *other* is compatible with this signature.

        Compatibility means that *other*'s type chain is a prefix of or equal
        to this signature's type chain (i.e. this type is a subtype of other).
        For composite types, slot schemas must also be compatible.
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
    def from_type(cls, data_type: type) -> TypeSignature:
        """Build a :class:`TypeSignature` from a Python class's MRO.

        This walks the MRO up to (but not including) ``object`` and records
        the class names, filtered to only include ``DataObject`` and its
        subclasses.

        If ``data_type`` is an ``Array`` subclass with a non-empty
        ``required_axes`` ClassVar, the frozenset is captured on the
        resulting signature (ADR-027 D1). ``Array`` itself has an empty
        ``required_axes`` and therefore produces ``required_axes=None``.
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


class DataObject:
    """Base class for all first-class data objects in SciStudio.

    Subclasses represent concrete scientific data kinds (arrays, series,
    dataframes, text, artifacts, composites).

    ADR-027 D5 (stratified metadata): every DataObject has three metadata
    slots populated at construction time:

    - :attr:`framework` — :class:`FrameworkMeta`, framework-managed and
      immutable from block authors' perspective.
    - :attr:`meta` — a typed Pydantic ``BaseModel`` (or ``None`` on the
      base class). Plugin subclasses declare their own ``Meta`` model
      class via the :attr:`Meta` ClassVar.
    - :attr:`user` — a free-form ``dict[str, Any]`` escape hatch. Must
      be JSON-serialisable per ADR-017 (cross-process worker transport).

    Backward-compat shim: ``DataObject(metadata=...)`` and the
    ``DataObject.metadata`` property both still work and emit
    :class:`DeprecationWarning`. Both are removed in Phase 11.
    """

    # ADR-027 D5: subclasses override this with their own typed Pydantic
    # model. The base class has no Meta (None), so bare ``DataObject()``
    # instances have ``meta=None``. T-013 will use this ClassVar in
    # ``_reconstruct_extra_kwargs`` to know which Pydantic model to
    # instantiate when round-tripping a DataObject through the worker
    # subprocess.
    Meta: ClassVar[type[BaseModel] | None] = None

    def __init__(
        self,
        *,
        framework: FrameworkMeta | None = None,
        meta: BaseModel | None = None,
        user: dict[str, Any] | None = None,
        storage_ref: StorageReference | None = None,
        # Legacy kwarg, deprecated in Phase 10, removed in Phase 11.
        metadata: dict[str, Any] | None = None,
    ) -> None:
        # Backward-compat shim: if the legacy ``metadata=`` kwarg is
        # passed, treat it as the new ``user`` slot. Refuse to accept
        # both forms simultaneously to avoid silent ambiguity.
        if metadata is not None:
            if user is not None:
                raise ValueError(
                    "Cannot pass both `metadata` (deprecated) and `user`. "
                    "Use `user` only — `metadata` is removed in Phase 11."
                )
            warnings.warn(
                "DataObject(metadata=...) is deprecated since Phase 10; "
                "use the typed three-slot model: framework=, meta=, user=. "
                "The deprecation shim is removed in Phase 11.",
                DeprecationWarning,
                stacklevel=2,
            )
            user = metadata

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
    def framework(self) -> FrameworkMeta:
        """Framework-managed metadata. Immutable from block authors' perspective.

        See ADR-027 D5 and :class:`scistudio.core.meta.FrameworkMeta`.
        """
        return self._framework

    @property
    def meta(self) -> BaseModel | None:
        """Typed domain metadata (Pydantic ``BaseModel``).

        ``None`` for plain :class:`DataObject` instances and any subclass
        that has not declared its own :attr:`DataObject.Meta` ClassVar.
        Plugin subclasses (e.g. ``FluorImage`` in
        ``scistudio-blocks-imaging``) override the ``Meta`` ClassVar and
        pass an instance of that model via the constructor.
        """
        return self._meta

    @property
    def user(self) -> dict[str, Any]:
        """Free-form user metadata dict.

        The framework does not interpret these values. Must be
        JSON-serialisable per ADR-017.
        """
        return self._user

    # -- backward-compat metadata property ----------------------------------

    @property
    def metadata(self) -> dict[str, Any]:
        """DEPRECATED: returns :attr:`user` for backward compatibility.

        Removed in Phase 11. Use :attr:`user` for free-form metadata or
        :attr:`meta` for typed domain metadata.
        """
        warnings.warn(
            "DataObject.metadata is deprecated since Phase 10; use `obj.user` "
            "for free-form metadata or `obj.meta` (a typed Pydantic model) "
            "for domain metadata. Removed in Phase 11.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._user

    # -- with_meta immutable update -----------------------------------------

    def with_meta(self, **changes: Any) -> Self:
        """Return a new instance with the ``meta`` slot's fields updated.

        Implements the immutable-update half of ADR-027 D5. The new
        instance has:

        - a freshly-derived :class:`FrameworkMeta` whose ``derived_from``
          is set to this instance's ``object_id`` (so lineage is
          traceable across the immutable copy);
        - a new ``meta`` produced by ``with_meta_changes(self.meta, **changes)``;
        - the same ``user`` dict (shallow-copied) and ``storage_ref``.

        Other slots that subclasses may carry (e.g. ``axes`` / ``shape`` /
        ``dtype`` on :class:`Array`, ``slots`` on
        :class:`CompositeData`) are NOT propagated by this base
        implementation because the base ``__init__`` does not know about
        them. **Subclasses with extra ``__init__`` parameters must
        override ``with_meta()`` to pass those through.** T-006 will
        provide the ``Array`` override; T-007 will audit the other base
        classes.

        Raises:
            ValueError: if ``self.meta is None`` (no typed Meta to
                update). The base ``DataObject`` class has no Meta;
                only plugin subclasses that override the :attr:`Meta`
                ClassVar can use ``with_meta``.
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
    def dtype_info(self) -> TypeSignature:
        """Return the :class:`TypeSignature` describing this object's type."""
        return TypeSignature.from_type(type(self))

    @property
    def storage_ref(self) -> StorageReference | None:
        """Return the :class:`StorageReference` if the object is persisted."""
        return self._storage_ref

    @storage_ref.setter
    def storage_ref(self, ref: StorageReference | None) -> None:
        """Set the storage reference."""
        self._storage_ref = ref

    # -- ADR-031 Addendum 2: backward-compat property bridges ----------------
    # These properties let legacy code that writes ``obj._data = arr`` or
    # ``obj._arrow_table = table`` transparently use the declared
    # ``_transient_data`` slot. They will be removed once all callers are
    # migrated to the ``data=`` constructor parameter.

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

    def to_memory(self) -> Any:
        """Materialise the full data from storage into memory.

        ADR-031 D1: routes through ``storage_ref`` -> backend. Emits a
        :class:`ResourceWarning` when the estimated size exceeds 2 GB.

        Raises:
            ValueError: if ``storage_ref`` is not set.
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

    def slice(self, *args: Any) -> Any:
        """Return a sub-selection of the data without full materialisation.

        ADR-031 D2: moved from ViewProxy. Delegates to the backend's
        ``slice()`` method.

        Raises:
            ValueError: if ``storage_ref`` is not set.
        """
        if self._storage_ref is None:
            raise ValueError("Cannot slice: no storage reference set.")
        return _get_backend(self._storage_ref).slice(self._storage_ref, *args)

    def iter_chunks(self, chunk_size: int) -> Iterator[Any]:
        """Yield successive chunks of the data from storage.

        ADR-031 D2: moved from ViewProxy. Delegates to the backend's
        ``iter_chunks()`` method.

        Raises:
            ValueError: if ``storage_ref`` is not set.
        """
        if self._storage_ref is None:
            raise ValueError("Cannot iterate chunks: no storage reference set.")
        yield from _get_backend(self._storage_ref).iter_chunks(self._storage_ref, chunk_size)

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

    def save(self, path: str | Path) -> StorageReference:
        """Persist the data object to *path* using the appropriate backend.

        Returns the :class:`StorageReference` pointing to the persisted data.
        Also sets ``self._storage_ref`` so subsequent calls are no-ops.
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
    def _reconstruct_extra_kwargs(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        """Return base-class-specific kwargs for worker reconstruction.

        Called by :func:`scistudio.core.types.serialization._reconstruct_one`
        (full implementation in T-014) to extract the keyword arguments
        that ``cls.__init__`` needs **beyond** the four standard
        :class:`DataObject` slots (``storage_ref``, ``framework``,
        ``meta``, ``user``).

        Base-class default: no extra kwargs. Plain ``DataObject``
        instances round-trip through the four standard slots alone.

        Each concrete base class (``Array``, ``Series``, ``DataFrame``,
        ``Text``, ``Artifact``, ``CompositeData``) overrides this hook
        to extract its constructor-required fields from the wire-format
        metadata sidecar. Plugin subclasses inherit their base class's
        hook and almost never need to override; the rare override pattern
        is to call ``super()._reconstruct_extra_kwargs(metadata)`` and
        extend the returned dict with additional fields. See ADR-027
        Addendum 1 §2 ("D11' companion") for the full contract.

        Args:
            metadata: The ``metadata`` dict from the wire-format payload
                item (produced by :meth:`_serialise_extra_metadata`).

        Returns:
            A dict of kwargs to splat into ``cls(**kwargs)``.
        """
        return {}

    @classmethod
    def _serialise_extra_metadata(cls, obj: DataObject) -> dict[str, Any]:
        """Return base-class-specific fields for the metadata sidecar.

        Symmetric counterpart of :meth:`_reconstruct_extra_kwargs`.
        Called by :func:`scistudio.core.types.serialization._serialise_one`
        (full implementation in T-014) to compute the fields that need
        to live in the wire-format metadata sidecar **beyond** the four
        standard slots that :func:`_serialise_one` always writes
        (``type_chain``, ``framework``, ``meta``, ``user``).

        Base-class default: no extras. Plain ``DataObject`` instances
        serialise through the four standard slots alone.

        Each concrete base class overrides this hook to emit its
        constructor-specific fields in a JSON-serialisable form
        (e.g. tuples become lists, :class:`pathlib.Path` becomes
        :class:`str`). See ADR-027 Addendum 1 §2 for the full contract.

        Args:
            obj: The :class:`DataObject` instance to serialise.

        Returns:
            A JSON-serialisable dict that will be merged into the
            wire-format metadata sidecar by :func:`_serialise_one`.
        """
        return {}
