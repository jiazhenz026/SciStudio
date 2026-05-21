"""Tests for Block.config_schema ClassVar and registry propagation."""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.registry import _spec_from_class
from scistudio.core.types.collection import Collection


class TestBlockConfigSchema:
    """Tests for config_schema on Block base and subclasses."""

    def test_base_block_has_default_empty_schema(self) -> None:
        assert Block.config_schema == {"type": "object", "properties": {}}

    def test_io_block_schema_contains_path(self) -> None:
        # T-TRK-004 / ADR-028 §D1: the new IOBlock config_schema is
        # intentionally minimal — only ``path`` survives. The legacy
        # ``direction`` and ``format`` properties were removed when the
        # adapter dispatch layer was deleted. ``direction`` is now a
        # ClassVar on subclasses (``input`` / ``output``), not user
        # config.
        from scistudio.blocks.io.io_block import IOBlock

        schema = IOBlock.config_schema
        assert schema["type"] == "object"
        assert "path" in schema["properties"]
        assert "path" in schema.get("required", [])

    def test_code_block_schema_contains_language(self) -> None:
        from scistudio.blocks.code.code_block import CodeBlock

        schema = CodeBlock.config_schema
        assert "language" in schema["properties"]
        assert "python" in schema["properties"]["language"]["enum"]

    def test_spec_from_class_includes_config_schema(self) -> None:
        class MyBlock(Block):
            name: ClassVar[str] = "Test Block"
            config_schema: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {"threshold": {"type": "number"}},
            }

            def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
                return {}

        spec = _spec_from_class(MyBlock, source="test")
        assert spec.config_schema["properties"]["threshold"]["type"] == "number"

    def test_appblock_schema_executable_path_and_output_dir(self) -> None:
        """Issue #571: AppBlock config_schema has Executable Path (file_browser, priority 0)
        and Save Outputs At (directory_browser, priority 1)."""
        from scistudio.blocks.app.app_block import AppBlock

        schema = AppBlock.config_schema
        props = schema["properties"]
        # app_command renamed to "Executable Path" with file_browser
        assert props["app_command"]["title"] == "Executable Path"
        assert props["app_command"]["ui_widget"] == "file_browser"
        assert props["app_command"]["ui_priority"] == 0
        # output_dir is "Save Outputs At" with directory_browser, priority 1
        assert props["output_dir"]["title"] == "Save Outputs At"
        assert props["output_dir"]["ui_widget"] == "directory_browser"
        assert props["output_dir"]["ui_priority"] == 1

    def test_spec_from_class_default_when_no_schema(self) -> None:
        class PlainBlock(Block):
            name: ClassVar[str] = "Plain"

            def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
                return {}

        spec = _spec_from_class(PlainBlock, source="test")
        # ADR-030: _merge_config_schema always produces a ``required`` key.
        assert spec.config_schema == {"type": "object", "properties": {}, "required": []}


class TestVariadicPortEditorSchemaInjection:
    """ADR-029 D12: port editor config_schema fields injected into AIBlock,
    CodeBlock, AppBlock and propagated to leaf subclasses via MRO merge."""

    def _assert_port_editor_fields(self, props: dict) -> None:
        """Assert input_ports and output_ports port-editor fields are present."""
        assert "input_ports" in props, "input_ports port editor field missing"
        assert "output_ports" in props, "output_ports port editor field missing"
        assert props["input_ports"]["type"] == "array"
        assert props["input_ports"]["ui_widget"] == "port_editor"
        assert props["output_ports"]["type"] == "array"
        assert props["output_ports"]["ui_widget"] == "port_editor"

    def test_aiblock_own_schema_has_port_editor_fields(self) -> None:
        from scistudio.blocks.ai.ai_block import AIBlock

        props = AIBlock.config_schema["properties"]
        self._assert_port_editor_fields(props)

    def test_codeblock_own_schema_has_port_editor_fields(self) -> None:
        from scistudio.blocks.code.code_block import CodeBlock

        props = CodeBlock.config_schema["properties"]
        self._assert_port_editor_fields(props)

    def test_appblock_own_schema_has_port_editor_fields(self) -> None:
        from scistudio.blocks.app.app_block import AppBlock

        props = AppBlock.config_schema["properties"]
        self._assert_port_editor_fields(props)

    def test_aiblock_mro_merged_schema_has_port_editor_fields(self) -> None:
        from scistudio.blocks.ai.ai_block import AIBlock
        from scistudio.blocks.registry import _merge_config_schema

        merged = _merge_config_schema(AIBlock)
        self._assert_port_editor_fields(merged["properties"])

    def test_codeblock_mro_merged_schema_has_port_editor_fields(self) -> None:
        from scistudio.blocks.code.code_block import CodeBlock
        from scistudio.blocks.registry import _merge_config_schema

        merged = _merge_config_schema(CodeBlock)
        self._assert_port_editor_fields(merged["properties"])

    def test_appblock_mro_merged_schema_has_port_editor_fields(self) -> None:
        from scistudio.blocks.app.app_block import AppBlock
        from scistudio.blocks.registry import _merge_config_schema

        merged = _merge_config_schema(AppBlock)
        self._assert_port_editor_fields(merged["properties"])

    def test_aiblock_subclass_inherits_port_editor_via_mro(self) -> None:
        """A subclass of AIBlock that declares no port editor fields gets them via MRO."""
        from scistudio.blocks.ai.ai_block import AIBlock
        from scistudio.blocks.registry import _merge_config_schema

        class _MyAIBlock(AIBlock):
            name: ClassVar[str] = "My AI"
            config_schema: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {
                    "custom_param": {"type": "string"},
                },
            }

            def run(self, inputs: dict, config: Any) -> dict:
                return {}

        merged = _merge_config_schema(_MyAIBlock)
        props = merged["properties"]
        assert "custom_param" in props
        self._assert_port_editor_fields(props)

    def test_port_editor_fields_have_correct_item_schema(self) -> None:
        """Each port entry must have name (string) and types (array of strings)."""
        from scistudio.blocks.ai.ai_block import AIBlock

        props = AIBlock.config_schema["properties"]
        item_props = props["input_ports"]["items"]["properties"]
        assert "name" in item_props
        assert item_props["name"]["type"] == "string"
        assert "types" in item_props
        assert item_props["types"]["type"] == "array"
