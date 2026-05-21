from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.io.capabilities import FormatCapability
from scistudio.blocks.io.io_block import IOBlock
from scistudio.blocks.registry import BlockRegistry, BlockSpec, _spec_from_class
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.text import Text
from scistudio.workflow.definition import NodeDef, WorkflowDefinition
from scistudio.workflow.validator import validate_workflow


def _capability(
    *,
    capability_id: str,
    direction: str,
    block_type: str,
    handler: str,
) -> FormatCapability:
    return FormatCapability(
        id=capability_id,
        direction=direction,  # type: ignore[arg-type]
        data_type=Text,
        format_id="bound",
        extensions=(".bound",),
        label="Boundary",
        block_type=block_type,
        handler=handler,
    )


class _BoundaryTextLoader(IOBlock):
    name: ClassVar[str] = "_BoundaryTextLoader"
    type_name: ClassVar[str] = "test.boundary_text_loader"
    direction: ClassVar[str] = "input"
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="data", accepted_types=[Text])]
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        _capability(
            capability_id="tests.boundary.text.primary.load",
            direction="load",
            block_type="_BoundaryTextLoader",
            handler="_load_bound",
        ),
    )

    def _load_bound(self, path: object, config: object) -> Text:
        return Text(content="")

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError


class _AltBoundaryTextLoader(_BoundaryTextLoader):
    name: ClassVar[str] = "_AltBoundaryTextLoader"
    type_name: ClassVar[str] = "test.alt_boundary_text_loader"
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        _capability(
            capability_id="tests.boundary.text.alt.load",
            direction="load",
            block_type="_AltBoundaryTextLoader",
            handler="_load_bound",
        ),
    )


class _BoundaryTextSaver(IOBlock):
    name: ClassVar[str] = "_BoundaryTextSaver"
    type_name: ClassVar[str] = "test.boundary_text_saver"
    direction: ClassVar[str] = "output"
    input_ports: ClassVar[list[InputPort]] = [InputPort(name="data", accepted_types=[Text])]
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        _capability(
            capability_id="tests.boundary.text.primary.save",
            direction="save",
            block_type="_BoundaryTextSaver",
            handler="_save_bound",
        ),
    )

    def _save_bound(self, obj: object, path: object, config: object) -> None:
        return None

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError


def _registry(*classes: type) -> BlockRegistry:
    registry = BlockRegistry()
    registry._registry["boundary_app"] = BlockSpec(
        name="boundary_app",
        base_category="app",
        variadic_inputs=True,
        variadic_outputs=True,
    )
    registry._registry["boundary_code"] = BlockSpec(
        name="boundary_code",
        base_category="code",
        variadic_inputs=True,
        variadic_outputs=True,
    )
    for cls in classes:
        registry._register_spec(_spec_from_class(cls, source="test"))
    return registry


def _workflow(block_type: str, *, params: dict[str, Any]) -> WorkflowDefinition:
    return WorkflowDefinition(nodes=[NodeDef(id="B", block_type=block_type, config={"params": params})])


def test_appblock_output_missing_loader_reports_validation_error() -> None:
    registry = _registry(_BoundaryTextSaver)
    workflow = _workflow(
        "boundary_app",
        params={"output_ports": [{"name": "out", "types": ["Text"], "extension": "bound"}]},
    )

    errors = validate_workflow(workflow, registry=registry)

    assert any("output port 'out'" in error and "No IO format capability" in error for error in errors)


def test_appblock_output_ambiguous_loader_requires_capability_id() -> None:
    registry = _registry(_BoundaryTextLoader, _AltBoundaryTextLoader)
    workflow = _workflow(
        "boundary_app",
        params={"output_ports": [{"name": "out", "types": ["Text"], "extension": "bound"}]},
    )

    errors = validate_workflow(workflow, registry=registry)

    assert any("output port 'out'" in error and "Ambiguous IO format capability" in error for error in errors)


def test_appblock_output_explicit_capability_id_validates() -> None:
    registry = _registry(_BoundaryTextLoader, _AltBoundaryTextLoader)
    workflow = _workflow(
        "boundary_app",
        params={
            "output_ports": [
                {
                    "name": "out",
                    "types": ["Text"],
                    "extension": "bound",
                    "capability_id": "tests.boundary.text.alt.load",
                }
            ]
        },
    )

    errors = validate_workflow(workflow, registry=registry)

    assert [error for error in errors if "output port 'out'" in error] == []


def test_appblock_output_validation_uses_first_runtime_selected_type() -> None:
    registry = _registry(_BoundaryTextSaver)
    workflow = _workflow(
        "boundary_app",
        params={"output_ports": [{"name": "out", "types": ["Artifact", "Text"], "extension": "bound"}]},
    )

    errors = validate_workflow(workflow, registry=registry)

    assert [error for error in errors if "output port 'out'" in error] == []


def test_codeblock_input_missing_saver_reports_validation_error() -> None:
    registry = _registry(_BoundaryTextLoader)
    workflow = _workflow(
        "boundary_code",
        params={"input_ports": [{"name": "in", "types": ["Text"], "extension": "bound"}]},
    )

    errors = validate_workflow(workflow, registry=registry)

    assert any("input port 'in'" in error and "No IO format capability" in error for error in errors)


def test_codeblock_input_explicit_saver_capability_validates() -> None:
    registry = _registry(_BoundaryTextSaver)
    workflow = _workflow(
        "boundary_code",
        params={
            "input_ports": [
                {
                    "name": "in",
                    "types": ["Text"],
                    "extension": "bound",
                    "capability_id": "tests.boundary.text.primary.save",
                }
            ]
        },
    )

    errors = validate_workflow(workflow, registry=registry)

    assert [error for error in errors if "input port 'in'" in error] == []
