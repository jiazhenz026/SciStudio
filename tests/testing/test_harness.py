"""Tests for BlockTestHarness — contract validation and smoke testing.

Covers:
- Valid block passes all contract checks
- Invalid blocks (missing execute, missing ports, abstract, no name)
- Invalid PackageInfo
- Entry-point callable validation (both formats)
- Smoke test execution
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.package_info import PackageInfo
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.core.types.base import DataObject
from scistudio.testing import BlockTestHarness

# ---------------------------------------------------------------------------
# Fixture blocks for testing
# ---------------------------------------------------------------------------


class ValidBlock(Block):
    """A minimal valid block for testing."""

    name: ClassVar[str] = "Valid Test Block"
    description: ClassVar[str] = "A block that passes all contract checks."
    version: ClassVar[str] = "1.0.0"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[DataObject]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[DataObject]),
    ]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {"output": inputs.get("input")}


class BlockMissingPorts(Block):
    """Block with no input/output ports declared (uses base defaults)."""

    name: ClassVar[str] = "No Ports Block"

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {}


class BlockMissingName(Block):
    """Block that does not override the default name."""

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[DataObject]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[DataObject]),
    ]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {"output": inputs.get("input")}


class BlockBadPortTypes(Block):
    """Block with incorrect port type declarations."""

    name: ClassVar[str] = "Bad Ports Block"
    input_ports: ClassVar[list[Any]] = ["not_a_port"]  # type: ignore[assignment]
    output_ports: ClassVar[list[Any]] = [42]  # type: ignore[assignment]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {}


class BlockThatRaises(Block):
    """Block whose run() always raises."""

    name: ClassVar[str] = "Exploding Block"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[DataObject]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[DataObject]),
    ]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        raise RuntimeError("Intentional failure for testing")


class AnotherValidBlock(Block):
    """Second valid block for entry-point list testing."""

    name: ClassVar[str] = "Another Valid Block"
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[DataObject]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="result", accepted_types=[DataObject]),
    ]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {"result": inputs.get("data")}


# ---------------------------------------------------------------------------
# Tests: validate_block
# ---------------------------------------------------------------------------


class TestValidateBlock:
    """Tests for BlockTestHarness.validate_block()."""

    def test_valid_block_passes(self) -> None:
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_block()
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_not_a_block_subclass(self) -> None:
        harness = BlockTestHarness(dict)  # type: ignore[arg-type]
        errors = harness.validate_block()
        assert len(errors) == 1
        assert "not a subclass of Block" in errors[0]

    def test_not_a_class_at_all(self) -> None:
        harness = BlockTestHarness("not_a_class")  # type: ignore[arg-type]
        errors = harness.validate_block()
        assert len(errors) == 1
        assert "not a subclass of Block" in errors[0]

    def test_abstract_block_detected(self) -> None:
        # Block itself is abstract (has abstract run()).
        harness = BlockTestHarness(Block)
        errors = harness.validate_block()
        assert any("abstract" in e.lower() for e in errors)

    def test_missing_name(self) -> None:
        harness = BlockTestHarness(BlockMissingName)
        errors = harness.validate_block()
        assert any("name" in e.lower() for e in errors)

    def test_bad_port_types(self) -> None:
        harness = BlockTestHarness(BlockBadPortTypes)
        errors = harness.validate_block()
        assert any("input_ports" in e for e in errors)
        assert any("output_ports" in e for e in errors)

    def test_empty_ports_are_valid(self) -> None:
        """An empty list of ports is valid (some blocks legitimately have none)."""
        harness = BlockTestHarness(BlockMissingPorts)
        errors = harness.validate_block()
        # Empty lists are fine; only missing name triggers "Unnamed Block" check.
        # BlockMissingPorts has name set, so only port-related errors should be absent.
        port_errors = [e for e in errors if "port" in e.lower()]
        assert port_errors == [], f"Empty port lists should be valid: {port_errors}"


# ---------------------------------------------------------------------------
# Tests: validate_package_info
# ---------------------------------------------------------------------------


class TestValidatePackageInfo:
    """Tests for BlockTestHarness.validate_package_info()."""

    def test_valid_package_info(self) -> None:
        info = PackageInfo(
            name="Test Package",
            description="A test package",
            author="Test Author",
            version="1.0.0",
        )
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_package_info(info)
        assert errors == []

    def test_minimal_package_info(self) -> None:
        """PackageInfo with only required name and defaults is valid."""
        info = PackageInfo(name="Minimal")
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_package_info(info)
        assert errors == []

    def test_not_a_package_info(self) -> None:
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_package_info({"name": "fake"})
        assert len(errors) == 1
        assert "PackageInfo instance" in errors[0]

    def test_empty_name(self) -> None:
        info = PackageInfo(name="")
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_package_info(info)
        assert any("name" in e.lower() for e in errors)

    def test_empty_version(self) -> None:
        info = PackageInfo(name="Test", version="")
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_package_info(info)
        assert any("version" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Tests: validate_entry_point_callable
# ---------------------------------------------------------------------------


class TestValidateEntryPointCallable:
    """Tests for BlockTestHarness.validate_entry_point_callable()."""

    def test_tuple_format_with_package_info(self) -> None:
        info = PackageInfo(name="My Package", author="Author", version="1.0.0")
        result = (info, [ValidBlock, AnotherValidBlock])
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_entry_point_callable(result)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_plain_list_format(self) -> None:
        result = [ValidBlock, AnotherValidBlock]
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_entry_point_callable(result)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_invalid_return_type(self) -> None:
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_entry_point_callable("not_valid")
        assert len(errors) >= 1
        assert "must return" in errors[0]

    def test_tuple_wrong_length(self) -> None:
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_entry_point_callable((1, 2, 3))
        assert any("length" in e for e in errors)

    def test_tuple_wrong_first_element(self) -> None:
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_entry_point_callable(("not_info", [ValidBlock]))
        assert any("PackageInfo" in e for e in errors)

    def test_tuple_wrong_second_element(self) -> None:
        info = PackageInfo(name="Test", version="1.0.0")
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_entry_point_callable((info, "not_a_list"))
        assert any("list" in e.lower() for e in errors)

    def test_empty_block_list(self) -> None:
        info = PackageInfo(name="Empty", version="1.0.0")
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_entry_point_callable((info, []))
        assert any("empty" in e.lower() for e in errors)

    def test_non_class_in_block_list(self) -> None:
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_entry_point_callable(["not_a_class"])
        assert any("not a class" in e.lower() for e in errors)

    def test_non_block_class_in_list(self) -> None:
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_entry_point_callable([dict])
        assert any("not a subclass of Block" in e for e in errors)

    def test_invalid_block_in_list_reports_errors(self) -> None:
        """Entry-point with a valid structure but an invalid block inside."""
        info = PackageInfo(name="Mixed", version="1.0.0")
        harness = BlockTestHarness(ValidBlock)
        errors = harness.validate_entry_point_callable((info, [ValidBlock, BlockMissingName]))
        # BlockMissingName should generate a name error.
        assert any("name" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Tests: smoke_test
# ---------------------------------------------------------------------------


class TestSmokeTest:
    """Tests for BlockTestHarness.smoke_test()."""

    def test_smoke_test_returns_outputs(self, tmp_path: Any) -> None:
        harness = BlockTestHarness(ValidBlock, work_dir=tmp_path)
        sentinel = object()
        result = harness.smoke_test(inputs={"input": sentinel})
        assert result == {"output": sentinel}

    def test_smoke_test_with_params(self, tmp_path: Any) -> None:
        harness = BlockTestHarness(ValidBlock, work_dir=tmp_path)
        result = harness.smoke_test(
            inputs={"input": "data"},
            params={"key": "value"},
        )
        assert "output" in result

    def test_smoke_test_propagates_errors(self, tmp_path: Any) -> None:
        harness = BlockTestHarness(BlockThatRaises, work_dir=tmp_path)
        with pytest.raises(RuntimeError, match="Intentional failure"):
            harness.smoke_test(inputs={"input": "data"})

    def test_smoke_test_rejects_non_block(self, tmp_path: Any) -> None:
        harness = BlockTestHarness(dict, work_dir=tmp_path)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="not a subclass of Block"):
            harness.smoke_test(inputs={})

    def test_smoke_test_no_work_dir(self) -> None:
        """smoke_test works without an explicit work_dir."""
        harness = BlockTestHarness(ValidBlock)
        result = harness.smoke_test(inputs={"input": "hello"})
        assert result == {"output": "hello"}
