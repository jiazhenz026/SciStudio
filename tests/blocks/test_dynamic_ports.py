"""Tests for ADR-028 Addendum 1 dynamic-port hooks on Block ABC.

Covers:

- ``Block.get_effective_input_ports()`` / ``get_effective_output_ports()``
  default to the class-level ClassVar.
- A subclass that overrides ``get_effective_output_ports`` returns the
  per-instance computed ports instead of the ClassVar.
- ``BlockSpec.dynamic_ports`` and ``BlockSpec.direction`` are populated
  from the class via ``_spec_from_class``.
- ``BlockRegistry._validate_dynamic_ports`` raises descriptive errors for
  the documented malformed shapes.
- ``BlockSchemaResponse`` Pydantic model serializes ``dynamic_ports`` and
  ``direction`` correctly.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from scistudio.api.schemas import BlockSchemaResponse
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.blocks.registry import BlockRegistry, _spec_from_class
from scistudio.core.types.array import Array
from scistudio.core.types.base import DataObject
from scistudio.core.types.dataframe import DataFrame

# ---------------------------------------------------------------------------
# Effective-ports defaults and overrides
# ---------------------------------------------------------------------------


class _StaticBlock(ProcessBlock):
    """Static block that does not override the effective-ports hooks."""

    name: ClassVar[str] = "Static Block"
    type_name: ClassVar[str] = "static_block"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="x", accepted_types=[DataObject]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="y", accepted_types=[DataObject]),
    ]

    def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
        return item


class _DynamicOutputBlock(ProcessBlock):
    """Dynamic block whose effective output port type depends on config."""

    name: ClassVar[str] = "Dynamic Output Block"
    type_name: ClassVar[str] = "dynamic_output_block"

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[DataObject]),  # placeholder
    ]
    dynamic_ports: ClassVar[dict[str, Any] | None] = {
        "source_config_key": "core_type",
        "output_port_mapping": {
            "data": {
                "Array": ["Array"],
                "DataFrame": ["DataFrame"],
            },
        },
    }

    def get_effective_output_ports(self) -> list[OutputPort]:
        type_name = self.config.get("core_type", "DataFrame")
        cls: type = Array if type_name == "Array" else DataFrame
        return [OutputPort(name="data", accepted_types=[cls])]

    def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
        return item


class TestEffectivePortsDefaults:
    """Default behavior: effective ports return the class-level ClassVar."""

    def test_get_effective_input_ports_default_returns_classvar(self) -> None:
        block = _StaticBlock()
        ports = block.get_effective_input_ports()
        assert len(ports) == 1
        assert ports[0].name == "x"
        assert ports[0].accepted_types == [DataObject]

    def test_get_effective_output_ports_default_returns_classvar(self) -> None:
        block = _StaticBlock()
        ports = block.get_effective_output_ports()
        assert len(ports) == 1
        assert ports[0].name == "y"
        assert ports[0].accepted_types == [DataObject]

    def test_get_effective_input_ports_returns_a_copy(self) -> None:
        """Mutating the returned list must not affect the ClassVar."""
        block = _StaticBlock()
        ports = block.get_effective_input_ports()
        ports.append(InputPort(name="z", accepted_types=[Array]))
        assert len(_StaticBlock.input_ports) == 1


class TestEffectivePortsOverride:
    """A subclass that overrides ``get_effective_output_ports`` is honored."""

    def test_get_effective_output_ports_override_array(self) -> None:
        block = _DynamicOutputBlock(config={"params": {"core_type": "Array"}})
        ports = block.get_effective_output_ports()
        assert len(ports) == 1
        assert ports[0].name == "data"
        assert ports[0].accepted_types == [Array]

    def test_get_effective_output_ports_override_dataframe(self) -> None:
        block = _DynamicOutputBlock(config={"params": {"core_type": "DataFrame"}})
        ports = block.get_effective_output_ports()
        assert len(ports) == 1
        assert ports[0].accepted_types == [DataFrame]

    def test_classvar_unchanged_after_instance_override(self) -> None:
        """Overriding the method must not mutate the ClassVar declaration."""
        _ = _DynamicOutputBlock(config={"params": {"core_type": "Array"}})
        assert _DynamicOutputBlock.output_ports[0].accepted_types == [DataObject]


# ---------------------------------------------------------------------------
# BlockSpec population
# ---------------------------------------------------------------------------


class TestBlockSpecPopulation:
    """``_spec_from_class`` captures ``direction`` and ``dynamic_ports``."""

    def test_block_spec_dynamic_ports_populated(self) -> None:
        spec = _spec_from_class(_DynamicOutputBlock, source="test")
        assert spec.dynamic_ports is not None
        assert spec.dynamic_ports["source_config_key"] == "core_type"
        assert "data" in spec.dynamic_ports["output_port_mapping"]
        assert spec.dynamic_ports["output_port_mapping"]["data"]["Array"] == ["Array"]

    def test_block_spec_dynamic_ports_none_for_static_block(self) -> None:
        spec = _spec_from_class(_StaticBlock, source="test")
        assert spec.dynamic_ports is None

    def test_block_spec_direction_default_empty_for_non_io(self) -> None:
        spec = _spec_from_class(_StaticBlock, source="test")
        assert spec.direction == ""

    def test_block_spec_direction_populated_from_io_block(self) -> None:
        from scistudio.blocks.io.io_block import IOBlock

        spec = _spec_from_class(IOBlock, source="test")
        assert spec.direction == "input"


# ---------------------------------------------------------------------------
# _validate_dynamic_ports — malformed shape rejection
# ---------------------------------------------------------------------------


class TestValidateDynamicPorts:
    """``BlockRegistry._validate_dynamic_ports`` rejects malformed dicts."""

    def test_none_is_valid(self) -> None:
        class _NoneBlock(ProcessBlock):
            type_name: ClassVar[str] = "none_block"
            dynamic_ports: ClassVar[dict[str, Any] | None] = None

            def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
                return item

        # Should not raise.
        BlockRegistry._validate_dynamic_ports(_NoneBlock)

    def test_well_formed_descriptor_is_valid(self) -> None:
        class _GoodBlock(ProcessBlock):
            type_name: ClassVar[str] = "good_block"
            dynamic_ports: ClassVar[dict[str, Any] | None] = {
                "source_config_key": "mode",
                "output_port_mapping": {
                    "out": {"text": ["Text"], "array": ["Array"]},
                },
            }

            def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
                return item

        BlockRegistry._validate_dynamic_ports(_GoodBlock)

    def test_raises_when_dynamic_ports_not_a_dict(self) -> None:
        class _BadBlock(ProcessBlock):
            type_name: ClassVar[str] = "bad_block_not_dict"
            dynamic_ports: ClassVar[Any] = "not a dict"  # type: ignore[assignment]

            def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
                return item

        with pytest.raises(ValueError, match="must be a dict or None"):
            BlockRegistry._validate_dynamic_ports(_BadBlock)

    def test_raises_when_missing_source_config_key(self) -> None:
        class _BadBlock(ProcessBlock):
            type_name: ClassVar[str] = "bad_block_missing_source"
            dynamic_ports: ClassVar[dict[str, Any] | None] = {
                "output_port_mapping": {},
            }

            def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
                return item

        with pytest.raises(ValueError, match="source_config_key"):
            BlockRegistry._validate_dynamic_ports(_BadBlock)

    def test_raises_when_source_config_key_not_string(self) -> None:
        class _BadBlock(ProcessBlock):
            type_name: ClassVar[str] = "bad_block_source_not_str"
            dynamic_ports: ClassVar[dict[str, Any] | None] = {
                "source_config_key": 42,  # type: ignore[dict-item]
                "output_port_mapping": {},
            }

            def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
                return item

        with pytest.raises(ValueError, match=r"source_config_key.*non-empty string"):
            BlockRegistry._validate_dynamic_ports(_BadBlock)

    def test_raises_when_output_port_mapping_missing(self) -> None:
        class _BadBlock(ProcessBlock):
            type_name: ClassVar[str] = "bad_block_missing_mapping"
            dynamic_ports: ClassVar[dict[str, Any] | None] = {
                "source_config_key": "mode",
            }

            def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
                return item

        with pytest.raises(ValueError, match="output_port_mapping"):
            BlockRegistry._validate_dynamic_ports(_BadBlock)

    def test_raises_when_output_port_mapping_not_a_dict(self) -> None:
        class _BadBlock(ProcessBlock):
            type_name: ClassVar[str] = "bad_block_mapping_not_dict"
            dynamic_ports: ClassVar[dict[str, Any] | None] = {
                "source_config_key": "mode",
                "output_port_mapping": "not a dict",  # type: ignore[dict-item]
            }

            def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
                return item

        with pytest.raises(ValueError, match=r"output_port_mapping.*must be a dict"):
            BlockRegistry._validate_dynamic_ports(_BadBlock)

    def test_raises_when_enum_value_list_is_not_list(self) -> None:
        class _BadBlock(ProcessBlock):
            type_name: ClassVar[str] = "bad_block_enum_not_list"
            dynamic_ports: ClassVar[dict[str, Any] | None] = {
                "source_config_key": "mode",
                "output_port_mapping": {
                    "out": {"text": "Text"},  # should be ["Text"]  # type: ignore[dict-item]
                },
            }

            def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
                return item

        with pytest.raises(ValueError, match="must be a list"):
            BlockRegistry._validate_dynamic_ports(_BadBlock)

    def test_raises_when_type_name_entry_not_string(self) -> None:
        class _BadBlock(ProcessBlock):
            type_name: ClassVar[str] = "bad_block_type_not_str"
            dynamic_ports: ClassVar[dict[str, Any] | None] = {
                "source_config_key": "mode",
                "output_port_mapping": {
                    "out": {"text": [123]},  # type: ignore[list-item]
                },
            }

            def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
                return item

        with pytest.raises(ValueError, match="non-empty strings"):
            BlockRegistry._validate_dynamic_ports(_BadBlock)


# ---------------------------------------------------------------------------
# BlockSchemaResponse Pydantic serialization
# ---------------------------------------------------------------------------


class TestBlockSchemaResponseSerialization:
    """``BlockSchemaResponse`` round-trips ``dynamic_ports`` and ``direction``."""

    def test_serializes_dynamic_ports_and_direction(self) -> None:
        response = BlockSchemaResponse(
            name="Load",
            type_name="load_data",
            base_category="io",
            description="",
            version="0.1.0",
            input_ports=[],
            output_ports=[],
            config_schema={"type": "object", "properties": {}},
            type_hierarchy=[],
            dynamic_ports={
                "source_config_key": "core_type",
                "output_port_mapping": {"data": {"Array": ["Array"]}},
            },
            direction="input",
        )
        dump = response.model_dump()
        assert dump["dynamic_ports"]["source_config_key"] == "core_type"
        assert dump["dynamic_ports"]["output_port_mapping"]["data"]["Array"] == ["Array"]
        assert dump["direction"] == "input"

    def test_defaults_to_none_when_omitted(self) -> None:
        response = BlockSchemaResponse(
            name="Static",
            type_name="static",
            base_category="process",
        )
        assert response.dynamic_ports is None
        assert response.direction is None
        dump = response.model_dump()
        assert dump["dynamic_ports"] is None
        assert dump["direction"] is None


# ---------------------------------------------------------------------------
# Block.validate uses effective ports
# ---------------------------------------------------------------------------


class TestBlockValidateUsesEffectivePorts:
    """``Block.validate`` reads effective ports so dynamic blocks work."""

    def test_validate_uses_effective_input_ports(self) -> None:
        class _DynInBlock(ProcessBlock):
            type_name: ClassVar[str] = "dyn_in_block"

            def get_effective_input_ports(self) -> list[InputPort]:
                return [InputPort(name="dyn_in", accepted_types=[DataObject], required=True)]

            def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
                return item

        block = _DynInBlock()
        # Validation against effective ports should accept the per-instance "dyn_in".
        with pytest.raises(ValueError, match="dyn_in"):
            block.validate(inputs={})  # missing required dyn_in input


# ---------------------------------------------------------------------------
# ADR-050 canvas-node-readability — package BlockSpec contract (issue #1698)
#
# Complements the API-level tests in tests/api/test_blocks.py by asserting the
# registry-level contract: the live BlockRegistry resolves representative
# package blocks (imaging, spectroscopy, LCMS, SRS) into BlockSpec objects that
# still carry every field the square node + BottomPanel consume — base
# category/subcategory, typed ports, dynamic_ports, variadic flags + allowed
# types + min/max limits, format_capabilities, and config_schema. These are the
# upstream source of the API payloads, so a regression here would silently break
# the new node model. No package source is touched.
#
# Spec: docs/specs/adr-050-canvas-node-readability.md FR-027/FR-030/FR-033,
# SC-010/SC-011/SC-012.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _scanned_registry():  # type: ignore[no-untyped-def]
    """A scanned BlockRegistry with the installed package entry points."""
    registry = BlockRegistry()
    registry.scan()
    return registry


def _spec_by_type_name(registry: BlockRegistry, type_name: str):  # type: ignore[no-untyped-def]
    for spec in registry.all_specs().values():
        if spec.type_name == type_name:
            return spec
    raise AssertionError(f"package block {type_name!r} not registered")


class TestAdr050PackageBlockSpecContract:
    """Representative package blocks resolve to fully-populated BlockSpecs."""

    # (type_name, package_name) per domain — one process/analysis block each so
    # typed ports are exercised across imaging, spectroscopy, LCMS, and SRS.
    _PACKAGE_BLOCKS = (
        ("imaging.axis_merge", "scistudio-blocks-imaging"),
        ("spectroscopy.find_peaks", "scistudio-blocks-spectroscopy"),
        ("lcms.pool_size_normalize", "scistudio-blocks-lcms"),
        ("srs.pca", "scistudio-blocks-srs"),
    )

    @pytest.mark.parametrize(("type_name", "package_name"), _PACKAGE_BLOCKS)
    def test_block_spec_preserves_category_port_and_config_contract(
        self,
        _scanned_registry: BlockRegistry,
        type_name: str,
        package_name: str,
    ) -> None:
        """SC-010/SC-011: BlockSpec keeps category, typed ports, and config schema."""
        spec = _spec_by_type_name(_scanned_registry, type_name)

        assert spec.package_name == package_name
        # base_category feeds the square-node block-kind mark; subcategory feeds
        # palette grouping (FR-028).
        assert spec.base_category in {"io", "process", "code", "app", "ai", "subworkflow"}
        assert isinstance(spec.subcategory, str)

        # Typed ports remain on the spec for canvas rendering / TypeLegend.
        all_ports = [*spec.input_ports, *spec.output_ports]
        assert all_ports, f"{type_name} lost all declared ports"
        for port in all_ports:
            assert isinstance(port.name, str) and port.name
            assert port.accepted_types, f"{type_name} port {port.name} lost accepted_types"

        # config_schema stays an object schema so BottomPanel can render Config.
        assert isinstance(spec.config_schema, dict)
        assert isinstance(spec.config_schema.get("properties", {}), dict)

        # Variadic + dynamic-port + format-capability fields are present and the
        # right shape (FR-030).
        assert isinstance(spec.variadic_inputs, bool)
        assert isinstance(spec.variadic_outputs, bool)
        assert spec.dynamic_ports is None or isinstance(spec.dynamic_ports, dict)
        assert isinstance(spec.allowed_input_types, list)
        assert isinstance(spec.allowed_output_types, list)
        assert isinstance(spec.format_capabilities, list)
        for limit in (spec.min_input_ports, spec.max_input_ports, spec.min_output_ports, spec.max_output_ports):
            assert limit is None or isinstance(limit, int)

    def test_variadic_package_block_spec_keeps_variadic_flag(self, _scanned_registry: BlockRegistry) -> None:
        """FR-030/SC-011: a variadic package block keeps variadic_inputs on its spec."""
        spec = _spec_by_type_name(_scanned_registry, "spectroscopy.merge_spectral_dataset")
        assert spec.variadic_inputs is True
        assert isinstance(spec.allowed_input_types, list)

    def test_package_io_block_spec_keeps_format_capabilities(self, _scanned_registry: BlockRegistry) -> None:
        """FR-030/SC-011: package IO loaders keep non-empty format_capabilities."""
        for type_name in ("spectroscopy.load_spectrum", "lcms.load_mzml_files"):
            spec = _spec_by_type_name(_scanned_registry, type_name)
            assert spec.format_capabilities, f"{type_name} lost format_capabilities on its spec"

    def test_package_config_schema_round_trips_through_block_schema_response(
        self,
        _scanned_registry: BlockRegistry,
    ) -> None:
        """SC-010: a package config_schema with ui metadata survives BlockSchemaResponse.

        The API serializes BlockSpec into BlockSchemaResponse; this proves the
        Pydantic model preserves ``ui_priority`` / ``ui_widget`` on package
        config fields rather than dropping them as legacy node UI (FR-029).
        """
        spec = _spec_by_type_name(_scanned_registry, "lcms.pool_size_normalize")
        response = BlockSchemaResponse(
            name=spec.name,
            type_name=spec.type_name,
            base_category=spec.base_category,
            subcategory=spec.subcategory,
            config_schema=spec.config_schema,
            variadic_inputs=spec.variadic_inputs,
            variadic_outputs=spec.variadic_outputs,
            dynamic_ports=spec.dynamic_ports,
        )
        props = response.model_dump()["config_schema"]["properties"]
        assert props, "config properties dropped during BlockSchemaResponse round-trip"
        assert all("ui_priority" in prop for prop in props.values()), (
            "BlockSchemaResponse dropped ui_priority from package config fields"
        )
