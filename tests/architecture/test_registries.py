"""Architecture enforcement: registry contracts.

Validates that:

* ``BlockSpec`` stores descriptors (module path, class name) — not class objects (ADR-009).
* ``TypeSpec`` stores descriptors — not raw ``type`` references (ADR-009).
* ``BlockRegistry`` stores ``BlockSpec`` instances.
* ``TypeRegistry`` stores ``TypeSpec`` instances.
* ``pyproject.toml`` entry-points reference importable modules **and** resolvable classes.
"""

from __future__ import annotations

import importlib
from dataclasses import fields
from pathlib import Path

import pytest

from scistudio.blocks.registry import BlockRegistry, BlockSpec
from scistudio.core.types.registry import TypeRegistry, TypeSpec

# ---------------------------------------------------------------------------
# ADR-009: BlockSpec must NOT hold class references
# ---------------------------------------------------------------------------


def test_block_spec_does_not_store_class_object() -> None:
    """``BlockSpec`` must not have a ``block_class`` field (ADR-009)."""
    field_names = {f.name for f in fields(BlockSpec)}
    assert "block_class" not in field_names, (
        "BlockSpec contains a 'block_class' field — ADR-009 requires storing "
        "module_path + class_name descriptors, not class object references."
    )


def test_block_spec_has_descriptor_fields() -> None:
    """``BlockSpec`` must store module_path and class_name for deferred import."""
    required = {"name", "module_path", "class_name", "base_category", "source"}
    spec = BlockSpec(name="example", module_path="scistudio.blocks.io.io_block", class_name="IOBlock")
    actual = set(vars(spec).keys())
    assert required.issubset(actual), f"BlockSpec is missing fields: {required - actual}"


def test_block_spec_has_reload_metadata() -> None:
    """``BlockSpec`` must carry file_path and file_mtime for hot-reload detection."""
    spec = BlockSpec(name="t", file_path="/some/path.py", file_mtime=1234567890.0)
    assert spec.file_path == "/some/path.py"
    assert spec.file_mtime == 1234567890.0


# ---------------------------------------------------------------------------
# ADR-009: TypeSpec must NOT hold class references
# ---------------------------------------------------------------------------


def test_type_spec_does_not_store_class_object() -> None:
    """``TypeSpec`` must not have a field holding a ``type`` object (ADR-009)."""
    for f in fields(TypeSpec):
        assert f.type != "type", (
            f"TypeSpec field '{f.name}' has type annotation 'type' — ADR-009 "
            "requires storing module_path + class_name, not class references."
        )


def test_type_spec_has_descriptor_fields() -> None:
    """``TypeSpec`` must store module_path and class_name for deferred import."""
    spec = TypeSpec(name="Image", module_path="scistudio.core.types.array", class_name="Image")
    assert spec.module_path == "scistudio.core.types.array"
    assert spec.class_name == "Image"


# ---------------------------------------------------------------------------
# BlockRegistry
# ---------------------------------------------------------------------------


def test_block_registry_internal_storage_type() -> None:
    """``BlockRegistry._registry`` values must be ``BlockSpec`` instances."""
    reg = BlockRegistry()
    assert isinstance(reg._registry, dict)
    spec = BlockSpec(name="test_block", module_path="some.module", class_name="SomeBlock")
    reg._registry["test"] = spec
    assert isinstance(reg._registry["test"], BlockSpec)


# ---------------------------------------------------------------------------
# TypeRegistry
# ---------------------------------------------------------------------------


def test_type_registry_internal_storage_type() -> None:
    """``TypeRegistry._registry`` values must be ``TypeSpec`` instances."""
    reg = TypeRegistry()
    assert isinstance(reg._registry, dict)
    spec = TypeSpec(name="Image", module_path="scistudio.core.types.array", class_name="Image")
    reg._registry["Image"] = spec
    assert isinstance(reg._registry["Image"], TypeSpec)


def test_type_registry_has_required_interface() -> None:
    """``TypeRegistry`` exposes ``register``, ``resolve``, and ``all_types``."""
    reg = TypeRegistry()
    assert callable(getattr(reg, "register", None)), "TypeRegistry missing register()"
    assert callable(getattr(reg, "resolve", None)), "TypeRegistry missing resolve()"
    assert callable(getattr(reg, "all_types", None)), "TypeRegistry missing all_types()"


# ---------------------------------------------------------------------------
# pyproject.toml entry-points → importable modules AND resolvable classes
# ---------------------------------------------------------------------------


def _parse_entry_points() -> list[tuple[str, str, str]]:
    """Parse ``pyproject.toml`` entry-points and return (group, name, ref) triples.

    Each *ref* is a string like ``"scistudio.blocks.io:IOBlock"``.
    """
    try:
        import tomllib
    except ModuleNotFoundError:  # Python < 3.11 fallback
        import tomli as tomllib  # type: ignore[no-redef]

    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    results: list[tuple[str, str, str]] = []
    entry_points: dict[str, dict[str, str]] = data.get("project", {}).get("entry-points", {})
    for group, entries in entry_points.items():
        for ep_name, ep_ref in entries.items():
            results.append((group, ep_name, ep_ref))
    return results


ENTRY_POINTS = _parse_entry_points()


@pytest.mark.parametrize(
    ("group", "ep_name", "ep_ref"),
    ENTRY_POINTS,
    ids=[f"{g}:{n}" for g, n, _ in ENTRY_POINTS],
)
def test_entry_point_resolves_to_class(
    group: str,
    ep_name: str,
    ep_ref: str,
) -> None:
    """Every entry-point must reference an importable module AND an existing class.

    Both the module (before ``:``) and the attribute (after ``:``) must resolve.
    """
    module_path, attr_name = ep_ref.split(":")
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        pytest.fail(f"Entry-point [{group}] {ep_name} = '{ep_ref}': module '{module_path}' is not importable: {exc}")
    assert hasattr(mod, attr_name), (
        f"Entry-point [{group}] {ep_name} = '{ep_ref}': module '{module_path}' has no attribute '{attr_name}'"
    )
