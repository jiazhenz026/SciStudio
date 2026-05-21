"""Tests for the init-block-package CLI command and scaffold module."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from scistudio.cli._scaffold import (
    _to_display_name,
    _to_entry_point_name,
    _to_module_name,
    render_template,
    scaffold_block_package,
)
from scistudio.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Unit tests for scaffold helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    """Test name conversion helpers."""

    def test_to_module_name_replaces_hyphens(self) -> None:
        assert _to_module_name("scistudio-blocks-srs") == "scistudio_blocks_srs"

    def test_to_module_name_replaces_dots(self) -> None:
        assert _to_module_name("my.package") == "my_package"

    def test_to_display_name(self) -> None:
        assert _to_display_name("scistudio-blocks-srs") == "Scistudio Blocks Srs"

    def test_to_display_name_underscores(self) -> None:
        assert _to_display_name("my_blocks") == "My Blocks"

    def test_to_entry_point_name(self) -> None:
        assert _to_entry_point_name("scistudio-blocks-srs") == "scistudio_blocks_srs"


class TestRenderTemplate:
    """Test template rendering with placeholder substitution."""

    def test_simple_substitution(self) -> None:
        tpl = "Hello {name}!"
        assert render_template(tpl, {"name": "World"}) == "Hello World!"

    def test_multiple_placeholders(self) -> None:
        tpl = "{a} and {b}"
        assert render_template(tpl, {"a": "X", "b": "Y"}) == "X and Y"

    def test_escaped_braces_preserved(self) -> None:
        tpl = '{{text = "MIT"}}'
        assert render_template(tpl, {}) == '{text = "MIT"}'

    def test_mixed_escaped_and_placeholder(self) -> None:
        tpl = 'license = {{text = "{license_type}"}}'
        result = render_template(tpl, {"license_type": "MIT"})
        assert result == 'license = {text = "MIT"}'

    def test_unknown_placeholder_kept(self) -> None:
        tpl = "Hello {unknown}!"
        assert render_template(tpl, {}) == "Hello {unknown}!"


# ---------------------------------------------------------------------------
# Unit tests for scaffold_block_package
# ---------------------------------------------------------------------------


class TestScaffoldBlockPackage:
    """Test the scaffold_block_package function."""

    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        result = scaffold_block_package(
            tmp_path,
            "my-blocks",
            author="Test Author",
            description="Test description",
        )
        root: Path = result["root"]
        assert root.is_dir()
        assert (root / "pyproject.toml").is_file()
        assert (root / "src" / "my_blocks" / "__init__.py").is_file()
        assert (root / "src" / "my_blocks" / "blocks.py").is_file()
        assert (root / "tests" / "test_blocks.py").is_file()
        assert (root / "README.md").is_file()

    def test_returns_file_list(self, tmp_path: Path) -> None:
        result = scaffold_block_package(tmp_path, "test-pkg")
        files = result["files"]
        assert "pyproject.toml" in files
        assert "src/test_pkg/__init__.py" in files
        assert "src/test_pkg/blocks.py" in files
        assert "tests/test_blocks.py" in files
        assert "README.md" in files

    def test_pyproject_has_entry_points(self, tmp_path: Path) -> None:
        scaffold_block_package(tmp_path, "my-blocks")
        content = (tmp_path / "my-blocks" / "pyproject.toml").read_text()
        assert '[project.entry-points."scistudio.blocks"]' in content
        assert "my_blocks" in content
        assert 'my_blocks = "my_blocks:get_blocks"' in content

    def test_pyproject_has_correct_name(self, tmp_path: Path) -> None:
        scaffold_block_package(tmp_path, "my-blocks", author="Dr. Smith")
        content = (tmp_path / "my-blocks" / "pyproject.toml").read_text()
        assert 'name = "my-blocks"' in content
        assert 'name = "Dr. Smith"' in content

    def test_init_follows_callable_protocol(self, tmp_path: Path) -> None:
        scaffold_block_package(
            tmp_path,
            "my-blocks",
            display_name="My Blocks",
        )
        content = (tmp_path / "my-blocks" / "src" / "my_blocks" / "__init__.py").read_text()
        assert "from scistudio.blocks.base.package_info import PackageInfo" in content
        assert "def get_blocks()" in content
        assert "tuple[PackageInfo, list[type]]" in content
        assert 'name="My Blocks"' in content

    def test_init_imports_block(self, tmp_path: Path) -> None:
        scaffold_block_package(tmp_path, "my-blocks")
        content = (tmp_path / "my-blocks" / "src" / "my_blocks" / "__init__.py").read_text()
        assert "from my_blocks.blocks import ExampleBlock" in content

    def test_blocks_extends_process_block(self, tmp_path: Path) -> None:
        scaffold_block_package(tmp_path, "my-blocks")
        content = (tmp_path / "my-blocks" / "src" / "my_blocks" / "blocks.py").read_text()
        assert "class ExampleBlock(ProcessBlock):" in content
        assert "def process_item" in content
        assert "input_ports" in content
        assert "output_ports" in content

    def test_custom_display_name(self, tmp_path: Path) -> None:
        scaffold_block_package(
            tmp_path,
            "my-blocks",
            display_name="SRS Imaging",
        )
        init_content = (tmp_path / "my-blocks" / "src" / "my_blocks" / "__init__.py").read_text()
        assert 'name="SRS Imaging"' in init_content

    def test_default_display_name(self, tmp_path: Path) -> None:
        scaffold_block_package(tmp_path, "scistudio-blocks-srs")
        init_content = (tmp_path / "scistudio-blocks-srs" / "src" / "scistudio_blocks_srs" / "__init__.py").read_text()
        assert 'name="Scistudio Blocks Srs"' in init_content

    def test_existing_directory_raises(self, tmp_path: Path) -> None:
        (tmp_path / "existing").mkdir()
        import pytest

        with pytest.raises(FileExistsError):
            scaffold_block_package(tmp_path, "existing")

    def test_test_file_checks_protocol(self, tmp_path: Path) -> None:
        scaffold_block_package(tmp_path, "my-blocks", display_name="My Blocks")
        content = (tmp_path / "my-blocks" / "tests" / "test_blocks.py").read_text()
        assert "from my_blocks import get_blocks" in content
        assert "from my_blocks.blocks import ExampleBlock" in content
        assert "PackageInfo" in content
        assert 'info.name == "My Blocks"' in content

    def test_readme_has_package_name(self, tmp_path: Path) -> None:
        scaffold_block_package(
            tmp_path,
            "my-blocks",
            display_name="My Blocks",
        )
        content = (tmp_path / "my-blocks" / "README.md").read_text()
        assert "# My Blocks" in content
        assert "scistudio blocks" in content


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestCLIInitBlockPackage:
    """Test the ``scistudio init-block-package`` CLI command."""

    def test_help_shows_command(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "init-block-package" in result.output

    def test_creates_package(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        result = runner.invoke(app, ["init-block-package", "test-pkg"])
        assert result.exit_code == 0
        assert "Created block package: test-pkg/" in result.output
        assert (tmp_path / "test-pkg" / "pyproject.toml").is_file()

    def test_creates_correct_structure(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        result = runner.invoke(app, ["init-block-package", "my-blocks"])
        assert result.exit_code == 0
        assert (tmp_path / "my-blocks" / "src" / "my_blocks" / "__init__.py").is_file()
        assert (tmp_path / "my-blocks" / "src" / "my_blocks" / "blocks.py").is_file()
        assert (tmp_path / "my-blocks" / "tests" / "test_blocks.py").is_file()

    def test_with_options(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        result = runner.invoke(
            app,
            [
                "init-block-package",
                "my-pkg",
                "--display-name",
                "My Package",
                "--author",
                "Dr. Smith",
                "--description",
                "A test package",
            ],
        )
        assert result.exit_code == 0
        content = (tmp_path / "my-pkg" / "pyproject.toml").read_text()
        assert 'description = "A test package"' in content
        assert 'name = "Dr. Smith"' in content

    def test_existing_directory_fails(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        (tmp_path / "existing").mkdir()
        result = runner.invoke(app, ["init-block-package", "existing"])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_shows_next_steps(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        result = runner.invoke(app, ["init-block-package", "test-pkg"])
        assert result.exit_code == 0
        assert "Next steps:" in result.output
        assert "pip install" in result.output
        assert "pytest" in result.output
        assert "scistudio blocks" in result.output

    def test_generated_entry_points_correct(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        runner.invoke(app, ["init-block-package", "scistudio-blocks-srs"])
        content = (tmp_path / "scistudio-blocks-srs" / "pyproject.toml").read_text()
        assert '[project.entry-points."scistudio.blocks"]' in content
        assert 'scistudio_blocks_srs = "scistudio_blocks_srs:get_blocks"' in content

    def test_generated_init_callable_protocol(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        runner.invoke(app, ["init-block-package", "scistudio-blocks-srs"])
        content = (tmp_path / "scistudio-blocks-srs" / "src" / "scistudio_blocks_srs" / "__init__.py").read_text()
        assert "def get_blocks() -> tuple[PackageInfo, list[type]]:" in content
        assert "PackageInfo" in content
        assert "ExampleBlock" in content
