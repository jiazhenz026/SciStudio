"""Serialization helpers for typed DataObject reconstruction.

Implements ADR-027 Addendum 1 §1 (Decision D11': worker subprocess
returns typed ``DataObject`` instances, not ``ViewProxy``).

This module owns :func:`_reconstruct_one` and :func:`_serialise_one` —
the helpers that round-trip a single :class:`~scistudio.core.types.base.DataObject`
through the JSON wire format used by the engine↔worker subprocess
boundary. :class:`~scistudio.core.types.composite.CompositeData`'s
``_reconstruct_extra_kwargs`` / ``_serialise_extra_metadata`` hook pair
(T-013) imports these helpers via lazy in-method imports to recursively
reconstruct/serialise nested slots.

The functions delegate to each base class's
``_reconstruct_extra_kwargs`` / ``_serialise_extra_metadata`` classmethod
hooks (T-013) via polymorphic class lookup. They never know about the
specific ``Array`` / ``Series`` / ``DataFrame`` / ``Text`` / ``Artifact``
/ ``CompositeData`` surface — the per-class knowledge lives on the base
classes themselves.

Per Open Question 1 of the Phase 10 implementation standards doc, this
module lives in :mod:`scistudio.core.types.serialization` rather than in
:mod:`scistudio.engine.runners.worker` so the import direction is always
``core ← engine``, never the reverse. That keeps the importlinter
contract ``core must not depend on blocks/engine/api/ai/workflow``
clean.

T-013 shipped this module as a stub whose bodies raised
:class:`NotImplementedError` with a pointer at T-014. T-014 replaces
those bodies with the full implementations described in ADR-027
Addendum 1 §1. The signatures (single payload-item dict in, single
typed ``DataObject`` out; and the reverse) are locked from T-013 onward.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scistudio.core.types.base import DataObject
    from scistudio.core.types.registry import TypeRegistry


# Module-level lazy singleton used by :func:`_reconstruct_one` to look up
# the concrete :class:`DataObject` subclass that matches a serialised
# ``type_chain``. T-012's :class:`TypeRegistry` is instance-based, not
# class-based; T-014 needs a single shared instance per worker subprocess
# so the scan cost is paid once at cold start, not per reconstruction.
# Populated lazily by :func:`_get_type_registry` on first call.
_registry_instance: TypeRegistry | None = None


def _get_type_registry() -> TypeRegistry:
    """Return the shared :class:`TypeRegistry` singleton for this process.

    The first call constructs a fresh :class:`TypeRegistry`, runs
    :meth:`TypeRegistry.scan_builtins` to register the six core base
    classes, and attempts :meth:`TypeRegistry._scan_entrypoint_types` to
    pick up plugin-provided types. Subsequent calls return the same
    instance.

    Entry-point scanning is wrapped in a best-effort try/except: a
    broken plugin must not prevent reconstruction of core instances.
    Any plugin scan error is swallowed here (the registry's own
    per-entry-point exception handling already logs a warning); the
    core built-ins remain available either way.

    The worker subprocess calls this helper once at :func:`main`
    startup (via :func:`scistudio.engine.runners.worker.main`) to warm up
    the singleton before the first :func:`_reconstruct_one` call, so
    the scan is paid upfront rather than hidden inside the first
    reconstruction. This mirrors the "scan once at startup" model
    described in ADR-027 D11.

    Tests can reset the singleton by setting the module-level
    ``_registry_instance`` to ``None``; the next call will re-scan.
    """
    import contextlib

    from scistudio.core.types.registry import TypeRegistry

    global _registry_instance
    if _registry_instance is None:
        registry = TypeRegistry()
        registry.scan_builtins()
        # Plugin scan errors are logged by the registry itself; never
        # fail reconstruction because of a broken plugin entry-point.
        with contextlib.suppress(Exception):
            registry._scan_entrypoint_types()
        _registry_instance = registry
    return _registry_instance


def _reconstruct_one(payload_item: dict[str, Any]) -> DataObject:
    """Reconstruct one typed ``DataObject`` from a wire-format payload item.

    Implements ADR-027 Addendum 1 §1 (D11' pseudocode). The payload
    item shape is the JSON dict that :func:`_serialise_one` writes::

        {
            "backend":  "zarr" | "arrow" | "filesystem" | None,
            "path":     "/path/to/store" | None,
            "format":   "..." | None,
            "metadata": {
                "type_chain":  ["DataObject", "Array", "Image", "FluorImage"],
                "framework":   { ...FrameworkMeta JSON... },
                "meta":        { ...subtype Meta JSON, or None... },
                "user":        { ...free dict... },
                # base-class extras (axes/shape/dtype/chunk_shape, slots, ...)
            },
        }

    Reconstruction steps:

    1. Build a :class:`StorageReference` from the top-level
       ``backend``/``path``/``format``/``metadata`` when both
       ``backend`` and ``path`` are set; otherwise ``storage_ref=None``
       (supports in-memory objects that bypass flush).
    2. Look up the most specific registered class via
       :meth:`TypeRegistry.resolve`. Unknown chains fall back to the
       bare :class:`DataObject`.
    3. Validate the ``framework`` slot via
       :meth:`FrameworkMeta.model_validate`.
    4. Validate the ``meta`` slot via ``cls.Meta.model_validate`` when
       ``cls.Meta`` is declared; ``None`` on classes that do not
       declare a Meta ClassVar.
    5. Copy the ``user`` slot (shallow dict).
    6. Call ``cls._reconstruct_extra_kwargs(md)`` to pick up the
       base-class-specific constructor kwargs (e.g. ``axes``/``shape``
       for :class:`Array`, ``slots`` for :class:`CompositeData`).
    7. Construct ``cls(**all_kwargs)`` and return.

    The returned instance has ``storage_ref`` set (when the payload
    provided one) but does **not** read its backing data until
    :meth:`to_memory` / :meth:`view` / :meth:`sel` / :meth:`iter_over`
    is called. Lazy loading is preserved at the method level per
    ADR-027 D4.

    Args:
        payload_item: The wire-format JSON dict produced by
            :func:`_serialise_one`.

    Returns:
        A typed :class:`DataObject` instance.

    Raises:
        ValueError: if ``payload_item`` is not a dict or if
            ``cls(**kwargs)`` fails (the original exception is chained
            via ``raise ... from exc`` with a message pointing at the
            offending class).
    """
    from scistudio.core.meta import FrameworkMeta
    from scistudio.core.storage.ref import StorageReference
    from scistudio.core.types.base import DataObject

    if not isinstance(payload_item, dict):
        raise ValueError(f"_reconstruct_one expects a dict payload_item, got {type(payload_item).__name__}")

    backend = payload_item.get("backend")
    path = payload_item.get("path")
    format_ = payload_item.get("format")
    md = payload_item.get("metadata") or {}
    if not isinstance(md, dict):
        md = {}

    # Step 1: storage_ref (only when both backend and path are provided).
    storage_ref: StorageReference | None
    if backend is not None and path is not None:
        storage_ref = StorageReference(
            backend=backend,
            path=path,
            format=format_,
            metadata=md,
        )
    else:
        storage_ref = None

    # Step 2: resolve the most specific registered class via TypeRegistry.
    type_chain_raw = md.get("type_chain", ["DataObject"])
    if not isinstance(type_chain_raw, list):
        type_chain_raw = ["DataObject"]
    type_chain: list[str] = [str(name) for name in type_chain_raw]

    registry = _get_type_registry()
    resolved = registry.resolve(type_chain)
    cls: type[DataObject] = resolved if resolved is not None else DataObject

    # Step 3: framework slot — Pydantic round-trip via model_validate.
    framework_data = md.get("framework") or {}
    if not isinstance(framework_data, dict):
        framework_data = {}
    framework = FrameworkMeta.model_validate(framework_data)

    # Step 4: meta slot — validate only when cls declares a Meta ClassVar.
    meta_obj: Any = None
    meta_cls = getattr(cls, "Meta", None)
    if meta_cls is not None:
        meta_data = md.get("meta")
        if meta_data is None:
            meta_data = {}
        meta_obj = meta_cls.model_validate(meta_data)

    # Step 5: user slot — copied dict (caller cannot share state with us).
    user_raw = md.get("user") or {}
    if not isinstance(user_raw, dict):
        user_raw = {}
    user = dict(user_raw)

    # Step 6: base-class-specific extras via the T-013 classmethod hook.
    extra_kwargs: dict[str, Any] = {}
    if hasattr(cls, "_reconstruct_extra_kwargs"):
        extra_kwargs = cls._reconstruct_extra_kwargs(md)

    # Step 7: construct. Wrap the call in a try/except so any failure
    # (e.g. Array axes validation, missing required kwarg on a plugin
    # subclass) surfaces with the class name attached.
    try:
        return cls(
            storage_ref=storage_ref,
            framework=framework,
            meta=meta_obj,
            user=user,
            **extra_kwargs,
        )
    except Exception as exc:
        raise ValueError(f"Failed to reconstruct {cls.__name__} from payload: {exc}") from exc


def _serialise_one(obj: DataObject) -> dict[str, Any]:
    """Serialise one typed ``DataObject`` to a wire-format payload item.

    Symmetric counterpart of :func:`_reconstruct_one`. Writes the
    metadata sidecar with ``type_chain``, ``framework``, ``meta``,
    ``user``, and base-class-specific extras, then wraps it in the
    top-level ``backend``/``path``/``format``/``metadata`` envelope
    that the engine's wire format expects.

    Per ADR-027 Addendum 1 §"Out of scope", the top-level wire-format
    keys are unchanged from the pre-Addendum format; only the contents
    of the ``metadata`` sidecar become richer.

    Auto-flush behaviour from ADR-020-Add5 is preserved **outside** this
    function: the worker's :func:`serialise_outputs` calls
    :meth:`Block._auto_flush` before handing the object to
    :func:`_serialise_one`. If the flush succeeded, ``obj.storage_ref``
    is set and the wire-format payload carries the concrete backend /
    path / format. If no flush context was configured, ``obj.storage_ref``
    may still be ``None``; we tolerate that by emitting ``backend=None``
    / ``path=None`` rather than raising, so downstream code can round-
    trip in-memory metadata-only objects through the wire format.

    Args:
        obj: The typed :class:`DataObject` to serialise.

    Returns:
        A JSON-serialisable dict that :func:`_reconstruct_one` can
        round-trip back into a typed instance.

    Raises:
        ValueError: if ``obj`` is not a :class:`DataObject`.
    """
    from scistudio.core.types.base import DataObject

    if not isinstance(obj, DataObject):
        raise ValueError(f"_serialise_one expects a DataObject, got {type(obj).__name__}")

    # Build metadata sidecar.
    md: dict[str, Any] = {}

    # type_chain — consumed by TypeRegistry.resolve in the receiving worker.
    md["type_chain"] = list(obj.dtype_info.type_chain)

    # framework slot — Pydantic round-trip via JSON mode.
    md["framework"] = obj.framework.model_dump(mode="json")

    # meta slot — Pydantic round-trip via JSON mode when present.
    if obj.meta is not None:
        md["meta"] = obj.meta.model_dump(mode="json")
    else:
        md["meta"] = None

    # user slot — already JSON-serialisable per ADR-017.
    md["user"] = dict(obj.user or {})

    # Base-class extras: delegate to the T-013 classmethod hook on the
    # concrete class. type(obj) is used (not cls) so that plugin
    # subclasses that override _serialise_extra_metadata are called
    # polymorphically.
    cls = type(obj)
    if hasattr(cls, "_serialise_extra_metadata"):
        md.update(cls._serialise_extra_metadata(obj))

    # Storage reference envelope. ADR-031 Addendum 1: reject None
    # storage_ref unless this is an Artifact with file_path (path-only transport).
    ref = obj.storage_ref
    if ref is None:
        from scistudio.core.types.artifact import Artifact

        if not (isinstance(obj, Artifact) and getattr(obj, "file_path", None) is not None):
            raise ValueError(
                f"Cannot serialise {type(obj).__name__}: storage_ref is None. "
                f"Object must be persisted to storage before serialisation."
            )
        # Artifact with file_path: emit None backend/path (path-only transport)
        backend, path, format_ = None, None, None
    else:
        backend = ref.backend
        path = ref.path
        format_ = ref.format

    return {
        "backend": backend,
        "path": path,
        "format": format_,
        "metadata": md,
    }
