"""Scan / registration helpers for :class:`BlockRegistry`."""
# Maintainer context (kept outside generated API documentation):
# Scan / registration helpers for :class:`BlockRegistry`.
#
# Per ADR-047 §C9: this module hosts only module-level private helpers — it
# must contain **zero** ``class`` definitions. The :class:`BlockRegistry`
# class lives in ``__init__.py``.
#
# Owns:
#
# - ``_scan_builtins`` — register the four core blocks (LoadData, SaveData,
#   AIBlock, SubWorkflowBlock).
# - ``_scan_tier1`` — import the ``.py`` files under configured scan
#   directories by module name (ADR-056) and register their blocks; name-check
#   refusals and import failures become ``DropinFailure`` records.
# - ``_scan_tier2`` — discover blocks via ``scistudio.blocks`` entry points
#   (ADR-025 callable protocol).
# - ``_scan_package_src_dirs`` — Tier 3 scan of hard-installed/bundled
#   ``packages/*/src`` source packages (desktop runtime).
# - ``_register_spec`` — apply per-spec validation and write into the
#   registry's ``_registry`` + ``_aliases`` dicts.
# - ``_validate_capability_registration`` — ADR-043 capability-id and
#   default-conflict cross-spec validation.
# Development references: ADR-025, ADR-043, ADR-047, ADR-053, ADR-056.

from __future__ import annotations

import importlib
import importlib.metadata
import inspect
import logging
import sys
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scistudio.blocks.io.capabilities import FormatCapability
from scistudio.core.entry_points import (
    BLOCKS_ENTRY_POINT_GROUP,
    STAGE_REGISTER,
    EntryPointDiagnostic,
    entry_point_name,
    enumerate_group,
    load_entry_point,
    prepared_plugin_import_roots,
    resolve_payload,
)
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

    core's own palette blocks are registered here by direct
    import, **not** via ``scistudio.blocks`` entry points. Entry-point
    discovery (:func:`_scan_tier2`) depends on installed ``*.dist-info``
    metadata, which the desktop bundle does not carry — it ships core as raw
    source on ``PYTHONPATH`` and strips build metadata (``stage-resources.sh``,
    ). Relying on entry points for first-party blocks made the whole
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
    # Development references: #1775, #1779.
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


def _record_dropin_failure(registry: BlockRegistry, py_file: Path, error_type: str, message: str) -> None:
    """Record one refused drop-in file on the registry."""
    # Development references: ADR-053, FR-015.
    from scistudio.blocks.registry import DropinFailure

    registry._dropin_failures.append(DropinFailure(file_path=str(py_file), error_type=error_type, message=message))


def _reported_dirs(scan_dirs: list[Path]) -> set[Path]:
    """Return the directories whose refusals the block listing reports.

    The block scan directories and the ``types/`` directory of each one's
    tier: the block listing is the surface a user sees, so a refused type file
    of the same tier is reported there too, as it always was (ADR-053 FR-015).
    """
    from scistudio.core.dropins import BLOCKS_DIR_NAME, TYPES_DIR_NAME

    reported: set[Path] = set()
    for scan_dir in scan_dirs:
        with suppress(OSError, ValueError):
            resolved = scan_dir.resolve()
            reported.add(resolved)
            if resolved.name == BLOCKS_DIR_NAME:
                reported.add(resolved.parent / TYPES_DIR_NAME)
    return reported


