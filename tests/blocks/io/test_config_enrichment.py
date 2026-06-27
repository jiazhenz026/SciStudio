"""Tests for the shared core-IO config-schema enrichment (bug #7).

Pins that ``load_data`` / ``save_data`` advertise a ``core_type`` enum derived
from the live capability + type registries (so package-registered types such as
``Spectrum`` appear), and that the same helper now backs both the HTTP block API
and the MCP ``get_block_schema`` / ``list_blocks`` tools — removing the static
vs. dynamic contract inconsistency the AI agent hit.
"""

from __future__ import annotations

from typing import Any

from scistudio.blocks.io._config_enrichment import enrich_io_config_schema, io_capable_type_names


def _fake_type(name: str) -> type:
    return type(name, (), {})


class _FakeCapability:
    def __init__(self, type_name: str) -> None:
        self.data_type = _fake_type(type_name)


class _FakeRegistry:
    def __init__(self, *, load: list[str], save: list[str]) -> None:
        self._caps = {
            "load": [_FakeCapability(n) for n in load],
            "save": [_FakeCapability(n) for n in save],
        }

    def list_format_capabilities(self, *, direction: str) -> list[_FakeCapability]:
        return self._caps[direction]


class _FakeTypeRegistry:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    def all_types(self) -> dict[str, Any]:
        return {n: object() for n in self._names}


class _FakeSpec:
    def __init__(self, type_name: str, config_schema: dict[str, Any]) -> None:
        self.type_name = type_name
        self.config_schema = config_schema


_CORE = ["Array", "DataFrame", "Series", "Text", "Artifact", "CompositeData"]


def _load_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"core_type": {"type": "string", "enum": list(_CORE), "default": "DataFrame"}},
        "required": ["core_type"],
    }


def test_io_capable_type_names_orders_core_then_package() -> None:
    registry = _FakeRegistry(load=["Spectrum", "Series"], save=[])
    type_registry = _FakeTypeRegistry([*_CORE, "Spectrum"])
    names = io_capable_type_names(registry, type_registry, direction="load")
    assert names[: len(_CORE)] == _CORE  # core types keep canonical order first
    assert "Spectrum" in names  # package type with a load capability is included


def test_enrich_load_data_adds_package_type_to_core_type_enum() -> None:
    spec = _FakeSpec("load_data", _load_schema())
    registry = _FakeRegistry(load=["Spectrum"], save=[])
    type_registry = _FakeTypeRegistry([*_CORE, "Spectrum"])

    enriched = enrich_io_config_schema(spec, registry, type_registry)
    enum = enriched["properties"]["core_type"]["enum"]

    assert "Spectrum" in enum
    assert set(_CORE).issubset(set(enum))
    # The static spec schema is not mutated (deep-copied).
    assert "Spectrum" not in spec.config_schema["properties"]["core_type"]["enum"]


def test_enrich_is_noop_without_registries() -> None:
    spec = _FakeSpec("load_data", _load_schema())
    assert enrich_io_config_schema(spec, None, None) == spec.config_schema


def test_enrich_is_noop_for_non_core_io_block() -> None:
    schema = {"type": "object", "properties": {"core_type": {"enum": list(_CORE)}}}
    spec = _FakeSpec("spectroscopy.load_spectrum", schema)
    registry = _FakeRegistry(load=["Spectrum"], save=[])
    type_registry = _FakeTypeRegistry([*_CORE, "Spectrum"])
    # Package IO blocks carry their own schema; enrichment must not touch them.
    assert enrich_io_config_schema(spec, registry, type_registry) == schema
