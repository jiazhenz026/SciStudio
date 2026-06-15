from __future__ import annotations

import sys
import zipfile
from pathlib import Path

from scistudio.packages.validation.inventory import build_inventory


def test_source_inventory_exposes_only_declared_monorepo_dependencies(tmp_path: Path) -> None:
    packages_root = tmp_path / "packages"
    dependency_root = _write_project(packages_root / "dep", "scistudio-blocks-dep")
    unused_root = _write_project(packages_root / "unused", "scistudio-blocks-unused")
    consumer_root = _write_project(
        packages_root / "consumer",
        "scistudio-blocks-consumer",
        dependencies=("scistudio-blocks-dep>=0.1",),
    )

    inventory = build_inventory(consumer_root)

    assert consumer_root / "src" in inventory.import_paths
    assert dependency_root / "src" in inventory.import_paths
    assert unused_root / "src" not in inventory.import_paths


def test_source_inventory_keeps_unknown_scistudio_entry_point_groups(tmp_path: Path) -> None:
    root = _write_project(tmp_path / "pkg", "scistudio-blocks-unknown-group")
    root.joinpath("pyproject.toml").write_text(
        """[project]
name = "scistudio-blocks-unknown-group"
version = "0.0.0"

[project.entry-points."scistudio.unknown"]
bad = "pkg:get_bad"

[tool.setuptools.packages.find]
where = ["src"]
""",
        encoding="utf-8",
    )

    inventory = build_inventory(root)

    assert [entry_point.group for entry_point in inventory.entry_points] == ["scistudio.unknown"]


def test_wheel_inventory_reads_distribution_entry_points(tmp_path: Path) -> None:
    wheel_path = tmp_path / "pv_wheel-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as wheel:
        wheel.writestr("pv_wheel/__init__.py", "def get_types():\n    return []\n")
        wheel.writestr("pv_wheel-0.1.0.dist-info/METADATA", "Name: pv-wheel\nVersion: 0.1.0\n")
        wheel.writestr(
            "pv_wheel-0.1.0.dist-info/entry_points.txt",
            "[scistudio.types]\nmain = pv_wheel:get_types\n",
        )

    inventory = build_inventory(wheel_path)

    assert inventory.inventory.package.name == "pv-wheel"
    assert inventory.inventory.package.version == "0.1.0"
    assert inventory.entry_points[0].group == "scistudio.types"


def test_candidate_import_context_removes_source_modules(tmp_path: Path) -> None:
    from scistudio.packages.validation.inventory import candidate_import_context

    root = _write_project(tmp_path / "pkg", "scistudio-blocks-module-cleanup")
    package_dir = root / "src" / "shared_candidate"
    package_dir.mkdir()
    package_dir.joinpath("__init__.py").write_text("VALUE = 'loaded'\n", encoding="utf-8")
    inventory = build_inventory(root)
    sys.modules.pop("shared_candidate", None)

    with candidate_import_context(inventory):
        __import__("shared_candidate")
        assert "shared_candidate" in sys.modules

    assert "shared_candidate" not in sys.modules


def test_candidate_import_context_keeps_declared_dependency_modules(tmp_path: Path) -> None:
    from scistudio.packages.validation.inventory import candidate_import_context

    packages_root = tmp_path / "packages"
    dependency_root = _write_project(packages_root / "dep", "scistudio-blocks-dep")
    dependency_package_dir = dependency_root / "src" / "scistudio_blocks_dep"
    dependency_package_dir.joinpath("__init__.py").write_text("VALUE = 'dependency'\n", encoding="utf-8")
    consumer_root = _write_project(
        packages_root / "consumer",
        "scistudio-blocks-consumer",
        dependencies=("scistudio-blocks-dep>=0.1",),
    )
    candidate_package_dir = consumer_root / "src" / "scistudio_blocks_consumer"
    candidate_package_dir.joinpath("__init__.py").write_text("VALUE = 'candidate'\n", encoding="utf-8")
    inventory = build_inventory(consumer_root)
    sys.modules.pop("scistudio_blocks_consumer", None)
    sys.modules.pop("scistudio_blocks_dep", None)

    with candidate_import_context(inventory):
        __import__("scistudio_blocks_consumer")
        __import__("scistudio_blocks_dep")

    assert "scistudio_blocks_consumer" not in sys.modules
    assert "scistudio_blocks_dep" in sys.modules
    sys.modules.pop("scistudio_blocks_dep", None)


def _write_project(root: Path, name: str, dependencies: tuple[str, ...] = ()) -> Path:
    package_dir = root / "src" / name.replace("-", "_")
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    dependency_lines = "".join(f'    "{dependency}",\n' for dependency in dependencies)
    root.joinpath("pyproject.toml").write_text(
        f"""[project]
name = "{name}"
version = "0.0.0"
dependencies = [
{dependency_lines}]

[tool.setuptools.packages.find]
where = ["src"]
""",
        encoding="utf-8",
    )
    return root
