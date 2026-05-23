"""Spec-construction helpers for :class:`BlockRegistry`.

Per ADR-047 §C9: this module hosts only module-level private helpers — it
must contain **zero** ``class`` definitions. The public dataclass
:class:`BlockSpec` and the :class:`BlockRegistry` class live in
``__init__.py``.

Owns:

- ``_spec_from_class`` — turn a Block subclass into a :class:`BlockSpec`
  (ADR-009 / ADR-028 Addendum 1 / ADR-029 / ADR-038 / ADR-043).
- ``_infer_category`` / ``_type_name_for_class`` — base-category resolution.
- ``_merge_config_schema`` — ADR-030 D1/D2 MRO merge with direction-aware
  post-processing.
- ``_resolve_distribution_version`` + ``_packages_distributions_cached`` —
  ADR-038 §3.3 reproducibility version stamping.
- ``_validate_simple_extension_declaration`` /
  ``_validate_class_capability`` / ``_subclass_declares_field`` — ADR-043
  capability sanity checks invoked from
  ``_capability._format_capabilities_from_class``.
"""

from __future__ import annotations

import contextlib
import copy
import importlib.metadata
import logging
from typing import TYPE_CHECKING, Any

from scistudio.blocks.io.capabilities import CapabilityDirection, FormatCapability

if TYPE_CHECKING:
    from scistudio.blocks.registry import BlockSpec

logger = logging.getLogger(__name__)

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
    live under the ``scistudio`` distribution and read
    ``scistudio.__version__``. Plugin blocks read their entry-point
    distribution version (ADR-037 D11). Drop-in ``.py`` files have no
    distribution, so they fall back to the SciStudio version as a uniform
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
    from scistudio.blocks.registry import BlockRegistrationError

    module_name = getattr(cls, "__module__", "") or ""

    def _scistudio_version() -> str | None:
        try:
            from scistudio import __version__ as scistudio_version

            v = str(scistudio_version)
            return v if v else None
        except Exception:
            return None

    # 1. Built-in / in-tree blocks: stamp the running scistudio version.
    if module_name.startswith("scistudio.") or module_name == "scistudio":
        sv = _scistudio_version()
        if sv is not None:
            return sv
    # 2. Tier-1 drop-in modules use a synthetic name (``_scistudio_dropin_...``);
    #    they have no distribution. Use scistudio version as the uniform default.
    if module_name.startswith("_scistudio_dropin_"):
        sv = _scistudio_version()
        if sv is not None:
            return sv
    # 3. In-tree test fixtures (``tests.*``) are not a real distribution but
    #    are part of the repo and exist only when running pytest. Stamp the
    #    scistudio version so the strict raise doesn't fire on test-only
    #    Block subclasses like ``tests.fixtures.noop_block.NoopBlock``.
    if module_name.startswith("tests.") or module_name == "tests":
        sv = _scistudio_version()
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
        # 6. Monorepo / dev-install convention: ``scistudio_blocks_<name>``
        #    Python package → ``scistudio-blocks-<name>`` distribution name
        #    (PEP 503 normalisation). ``packages_distributions`` does not
        #    always populate this mapping for editable installs, so try
        #    the explicit normalised name as a last resort.
        if top_level.startswith("scistudio_blocks_"):
            normalised = top_level.replace("_", "-")
            with contextlib.suppress(importlib.metadata.PackageNotFoundError):
                return str(importlib.metadata.version(normalised))
            # If the plugin distribution truly isn't installed (CI without
            # ``pip install -e .`` on the monorepo packages), stamp the
            # scistudio version so the per-block registration still succeeds.
            # This is identical to the in-tree fallback in §1: the plugin
            # is part of the same repo checkout.
            sv = _scistudio_version()
            if sv is not None:
                return sv

    # 5. ADR §3.3 forbids the historical "unknown" default. Fail loudly —
    # the scan-loop catch logs and continues so a single mis-packaged
    # block does not kill the palette.
    raise BlockRegistrationError(
        f"ADR-038 §3.3: cannot resolve distribution version for {cls!r} "
        f"(module={module_name!r}); register a setuptools/poetry distribution "
        f"or place the block under ``scistudio.*`` so ``scistudio.__version__`` "
        f"can be stamped."
    )


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
    from scistudio.blocks.app.app_block import AppBlock

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


def _validate_simple_extension_declaration(cls: type) -> None:
    from scistudio.blocks.registry import CapabilityRegistrationError

    if not hasattr(cls, "extensions"):
        return
    extensions = cls.extensions
    if isinstance(extensions, str):
        raise CapabilityRegistrationError(
            f"{cls.__name__}.extensions must be an iterable of extension strings, not a scalar string."
        )


def _validate_class_capability(cls: type, capability: FormatCapability) -> None:
    from scistudio.blocks.registry import CapabilityRegistrationError
    from scistudio.blocks.registry._capability import _validate_capability_id

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


def _infer_category(cls: type) -> str:
    """Infer the base block category from the class hierarchy.

    Always returns one of the 6 base types (io, process, code, app, ai,
    subworkflow) based on isinstance checks.  Never reads a ClassVar
    override — subcategory is a separate field.  See issue #588.
    """
    # Lazy imports to avoid circular dependencies.
    from scistudio.blocks.ai.ai_block import AIBlock
    from scistudio.blocks.app.app_block import AppBlock
    from scistudio.blocks.code.code_block import CodeBlock
    from scistudio.blocks.io.io_block import IOBlock
    from scistudio.blocks.process.process_block import ProcessBlock
    from scistudio.blocks.subworkflow.subworkflow_block import SubWorkflowBlock

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
    from scistudio.blocks.registry import BlockRegistry, BlockSpec
    from scistudio.blocks.registry._capability import _format_capabilities_from_class

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
        # :meth:`BlockRegistry.find_loader_capability` / :meth:`find_saver_capability`.
        # Default to an empty dict for non-IOBlock classes (or IOBlocks that have
        # not yet declared the ClassVar — see #1074-#1076).
        supported_extensions=dict(getattr(cls, "supported_extensions", {}) or {}),
        # ADR-043: capture normalized IO format capabilities at scan time so
        # lookup does not need to re-import block classes for ordinary queries.
        format_capabilities=_format_capabilities_from_class(cls),
    )
