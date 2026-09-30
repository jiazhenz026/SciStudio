"""Desktop source-package discovery coverage for non-block plugin surfaces.

Covers both the bundled desktop app (``SCISTUDIO_BUNDLED=1``) and the
non-bundled desktop runtime. Issue #1885: type module-glob discovery must run
unconditionally, matching block discovery, so plugin types are not silently
dropped when the bundled flag is absent. (The previewer half left with the
legacy previewer registry, #2493.)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scistudio.core.types.registry import TypeRegistry
from scistudio.desktop import paths as desktop_paths


def _write_type_package(packages_dir: Path) -> Path:
    package_root = packages_dir / "scistudio-blocks-typeprobe-0.1.0"
    module_dir = package_root / "src" / "scistudio_blocks_typeprobe"
    module_dir.mkdir(parents=True)
    (package_root / "pyproject.toml").write_text(
        """[project]
name = "scistudio-blocks-typeprobe"
version = "0.1.0"

[project.entry-points."scistudio.types"]
typeprobe = "scistudio_blocks_typeprobe:get_types"
""",
        encoding="utf-8",
    )
    (module_dir / "__init__.py").write_text(
        "from scistudio.core.types.series import Series\n"
        "\n"
        "class DesktopSpectrum(Series):\n"
        '    """Desktop package source-discovered type."""\n'
        "\n"
        "def get_types():\n"
        "    return [DesktopSpectrum]\n",
        encoding="utf-8",
    )
    return package_root / "src"


@pytest.fixture
def bundled_desktop_packages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point desktop user/plugin dirs at a temporary bundled-like install."""
    monkeypatch.setenv("SCISTUDIO_BUNDLED", "1")
    monkeypatch.setattr(desktop_paths, "_platformdirs_dir", lambda kind: tmp_path / kind)
    packages_dir = tmp_path / "packages"
    monkeypatch.setenv("SCISTUDIO_PLUGIN_PACKAGE_DIRS", str(packages_dir))
    return packages_dir


@pytest.fixture
def desktop_packages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point desktop plugin dirs at a temp install *without* ``SCISTUDIO_BUNDLED``.

    Issue #1885: the non-bundled desktop runtime is the case where plugin type
    and previewer discovery used to silently fail — the module-glob scan was
    gated behind ``SCISTUDIO_BUNDLED == "1"`` while blocks scanned
    unconditionally. This fixture mirrors :func:`bundled_desktop_packages`
    with the bundled flag explicitly absent.
    """
    monkeypatch.delenv("SCISTUDIO_BUNDLED", raising=False)
    monkeypatch.setattr(desktop_paths, "_platformdirs_dir", lambda kind: tmp_path / kind)
    packages_dir = tmp_path / "packages"
    monkeypatch.setenv("SCISTUDIO_PLUGIN_PACKAGE_DIRS", str(packages_dir))
    return packages_dir


def test_type_registry_discovers_bundled_desktop_source_package_types(
    bundled_desktop_packages: Path,
) -> None:
    """Bundled desktop source packages must register ``get_types()`` payloads."""
    src_dir = _write_type_package(bundled_desktop_packages)

    registry = TypeRegistry()
    registry.scan_all()

    assert "DesktopSpectrum" in registry.all_types()
    resolved = registry.resolve(["DataObject", "Series", "DesktopSpectrum"])
    assert resolved is not None
    assert resolved.__name__ == "DesktopSpectrum"
    assert str(src_dir.resolve()) not in sys.path


def test_type_registry_discovers_non_bundled_desktop_source_package_types(
    desktop_packages: Path,
) -> None:
    """#1885: plugin types must register in a non-bundled desktop run too.

    Regression guard: before the fix the module-glob scan was gated behind
    ``SCISTUDIO_BUNDLED == "1"``, so without that flag the type never
    registered even though the same package's blocks would.
    """
    src_dir = _write_type_package(desktop_packages)

    registry = TypeRegistry()
    registry.scan_all()

    assert "DesktopSpectrum" in registry.all_types()
    resolved = registry.resolve(["DataObject", "Series", "DesktopSpectrum"])
    assert resolved is not None
    assert resolved.__name__ == "DesktopSpectrum"
    assert str(src_dir.resolve()) not in sys.path
