from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

import pytest

from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scistudio.blocks.io.loaders.load_data import LoadData
from scistudio.blocks.io.savers.save_data import SaveData
from scistudio.blocks.registry import BlockRegistry, BlockSpec, _spec_from_class
from scistudio.core.types.base import DataObject
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.text import Text
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition
from scistudio.workflow.validator import validate_workflow


def _core_io_registry() -> BlockRegistry:
    registry = BlockRegistry()
    registry._register_spec(_spec_from_class(LoadData, source="contract"))
    registry._register_spec(_spec_from_class(SaveData, source="contract"))
    return registry


def _registered_capabilities() -> list[FormatCapability]:
    return [capability for spec in _core_io_registry().all_specs().values() for capability in spec.format_capabilities]


def _capability_key(capability: FormatCapability) -> tuple[str, type[DataObject], str]:
    return (capability.direction, capability.data_type, capability.format_id)


def _direction_index(
    capabilities: Iterable[FormatCapability],
) -> dict[str | None, dict[str, list[FormatCapability]]]:
    groups: dict[str | None, dict[str, list[FormatCapability]]] = defaultdict(lambda: defaultdict(list))
    for capability in capabilities:
        groups[capability.roundtrip_group][capability.direction].append(capability)
    return groups


def test_registered_io_capabilities_expose_stable_replay_fields() -> None:
    capabilities = _registered_capabilities()

    assert capabilities
    for capability in capabilities:
        assert isinstance(capability.id, str) and capability.id.strip() == capability.id
        assert capability.id.count(".") >= 2
        assert capability.direction in {"load", "save"}
        assert isinstance(capability.data_type, type)
        assert issubclass(capability.data_type, DataObject)
        assert isinstance(capability.format_id, str) and capability.format_id == capability.format_id.lower()
        assert capability.extensions
        assert all(extension.startswith(".") for extension in capability.extensions)
        assert all(extension == extension.lower() for extension in capability.extensions)
        assert len(capability.extensions) == len(set(capability.extensions))
        assert isinstance(capability.label, str) and capability.label.strip() == capability.label
        assert capability.block_type in {"LoadData", "SaveData"}
        assert isinstance(capability.handler, str) and capability.handler.strip() == capability.handler
        assert isinstance(capability.is_default, bool)
        assert isinstance(capability.priority, int)
        assert isinstance(capability.roundtrip_group, str) and capability.roundtrip_group
        assert isinstance(capability.metadata_fidelity, MetadataFidelity)


def test_capability_ids_are_unique_and_defaults_do_not_overlap() -> None:
    capabilities = _registered_capabilities()
    ids = [capability.id for capability in capabilities]
    duplicate_ids = [identifier for identifier, count in Counter(ids).items() if count > 1]

    assert duplicate_ids == []

    defaults_by_type_format = [_capability_key(capability) for capability in capabilities if capability.is_default]
    duplicate_type_format_defaults = [key for key, count in Counter(defaults_by_type_format).items() if count > 1]
    assert duplicate_type_format_defaults == []

    defaults_by_extension: list[tuple[str, type[DataObject], str]] = []
    for capability in capabilities:
        if not capability.is_default:
            continue
        defaults_by_extension.extend(
            (capability.direction, capability.data_type, extension) for extension in capability.extensions
        )
    duplicate_extension_defaults = [key for key, count in Counter(defaults_by_extension).items() if count > 1]
    assert duplicate_extension_defaults == []


def test_paired_roundtrip_groups_have_compatible_load_and_save_contracts() -> None:
    grouped = _direction_index(_registered_capabilities())

    for group, by_direction in grouped.items():
        loads = by_direction.get("load", [])
        saves = by_direction.get("save", [])
        if not loads or not saves:
            continue
        for load_capability in loads:
            for save_capability in saves:
                assert load_capability.data_type is save_capability.data_type, group
                assert load_capability.format_id == save_capability.format_id, group
                assert set(load_capability.extensions) & set(save_capability.extensions), group


@pytest.mark.parametrize(
    "roundtrip_group",
    [
        pytest.param(
            "core.series.json",
            marks=pytest.mark.xfail(
                reason="#1454: current core IO declarations have save-only Series JSON roundtrip drift",
                strict=False,
            ),
        ),
        pytest.param(
            "core.text.json",
            marks=pytest.mark.xfail(
                reason="#1454: current core IO declarations have save-only Text JSON roundtrip drift",
                strict=False,
            ),
        ),
    ],
)
def test_roundtrip_group_claims_have_registered_load_and_save_sides(roundtrip_group: str) -> None:
    grouped = _direction_index(_registered_capabilities())
    directions = set(grouped[roundtrip_group])

    assert directions == {"load", "save"}


