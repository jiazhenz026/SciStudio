"""Tests for DataRouter interactive variadic block (#591)."""

from __future__ import annotations

import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import InteractiveMixin, InteractivePrompt
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.builtins.data_router import DataRouter
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


class StubItem(DataObject):
    """Minimal DataObject stub for testing."""

    def __init__(self, name: str = "item") -> None:
        super().__init__()
        self.name = name


class _SourceMeta:
    """Stand-in for a typed domain meta exposing ``source_file``."""

    def __init__(self, source_file: str) -> None:
        self.source_file = source_file


class FileItem(DataObject):
    """DataObject stub with a ``source_file`` meta and no ``name`` attribute.

    Mirrors real loaded data, where the routing panel should surface the
    originating filename rather than a generic ``item_N``.
    """

    def __init__(self, source_file: str) -> None:
        super().__init__()
        self._source_meta = _SourceMeta(source_file)

    @property
    def meta(self) -> _SourceMeta:  # type: ignore[override]
        return self._source_meta


class TestDataRouterMetadata:
    """Test DataRouter class-level metadata and variadic port declarations."""

    def test_name(self) -> None:
        assert DataRouter.name == "Data Router"

    def test_subcategory(self) -> None:
        assert DataRouter.subcategory == "routing"

    def test_execution_mode_is_interactive(self) -> None:
        assert DataRouter.execution_mode == ExecutionMode.INTERACTIVE

    def test_variadic_flags(self) -> None:
        assert DataRouter.variadic_inputs is True
        assert DataRouter.variadic_outputs is True

    def test_allowed_types(self) -> None:
        # Empty list = accept all DataObject subtypes (#665).
        assert DataRouter.allowed_input_types == []
        assert DataRouter.allowed_output_types == []

    def test_min_ports(self) -> None:
        assert DataRouter.min_input_ports == 1
        assert DataRouter.min_output_ports == 1


class TestDataRouterPreparePrompt:
    """Test prepare_prompt() generates correct data for the frontend."""

    def test_single_input_port(self) -> None:
        block = DataRouter(
            config={
                "input_ports": [{"name": "images", "types": ["DataObject"]}],
                "output_ports": [{"name": "batch_1", "types": ["DataObject"]}],
            }
        )
        col = Collection([StubItem("im1"), StubItem("im2")], item_type=StubItem)
        inputs = {"images": col}
        config = BlockConfig()

        prompt = block.prepare_prompt(inputs, config)
        # ADR-051: prepare_prompt now returns an InteractivePrompt whose
        # panel_payload preserves the pre-migration dict shape.
        assert isinstance(prompt, InteractivePrompt)
        result = prompt.panel_payload

        assert result["input_ports"] == ["images"]
        assert len(result["items_per_port"]["images"]) == 2
        assert result["items_per_port"]["images"][0]["ref"] == "images:0"
        assert result["items_per_port"]["images"][0]["name"] == "im1"
        assert result["items_per_port"]["images"][1]["ref"] == "images:1"
        assert result["output_ports"] == ["batch_1"]

    def test_multiple_input_ports(self) -> None:
        block = DataRouter(
            config={
                "input_ports": [
                    {"name": "port_a", "types": ["DataObject"]},
                    {"name": "port_b", "types": ["DataObject"]},
                ],
                "output_ports": [
                    {"name": "out_x", "types": ["DataObject"]},
                    {"name": "out_y", "types": ["DataObject"]},
                ],
            }
        )
        col_a = Collection([StubItem("a1")], item_type=StubItem)
        col_b = Collection([StubItem("b1"), StubItem("b2")], item_type=StubItem)
        inputs = {"port_a": col_a, "port_b": col_b}
        config = BlockConfig()

        prompt = block.prepare_prompt(inputs, config)
        # ADR-051: prepare_prompt now returns an InteractivePrompt whose
        # panel_payload preserves the pre-migration dict shape.
        assert isinstance(prompt, InteractivePrompt)
        result = prompt.panel_payload

        assert set(result["input_ports"]) == {"port_a", "port_b"}
        assert len(result["items_per_port"]["port_a"]) == 1
        assert len(result["items_per_port"]["port_b"]) == 2
        assert set(result["output_ports"]) == {"out_x", "out_y"}

    def test_item_name_uses_source_filename(self) -> None:
        """Items surface their source filename, not a generic ``item_N`` label."""
        block = DataRouter(
            config={
                "input_ports": [{"name": "input_1", "types": ["DataObject"]}],
                "output_ports": [{"name": "port_1", "types": ["DataObject"]}],
            }
        )
        col = Collection(
            [FileItem("/data/raw/io-coverage/spectrum_10.txt"), FileItem("/data/raw/img_03.tif")],
            item_type=FileItem,
        )

        prompt = block.prepare_prompt({"input_1": col}, BlockConfig())
        items = prompt.panel_payload["items_per_port"]["input_1"]

        assert [i["name"] for i in items] == ["spectrum_10.txt", "img_03.tif"]
        # ref/index are unaffected by the label change.
        assert items[0]["ref"] == "input_1:0"


