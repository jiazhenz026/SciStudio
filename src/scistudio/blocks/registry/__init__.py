"""BlockRegistry — discovers blocks from drop-in files and entry_points.

Per ADR-009, the registry stores :class:`BlockSpec` descriptors (module path,
class name, metadata, file mtime) — never the class object itself.  This
ensures hot-reload safety: a reload updates specs without affecting running
workflow instances.

Per ADR-047, the registry is a sub-package (``Path D`` pattern) split into:

- ``__init__.py`` — :class:`BlockRegistry`, :class:`BlockSpec`, and the
  five capability error classes.
- ``_scan.py`` — Tier 1 / Tier 2 / monorepo scan loops + ``_register_spec``.
- ``_capability.py`` — ADR-043 capability lookup helpers
  (``find_loader_capability`` / ``find_saver_capability`` /
  ``list_format_capabilities`` + matching primitives).
- ``_spec.py`` — :func:`_spec_from_class` + ADR-030 ``_merge_config_schema`` +
  ADR-038 distribution-version resolution.

The pre-ADR-043 "legacy IO finder" methods
(``find_loader`` / ``find_saver`` / ``find_io_blocks_for_type``) were
removed in this refactor — all production callers reach the capability
methods first; the legacy fallback paths are dead code.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scistudio.blocks.io.capabilities import CapabilityDirection, FormatCapability
from scistudio.core.types.base import DataObject

if TYPE_CHECKING:
    from scistudio.blocks.base.package_info import PackageInfo


class BlockRegistrationError(Exception):
    """Raised when a Block class cannot be registered.

    ADR-038 §3.3 (D38-3.2): the registry must "fail loudly" when the
    distribution version for a Block class cannot be resolved — the
    reproducibility guarantee requires a real version on every row.

    The Tier 1 / Tier 2 / monorepo scan loops catch this exception and
    log the failure per-block, so a single mis-packaged plugin does not
    kill the whole palette (less-destructive degradation while still
    removing the historical ``"unknown"`` default).
    """


class CapabilityRegistrationError(BlockRegistrationError):
    """Raised when an IO format capability cannot be indexed."""


class CapabilityLookupError(LookupError):
    """Base class for IO format capability lookup failures."""

    def __init__(
        self,
        message: str,
        *,
        direction: CapabilityDirection,
        data_type: type[DataObject],
        extension: str | None = None,
        format_id: str | None = None,
        capability_id: str | None = None,
        candidates: tuple[FormatCapability, ...] = (),
    ) -> None:
        super().__init__(message)
        self.direction = direction
        self.data_type = data_type
        self.extension = extension
        self.format_id = format_id
        self.capability_id = capability_id
        self.candidates = candidates


class MissingCapabilityError(CapabilityLookupError):
    """Raised when no IO format capability matches a query."""


class AmbiguousCapabilityError(CapabilityLookupError):
    """Raised when a capability query has no deterministic winner."""


@dataclass
class BlockSpec:
    """Metadata descriptor for a registered block type.

    Stores the *location* of the block class (module path + class name)
    rather than holding a reference to the class object.  See ADR-009.
    """

    name: str
    description: str = ""
    version: str = "0.1.0"
    module_path: str = ""
    class_name: str = ""
    file_path: str | None = None
    file_mtime: float | None = None
    base_category: str = ""
    subcategory: str = ""
    input_ports: list[Any] = field(default_factory=list)
    output_ports: list[Any] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    type_name: str = ""
    package_name: str = ""
    # ADR-028 Addendum 1 D3: IO direction for IO blocks ("input" | "output").
    # Empty string means "not an IO block / no direction".
    direction: str = ""
    # ADR-028 Addendum 1 D3: enum-driven dynamic-port descriptor copied from
    # the class-level ``Block.dynamic_ports`` ClassVar. Validated at scan
    # time by :meth:`BlockRegistry._validate_dynamic_ports`.
    dynamic_ports: dict[str, Any] | None = None
    # ADR-029 D8: variadic port flags — copied from Block ClassVars at scan time.
    variadic_inputs: bool = False
    variadic_outputs: bool = False
    # ADR-029 D11: allowed type names for variadic port editor dropdown.
    # Empty list means "any DataObject subclass".
    allowed_input_types: list[str] = field(default_factory=list)
    allowed_output_types: list[str] = field(default_factory=list)
    # ADR-029 Addendum 1: optional min/max constraints on variadic port count.
    min_input_ports: int | None = None
    max_input_ports: int | None = None
    min_output_ports: int | None = None
    max_output_ports: int | None = None
    # ADR-028 §D8 / #1077: cached copy of the class-level ``supported_extensions``
    # ClassVar so the registry can dispatch by extension without re-importing
    # the block class.
    supported_extensions: dict[str, str] = field(default_factory=dict)
    # ADR-043: normalized IO format capability records captured at scan time.
    format_capabilities: list[FormatCapability] = field(default_factory=list)
    # Desktop package blocks may need import roots that are intentionally not
    # exposed to the core process globally. The runner passes these to the
    # worker payload for block-local imports.
    runtime_import_roots: list[str] = field(default_factory=list)


class BlockRegistry:
    """Central catalogue of available block types.

    The registry is populated via :meth:`scan` (entry-points / drop-in
    directories) and queried by the runtime when constructing workflows.

    Tier 1: Drop-in ``.py`` files from configured scan directories.
    Tier 2: ``pyproject.toml`` entry-points under ``"scistudio.blocks"``.
    """

    def __init__(self) -> None:
        self._registry: dict[str, BlockSpec] = {}
        self._aliases: dict[str, str] = {}
        self._scan_dirs: list[Path] = []
        self._package_src_dirs: list[Path] = []
        self._packages: dict[str, PackageInfo] = {}

    def add_scan_dir(self, directory: str | Path) -> None:
        """Add a directory to the Tier 1 scan path."""
        self._scan_dirs.append(Path(directory))

    def add_package_src_dir(self, directory: str | Path) -> None:
        """Add a hard-installed source-package directory to the Tier 3 scan path.

        ``directory`` may be a ``packages`` directory containing ``*/src``
        package sources, a single package root with a ``src`` child, or an
        already-resolved ``src`` directory.
        """
        self._package_src_dirs.append(Path(directory))

    def scan(self) -> None:
        """Discover block classes from entry-points and drop-in directories."""
        self._scan_builtins()
        self._scan_tier1()
        self._scan_tier2()
        self._scan_package_src_dirs()

    def _scan_builtins(self) -> None:
        from scistudio.blocks.registry._scan import _scan_builtins

        _scan_builtins(self)

    def _scan_tier1(self) -> None:
        from scistudio.blocks.registry._scan import _scan_tier1

        _scan_tier1(self)

    def _scan_tier2(self) -> None:
        from scistudio.blocks.registry._scan import _scan_tier2

        _scan_tier2(self)

    def _scan_package_src_dirs(self) -> None:
        """Tier 3: scan hard-installed source package directories."""
        from scistudio.blocks.registry._scan import _scan_package_src_dirs

        _scan_package_src_dirs(self)

    def _register_spec(self, spec: BlockSpec) -> None:
        """Register a spec under its display name and public type name."""
        from scistudio.blocks.registry._scan import _register_spec

        _register_spec(self, spec)

    def _validate_capability_registration(self, spec: BlockSpec) -> None:
        """Validate new capability rows against the already-indexed registry."""
        from scistudio.blocks.registry._scan import _validate_capability_registration

        _validate_capability_registration(self, spec)

    @staticmethod
    def _validate_dynamic_ports(cls: type) -> None:
        """Validate the shape of ``cls.dynamic_ports`` per ADR-028 Addendum 1."""
        from scistudio.blocks.registry._capability import _validate_dynamic_ports

        _validate_dynamic_ports(cls)

    def get_spec(self, identifier: str) -> BlockSpec | None:
        """Resolve a block spec by display name or public type name."""
        if identifier in self._registry:
            return self._registry[identifier]
        alias = self._aliases.get(identifier)
        if alias is None:
            return None
        return self._registry.get(alias)

    def instantiate(self, name: str, config: dict[str, Any] | None = None) -> Any:
        """Create a block instance by registered *name*.

        Performs a fresh import using the stored module path and class name,
        with mtime-based module name for hot-reload safety.
        """
        spec = self.get_spec(name)
        if spec is None:
            raise KeyError(f"Block '{name}' is not registered.")

        from scistudio.desktop.paths import prepended_sys_paths

        runtime_import_roots = [Path(root) for root in spec.runtime_import_roots]
        with prepended_sys_paths(runtime_import_roots):
            # For Tier 1 (file-based), re-import with mtime.
            if spec.file_path:
                path = Path(spec.file_path)
                mtime = path.stat().st_mtime
                mod_name = f"_scistudio_dropin_{path.stem}_{int(mtime)}"
                mod_spec = importlib.util.spec_from_file_location(mod_name, path)
                if mod_spec is None or mod_spec.loader is None:
                    raise ImportError(f"Cannot load block from {spec.file_path}")
                module = importlib.util.module_from_spec(mod_spec)
                mod_spec.loader.exec_module(module)
            else:
                # For Tier 2, standard import.
                module = importlib.import_module(spec.module_path)

        cls = getattr(module, spec.class_name)
        # #706: this is a *fresh* class object (re-imported from the file) so
        # the stamp set during _scan_tier1 is on the prior class object. Re-
        # stamp here so LocalRunner can read _scistudio_file_path from the class
        # of the instance it is about to dispatch.
        if spec.file_path:
            with contextlib.suppress(AttributeError, TypeError):
                cls._scistudio_file_path = spec.file_path
        if spec.runtime_import_roots:
            with contextlib.suppress(AttributeError, TypeError):
                cls._scistudio_runtime_import_roots = tuple(spec.runtime_import_roots)
        return cls(config=config)

    def hot_reload(self) -> None:
        """Re-scan Tier 1 dirs and update specs that have changed.

        Compares file mtimes to detect changes.  New files are added,
        modified files are re-scanned, deleted files are removed.
        """
        from scistudio.blocks.registry._scan import _scan_tier1

        # Remove stale Tier 1 entries.
        stale = [
            name
            for name, spec in self._registry.items()
            if spec.source == "tier1" and spec.file_path and not Path(spec.file_path).exists()
        ]
        for name in stale:
            del self._registry[name]

        # Re-scan Tier 1 only.
        _scan_tier1(self)

    def packages(self) -> dict[str, PackageInfo]:
        """Return registered package metadata keyed by package name.

        Only packages that provided a :class:`PackageInfo` via the
        ``(PackageInfo, list)`` return convention are included.
        """
        return dict(self._packages)

    def specs_by_package(self) -> dict[str, list[BlockSpec]]:
        """Return block specs grouped by ``package_name``.

        Blocks without a ``package_name`` (builtins, Tier 1) are grouped
        under the empty string key ``""``.
        """
        grouped: dict[str, list[BlockSpec]] = {}
        for spec in self._registry.values():
            grouped.setdefault(spec.package_name, []).append(spec)
        return grouped

    def all_specs(self) -> dict[str, BlockSpec]:
        """Return a copy of the full registry mapping."""
        return dict(self._registry)

    # ------------------------------------------------------------------
    # ADR-043: IO format capability lookup.
    # ------------------------------------------------------------------

    def list_format_capabilities(
        self,
        *,
        direction: CapabilityDirection | None = None,
        data_type: type[DataObject] | None = None,
        extension: str | None = None,
        format_id: str | None = None,
    ) -> list[FormatCapability]:
        """List registered ADR-043 IO format capabilities matching filters."""
        from scistudio.blocks.registry._capability import list_format_capabilities

        return list_format_capabilities(
            self,
            direction=direction,
            data_type=data_type,
            extension=extension,
            format_id=format_id,
        )

    def find_loader_capability(
        self,
        data_type: type[DataObject],
        extension: str | None = None,
        *,
        format_id: str | None = None,
        capability_id: str | None = None,
    ) -> FormatCapability:
        """Resolve a load capability without falling back to registration order."""
        from scistudio.blocks.registry._capability import find_loader_capability

        return find_loader_capability(
            self,
            data_type,
            extension,
            format_id=format_id,
            capability_id=capability_id,
        )

    def find_saver_capability(
        self,
        data_type: type[DataObject],
        extension: str | None = None,
        *,
        format_id: str | None = None,
        capability_id: str | None = None,
    ) -> FormatCapability:
        """Resolve a save capability without falling back to registration order."""
        from scistudio.blocks.registry._capability import find_saver_capability

        return find_saver_capability(
            self,
            data_type,
            extension,
            format_id=format_id,
            capability_id=capability_id,
        )

    @staticmethod
    def _resolve_class(spec: BlockSpec) -> type | None:
        """Load the class referenced by *spec*. Returns ``None`` on import failure."""
        from scistudio.blocks.registry._capability import _resolve_class

        return _resolve_class(spec)

    def _resolve_capability_class(self, capability: FormatCapability) -> type | None:
        """Return the block class that owns *capability* (mtime-aware re-import)."""
        from scistudio.blocks.registry._capability import _resolve_capability_class

        return _resolve_capability_class(self, capability)


# ---------------------------------------------------------------------------
# Re-exports for backward-compatible module-level access.
#
# Many tests and one production caller (``workflow/validator.py``) import
# ``_spec_from_class``, ``_merge_config_schema``, ``_infer_category``,
# ``_resolve_distribution_version`` directly from
# ``scistudio.blocks.registry``. The Path D split moves those helpers into
# the ``_spec.py`` sibling; re-export them here so the public import
# surface is preserved exactly.
# ---------------------------------------------------------------------------

from scistudio.blocks.registry._capability import (  # noqa: E402
    _iter_compound_to_single_suffix,
    _validate_capability_id,
)
from scistudio.blocks.registry._spec import (  # noqa: E402
    _format_capabilities_from_class,
    _infer_category,
    _merge_config_schema,
    _packages_distributions_cached,
    _resolve_distribution_version,
    _spec_from_class,
    _subclass_declares_field,
    _type_name_for_class,
    _validate_class_capability,
    _validate_simple_extension_declaration,
)

__all__ = [
    "AmbiguousCapabilityError",
    "BlockRegistrationError",
    "BlockRegistry",
    "BlockSpec",
    "CapabilityLookupError",
    "CapabilityRegistrationError",
    "MissingCapabilityError",
    "_format_capabilities_from_class",
    "_infer_category",
    "_iter_compound_to_single_suffix",
    "_merge_config_schema",
    "_packages_distributions_cached",
    "_resolve_distribution_version",
    "_spec_from_class",
    "_subclass_declares_field",
    "_type_name_for_class",
    "_validate_capability_id",
    "_validate_class_capability",
    "_validate_simple_extension_declaration",
]
