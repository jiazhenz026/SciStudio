"""Tests for ADR-037 desktop hard-installed source package discovery."""

from __future__ import annotations

import sys
from pathlib import Path

from scistudio.blocks.registry import BlockRegistry


def _write_source_package(
    packages_dir: Path,
    *,
    dist_name: str,
    module_name: str,
    block_name: str,
    package_name: str,
) -> Path:
    package_root = packages_dir / dist_name
    module_dir = package_root / "src" / module_name
    module_dir.mkdir(parents=True)
    (package_root / "pyproject.toml").write_text(
        f'[project]\nname = "{dist_name}"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (module_dir / "__init__.py").write_text(
        "from typing import Any\n"
        "\n"
        "from scistudio.blocks.base.config import BlockConfig\n"
        "from scistudio.blocks.base.package_info import PackageInfo\n"
        "from scistudio.blocks.base.block import Block\n"
        "\n"
        f"class {block_name}(Block):\n"
        f'    name = "{block_name}"\n'
        "    input_ports = []\n"
        "    output_ports = []\n"
        '    config_schema = {"type": "object", "properties": {}}\n'
        "\n"
        "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
        "        return {}\n"
        "\n"
        "def get_block_package():\n"
        f'    return PackageInfo(name="{package_name}", version="0.1.0"), [{block_name}]\n',
        encoding="utf-8",
    )
    return package_root / "src"


def test_scan_discovers_env_package_dirs(monkeypatch, tmp_path: Path) -> None:
    packages_dir = tmp_path / "env-packages"
    src_dir = _write_source_package(
        packages_dir,
        dist_name="scistudio-blocks-envprobe",
        module_name="scistudio_blocks_envprobe",
        block_name="EnvProbeBlock",
        package_name="Env Probe",
    )
    monkeypatch.setenv("SCISTUDIO_PLUGIN_PACKAGE_DIRS", str(packages_dir))

    registry = BlockRegistry()
    registry.scan()

    spec = registry.get_spec("EnvProbeBlock")
    assert spec is not None
    assert spec.source == "package_src"
    assert spec.module_path == "scistudio_blocks_envprobe"
    assert spec.package_name == "Env Probe"
    assert registry.packages()["Env Probe"].version == "0.1.0"
    assert str(src_dir) not in sys.path


def test_scan_discovers_desktop_resource_packages(monkeypatch, tmp_path: Path) -> None:
    resources_dir = tmp_path / "resources"
    packages_dir = resources_dir / "packages"
    _write_source_package(
        packages_dir,
        dist_name="scistudio-blocks-resourceprobe",
        module_name="scistudio_blocks_resourceprobe",
        block_name="ResourceProbeBlock",
        package_name="Resource Probe",
    )
    monkeypatch.setenv("SCISTUDIO_DESKTOP_RESOURCES", str(resources_dir))

    registry = BlockRegistry()
    registry.scan()

    spec = registry.get_spec("ResourceProbeBlock")
    assert spec is not None
    assert spec.source == "package_src"
    assert spec.package_name == "Resource Probe"


def test_add_package_src_dir_accepts_resolved_src_directory(tmp_path: Path) -> None:
    packages_dir = tmp_path / "manual-packages"
    src_dir = _write_source_package(
        packages_dir,
        dist_name="scistudio-blocks-manualprobe",
        module_name="scistudio_blocks_manualprobe",
        block_name="ManualProbeBlock",
        package_name="Manual Probe",
    )

    registry = BlockRegistry()
    registry.add_package_src_dir(src_dir)
    registry.scan()

    spec = registry.get_spec("ManualProbeBlock")
    assert spec is not None
    assert spec.source == "package_src"
    assert spec.package_name == "Manual Probe"
