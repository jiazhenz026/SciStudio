"""Tests for schema_reference generator — ADR-044 §11.5."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestGenerate:
    """Tests for schema_reference.generate."""

    def test_creates_output_directory(self, tmp_path: Path):
        from scieasy.qa.docs.generators.schema_reference import generate

        output_dir = tmp_path / "schemas"
        generate(tmp_path, output_dir)
        assert output_dir.is_dir()

    def test_emits_per_schema_files(self, tmp_path: Path):
        """At least one schema .md file should be emitted."""
        from scieasy.qa.docs.generators.schema_reference import generate

        output_dir = tmp_path / "schemas"
        generate(tmp_path, output_dir)
        md_files = list(output_dir.glob("*.md"))
        assert len(md_files) >= 1

    def test_each_file_has_frontmatter(self, tmp_path: Path):
        from scieasy.qa.docs.generators.schema_reference import generate

        output_dir = tmp_path / "schemas"
        generate(tmp_path, output_dir, source_sha="abc123")
        for f in output_dir.glob("*.md"):
            content = f.read_text(encoding="utf-8")
            assert "generation: auto" in content
            assert "abc123" in content

    def test_each_file_has_generated_marker(self, tmp_path: Path):
        from scieasy.qa.docs.generators.schema_reference import generate

        output_dir = tmp_path / "schemas"
        generate(tmp_path, output_dir)
        for f in output_dir.glob("*.md"):
            content = f.read_text(encoding="utf-8")
            assert "<!-- generated" in content

    def test_each_file_has_autopydantic_directive(self, tmp_path: Path):
        """Each schema file must reference the autopydantic_model directive."""
        from scieasy.qa.docs.generators.schema_reference import generate

        output_dir = tmp_path / "schemas"
        generate(tmp_path, output_dir)
        for f in output_dir.glob("*.md"):
            content = f.read_text(encoding="utf-8")
            assert "autopydantic_model" in content

    def test_known_model_is_emitted(self, tmp_path: Path):
        """Finding model (from report.py) should have its own .md file."""
        from scieasy.qa.docs.generators.schema_reference import generate

        output_dir = tmp_path / "schemas"
        generate(tmp_path, output_dir)
        schema_names = {f.stem for f in output_dir.glob("*.md")}
        # At least one of the known model names should be present
        known = {"Finding", "AuditReport", "ToolRun"}
        assert known & schema_names, f"Expected one of {known} in {schema_names}"

    def test_creates_parent_dirs(self, tmp_path: Path):
        from scieasy.qa.docs.generators.schema_reference import generate

        output_dir = tmp_path / "deep" / "schemas"
        generate(tmp_path, output_dir)
        assert output_dir.is_dir()

    def test_file_names_match_class_names(self, tmp_path: Path):
        """Each .md file name matches the PascalCase class name."""
        from scieasy.qa.docs.generators.schema_reference import generate

        output_dir = tmp_path / "schemas"
        generate(tmp_path, output_dir)
        for f in output_dir.glob("*.md"):
            # File name should be PascalCase (no underscores/hyphens)
            assert f.stem[0].isupper(), f"Expected PascalCase file name, got {f.stem}"


class TestCollectModels:
    """Tests for _collect_models helper."""

    def test_returns_list(self):
        from scieasy.qa.docs.generators.schema_reference import _collect_models

        models = _collect_models()
        assert isinstance(models, list)

    def test_each_entry_has_three_elements(self):
        from scieasy.qa.docs.generators.schema_reference import _collect_models

        models = _collect_models()
        for item in models:
            assert len(item) == 3
            class_name, full_path, _cls = item
            assert isinstance(class_name, str)
            assert isinstance(full_path, str)
            assert "." in full_path

    def test_sorted_by_class_name(self):
        from scieasy.qa.docs.generators.schema_reference import _collect_models

        models = _collect_models()
        names = [m[0] for m in models]
        assert names == sorted(names)

    def test_no_duplicates(self):
        from scieasy.qa.docs.generators.schema_reference import _collect_models

        models = _collect_models()
        full_paths = [m[1] for m in models]
        assert len(full_paths) == len(set(full_paths))

    def test_finding_is_included(self):
        """Finding model should be in the collected models."""
        from scieasy.qa.docs.generators.schema_reference import _collect_models

        models = _collect_models()
        class_names = {m[0] for m in models}
        assert "Finding" in class_names


class TestIsPydanticModel:
    """Tests for _is_pydantic_model helper."""

    def test_pydantic_basemodel_subclass(self):
        from scieasy.qa.docs.generators.schema_reference import _is_pydantic_model

        try:
            from pydantic import BaseModel

            class MyModel(BaseModel):
                x: int

            assert _is_pydantic_model(MyModel)
        except ImportError:
            pytest.skip("pydantic not installed")

    def test_plain_class(self):
        from scieasy.qa.docs.generators.schema_reference import _is_pydantic_model

        class Plain:
            pass

        assert not _is_pydantic_model(Plain)

    def test_basemodel_itself_excluded(self):
        """BaseModel itself should not be included (it is not a *subclass*)."""
        from scieasy.qa.docs.generators.schema_reference import _is_pydantic_model

        try:
            from pydantic import BaseModel

            assert not _is_pydantic_model(BaseModel)
        except ImportError:
            pytest.skip("pydantic not installed")
