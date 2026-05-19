"""BlockRegistry — discovers blocks from drop-in files and entry_points.

Per ADR-009, the registry stores :class:`BlockSpec` descriptors (module path,
class name, metadata, file mtime) — never the class object itself.  This
ensures hot-reload safety: a reload updates specs without affecting running
workflow instances.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.metadata
import importlib.util
import inspect
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scieasy.blocks.io.capabilities import CapabilityDirection, FormatCapability, normalize_extension
from scieasy.core.types.base import DataObject, TypeSignature

if TYPE_CHECKING:
    from scieasy.blocks.base.package_info import PackageInfo

logger = logging.getLogger(__name__)


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
    """Raised when an ADR-043 format capability cannot be indexed."""


class CapabilityLookupError(LookupError):
    """Base class for ADR-043 format capability lookup failures."""

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
    # ClassVar so :meth:`BlockRegistry.find_loader` / :meth:`find_saver` /
    # :meth:`find_io_blocks_for_type` can dispatch by extension without
    # re-importing the block class.
    supported_extensions: dict[str, str] = field(default_factory=dict)
    # ADR-043: normalized IO format capability records captured at scan time.
    format_capabilities: list[FormatCapability] = field(default_factory=list)


class BlockRegistry:
    """Central catalogue of available block types.

    The registry is populated via :meth:`scan` (entry-points / drop-in
    directories) and queried by the runtime when constructing workflows.

    Tier 1: Drop-in ``.py`` files from configured scan directories.
    Tier 2: ``pyproject.toml`` entry-points under ``"scieasy.blocks"``.
    """

    def __init__(self) -> None:
        self._registry: dict[str, BlockSpec] = {}
        self._aliases: dict[str, str] = {}
        self._scan_dirs: list[Path] = []
        self._packages: dict[str, PackageInfo] = {}

    def add_scan_dir(self, directory: str | Path) -> None:
        """Add a directory to the Tier 1 scan path."""
        self._scan_dirs.append(Path(directory))

    def scan(self, *, include_monorepo: bool = False) -> None:
        """Discover block classes from entry-points and drop-in directories."""
        self._scan_builtins()
        self._scan_tier1()
        self._scan_tier2()
        if include_monorepo:
            self._scan_monorepo_packages()

    def _register_spec(self, spec: BlockSpec) -> None:
        """Register a spec under its display name and public type name."""
        self._validate_capability_registration(spec)
        self._registry[spec.name] = spec
        if spec.type_name:
            self._aliases[spec.type_name] = spec.name

    def _validate_capability_registration(self, spec: BlockSpec) -> None:
        """Validate new capability rows against the already-indexed registry."""
        seen_ids: set[str] = set()
        for capability in spec.format_capabilities:
            if capability.id in seen_ids:
                raise CapabilityRegistrationError(
                    f"{spec.class_name} declares duplicate capability id {capability.id!r}."
                )
            seen_ids.add(capability.id)
            _validate_capability_id(capability)

            for existing_capability, existing_spec in self._iter_capability_specs():
                if existing_spec.name == spec.name:
                    continue
                if existing_capability.id == capability.id:
                    raise CapabilityRegistrationError(
                        "Duplicate capability id "
                        f"{capability.id!r} on {spec.class_name}; already declared by {existing_spec.class_name}."
                    )

        default_index: dict[tuple[str, type[DataObject], str], tuple[FormatCapability, BlockSpec]] = {}
        prospective_specs = [
            existing_spec for existing_spec in self._registry.values() if existing_spec.name != spec.name
        ]
        prospective_specs.append(spec)
        for candidate_spec in prospective_specs:
            for capability in candidate_spec.format_capabilities:
                if not capability.is_default:
                    continue
                for extension in capability.extensions:
                    key = (capability.direction, capability.data_type, extension)
                    previous = default_index.get(key)
                    if previous is not None:
                        previous_capability, previous_spec = previous
                        raise CapabilityRegistrationError(
                            "Conflicting default IO format capabilities for "
                            f"({capability.direction}, {capability.data_type.__name__}, {extension}): "
                            f"{previous_capability.id!r} on {previous_spec.class_name} and "
                            f"{capability.id!r} on {candidate_spec.class_name}."
                        )
                    default_index[key] = (capability, candidate_spec)

    @staticmethod
    def _validate_dynamic_ports(cls: type) -> None:
        """Validate the shape of ``cls.dynamic_ports`` per ADR-028 Addendum 1.

        Called at scan time so malformed declarations fail loudly at import.
        Accepts ``None`` (the default) and any dict that matches::

            {
                "source_config_key": str,
                # Exactly one of the following two keys must be present.
                # ``output_port_mapping`` is used by input-direction blocks
                # (LoadData) and ``input_port_mapping`` by output-direction
                # blocks (SaveData). The shape of the value is identical.
                "output_port_mapping": {
                    "<port_name>": {
                        "<enum_value>": ["<TypeName>", ...],
                        ...
                    },
                    ...
                },
                # OR
                "input_port_mapping": {
                    "<port_name>": {
                        "<enum_value>": ["<TypeName>", ...],
                        ...
                    },
                    ...
                },
            }

        Raises ``ValueError`` with the offending class name and field path
        when the shape is wrong.

        T-TRK-008 (SaveData) note: the ``input_port_mapping`` variant was
        added in this ticket per ADR-028 Addendum 1 §C5/§C9. T-TRK-006
        (PR #321) only declared the ``output_port_mapping`` variant
        because LoadData (T-TRK-007) was the first consumer; SaveData is
        the symmetric output-direction consumer and uses the
        ``input_port_mapping`` key. The frontend
        ``computeEffectivePorts`` helper in T-TRK-009 must handle both
        keys.
        """
        descriptor = getattr(cls, "dynamic_ports", None)
        if descriptor is None:
            return

        cls_name = cls.__name__
        if not isinstance(descriptor, dict):
            raise ValueError(f"{cls_name}.dynamic_ports must be a dict or None, got {type(descriptor).__name__}")

        if "source_config_key" not in descriptor:
            raise ValueError(f"{cls_name}.dynamic_ports is missing required key 'source_config_key'")
        source_key = descriptor["source_config_key"]
        if not isinstance(source_key, str) or not source_key:
            raise ValueError(
                f"{cls_name}.dynamic_ports['source_config_key'] must be a non-empty string, "
                f"got {type(source_key).__name__}"
            )

        # Exactly one of ``output_port_mapping`` or ``input_port_mapping``
        # must be present. Per ADR-028 Addendum 1 §C5: input-direction
        # blocks (LoadData) drive output ports from a config enum, and
        # output-direction blocks (SaveData) drive input ports from a
        # config enum. Both use the same nested-dict shape.
        has_output = "output_port_mapping" in descriptor
        has_input = "input_port_mapping" in descriptor
        if not has_output and not has_input:
            raise ValueError(
                f"{cls_name}.dynamic_ports is missing required key 'output_port_mapping' or 'input_port_mapping'"
            )
        if has_output and has_input:
            raise ValueError(
                f"{cls_name}.dynamic_ports must declare exactly one of "
                "'output_port_mapping' or 'input_port_mapping', not both"
            )
        mapping_key = "output_port_mapping" if has_output else "input_port_mapping"
        mapping = descriptor[mapping_key]
        if not isinstance(mapping, dict):
            raise ValueError(f"{cls_name}.dynamic_ports[{mapping_key!r}] must be a dict, got {type(mapping).__name__}")

        for port_name, enum_map in mapping.items():
            if not isinstance(port_name, str) or not port_name:
                raise ValueError(
                    f"{cls_name}.dynamic_ports[{mapping_key!r}] keys must be non-empty strings, got {port_name!r}"
                )
            if not isinstance(enum_map, dict):
                raise ValueError(
                    f"{cls_name}.dynamic_ports[{mapping_key!r}][{port_name!r}] must be a dict, "
                    f"got {type(enum_map).__name__}"
                )
            for enum_value, type_names in enum_map.items():
                if not isinstance(enum_value, str) or not enum_value:
                    raise ValueError(
                        f"{cls_name}.dynamic_ports[{mapping_key!r}][{port_name!r}] keys must be "
                        f"non-empty strings, got {enum_value!r}"
                    )
                if not isinstance(type_names, list):
                    raise ValueError(
                        f"{cls_name}.dynamic_ports[{mapping_key!r}][{port_name!r}][{enum_value!r}] "
                        f"must be a list, got {type(type_names).__name__}"
                    )
                for type_name in type_names:
                    if not isinstance(type_name, str) or not type_name:
                        raise ValueError(
                            f"{cls_name}.dynamic_ports[{mapping_key!r}][{port_name!r}][{enum_value!r}] "
                            f"entries must be non-empty strings, got {type_name!r}"
                        )

    def _scan_builtins(self) -> None:
        """Register built-in core blocks used by the API/frontend.

        Only concrete, user-facing blocks are registered here.  Base
        classes (AppBlock, CodeBlock, IOBlock) and non-functional process
        placeholders (Merge, Split, …) are excluded from the palette so
        end users see only the blocks they can actually use.  The
        excluded classes remain importable for plugin development and
        tests.
        """
        from scieasy.blocks.ai.ai_block import AIBlock
        from scieasy.blocks.io.loaders.load_data import LoadData
        from scieasy.blocks.io.savers.save_data import SaveData
        from scieasy.blocks.subworkflow.subworkflow_block import SubWorkflowBlock

        for cls in (
            LoadData,
            SaveData,
            AIBlock,
            SubWorkflowBlock,
        ):
            self._register_spec(_spec_from_class(cls, source="builtin"))

    def _scan_tier1(self) -> None:
        """Tier 1: scan configured directories for ``.py`` files containing Block subclasses."""
        from scieasy.blocks.base.block import Block

        for scan_dir in self._scan_dirs:
            if not scan_dir.is_dir():
                continue
            for py_file in scan_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                try:
                    mtime = py_file.stat().st_mtime
                    mod_name = f"_scieasy_dropin_{py_file.stem}_{int(mtime)}"
                    spec = importlib.util.spec_from_file_location(mod_name, py_file)
                    if spec is None or spec.loader is None:
                        continue
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    for attr_name in dir(module):
                        obj = getattr(module, attr_name)
                        if (
                            isinstance(obj, type)
                            and issubclass(obj, Block)
                            and obj is not Block
                            and not inspect.isabstract(obj)
                            # #706 audit: ``dir(module)`` also surfaces Block
                            # subclasses *imported* from other modules (e.g.
                            # ``from scieasy.blocks.code import CodeBlock``).
                            # Stamping or re-registering those would make the
                            # worker try to spec_from_file_location the wrong
                            # source. Restrict the loop body to classes that
                            # are actually defined in this drop-in file.
                            and getattr(obj, "__module__", None) == module.__name__
                        ):
                            # #706: stamp the source-file path on the class so the
                            # worker subprocess can reload the synthetic module via
                            # importlib.util.spec_from_file_location (the synthetic
                            # mod_name only exists in the parent's sys.modules).
                            # Only Tier-1 drop-in classes get this attribute;
                            # Tier-2 entry-point blocks remain importable via the
                            # normal importlib.import_module path.
                            # Defensive: if the class disallows attribute
                            # assignment (e.g. __slots__ without the slot),
                            # fall through; the worker will then fail loudly
                            # with the original ModuleNotFoundError rather
                            # than silently mis-dispatching.
                            with contextlib.suppress(AttributeError, TypeError):
                                obj._scieasy_file_path = str(py_file)  # type: ignore[attr-defined]
                            block_spec = _spec_from_class(obj, source="tier1")
                            block_spec.file_path = str(py_file)
                            block_spec.file_mtime = mtime
                            block_spec.module_path = mod_name
                            self._register_spec(block_spec)
                except Exception:
                    logger.warning(
                        "Failed to import block from %s",
                        py_file,
                        exc_info=True,
                    )
                    continue

    def _scan_tier2(self) -> None:
        """Tier 2: scan ``scieasy.blocks`` entry-points using callable protocol.

        Each entry-point resolves to a callable.  When invoked, it returns
        either:

        * ``(PackageInfo, list[type[Block]])`` -- package metadata + block list
        * ``list[type[Block]]`` -- plain list (backward compatible, uses
          entry-point name as the package display name)

        See ADR-025 for the full specification.
        """
        from scieasy.blocks.base.block import Block
        from scieasy.blocks.base.package_info import PackageInfo

        try:
            eps = importlib.metadata.entry_points()
        except Exception:
            logger.warning("Failed to load entry_points for block discovery", exc_info=True)
            return

        eps_any: Any = eps
        block_eps: Any = (
            eps_any.select(group="scieasy.blocks") if hasattr(eps_any, "select") else eps_any.get("scieasy.blocks", [])
        )

        for ep in block_eps:
            try:
                loaded = ep.load()
            except Exception:
                logger.warning(
                    "Failed to load entry_point '%s'",
                    ep.name,
                    exc_info=True,
                )
                continue

            try:
                # Entry-points may point at a concrete block class directly.
                # Classes are callable, so detect them before invoking.
                if isinstance(loaded, type) and issubclass(loaded, Block):
                    result = loaded
                else:
                    result = loaded() if callable(loaded) else loaded

                info: PackageInfo | None = None
                block_classes: list[type] = []

                if isinstance(result, tuple) and len(result) == 2:
                    first, second = result
                    if isinstance(first, PackageInfo) and isinstance(second, list):
                        info = first
                        block_classes = second
                    else:
                        logger.warning(
                            "Entry-point '%s' returned unexpected tuple format",
                            ep.name,
                        )
                        continue
                elif isinstance(result, list):
                    block_classes = result
                else:
                    # Legacy path: entry-point points directly to a class.
                    if isinstance(result, type) and issubclass(result, Block):
                        block_classes = [result]
                    else:
                        logger.warning(
                            "Entry-point '%s' returned unsupported type: %s",
                            ep.name,
                            type(result).__name__,
                        )
                        continue

                pkg_name = info.name if info is not None else ep.name
                if info is not None:
                    self._packages[info.name] = info

                for cls in block_classes:
                    if isinstance(cls, type) and issubclass(cls, Block) and not inspect.isabstract(cls):
                        block_spec = _spec_from_class(cls, source="entry_point")
                        block_spec.module_path = cls.__module__
                        block_spec.class_name = cls.__name__
                        block_spec.package_name = pkg_name
                        self._register_spec(block_spec)
                    elif isinstance(cls, type) and issubclass(cls, Block) and inspect.isabstract(cls):
                        logger.warning(
                            "Entry-point '%s' contained abstract Block subclass: %s",
                            ep.name,
                            cls,
                        )
                    else:
                        logger.warning(
                            "Entry-point '%s' contained non-Block item: %s",
                            ep.name,
                            cls,
                        )
            except Exception:
                logger.warning(
                    "Failed to process entry_point '%s'",
                    ep.name,
                    exc_info=True,
                )
                continue

    def _scan_monorepo_packages(self) -> None:
        """Development fallback for plugin packages living in the monorepo.

        The desktop/app development workflow often runs the core package from
        source without separately installing Phase 11 plugin packages in
        editable mode. In that case there are no ``scieasy.blocks`` entry
        points for the plugins yet, but the plugin sources are still present
        under ``packages/*/src`` in the same repository checkout.

        This fallback mirrors the entry-point callable protocol for any
        ``scieasy_blocks_*`` package found in the monorepo:

        - prefer ``get_block_package() -> (PackageInfo, list[type[Block]])``
        - fall back to ``get_blocks() -> list[type[Block]]``

        Installed entry-points remain authoritative because this scan runs
        after :meth:`_scan_tier2` and skips any block type that is already
        registered.
        """
        from scieasy.blocks.base.block import Block
        from scieasy.blocks.base.package_info import PackageInfo

        repo_root = Path(__file__).resolve().parents[3]
        packages_dir = repo_root / "packages"
        if not packages_dir.is_dir():
            return

        for pkg_dir in packages_dir.glob("scieasy-blocks-*"):
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
                logger.warning("Failed to import monorepo plugin package '%s'", module_name, exc_info=True)
                continue

            result: Any | None = None
            if hasattr(module, "get_block_package") and callable(module.get_block_package):
                result = module.get_block_package()
            elif hasattr(module, "get_blocks") and callable(module.get_blocks):
                result = module.get_blocks()
            else:
                continue

            info: PackageInfo | None = None
            block_classes: list[type] = []
            if isinstance(result, tuple) and len(result) == 2:
                first, second = result
                if isinstance(first, PackageInfo) and isinstance(second, list):
                    info = first
                    block_classes = second
            elif isinstance(result, list):
                block_classes = result

            if not block_classes:
                continue

            pkg_name = info.name if info is not None else module_name
            if info is not None:
                self._packages[info.name] = info

            for cls in block_classes:
                if not (isinstance(cls, type) and issubclass(cls, Block) and not inspect.isabstract(cls)):
                    continue
                block_spec = _spec_from_class(cls, source="monorepo")
                block_spec.module_path = cls.__module__
                block_spec.class_name = cls.__name__
                block_spec.package_name = pkg_name
                if block_spec.type_name in self._aliases or block_spec.name in self._registry:
                    continue
                self._register_spec(block_spec)

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

        # For Tier 1 (file-based), re-import with mtime.
        if spec.file_path:
            path = Path(spec.file_path)
            mtime = path.stat().st_mtime
            mod_name = f"_scieasy_dropin_{path.stem}_{int(mtime)}"
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
        # stamp here so LocalRunner can read _scieasy_file_path from the class
        # of the instance it is about to dispatch.
        if spec.file_path:
            with contextlib.suppress(AttributeError, TypeError):
                cls._scieasy_file_path = spec.file_path
        return cls(config=config)

    def hot_reload(self) -> None:
        """Re-scan Tier 1 dirs and update specs that have changed.

        Compares file mtimes to detect changes.  New files are added,
        modified files are re-scanned, deleted files are removed.
        """
        # Remove stale Tier 1 entries.
        stale = [
            name
            for name, spec in self._registry.items()
            if spec.source == "tier1" and spec.file_path and not Path(spec.file_path).exists()
        ]
        for name in stale:
            del self._registry[name]

        # Re-scan Tier 1 only.
        self._scan_tier1()

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
        normalized_extension = normalize_extension(extension) if extension else None
        normalized_format_id = format_id.strip().lower() if format_id else None

        capabilities: list[FormatCapability] = []
        for capability, _spec in self._iter_capability_specs():
            if direction is not None and capability.direction != direction:
                continue
            if normalized_extension is not None and normalized_extension not in capability.extensions:
                continue
            if normalized_format_id is not None and capability.format_id != normalized_format_id:
                continue
            if data_type is not None and not _capability_matches_type(
                capability,
                data_type,
                capability.direction,
            ):
                continue
            capabilities.append(capability)
        return capabilities

    def find_loader_capability(
        self,
        data_type: type[DataObject],
        extension: str | None = None,
        *,
        format_id: str | None = None,
        capability_id: str | None = None,
    ) -> FormatCapability:
        """Resolve a load capability without falling back to registration order."""
        return self._find_format_capability(
            direction="load",
            data_type=data_type,
            extension=extension,
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
        return self._find_format_capability(
            direction="save",
            data_type=data_type,
            extension=extension,
            format_id=format_id,
            capability_id=capability_id,
        )

    def _find_format_capability(
        self,
        *,
        direction: CapabilityDirection,
        data_type: type[DataObject],
        extension: str | None,
        format_id: str | None,
        capability_id: str | None,
    ) -> FormatCapability:
        normalized_extension = normalize_extension(extension) if extension else None
        normalized_format_id = format_id.strip().lower() if format_id else None

        if capability_id is not None:
            for capability, _spec in self._iter_capability_specs():
                if capability.id != capability_id:
                    continue
                if self._capability_satisfies_query(
                    capability,
                    direction=direction,
                    data_type=data_type,
                    extension=normalized_extension,
                    format_id=normalized_format_id,
                ):
                    return capability
                raise MissingCapabilityError(
                    _capability_error_message(
                        "Capability id exists but does not satisfy the requested IO contract",
                        direction=direction,
                        data_type=data_type,
                        extension=normalized_extension,
                        format_id=normalized_format_id,
                        capability_id=capability_id,
                        candidates=(capability,),
                    ),
                    direction=direction,
                    data_type=data_type,
                    extension=normalized_extension,
                    format_id=normalized_format_id,
                    capability_id=capability_id,
                    candidates=(capability,),
                )
            raise MissingCapabilityError(
                _capability_error_message(
                    "No IO format capability matches capability_id",
                    direction=direction,
                    data_type=data_type,
                    extension=normalized_extension,
                    format_id=normalized_format_id,
                    capability_id=capability_id,
                ),
                direction=direction,
                data_type=data_type,
                extension=normalized_extension,
                format_id=normalized_format_id,
                capability_id=capability_id,
            )

        candidates = tuple(
            capability
            for capability in self.list_format_capabilities(
                direction=direction,
                data_type=data_type,
                extension=normalized_extension,
                format_id=normalized_format_id,
            )
        )
        if not candidates:
            raise MissingCapabilityError(
                _capability_error_message(
                    "No IO format capability matches the requested contract",
                    direction=direction,
                    data_type=data_type,
                    extension=normalized_extension,
                    format_id=normalized_format_id,
                ),
                direction=direction,
                data_type=data_type,
                extension=normalized_extension,
                format_id=normalized_format_id,
            )
        if len(candidates) == 1:
            return candidates[0]

        default_candidates = tuple(candidate for candidate in candidates if candidate.is_default)
        if len(default_candidates) == 1:
            return default_candidates[0]
        ranked_candidates = default_candidates or candidates

        max_specificity = max(_capability_type_specificity(candidate) for candidate in ranked_candidates)
        most_specific = tuple(
            candidate for candidate in ranked_candidates if _capability_type_specificity(candidate) == max_specificity
        )
        if len(most_specific) == 1:
            return most_specific[0]

        max_priority = max(candidate.priority for candidate in most_specific)
        highest_priority = tuple(candidate for candidate in most_specific if candidate.priority == max_priority)
        if len(highest_priority) == 1:
            return highest_priority[0]

        raise AmbiguousCapabilityError(
            _capability_error_message(
                "Ambiguous IO format capability lookup",
                direction=direction,
                data_type=data_type,
                extension=normalized_extension,
                format_id=normalized_format_id,
                candidates=highest_priority,
            ),
            direction=direction,
            data_type=data_type,
            extension=normalized_extension,
            format_id=normalized_format_id,
            candidates=highest_priority,
        )

    def _capability_satisfies_query(
        self,
        capability: FormatCapability,
        *,
        direction: CapabilityDirection,
        data_type: type[DataObject],
        extension: str | None,
        format_id: str | None,
    ) -> bool:
        if capability.direction != direction:
            return False
        if extension is not None and extension not in capability.extensions:
            return False
        if format_id is not None and capability.format_id != format_id:
            return False
        return _capability_matches_type(capability, data_type, direction)

    def _iter_capability_specs(self) -> list[tuple[FormatCapability, BlockSpec]]:
        """Return capability/spec pairs in registry insertion order."""
        return [(capability, spec) for spec in self._registry.values() for capability in spec.format_capabilities]

    def _resolve_capability_class(self, capability: FormatCapability) -> type | None:
        for candidate, spec in self._iter_capability_specs():
            if candidate.id == capability.id:
                return self._resolve_class(spec)
        return None

    def _resolve_first_capability_class(self, capabilities: tuple[FormatCapability, ...]) -> type | None:
        candidate_ids = {capability.id for capability in capabilities}
        for capability, spec in self._iter_capability_specs():
            if capability.id not in candidate_ids:
                continue
            cls = self._resolve_class(spec)
            if cls is not None:
                return cls
        return None

    # ------------------------------------------------------------------
    # ADR-028 §D8 / #1077: IO-block dispatch by (type, extension).
    # ------------------------------------------------------------------

    def find_loader(
        self,
        dtype: type | None,
        extension: str,
    ) -> type | None:
        """Return the loader class whose ``supported_extensions`` contains *extension*
        and whose first output port accepts *dtype*.

        Extension matching is case-insensitive and runs against the same
        compound-first lookup used by :meth:`IOBlock._detect_format` (so
        a query for ``".OME.TIF"`` resolves a loader that declared
        ``".ome.tif"``).

        Type compatibility uses :meth:`TypeSignature.matches` (ADR-027):
        a registered loader matches *dtype* when at least one of the
        loader's declared ``output_ports[0].accepted_types`` produces a
        signature that *dtype*'s signature is compatible with (i.e. the
        loader's output IS-A *dtype*). A loader declaring ``Array`` output
        is **not** a match when queried with ``Image`` because ``Array``
        is not an ``Image`` subtype.

        Migration policy: ADR-043 capability lookup is used whenever it can
        resolve a deterministic winner. If a legacy caller hits a capability
        ambiguity, this method falls back to the pre-ADR-043 compatibility
        path so old extension-only callers continue to run during migration.
        New runtime dispatch should use :meth:`find_loader_capability`, which
        raises :class:`AmbiguousCapabilityError` instead of selecting by
        registration order.

        When ``dtype is None`` the type filter is skipped and the first
        loader (by registration order) whose ``supported_extensions``
        contains *extension* is returned. Used by callers that only know
        the file extension.

        Returns ``None`` if no loader matches. Plugin modules that fail
        to import at query time are dropped silently (matches the
        existing tolerance in :meth:`scan`).
        """
        if not extension:
            return None
        try:
            capability = self.find_loader_capability(dtype or DataObject, extension)
        except MissingCapabilityError:
            return None
        except AmbiguousCapabilityError as exc:
            legacy_cls = self._resolve_first_capability_class(exc.candidates)
            return legacy_cls or self._find_io_block(direction="input", dtype=dtype, extension=extension)
        return self._resolve_capability_class(capability)

    def find_saver(
        self,
        dtype: type,
        extension: str,
    ) -> type | None:
        """Return the saver class whose ``supported_extensions`` contains *extension*
        and whose first input port accepts an instance of *dtype*.

        Extension matching and type matching follow the same migration
        behavior as :meth:`find_loader`. New runtime dispatch should use
        :meth:`find_saver_capability` for explicit ambiguity errors.
        """
        if not extension:
            return None
        try:
            capability = self.find_saver_capability(dtype, extension)
        except MissingCapabilityError:
            return None
        except AmbiguousCapabilityError as exc:
            legacy_cls = self._resolve_first_capability_class(exc.candidates)
            return legacy_cls or self._find_io_block(direction="output", dtype=dtype, extension=extension)
        return self._resolve_capability_class(capability)

    def find_io_blocks_for_type(
        self,
        dtype: type,
        direction: str,
    ) -> list[type]:
        """Enumerate every loader (``direction=\"input\"``) or saver
        (``direction=\"output\"``) whose first port accepts *dtype*.

        Returns the resolved class objects in registration order
        (extension is not part of the filter). Intended for port-editor
        UI code that populates a \"save as format\" dropdown for a given
        DataObject type. Type compatibility uses the same
        :meth:`TypeSignature.matches` rule as :meth:`find_loader` /
        :meth:`find_saver`.

        Raises ``ValueError`` for any *direction* other than
        ``\"input\"`` or ``\"output\"``.
        """
        if direction not in ("input", "output"):
            raise ValueError(f"direction must be 'input' or 'output', got {direction!r}")

        results: list[type] = []
        for spec in self._registry.values():
            if spec.direction != direction:
                continue
            cls = self._resolve_class(spec)
            if cls is None:
                continue
            if not self._class_accepts_dtype(cls, dtype, direction):
                continue
            results.append(cls)
        return results

    # --- helpers --------------------------------------------------------

    def _find_io_block(
        self,
        *,
        direction: str,
        dtype: type | None,
        extension: str,
    ) -> type | None:
        """Shared core for :meth:`find_loader` / :meth:`find_saver`."""
        if not extension:
            return None
        normalized_ext = extension.lower()

        # Collect (specificity_key, cls) for ranking. Specificity = length
        # of the longest accepted-types signature chain that satisfies
        # the type filter. Insertion order is preserved by iterating
        # ``self._registry.values()`` (Python 3.7+ dict ordering).
        matches: list[tuple[int, type]] = []
        for spec in self._registry.values():
            if spec.direction != direction:
                continue
            if not _ext_in_mapping(normalized_ext, spec.supported_extensions):
                continue
            cls = self._resolve_class(spec)
            if cls is None:
                continue
            if dtype is not None:
                specificity = self._best_specificity(cls, dtype, direction)
                if specificity < 0:
                    continue
            else:
                specificity = 0
            matches.append((specificity, cls))

        if not matches:
            return None
        # Sort by specificity DESC, preserving insertion order on ties
        # (Python's sort is stable).
        matches.sort(key=lambda pair: -pair[0])
        return matches[0][1]

    @staticmethod
    def _resolve_class(spec: BlockSpec) -> type | None:
        """Load the class referenced by *spec*. Returns ``None`` on import failure.

        Mirrors :meth:`instantiate`'s import path (mtime-keyed reload for
        Tier-1 drop-ins, normal ``import_module`` otherwise) but does
        **not** instantiate the class — query methods only need the
        ClassVars (``supported_extensions``, ports). On any import or
        attribute error the method returns ``None`` so a single bad
        plugin does not break dispatch for the rest.
        """
        try:
            if spec.file_path:
                path = Path(spec.file_path)
                mtime = path.stat().st_mtime
                mod_name = f"_scieasy_dropin_{path.stem}_{int(mtime)}"
                mod_spec = importlib.util.spec_from_file_location(mod_name, path)
                if mod_spec is None or mod_spec.loader is None:
                    return None
                module = importlib.util.module_from_spec(mod_spec)
                mod_spec.loader.exec_module(module)
            else:
                module = importlib.import_module(spec.module_path)
            cls = getattr(module, spec.class_name, None)
            return cls if isinstance(cls, type) else None
        except Exception:
            logger.debug(
                "registry.find_*: class import failed for %s.%s",
                spec.module_path,
                spec.class_name,
                exc_info=True,
            )
            return None

    @staticmethod
    def _class_accepts_dtype(cls: type, dtype: type, direction: str) -> bool:
        """Return True if *cls*'s first port is compatible with *dtype* (boolean form)."""
        return BlockRegistry._best_specificity(cls, dtype, direction) >= 0

    @staticmethod
    def _best_specificity(cls: type, dtype: type, direction: str) -> int:
        """Return the longest matching type-chain length, or ``-1`` if no match.

        For ``direction == \"input\"`` the loader's ``output_ports[0]``
        is checked: the loader's output type must be a subtype of *dtype*
        (the loader produces something assignable to dtype).

        For ``direction == \"output\"`` the saver's ``input_ports[0]``
        is checked: the saver's input accepted-types must include a
        supertype of *dtype* (the saver can accept an instance of dtype).
        """
        from scieasy.core.types.base import TypeSignature

        if direction == "input":
            ports = getattr(cls, "output_ports", None) or []
        else:
            ports = getattr(cls, "input_ports", None) or []
        if not ports:
            return -1
        accepted_types = getattr(ports[0], "accepted_types", None) or []
        if not accepted_types:
            # Empty list means "accepts anything"; treat as the most-
            # general match (chain length 1 — DataObject).
            return 1

        try:
            dtype_sig = TypeSignature.from_type(dtype)
        except Exception:
            return -1

        best = -1
        for accepted in accepted_types:
            try:
                accepted_sig = TypeSignature.from_type(accepted)
            except Exception:
                continue
            if direction == "input":
                # Loader produces ``accepted`` — does that satisfy dtype?
                # accepted IS-A dtype iff accepted's chain includes dtype
                # as a prefix, i.e. dtype_sig is a prefix of accepted_sig,
                # i.e. ``accepted_sig.matches(dtype_sig)`` is True.
                if accepted_sig.matches(dtype_sig):
                    best = max(best, len(accepted_sig.type_chain))
            else:
                # Saver accepts ``accepted`` — can it receive a dtype
                # instance? Yes iff dtype IS-A accepted, i.e. accepted
                # is a prefix of dtype.
                if dtype_sig.matches(accepted_sig):
                    best = max(best, len(accepted_sig.type_chain))
        return best


def _ext_in_mapping(extension_lower: str, mapping: dict[str, str]) -> bool:
    """Case-insensitive membership check for ``supported_extensions``.

    Accepts both forms ``".tif"`` and ``"tif"`` for *extension_lower*
    (the leading dot is normalized). Returns True if any key in *mapping*
    matches case-insensitively. Used by :meth:`BlockRegistry._find_io_block`.
    """
    if not mapping:
        return False
    candidate = extension_lower if extension_lower.startswith(".") else f".{extension_lower}"
    return any(candidate == key.lower() for key in mapping)


def _capability_matches_type(
    capability: FormatCapability,
    data_type: type[DataObject],
    direction: CapabilityDirection,
) -> bool:
    try:
        capability_signature = TypeSignature.from_type(capability.data_type)
        query_signature = TypeSignature.from_type(data_type)
    except Exception:
        return False

    if direction == "load":
        return capability_signature.matches(query_signature)
    return query_signature.matches(capability_signature)


def _capability_type_specificity(capability: FormatCapability) -> int:
    try:
        return len(TypeSignature.from_type(capability.data_type).type_chain)
    except Exception:
        return 0


def _capability_error_message(
    prefix: str,
    *,
    direction: CapabilityDirection,
    data_type: type[DataObject],
    extension: str | None = None,
    format_id: str | None = None,
    capability_id: str | None = None,
    candidates: tuple[FormatCapability, ...] = (),
) -> str:
    candidate_ids = ", ".join(candidate.id for candidate in candidates) if candidates else "none"
    return (
        f"{prefix}: direction={direction!r}, data_type={data_type.__name__!r}, "
        f"extension={extension!r}, format_id={format_id!r}, capability_id={capability_id!r}, "
        f"candidates=[{candidate_ids}]"
    )


def _validate_capability_id(capability: FormatCapability) -> None:
    parts = capability.id.split(".")
    if len(parts) < 3 or any(not part for part in parts):
        raise CapabilityRegistrationError(f"Capability id {capability.id!r} must be stable and package-qualified.")
    if any(char.isspace() for char in capability.id):
        raise CapabilityRegistrationError(f"Capability id {capability.id!r} must not contain whitespace.")


def _format_capabilities_from_class(cls: type) -> list[FormatCapability]:
    from scieasy.blocks.io.io_block import IOBlock

    if not issubclass(cls, IOBlock):
        return []

    _validate_simple_extension_declaration(cls)
    capabilities = list(cls.get_format_capabilities())
    for capability in capabilities:
        if not isinstance(capability, FormatCapability):
            raise CapabilityRegistrationError(
                f"{cls.__name__}.get_format_capabilities() returned {type(capability).__name__}, "
                "expected FormatCapability."
            )
        _validate_class_capability(cls, capability)
    return capabilities


def _validate_simple_extension_declaration(cls: type) -> None:
    if not hasattr(cls, "extensions"):
        return
    extensions = cls.extensions
    if isinstance(extensions, str):
        raise CapabilityRegistrationError(
            f"{cls.__name__}.extensions must be an iterable of extension strings, not a scalar string."
        )


def _validate_class_capability(cls: type, capability: FormatCapability) -> None:
    expected_direction: CapabilityDirection = "load" if getattr(cls, "direction", "") == "input" else "save"
    if capability.direction != expected_direction:
        raise CapabilityRegistrationError(
            f"{cls.__name__} has IO direction {getattr(cls, 'direction', '')!r} but capability "
            f"{capability.id!r} declares {capability.direction!r}."
        )
    if capability.block_type != cls.__name__:
        raise CapabilityRegistrationError(
            f"{cls.__name__} capability {capability.id!r} must declare block_type={cls.__name__!r}, "
            f"got {capability.block_type!r}."
        )
    handler = getattr(cls, capability.handler, None)
    if not callable(handler):
        raise CapabilityRegistrationError(
            f"{cls.__name__} capability {capability.id!r} references missing handler {capability.handler!r}."
        )
    _validate_capability_id(capability)


def _subclass_declares_field(cls: type, field_name: str) -> bool:
    """Return True if the leaf class's own ``config_schema`` declares *field_name*.

    Checks only ``cls.__dict__`` (the leaf class itself), not the MRO.
    Used by direction-aware post-processing to decide whether to override
    inherited path fields.
    """
    own_schema = cls.__dict__.get("config_schema")
    if not isinstance(own_schema, dict):
        return False
    return field_name in own_schema.get("properties", {})


def _merge_config_schema(cls: type) -> dict[str, Any]:
    """Merge ``config_schema`` properties along the MRO (child wins on conflict).

    ADR-030 D1: walks ``cls.__mro__`` in reverse (base first) and unions
    all ``properties`` dicts.  Uses ``klass.__dict__`` (own attributes only),
    not ``getattr``, so intermediate classes that do not declare their own
    ``config_schema`` are skipped rather than inheriting the same dict
    repeatedly.

    After merging, applies direction-aware post-processing for IOBlock
    subclasses (ADR-030 D2): if the block has ``direction == "output"``
    and the ``path`` field was inherited (not declared in the leaf class),
    the path field is converted to single-string ``directory_browser``.
    """
    import copy

    merged_properties: dict[str, Any] = {}
    merged_required: list[str] = []
    for klass in reversed(cls.__mro__):
        schema = klass.__dict__.get("config_schema")
        if schema and isinstance(schema, dict):
            # Deep-copy so post-processing mutations don't corrupt the
            # class-level dict shared by all instances of the base class.
            merged_properties.update(copy.deepcopy(schema.get("properties", {})))
            merged_required.extend(schema.get("required", []))

    # ADR-030 D2: direction-aware path adjustment for IOBlock output subclasses.
    direction = getattr(cls, "direction", "")
    if direction == "output" and "path" in merged_properties and not _subclass_declares_field(cls, "path"):
        path_prop = merged_properties["path"]
        path_prop["type"] = "string"
        path_prop["ui_widget"] = "directory_browser"
        path_prop.pop("items", None)

    # Issue #571: enforce forced ordering for AppBlock subclasses.
    # app_command must be ui_priority 0, output_dir must be ui_priority 1,
    # and all other properties must have ui_priority >= 2.
    from scieasy.blocks.app.app_block import AppBlock

    if isinstance(cls, type) and issubclass(cls, AppBlock):
        if "app_command" in merged_properties:
            merged_properties["app_command"]["ui_priority"] = 0
        if "output_dir" in merged_properties:
            merged_properties["output_dir"]["ui_priority"] = 1
        reserved_keys = {"app_command", "output_dir"}
        for key, prop in merged_properties.items():
            if key not in reserved_keys and isinstance(prop, dict):
                current_priority = prop.get("ui_priority")
                if isinstance(current_priority, (int, float)) and current_priority < 2:
                    prop["ui_priority"] = 2

        # Inject ClassVar defaults into config_schema so the frontend shows
        # pre-filled values (e.g. "napari", "fiji") when a block is dropped.
        if "app_command" in merged_properties:
            cls_cmd = getattr(cls, "app_command", "")
            if cls_cmd and "default" not in merged_properties["app_command"]:
                merged_properties["app_command"]["default"] = cls_cmd
        if "output_patterns" in merged_properties:
            cls_patterns = getattr(cls, "output_patterns", None)
            if cls_patterns and "default" not in merged_properties["output_patterns"]:
                default_pat = ",".join(cls_patterns) if isinstance(cls_patterns, list) else cls_patterns
                merged_properties["output_patterns"]["default"] = default_pat

    return {
        "type": "object",
        "properties": merged_properties,
        "required": list(dict.fromkeys(merged_required)),
    }


_PACKAGES_DISTRIBUTIONS_CACHE: dict[str, list[str]] | None = None


def _packages_distributions_cached() -> dict[str, list[str]]:
    """Cache ``importlib.metadata.packages_distributions()`` — it walks the
    full site-packages tree and is too slow to call once per block."""
    global _PACKAGES_DISTRIBUTIONS_CACHE
    if _PACKAGES_DISTRIBUTIONS_CACHE is None:
        try:
            _PACKAGES_DISTRIBUTIONS_CACHE = dict(importlib.metadata.packages_distributions())
        except Exception:
            _PACKAGES_DISTRIBUTIONS_CACHE = {}
    return _PACKAGES_DISTRIBUTIONS_CACHE


def _resolve_distribution_version(cls: type) -> str:
    """Return the PyPI distribution version of the module hosting ``cls``.

    ADR-038 §3.3 (D38-3.2 / closes audit D38-3.1a P1-2): ``block_version``
    is force-injected at registry scan time from
    ``importlib.metadata.version(<distribution_name>)``. In-tree blocks
    live under the ``scieasy`` distribution and read
    ``scieasy.__version__``. Plugin blocks read their entry-point
    distribution version (ADR-037 D11). Drop-in ``.py`` files have no
    distribution, so they fall back to the SciEasy version as a uniform
    default.

    The function **raises** :class:`BlockRegistrationError` when no
    distribution can be resolved. Per ADR §3.3 the historical
    ``"unknown"`` default is forbidden because every lineage row's
    ``block_version`` column must carry a real version for
    reproducibility. The Tier 1 / Tier 2 / monorepo scan loops already
    wrap each block registration in ``try/except`` so a per-block raise
    here does not kill the whole palette — only the offending block is
    dropped, with a logged warning.
    """
    module_name = getattr(cls, "__module__", "") or ""

    def _scieasy_version() -> str | None:
        try:
            from scieasy import __version__ as scieasy_version

            v = str(scieasy_version)
            return v if v else None
        except Exception:
            return None

    # 1. Built-in / in-tree blocks: stamp the running scieasy version.
    if module_name.startswith("scieasy.") or module_name == "scieasy":
        sv = _scieasy_version()
        if sv is not None:
            return sv
    # 2. Tier-1 drop-in modules use a synthetic name (``_scieasy_dropin_...``);
    #    they have no distribution. Use scieasy version as the uniform default.
    if module_name.startswith("_scieasy_dropin_"):
        sv = _scieasy_version()
        if sv is not None:
            return sv
    # 3. In-tree test fixtures (``tests.*``) are not a real distribution but
    #    are part of the repo and exist only when running pytest. Stamp the
    #    scieasy version so the strict raise doesn't fire on test-only
    #    Block subclasses like ``tests.fixtures.noop_block.NoopBlock``.
    if module_name.startswith("tests.") or module_name == "tests":
        sv = _scieasy_version()
        if sv is not None:
            return sv
    # 4. Entry-point / monorepo plugins: look up the distribution that owns
    #    the top-level module.
    top_level = module_name.split(".", 1)[0]
    if top_level:
        try:
            mapping = _packages_distributions_cached()
            dists = mapping.get(top_level) or []
            for dist_name in dists:
                with contextlib.suppress(importlib.metadata.PackageNotFoundError):
                    return str(importlib.metadata.version(dist_name))
        except Exception:
            logger.debug(
                "registry: packages_distributions() lookup failed for %s",
                top_level,
                exc_info=True,
            )
        # 5. Some plugins publish under the same name as their top-level module.
        with contextlib.suppress(importlib.metadata.PackageNotFoundError):
            return str(importlib.metadata.version(top_level))
        # 6. Monorepo / dev-install convention: ``scieasy_blocks_<name>``
        #    Python package → ``scieasy-blocks-<name>`` distribution name
        #    (PEP 503 normalisation). ``packages_distributions`` does not
        #    always populate this mapping for editable installs, so try
        #    the explicit normalised name as a last resort.
        if top_level.startswith("scieasy_blocks_"):
            normalised = top_level.replace("_", "-")
            with contextlib.suppress(importlib.metadata.PackageNotFoundError):
                return str(importlib.metadata.version(normalised))
            # If the plugin distribution truly isn't installed (CI without
            # ``pip install -e .`` on the monorepo packages), stamp the
            # scieasy version so the per-block registration still succeeds.
            # This is identical to the in-tree fallback in §1: the plugin
            # is part of the same repo checkout.
            sv = _scieasy_version()
            if sv is not None:
                return sv

    # 5. ADR §3.3 forbids the historical "unknown" default. Fail loudly —
    # the scan-loop catch logs and continues so a single mis-packaged
    # block does not kill the palette.
    raise BlockRegistrationError(
        f"ADR-038 §3.3: cannot resolve distribution version for {cls!r} "
        f"(module={module_name!r}); register a setuptools/poetry distribution "
        f"or place the block under ``scieasy.*`` so ``scieasy.__version__`` "
        f"can be stamped."
    )


def _spec_from_class(cls: type, source: str = "") -> BlockSpec:
    """Build a :class:`BlockSpec` from a Block subclass's class-level metadata.

    ADR-028 Addendum 1 D3: validates ``dynamic_ports`` shape at scan time and
    captures both ``direction`` (for IO blocks) and ``dynamic_ports`` (for
    enum-driven dynamic-port blocks) onto the spec.

    ADR-030 D1: uses ``_merge_config_schema()`` instead of a simple
    ``getattr`` to merge config_schema properties along the MRO.

    ADR-038 §3.3: ``version`` is force-injected from ``importlib.metadata``
    rather than the legacy ``getattr(cls, "version", "0.1.0")`` default.
    """
    # Fail loudly at scan time on malformed dynamic-port descriptors.
    BlockRegistry._validate_dynamic_ports(cls)

    base_cat = _infer_category(cls)
    sub_cat = getattr(cls, "subcategory", "") or ""

    # ADR-029 D11: serialize allowed_input/output_types ClassVars to string
    # lists for the API.  Empty list on the class means "any DataObject".
    allowed_in: list[str] = [t.__name__ for t in (getattr(cls, "allowed_input_types", None) or [])]
    allowed_out: list[str] = [t.__name__ for t in (getattr(cls, "allowed_output_types", None) or [])]

    return BlockSpec(
        name=getattr(cls, "name", cls.__name__),
        description=getattr(cls, "description", "") or (cls.__doc__ or "").split("\n")[0],
        version=_resolve_distribution_version(cls),
        module_path=cls.__module__,
        class_name=cls.__name__,
        base_category=base_cat,
        subcategory=sub_cat,
        input_ports=list(getattr(cls, "input_ports", [])),
        output_ports=list(getattr(cls, "output_ports", [])),
        config_schema=_merge_config_schema(cls),
        source=source,
        type_name=_type_name_for_class(cls),
        direction=getattr(cls, "direction", "") or "",
        dynamic_ports=getattr(cls, "dynamic_ports", None),
        variadic_inputs=bool(getattr(cls, "variadic_inputs", False)),
        variadic_outputs=bool(getattr(cls, "variadic_outputs", False)),
        allowed_input_types=allowed_in,
        allowed_output_types=allowed_out,
        # ADR-029 Addendum 1: port count limits.
        min_input_ports=getattr(cls, "min_input_ports", None),
        max_input_ports=getattr(cls, "max_input_ports", None),
        min_output_ports=getattr(cls, "min_output_ports", None),
        max_output_ports=getattr(cls, "max_output_ports", None),
        # ADR-028 §D8 / #1077: cache the declared extensions for
        # :meth:`BlockRegistry.find_loader` / :meth:`find_saver`. Default
        # to an empty dict for non-IOBlock classes (or IOBlocks that have
        # not yet declared the ClassVar — see #1074-#1076).
        supported_extensions=dict(getattr(cls, "supported_extensions", {}) or {}),
        # ADR-043: capture normalized IO format capabilities at scan time so
        # lookup does not need to re-import block classes for ordinary queries.
        format_capabilities=_format_capabilities_from_class(cls),
    )


def _infer_category(cls: type) -> str:
    """Infer the base block category from the class hierarchy.

    Always returns one of the 6 base types (io, process, code, app, ai,
    subworkflow) based on isinstance checks.  Never reads a ClassVar
    override — subcategory is a separate field.  See issue #588.
    """
    # Lazy imports to avoid circular dependencies.
    from scieasy.blocks.ai.ai_block import AIBlock
    from scieasy.blocks.app.app_block import AppBlock
    from scieasy.blocks.code.code_block import CodeBlock
    from scieasy.blocks.io.io_block import IOBlock
    from scieasy.blocks.process.process_block import ProcessBlock
    from scieasy.blocks.subworkflow.subworkflow_block import SubWorkflowBlock

    if issubclass(cls, IOBlock):
        return "io"
    if issubclass(cls, ProcessBlock):
        return "process"
    if issubclass(cls, CodeBlock):
        return "code"
    if issubclass(cls, AppBlock):
        return "app"
    if issubclass(cls, AIBlock):
        return "ai"
    if issubclass(cls, SubWorkflowBlock):
        return "subworkflow"
    return "unknown"


def _type_name_for_class(cls: type) -> str:
    """Return the public API identifier for a block class."""
    explicit = getattr(cls, "type_name", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    return cls.__name__.replace("Block", "").lower() + "_block"
