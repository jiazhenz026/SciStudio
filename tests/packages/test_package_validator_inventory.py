from __future__ import annotations

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
