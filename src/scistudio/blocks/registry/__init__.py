"""Discover the available block types and look them up at runtime.

A :class:`BlockRegistry` is the catalogue the system consults to find out
which blocks exist and how to build one. The usual flow is: create a
registry, call :meth:`BlockRegistry.scan` once to populate it from every
configured source, then ask it for a block by name with
:meth:`BlockRegistry.get_spec` or :meth:`BlockRegistry.instantiate`.

For each block the registry keeps a small :class:`BlockSpec` descriptor —
where the class lives plus its display metadata, ports, config schema, and
file-format support — instead of the block class itself. Because it stores
only the location, the registry can re-scan edited drop-in files without
disturbing blocks already running in a workflow.

This module also defines the errors raised when registration or a
file-format lookup fails: :class:`BlockRegistrationError`,
:class:`CapabilityRegistrationError`, :class:`CapabilityLookupError`,
:class:`MissingCapabilityError`, and :class:`AmbiguousCapabilityError`.
"""

# Maintainer notes (provenance):
# - Specs store the class *location*, not the class object, for hot-reload
#   safety (ADR-009).
# - The package is split per ADR-047 ("Path D"): ``__init__.py`` holds the
#   public classes; ``_scan.py`` the scan loops + ``_register_spec``;
#   ``_capability.py`` the ADR-043 capability lookups; ``_spec.py``
#   ``_spec_from_class`` + the ADR-030 config-schema merge + ADR-038
#   distribution-version resolution.
# - The pre-ADR-043 legacy IO finders (``find_loader`` / ``find_saver`` /
#   ``find_io_blocks_for_type``) were removed in that refactor; all production
#   callers reach the capability methods first.

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


# Provenance: the registry fails loudly on an unresolvable version per
# ADR-038 §3.3 (every lineage row needs a real block version); the scan loops
# catch this per block so one bad plugin does not drop the whole palette.
class BlockRegistrationError(Exception):
    """Raised when a block class cannot be added to the registry.

    The usual cause is that the registry cannot tell which installed
    distribution a block came from, so it cannot stamp a real version on the
    block. A version is required so that every result the block produces can
    be traced back to an exact build.

    The scan step catches this error for each block on its own and logs it, so
    a single mis-packaged plugin is skipped rather than taking down the whole
    block palette.
    """


class CapabilityRegistrationError(BlockRegistrationError):
    """Raised when a block's declared file-format support cannot be registered.

    A block that loads or saves files declares one or more *format
    capabilities*: which data type, which file extensions, and which handler
    method does the work. This error is raised while scanning when such a
    declaration is malformed or inconsistent — for example a capability whose
    direction or handler does not match the block. The offending block is
    skipped.
    """


class CapabilityLookupError(LookupError):
    """Base error for a failed file-format capability lookup.

    Raised through its subclasses :class:`MissingCapabilityError` and
    :class:`AmbiguousCapabilityError` when asking the registry which block can
    load or save a given data type and file format does not yield a single
    clear answer. The attributes record exactly what was asked and which
    capabilities were considered, so a caller can build a helpful message or
    fall back.

    Args:
        message: Human-readable description of the failure.
        direction: Whether the failed lookup was for loading (``"load"``) or
            saving (``"save"``).
        data_type: The data type the lookup was for.
        extension: The file extension that was queried (e.g. ``".csv"``), or
            ``None``.
        format_id: The named format that was queried, or ``None``.
        capability_id: The exact capability identifier that was queried, or
            ``None``.
        candidates: The capabilities that were considered for the query.
    """

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
        """Whether the lookup was for loading (``"load"``) or saving (``"save"``)."""
        self.data_type = data_type
        """The data type the lookup was for."""
        self.extension = extension
        """The file extension that was queried (e.g. ``".csv"``), or ``None``."""
        self.format_id = format_id
        """The named format that was queried, or ``None``."""
        self.capability_id = capability_id
        """The exact capability identifier that was queried, or ``None``."""
        self.candidates = candidates
        """The capabilities that were considered for this query."""


