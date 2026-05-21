"""Tests for {package_name} blocks."""

from __future__ import annotations

from {module_name} import get_blocks
from {module_name}.blocks import ExampleBlock
from scieasy.blocks.base.package_info import PackageInfo


class TestEntryPoint:
    """Verify the entry-point callable follows the block package protocol."""

    def test_get_blocks_returns_tuple(self) -> None:
        result = get_blocks()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_get_blocks_first_element_is_package_info(self) -> None:
        info, _blocks = get_blocks()
        assert isinstance(info, PackageInfo)
        assert info.name == "{display_name}"

    def test_get_blocks_second_element_is_list(self) -> None:
        _info, blocks = get_blocks()
        assert isinstance(blocks, list)
        assert len(blocks) > 0

    def test_get_blocks_contains_block_classes(self) -> None:
        _info, blocks = get_blocks()
        for cls in blocks:
            assert isinstance(cls, type)
            assert hasattr(cls, "run")
            assert hasattr(cls, "input_ports")
            assert hasattr(cls, "output_ports")


class TestExampleBlock:
    """Verify ExampleBlock follows the block contract."""

    def test_has_name(self) -> None:
        assert ExampleBlock.name

    def test_has_input_ports(self) -> None:
        assert len(ExampleBlock.input_ports) > 0

    def test_has_output_ports(self) -> None:
        assert len(ExampleBlock.output_ports) > 0

    def test_instantiates(self) -> None:
        block = ExampleBlock()
        assert block is not None