def _scan_tier1(registry: BlockRegistry) -> None:
    """Tier 1: import the ``.py`` files of the configured directories by name.

    Security boundary: drop-in files are executed as Python modules in the
    server process. Only files from trusted project- or user-controlled
    directories should be registered via :meth:`BlockRegistry.add_scan_dir`.

    ADR-056 Section 4.2. The directories join the user import path
    (:func:`scistudio.core.user_code.ensure_user_import_path`) if they are not
    on it already, and every ``*.py`` file not starting with ``_`` is imported
    with ``importlib.import_module(<stem>)`` through
    :func:`scistudio.core.user_code.load_user_module`. The module keeps its own
    name in ``sys.modules``, so the worker, the in-process instantiation and a
    pickle all resolve the block class by that name, and a block can import a
    helper or another block file beside it.

    Per file:

    - A file the name check refuses (FR-008) is not imported and is recorded as
      a :class:`~scistudio.blocks.registry.DropinFailure`. Refused type files of
      the same tier are recorded here too.
    - A stem that resolves to a file in an earlier user directory (a project
      file shadowing a library file of the same stem) is left to that
      directory's pass, so a block registers once, from the file that defines
      it.
    - A module that raises on import — ``SystemExit`` included — is recorded
      as a failure and contributes no blocks. ``KeyboardInterrupt`` still
      propagates.
    - Only concrete :class:`Block` subclasses the module *defines* register; a
      class it imported from another file registers from that file.

    Two failure modes remain outside this boundary and cannot be brought inside
    it in-process: ``os._exit()``, which no handler can intercept, and a module
    that never returns from import. Both need isolation in a separate process.
    """
    # Maintainer context (kept outside generated API documentation):
    # TODO(#1531): a full subprocess-sandbox for drop-in execution is deferred.
    #   Out of scope per issue #1531 (contained hardening only for this PR).
    #   Followup: https://github.com/zjzcpj/SciStudio/issues/1531
    # Development references: #1531, ADR-053, ADR-056, FR-008, FR-012, FR-013, FR-015, TODO.
    from scistudio.blocks.base.block import Block
    from scistudio.blocks.registry._spec import _spec_from_class
    from scistudio.core.user_code import (
        check_user_import_path,
        ensure_user_import_path,
        load_user_module,
        module_owner_dir,
    )

    registry._dropin_failures = []
    if not registry._scan_dirs:
        return
    user_path = ensure_user_import_path(registry._scan_dirs)
    refusals = {refusal.path: refusal for refusal in check_user_import_path(user_path)}
    reported = _reported_dirs(registry._scan_dirs)
    for path, refusal in refusals.items():
        if path.parent in reported:
            logger.error("ADR-056 FR-008: refused user file %s — %s", path, refusal.message)
            _record_dropin_failure(registry, path, refusal.error_type, refusal.message)

    for scan_dir in registry._scan_dirs:
        if not scan_dir.is_dir():
            continue
        scan_root = scan_dir.resolve()
        for py_file in sorted(scan_root.glob("*.py")):
            if py_file.name.startswith("_") or py_file in refusals:
                continue
            if module_owner_dir(py_file.stem) != scan_root:
                logger.debug("Drop-in block file %s is shadowed by an earlier user directory", py_file)
                continue
            # Issue #1531: emit a security warning before executing any
            # drop-in so operators can audit which files run in-process.
            logger.warning(
                "SECURITY: executing drop-in block module from %s in the server process. "
                "Only add trusted directories via BlockRegistry.add_scan_dir.",
                py_file,
            )
            # #1772: packages the user installed through the in-app terminal
            # live in the shared user dependency site. That window serves
            # installed-package loading, not user code, and stays (ADR-056).
            with prepended_sys_paths(user_python_import_roots()):
                loaded = load_user_module(py_file.stem)
            if not loaded.ok:
                # Keep the historical "Failed to import block from" wording
                # (asserted by the registry-logging contract test).
                logger.warning(
                    "Failed to import block from %s: drop-in module raised during import; "
                    "skipping (it contributes no blocks). %s: %s",
                    py_file,
                    loaded.error_type,
                    loaded.message,
                )
                _record_dropin_failure(registry, py_file, loaded.error_type or "ImportError", loaded.message or "")
                continue
            try:
                for obj in loaded.classes:
                    if issubclass(obj, Block) and obj is not Block and not inspect.isabstract(obj):
                        _register_spec(registry, _spec_from_class(obj, source="tier1"))
            except Exception as exc:
                logger.warning("Failed to import block from %s", py_file, exc_info=True)
                _record_dropin_failure(registry, py_file, type(exc).__name__, str(exc) or type(exc).__name__)


