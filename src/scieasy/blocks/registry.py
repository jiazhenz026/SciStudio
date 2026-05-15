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

if TYPE_CHECKING:
    from scieasy.blocks.base.package_info import PackageInfo

logger = logging.getLogger(__name__)


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
        self._registry[spec.name] = spec
        if spec.type_name:
            self._aliases[spec.type_name] = spec.name

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

        block_eps: Any = eps.select(group="scieasy.blocks") if hasattr(eps, "select") else eps.get("scieasy.blocks", [])

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

    ADR-038 §3.3: ``block_version`` is force-injected at registry scan time
    from ``importlib.metadata.version(<distribution_name>)``. In-tree blocks
    live under the ``scieasy`` distribution and read ``scieasy.__version__``.
    Plugin blocks read their entry-point distribution version (ADR-037 D11).
    Drop-in ``.py`` files have no distribution, so they fall back to the
    SciEasy version as a uniform default.

    The function is best-effort: when no distribution can be resolved (e.g.
    an editable-install path that ``packages_distributions`` does not yet
    know about) it returns ``scieasy.__version__``. Registration does not
    fail because failing scan-time for a single block kills the whole
    palette — a less destructive degradation than ADR §3.3's narrative
    suggests, while still removing the historical ``"unknown"`` default.
    """
    module_name = getattr(cls, "__module__", "") or ""
    # 1. Built-in / in-tree blocks: stamp the running scieasy version.
    if module_name.startswith("scieasy.") or module_name == "scieasy":
        try:
            from scieasy import __version__ as scieasy_version

            return str(scieasy_version)
        except Exception:
            pass
    # 2. Tier-1 drop-in modules use a synthetic name (``_scieasy_dropin_...``);
    #    they have no distribution. Use scieasy version as the uniform default.
    if module_name.startswith("_scieasy_dropin_"):
        try:
            from scieasy import __version__ as scieasy_version

            return str(scieasy_version)
        except Exception:
            pass
    # 3. Entry-point / monorepo plugins: look up the distribution that owns
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
        # 4. Some plugins publish under the same name as their top-level module.
        with contextlib.suppress(importlib.metadata.PackageNotFoundError):
            return str(importlib.metadata.version(top_level))

    # 5. Last-ditch fallback: explicit class attribute, then scieasy version.
    explicit = getattr(cls, "version", None)
    if isinstance(explicit, str) and explicit and explicit != "0.1.0":
        return explicit
    try:
        from scieasy import __version__ as scieasy_version

        return str(scieasy_version)
    except Exception:
        return "unknown"


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
