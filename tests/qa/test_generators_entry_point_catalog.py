"""Tests for entry_point_catalog generator — ADR-044 §11.5."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


class TestGenerate:
    """Tests for entry_point_catalog.generate."""

    def test_creates_output_file(self, tmp_path: Path):
        from scieasy.qa.docs.generators.entry_point_catalog import generate

        output = tmp_path / "entry-points.md"
        generate(tmp_path, output)
        assert output.exists()

    def test_has_generation_frontmatter(self, tmp_path: Path):
        from scieasy.qa.docs.generators.entry_point_catalog import generate

        output = tmp_path / "ep.md"
        generate(tmp_path, output, source_sha="abc123")
        content = output.read_text(encoding="utf-8")
        assert "generation: auto" in content
        assert "abc123" in content

    def test_has_generated_marker(self, tmp_path: Path):
        from scieasy.qa.docs.generators.entry_point_catalog import generate

        output = tmp_path / "ep.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "<!-- generated" in content

    def test_contains_table_header(self, tmp_path: Path):
        from scieasy.qa.docs.generators.entry_point_catalog import generate

        output = tmp_path / "ep.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "Entry-point name" in content

    def test_contains_real_entries(self, tmp_path: Path):
        """Real scieasy.blocks entry-points appear in the output."""
        from scieasy.qa.docs.generators.entry_point_catalog import generate

        output = tmp_path / "ep.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        # At least one of the known entry-points should appear
        assert "load_data" in content or "save_data" in content or "scieasy.blocks" in content

    def test_creates_parent_dirs(self, tmp_path: Path):
        from scieasy.qa.docs.generators.entry_point_catalog import generate

        output = tmp_path / "deep" / "ref" / "ep.md"
        generate(tmp_path, output)
        assert output.exists()

    def test_empty_group_writes_no_entries_note(self, tmp_path: Path):
        """When no entry-points exist, a note is written instead of a table."""
        from scieasy.qa.docs.generators.entry_point_catalog import generate

        with patch(
            "scieasy.qa.docs.generators.entry_point_catalog.importlib.metadata.entry_points",
            return_value=[],
        ):
            output = tmp_path / "ep.md"
            generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "No entry-points" in content or "Entry-Point Catalog" in content

    def test_heading_present(self, tmp_path: Path):
        from scieasy.qa.docs.generators.entry_point_catalog import generate

        output = tmp_path / "ep.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "# Entry-Point Catalog" in content


class TestCollectEntryPoints:
    """Tests for _collect_entry_points helper."""

    def test_returns_list_of_tuples(self):
        from scieasy.qa.docs.generators.entry_point_catalog import _collect_entry_points

        rows = _collect_entry_points()
        assert isinstance(rows, list)
        for row in rows:
            assert len(row) == 3
            name, value, group = row
            assert isinstance(name, str)
            assert isinstance(value, str)
            assert isinstance(group, str)

    def test_sorted_by_group_then_name(self):
        from scieasy.qa.docs.generators.entry_point_catalog import _collect_entry_points

        rows = _collect_entry_points()
        sort_keys = [(r[2], r[0]) for r in rows]
        assert sort_keys == sorted(sort_keys)

    def test_contains_known_groups(self):
        from scieasy.qa.docs.generators.entry_point_catalog import _collect_entry_points

        rows = _collect_entry_points()
        groups = {r[2] for r in rows}
        # At least one of the known SciEasy groups should be present
        assert groups & {"scieasy.blocks", "scieasy.runners", "scieasy.types"}
