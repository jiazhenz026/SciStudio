"""Tests for openapi_reference generator — ADR-044 §11.5."""

from __future__ import annotations

from pathlib import Path


class TestGenerate:
    """Tests for openapi_reference.generate."""

    def test_creates_output_file(self, tmp_path: Path):
        from scieasy.qa.docs.generators.openapi_reference import generate

        output = tmp_path / "server-api.md"
        generate(tmp_path, output)
        assert output.exists()

    def test_has_generation_frontmatter(self, tmp_path: Path):
        from scieasy.qa.docs.generators.openapi_reference import generate

        output = tmp_path / "server-api.md"
        generate(tmp_path, output, source_sha="deadbeef")
        content = output.read_text(encoding="utf-8")
        assert "generation: auto" in content
        assert "deadbeef" in content

    def test_has_generated_marker(self, tmp_path: Path):
        """The file must have a <!-- generated --> marker."""
        from scieasy.qa.docs.generators.openapi_reference import generate

        output = tmp_path / "server-api.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "<!-- generated" in content

    def test_has_openapi_directive(self, tmp_path: Path):
        """The file references the sphinxcontrib-openapi directive."""
        from scieasy.qa.docs.generators.openapi_reference import generate

        output = tmp_path / "server-api.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "openapi" in content.lower()

    def test_heading_present(self, tmp_path: Path):
        from scieasy.qa.docs.generators.openapi_reference import generate

        output = tmp_path / "server-api.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "# Server API Reference" in content

    def test_creates_parent_dirs(self, tmp_path: Path):
        from scieasy.qa.docs.generators.openapi_reference import generate

        output = tmp_path / "deep" / "ref" / "server-api.md"
        generate(tmp_path, output)
        assert output.exists()

    def test_frontmatter_starts_with_dashes(self, tmp_path: Path):
        from scieasy.qa.docs.generators.openapi_reference import generate

        output = tmp_path / "server-api.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert content.startswith("---\n")

    def test_default_sha_is_unknown(self, tmp_path: Path):
        from scieasy.qa.docs.generators.openapi_reference import generate

        output = tmp_path / "server-api.md"
        generate(tmp_path, output)
        content = output.read_text(encoding="utf-8")
        assert "unknown" in content

    def test_todo_comment_present(self, tmp_path: Path):
        """A TODO comment should note Phase 5 full integration."""
        # This test verifies the module-level TODO exists as a code comment
        import inspect

        import scieasy.qa.docs.generators.openapi_reference as mod

        source = inspect.getsource(mod)
        assert "TODO" in source
