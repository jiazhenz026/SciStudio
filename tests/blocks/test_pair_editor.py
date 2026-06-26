"""Tests for PairEditor interactive variadic block (#594)."""

from __future__ import annotations

import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import InteractiveMixin, InteractivePrompt
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.builtins.pair_editor import PairEditor
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


class StubItem(DataObject):
    """Minimal DataObject stub for testing."""

    def __init__(self, name: str = "item") -> None:
        super().__init__()
        self.name = name


class TestPairEditorMetadata:
    """Test PairEditor class-level metadata and variadic port declarations."""

    def test_name(self) -> None:
        assert PairEditor.name == "Pair Editor"

    def test_subcategory(self) -> None:
        assert PairEditor.subcategory == "routing"

    def test_execution_mode_is_interactive(self) -> None:
        assert PairEditor.execution_mode == ExecutionMode.INTERACTIVE

    def test_variadic_flags(self) -> None:
        assert PairEditor.variadic_inputs is True
        assert PairEditor.variadic_outputs is True

    def test_port_limits(self) -> None:
        assert PairEditor.min_input_ports == 2
        assert PairEditor.max_input_ports == 8

    def test_allowed_types(self) -> None:
        # Empty list = accept all DataObject subtypes (#665).
        assert PairEditor.allowed_input_types == []
        assert PairEditor.allowed_output_types == []


class TestPairEditorPreparePrompt:
    """Test prepare_prompt() generates correct data for the frontend."""

    def test_two_equal_collections(self) -> None:
        block = PairEditor(
            config={
                "input_ports": [
                    {"name": "A", "types": ["DataObject"]},
                    {"name": "B", "types": ["DataObject"]},
                ],
                "output_ports": [
                    {"name": "A", "types": ["DataObject"]},
                    {"name": "B", "types": ["DataObject"]},
                ],
            }
        )
        col_a = Collection([StubItem("a1"), StubItem("a2"), StubItem("a3")], item_type=StubItem)
        col_b = Collection([StubItem("b1"), StubItem("b2"), StubItem("b3")], item_type=StubItem)
        inputs = {"A": col_a, "B": col_b}
        config = BlockConfig()

        prompt = block.prepare_prompt(inputs, config)
        # ADR-051: prepare_prompt now returns an InteractivePrompt whose
        # panel_payload preserves the pre-migration dict shape.
        assert isinstance(prompt, InteractivePrompt)
        result = prompt.panel_payload

        assert set(result["ports"]) == {"A", "B"}
        assert result["collection_length"] == 3
        assert len(result["items_per_port"]["A"]) == 3
        assert len(result["items_per_port"]["B"]) == 3
        assert result["items_per_port"]["A"][0]["name"] == "a1"

    def test_unequal_lengths_raises(self) -> None:
        block = PairEditor(
            config={
                "input_ports": [
                    {"name": "A", "types": ["DataObject"]},
                    {"name": "B", "types": ["DataObject"]},
                ],
                "output_ports": [
                    {"name": "A", "types": ["DataObject"]},
                    {"name": "B", "types": ["DataObject"]},
                ],
            }
        )
        col_a = Collection([StubItem("a1"), StubItem("a2")], item_type=StubItem)
        col_b = Collection([StubItem("b1"), StubItem("b2"), StubItem("b3")], item_type=StubItem)
        inputs = {"A": col_a, "B": col_b}
        config = BlockConfig()

        with pytest.raises(ValueError, match="equal length"):
            block.prepare_prompt(inputs, config)

    def test_three_ports(self) -> None:
        block = PairEditor(
            config={
                "input_ports": [
                    {"name": "X", "types": ["DataObject"]},
                    {"name": "Y", "types": ["DataObject"]},
                    {"name": "Z", "types": ["DataObject"]},
                ],
                "output_ports": [
                    {"name": "X", "types": ["DataObject"]},
                    {"name": "Y", "types": ["DataObject"]},
                    {"name": "Z", "types": ["DataObject"]},
                ],
            }
        )
        items: list[DataObject] = [StubItem(f"i{i}") for i in range(5)]
        inputs = {
            "X": Collection(items, item_type=StubItem),
            "Y": Collection(items, item_type=StubItem),
            "Z": Collection(items, item_type=StubItem),
        }
        config = BlockConfig()

        prompt = block.prepare_prompt(inputs, config)
        # ADR-051: prepare_prompt now returns an InteractivePrompt whose
        # panel_payload preserves the pre-migration dict shape.
        assert isinstance(prompt, InteractivePrompt)
        result = prompt.panel_payload

        assert result["collection_length"] == 5
        assert len(result["ports"]) == 3


