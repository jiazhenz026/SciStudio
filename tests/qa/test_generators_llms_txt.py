"""Tests for llms_txt generator — ADR-044 §11.5."""

from __future__ import annotations

from pathlib import Path


class TestGenerate:
    """Tests for scieasy.qa.docs.generators.llms_txt.generate."""

    def test_creates_output_file(self, tmp_path: Path):
        """generate() creates the output file."""
        from scieasy.qa.docs.generators.llms_txt import generate

        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        (docs_root / "index.rst").write_text(
            "SciEasy Docs\n============\n\n.. toctree::\n\n   intro\n",
            encoding="utf-8",
        )
        output = tmp_path / "llms.txt"
        generate(docs_root, output, source_sha="abc1234")
        assert output.exists()

    def test_output_has_frontmatter(self, tmp_path: Path):
        """Generated file starts with YAML-style frontmatter block."""
        from scieasy.qa.docs.generators.llms_txt import generate

        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        (docs_root / "index.rst").write_text("Title\n=====\n", encoding="utf-8")
        output = tmp_path / "llms.txt"
        generate(docs_root, output, source_sha="deadbeef")
        content = output.read_text(encoding="utf-8")
        assert "---" in content
        assert "generation: auto" in content

    def test_source_sha_recorded(self, tmp_path: Path):
        """The source.last_generated_sha field is written."""
        from scieasy.qa.docs.generators.llms_txt import generate

        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        (docs_root / "index.md").write_text("# My Docs\n", encoding="utf-8")
        output = tmp_path / "llms.txt"
        sha = "cafebabe"
        generate(docs_root, output, source_sha=sha)
        content = output.read_text(encoding="utf-8")
        assert sha in content

    def test_toctree_section_present(self, tmp_path: Path):
        """The generated file contains a Table of Contents section."""
        from scieasy.qa.docs.generators.llms_txt import generate

        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        (docs_root / "index.md").write_text("# SciEasy\n", encoding="utf-8")
        output = tmp_path / "llms.txt"
        generate(docs_root, output)
        content = output.read_text(encoding="utf-8")
        assert "Table of Contents" in content

    def test_parent_dirs_created(self, tmp_path: Path):
        """generate() creates parent directories for output if needed."""
        from scieasy.qa.docs.generators.llms_txt import generate

        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        (docs_root / "index.rst").write_text("Title\n=====\n", encoding="utf-8")
        output = tmp_path / "deep" / "nested" / "llms.txt"
        generate(docs_root, output)
        assert output.exists()

    def test_project_blurb_present(self, tmp_path: Path):
        """The project blurb is included in the output."""
        from scieasy.qa.docs.generators.llms_txt import generate

        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        (docs_root / "index.md").write_text("# SciEasy\n", encoding="utf-8")
        output = tmp_path / "llms.txt"
        generate(docs_root, output)
        content = output.read_text(encoding="utf-8")
        # The blurb is embedded in a > blockquote line
        assert "SciEasy" in content

    def test_default_sha_is_unknown(self, tmp_path: Path):
        """When source_sha is not provided, 'unknown' appears in output."""
        from scieasy.qa.docs.generators.llms_txt import generate

        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        (docs_root / "index.md").write_text("# X\n", encoding="utf-8")
        output = tmp_path / "out.txt"
        generate(docs_root, output)
        content = output.read_text(encoding="utf-8")
        assert "unknown" in content

    def test_walks_toctree_references(self, tmp_path: Path):
        """References in a toctree are included in the output."""
        from scieasy.qa.docs.generators.llms_txt import generate

        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        child = docs_root / "intro.rst"
        child.write_text("Introduction\n============\n", encoding="utf-8")
        index = docs_root / "index.rst"
        index.write_text(
            "SciEasy\n=======\n\n.. toctree::\n\n   intro\n",
            encoding="utf-8",
        )
        output = tmp_path / "llms.txt"
        generate(docs_root, output)
        content = output.read_text(encoding="utf-8")
        assert "intro" in content or "Introduction" in content


class TestWalkToctrees:
    """Tests for the _walk_toctrees helper."""

    def test_no_index_returns_empty(self, tmp_path: Path):
        from scieasy.qa.docs.generators.llms_txt import _walk_toctrees

        entries = list(_walk_toctrees(tmp_path))
        assert entries == []

    def test_index_only_returns_one_entry(self, tmp_path: Path):
        from scieasy.qa.docs.generators.llms_txt import _walk_toctrees

        (tmp_path / "index.md").write_text("# Title\n", encoding="utf-8")
        entries = list(_walk_toctrees(tmp_path))
        assert len(entries) >= 1
        assert entries[0]["depth"] == 0

    def test_entry_has_required_keys(self, tmp_path: Path):
        from scieasy.qa.docs.generators.llms_txt import _walk_toctrees

        (tmp_path / "index.md").write_text("# Title\n", encoding="utf-8")
        entries = list(_walk_toctrees(tmp_path))
        for entry in entries:
            assert "title" in entry
            assert "path" in entry
            assert "depth" in entry


class TestExtractTitle:
    """Tests for the _extract_title helper."""

    def test_markdown_h1(self, tmp_path: Path):
        from scieasy.qa.docs.generators.llms_txt import _extract_title

        p = tmp_path / "doc.md"
        p.write_text("# My Document\n\nBody text.\n", encoding="utf-8")
        assert _extract_title(p) == "My Document"

    def test_rst_underlined_title(self, tmp_path: Path):
        from scieasy.qa.docs.generators.llms_txt import _extract_title

        p = tmp_path / "doc.rst"
        p.write_text("My RST Title\n============\n\nBody.\n", encoding="utf-8")
        assert _extract_title(p) == "My RST Title"

    def test_fallback_to_stem(self, tmp_path: Path):
        from scieasy.qa.docs.generators.llms_txt import _extract_title

        p = tmp_path / "my_file.rst"
        p.write_text("", encoding="utf-8")
        assert _extract_title(p) == "my_file"
