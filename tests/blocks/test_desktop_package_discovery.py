"""Tests for ADR-037 desktop hard-installed source package discovery."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from scistudio.blocks.registry import BlockRegistry
from scistudio.desktop import paths as desktop_paths


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


def test_scan_discovers_env_package_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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


def test_scan_discovers_desktop_resource_packages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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


def test_add_package_src_dir_accepts_flat_installed_package(tmp_path: Path) -> None:
    packages_dir = tmp_path / "installed-packages"
    package_root = packages_dir / "scistudio-blocks-flatprobe-0.1.0"
    module_dir = package_root / "scistudio_blocks_flatprobe"
    module_dir.mkdir(parents=True)
    (module_dir / "__init__.py").write_text(
        "from typing import Any\n"
        "\n"
        "from scistudio.blocks.base.config import BlockConfig\n"
        "from scistudio.blocks.base.package_info import PackageInfo\n"
        "from scistudio.blocks.base.block import Block\n"
        "\n"
        "class FlatProbeBlock(Block):\n"
        '    name = "FlatProbeBlock"\n'
        "    input_ports = []\n"
        "    output_ports = []\n"
        '    config_schema = {"type": "object", "properties": {}}\n'
        "\n"
        "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
        "        return {}\n"
        "\n"
        "def get_block_package():\n"
        '    return PackageInfo(name="Flat Probe", version="0.1.0"), [FlatProbeBlock]\n',
        encoding="utf-8",
    )

    registry = BlockRegistry()
    registry.add_package_src_dir(packages_dir)
    registry.scan()

    spec = registry.get_spec("FlatProbeBlock")
    assert spec is not None
    assert spec.source == "package_src"
    assert spec.module_path == "scistudio_blocks_flatprobe"
    assert spec.package_name == "Flat Probe"


def test_scan_imports_source_package_with_per_package_runtime_dependencies(tmp_path: Path) -> None:
    packages_dir = tmp_path / "installed-packages"
    package_root = packages_dir / "scistudio-blocks-runtimeprobe-0.1.0"
    module_dir = package_root / "src" / "scistudio_blocks_runtimeprobe"
    runtime_dir = package_root / "site-packages"
    module_dir.mkdir(parents=True)
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "runtime_dep.py").write_text("VALUE = 'runtime-ok'\n", encoding="utf-8")
    (package_root / "pyproject.toml").write_text(
        '[project]\nname = "scistudio-blocks-runtimeprobe"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (module_dir / "__init__.py").write_text(
        "from typing import Any\n"
        "\n"
        "import runtime_dep\n"
        "from scistudio.blocks.base.config import BlockConfig\n"
        "from scistudio.blocks.base.package_info import PackageInfo\n"
        "from scistudio.blocks.base.block import Block\n"
        "\n"
        "class RuntimeProbeBlock(Block):\n"
        '    name = "RuntimeProbeBlock"\n'
        "    description = runtime_dep.VALUE\n"
        "    input_ports = []\n"
        "    output_ports = []\n"
        '    config_schema = {"type": "object", "properties": {}}\n'
        "\n"
        "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
        "        return {}\n"
        "\n"
        "def get_block_package():\n"
        '    return PackageInfo(name="Runtime Probe", version="0.1.0"), [RuntimeProbeBlock]\n',
        encoding="utf-8",
    )

    registry = BlockRegistry()
    registry.add_package_src_dir(packages_dir)
    registry.scan()

    spec = registry.get_spec("RuntimeProbeBlock")
    assert spec is not None
    assert spec.description == "runtime-ok"
    assert spec.source == "package_src"
    assert str(module_dir.parent) not in sys.path
    assert str(runtime_dir) not in sys.path


def test_tier1_dropin_imports_shared_user_python_dependency(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(desktop_paths, "_platformdirs_dir", lambda kind: tmp_path / kind)
    runtime_dir = desktop_paths.user_python_site_dir()
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "user_dep.py").write_text("VALUE = 'user-dep-ok'\n", encoding="utf-8")

    scan_dir = tmp_path / "blocks"
    scan_dir.mkdir()
    (scan_dir / "user_dep_block.py").write_text(
        "from typing import Any\n"
        "\n"
        "import user_dep\n"
        "from scistudio.blocks.base.config import BlockConfig\n"
        "from scistudio.blocks.base.block import Block\n"
        "\n"
        "class UserDepProbeBlock(Block):\n"
        '    name = "UserDepProbeBlock"\n'
        "    description = user_dep.VALUE\n"
        "    input_ports = []\n"
        "    output_ports = []\n"
        '    config_schema = {"type": "object", "properties": {}}\n'
        "\n"
        "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
        "        return {}\n",
        encoding="utf-8",
    )

    registry = BlockRegistry()
    registry.add_scan_dir(scan_dir)
    registry.scan()

    spec = registry.get_spec("UserDepProbeBlock")
    assert spec is not None
    assert spec.description == "user-dep-ok"
    assert str(runtime_dir) not in sys.path


def test_scan_reloads_reinstalled_package_from_same_source_path(tmp_path: Path) -> None:
    packages_dir = tmp_path / "installed-packages"
    dist_name = "scistudio-blocks-reloadprobe-0.1.0"
    module_name = "scistudio_blocks_reloadprobe"
    package_root = packages_dir / dist_name

    _write_source_package(
        packages_dir,
        dist_name=dist_name,
        module_name=module_name,
        block_name="ReloadProbeBlockV1",
        package_name="Reload Probe",
    )
    registry = BlockRegistry()
    registry.add_package_src_dir(packages_dir)
    registry.scan()
    assert registry.get_spec("ReloadProbeBlockV1") is not None
    assert registry.get_spec("ReloadProbeBlockV2") is None

    shutil.rmtree(package_root)
    _write_source_package(
        packages_dir,
        dist_name=dist_name,
        module_name=module_name,
        block_name="ReloadProbeBlockV2",
        package_name="Reload Probe",
    )
    registry = BlockRegistry()
    registry.add_package_src_dir(packages_dir)
    registry.scan()

    assert registry.get_spec("ReloadProbeBlockV1") is None
    assert registry.get_spec("ReloadProbeBlockV2") is not None
