"""TypeRegistry — discovers and manages DataObject types from plugins and drop-in files.

Per ADR-009, the registry stores :class:`TypeSpec` descriptors (module path,
class name, base type) — never the class object itself.

ADR-027 D11 + Addendum 1 §3 (T-012) added two additional capabilities on top
of the original ADR-009 descriptor-only design:

1. :meth:`TypeRegistry.resolve` is overloaded on argument type:

   - ``resolve(name: str) -> TypeSpec`` — the legacy behaviour. Looks up the
     descriptor registered under *name* and raises :class:`KeyError` when no
     entry matches. Preserved for backward compatibility with existing
     callers (:meth:`load_class`, the architecture tests, and the core type
     tests).
   - ``resolve(type_chain: list[str]) -> type | None`` — the new behaviour
     per ADR-027 D11. Walks *type_chain* from rightmost (most specific) to
     leftmost (most general) and returns the first registered class, or
     ``None`` when no entry in the chain is registered. Used by the worker
     subprocess reconstruction path (T-014) to map a serialised
     ``type_chain`` to a concrete :class:`DataObject` subclass.

2. :meth:`TypeRegistry._validate_meta_class` enforces the ADR-027 Addendum 1
   §3 constraints on any subclass declaring a ``Meta`` ClassVar (frozen
   Pydantic ``BaseModel``, no ``PrivateAttr`` fields, all fields
   JSON-round-trippable). Validation runs at registration time inside
   :meth:`scan_builtins` and :meth:`_scan_entrypoint_types`, so a plugin
   shipping a broken ``Meta`` is rejected at startup with a clear error
   message pointing at the offending class rather than failing silently at
   serialisation time inside a worker subprocess.

T-013 will add per-base-class ``_reconstruct_extra_kwargs`` / ``_serialise_
extra_metadata`` hooks on each of the six core base classes; T-014 will
wire the worker subprocess call site. Both rely on the resolver and the
validation hook added here.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, overload

if TYPE_CHECKING:
    from pydantic import BaseModel  # noqa: F401

logger = logging.getLogger(__name__)


@dataclass
class TypeSpec:
    """Metadata descriptor for a registered DataObject subtype.

    Stores the *location* of the type class (module path + class name)
    rather than holding a reference to the class object.  See ADR-009.
    """

    name: str
    module_path: str = ""
    class_name: str = ""
    base_type: str = ""
    description: str = ""


class TypeRegistry:
    """Registry of known :class:`DataObject` subclasses.

    Provides registration, lookup by name, and enumeration.
    Supports isinstance-style matching via :meth:`is_instance`.

    ADR-027 D11 + Addendum 1 §3 (T-012): also provides
    :meth:`resolve(type_chain)` for worker subprocess reconstruction and
    :meth:`_validate_meta_class` to enforce plugin ``Meta`` constraints at
    registration time.
    """

    def __init__(self) -> None:
        self._registry: dict[str, TypeSpec] = {}
        # Issue #1332 / ARCHITECTURE.md §10 + §10.5: filesystem scan dirs for
        # project-local (``<project>/types``) and user-wide
        # (``~/.scistudio/types``) custom DataObject subclasses. Mirrors
        # :attr:`BlockRegistry._scan_dirs`. Populated via :meth:`add_scan_dir`
        # and consumed by :meth:`scan_all` (after entry-points / monorepo).
        self._scan_dirs: list[Path] = []

    def add_scan_dir(self, directory: str | Path) -> None:
        """Add a directory to the filesystem scan path (issue #1332).

        Mirrors :meth:`BlockRegistry.add_scan_dir`. Each registered
        directory is walked by :meth:`scan_all` after the entry-point and
        monorepo passes; any top-level :class:`DataObject` subclass
        defined in a ``.py`` file under *directory* is registered.

        ``directory`` may be a :class:`pathlib.Path` or a string. The
        path is stored as-is (not eagerly resolved) so a not-yet-created
        ``<project>/types`` or ``~/.scistudio/types`` dir is silently
        skipped at scan time rather than raising at registration time.

        ARCHITECTURE.md §10 (project layout) and §10.5 (user-wide
        extension paths) document the two intended call sites; runtime
        wiring in :class:`scistudio.api.runtime.ApiRuntime` issues these
        calls before invoking :meth:`scan_all`.
        """
        self._scan_dirs.append(Path(directory))

    def register(self, name: str, spec: TypeSpec) -> None:
        """Register *spec* under *name*."""
        self._registry[name] = spec

    def register_class(self, cls: type) -> None:
        """Validate *cls* and register it by its ``__name__``.

        Convenience helper for callers that already have the class object
        (``scan_builtins`` / ``_scan_entrypoint_types`` / plugin tests).
        Runs :meth:`_validate_meta_class` first — the class is only added
        to the registry if validation passes.

        ADR-027 Addendum 1 §3: any subclass declaring a ``Meta`` ClassVar
        must obey the Pydantic constraints documented on
        :meth:`_validate_meta_class`, and validation happens here at
        registration time so broken ``Meta`` classes never enter the
        registry.
        """
        self._validate_meta_class(cls)
        base = cls.__mro__[1].__name__ if len(cls.__mro__) > 2 else ""
        spec = TypeSpec(
            name=cls.__name__,
            module_path=cls.__module__,
            class_name=cls.__name__,
            base_type=base,
            description=cls.__doc__.split("\n")[0] if cls.__doc__ else "",
        )
        self.register(cls.__name__, spec)

    # -- resolve: overloaded on argument type -------------------------------

    @overload
    def resolve(self, name_or_chain: str) -> TypeSpec: ...

    @overload
    def resolve(self, name_or_chain: list[str]) -> type | None: ...

    def resolve(self, name_or_chain: str | list[str]) -> TypeSpec | type | None:
        """Resolve either a single name or a type chain.

        Two call shapes are supported:

        - ``resolve(name: str) -> TypeSpec`` — legacy behaviour. Returns
          the :class:`TypeSpec` registered under *name*, or raises
          :class:`KeyError` when no entry matches. Callers include
          :meth:`load_class`, the architecture enforcement tests, and the
          core type tests written before ADR-027.

        - ``resolve(type_chain: list[str]) -> type | None`` — ADR-027
          D11 behaviour. Walks *type_chain* from rightmost (most
          specific) to leftmost (most general) and returns the first
          registered class. Returns ``None`` when no entry in the chain
          is registered (including when the chain is empty). Used by the
          worker subprocess ``_reconstruct_one`` helper (ADR-027
          Addendum 1 §1) to look up the most specific
          :class:`DataObject` subclass that matches a serialised type
          chain.

        Example:
            >>> registry.resolve(["DataObject", "Array", "Image", "FluorImage"])
            <class 'scistudio_blocks_imaging.types.FluorImage'>  # if installed
            >>> registry.resolve(["DataObject", "Array"])
            <class 'scistudio.core.types.array.Array'>
            >>> registry.resolve(["NonExistent"])
            None
            >>> registry.resolve("Array")  # legacy path
            TypeSpec(name='Array', ...)
        """
        if isinstance(name_or_chain, list):
            # ADR-027 D11: walk rightmost (most specific) -> leftmost
            # (most general) and return the first registered class.
            for type_name in reversed(name_or_chain):
                if type_name in self._registry:
                    return self.load_class(type_name)
            return None

        # Legacy str path: return the TypeSpec or raise KeyError.
        if name_or_chain not in self._registry:
            raise KeyError(f"Type '{name_or_chain}' is not registered.")
        return self._registry[name_or_chain]

    def all_types(self) -> dict[str, TypeSpec]:
        """Return a copy of the full registry mapping."""
        return dict(self._registry)

    def load_class(self, name: str) -> type:
        """Import and return the class for the type registered under *name*."""
        # Call legacy str-resolve path directly to avoid the overload
        # dispatch cost and to return a concrete ``TypeSpec`` for mypy.
        if name not in self._registry:
            raise KeyError(f"Type '{name}' is not registered.")
        spec = self._registry[name]
        module = importlib.import_module(spec.module_path)
        return getattr(module, spec.class_name)  # type: ignore[no-any-return]

    def is_instance(self, obj: Any, type_name: str) -> bool:
        """Check if *obj* is an instance of the type registered under *type_name*.

        Uses isinstance-style matching that respects inheritance.
        """
        cls = self.load_class(type_name)
        return isinstance(obj, cls)

    # -- ADR-027 Addendum 1 §3: Meta-class validation -----------------------

    def _validate_meta_class(self, cls: type) -> None:
        """Validate that ``cls.Meta`` meets ADR-027 Addendum 1 §3 constraints.

        Runs at registration time (via :meth:`register_class` and from
        :meth:`scan_builtins` / :meth:`_scan_entrypoint_types`). Plugin
        subclasses declaring a non-``None`` ``Meta`` ClassVar must obey:

        1. ``Meta`` inherits from :class:`pydantic.BaseModel`.
        2. ``Meta`` has no ``PrivateAttr`` fields (private state cannot
           round-trip through JSON and would silently be lost when the
           worker subprocess serialises the object across
           ``stdin``/``stdout``).
        3. ``Meta`` fields are JSON-round-trippable via
           ``model_dump(mode="json")`` / ``model_validate``. This is
           checked best-effort by constructing a default instance and
           round-tripping it; if ``Meta`` has required fields with no
           defaults we cannot build a default instance, so we skip the
           round-trip check and trust the schema. Plugin authors with
           required-field ``Meta`` classes should write their own
           round-trip regression test in their plugin's test suite.

        ``frozen=True`` on ``model_config`` is *recommended* (and enforced
        by convention by :meth:`DataObject.with_meta`) but not strictly
        required here — that is a soft ADR-027 Addendum 1 §3 suggestion
        rather than a hard constraint.

        Bare ``DataObject`` and any class with ``Meta = None`` (all six
        core base classes ship with ``Meta: ClassVar = None``) short-
        circuit immediately and pass validation.

        Raises:
            ValueError: if ``cls.Meta`` violates any hard constraint. The
                error message always includes the offending class name so
                plugin authors can find the broken file quickly.
        """
        meta = getattr(cls, "Meta", None)
        if meta is None:
            # Bare DataObject and the six core base classes ship with
            # ``Meta = None`` (T-005). No validation needed.
            return

        # Lazy import of pydantic to keep registry import cost low in the
        # worker subprocess cold-start path.
        from pydantic import BaseModel

        # (1) Must be a pydantic.BaseModel subclass.
        if not (isinstance(meta, type) and issubclass(meta, BaseModel)):
            meta_repr = meta.__name__ if isinstance(meta, type) else type(meta).__name__
            raise ValueError(
                f"{cls.__name__}.Meta must be a pydantic.BaseModel subclass; "
                f"got {meta_repr!r}. "
                f"See ADR-027 Addendum 1 §3 (Meta Pydantic constraints)."
            )

        # (2) No PrivateAttr fields — private state cannot JSON-round-trip.
        private_attrs = getattr(meta, "__private_attributes__", {}) or {}
        if private_attrs:
            raise ValueError(
                f"{cls.__name__}.Meta declares PrivateAttr fields "
                f"{list(private_attrs.keys())!r}, which are not allowed. "
                f"ADR-027 Addendum 1 §3 requires Meta to be fully "
                f"JSON-round-trippable through model_dump(mode='json') / "
                f"model_validate — PrivateAttr fields are silently lost "
                f"when the worker subprocess serialises outputs across "
                f"stdin/stdout."
            )

        # (3) Best-effort JSON round-trip on a default instance. If Meta
        # has required fields with no defaults, we cannot construct a
        # default instance — in that case we skip the round-trip check
        # (plugin authors should write their own) and trust the schema.
        try:
            instance = meta()
        except Exception as exc:
            # A ValidationError raised because a required field has no
            # default is expected and fine; any other failure is a bug we
            # want to surface.
            if _looks_like_missing_required_field(exc):
                return
            raise ValueError(
                f"{cls.__name__}.Meta could not be default-constructed for "
                f"JSON round-trip validation: {exc}. "
                f"ADR-027 Addendum 1 §3 requires Meta fields to be "
                f"JSON-round-trippable."
            ) from exc

        try:
            dumped = instance.model_dump(mode="json")
            meta.model_validate(dumped)
        except Exception as exc:
            raise ValueError(
                f"{cls.__name__}.Meta failed JSON round-trip: {exc}. "
                f"ADR-027 Addendum 1 §3 requires all fields to round-trip "
                f"via model_dump(mode='json') / model_validate — see the "
                f"list of acceptable types in the ADR."
            ) from exc

    # -- entry-point / built-in scanning ------------------------------------

    def scan_builtins(self) -> None:
        """Register all built-in DataObject subclasses shipped with SciStudio.

        Per ADR-027 D2, the domain subtypes no longer live in core:

        - T-006 removed the Array family (``Image``, ``FluorImage``,
          ``MSImage``, ``SRSImage``) to ``scistudio-blocks-imaging``.
        - T-007 removed the remaining Series/DataFrame/Composite
          families (``Spectrum``, ``RamanSpectrum``, ``MassSpectrum``,
          ``PeakTable``, ``MetabPeakTable``, ``AnnData``,
          ``SpatialData``) to ``scistudio-blocks-spectral``,
          ``scistudio-blocks-singlecell``, and
          ``scistudio-blocks-spatial-omics`` respectively.

        The registry therefore no longer auto-registers any of them.
        They are re-registered via the ``scistudio.types`` entry-point
        mechanism when the plugin is installed (see
        :meth:`_scan_entrypoint_types`).

        ADR-027 Addendum 1 §3 (T-012): each built-in also passes through
        :meth:`_validate_meta_class` so a future refactor that adds a
        broken ``Meta`` ClassVar to a core type fails loudly here instead
        of silently at worker-subprocess serialisation time. All six core
        base classes ship with ``Meta = None`` today (T-005), so they
        short-circuit without cost.
        """
        from scistudio.core.types.array import Array
        from scistudio.core.types.artifact import Artifact
        from scistudio.core.types.base import DataObject
        from scistudio.core.types.composite import CompositeData
        from scistudio.core.types.dataframe import DataFrame
        from scistudio.core.types.series import Series
        from scistudio.core.types.text import Text

        builtins: list[type] = [
            DataObject,
            Array,
            Series,
            DataFrame,
            Text,
            Artifact,
            CompositeData,
        ]
        for cls in builtins:
            # ADR-027 Addendum 1 §3: reject broken Meta declarations.
            self._validate_meta_class(cls)
            base = cls.__mro__[1].__name__ if len(cls.__mro__) > 2 else ""
            self.register(
                cls.__name__,
                TypeSpec(
                    name=cls.__name__,
                    module_path=cls.__module__,
                    class_name=cls.__name__,
                    base_type=base,
                    description=cls.__doc__.split("\n")[0] if cls.__doc__ else "",
                ),
            )

    def _scan_entrypoint_types(self) -> None:
        """Discover and register DataObject subtypes from ``scistudio.types`` entry-points.

        Each entry-point must be a callable that returns a list of type classes
        (subclasses of :class:`DataObject`).  Invalid entries are logged as
        warnings and skipped — they never crash the registry.

        See ADR-025 Section 4 for the protocol specification and ADR-027
        Addendum 1 §3 for the ``Meta`` constraints enforced here. A plugin
        shipping a broken ``Meta`` is logged as a warning and skipped;
        the rest of its entry-point payload still registers successfully.
        """
        from scistudio.core.types.base import DataObject

        eps = importlib.metadata.entry_points(group="scistudio.types")
        for ep in eps:
            try:
                factory = ep.load()
            except Exception:
                logger.warning(
                    "Failed to load entry-point '%s' from group 'scistudio.types'",
                    ep.name,
                    exc_info=True,
                )
                continue

            try:
                type_classes = factory()
            except Exception:
                logger.warning(
                    "Entry-point '%s' callable raised an exception",
                    ep.name,
                    exc_info=True,
                )
                continue

            if not isinstance(type_classes, (list, tuple)):
                logger.warning(
                    "Entry-point '%s' returned %s instead of a list of type classes; skipping",
                    ep.name,
                    type(type_classes).__name__,
                )
                continue

            for cls in type_classes:
                if not isinstance(cls, type) or not issubclass(cls, DataObject):
                    logger.warning(
                        "Entry-point '%s' returned item %r which is not a DataObject subclass; skipping",
                        ep.name,
                        cls,
                    )
                    continue

                # ADR-027 Addendum 1 §3: Meta validation. Reject broken
                # Meta with a warning (log + skip) instead of raising so
                # one bad plugin does not take down the whole registry.
                try:
                    self._validate_meta_class(cls)
                except ValueError:
                    logger.warning(
                        "Entry-point '%s' type %r has a Meta class that violates ADR-027 Addendum 1 §3; skipping",
                        ep.name,
                        cls,
                        exc_info=True,
                    )
                    continue

                base = cls.__mro__[1].__name__ if len(cls.__mro__) > 2 else ""
                self.register(
                    cls.__name__,
                    TypeSpec(
                        name=cls.__name__,
                        module_path=cls.__module__,
                        class_name=cls.__name__,
                        base_type=base,
                        description=cls.__doc__.split("\n")[0] if cls.__doc__ else "",
                    ),
                )
                logger.info("Registered external type '%s' from entry-point '%s'", cls.__name__, ep.name)

    def scan_all(self, *, include_monorepo: bool = False) -> None:
        """Register built-in types and then scan entry-points for external types.

        Issue #1332 / ARCHITECTURE.md §10 + §10.5: after the entry-point and
        monorepo passes, this also walks every directory registered via
        :meth:`add_scan_dir` and registers any drop-in :class:`DataObject`
        subclass found in a ``.py`` file there. Entry-point and monorepo
        registrations win on duplicates (this matches
        :meth:`BlockRegistry.scan`'s ordering).
        """
        self.scan_builtins()
        self._scan_entrypoint_types()
        if include_monorepo:
            self._scan_monorepo_types()
        self._scan_filesystem_dirs()

    def _scan_filesystem_dirs(self) -> None:
        """Walk each registered scan directory and register drop-in types.

        Issue #1332 / ARCHITECTURE.md §10 + §10.5. Mirrors
        :meth:`BlockRegistry._scan_tier1` for the type-registration path.

        For each registered directory (see :meth:`add_scan_dir`):

        - Silently skip if the directory does not exist (the
          ``<project>/types`` dir is created on project init but a
          freshly-cloned project or a user without ``~/.scistudio/types``
          must not crash registry startup).
        - Import every ``.py`` file via
          :func:`importlib.util.spec_from_file_location`. Files whose
          names start with ``_`` are skipped (private / dunder modules).
        - Any top-level :class:`DataObject` subclass that is defined in
          the loaded module (not merely re-exported from another module)
          is registered under its ``__name__`` via
          :meth:`register_class`. Names already in the registry (from
          built-ins, entry-points, or monorepo passes) are left alone —
          plugin and built-in registrations win on duplicates.
        - Import failures and Meta-validation failures are logged as
          warnings; the offending file is skipped and scanning
          continues. A single broken drop-in must never kill the
          registry.
        """
        if not self._scan_dirs:
            return

        from scistudio.core.types.base import DataObject

        for scan_dir in self._scan_dirs:
            if not scan_dir.is_dir():
                logger.debug("TypeRegistry: scan dir %s does not exist; skipping", scan_dir)
                continue
            for py_file in scan_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                try:
                    mtime = py_file.stat().st_mtime
                    mod_name = f"_scistudio_type_dropin_{py_file.stem}_{int(mtime)}"
                    spec = importlib.util.spec_from_file_location(mod_name, py_file)
                    if spec is None or spec.loader is None:
                        continue
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                except Exception:
                    logger.warning(
                        "TypeRegistry: failed to import type drop-in from %s",
                        py_file,
                        exc_info=True,
                    )
                    continue

                for attr_name in dir(module):
                    obj = getattr(module, attr_name, None)
                    if not (
                        isinstance(obj, type)
                        and issubclass(obj, DataObject)
                        and obj is not DataObject
                        # Skip re-exports — only register classes actually
                        # defined in this drop-in file. Matches the #706
                        # guard in :meth:`BlockRegistry._scan_tier1`.
                        and getattr(obj, "__module__", None) == module.__name__
                    ):
                        continue
                    if obj.__name__ in self._registry:
                        # Built-ins / entry-points / monorepo plugins win
                        # on duplicates; the drop-in path is the last
                        # tier and must not silently shadow them.
                        continue
                    try:
                        self.register_class(obj)
                        logger.info(
                            "TypeRegistry: registered drop-in type %r from %s",
                            obj.__name__,
                            py_file,
                        )
                    except Exception:
                        logger.warning(
                            "TypeRegistry: failed to register drop-in type %r from %s",
                            obj.__name__,
                            py_file,
                            exc_info=True,
                        )

    def _scan_monorepo_types(self) -> None:
        """Development fallback for plugin type discovery in the monorepo.

        Mirrors the plugin skeleton smoke tests: when plugin packages live in
        ``packages/*/src`` but have not been installed in editable mode yet,
        import them directly from source and register any types returned by a
        conventional ``get_types()`` callable.
        """
        repo_root = Path(__file__).resolve().parents[4]
        packages_dir = repo_root / "packages"
        if not packages_dir.is_dir():
            return

        for pkg_dir in packages_dir.glob("scistudio-blocks-*"):
            src_dir = pkg_dir / "src"
            if not src_dir.is_dir():
                continue

            src_dir_str = str(src_dir)
            if src_dir_str not in sys.path:
                sys.path.insert(0, src_dir_str)

            module_name = pkg_dir.name.replace("-", "_")
            try:
                module = importlib.import_module(module_name)
            except Exception:
                logger.warning("Failed to import monorepo plugin types from '%s'", module_name, exc_info=True)
                continue

            get_types = getattr(module, "get_types", None)
            if not callable(get_types):
                continue

            try:
                type_classes = get_types()
            except Exception:
                logger.warning("Monorepo plugin '%s' get_types() raised", module_name, exc_info=True)
                continue

            if not isinstance(type_classes, (list, tuple)):
                continue

            for cls in type_classes:
                try:
                    self.register_class(cls)
                except Exception:
                    logger.warning(
                        "Failed to register monorepo plugin type %r from '%s'",
                        cls,
                        module_name,
                        exc_info=True,
                    )


def _looks_like_missing_required_field(exc: BaseException) -> bool:
    """Return True if *exc* looks like a Pydantic "required field missing" error.

    Pydantic v2 raises ``ValidationError`` with one or more ``missing``
    errors when you default-construct a model whose required fields have
    no defaults. We treat that specific case as "cannot round-trip a
    default instance — skip this check" rather than an actual validation
    failure of the Meta class.

    We deliberately pattern-match on the error string instead of
    importing ``pydantic.ValidationError`` at module level, because the
    registry is imported by the worker subprocess cold-start path and we
    want to keep the pydantic import lazy (happens inside
    :meth:`_validate_meta_class`).
    """
    text = str(exc).lower()
    return "field required" in text or "missing" in text