def _registry_from_specs(*specs: BlockSpec) -> BlockRegistry:
    registry = BlockRegistry()
    for spec in specs:
        registry._registry[spec.name] = spec
        if spec.type_name:
            registry._aliases[spec.type_name] = spec.name
    return registry


def _workflow_for_edge(
    *,
    source_spec: BlockSpec,
    target_spec: BlockSpec,
) -> WorkflowDefinition:
    return WorkflowDefinition(
        nodes=[
            NodeDef(id="source", block_type=source_spec.name),
            NodeDef(id="target", block_type=target_spec.name),
        ],
        edges=[EdgeDef(source="source:out", target="target:in")],
    )


def test_workflow_validation_rejects_hidden_format_conversion_on_ordinary_edges() -> None:
    producer = BlockSpec(
        name="contract_text_producer",
        base_category="process",
        output_ports=[OutputPort(name="out", accepted_types=[Text])],
    )
    consumer = BlockSpec(
        name="contract_dataframe_consumer",
        base_category="process",
        input_ports=[InputPort(name="in", accepted_types=[DataFrame])],
    )
    registry = _registry_from_specs(producer, consumer)

    errors = validate_workflow(
        _workflow_for_edge(source_spec=producer, target_spec=consumer),
        registry=registry,
    )

    assert any("source:out" in error and "target:in" in error for error in errors)


def test_workflow_validation_accepts_type_compatible_canonical_zone_edges() -> None:
    producer = BlockSpec(
        name="contract_text_canonical_producer",
        base_category="process",
        output_ports=[OutputPort(name="out", accepted_types=[Text])],
    )
    consumer = BlockSpec(
        name="contract_text_canonical_consumer",
        base_category="process",
        input_ports=[InputPort(name="in", accepted_types=[Text])],
    )
    registry = _registry_from_specs(producer, consumer)

    errors = validate_workflow(
        _workflow_for_edge(source_spec=producer, target_spec=consumer),
        registry=registry,
    )

    assert [error for error in errors if "source:out" in error and "target:in" in error] == []


def _boundary_registry() -> BlockRegistry:
    text_loader = FormatCapability(
        id="tests.contract.text.same.load",
        direction="load",
        data_type=Text,
        format_id="same",
        extensions=("same",),
        label="Same Text",
        block_type="ContractTextLoader",
        handler="_load_same",
    )
    dataframe_loader = FormatCapability(
        id="tests.contract.dataframe.same.load",
        direction="load",
        data_type=DataFrame,
        format_id="same",
        extensions=(".same",),
        label="Same DataFrame",
        block_type="ContractDataFrameLoader",
        handler="_load_same",
    )
    registry = _registry_from_specs(
        BlockSpec(
            name="contract_app_boundary",
            base_category="app",
            variadic_outputs=True,
        ),
        BlockSpec(name="contract_text_loader", format_capabilities=[text_loader]),
        BlockSpec(name="contract_dataframe_loader", format_capabilities=[dataframe_loader]),
    )
    return registry


def _boundary_workflow(*, capability_id: str) -> WorkflowDefinition:
    return WorkflowDefinition(
        nodes=[
            NodeDef(
                id="boundary",
                block_type="contract_app_boundary",
                config={
                    "params": {
                        "output_ports": [
                            {
                                "name": "out",
                                "types": ["Text"],
                                "extension": "same",
                                "capability_id": capability_id,
                            }
                        ]
                    }
                },
            )
        ],
    )


def test_boundary_validation_uses_capability_id_not_extension_hint_as_contract() -> None:
    errors = validate_workflow(
        _boundary_workflow(capability_id="tests.contract.dataframe.same.load"),
        registry=_boundary_registry(),
    )

    assert any("capability_id='tests.contract.dataframe.same.load'" in error for error in errors)


def test_boundary_validation_accepts_matching_capability_id_with_same_extension_hint() -> None:
    errors = validate_workflow(
        _boundary_workflow(capability_id="tests.contract.text.same.load"),
        registry=_boundary_registry(),
    )

    assert [error for error in errors if "output port 'out'" in error] == []
