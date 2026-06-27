"""Scan / registration helpers for :class:`BlockRegistry`.

Per ADR-047 §C9: this module hosts only module-level private helpers — it
must contain **zero** ``class`` definitions. The :class:`BlockRegistry`
class lives in ``__init__.py``.

Owns:

- ``_scan_builtins`` — register the four core blocks (LoadData, SaveData,
  AIBlock, SubWorkflowBlock).
- ``_scan_tier1`` — discover blocks from ``.py`` files under configured
  scan directories.
- ``_scan_tier2`` — discover blocks via ``scistudio.blocks`` entry points
  (ADR-025 callable protocol).
- ``_scan_package_src_dirs`` — Tier 3 scan of hard-installed/bundled
  ``packages/*/src`` source packages (desktop runtime).
- ``_register_spec`` — apply per-spec validation and write into the
  registry's ``_registry`` + ``_aliases`` dicts.
- ``_validate_capability_registration`` — ADR-043 capability-id and
  default-conflict cross-spec validation.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import inspect
import logging
import sys
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scistudio.blocks.io.capabilities import FormatCapability
from scistudio.core.types.base import DataObject
from scistudio.desktop.paths import (
    candidate_package_dirs,
    iter_source_package_module_candidates,
    prepended_sys_paths,
    user_python_import_roots,
)

if TYPE_CHECKING:
    from scistudio.blocks.registry import BlockRegistry, BlockSpec

logger = logging.getLogger(__name__)


def _register_spec(registry: BlockRegistry, spec: BlockSpec) -> None:
    _validate_capability_registration(registry, spec)
    registry._registry[spec.name] = spec
    if spec.type_name:
        registry._aliases[spec.type_name] = spec.name


def _validate_capability_registration(registry: BlockRegistry, spec: BlockSpec) -> None:
    """Validate new capability rows against the already-indexed registry."""
    from scistudio.blocks.registry import CapabilityRegistrationError
    from scistudio.blocks.registry._capability import _iter_capability_specs, _validate_capability_id

    seen_ids: set[str] = set()
    for capability in spec.format_capabilities:
        if capability.id in seen_ids:
            raise CapabilityRegistrationError(f"{spec.class_name} declares duplicate capability id {capability.id!r}.")
        seen_ids.add(capability.id)
        _validate_capability_id(capability)

        for existing_capability, existing_spec in _iter_capability_specs(registry):
            if existing_spec.name == spec.name:
                continue
            if existing_capability.id == capability.id:
                raise CapabilityRegistrationError(
                    "Duplicate capability id "
                    f"{capability.id!r} on {spec.class_name}; already declared by {existing_spec.class_name}."
                )

    default_index: dict[tuple[str, type[DataObject], str], tuple[FormatCapability, BlockSpec]] = {}
    prospective_specs = [
        existing_spec for existing_spec in registry._registry.values() if existing_spec.name != spec.name
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


def _scan_builtins(registry: BlockRegistry) -> None:
    """Register first-party core blocks shipped inside ``scistudio`` itself.

    Issue #1779: core's own palette blocks are registered here by direct
    import, **not** via ``scistudio.blocks`` entry points. Entry-point
    discovery (:func:`_scan_tier2`) depends on installed ``*.dist-info``
    metadata, which the desktop bundle does not carry — it ships core as raw
    source on ``PYTHONPATH`` and strips build metadata (``stage-resources.sh``,
    #1775). Relying on entry points for first-party blocks made the whole
    process/code/app palette vanish in packaged builds, leaving only the
    handful already hard-registered here. Direct registration is
    environment-independent (source checkout, editable install, bundled
    source, or frozen), so the ``scistudio.blocks`` entry-point group is now
    reserved for third-party plugin packages only.

    Only concrete, user-facing blocks are registered. The DataFrame-level
    process placeholders ``MergeBlock`` (``Merge``) and ``SplitBlock``
    (``Split``) are intentionally excluded from the palette. The interactive
    :class:`DataRouter` supersedes the former collection filter/slice/split
    blocks; :class:`MergeCollection` remains as the variadic merge primitive.
    The excluded classes remain importable for plugin development
    and tests.
    """
    from scistudio.blocks.ai.ai_block import AIBlock
    from scistudio.blocks.app import AppBlock
    from scistudio.blocks.code import CodeBlock
    from scistudio.blocks.io.loaders.load_data import LoadData
    from scistudio.blocks.io.savers.save_data import SaveData
    from scistudio.blocks.process.builtins.data_router import DataRouter
    from scistudio.blocks.process.builtins.merge_collection import MergeCollection
    from scistudio.blocks.process.builtins.pair_editor import PairEditor
    from scistudio.blocks.registry._spec import _spec_from_class
    from scistudio.blocks.subworkflow.subworkflow_block import SubWorkflowBlock

    for cls in (
        LoadData,
        SaveData,
        AIBlock,
        SubWorkflowBlock,
        CodeBlock,
        AppBlock,
        DataRouter,
        MergeCollection,
        PairEditor,
    ):
        _register_spec(registry, _spec_from_class(cls, source="builtin"))


def _scan_tier1(registry: BlockRegistry) -> None:
    """Tier 1: scan configured directories for ``.py`` files containing Block subclasses.

    Security boundary (issue #1531): drop-in files are executed as Python
    modules in the server process.  Only files from trusted project- or
    user-controlled directories should be registered via
    :meth:`BlockRegistry.add_scan_dir`.  Hostile or corrupt drop-ins are
    isolated by the try/except below — a failing module is logged as a
    warning and skipped without crashing the palette refresh.

    TODO(#1531): a full subprocess-sandbox for drop-in execution is deferred.
      Out of scope per issue #1531 (contained hardening only for this PR).
      Followup: https://github.com/zjzcpj/SciStudio/issues/1531
    """
    from scistudio.blocks.base.block import Block
    from scistudio.blocks.registry._spec import _spec_from_class

    for scan_dir in registry._scan_dirs:
        if not scan_dir.is_dir():
            continue
        for py_file in scan_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            # Issue #1531: emit a security warning before executing any
            # drop-in so operators can audit which files run in-process.
            logger.warning(
                "SECURITY: executing drop-in block module from %s in the server process. "
                "Only add trusted directories via BlockRegistry.add_scan_dir.",
                py_file,
            )
            try:
                mtime = py_file.stat().st_mtime
                mod_name = f"_scistudio_dropin_{py_file.stem}_{int(mtime)}"
                spec = importlib.util.spec_from_file_location(mod_name, py_file)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                # Issue #1531: wrap exec_module in its own try/except so a
                # failing or hostile drop-in cannot crash the palette refresh.
                try:
                    with prepended_sys_paths(_desktop_user_python_import_roots()):
                        spec.loader.exec_module(module)
                except Exception:
                    # #1531: skip-don't-crash on a failing/hostile drop-in.
                    # Keep the historical "Failed to import block from" wording
                    # (asserted by the registry-logging contract test) so the
                    # hardening does not change the observable error log.
                    logger.warning(
                        "Failed to import block from %s: drop-in module raised "
                        "during import; skipping (it contributes no blocks).",
                        py_file,
                        exc_info=True,
                    )
                    continue

                for attr_name in dir(module):
                    obj = getattr(module, attr_name)
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, Block)
                        and obj is not Block
                        and not inspect.isabstract(obj)
                        # #706 audit: ``dir(module)`` also surfaces Block
                        # subclasses *imported* from other modules (e.g.
                        # ``from scistudio.blocks.code import CodeBlock``).
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
                        with suppress(AttributeError, TypeError):
                            obj._scistudio_file_path = str(py_file)  # type: ignore[attr-defined]
                        block_spec = _spec_from_class(obj, source="tier1")
                        block_spec.file_path = str(py_file)
                        block_spec.file_mtime = mtime
                        block_spec.module_path = mod_name
                        block_spec.runtime_import_roots = [str(path) for path in _desktop_user_python_import_roots()]
                        _register_spec(registry, block_spec)
            except Exception:
                logger.warning(
                    "Failed to import block from %s",
                    py_file,
                    exc_info=True,
                )
                continue


def _scan_tier2(registry: BlockRegistry) -> None:
    """Tier 2: scan ``scistudio.blocks`` entry-points using callable protocol.

    This group is reserved for third-party plugin packages (#1779). Core's own
    first-party blocks are registered directly in :func:`_scan_builtins` and do
    not appear here, so a packaged build with no ``*.dist-info`` metadata still
    gets the full core palette.

    Each entry-point resolves to a callable.  When invoked, it returns
    either:

    * ``(PackageInfo, list[type[Block]])`` -- package metadata + block list
    * ``list[type[Block]]`` -- plain list (backward compatible, uses
      entry-point name as the package display name)

    See ADR-025 for the full specification.
    """
    from scistudio.blocks.base.block import Block
    from scistudio.blocks.base.package_info import PackageInfo
    from scistudio.blocks.registry._spec import _spec_from_class

    try:
        eps = importlib.metadata.entry_points()
    except Exception:
        logger.warning("Failed to load entry_points for block discovery", exc_info=True)
        return

    eps_any: Any = eps
    block_eps: Any = (
        eps_any.select(group="scistudio.blocks") if hasattr(eps_any, "select") else eps_any.get("scistudio.blocks", [])
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
                registry._packages[info.name] = info

            for cls in block_classes:
                if isinstance(cls, type) and issubclass(cls, Block) and not inspect.isabstract(cls):
                    block_spec = _spec_from_class(cls, source="entry_point")
                    block_spec.module_path = cls.__module__
                    block_spec.class_name = cls.__name__
                    block_spec.package_name = pkg_name
                    # #1772: surface shared user-site deps (installed via the
                    # in-app Python terminal) to the worker for entry-point
                    # blocks too, matching the source-package path.
                    block_spec.runtime_import_roots = [str(path) for path in _desktop_user_python_import_roots()]
                    _register_spec(registry, block_spec)
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


def _desktop_resource_package_dirs() -> list[Path]:
    """Return package directories implied by desktop/resource environment."""
    return candidate_package_dirs()


def _desktop_user_python_import_roots() -> list[Path]:
    """Return shared user dependency roots for trusted drop-in imports."""
    return list(user_python_import_roots())


def _process_package_protocol_result(
    registry: BlockRegistry,
    *,
    module_name: str,
    result: Any,
    source: str,
    runtime_import_roots: list[Path] | None = None,
) -> None:
    """Register block classes returned by a source package protocol hook."""
    from scistudio.blocks.base.block import Block
    from scistudio.blocks.base.package_info import PackageInfo
    from scistudio.blocks.registry._spec import _spec_from_class

    info: PackageInfo | None = None
    block_classes: list[type] = []
    if isinstance(result, tuple) and len(result) == 2:
        first, second = result
        if isinstance(first, PackageInfo) and isinstance(second, list):
            info = first
            block_classes = second
        else:
            logger.warning("Package '%s' returned unexpected tuple format", module_name)
            return
    elif isinstance(result, list):
        block_classes = result
    else:
        logger.warning(
            "Package '%s' returned unsupported type: %s",
            module_name,
            type(result).__name__,
        )
        return

    pkg_name = info.name if info is not None else module_name
    if info is not None:
        registry._packages[info.name] = info

    for cls in block_classes:
        if not (isinstance(cls, type) and issubclass(cls, Block) and not inspect.isabstract(cls)):
            logger.warning("Package '%s' contained non-concrete Block item: %s", module_name, cls)
            continue
        block_spec = _spec_from_class(cls, source=source)
        block_spec.module_path = cls.__module__
        block_spec.class_name = cls.__name__
        block_spec.package_name = pkg_name
        # #1772: a worker running this block must also resolve dependencies the
        # user installed through the in-app Python terminal, which land in the
        # shared user dependency site. Append that site after the package's own
        # roots so per-package deps keep precedence while shared-site extras
        # (e.g. ``cellpose``) become importable.
        block_spec.runtime_import_roots = list(
            dict.fromkeys(str(path) for path in [*(runtime_import_roots or []), *_desktop_user_python_import_roots()])
        )
        if block_spec.type_name in registry._aliases or block_spec.name in registry._registry:
            continue
        _register_spec(registry, block_spec)


def _scan_source_package_module(
    registry: BlockRegistry,
    *,
    import_roots: tuple[Path, ...],
    module_name: str,
    source: str,
) -> None:
    """Import one ``scistudio_blocks_*`` package and register its block classes."""
    try:
        runtime_import_roots = tuple(import_roots)
        with prepended_sys_paths(runtime_import_roots):
            stale_modules = [name for name in sys.modules if name == module_name or name.startswith(f"{module_name}.")]
            for name in stale_modules:
                # Keep DataObject type modules stable across block-package refreshes.
                if name.endswith(".types"):
                    continue
                sys.modules.pop(name, None)
            importlib.invalidate_caches()
            module = importlib.import_module(module_name)
            result: Any | None = None
            if hasattr(module, "get_block_package") and callable(module.get_block_package):
                result = module.get_block_package()
            elif hasattr(module, "get_blocks") and callable(module.get_blocks):
                result = module.get_blocks()
            else:
                return
            _process_package_protocol_result(
                registry,
                module_name=module_name,
                result=result,
                source=source,
                runtime_import_roots=list(runtime_import_roots),
            )
    except Exception:
        logger.warning("Failed to import source plugin package '%s' from %s", module_name, import_roots, exc_info=True)


def _scan_package_src_dirs(registry: BlockRegistry) -> None:
    """Tier 3: scan hard-installed ``packages/*/src`` source packages.

    This desktop package path imports already-present ``scistudio_blocks_*``
    source packages through the existing ADR-025 package protocol so ADR-043
    capability validation remains the registry's single source of truth.
    """
    package_dirs = [*registry._package_src_dirs, *_desktop_resource_package_dirs()]
    for _root_name, module_name, import_roots in iter_source_package_module_candidates(package_dirs):
        _scan_source_package_module(
            registry,
            import_roots=import_roots,
            module_name=module_name,
            source="package_src",
        )
