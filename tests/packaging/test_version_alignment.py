"""Regression tests for packaging/version metadata alignment."""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement

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


# NOTE (issue #1770): ``test_plugin_core_dependency_accepts_current_root_version``
# was removed. It read ``packages/scistudio-blocks-*/pyproject.toml`` to assert
# each plugin's ``scistudio>=`` dependency floor accepted the current core
# version. The domain packages were decoupled into their own repositories, so
# that floor check now belongs to each package repo's own CI; core no longer
# vendors those pyproject files.


def test_core_runtime_dependencies_cover_core_imports_without_image_decoders() -> None:
    """Core ships direct runtime imports, but package image decoders stay out."""
    pyproject = _load_toml(REPO_ROOT / "pyproject.toml")
    dependencies = pyproject["project"]["dependencies"]
    names = {Requirement(dep).name.lower() for dep in dependencies}

    assert {"numpy", "packaging", "matplotlib", "pandas"}.issubset(names)
    assert "tifffile" not in names
    assert "pillow" not in names


def test_core_source_does_not_import_package_owned_image_decoders() -> None:
    """TIFF/Pillow decoding belongs to imaging package code, not core."""
    forbidden = ("import tifffile", "from tifffile", "from PIL", "import PIL")
    offenders: list[str] = []
    for path in (REPO_ROOT / "src" / "scistudio").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            if needle in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)} contains {needle!r}")

    assert offenders == []


def test_readme_declares_alpha_and_points_to_releases() -> None:
    """README must declare the project status and route users to a release.

    The README was rewritten (#1850) into a short landing page that no longer
    hard-codes the package version (which would drift every release); the
    authoritative version lives in package metadata, the Releases page, and the
    per-symbol stability tiers in the API reference. This test pins the new
    contract instead: the README advertises the development status and links to
    the Releases page so users can find the current build.
    """
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "alpha" in readme.lower(), "README must state the development status (alpha)"
    assert "/releases" in readme, "README must link users to the Releases page"
