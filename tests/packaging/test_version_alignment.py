"""Regression tests for packaging/version metadata alignment."""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_toml(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def test_root_project_and_commitizen_versions_match() -> None:
    """The published package version and commitizen version must stay aligned."""
    pyproject = _load_toml(REPO_ROOT / "pyproject.toml")

    project_version = pyproject["project"]["version"]
    commitizen_version = pyproject["tool"]["commitizen"]["version"]

    assert project_version == commitizen_version


def test_plugin_core_dependency_accepts_current_root_version() -> None:
    """Plugin dependency floors must accept the currently published core version."""
    pyproject = _load_toml(REPO_ROOT / "pyproject.toml")
    root_version = Version(pyproject["project"]["version"])

    plugin_files = [
        REPO_ROOT / "packages" / "scistudio-blocks-imaging" / "pyproject.toml",
        REPO_ROOT / "packages" / "scistudio-blocks-lcms" / "pyproject.toml",
        REPO_ROOT / "packages" / "scistudio-blocks-srs" / "pyproject.toml",
    ]

    for plugin_file in plugin_files:
        plugin = _load_toml(plugin_file)
        dependencies = plugin["project"]["dependencies"]
        req = next(Requirement(dep) for dep in dependencies if dep.startswith("scistudio>="))
        assert root_version in req.specifier, f"{plugin_file} does not accept core version {root_version}"


def test_readme_current_status_mentions_root_version() -> None:
    """README should advertise the same current version as package metadata."""
    pyproject = _load_toml(REPO_ROOT / "pyproject.toml")
    root_version = pyproject["project"]["version"]

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.count(f"(v{root_version})") >= 2
