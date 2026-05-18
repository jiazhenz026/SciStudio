"""Tests for cli_reference generator — ADR-044 §11.5."""

from __future__ import annotations

from pathlib import Path


class TestGenerate:
    """Tests for cli_reference.generate."""

    def test_creates_output_file(self, tmp_path: Path):
        from scieasy.qa.docs.generators.cli_reference import generate

        output = tmp_path / "cli.md"
        generate(tmp_path, output)
        assert output.exists()

    def test_has_generation_frontmatter(self, tmp_path: Path):
        from scieasy.qa.docs.generators.cli_reference import generate

        output = tmp_path / "cli.md"
        generate(tmp_path, output, source_sha="sha123")
        content = output.read_text(encoding="utf-8")
        assert "generation: auto" in content
        assert "sha123" in content

    def test_has_generated_marker(self, tmp_path: Path):
        """The file must have a <!-- generated --> marker."""
        from scieasy.qa.docs.generators.cli_reference import generate

        output = tmp_path / "cli.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "<!-- generated" in content

    def test_has_sphinx_click_directive(self, tmp_path: Path):
        """The file must reference the sphinx-click directive."""
        from scieasy.qa.docs.generators.cli_reference import generate

        output = tmp_path / "cli.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "click" in content.lower()

    def test_heading_present(self, tmp_path: Path):
        from scieasy.qa.docs.generators.cli_reference import generate

        output = tmp_path / "cli.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "# CLI Reference" in content

    def test_creates_parent_dirs(self, tmp_path: Path):
        from scieasy.qa.docs.generators.cli_reference import generate

        output = tmp_path / "deep" / "nested" / "cli.md"
        generate(tmp_path, output)
        assert output.exists()

    def test_default_sha_is_unknown(self, tmp_path: Path):
        from scieasy.qa.docs.generators.cli_reference import generate

        output = tmp_path / "cli.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "unknown" in content

    def test_frontmatter_block_is_valid_yaml_section(self, tmp_path: Path):
        """Frontmatter block is delimited by ---."""
        from scieasy.qa.docs.generators.cli_reference import generate

        output = tmp_path / "cli.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        # Should have a closing --- too
        assert content.count("---") >= 2

    def test_scieasy_cli_module_referenced(self, tmp_path: Path):
        """The scieasy CLI entry-point is referenced in the directive."""
        from scieasy.qa.docs.generators.cli_reference import generate

        output = tmp_path / "cli.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "scieasy.cli.main" in content or "scieasy" in content
