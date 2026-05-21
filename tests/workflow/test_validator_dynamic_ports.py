"""Workflow-level validator tests for ADR-028 Addendum 1 dynamic ports.

These tests verify that ``validate_workflow`` exercises the
``Block.get_effective_input_ports`` / ``get_effective_output_ports``
methods on freshly-instantiated block instances when the registry can
construct them, and falls back to spec ports when it cannot.

A dynamic block in a workflow should validate against its config-driven
effective ports, NOT against its static ClassVar declarations.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.blocks.registry import BlockRegistry, BlockSpec, _spec_from_class
from scistudio.core.types.array import Array
from scistudio.core.types.base import DataObject
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition
from scistudio.workflow.validator import validate_workflow

# ---------------------------------------------------------------------------
# Test fixture blocks (module-level so the registry can import them)
# ---------------------------------------------------------------------------


class _DynamicLoaderBlock(ProcessBlock):
    """Dynamic-output loader: ``data`` port type derived from ``core_type`` config.

    Mirrors the planned ``LoadData`` shape from ADR-028 Addendum 1 §C without
    actually loading any data.
    """

    name: ClassVar[str] = "Dynamic Loader"
    type_name: ClassVar[str] = "dynamic_loader"

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[DataObject]),  # placeholder
    ]
    dynamic_ports: ClassVar[dict[str, Any] | None] = {
        "source_config_key": "core_type",
        "output_port_mapping": {
            "data": {
                "Array": ["Array"],
                "DataFrame": ["DataFrame"],
                "Series": ["Series"],
            },
        },
    }

    def get_effective_output_ports(self) -> list[OutputPort]:
        type_name = self.config.get("core_type", "DataFrame")
        cls: type
        if type_name == "Array":
            cls = Array
        elif type_name == "Series":
            cls = Series
        else:
            cls = DataFrame
        return [OutputPort(name="data", accepted_types=[cls])]

    def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
        return item


class _ArrayConsumerBlock(ProcessBlock):
    """Static block that only accepts Array on its ``data`` input port."""

    name: ClassVar[str] = "Array Consumer"
    type_name: ClassVar[str] = "array_consumer"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[Array], required=True),
    ]

    def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
        return item


class _DataFrameConsumerBlock(ProcessBlock):
    """Static block that only accepts DataFrame on its ``data`` input port."""

    name: ClassVar[str] = "DataFrame Consumer"
    type_name: ClassVar[str] = "dataframe_consumer"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[DataFrame], required=True),
    ]

    def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
        return item


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _registry_with(*classes: type) -> BlockRegistry:
    """Build a BlockRegistry from in-process classes that can be instantiated.

    Each class is registered under its display name and ``type_name`` alias
    so the validator's ``registry.instantiate()`` call resolves to the same
    class. ``module_path`` and ``class_name`` are filled so the registry's
    Tier-2 import path succeeds for these test fixtures.
    """
    reg = BlockRegistry()
    for cls in classes:
        spec = _spec_from_class(cls, source="test")
        spec.module_path = cls.__module__
        spec.class_name = cls.__name__
        reg._registry[spec.name] = spec
        if spec.type_name:
            reg._aliases[spec.type_name] = spec.name
    return reg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestValidatorDynamicPortsCompatible:
    """A dynamic block whose config drives a compatible effective output."""

    def test_dynamic_loader_to_array_consumer_compatible_when_core_type_array(self) -> None:
        """Setting ``core_type=Array`` makes the loader compatible with the Array consumer."""
        reg = _registry_with(_DynamicLoaderBlock, _ArrayConsumerBlock)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="L", block_type="dynamic_loader", config={"params": {"core_type": "Array"}}),
                NodeDef(id="C", block_type="array_consumer"),
            ],
            edges=[EdgeDef(source="L:data", target="C:data")],
        )
        errors = validate_workflow(wf, registry=reg)
        # No type-compatibility error because effective ports give Array.
        type_errors = [e for e in errors if "L:data" in e and "C:data" in e]
        assert type_errors == [], errors

    def test_dynamic_loader_to_dataframe_consumer_compatible_when_core_type_dataframe(self) -> None:
        reg = _registry_with(_DynamicLoaderBlock, _DataFrameConsumerBlock)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="L", block_type="dynamic_loader", config={"params": {"core_type": "DataFrame"}}),
                NodeDef(id="C", block_type="dataframe_consumer"),
            ],
            edges=[EdgeDef(source="L:data", target="C:data")],
        )
        errors = validate_workflow(wf, registry=reg)
        type_errors = [e for e in errors if "L:data" in e and "C:data" in e]
        assert type_errors == [], errors


class TestValidatorDynamicPortsIncompatible:
    """A dynamic block whose effective ports are incompatible should error."""

    def test_dynamic_loader_dataframe_to_array_consumer_rejected(self) -> None:
        """Loader configured with DataFrame must NOT be accepted by an Array consumer."""
        reg = _registry_with(_DynamicLoaderBlock, _ArrayConsumerBlock)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="L", block_type="dynamic_loader", config={"params": {"core_type": "DataFrame"}}),
                NodeDef(id="C", block_type="array_consumer"),
            ],
            edges=[EdgeDef(source="L:data", target="C:data")],
        )
        errors = validate_workflow(wf, registry=reg)
        # The validator must report a type incompatibility on this edge.
        type_errors = [e for e in errors if "L:data" in e and "C:data" in e]
        assert len(type_errors) == 1, f"expected 1 type error, got: {errors}"

    def test_dynamic_loader_array_to_dataframe_consumer_rejected(self) -> None:
        """Loader configured with Array must NOT be accepted by a DataFrame consumer."""
        reg = _registry_with(_DynamicLoaderBlock, _DataFrameConsumerBlock)

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="L", block_type="dynamic_loader", config={"params": {"core_type": "Array"}}),
                NodeDef(id="C", block_type="dataframe_consumer"),
            ],
            edges=[EdgeDef(source="L:data", target="C:data")],
        )
        errors = validate_workflow(wf, registry=reg)
        type_errors = [e for e in errors if "L:data" in e and "C:data" in e]
        assert len(type_errors) == 1, f"expected 1 type error, got: {errors}"


class TestValidatorSpecOnlyFallback:
    """Spec-only registry entries (no importable class) still validate via spec ports."""

    def test_spec_only_registry_entry_uses_spec_ports(self) -> None:
        """Tests that inject a bare ``BlockSpec`` (no real module) still pass.

        This guards the explicit fallback path in
        ``_effective_ports_for_node``: when ``registry.instantiate()`` raises,
        the validator must read the spec's static ports instead of crashing.
        """
        reg = BlockRegistry()
        reg._registry["producer"] = BlockSpec(
            name="producer",
            module_path="this.module.does.not.exist",
            class_name="Imaginary",
            output_ports=[OutputPort(name="out", accepted_types=[Array])],
        )
        reg._registry["consumer"] = BlockSpec(
            name="consumer",
            module_path="this.module.does.not.exist",
            class_name="Imaginary",
            input_ports=[InputPort(name="in", accepted_types=[Array], required=True)],
        )

        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="A", block_type="producer"),
                NodeDef(id="B", block_type="consumer"),
            ],
            edges=[EdgeDef(source="A:out", target="B:in")],
        )
        # Should not crash and should not report a type error: the spec-only
        # fallback uses ``spec.input_ports`` / ``spec.output_ports`` directly.
        errors = validate_workflow(wf, registry=reg)
        type_errors = [e for e in errors if "A:out" in e and "B:in" in e]
        assert type_errors == []
