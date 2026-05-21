"""Tests for workflow path portability (#506).

Verifies that absolute paths in block configs are relativized on save
and absolutified on load, using forward slashes in YAML.
"""

from __future__ import annotations

from pathlib import Path

from scistudio.workflow.serializer import absolutify_paths, relativify_paths

# Sample config schema with file_browser and directory_browser widgets.
SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "ui_widget": "file_browser"},
        "output_dir": {"type": "string", "ui_widget": "directory_browser"},
        "name": {"type": "string"},
        "timeout": {"type": "integer"},
    },
}


class TestRelativifyPaths:
    """Test relativify_paths utility."""

    def test_converts_path_under_project(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        data_file = project_dir / "data" / "raw" / "sample.tif"
        data_file.parent.mkdir(parents=True)
        data_file.touch()

        config = {"path": str(data_file), "name": "test"}
        result = relativify_paths(config, str(project_dir), SCHEMA)

        assert result["path"] == "data/raw/sample.tif"
        assert result["name"] == "test"  # non-path field unchanged

    def test_keeps_path_outside_project(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        external_file = tmp_path / "external" / "data.csv"
        external_file.parent.mkdir(parents=True)
        external_file.touch()

        config = {"path": str(external_file)}
        result = relativify_paths(config, str(project_dir), SCHEMA)

        # Path outside project dir should remain absolute.
        assert Path(result["path"]).is_absolute()

    def test_uses_forward_slashes(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        nested = project_dir / "sub" / "dir" / "file.csv"
        nested.parent.mkdir(parents=True)
        nested.touch()

        config = {"path": str(nested)}
        result = relativify_paths(config, str(project_dir), SCHEMA)

        assert "\\" not in result["path"]
        assert result["path"] == "sub/dir/file.csv"

    def test_handles_directory_browser(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        output = project_dir / "results"
        output.mkdir()

        config = {"output_dir": str(output)}
        result = relativify_paths(config, str(project_dir), SCHEMA)

        assert result["output_dir"] == "results"

    def test_ignores_empty_value(self, tmp_path: Path) -> None:
        config = {"path": "", "name": "test"}
        result = relativify_paths(config, str(tmp_path), SCHEMA)
        assert result["path"] == ""

    def test_ignores_none_value(self, tmp_path: Path) -> None:
        config = {"path": None, "name": "test"}
        result = relativify_paths(config, str(tmp_path), SCHEMA)
        assert result["path"] is None

    def test_no_path_keys_in_schema(self, tmp_path: Path) -> None:
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        config = {"name": "test"}
        result = relativify_paths(config, str(tmp_path), schema)
        assert result == config


class TestAbsolutifyPaths:
    """Test absolutify_paths utility."""

    def test_resolves_relative_path(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "data").mkdir()

        config = {"path": "data/sample.tif"}
        result = absolutify_paths(config, str(project_dir), SCHEMA)

        expected = str((project_dir / "data" / "sample.tif").resolve())
        assert result["path"] == expected

    def test_leaves_absolute_path_unchanged(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        abs_path = str(tmp_path / "external" / "file.csv")
        config = {"path": abs_path}
        result = absolutify_paths(config, str(project_dir), SCHEMA)

        assert result["path"] == abs_path

    def test_round_trip(self, tmp_path: Path) -> None:
        """relativify -> absolutify should return the original absolute path."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        data_file = project_dir / "data" / "raw" / "image.tif"
        data_file.parent.mkdir(parents=True)
        data_file.touch()

        original = {"path": str(data_file.resolve()), "output_dir": str(project_dir / "results")}
        (project_dir / "results").mkdir()

        relative = relativify_paths(original, str(project_dir), SCHEMA)
        restored = absolutify_paths(relative, str(project_dir), SCHEMA)

        assert Path(restored["path"]).resolve() == data_file.resolve()
        assert Path(restored["output_dir"]).resolve() == (project_dir / "results").resolve()