class TestPairEditorRun:
    """Test run() reorders items based on user-specified indices."""

    def test_basic_reorder(self) -> None:
        block = PairEditor(
            config={
                "input_ports": [
                    {"name": "A", "types": ["DataObject"]},
                    {"name": "B", "types": ["DataObject"]},
                ],
                "output_ports": [
                    {"name": "A", "types": ["DataObject"]},
                    {"name": "B", "types": ["DataObject"]},
                ],
            }
        )

        col_a = Collection([StubItem("a0"), StubItem("a1"), StubItem("a2")], item_type=StubItem)
        col_b = Collection([StubItem("b0"), StubItem("b1"), StubItem("b2")], item_type=StubItem)
        inputs = {"A": col_a, "B": col_b}

        config = BlockConfig(
            **{
                "interactive_response": {
                    "reorder": {
                        "A": [2, 0, 1],
                        "B": [1, 2, 0],
                    }
                }
            }
        )

        result = block.run(inputs, config)

        assert next(iter(result["A"])).name == "a2"
        assert list(result["A"])[1].name == "a0"
        assert list(result["A"])[2].name == "a1"
        assert next(iter(result["B"])).name == "b1"
        assert list(result["B"])[1].name == "b2"
        assert list(result["B"])[2].name == "b0"

    def test_identity_reorder(self) -> None:
        """Confirming without changes should produce same order."""
        block = PairEditor(
            config={
                "input_ports": [
                    {"name": "A", "types": ["DataObject"]},
                    {"name": "B", "types": ["DataObject"]},
                ],
                "output_ports": [
                    {"name": "A", "types": ["DataObject"]},
                    {"name": "B", "types": ["DataObject"]},
                ],
            }
        )

        items_a: list[DataObject] = [StubItem("x"), StubItem("y")]
        items_b: list[DataObject] = [StubItem("p"), StubItem("q")]
        inputs = {
            "A": Collection(items_a, item_type=StubItem),
            "B": Collection(items_b, item_type=StubItem),
        }

        config = BlockConfig(
            **{
                "interactive_response": {
                    "reorder": {
                        "A": [0, 1],
                        "B": [0, 1],
                    }
                }
            }
        )

        result = block.run(inputs, config)

        assert next(iter(result["A"])).name == "x"
        assert list(result["A"])[1].name == "y"
        assert next(iter(result["B"])).name == "p"
        assert list(result["B"])[1].name == "q"

    def test_no_reorder_raises(self) -> None:
        block = PairEditor(
            config={
                "input_ports": [
                    {"name": "A", "types": ["DataObject"]},
                    {"name": "B", "types": ["DataObject"]},
                ],
                "output_ports": [
                    {"name": "A", "types": ["DataObject"]},
                    {"name": "B", "types": ["DataObject"]},
                ],
            }
        )
        col = Collection([StubItem("item")], item_type=StubItem)

        with pytest.raises(ValueError, match="no reorder"):
            block.run(
                {"A": col, "B": col},
                BlockConfig(**{"interactive_response": {}}),
            )

    def test_mismatched_indices_length_raises(self) -> None:
        block = PairEditor(
            config={
                "input_ports": [
                    {"name": "A", "types": ["DataObject"]},
                    {"name": "B", "types": ["DataObject"]},
                ],
                "output_ports": [
                    {"name": "A", "types": ["DataObject"]},
                    {"name": "B", "types": ["DataObject"]},
                ],
            }
        )
        col = Collection([StubItem("a"), StubItem("b")], item_type=StubItem)

        config = BlockConfig(
            **{
                "interactive_response": {
                    "reorder": {
                        "A": [0],  # Wrong length — should be 2
                        "B": [0, 1],
                    }
                }
            }
        )

        with pytest.raises(ValueError, match="does not match"):
            block.run({"A": col, "B": col}, config)

    def test_port_without_reorder_passes_through(self) -> None:
        """If reorder dict omits a port, that port's Collection passes through."""
        block = PairEditor(
            config={
                "input_ports": [
                    {"name": "A", "types": ["DataObject"]},
                    {"name": "B", "types": ["DataObject"]},
                ],
                "output_ports": [
                    {"name": "A", "types": ["DataObject"]},
                    {"name": "B", "types": ["DataObject"]},
                ],
            }
        )

        items_a: list[DataObject] = [StubItem("a0"), StubItem("a1")]
        items_b: list[DataObject] = [StubItem("b0"), StubItem("b1")]
        inputs = {
            "A": Collection(items_a, item_type=StubItem),
            "B": Collection(items_b, item_type=StubItem),
        }

        config = BlockConfig(
            **{
                "interactive_response": {
                    "reorder": {
                        "A": [1, 0],
                        # "B" omitted — should pass through unchanged.
                    }
                }
            }
        )

        result = block.run(inputs, config)

        assert next(iter(result["A"])).name == "a1"
        assert list(result["A"])[1].name == "a0"
        # B passes through unchanged.
        assert next(iter(result["B"])).name == "b0"
        assert list(result["B"])[1].name == "b1"


class TestPairEditorAdr051Migration:
    """ADR-051: PairEditor carries the interaction capability and a panel manifest."""

    def test_carries_interactive_capability(self) -> None:
        assert issubclass(PairEditor, InteractiveMixin)
        assert PairEditor.execution_mode == ExecutionMode.INTERACTIVE

    def test_declares_panel_manifest(self) -> None:
        manifest = PairEditor().get_panel_manifest()
        assert manifest is not None
        assert manifest.panel_id == "core.interactive.pair_editor"
