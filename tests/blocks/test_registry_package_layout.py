"""Structural tests for the ``scistudio.blocks.registry`` sub-package.

These tests guard the Path D refactor from issue #1471 (Phase 3 D2 of
backend god-file refactor umbrella #1427):

1. ADR-047 §C9 ("private functions, not helper classes") — no helper
   class may be introduced into the new ``_scan.py`` / ``_capability.py``
   / ``_spec.py`` sibling modules. The :class:`BlockRegistry` class, the
   :class:`BlockSpec` dataclass, and the five capability error classes
   live exclusively in ``__init__.py``.

2. Public import surface — :class:`BlockRegistry`, :class:`BlockSpec`,
   :class:`BlockRegistrationError`, :class:`CapabilityRegistrationError`,
   :class:`CapabilityLookupError`, :class:`MissingCapabilityError`, and
   :class:`AmbiguousCapabilityError` must continue to be importable from
   ``scistudio.blocks.registry``.

3. Legacy IO finder API removal — :meth:`BlockRegistry.find_loader`,
   :meth:`find_saver`, :meth:`find_io_blocks_for_type` and the
   underlying helpers (``_find_io_block``, ``_class_accepts_dtype``,
   ``_best_specificity``, ``_matching_capabilities_for_legacy_io``,
   ``_resolve_legacy_capability_class``) MUST be absent. The
   capability-aware :meth:`find_loader_capability` /
   :meth:`find_saver_capability` /
   :meth:`list_format_capabilities` surface is the canonical lookup
   API per ADR-043 / ADR-047.

The tests intentionally do not import private symbols from sibling
modules so the package-private contract stays honest.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from scistudio.blocks.registry import (
    AmbiguousCapabilityError,
    BlockRegistrationError,
    BlockRegistry,
    BlockSpec,
    CapabilityLookupError,
    CapabilityRegistrationError,
    MissingCapabilityError,
)

# ---------------------------------------------------------------------------
# 1. ADR-047 §C9 compliance: sibling modules host only module-level helpers
# ---------------------------------------------------------------------------


_SIBLING_MODULES = (
    "scistudio.blocks.registry._scan",
    "scistudio.blocks.registry._capability",
    "scistudio.blocks.registry._spec",
)


def _module_class_names(module_name: str) -> list[str]:
    """Return the names of every top-level ``class ...:`` in *module_name*."""
    module = importlib.import_module(module_name)
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=module.__file__)
    return [node.name for node in tree.body if isinstance(node, ast.ClassDef)]


@pytest.mark.parametrize("module_name", _SIBLING_MODULES)
def test_sibling_modules_define_no_classes(module_name: str) -> None:
    """ADR-047 §C9 — sibling helper modules hold private functions only."""
    assert _module_class_names(module_name) == [], (
        f"{module_name} introduces helper classes; ADR-047 §C9 forbids "
        "this. Refactor the helper back into module-level private functions."
    )


def test_registry_init_defines_exactly_the_public_classes() -> None:
    """``__init__.py`` owns ``BlockRegistry`` + ``BlockSpec`` + 5 error classes."""
    assert sorted(_module_class_names("scistudio.blocks.registry")) == sorted(
        [
            "AmbiguousCapabilityError",
            "BlockRegistrationError",
            "BlockRegistry",
            "BlockSpec",
            "CapabilityLookupError",
            "CapabilityRegistrationError",
            "MissingCapabilityError",
        ]
    )


# ---------------------------------------------------------------------------
# 2. Public import surface preservation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "symbol",
    [
        "AmbiguousCapabilityError",
        "BlockRegistrationError",
        "BlockRegistry",
        "BlockSpec",
        "CapabilityLookupError",
        "CapabilityRegistrationError",
        "MissingCapabilityError",
    ],
)
def test_public_classes_importable_from_package_root(symbol: str) -> None:
    """``from scistudio.blocks.registry import <symbol>`` keeps working."""
    module = importlib.import_module("scistudio.blocks.registry")
    assert hasattr(module, symbol), (
        f"scistudio.blocks.registry.{symbol} disappeared; ADR-047 hard "
        "constraint #1 (public import surface preserved) is broken."
    )


@pytest.mark.parametrize(
    "symbol",
    [
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
    ],
)
def test_legacy_private_helper_symbols_still_importable(symbol: str) -> None:
    """Module-level private helpers used by external callers stay importable.

    ``scistudio.workflow.validator`` and the test suite import these
    private symbols directly from ``scistudio.blocks.registry``. The
    Path D split moves them into sibling modules; ``__init__.py``
    re-exports them so existing imports keep working.
    """
    module = importlib.import_module("scistudio.blocks.registry")
    assert hasattr(module, symbol), (
        f"scistudio.blocks.registry.{symbol} disappeared; existing tests "
        "and external callers may break. Re-export it from the appropriate "
        "sibling module."
    )


def test_error_hierarchy_matches_adr_047_section_3() -> None:
    """The five capability error classes inherit per ADR-047 §3 / ADR-043 §3."""
    assert issubclass(CapabilityRegistrationError, BlockRegistrationError)
    assert issubclass(CapabilityLookupError, LookupError)
    assert issubclass(MissingCapabilityError, CapabilityLookupError)
    assert issubclass(AmbiguousCapabilityError, CapabilityLookupError)


# ---------------------------------------------------------------------------
# 3. Legacy IO finder API removal (ADR-047 §4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method_name",
    [
        "find_loader",
        "find_saver",
        "find_io_blocks_for_type",
        "_find_io_block",
        "_class_accepts_dtype",
        "_best_specificity",
        "_matching_capabilities_for_legacy_io",
        "_resolve_legacy_capability_class",
    ],
)
def test_legacy_io_finder_methods_deleted(method_name: str) -> None:
    """ADR-047 §4 — the legacy IO finder API is removed entirely.

    The capability-aware methods (``find_loader_capability`` /
    ``find_saver_capability`` / ``list_format_capabilities``) replace
    these. Re-introducing the legacy surface would defeat the purpose
    of the refactor.
    """
    assert not hasattr(BlockRegistry, method_name), (
        f"ADR-047 §4 forbids BlockRegistry.{method_name} — the legacy "
        "IO finder API was deleted in this refactor. Use the "
        "capability-aware lookup methods instead."
    )


def test_capability_methods_present_after_refactor() -> None:
    """The capability lookup API survives the decomposition."""
    for method_name in (
        "find_loader_capability",
        "find_saver_capability",
        "list_format_capabilities",
    ):
        assert callable(getattr(BlockRegistry, method_name, None)), (
            f"BlockRegistry.{method_name} disappeared; ADR-043 / ADR-047 require the capability-aware lookup surface."
        )


def test_block_spec_remains_a_dataclass() -> None:
    """``BlockSpec`` keeps the dataclass shape (defaults, fields)."""
    spec = BlockSpec(name="example")
    assert spec.name == "example"
    assert spec.version == "0.1.0"
    assert spec.format_capabilities == []


# ---------------------------------------------------------------------------
# ADR-050 canvas-node-readability — BlockSpec field-preservation guard (#1698)
#
# SC-012 / FR-031 / FR-032: the square node + BottomPanel refactor must NOT
# remove any package-facing schema field. This dataclass-level guard fails
# loudly if a future change drops the category, port, dynamic-port, variadic,
# config-schema, or capability fields that the registry carries from package
# block classes into the API. Keeping it at the dataclass field set (not a
# specific block) makes it a structural regression tripwire independent of which
# packages happen to be installed.
# ---------------------------------------------------------------------------


def test_adr050_block_spec_retains_package_facing_fields() -> None:
    """SC-012/FR-031: BlockSpec keeps every package-facing contract field.

    These fields are the source of the BlockSummary / BlockSchemaResponse
    payloads the canvas node, port editor, TypeLegend, and BottomPanel read.
    Dropping any of them would silently break the new node model.
    """
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(BlockSpec)}
    required = {
        # block-kind mark + palette grouping (FR-028)
        "base_category",
        "subcategory",
        # canvas ports + TypeLegend (FR-030)
        "input_ports",
        "output_ports",
        "direction",
        # BottomPanel Config ordering + widget selection (FR-029)
        "config_schema",
        # enum-driven dynamic ports (FR-030)
        "dynamic_ports",
        # variadic + topology controls (FR-030)
        "variadic_inputs",
        "variadic_outputs",
        "allowed_input_types",
        "allowed_output_types",
        "min_input_ports",
        "max_input_ports",
        "min_output_ports",
        "max_output_ports",
        # BottomPanel capability selection (FR-030)
        "format_capabilities",
        # palette source + grouping (FR-027)
        "type_name",
        "package_name",
        "source",
    }
    missing = required - field_names
    assert not missing, f"ADR-050 SC-012: BlockSpec dropped package-facing fields {missing}"


def test_adr050_block_spec_defaults_keep_contract_shapes() -> None:
    """SC-010: a default BlockSpec exposes the contract fields with safe shapes.

    The frontend tolerates "no metadata" only when the fields exist with their
    documented empty shapes (lists, dicts, None). This pins the defaults so a
    refactor cannot quietly change a list field to None or vice versa.
    """
    spec = BlockSpec(name="example")
    assert spec.base_category == ""
    assert spec.subcategory == ""
    assert spec.input_ports == []
    assert spec.output_ports == []
    assert spec.config_schema == {}
    assert spec.dynamic_ports is None
    assert spec.variadic_inputs is False
    assert spec.variadic_outputs is False
    assert spec.allowed_input_types == []
    assert spec.allowed_output_types == []
    assert spec.min_input_ports is None
    assert spec.max_input_ports is None
    assert spec.min_output_ports is None
    assert spec.max_output_ports is None
    assert spec.format_capabilities == []