def _scan_tier2(registry: BlockRegistry) -> None:
    """Tier 2: scan ``scistudio.blocks`` entry-points using callable protocol.

    This group is reserved for third-party plugin packages. Core's own
    first-party blocks are registered directly in :func:`_scan_builtins` and do
    not appear here, so a packaged build with no ``*.dist-info`` metadata still
    gets the full core palette.

    Each entry-point resolves to a callable.  When invoked, it returns
    either:

    * ``(PackageInfo, list[type[Block]])`` -- package metadata + block list
    * ``list[type[Block]]`` -- plain list (backward compatible, uses
      entry-point name as the package display name)



    enumeration, per-entry-point error containment, payload
    shape, diagnostics, and ``sys.path`` preparation are
    :mod:`scistudio.core.entry_points`'s answer, shared with the type and
    previewer registries. What stays here is registration: what a
    :class:`PackageInfo` means, which classes are eligible, and what a
    ``BlockSpec`` carries. ``allow_bare_class=True`` below is the
    compatibility affordance for this group alone; the reason it exists and
    the reason it is not extended are recorded in that module, not repeated
    here.
    """
    # Development references: #1779, ADR-025, ADR-053, FR-025, FR-029.
    diagnostics: list[EntryPointDiagnostic] = []
    # FR-030: the plugin import roots carry the ``dist-info`` that makes a
    # user-installed package's entry points visible at all. The previewer
    # registry has always activated them; scanning this group without them is
    # what let the same package resolve for previewers and vanish for blocks.
    with prepared_plugin_import_roots():
        block_eps = enumerate_group(BLOCKS_ENTRY_POINT_GROUP, diagnostics=diagnostics)
        for ep in block_eps:
            _register_entry_point_blocks(registry, ep, diagnostics=diagnostics)
    _record_entry_point_diagnostics(registry, diagnostics)


def _register_entry_point_blocks(
    registry: BlockRegistry,
    ep: Any,
    *,
    diagnostics: list[EntryPointDiagnostic],
) -> None:
    """Load one ``scistudio.blocks`` entry point and register what it returns.

    The registration half of :func:`_scan_tier2`: which payload shapes carry
    blocks, which classes are eligible, and what a ``BlockSpec`` records. The
    ``(PackageInfo, list)`` pair, the plain list, and the bare class are
    the shapes this group accepts.
    """
    # Development references: FR-029.
    from scistudio.blocks.base.block import Block
    from scistudio.blocks.base.package_info import PackageInfo
    from scistudio.blocks.registry._spec import _spec_from_class

    ep_name = entry_point_name(ep)

    loaded = load_entry_point(ep, BLOCKS_ENTRY_POINT_GROUP, diagnostics=diagnostics)
    if loaded is None:
        return

    result = resolve_payload(
        loaded,
        group=BLOCKS_ENTRY_POINT_GROUP,
        entry_point=ep_name,
        allow_bare_class=True,
        diagnostics=diagnostics,
    )
    if result is None:
        return

    try:
        info: Any = None
        block_classes: list[type] = []

        if isinstance(result, tuple) and len(result) == 2:
            first, second = result
            if isinstance(first, PackageInfo) and isinstance(second, list):
                info = first
                block_classes = second
            else:
                message = "returned unexpected tuple format"
                logger.warning("Entry-point '%s' %s", ep_name, message)
                diagnostics.append(
                    EntryPointDiagnostic(
                        group=BLOCKS_ENTRY_POINT_GROUP,
                        entry_point=ep_name,
                        stage=STAGE_REGISTER,
                        message=message,
                    )
                )
                return
        elif isinstance(result, list):
            block_classes = result
        elif isinstance(result, type) and issubclass(result, Block):
            # The FR-029 compatibility affordance: the entry point named a
            # block class directly rather than a factory.
            block_classes = [result]
        else:
            message = f"returned unsupported type: {type(result).__name__}"
            logger.warning("Entry-point '%s' %s", ep_name, message)
            diagnostics.append(
                EntryPointDiagnostic(
                    group=BLOCKS_ENTRY_POINT_GROUP,
                    entry_point=ep_name,
                    stage=STAGE_REGISTER,
                    message=message,
                )
            )
            return

        pkg_name = info.name if info is not None else ep_name
        if info is not None:
            registry._packages[info.name] = info

        for cls in block_classes:
            if isinstance(cls, type) and issubclass(cls, Block) and not inspect.isabstract(cls):
                block_spec = _spec_from_class(cls, source="entry_point")
                block_spec.module_path = cls.__module__
                block_spec.class_name = cls.__name__
                block_spec.package_name = pkg_name
                _register_spec(registry, block_spec)
            elif isinstance(cls, type) and issubclass(cls, Block) and inspect.isabstract(cls):
                message = f"contained abstract Block subclass: {cls}"
                logger.warning("Entry-point '%s' %s", ep_name, message)
                diagnostics.append(
                    EntryPointDiagnostic(
                        group=BLOCKS_ENTRY_POINT_GROUP,
                        entry_point=ep_name,
                        stage=STAGE_REGISTER,
                        message=message,
                    )
                )
            else:
                message = f"contained non-Block item: {cls}"
                logger.warning("Entry-point '%s' %s", ep_name, message)
                diagnostics.append(
                    EntryPointDiagnostic(
                        group=BLOCKS_ENTRY_POINT_GROUP,
                        entry_point=ep_name,
                        stage=STAGE_REGISTER,
                        message=message,
                    )
                )
    except Exception as exc:
        logger.warning("Failed to process entry_point '%s'", ep_name, exc_info=True)
        diagnostics.append(
            EntryPointDiagnostic(
                group=BLOCKS_ENTRY_POINT_GROUP,
                entry_point=ep_name,
                stage=STAGE_REGISTER,
                message=f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__,
            )
        )


