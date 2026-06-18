"""Tests for desktop local package installation."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

from scistudio.blocks.registry import BlockRegistry
from scistudio.desktop.package_installer import PackageInstallError, install_local_package


def _package_init(block_name: str, package_name: str, version: str = "0.1.0") -> str:
    return (
        "from typing import Any\n"
        "\n"
        "from scistudio.blocks.base.block import Block\n"
        "from scistudio.blocks.base.config import BlockConfig\n"
        "from scistudio.blocks.base.package_info import PackageInfo\n"
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
        f'    return PackageInfo(name="{package_name}", version="{version}"), [{block_name}]\n'
    )


def _write_source_package(
    root: Path,
    *,
    dist_name: str,
    module_name: str,
    block_name: str,
    package_name: str,
    version: str = "0.1.0",
) -> Path:
    package_root = root / dist_name
    module_dir = package_root / "src" / module_name
    module_dir.mkdir(parents=True)
    (package_root / "pyproject.toml").write_text(
        f'[project]\nname = "{dist_name}"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    (module_dir / "__init__.py").write_text(
        _package_init(block_name, package_name, version),
        encoding="utf-8",
    )
    return package_root


def test_install_source_directory_registers_blocks(tmp_path: Path) -> None:
    source_root = _write_source_package(
        tmp_path / "source",
        dist_name="scistudio-blocks-localprobe",
        module_name="scistudio_blocks_localprobe",
        block_name="LocalProbeBlock",
        package_name="Local Probe",
        version="0.3.0",
    )
    install_root = tmp_path / "installed"

    result = install_local_package(source_root, install_root=install_root)

    assert result.package_name == "scistudio-blocks-localprobe"
    assert result.version == "0.3.0"
    assert result.modules == ("scistudio_blocks_localprobe",)
    assert result.install_path == install_root / "scistudio-blocks-localprobe-0.3.0"
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_path"] == str(source_root.resolve())

    registry = BlockRegistry()
    registry.add_package_src_dir(install_root)
    registry.scan()
    spec = registry.get_spec("LocalProbeBlock")
    assert spec is not None
    assert spec.source == "package_src"
    assert spec.module_path == "scistudio_blocks_localprobe"
    assert spec.package_name == "Local Probe"
    assert str(result.install_path / "src") not in sys.path


def test_install_wheel_registers_flat_module_layout(tmp_path: Path) -> None:
    wheel_path = tmp_path / "scistudio_blocks_wheelprobe-0.2.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as archive:
        archive.writestr(
            "scistudio_blocks_wheelprobe/__init__.py",
            _package_init("WheelProbeBlock", "Wheel Probe", "0.2.0"),
        )
        archive.writestr(
            "scistudio_blocks_wheelprobe-0.2.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: scistudio-blocks-wheelprobe\nVersion: 0.2.0\n",
        )

    install_root = tmp_path / "installed"
    result = install_local_package(wheel_path, install_root=install_root)

    assert result.package_name == "scistudio-blocks-wheelprobe"
    assert result.version == "0.2.0"
    assert (result.install_path / "scistudio_blocks_wheelprobe" / "__init__.py").is_file()

    registry = BlockRegistry()
    registry.add_package_src_dir(install_root)
    registry.scan()
    spec = registry.get_spec("WheelProbeBlock")
    assert spec is not None
    assert spec.source == "package_src"
    assert spec.module_path == "scistudio_blocks_wheelprobe"
    assert spec.package_name == "Wheel Probe"


def test_install_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "bad-package.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.py", "print('nope')\n")

    with pytest.raises(PackageInstallError, match="outside its install root"):
        install_local_package(archive_path, install_root=tmp_path / "installed")