class MissingCapabilityError(CapabilityLookupError):
    """Raised when no block can load or save the requested data and format.

    Ask the registry, for example, to find a loader for a data type from a
    ``.xyz`` file when nothing has registered support for that combination and
    you get this error. Check that the plugin providing the format is
    installed and that the data type and extension are spelled as expected.
    """


class AmbiguousCapabilityError(CapabilityLookupError):
    """Raised when more than one block could handle the request equally well.

    Several blocks can load or save the same data type and extension and none
    stands out as the obvious choice, so the registry refuses to guess. Narrow
    the request to resolve it — pass an explicit ``format_id`` or
    ``capability_id`` to :meth:`BlockRegistry.find_loader_capability` or
    :meth:`BlockRegistry.find_saver_capability`.
    """


@dataclass
class BlockSpec:
    """A lightweight description of one registered block type.

    The registry keeps a :class:`BlockSpec` for every block it knows about
    instead of importing and holding the block class. It records *where* the
    class lives (module path and class name) plus the display metadata, ports,
    config schema, and file-format support the system and the UI need to show
    the block in the palette and build it on demand. Storing only the location
    lets the registry re-scan edited files without disturbing blocks already
    running in a workflow.

    You normally obtain a :class:`BlockSpec` from
    :meth:`BlockRegistry.get_spec` rather than constructing one yourself.

    Example:
        >>> registry = BlockRegistry()
        >>> registry.scan()
        >>> spec = registry.get_spec("LoadData")  # -> BlockSpec or None
        >>> if spec is not None:
        ...     print(spec.base_category)
        io
    """

    name: str
    """Human-readable display name shown in the block palette."""
    description: str = ""
    """One-line summary of what the block does, shown in the UI."""
    version: str = "0.1.0"
    """Version of the installed distribution the block came from.

    Stamped onto every result the block produces so a run can be traced back
    to an exact build.
    """
    module_path: str = ""
    """Importable module path of the block class (e.g. ``"my_pkg.blocks"``)."""
    class_name: str = ""
    """Name of the block class within :attr:`module_path`."""
    file_path: str | None = None
    """Source file of a drop-in block, or ``None`` for installed blocks.

    Set only for blocks discovered as loose ``.py`` files; it lets the
    registry re-import the file when it changes.
    """
    file_mtime: float | None = None
    """Last-modified time of :attr:`file_path`, used to detect edited drop-in files."""
    base_category: str = ""
    """Broad block family.

    One of ``"io"``, ``"process"``, ``"code"``, ``"app"``, ``"ai"``, or
    ``"subworkflow"``.
    """
    subcategory: str = ""
    """Optional finer grouping within :attr:`base_category`, for palette organisation."""
    # Canvas-node display hints copied from the block class at scan time (#1839).
    ui_color: str | None = None
    """Accent colour for this block's node on the canvas.

    ``None`` falls back to the colour for its :attr:`base_category`.
    """
    ui_icon: str | None = None
    """Icon name for this block's node on the canvas.

    ``None`` falls back to the icon for its :attr:`base_category`.
    """
    input_ports: list[Any] = field(default_factory=list)
    """The block's declared input ports (the connections it accepts)."""
    output_ports: list[Any] = field(default_factory=list)
    """The block's declared output ports (the connections it produces)."""
    config_schema: dict[str, Any] = field(default_factory=dict)
    """JSON-schema-style description of the block's configuration fields.

    Drives the settings form shown for the block. Fields inherited from base
    classes are merged in, so this is the full effective schema.
    """
    source: str = ""
    """Where the block was discovered (e.g. ``"builtin"`` or a drop-in source tag)."""
    type_name: str = ""
    """Stable identifier for the block type, used in saved workflow files."""
    package_name: str = ""
    """Plugin package that provided the block, or ``""`` for built-ins and drop-ins."""
    # IO direction copied from the block class at scan time (ADR-028 Addendum 1).
    direction: str = ""
    """For file-IO blocks, ``"input"`` (loads files) or ``"output"`` (saves files).

    Empty for blocks that do not read or write files.
    """
    # Enum-driven dynamic-port descriptor; shape-checked at scan time
    # (ADR-028 Addendum 1).
    dynamic_ports: dict[str, Any] | None = None
    """Describes ports whose set changes with a config choice, or ``None``.

    Used by blocks whose available inputs or outputs depend on a configuration
    value (for example a chosen file format). ``None`` means the ports are
    fixed.
    """
    # Variadic-port flags copied from the block class (ADR-029).
    variadic_inputs: bool = False
    """Whether the user may add an arbitrary number of input ports."""
    variadic_outputs: bool = False
    """Whether the user may add an arbitrary number of output ports."""
    # Allowed type names for the variadic-port editor dropdown (ADR-029 D11).
    allowed_input_types: list[str] = field(default_factory=list)
    """Data-type names a variadic input port may be set to; empty means any type."""
    allowed_output_types: list[str] = field(default_factory=list)
    """Data-type names a variadic output port may be set to; empty means any type."""
    # Optional min/max constraints on variadic port count (ADR-029 Addendum 1).
    min_input_ports: int | None = None
    """Minimum number of input ports allowed, or ``None`` for no minimum."""
    max_input_ports: int | None = None
    """Maximum number of input ports allowed, or ``None`` for no maximum."""
    min_output_ports: int | None = None
    """Minimum number of output ports allowed, or ``None`` for no minimum."""
    max_output_ports: int | None = None
    """Maximum number of output ports allowed, or ``None`` for no maximum."""
    # Cached copy of the class ``supported_extensions`` ClassVar so the registry
    # can dispatch by extension without re-importing the block (ADR-028 §D8 / #1077).
    supported_extensions: dict[str, str] = field(default_factory=dict)
    """File extensions this block handles, mapping each extension to a format label.

    Lets the registry pick a block by file extension without importing it.
    Empty for blocks that do not read or write files.
    """
    # Normalized IO format capability records captured at scan time (ADR-043).
    format_capabilities: list[FormatCapability] = field(default_factory=list)
    """Detailed load/save capabilities this block provides.

    Each entry pairs a data type and file format with the handler that does
    the work; the registry searches these when resolving a loader or saver.
    """
    # Extra import roots a packaged block needs at run time; deliberately not
    # added to the core process's global import path.
    runtime_import_roots: list[str] = field(default_factory=list)
    """Extra import directories a packaged block needs when it runs.

    These are made available to the worker that runs the block instead of
    being added to the main process's import path.
    """
    # Execution mode + interactive panel metadata copied from the block class
    # (ADR-051) so consumers can inspect a block without instantiating it.
    execution_mode: str = "auto"
    """How the block runs.

    ``"auto"`` (runs straight through), ``"interactive"`` (pauses for user
    input mid-run), or ``"external"`` (drives an external application).
    """
    panel_manifest: dict[str, Any] | None = None
    """Description of the interactive-panel UI for an interactive block, or ``None``.

    Present only when :attr:`execution_mode` is ``"interactive"``.
    """
    panel_asset_root: str | None = None
    """Server-side folder an interactive panel's files are served from, or ``None``.

    Used to confine panel asset serving to one directory; it is never sent to
    the browser. ``None`` for built-in panels and non-interactive blocks.
    """


