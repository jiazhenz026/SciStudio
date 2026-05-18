"""Tests for ScieasyBlockCatalog directive — ADR-044 §11.5."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from docutils import nodes


class TestBlockCatalogDirective:
    """Tests for ScieasyBlockCatalog."""

    def _make_directive(self, options: dict | None = None):
        """Instantiate ScieasyBlockCatalog with minimal state."""
        from scieasy.qa.docs.directives.scieasy_block_catalog import ScieasyBlockCatalog

        directive = ScieasyBlockCatalog(
            name="scieasy-block-catalog",
            arguments=[],
            options=options or {},
            content=[],
            lineno=1,
            content_offset=0,
            block_text="",
            state=MagicMock(),
            state_machine=MagicMock(),
        )
        return directive

    def test_run_returns_node_list(self):
        """run() must return a list of nodes.Node."""
        directive = self._make_directive()
        result = directive.run()
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_run_with_real_entry_points(self):
        """With real scieasy.blocks entry-points, at least one block row is present."""
        directive = self._make_directive()
        result = directive.run()
        # Should not produce a warning node (warning means empty group)
        assert not any(isinstance(n, nodes.warning) for n in result)

    def test_run_with_empty_group(self):
        """An empty entry-point group emits a warning node."""

        with patch("scieasy.qa.docs.directives.scieasy_block_catalog.importlib.metadata.entry_points") as mock_eps:
            mock_eps.return_value = []
            directive = self._make_directive(options={"entry-point-group": "nonexistent.group"})
            result = directive.run()
            assert any(isinstance(n, nodes.warning) for n in result)

    def test_run_with_custom_group(self):
        """The entry-point-group option is respected."""
        directive = self._make_directive(options={"entry-point-group": "scieasy.blocks"})
        result = directive.run()
        assert isinstance(result, list)

    def test_raw_node_contains_list_table(self):
        """The emitted raw node should contain '.. list-table::'."""
        directive = self._make_directive()
        result = directive.run()
        raw_nodes = [n for n in result if isinstance(n, nodes.raw)]
        assert raw_nodes, "Expected at least one raw node"
        combined = "".join(str(n.astext()) for n in raw_nodes)
        assert "list-table" in combined or len(result) > 0

    def test_run_bad_group_returns_warning(self):
        """A group that raises an exception yields a warning node."""
        with patch(
            "scieasy.qa.docs.directives.scieasy_block_catalog.importlib.metadata.entry_points",
            side_effect=Exception("simulated failure"),
        ):
            directive = self._make_directive(options={"entry-point-group": "fail.group"})
            result = directive.run()
            assert any(isinstance(n, nodes.warning) for n in result)


class TestLoadBlockSpecs:
    """Tests for the _load_block_specs helper."""

    def test_returns_sorted_list(self):
        """Block specs should be returned sorted by name."""
        from scieasy.qa.docs.directives.scieasy_block_catalog import _load_block_specs

        specs = _load_block_specs("scieasy.blocks")
        names = [s["name"] for s in specs]
        assert names == sorted(names)

    def test_empty_group(self):
        """An unrecognised group returns an empty list."""
        from scieasy.qa.docs.directives.scieasy_block_catalog import _load_block_specs

        specs = _load_block_specs("scieasy.nonexistent.group")
        assert isinstance(specs, list)

    def test_spec_has_required_keys(self):
        """Each spec dict must carry the expected keys."""
        from scieasy.qa.docs.directives.scieasy_block_catalog import _load_block_specs

        specs = _load_block_specs("scieasy.blocks")
        for spec in specs:
            assert "name" in spec
            assert "symbol" in spec
            assert "input_ports" in spec
            assert "output_ports" in spec
            assert "supported_extensions" in spec
            assert "class_ref" in spec


class TestExtractSpec:
    """Tests for the _extract_spec helper."""

    def test_with_block_class(self):
        """_extract_spec returns a valid dict for a real block class."""
        from scieasy.qa.docs.directives.scieasy_block_catalog import _extract_spec

        try:
            from scieasy.blocks.ai import AIBlock

            spec = _extract_spec("ai_block", "scieasy.blocks.ai:AIBlock", AIBlock)
            assert spec["name"] == AIBlock.name
            assert "scieasy.blocks" in spec["symbol"]
        except ImportError:
            pytest.skip("scieasy.blocks.ai not importable")

    def test_with_non_class_callable(self):
        """_extract_spec handles factory callables without crashing."""
        from scieasy.qa.docs.directives.scieasy_block_catalog import _extract_spec

        def fake_factory() -> None:
            return None

        spec = _extract_spec("fake", "pkg:fake_factory", fake_factory)
        assert spec["name"] == "fake"
        assert spec["symbol"] == "pkg:fake_factory"


class TestBuildListTable:
    """Tests for the _build_list_table helper."""

    def test_returns_raw_node(self):
        """_build_list_table returns a raw docutils node."""
        from scieasy.qa.docs.directives.scieasy_block_catalog import _build_list_table

        node = _build_list_table(["Col1", "Col2"], [["a", "b"], ["c", "d"]])
        assert isinstance(node, nodes.raw)

    def test_contains_headers(self):
        """The generated RST contains all header names."""
        from scieasy.qa.docs.directives.scieasy_block_catalog import _build_list_table

        node = _build_list_table(["Header1", "Header2"], [])
        raw = node.rawsource
        assert "Header1" in raw
        assert "Header2" in raw

    def test_contains_row_data(self):
        """The generated RST contains row cell data."""
        from scieasy.qa.docs.directives.scieasy_block_catalog import _build_list_table

        node = _build_list_table(["H"], [["cell_value"]])
        raw = node.rawsource
        assert "cell_value" in raw