def _record_entry_point_diagnostics(
    registry: BlockRegistry,
    diagnostics: list[EntryPointDiagnostic],
) -> None:
    """Publish this scan's entry-point diagnostics on the registry.

    Replaces the previous pass's list rather than appending to it, so the
    surface always describes the most recent scan the way
    :meth:`BlockRegistry.dropin_failures` does.
    """
    # Development references: FR-028.
    registry._entry_point_diagnostics = [str(diagnostic) for diagnostic in diagnostics]


def _desktop_resource_package_dirs() -> list[Path]:
    """Return package directories implied by desktop/resource environment."""
    return candidate_package_dirs()


def _process_package_protocol_result(
    registry: BlockRegistry,
    *,
    module_name: str,
    result: Any,
    source: str,
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
        # #1772: the worker running this block resolves the package's own
        # roots and the shared user dependency site from the module name
        # (:func:`scistudio.desktop.paths.installed_import_roots_for_module`),
        # so the spec carries no import roots.
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
    """Import one ``scistudio_blocks_*`` package and register its block classes.

    The ``sys.path`` window here serves installed-package loading, not user
    code (ADR-056 keeps plugin roots with :mod:`scistudio.desktop.paths`), and
    so does the eviction of the package's previously imported modules.
    """
    try:
        with prepended_sys_paths(import_roots):
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
            )
    except Exception:
        logger.warning("Failed to import source plugin package '%s' from %s", module_name, import_roots, exc_info=True)


def _scan_package_src_dirs(registry: BlockRegistry) -> None:
    """Tier 3: scan hard-installed ``packages/*/src`` source packages.

    This desktop package path imports already-present ``scistudio_blocks_*``
    source packages through the existing package protocol so
    capability validation remains the registry's single source of truth.
    """
    # Development references: ADR-025, ADR-043.
    package_dirs = [*registry._package_src_dirs, *_desktop_resource_package_dirs()]
    for _root_name, module_name, import_roots in iter_source_package_module_candidates(package_dirs):
        _scan_source_package_module(
            registry,
            import_roots=import_roots,
            module_name=module_name,
            source="package_src",
        )