class TestDataRouterRun:
    """Test run() routes items based on user assignments."""

    def test_basic_routing(self) -> None:
        block = DataRouter(
            config={
                "input_ports": [{"name": "images", "types": ["DataObject"]}],
                "output_ports": [
                    {"name": "batch_1", "types": ["DataObject"]},
                    {"name": "batch_2", "types": ["DataObject"]},
                ],
            }
        )

        items: list[DataObject] = [StubItem("im1"), StubItem("im2"), StubItem("im3")]
        col = Collection(items, item_type=StubItem)
        inputs = {"images": col}

        config = BlockConfig(
            **{
                "interactive_response": {
                    "assignments": {
                        "batch_1": ["images:0", "images:2"],
                        "batch_2": ["images:1"],
                    }
                }
            }
        )

        result = block.run(inputs, config)

        assert "batch_1" in result
        assert "batch_2" in result
        assert len(result["batch_1"]) == 2
        assert len(result["batch_2"]) == 1
        assert next(iter(result["batch_1"])).name == "im1"
        assert list(result["batch_1"])[1].name == "im3"
        assert next(iter(result["batch_2"])).name == "im2"

    def test_cross_port_routing(self) -> None:
        """Items from different input ports can be routed to the same output."""
        block = DataRouter(
            config={
                "input_ports": [
                    {"name": "a", "types": ["DataObject"]},
                    {"name": "b", "types": ["DataObject"]},
                ],
                "output_ports": [{"name": "merged", "types": ["DataObject"]}],
            }
        )

        col_a = Collection([StubItem("a1")], item_type=StubItem)
        col_b = Collection([StubItem("b1")], item_type=StubItem)
        inputs = {"a": col_a, "b": col_b}

        config = BlockConfig(
            **{
                "interactive_response": {
                    "assignments": {
                        "merged": ["a:0", "b:0"],
                    }
                }
            }
        )

        result = block.run(inputs, config)
        assert len(result["merged"]) == 2

    def test_no_assignments_raises(self) -> None:
        block = DataRouter(
            config={
                "input_ports": [{"name": "input", "types": ["DataObject"]}],
                "output_ports": [{"name": "output", "types": ["DataObject"]}],
            }
        )
        col = Collection([StubItem("item")], item_type=StubItem)

        with pytest.raises(ValueError, match="no assignments"):
            block.run({"input": col}, BlockConfig(**{"interactive_response": {}}))

    def test_unknown_ref_skipped(self) -> None:
        """Unknown item refs are skipped with a warning, not an error."""
        block = DataRouter(
            config={
                "input_ports": [{"name": "input", "types": ["DataObject"]}],
                "output_ports": [{"name": "output", "types": ["DataObject"]}],
            }
        )
        col = Collection([StubItem("item")], item_type=StubItem)

        config = BlockConfig(
            **{
                "interactive_response": {
                    "assignments": {
                        "output": ["input:0", "nonexistent:99"],
                    }
                }
            }
        )

        result = block.run({"input": col}, config)
        # Only the valid ref should be routed.
        assert len(result["output"]) == 1


class TestDataRouterAdr051Migration:
    """ADR-051: DataRouter carries the interaction capability and a panel manifest."""

    def test_carries_interactive_capability(self) -> None:
        assert issubclass(DataRouter, InteractiveMixin)
        assert DataRouter.execution_mode == ExecutionMode.INTERACTIVE

    def test_declares_panel_manifest(self) -> None:
        manifest = DataRouter().get_panel_manifest()
        assert manifest is not None
        assert manifest.panel_id == "core.interactive.data_router"