class BlockRegistry:
    """Catalogue of every block type available for building workflows.

    Create one registry, call :meth:`scan` once to discover blocks from every
    source, then look a block up by name with :meth:`get_spec` or build one
    with :meth:`instantiate`. The system uses a registry to turn a saved
    workflow into running blocks; tools and the UI use it to list what is
    available.

    :meth:`scan` discovers blocks from four sources:

    - the blocks built in to SciStudio,
    - loose ``.py`` files in directories you add with :meth:`add_scan_dir`,
    - installed plugin packages that advertise blocks through the
      ``scistudio.blocks`` entry-point group in their ``pyproject.toml``,
    - source-package directories you add with :meth:`add_package_src_dir`.

    Example:
        >>> registry = BlockRegistry()
        >>> registry.scan()
        >>> block = registry.instantiate("LoadData")
    """

    def __init__(self) -> None:
        self._registry: dict[str, BlockSpec] = {}
        self._aliases: dict[str, str] = {}
        self._scan_dirs: list[Path] = []
        self._package_src_dirs: list[Path] = []
        self._packages: dict[str, PackageInfo] = {}

    def add_scan_dir(self, directory: str | Path) -> None:
        """Register a directory of drop-in block files to scan.

        Any ``.py`` file in *directory* that defines a block class is picked up
        the next time :meth:`scan` (or :meth:`hot_reload`) runs. Use this for
        loose, file-based blocks that are not installed as a package.

        Args:
            directory: Path to the folder holding the drop-in block files.
        """
        self._scan_dirs.append(Path(directory))

    def add_package_src_dir(self, directory: str | Path) -> None:
        """Register a directory of block source packages to scan.

        Use this to discover blocks that live in package source trees on disk
        rather than being installed with pip. The next :meth:`scan` imports the
        packages found under *directory* and registers their blocks.

        Args:
            directory: A folder of package sources. It may be a ``packages``
                folder containing ``*/src`` package sources, a single package
                root that has a ``src`` child, or an already-resolved ``src``
                folder.
        """
        self._package_src_dirs.append(Path(directory))

    def scan(self) -> None:
        """Discover all available blocks and populate the registry.

        Runs every discovery source in turn: the built-in blocks, drop-in
        files from directories added with :meth:`add_scan_dir`, installed
        plugin packages advertised through the ``scistudio.blocks``
        entry-point group, and source-package directories added with
        :meth:`add_package_src_dir`. Call this once after creating the
        registry, before looking blocks up.

        A block that cannot be registered (for example a mis-packaged plugin)
        is logged and skipped so the rest of the catalogue still loads.

        Example:
            >>> registry = BlockRegistry()
            >>> registry.scan()
            >>> specs = registry.all_specs()  # name -> BlockSpec
        """
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

    @staticmethod
    def _validate_interactive_capability(cls: type) -> None:
        """Bind InteractiveMixin to ``execution_mode=INTERACTIVE`` at scan time (ADR-051 FR-002)."""
        from scistudio.blocks.registry._capability import _validate_interactive_capability

        _validate_interactive_capability(cls)

    def get_spec(self, identifier: str) -> BlockSpec | None:
        """Look up a block's descriptor by name.

        Accepts either the block's display name (as shown in the palette) or
        its stable type name (as stored in saved workflows).

        Args:
            identifier: The block's display name or type name.

        Returns:
            The matching :class:`BlockSpec`, or ``None`` if no block is
            registered under that name.

        Example:
            >>> registry = BlockRegistry()
            >>> registry.scan()
            >>> spec = registry.get_spec("LoadData")  # -> BlockSpec or None
        """
        if identifier in self._registry:
            return self._registry[identifier]
        alias = self._aliases.get(identifier)
        if alias is None:
            return None
        return self._registry.get(alias)

    def instantiate(self, name: str, config: dict[str, Any] | None = None) -> Any:
        """Build a ready-to-run block instance by name.

        Imports the block class from where its descriptor says it lives and
        constructs it with the given configuration. For drop-in file blocks
        the file is re-imported each time, so edits are picked up without a
        restart.

        Args:
            name: The block's display name or type name (see :meth:`get_spec`).
            config: Configuration values for the block, or ``None`` to use the
                block's defaults.

        Returns:
            A new block instance.

        Raises:
            KeyError: If no block is registered under *name*.
            ImportError: If the block's source file cannot be loaded.

        Example:
            >>> registry = BlockRegistry()
            >>> registry.scan()
            >>> block = registry.instantiate("LoadData", {"path": "data.csv"})
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
        """Re-scan the drop-in block directories and apply any changes.

        Detects edited files by their last-modified time: new drop-in files
        are added, changed ones are re-read, and files that were deleted are
        removed from the registry. Built-in and installed blocks are left
        untouched. Use this to pick up edits to file-based blocks without
        rebuilding the whole catalogue.
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
        """Return metadata for the plugin packages that provided blocks.

        Only packages that supplied their own :class:`PackageInfo` (name,
        description, author, version, update source) appear here; built-in and
        drop-in blocks have no package entry.

        Returns:
            A mapping from package name to its :class:`PackageInfo`.
        """
        return dict(self._packages)

    def specs_by_package(self) -> dict[str, list[BlockSpec]]:
        """Group every registered block by the package that provided it.

        Useful for showing the palette organised by plugin. Built-in and
        drop-in blocks have no package and are collected under the empty-string
        key ``""``.

        Returns:
            A mapping from package name (or ``""``) to the list of that
            package's :class:`BlockSpec` descriptors.
        """
        grouped: dict[str, list[BlockSpec]] = {}
        for spec in self._registry.values():
            grouped.setdefault(spec.package_name, []).append(spec)
        return grouped

    def all_specs(self) -> dict[str, BlockSpec]:
        """Return every registered block keyed by name.

        Returns:
            A copy of the registry: a mapping from block name to its
            :class:`BlockSpec`. Mutating the returned dict does not affect the
            registry.
        """
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
        """List the file-format load/save capabilities matching the filters.

        Each capability says that some block can load or save a particular
        data type in a particular file format. Call with no arguments to list
        them all, or pass filters to narrow the result.

        Args:
            direction: Keep only ``"load"`` or only ``"save"`` capabilities.
            data_type: Keep only capabilities for this data type (and, when
                loading, its subtypes).
            extension: Keep only capabilities that handle this file extension
                (e.g. ``".csv"``). A compound extension like ``".ome.tif"``
                also matches a block that declares only ``".tif"``.
            format_id: Keep only capabilities for this named format.

        Returns:
            The matching capabilities, in registration order.

        Example:
            >>> savers = registry.list_format_capabilities(direction="save")
            >>> [cap.format_id for cap in savers]
            [...]
        """
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
        """Find the single block capability that loads *data_type* from a file.

        Picks one best match for reading the given data type, optionally
        narrowed by file extension, named format, or an exact capability id.
        Unlike :meth:`list_format_capabilities`, this never falls back to
        "whichever was registered first": if the request is not specific enough
        to choose one, it raises rather than guessing.

        Args:
            data_type: The data type you want to load.
            extension: The source file's extension (e.g. ``".csv"``), if known.
            format_id: A named format to require.
            capability_id: An exact capability identifier to require.

        Returns:
            The matching load :class:`FormatCapability`.

        Raises:
            MissingCapabilityError: If no registered capability can load the
                request.
            AmbiguousCapabilityError: If several capabilities match equally and
                none is clearly best.

        Example:
            >>> # MyData is the data type you want to read in.
            >>> cap = registry.find_loader_capability(MyData, ".csv")
            >>> cap.handler  # name of the method that does the loading
            'load_csv'
        """
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
        """Find the single block capability that saves *data_type* to a file.

        The save counterpart of :meth:`find_loader_capability`. Picks one best
        match for writing the given data type, optionally narrowed by file
        extension, named format, or an exact capability id, and raises rather
        than guessing when the request is not specific enough.

        Args:
            data_type: The data type you want to save.
            extension: The target file's extension (e.g. ``".csv"``), if known.
            format_id: A named format to require.
            capability_id: An exact capability identifier to require.

        Returns:
            The matching save :class:`FormatCapability`.

        Raises:
            MissingCapabilityError: If no registered capability can save the
                request.
            AmbiguousCapabilityError: If several capabilities match equally and
                none is clearly best.

        Example:
            >>> # MyData is the data type you want to write out.
            >>> cap = registry.find_saver_capability(MyData, ".csv")
        """
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
