"""Tests for ScieasyAIBlockCatalog directive — ADR-044 §11.5."""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest
from docutils import nodes


class TestAIBlockCatalogDirective:
    """Tests for ScieasyAIBlockCatalog."""

    def _make_directive(self, options: dict | None = None):
        from scieasy.qa.docs.directives.scieasy_ai_block_catalog import ScieasyAIBlockCatalog

        return ScieasyAIBlockCatalog(
            name="scieasy-ai-block-catalog",
            arguments=[],
            options=options or {},
            content=[],
            lineno=1,
            content_offset=0,
            block_text="",
            state=MagicMock(),
            state_machine=MagicMock(),
        )

    def test_run_returns_node_list(self):
        directive = self._make_directive()
        result = directive.run()
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_run_with_real_entry_points(self):
        """With real scieasy.blocks, AIBlock should be discoverable."""
        directive = self._make_directive()
        result = directive.run()
        # Should not crash; may or may not find AI blocks depending on filtering
        assert isinstance(result, list)

    def test_run_empty_group(self):
        """Empty group emits a warning node."""
        with patch("scieasy.qa.docs.directives.scieasy_ai_block_catalog.importlib.metadata.entry_points") as mock_eps:
            mock_eps.return_value = []
            directive = self._make_directive(options={"entry-point-group": "nonexistent"})
            result = directive.run()
            assert any(isinstance(n, nodes.warning) for n in result)

    def test_run_exception_returns_warning(self):
        with patch(
            "scieasy.qa.docs.directives.scieasy_ai_block_catalog.importlib.metadata.entry_points",
            side_effect=Exception("boom"),
        ):
            directive = self._make_directive(options={"entry-point-group": "fail"})
            result = directive.run()
            assert any(isinstance(n, nodes.warning) for n in result)

    def test_raw_node_has_list_table(self):
        """When AI blocks are found, the raw node contains list-table."""
        # Inject a fake AI-block class to bypass entry-point loading
        from scieasy.qa.docs.directives.scieasy_ai_block_catalog import (
            _build_list_table,
        )

        node = _build_list_table(
            headers=["A", "B", "C", "D", "E", "F"],
            rows=[["a", "b", "c", "1", "1", "route"]],
        )
        assert "list-table" in node.rawsource


class TestIsAIBlock:
    """Tests for the _is_ai_block predicate."""

    def test_ai_type_name(self):
        from scieasy.qa.docs.directives.scieasy_ai_block_catalog import _is_ai_block

        class FakeAI:
            type_name = "ai.agent"
            subcategory = ""

        assert _is_ai_block(FakeAI)

    def test_ai_subcategory(self):
        from scieasy.qa.docs.directives.scieasy_ai_block_catalog import _is_ai_block

        class FakeAI:
            type_name = "code.python"
            subcategory = "ai"

        assert _is_ai_block(FakeAI)

    def test_non_ai_block(self):
        from scieasy.qa.docs.directives.scieasy_ai_block_catalog import _is_ai_block

        class FakeBlock:
            type_name = "io.load"
            subcategory = "io"

        assert not _is_ai_block(FakeBlock)

    def test_with_real_ai_block(self):
        """AIBlock from scieasy.blocks.ai should be identified as an AI block."""
        from scieasy.qa.docs.directives.scieasy_ai_block_catalog import _is_ai_block

        try:
            from scieasy.blocks.ai import AIBlock

            assert _is_ai_block(AIBlock)
        except ImportError:
            pytest.skip("scieasy.blocks.ai not importable")


class TestExtractAISpec:
    """Tests for _extract_ai_spec helper."""

    def test_with_real_ai_block(self):
        from scieasy.qa.docs.directives.scieasy_ai_block_catalog import _extract_ai_spec

        try:
            from scieasy.blocks.ai import AIBlock

            spec = _extract_ai_spec("ai_block", "scieasy.blocks.ai:AIBlock", AIBlock)
            assert "name" in spec
            assert "symbol" in spec
            assert "provider" in spec
            assert "model" in spec
            assert "pty_route" in spec
        except ImportError:
            pytest.skip("scieasy.blocks.ai not importable")

    def test_with_minimal_class(self):
        from scieasy.qa.docs.directives.scieasy_ai_block_catalog import _extract_ai_spec

        class MinimalAI:
            name = "Minimal AI"
            type_name = "ai.minimal"
            subcategory = "ai"
            config_schema: ClassVar[dict] = {}  # type: ignore[misc]
            input_ports: ClassVar[list] = []  # type: ignore[misc]
            output_ports: ClassVar[list] = []  # type: ignore[misc]
            __module__ = "test.module"
            __qualname__ = "MinimalAI"

        spec = _extract_ai_spec("minimal_ai", "test.module:MinimalAI", MinimalAI)
        assert spec["name"] == "Minimal AI"
        assert spec["provider"] == "claude-code"  # default
